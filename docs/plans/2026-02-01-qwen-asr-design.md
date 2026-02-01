# Qwen3-ASR 集成设计

## 概述

添加 Qwen3-ASR 作为可选的 ASR 引擎，通过环境变量切换，保留现有 Azure Speech SDK 方案。

## 动机

- Qwen3-ASR 速度更快
- 支持本地/自托管部署
- 无需手动分段处理长音频

## API 信息

- **服务地址**: `http://home_ubuntu:8001`
- **模型**: `Qwen3-ASR-1.7B` (运行在 vLLM 上)
- **端点**: `/v1/audio/transcriptions` (OpenAI Whisper API 兼容)
- **支持格式**: json, text, verbose_json, srt, vtt

## 配置设计

### 新增环境变量

```bash
# .env

# ASR Provider: "azure" (默认) 或 "qwen"
ASR_PROVIDER=qwen

# Qwen ASR 配置 (仅当 ASR_PROVIDER=qwen 时需要)
QWEN_ASR_URL=http://home_ubuntu:8001
```

### Config 模型更新

```python
class Config(BaseModel):
    # 现有 Azure Speech 配置保持不变
    speech_key: str | None = None
    speech_region: str | None = None

    # 新增：ASR Provider 选择
    asr_provider: str = "azure"  # "azure" 或 "qwen"

    # 新增：Qwen ASR 配置
    qwen_asr_url: str | None = None

    def require_speech(self) -> None:
        """验证 ASR 配置"""
        if self.asr_provider == "azure":
            if not self.speech_key or not self.speech_region:
                raise ValueError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION required")
        elif self.asr_provider == "qwen":
            if not self.qwen_asr_url:
                raise ValueError("QWEN_ASR_URL required")
        else:
            raise ValueError(f"Unknown ASR provider: {self.asr_provider}")
```

## 架构设计

### 文件结构

```
src/podcast_to_text/
├── transcriber.py          # 保留：Azure Speech SDK 实现
├── qwen_transcriber.py     # 新增：Qwen ASR 实现
└── steps/
    └── transcribe.py       # 修改：根据 config 选择 transcriber
```

### qwen_transcriber.py

```python
"""Qwen3-ASR transcription using OpenAI-compatible API."""

import httpx
from pathlib import Path
from rich.console import Console

console = Console()


def _parse_response(result: dict) -> list[dict]:
    """将 Qwen ASR 响应转换为统一格式。"""
    # verbose_json 格式包含 segments
    if "segments" in result:
        return [
            {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", ""),
            }
            for seg in result["segments"]
        ]

    # 简单 json 格式只有 text
    return [{"start": 0, "end": 0, "text": result.get("text", "")}]


def transcribe_audio_qwen(
    audio_path: str,
    api_url: str,
    language: str = "zh",
) -> list[dict]:
    """
    使用 Qwen3-ASR API 转写音频。

    Args:
        audio_path: 音频文件路径
        api_url: Qwen ASR 服务地址
        language: 语言代码

    Returns:
        转写结果列表 [{"start": 0.0, "end": 5.2, "text": "..."}]
    """
    url = f"{api_url}/v1/audio/transcriptions"

    console.print(f"[bold blue]Transcribing with Qwen3-ASR...[/bold blue]")

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

    console.print(f"[bold green]Transcription complete: {len(segments)} segments[/bold green]")
    return segments
```

### TranscribeStep 修改

```python
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

    if not ctx.episode_title:
        ctx.episode_title = ctx.audio_path.stem

    return ctx
```

## 实现任务

1. 更新 `config.py` - 添加 `asr_provider` 和 `qwen_asr_url` 字段
2. 创建 `qwen_transcriber.py` - Qwen ASR 实现
3. 更新 `steps/transcribe.py` - 根据配置选择 transcriber
4. 更新 `.env.example` - 添加新的环境变量说明
5. 验证功能正常

## 优点

1. **向后兼容**: 现有 Azure 用户无需改动
2. **灵活切换**: 通过环境变量轻松切换 ASR 引擎
3. **速度提升**: Qwen3-ASR 处理速度更快
4. **简化流程**: 无需手动分段，API 内部处理
