"""Organize command module for smart-file-cleaner."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_file_cleaner.core.sorter import execute_organization, plan_organization
from smart_file_cleaner.utils.path_utils import UnsafePathError, validate_safe_target_directory

console = Console()


def organize_command(
    target_dir: Path = typer.Argument(
        ...,
        help="Directory path to organize.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        "-d/-e",
        help="Preview actions without moving files (default: --dry-run).",
    ),
    rules: Optional[str] = typer.Option(
        None,
        "--rules",
        "-r",
        help="Path to custom organization rules configuration file.",
    ),
) -> None:
    """Organize files in target directory into categorized subdirectories.

    Cross-platform safe file categorization by file extensions and rules.
    """
    try:
        resolved_path = validate_safe_target_directory(target_dir)
    except UnsafePathError as err:
        console.print(
            Panel(f"[bold red]Security Guardrail Error:[/bold red]\n{err}", border_style="red")
        )
        raise typer.Exit(code=1) from None

    console.print(
        Panel.fit(
            f"[bold blue]Smart File Cleaner[/bold blue] - [cyan]Organize Mode[/cyan]\n"
            f"Target Directory: [yellow]{resolved_path}[/yellow]\n"
            f"Mode: [bold {'green' if dry_run else 'red'}]{'DRY-RUN (Safe Preview)' if dry_run else 'EXECUTE'}[/]",
            title="[bold]Organize Command[/bold]",
            border_style="blue",
        )
    )

    planned_moves = plan_organization(resolved_path)

    if not planned_moves:
        console.print(
            "[bold yellow]No loose files found to organize in target directory.[/bold yellow]"
        )
        return

    table = Table(title=f"Organization Plan ({len(planned_moves)} files found)")
    table.add_column("File Name", style="cyan", no_wrap=True)
    table.add_column("Extension", style="magenta")
    table.add_column("Category", style="bold green")
    table.add_column("Target Path", style="yellow")
    table.add_column("Size", style="dim")
    table.add_column("Collision Note", style="bold red")

    total_bytes = 0
    for move in planned_moves:
        total_bytes += move.size_bytes
        rel_dest = str(move.destination.relative_to(resolved_path))
        table.add_row(
            move.source.name,
            move.extension,
            move.category,
            rel_dest,
            _fmt(move.size_bytes),
            "Auto-renamed" if move.is_collision else "[dim green]Safe[/dim green]",
        )

    console.print(table)

    if dry_run:
        console.print(
            f"\n[bold yellow]Notice:[/bold yellow] Dry-run complete. {len(planned_moves)} files "
            f"({_fmt(total_bytes)}) would be organized. No files were moved.\n"
            "Use [bold]--execute[/bold] (or [bold]-e[/bold]) to apply changes."
        )
    else:
        from smart_file_cleaner.core.history import OperationManifest, save_manifest

        manifest = OperationManifest(operation="organize", target_dir=str(resolved_path))
        executed_moves = execute_organization(planned_moves)
        for move in executed_moves:
            manifest.add_move(move.source, move.destination)
        save_manifest(manifest)
        console.print(
            f"\n[bold green]Success:[/bold green] Successfully organized {len(executed_moves)} files "
            f"({_fmt(total_bytes)}) into categorized subdirectories.\n"
            "[dim]Run [bold]smart-file-cleaner undo[/bold] to reverse this operation.[/dim]"
        )


def format_bytes(size: int) -> str:
    """Format byte count into human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size //= 1024
    return f"{size:.1f} TB"


_fmt = format_bytes
