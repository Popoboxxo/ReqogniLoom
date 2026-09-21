"""Issue #1021 (task 3) — a stable, run-independent finding identity.

``AuditFindingView.index`` is a position inside one audit run. It is stable
*within* a response (the frontend keys rows by it), but it is not an identity:
the same TRACE-P1 on the same artifact sits at a different index as soon as any
other finding appears or disappears, so it cannot be persisted, correlated
across runs, or used to decide which waiver/suppression covers a finding.

The canonical identity is ``baseline.waivers.finding_key`` — rule id + sorted
artifact ids (+ scope). It already decides which ``BaselineGateWaiver`` row
(GH-821) a finding matches; #1021 makes the audit API expose the *same* value
instead of a second, positional notion of identity, and removes the duplicated
private wrapper ``application.baseline_facade._finding_key`` that used to sit
in front of it.

The backwards-compatibility guard matters as much as the new field:
``BaselineGateWaiver`` rows are append-only governance records persisted with
the exact legacy rendering, so the scope-less key must stay byte-identical.
"""
from __future__ import annotations

import contextlib
from typing import Iterator

import pytest

from application import baseline_facade
from application.audit_service import AuditFindingView, AuditService
from auth_tenancy.context import AuthContext
from baseline.waivers import finding_key
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import Finding, RemediationProposal, Severity
from traceability.audit.registry import TRACE_P1
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

#: The unit separator ``baseline.waivers`` renders the key with. Spelled out
#: here on purpose: the literal is the *contract* with the persisted rows.
_US = "\x1f"


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
    return Tenant.objects.create(name="Identity Tenant", slug="identity-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="identity-user", email="identity@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return make_workspace(tenant, name="Identity-WS")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="Identity Tenant",
    )


def _orphan_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Artifact:
    """A root Requirement with no ``derives-from`` link — a TRACE-P1 finding."""
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _view(index: int, finding: Finding) -> AuditFindingView:
    return AuditFindingView(
        index=index,
        finding=finding,
        remediation=RemediationProposal.manual(
            finding.rule_id, "manual", finding.artifact_ids
        ),
    )


# ---------------------------------------------------------------------------
# The canonical rendering
# ---------------------------------------------------------------------------


class TestCanonicalFindingKey:
    def test_the_scope_less_rendering_is_byte_identical_to_the_legacy_format(self):
        """GH-821 compatibility: persisted waiver rows must keep matching.

        If this fails, every ``BaselineGateWaiver`` already on file silently
        stops matching its finding and a previously waived workspace starts
        blocking again.
        """
        assert finding_key("TRACE-P1", ["b", "a"]) == f"TRACE-P1{_US}a,b"

    def test_artifact_order_and_duplicates_do_not_change_the_identity(self):
        assert finding_key("TRACE-P1", ["b", "a"]) == finding_key("TRACE-P1", ["a", "b"])
        assert finding_key("TRACE-P1", ["a", "a"]) == finding_key("TRACE-P1", ["a"])

    def test_a_scope_extends_the_identity(self):
        scoped = finding_key("TRACE-P1", ["a"], "project")
        assert scoped != finding_key("TRACE-P1", ["a"])
        assert scoped == f"TRACE-P1{_US}a{_US}project"

    def test_an_empty_scope_is_the_scope_less_rendering(self):
        assert finding_key("TRACE-P1", ["a"], None) == finding_key("TRACE-P1", ["a"])
        assert finding_key("TRACE-P1", ["a"], "") == finding_key("TRACE-P1", ["a"])

    def test_different_scopes_are_different_findings(self):
        assert finding_key("TRACE-P1", ["a"], "document") != finding_key(
            "TRACE-P1", ["a"], "project"
        )


# ---------------------------------------------------------------------------
# The audit API exposes it
# ---------------------------------------------------------------------------


class TestAuditFindingViewExposesTheKey:
    def test_the_key_is_independent_of_the_positional_index(self):
        finding = Finding(
            rule_id=TRACE_P1,
            severity=Severity.BLOCKER,
            message="root without a need",
            artifact_ids=("art-1",),
        )
        assert _view(0, finding).finding_key == _view(137, finding).finding_key

    def test_to_dict_carries_the_canonical_key(self):
        finding = Finding(
            rule_id=TRACE_P1,
            severity=Severity.BLOCKER,
            message="root without a need",
            artifact_ids=("art-2", "art-1"),
        )
        data = _view(3, finding).to_dict()
        assert data["finding_key"] == finding_key(TRACE_P1, ("art-2", "art-1"))
        assert data["index"] == 3

    def test_the_scope_of_a_finding_is_part_of_the_exposed_key(self):
        finding = Finding(
            rule_id="TRACE-P7",
            severity=Severity.BLOCKER,
            message="scoped",
            artifact_ids=("art-1",),
            scope="document",
            scope_artifact_id="doc-1",
        )
        assert _view(0, finding).to_dict()["finding_key"] == finding_key(
            "TRACE-P7", ("art-1",), "document"
        )


# ---------------------------------------------------------------------------
# Re-audit stability (the acceptance criterion)
# ---------------------------------------------------------------------------


class TestStableAcrossReAudit:
    def test_the_same_finding_keeps_its_key_across_two_runs(
        self, tenant, workspace, ctx
    ):
        with _active(tenant):
            artifact = _orphan_requirement(tenant, workspace, "Root")
            service = AuditService()
            first = service.run_audit(workspace.id, ctx, tier="extended")
            second = service.run_audit(workspace.id, ctx, tier="extended")

        def _p1_keys(report):
            return {
                fv.finding_key
                for fv in report.findings
                if fv.finding.rule_id == TRACE_P1
            }

        assert _p1_keys(first) == _p1_keys(second)
        assert finding_key(TRACE_P1, (str(artifact.id),)) in _p1_keys(first)

    def test_an_unrelated_new_finding_does_not_change_an_existing_key(
        self, tenant, workspace, ctx
    ):
        """``index`` may move; the identity must not.

        The second run reports an additional TRACE-P1 finding, so the first
        one's position in the engine's finding list can shift — its key is what
        a client may persist, and it stays the same.
        """
        with _active(tenant):
            first_artifact = _orphan_requirement(tenant, workspace, "Root A")
            service = AuditService()
            before = service.run_audit(workspace.id, ctx, tier="extended")
            _orphan_requirement(tenant, workspace, "Root B")
            after = service.run_audit(workspace.id, ctx, tier="extended")

        expected = finding_key(TRACE_P1, (str(first_artifact.id),))

        def _by_artifact(report):
            for fv in report.findings:
                if (
                    fv.finding.rule_id == TRACE_P1
                    and str(first_artifact.id) in fv.finding.artifact_ids
                ):
                    return fv
            return None

        before_view = _by_artifact(before)
        after_view = _by_artifact(after)
        assert before_view is not None and after_view is not None
        assert before_view.finding_key == expected
        assert after_view.finding_key == expected

    def test_every_finding_in_a_run_has_a_unique_key(self, tenant, workspace, ctx):
        with _active(tenant):
            _orphan_requirement(tenant, workspace, "Root A")
            _orphan_requirement(tenant, workspace, "Root B")
            report = AuditService().run_audit(workspace.id, ctx, tier="extended")

        keys = [fv.finding_key for fv in report.findings]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Unification: one implementation, no private duplicate
# ---------------------------------------------------------------------------


class TestSingleImplementation:
    def test_the_facade_no_longer_owns_a_private_finding_key(self):
        """The duplicated wrapper was removed in favour of ``baseline.waivers``."""
        assert not hasattr(baseline_facade, "_finding_key")

    def test_the_gate_matches_the_canonical_scope_less_key(self):
        """The gate's waiver matching and the API agree on the identity.

        TRACE-P1 is a scope-agnostic rule, so the finding carries no scope and
        the two renderings coincide — which is why the audit API's key can be
        handed straight back to the gate's waiver endpoint.
        """
        finding = Finding(
            rule_id=TRACE_P1,
            severity=Severity.BLOCKER,
            message="root without a need",
            artifact_ids=("art-1",),
        )
        assert _view(0, finding).finding_key == finding_key(
            finding.rule_id, finding.artifact_ids
        )
