# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

podcast-to-text is a CLI tool that converts podcast audio into formatted Markdown text. It supports a full pipeline: downloading from URL (Apple Podcasts via iTunes API + yt-dlp), transcribing using Azure Speech SDK (with automatic segmentation for long audio), and formatting using Azure OpenAI (GPT-4o).

## Commands

```bash
# Install dependencies
uv sync

# Run from URL (full pipeline: download → transcribe → format)
uv run python -m podcast_to_text "https://podcasts.apple.com/..."

# Run from local audio file
uv run python -m podcast_to_text --audio path/to/audio.mp3

# Format existing transcription only
uv run python -m podcast_to_text --text path/to/transcript.txt

# Skip LLM formatting (raw transcription only)
uv run python -m podcast_to_text "URL" --no-format
```

## Architecture

The codebase follows a modular pipeline architecture:

```
src/podcast_to_text/
├── main.py          # CLI entry point (click), orchestrates pipeline
├── downloader.py    # iTunes API metadata + yt-dlp audio download
├── transcriber.py   # Azure Speech SDK, handles audio segmentation (15min chunks)
└── formatter.py     # Azure OpenAI formatting, preserves original content
```

**Pipeline flow**: URL → Download (WAV) → Segment → Transcribe → Format → Markdown

**Configuration**: Azure credentials loaded from `.env` file (see `.env.example`).

**External dependencies**:
- `ffmpeg` required for audio processing (install via `brew install ffmpeg` on macOS)
- Azure Speech SDK for Chinese speech recognition
- Azure OpenAI for text formatting
