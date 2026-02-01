# Qwen3-ASR 集成实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 添加 Qwen3-ASR 作为可选 ASR 引擎，通过环境变量切换，保留现有 Azure 方案

**Architecture:** 新增 `qwen_transcriber.py` 模块，更新 Config 支持多 ASR provider，TranscribeStep 根据配置动态选择 transcriber

**Tech Stack:** Python 3.13+, httpx, Pydantic, OpenAI Whisper API 兼容接口

---

## Task 1: 添加 httpx 依赖

**Files:**
- Modify: `pyproject.toml`

**Step 1: 添加 httpx 依赖**

```bash
uv add httpx
```

**Step 2: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add httpx dependency for Qwen ASR"
```

---

## Task 2: 更新 Config 模型

**Files:**
- Modify: `src/podcast_to_text/config.py`

**Step 1: 更新 config.py**

在 Config 类中添加新字段和更新 `from_env` 和 `require_speech` 方法：

```python
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
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/config.py
git commit -m "feat: add ASR provider configuration (azure/qwen)"
```

---

## Task 3: 创建 Qwen Transcriber

**Files:**
- Create: `src/podcast_to_text/qwen_transcriber.py`

**Step 1: 创建 qwen_transcriber.py**

```python
"""Qwen3-ASR transcription using OpenAI-compatible API."""

from pathlib import Path

import httpx
from rich.console import Console

console = Console()


def _parse_response(result: dict) -> list[dict]:
    """Convert Qwen ASR response to unified format."""
    # verbose_json format includes segments
    if "segments" in result:
        return [
            {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", ""),
            }
            for seg in result["segments"]
        ]

    # Simple json format only has text
    return [{"start": 0, "end": 0, "text": result.get("text", "")}]


def transcribe_audio_qwen(
    audio_path: str,
    api_url: str,
    language: str = "zh",
) -> list[dict]:
    """
    Transcribe audio using Qwen3-ASR API.

    Args:
        audio_path: Path to audio file
        api_url: Qwen ASR service URL
        language: Language code

    Returns:
        List of transcription segments [{"start": 0.0, "end": 5.2, "text": "..."}]
    """
    url = f"{api_url}/v1/audio/transcriptions"

    console.print("[bold blue]Transcribing with Qwen3-ASR...[/bold blue]")

    try:
        with open(audio_path, "rb") as f:
            files = {"file": (Path(audio_path).name, f)}
            data = {
                "language": language,
                "response_format": "verbose_json",
            }
            response = httpx.post(url, files=files, data=data, timeout=600)

        response.raise_for_status()
    except httpx.ConnectError:
        raise ValueError(f"Cannot connect to Qwen ASR at {api_url}")
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
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/qwen_transcriber.py
git commit -m "feat: add Qwen3-ASR transcriber"
```

---

## Task 4: 更新 TranscribeStep

**Files:**
- Modify: `src/podcast_to_text/steps/transcribe.py`

**Step 1: 更新 transcribe.py**

```python
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
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/steps/transcribe.py
git commit -m "feat: support multiple ASR providers in TranscribeStep"
```

---

## Task 5: 更新 .env.example

**Files:**
- Modify: `.env.example`

**Step 1: 更新 .env.example**

```bash
# ASR Provider: "azure" (default) or "qwen"
ASR_PROVIDER=azure

# Azure Speech (required if ASR_PROVIDER=azure)
AZURE_SPEECH_KEY=your_speech_key_here
AZURE_SPEECH_REGION=japaneast

# Qwen ASR (required if ASR_PROVIDER=qwen)
QWEN_ASR_URL=http://your-qwen-asr-server:8001

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_KEY=your_openai_key_here
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add Qwen ASR configuration to .env.example"
```

---

## Task 6: 验证功能

**Step 1: 验证 CLI 正常启动**

```bash
uv run python -m podcast_to_text --help
```

Expected: 显示帮助信息，无导入错误

**Step 2: 测试 Qwen ASR（需要设置环境变量）**

创建测试用的 .env：
```bash
ASR_PROVIDER=qwen
QWEN_ASR_URL=http://home_ubuntu:8001
```

使用短音频测试：
```bash
uv run python -m podcast_to_text --audio <test_audio_file> --no-format
```

Expected: 成功转写并输出结果

---

## 完成检查清单

- [ ] httpx 依赖已添加
- [ ] config.py 更新（asr_provider, qwen_asr_url）
- [ ] qwen_transcriber.py 创建
- [ ] steps/transcribe.py 更新
- [ ] .env.example 更新
- [ ] CLI 验证通过
- [ ] Qwen ASR 功能测试通过
