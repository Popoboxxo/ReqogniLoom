"""Guard for the documented MPL-2.0 legal exception (DEP-007 / E6).

The audit raised DEP-007 because MPL-2.0 licensed packages appear in the npm
lockfiles. E6 (user decision, 2026-11-17) keeps them with a documented legal
review: they are dev/build-only, unmodified, never vendored and never shipped
in the production image, so the MPL section 3.2 source-offer obligation is not
triggered. This guard re-reads every lockfile as data and fails when a new MPL
component is not covered by docs/legal/THIRD-PARTY-NOTICES.md, when the
decision metadata is missing, or when an MPL component stops being dev-only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
NOTICES = REPO_ROOT / "docs" / "legal" / "THIRD-PARTY-NOTICES.md"
MPL_LICENSE = "MPL-2.0"
DECISION_ID = "E6"
DECISION_DATE = "2026-11-17"
OWNER = "security-auditor"
SKIP_PARTS = {".git", "node_modules", "dist", "build", ".venv", "venv"}


@dataclass(frozen=True)
class MplComponent:
    """One MPL-2.0 licensed package instance found in a lockfile."""

    name: str
    version: str
    lockfile: str  # repo-relative, POSIX separators
    line: int  # 1-based line of the license field in that lockfile
    dev: bool


def _lockfiles() -> list[Path]:
    """Return all committed npm lockfiles, excluding generated directories."""
    return sorted(
        path
        for path in REPO_ROOT.rglob("package-lock.json")
        if not (SKIP_PARTS & set(path.parts))
    )


def _license_line(lines: list[str], key: str) -> int | None:
    """Find the 1-based line of the MPL license field within one package block."""
    needle = f'"{key}": {{'
    for start, line in enumerate(lines):
        if needle not in line:
            continue
        for look in range(start + 1, min(start + 40, len(lines))):
            if f'"license": "{MPL_LICENSE}"' in lines[look]:
                return look + 1
        return None
    return None


def _mpl_components() -> list[MplComponent]:
    """Extract every pure MPL-2.0 package from every committed lockfile."""
    found: list[MplComponent] = []
    for lock in _lockfiles():
        text = lock.read_text(encoding="utf-8")
        document = json.loads(text)
        lines = text.splitlines()
        relative = lock.relative_to(REPO_ROOT).as_posix()
        for key, package in document.get("packages", {}).items():
            if not isinstance(package, dict) or package.get("license") != MPL_LICENSE:
                # Dual-licensed entries (e.g. dompurify MPL-2.0 OR Apache-2.0)
                # are intentionally excluded: they are not an MPL finding.
                continue
            found.append(
                MplComponent(
                    name=key.split("node_modules/")[-1],
                    version=str(package.get("version", "")),
                    lockfile=relative,
                    line=_license_line(lines, key) or -1,
                    dev=bool(package.get("dev", False)),
                )
            )
    return found


def test_lockfiles_contain_mpl_components() -> None:
    components = _mpl_components()
    assert components, "no MPL-2.0 packages found - lockfile format may have changed"
    assert len({(c.name, c.version) for c in components}) >= 13


def test_notice_file_exists() -> None:
    assert NOTICES.is_file(), f"missing {NOTICES} (DEP-007 / E6 requires documented legal review)"


def test_notice_covers_every_mpl_component() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    for name, version in sorted({(c.name, c.version) for c in _mpl_components()}):
        assert name in text, f"{name} not documented in THIRD-PARTY-NOTICES.md"
        assert version in text, f"{name} {version} not documented in THIRD-PARTY-NOTICES.md"


def test_inventory_line_references_are_current() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    for component in _mpl_components():
        reference = f"{component.lockfile}:{component.line}"
        assert reference in text, (
            f"stale or missing inventory reference {reference} for {component.name}; "
            "the legal notice must track the exact lockfile line"
        )


def test_notice_has_decision_metadata() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    assert DECISION_ID in text, f"{DECISION_ID} decision reference missing"
    assert DECISION_DATE in text, f"E6 decision date {DECISION_DATE} missing"
    assert OWNER in text, f"named owner {OWNER} missing"
    assert re.search(r"2026-\d{2}-\d{2}", text), "notice review date missing"


def test_every_mpl_component_is_dev_only() -> None:
    for component in _mpl_components():
        assert component.dev, (
            f"{component.name} is no longer dev-only - re-run the E6 legal review "
            "before it can enter a distributed artifact"
        )


def test_notice_records_the_three_explicit_conditions() -> None:
    text = NOTICES.read_text(encoding="utf-8").lower()
    for keyword in ("vendored", "modified", "distributed"):
        assert keyword in text, f"explicit '(no MPL file) {keyword}' statement missing"


def test_notice_has_mpl_section_3_2_reasoning() -> None:
    text = NOTICES.read_text(encoding="utf-8")
    assert "3.2" in text, "MPL section 3.2 reasoning missing"
    assert "source" in text.lower(), "source-offer conclusion missing"


def test_notice_has_owner_and_review_trigger() -> None:
    text = NOTICES.read_text(encoding="utf-8").lower()
    assert OWNER in text, f"owner {OWNER} missing"
    assert "review trigger" in text, "review trigger missing"


def test_notice_acknowledges_dompurify_dual_license() -> None:
    text = NOTICES.read_text(encoding="utf-8").lower()
    assert "dompurify" in text, "dual-licensed dompurify must be explained (not a finding)"
    assert "apache-2.0" in text, "dual-license alternative not stated"
