"""Cleanup step for pipeline."""

from rich.console import Console

from ..pipeline import PipelineContext

console = Console()


class CleanupStep:
    """Clean up temporary files (audio) after processing."""

    name = "Cleanup"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.config.keep_audio and ctx.audio_path and ctx.audio_path.exists():
            ctx.audio_path.unlink()
            console.print("[dim]Audio file cleaned up[/dim]")

        return ctx
