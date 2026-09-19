"""Real junk file scanning and cleaning engine for smart-file-cleaner.

Replaces the original stub in commands/clean.py.

Scanning strategy:
  1. Pattern matching — glob-based junk file patterns (*.tmp, *.bak, etc.)
  2. OS cruft detection — .DS_Store, Thumbs.db, desktop.ini, etc.
  3. Dev cache detection — __pycache__, .pytest_cache, node_modules/.cache, etc.
  4. Empty directory pruning — bottom-up traversal removes empty subdirs

Safety rules:
  - Never enters .git, .svn, .hg, .venv, node_modules
  - Never targets protected system paths (/, /etc, C:\\Windows, etc.)
  - Dry-run by default
  - All deletions go to OS Trash unless --permanent is passed
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from smart_file_cleaner.core.history import OperationManifest
from smart_file_cleaner.utils.path_utils import (
    format_size,
    is_protected_directory,
    walk_filtered,
)
from smart_file_cleaner.utils.signals import shutdown_requested
from smart_file_cleaner.utils.trash import safe_delete

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class JunkItem:
    """Represents a single file or directory identified as junk."""

    path: Path
    reason: str  # "pattern", "os_cruft", "dev_cache", "empty_dir"
    size_bytes: int = 0

    def is_dir(self) -> bool:
        return self.path.is_dir() if self.path.exists() else False

    @property
    def display_size(self) -> str:
        return format_size(self.size_bytes)


@dataclass
class ScanResult:
    """Aggregated result of a junk scan."""

    root: Path
    items: List[JunkItem] = field(default_factory=list)

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items)

    @property
    def total_display_size(self) -> str:
        return format_size(self.total_size_bytes)

    @property
    def file_count(self) -> int:
        return sum(1 for item in self.items if not item.path.is_dir())

    @property
    def dir_count(self) -> int:
        return sum(1 for item in self.items if item.path.is_dir())


@dataclass
class CleanResult:
    """Result of executing a clean operation."""

    removed: List[JunkItem] = field(default_factory=list)
    failed: List[tuple] = field(default_factory=list)  # (JunkItem, error_message)

    @property
    def total_reclaimed_bytes(self) -> int:
        return sum(item.size_bytes for item in self.removed)

    @property
    def total_reclaimed_display(self) -> str:
        return format_size(self.total_reclaimed_bytes)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _matches_pattern(name: str, patterns: List[str]) -> bool:
    """Check if a filename matches any of the provided glob patterns."""
    name_lower = name.lower()
    return any(fnmatch.fnmatch(name_lower, p.lower()) for p in patterns)


def _is_os_cruft(path: Path, cruft_names: List[str]) -> bool:
    """Check if a file is a known OS cruft file."""
    return path.name in cruft_names or path.name.lower() in {c.lower() for c in cruft_names}


def _is_dev_cache(path: Path, dev_caches: List[str]) -> bool:
    """Check if a path (file or dir) is a developer cache artifact."""
    for pattern in dev_caches:
        if fnmatch.fnmatch(path.name, pattern):
            return True
        if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
            return True
    return False


def _get_size(path: Path) -> int:
    """Return total size in bytes (handles files and directories)."""
    try:
        if path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return path.stat().st_size
    except (OSError, PermissionError):
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_for_junk(
    root: Path,
    *,
    junk_patterns: Optional[List[str]] = None,
    os_cruft: Optional[List[str]] = None,
    dev_caches: Optional[List[str]] = None,
    recursive: bool = False,
    progress_callback=None,
) -> ScanResult:
    """Scan a directory for junk files and return a ScanResult.

    Args:
        root: Directory to scan.
        junk_patterns: Glob patterns for junk files (*.tmp, *.bak, etc.)
        os_cruft: OS-specific cruft filenames (.DS_Store, Thumbs.db, etc.)
        dev_caches: Dev tool cache names (__pycache__, .pytest_cache, etc.)
        recursive: Whether to recurse into subdirectories.
        progress_callback: Optional callable(path) called for each file visited.

    Returns:
        ScanResult with all identified junk items.
    """
    from smart_file_cleaner.utils.config import (
        DEFAULT_DEV_CACHES,
        DEFAULT_JUNK_PATTERNS,
        DEFAULT_OS_CRUFT,
    )

    patterns = junk_patterns if junk_patterns is not None else DEFAULT_JUNK_PATTERNS
    cruft = os_cruft if os_cruft is not None else DEFAULT_OS_CRUFT
    caches = dev_caches if dev_caches is not None else DEFAULT_DEV_CACHES

    result = ScanResult(root=root)
    seen_paths = set()  # Avoid duplicates (a dir may match multiple rules)

    def _add(path: Path, reason: str) -> None:
        key = str(path)
        if key not in seen_paths:
            seen_paths.add(key)
            result.items.append(JunkItem(path=path, reason=reason, size_bytes=_get_size(path)))

    # Scan files via walk_filtered
    for file_path in walk_filtered(root, recursive=recursive, include_hidden_files=True):
        if shutdown_requested():
            break
        if progress_callback:
            progress_callback(file_path)

        # 1. Junk patterns
        if _matches_pattern(file_path.name, patterns):
            _add(file_path, "pattern")
            continue

        # 2. OS cruft
        if _is_os_cruft(file_path, cruft):
            _add(file_path, "os_cruft")
            continue

        # 3. Dev caches (files)
        if _is_dev_cache(file_path, caches):
            _add(file_path, "dev_cache")
            continue

    # 4. Dev cache directories + empty dirs (requires separate traversal)
    if root.is_dir():
        _scan_dirs(root, caches, recursive, seen_paths, result)

    return result


def _scan_dirs(
    root: Path,
    dev_caches: List[str],
    recursive: bool,
    seen_paths: set,
    result: ScanResult,
) -> None:
    """Scan for dev-cache directories and empty directories."""
    try:
        entries = sorted(root.iterdir())
    except (PermissionError, OSError):
        return

    for entry in entries:
        if entry.is_symlink() or not entry.is_dir():
            continue
        if is_protected_directory(entry):
            continue

        # Dev cache directories (e.g. __pycache__, .pytest_cache)
        if _is_dev_cache(entry, dev_caches):
            key = str(entry)
            if key not in seen_paths:
                seen_paths.add(key)
                result.items.append(
                    JunkItem(path=entry, reason="dev_cache", size_bytes=_get_size(entry))
                )
            continue  # Don't recurse into cache dirs

        if recursive:
            _scan_dirs(entry, dev_caches, recursive, seen_paths, result)

    # Check for empty directories after child scan
    for entry in sorted(root.iterdir()):
        if entry.is_symlink() or not entry.is_dir():
            continue
        if is_protected_directory(entry):
            continue
        if _is_empty_dir(entry):
            key = str(entry)
            if key not in seen_paths:
                seen_paths.add(key)
                result.items.append(JunkItem(path=entry, reason="empty_dir", size_bytes=0))


def _is_empty_dir(path: Path) -> bool:
    """Return True if directory contains no files or non-hidden subdirs."""
    try:
        return not any(True for _ in path.iterdir())
    except (PermissionError, OSError):
        return False


def execute_clean(
    scan_result: ScanResult,
    manifest: OperationManifest,
    *,
    permanent: bool = False,
    progress_callback=None,
) -> CleanResult:
    """Execute a clean operation based on a ScanResult.

    Args:
        scan_result: Previously computed junk scan.
        manifest: Operation manifest to log actions into.
        permanent: If True, hard-delete instead of trashing.
        progress_callback: Optional callable(item) called for each deletion.

    Returns:
        CleanResult with removed and failed items.
    """
    result = CleanResult()

    for item in scan_result.items:
        if shutdown_requested():
            break
        if progress_callback:
            progress_callback(item)

        if not item.path.exists() and not item.path.is_symlink():
            continue  # Already gone

        try:
            safe_delete(item.path, permanent=permanent)
            manifest.add_delete(item.path)
            result.removed.append(item)
        except Exception as exc:
            result.failed.append((item, str(exc)))

    return result
