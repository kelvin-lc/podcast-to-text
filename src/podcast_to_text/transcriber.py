"""Audio transcription using Azure Speech SDK."""

import os
import tempfile
import time
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# 15 minutes in milliseconds
SEGMENT_DURATION_MS = 15 * 60 * 1000


def split_audio(audio_path: str, segment_duration_ms: int = SEGMENT_DURATION_MS) -> list[str]:
    """
    Split long audio into segments using pydub.

    Args:
        audio_path: Path to the audio file
        segment_duration_ms: Duration of each segment in milliseconds

    Returns:
        List of paths to temporary segment files
    """
    console.print("[bold blue]Splitting audio into segments...[/bold blue]")

    audio = AudioSegment.from_file(audio_path)
    total_duration = len(audio)
    segments = []

    temp_dir = tempfile.mkdtemp(prefix="podcast_segments_")

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

            segment_path = os.path.join(temp_dir, f"segment_{i:04d}.wav")
            segment.export(segment_path, format="wav")
            segments.append(segment_path)

            progress.update(task, advance=1)

    console.print(f"[bold green]Split into {len(segments)} segments[/bold green]")
    return segments


def transcribe_segment(segment_path: str, speech_key: str, speech_region: str) -> list[dict]:
    """
    Transcribe a single audio segment using Azure Speech SDK Continuous Recognition.

    Args:
        segment_path: Path to the audio segment
        speech_key: Azure Speech API key
        speech_region: Azure Speech region

    Returns:
        List of transcription results with timestamps
    """
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = "zh-CN"

    # Enable detailed output with timing
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    audio_config = speechsdk.AudioConfig(filename=segment_path)
    speech_recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config, audio_config=audio_config
    )

    results = []
    done = False

    def recognized_callback(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            # Get timing info from the result
            offset_ticks = evt.result.offset  # in 100-nanosecond units
            duration_ticks = evt.result.duration
            start_seconds = offset_ticks / 10_000_000
            end_seconds = (offset_ticks + duration_ticks) / 10_000_000

            results.append({
                "start": start_seconds,
                "end": end_seconds,
                "text": evt.result.text,
            })

    def stopped_callback(evt):
        nonlocal done
        done = True

    speech_recognizer.recognized.connect(recognized_callback)
    speech_recognizer.session_stopped.connect(stopped_callback)
    speech_recognizer.canceled.connect(stopped_callback)

    speech_recognizer.start_continuous_recognition()

    while not done:
        time.sleep(0.5)

    speech_recognizer.stop_continuous_recognition()

    return results


def transcribe_audio(audio_path: str, speech_key: str, speech_region: str) -> list[dict]:
    """
    Transcribe audio file, handling long audio by splitting into segments.

    Args:
        audio_path: Path to the audio file
        speech_key: Azure Speech API key
        speech_region: Azure Speech region

    Returns:
        List of transcription segments with timestamps:
        [{"start": 0.0, "end": 5.2, "text": "..."}, ...]
    """
    # Check audio duration to decide if splitting is needed
    audio = AudioSegment.from_file(audio_path)
    duration_ms = len(audio)
    duration_minutes = duration_ms / 60000

    console.print(f"[bold]Audio duration:[/bold] {duration_minutes:.1f} minutes")

    if duration_ms <= SEGMENT_DURATION_MS:
        # Short audio, process directly
        console.print("[bold blue]Transcribing audio...[/bold blue]")
        segments = transcribe_segment(audio_path, speech_key, speech_region)
        console.print(f"[bold green]Transcription complete: {len(segments)} segments[/bold green]")
        return segments

    # Long audio, split and process
    segment_files = split_audio(audio_path)

    all_results = []
    time_offset = 0.0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Transcribing segments", total=len(segment_files))

        for segment_file in segment_files:
            segment_results = transcribe_segment(segment_file, speech_key, speech_region)

            # Adjust timestamps with offset
            for result in segment_results:
                result["start"] += time_offset
                result["end"] += time_offset
                all_results.append(result)

            # Get segment duration for next offset
            seg_audio = AudioSegment.from_file(segment_file)
            time_offset += len(seg_audio) / 1000.0

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

    console.print(f"[bold green]Transcription complete: {len(all_results)} segments[/bold green]")
    return all_results


def segments_to_text(segments: list[dict]) -> str:
    """Convert transcription segments to plain text."""
    return "".join(seg["text"] for seg in segments)
