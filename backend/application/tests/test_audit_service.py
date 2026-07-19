"""
AuditService (SysEng 2.0 Phase 3) — facade + Adopt/Modify remediation tests.

UMSETZUNGSPLAN_SYSENG_2.0.md §4, Phase 3. Covers:

* run_audit() returns findings with a remediation proposal attached and a
  JSON-serialisable shape (the findings-retrieval path the GET endpoint uses).
* Adopt regression (negative -> positive) for every automatic remediation:
  a Phase-2 finding exists, remediate() applies the fix, and the *same* re-run
  no longer reports that finding — proving a correct TraceLink was created.
    - TRACE-P5: deterministic (endpoints from the finding).
    - TRACE-P1: unique-candidate (single StakeholderNeed).
    - TRACE-P2: unique-candidate (single ArchitectureElement).
* The not-automatic path: ambiguous candidates (TRACE-P1 with two needs) and a
  rule with no registered remediation (TRACE-P4) both refuse cleanly
  (ValidationError, no crash).
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application.audit_service import AuditService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.audit.registry import TRACE_P1, TRACE_P2, TRACE_P4, TRACE_P5
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


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
    return Tenant.objects.create(name="Audit Tenant", slug="audit-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="audit-user", email="audit@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="Audit-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Audit Tenant",
    )


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _requirement(tenant: Tenant, workspace: Workspace, title: str = "Req") -> Requirement:
    art = _artifact(tenant, workspace, "requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


def _need(tenant: Tenant, workspace: Workspace, title: str = "Need") -> StakeholderNeed:
    art = _artifact(tenant, workspace, "stakeholder-need")
    return StakeholderNeed.objects.create(tenant=tenant, artifact=art, title=title)


def _arch(tenant: Tenant, workspace: Workspace, title: str = "AE") -> ArchitectureElement:
    art = _artifact(tenant, workspace, "architecture-element")
    return ArchitectureElement.objects.create(tenant=tenant, artifact=art, title=title)


def _link(tenant: Tenant, source: Artifact, target: Artifact, link_type: str) -> TraceLink:
    return TraceLink.objects.create(
        tenant=tenant, source=source, target=target, link_type=link_type
    )


def _findings(report, rule_id):
    return [fv for fv in report.findings if fv.finding.rule_id == rule_id]


# ---------------------------------------------------------------------------
# run_audit / findings-retrieval path
# ---------------------------------------------------------------------------


class TestRunAudit:
    def test_report_is_json_serialisable_with_remediation(self, tenant, workspace, ctx):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            report = AuditService().run_audit(workspace.id, ctx, tier="extended")

        data = report.to_dict()
        assert data["tier"] == "extended"
        assert "counts" in data and data["counts"]["total"] == len(data["findings"])
        # every finding carries a remediation proposal
        for f in data["findings"]:
            assert "remediation" in f
            assert "automatic" in f["remediation"]
            assert "index" in f

    def test_explicit_tier_minimal_yields_no_findings(self, tenant, workspace, ctx):
        with _active(tenant):
            _requirement(tenant, workspace, "Root")
            report = AuditService().run_audit(workspace.id, ctx, tier="minimal")
        assert report.findings == []

    def test_resolve_tier_falls_back_to_standard(self, monkeypatch, workspace):
        def _boom(_ws):
            raise RuntimeError("no preset")

        monkeypatch.setattr("presets.services.get_preset", _boom)
        assert AuditService.resolve_tier(str(workspace.id)) == "standard"


# ---------------------------------------------------------------------------
# TRACE-P5 — deterministic Adopt regression (negative -> positive)
# ---------------------------------------------------------------------------


class TestRemediateTraceP5:
    def test_adopt_creates_derives_from_and_clears_finding(self, tenant, workspace, ctx):
        with _active(tenant):
            parent = _requirement(tenant, workspace, "Parent")
            child = _requirement(tenant, workspace, "Child")
            # decomposes parent -> child, but NO matching derives-from child -> parent
            _link(tenant, parent.artifact, child.artifact, LinkType.DECOMPOSES.value)

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p5 = _findings(before, TRACE_P5)
            assert len(p5) == 1
            finding = p5[0].finding
            assert p5[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P5,
                artifact_ids=list(finding.artifact_ids),
            )
            assert result.applied is True
            assert result.finding_resolved is True
            assert result.created_link_id

            # The derives-from link now exists: child -> parent.
            assert TraceLink.objects.filter(
                source_id=child.artifact_id,
                target_id=parent.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P5) == []


# ---------------------------------------------------------------------------
# TRACE-P1 — unique-candidate Adopt + ambiguous refusal
# ---------------------------------------------------------------------------


class TestRemediateTraceP1:
    def test_adopt_links_root_to_unique_need(self, tenant, workspace, ctx):
        with _active(tenant):
            need = _need(tenant, workspace, "The Need")
            root = _requirement(tenant, workspace, "Root")

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p1 = _findings(before, TRACE_P1)
            assert len(p1) == 1
            assert p1[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P1,
                artifact_ids=list(p1[0].finding.artifact_ids),
            )
            assert result.applied is True and result.finding_resolved is True
            assert TraceLink.objects.filter(
                source_id=root.artifact_id,
                target_id=need.artifact_id,
                link_type=LinkType.DERIVES_FROM.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P1) == []

    def test_ambiguous_needs_refuse_automatic_remediation(self, tenant, workspace, ctx):
        with _active(tenant):
            _need(tenant, workspace, "Need A")
            _need(tenant, workspace, "Need B")
            root = _requirement(tenant, workspace, "Root")

            svc = AuditService()
            report = svc.run_audit(workspace.id, ctx, tier="extended")
            p1 = _findings(report, TRACE_P1)
            assert len(p1) == 1
            assert p1[0].remediation.automatic is False

            with pytest.raises(ValidationError):
                svc.remediate(
                    workspace.id,
                    ctx,
                    rule_id=TRACE_P1,
                    artifact_ids=list(p1[0].finding.artifact_ids),
                )


# ---------------------------------------------------------------------------
# TRACE-P2 — unique-candidate Adopt (allocated-to)
# ---------------------------------------------------------------------------


class TestRemediateTraceP2:
    def test_adopt_allocates_to_unique_architecture(self, tenant, workspace, ctx):
        with _active(tenant):
            arch = _arch(tenant, workspace, "The System")
            req = _requirement(tenant, workspace, "Req")

            svc = AuditService()
            before = svc.run_audit(workspace.id, ctx, tier="extended")
            p2 = _findings(before, TRACE_P2)
            assert len(p2) == 1
            assert p2[0].remediation.automatic is True

            result = svc.remediate(
                workspace.id,
                ctx,
                rule_id=TRACE_P2,
                artifact_ids=list(p2[0].finding.artifact_ids),
            )
            assert result.applied is True and result.finding_resolved is True
            assert TraceLink.objects.filter(
                source_id=req.artifact_id,
                target_id=arch.artifact_id,
                link_type=LinkType.ALLOCATED_TO.value,
            ).exists()

            after = svc.run_audit(workspace.id, ctx, tier="extended")
            assert _findings(after, TRACE_P2) == []


# ---------------------------------------------------------------------------
# Not-automatic path — rule without a registered remediation
# ---------------------------------------------------------------------------


class TestNoAutomaticRemediation:
    def test_trace_p4_has_no_auto_fix_and_refuses(self, tenant, workspace, ctx):
        with _active(tenant):
            root = _arch(tenant, workspace, "System")
            child = _arch(tenant, workspace, "Sub")
            child.parent = root
            child.save(update_fields=["parent"])
            # Make the parent dangling: soft-delete it -> TRACE-P4 fires.
            from persistence.models import LifecycleStatus

            root.lifecycle_status = LifecycleStatus.DELETED
            root.save(update_fields=["lifecycle_status"])

            svc = AuditService()
            report = svc.run_audit(workspace.id, ctx, tier="extended")
            p4 = _findings(report, TRACE_P4)
            assert len(p4) == 1
            assert p4[0].remediation.automatic is False
            assert "manual" in p4[0].remediation.reason.lower()

            with pytest.raises(ValidationError):
                svc.remediate(
                    workspace.id,
                    ctx,
                    rule_id=TRACE_P4,
                    artifact_ids=list(p4[0].finding.artifact_ids),
                )
