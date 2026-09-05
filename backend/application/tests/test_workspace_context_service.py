"""Service-level tests for the workspace-context read model (ADR-01, #124).

``workspace.get_context``'s aggregation was moved out of
``mcp_server/tools/cross_cutting.py`` into
``application.workspace_context_service``. The MCP tool group keeps its own
end-to-end coverage (``mcp_server/tests/test_cross_cutting_tool_group.py``);
these tests pin the *service* contract directly, so the seam stays covered even
if the MCP tool later stops being the only caller.

The emphasis is on the behaviours that are easy to break in a refactor and
would otherwise fail silently: the exact response keys, and the two different
"outdated" exclusion mechanisms (``status`` mirror vs. ``WorkflowItemState``).

req_id  : REQ-L2-MC-004
"""
from __future__ import annotations

import pytest

from application import workspace_context_service
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


def _make_tenant_workspace_ctx(name: str):
    """Create a Tenant + User + Workspace + AuthContext for *name*."""
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


@pytest.fixture
def workspace_ctx():
    return _make_tenant_workspace_ctx("wsctx-service")


@pytest.fixture
def workspace_with_requirements(workspace_ctx):
    """One approved, one draft and one outdated Requirement."""
    from application.requirement_service import RequirementService
    from mcp_server.tools.requirements import RequirementsToolGroup

    tenant, workspace, ctx = workspace_ctx
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()

    svc = RequirementService()
    svc.create_requirement(workspace_id=workspace.id, title="Draft one", ctx=ctx)
    doomed = svc.create_requirement(workspace_id=workspace.id, title="Doomed", ctx=ctx)

    group = RequirementsToolGroup(service=svc)
    result = group._handle_outdate(
        params={"id": str(doomed.id), "reason": "obsolete"},
        auth_context=ctx,
        api_key="x",
    )
    assert result.success is True

    return tenant, workspace, ctx, doomed


class TestCountOpenRequirements:
    """REQ-006: outdated requirements only count as open when asked for."""

    def test_excludes_outdated_by_default(self, workspace_with_requirements):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        # "Draft one" is open; "Doomed" is outdated and must not be counted.
        assert count == 1

    def test_includes_outdated_when_requested(self, workspace_with_requirements):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=True,
        )

        assert count == 2

    def test_empty_workspace_counts_zero(self, workspace_ctx):
        tenant, workspace, _ctx = workspace_ctx

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        assert count == 0


class TestCountOpenRequirementsPresetAware:
    """SYSTEMAUDIT SA-56: "open" must be resolved against the workspace's
    *actual* active workflow, not a hardcoded ``status != "approved"`` literal
    — otherwise Extended's post-approval V-model states ("implemented",
    "verified") are wrongly counted as open, and Minimal's "done" requirements
    (which never carry an "approved" status at all) are wrongly counted as
    open forever.
    """

    def _requirement_in_state(self, *, workspace, ctx, tenant, title, status):
        """Put *req* in *status* — datenmodell-konsolidierung Phase 1: counting
        now reads ``WorkflowItemState`` (via ``workflow.state_reader``), not
        the (now dropped, Task 12) ``status`` column, so the fixture only
        needs to move the engine state. Directly setting ``current_state``
        (rather than a real, preset-validated transition) keeps this fixture
        able to reach states — like "verified" from a freshly created
        "draft" item — that are not a single legal hop away.
        """
        from application.requirement_service import RequirementService
        from workflow.models import WorkflowItemState

        svc = RequirementService()
        req = svc.create_requirement(workspace_id=workspace.id, title=title, ctx=ctx)
        WorkflowItemState.unscoped.filter(
            tenant_id=tenant.id,
            item_id=req.id,
            item_type="Requirement",
            workspace_id=workspace.id,
        ).update(current_state=status)
        return req

    def test_extended_implemented_and_verified_are_not_open(self, workspace_ctx):
        """Requirements past the "approved" gate must not count as open —
        the pre-fix ``status != "approved"`` check wrongly counted them."""
        tenant, workspace, ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="extended",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
        finally:
            TenantContext.clear_tenant()

        self._requirement_in_state(
            workspace=workspace, ctx=ctx, tenant=tenant, title="draft", status="draft"
        )
        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="approved",
            status="approved",
        )
        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="implemented",
            status="implemented",
        )
        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="verified",
            status="verified",
        )

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        # Only "draft" is still open; approved/implemented/verified are all
        # past the approval gate.
        assert count == 1

    def test_minimal_done_is_not_open_despite_no_approved_state(self, workspace_ctx):
        """Minimal has no "approved" state at all — the pre-fix literal check
        would count "done" requirements as open forever."""
        tenant, workspace, ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="minimal",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
        finally:
            TenantContext.clear_tenant()

        self._requirement_in_state(
            workspace=workspace, ctx=ctx, tenant=tenant, title="draft", status="draft"
        )
        self._requirement_in_state(
            workspace=workspace, ctx=ctx, tenant=tenant, title="done", status="done"
        )

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        assert count == 1

    def test_standard_approved_is_not_open(self, workspace_ctx):
        """Standard's ``{"approved"}`` must be recognised as terminal-positive
        — the middle tier between Minimal ("done") and Extended
        ("implemented"/"verified")."""
        tenant, workspace, ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
        finally:
            TenantContext.clear_tenant()

        self._requirement_in_state(
            workspace=workspace, ctx=ctx, tenant=tenant, title="draft", status="draft"
        )
        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="approved",
            status="approved",
        )

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        # Only "draft" is still open; "approved" is Standard's terminal-positive state.
        assert count == 1

    def test_deprecated_status_still_counts_as_open(self, workspace_ctx):
        """``is_outdated_equivalent`` states (e.g. "deprecated") are a dead
        end, not a successful completion — they must keep counting as "open"
        (point 4 of the ``terminal_positive_states`` contract), not be folded
        into the terminal-positive set."""
        tenant, workspace, ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=tenant.id,
            )
        finally:
            TenantContext.clear_tenant()

        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="approved",
            status="approved",
        )
        self._requirement_in_state(
            workspace=workspace,
            ctx=ctx,
            tenant=tenant,
            title="deprecated",
            status="deprecated",
        )

        count = workspace_context_service.count_open_requirements(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        # "approved" is done; "deprecated" is a dead end, not a completion,
        # so it still counts as open.
        assert count == 1

    def test_terminal_positive_states_excludes_back_edge_rework_cycle(
        self, workspace_ctx
    ):
        """Regression for SYSTEMAUDIT AP-7 review MEDIUM-2: a workflow with a
        rework back-edge (ccb_approval-style ``under_review -> rejected`` then
        ``rejected -> draft``) must not have the forward-reachability walk
        from each approval-gate target swallow the entire graph just because
        one of the gate targets ("rejected") can cycle back to the start.

        Pre-fix, ``_reachable_from("rejected")`` walks the whole
        ``rejected -> draft -> submitted -> under_review -> approved ->
        implemented`` cycle and returns 5 of the preset's 6 states as
        "terminal positive" (everything except "rejected" itself, filtered
        only via the literal ``is_outdated_equivalent`` flag) — i.e.
        practically the entire graph, which would make ``count_open_*``
        wrongly report almost nothing as open for any workspace configured
        with this workflow.
        """
        from workflow.definition_store import PRESET_SCHEMAS
        from workflow.models import WorkflowEngineDefinition
        from workflow.services import terminal_positive_states

        tenant, workspace, _ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            WorkflowEngineDefinition.unscoped.create(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                item_type="Requirement",
                preset="ccb_approval",
                workflow_json=PRESET_SCHEMAS["ccb_approval"],
                is_custom=False,
            )
            # terminal_positive_states (unlike count_open_requirements) does
            # not set its own TenantContext — it must be called while the
            # tenant scope from the definition write above is still active.
            done_states = terminal_positive_states(workspace.id, "Requirement")
        finally:
            TenantContext.clear_tenant()

        # Only "approved" and "implemented" cannot cycle back to "draft"
        # (the initial_state) — they are the only genuine dead-end successes.
        # "draft"/"submitted"/"under_review"/"rejected" all sit on the
        # rejected -> draft rework cycle and must stay "open".
        assert done_states == frozenset({"approved", "implemented"})


class TestEntityCounts:
    def test_response_shape_is_stable(self, workspace_ctx):
        """The MCP contract depends on these exact keys — pin them."""
        tenant, workspace, _ctx = workspace_ctx

        counts = workspace_context_service.entity_counts(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        assert set(counts) == {"requirements", "architecture", "tests", "risks"}
        assert set(counts["requirements"]) == {"active", "outdated", "total"}
        assert set(counts["architecture"]) == {"active", "outdated", "total"}
        # Note "pass"/"fail", not "passed"/"failed" — these mirror the most
        # recent TestRunResult, not the TestCase lifecycle status.
        assert set(counts["tests"]) == {"active", "pass", "fail", "outdated"}
        assert set(counts["risks"]) == {"open", "mitigated", "accepted"}

    def test_outdated_is_reported_separately_from_active(
        self, workspace_with_requirements
    ):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        counts = workspace_context_service.entity_counts(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        assert counts["requirements"]["active"] == 1
        assert counts["requirements"]["outdated"] == 1
        assert counts["requirements"]["total"] == 2

    def test_include_outdated_does_not_change_counts(
        self, workspace_with_requirements
    ):
        """``include_outdated`` governs *lists*, never the counts (by design)."""
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        without = workspace_context_service.entity_counts(
            workspace_id=workspace.id, tenant_id=tenant.id, include_outdated=False
        )
        with_ = workspace_context_service.entity_counts(
            workspace_id=workspace.id, tenant_id=tenant.id, include_outdated=True
        )

        assert without == with_


class TestEntityLists:
    def test_response_shape_is_stable(self, workspace_ctx):
        tenant, workspace, _ctx = workspace_ctx

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        assert set(lists) == {
            "requirements_list",
            "architecture_list",
            "tests_list",
        }
        assert lists["requirements_list"] == []

    def test_outdated_requirement_hidden_by_default(
        self, workspace_with_requirements
    ):
        tenant, workspace, _ctx, doomed = workspace_with_requirements

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        ids = {str(r["id"]) for r in lists["requirements_list"]}
        assert str(doomed.id) not in ids
        assert len(ids) == 1

    def test_outdated_requirement_visible_when_requested(
        self, workspace_with_requirements
    ):
        tenant, workspace, _ctx, doomed = workspace_with_requirements

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=True,
        )

        ids = {str(r["id"]) for r in lists["requirements_list"]}
        assert str(doomed.id) in ids

    def test_requirement_entries_carry_the_documented_fields(
        self, workspace_with_requirements
    ):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            include_outdated=False,
        )

        entry = lists["requirements_list"][0]
        assert set(entry) == {"id", "title", "status", "level"}


class TestEntityListsJsonSerializable:
    """Issue #441: ``entity_lists()`` feeds ``workspace.get_context`` at
    ``depth in ("normal", "full")``, which is JSON-encoded verbatim by the
    MCP HTTP transport. ``.values("id", ...)`` returns raw ``UUID`` objects,
    which ``json.dumps`` cannot encode without a custom default — the
    resulting ``TypeError`` crashed the endpoint with an HTTP 500 for those
    two depths (``depth="summary"`` never calls ``entity_lists()`` and was
    unaffected). Every id-shaped field in the response must be a plain
    ``str``.
    """

    def test_requirement_id_is_a_string(self, workspace_with_requirements):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id, tenant_id=tenant.id, include_outdated=False
        )

        entry = lists["requirements_list"][0]
        assert isinstance(entry["id"], str)

    def test_architecture_id_is_a_string(self, workspace_ctx):
        from application.architecture_service import ArchitectureService

        tenant, workspace, ctx = workspace_ctx
        TenantContext.set_tenant(tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace.id,
                preset="standard",
                item_type="ArchitectureElement",
                tenant_id=tenant.id,
            )
        finally:
            TenantContext.clear_tenant()

        ArchitectureService().create_architecture_element(
            workspace_id=workspace.id,
            title="Some Element",
            element_type="component",
            ctx=ctx,
        )

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id, tenant_id=tenant.id, include_outdated=False
        )

        assert len(lists["architecture_list"]) == 1
        entry = lists["architecture_list"][0]
        assert isinstance(entry["id"], str)

    def test_full_payload_is_json_dumpable(self, workspace_with_requirements):
        """Direct regression for the reported TypeError."""
        import json

        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        lists = workspace_context_service.entity_lists(
            workspace_id=workspace.id, tenant_id=tenant.id, include_outdated=True
        )

        # Must not raise TypeError: Object of type UUID is not JSON serializable
        json.dumps(lists)


class TestRecentChanges:
    def test_empty_workspace_returns_empty_list(self, workspace_ctx):
        tenant, workspace, _ctx = workspace_ctx

        assert (
            workspace_context_service.recent_changes(
                workspace_id=workspace.id, tenant_id=tenant.id
            )
            == []
        )

    def test_outdate_transition_is_reported_with_a_resolved_title(
        self, workspace_with_requirements
    ):
        tenant, workspace, _ctx, doomed = workspace_with_requirements

        changes = workspace_context_service.recent_changes(
            workspace_id=workspace.id, tenant_id=tenant.id
        )

        assert changes, "the outdate() transition should be recorded"
        assert set(changes[0]) == {"entity_type", "title", "timestamp"}
        titles = {c["title"] for c in changes}
        # Title resolved via the bulk per-item_type lookup, not left as a UUID.
        assert "Doomed" in titles
        assert str(doomed.id) not in titles

    def test_limit_is_honoured(self, workspace_with_requirements):
        tenant, workspace, _ctx, _doomed = workspace_with_requirements

        changes = workspace_context_service.recent_changes(
            workspace_id=workspace.id, tenant_id=tenant.id, limit=1
        )

        assert len(changes) <= 1


class TestGetWorkspace:
    def test_returns_the_workspace(self, workspace_ctx):
        tenant, workspace, _ctx = workspace_ctx

        loaded = workspace_context_service.get_workspace(
            workspace_id=workspace.id, tenant_id=tenant.id
        )

        assert loaded is not None
        assert loaded.id == workspace.id

    def test_unknown_workspace_returns_none(self, workspace_ctx):
        import uuid

        tenant, _workspace, _ctx = workspace_ctx

        assert (
            workspace_context_service.get_workspace(
                workspace_id=uuid.uuid4(), tenant_id=tenant.id
            )
            is None
        )

    def test_does_not_leak_across_tenants(self, workspace_ctx):
        """The tenant-scoped manager must hide another tenant's workspace."""
        tenant_a, workspace_a, _ctx = workspace_ctx
        tenant_b, _workspace_b, _ctx_b = _make_tenant_workspace_ctx("wsctx-other")

        leaked = workspace_context_service.get_workspace(
            workspace_id=workspace_a.id, tenant_id=tenant_b.id
        )

        assert leaked is None
