"""Output format dispatcher for smart-file-cleaner.

Controls whether results are rendered as Rich tables / panels (human-readable)
or JSON lines (machine-readable, for piping to jq / scripts).

Usage::

    from smart_file_cleaner.utils.output import OutputFormatter, OutputFormat

    fmt = OutputFormatter(format=OutputFormat.JSON)
    fmt.print_json({"operation": "clean", "files_removed": 5})

All human-readable output goes to stdout via Rich.
All logging (debug, info, warnings) goes to stderr via the logging module.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


# Shared console instances
_stdout_console = Console(stderr=False)
_stderr_console = Console(stderr=True)


class OutputFormatter:
    """Dispatches output to Rich (text) or JSON lines (json) format.

    Args:
        format: OutputFormat.TEXT or OutputFormat.JSON.
        no_color: If True, strip all Rich markup (useful when piped).
    """

    def __init__(self, format: OutputFormat = OutputFormat.TEXT, no_color: bool = False) -> None:
        self.format = format
        self._console = Console(stderr=False, no_color=no_color, highlight=not no_color)

    # ------------------------------------------------------------------
    # Generic output
    # ------------------------------------------------------------------

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Print to stdout using Rich or plain text depending on format."""
        if self.format == OutputFormat.JSON:
            return  # In JSON mode only emit structured JSON, never Rich markup
        self._console.print(*args, **kwargs)

    def print_json(self, data: Dict[str, Any]) -> None:
        """Emit a structured JSON line to stdout."""
        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()

    def print_error(self, message: str) -> None:
        """Print an error message to stderr (always visible regardless of format)."""
        _stderr_console.print(f"[bold red]Error:[/bold red] {message}")

    def print_warning(self, message: str) -> None:
        """Print a warning to stderr."""
        _stderr_console.print(f"[bold yellow]Warning:[/bold yellow] {message}")

    def print_success(self, message: str) -> None:
        """Print a success message (text mode only)."""
        if self.format == OutputFormat.TEXT:
            self._console.print(f"[bold green]✓[/bold green] {message}")

    # ------------------------------------------------------------------
    # Structured result helpers
    # ------------------------------------------------------------------

    def print_panel(self, content: str, title: str = "", border_style: str = "dim") -> None:
        """Print a Rich panel (text mode only)."""
        if self.format == OutputFormat.TEXT:
            self._console.print(Panel.fit(content, title=title, border_style=border_style))

    def print_table(self, table: Table) -> None:
        """Print a Rich table (text mode only)."""
        if self.format == OutputFormat.TEXT:
            self._console.print(table)


def make_formatter(output: str = "text", no_color: bool = False) -> OutputFormatter:
    """Factory to create an OutputFormatter from a string format name.

    Args:
        output: "text" or "json".
        no_color: Strip Rich markup.

    Returns:
        Configured OutputFormatter instance.
    """
    fmt = OutputFormat(output) if output in ("text", "json") else OutputFormat.TEXT
    return OutputFormatter(format=fmt, no_color=no_color)
