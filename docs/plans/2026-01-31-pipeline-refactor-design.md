# Pipeline 架构重构设计

## 概述

将 podcast-to-text 重构为 Pipeline 模式，解决当前 `main.py` 中三种模式（URL/audio/text）的重复代码问题，提升可维护性和可测试性。

## 当前问题

1. `main.py` 三种模式有大量重复逻辑（加载配置、转写、格式化、保存）
2. 配置加载和验证混在业务逻辑中
3. 每个模块各自创建 `Console()` 实例
4. `downloader.py` 有重复的 `except` 块（死代码）

## 核心设计

### 架构图

```
┌─────────────────────────────────────────────────────┐
│  PipelineContext                                     │
│  - 在步骤间传递数据 (audio_path, segments, text)    │
│  - 持有配置 (Config)                                 │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Step (Protocol)                                     │
│  - name: str                                         │
│  - run(context) -> context                          │
│  - 每个步骤是独立、可测试的单元                       │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│  Pipeline                                            │
│  - 按顺序执行 steps                                  │
│  - 处理错误和进度显示                                │
└─────────────────────────────────────────────────────┘
```

### 三种模式的 Pipeline 组合

- **URL 模式**: Download → Transcribe → Format → Save
- **Audio 模式**: Transcribe → Format → Save
- **Text 模式**: Format → Save

## 数据模型（Pydantic）

### Config

```python
from pydantic import BaseModel
from pathlib import Path

class Config(BaseModel):
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

    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        ...

    def require_speech(self) -> None:
        """Validate speech config, raise if missing."""
        if not self.speech_key or not self.speech_region:
            raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION required")

    def require_openai(self) -> None:
        """Validate OpenAI config, raise if missing."""
        if not all([self.openai_endpoint, self.openai_key, self.openai_deployment]):
            raise ValueError("AZURE_OPENAI_* credentials required")
```

### PipelineContext

```python
class PipelineContext(BaseModel):
    config: Config

    # 流程数据
    source_url: str | None = None
    audio_path: Path | None = None
    text_path: Path | None = None
    episode_title: str | None = None
    segments: list[dict] | None = None
    text: str | None = None
    output_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}
```

## Step 协议和 Pipeline 实现

### Step Protocol

```python
from typing import Protocol

class Step(Protocol):
    """Pipeline step interface."""

    name: str  # 显示名称

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute step, return updated context."""
        ...
```

### Pipeline

```python
class Pipeline:
    def __init__(self, steps: list[Step], console: Console | None = None):
        self.steps = steps
        self.console = console or Console()

    def run(self, ctx: PipelineContext) -> PipelineContext:
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

### Step 实现示例

```python
class DownloadStep:
    name = "Download"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        audio_path, title = download_podcast(
            ctx.source_url,
            str(ctx.config.audio_dir)
        )
        ctx.audio_path = Path(audio_path)
        ctx.episode_title = title
        return ctx
```

## 文件结构

```
src/podcast_to_text/
├── __init__.py
├── __main__.py          # 入口，调用 main.py
├── main.py              # CLI 定义，构建 Pipeline 并执行
├── config.py            # Config 模型 (新增)
├── pipeline.py          # Pipeline, PipelineContext, Step 协议 (新增)
├── steps/               # 各步骤实现 (新增目录)
│   ├── __init__.py      # 导出所有 steps
│   ├── download.py      # DownloadStep
│   ├── transcribe.py    # TranscribeStep
│   ├── format.py        # FormatStep
│   └── save.py          # SaveStep
├── downloader.py        # 保留，作为 download 的底层实现
├── transcriber.py       # 保留，作为 transcribe 的底层实现
└── formatter.py         # 保留，作为 format 的底层实现
```

### 职责划分

| 文件 | 职责 |
|------|------|
| `config.py` | Config 模型、环境变量加载、验证方法 |
| `pipeline.py` | Pipeline 类、PipelineContext、Step 协议 |
| `steps/*.py` | 每个 Step 封装一个处理阶段，调用底层实现 |
| `downloader.py` | 纯下载逻辑（iTunes API、yt-dlp），不依赖 Pipeline |
| `main.py` | CLI 参数解析 → 构建 Context → 选择 Steps → 运行 Pipeline |

## 重构后的 main.py

```python
"""CLI entry point for podcast-to-text."""

import sys
from pathlib import Path

import click
from rich.console import Console

from .config import Config
from .pipeline import Pipeline, PipelineContext
from .steps import DownloadStep, TranscribeStep, FormatStep, SaveStep

console = Console()


def create_pipeline(mode: str, skip_format: bool) -> Pipeline:
    """Create pipeline based on input mode."""
    steps = []

    if mode == "url":
        steps.append(DownloadStep())
    if mode in ("url", "audio"):
        steps.append(TranscribeStep())
    if not skip_format:
        steps.append(FormatStep())
    steps.append(SaveStep())

    return Pipeline(steps, console)


@click.command()
@click.argument("source", required=False)
@click.option("--audio", "-a", type=click.Path(exists=True))
@click.option("--text", "-t", type=click.Path(exists=True))
@click.option("--output", "-o", default="output")
@click.option("--audio-dir", default="audio")
@click.option("--no-format", is_flag=True)
@click.option("--keep-audio", is_flag=True)
def main(source, audio, text, output, audio_dir, no_format, keep_audio):
    """Convert podcast audio to formatted Markdown text."""
    console.print("[bold]Podcast to Text[/bold]\n")

    # Determine mode
    if text:
        mode = "text"
    elif audio:
        mode = "audio"
    elif source:
        mode = "url"
    else:
        console.print("[bold red]Error:[/bold red] Must provide URL, --audio, or --text")
        sys.exit(1)

    # Build context
    config = Config.from_env()
    config.output_dir = Path(output)
    config.audio_dir = Path(audio_dir)
    config.keep_audio = keep_audio

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
```

## 优点

1. **代码简化**: main.py 从 280 行减少到约 60 行
2. **可测试性**: 每个 Step 可独立测试
3. **可扩展性**: 易于添加新 Step（如 CleanupStep、NotifyStep）
4. **职责清晰**: 底层模块保持独立，Steps 作为适配层
5. **配置管理**: 统一的 Config 模型，延迟验证

## 实现顺序

1. 创建 `config.py` - Config 模型
2. 创建 `pipeline.py` - Pipeline、PipelineContext、Step 协议
3. 创建 `steps/` 目录和各 Step 实现
4. 重构 `main.py` 使用 Pipeline
5. 清理 `downloader.py` 中的死代码
6. 移除各模块中重复的 Console 实例
