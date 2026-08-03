"""
Tests for TraceabilityViewSet.resolve (Task 3.2a, UI-Konzept Vollrollout).

GET /api/v1/traceability/resolve/?artifact_ids=<uuid>[,<uuid>...]

Resolves Artifact.id -> (entity_type, entity_id) for every Generic Artifact
Model type that carries a backing Artifact: Requirement, ArchitectureElement,
StakeholderNeed, TestCase, Adr, Risk, Issue, Goal, MainGoal.

Uses DRF APIRequestFactory with a real AuthContext attached to the request and
real DB fixtures (django_db) — no service mocking — mirroring the pattern
used by rest_api/tests/test_goal_views.py (there is no ``auth_client_factory``
fixture in this codebase, verified against rest_api/tests/conftest.py).

Security focus (REQ-L2-TE-011 / project history of RBAC/tenant-scoping
defects): test_resolve_does_not_leak_cross_tenant_artifact is the load-bearing
test here — it asserts a foreign-tenant artifact_id resolves as
``resolved: false``, never leaking entity_type/entity_id across the tenant
boundary, and never raising (a mixed batch must stay a 200).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.views import TraceabilityViewSet

pytestmark = pytest.mark.django_db


def _make_auth_context(*, tenant_id, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _new_tenant_and_workspace(tenant_name: str, **workspace_kwargs):
    """Create a Tenant + Workspace under an active TenantContext.

    persistence.tenancy.TenantScopedModel.objects.create() requires
    TenantContext.set_tenant() before any tenant-scoped query; mirrors
    rest_api/tests/test_goal_views.py's ``_new_tenant_and_workspace``.
    """
    slug = f"{tenant_name}-{uuid.uuid4().hex[:8]}".lower().replace(" ", "-")
    tenant = Tenant.objects.create(name=tenant_name, slug=slug)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, **workspace_kwargs)
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _make_artifact(tenant, workspace, artifact_type: str):
    from persistence.models import Artifact

    TenantContext.set_tenant(tenant.id)
    try:
        return Artifact.objects.create(workspace=workspace, artifact_type=artifact_type)
    finally:
        TenantContext.clear_tenant()


def _make_requirement(tenant, workspace):
    from persistence.models import Requirement

    artifact = _make_artifact(tenant, workspace, "Requirement")
    TenantContext.set_tenant(tenant.id)
    try:
        entity = Requirement.objects.create(artifact=artifact, title="Req A")
    finally:
        TenantContext.clear_tenant()
    return artifact, entity


def _make_architecture_element(tenant, workspace):
    from persistence.models import ArchitectureElement

    artifact = _make_artifact(tenant, workspace, "ArchitectureElement")
    TenantContext.set_tenant(tenant.id)
    try:
        entity = ArchitectureElement.objects.create(artifact=artifact, title="Arch A")
    finally:
        TenantContext.clear_tenant()
    return artifact, entity


def _make_stakeholder_need(tenant, workspace):
    from persistence.models import StakeholderNeed

    artifact = _make_artifact(tenant, workspace, "StakeholderNeed")
    TenantContext.set_tenant(tenant.id)
    try:
        entity = StakeholderNeed.objects.create(artifact=artifact, title="Need A")
    finally:
        TenantContext.clear_tenant()
    return artifact, entity


def _make_test_case(tenant, workspace):
    from persistence.models import TestCase

    artifact = _make_artifact(tenant, workspace, "TestCase")
    TenantContext.set_tenant(tenant.id)
    try:
        entity = TestCase.objects.create(artifact=artifact, title="Test A")
    finally:
        TenantContext.clear_tenant()
    return artifact, entity


def _make_adr(tenant, workspace):
    from application.models import Adr

    artifact = _make_artifact(tenant, workspace, "Adr")
    entity = Adr.objects.create(
        artifact=artifact,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        title="ADR A",
        description="desc",
    )
    return artifact, entity


def _make_risk(tenant, workspace):
    from application.models import Risk

    artifact = _make_artifact(tenant, workspace, "Risk")
    entity = Risk.objects.create(
        artifact=artifact,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        title="Risk A",
    )
    return artifact, entity


def _make_issue(tenant, workspace):
    from application.models import Issue

    artifact = _make_artifact(tenant, workspace, "Issue")
    entity = Issue.objects.create(
        artifact=artifact,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        title="Issue A",
    )
    return artifact, entity


def _make_goal(tenant, workspace):
    from application.models import Goal

    artifact = _make_artifact(tenant, workspace, "Goal")
    entity = Goal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        lineage_id=uuid.uuid4(),
        sequence_number=1,
        title="Goal A",
    )
    return artifact, entity


def _make_main_goal(tenant, workspace):
    from application.models import MainGoal

    artifact = _make_artifact(tenant, workspace, "MainGoal")
    entity = MainGoal.objects.create(
        artifact=artifact,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        sequence_number=1,
        content="Main goal content",
        source="manual",
    )
    return artifact, entity


ALL_TYPE_FACTORIES = {
    "Requirement": _make_requirement,
    "ArchitectureElement": _make_architecture_element,
    "StakeholderNeed": _make_stakeholder_need,
    "TestCase": _make_test_case,
    "Adr": _make_adr,
    "Risk": _make_risk,
    "Issue": _make_issue,
    "Goal": _make_goal,
    "MainGoal": _make_main_goal,
}


def _resolve(ctx, artifact_ids):
    factory = APIRequestFactory()
    ids_param = ",".join(str(a) for a in artifact_ids)
    req = factory.get(f"/api/v1/traceability/resolve/?artifact_ids={ids_param}")
    req.auth_context = ctx
    return TraceabilityViewSet.as_view({"get": "resolve"})(req)


def test_resolve_all_nine_artifact_types_returns_correct_entity():
    tenant, workspace = _new_tenant_and_workspace("T-resolve-all", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    expected: dict[str, tuple[str, str]] = {}
    artifact_ids = []
    for entity_type, factory_fn in ALL_TYPE_FACTORIES.items():
        artifact, entity = factory_fn(tenant, workspace)
        artifact_ids.append(artifact.id)
        expected[str(artifact.id)] = (entity_type, str(entity.id))

    resp = _resolve(ctx, artifact_ids)

    assert resp.status_code == 200
    assert len(resp.data) == len(ALL_TYPE_FACTORIES)
    for row in resp.data:
        aid = str(row["artifact_id"])
        exp_type, exp_entity_id = expected[aid]
        assert row["resolved"] is True, row
        assert row["entity_type"] == exp_type
        assert str(row["entity_id"]) == exp_entity_id


def test_resolve_nonexistent_artifact_id_is_not_an_error():
    tenant, workspace = _new_tenant_and_workspace("T-resolve-404", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    missing_id = uuid.uuid4()
    resp = _resolve(ctx, [missing_id])

    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["artifact_id"] == str(missing_id)
    assert resp.data[0]["resolved"] is False
    assert resp.data[0]["entity_type"] is None
    assert resp.data[0]["entity_id"] is None


def test_resolve_artifact_without_backing_domain_row_is_not_an_error():
    """An Artifact row can exist with no (or a deleted) domain entity."""
    tenant, workspace = _new_tenant_and_workspace("T-resolve-orphan", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    artifact = _make_artifact(tenant, workspace, "Requirement")  # no Requirement row created

    resp = _resolve(ctx, [artifact.id])

    assert resp.status_code == 200
    assert resp.data[0]["resolved"] is False


def test_resolve_does_not_leak_cross_tenant_artifact():
    """Load-bearing tenant-isolation test (project history: RBAC/tenant gaps).

    Tenant B must NEVER be able to resolve Tenant A's artifact_id — not to its
    entity_type/entity_id, and not even to a distinguishable error. It must
    come back exactly like an unknown id: resolved=False, both fields null.
    """
    tenant_a, workspace_a = _new_tenant_and_workspace("T-A-leak", name="WA")
    tenant_b, workspace_b = _new_tenant_and_workspace("T-B-leak", name="WB")

    artifact_a, requirement_a = _make_requirement(tenant_a, workspace_a)

    ctx_b = _make_auth_context(tenant_id=tenant_b.id)
    resp = _resolve(ctx_b, [artifact_a.id])

    assert resp.status_code == 200
    row = resp.data[0]
    assert row["artifact_id"] == str(artifact_a.id)
    assert row["resolved"] is False
    assert row["entity_type"] is None
    assert row["entity_id"] is None

    # Sanity: the SAME id resolves for its own tenant, proving the negative
    # result above is a tenant-isolation effect, not a fixture bug.
    ctx_a = _make_auth_context(tenant_id=tenant_a.id)
    own_resp = _resolve(ctx_a, [artifact_a.id])
    assert own_resp.status_code == 200
    assert own_resp.data[0]["resolved"] is True
    assert own_resp.data[0]["entity_type"] == "Requirement"
    assert str(own_resp.data[0]["entity_id"]) == str(requirement_a.id)


def test_resolve_does_not_leak_cross_tenant_adr():
    """Same isolation guarantee for an application-layer (non-tenant-scoped
    model) type — Adr, Risk, Issue, Goal, MainGoal all skip TenantScopedModel
    and carry their own tenant_id column, so their isolation depends entirely
    on the Artifact-side filter in resolve_artifacts(); this is the type most
    likely to regress if that assumption is ever weakened.
    """
    tenant_a, workspace_a = _new_tenant_and_workspace("T-A-adr-leak", name="WA")
    tenant_b, workspace_b = _new_tenant_and_workspace("T-B-adr-leak", name="WB")

    artifact_a, adr_a = _make_adr(tenant_a, workspace_a)

    ctx_b = _make_auth_context(tenant_id=tenant_b.id)
    resp = _resolve(ctx_b, [artifact_a.id])

    assert resp.status_code == 200
    assert resp.data[0]["resolved"] is False
    assert resp.data[0]["entity_type"] is None
    assert resp.data[0]["entity_id"] is None

    # Sanity: the SAME id resolves for its own tenant, proving the negative
    # result above is a tenant-isolation effect, not a fixture bug (mirrors
    # the Requirement sibling test).
    ctx_a = _make_auth_context(tenant_id=tenant_a.id)
    own_resp = _resolve(ctx_a, [artifact_a.id])
    assert own_resp.status_code == 200
    assert own_resp.data[0]["resolved"] is True
    assert own_resp.data[0]["entity_type"] == "Adr"
    assert str(own_resp.data[0]["entity_id"]) == str(adr_a.id)


def test_resolve_mixed_batch_returns_200_and_preserves_order():
    """A batch mixing resolvable / foreign-tenant / unknown ids must still be
    a single 200 — AC3: unresolvable entries stay visible-but-not-clickable,
    never a dead link AND never a failed request for the whole batch.
    """
    tenant_a, workspace_a = _new_tenant_and_workspace("T-A-mixed", name="WA")
    tenant_b, workspace_b = _new_tenant_and_workspace("T-B-mixed", name="WB")

    artifact_own, req_own = _make_requirement(tenant_a, workspace_a)
    artifact_foreign, _ = _make_requirement(tenant_b, workspace_b)
    unknown_id = uuid.uuid4()

    ctx_a = _make_auth_context(tenant_id=tenant_a.id)
    ordered_ids = [artifact_foreign.id, artifact_own.id, unknown_id]
    resp = _resolve(ctx_a, ordered_ids)

    assert resp.status_code == 200
    assert [row["artifact_id"] for row in resp.data] == [str(i) for i in ordered_ids]
    assert resp.data[0]["resolved"] is False  # foreign tenant
    assert resp.data[1]["resolved"] is True  # own tenant
    assert resp.data[1]["entity_type"] == "Requirement"
    assert resp.data[2]["resolved"] is False  # unknown


def test_resolve_requires_artifact_ids_param():
    tenant, _workspace = _new_tenant_and_workspace("T-resolve-missing-param", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    req = factory.get("/api/v1/traceability/resolve/")
    req.auth_context = ctx
    resp = TraceabilityViewSet.as_view({"get": "resolve"})(req)

    assert resp.status_code == 400


def test_resolve_rejects_malformed_uuid():
    tenant, _workspace = _new_tenant_and_workspace("T-resolve-bad-uuid", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    factory = APIRequestFactory()
    req = factory.get("/api/v1/traceability/resolve/?artifact_ids=not-a-uuid")
    req.auth_context = ctx
    resp = TraceabilityViewSet.as_view({"get": "resolve"})(req)

    assert resp.status_code == 400


def test_resolve_rejects_batch_over_limit():
    from traceability.service import RESOLVE_BATCH_LIMIT

    tenant, _workspace = _new_tenant_and_workspace("T-resolve-over-limit", name="W")
    ctx = _make_auth_context(tenant_id=tenant.id)

    too_many = [uuid.uuid4() for _ in range(RESOLVE_BATCH_LIMIT + 1)]
    resp = _resolve(ctx, too_many)

    assert resp.status_code == 400


def test_resolve_artifacts_service_truncates_oversized_batch_directly():
    """Task 3.2a hardening (review finding 1): resolve_artifacts() itself
    must cap its input, independent of the REST view's 400 check, since it is
    a Layer 1 export (__all__) any future non-REST caller (MCP tool, Celery
    task, another service) could call directly with an unbounded id list.

    Calls the service function directly (bypassing the view entirely) with
    RESOLVE_BATCH_LIMIT + 1 ids and asserts it degrades gracefully (silently
    truncates, like impact_analysis's own _clamp_depth/_clamp_limit) instead
    of building an unbounded IN clause across nine domain tables.
    """
    from traceability.service import RESOLVE_BATCH_LIMIT, resolve_artifacts

    tenant, workspace = _new_tenant_and_workspace("T-resolve-svc-cap", name="W")

    artifact, requirement = _make_requirement(tenant, workspace)
    padding = [uuid.uuid4() for _ in range(RESOLVE_BATCH_LIMIT)]
    oversized = [artifact.id] + padding  # RESOLVE_BATCH_LIMIT + 1 entries

    TenantContext.set_tenant(tenant.id)
    try:
        results = resolve_artifacts(oversized, tenant_id=tenant.id)
    finally:
        TenantContext.clear_tenant()

    assert len(results) == RESOLVE_BATCH_LIMIT
    # The truncation keeps the head of the input, so the one resolvable id
    # (placed first) must still resolve correctly.
    first = results[0]
    assert str(first.artifact_id) == str(artifact.id)
    assert first.resolved is True
    assert first.entity_type == "Requirement"
    assert str(first.entity_id) == str(requirement.id)


def test_resolve_artifacts_service_applies_explicit_tenant_filter_for_adr():
    """Task 3.2a hardening (review finding 2): resolve_artifacts()'s explicit
    tenant_id filter for the five non-TenantScopedModel types (Adr and
    friends) must actually be load-bearing, not dead/unused. Regression guard
    for the specific `.filter(tenant_id=...)` line — calls the service
    directly with the WRONG tenant_id for a verified artifact_id (simulating
    what would happen if a future caller mixed up Artifact-side verification
    with a mismatched tenant_id argument) and asserts the row does not
    resolve.
    """
    from traceability.service import resolve_artifacts

    tenant_a, workspace_a = _new_tenant_and_workspace("T-A-svc-adr-filter", name="WA")
    tenant_b, _workspace_b = _new_tenant_and_workspace("T-B-svc-adr-filter", name="WB")

    artifact_a, adr_a = _make_adr(tenant_a, workspace_a)

    # Correct tenant_id -> resolves.
    TenantContext.set_tenant(tenant_a.id)
    try:
        own = resolve_artifacts([artifact_a.id], tenant_id=tenant_a.id)
    finally:
        TenantContext.clear_tenant()
    assert own[0].resolved is True
    assert own[0].entity_type == "Adr"
    assert str(own[0].entity_id) == str(adr_a.id)

    # Correct TenantContext (so the Artifact-side check still passes) but a
    # mismatched tenant_id argument -> the explicit Adr-side filter must
    # reject it even though the single-point Artifact check alone would not.
    TenantContext.set_tenant(tenant_a.id)
    try:
        mismatched = resolve_artifacts([artifact_a.id], tenant_id=tenant_b.id)
    finally:
        TenantContext.clear_tenant()
    assert mismatched[0].resolved is False
    assert mismatched[0].entity_type is None
    assert mismatched[0].entity_id is None
