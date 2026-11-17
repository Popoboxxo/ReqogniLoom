"""Offline guards for the scanner/security baseline slice (S0.1, R1-R6).

Pins the gate-confirmed changes so a later edit cannot silently weaken them
again:

* OPS-003 / SEC-006 -- at least one BLOCKING gitleaks scan must run with the
  default rule set (no ``--enable-rule``). Restricting every blocking scan to
  ``--enable-rule`` disables all built-in detectors (AWS/GitHub/PEM/...), which
  is exactly how a committed cloud key used to pass CI green.
* R1 -- the three dedicated custom-rule scans must use the no-allowlist
  ``.gitleaks-dedicated.toml``. A ``reqlo_<40 alnum>`` token in a path that the
  default config allowlists must STILL be reported there.
* R2 -- the TEMP SEC-001 commit allowlist carries owner / issue link / hard
  removal date, is narrowed to ``.env`` and expires in CI.
* R3 -- a REDACTED full-history evidence report exists under docs/audit/.
* R4 -- pre-commit runs both the dedicated and the default rule set.
* R5 -- the default-rule canary pins the exact required rule-id set.
* R6 -- the HONCHO_DB_PASSWORD example is not a public ``CHANGE-ME*`` value.
* SEC-007 -- ``deploy/docker-compose.yml`` must not fall back to the shared
  ``honcho-dev-password``; the variable is required (``${VAR:?...}``).

Mirrors ``scripts/test_gitignore_env.py``: stdlib only (pytest is used only to
skip the optional functional gitleaks test), reads the repo as text, and is
wired explicitly into ``agent-templates-test`` in .github/workflows/ci.yml.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GITLEAKS = REPO_ROOT / ".gitleaks.toml"
DEDICATED = REPO_ROOT / ".gitleaks-dedicated.toml"
PRECOMMIT = REPO_ROOT / ".pre-commit-config.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
EVIDENCE = REPO_ROOT / "docs" / "audit" / "2026-11-17-s01-gitleaks-evidence.md"


def _secret_scan_job() -> str:
    """Return the text of the ``secret-scan`` job block from ci.yml."""
    lines = CI.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"^  secret-scan:\s*$", line)),
        None,
    )
    assert start is not None, "secret-scan job not found in ci.yml"
    end = next(
        (
            j
            for j in range(start + 1, len(lines))
            if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[j])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _steps(job: str) -> list[tuple[str, str]]:
    """Return (name, body) for every ``- name:`` step in a job block."""
    steps: list[tuple[str, str]] = []
    name: str | None = None
    body: list[str] = []
    for line in job.splitlines():
        match = re.match(r'^      - name:\s*"?(.*?)"?(?:\s*#.*)?$', line)
        if match:
            if name is not None:
                steps.append((name, "\n".join(body)))
            name, body = match.group(1), [line]
        elif name is not None:
            body.append(line)
    if name is not None:
        steps.append((name, "\n".join(body)))
    return steps


def _blocking_scan_steps() -> list[tuple[str, str]]:
    """Return only the blocking ``Scan ...`` steps (the canary is not one)."""
    return [(n, b) for n, b in _steps(_secret_scan_job()) if re.match(r"^Scan\b", n)]


def _gitleaks_commands(body: str) -> list[str]:
    """Actual ``gitleaks dir/git`` command lines (ignore comments/echo text).

    Shell line continuations are joined so a flag such as ``--enable-rule`` on
    a following line is still attributed to the command it belongs to.
    """
    joined = re.sub(r"\\\s*\n\s*", " ", body)
    commands: list[str] = []
    for line in joined.splitlines():
        # Single-line steps write `run: gitleaks ...`; block steps write the
        # command on the following line. Normalise both to the command itself.
        normalized = re.sub(r"^\s*run:\s*", "", line)
        if re.match(r"^\s*gitleaks\s+(dir|git)\b", normalized):
            commands.append(normalized)
    return commands


def _default_rule_scans() -> list[tuple[str, str]]:
    """Blocking gitleaks scans that do NOT restrict execution to custom rules."""
    result: list[tuple[str, str]] = []
    for name, body in _blocking_scan_steps():
        commands = _gitleaks_commands(body)
        if commands and not any("--enable-rule" in c for c in commands):
            result.append((name, body))
    return result


def _canary_required_rules() -> set[str]:
    """Extract the exact ``required = {...}`` rule-id set from the canary."""
    job = _secret_scan_job()
    match = re.search(r"^\s*required\s*=\s*\{([^}]*)\}", job, re.M)
    assert match, "default-rule canary must pin an explicit required = {...} set"
    return {
        token.strip().strip("'\"")
        for token in match.group(1).split(",")
        if token.strip()
    }


def _allowlist_blocks(text: str) -> list[str]:
    return re.findall(
        r"\[\[allowlists\]\]\s*\n(.*?)(?=\n\[\[allowlists\]\]|\Z)", text, re.S
    )


# ---------------------------------------------------------------------------
# OPS-003 / SEC-006 — baseline gates (pre-existing)
# ---------------------------------------------------------------------------
def test_a_blocking_scan_uses_the_default_rule_set() -> None:
    """OPS-003/SEC-006: not every blocking scan may be --enable-rule-only."""
    scans = _blocking_scan_steps()
    assert scans, "no blocking gitleaks scan steps found"
    assert _default_rule_scans(), (
        "every blocking gitleaks scan uses --enable-rule; built-in detectors "
        "(AWS/GitHub/PEM) are disabled -- OPS-003/SEC-006 regression"
    )


def test_existing_custom_rule_scans_are_retained() -> None:
    """The fix must ADD a default scan, not remove/loosen the custom gates."""
    bodies = "\n".join(b for _, b in _blocking_scan_steps())
    assert "REQLO_API_KEY_RULE" in bodies, "reqlo-api-key scan was removed"
    assert "ENV_SECRET_RULE" in bodies, "env-secret-assignment scan was removed"


def test_b_default_rule_step_scans_full_history_and_working_tree() -> None:
    default = _default_rule_scans()
    assert len(default) == 1, (
        f"expected exactly one default-rule scan step, got {[n for n, _ in default]}"
    )
    name, body = default[0]
    assert re.search(r"gitleaks\s+git\s+\.", body), (
        f"'{name}' must scan full git history (gitleaks git .)"
    )
    assert re.search(r"gitleaks\s+dir\s+\.", body), (
        f"'{name}' must scan the working tree (gitleaks dir .)"
    )
    assert "--config .gitleaks.toml" in body, "default scan must use .gitleaks.toml"
    assert "--exit-code 1" in body, "default scan must be blocking"


def test_gitleaks_allowlists_carry_explicit_reasons() -> None:
    entries = _allowlist_blocks(GITLEAKS.read_text(encoding="utf-8"))
    assert entries, "no [[allowlists]] entries found in .gitleaks.toml"
    for entry in entries:
        assert re.search(r"^\s*description\s*=", entry, re.M), (
            "every allowlist entry needs an explicit reason (no blanket-allow)"
        )


def test_c_compose_has_no_honcho_dev_password_fallback() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "honcho-dev-password" not in text, (
        "SEC-007 regression: shared honcho-dev-password fallback reappeared"
    )
    required = "${HONCHO_DB_PASSWORD:?set HONCHO_DB_PASSWORD}"
    assert text.count(required) >= 3, (
        "expected all HONCHO_DB_PASSWORD sites to use the required (?:) form"
    )


# ---------------------------------------------------------------------------
# R5 — canary pins the actual rule-id set, not mere string presence
# ---------------------------------------------------------------------------
def test_canary_proves_builtin_detectors_are_live() -> None:
    job = _secret_scan_job()
    assert _canary_required_rules() == {
        "reqlo-api-key",
        "env-secret-assignment",
        "github-pat",
        "private-key",
    }, (
        "default-rule canary's required rule-id set drifted -- a built-in or "
        "custom detector may no longer be asserted live"
    )
    assert "BEGIN RSA PRIVATE KEY" in job, "canary must emit a PEM private-key header"
    assert "missing = required - reported" in job, (
        "canary must assert on the required set, not just echo rule names"
    )


# ---------------------------------------------------------------------------
# R1 — config split: dedicated gates must stay strict in allowlisted paths
# ---------------------------------------------------------------------------
def test_r1_dedicated_config_is_strict_and_default_config_is_allowlisted() -> None:
    dedicated = DEDICATED.read_text(encoding="utf-8")
    assert re.search(r"^\s*useDefault\s*=\s*false\s*$", dedicated, re.M), (
        "dedicated config must not inherit gitleaks' default ruleset"
    )
    assert not re.search(r"^\[\[allowlists\]\]", dedicated, re.M), (
        "R1 regression: global allowlists reappeared in the dedicated config"
    )
    assert re.search(r'id\s*=\s*"reqlo-api-key"', dedicated)
    assert re.search(r'id\s*=\s*"env-secret-assignment"', dedicated)
    assert "reqlo_[A-Za-z0-9]{40}" in dedicated, "incident regex drifted"

    shared = GITLEAKS.read_text(encoding="utf-8")
    assert re.search(r"^\s*useDefault\s*=\s*true\s*$", shared, re.M)
    assert "[[allowlists]]" in shared, "default config must keep its reviewed allowlists"


def test_r1_dedicated_scans_use_the_dedicated_config() -> None:
    scans = _blocking_scan_steps()
    default_names = {name for name, _ in _default_rule_scans()}
    dedicated_scans = [(n, b) for n, b in scans if n not in default_names]
    assert len(dedicated_scans) == 3, (
        f"expected three dedicated scans, got {[n for n, _ in dedicated_scans]}"
    )
    for name, body in dedicated_scans:
        commands = _gitleaks_commands(body)
        assert commands, f"'{name}' has no gitleaks command"
        for command in commands:
            assert "--enable-rule" in command, (
                f"'{name}' is a dedicated gate but lost its --enable-rule scope"
            )
            assert "--config .gitleaks-dedicated.toml" in command, (
                f"'{name}' must use .gitleaks-dedicated.toml (R1): {command}"
            )
    job = _secret_scan_job()
    assert job.count("--config .gitleaks-dedicated.toml") >= 5, (
        "canary + regression + three scans must all reference the dedicated config"
    )


def test_r1_reqlo_in_allowlisted_path_is_reported_by_dedicated_config(
    tmp_path: Path,
) -> None:
    """Functional negative test for R1 (skipped when gitleaks is unavailable).

    A live-shaped ``reqlo_<40 alnum>`` token in ``docs/`` (which the default
    config globally allowlists via ``\\.md$``) MUST be reported by the
    dedicated config; the default config MUST suppress it. Set GITLEAKS_BIN to
    run this locally with the pinned 8.30.1 binary.
    """
    binary = os.environ.get("GITLEAKS_BIN") or shutil.which("gitleaks")
    if not binary or not Path(binary).is_file():
        pytest.skip("gitleaks binary unavailable (CI installs it in secret-scan)")

    scan = tmp_path / "scan"
    (scan / "docs").mkdir(parents=True)
    token = "reqlo_" + ("Zx9Qm2Lp7Rt4Wv8N" * 3)[:40]
    (scan / "docs" / "canary.md").write_text(
        f"documentation example: {token}\n", encoding="utf-8"
    )

    def run(config: Path) -> list[dict]:
        report = tmp_path / f"{config.stem}-report.json"
        subprocess.run(
            [
                binary,
                "dir",
                str(scan),
                "--config",
                str(config),
                "--enable-rule",
                "reqlo-api-key",
                "--no-banner",
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return json.loads(report.read_text(encoding="utf-8") or "[]")

    dedicated_findings = run(DEDICATED)
    assert any(f.get("RuleID") == "reqlo-api-key" for f in dedicated_findings), (
        "R1 regression: dedicated config did not report a reqlo token in an "
        "allowlisted path"
    )
    allowlisted_findings = run(GITLEAKS)
    assert not any(f.get("RuleID") == "reqlo-api-key" for f in allowlisted_findings), (
        "the default config no longer demonstrates the allowlist hollowing that "
        "motivated the config split"
    )


# ---------------------------------------------------------------------------
# R2 — TEMP SEC-001 allowlist metadata, narrowing and CI expiry
# ---------------------------------------------------------------------------
def test_r2_temp_allowlist_has_owner_issue_and_hard_expiry() -> None:
    entries = _allowlist_blocks(GITLEAKS.read_text(encoding="utf-8"))
    temp = [entry for entry in entries if "TEMP SEC-001" in entry]
    assert len(temp) == 1, "expected exactly one TEMP SEC-001 allowlist"
    entry = temp[0]
    assert "owner: devops-engineer" in entry, "temporary allowlist needs a named owner"
    assert "remove-by: 2026-12-01" in entry, "temporary allowlist needs a hard removal date"
    assert "docs/audit/gates/2026-11-16/mvp-gates.md" in entry, (
        "temporary allowlist needs an issue/evidence link"
    )
    assert "paths = ['''^\\.env$''']" in entry, (
        "temporary allowlist must be narrowed to the repo-root .env file"
    )
    assert 'targetRules = ["env-secret-assignment", "generic-api-key"]' in entry, (
        "gitleaks ORs allowlist conditions: targetRules is required to genuinely "
        "narrow the commit suppression to the two rules that fire on those lines"
    )
    for sha in (
        "798650dfad0c11c40285596d2b591d3faee75686",
        "a8cee99e1545e5a4df3b727f6a760a5417ed1daa",
        "bad447fdb9ca366bb6cbec5c78730acfc0e79553",
    ):
        assert sha in entry, f"reconciled SEC-001 commit {sha} missing"
    assert "cedb62f8 / 08550995" in GITLEAKS.read_text(encoding="utf-8"), (
        "audit-doc commits must be documented as covered by the path allowlist"
    )


def test_r2_ci_expires_the_temp_allowlist() -> None:
    job = _secret_scan_job()
    assert "REMOVAL_DATE: '2026-12-01'" in job, "CI must pin the expiry date"
    guard_steps = [
        (name, body)
        for name, body in _steps(job)
        if "expiry guard" in name.lower()
    ]
    assert len(guard_steps) == 1, "SEC-001 expiry guard step missing"
    _, body = guard_steps[0]
    assert "date -u +%F" in body, "expiry guard must compare the current UTC date"
    assert "grep -Fq" in body, "expiry guard must detect the allowlist marker"
    assert "exit 1" in body, "expiry guard must fail closed after the deadline"


# ---------------------------------------------------------------------------
# R3 — redacted evidence
# ---------------------------------------------------------------------------
def test_r3_redacted_full_history_evidence_exists() -> None:
    assert EVIDENCE.is_file(), "missing redacted gitleaks evidence report"
    body = EVIDENCE.read_text(encoding="utf-8")
    assert "gitleaks 8.30.1" in body, "evidence must pin the scanner version"
    assert not re.search(r"reqlo_[A-Za-z0-9]{40}\b", body), (
        "secret-shaped reqlo token leaked into the redacted evidence report"
    )
    assert not re.search(r"SECRET_KEY=[0-9a-fA-F]{12,}", body), (
        "secret value leaked into the redacted evidence report"
    )


# ---------------------------------------------------------------------------
# R4 — pre-commit runs both rule families
# ---------------------------------------------------------------------------
def test_r4_precommit_runs_dedicated_and_default_rules() -> None:
    text = PRECOMMIT.read_text(encoding="utf-8")
    assert re.search(r"^\s*- id: gitleaks\s*$", text, re.M), "dedicated hook missing"
    assert re.search(r"^\s*- id: gitleaks-default\s*$", text, re.M), (
        "R4 regression: second (default-rule) pre-commit hook missing"
    )
    assert "gitleaks git --staged --redact --config .gitleaks-dedicated.toml" in text
    assert "gitleaks git --staged --redact --config .gitleaks.toml" in text


# ---------------------------------------------------------------------------
# R6 — HONCHO_DB_PASSWORD example must not be a public placeholder
# ---------------------------------------------------------------------------
def test_r6_honcho_db_password_is_not_a_public_placeholder() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    match = re.search(r"^HONCHO_DB_PASSWORD=(.*)$", text, re.M)
    assert match, "HONCHO_DB_PASSWORD missing from .env.example"
    value = match.group(1).strip()
    assert not value.upper().startswith("CHANGE-ME"), (
        "R6 regression: a copied example could run with a public CHANGE-ME credential"
    )
    assert re.fullmatch(r"local-dev-only-honcho-[0-9a-f]{12}", value), (
        "expected the pinned non-placeholder local-dev value shape"
    )
