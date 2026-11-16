"""Slice 2 (Tabellenansicht) — MCP tool ``artifact.bulk_transition``.

The transition semantics live in ``application.bulk_update_service`` (covered by
``application/tests/test_bulk_update_service_transition.py``); this file pins the
MCP surface:

* the **manifest** contains the tool, the catalogue moved 297 -> 298 (and on to
  301 with the Phase D ``tool`` group and Tabellenansicht slice 3's
  ``saved_view`` group, the 48th prefix); the drift gate compares the live
  registry against that file, so the number is not maintained by hand;
* the registry advertises the schema (required ``item_type``/``ids``/``to_state``/
  ``change_reason``, **no** ``workspace_id``) and classifies the tool as a write;
* **error codes are the REST ones**: a request defect is ``VALIDATION_ERROR``, a
  missing workspace write role is ``PERMISSION_DENIED`` — while a *refused row*
  is not an error at all but an entry in ``failed[]`` (partial success);
* an end-to-end dispatch (API key -> RBAC -> tool -> service -> facade) really
  moves the row, and the payload is JSON primitives only.

Everything runs against the real ``ToolRegistry``/DB; nothing is mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from auth_tenancy.models import ROLE_EDITOR, ApiKey
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from mcp_server.management.commands.export_tool_manifest import _MANIFEST_SUFFIX
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

EXPECTED_TOOL_COUNT = 301
TRANSITION_TOOL = "artifact.bulk_transition"
IN_REVIEW = "in_review"
APPROVED = "approved"


def _find_manifest_path() -> Path:
    """Locate the committed manifest in both the host and the container layout."""
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / _MANIFEST_SUFFIX
        if candidate.is_file():
            return candidate
    raise AssertionError(f"could not find {_MANIFEST_SUFFIX} above {__file__}")


MANIFEST_PATH = _find_manifest_path()


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _requirement_workflow(e2e_tenant, e2e_workspace):
    """Provision the extended requirement graph the transitions need."""
    set_request_tenant(e2e_tenant.id)
    try:
        create_default_workflow(
            workspace_id=e2e_workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=e2e_tenant.id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_member, e2e_userrole_viewer):
    """Materialise the role rows the API keys resolve against."""


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create_requirement(api_key: str, workspace_id: str, title: str) -> dict[str, Any]:
    created = _dispatch(
        "requirement.create",
        {
            "workspace_id": workspace_id,
            "title": title,
            # The extended preset refuses ``in_review -> approved`` without
            # these three, which would mask the graph case under test.
            "description": "System shall behave",
            "acceptance_criteria": "Given X, when Y, then Z",
            "verification_method": "Inspection",
        },
        api_key,
    )
    assert created.success is True, created.message
    return created.data["requirement"]


def _bulk_transition(
    api_key: str,
    ids: list[str],
    *,
    item_type: str = "Requirement",
    to_state: str = IN_REVIEW,
    change_reason: str = "bulk review",
):
    return _dispatch(
        TRANSITION_TOOL,
        {
            "item_type": item_type,
            "ids": ids,
            "to_state": to_state,
            "change_reason": change_reason,
        },
        api_key,
    )


def _state_of(requirement_id: str) -> str:
    return WorkflowItemState.unscoped.get(
        item_id=requirement_id, item_type="Requirement"
    ).current_state


# ---------------------------------------------------------------------------
# Manifest / registry
# ---------------------------------------------------------------------------


def test_manifest_contains_the_transition_tool(manifest: dict[str, Any]) -> None:
    tools = {tool["name"]: tool for tool in manifest["tools"]}

    assert TRANSITION_TOOL in tools
    tool = tools[TRANSITION_TOOL]
    assert tool["prefix"] == "artifact"
    assert tool["is_write"] is True
    properties = tool["inputSchema"]["properties"]
    assert tool["inputSchema"]["required"] == [
        "item_type",
        "ids",
        "to_state",
        "change_reason",
    ]
    # The workspace is derived from the ids — a second, client-chosen scope
    # would let the role check and the written rows disagree.
    assert "workspace_id" not in properties
    assert properties["ids"]["minItems"] == 1
    assert properties["ids"]["maxItems"] == 100


def test_tool_count_is_301_with_49_prefixes(manifest: dict[str, Any]) -> None:
    assert manifest["tool_count"] == EXPECTED_TOOL_COUNT
    assert len(manifest["tools"]) == EXPECTED_TOOL_COUNT
    assert len({tool["prefix"] for tool in manifest["tools"]}) == 49


def test_registry_advertises_the_tool_as_a_write() -> None:
    registry = ToolRegistry()
    registry._ensure_groups()

    schema = next(
        (
            entry
            for entry in registry.all_tool_schemas()
            if entry.get("name") == TRANSITION_TOOL
        ),
        None,
    )
    assert schema is not None, f"{TRANSITION_TOOL} missing from the live registry"
    assert schema["inputSchema"]["properties"]["ids"]["type"] == "array"
    # Fail-closed classification: not listed as read-only, therefore write-gated.
    assert registry._is_write_tool(TRANSITION_TOOL) is True


# ---------------------------------------------------------------------------
# End-to-end dispatch
# ---------------------------------------------------------------------------


def test_bulk_transition_moves_the_rows_and_reports_failures(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    first = _create_requirement(e2e_api_key_member, workspace_id, "Req A")
    second = _create_requirement(e2e_api_key_member, workspace_id, "Req B")

    moved = _bulk_transition(
        e2e_api_key_member,
        [first["artifact_id"], second["artifact_id"]],
    )

    assert moved.success is True, moved.message
    assert moved.data["failed"] == []
    assert moved.data["transitioned"] == [
        {"artifact_id": first["artifact_id"], "state": IN_REVIEW},
        {"artifact_id": second["artifact_id"], "state": IN_REVIEW},
    ]
    assert _state_of(first["id"]) == IN_REVIEW
    assert _state_of(second["id"]) == IN_REVIEW
    # JSON primitives only — the payload crosses a JSON-RPC boundary.
    json.dumps(moved.data)

    # An editor may not approve (the extended graph allows approver/admin only).
    # This is a *refused row*, so it is reported, never raised.
    refused = _bulk_transition(
        e2e_api_key_member,
        [first["artifact_id"], second["artifact_id"]],
        to_state=APPROVED,
    )

    assert refused.success is True, refused.message
    assert refused.data["transitioned"] == []
    assert [row["code"] for row in refused.data["failed"]] == [
        "FORBIDDEN",
        "FORBIDDEN",
    ]
    assert _state_of(first["id"]) == IN_REVIEW


def test_partial_success_keeps_the_reachable_rows(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    first = _create_requirement(e2e_api_key_member, workspace_id, "Keep me")
    missing = str(uuid4())

    result = _bulk_transition(
        e2e_api_key_member, [first["artifact_id"], missing]
    )

    assert result.success is True, result.message
    assert [row["artifact_id"] for row in result.data["transitioned"]] == [
        first["artifact_id"]
    ]
    assert result.data["failed"][0]["index"] == 1
    assert result.data["failed"][0]["code"] == "NOT_FOUND"
    assert result.data["failed"][0]["artifact_id"] == missing
    assert _state_of(first["id"]) == IN_REVIEW


def test_blank_change_reason_is_a_validation_error(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    requirement = _create_requirement(e2e_api_key_member, workspace_id, "No reason")

    result = _bulk_transition(
        e2e_api_key_member,
        [requirement["artifact_id"]],
        change_reason="",
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert _state_of(requirement["id"]) == "draft"


def test_over_100_ids_is_a_validation_error(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    requirement = _create_requirement(e2e_api_key_member, workspace_id, "Many")

    result = _bulk_transition(
        e2e_api_key_member, [requirement["artifact_id"]] * 101
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_two_workspaces_is_a_validation_error(
    e2e_workspace, e2e_tenant, e2e_api_key_member, e2e_user_member
) -> None:
    """A second workspace in the same tenant: one request may not span both."""
    from auth_tenancy.models import UserRole

    set_request_tenant(e2e_tenant.id)
    try:
        other = Workspace.objects.create(
            tenant=e2e_tenant, name="Other WS", preset={"name": "extended"}
        )
        create_default_workflow(
            workspace_id=other.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=e2e_tenant.id,
        )
        UserRole.objects.create(
            tenant=e2e_tenant,
            user=e2e_user_member,
            workspace=other,
            role=ROLE_EDITOR,
        )
    finally:
        clear_request_tenant()

    here = _create_requirement(
        e2e_api_key_member, str(e2e_workspace.id), "Here"
    )
    there = _create_requirement(e2e_api_key_member, str(other.id), "There")

    result = _bulk_transition(
        e2e_api_key_member, [here["artifact_id"], there["artifact_id"]]
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_read_only_key_is_refused(e2e_workspace, e2e_api_key_viewer) -> None:
    result = _bulk_transition(e2e_api_key_viewer, [str(uuid4())])

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_fenced_key_cannot_reach_this_workspace(
    e2e_workspace, e2e_tenant, e2e_user_member
) -> None:
    """A key fenced to other workspaces has no target to check → fail closed."""
    set_request_tenant(e2e_tenant.id)
    try:
        other = Workspace.objects.create(
            tenant=e2e_tenant, name="Fenced WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()

    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=e2e_tenant,
        user=e2e_user_member,
        name=f"fenced-{uuid4().hex[:8]}",
        key_hash=hash_api_key(plaintext),
        workspace_ids=[str(other.id)],
    )

    result = _bulk_transition(plaintext, [str(uuid4())])

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_role_is_evaluated_in_the_derived_workspace(
    e2e_tenant, e2e_workspace, e2e_user_member, e2e_api_key_member
) -> None:
    """An editor elsewhere must not transition this workspace's rows (ADR-011).

    The dispatcher's write gate sees the tenant-wide role union (the tool names
    no workspace), so the *service* is what has to narrow it: it derives the
    workspace from the ids and resolves the caller's roles there.
    """
    from auth_tenancy.models import UserRole

    requirement = _create_requirement(
        e2e_api_key_member, str(e2e_workspace.id), "Workspace A row"
    )

    set_request_tenant(e2e_tenant.id)
    try:
        other = Workspace.objects.create(
            tenant=e2e_tenant, name="Elsewhere WS", preset={"name": "extended"}
        )
        UserRole.objects.filter(
            user=e2e_user_member, workspace=e2e_workspace
        ).delete()
        UserRole.objects.create(
            tenant=e2e_tenant,
            user=e2e_user_member,
            workspace=other,
            role=ROLE_EDITOR,
        )
    finally:
        clear_request_tenant()

    result = _bulk_transition(e2e_api_key_member, [requirement["artifact_id"]])

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"
    assert _state_of(requirement["id"]) == "draft"


def test_user_and_tenant_fixtures_are_distinct(
    e2e_tenant: Tenant, e2e_user_member: User
) -> None:
    """Guard: the fixtures above really are one tenant/user, not shared rows."""
    assert e2e_user_member.tenant_id == e2e_tenant.id
