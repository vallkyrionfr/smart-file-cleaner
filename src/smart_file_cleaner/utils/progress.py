"""Rich progress bar helpers for smart-file-cleaner.

Wraps rich.progress so all scanning commands use consistent,
styled progress indicators. Respects --quiet (no output when quiet=True).

Usage::

    from smart_file_cleaner.utils.progress import make_progress, ProgressTask

    with make_progress(quiet=False) as progress:
        task = progress.add_task("[cyan]Scanning...", total=None)
        for path in walk():
            progress.advance(task)
            progress.update(task, description=f"[cyan]{path.name}")
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)


def _build_progress(quiet: bool = False) -> Progress:
    """Build a Rich Progress instance with the standard smart-file-cleaner style."""
    if quiet:
        # Return a no-op progress object by disabling rendering
        return Progress(
            TextColumn("[progress.description]{task.description}"),
            disable=True,
        )
    return Progress(
        SpinnerColumn("dots", style="bold cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        expand=True,
    )


@contextmanager
def make_progress(quiet: bool = False) -> Generator[Progress, None, None]:
    """Context manager that yields an active Rich Progress bar.

    Args:
        quiet: If True, progress bar is hidden (disabled=True).

    Yields:
        A started rich.progress.Progress instance.
    """
    progress = _build_progress(quiet=quiet)
    with progress:
        yield progress
