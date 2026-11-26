"""Plan F F3-T6 (#1374) — the ``work_item.*`` MCP tool group.

Drives the real ``ToolRegistry.dispatch_request`` stack (API-key auth -> RBAC ->
workspace gate -> tool group -> ``WorkItemService``) against a real database,
so the transport is exercised end to end and nothing is mocked:

* the eight tools are published, with the read/write classification the
  dispatcher gates on (``read``/``query``/``resume`` read-only, the rest write);
* create/read/query round-trip incl. ``custom_fields`` on the backing Artifact,
  and the same item is readable through REST (transport parity);
* update/set_progress bump the version and stamp the heartbeat; a stale
  ``expected_version`` answers ``CONFLICT``;
* transition enforces rule 10 (``blocked`` needs a reason) and reports the
  previous/new state;
* checkpoint + resume return the newest checkpoint and the open items sorted
  ``(ordinal, id)``, excluding finished work;
* outdate/reactivate (P2.8) round-trip the soft-delete: the item disappears from
  ``query``, reappears with ``include_outdated``, keeps its workflow state and
  comes back finished; the preset's mandatory ``change_reason`` gate, an
  unknown id and a stale version are reported as the REST endpoint reports them;
* the WorkItem lifecycle is complete on both transports — the REST
  ``DELETE``/``reactivate`` pair and ``work_item.outdate``/``.reactivate`` exist
  side by side (entity-surface note in ``entity_surface_matrix.py``);
* viewer may read but not write (RBAC parity);
* a foreign workspace is denied for both reads and writes (workspace fence),
  and the dispatcher resolves the owning workspace from the item id.
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from application.work_item_service import WorkItemService
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.management.commands.export_tool_manifest import build_manifest
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import resolve_target_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Document, Tenant, WorkItem, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

IN_PROGRESS = "in_progress"
BLOCKED = "blocked"
DONE = "done"
DROPPED = "dropped"

READ_TOOLS = frozenset({"work_item.read", "work_item.query", "work_item.resume"})
WRITE_TOOLS = frozenset(
    {
        "work_item.create",
        "work_item.update",
        "work_item.transition",
        "work_item.set_progress",
        "work_item.checkpoint",
        "work_item.outdate",
        "work_item.reactivate",
    }
)
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_admin, e2e_userrole_member, e2e_userrole_viewer):
    """Materialise the role rows the API keys resolve against."""
    return None


@pytest.fixture(autouse=True)
def _work_item_workflow(e2e_tenant, e2e_workspace):
    """Provision the ``work_item_standard`` lifecycle the transitions need."""
    set_request_tenant(e2e_tenant.id)
    try:
        create_default_workflow(
            workspace_id=e2e_workspace.id,
            preset="work_item_standard",
            item_type="WorkItem",
            tenant_id=e2e_tenant.id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def document(e2e_tenant, e2e_workspace) -> Document:
    """A document in the E2E workspace (the mandatory home of an item)."""
    set_request_tenant(e2e_tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=e2e_tenant, workspace=e2e_workspace, artifact_type="Document"
        )
        return Document.objects.create(
            tenant=e2e_tenant,
            artifact=artifact,
            workspace=e2e_workspace,
            title="Work plan",
            kind=Document.Kind.PLAN,
            body="# Work plan",
        )
    finally:
        clear_request_tenant()


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _transition(api_key: str, item_id: str, target: str, **extra: Any):
    """Move an item; the E2E workspace preset mandates a change_reason."""
    params: dict[str, Any] = {
        "id": item_id,
        "target_state": target,
        "change_reason": "test transition",
    }
    params.update(extra)
    return _dispatch("work_item.transition", params, api_key)


def _create(api_key: str, workspace_id: str, document_id: str, **overrides: Any):
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "document_id": document_id,
        "kind": "Step",
        "title": "Write the MCP surface",
        "body": "## Step\n\nDo the work.",
    }
    params.update(overrides)
    return _dispatch("work_item.create", params, api_key)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def test_all_ten_tools_are_published_with_the_right_classification() -> None:
    tools = {tool["name"]: tool for tool in build_manifest()["tools"]}
    for name in ALL_TOOLS:
        assert name in tools, f"{name} missing from the catalogue"
        assert tools[name]["prefix"] == "work_item"
    for name in READ_TOOLS:
        assert tools[name]["is_write"] is False, f"{name} must be read-only"
    for name in WRITE_TOOLS:
        assert tools[name]["is_write"] is True, f"{name} must be write-gated"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_read_and_query_round_trip(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(
        e2e_api_key_member,
        workspace_id,
        str(document.id),
        custom_fields={"traceability_ref": "REQ-L1-001"},
    )
    assert created.success is True, created.message
    item = created.data["work_item"]
    assert item["uid"].startswith("WI-")
    assert item["workspace_id"] == workspace_id
    assert item["document_id"] == str(document.id)
    assert item["status"] == "todo"
    assert item["version"] == 1
    assert item["artifact_id"]
    assert item["custom_fields"] == {"traceability_ref": "REQ-L1-001"}

    read = _dispatch("work_item.read", {"id": item["id"]}, e2e_api_key_member)
    assert read.success is True, read.message
    assert read.data["work_item"]["body"] == "## Step\n\nDo the work."

    listed = _dispatch(
        "work_item.query",
        {"workspace_id": workspace_id, "document_id": str(document.id)},
        e2e_api_key_member,
    )
    assert listed.success is True, listed.message
    assert [row["id"] for row in listed.data["work_items"]] == [item["id"]]
    assert listed.data["count"] == 1

    by_uid = _dispatch(
        "work_item.query",
        {"workspace_id": workspace_id, "uid": item["uid"]},
        e2e_api_key_member,
    )
    assert by_uid.success is True, by_uid.message
    assert [row["id"] for row in by_uid.data["work_items"]] == [item["id"]]


def test_create_workflow_init_failure_is_an_internal_error_and_rolls_back(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    """P2.13: the create is rolled back and the tool answers a static error."""
    workspace_id = str(e2e_workspace.id)

    with patch(
        "workflow.services.initialize_workflow_states",
        side_effect=RuntimeError("boom"),
    ):
        result = _create(e2e_api_key_member, workspace_id, str(document.id))

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == (
        "The artifact was not created because its workflow state could not be "
        "initialised."
    )
    assert "boom" not in (result.message or "")
    assert WorkItem.unscoped.filter(workspace_id=e2e_workspace.id).count() == 0


def test_create_is_visible_through_rest(
    e2e_workspace, e2e_api_key_member, admin_client, document
) -> None:
    """Transport parity: one item, readable with the same field values."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    assert created.success is True, created.message
    item = created.data["work_item"]

    rest = admin_client.get(f"/api/v1/work-items/{item['id']}/")
    assert rest.status_code == 200, rest.content
    body = rest.json()
    assert body["id"] == item["id"]
    assert body["uid"] == item["uid"]
    assert body["document_id"] == item["document_id"]
    assert body["status"] == item["status"]
    assert body["version"] == item["version"]


def test_update_and_set_progress(e2e_workspace, e2e_api_key_member, document) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item = created.data["work_item"]

    updated = _dispatch(
        "work_item.update",
        {"id": item["id"], "title": "Renamed", "next_action": "Continue here"},
        e2e_api_key_member,
    )
    assert updated.success is True, updated.message
    assert updated.data["work_item"]["title"] == "Renamed"
    assert updated.data["work_item"]["next_action"] == "Continue here"
    assert updated.data["work_item"]["version"] == 2
    assert updated.data["work_item"]["last_activity_at"] is not None

    progress = _dispatch(
        "work_item.set_progress",
        {"id": item["id"], "progress": 40},
        e2e_api_key_member,
    )
    assert progress.success is True, progress.message
    assert progress.data["work_item"]["progress"] == 40
    assert progress.data["work_item"]["version"] == 3


def test_update_rejects_document_id_and_status(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    moved = _dispatch(
        "work_item.update",
        {"id": item_id, "document_id": str(document.id)},
        e2e_api_key_member,
    )
    assert moved.success is False
    assert moved.error_code == "VALIDATION_ERROR"

    status = _dispatch(
        "work_item.update",
        {"id": item_id, "status": DONE},
        e2e_api_key_member,
    )
    assert status.success is False
    assert status.error_code == "VALIDATION_ERROR"


def test_stale_expected_version_is_a_conflict(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    first = _dispatch(
        "work_item.update",
        {"id": item_id, "title": "First", "expected_version": 1},
        e2e_api_key_member,
    )
    assert first.success is True, first.message

    stale = _dispatch(
        "work_item.update",
        {"id": item_id, "title": "Second", "expected_version": 1},
        e2e_api_key_member,
    )
    assert stale.success is False
    assert stale.error_code == "CONFLICT"


# ---------------------------------------------------------------------------
# Transition
# ---------------------------------------------------------------------------


def test_transition_reports_previous_and_new_state(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    moved = _transition(e2e_api_key_member, item_id, IN_PROGRESS)
    assert moved.success is True, moved.message
    assert moved.data["previous_state"] == "todo"
    assert moved.data["new_state"] == IN_PROGRESS
    assert moved.data["work_item"]["status"] == IN_PROGRESS
    assert moved.data["work_item"]["last_activity_at"] is not None


def test_transition_into_blocked_requires_a_reason(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]
    _transition(e2e_api_key_member, item_id, IN_PROGRESS)

    missing = _transition(e2e_api_key_member, item_id, BLOCKED)
    assert missing.success is False
    assert missing.error_code == "VALIDATION_ERROR"

    blocked = _transition(
        e2e_api_key_member,
        item_id,
        BLOCKED,
        blocked_reason="Waiting for review",
    )
    assert blocked.success is True, blocked.message
    assert blocked.data["work_item"]["blocked_reason"] == "Waiting for review"


# ---------------------------------------------------------------------------
# Checkpoint / resume
# ---------------------------------------------------------------------------


def test_checkpoint_and_resume_return_open_items_sorted(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    workspace_id = str(e2e_workspace.id)
    document_id = str(document.id)

    second = _create(
        e2e_api_key_member, workspace_id, document_id, title="Second", ordinal=2
    )
    first = _create(
        e2e_api_key_member, workspace_id, document_id, title="First", ordinal=1
    )
    third = _create(
        e2e_api_key_member, workspace_id, document_id, title="Done", ordinal=3
    )
    assert second.success and first.success and third.success

    # Finish the third item: resume must omit it.
    for target in (IN_PROGRESS, DONE):
        moved = _transition(
            e2e_api_key_member, third.data["work_item"]["id"], target
        )
        assert moved.success is True, moved.message

    checkpoint = _dispatch(
        "work_item.checkpoint",
        {
            "workspace_id": workspace_id,
            "document_id": document_id,
            "next_action": "Pick up step one",
            "ordinal": 0,
        },
        e2e_api_key_member,
    )
    assert checkpoint.success is True, checkpoint.message
    assert checkpoint.data["work_item"]["kind"] == "Checkpoint"
    assert checkpoint.data["work_item"]["next_action"] == "Pick up step one"

    resumed = _dispatch(
        "work_item.resume",
        {"workspace_id": workspace_id, "document_id": document_id},
        e2e_api_key_member,
    )
    assert resumed.success is True, resumed.message
    assert resumed.data["checkpoint"]["next_action"] == "Pick up step one"
    assert [row["id"] for row in resumed.data["open_items"]] == [
        checkpoint.data["work_item"]["id"],
        first.data["work_item"]["id"],
        second.data["work_item"]["id"],
    ]


def test_resume_requires_a_document(
    e2e_workspace, e2e_api_key_member
) -> None:
    result = _dispatch(
        "work_item.resume",
        {"workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_create_without_document_is_a_validation_error(
    e2e_workspace, e2e_api_key_member
) -> None:
    result = _dispatch(
        "work_item.create",
        {
            "workspace_id": str(e2e_workspace.id),
            "kind": "Step",
            "title": "No document",
        },
        e2e_api_key_member,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_create_with_unknown_document_is_not_found(
    e2e_workspace, e2e_api_key_member
) -> None:
    import uuid

    result = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(uuid.uuid4())
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_set_progress_out_of_range_is_a_validation_error(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    result = _dispatch(
        "work_item.set_progress",
        {"id": created.data["work_item"]["id"], "progress": 101},
        e2e_api_key_member,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_unknown_item_is_not_found(e2e_api_key_member) -> None:
    import uuid

    result = _dispatch(
        "work_item.read", {"id": str(uuid.uuid4())}, e2e_api_key_member
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Soft delete / restore (P2.8)
# ---------------------------------------------------------------------------


def test_outdate_and_reactivate_round_trip(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    """Soft-delete hides the item, reactivate brings it back in its state."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]
    assert created.data["work_item"]["status"] == "todo"

    deleted = _dispatch(
        "work_item.outdate",
        {"id": item_id, "change_reason": "no longer needed"},
        e2e_api_key_member,
    )
    assert deleted.success is True, deleted.message
    assert deleted.data == {"id": item_id, "status": "outdated"}

    listed = _dispatch(
        "work_item.query", {"workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )
    assert item_id not in [item["id"] for item in listed.data["work_items"]]

    with_deleted = _dispatch(
        "work_item.query",
        {"workspace_id": str(e2e_workspace.id), "include_outdated": True},
        e2e_api_key_member,
    )
    hidden = [
        item
        for item in with_deleted.data["work_items"]
        if item["id"] == item_id
    ]
    assert hidden and hidden[0]["status"] == "outdated"

    restored = _dispatch(
        "work_item.reactivate", {"id": item_id}, e2e_api_key_member
    )
    assert restored.success is True, restored.message
    # The REST payload: the item came from "outdated" and kept its state.
    assert restored.data["id"] == item_id
    assert restored.data["previous_state"] == "outdated"
    assert restored.data["new_state"] == "todo"
    assert restored.data["work_item"]["id"] == item_id
    assert restored.data["work_item"]["status"] == "todo"

    visible = _dispatch(
        "work_item.query", {"workspace_id": str(e2e_workspace.id)},
        e2e_api_key_member,
    )
    assert item_id in [item["id"] for item in visible.data["work_items"]]


def test_outdate_requires_a_change_reason_when_the_preset_demands_one(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    """The extended E2E workspace mandates a reason on every guarded write."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    refused = _dispatch(
        "work_item.outdate", {"id": item_id}, e2e_api_key_member
    )
    assert refused.success is False
    assert refused.error_code == "VALIDATION_ERROR"

    still_visible = _dispatch(
        "work_item.read", {"id": item_id}, e2e_api_key_member
    )
    assert still_visible.success is True
    assert still_visible.data["work_item"]["status"] != "outdated"


def test_outdate_accepts_the_deprecated_reason_alias(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    """P1.10: an old client sending ``reason`` keeps working unchanged."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    deleted = _dispatch(
        "work_item.outdate",
        {"id": item_id, "reason": "legacy client"},
        e2e_api_key_member,
    )
    assert deleted.success is True, deleted.message
    assert deleted.data["status"] == "outdated"


def test_outdate_stale_expected_version_is_a_conflict(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    result = _dispatch(
        "work_item.outdate",
        {"id": item_id, "change_reason": "gone", "expected_version": 99},
        e2e_api_key_member,
    )
    assert result.success is False
    assert result.error_code == "CONFLICT"


def test_outdate_and_reactivate_unknown_item_is_denied_before_the_handler(
    e2e_api_key_member,
) -> None:
    """A write tool whose target resolves to no row is denied, not NOT_FOUND.

    ``workspace_scope``'s fail-closed write rule (security finding #4) answers
    ``PERMISSION_DENIED`` for a well-formed id that matches no row: a
    nonexistent object must stay indistinguishable from a foreign one. The
    service-level ``NOT_FOUND`` mapping behind that gate is pinned by
    :func:`test_unknown_item_is_not_found_at_the_handler`.
    """
    unknown = str(uuid4())
    for tool in ("work_item.outdate", "work_item.reactivate"):
        params: dict[str, Any] = {"id": unknown}
        if tool == "work_item.outdate":
            params["change_reason"] = "unknown"
        result = _dispatch(tool, params, e2e_api_key_member)
        assert result.success is False, tool
        assert result.error_code == "PERMISSION_DENIED", tool


def test_unknown_item_is_not_found_at_the_handler(
    e2e_tenant, e2e_api_key_member
) -> None:
    """The handler maps the service's NotFoundError — the scope gate never runs here.

    ``_validate_api_key`` hands back a *partial* context (roles are resolved by
    the dispatcher), so this test builds the editor context the service checks
    and calls the tool group directly, bypassing the fail-closed gate that
    answers ``PERMISSION_DENIED`` at dispatch (see the test above).
    """
    from mcp_server.tools.work_items import WorkItemToolGroup

    partial = ToolRegistry()._validate_api_key(e2e_api_key_member)[0]
    assert partial is not None
    ctx = AuthContext(
        user_id=partial.user_id,
        tenant_id=partial.tenant_id,
        active_roles=("editor",),
        auth_method=partial.auth_method,
        api_key_id=partial.api_key_id,
    )
    group = WorkItemToolGroup()
    for tool in ("work_item.outdate", "work_item.reactivate"):
        params: dict[str, Any] = {"id": str(uuid4())}
        if tool == "work_item.outdate":
            params["change_reason"] = "unknown"
        result = group.execute_tool(
            tool, params, ctx, e2e_api_key_member
        )
        assert result.success is False, tool
        assert result.error_code == "NOT_FOUND", tool


def test_outdate_resolves_the_reason_for_the_service() -> None:
    """P1.10 wiring for the new tool: canonical wins, alias is the fallback."""
    from unittest.mock import MagicMock

    from mcp_server.tools.work_items import WorkItemToolGroup

    ctx = AuthContext(
        user_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
    )
    cases = (
        ({"change_reason": "canonical"}, "canonical"),
        ({"reason": "legacy"}, "legacy"),
        ({"change_reason": "canonical", "reason": "legacy"}, "canonical"),
    )
    for params, expected in cases:
        service = MagicMock()
        with patch(
            "mcp_server.tools.work_items.WorkItemService", return_value=service
        ):
            result = WorkItemToolGroup().execute_tool(
                "work_item.outdate",
                {"id": str(uuid4()), **params},
                ctx,
                "reqlo_test",
            )
        assert result.success is True, result.message
        assert service.delete_work_item.call_args.kwargs["change_reason"] == expected


# ---------------------------------------------------------------------------
# REST <-> MCP lifecycle parity (P2.8)
# ---------------------------------------------------------------------------


def test_rest_and_mcp_expose_the_same_work_item_lifecycle() -> None:
    """Both transports must keep the soft-delete/restore pair (no hard-coded count)."""
    from django.urls import resolve

    tools = {tool["name"]: tool for tool in build_manifest()["tools"]}
    for name in ("work_item.outdate", "work_item.reactivate"):
        assert name in tools, f"{name} is missing from the MCP catalogue"
        assert tools[name]["is_write"] is True, f"{name} must be write-gated"

    item_id = uuid4()
    detail = resolve(f"/api/v1/work-items/{item_id}/")
    assert getattr(detail.func, "actions", {}).get("delete") == "destroy"

    reactivate = resolve(f"/api/v1/work-items/{item_id}/reactivate/")
    assert getattr(reactivate.func, "actions", {}).get("post") == "reactivate"


def test_viewer_can_read_but_not_write(
    e2e_workspace, e2e_api_key_member, e2e_api_key_viewer, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    read = _dispatch("work_item.read", {"id": item_id}, e2e_api_key_viewer)
    assert read.success is True, read.message

    denied = _dispatch(
        "work_item.update",
        {"id": item_id, "title": "viewer write"},
        e2e_api_key_viewer,
    )
    assert denied.success is False
    assert denied.error_code == "PERMISSION_DENIED"


def _foreign_workspace_item(tenant: Tenant) -> tuple[Workspace, WorkItem]:
    """Create a workspace the E2E member holds no role in, plus one item."""
    from uuid import uuid4

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"Foreign {uuid4().hex[:8]}", is_active=True
        )
        doc_artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Document"
        )
        document = Document.objects.create(
            tenant=tenant,
            artifact=doc_artifact,
            workspace=workspace,
            title="Foreign plan",
            kind=Document.Kind.PLAN,
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="WorkItem"
        )
        item = WorkItem.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            document=document,
            kind=WorkItem.Kind.STEP,
            title="Foreign item",
        )
        return workspace, item
    finally:
        clear_request_tenant()


def test_foreign_workspace_read_and_write_are_denied(
    e2e_tenant, e2e_api_key_member
) -> None:
    foreign, item = _foreign_workspace_item(e2e_tenant)

    listed = _dispatch(
        "work_item.query", {"workspace_id": str(foreign.id)}, e2e_api_key_member
    )
    assert listed.success is False
    assert listed.error_code == "PERMISSION_DENIED"

    read = _dispatch(
        "work_item.read", {"id": str(item.id)}, e2e_api_key_member
    )
    assert read.success is False
    assert read.error_code == "PERMISSION_DENIED"

    written = _dispatch(
        "work_item.update",
        {"id": str(item.id), "title": "hijack"},
        e2e_api_key_member,
    )
    assert written.success is False
    assert written.error_code == "PERMISSION_DENIED"


def test_read_and_write_tools_resolve_the_owning_workspace(
    e2e_workspace, e2e_api_key_member, document
) -> None:
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    item_id = created.data["work_item"]["id"]

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        assert resolve_target_workspace_id(
            "work_item.read", {"id": item_id}
        ) == str(e2e_workspace.id)
        for tool in (
            "work_item.update",
            "work_item.transition",
            "work_item.set_progress",
        ):
            assert resolve_target_workspace_id(tool, {"id": item_id}) == str(
                e2e_workspace.id
            )
    finally:
        clear_request_tenant()


def test_service_exposes_the_same_resume_contract(
    e2e_tenant, e2e_workspace, e2e_api_key_member, document
) -> None:
    """The MCP answer is exactly ``WorkItemService.resume``'s contract."""
    created = _create(
        e2e_api_key_member, str(e2e_workspace.id), str(document.id)
    )
    assert created.success is True, created.message

    ctx = ToolRegistry()._validate_api_key(e2e_api_key_member)[0]
    assert ctx is not None
    set_request_tenant(e2e_tenant.id)
    try:
        service_result = WorkItemService().resume(
            e2e_workspace.id, document.id, ctx
        )
    finally:
        clear_request_tenant()

    resumed = _dispatch(
        "work_item.resume",
        {
            "workspace_id": str(e2e_workspace.id),
            "document_id": str(document.id),
        },
        e2e_api_key_member,
    )
    assert resumed.success is True, resumed.message
    assert resumed.data == service_result


# ---------------------------------------------------------------------------
# Masked failures are logged (plan P1.12 / M-16)
# ---------------------------------------------------------------------------


def test_masked_failure_is_logged_with_the_tool_name(
    e2e_workspace, e2e_api_key_member, caplog
) -> None:
    """The static ``INTERNAL_ERROR`` answer must not be a silent failure."""
    caplog.set_level(logging.ERROR)

    with patch.object(
        WorkItemService, "list_work_items", side_effect=RuntimeError("boom")
    ):
        result = _dispatch(
            "work_item.query",
            {"workspace_id": str(e2e_workspace.id), "secret": "TOKEN-NOT-LOGGED"},
            e2e_api_key_member,
        )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."
    assert "boom" not in result.message

    records = [
        record
        for record in caplog.records
        if record.name == "mcp_server.tools.work_items"
        and record.levelno >= logging.ERROR
    ]
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert "work_item.query" in records[0].getMessage()
    assert "TOKEN-NOT-LOGGED" not in caplog.text
