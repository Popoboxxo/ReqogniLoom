"""Issue #17 — MCP ``workspace.resolve_references`` (local uid → entity).

The tool resolves a batch of human-readable artifact references
(``REQ-L1-007``, ``NEED-003``, ``ARCH-001``) to their entities within one
workspace, so coding agents (Claude Code, Cursor) and CI gates can load the
full context of every REQ a commit names without hand-mapping UUIDs.

leaf_id : COMP-MC-006 (CrossCuttingToolGroup)
req_id  : REQ-L2-MC-004 (workspace read tools)

Covered here:
  * positive   — multiple artifact types resolve; the response shape matches
                 the issue's example.
  * negative   — unknown and malformed references land in ``not_found``;
                 out-of-bound / wrongly-typed ``references`` lists are
                 VALIDATION_ERROR.
  * isolation  — an id that exists only in another workspace (or tenant) is
                 not resolved; the dispatcher gate refuses a workspace the
                 caller holds no role in.
  * drift      — the tool is registered read-only with a bounded,
                 workspace-required schema (the manifest guard compares the
                 live registry against docs/agent-templates/tool-manifest.json).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple
from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.cross_cutting import (
    _MAX_RESOLVE_REFERENCES,
    CrossCuttingToolGroup,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_ctx(name: str) -> Tuple[Tenant, Workspace, AuthContext]:
    """Create a Tenant + User + Workspace + AuthContext triple for *name*."""
    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )
    return tenant, workspace, ctx


def _ensure_workflow(workspace: Workspace, item_type: str) -> None:
    """Bootstrap the default workflow definition for *item_type*."""
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        clear_request_tenant()


def _seed_entities(workspace: Workspace, ctx: AuthContext) -> Dict[str, str]:
    """Seed one entity per core artifact type; return their local uids."""
    from application.adr_service import AdrService
    from application.architecture_service import ArchitectureService
    from application.requirement_service import RequirementService
    from application.stakeholder_need_service import StakeholderNeedService

    for item_type in ("Requirement", "StakeholderNeed", "ArchitectureElement", "Adr"):
        _ensure_workflow(workspace, item_type)

    RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="SSO Login",
        ctx=ctx,
        description="Single sign-on via SAML 2.0",
        uid="REQ-L1-007",
    )
    need = StakeholderNeedService().create(
        ctx=ctx,
        workspace_id=workspace.id,
        title="Single Sign-On",
        description="Users log in once for all tools",
    )
    ArchitectureService().create_architecture_element(
        workspace_id=workspace.id,
        title="Auth Module",
        ctx=ctx,
        description="Handles authentication and session tokens",
        uid="ARCH-001",
    )
    AdrService().create_adr(
        workspace_id=workspace.id,
        title="Use OIDC for SSO",
        description="OIDC over SAML for ecosystem breadth",
        ctx=ctx,
        uid="ADR-042",
    )
    return {"need": need.uid}


@pytest.fixture
def resolver_env() -> Tuple[Workspace, AuthContext, Dict[str, str]]:
    _, workspace, ctx = _make_ctx("resolve-refs")
    uids = _seed_entities(workspace, ctx)
    return workspace, ctx, uids


def _resolve(workspace: Workspace, ctx: AuthContext, references: list) -> Any:
    group = CrossCuttingToolGroup()
    return group.execute_tool(
        "workspace.resolve_references",
        params={"workspace_id": str(workspace.id), "references": references},
        auth_context=ctx,
        api_key="reqlo_test_key",
    )


# ---------------------------------------------------------------------------
# Positive
# ---------------------------------------------------------------------------


class TestResolvePositive:
    def test_resolves_references_across_artifact_types(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, uids = resolver_env
        result = _resolve(
            workspace, ctx, ["REQ-L1-007", uids["need"], "ARCH-001", "ADR-042"]
        )

        assert result.success is True, result.message
        data = result.data
        assert data["not_found"] == []

        req = data["resolved"]["REQ-L1-007"]
        assert req["title"] == "SSO Login"
        assert req["description"] == "Single sign-on via SAML 2.0"
        assert req["artifact_type"] == "Requirement"
        assert req["status"]  # resolved through the workflow engine
        assert UUID(req["id"])  # a real uuid string, parseable

        assert data["resolved"][uids["need"]]["artifact_type"] == "StakeholderNeed"
        arch = data["resolved"]["ARCH-001"]
        assert arch["artifact_type"] == "ArchitectureElement"
        assert arch["title"] == "Auth Module"
        assert data["resolved"]["ADR-042"]["artifact_type"] == "Adr"

    def test_response_matches_issue_example_shape(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        """The issue's contract verbatim: resolved keyed by reference,
        not_found for the invalid one."""
        workspace, ctx, uids = resolver_env
        result = _resolve(
            workspace,
            ctx,
            ["REQ-L1-007", uids["need"], "ARCH-001", "INVALID-REF-001"],
        )

        assert result.success is True
        resolved = result.data["resolved"]
        not_found = result.data["not_found"]
        assert set(resolved) == {"REQ-L1-007", uids["need"], "ARCH-001"}
        assert not_found == ["INVALID-REF-001"]
        entry = resolved["REQ-L1-007"]
        assert set(entry) == {"id", "artifact_type", "title", "description", "status"}

    def test_empty_reference_list_resolves_to_empty_payload(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = _resolve(workspace, ctx, [])

        assert result.success is True
        assert result.data == {"resolved": {}, "not_found": []}

    def test_duplicate_reference_resolves_once(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = _resolve(workspace, ctx, ["REQ-L1-007", "REQ-L1-007"])

        assert result.success is True
        assert list(result.data["resolved"]) == ["REQ-L1-007"]
        assert result.data["not_found"] == []


# ---------------------------------------------------------------------------
# Negative
# ---------------------------------------------------------------------------


class TestResolveNegative:
    def test_unknown_and_malformed_references_land_in_not_found(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = _resolve(
            workspace,
            ctx,
            [
                "REQ-L1-999",      # well-formed, absent
                "INVALID-REF-001",  # unknown prefix
                "not an id at all",
                "",                # blank
                "   ",             # whitespace only
                "../../etc/passwd",  # hostile, still just no match
            ],
        )

        assert result.success is True, result.message
        assert result.data["resolved"] == {}
        assert result.data["not_found"] == [
            "REQ-L1-999",
            "INVALID-REF-001",
            "not an id at all",
            "",
            "../../etc/passwd",
        ]

    def test_reference_list_longer_than_bound_is_rejected(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        references = [f"REQ-L1-{n:03d}" for n in range(_MAX_RESOLVE_REFERENCES + 1)]

        result = _resolve(workspace, ctx, references)

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert str(_MAX_RESOLVE_REFERENCES) in result.message

    def test_non_string_entries_are_rejected(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = _resolve(workspace, ctx, ["REQ-L1-007", 42, None])  # type: ignore[list-item]

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_references_must_be_a_list(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = _resolve(workspace, ctx, "REQ-L1-007")  # type: ignore[arg-type]

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_missing_references_parameter_is_rejected(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        workspace, ctx, _ = resolver_env
        result = CrossCuttingToolGroup().execute_tool(
            "workspace.resolve_references",
            params={"workspace_id": str(workspace.id)},
            auth_context=ctx,
            api_key="reqlo_test_key",
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_invalid_workspace_uuid_is_rejected(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        _, ctx, _ = resolver_env
        result = CrossCuttingToolGroup().execute_tool(
            "workspace.resolve_references",
            params={"workspace_id": "not-a-uuid", "references": ["REQ-L1-007"]},
            auth_context=ctx,
            api_key="reqlo_test_key",
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_unknown_workspace_reports_not_found(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        _, ctx, _ = resolver_env
        result = CrossCuttingToolGroup().execute_tool(
            "workspace.resolve_references",
            params={"workspace_id": str(uuid4()), "references": ["REQ-L1-007"]},
            auth_context=ctx,
            api_key="reqlo_test_key",
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


class TestResolveIsolation:
    def test_reference_from_other_workspace_not_resolved(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        """The same uid in a sibling workspace must not leak across."""
        workspace, ctx, _ = resolver_env
        _, other_workspace, other_ctx = _make_ctx("resolve-refs-b")
        from application.requirement_service import RequirementService

        _ensure_workflow(other_workspace, "Requirement")
        RequirementService().create_requirement(
            workspace_id=other_workspace.id,
            title="Foreign requirement",
            ctx=other_ctx,
            uid="REQ-L1-007",  # same uid, other workspace
        )

        result = _resolve(workspace, ctx, ["REQ-L1-007"])

        assert result.success is True, result.message
        entry = result.data["resolved"]["REQ-L1-007"]
        assert entry["title"] == "SSO Login"
        assert "Foreign requirement" not in str(result.data)

    def test_reference_from_other_tenant_not_resolved(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        """Same uid in another tenant: invisible, reported not_found."""
        workspace, ctx, _ = resolver_env
        _, foreign_workspace, foreign_ctx = _make_ctx("resolve-refs-tenant-b")

        set_request_tenant(foreign_workspace.tenant_id)
        try:
            from application.requirement_service import RequirementService

            _ensure_workflow(foreign_workspace, "Requirement")
            RequirementService().create_requirement(
                workspace_id=foreign_workspace.id,
                title="Cross-tenant requirement",
                ctx=foreign_ctx,
                uid="REQ-L1-007",
            )
        finally:
            clear_request_tenant()

        result = _resolve(workspace, ctx, ["REQ-L1-007"])

        assert result.success is True, result.message
        entry = result.data["resolved"]["REQ-L1-007"]
        assert entry["title"] == "SSO Login"
        assert "Cross-tenant requirement" not in str(result.data)

    def test_workspace_of_other_tenant_is_not_found(
        self, resolver_env: Tuple[Workspace, AuthContext, Dict[str, str]]
    ) -> None:
        """Naming a foreign-tenant workspace: NOT_FOUND, not a leak."""
        _, ctx, _ = resolver_env
        _, foreign_workspace, _ = _make_ctx("resolve-refs-tenant-c")

        result = CrossCuttingToolGroup().execute_tool(
            "workspace.resolve_references",
            params={
                "workspace_id": str(foreign_workspace.id),
                "references": ["REQ-L1-007"],
            },
            auth_context=ctx,
            api_key="reqlo_test_key",
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Dispatcher gate (real ToolRegistry, real API key)
# ---------------------------------------------------------------------------


def _make_foreign_workspace(tenant: Tenant, name: str, preset: Dict[str, Any]) -> Workspace:
    """Workspace B — same tenant, no role assignment for any e2e user."""
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, is_active=True, preset=preset
        )
    finally:
        clear_request_tenant()
    return workspace


def _dispatch(tool_name: str, params: Dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


class TestDispatchGate:
    def test_foreign_workspace_is_permission_denied(
        self,
        e2e_userrole_viewer: Any,
        e2e_api_key_viewer: str,
        e2e_tenant: Tenant,
        e2e_preset: Dict[str, Any],
    ) -> None:
        """The required ``workspace_id`` is what lets the gate scope
        the caller's roles — resolving against an unassigned workspace
        must fail closed, never return that workspace's data."""
        foreign = _make_foreign_workspace(e2e_tenant, "Foreign Workspace B", e2e_preset)
        result = _dispatch(
            "workspace.resolve_references",
            {"workspace_id": str(foreign.id), "references": ["REQ-L1-007"]},
            e2e_api_key_viewer,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_own_workspace_resolves_through_the_real_gate(
        self,
        e2e_userrole_viewer: Any,
        e2e_api_key_viewer: str,
        e2e_workspace: Workspace,
    ) -> None:
        """Positive control: the caller's own workspace, viewer scope.
        The workspace holds no artifacts — an empty resolved map is the
        correct answer, and proves the call passes the gate."""
        result = _dispatch(
            "workspace.resolve_references",
            {"workspace_id": str(e2e_workspace.id), "references": ["REQ-L1-007"]},
            e2e_api_key_viewer,
        )

        assert result.success is True, result.message
        assert result.data == {"resolved": {}, "not_found": ["REQ-L1-007"]}


# ---------------------------------------------------------------------------
# Registry classification (drift-gate surface)
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_tool_is_read_only_with_required_bounded_schema(self) -> None:
        from mcp_server.management.commands.export_tool_manifest import build_manifest

        tools = {tool["name"]: tool for tool in build_manifest()["tools"]}
        assert "workspace.resolve_references" in tools
        tool = tools["workspace.resolve_references"]

        assert tool["is_write"] is False
        schema = tool["inputSchema"]
        assert set(schema["required"]) == {"workspace_id", "references"}
        assert schema["properties"]["references"]["maxItems"] == _MAX_RESOLVE_REFERENCES
        assert schema["properties"]["references"]["items"] == {"type": "string"}

    def test_group_schema_and_map_agree(self) -> None:
        group = CrossCuttingToolGroup()
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert "workspace.resolve_references" in names
