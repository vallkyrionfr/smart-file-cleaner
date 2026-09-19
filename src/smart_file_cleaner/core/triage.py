"""Core triage and analysis engine for smart-file-cleaner review command.

Analyzes messy directories and groups files into smart triage buckets:
- Unused Installers (.exe, .msi, .deb, .iso, .dmg, .pkg, .appimage)
- Stale Files (untouched for 30+ days)
- Large Files (file size >= 100MB)
- Uncategorized Clutter
"""

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from smart_file_cleaner.core.sorter import (
    get_category_for_extension,
    get_unique_destination_path,
    is_hidden_or_system_file,
)
from smart_file_cleaner.utils.path_utils import normalize_path

INSTALLER_EXTENSIONS: Set[str] = {".exe", ".msi", ".deb", ".iso", ".dmg", ".pkg", ".appimage"}

SECONDS_PER_DAY = 86400


@dataclass
class TriageFileItem:
    """Represents a file evaluated for triage."""

    path: Path
    filename: str
    size_bytes: int
    mtime: float
    age_days: float
    extension: str
    buckets: List[str] = field(default_factory=list)


@dataclass
class TriageAnalysisResult:
    """Container for grouped triage analysis results."""

    target_dir: Path
    installers: List[TriageFileItem] = field(default_factory=list)
    stale_files: List[TriageFileItem] = field(default_factory=list)
    large_files: List[TriageFileItem] = field(default_factory=list)
    clutter: List[TriageFileItem] = field(default_factory=list)
    all_files: List[TriageFileItem] = field(default_factory=list)


def analyze_directory_for_triage(
    target_dir: Path,
    stale_days: int = 30,
    large_mb: float = 100.0,
    current_timestamp: Optional[float] = None,
) -> TriageAnalysisResult:
    """Analyze target directory and categorize files into smart triage buckets.

    Args:
        target_dir: Directory path to inspect.
        stale_days: Threshold in days for stale files (default: 30 days).
        large_mb: Threshold in megabytes for large files (default: 100 MB).
        current_timestamp: Optional explicit timestamp for testing/mocking.

    Returns:
        TriageAnalysisResult: Grouped file items by bucket.
    """
    resolved_target = normalize_path(target_dir)
    result = TriageAnalysisResult(target_dir=resolved_target)

    if not resolved_target.is_dir():
        return result

    now = current_timestamp if current_timestamp is not None else time.time()
    large_bytes_threshold = large_mb * 1024 * 1024
    stale_seconds_threshold = stale_days * SECONDS_PER_DAY

    for item in resolved_target.iterdir():
        # Ignore symlinks for security
        if item.is_symlink():
            continue

        if item.is_dir():
            continue

        if is_hidden_or_system_file(item):
            continue

        try:
            stat_info = item.stat()
            file_size = stat_info.st_size
            mtime = stat_info.st_mtime
        except OSError:
            file_size = 0
            mtime = now

        age_days = max(0.0, (now - mtime) / SECONDS_PER_DAY)
        ext = item.suffix.lower()

        triage_item = TriageFileItem(
            path=item,
            filename=item.name,
            size_bytes=file_size,
            mtime=mtime,
            age_days=round(age_days, 1),
            extension=ext or "[no ext]",
        )

        matched_specific_bucket = False

        # 1. Unused Installers
        if ext in INSTALLER_EXTENSIONS:
            triage_item.buckets.append("Installers")
            result.installers.append(triage_item)
            matched_specific_bucket = True

        # 2. Large Files
        if file_size >= large_bytes_threshold:
            triage_item.buckets.append("Large Files")
            result.large_files.append(triage_item)
            matched_specific_bucket = True

        # 3. Stale Files
        if (now - mtime) >= stale_seconds_threshold:
            triage_item.buckets.append("Stale Files")
            result.stale_files.append(triage_item)
            matched_specific_bucket = True

        # 4. Uncategorized Clutter
        if not matched_specific_bucket:
            triage_item.buckets.append("Clutter")
            result.clutter.append(triage_item)

        result.all_files.append(triage_item)

    return result


def move_to_sort_later(item_path: Path, target_dir: Path) -> Path:
    """Move file to target_dir/SortLater subfolder safely.

    Args:
        item_path: File path to move.
        target_dir: Base target directory containing SortLater.

    Returns:
        Path: Destination path of moved file.
    """
    if item_path.is_symlink():
        return item_path

    sort_later_dir = target_dir / "SortLater"
    sort_later_dir.mkdir(parents=True, exist_ok=True)

    dest = get_unique_destination_path(sort_later_dir / item_path.name)
    shutil.move(str(item_path), str(dest))
    return dest


def auto_sort_file(item_path: Path, target_dir: Path) -> Path:
    """Auto-sort a single file into its extension category subfolder.

    Args:
        item_path: File path to move.
        target_dir: Base target directory.

    Returns:
        Path: Destination path of moved file.
    """
    if item_path.is_symlink():
        return item_path

    ext = item_path.suffix.lower()
    category = get_category_for_extension(ext)
    category_dir = target_dir / category
    category_dir.mkdir(parents=True, exist_ok=True)

    dest = get_unique_destination_path(category_dir / item_path.name)
    shutil.move(str(item_path), str(dest))
    return dest
