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
