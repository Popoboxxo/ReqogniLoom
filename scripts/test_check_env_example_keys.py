"""Unit tests for ``scripts/check_env_example_keys.py`` (#1737, C1-T3)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).with_name("check_env_example_keys.py")
_spec = importlib.util.spec_from_file_location("check_env_example_keys", _SCRIPT)
assert _spec and _spec.loader
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


def _fixture(tmp_path: Path, *, compose: str, settings: str = "", env: str = "") -> Path:
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "docker-compose.yml").write_text(compose, encoding="utf-8")
    (tmp_path / "backend" / "reqogniloom").mkdir(parents=True)
    (tmp_path / "backend" / "reqogniloom" / "settings.py").write_text(
        settings, encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text(env, encoding="utf-8")
    return tmp_path


def test_missing_compose_key_is_reported(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="services:\n  x:\n    environment:\n      A: ${MISSING_KEY:-1}\n",
        env="#A=1\n",
    )
    assert checker.collect_issues(root)["missing"] == ["MISSING_KEY"]


def test_missing_settings_key_is_reported(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="services: {}\n",
        settings='X = config("SETTINGS_ONLY", default=1)\n',
        env="",
    )
    assert checker.collect_issues(root)["missing"] == ["SETTINGS_ONLY"]


def test_commented_env_entry_counts_as_documented(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="services:\n  x:\n    environment:\n      A: ${DOCUMENTED:-1}\n",
        env="#DOCUMENTED=1\n",
    )
    assert checker.collect_issues(root)["missing"] == []


def test_shell_dollar_escape_is_not_a_compose_key(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose='command: sh -c "echo $${NOT_A_VAR:-x} $$HOSTNAME"\n',
        env="",
    )
    assert checker.collect_issues(root)["missing"] == []


def test_yaml_comment_prose_is_not_a_key(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="# Use ${VAR:-default} syntax here.\nservices: {}\n",
        env="",
    )
    assert checker.collect_issues(root)["missing"] == []


def test_duplicate_active_assignment_is_reported(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="services: {}\n",
        env="A=1\nA=2\n",
    )
    assert checker.collect_issues(root)["duplicates"] == ["A"]


def test_allowlisted_key_is_not_missing(tmp_path: Path) -> None:
    root = _fixture(
        tmp_path,
        compose="services:\n  x:\n    environment:\n      A: ${COMPOSE_PROFILES:-}\n",
        env="",
    )
    assert checker.collect_issues(root)["missing"] == []


def test_main_returns_non_zero_on_issue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _fixture(tmp_path, compose="services: {}\n", env="")
    (root / "deploy" / "docker-compose.yml").write_text(
        "services:\n  x:\n    environment:\n      A: ${NOPE:-1}\n", encoding="utf-8"
    )
    assert checker.main(["--root", str(root)]) == 1
    assert "NOPE" in capsys.readouterr().out
