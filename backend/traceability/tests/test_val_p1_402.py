"""#402 — goals default-on, the VAL-P1 goal rule and the off-nominal category.

Cluster-5 spec section 5. The two central properties:

* **VAL-P1 is advisory.** The gate-effective severity is
  ``ValidationGoalsRule.severity_for_tier`` (the RuleEngine re-stamps every
  finding with it), and ``AuditService.blocking_findings`` — the only method
  ``BaselineFacade._enforce_audit_gate`` consumes — filters on BLOCKER. A
  WARNING can therefore never retroactively block a baseline build for
  existing Goal-using Extended workspaces.
* **Double gate.** No finding without ``goals_enabled`` *and* at least one
  active Goal.

Mutationsprobe (spec AC-402-9): flipping
``ValidationGoalsRule.severity_for_tier`` to ``Severity.BLOCKER`` must turn
``test_val_p1_never_blocks_a_baseline_build`` red.
"""
from __future__ import annotations

import pytest

from application.audit_service import AuditService
from persistence.models import Artifact, Goal, StakeholderNeed, Tenant, Workspace
from persistence.tenancy import TenantContext
from traceability.audit import AuditScope, RuleEngine, Severity
from traceability.audit.registry import (
    VAL_P1,
    active_rule_ids_for_tier,
    full_se_rule_ids,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures / factories
# ---------------------------------------------------------------------------


@pytest.fixture
def env(db):
    """An Extended workspace with Goals enabled and an admin context."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import User

    tenant = Tenant.objects.create(name="t-402", slug="t-402")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant,
        name="ws-402",
        preset={"name": "extended"},
        goals_enabled=True,
    )
    user = User.objects.create(username="u-402", email="u-402@example.com", tenant=tenant)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, workspace, user, ctx


def _make_need(tenant, workspace, title="Need", uid=None):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    # StakeholderNeed is artifact-backed but keeps its own artifact_type value;
    # the link catalog keys on the plain type name.
    artifact.artifact_type = "StakeholderNeed"
    artifact.save(update_fields=["artifact_type"])
    return StakeholderNeed.objects.create(
        tenant=tenant, artifact=artifact, title=title, uid=uid
    )


def _make_goal(tenant, workspace, title="Goal"):
    import uuid as _uuid

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Goal"
    )
    return Goal.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace_id=workspace.id,
        lineage_id=_uuid.uuid4(),
        sequence_number=1,
        title=title,
    )


def _satisfies(need, goal, tenant):
    from persistence.models import TraceLink

    return TraceLink.objects.create(
        source=need.artifact,
        target=goal.artifact,
        link_type="satisfies",
        tenant=tenant,
    )


def _findings(tenant, workspace, tier="extended"):
    result = RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )
    return [f for f in result.findings if f.rule_id == VAL_P1]


# ---------------------------------------------------------------------------
# AC-402-3 — one finding for the uncovered need, none once linked
# ---------------------------------------------------------------------------


def test_val_p1_flags_only_the_need_without_a_goal_link(env):
    tenant, workspace, user, ctx = env
    goal = _make_goal(tenant, workspace)
    linked = _make_need(tenant, workspace, title="Linked need")
    unlinked = _make_need(tenant, workspace, title="Unlinked need")
    _satisfies(linked, goal, tenant)

    findings = _findings(tenant, workspace)

    assert len(findings) == 1
    assert str(unlinked.artifact_id) in findings[0].artifact_ids
    assert "Unlinked need" in findings[0].message


def test_val_p1_clears_when_the_second_link_is_set(env):
    tenant, workspace, user, ctx = env
    goal = _make_goal(tenant, workspace)
    first = _make_need(tenant, workspace, title="First")
    second = _make_need(tenant, workspace, title="Second")
    _satisfies(first, goal, tenant)

    assert len(_findings(tenant, workspace)) == 1

    _satisfies(second, goal, tenant)
    assert _findings(tenant, workspace) == []


def test_val_p1_ignores_a_satisfies_link_to_an_archived_goal(env):
    """The target must be an *active* Goal."""
    tenant, workspace, user, ctx = env
    goal = _make_goal(tenant, workspace)
    need = _make_need(tenant, workspace, title="Need")
    _satisfies(need, goal, tenant)

    assert _findings(tenant, workspace) == []

    # `Artifact.lifecycle_status` is the single soft-delete flag
    # (Datenmodell-Konsolidierung Phase 4, D-3) — set it directly instead of
    # driving the full workflow outdate path (which needs a Goal definition).
    goal.artifact.lifecycle_status = "outdated"
    goal.artifact.save(update_fields=["lifecycle_status"])

    # With no active Goal left, the rule's existence gate already returns
    # early — the archived goal is neither a remediation target nor a reason
    # to flag the need.
    assert _findings(tenant, workspace) == []


# ---------------------------------------------------------------------------
# AC-402-4 — the double gate
# ---------------------------------------------------------------------------


def test_val_p1_is_silent_when_goals_are_disabled(env):
    tenant, workspace, user, ctx = env
    workspace.goals_enabled = False
    workspace.save(update_fields=["goals_enabled"])
    _make_goal(tenant, workspace)
    _make_need(tenant, workspace, title="Need")

    assert _findings(tenant, workspace) == []


def test_val_p1_is_silent_without_any_goal(env):
    tenant, workspace, user, ctx = env
    _make_need(tenant, workspace, title="Need")

    assert _findings(tenant, workspace) == []


def test_val_p1_is_fail_open_for_an_unresolvable_workspace(env):
    """A workspace id that does not resolve yields no findings (fail-open)."""
    import uuid as _uuid

    tenant, workspace, user, ctx = env
    result = RuleEngine().run(
        tier="extended",
        workspace_id=str(_uuid.uuid4()),
        tenant_id=str(tenant.id),
    )
    assert [f for f in result.findings if f.rule_id == VAL_P1] == []


# ---------------------------------------------------------------------------
# AC-402-5 — Extended only
# ---------------------------------------------------------------------------


def test_val_p1_is_extended_only():
    assert VAL_P1 in active_rule_ids_for_tier("extended")
    assert VAL_P1 not in active_rule_ids_for_tier("standard")
    assert VAL_P1 not in active_rule_ids_for_tier("minimal")
    assert VAL_P1 in full_se_rule_ids()


# ---------------------------------------------------------------------------
# AC-402-9 — the advisory severity, after the engine re-stamp
# ---------------------------------------------------------------------------


def test_val_p1_findings_are_warning_after_the_engine_restamp(env):
    tenant, workspace, user, ctx = env
    _make_goal(tenant, workspace)
    _make_need(tenant, workspace, title="Need")

    findings = _findings(tenant, workspace)

    assert len(findings) == 1
    # Post-RuleEngine objects: the engine re-stamps with
    # rule.severity_for_tier(tier).
    assert findings[0].severity is Severity.WARNING


def test_val_p1_is_not_a_blocking_finding(env):
    """The exact method the baseline gate consumes."""
    tenant, workspace, user, ctx = env
    _make_goal(tenant, workspace)
    _make_need(tenant, workspace, title="Need")

    blockers = AuditService().blocking_findings(
        workspace.id, ctx, scopes=[AuditScope(scope="project", artifact_id=None)]
    )

    assert [f for f in blockers if f.rule_id == VAL_P1] == []


def test_val_p1_never_blocks_a_baseline_build(env):
    """AC-402-9: advisory means the (Extended) baseline build still succeeds."""
    from application.baseline_facade import BaselineFacade

    tenant, workspace, user, ctx = env
    _make_goal(tenant, workspace)
    _make_need(tenant, workspace, title="Need")  # deliberately unlinked

    baseline_id = BaselineFacade().create_baseline(
        scope="project", workspace_id=workspace.id, name="v1", ctx=ctx
    )

    assert baseline_id is not None


# ---------------------------------------------------------------------------
# AC-402-6 — the satisfies StakeholderNeed -> Goal pair
# ---------------------------------------------------------------------------


def test_catalog_accepts_need_satisfies_goal(env):
    from link_types.catalog import validate_link_pair
    from link_types.workspace_store import provision_workspace_link_types

    tenant, workspace, user, ctx = env
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)

    # Must not raise.
    validate_link_pair(
        workspace.id, "satisfies", "StakeholderNeed", "Goal", manual=True
    )


def test_migration_pins_the_same_pair_as_the_builtin_catalog():
    """The 0009 backfill must carry exactly the pair builtin.py now declares."""
    import importlib

    from link_types.builtin import BUILTIN_LINK_TYPES

    migration_module = importlib.import_module(
        "link_types.migrations.0009_backfill_need_satisfies_pair"
    )

    builtin_pairs = {
        (p["source_type"], p["target_type"])
        for p in BUILTIN_LINK_TYPES["satisfies"]["allowed_pairs"]
    }
    migration_pairs = {
        (p["source_type"], p["target_type"]) for p in migration_module.WANTED_PAIRS
    }
    assert migration_pairs <= builtin_pairs
    assert migration_module.KEY == "satisfies"
