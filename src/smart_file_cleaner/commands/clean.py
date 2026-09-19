"""Clean command — replaces the original stub with a real junk file scanner."""

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_file_cleaner.core.cleaner import execute_clean, scan_for_junk
from smart_file_cleaner.core.history import OperationManifest, save_manifest
from smart_file_cleaner.utils.errors import UnsafePathError
from smart_file_cleaner.utils.output import make_formatter
from smart_file_cleaner.utils.path_utils import validate_safe_target_directory
from smart_file_cleaner.utils.progress import make_progress

console = Console()

_REASON_LABELS = {
    "pattern": "Junk Pattern",
    "os_cruft": "OS Cruft",
    "dev_cache": "Dev Cache",
    "empty_dir": "Empty Directory",
}


def clean_command(
    target_dir: Path = typer.Argument(
        ...,
        help="Target directory to scan and clean.",
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
        help="Preview files to clean without deleting (default: --dry-run).",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive/--no-recursive",
        "-r",
        help="Recurse into subdirectories.",
    ),
    permanent: bool = typer.Option(
        False,
        "--permanent",
        help="Hard-delete instead of sending to OS Trash. IRREVERSIBLE.",
    ),
    pattern: Optional[List[str]] = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Extra glob patterns to target (repeatable, e.g. -p '*.log' -p '*.cache').",
    ),
    output: str = typer.Option(
        "text",
        "--output",
        "-o",
        help="Output format: 'text' (default) or 'json'.",
    ),
) -> None:
    """Scan for and remove junk files, OS cruft, dev caches, and empty directories.

    Dry-run by default — use --execute to actually delete.
    Files are sent to the OS Trash unless --permanent is specified.
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
            f"[bold]Smart File Cleaner[/bold] — [cyan]Clean Mode[/cyan]\n"
            f"Target: [yellow]{resolved_path}[/yellow]\n"
            f"Mode: [bold {'green' if dry_run else 'red'}]{'DRY-RUN' if dry_run else 'EXECUTE'}[/]"
            + ("  [bold red]⚠ PERMANENT DELETE[/bold red]" if permanent and not dry_run else "")
            + f"\nRecursive: {'Yes' if recursive else 'No'}",
            title="[bold]Clean[/bold]",
            border_style="blue" if dry_run else "red",
        )
    )

    # Confirm permanent deletion
    if permanent and not dry_run:
        confirm = typer.confirm(
            "⚠  Permanent deletion is irreversible. Files will NOT go to Trash. Continue?",
            default=False,
        )
        if not confirm:
            fmt.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    # Scan with progress
    scan_result = None
    with make_progress(quiet=(output == "json")) as progress:
        task = progress.add_task("[cyan]Scanning...", total=None)
        count = 0

        def _on_progress(p):
            nonlocal count
            count += 1
            progress.update(task, description=f"[cyan]Scanning ({count} files)...", advance=1)

        # Load config-driven patterns
        from smart_file_cleaner.utils.config import load_config

        cfg = load_config()
        junk_patterns = list(cfg.clean.junk_patterns) + list(pattern or [])

        scan_result = scan_for_junk(
            resolved_path,
            junk_patterns=junk_patterns,
            os_cruft=cfg.clean.os_cruft,
            dev_caches=cfg.clean.dev_caches,
            recursive=recursive,
            progress_callback=_on_progress,
        )

    if not scan_result.items:
        fmt.print("[bold green]✓ Nothing to clean — directory is already tidy![/bold green]")
        if output == "json":
            fmt.print_json({"status": "clean", "items_found": 0, "total_bytes": 0})
        return

    # Show results table
    table = Table(
        title=f"Scan Results — {len(scan_result.items)} items found ({scan_result.total_display_size} reclaimable)"
    )
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Path", style="yellow")
    table.add_column("Size", style="dim", justify="right")

    for item in scan_result.items:
        try:
            display_path = str(item.path.relative_to(resolved_path))
        except ValueError:
            display_path = str(item.path)
        table.add_row(
            _REASON_LABELS.get(item.reason, item.reason),
            display_path,
            item.display_size,
        )
    fmt.print_table(table)

    if output == "json":
        fmt.print_json(
            {
                "status": "dry_run" if dry_run else "executed",
                "items_found": len(scan_result.items),
                "total_bytes": scan_result.total_size_bytes,
                "items": [
                    {"path": str(i.path), "reason": i.reason, "size_bytes": i.size_bytes}
                    for i in scan_result.items
                ],
            }
        )

    if dry_run:
        fmt.print(
            f"\n[bold yellow]Notice:[/bold yellow] Dry-run complete — "
            f"{len(scan_result.items)} items ({scan_result.total_display_size}) identified.\n"
            "Run with [bold]--execute[/bold] to delete. Files go to OS Trash by default."
        )
        return

    # Execute clean
    manifest = OperationManifest(operation="clean", target_dir=str(resolved_path))
    clean_result = None
    with make_progress(quiet=(output == "json")) as progress:
        task = progress.add_task("[red]Cleaning...", total=len(scan_result.items))

        def _on_delete(item):
            progress.advance(task)

        clean_result = execute_clean(
            scan_result,
            manifest,
            permanent=permanent,
            progress_callback=_on_delete,
        )

    save_manifest(manifest)

    if output == "json":
        fmt.print_json(
            {
                "status": "executed",
                "removed": len(clean_result.removed),
                "failed": len(clean_result.failed),
                "reclaimed_bytes": clean_result.total_reclaimed_bytes,
            }
        )
    else:
        fmt.print_success(
            f"Cleaned {len(clean_result.removed)} items — "
            f"{clean_result.total_reclaimed_display} reclaimed."
        )
        if clean_result.failed:
            fmt.print_warning(f"{len(clean_result.failed)} items could not be removed:")
            for item, fail_err in clean_result.failed:
                fmt.print(f"  [dim]• {item.path}: {fail_err}[/dim]")
        if not permanent:
            fmt.print(
                "[dim]Run [bold]smart-file-cleaner undo[/bold] to restore (moves only).[/dim]"
            )
