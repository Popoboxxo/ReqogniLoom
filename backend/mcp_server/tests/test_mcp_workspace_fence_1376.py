"""#1376 / #1373 — an undeclared ``workspace_id`` must not drive the gate.

#1376 (HIGH, CWE-863): ``ToolRegistry._scoped_gate_context`` Case 1 trusts a
client-supplied ``workspace_id`` as the workspace the call targets. That
shortcut exists for tools that genuinely accept the parameter, but it used to
fire for **any** tool: a key fenced to workspace A could send
``{"workspace_id": "<A>", "id": "<object in B>"}`` and the fence + RBAC were
checked against A while the target object was never resolved. The listed
families (``requirement.update``/``outdate``/``reactivate``/``validate``/
``decompose``/``derive`` plus read siblings, structurally ~85 tools) could
therefore read and write foreign-workspace objects.

The root fix pins the shortcut to the tool's **published schema**: only a
declared ``workspace_id`` may activate it. For every other tool the parameter
is dropped before role resolution, so the call behaves exactly as if it had
not been sent — the target object is resolved and fenced normally.

#1373 (MED): ``test.mark_reviewed`` was missing from
``mcp_server.workspace_scope._TOOL_TARGETS``, so its target workspace was never
resolved: fenced keys were over-denied inside their own workspace and an
unfenced Editor in A could flip the review flag of a test case in B.

This module drives the real ``ToolRegistry.dispatch_request`` stack (real
authentication, real fence/RBAC gates) and pins the wire contract through
``ProtocolHandler``. It also ratchets the two structural invariants the fix
relies on: every production group is a ``BaseToolGroup`` (so the schema check
is always available) and every ``_TOOL_TARGETS`` entry really has an
undeclared ``workspace_id`` (otherwise the Case-1 shortcut would pre-empt its
own object-derived resolution).
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from auth_tenancy.services.authentication import AuthenticationService
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.base import BaseToolGroup
from mcp_server.workspace_scope import _TOOL_TARGETS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, TestCase, Workspace
from presets.models import WorkspacePresetConfig

pytestmark = pytest.mark.django_db

SCOPE_MESSAGE_FRAGMENT = "restricted to specific workspaces"


# ---------------------------------------------------------------------------
# Seed helpers (mirror test_api_key_scope_diagnostics_1357.py)
# ---------------------------------------------------------------------------


def _make_workspace(tenant: Tenant, name: str, preset: dict[str, Any]) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, is_active=True, preset=preset
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
            description="seeded by test_mcp_workspace_fence_1376",
        )
    finally:
        clear_request_tenant()


def _make_test_case(workspace: Workspace, title: str) -> TestCase:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.unscoped.create(
            tenant=workspace.tenant,
            workspace=workspace,
            artifact_type="TestCase:Unit",
        )
        return TestCase.unscoped.create(
            tenant=workspace.tenant,
            artifact=artifact,
            title=title,
            description="seeded by test_mcp_workspace_fence_1376",
            steps=["step 1"],
        )
    finally:
        clear_request_tenant()


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def foreign_workspace(e2e_tenant: Tenant, e2e_preset: dict[str, Any]) -> Workspace:
    """Workspace B — same tenant, no role assignment for any e2e user."""
    return _make_workspace(e2e_tenant, "W13c Foreign Workspace B", e2e_preset)


@pytest.fixture
def foreign_requirement(foreign_workspace: Workspace) -> Requirement:
    return _make_requirement(foreign_workspace, "W13c secret req in B")


@pytest.fixture
def home_requirement(e2e_workspace: Workspace) -> Requirement:
    return _make_requirement(e2e_workspace, "W13c req in A")


@pytest.fixture
def foreign_test_case(foreign_workspace: Workspace) -> TestCase:
    return _make_test_case(foreign_workspace, "W13c secret test in B")


@pytest.fixture
def home_test_case(e2e_workspace: Workspace) -> TestCase:
    return _make_test_case(e2e_workspace, "W13c test in A")


@pytest.fixture
def fenced_key(
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    e2e_user_member,
    e2e_userrole_member,
) -> str:
    """Write-scoped agent key fenced to workspace A, owned by an Editor in A."""
    return (
        AuthenticationService()
        .create_api_key(
            user_id=e2e_user_member.id,
            tenant_id=e2e_tenant.id,
            name=f"w13c-fenced-{uuid4().hex[:8]}",
            principal_type="agent",
            agent_label="w13c-agent",
            scope="write",
            workspace_ids=[str(e2e_workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


# ---------------------------------------------------------------------------
# #1376 — ATTACK: undeclared workspace_id on a foreign target
# ---------------------------------------------------------------------------


class TestUndeclaredWorkspaceIdCannotBypassTargetResolution:
    """``workspace_id=A`` plus an object id in B must not reach the object."""

    def test_requirement_update_on_foreign_object_is_denied(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        before = foreign_requirement.title

        with patch(
            "application.requirement_service.RequirementService.update_requirement"
        ) as updater, patch(
            "application.requirement_service.RequirementService.get_requirement"
        ) as getter:
            result = _dispatch(
                "requirement.update",
                {
                    "workspace_id": str(e2e_workspace.id),
                    "id": str(foreign_requirement.id),
                    "data": {"title": "W13c bypass"},
                },
                fenced_key,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message
        # Denied before any service work: neither read nor mutated.
        updater.assert_not_called()
        getter.assert_not_called()
        foreign_requirement.refresh_from_db()
        assert foreign_requirement.title == before

    def test_requirement_get_on_foreign_object_is_denied(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        with patch(
            "application.requirement_service.RequirementService.get_requirement"
        ) as getter:
            result = _dispatch(
                "requirement.get",
                {
                    "workspace_id": str(e2e_workspace.id),
                    "id": str(foreign_requirement.id),
                },
                fenced_key,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message
        getter.assert_not_called()
        # Confidentiality: the foreign payload never reaches the caller.
        assert foreign_requirement.title not in str(result.data or "")
        assert foreign_requirement.title not in (result.message or "")

    def test_existing_foreign_and_nonexistent_ids_are_indistinguishable(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        """No existence oracle: both answer the same fail-closed denial."""
        params = {"workspace_id": str(e2e_workspace.id)}
        foreign = _dispatch(
            "requirement.get",
            {**params, "id": str(foreign_requirement.id)},
            fenced_key,
        )
        missing = _dispatch(
            "requirement.get", {**params, "id": str(uuid4())}, fenced_key
        )

        assert foreign.error_code == missing.error_code == "PERMISSION_DENIED"
        assert foreign.message == missing.message
        assert SCOPE_MESSAGE_FRAGMENT in foreign.message

    def test_undeclared_workspace_id_is_not_visible_to_the_handler(
        self,
        fenced_key: str,
        home_requirement: Requirement,
    ) -> None:
        """The stripped param must not reach the handler either.

        ``requirement.update``'s handler tolerates extra params; the assertion
        is at the dispatch seam so it holds for handlers with and without
        ``reject_unknown_params``.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        normalized = registry._drop_undeclared_workspace_id(
            "requirement.update",
            {"workspace_id": str(uuid4()), "id": str(home_requirement.id)},
        )
        assert "workspace_id" not in normalized
        assert normalized["id"] == str(home_requirement.id)


# ---------------------------------------------------------------------------
# Wire contract: the QA pipeline sees -32001, not a handler error
# ---------------------------------------------------------------------------


class TestWireErrorContract:
    @staticmethod
    def _handle(method: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
        from mcp_server.protocol_handler import ProtocolHandler

        handler = ProtocolHandler(tool_registry=ToolRegistry())
        frame = {"jsonrpc": "2.0", "method": method, "id": 7, "params": params}
        return handler.handle_http_request(
            body=json.dumps(frame).encode(), headers={"HTTP_X_API_KEY": api_key}
        )

    def test_attack_surfaces_as_permission_denied(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        response = self._handle(
            "requirement.update",
            {
                "workspace_id": str(e2e_workspace.id),
                "id": str(foreign_requirement.id),
                "data": {"title": "W13c wire bypass"},
            },
            fenced_key,
        )

        assert response["error"]["code"] == -32001  # Permission denied
        assert SCOPE_MESSAGE_FRAGMENT in response["error"]["message"]


# ---------------------------------------------------------------------------
# #1373 — test.mark_reviewed is now in _TOOL_TARGETS
# ---------------------------------------------------------------------------


class TestMarkReviewedWorkspaceScope:
    def test_foreign_test_case_is_denied_without_mutation(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        foreign_test_case: TestCase,
    ) -> None:
        with patch(
            "application.test_service.TestService.mark_reviewed"
        ) as handler:
            result = _dispatch(
                "test.mark_reviewed",
                {
                    # #1376 overlap: the undeclared workspace_id must not
                    # re-open the #1373 hole either.
                    "workspace_id": str(e2e_workspace.id),
                    "test_case_id": str(foreign_test_case.id),
                },
                fenced_key,
            )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        assert SCOPE_MESSAGE_FRAGMENT in result.message
        handler.assert_not_called()
        foreign_test_case.refresh_from_db()
        assert foreign_test_case.reviewed is False

    def test_own_test_case_is_allowed_for_a_fenced_key(
        self,
        fenced_key: str,
        home_test_case: TestCase,
    ) -> None:
        result = _dispatch(
            "test.mark_reviewed",
            {"test_case_id": str(home_test_case.id)},
            fenced_key,
        )

        assert result.success is True, result.message
        home_test_case.refresh_from_db()
        assert home_test_case.reviewed is True

    def test_unfenced_editor_cannot_mark_a_foreign_test_case(
        self,
        e2e_userrole_member,
        e2e_api_key_member: str,
        foreign_test_case: TestCase,
    ) -> None:
        """#1373 (a): the unfenced cross-workspace write is closed too."""
        result = _dispatch(
            "test.mark_reviewed",
            {"test_case_id": str(foreign_test_case.id)},
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        foreign_test_case.refresh_from_db()
        assert foreign_test_case.reviewed is False

    def test_unfenced_editor_can_still_mark_own_test_case(
        self,
        e2e_userrole_member,
        e2e_api_key_member: str,
        home_test_case: TestCase,
    ) -> None:
        """Unchanged behaviour inside the caller's own workspace."""
        result = _dispatch(
            "test.mark_reviewed",
            {"test_case_id": str(home_test_case.id)},
            e2e_api_key_member,
        )

        assert result.success is True, result.message
        home_test_case.refresh_from_db()
        assert home_test_case.reviewed is True


# ---------------------------------------------------------------------------
# REGRESSION — schema-declared workspace_id keeps working as before
# ---------------------------------------------------------------------------


class TestDeclaredWorkspaceIdUnchanged:
    def test_declared_workspace_id_still_targets_that_workspace(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
        home_requirement: Requirement,
    ) -> None:
        """``requirement.query`` declares the parameter; role narrowing applies."""
        result = _dispatch(
            "requirement.query",
            {"workspace_id": str(e2e_workspace.id)},
            fenced_key,
        )

        assert result.success is True, result.message
        titles = {r["title"] for r in result.data["requirements"]}
        assert home_requirement.title in titles

    def test_normaliser_leaves_declared_params_alone(self) -> None:
        registry = ToolRegistry()
        registry._ensure_groups()
        params = {"workspace_id": str(uuid4())}

        assert registry._drop_undeclared_workspace_id("requirement.query", params) is params
        assert "workspace_id" in registry._drop_undeclared_workspace_id(
            "requirement.query", params
        )

    def test_delegated_workspace_tool_keeps_its_published_param(self) -> None:
        """``workspace.get_context`` is routed to AdminToolGroup but published
        by the wrapped CrossCuttingToolGroup — the index must use the
        published schema, not the routed group's local ``_TOOL_SCHEMAS``.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        params = {"workspace_id": str(uuid4())}

        assert registry._drop_undeclared_workspace_id("workspace.get_context", params) is params

    def test_delegated_workspace_tool_still_reads_the_named_workspace(
        self,
        fenced_key: str,
        e2e_workspace: Workspace,
    ) -> None:
        result = _dispatch(
            "workspace.get_context",
            {"workspace_id": str(e2e_workspace.id)},
            fenced_key,
        )

        assert result.success is True, result.message
        # Workspace-specific sections only exist when the parameter was kept.
        assert "preset" in result.data["workspace_context"]

    def test_every_target_tool_strips_an_undeclared_workspace_id(self) -> None:
        """Structural ratchet for the whole ``_TOOL_TARGETS`` surface.

        If a target tool ever *declared* ``workspace_id``, Case 1 would win and
        its object-derived entry would never run — so every entry must strip.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        params = {"workspace_id": str(uuid4()), "id": str(uuid4())}

        undeclared = [
            name
            for name in sorted(_TOOL_TARGETS)
            if "workspace_id"
            in registry._drop_undeclared_workspace_id(name, dict(params))
        ]
        assert not undeclared, (
            "_TOOL_TARGETS tools must not declare workspace_id (Case 1 would "
            f"pre-empt target resolution): {undeclared}"
        )

    def test_every_production_group_has_an_inspectable_schema(self) -> None:
        """The schema-declaration check is only fail-closed on BaseToolGroups.

        Every group registered by ``_ensure_groups`` is a ``BaseToolGroup``;
        the ``None`` fallback in ``_published_schema_param_names`` exists
        solely for unit-test doubles.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        assert registry._router is not None
        groups = registry._router._groups
        for prefix, group in groups.items():
            assert isinstance(group, BaseToolGroup), prefix

    def test_no_group_has_shadow_tools(self) -> None:
        """Every executable tool must also be published in the group's schemas.

        ``_drop_undeclared_workspace_id`` keeps the parameter when
        ``_published_schema_param_names`` cannot find the tool (``None``).
        That legacy branch is safe in production only because a routable tool
        is necessarily published: a "shadow" tool — present in ``_TOOL_MAP``
        but absent from ``get_tool_schemas()`` — would silently lose the
        #1376 protection (its undeclared ``workspace_id`` would never be
        stripped). Together with the ``BaseToolGroup`` ratchet above, this
        closes that dependency.
        """
        registry = ToolRegistry()
        registry._ensure_groups()
        assert registry._router is not None

        checked = 0
        shadows: list[tuple[str, str]] = []
        seen_group_ids: set[int] = set()
        for prefix, group in registry._router._groups.items():
            if id(group) in seen_group_ids:
                continue
            seen_group_ids.add(id(group))
            if not isinstance(group, BaseToolGroup):  # test double
                continue
            checked += 1
            published = {
                schema.get("name") for schema in group.get_tool_schemas()
            }
            for tool_name in sorted(set(group._TOOL_MAP) - published):
                shadows.append((prefix, tool_name))

        assert checked, "no BaseToolGroup instances were checked"
        assert not shadows, (
            "Groups expose executable-but-unpublished ('shadow') tools: "
            f"{shadows}. Publish a schema for each tool or drop the handler — "
            "otherwise the undeclared-workspace_id guard cannot see the tool."
        )
