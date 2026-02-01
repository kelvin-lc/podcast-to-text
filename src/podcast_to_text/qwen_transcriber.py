"""Qwen3-ASR transcription using OpenAI-compatible API."""

import json
import re
from pathlib import Path

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console()

# Model name for Qwen3-ASR
QWEN_ASR_MODEL = "/models/Qwen3-ASR-1.7B"


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
    stream: bool = True,
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

    if stream:
        return _transcribe_streaming(audio_path, url, language)
    else:
        return _transcribe_non_streaming(audio_path, url, language)


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


def _transcribe_non_streaming(audio_path: str, url: str, language: str) -> list[dict]:
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

    console.print(
        f"[bold green]Transcription complete: {len(segments)} segments[/bold green]"
    )
    return segments
