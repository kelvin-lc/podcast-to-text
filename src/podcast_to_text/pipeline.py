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
