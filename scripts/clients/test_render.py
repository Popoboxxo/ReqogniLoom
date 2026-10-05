"""Tests for the client-doc renderer (#1171, Bundle B0, AP-1.2).

These pin the properties the CI drift gate depends on:

* **Idempotence** — rendering twice yields byte-identical output, so a green
  ``--check`` cannot be a formatting accident.
* **Committed == generated** — the checked-in ``docs/clients/**`` equals a fresh
  render; a hand edit fails here as well as in CI.
* **DE/EN parity** — every client page has the same heading and code-block
  counts in both languages.
* **Registry <-> shipped snippet** — the referenced ``dist/**`` artifacts exist,
  carry the registry's transport path, and embed no literal key.

Only stdlib + PyYAML; no Django/DB. Runs from the repo root.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDER_PATH = REPO_ROOT / "scripts" / "clients" / "render.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("reqlo_client_render", _RENDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load_renderer()


def test_render_is_idempotent() -> None:
    files = render.plan_outputs(render.load_registry())
    files_again = render.plan_outputs(render.load_registry())
    assert files == files_again


def test_committed_docs_match_generated() -> None:
    files = render.plan_outputs(render.load_registry())
    stale = []
    for path, content in files.items():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            stale.append(path.relative_to(REPO_ROOT).as_posix())
    assert not stale, (
        f"docs/clients artifacts are stale: {stale}. "
        "Run `python scripts/clients/render.py` and commit the result."
    )


def test_german_and_english_are_parity_equal() -> None:
    files = render.plan_outputs(render.load_registry())
    assert render.check_parity(files) == []


def test_registry_matches_shipped_snippets() -> None:
    problems = render.validate_artifacts(render.load_registry())
    assert problems == []


def test_every_client_has_both_language_pages() -> None:
    files = render.plan_outputs(render.load_registry())
    for client_id in render.CLIENT_IDS:
        assert render.DOCS_DIR / f"{client_id}.md" in files
        assert render.DOCS_DIR / f"{client_id}.de.md" in files
