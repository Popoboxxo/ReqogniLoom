"""
DB-backed tests for ChangeRequest configuration-management traceability.

leaf_id : COMP-AS-021
req_id  : REQ-157

Covers the two CCB / configuration-management levers:

Lever 4 — affected items + baseline linkage
    * affected items are validated (existence + workspace) and persisted with a
      "before" state snapshot captured through ``baseline.state_capture``;
    * ``link_baseline`` attaches the workspace's baseline of record;
    * both are a safe **no-op** (never an error) on the ``minimal`` rigor tier,
      which has neither baselines nor an approval CCB.

Lever 5 — separation of duties + no silent workflow bypass
    * the requestor may not decide their own change request (extended tier);
    * a missing ``ccb_approval`` workflow definition now raises instead of
      silently writing the status field.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.change_request_service import ChangeRequestService
from application.models import ChangeRequest, ChangeRequestAffectedItem
from application.preset_policy_service import get_preset_policy_service
from auth_tenancy.context import AuthContext
from baseline.models import BaselineSnapshot
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="ccb-tenant", slug="ccb-tenant")


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username="ccb-user", email="ccb@example.com", tenant=tenant
    )


def _make_workspace(tenant: Tenant, name: str, tier: str) -> Workspace:
    """Create a workspace pinned to *tier*.

    ``presets.gate._get_or_create_preset_config`` reads the initial tier from
    ``Workspace.preset["name"]`` — the same mechanism ``seed_demo`` uses — so
    this is how a test workspace declares its rigor tier.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": tier}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def extended_workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant, "ws-extended", "extended")


@pytest.fixture
def standard_workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant, "ws-standard", "standard")


@pytest.fixture
def minimal_workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant, "ws-minimal", "minimal")


@pytest.fixture
def ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="ccb-tenant",
    )


@pytest.fixture(autouse=True)
def _clear_preset_cache():
    """Drop the preset caches around each test.

    ``PresetPolicyService`` is a process singleton with a 5-minute TTL cache and
    ``presets.gate`` keeps a module-level tier cache; both are keyed by
    workspace id. Test workspaces are fresh per test, but the caches survive
    the DB rollback, so a recycled UUID would otherwise leak a tier.
    """
    yield
    from presets import gate

    with gate._cache_lock:
        gate._tier_cache.clear()
    get_preset_policy_service()._cache.clear()


def _requirement_artifact(tenant: Tenant, workspace: Workspace, title: str) -> Artifact:
    """Create a Requirement plus its backing Artifact and return the Artifact."""
    TenantContext.set_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
        return artifact
    finally:
        TenantContext.clear_tenant()


def _baseline(tenant: Tenant, workspace: Workspace, name: str) -> BaselineSnapshot:
    TenantContext.set_tenant(tenant.id)
    try:
        return BaselineSnapshot.objects.create(
            tenant=tenant, workspace_id=workspace.id, scope="project", name=name
        )
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Lever 4 — affected items
# ---------------------------------------------------------------------------


class TestAffectedItems:
    def test_create_with_affected_items_persists_snapshot(
        self, tenant, standard_workspace, ctx
    ):
        artifact = _requirement_artifact(tenant, standard_workspace, "Login must be 2FA")
        svc = ChangeRequestService()

        cr = svc.create_change_request(
            workspace_id=standard_workspace.id,
            title="Introduce 2FA",
            ctx=ctx,
            affected_item_ids=[artifact.id],
        )

        rows = list(ChangeRequestAffectedItem.objects.filter(change_request_id=cr.id))
        assert len(rows) == 1
        row = rows[0]
        assert row.item_id == str(artifact.id)
        assert row.entity_type == "item"
        assert row.tenant_id == tenant.id
        # State snapshot comes from baseline.state_capture — same curated field
        # set the baseline snapshots use.
        assert row.state_before["artifact_type"] == "requirement"
        assert row.state_before["title"] == "Login must be 2FA"
        assert row.version_before == row.state_before["version"]
        assert row.state_after is None and row.version_after is None

    def test_set_affected_items_replaces_the_set(
        self, tenant, standard_workspace, ctx
    ):
        first = _requirement_artifact(tenant, standard_workspace, "A")
        second = _requirement_artifact(tenant, standard_workspace, "B")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id,
            title="Replace impact set",
            ctx=ctx,
            affected_item_ids=[first.id],
        )

        svc.set_affected_items(cr_id=cr.id, item_ids=[second.id], ctx=ctx)

        item_ids = {r.item_id for r in svc.list_affected_items(cr.id, ctx)}
        assert item_ids == {str(second.id)}

    def test_duplicate_ids_are_collapsed(self, tenant, standard_workspace, ctx):
        artifact = _requirement_artifact(tenant, standard_workspace, "Dup")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id,
            title="Dup ids",
            ctx=ctx,
            affected_item_ids=[artifact.id, str(artifact.id)],
        )
        assert len(svc.list_affected_items(cr.id, ctx)) == 1

    def test_unknown_item_is_rejected(self, standard_workspace, ctx):
        svc = ChangeRequestService()
        with pytest.raises(ValidationError, match="not found in workspace"):
            svc.create_change_request(
                workspace_id=standard_workspace.id,
                title="Bad impact set",
                ctx=ctx,
                affected_item_ids=[uuid.uuid4()],
            )
        assert not ChangeRequest.objects.filter(
            workspace_id=standard_workspace.id
        ).exists()

    def test_artifact_from_another_workspace_is_rejected(
        self, tenant, standard_workspace, extended_workspace, ctx
    ):
        foreign = _requirement_artifact(tenant, extended_workspace, "Foreign")
        svc = ChangeRequestService()
        with pytest.raises(ValidationError, match="not found in workspace"):
            svc.create_change_request(
                workspace_id=standard_workspace.id,
                title="Cross-workspace impact",
                ctx=ctx,
                affected_item_ids=[foreign.id],
            )

    def test_malformed_id_is_rejected(self, standard_workspace, ctx):
        svc = ChangeRequestService()
        with pytest.raises(ValidationError, match="not a valid UUID"):
            svc.create_change_request(
                workspace_id=standard_workspace.id,
                title="Malformed impact set",
                ctx=ctx,
                affected_item_ids=["not-a-uuid"],
            )

    def test_affected_items_work_on_minimal_tier(self, tenant, minimal_workspace, ctx):
        """Minimal tier keeps the CCB lightweight — recording impact must still
        be possible and must never raise."""
        artifact = _requirement_artifact(tenant, minimal_workspace, "Minimal req")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=minimal_workspace.id,
            title="Lightweight change",
            ctx=ctx,
            affected_item_ids=[artifact.id],
        )
        assert len(svc.list_affected_items(cr.id, ctx)) == 1


# ---------------------------------------------------------------------------
# Lever 4 — baseline linkage
# ---------------------------------------------------------------------------


class TestBaselineLinkage:
    def test_link_baseline_uses_latest_when_unspecified(
        self, tenant, standard_workspace, ctx
    ):
        _baseline(tenant, standard_workspace, "v1.0")
        newest = _baseline(tenant, standard_workspace, "v1.1")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id, title="Link latest", ctx=ctx
        )

        svc.link_baseline(cr_id=cr.id, ctx=ctx)

        cr.refresh_from_db()
        assert cr.baseline_id == newest.id

    def test_link_baseline_explicit_id(self, tenant, standard_workspace, ctx):
        target = _baseline(tenant, standard_workspace, "v2.0")
        _baseline(tenant, standard_workspace, "v2.1")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id, title="Link explicit", ctx=ctx
        )

        svc.link_baseline(cr_id=cr.id, ctx=ctx, baseline_id=target.id)

        cr.refresh_from_db()
        assert cr.baseline_id == target.id

    def test_link_baseline_from_other_workspace_raises(
        self, tenant, standard_workspace, extended_workspace, ctx
    ):
        foreign = _baseline(tenant, extended_workspace, "foreign-baseline")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id, title="Foreign baseline", ctx=ctx
        )

        with pytest.raises(NotFoundError):
            svc.link_baseline(cr_id=cr.id, ctx=ctx, baseline_id=foreign.id)

    def test_link_baseline_without_any_baseline_is_noop(
        self, standard_workspace, ctx
    ):
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id, title="No baseline yet", ctx=ctx
        )

        svc.link_baseline(cr_id=cr.id, ctx=ctx)

        cr.refresh_from_db()
        assert cr.baseline_id is None

    def test_link_baseline_is_noop_on_minimal_tier(
        self, tenant, minimal_workspace, ctx
    ):
        """``minimal`` has ``baselines=False`` — linkage must degrade to a
        no-op, not raise, even when a baseline row happens to exist."""
        _baseline(tenant, minimal_workspace, "leftover-baseline")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=minimal_workspace.id, title="Minimal CR", ctx=ctx
        )

        svc.link_baseline(cr_id=cr.id, ctx=ctx)

        cr.refresh_from_db()
        assert cr.baseline_id is None


# ---------------------------------------------------------------------------
# Lever 5 — no silent workflow bypass
# ---------------------------------------------------------------------------


class TestNoSilentWorkflowBypass:
    def test_missing_workflow_definition_raises_instead_of_writing_status(
        self, standard_workspace, ctx
    ):
        """The workspace fixture never provisions ``ccb_approval``.

        Previously the service logged at DEBUG and wrote ``status`` directly,
        bypassing role checks, the state machine and change_reason. It must now
        raise and leave the CR untouched.
        """
        from workflow.lifecycle_manager import WorkflowStateError
        from workflow.definition_store import WorkflowDefinitionError

        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id, title="Ungoverned CR", ctx=ctx
        )

        with pytest.raises((WorkflowStateError, WorkflowDefinitionError)):
            svc.transition_status(
                cr_id=cr.id,
                target_status="submitted",
                ctx=ctx,
                change_reason="please review",
            )

        cr.refresh_from_db()
        # Task 12: the `status` column is dropped -- resolve through the
        # engine seam (falls back to the ccb_approval initial state, since
        # no definition exists to create a WorkflowItemState against).
        from workflow import state_reader

        resolved = state_reader.current_state(
            "ChangeRequest", cr.id
        ) or state_reader.initial_state("ChangeRequest")
        assert resolved == "draft"
        assert cr.version == 1


# ---------------------------------------------------------------------------
# Lever 5 — separation of duties, end to end through the real CCB workflow
# ---------------------------------------------------------------------------


def _provision_ccb(workspace: Workspace, tenant: Tenant) -> None:
    """Provision the workspace defaults so ``ccb_approval`` really exists."""
    from application.workspace_provisioning import provision_workspace_defaults_scoped

    provision_workspace_defaults_scoped(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        requirement_preset="extended",
    )


def _engine_status(cr_id) -> str | None:
    """Datenmodell-Konsolidierung Phase 1: ``ChangeRequest.status`` is no
    longer written by the workflow engine, so tests must read the current
    state through ``workflow.state_reader`` instead of ``cr.refresh_from_db()``
    — that column is frozen at whatever it held at creation."""
    from workflow import state_reader

    return state_reader.current_state("ChangeRequest", cr_id)


def _ctx_for(user_id, tenant: Tenant, roles: tuple[str, ...]) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant.id,
        active_roles=roles,
        auth_method="test",
        api_key_id=None,
        tenant_name="ccb-tenant",
    )


class TestSeparationOfDuties:
    """Extended tier (``approval_workflows`` enabled) — full CCB path."""

    def _submitted_cr(self, tenant, workspace, requestor_ctx, artifact, **kwargs):
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=workspace.id,
            title="Change the auth subsystem",
            ctx=requestor_ctx,
            affected_item_ids=[artifact.id],
            **kwargs,
        )
        svc.transition_status(
            cr_id=cr.id,
            target_status="submitted",
            ctx=requestor_ctx,
            change_reason="ready for the board",
        )
        approver_ctx = _ctx_for(uuid.uuid4(), tenant, ("approver",))
        svc.transition_status(
            cr_id=cr.id,
            target_status="under_review",
            ctx=approver_ctx,
            change_reason="board picked it up",
        )
        return svc, cr, approver_ctx

    def test_requestor_cannot_approve_own_change_request(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        artifact = _requirement_artifact(tenant, extended_workspace, "Auth req")
        svc, cr, _approver_ctx = self._submitted_cr(
            tenant, extended_workspace, ctx, artifact
        )

        # Same user as cr.requestor_id, and even with the approver role.
        self_approver_ctx = _ctx_for(ctx.user_id, tenant, ("approver", "editor"))
        with pytest.raises(PermissionDeniedError, match="Separation of duties"):
            svc.transition_status(
                cr_id=cr.id,
                target_status="approved",
                ctx=self_approver_ctx,
                change_reason="looks good to me",
            )

        assert _engine_status(cr.id) == "under_review"

    def test_requestor_cannot_reject_own_change_request(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        artifact = _requirement_artifact(tenant, extended_workspace, "Auth req")
        svc, cr, _approver_ctx = self._submitted_cr(
            tenant, extended_workspace, ctx, artifact
        )

        self_approver_ctx = _ctx_for(ctx.user_id, tenant, ("approver",))
        with pytest.raises(PermissionDeniedError, match="Separation of duties"):
            svc.transition_status(
                cr_id=cr.id,
                target_status="rejected",
                ctx=self_approver_ctx,
                change_reason="withdrawing",
            )

    def test_foreign_user_cannot_decide_assigned_change_request(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        artifact = _requirement_artifact(tenant, extended_workspace, "Auth req")
        reviewer_id = uuid.uuid4()
        svc, cr, _approver_ctx = self._submitted_cr(
            tenant,
            extended_workspace,
            ctx,
            artifact,
            assigned_reviewer_id=reviewer_id,
        )

        stranger_ctx = _ctx_for(uuid.uuid4(), tenant, ("approver",))
        with pytest.raises(PermissionDeniedError, match="assigned to reviewer"):
            svc.transition_status(
                cr_id=cr.id,
                target_status="approved",
                ctx=stranger_ctx,
                change_reason="rubber stamp",
            )

    def test_admin_may_override_the_assigned_reviewer(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        artifact = _requirement_artifact(tenant, extended_workspace, "Auth req")
        svc, cr, _approver_ctx = self._submitted_cr(
            tenant,
            extended_workspace,
            ctx,
            artifact,
            assigned_reviewer_id=uuid.uuid4(),
        )

        admin_ctx = _ctx_for(uuid.uuid4(), tenant, ("admin", "approver"))
        svc.transition_status(
            cr_id=cr.id,
            target_status="approved",
            ctx=admin_ctx,
            change_reason="board decision recorded",
        )

        assert _engine_status(cr.id) == "approved"

    def test_approval_captures_after_state_and_links_baseline(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        artifact = _requirement_artifact(tenant, extended_workspace, "Auth req")
        baseline = _baseline(tenant, extended_workspace, "release-1.0")
        svc, cr, approver_ctx = self._submitted_cr(
            tenant, extended_workspace, ctx, artifact
        )

        svc.transition_status(
            cr_id=cr.id,
            target_status="approved",
            ctx=approver_ctx,
            change_reason="board approved",
        )

        cr.refresh_from_db()
        assert _engine_status(cr.id) == "approved"
        assert cr.baseline_id == baseline.id
        row = ChangeRequestAffectedItem.objects.get(change_request_id=cr.id)
        assert row.state_after is not None
        assert row.version_after == row.state_after["version"]

    def test_extended_tier_rejects_approval_without_affected_items(
        self, tenant, extended_workspace, ctx
    ):
        _provision_ccb(extended_workspace, tenant)
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=extended_workspace.id,
            title="Impact-less change",
            ctx=ctx,
        )
        svc.transition_status(
            cr_id=cr.id,
            target_status="submitted",
            ctx=ctx,
            change_reason="ready",
        )
        approver_ctx = _ctx_for(uuid.uuid4(), tenant, ("approver",))
        svc.transition_status(
            cr_id=cr.id,
            target_status="under_review",
            ctx=approver_ctx,
            change_reason="reviewing",
        )

        with pytest.raises(ValidationError, match="without recorded affected items"):
            svc.transition_status(
                cr_id=cr.id,
                target_status="approved",
                ctx=approver_ctx,
                change_reason="approve anyway",
            )


class TestLightweightTiersStayLightweight:
    """Standard tier has ``approval_workflows=False`` — SoD is intentionally
    not enforced there, mirroring PresetPolicyService.validate_transition_roles.
    """

    def test_requestor_may_decide_on_standard_tier(
        self, tenant, standard_workspace, ctx
    ):
        _provision_ccb(standard_workspace, tenant)
        artifact = _requirement_artifact(tenant, standard_workspace, "Small req")
        svc = ChangeRequestService()
        cr = svc.create_change_request(
            workspace_id=standard_workspace.id,
            title="Small change",
            ctx=ctx,
            affected_item_ids=[artifact.id],
        )
        svc.transition_status(
            cr_id=cr.id, target_status="submitted", ctx=ctx, change_reason="go"
        )
        self_ctx = _ctx_for(ctx.user_id, tenant, ("approver", "editor"))
        svc.transition_status(
            cr_id=cr.id, target_status="under_review", ctx=self_ctx
        )

        svc.transition_status(
            cr_id=cr.id,
            target_status="approved",
            ctx=self_ctx,
            change_reason="self-approved, lightweight tier",
        )

        assert _engine_status(cr.id) == "approved"
