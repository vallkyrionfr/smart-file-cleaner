"""Tests for the disk analyzer (core/analyzer.py)."""

import time
from pathlib import Path

from smart_file_cleaner.core.analyzer import analyze_directory


class TestAnalyzeDirectory:
    def test_empty_directory(self, tmp_path: Path):
        result = analyze_directory(tmp_path)
        assert result.total_files == 0
        assert result.total_bytes == 0
        assert result.category_bytes == {}

    def test_counts_files(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        result = analyze_directory(tmp_path)
        assert result.total_files == 2

    def test_sums_bytes(self, tmp_path: Path):
        (tmp_path / "file.bin").write_bytes(b"x" * 1000)
        result = analyze_directory(tmp_path)
        assert result.total_bytes == 1000

    def test_category_breakdown(self, tmp_path: Path):
        (tmp_path / "photo.jpg").write_bytes(b"j" * 500)
        (tmp_path / "doc.pdf").write_bytes(b"p" * 300)
        result = analyze_directory(tmp_path)
        assert "Images" in result.category_bytes
        assert "Documents" in result.category_bytes
        assert result.category_bytes["Images"] == 500
        assert result.category_bytes["Documents"] == 300

    def test_top_n_largest(self, tmp_path: Path):
        for i, size in enumerate([100, 500, 200, 50, 800]):
            (tmp_path / f"file{i}.bin").write_bytes(b"x" * size)
        result = analyze_directory(tmp_path, top_n=3)
        assert len(result.top_files) == 3
        assert result.top_files[0].size_bytes == 800
        assert result.top_files[1].size_bytes == 500

    def test_stale_files_detection(self, tmp_path: Path):
        old_file = tmp_path / "old.txt"
        old_file.write_text("old")
        import os

        old_time = time.time() - (60 * 86400)  # 60 days ago
        os.utime(old_file, (old_time, old_time))

        fresh_file = tmp_path / "fresh.txt"
        fresh_file.write_text("new")

        result = analyze_directory(tmp_path, stale_days=30)
        stale_paths = [e.path for e in result.stale_files]
        assert old_file in stale_paths
        assert fresh_file not in stale_paths

    def test_recursive_mode(self, tmp_path: Path):
        (tmp_path / "root.txt").write_text("root")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested")

        non_recursive = analyze_directory(tmp_path, recursive=False)
        recursive = analyze_directory(tmp_path, recursive=True)

        assert non_recursive.total_files == 1
        assert recursive.total_files == 2

    def test_skips_protected_dirs(self, tmp_path: Path):
        git = tmp_path / ".git"
        git.mkdir()
        (git / "config").write_text("gitconfig")
        result = analyze_directory(tmp_path, recursive=True)
        assert result.total_files == 0

    def test_largest_category_property(self, tmp_path: Path):
        (tmp_path / "huge_video.mp4").write_bytes(b"v" * 10000)
        (tmp_path / "small_doc.pdf").write_bytes(b"d" * 100)
        result = analyze_directory(tmp_path)
        assert result.largest_category == "Videos"

    def test_progress_callback_called(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        called = []
        analyze_directory(tmp_path, progress_callback=lambda p: called.append(p))
        assert len(called) == 2

    def test_uncategorized_extension(self, tmp_path: Path):
        (tmp_path / "mystery.xyzabc").write_bytes(b"data")
        result = analyze_directory(tmp_path)
        assert "Uncategorized" in result.category_bytes
