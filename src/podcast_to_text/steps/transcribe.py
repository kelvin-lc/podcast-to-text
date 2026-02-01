"""Transcribe step for pipeline."""

from ..pipeline import PipelineContext


class TranscribeStep:
    """Transcribe audio to text segments."""

    name = "Transcribe"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.config.require_speech()

        if not ctx.audio_path:
            raise ValueError("audio_path is required for TranscribeStep")

        if ctx.config.asr_provider == "qwen":
            from ..qwen_transcriber import transcribe_audio_qwen

            segments = transcribe_audio_qwen(
                str(ctx.audio_path),
                ctx.config.qwen_asr_url,
            )
        else:  # azure (default)
            from ..transcriber import transcribe_audio

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
