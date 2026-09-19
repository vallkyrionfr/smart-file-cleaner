"""Unit tests for file sorting core engine in core/sorter.py."""

from pathlib import Path

import pytest

from smart_file_cleaner.core.sorter import (
    execute_organization,
    get_category_for_extension,
    get_unique_destination_path,
    is_hidden_or_system_file,
    plan_organization,
)


def test_get_category_for_extension():
    """Test mapping of file extensions to logical categories."""
    assert get_category_for_extension(".jpg") == "Images"
    assert get_category_for_extension(".PNG") == "Images"
    assert get_category_for_extension(".pdf") == "Documents"
    assert get_category_for_extension(".xlsx") == "Spreadsheets"
    assert get_category_for_extension(".pptx") == "Presentations"
    assert get_category_for_extension(".mp4") == "Videos"
    assert get_category_for_extension(".mp3") == "Audio"
    assert get_category_for_extension(".zip") == "Archives"
    assert get_category_for_extension(".py") == "Code"
    assert get_category_for_extension(".exe") == "Installers"
    assert get_category_for_extension(".xyz_unknown") == "Uncategorized"
    assert get_category_for_extension("") == "Uncategorized"


def test_is_hidden_or_system_file():
    """Test identification of hidden and system files."""
    assert is_hidden_or_system_file(Path(".DS_Store")) is True
    assert is_hidden_or_system_file(Path(".env")) is True
    assert is_hidden_or_system_file(Path("desktop.ini")) is True
    assert is_hidden_or_system_file(Path("Thumbs.db")) is True
    assert is_hidden_or_system_file(Path("report.pdf")) is False
    assert is_hidden_or_system_file(Path("script.py")) is False


def test_get_unique_destination_path(tmp_path: Path):
    """Test collision-free unique path generation."""
    original_file = tmp_path / "document.pdf"

    # Does not exist yet -> returns same path
    assert get_unique_destination_path(original_file) == original_file

    # Create file -> next should append _1
    original_file.write_text("v1")
    dest_1 = get_unique_destination_path(original_file)
    assert dest_1 == tmp_path / "document_1.pdf"

    # Create dest_1 -> next should append _2
    dest_1.write_text("v2")
    dest_2 = get_unique_destination_path(original_file)
    assert dest_2 == tmp_path / "document_2.pdf"


def test_plan_organization(tmp_path: Path):
    """Test planning organization scans files and ignores hidden/system items."""
    (tmp_path / "photo.png").write_text("image content")
    (tmp_path / "document.pdf").write_text("pdf content")
    (tmp_path / "archive.zip").write_text("zip content")
    (tmp_path / ".ds_store").write_text("system content")
    (tmp_path / ".hidden_config").write_text("hidden content")

    # Create category subdirectory to verify it is ignored
    (tmp_path / "Images").mkdir()

    moves = plan_organization(tmp_path)
    sources = [m.source.name for m in moves]

    assert "photo.png" in sources
    assert "document.pdf" in sources
    assert "archive.zip" in sources
    assert ".ds_store" not in sources
    assert ".hidden_config" not in sources

    categories = {m.source.name: m.category for m in moves}
    assert categories["photo.png"] == "Images"
    assert categories["document.pdf"] == "Documents"
    assert categories["archive.zip"] == "Archives"


def test_execute_organization_moves_files(tmp_path: Path):
    """Test executing organization moves files to categorized subdirectories."""
    photo = tmp_path / "vacation.jpg"
    doc = tmp_path / "notes.txt"
    photo.write_text("photo data")
    doc.write_text("notes data")

    moves = plan_organization(tmp_path)
    executed = execute_organization(moves)

    assert len(executed) == 2
    assert not photo.exists()
    assert not doc.exists()

    expected_photo = tmp_path / "Images" / "vacation.jpg"
    expected_doc = tmp_path / "Documents" / "notes.txt"

    assert expected_photo.exists()
    assert expected_doc.exists()
    assert expected_photo.read_text() == "photo data"
    assert expected_doc.read_text() == "notes data"


def test_execute_organization_handles_collisions(tmp_path: Path):
    """Test executing organization handles filename collisions safely without overwriting."""
    images_dir = tmp_path / "Images"
    images_dir.mkdir()
    existing_photo = images_dir / "vacation.jpg"
    existing_photo.write_text("original photo")

    new_photo = tmp_path / "vacation.jpg"
    new_photo.write_text("new photo")

    moves = plan_organization(tmp_path)
    executed = execute_organization(moves)

    assert len(executed) == 1
    assert existing_photo.exists()
    assert existing_photo.read_text() == "original photo"

    collided_photo = images_dir / "vacation_1.jpg"
    assert collided_photo.exists()
    assert collided_photo.read_text() == "new photo"


def test_symlinks_are_skipped(tmp_path: Path):
    """Test symlinks are skipped during directory scanning for security."""
    real_file = tmp_path / "real_doc.pdf"
    real_file.write_text("real content")

    symlink_file = tmp_path / "sym_doc.pdf"
    try:
        symlink_file.symlink_to(real_file)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this environment.")

    assert symlink_file.is_symlink()

    moves = plan_organization(tmp_path)
    sources = [m.source.name for m in moves]

    assert "real_doc.pdf" in sources
    assert "sym_doc.pdf" not in sources
