"""Main Typer CLI application for smart-file-cleaner."""

import sys
from typing import Optional

import typer
from rich.console import Console

from smart_file_cleaner import __version__
from smart_file_cleaner.commands.analyze import analyze_command
from smart_file_cleaner.commands.clean import clean_command
from smart_file_cleaner.commands.config_cmd import config_app
from smart_file_cleaner.commands.dedupe import dedupe_command
from smart_file_cleaner.commands.organize import organize_command
from smart_file_cleaner.commands.review import review_command
from smart_file_cleaner.commands.undo import undo_command
from smart_file_cleaner.utils.errors import SmartCleanerError

console = Console()

app = typer.Typer(
    name="smart-file-cleaner",
    help=(
        "[bold]smart-file-cleaner[/bold] — A safe, cross-platform CLI to organize, "
        "clean, and analyze your files.\n\n"
        "Dry-run is the default for all destructive operations. "
        "Files go to OS Trash, not permanent deletion."
    ),
    add_completion=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

# ---------------------------------------------------------------------------
# Subcommand registration
# ---------------------------------------------------------------------------
app.command(name="organize", help="Organize files by type into categorized folders.")(
    organize_command
)
app.command(name="clean", help="Scan and remove junk files, OS cruft, dev caches, and empty dirs.")(
    clean_command
)
app.command(name="review", help="Interactive triage for messy folders (Downloads, Desktop, etc.).")(
    review_command
)
app.command(
    name="dedupe", help="Find and remove duplicate files using fast 3-tier hash detection."
)(dedupe_command)
app.command(
    name="analyze",
    help="Show a disk usage dashboard: storage breakdown, largest files, stale files.",
)(analyze_command)
app.command(name="undo", help="Reverse the last organize, clean, or dedupe operation.")(
    undo_command
)

# Config is a sub-app (config show / config path / config init)
app.add_typer(config_app, name="config")


# ---------------------------------------------------------------------------
# Version callback
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]smart-file-cleaner[/bold] [green]{__version__}[/green]")
        console.print(f"Python [dim]{sys.version}[/dim]")
        console.print(f"Platform [dim]{sys.platform}[/dim]")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Global callback — runs before every command
# ---------------------------------------------------------------------------


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """smart-file-cleaner: Cross-platform file organisation & cleanup utility."""
    from smart_file_cleaner.utils.signals import setup_signal_handlers

    setup_signal_handlers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        app()
    except SmartCleanerError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=exc.exit_code) from None
