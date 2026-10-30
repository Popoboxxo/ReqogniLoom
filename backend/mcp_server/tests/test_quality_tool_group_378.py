"""Plan B / B5-T3 (#378) — MCP ``quality.*`` tool group.

Pins the MCP surface: two published tools, ``assess`` is fail-closed
write-gated while ``query`` is read-exempt, and the workspace binding is the
same one REST enforces — an entity from another workspace of the same tenant is
``NOT_FOUND``, a fenced key on a foreign workspace is ``-32001`` before the
handler runs.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from auth_tenancy.models import UserRole
from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tests.helpers import extract_error_code, extract_result, post_mcp
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, QualityAssessment, Requirement, Tenant, Workspace
from presets.models import WorkspacePresetConfig

pytestmark = pytest.mark.django_db

_VERDICT = {
    "score": 0.4,
    "reasoning": "mock",
    "suggestions": [],
    "criteria": {"atomic": 0.4},
}


class _CountingProvider:
    PROVIDER_NAME = "counting"
    MODEL_NAME = "counting-v1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.calls.append(prompt)
        return json.dumps(_VERDICT)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider()
    monkeypatch.setattr("llm_adapter.providers.get_provider", lambda *a, **k: fake)
    return fake


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, is_active=True, preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()
    WorkspacePresetConfig.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        active_tier="extended",
        terminology_profile="dev_mode",
        downgrade_policy="allow",
    )
    return workspace


def _make_requirement(workspace: Workspace, title: str) -> Requirement:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.objects.create(
            tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=workspace.tenant,
            workspace=workspace,
            artifact=artifact,
            title=title,
            description="seeded by test_quality_tool_group_378",
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def requirement(e2e_workspace: Workspace) -> Requirement:
    return _make_requirement(e2e_workspace, "The system shall answer")


@pytest.fixture
def other_workspace(e2e_tenant: Tenant) -> Workspace:
    return _make_workspace(e2e_tenant, "Quality Other WS")


@pytest.fixture
def requirement_in_other_workspace(other_workspace: Workspace) -> Requirement:
    return _make_requirement(other_workspace, "Belongs to the other workspace")


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _fenced_key(tenant: Tenant, user, workspace: Workspace) -> str:
    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name=f"quality-fenced-{uuid.uuid4().hex[:6]}",
        principal_type="agent",
        agent_label="quality-agent",
        scope="write",
        workspace_ids=[str(workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    return key.plaintext


# ---------------------------------------------------------------------------
# Schemas + registry wiring
# ---------------------------------------------------------------------------


def test_group_publishes_the_two_quality_tools():
    from mcp_server.tools.quality import QualityToolGroup

    names = {schema["name"] for schema in QualityToolGroup().get_tool_schemas()}
    assert names == {"quality.assess", "quality.query"}


def test_quality_tools_are_in_the_live_registry_and_manifest():
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    manifest = build_manifest()
    by_name = {tool["name"]: tool for tool in manifest["tools"]}
    assert {"quality.assess", "quality.query"} <= set(by_name)
    assert by_name["quality.assess"]["is_write"] is True
    assert by_name["quality.query"]["is_write"] is False
    assert by_name["quality.assess"]["prefix"] == "quality"


def test_assess_and_query_are_gated_as_documented():
    registry = ToolRegistry()
    assert registry._is_write_tool("quality.assess") is True
    assert registry._is_write_tool("quality.query") is False


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def test_viewer_key_may_not_assess_but_may_query(
    e2e_userrole_viewer: UserRole,
    e2e_api_key_viewer: str,
    e2e_workspace: Workspace,
    requirement: Requirement,
):
    assess = _dispatch(
        "quality.assess",
        {
            "workspace_id": str(e2e_workspace.id),
            "entity_type": "Requirement",
            "entity_id": str(requirement.id),
        },
        e2e_api_key_viewer,
    )
    assert assess.success is False
    assert assess.error_code == "PERMISSION_DENIED"

    query = _dispatch(
        "quality.query",
        {
            "workspace_id": str(e2e_workspace.id),
            "entity_type": "Requirement",
            "entity_id": str(requirement.id),
        },
        e2e_api_key_viewer,
    )
    assert query.success is True
    assert query.data == {"assessments": [], "count": 0, "latest": None}


# ---------------------------------------------------------------------------
# Workspace binding
# ---------------------------------------------------------------------------


def test_mcp_quality_assess_other_workspace_entity_not_found(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_workspace: Workspace,
    requirement_in_other_workspace: Requirement,
    other_workspace: Workspace,
    provider: _CountingProvider,
):
    """Workspace A is addressed; the entity belongs to workspace B (same tenant)."""
    result = _dispatch(
        "quality.assess",
        {
            "workspace_id": str(e2e_workspace.id),
            "entity_type": "Requirement",
            "entity_id": str(requirement_in_other_workspace.id),
        },
        e2e_api_key_member,
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"
    assert provider.calls == []
    assert QualityAssessment.unscoped.count() == 0


def test_fenced_key_on_a_foreign_workspace_is_denied_with_32001(
    e2e_tenant: Tenant,
    e2e_user_member,
    e2e_userrole_member: UserRole,
    e2e_workspace: Workspace,
    other_workspace: Workspace,
    requirement_in_other_workspace: Requirement,
):
    key = _fenced_key(e2e_tenant, e2e_user_member, e2e_workspace)
    response = post_mcp(
        Client(),
        "quality.assess",
        {
            "workspace_id": str(other_workspace.id),
            "entity_type": "Requirement",
            "entity_id": str(requirement_in_other_workspace.id),
        },
        api_key=key,
    )
    # The transport answers 403 with the JSON-RPC error body (the -32001 code
    # is the wire contract the QA pipeline reads, not the HTTP status).
    assert response.status_code in (200, 403), response.content
    assert response.json()["error"]["code"] == -32001
    assert extract_error_code(response) == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# End-to-end through the HTTP transport
# ---------------------------------------------------------------------------


def test_assess_over_http_returns_the_rest_payload(
    e2e_userrole_member: UserRole,
    e2e_api_key_member: str,
    e2e_workspace: Workspace,
    requirement: Requirement,
    provider: _CountingProvider,
):
    client = Client()
    params = {
        "workspace_id": str(e2e_workspace.id),
        "entity_type": "Requirement",
        "entity_id": str(requirement.id),
    }
    response = post_mcp(client, "quality.assess", params, api_key=e2e_api_key_member)
    assert response.status_code == 200, response.content
    payload = extract_result(response)

    assert "content" not in payload
    assert payload["cached"] is False
    assert payload["status"] == "ok"
    assert payload["prompt_slot"] == "quality_requirement"
    assert payload["entity_id"] == str(requirement.id)
    assert len(provider.calls) == 1

    query = post_mcp(
        client, "quality.query", params, api_key=e2e_api_key_member
    )
    history = extract_result(query)
    assert history["count"] == 1
    assert history["latest"]["assessment_id"] == payload["assessment_id"]
