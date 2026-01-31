"""CLI entry point for podcast-to-text."""

import sys
from pathlib import Path

import click
from rich.console import Console

from .config import Config
from .pipeline import Pipeline, PipelineContext
from .steps import (
    DownloadStep,
    TranscribeStep,
    FormatStep,
    SkipFormatStep,
    SaveStep,
    CleanupStep,
)

console = Console()


def create_pipeline(mode: str, skip_format: bool) -> Pipeline:
    """Create pipeline based on input mode."""
    steps = []

    if mode == "url":
        steps.append(DownloadStep())

    if mode in ("url", "audio"):
        steps.append(TranscribeStep())

    if skip_format:
        steps.append(SkipFormatStep())
    else:
        steps.append(FormatStep())

    steps.append(SaveStep())

    if mode == "url":
        steps.append(CleanupStep())

    return Pipeline(steps, console)


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

    # Build config
    config = Config.from_env()
    config = config.model_copy(
        update={
            "output_dir": Path(output),
            "audio_dir": Path(audio_dir),
            "keep_audio": keep_audio,
        }
    )

    # Build context
    ctx = PipelineContext(
        config=config,
        source_url=source,
        audio_path=Path(audio) if audio else None,
        text_path=Path(text) if text else None,
    )

    # Run pipeline
    try:
        pipeline = create_pipeline(mode, no_format)
        pipeline.run(ctx)
        console.print("\n[bold green]Done![/bold green]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
