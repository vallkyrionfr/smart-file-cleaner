"""Disk usage analysis engine for smart-file-cleaner.

Provides category-wise storage breakdown, top-N largest files,
stale file detection, and reclaimable space estimates.

The engine is pure computation — no CLI/Rich code here.
The CLI command (commands/analyze.py) handles all rendering.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from smart_file_cleaner.core.sorter import get_category_for_extension
from smart_file_cleaner.utils.path_utils import format_size, walk_filtered
from smart_file_cleaner.utils.signals import shutdown_requested

SECONDS_PER_DAY = 86_400


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """Represents a single file in the analysis."""

    path: Path
    size_bytes: int
    mtime: float
    category: str

    @property
    def age_days(self) -> float:
        return max(0.0, (time.time() - self.mtime) / SECONDS_PER_DAY)

    @property
    def display_size(self) -> str:
        return format_size(self.size_bytes)


@dataclass
class AnalysisResult:
    """Full disk analysis result for a directory."""

    root: Path
    total_files: int = 0
    total_bytes: int = 0
    category_bytes: Dict[str, int] = field(default_factory=dict)
    category_counts: Dict[str, int] = field(default_factory=dict)
    top_files: List[FileEntry] = field(default_factory=list)
    stale_files: List[FileEntry] = field(default_factory=list)
    all_files: List[FileEntry] = field(default_factory=list)

    @property
    def total_display(self) -> str:
        return format_size(self.total_bytes)

    def category_display(self, cat: str) -> str:
        return format_size(self.category_bytes.get(cat, 0))

    @property
    def largest_category(self) -> Optional[str]:
        if not self.category_bytes:
            return None
        return max(self.category_bytes, key=lambda c: self.category_bytes[c])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_directory(
    root: Path,
    *,
    recursive: bool = False,
    top_n: int = 10,
    stale_days: int = 30,
    progress_callback=None,
    current_timestamp: Optional[float] = None,
) -> AnalysisResult:
    """Analyze a directory and return storage statistics.

    Args:
        root: Directory to analyze.
        recursive: Whether to recurse into subdirectories.
        top_n: Number of largest files to include in results.
        stale_days: Age threshold in days for "stale" files.
        progress_callback: Optional callable(path) called per file.
        current_timestamp: Override current time (for testing).

    Returns:
        AnalysisResult with full disk breakdown.
    """
    now = current_timestamp or time.time()
    stale_threshold = stale_days * SECONDS_PER_DAY
    result = AnalysisResult(root=root)
    all_entries: List[FileEntry] = []

    for path in walk_filtered(root, recursive=recursive):
        if shutdown_requested():
            break
        if progress_callback:
            progress_callback(path)

        try:
            stat = path.stat()
            size = stat.st_size
            mtime = stat.st_mtime
        except (OSError, PermissionError):
            size, mtime = 0, now

        ext = path.suffix.lower()
        category = get_category_for_extension(ext)

        entry = FileEntry(path=path, size_bytes=size, mtime=mtime, category=category)
        all_entries.append(entry)

        result.total_files += 1
        result.total_bytes += size
        result.category_bytes[category] = result.category_bytes.get(category, 0) + size
        result.category_counts[category] = result.category_counts.get(category, 0) + 1

        if (now - mtime) >= stale_threshold:
            result.stale_files.append(entry)

    # Sort for top-N largest
    result.all_files = all_entries
    result.top_files = sorted(all_entries, key=lambda e: e.size_bytes, reverse=True)[:top_n]
    result.stale_files.sort(key=lambda e: e.mtime)  # oldest first

    return result
