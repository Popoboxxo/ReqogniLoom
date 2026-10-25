"""``export_promptfoo_configs``: output shape, guard rails and CI refusal.

Path convention: ``backend/application/tests`` runs in the ``set-1-core`` CI
leg (index §f.4). Every test renders under the nil tenant, so the assertions
are about the exporter, never about tenant data.
"""
from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError

from application.prompt_slots import get_prompt_slots, get_slot_data_variables

pytestmark = pytest.mark.django_db

_SUMMARY_RE = re.compile(
    r"promptfoo export: (\d+)/(\d+) slots, (\d+) missing cases, "
    r"(\d+) unresolved placeholders, memory slots covered (\d+)/(\d+)"
)


def _run(tmp_path: Path, *args: str) -> str:
    stream = StringIO()
    call_command("export_promptfoo_configs", *args, out=str(tmp_path), stdout=stream)
    return stream.getvalue()


def _slot_of(path: Path) -> str:
    # <slot>__<scenario>.promptfooconfig.yaml — one file per scenario (a
    # promptfoo config evaluates prompts × tests, so pairing must be structural).
    return path.name.removesuffix(".promptfooconfig.yaml").rsplit("__", 1)[0]


def test_writes_one_config_per_scenario(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)

    summary = _run(tmp_path)

    files = sorted(tmp_path.glob("*.promptfooconfig.yaml"))
    assert files
    assert {_slot_of(path) for path in files} == set(get_prompt_slots())

    for path in files:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        slot = _slot_of(path)
        assert config["providers"] == ["echo"]
        # Exactly one prompt and one test: promptfoo runs their cross-product.
        assert len(config["prompts"]) == 1
        assert len(config["tests"]) == 1
        prompt = config["prompts"][0]
        assert prompt["id"].startswith(f"{slot}::")
        declared = get_slot_data_variables(slot)
        for variable in declared:
            assert "{" + variable + "}" not in prompt["raw"]
    assert "0 missing cases" in summary
    assert "0 unresolved placeholders" in summary


def test_check_writes_nothing_and_reports_a_complete_set(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)

    summary = _run(tmp_path, "--check")

    assert not list(tmp_path.glob("*.promptfooconfig.yaml"))
    match = _SUMMARY_RE.fullmatch(summary.strip().splitlines()[-1])
    assert match, summary
    assert int(match.group(1)) == len(get_prompt_slots())
    assert int(match.group(2)) == len(get_prompt_slots())


def test_check_fails_on_missing_case(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()

    with pytest.raises(CommandError, match="missing cases"):
        call_command(
            "export_promptfoo_configs",
            "--check",
            cases_dir=str(cases_dir),
            out=str(tmp_path / "out"),
        )


def test_check_fails_on_an_unknown_slot(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(CommandError, match="Unknown prompt slot"):
        call_command(
            "export_promptfoo_configs",
            "--check",
            slot="not-a-real-slot",
            out=str(tmp_path / "out"),
        )


def test_deep_asserts_only_with_deep(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    shallow_dir = tmp_path / "shallow"
    deep_dir = tmp_path / "deep"

    _run(shallow_dir)
    _run(deep_dir, "--deep", "--provider", "echo")

    def _assertion_types(directory: Path) -> set[str]:
        types: set[str] = set()
        for path in directory.glob("need_to_sysreq__*.promptfooconfig.yaml"):
            config = yaml.safe_load(path.read_text(encoding="utf-8"))
            for test in config["tests"]:
                types.update(assertion["type"] for assertion in test["assert"])
        return types

    shallow_types = _assertion_types(shallow_dir)
    deep_types = _assertion_types(deep_dir)

    assert "llm-rubric" not in shallow_types
    assert "llm-rubric" in deep_types


def test_summary_line_format(tmp_path, monkeypatch):
    monkeypatch.delenv("CI", raising=False)

    summary = _run(tmp_path)

    last_line = summary.strip().splitlines()[-1]
    match = _SUMMARY_RE.fullmatch(last_line)
    assert match, last_line
    exported, total = int(match.group(1)), int(match.group(2))
    assert total == len(get_prompt_slots())
    assert exported == total
    assert match.group(3) == "0"
    assert match.group(4) == "0"
    assert match.group(5) == match.group(6)


def test_deep_refused_in_ci(tmp_path, monkeypatch):
    monkeypatch.setenv("CI", "true")

    with pytest.raises(CommandError, match="--deep is refused in CI"):
        call_command(
            "export_promptfoo_configs",
            "--deep",
            provider="echo",
            out=str(tmp_path),
        )
