"""Tests for the configuration system (utils/config.py)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_file_cleaner.utils.config import (
    AppConfig,
    _env_bool,
    _load_toml,
    init_config_file,
    load_config,
)
from smart_file_cleaner.utils.errors import ConfigError


class TestEnvBool:
    def test_true_values(self):
        for val in ("1", "true", "yes", "on", "TRUE", "YES"):
            with patch.dict(os.environ, {"TEST_VAR": val}):
                assert _env_bool("TEST_VAR", False) is True

    def test_false_values(self):
        for val in ("0", "false", "no", "off"):
            with patch.dict(os.environ, {"TEST_VAR": val}):
                assert _env_bool("TEST_VAR", True) is False

    def test_missing_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _env_bool("NONEXISTENT_VAR", True) is True
            assert _env_bool("NONEXISTENT_VAR", False) is False


class TestLoadToml:
    def test_returns_empty_for_nonexistent(self, tmp_path: Path):
        result = _load_toml(tmp_path / "nonexistent.toml")
        assert result == {}

    def test_parses_valid_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("[defaults]\ndry_run = false\n")
        result = _load_toml(toml_file)
        assert result.get("defaults", {}).get("dry_run") is False

    def test_raises_config_error_for_invalid_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("THIS IS NOT TOML {{{{")
        with pytest.raises(ConfigError):
            _load_toml(toml_file)


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path: Path):
        cfg = load_config(config_file=tmp_path / "nonexistent.toml")
        assert isinstance(cfg, AppConfig)
        assert cfg.dry_run is True  # Default
        assert cfg.output == "text"

    def test_loads_from_toml_file(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[defaults]\ndry_run = false\noutput = "json"\n')
        cfg = load_config(config_file=toml_file)
        assert cfg.dry_run is False
        assert cfg.output == "json"

    def test_env_var_overrides_file(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("[defaults]\ndry_run = false\n")
        with patch.dict(os.environ, {"SFC_DRY_RUN": "1"}):
            cfg = load_config(config_file=toml_file)
        assert cfg.dry_run is True  # Env var wins

    def test_no_color_env_respected(self, tmp_path: Path):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            cfg = load_config(config_file=tmp_path / "nonexistent.toml")
        assert cfg.no_color is True

    def test_clean_config_loaded_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text('[clean]\njunk_patterns = ["*.bak"]\n')
        cfg = load_config(config_file=toml_file)
        assert cfg.clean.junk_patterns == ["*.bak"]

    def test_review_config_loaded_from_toml(self, tmp_path: Path):
        toml_file = tmp_path / "config.toml"
        toml_file.write_text("[review]\nstale_days = 90\nlarge_mb = 500.0\n")
        cfg = load_config(config_file=toml_file)
        assert cfg.review.stale_days == 90
        assert cfg.review.large_mb == 500.0


class TestInitConfigFile:
    def test_creates_config_file(self, tmp_path: Path):
        with patch(
            "smart_file_cleaner.utils.config.get_config_file", return_value=tmp_path / "config.toml"
        ):
            path = init_config_file()

        assert path.exists()
        content = path.read_text()
        assert "[defaults]" in content
        assert "[clean]" in content

    def test_does_not_overwrite_existing(self, tmp_path: Path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("custom content")

        with patch("smart_file_cleaner.utils.config.get_config_file", return_value=config_file):
            init_config_file()

        assert config_file.read_text() == "custom content"
