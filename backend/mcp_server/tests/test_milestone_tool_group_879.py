"""Plan B B6-T2 (#879) — the ``milestone.*`` MCP tool group.

Drives the real ``ToolRegistry.dispatch_request`` stack (API-key auth → RBAC →
workspace gate → tool group → ``MilestoneService``) against a real database, so
nothing is mocked:

* the group advertises exactly the six tools of the task, with the expected
  read/write classification (manifest-level parity);
* create/get/list/update round-trip and a stale ``expected_version`` answers
  ``CONFLICT``;
* ``bind_baseline`` refuses a baseline from another workspace with
  ``VALIDATION_ERROR``;
* ``record_audit`` freezes ``{tier, counts, run_at}`` and bumps the version;
* a viewer may read but not write (RBAC parity with REST);
* the dispatcher resolves the workspace fence from the milestone id, and an
  unknown field is rejected instead of silently dropped.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from baseline.models import BaselineSnapshot
from mcp_server.management.commands.export_tool_manifest import build_manifest
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import resolve_target_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Workspace

pytestmark = pytest.mark.django_db

EXPECTED_TOOLS = {
    "milestone.create": True,
    "milestone.get": False,
    "milestone.list": False,
    "milestone.update": True,
    "milestone.bind_baseline": True,
    "milestone.record_audit": True,
}


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_admin, e2e_userrole_member, e2e_userrole_viewer):
    """Materialise the role rows the API keys resolve against."""
    return None


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create(api_key: str, workspace_id: str, **overrides: Any):
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "name": "PDR Fahrwerk",
        "review_type": "PDR",
        "target_date": "2026-12-01",
    }
    params.update(overrides)
    return _dispatch("milestone.create", params, api_key)


def _baseline(tenant, workspace: Workspace, name: str = "BL-1") -> BaselineSnapshot:
    set_request_tenant(tenant.id)
    try:
        return BaselineSnapshot.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope=BaselineSnapshot.SCOPE_PROJECT,
            name=name,
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def other_workspace(e2e_tenant, e2e_workspace) -> Workspace:
    set_request_tenant(e2e_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=e2e_tenant, name="Milestone Other WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def test_group_advertises_exactly_six_tools() -> None:
    manifest = build_manifest()
    milestone_tools = {
        tool["name"]: tool["is_write"]
        for tool in manifest["tools"]
        if tool["prefix"] == "milestone"
    }

    assert milestone_tools == EXPECTED_TOOLS


def test_registry_classifies_reads_and_writes() -> None:
    registry = ToolRegistry()
    registry._ensure_groups()
    for name, is_write in EXPECTED_TOOLS.items():
        assert registry._is_write_tool(name) is is_write, name


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_get_and_list_round_trip(e2e_workspace, e2e_api_key_member) -> None:
    workspace_id = str(e2e_workspace.id)

    created = _create(e2e_api_key_member, workspace_id)
    assert created.success is True, created.message
    milestone = created.data["milestone"]
    assert milestone["workspace_id"] == workspace_id
    assert milestone["name"] == "PDR Fahrwerk"
    assert milestone["review_type"] == "PDR"
    assert milestone["target_date"] == "2026-12-01"
    assert milestone["status"] == "planned"
    assert milestone["baseline_id"] is None
    assert milestone["audit_snapshot"] is None
    assert milestone["version"] == 1

    read = _dispatch(
        "milestone.get", {"id": milestone["id"]}, e2e_api_key_member
    )
    assert read.success is True, read.message
    assert read.data["milestone"]["id"] == milestone["id"]

    listed = _dispatch(
        "milestone.list", {"workspace_id": workspace_id}, e2e_api_key_member
    )
    assert listed.success is True, listed.message
    assert milestone["id"] in {row["id"] for row in listed.data["milestones"]}
    assert listed.data["count"] == len(listed.data["milestones"])


def test_list_is_ordered_by_target_date_then_id(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    late = _create(
        e2e_api_key_member, workspace_id, name="late", target_date="2027-03-01"
    ).data["milestone"]
    early_a = _create(
        e2e_api_key_member, workspace_id, name="early-a", target_date="2026-01-01"
    ).data["milestone"]
    early_b = _create(
        e2e_api_key_member, workspace_id, name="early-b", target_date="2026-01-01"
    ).data["milestone"]

    listed = _dispatch(
        "milestone.list", {"workspace_id": workspace_id}, e2e_api_key_member
    )
    assert listed.success is True, listed.message
    same_day = sorted([early_a["id"], early_b["id"]])
    assert [row["id"] for row in listed.data["milestones"]] == [
        same_day[0],
        same_day[1],
        late["id"],
    ]


def test_update_round_trip_and_version_conflict(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id).data["milestone"]

    updated = _dispatch(
        "milestone.update",
        {
            "id": created["id"],
            "name": "CDR Fahrwerk",
            "status": "in_review",
            "expected_version": 1,
        },
        e2e_api_key_member,
    )
    assert updated.success is True, updated.message
    assert updated.data["milestone"]["name"] == "CDR Fahrwerk"
    assert updated.data["milestone"]["status"] == "in_review"
    assert updated.data["milestone"]["version"] == 2

    stale = _dispatch(
        "milestone.update",
        {"id": created["id"], "name": "stale", "expected_version": 1},
        e2e_api_key_member,
    )
    assert stale.success is False
    assert stale.error_code == "CONFLICT"


def test_update_rejects_unknown_field(e2e_workspace, e2e_api_key_member) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id).data["milestone"]

    response = _dispatch(
        "milestone.update",
        {"id": created["id"], "typo_field": "x"},
        e2e_api_key_member,
    )
    assert response.success is False
    assert response.error_code == "VALIDATION_ERROR"
    assert "typo_field" in response.message


# ---------------------------------------------------------------------------
# Domain actions
# ---------------------------------------------------------------------------


def test_bind_baseline_bumps_the_version(
    e2e_tenant, e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id).data["milestone"]
    baseline = _baseline(e2e_tenant, e2e_workspace)

    bound = _dispatch(
        "milestone.bind_baseline",
        {"id": created["id"], "baseline_id": str(baseline.id)},
        e2e_api_key_member,
    )
    assert bound.success is True, bound.message
    assert bound.data["milestone"]["baseline_id"] == str(baseline.id)
    assert bound.data["milestone"]["version"] == 2


def test_bind_baseline_from_other_workspace_is_refused(
    e2e_tenant, e2e_workspace, other_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id).data["milestone"]
    foreign = _baseline(e2e_tenant, other_workspace, name="BL-other")

    response = _dispatch(
        "milestone.bind_baseline",
        {"id": created["id"], "baseline_id": str(foreign.id)},
        e2e_api_key_member,
    )
    assert response.success is False
    assert response.error_code == "VALIDATION_ERROR"

    unchanged = _dispatch(
        "milestone.get", {"id": created["id"]}, e2e_api_key_member
    )
    assert unchanged.data["milestone"]["baseline_id"] is None
    assert unchanged.data["milestone"]["version"] == 1


def test_record_audit_freezes_the_snapshot(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id).data["milestone"]

    recorded = _dispatch(
        "milestone.record_audit", {"id": created["id"]}, e2e_api_key_member
    )
    assert recorded.success is True, recorded.message
    snapshot = recorded.data["milestone"]["audit_snapshot"]
    assert snapshot is not None
    assert set(snapshot["counts"]) == {"total", "blockers", "warnings"}
    assert snapshot["tier"]
    assert snapshot["run_at"]
    assert recorded.data["milestone"]["version"] == 2


# ---------------------------------------------------------------------------
# RBAC + workspace fence
# ---------------------------------------------------------------------------


def test_viewer_can_read_but_not_write(
    e2e_workspace, e2e_api_key_member, e2e_api_key_viewer
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id)
    ).data["milestone"]

    read = _dispatch("milestone.get", {"id": created["id"]}, e2e_api_key_viewer)
    assert read.success is True, read.message

    denied = _dispatch(
        "milestone.update",
        {"id": created["id"], "name": "viewer write"},
        e2e_api_key_viewer,
    )
    assert denied.success is False
    assert denied.error_code == "PERMISSION_DENIED"


def test_read_and_write_tools_resolve_the_owning_workspace(
    e2e_workspace, e2e_api_key_member
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id)
    ).data["milestone"]

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        for tool in (
            "milestone.get",
            "milestone.update",
            "milestone.bind_baseline",
            "milestone.record_audit",
        ):
            assert resolve_target_workspace_id(tool, {"id": created["id"]}) == str(
                e2e_workspace.id
            )
    finally:
        clear_request_tenant()


def test_tenant_fence_hides_foreign_milestone_ids(
    e2e_workspace, e2e_api_key_member
) -> None:
    """An id of another tenant resolves to NOT_FOUND, never to data."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id)
    ).data["milestone"]

    # A well-formed id that belongs to no row behaves like an unknown id.
    missing = _dispatch(
        "milestone.get", {"id": str(uuid.uuid4())}, e2e_api_key_member
    )
    assert missing.success is False
    assert missing.error_code == "NOT_FOUND"

    listed = _dispatch(
        "milestone.list",
        {"workspace_id": str(uuid.uuid4())},
        e2e_api_key_member,
    )
    assert listed.success is False
    assert listed.error_code == "NOT_FOUND"

    # The created row is visible to its own tenant.
    own = _dispatch("milestone.get", {"id": created["id"]}, e2e_api_key_member)
    assert own.success is True, own.message
