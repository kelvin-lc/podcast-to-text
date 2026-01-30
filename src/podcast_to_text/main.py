"""CLI entry point for podcast-to-text."""

import os
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console

from .downloader import download_podcast
from .transcriber import transcribe_audio, segments_to_text
from .formatter import format_transcript, format_text

console = Console()


def load_config(need_speech: bool = True, need_openai: bool = True) -> dict:
    """Load configuration from environment variables."""
    load_dotenv()

    config = {
        "speech_key": os.getenv("AZURE_SPEECH_KEY"),
        "speech_region": os.getenv("AZURE_SPEECH_REGION"),
        "openai_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
        "openai_key": os.getenv("AZURE_OPENAI_KEY"),
        "openai_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    }

    # Validate required config
    if need_speech and (not config["speech_key"] or not config["speech_region"]):
        console.print(
            "[bold red]Error:[/bold red] AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set"
        )
        sys.exit(1)

    if need_openai and not all(
        [config["openai_endpoint"], config["openai_key"], config["openai_deployment"]]
    ):
        console.print(
            "[bold red]Error:[/bold red] AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY and "
            "AZURE_OPENAI_DEPLOYMENT must be set"
        )
        sys.exit(1)

    return config


import re


def sanitize_filename(title: str) -> str:
    """Sanitize title for use as filename."""
    # Remove invalid filename characters
    safe = re.sub(r'[<>:"/\\|?*]', "_", title)
    # Limit length
    return safe[:100].strip()


def generate_output_filename(output_dir: Path, title: str | None = None, prefix: str = "podcast") -> Path:
    """Generate output filename, using title if provided."""
    if title:
        safe_title = sanitize_filename(title)
        return output_dir / f"{safe_title}.md"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"{prefix}_{timestamp}.md"


@click.command()
@click.argument("source", required=False)
@click.option(
    "--audio",
    "-a",
    type=click.Path(exists=True),
    help="Local audio file to transcribe (skip download)",
)
@click.option(
    "--text",
    "-t",
    type=click.Path(exists=True),
    help="Raw transcript file to format (skip download and transcription)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="output",
    help="Output directory for the Markdown file",
)
@click.option(
    "--audio-dir",
    type=click.Path(),
    default="audio",
    help="Directory to cache downloaded audio",
)
@click.option(
    "--no-format",
    is_flag=True,
    default=False,
    help="Skip LLM formatting (output raw transcription only)",
)
@click.option(
    "--keep-audio",
    is_flag=True,
    default=False,
    help="Keep the downloaded audio file after processing",
)
def main(
    source: str | None,
    audio: str | None,
    text: str | None,
    output: str,
    audio_dir: str,
    no_format: bool,
    keep_audio: bool,
):
    """
    Convert podcast audio to formatted Markdown text.

    Three input modes:

    \b
    1. From URL (default):
       podcast-to-text "https://podcasts.apple.com/..."

    \b
    2. From local audio file:
       podcast-to-text --audio ./episode.mp3

    \b
    3. From raw transcript text:
       podcast-to-text --text ./raw-transcript.txt
    """
    console.print("[bold]Podcast to Text[/bold]\n")

    # Determine input mode
    if text:
        mode = "text"
    elif audio:
        mode = "audio"
    elif source:
        mode = "url"
    else:
        console.print(
            "[bold red]Error:[/bold red] Must provide a URL, --audio, or --text"
        )
        console.print("Run with --help for usage information.")
        sys.exit(1)

    # Ensure output directory exists
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        if mode == "text":
            # Mode 3: Format existing text
            console.print(f"[bold]Input:[/bold] {text} (text file)")

            config = load_config(need_speech=False, need_openai=not no_format)

            # Use text filename as title
            text_title = Path(text).stem

            console.print("\n[bold]Step 1: Read text file[/bold]")
            raw_text = Path(text).read_text(encoding="utf-8")
            console.print(f"  Read {len(raw_text)} characters")

            if no_format:
                console.print("\n[bold]Step 2: Skipping formatting[/bold]")
                final_text = raw_text
            else:
                console.print("\n[bold]Step 2: Format[/bold]")
                final_text = format_text(
                    raw_text,
                    config["openai_endpoint"],
                    config["openai_key"],
                    config["openai_deployment"],
                )

            # Save output
            console.print("\n[bold]Step 3: Save[/bold]")
            output_file = generate_output_filename(output_path, title=f"{text_title}_formatted")
            output_file.write_text(final_text, encoding="utf-8")
            console.print(f"[bold green]Saved to:[/bold green] {output_file}")

        elif mode == "audio":
            # Mode 2: Transcribe local audio
            console.print(f"[bold]Input:[/bold] {audio} (audio file)")

            config = load_config(need_speech=True, need_openai=not no_format)

            # Use audio filename as title
            audio_title = Path(audio).stem

            console.print("\n[bold]Step 1: Transcribe[/bold]")
            segments = transcribe_audio(
                audio,
                config["speech_key"],
                config["speech_region"],
            )

            if not segments:
                console.print("[bold red]Error:[/bold red] No transcription results")
                sys.exit(1)

            if no_format:
                console.print("\n[bold]Step 2: Skipping formatting[/bold]")
                final_text = segments_to_text(segments)
            else:
                console.print("\n[bold]Step 2: Format[/bold]")
                final_text = format_transcript(
                    segments,
                    config["openai_endpoint"],
                    config["openai_key"],
                    config["openai_deployment"],
                )

            # Save output
            console.print("\n[bold]Step 3: Save[/bold]")
            output_file = generate_output_filename(output_path, title=audio_title)
            output_file.write_text(final_text, encoding="utf-8")
            console.print(f"[bold green]Saved to:[/bold green] {output_file}")

        else:
            # Mode 1: Full pipeline from URL
            console.print(f"[bold]Input:[/bold] {source} (URL)")

            config = load_config(need_speech=True, need_openai=not no_format)

            audio_path = None
            episode_title = None

            # Step 1: Download podcast
            console.print("\n[bold]Step 1: Download[/bold]")
            audio_path, episode_title = download_podcast(source, audio_dir)

            # Step 2: Transcribe audio
            console.print("\n[bold]Step 2: Transcribe[/bold]")
            segments = transcribe_audio(
                audio_path,
                config["speech_key"],
                config["speech_region"],
            )

            if not segments:
                console.print("[bold red]Error:[/bold red] No transcription results")
                sys.exit(1)

            # Step 3: Format text (optional)
            if no_format:
                console.print("\n[bold]Step 3: Skipping formatting[/bold]")
                final_text = segments_to_text(segments)
            else:
                console.print("\n[bold]Step 3: Format[/bold]")
                final_text = format_transcript(
                    segments,
                    config["openai_endpoint"],
                    config["openai_key"],
                    config["openai_deployment"],
                )

            # Step 4: Save output
            console.print("\n[bold]Step 4: Save[/bold]")
            output_file = generate_output_filename(output_path, title=episode_title)
            output_file.write_text(final_text, encoding="utf-8")
            console.print(f"[bold green]Saved to:[/bold green] {output_file}")

            # Cleanup audio if not keeping
            if not keep_audio and audio_path:
                os.remove(audio_path)
                console.print("[dim]Audio file cleaned up[/dim]")

        console.print("\n[bold green]Done![/bold green]")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
