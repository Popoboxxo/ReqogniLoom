"""Guard for the narrow, expiring npm advisory waiver file (PR #1908 / S4-3).

CI's frontend gate fails on high/critical npm advisories. The ONLY sanctioned
exception is a per-advisory entry in ``.github/npm-audit-waivers.json`` that
carries a reason, an owner and an expiry in the future. This guard keeps that
exception mechanism honest: it fails if the file cannot be parsed, if an entry
is malformed, if an id is not GHSA-shaped, or if any waiver has expired.

Mirrors ``scripts/tests/test_security_scan_config_guard.py``: stdlib only, reads
the repo as data, wired into the repository-tests step of ci.yml by the caller.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
WAIVERS_FILE = REPO_ROOT / ".github" / "npm-audit-waivers.json"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"

GHSA_RE = re.compile(r"GHSA-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}")
REQUIRED_FIELDS = ("reason", "owner", "expires")
EXPECTED_ID = "GHSA-fc5q-39xc-vjpf"


def _load() -> dict:
    assert WAIVERS_FILE.is_file(), f"missing {WAIVERS_FILE}"
    return json.loads(WAIVERS_FILE.read_text(encoding="utf-8"))


def _waivers(doc: dict) -> dict:
    assert isinstance(doc, dict), "waiver file must contain a JSON object"
    assert "waivers" in doc, "waiver file must have a top-level 'waivers' object"
    waivers = doc["waivers"]
    assert isinstance(waivers, dict), "'waivers' must be an object of id -> entry"
    assert waivers, "waiver file must not be empty without updating the gate comment"
    return waivers


def test_waiver_file_parses_and_documents_narrowness() -> None:
    doc = _load()
    assert isinstance(doc.get("_comment"), str) and doc["_comment"].strip(), (
        "top-level '_comment' must explain that waivers are narrow and expiring"
    )
    _waivers(doc)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_every_waiver_has_required_fields(field: str) -> None:
    for wid, waiver in _waivers(_load()).items():
        assert isinstance(waiver, dict), f"{wid}: entry must be an object"
        assert isinstance(waiver.get(field), str) and waiver[field].strip(), (
            f"{wid}: missing or empty '{field}'"
        )


def test_waiver_ids_are_ghsa_shaped() -> None:
    for wid in _waivers(_load()):
        assert GHSA_RE.fullmatch(wid), f"{wid!r} is not a GHSA-xxxx-xxxx-xxxx id"


def test_no_waiver_is_expired() -> None:
    today = dt.date.today()
    for wid, waiver in _waivers(_load()).items():
        expires = dt.date.fromisoformat(waiver["expires"][:10])
        assert expires > today, (
            f"{wid}: waiver expired on {expires} — renew or remove it "
            "(an expired waiver fails CI until acted on)"
        )


def test_picomatch_waiver_matches_the_reviewed_exception() -> None:
    waiver = _waivers(_load())[EXPECTED_ID]
    assert waiver["owner"] == "security-auditor"
    assert waiver["expires"] == "2026-12-15"
    assert "no fixed version" in waiver["reason"]
    assert "dev-only" in waiver["reason"].lower()


def test_ci_gate_is_not_weakened_globally() -> None:
    """The npm step must keep a real gate; the waiver file is the only escape hatch."""
    text = CI.read_text(encoding="utf-8")
    marker = "- name: Frontend - npm audit (fails on high/critical)"
    assert marker in text, "frontend npm audit step not found in ci.yml"
    step = text.split(marker, 1)[1].split("\n      - name:", 1)[0]
    # Only inspect the shell portion; the embedded Python summary string
    # mentions `|| true` as documentation, which is not a shell command.
    shell = step.split("<<'PY'", 1)[0]
    shell = "\n".join(ln for ln in shell.splitlines() if not ln.lstrip().startswith("#"))
    for forbidden in (
        "--audit-level=critical",
        "--audit-level=moderate",
        "--audit-level=low",
        "--audit-level=none",
        "--omit=dev",
        "--omit=optional",
        "--production",
        "|| true",
    ):
        assert forbidden not in shell, f"frontend gate was weakened with {forbidden!r}"
    assert "npm audit" in shell
    assert "npm-audit-waivers.json" in shell
