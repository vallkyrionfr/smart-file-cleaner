"""Dedupe command — find and remove duplicate files using 3-tier hash detection."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_file_cleaner.core.dedupe import DedupeResult, resolve_duplicates, scan_for_duplicates
from smart_file_cleaner.core.history import OperationManifest, save_manifest
from smart_file_cleaner.utils.errors import UnsafePathError
from smart_file_cleaner.utils.output import make_formatter
from smart_file_cleaner.utils.path_utils import format_size, validate_safe_target_directory
from smart_file_cleaner.utils.progress import make_progress

console = Console()


def dedupe_command(
    target_dir: Path = typer.Argument(
        ...,
        help="Directory to scan for duplicate files.",
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
        help="Preview duplicates without deleting (default: --dry-run).",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive/--no-recursive",
        "-r",
        help="Recurse into subdirectories.",
    ),
    keep: str = typer.Option(
        "newest",
        "--keep",
        help="Which duplicate to keep: newest, oldest, or interactive.",
    ),
    permanent: bool = typer.Option(
        False,
        "--permanent",
        help="Hard-delete duplicates instead of sending to Trash.",
    ),
    min_size: int = typer.Option(
        1,
        "--min-size",
        help="Minimum file size in bytes to consider (default: 1, skips empty files).",
    ),
    output: str = typer.Option(
        "text",
        "--output",
        "-o",
        help="Output format: 'text' or 'json'.",
    ),
) -> None:
    """Find and remove duplicate files using fast 3-tier hash detection.

    Tier 1: Group by exact file size.
    Tier 2: Hash first 4 KB (cheap filter).
    Tier 3: Full SHA-256 hash (definitive match).

    Dry-run by default. Duplicates go to OS Trash unless --permanent is used.
    """
    try:
        resolved_path = validate_safe_target_directory(target_dir)
    except UnsafePathError as err:
        console.print(
            Panel(f"[bold red]Security Guardrail Error:[/bold red]\n{err}", border_style="red")
        )
        raise typer.Exit(code=1) from None

    fmt = make_formatter(output)

    fmt.print(
        Panel.fit(
            f"[bold]Smart File Cleaner[/bold] — [cyan]Dedupe Mode[/cyan]\n"
            f"Target: [yellow]{resolved_path}[/yellow]\n"
            f"Mode: [bold {'green' if dry_run else 'red'}]{'DRY-RUN' if dry_run else 'EXECUTE'}[/]  "
            f"Keep: [magenta]{keep}[/magenta]  Recursive: {'Yes' if recursive else 'No'}",
            title="[bold]Dedupe[/bold]",
            border_style="magenta",
        )
    )

    # Scan
    dedupe_result: Optional[DedupeResult] = None
    with make_progress(quiet=(output == "json")) as progress:
        task = progress.add_task("[cyan]Scanning for duplicates...", total=None)
        count = 0

        def _on_file(p):
            nonlocal count
            count += 1
            progress.update(task, description=f"[cyan]Scanned {count} files...")

        dedupe_result = scan_for_duplicates(
            resolved_path,
            recursive=recursive,
            min_size_bytes=min_size,
            progress_callback=_on_file,
        )

    if not dedupe_result.groups:
        fmt.print(
            f"[bold green]✓ No duplicates found![/bold green] "
            f"Scanned {dedupe_result.scanned_files} files."
        )
        if output == "json":
            fmt.print_json(
                {
                    "status": "no_duplicates",
                    "scanned_files": dedupe_result.scanned_files,
                    "groups_found": 0,
                }
            )
        return

    # Display groups
    for i, group in enumerate(dedupe_result.groups, 1):
        table = Table(
            title=f"Duplicate Group #{i} — {len(group.files)} copies x {group.display_size} "
            f"(wasting {group.display_wasted})",
            show_lines=True,
        )
        table.add_column("File", style="yellow")
        table.add_column("Size", justify="right", style="dim")
        for f in group.files:
            table.add_row(str(f), group.display_size)
        fmt.print_table(table)

    total_wasted = format_size(dedupe_result.total_wasted_bytes)
    fmt.print(
        f"\n[bold]Found [red]{len(dedupe_result.groups)}[/red] duplicate group(s).[/bold] "
        f"Reclaimable: [red]{total_wasted}[/red]"
    )

    if output == "json":
        fmt.print_json(
            {
                "status": "dry_run" if dry_run else "pending",
                "scanned_files": dedupe_result.scanned_files,
                "groups_found": len(dedupe_result.groups),
                "wasted_bytes": dedupe_result.total_wasted_bytes,
                "groups": [
                    {"files": [str(f) for f in g.files], "size_bytes": g.size_bytes}
                    for g in dedupe_result.groups
                ],
            }
        )

    if dry_run:
        fmt.print(
            "\n[bold yellow]Dry-run:[/bold yellow] No files removed. "
            "Run with [bold]--execute[/bold] to delete duplicates."
        )
        return

    # Execute
    manifest = OperationManifest(operation="dedupe", target_dir=str(resolved_path))
    clean_result = resolve_duplicates(
        dedupe_result,
        manifest,
        keep_strategy=keep,
        permanent=permanent,
    )
    save_manifest(manifest)

    if output == "json":
        fmt.print_json(
            {
                "status": "executed",
                "removed": len(clean_result.removed),
                "kept": len(clean_result.kept),
                "reclaimed_bytes": clean_result.total_reclaimed_bytes,
            }
        )
    else:
        fmt.print_success(
            f"Removed {len(clean_result.removed)} duplicate(s) — "
            f"{format_size(clean_result.total_reclaimed_bytes)} reclaimed."
        )
        if clean_result.failed:
            fmt.print_warning(f"{len(clean_result.failed)} files could not be removed.")
