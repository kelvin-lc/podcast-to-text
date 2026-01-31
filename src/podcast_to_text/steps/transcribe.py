"""Transcribe step for pipeline."""

from ..pipeline import PipelineContext
from ..transcriber import transcribe_audio


class TranscribeStep:
    """Transcribe audio to text segments."""

    name = "Transcribe"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.config.require_speech()

        if not ctx.audio_path:
            raise ValueError("audio_path is required for TranscribeStep")

        segments = transcribe_audio(
            str(ctx.audio_path),
            ctx.config.speech_key,
            ctx.config.speech_region,
        )

        if not segments:
            raise ValueError("No transcription results")

        ctx.segments = segments

        # Set title from audio filename if not already set
        if not ctx.episode_title:
            ctx.episode_title = ctx.audio_path.stem

        return ctx
