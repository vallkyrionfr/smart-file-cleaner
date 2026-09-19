"""Cross-platform trash / safe-delete adapter for smart-file-cleaner.

Provides a unified interface for removing files and directories:

- Default behaviour: moves to OS-native Trash / Recycle Bin via send2trash.
- Permanent deletion (``permanent=True``): irreversibly removes with
  os.unlink / shutil.rmtree. Requires explicit opt-in.

Usage::

    from smart_file_cleaner.utils.trash import safe_delete

    safe_delete(path)                   # → OS Trash
    safe_delete(path, permanent=True)   # → permanent delete
"""

from __future__ import annotations

import shutil
from pathlib import Path

from smart_file_cleaner.utils.errors import TrashError

try:
    import send2trash
except ImportError:
    send2trash = None


def safe_delete(path: Path, permanent: bool = False) -> None:
    """Delete a file or directory safely.

    By default, moves the path to the OS-native Trash / Recycle Bin.
    Pass ``permanent=True`` to perform an irreversible hard delete.

    Args:
        path: File or directory to remove.
        permanent: If True, permanently delete instead of trashing.

    Raises:
        TrashError: If the trash operation fails or send2trash is unavailable
            and permanent deletion was not requested.
        FileNotFoundError: If the path does not exist.
    """
    if not path.exists() and not path.is_symlink():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if permanent:
        _permanent_delete(path)
    else:
        _trash(path)


def _trash(path: Path) -> None:
    """Move path to the OS-native Trash."""
    if send2trash is None:
        raise TrashError(
            "send2trash is not installed. Install it with: "
            "pip install send2trash\n"
            "Or pass --permanent to delete files directly."
        )
    try:
        send2trash.send2trash(str(path))
    except Exception as exc:
        raise TrashError(f"Failed to move '{path}' to Trash: {exc}") from exc


def _permanent_delete(path: Path) -> None:
    """Permanently and irreversibly delete a file or directory."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        raise TrashError(f"Failed to permanently delete '{path}': {exc}") from exc
