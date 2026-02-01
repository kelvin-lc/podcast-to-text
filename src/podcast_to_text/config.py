"""Configuration management."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Config(BaseModel):
    """Application configuration."""

    # Azure Speech
    speech_key: str | None = None
    speech_region: str | None = None

    # Azure OpenAI
    openai_endpoint: str | None = None
    openai_key: str | None = None
    openai_deployment: str | None = None

    # ASR Provider
    asr_provider: str = "azure"  # "azure" or "qwen"

    # Qwen ASR
    qwen_asr_url: str | None = None

    # Paths
    output_dir: Path = Path("output")
    audio_dir: Path = Path("audio")

    # Options
    keep_audio: bool = False

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        load_dotenv()
        return cls(
            speech_key=os.getenv("AZURE_SPEECH_KEY"),
            speech_region=os.getenv("AZURE_SPEECH_REGION"),
            openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            openai_key=os.getenv("AZURE_OPENAI_KEY"),
            openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            asr_provider=os.getenv("ASR_PROVIDER", "azure"),
            qwen_asr_url=os.getenv("QWEN_ASR_URL"),
        )

    def require_speech(self) -> None:
        """Validate ASR credentials are present."""
        if self.asr_provider == "azure":
            if not self.speech_key or not self.speech_region:
                raise ValueError(
                    "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set"
                )
        elif self.asr_provider == "qwen":
            if not self.qwen_asr_url:
                raise ValueError("QWEN_ASR_URL must be set")
        else:
            raise ValueError(f"Unknown ASR provider: {self.asr_provider}")

    def require_openai(self) -> None:
        """Validate OpenAI credentials are present."""
        if not all([self.openai_endpoint, self.openai_key, self.openai_deployment]):
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY and AZURE_OPENAI_DEPLOYMENT must be set"
            )
