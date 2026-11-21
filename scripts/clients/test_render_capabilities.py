"""Tests for the client capability matrix (#2001).

Pins the validation rules of the ``capabilities`` section (nothing is claimed
without evidence) and the rendered legend / matrix / detail tables, including
DE/EN parity of the generated page. Only stdlib + PyYAML; no Django/DB.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_RENDER_PATH = REPO_ROOT / "scripts" / "clients" / "render.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("reqlo_client_render_caps", _RENDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = _load_renderer()


def _registry() -> dict[str, Any]:
    return copy.deepcopy(render.load_registry())


def _cell(registry: dict[str, Any], client_id: str, row: str) -> dict[str, Any]:
    return next(c for c in registry["capabilities"]["cells"][client_id] if c["row"] == row)


def test_committed_registry_section_is_valid() -> None:
    assert render.validate_capabilities(_registry()) == []


def test_claude_code_supported_and_partial_cells_have_live_evidence() -> None:
    # supported/partial claims rest on the live run; "unsupported" may rest on a
    # repository inspection (for example "no hook files shipped").
    for cell in _registry()["capabilities"]["cells"]["claude-code"]:
        if cell["status"] in ("supported", "partial"):
            assert cell["evidence"]["kind"] == "live", cell["row"]
        if cell["status"] == "unsupported":
            assert cell["evidence"]["kind"] in ("live", "repo"), cell["row"]


def test_unknown_status_is_an_error() -> None:
    registry = _registry()
    _cell(registry, "claude-code", "skills")["status"] = "mostly"
    problems = render.validate_capabilities(registry)
    assert any("skills: unknown status 'mostly'" in p for p in problems)


@pytest.mark.parametrize("status", ["supported", "partial"])
def test_missing_evidence_is_an_error(status: str) -> None:
    registry = _registry()
    cell = _cell(registry, "claude-code", "skills")
    cell["status"] = status
    cell.pop("evidence")
    problems = render.validate_capabilities(registry)
    assert any(f"skills: {status} needs evidence" in p for p in problems)


def test_evidence_without_detail_is_an_error() -> None:
    registry = _registry()
    _cell(registry, "codex", "mcp_connection")["evidence"] = {"kind": "registry"}
    problems = render.validate_capabilities(registry)
    assert any("codex.mcp_connection: supported needs evidence" in p for p in problems)


def test_unknown_evidence_kind_is_an_error() -> None:
    registry = _registry()
    _cell(registry, "codex", "mcp_connection")["evidence"] = {"kind": "rumour", "detail": "x"}
    problems = render.validate_capabilities(registry)
    assert any("unknown evidence kind 'rumour'" in p for p in problems)


@pytest.mark.parametrize("status", ["partial", "unsupported"])
def test_missing_issue_and_note_is_an_error(status: str) -> None:
    registry = _registry()
    cell = _cell(registry, "claude-code", "role_agents")
    cell["status"] = status
    for field in ("issues", "note_de", "note_en"):
        cell.pop(field, None)
    problems = render.validate_capabilities(registry)
    assert any(f"role_agents: {status} needs an issue or an explanatory note" in p for p in problems)


def test_note_alone_justifies_unsupported() -> None:
    registry = _registry()
    cell = _cell(registry, "claude-code", "role_agents")
    cell.pop("issues")
    assert render.validate_capabilities(registry) == []


def test_unverified_needs_no_evidence() -> None:
    registry = _registry()
    cell = _cell(registry, "codex", "skills")
    for field in ("evidence", "note_de", "note_en"):
        cell.pop(field)
    assert render.validate_capabilities(registry) == []


def test_unknown_client_id_is_an_error() -> None:
    registry = _registry()
    registry["capabilities"]["cells"]["cursor"] = []
    problems = render.validate_capabilities(registry)
    assert "capabilities: unknown client id 'cursor'" in problems


def test_unknown_row_key_is_an_error() -> None:
    registry = _registry()
    registry["capabilities"]["cells"]["kimi-code"].append({"row": "teleport", "status": "unverified"})
    problems = render.validate_capabilities(registry)
    assert "capabilities.kimi-code.teleport: unknown row key" in problems


def test_duplicate_cell_row_is_an_error() -> None:
    registry = _registry()
    cells = registry["capabilities"]["cells"]["hermes"]
    cells.append(copy.deepcopy(cells[0]))
    problems = render.validate_capabilities(registry)
    assert "capabilities.hermes.mcp_connection: duplicate row" in problems


def test_duplicate_row_definition_is_an_error() -> None:
    registry = _registry()
    rows = registry["capabilities"]["groups"][0]["rows"]
    rows.append(copy.deepcopy(rows[0]))
    problems = render.validate_capabilities(registry)
    assert "capabilities: duplicate row 'mcp_connection'" in problems


def test_legend_must_list_the_four_statuses() -> None:
    registry = _registry()
    registry["capabilities"]["legend"].pop()
    problems = render.validate_capabilities(registry)
    assert any(p.startswith("capabilities.legend:") for p in problems)


def test_page_renders_legend_versions_and_symbols() -> None:
    page = render.render_capabilities(_registry(), lang="en")
    assert page.startswith(render.GENERATED_HEADER)
    for symbol, status in (("✓", "supported"), ("◐", "partial"), ("✗", "unsupported"), ("?", "unverified")):
        assert f"| {symbol} | `{status}` |" in page
    assert "2026-11-21" in page and "1.9.0-beta.5" in page and "1.9.0-beta.4" in page
    assert "| MCP connection | ◐ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |" in page
    assert "| Role agents | ✗ | ✗ | ✗ | ✗ | ? | ✗ | ? |" in page


def test_missing_cell_renders_as_unverified() -> None:
    page = render.render_capabilities(_registry(), lang="en")
    # Kimi Code lists no role_agents cell -> explicit "?" in its detail table.
    kimi = page.split("### Kimi Code", 1)[1].split("###", 1)[0]
    assert "| Role agents | ? `unverified` | — | — | — |" in kimi


def test_issue_links_point_at_github_issues() -> None:
    page = render.render_capabilities(_registry(), lang="en")
    assert "[#1974](https://github.com/Popoboxxo/ReqogniLoom/issues/1974)" in page


def test_capability_pages_are_planned_and_parity_equal() -> None:
    files = render.plan_outputs(render.load_registry())
    en = files[render.DOCS_DIR / "capabilities.md"]
    de = files[render.DOCS_DIR / "capabilities.de.md"]
    assert render.check_parity(files) == []
    assert "## Legend" in en and "## Legende" in de
    broken = dict(files)
    broken[render.DOCS_DIR / "capabilities.de.md"] = de + "\n## extra\n"
    assert "capabilities: DE/EN heading count differs" in render.check_parity(broken)


def test_readme_links_the_capability_page() -> None:
    files = render.plan_outputs(render.load_registry())
    assert "(capabilities.md)" in files[render.DOCS_DIR / "README.md"]
    assert "(capabilities.de.md)" in files[render.DOCS_DIR / "README.de.md"]
