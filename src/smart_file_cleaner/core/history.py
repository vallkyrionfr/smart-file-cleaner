"""Operation history and undo engine for smart-file-cleaner.

Stores atomic JSON manifests in the XDG-compliant data directory so that
any organize / clean / dedupe operation can be fully reversed by ``undo``.

Manifest schema::

    {
        "id": "20260920T001523",
        "operation": "organize",
        "timestamp": "2026-09-20T00:15:23Z",
        "target_dir": "/home/user/Downloads",
        "actions": [
            {"type": "move", "source": "/path/from", "destination": "/path/to"},
            {"type": "delete", "path": "/path/file"}
        ]
    }

At most MAX_MANIFESTS manifests are retained; older ones are pruned automatically.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from smart_file_cleaner.utils.config import get_history_dir
from smart_file_cleaner.utils.errors import HistoryCorruptError

MAX_MANIFESTS = 50


# ---------------------------------------------------------------------------
# Action records
# ---------------------------------------------------------------------------


@dataclass
class MoveAction:
    """Records a file move that can be reversed."""

    source: str
    destination: str
    type: str = "move"


@dataclass
class DeleteAction:
    """Records a file deletion (not reversible via undo, but logged for auditing)."""

    path: str
    type: str = "delete"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass
class OperationManifest:
    """Full record of a single CLI operation."""

    operation: str
    target_dir: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_move(self, source: Path, destination: Path) -> None:
        """Record a file move action."""
        self.actions.append(
            {"type": "move", "source": str(source), "destination": str(destination)}
        )

    def add_delete(self, path: Path) -> None:
        """Record a file deletion (not undoable)."""
        self.actions.append({"type": "delete", "path": str(path)})

    def is_empty(self) -> bool:
        """Return True if no actions were recorded."""
        return len(self.actions) == 0


# ---------------------------------------------------------------------------
# History engine
# ---------------------------------------------------------------------------


def _history_dir() -> Path:
    d = get_history_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_manifest(manifest: OperationManifest) -> Path:
    """Persist an operation manifest to disk.

    Args:
        manifest: Completed operation to save.

    Returns:
        Path to the written manifest file.
    """
    if manifest.is_empty():
        return Path("/dev/null")  # Don't write empty manifests

    history_dir = _history_dir()
    filename = f"{manifest.id}_{manifest.operation}.json"
    manifest_path = history_dir / filename

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(asdict(manifest), f, indent=2)

    _prune_old_manifests(history_dir)
    return manifest_path


def list_manifests(n: int = 10) -> List[Dict[str, Any]]:
    """Return the N most recent operation manifests.

    Args:
        n: Maximum number of manifests to return.

    Returns:
        List of manifest dicts, most recent first.
    """
    history_dir = _history_dir()
    manifests = sorted(history_dir.glob("*.json"), reverse=True)
    results = []
    for p in manifests[:n]:
        try:
            with open(p, encoding="utf-8") as f:
                results.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def undo_last(dry_run: bool = True) -> Optional[Dict[str, Any]]:
    """Reverse the most recent undoable operation.

    Only 'move' actions are reversible. 'delete' actions are skipped.

    Args:
        dry_run: If True, preview what would be undone without making changes.

    Returns:
        The manifest that was (or would be) undone, or None if no history exists.

    Raises:
        HistoryCorruptError: If the manifest file is unreadable or malformed.
    """
    history_dir = _history_dir()
    manifests = sorted(history_dir.glob("*.json"), reverse=True)

    if not manifests:
        return None

    manifest_path = manifests[0]
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HistoryCorruptError(f"Cannot read manifest '{manifest_path.name}': {exc}") from exc

    if not dry_run:
        _execute_undo(manifest)
        manifest_path.unlink(missing_ok=True)

    return manifest


def undo_by_id(manifest_id: str, dry_run: bool = True) -> Optional[Dict[str, Any]]:
    """Reverse a specific operation by its ID.

    Args:
        manifest_id: The manifest ID (e.g. '20260920T001523').
        dry_run: If True, preview without making changes.

    Returns:
        The matching manifest dict, or None if not found.

    Raises:
        HistoryCorruptError: If the manifest is unreadable.
    """
    history_dir = _history_dir()
    matches = list(history_dir.glob(f"{manifest_id}_*.json"))
    if not matches:
        return None

    manifest_path = matches[0]
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise HistoryCorruptError(f"Cannot read manifest '{manifest_path.name}': {exc}") from exc

    if not dry_run:
        _execute_undo(manifest)
        manifest_path.unlink(missing_ok=True)

    return manifest


def _execute_undo(manifest: Dict[str, Any]) -> None:
    """Reverse all 'move' actions in a manifest."""
    for action in reversed(manifest.get("actions", [])):
        if action.get("type") != "move":
            continue
        src = Path(action["destination"])
        dst = Path(action["source"])

        if not src.exists():
            continue  # File already gone, skip

        dst.parent.mkdir(parents=True, exist_ok=True)

        # If destination exists, generate a unique name to avoid overwriting
        if dst.exists():
            stem, suffix = dst.stem, dst.suffix
            counter = 1
            while dst.exists():
                dst = dst.parent / f"{stem}_restored_{counter}{suffix}"
                counter += 1

        shutil.move(str(src), str(dst))


def _prune_old_manifests(history_dir: Path) -> None:
    """Remove oldest manifests beyond MAX_MANIFESTS."""
    manifests = sorted(history_dir.glob("*.json"), reverse=True)
    for old in manifests[MAX_MANIFESTS:]:
        old.unlink(missing_ok=True)
