"""Format step for pipeline."""

from ..formatter import format_transcript, format_text
from ..pipeline import PipelineContext
from ..transcriber import segments_to_text


class FormatStep:
    """Format transcription using LLM."""

    name = "Format"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.config.require_openai()

        if ctx.segments:
            # Format from segments
            ctx.text = format_transcript(
                ctx.segments,
                ctx.config.openai_endpoint,
                ctx.config.openai_key,
                ctx.config.openai_deployment,
            )
        elif ctx.text_path:
            # Format from text file
            raw_text = ctx.text_path.read_text(encoding="utf-8")
            ctx.text = format_text(
                raw_text,
                ctx.config.openai_endpoint,
                ctx.config.openai_key,
                ctx.config.openai_deployment,
            )
            # Set title from text filename if not already set
            if not ctx.episode_title:
                ctx.episode_title = f"{ctx.text_path.stem}_formatted"
        else:
            raise ValueError("segments or text_path required for FormatStep")

        return ctx


class SkipFormatStep:
    """Skip formatting, just convert segments to text."""

    name = "Skip Format"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.segments:
            ctx.text = segments_to_text(ctx.segments)
        elif ctx.text_path:
            ctx.text = ctx.text_path.read_text(encoding="utf-8")
            if not ctx.episode_title:
                ctx.episode_title = ctx.text_path.stem
        else:
            raise ValueError("segments or text_path required")

        return ctx
