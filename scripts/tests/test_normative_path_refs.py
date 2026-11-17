"""DOC-011 guard: normative path references must resolve to real targets.

Extracts path-like references (``docs/…``, ``.claude/…``, ``schemas/…``) and
``AGENTS.md#…`` anchors from AGENTS.md and docs/REQUIREMENTS.md and asserts that
every referenced file/directory exists and every anchor is present in AGENTS.md.

The five DOC-011 paths that used to be broken are asserted explicitly as well,
so the guard still covers them if the surrounding prose is reworded later.
Repointing beats creating stubs: no placeholder files are allowed here.

Stdlib-only file reads, mirroring ``scripts/tests/test_doc_index_freshness.py``.
CI wiring: add this file to the explicit pytest file list in
``.github/workflows/ci.yml`` next to ``scripts/tests/test_doc_index_freshness.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS = REPO_ROOT / "AGENTS.md"
REQUIREMENTS = REPO_ROOT / "docs" / "REQUIREMENTS.md"
SOURCES = (AGENTS, REQUIREMENTS)

# Previously missing: three AGENTS.md targets (now in-document anchors), the two
# SE schemas created in this slice, and the archived audit path in REQUIREMENTS.md.
PREVIOUSLY_MISSING = (
    "AGENTS.md#bekannte-grenzen",
    "AGENTS.md#guard-terminologie-convention-boundary-vs-security-boundary",
    "AGENTS.md#repo-containment-gefängnis-modus",
    "schemas/se-adr.schema.json",
    "schemas/se-review.schema.json",
    "docs/archive/audits/SYSTEMAUDIT_2026-08-27.md",
)
REMOVED_DEAD_REFS = (
    "docs/concepts/branch-guard-known-limits.md",
    ".claude/rules/branch-guard.md",
    "docs/concepts/repo-containment-prison-mode.md",
)
# Legacy reference in REQUIREMENTS.md:195 — outside the DOC-011 write set and
# tracked separately; documented here so the generic scan stays meaningful.
KNOWN_OUT_OF_SCOPE = frozenset({"docs/UMSETZUNGSPLAN_2026-07.md"})

_PATH_RE = re.compile(r"(?<![\w/])((?:docs|\.claude|schemas)/[A-Za-z0-9_./-]+)")
_ANCHOR_RE = re.compile(r"AGENTS\.md#([\w-]+)")
_HEADING_RE = re.compile(r"^#+[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _source_texts() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in SOURCES}


def _github_anchor(heading: str) -> str:
    """GitHub-style slug: lowercase, punctuation stripped, spaces -> hyphens."""
    slug = re.sub(r"^#+[ \t]*", "", heading.strip())
    slug = re.sub(r"`([^`]*)`", r"\1", slug)
    slug = slug.lower()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    return slug.replace(" ", "-")


def _agents_anchors(agents_text: str) -> set[str]:
    return {_github_anchor(line) for line in _HEADING_RE.findall(agents_text)}


def _normalise_path(token: str) -> str:
    return token.rstrip("/.")


def _is_placeholder(token: str) -> bool:
    return bool(re.search(r"<[^>]+>|NNN|\*|\.\.\.|YYYY|\{|\}", token))


def test_all_referenced_paths_exist() -> None:
    """Every `docs/…`, `.claude/…` and `schemas/…` ref resolves on disk."""
    for source, text in _source_texts().items():
        missing = []
        for match in _PATH_RE.finditer(text):
            path = _normalise_path(match.group(1))
            if not path or _is_placeholder(path) or path in KNOWN_OUT_OF_SCOPE:
                continue
            if not (REPO_ROOT / path).exists():
                missing.append(path)
        assert not missing, f"{source.name}: broken path references: {sorted(set(missing))}"


def test_all_agents_anchors_exist() -> None:
    """Every `AGENTS.md#…` reference points at a real heading slug."""
    texts = _source_texts()
    available = _agents_anchors(texts[AGENTS])
    for source, text in texts.items():
        missing = sorted(set(_ANCHOR_RE.findall(text)) - available)
        assert not missing, (
            f"{source.name}: missing AGENTS.md anchors: {', '.join(missing)}"
        )


def test_previously_missing_paths_are_covered() -> None:
    """DOC-011's broken targets stay fixed, including the part-B schemas."""
    texts = _source_texts()
    all_text = "\n".join(texts.values())
    available_anchors = _agents_anchors(texts[AGENTS])

    for ref in PREVIOUSLY_MISSING:
        assert ref in all_text, f"DOC-011 target no longer referenced: {ref}"
        if ref.startswith("AGENTS.md#"):
            assert ref.split("#", 1)[1] in available_anchors, (
                f"DOC-011 anchor missing in AGENTS.md: {ref}"
            )
        else:
            assert (REPO_ROOT / ref).exists(), f"DOC-011 target missing on disk: {ref}"


def test_dead_references_are_gone() -> None:
    """The four original dead links must not reappear in either normative file."""
    all_text = "\n".join(_source_texts().values())
    for dead in REMOVED_DEAD_REFS:
        assert dead not in all_text, f"dead reference reintroduced: {dead}"
    assert not re.search(r"(?<![/\w])docs/SYSTEMAUDIT_2026-08-27\.md", all_text), (
        "unarchived SYSTEMAUDIT path reintroduced"
    )
