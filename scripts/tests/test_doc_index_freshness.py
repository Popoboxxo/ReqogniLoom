"""Index-freshness guard for ``docs/plans`` and ``docs/features`` (DOC-006).

Asserts that every top-level ``*.md`` page in those directories is linked from
the matching ``index.md``. A new page without an index row now breaks CI, so
the indexes can no longer silently drift behind the directories they claim to
list.

Stdlib-only file reads, mirroring ``scripts/tests/test_security_scan_config_guard.py``.
CI wiring (agent-templates-test, .github/workflows/ci.yml): add this file to the
explicit pytest file list next to ``scripts/tests/test_npm_audit_waivers.py``.
"""
from __future__ import annotations

from pathlib import Path

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]

PLANS_DIR = REPO_ROOT / "docs" / "plans"
FEATURES_DIR = REPO_ROOT / "docs" / "features"


def _assert_index_links_every_page(directory: Path) -> None:
    """Every non-index ``*.md`` directly in *directory* appears in its index."""
    index_path = directory / "index.md"
    index_text = index_path.read_text(encoding="utf-8")

    pages = sorted(p for p in directory.glob("*.md") if p.name != "index.md")
    assert pages, f"no pages found in {directory}"

    missing = [page.name for page in pages if page.name not in index_text]
    assert not missing, (
        f"{index_path.relative_to(REPO_ROOT)} does not link: {', '.join(missing)}"
    )


def test_plans_index_links_every_page() -> None:
    _assert_index_links_every_page(PLANS_DIR)


def test_features_index_links_every_page() -> None:
    _assert_index_links_every_page(FEATURES_DIR)
