"""Undo command — reverse the last organize / clean / dedupe operation."""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_file_cleaner.core.history import list_manifests, undo_by_id, undo_last
from smart_file_cleaner.utils.errors import HistoryCorruptError

console = Console()


def undo_command(
    list_history: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List recent operations instead of undoing.",
    ),
    manifest_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Undo a specific operation by its ID (shown in --list).",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        "-d/-e",
        help="Preview what would be undone without applying (default: --dry-run).",
    ),
) -> None:
    """Reverse a previous organize, clean, or dedupe operation.

    Use --list to see recent operations, then --id <ID> --execute to
    undo a specific one.
    """
    if list_history:
        _show_history()
        return

    try:
        if manifest_id:
            manifest = undo_by_id(manifest_id, dry_run=dry_run)
        else:
            manifest = undo_last(dry_run=dry_run)
    except HistoryCorruptError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1) from None

    if manifest is None:
        console.print(
            Panel.fit(
                "[yellow]No operations found to undo.[/yellow]\n"
                "Run [bold]smart-file-cleaner undo --list[/bold] to see history.",
                title="Undo",
                border_style="yellow",
            )
        )
        return

    move_actions = [a for a in manifest.get("actions", []) if a.get("type") == "move"]
    delete_actions = [a for a in manifest.get("actions", []) if a.get("type") == "delete"]

    console.print(
        Panel.fit(
            f"Operation: [bold cyan]{manifest.get('operation', 'unknown')}[/bold cyan]\n"
            f"ID: [dim]{manifest.get('id', '?')}[/dim]\n"
            f"Timestamp: [dim]{manifest.get('timestamp', '?')}[/dim]\n"
            f"Target: [yellow]{manifest.get('target_dir', '?')}[/yellow]\n\n"
            f"Reversible moves: [green]{len(move_actions)}[/green]\n"
            f"Deletions (not reversible): [dim]{len(delete_actions)}[/dim]",
            title=f"[bold]Undo {'Preview' if dry_run else 'Executed'}[/bold]",
            border_style="green" if not dry_run else "yellow",
        )
    )

    if move_actions:
        table = Table(title="Moves to Reverse")
        table.add_column("FROM (current)", style="red")
        table.add_column("→", style="dim", width=3)
        table.add_column("TO (original)", style="green")
        for action in move_actions[:20]:
            table.add_row(action.get("destination", "?"), "→", action.get("source", "?"))
        if len(move_actions) > 20:
            console.print(f"[dim]... and {len(move_actions) - 20} more moves.[/dim]")
        console.print(table)

    if dry_run:
        console.print(
            "\n[bold yellow]Dry-run:[/bold yellow] Nothing changed. "
            "Run with [bold]--execute[/bold] to apply the undo."
        )
    else:
        console.print(
            f"\n[bold green]✓ Undo complete.[/bold green] {len(move_actions)} files restored."
        )


def _show_history() -> None:
    """Display recent operation history."""
    manifests = list_manifests(n=15)
    if not manifests:
        console.print(
            Panel.fit(
                "[yellow]No operation history found.[/yellow]",
                title="History",
                border_style="yellow",
            )
        )
        return

    table = Table(title="Recent Operations (most recent first)")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Operation", style="cyan")
    table.add_column("Timestamp", style="dim")
    table.add_column("Target", style="yellow")
    table.add_column("Actions", justify="right")

    for m in manifests:
        table.add_row(
            m.get("id", "?"),
            m.get("operation", "?"),
            m.get("timestamp", "?")[:19].replace("T", " "),
            m.get("target_dir", "?"),
            str(len(m.get("actions", []))),
        )

    console.print(table)
    console.print(
        "[dim]Run [bold]smart-file-cleaner undo --id <ID> --execute[/bold] to reverse a specific operation.[/dim]"
    )
