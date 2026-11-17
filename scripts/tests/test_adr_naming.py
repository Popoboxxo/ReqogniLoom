"""DOC-009 / S6.2 — ADR naming and MADR-minimal heading guard.

ADR filenames must follow ``ADR-NNN_kurztitel.md`` with a lowercase
snake_case kurztitle (AGENTS.md "SE-Kaskade: ADR-Standard", MADR-Minimal).
The three pre-existing CamelCase names (ADR-001/002/003) are frozen legacy —
the standard was introduced after them — and are the only allowed exception.
Every ADR body must carry the four normative sections.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = REPO_ROOT / "docs" / "se" / "ADR"

NAME_RE = re.compile(r"^ADR-(\d{3})_[a-z0-9_]+\.md$")
FROZEN_LEGACY_NAMES = {
    "ADR-001_Sandbox-Mechanismus.md",
    "ADR-002_Event-Bus.md",
    "ADR-003_Glossar-Storage.md",
}
REQUIRED_H2 = {"Kontext", "Alternativen", "Entscheidung", "Konsequenzen"}


def test_adr_filenames_match_convention() -> None:
    files = sorted(ADR_DIR.glob("ADR-*.md"))
    assert files, "no ADRs found — guard is misconfigured"
    offenders = [f.name for f in files if not NAME_RE.fullmatch(f.name)]
    unexpected = set(offenders) - FROZEN_LEGACY_NAMES
    assert not unexpected, f"new non-conforming ADR filenames: {sorted(unexpected)}"


def test_adr_ids_unique_monotonic_and_match_filename() -> None:
    ids: list[int] = []
    for f in sorted(ADR_DIR.glob("ADR-*.md")):
        stem_id = re.match(r"^ADR-(\d{3})_", f.name)
        fm = f.read_text(encoding="utf-8", errors="replace")
        adr_id = re.search(r"^adr_id:\s*ADR-(\d{3})\s*$", fm, re.MULTILINE)
        assert stem_id and adr_id, f"cannot read ADR id from {f.name}"
        assert int(stem_id.group(1)) == int(adr_id.group(1)), (
            f"adr_id does not match filename in {f.name}"
        )
        ids.append(int(stem_id.group(1)))
    assert len(ids) == len(set(ids)), "duplicate ADR ids"
    assert ids == sorted(ids), "ADR ids not monotonic"


def test_no_legacy_ds_prefix_remains() -> None:
    offenders = [f.name for f in ADR_DIR.glob("ADR-DS-*.md")]
    assert offenders == [], f"legacy ADR-DS- prefix remains: {offenders}"


def test_every_adr_has_madr_minimal_sections() -> None:
    for f in sorted(ADR_DIR.glob("ADR-*.md")):
        h2 = set(re.findall(r"^## (.+)$", f.read_text(
            encoding="utf-8", errors="replace"
        ), re.MULTILINE))
        missing = REQUIRED_H2 - h2
        assert not missing, f"{f.name} missing MADR sections: {sorted(missing)}"
