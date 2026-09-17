"""Fails CI the moment the registry and the committed manifest disagree —
this is the guard the 2026-08-05 research found missing: the committed
allowlist silently fell to 51/107 tools with nothing catching it.

The guard compares the *whole* tool contract (name, is_write, description and
inputSchema), not just the tool names. Agent templates, skills and the plugin
generators under ``dist/plugins/`` are built straight from the committed
manifest, so a stale ``inputSchema`` there makes every downstream consumer emit
calls that no longer satisfy the live registry — exactly what happened when
``events.dlq_list``, ``events.dlq_replay`` and ``permissions.revoke`` gained a
required ``workspace_id`` parameter without the manifest being regenerated
(issue #434).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from mcp_server.management.commands.export_tool_manifest import (
    _MANIFEST_SUFFIX,
    build_manifest,
)

#: Explicit escape hatch for environments that place the repo somewhere this
#: test cannot walk to (e.g. a CI image that copies only ``docs/``).
_MANIFEST_PATH_ENV = "MCP_TOOL_MANIFEST_PATH"

#: Opt-out for the *unreachable manifest* case. Unset (the default), an
#: unreachable manifest FAILS the test — this guard exists specifically to
#: catch the container/path misconfiguration that let the manifest silently
#: drift to 51/107 tools in the first place, so "can't find it" must not be
#: mistaken for "nothing to check". Set this only for an environment that
#: genuinely and permanently cannot mount ``docs/`` (documented exception),
#: never as a routine way to make a red run green.
_MANIFEST_UNREACHABLE_SKIP_ENV = "MCP_TOOL_MANIFEST_ALLOW_SKIP"


def _find_manifest_path() -> Optional[Path]:
    """Locate ``docs/agent-templates/tool-manifest.json``, or return None.

    A fixed ``parents[N]`` index cannot work here: on the host this file lives
    at ``<repo>/backend/mcp_server/tests/`` (repo root = ``parents[3]``), while
    in the container ``backend/`` *is* ``/app`` and ``docs/`` is bind-mounted at
    ``/app/docs`` (root = ``parents[2]``). The previous hard-coded
    ``parents[3]`` therefore resolved to ``/docs/...`` inside Docker and the
    assertion never ran there (issue #434). Walking up until the manifest turns
    up handles both layouts, plus any future one.
    """
    override = os.environ.get(_MANIFEST_PATH_ENV)
    if override:
        candidate = Path(override).expanduser().resolve()
        return candidate if candidate.is_file() else None

    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / _MANIFEST_SUFFIX
        if candidate.is_file():
            return candidate
    return None


MANIFEST_PATH = _find_manifest_path()


def _by_name(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Index a manifest's ``tools`` list by tool name."""
    return {tool["name"]: tool for tool in manifest["tools"]}


def _canonical(value: Any) -> str:
    """Return a stable, order-insensitive JSON rendering for comparison.

    ``inputSchema`` dicts are rebuilt on every registry import, so key order is
    not a meaningful difference — only content is. Sorting keys keeps the guard
    from firing on cosmetic reordering.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


@pytest.mark.django_db
def test_committed_manifest_matches_live_registry() -> None:
    """The committed manifest must be a byte-for-byte-equivalent contract."""
    if MANIFEST_PATH is None:
        reason = (
            f"{_MANIFEST_SUFFIX} not reachable from {Path(__file__).resolve()} "
            f"— no ancestor directory contains it and ${_MANIFEST_PATH_ENV} is "
            "unset. In Docker this means docker-compose's `./docs:/app/docs` "
            "mount is missing; mount it or point "
            f"${_MANIFEST_PATH_ENV} at the manifest so this guard can run."
        )
        # An unreachable manifest must fail loudly, not skip: a silent skip is
        # exactly how the committed allowlist fell to 51/107 tools unnoticed
        # (see module docstring). Only an explicit, deliberate opt-out may
        # downgrade this to a skip.
        if os.environ.get(_MANIFEST_UNREACHABLE_SKIP_ENV):
            pytest.skip(reason)
        pytest.fail(reason)

    committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    live = build_manifest()

    committed_tools = _by_name(committed)
    live_tools = _by_name(live)

    missing = live_tools.keys() - committed_tools.keys()
    stale = committed_tools.keys() - live_tools.keys()

    assert not missing, (
        f"{len(missing)} tool(s) exist in the registry but not in the "
        f"committed manifest — run export_tool_manifest and commit: {sorted(missing)}"
    )
    assert not stale, (
        f"{len(stale)} tool(s) in the committed manifest no longer exist in "
        f"the registry — regenerate and commit: {sorted(stale)}"
    )

    # Name sets can match while the rest of the contract drifts. Compare every
    # field a downstream consumer actually reads:
    #   * is_write   — security-relevant write gating,
    #   * description— what an agent uses to pick a tool,
    #   * inputSchema— the call contract itself (required params!).
    # Comparing only names + is_write let a newly required parameter ship
    # unnoticed (issue #434).
    drifted: Dict[str, list[str]] = {}
    for name in sorted(committed_tools.keys() & live_tools.keys()):
        differing = [
            field
            for field in ("is_write", "prefix", "description", "inputSchema")
            if _canonical(committed_tools[name].get(field))
            != _canonical(live_tools[name].get(field))
        ]
        if differing:
            drifted[name] = differing

    assert not drifted, (
        f"{len(drifted)} tool(s) drifted between the registry and the committed "
        f"manifest: {json.dumps(drifted, sort_keys=True)}\n"
        "Regenerate and commit:\n"
        "  host:      python backend/manage.py export_tool_manifest\n"
        "  container: docs/ is mounted read-only, so write elsewhere and copy —\n"
        "             docker compose run --rm --no-deps -v /tmp/out:/out backend \\\n"
        "               python manage.py export_tool_manifest --out /out/tool-manifest.json"
    )

    # tool_count is what plugin builders trust instead of len(tools); a stale
    # count silently truncates generated allowlists.
    assert committed.get("tool_count") == len(committed["tools"]), (
        f"tool_count ({committed.get('tool_count')}) does not match the number "
        f"of tools ({len(committed['tools'])}) in {MANIFEST_PATH}."
    )
    assert committed["tool_count"] == live["tool_count"], (
        f"tool_count drifted: committed {committed['tool_count']} vs live "
        f"{live['tool_count']} — regenerate and commit."
    )
