"""Review / Triage command module for smart-file-cleaner."""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from smart_file_cleaner.commands.organize import format_bytes
from smart_file_cleaner.core.triage import (
    analyze_directory_for_triage,
    auto_sort_file,
    move_to_sort_later,
)
from smart_file_cleaner.utils.path_utils import UnsafePathError, validate_safe_target_directory

console = Console()


def render_triage_tables(analysis_result) -> None:
    """Render Rich visual tables for triage analysis buckets."""
    buckets_data = [
        ("📦 Unused Installers", analysis_result.installers, "red"),
        ("🐘 Large Files (>=100MB)", analysis_result.large_files, "yellow"),
        ("⏳ Stale Files (>=30 Days)", analysis_result.stale_files, "magenta"),
        ("🗂️ Uncategorized Clutter", analysis_result.clutter, "cyan"),
    ]

    for title, items, color in buckets_data:
        if not items:
            continue

        table = Table(title=f"{title} ({len(items)} items)", border_style=color)
        table.add_column("Filename", style="bold white", no_wrap=True)
        table.add_column("Size", style="dim")
        table.add_column("Age", style="dim green")
        table.add_column("Extension", style="magenta")

        for item in items:
            table.add_row(
                item.filename,
                format_bytes(item.size_bytes),
                f"{item.age_days}d old",
                item.extension,
            )

        console.print(table)


def review_command(
    target_dir: Optional[Path] = typer.Argument(
        None,
        help="Directory path to triage and review (default: ~/Downloads).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Preview triage inspection without moving files.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        "--batch",
        "-b",
        help="Run without interactive prompt.",
    ),
    batch_action: str = typer.Option(
        "skip",
        "--batch-action",
        "-a",
        help="Action to execute in batch mode: 'sort_later', 'auto_sort', or 'skip'.",
    ),
) -> None:
    """Interactive triage menu for reviewing messy folders (like ~/Downloads).

    Groups files into Installers, Stale Files, Large Files, and Clutter,
    giving you fine-grained control to clean up or sort them.
    """
    raw_path = target_dir if target_dir is not None else Path("~/Downloads")

    try:
        resolved_path = validate_safe_target_directory(raw_path)
    except UnsafePathError as err:
        console.print(
            Panel(f"[bold red]Security Guardrail Error:[/bold red]\n{err}", border_style="red")
        )
        raise typer.Exit(code=1) from None

    if not resolved_path.exists() or not resolved_path.is_dir():
        console.print(
            f"[bold red]Error:[/bold red] Target directory [yellow]{resolved_path}[/yellow] does not exist."
        )
        raise typer.Exit(code=1)

    analysis = analyze_directory_for_triage(resolved_path)

    console.print(
        Panel.fit(
            f"[bold blue]Smart File Cleaner[/bold blue] - [cyan]Triage & Review Mode[/cyan]\n"
            f"Target Directory: [yellow]{resolved_path}[/yellow]\n"
            f"Total Files Analyzed: [bold green]{len(analysis.all_files)}[/bold green]\n"
            f"Installers: [red]{len(analysis.installers)}[/red] | "
            f"Large Files: [yellow]{len(analysis.large_files)}[/yellow] | "
            f"Stale: [magenta]{len(analysis.stale_files)}[/magenta] | "
            f"Clutter: [cyan]{len(analysis.clutter)}[/cyan]",
            title="[bold]Downloads Triage Summary[/bold]",
            border_style="magenta",
        )
    )

    if not analysis.all_files:
        console.print(
            "[bold green]✨ Target directory is completely clean! No files found for triage.[/bold green]"
        )
        return

    render_triage_tables(analysis)

    if dry_run:
        console.print(
            "\n[bold yellow]Notice:[/bold yellow] Dry-run preview complete. "
            "No file movements were performed."
        )
        return

    # Check if stdin is interactive or non-interactive flag was explicitly set
    is_tty = sys.stdin and sys.stdin.isatty()
    run_interactive = is_tty and not non_interactive

    if not run_interactive:
        console.print(
            f"\n[dim]Running in non-interactive batch mode (Action: [bold]{batch_action}[/bold])...[/dim]"
        )
        moved_count = 0

        for item in analysis.all_files:
            if batch_action == "sort_later":
                move_to_sort_later(item.path, resolved_path)
                moved_count += 1
            elif batch_action == "auto_sort":
                auto_sort_file(item.path, resolved_path)
                moved_count += 1

        console.print(
            f"[bold green]Batch action completed. Processed {moved_count} files.[/bold green]"
        )
        return

    # Interactive triage loop
    console.print("\n[bold cyan]Starting Interactive Triage Menu...[/bold cyan]")
    moved_count = 0
    skipped_count = 0

    items_to_review = list(analysis.all_files)
    idx = 0
    auto_sort_all = False
    sort_later_all = False

    while idx < len(items_to_review):
        item = items_to_review[idx]
        bucket_str = ", ".join(item.buckets)

        if auto_sort_all:
            auto_sort_file(item.path, resolved_path)
            moved_count += 1
            idx += 1
            continue

        if sort_later_all:
            move_to_sort_later(item.path, resolved_path)
            moved_count += 1
            idx += 1
            continue

        console.print(
            f"\n[bold]Item [{idx + 1}/{len(items_to_review)}]:[/bold] "
            f"[yellow]{item.filename}[/yellow] ({format_bytes(item.size_bytes)}, {item.age_days}d old) "
            f"[[magenta]{bucket_str}[/magenta]]"
        )
        console.print("  [1] Move to SortLater folder (~/Downloads/SortLater)")
        console.print("  [2] Auto-Sort into category folder")
        console.print("  [3] Keep in place (Skip)")
        console.print("  [A] Auto-Sort ALL remaining files")
        console.print("  [L] SortLater ALL remaining files")
        console.print("  [Q] Quit review")

        choice = Prompt.ask(
            "Select action",
            choices=["1", "2", "3", "a", "A", "l", "L", "q", "Q"],
            default="3",
        ).lower()

        if choice == "1":
            move_to_sort_later(item.path, resolved_path)
            console.print(f"  [green]Moved [yellow]{item.filename}[/yellow] to SortLater/[/green]")
            moved_count += 1
        elif choice == "2":
            dest = auto_sort_file(item.path, resolved_path)
            console.print(
                f"  [green]Auto-sorted [yellow]{item.filename}[/yellow] to {dest.parent.name}/[/green]"
            )
            moved_count += 1
        elif choice == "3":
            console.print(f"  [dim]Kept [yellow]{item.filename}[/yellow] in place.[/dim]")
            skipped_count += 1
        elif choice == "a":
            auto_sort_all = True
            auto_sort_file(item.path, resolved_path)
            moved_count += 1
        elif choice == "l":
            sort_later_all = True
            move_to_sort_later(item.path, resolved_path)
            moved_count += 1
        elif choice == "q":
            console.print("[yellow]Exiting review early.[/yellow]")
            break

        idx += 1

    console.print(
        f"\n[bold green]Triage Summary:[/bold green] "
        f"Moved/Organized: {moved_count} files | Kept in place: {skipped_count} files."
    )
