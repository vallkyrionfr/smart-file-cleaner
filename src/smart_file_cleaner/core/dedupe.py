"""Fast 3-tier duplicate file detection engine for smart-file-cleaner.

Detection algorithm (in order of cheapness):
  Tier 1 — Exact byte-size bucketing (os.stat). Unique sizes are instantly skipped.
  Tier 2 — First 4 KB partial hash. Filters most non-duplicates cheaply.
  Tier 3 — Full SHA-256 content hash. Definitive match confirmation.

Resolution strategies:
  - keep_newest   : Keep the file with the most recent mtime.
  - keep_oldest   : Keep the file with the oldest mtime.
  - interactive   : Return groups for the CLI layer to present interactively.

All duplicates are moved to the OS Trash (or hard-deleted with permanent=True).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from smart_file_cleaner.core.history import OperationManifest
from smart_file_cleaner.utils.path_utils import format_size, walk_filtered
from smart_file_cleaner.utils.signals import shutdown_requested
from smart_file_cleaner.utils.trash import safe_delete

_PARTIAL_HASH_BYTES = 4096


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DuplicateGroup:
    """A group of files with identical content."""

    files: List[Path]
    size_bytes: int

    @property
    def wasted_bytes(self) -> int:
        """Bytes wasted by duplicates (all but one copy)."""
        return self.size_bytes * (len(self.files) - 1)

    @property
    def display_size(self) -> str:
        return format_size(self.size_bytes)

    @property
    def display_wasted(self) -> str:
        return format_size(self.wasted_bytes)


@dataclass
class DedupeResult:
    """Result of a duplicate scan."""

    root: Path
    groups: List[DuplicateGroup] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def total_wasted_bytes(self) -> int:
        return sum(g.wasted_bytes for g in self.groups)

    @property
    def total_wasted_display(self) -> str:
        return format_size(self.total_wasted_bytes)


@dataclass
class DedupeCleanResult:
    """Result after resolving duplicates."""

    removed: List[Path] = field(default_factory=list)
    kept: List[Path] = field(default_factory=list)
    failed: List[Tuple[Path, str]] = field(default_factory=list)

    @property
    def total_reclaimed_bytes(self) -> int:
        return sum(_file_size(p) for p in self.removed)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def _partial_hash(path: Path) -> Optional[str]:
    """Hash the first 4 KB of a file."""
    try:
        with open(path, "rb") as f:
            data = f.read(_PARTIAL_HASH_BYTES)
        return hashlib.sha256(data).hexdigest()
    except (OSError, PermissionError):
        return None


def _full_hash(path: Path) -> Optional[str]:
    """Compute the full SHA-256 hash of a file in streaming chunks."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except (OSError, PermissionError):
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_for_duplicates(
    root: Path,
    *,
    recursive: bool = False,
    min_size_bytes: int = 1,
    progress_callback=None,
) -> DedupeResult:
    """Scan a directory for duplicate files using 3-tier hash detection.

    Args:
        root: Directory to scan.
        recursive: Whether to recurse into subdirectories.
        min_size_bytes: Minimum file size to consider (skip 0-byte files by default).
        progress_callback: Optional callable(path) called for each file visited.

    Returns:
        DedupeResult containing all groups of duplicate files.
    """
    result = DedupeResult(root=root)

    # --- Tier 1: Group by file size ---
    size_buckets: Dict[int, List[Path]] = {}
    for path in walk_filtered(root, recursive=recursive):
        if shutdown_requested():
            break
        if progress_callback:
            progress_callback(path)
        result.scanned_files += 1
        size = _file_size(path)
        if size < min_size_bytes:
            continue
        size_buckets.setdefault(size, []).append(path)

    # Only sizes with 2+ files are candidates
    candidates = {sz: paths for sz, paths in size_buckets.items() if len(paths) > 1}
    if not candidates:
        return result

    # --- Tier 2: Group by partial (first 4 KB) hash ---
    partial_buckets: Dict[str, List[Path]] = {}
    for paths in candidates.values():
        for path in paths:
            if shutdown_requested():
                return result
            ph = _partial_hash(path)
            if ph:
                partial_buckets.setdefault(ph, []).append(path)

    partial_candidates = {h: paths for h, paths in partial_buckets.items() if len(paths) > 1}
    if not partial_candidates:
        return result

    # --- Tier 3: Group by full SHA-256 hash ---
    full_buckets: Dict[str, List[Path]] = {}
    for paths in partial_candidates.values():
        for path in paths:
            if shutdown_requested():
                return result
            fh = _full_hash(path)
            if fh:
                full_buckets.setdefault(fh, []).append(path)

    for paths in full_buckets.values():
        if len(paths) > 1:
            size = _file_size(paths[0])
            result.groups.append(DuplicateGroup(files=paths, size_bytes=size))

    return result


def resolve_duplicates(
    dedupe_result: DedupeResult,
    manifest: OperationManifest,
    *,
    keep_strategy: str = "newest",
    permanent: bool = False,
    interactive_choices: Optional[Dict[int, Path]] = None,
) -> DedupeCleanResult:
    """Remove duplicate files based on a resolution strategy.

    Args:
        dedupe_result: Previously computed scan result.
        manifest: Operation manifest to log actions into.
        keep_strategy: 'newest', 'oldest', or 'interactive'.
        permanent: If True, permanently delete duplicates instead of trashing.
        interactive_choices: Dict mapping group index → path to keep (for interactive mode).

    Returns:
        DedupeCleanResult with removed, kept, and failed files.
    """
    clean_result = DedupeCleanResult()

    for idx, group in enumerate(dedupe_result.groups):
        if shutdown_requested():
            break

        keep: Optional[Path] = None

        if keep_strategy == "newest":
            keep = max(group.files, key=lambda p: _mtime(p))
        elif keep_strategy == "oldest":
            keep = min(group.files, key=lambda p: _mtime(p))
        elif keep_strategy == "interactive" and interactive_choices:
            keep = interactive_choices.get(idx)

        if keep is None:
            # Fallback: keep the first file alphabetically
            keep = min(group.files, key=lambda p: str(p))

        for dup in group.files:
            if dup == keep:
                clean_result.kept.append(dup)
                continue
            try:
                safe_delete(dup, permanent=permanent)
                manifest.add_delete(dup)
                clean_result.removed.append(dup)
            except Exception as exc:
                clean_result.failed.append((dup, str(exc)))

    return clean_result


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except (OSError, PermissionError):
        return 0.0
