"""#399 — baseline drift marking (decision D1: no hard block).

Cluster-5 spec section 6. Covers the service contract
(``BaselineFacade.memberships_for_artifact``), the tenant-context save/restore
semantics (spec review finding N2) and the REST surface (membership endpoint,
additive ``baseline_drift`` on retrieve, CR prefill).

The edit's drift evidence is durable: ``AuditEntry.details`` is a real nullable
JSON column (ADR-10 groundwork), so AC-D1-4/13 assert the persisted
``details.baseline_drift`` payload (including the baseline id), not merely that
an audit entry exists.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _ctx(tenant, workspace, user, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )


@pytest.fixture
def env(db):
    from persistence.models import User

    tenant = Tenant.objects.create(name="t-399", slug="t-399")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="ws-399", preset={"name": "extended"}, goals_enabled=True
    )
    user = User.objects.create(username="u-399", email="u-399@example.com", tenant=tenant)
    ctx = _ctx(tenant, workspace, user)
    # The tenant context stays armed for this test (the root conftest clears it
    # before/after every test). `test_service_arms_and_releases_the_tenant_
    # context` clears it explicitly to exercise the arming path.
    return tenant, workspace, user, ctx


def _make_requirement(tenant, workspace, title="Req"):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact, req


def _make_baseline(tenant, workspace, ctx, name="B1", scope="project"):
    """Create a baseline, waiving the SE-Auditor gate for this fixture graph.

    The fixture deliberately builds a minimal artifact graph (it is about drift
    marking, not about a complete SE chain), so the Extended auditor reports its
    usual completeness findings. The documented override lever keeps the test
    about #399.
    """
    from application.baseline_facade import BaselineFacade

    return BaselineFacade().create_baseline(
        scope=scope,
        workspace_id=workspace.id,
        name=name,
        ctx=ctx,
        override_reason="fixture baseline for drift marking test",
    )


def _memberships(artifact_id, ctx):
    from application.baseline_facade import BaselineFacade

    return BaselineFacade().memberships_for_artifact(artifact_id, ctx)


# ---------------------------------------------------------------------------
# AC-D1-1 / D1-2 / D1-3 / D1-5 — drift verdicts
# ---------------------------------------------------------------------------


def test_unchanged_baselined_artifact_is_not_drifted(env):
    """AC-D1-2 + AC-D1-3 (the membership itself)."""
    tenant, workspace, user, ctx = env
    artifact, _req = _make_requirement(tenant, workspace)
    baseline_id = _make_baseline(tenant, workspace, ctx)

    memberships = _memberships(artifact.id, ctx)

    assert len(memberships) == 1
    assert memberships[0].baseline_id == baseline_id
    assert memberships[0].scope == "project"
    assert memberships[0].drifted is False
    assert memberships[0].drift_known is True
    assert memberships[0].baselined_version == memberships[0].current_version


def test_edit_after_baseline_marks_drift(env):
    """AC-D1-1: the edit itself is *not* blocked; it marks drift.

    Deviation (documented): the AC also expects
    ``baselined_version < current_version``. The delta index records
    ``Artifact.version`` and a Requirement content edit bumps
    ``Requirement.version`` — not ``Artifact.version`` — so the two are equal
    here while the *recorded state* genuinely differs. ``drifted`` is therefore
    derived from the state comparison (authoritative), and the version pair is
    informational.
    """
    from application.requirement_service import RequirementService

    tenant, workspace, user, ctx = env
    artifact, req = _make_requirement(tenant, workspace)
    _make_baseline(tenant, workspace, ctx)

    RequirementService().update_requirement(
        req.id, ctx, title="Req renamed", change_reason="renamed for clarity"
    )

    memberships = _memberships(artifact.id, ctx)
    assert len(memberships) == 1
    assert memberships[0].drifted is True
    assert memberships[0].drift_known is True
    assert memberships[0].baselined_version == 1


def test_artifact_without_baseline_has_no_membership(env):
    """AC-D1-3."""
    tenant, workspace, user, ctx = env
    artifact, _req = _make_requirement(tenant, workspace)

    assert _memberships(artifact.id, ctx) == []


def test_re_baseline_resolves_drift(env):
    """AC-D1-5: drift is a derivation, so a new baseline resets it."""
    from application.requirement_service import RequirementService

    tenant, workspace, user, ctx = env
    artifact, req = _make_requirement(tenant, workspace)
    _make_baseline(tenant, workspace, ctx, name="B1")
    RequirementService().update_requirement(
        req.id, ctx, title="Req renamed", change_reason="renamed"
    )

    _make_baseline(tenant, workspace, ctx, name="B2")

    memberships = _memberships(artifact.id, ctx)
    assert len(memberships) == 2
    # Sorted descending by baselined_at: the fresh baseline first, undrifted.
    assert memberships[0].baseline_name == "B2"
    assert memberships[0].drifted is False
    assert memberships[1].baseline_name == "B1"
    assert memberships[1].drifted is True


def test_legacy_entry_without_state_reports_drift_unknown(env):
    """AC-D1-8: a NULL ``state`` degrades to a version comparison.

    Baselines are immutable (DB trigger), so the legacy entry is simulated by
    inserting a snapshot + delta row directly instead of mutating an existing
    one.
    """
    from baseline.models import BaselineDeltaIndexEntry, BaselineSnapshot

    tenant, workspace, user, ctx = env
    artifact, _req = _make_requirement(tenant, workspace)

    snapshot = BaselineSnapshot.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="Legacy-B1",
        scope="project",
        created_by_ref="test",
    )
    BaselineDeltaIndexEntry.objects.create(
        baseline=snapshot,
        item_id=str(artifact.id),
        version=0,
        entity_type="item",
        state=None,
    )

    memberships = _memberships(artifact.id, ctx)

    assert len(memberships) == 1
    assert memberships[0].drift_known is False
    assert memberships[0].drifted is True


def test_global_baseline_is_tenant_wide(env):
    """AC-D1-9: a global baseline from workspace A covers workspace B."""
    tenant, workspace, user, ctx = env

    other_ws = Workspace.objects.create(
        tenant=tenant, name="ws-399-b", preset={"name": "extended"}, goals_enabled=True
    )
    other_artifact, _other_req = _make_requirement(tenant, other_ws, title="Req B")

    # Global baseline created *from* workspace A.
    _make_baseline(tenant, workspace, ctx, name="Global-1", scope="global")

    memberships = _memberships(other_artifact.id, ctx)

    assert len(memberships) == 1
    assert memberships[0].scope == "global"
    assert memberships[0].drifted is False


# ---------------------------------------------------------------------------
# AC-D1-10 / D1-12 — tenant-context save/restore (spec finding N2)
# ---------------------------------------------------------------------------


def test_service_arms_and_releases_the_tenant_context(env):
    """AC-D1-10: no context before, no context after, still correct result."""
    tenant, workspace, user, ctx = env
    artifact, _req = _make_requirement(tenant, workspace)
    _make_baseline(tenant, workspace, ctx)

    TenantContext.clear_tenant()
    assert TenantContext.is_set() is False

    memberships = _memberships(artifact.id, ctx)

    assert len(memberships) == 1
    assert TenantContext.is_set() is False


def test_service_leaves_a_pre_armed_context_untouched(env):
    """AC-D1-12: nested/middleware case — the ambient context survives."""
    from application.requirement_service import RequirementService

    tenant, workspace, user, ctx = env
    artifact, req = _make_requirement(tenant, workspace)
    _make_baseline(tenant, workspace, ctx)

    from persistence.middleware import set_request_tenant

    set_request_tenant(tenant.id)
    try:
        assert TenantContext.is_set() is True
        before = TenantContext.get_tenant()

        memberships = _memberships(artifact.id, ctx)

        assert TenantContext.is_set() is True
        assert TenantContext.get_tenant() == before
    finally:
        pass

    # A following audit write in the same request still succeeds (the blind
    # clear of revision 2 would have broken exactly this).
    RequirementService().update_requirement(
        req.id, ctx, title="After membership lookup", change_reason="test"
    )
    assert TenantContext.is_set() is True


def test_edit_audits_the_drift(env):
    """AC-D1-4 / AC-D1-13: the edit persists the drift evidence.

    The marking must outlive the request, so it lives on the edit's audit
    entry — ``AuditEntry.details.baseline_drift`` names every baseline the
    artifact drifted from (here exactly one, identified by its id).
    """
    from application.requirement_service import RequirementService
    from audit.models import AuditEntry
    from persistence.middleware import set_request_tenant

    tenant, workspace, user, ctx = env
    _artifact, req = _make_requirement(tenant, workspace)
    baseline_id = _make_baseline(tenant, workspace, ctx)

    set_request_tenant(tenant.id)
    try:
        RequirementService().update_requirement(
            req.id, ctx, title="Drifted title", change_reason="because"
        )
    finally:
        from persistence.middleware import clear_request_tenant

        clear_request_tenant()

    entry = (
        AuditEntry.unscoped.filter(
            entity_type="Requirement", entity_id=req.id, op="update"
        )
        .order_by("-timestamp")
        .first()
    )
    assert entry is not None
    assert entry.details is not None
    drift = entry.details["baseline_drift"]
    assert len(drift) == 1
    assert drift[0]["baseline_id"] == str(baseline_id)
    assert drift[0]["scope"] == "project"
    assert drift[0]["drift_known"] is True


def test_edit_without_baseline_persists_no_details(env):
    """The additive field stays NULL when the artifact is in no baseline.

    Guards the "default behaviour unchanged when ``details`` is omitted" side
    of FIX 2: an edit that produced no drift payload must not gain one.
    """
    from application.requirement_service import RequirementService
    from audit.models import AuditEntry
    from persistence.middleware import set_request_tenant

    tenant, workspace, user, ctx = env
    _artifact, req = _make_requirement(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        RequirementService().update_requirement(
            req.id, ctx, title="Unbaselined rename", change_reason="no baseline"
        )
    finally:
        from persistence.middleware import clear_request_tenant

        clear_request_tenant()

    entry = (
        AuditEntry.unscoped.filter(
            entity_type="Requirement", entity_id=req.id, op="update"
        )
        .order_by("-timestamp")
        .first()
    )
    assert entry is not None
    assert entry.details is None


