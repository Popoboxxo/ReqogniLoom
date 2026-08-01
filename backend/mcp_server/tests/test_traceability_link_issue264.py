"""Real-DB regression tests for GitHub issue #264 (KRITISCH).

leaf_id : COMP-MC-006
req_id  : REQ-L2-MC-004, REQ-L2-AS-010

``traceability.create_link`` had three defects:

  Befund A  ``verifies`` Requirement -> TestCase and ``derives-from``
            Requirement -> StakeholderNeed answered 404 "Entity ... not
            found", although the entities existed and were reachable via
            ``GET /testcases/{id}`` / ``GET /needs/{id}``. TestCase and
            StakeholderNeed were simply absent from the generic entity ->
            Artifact resolution chain.
  Befund B  A reported success could not be confirmed through any read path:
            ``traceability.query`` was queried with the *business-entity* id
            while links are keyed by *Artifact* id, and
            ``GET /api/v1/tracelinks/?workspace_id=`` returned a hardcoded
            empty page. Both looked like silent data loss.
  Befund C  Creating a link that closes a cycle raised CycleDetectedError,
            which no layer mapped, producing ``-32603`` / HTTP 500.

Every test here asserts against the database, not just the response code.
"""
from __future__ import annotations

import uuid

import pytest

from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from traceability.types import LinkType
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_workspace_ctx():
    """Tenant + User + Workspace + editor AuthContext.

    ``goals_enabled`` is on because two of the #264 findings involve Goals as
    link endpoints (GoalService.create_version refuses otherwise).
    """
    from persistence.models import Tenant, User, Workspace

    name = "issue264"
    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{name}-ws", goals_enabled=True
        )
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
def auth_ctx(tenant_workspace_ctx):
    _, _, ctx = tenant_workspace_ctx
    return ctx


def _ensure_workflow(tenant, workspace, item_type: str) -> None:
    TenantContext.set_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type=item_type,
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def requirement(tenant_workspace_ctx):
    from application.requirement_service import RequirementService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "Requirement")
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title="Req under test", ctx=ctx
    )


@pytest.fixture
def test_case(tenant_workspace_ctx):
    from application.test_service import TestService

    tenant, workspace, ctx = tenant_workspace_ctx
    _ensure_workflow(tenant, workspace, "TestCase")
    return TestService().create_test_case(
        workspace_id=workspace.id, title="TC under test", ctx=ctx
    )


@pytest.fixture
def stakeholder_need(tenant_workspace_ctx):
    from application.stakeholder_need_service import StakeholderNeedService

    _tenant, workspace, ctx = tenant_workspace_ctx
    return StakeholderNeedService().create(
        ctx=ctx, workspace_id=workspace.id, title="Need under test"
    )


def _make_goal(workspace, ctx, title: str):
    """Create a Goal version and return the ORM row (create_version -> dict)."""
    from application.goal_service import GoalService
    from application.models import Goal

    created = GoalService().create_version(
        workspace_id=workspace.id, title=title, ctx=ctx
    )
    return Goal.objects.get(id=created["id"])


def _group():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    return CrossCuttingToolGroup()


def _create_link(source_id, target_id, link_type, ctx):
    return _group().execute_tool(
        "traceability.create_link",
        params={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "link_type": link_type,
        },
        auth_context=ctx,
        api_key="x",
    )


def _query(entity_id, direction, ctx):
    return _group().execute_tool(
        "traceability.query",
        params={"artifact_id": str(entity_id), "direction": direction},
        auth_context=ctx,
        api_key="x",
    )


def _stored_links(tenant_id):
    """Read the TraceLink table directly — the ground truth."""
    from persistence.models import TraceLink

    TenantContext.set_tenant(tenant_id)
    try:
        return list(TraceLink.objects.all())
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Befund A — TestCase / StakeholderNeed endpoints
# ---------------------------------------------------------------------------


def test_verifies_requirement_to_test_case_persists(
    tenant_workspace_ctx, requirement, test_case
):
    """#264 Befund A: ``verifies`` Requirement -> TestCase must persist.

    Previously NOT_FOUND, because TestCase was missing from the entity
    resolution chain. Asserted against the table, not the response code.
    """
    tenant, _workspace, ctx = tenant_workspace_ctx

    result = _create_link(
        requirement.id, test_case.id, LinkType.VERIFIES.value, ctx
    )

    assert result.success is True, result.message
    stored = _stored_links(tenant.id)
    assert len(stored) == 1
    link = stored[0]
    assert str(link.source_id) == str(requirement.artifact_id)
    assert str(link.target_id) == str(test_case.artifact_id)
    assert link.link_type == LinkType.VERIFIES.value
    # The response must name the row that actually exists.
    assert result.data["trace_link"]["id"] == str(link.id)


def test_derives_from_requirement_to_need_persists(
    tenant_workspace_ctx, requirement, stakeholder_need
):
    """#264 Befund A: ``derives-from`` Requirement -> StakeholderNeed persists.

    The 404 error message itself listed "Requirement->StakeholderNeed" as an
    allowed combination, so the rejection came from the lookup, not the rules.
    """
    tenant, _workspace, ctx = tenant_workspace_ctx

    result = _create_link(
        requirement.id, stakeholder_need.id, LinkType.DERIVES_FROM.value, ctx
    )

    assert result.success is True, result.message
    stored = _stored_links(tenant.id)
    assert len(stored) == 1
    assert str(stored[0].source_id) == str(requirement.artifact_id)
    assert str(stored[0].target_id) == str(stakeholder_need.artifact_id)


def test_resolver_accepts_test_case_and_need_ids(
    test_case, stakeholder_need, auth_ctx
):
    """The service seam resolves both entity types to their Artifact id."""
    from application.trace_link_service import TraceLinkService

    svc = TraceLinkService()
    assert svc.resolve_entity_to_artifact_id(
        test_case.id, ctx=auth_ctx
    ) == test_case.artifact_id
    assert svc.resolve_entity_to_artifact_id(
        stakeholder_need.id, ctx=auth_ctx
    ) == stakeholder_need.artifact_id


def test_unknown_entity_id_still_reports_not_found(auth_ctx, requirement):
    """A genuinely unknown id must stay NOT_FOUND, not become a phantom link."""
    result = _create_link(
        requirement.id, uuid.uuid4(), LinkType.TRACES.value, auth_ctx
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Befund B — a reported success must be readable back
# ---------------------------------------------------------------------------


def test_created_link_is_found_by_traceability_query(
    tenant_workspace_ctx, requirement, test_case
):
    """#264 Befund B: query with the same id that was passed to create_link.

    This is the regression that made a persisted link look lost: create_link
    resolves business-entity ids to Artifact ids, traceability.query did not,
    so querying with the Requirement id returned ``count: 0``.
    """
    _tenant, _workspace, ctx = tenant_workspace_ctx

    create = _create_link(
        requirement.id, test_case.id, LinkType.VERIFIES.value, ctx
    )
    assert create.success is True, create.message

    query = _query(requirement.id, "downstream", ctx)

    assert query.success is True, query.message
    assert query.data["count"] == 1
    link = query.data["links"][0]
    assert link["id"] == create.data["trace_link"]["id"]
    assert link["source_id"] == str(requirement.artifact_id)
    assert link["target_id"] == str(test_case.artifact_id)
    assert link["link_type"] == LinkType.VERIFIES.value


def test_query_returns_populated_endpoints_not_none(
    tenant_workspace_ctx, requirement, test_case
):
    """Every returned link must carry real ids.

    The old handler read ``source_id``/``target_id``/``id`` off NeighborResult
    projections, which have none of those attributes, so all three were
    silently ``None`` on every result.
    """
    _tenant, _workspace, ctx = tenant_workspace_ctx
    _create_link(requirement.id, test_case.id, LinkType.VERIFIES.value, ctx)

    query = _query(test_case.id, "upstream", ctx)

    assert query.success is True, query.message
    assert query.data["count"] == 1
    link = query.data["links"][0]
    assert link["id"] is not None
    assert link["source_id"] is not None
    assert link["target_id"] is not None


def test_query_unknown_artifact_id_returns_not_found(auth_ctx):
    """An unresolvable id is NOT_FOUND — not an empty, reassuring result."""
    query = _query(uuid.uuid4(), "both", auth_ctx)

    assert query.success is False
    assert query.error_code == "NOT_FOUND"


def test_goal_as_source_link_is_persisted_and_readable(
    tenant_workspace_ctx, requirement
):
    """#264 Befund B verbatim: ``traces`` Goal -> Requirement.

    Reported 200 with a trace_link.id while every read path said count 0.
    The link was in fact written; both read paths were broken.
    """
    tenant, workspace, ctx = tenant_workspace_ctx
    goal = _make_goal(workspace, ctx, "Goal A")

    result = _create_link(goal.id, requirement.id, LinkType.TRACES.value, ctx)
    assert result.success is True, result.message

    stored = _stored_links(tenant.id)
    assert len(stored) == 1
    assert str(stored[0].source_id) == str(goal.artifact_id)
    assert str(stored[0].target_id) == str(requirement.artifact_id)

    query = _query(requirement.id, "upstream", ctx)
    assert query.success is True, query.message
    assert query.data["count"] == 1
    assert query.data["links"][0]["id"] == str(stored[0].id)


def test_workspace_level_tracelink_listing_is_not_empty(
    tenant_workspace_ctx, requirement, test_case
):
    """``GET /tracelinks/?workspace_id=`` must report the links it holds.

    It used to return a hardcoded empty page, so it could never confirm a
    write — the second read path that made #264 look like data loss.
    """
    from application.trace_link_service import TraceLinkService

    _tenant, workspace, ctx = tenant_workspace_ctx
    _create_link(requirement.id, test_case.id, LinkType.VERIFIES.value, ctx)

    links = TraceLinkService().list_links_for_workspace(
        workspace_id=workspace.id, ctx=ctx
    )

    assert len(links) == 1
    assert str(links[0].source_id) == str(requirement.artifact_id)


# ---------------------------------------------------------------------------
# Befund C — never a 500
# ---------------------------------------------------------------------------


def test_goal_as_target_after_reverse_link_returns_validation_error(
    tenant_workspace_ctx, requirement
):
    """#264 Befund C: Goal as link TARGET must never yield an internal error.

    The reporter created ``traces`` Goal -> Requirement first (Befund B), then
    ``traces`` Requirement -> Goal. The second call closes a cycle in the
    ``traces`` graph; CycleDetectedError was unmapped and became HTTP 500.
    Expected per the issue: a clean 400 with a readable reason.
    """
    _tenant, workspace, ctx = tenant_workspace_ctx
    goal = _make_goal(workspace, ctx, "Goal B")

    forward = _create_link(goal.id, requirement.id, LinkType.TRACES.value, ctx)
    assert forward.success is True, forward.message

    backward = _create_link(requirement.id, goal.id, LinkType.TRACES.value, ctx)

    assert backward.success is False
    assert backward.error_code == "VALIDATION_ERROR"
    assert "cycle" in (backward.message or "").lower()


def test_goal_as_target_without_cycle_persists(tenant_workspace_ctx, requirement):
    """A Goal is a legitimate link target when no cycle is involved.

    Guards against "fixing" Befund C by rejecting Goal targets wholesale.
    """
    tenant, workspace, ctx = tenant_workspace_ctx
    goal = _make_goal(workspace, ctx, "Goal C")

    result = _create_link(requirement.id, goal.id, LinkType.TRACES.value, ctx)

    assert result.success is True, result.message
    stored = _stored_links(tenant.id)
    assert len(stored) == 1
    assert str(stored[0].target_id) == str(goal.artifact_id)


def test_duplicate_link_returns_validation_error_not_500(
    tenant_workspace_ctx, requirement, test_case
):
    """The uq_tracelink_edge violation is a client error (400), not a 500."""
    _tenant, _workspace, ctx = tenant_workspace_ctx

    first = _create_link(
        requirement.id, test_case.id, LinkType.VERIFIES.value, ctx
    )
    assert first.success is True, first.message

    second = _create_link(
        requirement.id, test_case.id, LinkType.VERIFIES.value, ctx
    )

    assert second.success is False
    assert second.error_code == "VALIDATION_ERROR"
