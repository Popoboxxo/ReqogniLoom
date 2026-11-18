"""S4.2 / R2C-009 — the consolidated tool-policy sets must never drift.

`tool_registry.py` now declares each tool group once (`_GroupSpec`) and DERIVES
the eight historical policy collections from those specs at import time. They
are kept as module-level aliases because ~17 tests and the manifest drift gate
import them. The security case for this refactor rests on the derived values
being ALGEBRAICALLY IDENTICAL to the pre-consolidation literals: a future edit
to `GROUP_SPECS` that places a write tool in `_READ_ONLY_TOOL_NAMES` would make
`_is_write_tool()` return False and silently bypass the write-RBAC gate.

These frozen baselines were captured from the pre-consolidation literals (HEAD
`517fa897`) and independently verified byte-equal to the derived sets.
"""
from __future__ import annotations

import json
from pathlib import Path

import mcp_server.tool_registry as registry

BASELINE = json.loads(
    (Path(__file__).with_name("fixtures") / "tool_policy_baselines.json").read_text(
        encoding="utf-8"
    )
)

# The fail-closed use is `_READ_ONLY_TOOL_NAMES` (+ suffixes); `_WRITE_TOOL_PREFIXES`
# is a documented catalogue / test oracle. All eight are pinned regardless.
POLICY_SETS = (
    "_READ_ONLY_TOOL_NAMES",
    "_READ_ONLY_TOOL_SUFFIXES",
    "_WRITE_TOOL_PREFIXES",
    "_GOVERNANCE_TOOL_NAMESPACES",
    "_GOVERNANCE_TOOL_NAMES",
    "_INSTANCE_LEVEL_TOOLS",
    "_ALWAYS_VISIBLE_TOOLS",
    "_TENANT_ADMIN_ELEVATED_USER_TOOLS",
)


def test_derived_policy_sets_match_frozen_baseline() -> None:
    for name in POLICY_SETS:
        derived = getattr(registry, name)
        expected = BASELINE[name]
        assert sorted(derived) == sorted(expected), (
            f"{name} drifted from the pre-consolidation baseline "
            f"(derived={len(derived)}, baseline={len(expected)})"
        )


def test_fail_closed_write_default_preserved() -> None:
    """Unknown tool names must still be treated as WRITE (RBAC-gated)."""
    from mcp_server.tool_registry import ToolRegistry

    reg = ToolRegistry()
    unknown = "totally.unknown.tool"
    assert unknown not in registry._READ_ONLY_TOOL_NAMES
    assert not any(unknown.endswith(s) for s in registry._READ_ONLY_TOOL_SUFFIXES)
    # Fail-closed: an unrecognised name is NOT granted a read bypass.
    assert reg._is_write_tool(unknown) is True


def test_write_tool_names_are_pinned() -> None:
    """The WRITE catalogue (an import-time tuple) is pinned too.

    The 301-tool count itself is already gated by ``test_tool_manifest_drift``;
    this test only guards the policy set that consolidation rewrote.
    """
    assert isinstance(registry._WRITE_TOOL_PREFIXES, tuple)
    assert len(registry._WRITE_TOOL_PREFIXES) == 146
