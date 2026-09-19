"""Analyze command — disk usage dashboard for a directory."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from smart_file_cleaner.core.analyzer import analyze_directory
from smart_file_cleaner.utils.errors import UnsafePathError
from smart_file_cleaner.utils.output import make_formatter
from smart_file_cleaner.utils.path_utils import format_size, validate_safe_target_directory
from smart_file_cleaner.utils.progress import make_progress

console = Console()


def analyze_command(
    target_dir: Path = typer.Argument(
        ...,
        help="Directory to analyze.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive/--no-recursive",
        "-r",
        help="Recurse into subdirectories.",
    ),
    top: int = typer.Option(
        10,
        "--top",
        "-n",
        help="Number of largest files to show.",
    ),
    stale_days: int = typer.Option(
        30,
        "--stale-days",
        help="Age threshold in days for stale files.",
    ),
    output: str = typer.Option(
        "text",
        "--output",
        "-o",
        help="Output format: 'text' or 'json'.",
    ),
) -> None:
    """Analyze disk usage and show a storage breakdown dashboard.

    Displays category distribution, top N largest files,
    and stale files that haven't been touched recently.
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
            f"[bold]Smart File Cleaner[/bold] — [cyan]Analyze Mode[/cyan]\n"
            f"Target: [yellow]{resolved_path}[/yellow]  "
            f"Recursive: {'Yes' if recursive else 'No'}  "
            f"Stale threshold: {stale_days} days",
            title="[bold]Analyze[/bold]",
            border_style="cyan",
        )
    )

    # Scan with progress
    result = None
    with make_progress(quiet=(output == "json")) as progress:
        task = progress.add_task("[cyan]Analyzing...", total=None)
        count = 0

        def _on_file(p):
            nonlocal count
            count += 1
            progress.update(task, description=f"[cyan]Analyzed {count} files...")

        result = analyze_directory(
            resolved_path,
            recursive=recursive,
            top_n=top,
            stale_days=stale_days,
            progress_callback=_on_file,
        )

    if result.total_files == 0:
        fmt.print("[yellow]No files found in directory.[/yellow]")
        return

    # --- Category breakdown ---
    cat_table = Table(
        title=f"Storage by Category  (Total: {result.total_display})", show_lines=False
    )
    cat_table.add_column("Category", style="cyan")
    cat_table.add_column("Files", justify="right", style="dim")
    cat_table.add_column("Size", justify="right", style="bold")
    cat_table.add_column("Share", justify="right")

    sorted_cats = sorted(result.category_bytes.items(), key=lambda x: x[1], reverse=True)
    for cat, size in sorted_cats:
        pct = (size / result.total_bytes * 100) if result.total_bytes else 0
        cat_table.add_row(
            cat,
            str(result.category_counts.get(cat, 0)),
            format_size(size),
            f"{pct:.1f}%",
        )
    fmt.print_table(cat_table)

    # --- Top N largest files ---
    if result.top_files:
        top_table = Table(title=f"Top {top} Largest Files")
        top_table.add_column("File", style="yellow")
        top_table.add_column("Size", justify="right", style="bold red")
        top_table.add_column("Age (days)", justify="right", style="dim")
        for entry in result.top_files:
            top_table.add_row(str(entry.path), entry.display_size, f"{entry.age_days:.0f}")
        fmt.print_table(top_table)

    # --- Stale files ---
    if result.stale_files:
        stale_table = Table(
            title=f"Stale Files (untouched >{stale_days} days) — {len(result.stale_files)} files"
        )
        stale_table.add_column("File", style="yellow")
        stale_table.add_column("Size", justify="right", style="dim")
        stale_table.add_column("Age (days)", justify="right", style="bold yellow")
        for entry in result.stale_files[:20]:  # Cap display at 20
            stale_table.add_row(str(entry.path), entry.display_size, f"{entry.age_days:.0f}")
        if len(result.stale_files) > 20:
            fmt.print(f"[dim]... and {len(result.stale_files) - 20} more stale files.[/dim]")
        fmt.print_table(stale_table)

    if output == "json":
        fmt.print_json(
            {
                "root": str(result.root),
                "total_files": result.total_files,
                "total_bytes": result.total_bytes,
                "categories": {
                    cat: {"bytes": sz, "files": result.category_counts.get(cat, 0)}
                    for cat, sz in result.category_bytes.items()
                },
                "top_files": [
                    {"path": str(e.path), "size_bytes": e.size_bytes, "age_days": e.age_days}
                    for e in result.top_files
                ],
                "stale_count": len(result.stale_files),
            }
        )
