"""Fails CI the moment the registry and the committed manifest disagree —
this is the guard the 2026-08-05 research found missing: the committed
allowlist silently fell to 51/107 tools with nothing catching it."""
import json
from pathlib import Path

import pytest

from mcp_server.management.commands.export_tool_manifest import build_manifest

MANIFEST_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs" / "agent-templates" / "tool-manifest.json"
)


@pytest.mark.django_db
def test_committed_manifest_matches_live_registry():
    assert MANIFEST_PATH.exists(), (
        "docs/agent-templates/tool-manifest.json is missing — run "
        "`python manage.py export_tool_manifest` and commit the result."
    )
    committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    live = build_manifest()

    committed_names = {t["name"] for t in committed["tools"]}
    live_names = {t["name"] for t in live["tools"]}

    missing = live_names - committed_names
    stale = committed_names - live_names

    assert not missing, (
        f"{len(missing)} tool(s) exist in the registry but not in the "
        f"committed manifest — run export_tool_manifest and commit: {sorted(missing)}"
    )
    assert not stale, (
        f"{len(stale)} tool(s) in the committed manifest no longer exist in "
        f"the registry — regenerate and commit: {sorted(stale)}"
    )

    # Name sets can match while the security-relevant is_write flag still
    # drifts (e.g. a tool's write-gating changes without a rename). Compare
    # (name, is_write) pairs too so that case is caught here instead of
    # going unnoticed with a stale committed manifest.
    committed_write_flags = {t["name"]: t["is_write"] for t in committed["tools"]}
    live_write_flags = {t["name"]: t["is_write"] for t in live["tools"]}
    flipped = sorted(
        name for name in committed_write_flags.keys() & live_write_flags.keys()
        if committed_write_flags[name] != live_write_flags[name]
    )
    assert not flipped, (
        f"is_write changed for {len(flipped)} tool(s) without a name change — "
        f"run export_tool_manifest and commit: {flipped}"
    )
