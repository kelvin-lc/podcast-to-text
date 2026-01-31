# Pipeline 架构重构实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 podcast-to-text 重构为 Pipeline 模式，消除 main.py 中的重复代码

**Architecture:** 使用 Pipeline + Step 模式，每个处理阶段封装为独立 Step，通过 PipelineContext 传递数据。底层模块（downloader/transcriber/formatter）保持独立。

**Tech Stack:** Python 3.13+, Pydantic, Click, Rich

---

## Task 1: 创建 Config 模型

**Files:**
- Create: `src/podcast_to_text/config.py`

**Step 1: 创建 config.py**

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
        )

    def require_speech(self) -> None:
        """Validate speech credentials are present."""
        if not self.speech_key or not self.speech_region:
            raise ValueError(
                "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set"
            )

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
git commit -m "refactor: add Config model for configuration management"
```

---

## Task 2: 创建 Pipeline 和 PipelineContext

**Files:**
- Create: `src/podcast_to_text/pipeline.py`

**Step 1: 创建 pipeline.py**

```python
"""Pipeline execution framework."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from rich.console import Console

from .config import Config


class PipelineContext(BaseModel):
    """Context passed between pipeline steps."""

    config: Config

    # Flow data
    source_url: str | None = None
    audio_path: Path | None = None
    text_path: Path | None = None
    episode_title: str | None = None
    segments: list[dict] | None = None
    text: str | None = None
    output_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


class Step(Protocol):
    """Pipeline step interface."""

    name: str

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute step and return updated context."""
        ...


class Pipeline:
    """Execute a sequence of steps."""

    def __init__(self, steps: list[Step], console: Console | None = None):
        self.steps = steps
        self.console = console or Console()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Run all steps in sequence."""
        total = len(self.steps)

        for i, step in enumerate(self.steps, 1):
            self.console.print(f"\n[bold]Step {i}/{total}: {step.name}[/bold]")
            try:
                ctx = step.run(ctx)
            except Exception as e:
                self.console.print(f"[bold red]Error in {step.name}:[/bold red] {e}")
                raise

        return ctx
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/pipeline.py
git commit -m "refactor: add Pipeline framework with Step protocol"
```

---

## Task 3: 创建 DownloadStep

**Files:**
- Create: `src/podcast_to_text/steps/__init__.py`
- Create: `src/podcast_to_text/steps/download.py`

**Step 1: 创建 steps 目录和 download.py**

```python
# src/podcast_to_text/steps/__init__.py
"""Pipeline steps."""

from .download import DownloadStep
from .transcribe import TranscribeStep
from .format import FormatStep
from .save import SaveStep

__all__ = ["DownloadStep", "TranscribeStep", "FormatStep", "SaveStep"]
```

```python
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
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/steps/
git commit -m "refactor: add DownloadStep"
```

---

## Task 4: 创建 TranscribeStep

**Files:**
- Create: `src/podcast_to_text/steps/transcribe.py`

**Step 1: 创建 transcribe.py**

```python
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
```

**Step 2: 更新 steps/__init__.py（已在 Task 3 包含）**

**Step 3: Commit**

```bash
git add src/podcast_to_text/steps/transcribe.py
git commit -m "refactor: add TranscribeStep"
```

---

## Task 5: 创建 FormatStep

**Files:**
- Create: `src/podcast_to_text/steps/format.py`

**Step 1: 创建 format.py**

```python
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
```

**Step 2: 更新 steps/__init__.py 添加 SkipFormatStep**

```python
# src/podcast_to_text/steps/__init__.py
"""Pipeline steps."""

from .download import DownloadStep
from .transcribe import TranscribeStep
from .format import FormatStep, SkipFormatStep
from .save import SaveStep

__all__ = ["DownloadStep", "TranscribeStep", "FormatStep", "SkipFormatStep", "SaveStep"]
```

**Step 3: Commit**

```bash
git add src/podcast_to_text/steps/format.py src/podcast_to_text/steps/__init__.py
git commit -m "refactor: add FormatStep and SkipFormatStep"
```

---

## Task 6: 创建 SaveStep

**Files:**
- Create: `src/podcast_to_text/steps/save.py`

**Step 1: 创建 save.py**

```python
"""Save step for pipeline."""

import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

from ..pipeline import PipelineContext

console = Console()


def sanitize_filename(title: str) -> str:
    """Sanitize title for use as filename."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", title)
    return safe[:100].strip()


class SaveStep:
    """Save formatted text to file."""

    name = "Save"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.text:
            raise ValueError("text is required for SaveStep")

        # Ensure output directory exists
        ctx.config.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate output filename
        if ctx.episode_title:
            safe_title = sanitize_filename(ctx.episode_title)
            output_file = ctx.config.output_dir / f"{safe_title}.md"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = ctx.config.output_dir / f"podcast_{timestamp}.md"

        # Write output
        output_file.write_text(ctx.text, encoding="utf-8")
        ctx.output_path = output_file

        console.print(f"[bold green]Saved to:[/bold green] {output_file}")

        return ctx
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/steps/save.py
git commit -m "refactor: add SaveStep"
```

---

## Task 7: 创建 CleanupStep

**Files:**
- Create: `src/podcast_to_text/steps/cleanup.py`
- Modify: `src/podcast_to_text/steps/__init__.py`

**Step 1: 创建 cleanup.py**

```python
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
```

**Step 2: 更新 steps/__init__.py**

```python
# src/podcast_to_text/steps/__init__.py
"""Pipeline steps."""

from .download import DownloadStep
from .transcribe import TranscribeStep
from .format import FormatStep, SkipFormatStep
from .save import SaveStep
from .cleanup import CleanupStep

__all__ = [
    "DownloadStep",
    "TranscribeStep",
    "FormatStep",
    "SkipFormatStep",
    "SaveStep",
    "CleanupStep",
]
```

**Step 3: Commit**

```bash
git add src/podcast_to_text/steps/cleanup.py src/podcast_to_text/steps/__init__.py
git commit -m "refactor: add CleanupStep for audio file cleanup"
```

---

## Task 8: 重构 main.py

**Files:**
- Modify: `src/podcast_to_text/main.py`

**Step 1: 重写 main.py**

```python
"""CLI entry point for podcast-to-text."""

import sys
from pathlib import Path

import click
from rich.console import Console

from .config import Config
from .pipeline import Pipeline, PipelineContext
from .steps import (
    DownloadStep,
    TranscribeStep,
    FormatStep,
    SkipFormatStep,
    SaveStep,
    CleanupStep,
)

console = Console()


def create_pipeline(mode: str, skip_format: bool) -> Pipeline:
    """Create pipeline based on input mode."""
    steps = []

    if mode == "url":
        steps.append(DownloadStep())

    if mode in ("url", "audio"):
        steps.append(TranscribeStep())

    if skip_format:
        steps.append(SkipFormatStep())
    else:
        steps.append(FormatStep())

    steps.append(SaveStep())

    if mode == "url":
        steps.append(CleanupStep())

    return Pipeline(steps, console)


@click.command()
@click.argument("source", required=False)
@click.option(
    "--audio",
    "-a",
    type=click.Path(exists=True),
    help="Local audio file to transcribe (skip download)",
)
@click.option(
    "--text",
    "-t",
    type=click.Path(exists=True),
    help="Raw transcript file to format (skip download and transcription)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="output",
    help="Output directory for the Markdown file",
)
@click.option(
    "--audio-dir",
    type=click.Path(),
    default="audio",
    help="Directory to cache downloaded audio",
)
@click.option(
    "--no-format",
    is_flag=True,
    default=False,
    help="Skip LLM formatting (output raw transcription only)",
)
@click.option(
    "--keep-audio",
    is_flag=True,
    default=False,
    help="Keep the downloaded audio file after processing",
)
def main(
    source: str | None,
    audio: str | None,
    text: str | None,
    output: str,
    audio_dir: str,
    no_format: bool,
    keep_audio: bool,
):
    """
    Convert podcast audio to formatted Markdown text.

    Three input modes:

    \b
    1. From URL (default):
       podcast-to-text "https://podcasts.apple.com/..."

    \b
    2. From local audio file:
       podcast-to-text --audio ./episode.mp3

    \b
    3. From raw transcript text:
       podcast-to-text --text ./raw-transcript.txt
    """
    console.print("[bold]Podcast to Text[/bold]\n")

    # Determine input mode
    if text:
        mode = "text"
    elif audio:
        mode = "audio"
    elif source:
        mode = "url"
    else:
        console.print(
            "[bold red]Error:[/bold red] Must provide a URL, --audio, or --text"
        )
        console.print("Run with --help for usage information.")
        sys.exit(1)

    # Build config
    config = Config.from_env()
    config = config.model_copy(
        update={
            "output_dir": Path(output),
            "audio_dir": Path(audio_dir),
            "keep_audio": keep_audio,
        }
    )

    # Build context
    ctx = PipelineContext(
        config=config,
        source_url=source,
        audio_path=Path(audio) if audio else None,
        text_path=Path(text) if text else None,
    )

    # Run pipeline
    try:
        pipeline = create_pipeline(mode, no_format)
        pipeline.run(ctx)
        console.print("\n[bold green]Done![/bold green]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/main.py
git commit -m "refactor: rewrite main.py to use Pipeline pattern"
```

---

## Task 9: 清理 downloader.py 死代码

**Files:**
- Modify: `src/podcast_to_text/downloader.py`

**Step 1: 删除重复的 except 块（第 125-127 行）**

删除 `get_episode_from_webpage` 函数中重复的 except 块：

```python
# 删除这段重复代码（第 125-127 行）
    except Exception as e:
        console.print(f"[yellow]Webpage scraping error: {e}[/yellow]")
        return None
```

**Step 2: Commit**

```bash
git add src/podcast_to_text/downloader.py
git commit -m "fix: remove duplicate except block in downloader.py"
```

---

## Task 10: 验证重构

**Step 1: 运行 CLI 帮助确认没有语法错误**

```bash
uv run python -m podcast_to_text --help
```

Expected: 显示帮助信息，无错误

**Step 2: Commit 所有更改（如有遗漏）**

```bash
git status
```

如果有未提交的更改，提交它们。

---

## 完成检查清单

- [ ] `config.py` - Config 模型创建
- [ ] `pipeline.py` - Pipeline 框架创建
- [ ] `steps/download.py` - DownloadStep 创建
- [ ] `steps/transcribe.py` - TranscribeStep 创建
- [ ] `steps/format.py` - FormatStep 和 SkipFormatStep 创建
- [ ] `steps/save.py` - SaveStep 创建
- [ ] `steps/cleanup.py` - CleanupStep 创建
- [ ] `main.py` - 重写使用 Pipeline
- [ ] `downloader.py` - 清理死代码
- [ ] CLI 验证通过
