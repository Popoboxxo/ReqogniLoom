"""#879 / Plan B B6-T1 — Milestone model + service.

Pins the service contract directly (no HTTP): creation defaults, baseline
binding (including the cross-workspace refusal), the frozen audit snapshot, the
optimistic-lock conflict, deterministic ordering and the tenant fence.

The RLS half of B6-T1 is covered by
``persistence/tests/test_rls_coverage.py`` (``pl_milestone`` must carry the
policy from ``persistence/0130_milestone_rls_policy``).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from application.audit_service import AuditService
from application.base import NotFoundError, OptimisticLockError, ValidationError
from application.milestone_service import MilestoneService
from auth_tenancy.context import AuthContext, AuthMethod
from baseline.models import BaselineSnapshot
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext


def _ctx(tenant: Tenant, user: User, *, roles: tuple[str, ...] = ("editor",)) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _provision_tenant(slug: str) -> dict:
    tenant = Tenant.objects.create(name=f"t-{slug}", slug=f"t-{slug}")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(
        tenant=tenant, username=f"user-{slug}", email=f"{slug}@example.com"
    )
    workspace = Workspace.objects.create(tenant=tenant, name=f"ws-{slug}")
    other_workspace = Workspace.objects.create(tenant=tenant, name=f"ws-{slug}-2")
    return {
        "tenant": tenant,
        "user": user,
        "workspace": workspace,
        "other_workspace": other_workspace,
        "ctx": _ctx(tenant, user),
    }


@pytest.fixture
def env(db):
    data = _provision_tenant("milestone")
    try:
        yield data
    finally:
        TenantContext.clear_tenant()


def _create(env, **overrides):
    payload = {
        "workspace_id": env["workspace"].id,
        "name": "PDR Fahrwerk",
        "review_type": "PDR",
        "target_date": date(2026, 12, 1),
    }
    payload.update(overrides)
    return MilestoneService().create(env["ctx"], **payload)


def _baseline(env, workspace=None, name="BL-1") -> BaselineSnapshot:
    return BaselineSnapshot.objects.create(
        tenant=env["tenant"],
        workspace_id=(workspace or env["workspace"]).id,
        scope=BaselineSnapshot.SCOPE_PROJECT,
        name=name,
    )


def test_create_milestone_defaults(env):
    milestone = _create(env)

    assert milestone.status == "planned"
    assert milestone.version == 1
    assert milestone.audit_snapshot is None
    assert milestone.baseline is None
    assert milestone.workspace_id == env["workspace"].id
    assert milestone.tenant_id == env["tenant"].id
    assert milestone.created_at is not None
    assert milestone.updated_at is not None


def test_create_rejects_unknown_review_type(env):
    with pytest.raises(ValidationError):
        _create(env, review_type="DESIGN-REVIEW")


def test_create_rejects_blank_name(env):
    with pytest.raises(ValidationError):
        _create(env, name="   ")


def test_bind_baseline(env):
    milestone = _create(env)
    baseline = _baseline(env)

    bound = MilestoneService().bind_baseline(
        milestone.id, baseline.id, env["ctx"]
    )

    assert bound.baseline_id == baseline.id
    assert bound.version == milestone.version + 1


def test_bind_baseline_from_other_workspace_is_rejected(env):
    milestone = _create(env)
    foreign = _baseline(env, workspace=env["other_workspace"], name="BL-other")

    with pytest.raises(ValidationError):
        MilestoneService().bind_baseline(milestone.id, foreign.id, env["ctx"])

    milestone.refresh_from_db()
    assert milestone.baseline_id is None
    assert milestone.version == 1


def _workspace_with_requirement(env) -> None:
    """Give the workspace one untraced requirement so the audit is non-empty."""
    artifact = Artifact.objects.create(
        tenant=env["tenant"],
        workspace=env["workspace"],
        artifact_type="Requirement",
    )
    Requirement.objects.create(
        tenant=env["tenant"], artifact=artifact, title="Untraced requirement"
    )


def test_record_audit_freezes_the_audit_counts(env):
    _workspace_with_requirement(env)
    milestone = _create(env)

    recorded = MilestoneService().record_audit(milestone.id, env["ctx"])

    report = AuditService().run_audit(env["workspace"].id, env["ctx"])
    snapshot = recorded.audit_snapshot
    assert snapshot is not None
    assert snapshot["tier"] == report.tier
    assert snapshot["counts"] == {
        "total": report.total_findings_available,
        "blockers": report.total_blockers_available,
        "warnings": report.total_warnings_available,
    }
    # ``run_at`` is an ISO-8601 instant, not a bare date.
    datetime.fromisoformat(snapshot["run_at"])
    # Recording is a record, never a gate: it bumps the counter and does not
    # refuse open blockers.
    assert recorded.version == milestone.version + 1


def test_update_with_stale_expected_version_conflicts(env):
    milestone = _create(env)
    service = MilestoneService()

    updated = service.update(
        milestone.id, env["ctx"], name="PDR neu", expected_version=milestone.version
    )
    assert updated.name == "PDR neu"
    assert updated.version == milestone.version + 1

    with pytest.raises(OptimisticLockError):
        service.update(
            milestone.id,
            env["ctx"],
            name="PDR veraltet",
            expected_version=milestone.version,
        )


def test_update_requires_at_least_one_field(env):
    milestone = _create(env)
    with pytest.raises(ValidationError):
        MilestoneService().update(milestone.id, env["ctx"])


def test_list_sorts_by_target_date_then_id(env):
    service = MilestoneService()
    late = _create(env, name="late", target_date=date(2027, 3, 1))
    early_a = _create(env, name="early-a", target_date=date(2026, 1, 1))
    early_b = _create(env, name="early-b", target_date=date(2026, 1, 1))

    rows = service.list(env["workspace"].id, env["ctx"])

    same_day = sorted([early_a, early_b], key=lambda m: m.id)
    assert [m.id for m in rows] == [same_day[0].id, same_day[1].id, late.id]


def test_tenant_fence_hides_other_tenants_milestones(env):
    milestone = _create(env)
    other = _provision_tenant("milestone-other")
    try:
        service = MilestoneService()
        with pytest.raises(NotFoundError):
            service.get(milestone.id, other["ctx"])
        with pytest.raises(NotFoundError):
            service.update(milestone.id, other["ctx"], name="hijack")
        with pytest.raises(NotFoundError):
            service.list(env["workspace"].id, other["ctx"])
        with pytest.raises(NotFoundError):
            service.create(
                other["ctx"],
                workspace_id=env["workspace"].id,
                name="hijack",
                review_type="SRR",
                target_date=date(2026, 6, 1),
            )
    finally:
        TenantContext.set_tenant(env["tenant"].id)
