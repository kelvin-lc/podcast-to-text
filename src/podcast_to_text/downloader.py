"""Podcast downloader using yt-dlp and iTunes API fallback."""

import os
import re
import subprocess
from pathlib import Path

import requests
import yt_dlp
from rich.console import Console

console = Console()


def extract_apple_podcast_ids(url: str) -> tuple[str | None, str | None]:
    """
    Extract podcast ID and episode ID from Apple Podcast URL.

    Returns:
        Tuple of (podcast_id, episode_id) or (None, None) if not an Apple Podcast URL
    """
    # Pattern: https://podcasts.apple.com/.../id{podcast_id}?i={episode_id}
    podcast_match = re.search(r"/id(\d+)", url)
    episode_match = re.search(r"[?&]i=(\d+)", url)

    if podcast_match:
        podcast_id = podcast_match.group(1)
        episode_id = episode_match.group(1) if episode_match else None
        return podcast_id, episode_id

    return None, None


def get_episode_from_itunes_api(podcast_id: str, episode_id: str) -> dict | None:
    """
    Fetch episode info from iTunes API.

    Returns:
        Episode dict with 'episodeUrl' and 'trackName', or None if not found
    """
    api_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcastEpisode&limit=200"

    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()
        data = response.json()

        for result in data.get("results", []):
            if result.get("wrapperType") == "podcastEpisode":
                if str(result.get("trackId")) == episode_id:
                    return result

    except Exception as e:
        console.print(f"[yellow]iTunes API error: {e}[/yellow]")

    return None


def download_direct_audio(audio_url: str, title: str, output_dir: Path) -> tuple[str, str]:
    """
    Download audio directly from URL and convert to WAV.

    Returns:
        Tuple of (path to WAV file, episode title)
    """
    # Sanitize filename
    safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)[:100]
    temp_path = output_dir / f"{safe_title}.m4a"
    wav_path = output_dir / f"{safe_title}.wav"

    console.print(f"[bold blue]Downloading: {title[:50]}...[/bold blue]")

    # Download with requests
    response = requests.get(audio_url, stream=True, timeout=600)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size:
                percent = (downloaded / total_size) * 100
                console.print(f"  Downloading: {percent:.1f}%", end="\r")

    console.print("\n  Download complete, converting to WAV...")

    # Convert to WAV using ffmpeg
    subprocess.run(
        ["ffmpeg", "-i", str(temp_path), "-y", str(wav_path)],
        capture_output=True,
        check=True,
    )

    # Clean up temp file
    temp_path.unlink()

    return str(wav_path), title


def download_with_ytdlp(url: str, output_dir: Path) -> tuple[str, str]:
    """
    Download podcast using yt-dlp.

    Returns:
        Tuple of (path to WAV file, episode title)
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "progress_hooks": [_progress_hook],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "podcast")
        safe_title = yt_dlp.utils.sanitize_filename(title)
        audio_path = output_dir / f"{safe_title}.wav"

        if not audio_path.exists():
            wav_files = list(output_dir.glob("*.wav"))
            if wav_files:
                audio_path = wav_files[0]
            else:
                raise FileNotFoundError(f"Downloaded audio not found in {output_dir}")

    return str(audio_path), title


def download_podcast(url: str, output_dir: str) -> tuple[str, str]:
    """
    Download podcast audio.

    Tries iTunes API for Apple Podcasts, falls back to yt-dlp.

    Args:
        url: Apple Podcast URL or other podcast URL
        output_dir: Directory to save the downloaded audio

    Returns:
        Tuple of (path to audio file, episode title)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print("[bold blue]Downloading podcast...[/bold blue]")

    # Try Apple Podcast via iTunes API
    podcast_id, episode_id = extract_apple_podcast_ids(url)

    if podcast_id and episode_id:
        console.print(f"  Detected Apple Podcast (episode: {episode_id})")
        episode = get_episode_from_itunes_api(podcast_id, episode_id)

        if episode and episode.get("episodeUrl"):
            audio_url = episode["episodeUrl"]
            title = episode.get("trackName", f"episode_{episode_id}")
            audio_path, title = download_direct_audio(audio_url, title, output_path)
            console.print(f"[bold green]Downloaded:[/bold green] {Path(audio_path).name}")
            return audio_path, title

        console.print("[yellow]  iTunes API failed, trying yt-dlp...[/yellow]")

    # Fallback to yt-dlp
    audio_path, title = download_with_ytdlp(url, output_path)
    console.print(f"[bold green]Downloaded:[/bold green] {Path(audio_path).name}")
    return audio_path, title


def _progress_hook(d: dict) -> None:
    """Progress hook for yt-dlp download."""
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "N/A")
        speed = d.get("_speed_str", "N/A")
        console.print(f"  Downloading: {percent} at {speed}", end="\r")
    elif d["status"] == "finished":
        console.print("\n  Download complete, converting to WAV...")
