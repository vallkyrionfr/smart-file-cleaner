"""Cross-platform path utility functions for smart-file-cleaner.

Provides safe path resolution, normalization, validation, protected-directory
detection, and a unified filtered directory walker used by all scanning engines.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path
from typing import List, Optional, Set, Union

from smart_file_cleaner.utils.errors import UnsafePathError

PathLike = Union[str, os.PathLike, Path]

# Critical system directories across POSIX and Windows
PROTECTED_SYSTEM_PATHS: Set[str] = {
    # POSIX roots and system folders
    "/",
    "/etc",
    "/usr",
    "/var",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
    "/sbin",
    "/bin",
    "/opt",
    "/lib",
    "/lib64",
    "/root",
    # Windows roots and system folders
    "c:\\",
    "c:/",
    "c:\\windows",
    "c:\\windows\\system32",
    "c:\\program files",
    "c:\\program files (x86)",
    "c:\\programdata",
}

# VCS and environment directories that should never be entered during scans
_PROTECTED_DIR_NAMES: Set[str] = {
    ".git",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
}


def normalize_path(path_input: PathLike) -> Path:
    """Convert string or Path into a resolved absolute Path object.

    Handles home directory expansion (~), mixed slash formats,
    and relative path resolution across Linux and Windows.

    Args:
        path_input: The input path string or Path object.

    Returns:
        Resolved absolute Path object.
    """
    raw_str = str(path_input).strip()
    expanded = os.path.expanduser(raw_str)
    path_obj = Path(expanded)
    try:
        return path_obj.resolve()
    except OSError:
        return path_obj.absolute()


def validate_safe_target_directory(path_input: PathLike) -> Path:
    """Validate that target path is not a protected system root or bare home directory.

    Args:
        path_input: Path to validate.

    Returns:
        Resolved safe Path object.

    Raises:
        UnsafePathError: If path is a system root, protected folder, or home root.
    """
    resolved = normalize_path(path_input)
    path_str_lower = str(resolved).lower()

    # Check root drive anchors (e.g. '/' or 'C:\\')
    if resolved == Path(resolved.anchor):
        raise UnsafePathError(f"Operation refused: '{resolved}' is a filesystem root directory.")

    # Check protected system directories
    if path_str_lower in PROTECTED_SYSTEM_PATHS:
        raise UnsafePathError(f"Operation refused: '{resolved}' is a protected system directory.")

    # Check un-subfoldered user home directory
    try:
        home_path = Path.home().resolve()
        if resolved == home_path:
            raise UnsafePathError(
                f"Operation refused: '{resolved}' is the home root directory. "
                "Please target a specific subfolder (e.g. ~/Downloads or ~/Desktop)."
            )
    except RuntimeError:
        pass

    return resolved


def is_protected_directory(path: Path) -> bool:
    """Check whether a directory is a VCS or environment directory that should not be entered.

    Args:
        path: Directory path to inspect.

    Returns:
        True if the directory name is in the protected set (.git, .venv, node_modules, etc.)
    """
    return path.name in _PROTECTED_DIR_NAMES


def is_hidden_or_system_file(path: Path) -> bool:
    """Check if a file is hidden, a known system file, or a symlink.

    Args:
        path: Path object to inspect.

    Returns:
        True if hidden, system file, or symlink.
    """
    if path.is_symlink():
        return True
    name = path.name.lower()
    if name.startswith("."):
        return True
    if name in {"desktop.ini", "thumbs.db", ".ds_store", "autorun.inf"}:
        return True
    return False


def walk_filtered(
    root: Path,
    *,
    recursive: bool = False,
    exclude_dirs: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    include_hidden: bool = False,
    include_hidden_files: Optional[bool] = None,
) -> Iterator[Path]:
    """Yield all files under *root* that pass safety filters.

    This is the central directory walker used by all scanning engines.
    It automatically skips symlinks, protected VCS/env dirs, and optionally
    hidden files and user-specified exclusion patterns.

    Args:
        root: Starting directory to walk.
        recursive: If False, only yield top-level files (non-recursive).
        exclude_dirs: Additional directory name patterns to skip (glob syntax).
        max_depth: Maximum recursion depth (None = unlimited).
        include_hidden: If True, include hidden (dot-prefixed) directories.
        include_hidden_files: If True, include hidden (dot-prefixed) files. Defaults to include_hidden.

    Yields:
        Path objects for each file that passes all filters.
    """
    exclude_set: Set[str] = set(exclude_dirs or [])
    allow_hidden_files = include_hidden if include_hidden_files is None else include_hidden_files

    def _should_skip_dir(d: Path, depth: int) -> bool:
        if d.is_symlink():
            return True
        if is_protected_directory(d):
            return True
        if not include_hidden and d.name.startswith("."):
            return True
        if max_depth is not None and depth >= max_depth:
            return True
        for pattern in exclude_set:
            if fnmatch.fnmatch(d.name, pattern):
                return True
        return False

    def _walk(directory: Path, depth: int) -> Iterator[Path]:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if recursive and not _should_skip_dir(entry, depth):
                    yield from _walk(entry, depth + 1)
            elif entry.is_file():
                if not allow_hidden_files and entry.name.startswith("."):
                    continue
                yield entry

    yield from _walk(root, depth=0)


def is_subpath(child_path: PathLike, parent_path: PathLike) -> bool:
    """Check if child_path is contained within parent_path.

    Args:
        child_path: Target child path.
        parent_path: Parent boundary path.

    Returns:
        True if child_path is equal to or inside parent_path.
    """
    resolved_child = normalize_path(child_path)
    resolved_parent = normalize_path(parent_path)
    try:
        resolved_child.relative_to(resolved_parent)
        return True
    except ValueError:
        return False


def safe_relative_to(path: PathLike, base: PathLike) -> Path:
    """Safely calculate relative path from base to path.

    Returns relative path if possible, or absolute path if on different roots.

    Args:
        path: Destination path.
        base: Base reference path.

    Returns:
        Relative path if under base, else absolute path.
    """
    resolved_path = normalize_path(path)
    resolved_base = normalize_path(base)
    try:
        return resolved_path.relative_to(resolved_base)
    except ValueError:
        return resolved_path


def format_size(size_bytes: int) -> str:
    """Format a byte count into a human-readable string (e.g. '4.2 MB').

    Args:
        size_bytes: Size in bytes.

    Returns:
        Human-readable size string.
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"
