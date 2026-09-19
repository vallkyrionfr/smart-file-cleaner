"""Unit tests for cross-platform path utilities in path_utils.py."""

import os
from pathlib import Path

import pytest

from smart_file_cleaner.utils.path_utils import (
    UnsafePathError,
    is_subpath,
    normalize_path,
    safe_relative_to,
    validate_safe_target_directory,
)


def test_normalize_path_basic(tmp_path: Path):
    """Test path normalization converts string and Path into absolute Path object."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("data")

    res_str = normalize_path(str(file_path))
    res_obj = normalize_path(file_path)

    assert isinstance(res_str, Path)
    assert res_str.is_absolute()
    assert res_str == res_obj


def test_normalize_path_home_expansion():
    """Test tilde ~ expansion for home directory resolution."""
    res = normalize_path("~")
    assert res.is_absolute()
    assert str(res) == os.path.expanduser("~")


def test_validate_safe_target_directory_valid(tmp_path: Path):
    """Test valid subfolders pass safety validation."""
    valid_subfolder = tmp_path / "Downloads"
    valid_subfolder.mkdir()

    res = validate_safe_target_directory(valid_subfolder)
    assert res == valid_subfolder.resolve()


def test_validate_safe_target_directory_blocks_roots_and_system():
    """Test system path guardrail blocks filesystem root, system paths, and home root."""
    # Test root directory '/'
    with pytest.raises(UnsafePathError) as exc_info_root:
        validate_safe_target_directory("/")
    assert "root" in str(exc_info_root.value).lower()

    # Test system directory '/etc'
    with pytest.raises(UnsafePathError) as exc_info_etc:
        validate_safe_target_directory("/etc")
    assert "system" in str(exc_info_etc.value).lower()

    # Test home directory '~'
    with pytest.raises(UnsafePathError) as exc_info_home:
        validate_safe_target_directory("~")
    assert "home" in str(exc_info_home.value).lower()


def test_is_subpath(tmp_path: Path):
    """Test subpath check correctly identifies contained paths and traversal attempts."""
    parent = tmp_path / "parent"
    parent.mkdir()

    child = parent / "child" / "file.txt"
    out_of_bounds = tmp_path / "other"

    assert is_subpath(child, parent) is True
    assert is_subpath(parent, parent) is True
    assert is_subpath(out_of_bounds, parent) is False
    assert is_subpath(parent / ".." / "other", parent) is False


def test_safe_relative_to(tmp_path: Path):
    """Test safe relative path calculation under base path."""
    base = tmp_path / "base"
    base.mkdir()
    target = base / "sub" / "doc.txt"

    rel = safe_relative_to(target, base)
    assert rel == Path("sub/doc.txt") or rel == Path("sub\\doc.txt")


def test_safe_relative_to_disjoint(tmp_path: Path):
    """Test safe_relative_to falls back to absolute path when target is outside base."""
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    res = safe_relative_to(dir_a, dir_b)
    assert res == dir_a.resolve()


def test_normalize_path_os_error(monkeypatch, tmp_path: Path):
    """Test normalize_path falls back to absolute() when resolve() raises OSError."""
    target = tmp_path / "somefile.txt"

    def mock_resolve(self):
        raise OSError("Permission denied or symlink cycle")

    monkeypatch.setattr(Path, "resolve", mock_resolve)
    res = normalize_path(target)
    assert res == target.absolute()
