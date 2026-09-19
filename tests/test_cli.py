"""Integration tests for all CLI commands."""

from pathlib import Path

from typer.testing import CliRunner

from smart_file_cleaner import __version__
from smart_file_cleaner.cli import app

# ---------------------------------------------------------------------------
# Version / Help
# ---------------------------------------------------------------------------


def test_cli_version(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_version_short_flag(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["-v"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_help(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "organize" in result.output
    assert "clean" in result.output
    assert "review" in result.output
    assert "dedupe" in result.output
    assert "analyze" in result.output
    assert "undo" in result.output
    assert "config" in result.output


# ---------------------------------------------------------------------------
# Organize command
# ---------------------------------------------------------------------------


def test_organize_dry_run(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["organize", str(sample_directory), "--dry-run"])
    assert result.exit_code == 0
    assert "Organize" in result.output
    assert "DRY-RUN" in result.output
    assert (sample_directory / "photo.jpg").exists()


def test_organize_execute(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["organize", str(sample_directory), "--execute"])
    assert result.exit_code == 0
    assert "Success" in result.output
    assert (sample_directory / "Images" / "photo.jpg").exists()
    assert (sample_directory / "Documents" / "document.pdf").exists()
    assert (sample_directory / "Code" / "script.py").exists()


def test_organize_no_files(cli_runner: CliRunner, tmp_path: Path):
    result = cli_runner.invoke(app, ["organize", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "No loose files" in result.output


# ---------------------------------------------------------------------------
# Clean command
# ---------------------------------------------------------------------------


def test_clean_dry_run(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["clean", str(sample_directory), "--dry-run"])
    assert result.exit_code == 0
    assert "Clean" in result.output
    assert "DRY-RUN" in result.output
    # temp_cache.tmp should be identified
    assert "temp_cache.tmp" in result.output


def test_clean_dry_run_no_deletion(cli_runner: CliRunner, sample_directory: Path):
    cli_runner.invoke(app, ["clean", str(sample_directory), "--dry-run"])
    # All original files still present
    assert (sample_directory / "temp_cache.tmp").exists()


def test_clean_execute_removes_junk(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(
        app,
        [
            "clean",
            str(sample_directory),
            "--execute",
            "--permanent",
        ],
        input="y\n",
    )  # Confirm permanent delete
    assert result.exit_code == 0
    assert not (sample_directory / "temp_cache.tmp").exists()


def test_clean_empty_dir_detection(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["clean", str(sample_directory), "--dry-run"])
    assert result.exit_code == 0
    # empty_folder should be identified
    assert "empty_folder" in result.output or "Empty Directory" in result.output


def test_clean_json_output(cli_runner: CliRunner, sample_directory: Path):
    import json

    result = cli_runner.invoke(
        app, ["clean", str(sample_directory), "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    # JSON should be parseable
    lines = [l.strip() for l in result.output.strip().splitlines() if l.strip().startswith("{")]
    assert lines  # At least one JSON line
    data = json.loads(lines[-1])
    assert "items_found" in data


def test_clean_system_path_guardrail(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["clean", "/"])
    assert result.exit_code == 1
    assert "Security Guardrail" in result.output or "Error" in result.output


# ---------------------------------------------------------------------------
# Review command
# ---------------------------------------------------------------------------


def test_review_dry_run(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["review", str(sample_directory), "--dry-run"])
    assert result.exit_code == 0
    assert "Triage" in result.output
    assert "Dry-run" in result.output


def test_review_batch_sort_later(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(
        app, ["review", str(sample_directory), "--batch", "--batch-action", "sort_later"]
    )
    assert result.exit_code == 0
    assert "Batch action completed" in result.output


def test_review_batch_auto_sort(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(
        app, ["review", str(sample_directory), "--batch", "--batch-action", "auto_sort"]
    )
    assert result.exit_code == 0
    assert (sample_directory / "Images" / "photo.jpg").exists()


# ---------------------------------------------------------------------------
# Dedupe command
# ---------------------------------------------------------------------------


def test_dedupe_no_duplicates(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["dedupe", str(sample_directory), "--dry-run"])
    assert result.exit_code == 0
    assert "No duplicates" in result.output


def test_dedupe_finds_duplicates(cli_runner: CliRunner, tmp_path: Path):
    content = b"duplicate content here"
    (tmp_path / "original.txt").write_bytes(content)
    (tmp_path / "copy.txt").write_bytes(content)

    result = cli_runner.invoke(app, ["dedupe", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Duplicate Group" in result.output


def test_dedupe_execute_removes_duplicate(cli_runner: CliRunner, tmp_path: Path):
    content = b"same content"
    (tmp_path / "original.txt").write_bytes(content)
    (tmp_path / "copy.txt").write_bytes(content)

    result = cli_runner.invoke(
        app, ["dedupe", str(tmp_path), "--execute", "--keep", "newest", "--permanent"]
    )
    assert result.exit_code == 0
    # One of the two should remain
    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1


def test_dedupe_json_output(cli_runner: CliRunner, tmp_path: Path):
    import json

    content = b"dupe"
    (tmp_path / "a.txt").write_bytes(content)
    (tmp_path / "b.txt").write_bytes(content)

    result = cli_runner.invoke(app, ["dedupe", str(tmp_path), "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    lines = [l.strip() for l in result.output.splitlines() if l.strip().startswith("{")]
    assert lines
    data = json.loads(lines[-1])
    assert "groups_found" in data


# ---------------------------------------------------------------------------
# Analyze command
# ---------------------------------------------------------------------------


def test_analyze_basic(cli_runner: CliRunner, sample_directory: Path):
    result = cli_runner.invoke(app, ["analyze", str(sample_directory)])
    assert result.exit_code == 0
    assert "Storage by Category" in result.output


def test_analyze_json_output(cli_runner: CliRunner, sample_directory: Path):
    import json

    result = cli_runner.invoke(app, ["analyze", str(sample_directory), "--output", "json"])
    assert result.exit_code == 0
    lines = [l.strip() for l in result.output.splitlines() if l.strip().startswith("{")]
    assert lines
    data = json.loads(lines[-1])
    assert "total_files" in data


def test_analyze_top_n(cli_runner: CliRunner, tmp_path: Path):
    for i in range(5):
        (tmp_path / f"file{i}.txt").write_bytes(b"x" * (i + 1) * 100)
    result = cli_runner.invoke(app, ["analyze", str(tmp_path), "--top", "3"])
    assert result.exit_code == 0
    assert "Top 3" in result.output


# ---------------------------------------------------------------------------
# Undo command
# ---------------------------------------------------------------------------


def test_undo_list_empty(cli_runner: CliRunner, tmp_path: Path):
    from unittest.mock import patch

    with patch("smart_file_cleaner.commands.undo.list_manifests", return_value=[]):
        result = cli_runner.invoke(app, ["undo", "--list"])
    assert result.exit_code == 0
    assert "No operation history" in result.output


def test_undo_no_history(cli_runner: CliRunner, tmp_path: Path):
    from unittest.mock import patch

    with patch("smart_file_cleaner.commands.undo.undo_last", return_value=None):
        result = cli_runner.invoke(app, ["undo", "--dry-run"])
    assert result.exit_code == 0
    assert "No operations found" in result.output


# ---------------------------------------------------------------------------
# Security guardrails
# ---------------------------------------------------------------------------


def test_system_path_guardrails_organize(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["organize", "/etc"])
    assert result.exit_code == 1
    assert "Security Guardrail" in result.output


def test_system_path_guardrails_clean(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["clean", "/"])
    assert result.exit_code == 1


def test_system_path_guardrails_review(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["review", "~"])
    assert result.exit_code == 1


def test_invalid_directory(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["organize", "/absolutely_nonexistent_dir_xyz"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Config command
# ---------------------------------------------------------------------------


def test_config_show(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "Active Configuration" in result.output
    assert "defaults.dry_run" in result.output


def test_config_path(cli_runner: CliRunner):
    result = cli_runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert "config.toml" in result.output


def test_config_init(cli_runner: CliRunner, tmp_path: Path):
    from unittest.mock import patch

    with patch(
        "smart_file_cleaner.commands.config_cmd.get_config_file", return_value=tmp_path / "cfg.toml"
    ):
        result = cli_runner.invoke(app, ["config", "init"])
        assert result.exit_code == 0
        assert "Config created" in result.output


def test_organize_and_undo_roundtrip(cli_runner: CliRunner, tmp_path: Path):
    from unittest.mock import patch

    hist_dir = tmp_path / "history"
    test_dir = tmp_path / "work"
    test_dir.mkdir()
    (test_dir / "photo.jpg").write_text("image")

    with patch("smart_file_cleaner.core.history.get_history_dir", return_value=hist_dir):
        # 1. Organize with execute
        res_org = cli_runner.invoke(app, ["organize", str(test_dir), "--execute"])
        assert res_org.exit_code == 0
        assert (test_dir / "Images" / "photo.jpg").exists()
        assert not (test_dir / "photo.jpg").exists()

        # 2. Undo list
        res_list = cli_runner.invoke(app, ["undo", "--list"])
        assert res_list.exit_code == 0
        assert "organize" in res_list.output

        # 3. Undo execute
        res_undo = cli_runner.invoke(app, ["undo", "--execute"])
        assert res_undo.exit_code == 0
        assert "Undo complete" in res_undo.output
        # File restored to original location!
        assert (test_dir / "photo.jpg").exists()
        assert not (test_dir / "Images" / "photo.jpg").exists()


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


def test_main_module_import():
    import smart_file_cleaner.__main__ as main_mod

    assert hasattr(main_mod, "app")
