"""Pytest configuration and fixtures for smart-file-cleaner tests."""

from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture providing Typer CliRunner for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def sample_directory(tmp_path: Path) -> Path:
    """Fixture creating a temporary directory with mock files and subfolders."""
    # Create sample files
    (tmp_path / "document.pdf").write_text("sample pdf content")
    (tmp_path / "photo.jpg").write_text("sample image content")
    (tmp_path / "script.py").write_text("print('hello')")
    (tmp_path / "temp_cache.tmp").write_text("temp data")

    # Create empty subdirectory
    empty_dir = tmp_path / "empty_folder"
    empty_dir.mkdir()

    return tmp_path
