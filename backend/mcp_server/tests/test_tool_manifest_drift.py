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

Re-baselining is a named entry point, not a side effect of a run
(#1103 / REQ-193)::

    TOOL_MANIFEST_REBASELINE=/tmp/manifest-candidate.json \\
        pytest mcp_server/tests/test_tool_manifest_drift.py -q

regenerates the manifest from the live registry. It refuses to do so while a
tool would silently DISAPPEAR from the manifest without a reason and an issue
(``$RATCHET_JUSTIFY``), because every agent template is generated from it. In
Docker ``docs/`` is read-only, so the ``<path>`` (candidate) form is the
portable one there; ``=1`` targets the committed file and needs a writable
``docs/``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from mcp_server.management.commands.export_tool_manifest import (
    _MANIFEST_SUFFIX,
    build_manifest,
)
from mcp_server.tests.ratchet_framework import (
    assert_dump_justified,
    entry_point,
    resolve_rebaseline_target,
    split_baseline,
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


def _find_manifest_path() -> Path | None:
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


def _rebaseline(
    live: dict[str, Any],
    live_tools: dict[str, dict[str, Any]],
    committed_tools: dict[str, dict[str, Any]],
) -> Path | None:
    """Regenerate the manifest — but only when the named env var asks for it.

    Re-baselining *this* ratchet is regenerating the committed manifest from the
    live registry, so that is what ``TOOL_MANIFEST_REBASELINE=<path|1>`` does
    (#1103 / REQ-193); a plain run resolves no target and writes nothing.

    The widening direction is :data:`JUSTIFY_ROTATED`, not ``JUSTIFY_NEW``:
    the danger is not "the manifest documents a tool the registry has" but the
    opposite — a tool the manifest stops documenting. Every agent template is
    generated from that manifest, so a tool that silently disappears from it is
    a contract break (#434), and "re-baseline it away" is exactly the escape
    hatch a ratchet must not offer. The dump therefore goes through
    :func:`assert_dump_justified` and refuses unless every disappearing tool
    carries a reason plus an issue (inline JSON or ``$RATCHET_JUSTIFY``).

    Manifest JSON is written directly rather than through
    :func:`ratchet_framework.write_baseline`: this baseline is a derived mirror
    of the registry, not a ``{"violations": [...]}`` gap list.
    """
    point = entry_point("tool-manifest-drift")
    target = resolve_rebaseline_target(point, default_path=MANIFEST_PATH)
    if target is None:
        return None
    diff = split_baseline(live_tools, committed_tools)
    assert_dump_justified(diff, point)
    target.write_text(
        json.dumps(live, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def _by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
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

    # The named re-baseline entry point (#1103 / REQ-193). It runs before the
    # assertions below so a dump is self-verifying: the comparison that follows
    # then reads the file the dump just wrote (for `=1`; a <path> candidate is
    # compared against on the next normal run). Note that in Docker `docs/` is
    # bind-mounted read-only, so `<path>` (a candidate) is the portable form
    # there — `=1` only works where the manifest is writable.
    _rebaseline(live, live_tools, committed_tools)

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
    drifted: dict[str, list[str]] = {}
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


# ---------------------------------------------------------------------------
# API-005 — name collisions must raise, never be silently deduplicated
# ---------------------------------------------------------------------------


def _raw_schema_names() -> list[str]:
    """Collect raw (pre-dedup) tool names from every registered tool group.

    Deliberately independent of :func:`build_manifest`: the defect this guards
    was a drift test comparing the committed manifest against the very builder
    that silently dropped the duplicate, so both sides agreed on a loss.
    """
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    names: list[str] = []
    seen_group_ids: set[int] = set()
    for group in registry._groups.values():
        if id(group) in seen_group_ids:
            continue
        seen_group_ids.add(id(group))
        if not hasattr(group, "get_tool_schemas"):
            continue
        names.extend(schema.get("name", "") for schema in group.get_tool_schemas())
    return names


def test_raw_names_equal_published_names_in_production_registry() -> None:
    """Against the real registry: raw names == published names == 301."""
    raw_names = _raw_schema_names()
    assert len(raw_names) == len(set(raw_names)), "raw tool schemas contain a duplicate"
    published = [tool["name"] for tool in build_manifest()["tools"]]
    assert set(raw_names) == set(published)
    assert len(raw_names) == len(published) == 301


# ---------------------------------------------------------------------------
# R2A-004 — description ratchet (grammar + minimum information density)
# ---------------------------------------------------------------------------

#: Broken English produced by the old ``"Delete a {prefix} entity"`` template.
#: ``"an ADR"`` is grammatical and deliberately does not match.
_BAD_ARTICLE_RE = re.compile(r"\ba (?:adr|issue|risk|glossary|change_request|work_item|icd)\b")

_MIN_DESCRIPTION_LENGTH = 40

#: Frozen legacy short descriptions owned by tool-group modules outside this
#: change's write set. The ratchet direction is one-way: this set may only
#: shrink as those groups are updated; a new short description fails.
_SHORT_DESCRIPTION_BASELINE: frozenset[str] = frozenset({
    "comment.create",
    "comment.resolve",
    "diagram.query",
    "goal.read",
    "needs.create",
    "needs.query",
    "needs.read",
    "requirement.create",
    "requirement.decompose",
    "requirement.derive",
    "requirement.get",
    "test.run_create",
    "test.run_get",
})


def test_committed_manifest_descriptions_meet_ratchet() -> None:
    """Every committed description is grammatical and informative enough.

    A tool description is the primary signal an agent uses to pick a tool;
    the old generic factory shipped strings such as ``"Delete a adr entity
    (write)."`` and 22 tools had under 40 characters. The generic CRUD group
    now emits per-prefix descriptions (grammatical, >= 40 chars, with
    hard-delete vs. soft-delete semantics); this gate keeps it that way.
    """
    assert MANIFEST_PATH is not None, (
        f"{_MANIFEST_SUFFIX} is unreachable; mount docs/ or set "
        f"${_MANIFEST_PATH_ENV} so the description ratchet can run."
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    descriptions = {
        tool["name"]: tool.get("description", "") for tool in manifest["tools"]
    }

    bad_articles = sorted(
        name for name, description in descriptions.items()
        if _BAD_ARTICLE_RE.search(description)
    )
    assert not bad_articles, (
        f"{len(bad_articles)} description(s) contain a broken article "
        f"('a adr'/'a issue'/'a risk'): {bad_articles}. Use a per-prefix "
        "label and 'the <label>' phrasing."
    )

    short = {
        name for name, description in descriptions.items()
        if len(description) < _MIN_DESCRIPTION_LENGTH
    }
    assert short <= _SHORT_DESCRIPTION_BASELINE, (
        f"{len(short - _SHORT_DESCRIPTION_BASELINE)} new description(s) under "
        f"{_MIN_DESCRIPTION_LENGTH} chars: "
        f"{sorted(short - _SHORT_DESCRIPTION_BASELINE)}. "
        "Every new description must be >= 40 characters."
    )


def test_build_manifest_raises_on_duplicate_tool_names(monkeypatch) -> None:
    """Two groups emitting one name must raise, not silently shadow one tool."""
    from mcp_server.management.commands import export_tool_manifest as command_module

    collision = {"name": "duplicate.tool", "description": "", "inputSchema": {}}
    group_a = mock.Mock()
    group_a.get_tool_schemas.return_value = [collision]
    group_b = mock.Mock()
    group_b.get_tool_schemas.return_value = [collision]
    fake_registry = mock.Mock()
    fake_registry._groups = {"a": group_a, "b": group_b}
    fake_registry._is_write_tool.return_value = False
    monkeypatch.setattr(command_module, "ToolRegistry", lambda: fake_registry)

    with pytest.raises(ValueError, match="duplicate.tool"):
        build_manifest()
