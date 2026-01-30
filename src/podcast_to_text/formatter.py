"""Text formatting using Azure OpenAI."""

from openai import AzureOpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Target chunk size in characters
CHUNK_SIZE = 8000

SYSTEM_PROMPT = """你是一个专业的文字编辑。你的任务是将语音识别的播客转写文本格式化为清晰易读的 Markdown 格式。

【最重要的原则】必须保留原文的每一句话，不得删减、省略或总结任何内容。输出文本的信息量必须与输入完全一致。

请按照以下要求处理文本：
1. 分段落：将连续的内容按语义分成合理的段落，每段之间空一行
2. 添加小标题：在主题明显变化时，添加适当的二级或三级标题（## 或 ###）
3. 标点优化：添加正确的中文标点符号（句号、逗号、问号等）
4. 修正明显错误：仅修正明显的语音识别错别字（如"哪"应为"那"），不要改写句子
5. 保持口语风格：保留原文的口语化表达和说话风格，不要书面化改写

【禁止事项】
- 禁止删除任何句子或段落
- 禁止合并或概括多句话为一句
- 禁止改变说话人的原话和表达方式
- 禁止添加原文没有的内容

输出纯 Markdown 格式，不需要代码块包裹。"""


def split_text_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    Split plain text into chunks for LLM processing.

    Tries to split at sentence boundaries (。！？) when possible.

    Args:
        text: Plain text to split
        chunk_size: Target size of each chunk in characters

    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to find a sentence boundary near the end
        search_start = max(start, end - 200)
        best_split = end

        for punct in ["。", "！", "？", ".", "!", "?"]:
            pos = text.rfind(punct, search_start, end)
            if pos > start:
                best_split = pos + 1
                break

        chunks.append(text[start:best_split])
        start = best_split

    return chunks


def split_into_chunks(segments: list[dict], chunk_size: int = CHUNK_SIZE) -> list[str]:
    """
    Split transcription segments into chunks for LLM processing.

    Args:
        segments: List of transcription segments with timestamps
        chunk_size: Target size of each chunk in characters

    Returns:
        List of text chunks
    """
    chunks = []
    current_chunk = []
    current_size = 0

    for seg in segments:
        text = seg["text"]
        if current_size + len(text) > chunk_size and current_chunk:
            chunks.append("".join(current_chunk))
            current_chunk = []
            current_size = 0

        current_chunk.append(text)
        current_size += len(text)

    if current_chunk:
        chunks.append("".join(current_chunk))

    return chunks


def format_chunk(text: str, client: AzureOpenAI, deployment: str) -> str:
    """
    Format a single text chunk using Azure OpenAI.

    Args:
        text: Text to format
        client: Azure OpenAI client
        deployment: Model deployment name

    Returns:
        Formatted Markdown text
    """
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请格式化以下播客转写文本：\n\n{text}"},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content


def format_transcript(
    segments: list[dict],
    endpoint: str,
    api_key: str,
    deployment: str,
) -> str:
    """
    Format transcription using Azure OpenAI, handling long text by chunking.

    Args:
        segments: List of transcription segments with timestamps
        endpoint: Azure OpenAI endpoint
        api_key: Azure OpenAI API key
        deployment: Model deployment name

    Returns:
        Formatted Markdown text
    """
    # Calculate total text length
    total_text = "".join(seg["text"] for seg in segments)
    total_length = len(total_text)

    console.print(f"[bold]Total text length:[/bold] {total_length} characters")

    # Split into chunks
    chunks = split_into_chunks(segments)
    console.print(f"[bold]Split into {len(chunks)} chunks for formatting[/bold]")

    # Initialize Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-15-preview",
    )

    formatted_chunks = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Formatting text", total=len(chunks))

        for chunk in chunks:
            formatted = format_chunk(chunk, client, deployment)
            formatted_chunks.append(formatted)
            progress.update(task, advance=1)

    # Combine all formatted chunks
    result = "\n\n".join(formatted_chunks)

    console.print("[bold green]Formatting complete[/bold green]")
    return result


def format_text(
    text: str,
    endpoint: str,
    api_key: str,
    deployment: str,
) -> str:
    """
    Format plain text using Azure OpenAI, handling long text by chunking.

    Args:
        text: Plain text to format
        endpoint: Azure OpenAI endpoint
        api_key: Azure OpenAI API key
        deployment: Model deployment name

    Returns:
        Formatted Markdown text
    """
    console.print(f"[bold]Total text length:[/bold] {len(text)} characters")

    # Split into chunks
    chunks = split_text_into_chunks(text)
    console.print(f"[bold]Split into {len(chunks)} chunks for formatting[/bold]")

    # Initialize Azure OpenAI client
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-15-preview",
    )

    formatted_chunks = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Formatting text", total=len(chunks))

        for chunk in chunks:
            formatted = format_chunk(chunk, client, deployment)
            formatted_chunks.append(formatted)
            progress.update(task, advance=1)

    # Combine all formatted chunks
    result = "\n\n".join(formatted_chunks)

    console.print("[bold green]Formatting complete[/bold green]")
    return result
