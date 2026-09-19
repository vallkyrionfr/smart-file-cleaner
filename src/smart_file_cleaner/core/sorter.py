"""Core file organization engine for smart-file-cleaner.

Categorizes files based on file extension, checks for hidden/system files,
previews planned moves, and safely moves files with collision avoidance.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

from smart_file_cleaner.utils.path_utils import normalize_path

# Standard category subfolders and file extension mappings
CATEGORY_MAPPINGS: Dict[str, Set[str]] = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".ico", ".heic"},
    "Documents": {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".md", ".epub", ".pages"},
    "Spreadsheets": {".xlsx", ".xls", ".csv", ".ods", ".numbers"},
    "Presentations": {".pptx", ".ppt", ".key"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Archives": {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz"},
    "Code": {
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".rs",
        ".cpp",
        ".c",
        ".java",
        ".sh",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".sql",
        ".go",
        ".rb",
    },
    "Installers": {".exe", ".msi", ".deb", ".dmg", ".pkg", ".iso", ".appimage"},
}

# System files to ignore
SYSTEM_FILENAMES: Set[str] = {
    "desktop.ini",
    "thumbs.db",
    ".ds_store",
    "autorun.inf",
    "icon\r",
}

# Standard category directory names to avoid re-processing
RESERVED_CATEGORY_DIRS: Set[str] = set(CATEGORY_MAPPINGS.keys()) | {"Uncategorized", "SortLater"}


@dataclass
class FileMoveAction:
    """Represents a planned or executed file move action."""

    source: Path
    destination: Path
    category: str
    extension: str
    size_bytes: int
    is_collision: bool = False


def is_hidden_or_system_file(path: Path) -> bool:
    """Check if file is a hidden file, system file, or symlink.

    Args:
        path: Path object to inspect.

    Returns:
        bool: True if hidden, system file, or symlink, False otherwise.
    """
    # Ignore symlinks for safety
    if path.is_symlink():
        return True

    filename = path.name.lower()

    if filename.startswith("."):
        return True

    if filename in SYSTEM_FILENAMES:
        return True

    return False


def get_category_for_extension(ext: str) -> str:
    """Resolve category name for a given file extension.

    Args:
        ext: File extension string (e.g. '.pdf', '.PNG').

    Returns:
        str: Category name (e.g. 'Documents', 'Images', or 'Uncategorized').
    """
    clean_ext = ext.lower().strip()
    if not clean_ext:
        return "Uncategorized"

    for category, extensions in CATEGORY_MAPPINGS.items():
        if clean_ext in extensions:
            return category

    return "Uncategorized"


def get_unique_destination_path(target_path: Path) -> Path:
    """Generate a collision-free destination path by appending numerical suffixes.

    If target_path already exists, generates target_path_1.ext, target_path_2.ext, etc.

    Args:
        target_path: Desired target file path.

    Returns:
        Path: Unique target path that does not exist on disk.
    """
    if not target_path.exists():
        return target_path

    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def plan_organization(target_dir: Path) -> List[FileMoveAction]:
    """Scan target directory and generate planned move actions.

    Only scans top-level files in target_dir, skipping directories,
    symlinks, hidden files, system files, and reserved category folders.

    Args:
        target_dir: Directory path to organize.

    Returns:
        List[FileMoveAction]: Planned file move operations.
    """
    resolved_target = normalize_path(target_dir)
    moves: List[FileMoveAction] = []

    if not resolved_target.is_dir():
        return moves

    for item in resolved_target.iterdir():
        # Ignore symlinks for safety
        if item.is_symlink():
            continue

        # Ignore subdirectories (including reserved category directories)
        if item.is_dir():
            continue

        # Ignore hidden and system files
        if is_hidden_or_system_file(item):
            continue

        ext = item.suffix.lower()
        category = get_category_for_extension(ext)
        dest_dir = resolved_target / category
        desired_dest = dest_dir / item.name

        # Check if destination would collide
        unique_dest = get_unique_destination_path(desired_dest)
        is_collision = unique_dest != desired_dest

        try:
            file_size = item.stat().st_size
        except OSError:
            file_size = 0

        moves.append(
            FileMoveAction(
                source=item,
                destination=unique_dest,
                category=category,
                extension=ext or "[no ext]",
                size_bytes=file_size,
                is_collision=is_collision,
            )
        )

    return moves


def execute_organization(moves: List[FileMoveAction]) -> List[FileMoveAction]:
    """Execute planned file move operations safely.

    Creates target category directories as needed and moves files using
    unique destination paths to prevent overwriting existing files.

    Args:
        moves: List of FileMoveAction objects.

    Returns:
        List[FileMoveAction]: Executed actions with updated final destination paths.
    """
    executed: List[FileMoveAction] = []

    for action in moves:
        # Ignore symlinks or missing files
        if action.source.is_symlink() or not action.source.exists():
            continue

        # Ensure unique destination path at execution time to guarantee no overwrites
        final_dest = get_unique_destination_path(action.destination)
        final_dest.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(action.source), str(final_dest))

        executed.append(
            FileMoveAction(
                source=action.source,
                destination=final_dest,
                category=action.category,
                extension=action.extension,
                size_bytes=action.size_bytes,
                is_collision=final_dest != action.destination or action.is_collision,
            )
        )

    return executed
