"""Tests for the operation history and undo engine (core/history.py)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_file_cleaner.core.history import (
    MAX_MANIFESTS,
    OperationManifest,
    _prune_old_manifests,
    list_manifests,
    save_manifest,
    undo_last,
)
from smart_file_cleaner.utils.errors import HistoryCorruptError


class TestOperationManifest:
    def test_default_id_and_timestamp(self):
        m = OperationManifest(operation="organize", target_dir="/tmp/test")
        assert m.id  # non-empty
        assert m.timestamp  # non-empty
        assert m.operation == "organize"
        assert m.actions == []

    def test_add_move(self, tmp_path: Path):
        m = OperationManifest(operation="organize", target_dir=str(tmp_path))
        m.add_move(tmp_path / "a.txt", tmp_path / "Documents/a.txt")
        assert len(m.actions) == 1
        assert m.actions[0]["type"] == "move"
        assert "a.txt" in m.actions[0]["source"]

    def test_add_delete(self, tmp_path: Path):
        m = OperationManifest(operation="clean", target_dir=str(tmp_path))
        m.add_delete(tmp_path / "junk.tmp")
        assert len(m.actions) == 1
        assert m.actions[0]["type"] == "delete"

    def test_is_empty_true_when_no_actions(self):
        m = OperationManifest(operation="clean", target_dir="/tmp")
        assert m.is_empty()

    def test_is_empty_false_after_action(self, tmp_path: Path):
        m = OperationManifest(operation="clean", target_dir="/tmp")
        m.add_delete(tmp_path / "junk.tmp")
        assert not m.is_empty()


class TestSaveManifest:
    def test_saves_to_disk(self, tmp_path: Path):
        m = OperationManifest(operation="organize", target_dir=str(tmp_path))
        m.add_move(tmp_path / "a.txt", tmp_path / "b.txt")

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            path = save_manifest(m)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["operation"] == "organize"

    def test_empty_manifest_not_saved(self, tmp_path: Path):
        m = OperationManifest(operation="clean", target_dir="/tmp")

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            save_manifest(m)

        assert list(tmp_path.glob("*.json")) == []


class TestListManifests:
    def test_returns_empty_when_no_history(self, tmp_path: Path):
        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            manifests = list_manifests()
        assert manifests == []

    def test_returns_manifests_most_recent_first(self, tmp_path: Path):
        for i, name in enumerate(["20260101T000001_organize.json", "20260102T000001_clean.json"]):
            (tmp_path / name).write_text(
                json.dumps(
                    {
                        "id": f"2026010{i + 1}T000001",
                        "operation": "organize" if i == 0 else "clean",
                        "timestamp": f"2026-01-0{i + 1}T00:00:01Z",
                        "target_dir": "/tmp",
                        "actions": [{"type": "move", "source": "a", "destination": "b"}],
                    }
                )
            )

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            manifests = list_manifests(n=2)

        assert len(manifests) == 2
        # Most recent (alphabetically last) should be first
        assert manifests[0]["id"] > manifests[1]["id"]

    def test_skips_corrupt_files(self, tmp_path: Path):
        (tmp_path / "20260101T000001_organize.json").write_text("NOT VALID JSON {{{")
        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            manifests = list_manifests()
        assert manifests == []


class TestUndoLast:
    def test_returns_none_when_no_history(self, tmp_path: Path):
        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            result = undo_last(dry_run=True)
        assert result is None

    def test_dry_run_does_not_move_files(self, tmp_path: Path):
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        # Simulate: file was moved from src → dst; dst exists
        dst.write_text("moved content")

        manifest = {
            "id": "20260101T000001",
            "operation": "organize",
            "timestamp": "2026-01-01T00:00:01Z",
            "target_dir": str(tmp_path),
            "actions": [{"type": "move", "source": str(src), "destination": str(dst)}],
        }
        mf = tmp_path / "20260101T000001_organize.json"
        mf.write_text(json.dumps(manifest))

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            undo_last(dry_run=True)

        # dry_run: dst should still exist; undo not applied
        assert dst.exists()
        assert mf.exists()  # Manifest not deleted in dry_run

    def test_execute_reverses_move(self, tmp_path: Path):
        src = tmp_path / "original_location.txt"
        dst = tmp_path / "moved_location.txt"
        dst.write_text("content after move")

        manifest = {
            "id": "20260101T000001",
            "operation": "organize",
            "timestamp": "2026-01-01T00:00:01Z",
            "target_dir": str(tmp_path),
            "actions": [{"type": "move", "source": str(src), "destination": str(dst)}],
        }
        mf = tmp_path / "20260101T000001_organize.json"
        mf.write_text(json.dumps(manifest))

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            undo_last(dry_run=False)

        assert src.exists()  # File restored to original location
        assert not dst.exists()
        assert not mf.exists()  # Manifest deleted after undo

    def test_raises_on_corrupt_manifest(self, tmp_path: Path):
        mf = tmp_path / "20260101T000001_organize.json"
        mf.write_text("BROKEN")

        with patch("smart_file_cleaner.core.history.get_history_dir", return_value=tmp_path):
            with pytest.raises(HistoryCorruptError):
                undo_last(dry_run=False)


class TestPruneOldManifests:
    def test_prunes_beyond_max(self, tmp_path: Path):
        for i in range(MAX_MANIFESTS + 5):
            (tmp_path / f"2026010{i:02d}T000001_organize.json").write_text("{}")

        _prune_old_manifests(tmp_path)
        remaining = list(tmp_path.glob("*.json"))
        assert len(remaining) == MAX_MANIFESTS
