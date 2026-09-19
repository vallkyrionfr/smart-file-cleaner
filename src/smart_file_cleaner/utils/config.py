"""Cross-platform XDG-compliant configuration for smart-file-cleaner.

Config resolution order (highest → lowest priority):
  1. CLI flags passed at runtime
  2. Environment variables (SFC_* prefix)
  3. User TOML config file (platform-appropriate location)
  4. Built-in defaults

Platform locations:
  Linux   : ~/.config/smart-file-cleaner/config.toml
  Windows : %APPDATA%\\smart-file-cleaner\\config.toml
  macOS   : ~/Library/Application Support/smart-file-cleaner/config.toml
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from platformdirs import user_config_path, user_data_path

from smart_file_cleaner.utils.errors import ConfigError

APP_NAME = "smart-file-cleaner"

# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------

DEFAULT_JUNK_PATTERNS: List[str] = [
    "*.tmp",
    "*.temp",
    "*.~*",
    "~$*",
    "*.bak",
    "*.swp",
    "*.swo",
    "*#",
    "*.orig",
]

DEFAULT_OS_CRUFT: List[str] = [
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "ehthumbs.db",
    ".Spotlight-V100",
    ".Trashes",
    "Icon\r",
]

DEFAULT_DEV_CACHES: List[str] = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".tox",
    "node_modules/.cache",
    ".parcel-cache",
    ".turbo",
    ".next/cache",
    ".nuxt",
    ".vite",
    "dist/.cache",
]

DEFAULT_PROTECTED_DIRS: List[str] = [
    ".git",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
]

DEFAULT_TOML_CONFIG = """\
# smart-file-cleaner configuration
# Generated automatically. Edit to customise behaviour.

[defaults]
dry_run = true
recursive = false
output = "text"        # "text" | "json"

[clean]
junk_patterns = [
    "*.tmp", "*.temp", "*.~*", "~$*", "*.bak",
    "*.swp", "*.swo", "*#", "*.orig",
]
os_cruft = [
    ".DS_Store", "Thumbs.db", "desktop.ini",
    "ehthumbs.db", ".Spotlight-V100", ".Trashes",
]
dev_caches = [
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".hypothesis", ".tox",
    "node_modules/.cache", ".parcel-cache",
]
protected = [
    ".git", ".svn", ".hg", ".venv",
    "venv", "env", "node_modules",
]

[dedupe]
min_size_bytes = 1
keep_strategy = "newest"   # "newest" | "oldest" | "interactive"

[review]
stale_days = 30
large_mb = 100
"""


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class CleanConfig:
    junk_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_JUNK_PATTERNS))
    os_cruft: List[str] = field(default_factory=lambda: list(DEFAULT_OS_CRUFT))
    dev_caches: List[str] = field(default_factory=lambda: list(DEFAULT_DEV_CACHES))
    protected: List[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED_DIRS))


@dataclass
class DedupeConfig:
    min_size_bytes: int = 1
    keep_strategy: str = "newest"  # "newest" | "oldest" | "interactive"


@dataclass
class ReviewConfig:
    stale_days: int = 30
    large_mb: float = 100.0


@dataclass
class AppConfig:
    dry_run: bool = True
    recursive: bool = False
    output: str = "text"  # "text" | "json"
    verbose: bool = False
    quiet: bool = False
    no_color: bool = False
    clean: CleanConfig = field(default_factory=CleanConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_config_dir() -> Path:
    """Return XDG-compliant config directory for smart-file-cleaner."""
    return user_config_path(APP_NAME)


def get_config_file() -> Path:
    """Return path to user config TOML file."""
    return get_config_dir() / "config.toml"


def get_data_dir() -> Path:
    """Return XDG-compliant data directory (used by history engine)."""
    return user_data_path(APP_NAME)


def get_history_dir() -> Path:
    """Return directory where operation manifests are stored."""
    return get_data_dir() / "history"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _load_toml(path: Path) -> dict:
    """Parse a TOML file, returning an empty dict if not found."""
    if not path.exists():
        return {}
    try:
        if sys.version_info >= (3, 11):
            import tomllib  # stdlib from 3.11

            with open(path, "rb") as f:
                return tomllib.load(f)
        else:
            try:
                import tomli  # lightweight backport

                with open(path, "rb") as f:
                    return tomli.load(f)
            except ImportError:
                # tomli not installed — silently use defaults
                return {}
    except Exception as exc:
        raise ConfigError(f"Failed to parse config file '{path}': {exc}") from exc


def load_config(config_file: Optional[Path] = None) -> AppConfig:
    """Load configuration from TOML file and environment variables.

    Args:
        config_file: Optional explicit config file path. Defaults to
            the XDG-appropriate user config location.

    Returns:
        AppConfig populated from file and environment.
    """
    toml_path = config_file or get_config_file()
    raw = _load_toml(toml_path)

    defaults = raw.get("defaults", {})
    clean_raw = raw.get("clean", {})
    dedupe_raw = raw.get("dedupe", {})
    review_raw = raw.get("review", {})

    # Environment variable overrides (SFC_ prefix)
    dry_run = _env_bool("SFC_DRY_RUN", defaults.get("dry_run", True))
    recursive = _env_bool("SFC_RECURSIVE", defaults.get("recursive", False))
    output = os.environ.get("SFC_OUTPUT", defaults.get("output", "text"))
    verbose = _env_bool("SFC_VERBOSE", False)
    quiet = _env_bool("SFC_QUIET", False)
    no_color = _env_bool("NO_COLOR", False)  # Respect the de-facto NO_COLOR standard

    return AppConfig(
        dry_run=dry_run,
        recursive=recursive,
        output=output,
        verbose=verbose,
        quiet=quiet,
        no_color=no_color,
        clean=CleanConfig(
            junk_patterns=clean_raw.get("junk_patterns", DEFAULT_JUNK_PATTERNS),
            os_cruft=clean_raw.get("os_cruft", DEFAULT_OS_CRUFT),
            dev_caches=clean_raw.get("dev_caches", DEFAULT_DEV_CACHES),
            protected=clean_raw.get("protected", DEFAULT_PROTECTED_DIRS),
        ),
        dedupe=DedupeConfig(
            min_size_bytes=dedupe_raw.get("min_size_bytes", 1),
            keep_strategy=dedupe_raw.get("keep_strategy", "newest"),
        ),
        review=ReviewConfig(
            stale_days=review_raw.get("stale_days", 30),
            large_mb=review_raw.get("large_mb", 100.0),
        ),
    )


def init_config_file() -> Path:
    """Create the default config file if it does not exist.

    Returns:
        Path to the (possibly newly created) config file.
    """
    config_file = get_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    if not config_file.exists():
        config_file.write_text(DEFAULT_TOML_CONFIG, encoding="utf-8")
    return config_file


def _env_bool(var: str, default: bool) -> bool:
    """Read a boolean from an environment variable."""
    val = os.environ.get(var)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")
