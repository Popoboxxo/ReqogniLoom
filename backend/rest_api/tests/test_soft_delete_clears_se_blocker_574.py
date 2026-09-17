"""Soft-deleting an artifact must clear its SE-Auditor blockers (GH-574).

Reproduction from the issue, step for step:

    POST /api/v1/testcases/          -> 201 (no 'verifies' link)
    DELETE /api/v1/testcases/{id}/   -> 204
    GET  /api/v1/testcases/{id}/     -> 200, status="outdated"
    POST /api/v1/workspaces/{ws}/baselines/
                                     -> 400 SE_AUDITOR_BLOCKED, and the
                                        TRACE-P6 finding names the TestCase
                                        that was just deleted.

The workspace was left fail-closed by an artifact the user had already
removed, and the finding pointed at an id that no longer resolves in any
list view — a dangling blocker with no correction path other than the GH-513
override.

Root cause was in ``traceability.audit.rules.coverage_consistency``:
``_active_test_cases()`` returned every TestCase row, on the (by then stale)
assumption that TestCase is never soft-deleted. GH-443 routed
``TestService.delete_test_case`` through ``workflow.services.outdate()`` and
REQ-165/REQ-166 registered TestCase in
``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``, so a deleted TestCase
does carry ``status="outdated"`` — exactly what the sibling helpers
``_active_requirements()`` / ``_active_architecture_elements()`` already
excluded.

req_id : REQ-011 (audit/compliance), GH-574 (verschaerft GH-513)
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from rest_api.views import BaselineViewSet
# Aliased: pytest tries to collect any module-level name starting with "Test".
from rest_api.views import TestCaseViewSet as _TestCaseViewSet
from traceability.audit.registry import TRACE_P6


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    """The preset tier is cached process-wide; keep tests independent."""
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()


def _auth_context(user_id: uuid.UUID, tenant_id: uuid.UUID, *, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _extended_workspace_with_orphan_testcase():
    """An Extended workspace whose only blocker is one TRACE-P6 TestCase.

    Deliberately contains no Requirement at all: TRACE-P1/P2/P3 and VERIF-P8
    all key off Requirements, so the orphan TestCase is the single blocking
    finding and the assertions below cannot be satisfied by accident.
    """
    from application.workspace_provisioning import provision_workspace_defaults
    from persistence.models import Artifact, Tenant, TestCase, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="gh574-tenant",
        slug=f"gh574-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"gh574-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "extended"},
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"gh574-{uuid.uuid4().hex[:8]}",
            email="gh574@example.com",
        )
        # The DELETE below routes through workflow.services.outdate(), which
        # needs a WorkflowEngineDefinition for "TestCase" to exist.
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=tenant.id,
            requirement_preset="extended",
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="TestCase:Unit"
        )
        test_case = TestCase.objects.create(
            tenant=tenant,
            artifact=artifact,
            title="Orphan test case",
            description="created without a 'verifies' link, exactly as in GH-574",
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user, test_case


def _post_baseline(workspace, ctx, body):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = factory.post(
        f"/api/v1/workspaces/{workspace.id}/baselines/", data=body, format="json"
    )
    req.auth_context = ctx
    view = BaselineViewSet.as_view({"post": "create"})
    # A direct view() call bypasses persistence.middleware, which is what sets
    # the thread-local tenant in production.
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return view(req, workspace_pk=str(workspace.id))
    finally:
        TenantContext.clear_tenant()


def _delete_test_case(workspace, ctx, test_case_id):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = factory.delete(f"/api/v1/testcases/{test_case_id}/")
    req.auth_context = ctx
    view = _TestCaseViewSet.as_view({"delete": "destroy"})
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return view(req, pk=str(test_case_id))
    finally:
        TenantContext.clear_tenant()


def _get_test_case(workspace, ctx, test_case_id):
    from persistence.tenancy import TenantContext

    factory = APIRequestFactory()
    req = factory.get(f"/api/v1/testcases/{test_case_id}/")
    req.auth_context = ctx
    view = _TestCaseViewSet.as_view({"get": "retrieve"})
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return view(req, pk=str(test_case_id))
    finally:
        TenantContext.clear_tenant()


def _blocking_findings(workspace, ctx):
    from application.audit_service import AuditService
    from persistence.tenancy import TenantContext
    from traceability.audit import AuditScope

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        return AuditService().blocking_findings(
            workspace.id, ctx, scopes=[AuditScope(scope="project", artifact_id=None)]
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_live_orphan_testcase_still_blocks_the_baseline() -> None:
    """Control assertion: the fix must not disarm TRACE-P6 for live TestCases."""
    _, workspace, user, test_case = _extended_workspace_with_orphan_testcase()
    ctx = _auth_context(user.id, workspace.tenant_id)

    findings = _blocking_findings(workspace, ctx)
    p6 = [f for f in findings if f.rule_id == TRACE_P6]
    assert len(p6) == 1, f"expected exactly one TRACE-P6 finding, got {findings}"
    assert str(test_case.artifact_id) in p6[0].artifact_ids

    response = _post_baseline(workspace, ctx, {"scope": "project", "name": "gh574-pre"})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "SE_AUDITOR_BLOCKED"


@pytest.mark.django_db
def test_deleting_the_testcase_clears_its_trace_p6_blocker() -> None:
    """The exact GH-574 repro: DELETE must resolve the blocker it caused."""
    _, workspace, user, test_case = _extended_workspace_with_orphan_testcase()
    ctx = _auth_context(user.id, workspace.tenant_id)

    delete_response = _delete_test_case(workspace, ctx, test_case.id)
    assert delete_response.status_code == 204, delete_response.data

    # Soft-delete, as documented in TestCaseViewSet.destroy: the row survives
    # and reports its outdated state.
    get_response = _get_test_case(workspace, ctx, test_case.id)
    assert get_response.status_code == 200
    assert get_response.data["status"] == "outdated"

    findings = _blocking_findings(workspace, ctx)
    dangling = [
        f
        for f in findings
        if f.rule_id == TRACE_P6 and str(test_case.artifact_id) in f.artifact_ids
    ]
    assert not dangling, (
        "TRACE-P6 still blocks on a soft-deleted TestCase — the workspace stays "
        f"fail-closed on an artifact the user already removed: {dangling}"
    )

    # ... and with the last blocker gone the baseline goes through.
    response = _post_baseline(workspace, ctx, {"scope": "project", "name": "gh574-post"})
    assert response.status_code == 201, response.data


@pytest.mark.django_db
def test_reactivating_the_testcase_restores_the_blocker() -> None:
    """The exclusion is state-based, not a permanent opt-out.

    Guards against "fixing" GH-574 by remembering deleted ids: a reactivated
    TestCase is a live artifact again and must be audited like one.
    """
    from persistence.tenancy import TenantContext
    from workflow.services import reactivate

    _, workspace, user, test_case = _extended_workspace_with_orphan_testcase()
    ctx = _auth_context(user.id, workspace.tenant_id)

    assert _delete_test_case(workspace, ctx, test_case.id).status_code == 204

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        reactivate(
            item_id=test_case.id,
            item_type="TestCase",
            workspace_id=workspace.id,
            ctx=ctx,
        )
    finally:
        TenantContext.clear_tenant()

    findings = _blocking_findings(workspace, ctx)
    p6 = [
        f
        for f in findings
        if f.rule_id == TRACE_P6 and str(test_case.artifact_id) in f.artifact_ids
    ]
    assert len(p6) == 1, f"reactivated TestCase must be audited again: {findings}"
