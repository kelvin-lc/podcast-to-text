"""Qwen3-ASR transcription using OpenAI-compatible API."""

import json
import os
import re
import tempfile
from pathlib import Path

import httpx
from pydub import AudioSegment
from rich.console import Console
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.text import Text

console = Console()

# Model name for Qwen3-ASR
QWEN_ASR_MODEL = "/models/Qwen3-ASR-1.7B"

# Maximum file size in MB (server limit)
MAX_FILE_SIZE_MB = 25

# Segment duration for long audio (10 minutes)
SEGMENT_DURATION_MS = 10 * 60 * 1000


def _clean_text(text: str) -> str:
    """Clean Qwen ASR output text.

    Qwen3-ASR returns text in format: "language Chinese<asr_text>actual text"
    This function extracts the actual transcription.
    """
    # Extract text after <asr_text> tag if present
    match = re.search(r"<asr_text>(.*)$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_response(result: dict) -> list[dict]:
    """Convert Qwen ASR response to unified format."""
    # verbose_json format includes segments (if supported)
    if "segments" in result:
        return [
            {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": _clean_text(seg.get("text", "")),
            }
            for seg in result["segments"]
        ]

    # Simple json format only has text
    text = _clean_text(result.get("text", ""))
    return [{"start": 0, "end": 0, "text": text}]


def _get_file_size_mb(file_path: str) -> float:
    """Get file size in MB."""
    return os.path.getsize(file_path) / (1024 * 1024)


def _split_audio(audio_path: str, segment_duration_ms: int = SEGMENT_DURATION_MS) -> list[str]:
    """Split long audio into segments."""
    console.print("[bold blue]Splitting audio into segments...[/bold blue]")

    audio = AudioSegment.from_file(audio_path)
    total_duration = len(audio)
    segments = []

    temp_dir = tempfile.mkdtemp(prefix="qwen_asr_segments_")

    num_segments = (total_duration + segment_duration_ms - 1) // segment_duration_ms

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Splitting audio", total=num_segments)

        for i, start in enumerate(range(0, total_duration, segment_duration_ms)):
            end = min(start + segment_duration_ms, total_duration)
            segment = audio[start:end]

            # Export as mp3 for smaller file size
            segment_path = os.path.join(temp_dir, f"segment_{i:04d}.mp3")
            segment.export(segment_path, format="mp3", bitrate="64k")
            segments.append(segment_path)

            progress.update(task, advance=1)

    console.print(f"[bold green]Split into {len(segments)} segments[/bold green]")
    return segments


def transcribe_audio_qwen(
    audio_path: str,
    api_url: str,
    language: str = "zh",
    stream: bool = False,
) -> list[dict]:
    """
    Transcribe audio using Qwen3-ASR API.

    Args:
        audio_path: Path to audio file
        api_url: Qwen ASR service URL
        language: Language code
        stream: Use streaming mode for real-time output

    Returns:
        List of transcription segments [{"start": 0.0, "end": 5.2, "text": "..."}]
    """
    url = f"{api_url}/v1/audio/transcriptions"

    console.print("[bold blue]Transcribing with Qwen3-ASR...[/bold blue]")

    # Check file size
    file_size_mb = _get_file_size_mb(audio_path)
    console.print(f"[dim]Audio file size: {file_size_mb:.1f} MB[/dim]")

    if file_size_mb > MAX_FILE_SIZE_MB:
        # Need to split audio
        return _transcribe_long_audio(audio_path, url, language)
    else:
        # Direct transcription
        if stream:
            return _transcribe_streaming(audio_path, url, language)
        else:
            return _transcribe_non_streaming(audio_path, url, language)


def _transcribe_long_audio(audio_path: str, url: str, language: str) -> list[dict]:
    """Transcribe long audio by splitting into segments."""
    segment_files = _split_audio(audio_path)

    all_segments = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transcribing segments", total=len(segment_files))

        for segment_file in segment_files:
            # Transcribe segment
            segments = _transcribe_non_streaming(segment_file, url, language, show_progress=False)
            all_segments.extend(segments)

            # Clean up temp file
            os.remove(segment_file)

            progress.update(task, advance=1)

    # Clean up temp directory
    if segment_files:
        temp_dir = os.path.dirname(segment_files[0])
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

    # Combine all text into one segment
    full_text = "".join(seg["text"] for seg in all_segments)
    console.print(
        f"[bold green]Transcription complete: {len(full_text)} characters[/bold green]"
    )
    return [{"start": 0, "end": 0, "text": full_text}]


def _transcribe_streaming(audio_path: str, url: str, language: str) -> list[dict]:
    """Transcribe with streaming output for real-time progress."""
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (Path(audio_path).name, f)}
            data = {
                "model": QWEN_ASR_MODEL,
                "language": language,
                "response_format": "json",
                "stream": "true",
            }

            full_text = ""
            with httpx.stream(
                "POST", url, files=files, data=data, timeout=600
            ) as response:
                response.raise_for_status()

                # Use Rich Live for real-time display
                with Live(Text(""), console=console, refresh_per_second=10) as live:
                    for line in response.iter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                                if "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full_text += content
                                        # Show cleaned text in real-time
                                        display_text = _clean_text(full_text)
                                        if display_text:
                                            live.update(
                                                Text(f"  {display_text[:100]}...", style="dim")
                                                if len(display_text) > 100
                                                else Text(f"  {display_text}", style="dim")
                                            )
                            except json.JSONDecodeError:
                                continue

    except httpx.ConnectError:
        raise ValueError(f"Cannot connect to Qwen ASR at {url}")
    except httpx.TimeoutException:
        raise ValueError("Qwen ASR request timed out")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Qwen ASR error: {e.response.status_code}")

    text = _clean_text(full_text)
    segments = [{"start": 0, "end": 0, "text": text}]

    console.print(
        f"[bold green]Transcription complete: {len(text)} characters[/bold green]"
    )
    return segments


def _transcribe_non_streaming(
    audio_path: str, url: str, language: str, show_progress: bool = True
) -> list[dict]:
    """Transcribe without streaming (simpler, same speed for short audio)."""
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (Path(audio_path).name, f)}
            data = {
                "language": language,
                "response_format": "json",
            }
            response = httpx.post(url, files=files, data=data, timeout=600)

        response.raise_for_status()
    except httpx.ConnectError:
        raise ValueError(f"Cannot connect to Qwen ASR at {url}")
    except httpx.TimeoutException:
        raise ValueError("Qwen ASR request timed out")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Qwen ASR error: {e.response.status_code}")

    result = response.json()
    segments = _parse_response(result)

    if show_progress:
        console.print(
            f"[bold green]Transcription complete: {len(segments)} segments[/bold green]"
        )
    return segments
