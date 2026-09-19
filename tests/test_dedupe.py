"""Tests for the 3-tier duplicate detection engine (core/dedupe.py)."""

from pathlib import Path

from smart_file_cleaner.core.dedupe import (
    _full_hash,
    _partial_hash,
    resolve_duplicates,
    scan_for_duplicates,
)
from smart_file_cleaner.core.history import OperationManifest

# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


class TestHashing:
    def test_partial_hash_returns_string(self, tmp_path: Path):
        f = tmp_path / "file.bin"
        f.write_bytes(b"hello world")
        h = _partial_hash(f)
        assert h is not None
        assert len(h) == 64  # SHA-256 hex digest

    def test_full_hash_returns_string(self, tmp_path: Path):
        f = tmp_path / "file.bin"
        f.write_bytes(b"hello world")
        h = _full_hash(f)
        assert h is not None
        assert len(h) == 64

    def test_identical_content_same_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        content = b"identical content"
        f1.write_bytes(content)
        f2.write_bytes(content)
        assert _full_hash(f1) == _full_hash(f2)

    def test_different_content_different_hash(self, tmp_path: Path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert _full_hash(f1) != _full_hash(f2)

    def test_partial_hash_nonexistent_returns_none(self, tmp_path: Path):
        fake = tmp_path / "ghost.bin"
        assert _partial_hash(fake) is None

    def test_full_hash_nonexistent_returns_none(self, tmp_path: Path):
        fake = tmp_path / "ghost.bin"
        assert _full_hash(fake) is None


# ---------------------------------------------------------------------------
# scan_for_duplicates
# ---------------------------------------------------------------------------


class TestScanForDuplicates:
    def test_no_duplicates(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("file A")
        (tmp_path / "b.txt").write_text("file B")
        result = scan_for_duplicates(tmp_path)
        assert result.groups == []

    def test_finds_duplicate_pair(self, tmp_path: Path):
        content = b"duplicate data"
        (tmp_path / "copy1.txt").write_bytes(content)
        (tmp_path / "copy2.txt").write_bytes(content)
        (tmp_path / "unique.txt").write_text("something else")

        result = scan_for_duplicates(tmp_path)
        assert len(result.groups) == 1
        assert len(result.groups[0].files) == 2

    def test_finds_triplicate(self, tmp_path: Path):
        content = b"same data everywhere"
        for i in range(3):
            (tmp_path / f"copy{i}.bin").write_bytes(content)

        result = scan_for_duplicates(tmp_path)
        assert len(result.groups) == 1
        assert len(result.groups[0].files) == 3

    def test_skips_empty_files_by_default(self, tmp_path: Path):
        (tmp_path / "empty1.txt").write_bytes(b"")
        (tmp_path / "empty2.txt").write_bytes(b"")
        result = scan_for_duplicates(tmp_path, min_size_bytes=1)
        assert result.groups == []

    def test_empty_files_included_at_zero_min_size(self, tmp_path: Path):
        (tmp_path / "empty1.txt").write_bytes(b"")
        (tmp_path / "empty2.txt").write_bytes(b"")
        result = scan_for_duplicates(tmp_path, min_size_bytes=0)
        assert len(result.groups) == 1

    def test_same_size_different_content_not_duplicate(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"aaaa")
        (tmp_path / "b.txt").write_bytes(b"bbbb")
        result = scan_for_duplicates(tmp_path)
        assert result.groups == []

    def test_skips_git_directory(self, tmp_path: Path):
        content = b"important git data"
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_bytes(content)
        (tmp_path / "same_content.txt").write_bytes(content)
        result = scan_for_duplicates(tmp_path, recursive=True)
        # Should not detect duplicate between .git internals and user files
        assert all(".git" not in str(f) for g in result.groups for f in g.files)

    def test_recursive_finds_nested_duplicates(self, tmp_path: Path):
        content = b"deeply nested duplicate"
        (tmp_path / "original.bin").write_bytes(content)
        sub = tmp_path / "subfolder"
        sub.mkdir()
        (sub / "copy.bin").write_bytes(content)

        result = scan_for_duplicates(tmp_path, recursive=True)
        assert len(result.groups) == 1

    def test_wasted_bytes_calculation(self, tmp_path: Path):
        content = b"x" * 100
        (tmp_path / "a.bin").write_bytes(content)
        (tmp_path / "b.bin").write_bytes(content)
        result = scan_for_duplicates(tmp_path)
        assert result.groups[0].wasted_bytes == 100  # 2 copies * 100B - 1 kept = 100B wasted

    def test_total_wasted_bytes(self, tmp_path: Path):
        content = b"y" * 50
        (tmp_path / "c.bin").write_bytes(content)
        (tmp_path / "d.bin").write_bytes(content)
        result = scan_for_duplicates(tmp_path)
        assert result.total_wasted_bytes == 50


# ---------------------------------------------------------------------------
# resolve_duplicates
# ---------------------------------------------------------------------------


class TestResolveDuplicates:
    def _make_dupes(self, tmp_path: Path, content: bytes = b"dupe"):
        f1 = tmp_path / "oldest.txt"
        f2 = tmp_path / "newest.txt"
        f1.write_bytes(content)
        f2.write_bytes(content)
        # Make f1 older by touching with older time
        import os
        import time

        older_time = time.time() - 1000
        os.utime(f1, (older_time, older_time))
        return f1, f2

    def test_keep_newest_removes_oldest(self, tmp_path: Path):
        oldest, newest = self._make_dupes(tmp_path)
        result = scan_for_duplicates(tmp_path)
        manifest = OperationManifest(operation="dedupe", target_dir=str(tmp_path))

        clean = resolve_duplicates(result, manifest, keep_strategy="newest", permanent=True)
        assert not oldest.exists()
        assert newest.exists()

    def test_keep_oldest_removes_newest(self, tmp_path: Path):
        oldest, newest = self._make_dupes(tmp_path)
        result = scan_for_duplicates(tmp_path)
        manifest = OperationManifest(operation="dedupe", target_dir=str(tmp_path))

        clean = resolve_duplicates(result, manifest, keep_strategy="oldest", permanent=True)
        assert oldest.exists()
        assert not newest.exists()

    def test_no_groups_does_nothing(self, tmp_path: Path):
        from smart_file_cleaner.core.dedupe import DedupeResult

        empty = DedupeResult(root=tmp_path)
        manifest = OperationManifest(operation="dedupe", target_dir=str(tmp_path))

        clean = resolve_duplicates(empty, manifest, keep_strategy="newest", permanent=True)
        assert clean.removed == []
        assert clean.kept == []
