"""Config command — inspect and manage the smart-file-cleaner configuration."""

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from smart_file_cleaner.utils.config import (
    get_config_file,
    init_config_file,
    load_config,
)

console = Console()

config_app = typer.Typer(
    name="config",
    help="Inspect and manage smart-file-cleaner configuration.",
    no_args_is_help=True,
)


@config_app.command("show")
def config_show() -> None:
    """Display the current effective configuration with source annotations."""
    config_file = get_config_file()
    cfg = load_config()

    source_label = (
        f"[green]{config_file}[/green]"
        if config_file.exists()
        else "[yellow]defaults (no config file found)[/yellow]"
    )

    table = Table(title=f"Active Configuration  (source: {source_label})", show_lines=True)
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="bold")

    table.add_row("defaults.dry_run", str(cfg.dry_run))
    table.add_row("defaults.recursive", str(cfg.recursive))
    table.add_row("defaults.output", cfg.output)
    table.add_row("clean.junk_patterns", str(cfg.clean.junk_patterns[:3]) + " ...")
    table.add_row("clean.os_cruft", str(cfg.clean.os_cruft[:3]) + " ...")
    table.add_row("clean.dev_caches", str(cfg.clean.dev_caches[:3]) + " ...")
    table.add_row("clean.protected", str(cfg.clean.protected))
    table.add_row("dedupe.keep_strategy", cfg.dedupe.keep_strategy)
    table.add_row("dedupe.min_size_bytes", str(cfg.dedupe.min_size_bytes))
    table.add_row("review.stale_days", str(cfg.review.stale_days))
    table.add_row("review.large_mb", str(cfg.review.large_mb))

    console.print(table)


@config_app.command("path")
def config_path() -> None:
    """Print the path to the active config file."""
    config_file = get_config_file()
    if config_file.exists():
        console.print(f"[green]{config_file}[/green]  [dim](exists)[/dim]")
    else:
        console.print(
            f"[yellow]{config_file}[/yellow]  [dim](not created yet — run [bold]config init[/bold])[/dim]"
        )


@config_app.command("init")
def config_init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config file."),
) -> None:
    """Create the default config file at the XDG config location."""
    config_file = get_config_file()

    if config_file.exists() and not force:
        console.print(
            f"[yellow]Config already exists:[/yellow] {config_file}\n"
            "Pass [bold]--force[/bold] to overwrite."
        )
        raise typer.Exit(0)

    if force and config_file.exists():
        config_file.unlink()

    created_path = init_config_file()
    console.print(f"[bold green]✓ Config created:[/bold green] {created_path}")

    # Show the contents
    content = created_path.read_text(encoding="utf-8")
    console.print(Syntax(content, "toml", theme="monokai", line_numbers=True))
