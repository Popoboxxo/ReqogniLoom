"""Workspace scoping of the MCP dispatch RBAC gate.

Regression tests for Systemaudit 2026-08-29
(``docs/SYSTEMAUDIT_2026-08-29_GESAMTTEST_MCP.md`` §6.5):

    "requirement.query with workspace_id = a foreign workspace B (same tenant,
    NO role assignment for the test user there) returns 200 OK with the real
    requirement data from workspace B."

and for the mirror-image write hole that mapping the surface turned up: 71 of
106 write tools take no ``workspace_id`` at all, so their RBAC gate ran against
the caller's tenant-wide role union — an Editor in workspace A could
``requirement.update`` an object living in workspace B.

The tests drive the real :class:`~mcp_server.tool_registry.ToolRegistry`
against real database rows on purpose. A mocked ``AuthorizationService``
returns a truthy ``MagicMock`` from ``decide_access``, which makes *every* gate
pass and would have kept this file green against the unfixed code.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple
from uuid import UUID, uuid4

import pytest

from auth_tenancy.models import UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace
from presets.models import WorkspacePresetConfig

from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import (
    TENANT_SCOPED_READ_TOOLS,
    resolve_target_workspace_id,
)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_workspace(tenant: Tenant, name: str, preset: Dict[str, Any]) -> Workspace:
    """Create an extended-preset workspace in *tenant*."""
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
    """Create a Requirement (plus its backing Artifact) in *workspace*."""
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
            description="seeded by test_mcp_workspace_scope",
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def foreign_workspace(
    e2e_tenant: Tenant, e2e_preset: Dict[str, Any]
) -> Workspace:
    """Workspace B — same tenant, no role assignment for any e2e user."""
    return _make_workspace(e2e_tenant, "Foreign Workspace B", e2e_preset)


@pytest.fixture
def foreign_requirement(foreign_workspace: Workspace) -> Requirement:
    """A requirement that only exists in workspace B."""
    return _make_requirement(foreign_workspace, "Secret req in workspace B")


@pytest.fixture
def home_requirement(
    e2e_workspace: Workspace, e2e_userrole_member: UserRole
) -> Requirement:
    """A requirement in workspace A, where the member holds Editor."""
    return _make_requirement(e2e_workspace, "Req in workspace A")


def _dispatch(tool_name: str, params: Dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


# ---------------------------------------------------------------------------
# READ path — the finding itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReadToolsAreWorkspaceScoped:
    """A read tool must not serve a workspace the caller holds no role in."""

    def test_query_against_foreign_workspace_is_denied(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        foreign_workspace: Workspace,
        foreign_requirement: Requirement,
    ) -> None:
        """§6.5 verbatim: viewer in A, ``requirement.query`` against B."""
        result = _dispatch(
            "requirement.query",
            {"workspace_id": str(foreign_workspace.id)},
            e2e_api_key_viewer,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # Fail-closed, not "silently empty": the caller must be told, and the
        # foreign title must not appear anywhere in the envelope.
        assert foreign_requirement.title not in str(result.data or "")

    def test_query_against_own_workspace_still_works(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        e2e_workspace: Workspace,
    ) -> None:
        """The gate must not lock a Viewer out of their own workspace."""
        result = _dispatch(
            "requirement.query",
            {"workspace_id": str(e2e_workspace.id)},
            e2e_api_key_viewer,
        )

        assert result.success is True, result.message
        assert "requirements" in (result.data or {})

    def test_detail_read_by_id_in_foreign_workspace_is_denied(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        foreign_requirement: Requirement,
    ) -> None:
        """``requirement.get`` names no workspace — it must still be scoped.

        Without the object-level resolution this is the trivial bypass of the
        ``workspace_id``-based gate: omit the parameter, pass the id.
        """
        result = _dispatch(
            "requirement.get", {"id": str(foreign_requirement.id)}, e2e_api_key_viewer
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_detail_read_by_id_in_own_workspace_still_works(
        self,
        e2e_api_key_member: str,
        home_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.get", {"id": str(home_requirement.id)}, e2e_api_key_member
        )

        assert result.success is True, result.message
        assert result.data["requirement"]["title"] == home_requirement.title

    def test_unknown_id_is_not_denied_but_reported_as_not_found(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
    ) -> None:
        """Resolution is fail-soft: an unresolvable id keeps the old path.

        Turning "no such object" into PERMISSION_DENIED would leak the
        existence of ids and would break every not-found test in the suite.
        """
        result = _dispatch("requirement.get", {"id": str(uuid4())}, e2e_api_key_viewer)

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# WRITE path — the mirror-image hole
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWriteToolsWithoutWorkspaceParamAreScoped:
    """An Editor in A must not mutate an object living in B."""

    def test_update_of_foreign_object_is_denied(
        self,
        e2e_userrole_member: UserRole,
        e2e_api_key_member: str,
        foreign_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.update",
            {
                "id": str(foreign_requirement.id),
                "data": {"title": "hijacked", "change_reason": "test"},
            },
            e2e_api_key_member,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

        foreign_requirement.refresh_from_db()
        assert foreign_requirement.title == "Secret req in workspace B"

    def test_update_of_own_object_still_works(
        self,
        e2e_api_key_member: str,
        home_requirement: Requirement,
    ) -> None:
        result = _dispatch(
            "requirement.update",
            {
                "id": str(home_requirement.id),
                "data": {"title": "renamed by owner", "change_reason": "test"},
            },
            e2e_api_key_member,
        )

        assert result.success is True, result.message
        home_requirement.refresh_from_db()
        assert home_requirement.title == "renamed by owner"


# ---------------------------------------------------------------------------
# Reads with an OPTIONAL workspace_id — the second finding
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestOptionalWorkspaceIdReadsAreScoped:
    """Declaring ``workspace_id`` is not the same as enforcing it.

    These two tools accept the parameter and used to fall through to a
    tenant-wide read when it was omitted. The dispatcher gate cannot help
    there: no workspace is named and there is no target object to resolve, so
    the fix has to live in the handler.
    """

    def test_artifact_search_without_workspace_id_uses_accessible_scope(self) -> None:
        """The handler must ask for ``scope="tenant"``, not the unscoped path.

        Asserted at the seam rather than through the tsvector index: the point
        of the fix is *which scope is requested*, and pinning that is immune to
        whether the FTS column happens to be populated for a freshly inserted
        row.
        """
        from unittest.mock import MagicMock

        from auth_tenancy.context import AuthContext, AuthMethod
        from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

        search_service = MagicMock()
        search_service.search.return_value = MagicMock(
            results=[], total_count=0, page=1, limit=20, query=""
        )
        group = CrossCuttingToolGroup(search_service=search_service)
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=("viewer",),
            auth_method=AuthMethod.API_KEY,
        )

        group._handle_artifact_search(
            params={"query": "anything"}, auth_context=ctx, api_key="reqlo_x"
        )
        assert search_service.search.call_args.kwargs["scope"] == "tenant"

        # With an explicit workspace the dispatcher has already gated
        # membership, so the single-workspace path must stay untouched.
        workspace_id = uuid4()
        group._handle_artifact_search(
            params={"query": "anything", "workspace_id": str(workspace_id)},
            auth_context=ctx,
            api_key="reqlo_x",
        )
        kwargs = search_service.search.call_args.kwargs
        assert kwargs["scope"] == "workspace"
        assert kwargs["workspace_id"] == workspace_id

    def test_prompt_template_list_hides_foreign_workspace_templates(
        self,
        e2e_userrole_viewer: UserRole,
        e2e_api_key_viewer: str,
        e2e_workspace: Workspace,
        foreign_workspace: Workspace,
    ) -> None:
        """Tenant-wide + own-workspace rows only, never another workspace's."""
        from persistence.models import PromptTemplate

        set_request_tenant(e2e_tenant_id := e2e_workspace.tenant_id)
        try:
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=None,
                name="tenant_wide_slot",
                content="tenant default",
                version=1,
                is_active=True,
            )
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=e2e_workspace.id,
                name="own_slot",
                content="own override",
                version=1,
                is_active=True,
            )
            PromptTemplate.objects.create(
                tenant_id=e2e_tenant_id,
                workspace_id=foreign_workspace.id,
                name="foreign_slot",
                content="FOREIGN SECRET PROMPT",
                version=1,
                is_active=True,
            )
        finally:
            clear_request_tenant()

        result = _dispatch("prompt_template.list", {}, e2e_api_key_viewer)

        assert result.success is True, result.message
        names = {t["name"] for t in result.data["templates"]}
        assert "tenant_wide_slot" in names
        assert "own_slot" in names
        assert "foreign_slot" not in names
        assert "FOREIGN SECRET PROMPT" not in str(result.data)


# ---------------------------------------------------------------------------
# Resolver unit tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolveTargetWorkspaceId:
    def test_resolves_requirement_id_to_its_workspace(
        self, foreign_workspace: Workspace, foreign_requirement: Requirement
    ) -> None:
        set_request_tenant(foreign_workspace.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "requirement.get", {"id": str(foreign_requirement.id)}
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)

    def test_unregistered_tool_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("workspace.list", {"id": str(uuid4())}) is None

    def test_malformed_uuid_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("requirement.get", {"id": "not-a-uuid"}) is None

    def test_missing_param_resolves_to_none(self) -> None:
        assert resolve_target_workspace_id("requirement.get", {}) is None

    def test_first_resolvable_candidate_wins(
        self, foreign_workspace: Workspace, foreign_requirement: Requirement
    ) -> None:
        """``context.change_impact`` probes four entity types for one param."""
        set_request_tenant(foreign_workspace.tenant_id)
        try:
            resolved = resolve_target_workspace_id(
                "context.change_impact",
                {"entity_id": str(foreign_requirement.id), "entity_type": "Requirement"},
            )
        finally:
            clear_request_tenant()
        assert resolved == str(foreign_workspace.id)


# ---------------------------------------------------------------------------
# Coverage ratchet
# ---------------------------------------------------------------------------


def _live_tools() -> Dict[str, Dict[str, Any]]:
    """Every tool the live registry advertises, indexed by name."""
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    return {tool["name"]: tool for tool in build_manifest()["tools"]}


class TestWorkspaceScopeCoverage:
    """Every read tool must be *explicitly* classified.

    A new read tool that is none of (a) ``workspace_id``-**required**,
    (b) registered in ``_TOOL_TARGETS``, (c) listed in
    ``TOOL_ENFORCED_WORKSPACE_SCOPE``, (d) listed in
    ``TENANT_SCOPED_READ_TOOLS`` would ship unscoped and silently reintroduce
    the finding. This is the ratchet that stops that; the fix for a red run is
    a registry entry or a real scoping fix, never a change to the assertion.
    """

    def test_every_read_tool_is_classified(self) -> None:
        """A *declared* ``workspace_id`` is not scoping — it must be required.

        The first cut of this ratchet skipped any tool whose schema merely
        mentioned ``workspace_id``. That let ``artifact.search`` through while
        it was still passing ``workspace_id=None`` into
        ``SearchService.search(scope="workspace")`` — documented as "the whole
        tenant with no RBAC narrowing", i.e. a live instance of the very bug
        this file exists to prevent. Requiring the parameter to be *required*
        is what makes the skip mean "the dispatcher will always have a
        workspace to gate on".
        """
        from mcp_server.workspace_scope import (
            TOOL_ENFORCED_WORKSPACE_SCOPE,
            _TOOL_TARGETS,
        )

        unclassified = []
        for name, tool in _live_tools().items():
            if tool["is_write"]:
                continue
            schema = tool.get("inputSchema") or {}
            if "workspace_id" in (schema.get("required") or []):
                continue
            if (
                name in _TOOL_TARGETS
                or name in TOOL_ENFORCED_WORKSPACE_SCOPE
                or name in TENANT_SCOPED_READ_TOOLS
            ):
                continue
            unclassified.append(name)

        assert not unclassified, (
            "Read tools with no enforced workspace scoping: "
            f"{sorted(unclassified)}. Make workspace_id required, add a target "
            "to mcp_server.workspace_scope._TOOL_TARGETS, or list the tool in "
            "TOOL_ENFORCED_WORKSPACE_SCOPE / TENANT_SCOPED_READ_TOOLS with a "
            "documented reason. Do not relax this assertion."
        )

    def test_classification_sets_are_disjoint(self) -> None:
        """A tool in two buckets means two contradictory claims about it."""
        from mcp_server.workspace_scope import (
            TOOL_ENFORCED_WORKSPACE_SCOPE,
            _TOOL_TARGETS,
        )

        buckets = {
            "_TOOL_TARGETS": set(_TOOL_TARGETS),
            "TOOL_ENFORCED_WORKSPACE_SCOPE": set(TOOL_ENFORCED_WORKSPACE_SCOPE),
            "TENANT_SCOPED_READ_TOOLS": set(TENANT_SCOPED_READ_TOOLS),
        }
        names = sorted(buckets)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                overlap = buckets[left] & buckets[right]
                assert not overlap, f"{left} and {right} both claim {sorted(overlap)}"

    def test_tool_enforced_scope_tools_are_real_read_tools(self) -> None:
        from mcp_server.workspace_scope import TOOL_ENFORCED_WORKSPACE_SCOPE

        tools = _live_tools()
        for name in TOOL_ENFORCED_WORKSPACE_SCOPE:
            assert name in tools, f"{name} is not a live tool"
            assert not tools[name]["is_write"], f"{name} is a write tool"

    def test_registry_targets_reference_known_tools(self) -> None:
        """A typo'd tool name in the registry is dead weight — catch it."""
        from mcp_server.workspace_scope import _TOOL_TARGETS

        live = set(_live_tools())
        unknown = sorted(set(_TOOL_TARGETS) - live)
        assert not unknown, f"_TOOL_TARGETS names non-existent tools: {unknown}"

    def test_registry_targets_reference_declared_params(self) -> None:
        """A target param the tool never accepts can never resolve."""
        from mcp_server.workspace_scope import _TOOL_TARGETS

        tools = _live_tools()
        bad: list[Tuple[str, str]] = []
        for tool_name, targets in _TOOL_TARGETS.items():
            properties = (tools[tool_name].get("inputSchema") or {}).get(
                "properties"
            ) or {}
            for param_name, _entity_key in targets:
                if param_name not in properties:
                    bad.append((tool_name, param_name))
        assert not bad, f"_TOOL_TARGETS names undeclared params: {sorted(bad)}"

    def test_every_entity_key_is_declared(self) -> None:
        from application.workspace_lookup import ENTITY_SPECS
        from mcp_server.workspace_scope import _TOOL_TARGETS

        used = {key for targets in _TOOL_TARGETS.values() for _p, key in targets}
        assert used <= set(ENTITY_SPECS), sorted(used - set(ENTITY_SPECS))

    def test_tenant_scoped_read_tools_are_real_read_tools(self) -> None:
        tools = _live_tools()
        for name in TENANT_SCOPED_READ_TOOLS:
            assert name in tools, f"{name} is not a live tool"
            assert not tools[name]["is_write"], f"{name} is a write tool"

    @pytest.mark.django_db
    def test_every_entity_spec_resolves_against_the_real_schema(
        self, e2e_tenant: Tenant
    ) -> None:
        """Every spec's model/field pair must be a valid ORM query.

        A renamed column would otherwise degrade silently to "unresolvable",
        i.e. back to the unscoped behaviour this module exists to remove —
        and, because resolution is fail-soft by design, nothing else would
        notice.
        """
        from application.workspace_lookup import ENTITY_SPECS, import_entity_model

        set_request_tenant(e2e_tenant.id)
        try:
            for key, spec in ENTITY_SPECS.items():
                model = import_entity_model(spec.model_path)
                manager = getattr(model, "unscoped", model.objects)
                # Executing the query is what validates both field paths; no
                # rows are needed for the ORM to reject an unknown column.
                assert (
                    list(
                        manager.filter(
                            **{spec.lookup_field: UUID(int=0)}
                        ).values_list(spec.workspace_field, flat=True)[:1]
                    )
                    == []
                ), key
        finally:
            clear_request_tenant()
