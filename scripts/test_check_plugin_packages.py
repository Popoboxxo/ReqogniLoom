"""Tests for the plugin-package release ratchet (#1284 / #1285).

These pin the two properties the release check must have:

* the *real* repository tree passes (all first-party plugin packages present
  and every coupled manifest carries the released ``VERSION``), and
* the ratchet actually fails on the two observed failure modes — a removed
  source file (#1283/#1285 rump tree) and a stray version in the
  hand-maintained Hermes desktop manifest (#1284).

Independently-versioned POC artifacts (ADR-017 decision 2) are presence-only,
so their version is not forced onto ``VERSION``.

Stdlib only; no Django/DB. Runs from the repo root.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = REPO_ROOT / "scripts" / "check_plugin_packages.py"


def _load_ratchet():
    spec = importlib.util.spec_from_file_location("reqlo_check_plugin_packages", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ratchet = _load_ratchet()


def _materialize(root: Path) -> None:
    """Copy every file the ratchet reads from the repo into ``root``."""
    rels = {rel for _, rel in ratchet.REQUIRED_SOURCES}
    rels |= {loc.path for loc in ratchet.VERSION_COUPLED}
    rels |= {rel for _, rel in ratchet.INDEPENDENT_POC}
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, target)


def test_real_repo_is_consistent() -> None:
    expected = ratchet.load_expected_version(REPO_ROOT)
    assert ratchet.collect_problems(REPO_ROOT, expected) == []


def test_missing_source_tree_is_reported(tmp_path: Path) -> None:
    _materialize(tmp_path)
    missing = tmp_path / "integrations/hermes-plugin/reqogniloom/package.json"
    missing.unlink()
    problems = ratchet.collect_problems(tmp_path, ratchet.load_expected_version(REPO_ROOT))
    assert any("package.json" in p and "missing" in p for p in problems), problems


def test_version_drift_in_desktop_manifest_is_reported(tmp_path: Path) -> None:
    _materialize(tmp_path)
    manifest = tmp_path / "integrations/hermes-plugin/reqogniloom/hermes-plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = "1.8.0-beta.19"
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    problems = ratchet.collect_problems(tmp_path, ratchet.load_expected_version(REPO_ROOT))
    assert any("hermes-plugin.json" in p and "1.8.0-beta.19" in p for p in problems), problems


def test_independent_poc_version_is_not_forced_to_version(tmp_path: Path) -> None:
    _materialize(tmp_path)
    # The POC agent plugin legitimately carries its own SemVer (ADR-017).
    plugin_yaml = tmp_path / "integrations/hermes-agent-plugin/plugin.yaml"
    assert "version: 0.2.0" in plugin_yaml.read_text(encoding="utf-8")
    problems = ratchet.collect_problems(tmp_path, ratchet.load_expected_version(REPO_ROOT))
    assert problems == [], problems


def test_tag_derives_expected_version() -> None:
    version = ratchet.load_expected_version(REPO_ROOT)
    assert ratchet.main(["--tag", f"v{version}"]) == 0


def test_tag_and_expect_version_are_mutually_exclusive() -> None:
    version = ratchet.load_expected_version(REPO_ROOT)
    assert ratchet.main(["--tag", f"v{version}", "--expect-version", version]) == 2
