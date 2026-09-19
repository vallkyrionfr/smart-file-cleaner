"""Unit tests for triage and download analysis engine in core/triage.py."""

import os
import time
from pathlib import Path

from smart_file_cleaner.core.triage import (
    analyze_directory_for_triage,
    auto_sort_file,
    move_to_sort_later,
)


def test_analyze_directory_triage_buckets(tmp_path: Path):
    """Test triage directory scanning and grouping into buckets."""
    now = time.time()
    stale_time = now - (40 * 86400)  # 40 days old

    # 1. Installer file
    installer = tmp_path / "setup.exe"
    installer.write_text("installer content")

    # 2. Stale file
    stale_file = tmp_path / "old_notes.txt"
    stale_file.write_text("old notes content")
    os.utime(str(stale_file), (stale_time, stale_time))

    # 3. Large file (we test with lower threshold large_mb=0.001 -> ~1KB)
    large_file = tmp_path / "big_dataset.csv"
    large_file.write_text("a" * 2000)

    # 4. Normal clutter file
    clutter_file = tmp_path / "random.xyz"
    clutter_file.write_text("random")

    # 5. Hidden file
    hidden_file = tmp_path / ".ds_store"
    hidden_file.write_text("hidden")

    analysis = analyze_directory_for_triage(
        tmp_path,
        stale_days=30,
        large_mb=0.001,  # 1 KB threshold for test
        current_timestamp=now,
    )

    filenames_all = [f.filename for f in analysis.all_files]
    assert "setup.exe" in filenames_all
    assert "old_notes.txt" in filenames_all
    assert "big_dataset.csv" in filenames_all
    assert "random.xyz" in filenames_all
    assert ".ds_store" not in filenames_all

    installer_names = [f.filename for f in analysis.installers]
    assert "setup.exe" in installer_names

    stale_names = [f.filename for f in analysis.stale_files]
    assert "old_notes.txt" in stale_names

    large_names = [f.filename for f in analysis.large_files]
    assert "big_dataset.csv" in large_names

    clutter_names = [f.filename for f in analysis.clutter]
    assert "random.xyz" in clutter_names


def test_move_to_sort_later(tmp_path: Path):
    """Test moving file to SortLater subfolder."""
    item = tmp_path / "messy_file.txt"
    item.write_text("messy content")

    dest = move_to_sort_later(item, tmp_path)

    assert not item.exists()
    assert dest.exists()
    assert dest == tmp_path / "SortLater" / "messy_file.txt"
    assert dest.read_text() == "messy content"


def test_auto_sort_file(tmp_path: Path):
    """Test auto-sorting a single file into category folder."""
    item = tmp_path / "vacation_photo.jpg"
    item.write_text("jpeg binary")

    dest = auto_sort_file(item, tmp_path)

    assert not item.exists()
    assert dest.exists()
    assert dest == tmp_path / "Images" / "vacation_photo.jpg"
    assert dest.read_text() == "jpeg binary"
