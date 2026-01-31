# src/podcast_to_text/steps/download.py
"""Download step for pipeline."""

from pathlib import Path

from ..downloader import download_podcast
from ..pipeline import PipelineContext


class DownloadStep:
    """Download podcast audio from URL."""

    name = "Download"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.source_url:
            raise ValueError("source_url is required for DownloadStep")

        audio_path, title = download_podcast(
            ctx.source_url,
            str(ctx.config.audio_dir),
        )

        ctx.audio_path = Path(audio_path)
        ctx.episode_title = title
        return ctx
