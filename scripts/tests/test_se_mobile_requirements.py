"""S6.1 guard: the seven mobile/PWA requirements live in the SE cascade.

DOC-003 (Option a) migrated REQ-209..REQ-215 out of the historical
``docs/REQUIREMENTS.md`` into standalone SE requirement files in the
ReactFrontendSystem cell. DOC-005 forbids an evidence-free ``Done``: REQ-209
and REQ-213 must stay ``Teilweise`` until a rendered 390px measurement and an
Android install proof exist. This test pins both the migration and the honest
status, and checks that the generated matrix actually carries all seven IDs.

Stdlib only; reads the repository as data (mirrors the other scripts guards).
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
CELL = REPO_ROOT / "docs/se/L1/Gesamtsystem/L2/ReactFrontendSystem"
MATRIX = REPO_ROOT / "docs/se/traceability-matrix.md"
REQUIREMENTS = REPO_ROOT / "docs/REQUIREMENTS.md"
GENERATOR = REPO_ROOT / "scripts/generate_traceability_matrix.py"

# legacy REQ-209..215 -> authoritative SE ID, filename, status, short title.
MOBILE_REQS = (
    (209, "REQ-L2-RF-209", "REQ-L2-RF-209_mobil_ia_detail.md", "Teilweise", "Mobil-IA"),
    (210, "REQ-L2-RF-210", "REQ-L2-RF-210_dvh_safe_areas.md", "Done", "dvh"),
    (211, "REQ-L2-RF-211", "REQ-L2-RF-211_listen_filter_ohne_hover.md", "Teilweise", "Hover"),
    (212, "REQ-L2-RF-212", "REQ-L2-RF-212_schwere_ansichten_mobil.md", "Teilweise", "schwere Ansichten"),
    (213, "REQ-L2-RF-213", "REQ-L2-RF-213_installierbare_pwa.md", "Teilweise", "PWA"),
    (214, "REQ-L2-RF-214", "REQ-L2-RF-214_service_worker_cache.md", "Done", "Service Worker"),
    (215, "REQ-L2-RF-215", "REQ-L2-RF-215_mobiler_abnahme_nachweis.md", "Teilweise", "Abnahme"),
)
# DOC-005: these two must never claim Done without rendered/device evidence.
NO_EVIDENCE = {209, 213}


def _frontmatter(text: str) -> dict[str, str]:
    """Minimal YAML frontmatter reader (flat ``key: value`` fields only)."""
    assert text.startswith("---\n"), "SE requirement must start with YAML frontmatter"
    end = text.index("\n---\n", 4)
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_traceability_matrix", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve __module__ via sys.modules during class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("legacy,se_id,filename,status,title_part", MOBILE_REQS)
def test_se_requirement_file_exists_and_is_taxonomy_clean(
    legacy: int, se_id: str, filename: str, status: str, title_part: str
) -> None:
    path = CELL / filename
    assert path.is_file(), f"missing SE requirement file {path.relative_to(REPO_ROOT)}"
    text = path.read_text(encoding="utf-8")

    # Naming: REQ-L{n}-NNN_<lowercase_snake_case>.md, no version/iteration suffix.
    assert re.fullmatch(
        r"REQ-L2-RF-(?:209|21[0-5])(?:_[a-z0-9]+(?:_[a-z0-9]+)*)?\.md", filename
    ), filename
    assert "_iter-" not in filename and not re.search(r"_v\d+\.md$", filename), filename

    fm = _frontmatter(text)
    for field in ("type", "scope", "status", "date", "author_agent"):
        assert field in fm and fm[field], f"{filename}: missing frontmatter field {field}"
    assert fm["type"] == "REQ", filename
    assert fm["scope"] == se_id, filename
    assert fm["date"] == "2026-11-16", filename
    assert fm["status"] == status, f"{filename}: frontmatter status drift"

    body = text[text.index("\n---\n", 4) + 5 :]
    h1 = re.findall(r"^# +(REQ-L\d[^\n]*)$", body, re.MULTILINE)
    assert len(h1) == 1, f"{filename}: expected exactly one H1, got {len(h1)}"
    assert se_id in h1[0] and f"ex REQ-{legacy}" in h1[0], h1
    assert title_part.lower() in h1[0].lower(), h1
    assert body.count("\n## Beschreibung\n") == 1, filename
    assert body.count("\n## Akzeptanzkriterien\n") >= 1, filename
    # L2-Trennregel: no forbidden H2 sections inline (architecture/review/
    # metric/trace tables). The machine-interface markers (**Implementation
    # State:** etc.) are intentionally outside H2 and checked separately below.
    forbidden = re.findall(r"^## +(?!Beschreibung$|Akzeptanzkriterien$)(.+)$", body, re.MULTILINE)
    assert forbidden == [], f"{filename}: forbidden H2 sections {forbidden}"
    assert "- [ ] " in body, f"{filename}: acceptance criteria must be checkable"

    # Generator markers (the matrix reads these verbatim).
    for marker in ("**Implementation State:**", "**Test Status:**", "**Traceability:**"):
        assert marker in body, f"{filename}: missing generator marker {marker}"
    if legacy in NO_EVIDENCE:
        assert "Teilweise Implementiert" in body, f"{filename}: must not claim full implementation"
        assert "**Test Status:** Teilweise" in body, f"{filename}: must not claim full coverage"

    # Back-links to spec / plan / feature docs.
    for source in (
        "docs/superpowers/specs/2026-11-16-mobile-pwa-design.md",
        "docs/plans/mobile-baseline-2026-11.md",
        "docs/features/mobile-and-pwa.md",
    ):
        assert source in text, f"{filename}: missing back-link {source}"


def test_generator_discovers_all_seven_and_keeps_honest_status() -> None:
    corpus = _load_generator().collect()
    for _legacy, se_id, _filename, status, _title in MOBILE_REQS:
        req = corpus.requirements.get(se_id)
        assert req is not None, f"generator does not discover {se_id}"
        assert req.level == 2 and req.system == "ReactFrontendSystem", se_id
        if status == "Teilweise":
            assert req.impl_bucket == "Teilweise Implementiert", (se_id, req.impl_bucket)
            assert req.test_status is not None and req.test_status.startswith("Teilweise"), se_id
        else:
            assert req.impl_bucket == "Implemented", (se_id, req.impl_bucket)
            assert req.test_bucket == "Covered", (se_id, req.test_bucket)


def test_matrix_contains_all_seven_ids_and_legacy_numbers() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    for legacy, se_id, _filename, status, _title in MOBILE_REQS:
        assert se_id in matrix, f"{se_id} missing from generated matrix"
        assert f"ex REQ-{legacy}" in matrix, f"legacy REQ-{legacy} missing from matrix"
    assert "REQ-L2-RF-209" in matrix and "REQ-L2-RF-213" in matrix
    # Status honesty is visible in the matrix too (no fabricated "Implemented").
    row_209 = next(line for line in matrix.splitlines() if line.startswith("| REQ-L2-RF-209 "))
    row_213 = next(line for line in matrix.splitlines() if line.startswith("| REQ-L2-RF-213 "))
    assert "Teilweise Implementiert" in row_209 and "Teilweise Implementiert" in row_213


def test_requirements_md_is_a_pointer_table_with_no_done_without_evidence() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    for legacy, se_id, filename, status, _title in MOBILE_REQS:
        row = next(
            line for line in text.splitlines() if line.startswith(f"| REQ-{legacy} |")
        )
        assert f"[{se_id}](" in row, row
        assert filename in row, row
        assert f"| {status} |" in row, row
        if legacy in NO_EVIDENCE:
            assert "| Done |" not in row, row
            assert "| Teilweise |" in row, row
    # Full legacy descriptions are gone; the SE files own them now.
    assert "| Beschreibung |" not in text.split("## Mobile Oberfläche", 1)[1]
