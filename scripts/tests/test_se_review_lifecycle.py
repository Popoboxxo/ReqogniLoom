"""SE review-lifecycle guard (DOC-010).

Three checks:

1. A review protocol older than 14 days may not be ``status: open`` unless it
   carries a dated response/closure entry — otherwise the mandatory
   ``open -> response -> closed`` lifecycle silently rots.
2. Every status-change table row has an ISO date, a from-state, a to-state and
   a reason (no undocumented autonomous transitions).
3. ADR-025 and ADR-026 stay ``proposed``: their transition to ``accepted`` is a
   *user* decision, never an agent-side side effect of closing a review.

Stdlib-only file reads, mirroring ``scripts/tests/test_doc_index_freshness.py``.
CI wiring: add this file to the explicit pytest file list in
``.github/workflows/ci.yml`` next to ``scripts/tests/test_doc_index_freshness.py``.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = REPO_ROOT / "docs" / "se" / "reviews"
ADR_DIR = REPO_ROOT / "docs" / "se" / "ADR"

STALE_AFTER_DAYS = 14
S62_REVIEWS = (
    "REVIEW_2026-10-31_adr-025.md",
    "REVIEW_2026-11-02_adr-026.md",
    "REVIEW_2026-11-02_f3-workitem.md",
)
GOVERNED_ADRS = (
    "ADR-025_additiver_baseline_rollback.md",
    "ADR-026_document_artefakt.md",
)

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n", re.DOTALL)
_STATUS_SECTION_RE = re.compile(
    r"(?im)^##[ \t]+"
    r"(?:status[- ]?change(?:[ \t]+log)?|response(?:[- ]?iteration)?|"
    r"abschluss|closure|statuswechsel)\b[^\n]*\n"
    r"(.*?)(?=^##[ \t]|\Z)",
    re.DOTALL | re.MULTILINE,
)
_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def _split_frontmatter(path: Path) -> tuple[str, str]:
    """Return ``(frontmatter, body)`` for a markdown file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match is not None, f"missing/invalid YAML frontmatter: {path.name}"
    return match.group(1), text[match.end() :]


def _field(frontmatter: str, name: str) -> str | None:
    """Read a scalar ``name: value`` field from the frontmatter block."""
    match = re.search(rf"(?m)^{re.escape(name)}:[ \t]*(.+?)[ \t]*$", frontmatter)
    return match.group(1).strip() if match else None


def _review_paths() -> list[Path]:
    paths = sorted(REVIEW_DIR.glob("REVIEW_*.md"))
    assert paths, f"no review protocols found in {REVIEW_DIR}"
    return paths


def test_no_stale_open_review_without_response_or_closure() -> None:
    """Old open reviews must have a dated response/closure entry."""
    today = date.today()
    offenders: list[str] = []
    for path in _review_paths():
        frontmatter, body = _split_frontmatter(path)
        if _field(frontmatter, "status") != "open":
            continue
        review_date_raw = _field(frontmatter, "date")
        assert review_date_raw, f"{path.name}: open review without a date"
        age = (today - date.fromisoformat(review_date_raw)).days
        if age <= STALE_AFTER_DAYS:
            continue
        has_entry = any(
            _DATE_RE.search(section) is not None
            for section in _STATUS_SECTION_RE.findall(body)
        )
        if not has_entry:
            offenders.append(f"{path.name} ({review_date_raw}, {age}d old)")
    assert not offenders, (
        "open review protocols older than "
        f"{STALE_AFTER_DAYS} days without response/closure entry: "
        + ", ".join(offenders)
    )


def test_every_status_change_has_date_and_reason() -> None:
    """Status-change log rows need date, from-state, to-state and a reason."""
    for path in _review_paths():
        _, body = _split_frontmatter(path)
        for section in _STATUS_SECTION_RE.findall(body):
            for line in section.splitlines():
                stripped = line.strip()
                if not stripped.startswith("|"):
                    continue
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
                    continue  # table header / separator, not a status change
                assert len(cells) >= 4, (
                    f"{path.name}: status-change row needs >= 4 cells, got {cells!r}"
                )
                assert cells[1] and cells[2], (
                    f"{path.name}: status change without from/to state: {cells!r}"
                )
                assert len(cells[3]) >= 10, (
                    f"{path.name}: status change without a reason: {cells!r}"
                )


def test_s62_reviews_closed_with_proposed_retained_note() -> None:
    """The three S6.2 protocols are closed and document the retained ADR status."""
    for name in S62_REVIEWS:
        frontmatter, body = _split_frontmatter(REVIEW_DIR / name)
        assert _field(frontmatter, "status") == "closed", f"{name} must be closed"
        assert _field(frontmatter, "closed_date") == "2026-11-17", (
            f"{name}: missing 2026-11-17 closure date"
        )
        lowered = body.lower()
        assert "status proposed retained" in lowered, (
            f"{name}: missing 'status proposed retained' note"
        )
        assert "awaiting user decision" in lowered, (
            f"{name}: missing 'awaiting user decision' note"
        )


def test_adr_025_and_026_remain_proposed() -> None:
    """Governance constraint: no autonomous ADR status escalation (DOC-010)."""
    for name in GOVERNED_ADRS:
        frontmatter, _ = _split_frontmatter(ADR_DIR / name)
        assert _field(frontmatter, "status") == "proposed", (
            f"{name} must stay 'proposed' — the transition to 'accepted' is a "
            "user decision and not part of the review-closure slice"
        )
