"""DOC-012 / S6.3 — internal navigation docs must follow AGENTS.md's language rule.

AGENTS.md "Sprachregeln": internal documentation is German, external
documentation is English. The external surface is ``site/**`` (published by
``.github/workflows/pages.yml``) and generated ``docs/clients/*.md`` — none of
that is in scope here. These five files are internal navigation/index docs and
must therefore be German.

This is deliberately an EXACT-STRING guard on the H1 and the intro region
(H1 → first ``##``), not a prose/stopword analysis: technical terms (MCP,
REST, PWA), quoted English commit subjects and IDs must stay untouched.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Exact expected H1 for each internal index/meta document.
EXPECTED_H1: dict[str, str] = {
    "docs/plans/index.md": "# Plan-Index",
    "docs/superpowers/plans/index.md": "# Plan-Index",
    "docs/superpowers/specs/index.md": "# Spezifikations-Index",
    "docs/se/strategy/PRODUCT_STRATEGY.md": "# ReqFlow — Produktstrategie & Projektwissen",
}

# Legacy English strings that must no longer appear in the intro region
# (H1 up to the first H2) of the three navigation indexes.
FORBIDDEN_INTRO_STRINGS = (
    "This index lists",
    "proven against the source code",
    "implementation status",
)
INTRO_MARKERS = ("Dieser Index", "Stand")

# REQUIREMENTS.md is a historical requirements register (not a nav index):
# only its leading HTML header comment is checked.
REQUIREMENTS = "docs/REQUIREMENTS.md"
REQUIREMENTS_REQUIRED = "**Hinweis:**"
REQUIREMENTS_FORBIDDEN = (
    "**Note:** This file contains",
    "This index serves as a historical record",
)


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _intro_region(text: str) -> str:
    """Text from the first H1 up to (excluding) the first subsequent H2."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("# ")), 0)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def test_internal_index_h1_is_german() -> None:
    for rel, expected in EXPECTED_H1.items():
        text = _read(rel)
        first_h1 = next((l for l in text.splitlines() if l.startswith("# ")), None)
        assert first_h1 == expected, f"{rel}: H1 is {first_h1!r}, expected {expected!r}"


def test_product_strategy_anglicism_headings_translated() -> None:
    """S63-R1: protect the two translated section headings too."""
    text = _read("docs/se/strategy/PRODUCT_STRATEGY.md")
    assert "## 1. Zusammenfassung & Vision" in text
    assert "### Nicht im Umfang (v1)" in text
    for legacy in ("## 1. Executive Summary & Vision", "### Out-of-Scope (v1)"):
        assert legacy not in text, f"legacy heading still present: {legacy!r}"


def test_navigation_index_intros_are_german() -> None:
    for rel in (
        "docs/plans/index.md",
        "docs/superpowers/plans/index.md",
        "docs/superpowers/specs/index.md",
    ):
        intro = _intro_region(_read(rel))
        assert any(marker in intro for marker in INTRO_MARKERS), (
            f"{rel}: intro has no German marker {INTRO_MARKERS}"
        )
        for forbidden in FORBIDDEN_INTRO_STRINGS:
            assert forbidden not in intro, f"{rel}: legacy English string {forbidden!r} still in intro"


def test_requirements_header_is_german() -> None:
    text = _read(REQUIREMENTS)
    header = text.split("-->", 1)[0]
    assert REQUIREMENTS_REQUIRED in header, f"{REQUIREMENTS}: German header marker missing"
    for forbidden in REQUIREMENTS_FORBIDDEN:
        assert forbidden not in header, f"{REQUIREMENTS}: {forbidden!r} still in header"


def test_rule_scope_documented_in_agents() -> None:
    """Guard only makes sense while AGENTS.md keeps the DE/EN rule."""
    agents = _read("AGENTS.md")
    assert "Interne Doku" in agents and "Externe Doku" in agents, (
        "AGENTS.md language table changed — re-check this guard's scope"
    )
