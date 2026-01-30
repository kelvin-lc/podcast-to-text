# Podcast to Text

将播客音频转换为格式化的 Markdown 文本。

## 功能

- 支持 Apple Podcast 和其他播客平台（通过 yt-dlp + iTunes API）
- 使用 Azure Speech SDK 进行中文语音识别
- 支持长音频（2-3小时），自动分段处理
- 使用 Azure OpenAI 优化文本格式和排版（保留原文，不删减内容）

## 安装

需要 Python 3.13+ 和 [uv](https://docs.astral.sh/uv/) 包管理器。

```bash
# 安装 ffmpeg（macOS）
brew install ffmpeg

# 安装依赖
uv sync
```

## 配置

复制 `.env.example` 为 `.env` 并填写 Azure 凭据：

```bash
# Azure Speech
AZURE_SPEECH_KEY=your_speech_key
AZURE_SPEECH_REGION=japaneast

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_KEY=your_openai_key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

## 使用

支持三种输入模式：

### 模式 1: 从 URL（完整流程）

```bash
# 下载 → 转写 → 格式化
uv run python -m podcast_to_text "https://podcasts.apple.com/..."

# 仅转写，跳过 LLM 格式化
uv run python -m podcast_to_text "https://..." --no-format

# 保留下载的音频文件
uv run python -m podcast_to_text "https://..." --keep-audio
```

### 模式 2: 从本地音频文件

```bash
# 转写本地音频 → 格式化
uv run python -m podcast_to_text --audio ./episode.mp3

# 仅转写，不格式化
uv run python -m podcast_to_text --audio ./episode.wav --no-format
```

### 模式 3: 从原始文本文件

```bash
# 直接格式化已有的转写文本
uv run python -m podcast_to_text --text ./raw-transcript.txt
```

## 命令行选项

| 选项 | 说明 |
|------|------|
| `-a, --audio PATH` | 本地音频文件（跳过下载） |
| `-t, --text PATH` | 原始文本文件（跳过下载和转写） |
| `-o, --output PATH` | 输出目录（默认: `output/`） |
| `--audio-dir PATH` | 音频缓存目录（默认: `audio/`） |
| `--no-format` | 跳过 LLM 格式化，仅输出原始转写 |
| `--keep-audio` | 处理完成后保留音频文件 |

## 处理流程

```
┌─────────────────────────────────────────────────────────────┐
│  模式 1: URL                                                 │
│  URL → 下载 → 转写 → 格式化 → Markdown                       │
├─────────────────────────────────────────────────────────────┤
│  模式 2: 本地音频                                            │
│  音频文件 → 转写 → 格式化 → Markdown                         │
├─────────────────────────────────────────────────────────────┤
│  模式 3: 原始文本                                            │
│  文本文件 → 格式化 → Markdown                                │
└─────────────────────────────────────────────────────────────┘
```

### 各步骤说明

1. **下载** - 使用 iTunes API + yt-dlp 下载播客音频并转换为 WAV
2. **分段** - 将长音频按 15 分钟分割（使用 pydub）
3. **转写** - 使用 Azure Speech SDK 逐段进行语音识别
4. **格式化** - 使用 Azure OpenAI 优化排版（分段、添加标题），保留所有原始内容
5. **输出** - 保存为 Markdown 文件
