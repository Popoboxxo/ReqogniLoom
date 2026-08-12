"""
Issue #395 — a chain built only with the tool's own guided buttons must pass
the tool's own SE-Auditor.

The walkthrough in the issue is reproduced service-for-service, in the order
the UI calls them:

1. StakeholderNeed exists.
2. "Ableiten" on the Need (``NeedForm.handleManualDerive``):
   ``RequirementService.create_requirement`` + ``derives-from`` Req -> Need
   + the form's optional ``allocated-to`` Req -> ArchitectureElement.
3. "Ableiten" on the Requirement (``ReqTraceLinkPanel`` -> ``POST
   /api/v1/requirements/{id}/derive/``): ``RequirementService.derive_requirement``
   with the mandatory target ArchitectureElement.
4. "Testfall generieren" on the derived Requirement: ``TestService.create_test_case``
   + the ``verifies`` link the TestCase view writes.

Then the SE-Auditor runs at the ``extended`` tier — the strictest one, where
TRACE-P2 is a BLOCKER rather than a WARNING — and must report zero blocking
findings. Before the fix this produced four: TRACE-P5 (``decomposes``
without the matching ``derives-from``), TRACE-P1b (derived Requirement had no
outgoing ``derives-from`` at all), TRACE-P1 (both Requirements misclassified
as roots) and TRACE-P3 (ArchitectureElements justified only by an incoming
allocation).
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.audit_service import AuditService
from application.architecture_service import ArchitectureService
from application.requirement_service import RequirementService
from application.test_service import TestService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import (
    Artifact,
    StakeholderNeed,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.audit.types import Severity
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Derive Tenant", slug="derive-tenant-395")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="derive-user-395", email="derive395@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Derive-WS-395")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Derive Tenant",
    )


def _need(tenant: Tenant, workspace: Workspace, title: str = "Stakeholder Need"):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
    )
    return StakeholderNeed.objects.create(
        tenant=tenant, artifact=artifact, title=title
    )


def _blockers(report):
    """Blocking findings of an :class:`~application.audit_service.AuditReport`.

    ``report.findings`` holds ``AuditFindingView`` wrappers (finding +
    remediation proposal), so the severity lives one level down.
    """
    return [view.finding for view in report.findings if view.finding.severity == Severity.BLOCKER]


def _walk_guided_flow(tenant, workspace, ctx):
    """Run the four guided steps; return the created artifacts."""
    req_svc = RequirementService()
    arch_svc = ArchitectureService()
    trace_svc = TraceLinkService()
    test_svc = TestService()

    need = _need(tenant, workspace)

    # The two system levels the user picks in the derive forms.
    system = arch_svc.create_architecture_element(
        workspace_id=workspace.id, title="System", ctx=ctx, element_type="module"
    )
    subsystem = arch_svc.create_architecture_element(
        workspace_id=workspace.id,
        title="Subsystem",
        ctx=ctx,
        element_type="component",
        parent_id=system.id,
    )

    # Step 2 — "Ableiten" on the Need.
    l1 = req_svc.create_requirement(
        workspace_id=workspace.id, title="L1 System Requirement", ctx=ctx
    )
    trace_svc.create_trace_link(
        source_id=l1.artifact_id,
        target_id=need.artifact_id,
        link_type=LinkType.DERIVES_FROM.value,
        ctx=ctx,
    )
    trace_svc.allocate(
        requirement_id=l1.id, architecture_element_id=system.id, ctx=ctx
    )

    # Step 3 — "Ableiten" on the Requirement (mandatory architecture target).
    derived = req_svc.derive_requirement(
        parent_requirement_id=l1.id,
        architecture_element_id=subsystem.id,
        title="L2 Subsystem Requirement",
        ctx=ctx,
    )
    l2_id = derived.children[0].id

    # Step 4 — "Testfall generieren" on the derived Requirement.
    test_case = test_svc.create_test_case(
        workspace_id=workspace.id, title="Verifies L2", ctx=ctx
    )
    trace_svc.create_trace_link(
        source_id=test_case.id,
        target_id=l2_id,
        link_type=LinkType.VERIFIES.value,
        ctx=ctx,
    )
    return need, system, subsystem, l1, l2_id, test_case


class TestGuidedDeriveFlowPassesItsOwnAuditor:
    def test_extended_audit_reports_no_blockers(self, tenant, workspace, ctx):
        with _active(tenant):
            _walk_guided_flow(tenant, workspace, ctx)
            report = AuditService().run_audit(workspace.id, ctx, tier="extended")

        assert _blockers(report) == [], [f.message for f in _blockers(report)]

    def test_derive_writes_the_reciprocal_derives_from_link(
        self, tenant, workspace, ctx
    ):
        """TRACE-P5 requires the ``decomposes``/``derives-from`` pair; the
        guided flow used to write only the first half."""
        with _active(tenant):
            _need_, _sys, _sub, l1, l2_id, _tc = _walk_guided_flow(
                tenant, workspace, ctx
            )
            from persistence.models import Requirement

            l2 = Requirement.objects.get(id=l2_id)

            assert TraceLink.objects.filter(
                source_id=l1.artifact_id,
                target_id=l2.artifact_id,
                link_type=LinkType.DECOMPOSES.value,
            ).exists()
            assert TraceLink.objects.filter(
                source_id=l2.artifact_id,
                target_id=l1.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()
