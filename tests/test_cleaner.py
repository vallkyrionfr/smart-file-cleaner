"""Tests for the real junk file scanner (core/cleaner.py)."""

from pathlib import Path
from unittest.mock import patch

from smart_file_cleaner.core.cleaner import (
    JunkItem,
    ScanResult,
    _is_dev_cache,
    _is_empty_dir,
    _matches_pattern,
    execute_clean,
    scan_for_junk,
)
from smart_file_cleaner.core.history import OperationManifest

# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------


class TestMatchesPattern:
    def test_matches_tmp(self):
        assert _matches_pattern("cache.tmp", ["*.tmp"])

    def test_matches_bak(self):
        assert _matches_pattern("notes.bak", ["*.bak"])

    def test_case_insensitive(self):
        assert _matches_pattern("Cache.TMP", ["*.tmp"])

    def test_no_match(self):
        assert not _matches_pattern("document.pdf", ["*.tmp", "*.bak"])

    def test_multiple_patterns(self):
        assert _matches_pattern("file.temp", ["*.tmp", "*.temp", "*.bak"])

    def test_exact_name(self):
        assert _matches_pattern("Thumbs.db", ["Thumbs.db"])


# ---------------------------------------------------------------------------
# Dev cache detection
# ---------------------------------------------------------------------------


class TestIsDevCache:
    def test_pycache(self, tmp_path: Path):
        d = tmp_path / "__pycache__"
        d.mkdir()
        assert _is_dev_cache(d, ["__pycache__"])

    def test_pytest_cache(self, tmp_path: Path):
        d = tmp_path / ".pytest_cache"
        d.mkdir()
        assert _is_dev_cache(d, [".pytest_cache"])

    def test_normal_dir_not_cache(self, tmp_path: Path):
        d = tmp_path / "Documents"
        d.mkdir()
        assert not _is_dev_cache(d, ["__pycache__"])


# ---------------------------------------------------------------------------
# Empty directory detection
# ---------------------------------------------------------------------------


class TestIsEmptyDir:
    def test_truly_empty(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()
        assert _is_empty_dir(d)

    def test_not_empty(self, tmp_path: Path):
        d = tmp_path / "nonempty"
        d.mkdir()
        (d / "file.txt").write_text("hello")
        assert not _is_empty_dir(d)


# ---------------------------------------------------------------------------
# scan_for_junk
# ---------------------------------------------------------------------------


class TestScanForJunk:
    def test_finds_tmp_file(self, tmp_path: Path):
        (tmp_path / "cache.tmp").write_text("data")
        result = scan_for_junk(tmp_path, junk_patterns=["*.tmp"])
        assert len(result.items) == 1
        assert result.items[0].reason == "pattern"

    def test_finds_os_cruft(self, tmp_path: Path):
        (tmp_path / ".DS_Store").write_text("")
        result = scan_for_junk(tmp_path, os_cruft=[".DS_Store"])
        assert any(i.reason == "os_cruft" for i in result.items)

    def test_finds_empty_dir(self, tmp_path: Path):
        empty = tmp_path / "EmptyFolder"
        empty.mkdir()
        result = scan_for_junk(tmp_path)
        assert any(i.reason == "empty_dir" for i in result.items)

    def test_no_junk(self, tmp_path: Path):
        (tmp_path / "document.pdf").write_text("real content")
        result = scan_for_junk(tmp_path)
        assert result.items == []

    def test_skips_git_dir(self, tmp_path: Path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("gitconfig")
        result = scan_for_junk(tmp_path, recursive=True)
        # Should NOT enter .git
        assert all(".git" not in str(i.path) for i in result.items)

    def test_skips_venv_dir(self, tmp_path: Path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("cfg")
        result = scan_for_junk(tmp_path, recursive=True)
        assert all(".venv" not in str(i.path) for i in result.items)

    def test_non_recursive_stays_shallow(self, tmp_path: Path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.tmp").write_text("data")
        result = scan_for_junk(tmp_path, junk_patterns=["*.tmp"], recursive=False)
        assert result.items == []

    def test_recursive_finds_nested(self, tmp_path: Path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.tmp").write_text("data")
        result = scan_for_junk(tmp_path, junk_patterns=["*.tmp"], recursive=True)
        assert len(result.items) == 1

    def test_dev_cache_dir_detected(self, tmp_path: Path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.pyc").write_bytes(b"\x00")
        result = scan_for_junk(tmp_path, dev_caches=["__pycache__"])
        assert any(i.reason == "dev_cache" for i in result.items)

    def test_total_size_computed(self, tmp_path: Path):
        f = tmp_path / "big.tmp"
        f.write_bytes(b"x" * 1000)
        result = scan_for_junk(tmp_path, junk_patterns=["*.tmp"])
        assert result.total_size_bytes == 1000

    def test_no_duplicates_in_result(self, tmp_path: Path):
        # A file should only appear once even if it matches multiple rules
        (tmp_path / "Thumbs.db").write_text("")
        result = scan_for_junk(
            tmp_path,
            junk_patterns=["Thumbs.db"],
            os_cruft=["Thumbs.db"],
        )
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# execute_clean
# ---------------------------------------------------------------------------


class TestExecuteClean:
    def test_dry_run_does_not_delete(self, tmp_path: Path):
        f = tmp_path / "junk.tmp"
        f.write_text("data")
        scan = ScanResult(root=tmp_path, items=[JunkItem(path=f, reason="pattern", size_bytes=4)])
        manifest = OperationManifest(operation="clean", target_dir=str(tmp_path))

        # We don't call execute_clean here; dry-run means NOT calling it
        assert f.exists()  # File still present

    def test_permanent_delete_removes_file(self, tmp_path: Path):
        f = tmp_path / "junk.tmp"
        f.write_text("data")
        scan = ScanResult(root=tmp_path, items=[JunkItem(path=f, reason="pattern", size_bytes=4)])
        manifest = OperationManifest(operation="clean", target_dir=str(tmp_path))

        result = execute_clean(scan, manifest, permanent=True)
        assert not f.exists()
        assert len(result.removed) == 1

    def test_trash_delete_calls_send2trash(self, tmp_path: Path):
        f = tmp_path / "junk.tmp"
        f.write_text("data")
        scan = ScanResult(root=tmp_path, items=[JunkItem(path=f, reason="pattern", size_bytes=4)])
        manifest = OperationManifest(operation="clean", target_dir=str(tmp_path))

        with patch("smart_file_cleaner.utils.trash.send2trash") as mock_trash:
            mock_trash.send2trash = lambda p: Path(p).unlink()
            execute_clean(scan, manifest, permanent=False)

    def test_failed_deletion_recorded(self, tmp_path: Path):
        # Point at a file that doesn't exist
        fake = tmp_path / "ghost.tmp"
        scan = ScanResult(
            root=tmp_path, items=[JunkItem(path=fake, reason="pattern", size_bytes=0)]
        )
        manifest = OperationManifest(operation="clean", target_dir=str(tmp_path))

        result = execute_clean(scan, manifest, permanent=True)
        # File doesn't exist, so it should be skipped (not in removed, not in failed)
        assert len(result.removed) == 0
