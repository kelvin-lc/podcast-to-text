"""Qwen3-ASR transcription using OpenAI-compatible API."""

import re
from pathlib import Path

import httpx
from rich.console import Console

console = Console()


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


def transcribe_audio_qwen(
    audio_path: str,
    api_url: str,
    language: str = "zh",
) -> list[dict]:
    """
    Transcribe audio using Qwen3-ASR API.

    Args:
        audio_path: Path to audio file
        api_url: Qwen ASR service URL
        language: Language code

    Returns:
        List of transcription segments [{"start": 0.0, "end": 5.2, "text": "..."}]
    """
    url = f"{api_url}/v1/audio/transcriptions"

    console.print("[bold blue]Transcribing with Qwen3-ASR...[/bold blue]")

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
        raise ValueError(f"Cannot connect to Qwen ASR at {api_url}")
    except httpx.TimeoutException:
        raise ValueError("Qwen ASR request timed out")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"Qwen ASR error: {e.response.status_code}")

    result = response.json()
    segments = _parse_response(result)

    console.print(
        f"[bold green]Transcription complete: {len(segments)} segments[/bold green]"
    )
    return segments
