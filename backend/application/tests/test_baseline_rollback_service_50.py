"""Plan F F4.4 (PR-F11a) — additive baseline rollback service (ADR-025).

Real DB, real services: the tenant, the workspace, the baseline, the change
request, the CCB transitions and every restore write go through the production
code paths. Nothing of ours is mocked — the only stubs are the ones the scenarios
need (``monkeypatch`` of :data:`MAX_ROLLBACK_ITEMS` in test 15).

The sixteen tests below are the TDD list of plan §F4.4, verbatim. Test 17 adds
the one thing that list does not cover: a second artifact type on the write path
(the dispatch in ``_call_update_service`` is per type, so exercising only
``Requirement`` would leave the other seven branches unproven).

Rules referenced in the docstrings are ADR-025 R1–R9.
"""
from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application.base import PermissionDeniedError, ValidationError
from application.baseline_rollback_service import (
    MAX_ROLLBACK_ITEMS,
    BaselineRollbackService,
    RollbackAlreadyAppliedError,
    RollbackEmptyError,
    RollbackForbiddenError,
    RollbackNotApprovedError,
    RollbackPlanStaleError,
    RollbackTooLargeError,
)
from application.change_request_service import ChangeRequestService
from auth_tenancy.context import AuthContext, AuthMethod
from baseline.services import build as baseline_build
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_permission_cache():
    """R7 resolves item rules through a thread-local 60 s cache.

    Several tests grant/revoke an ``ItemPermission`` row mid-test; without this
    the *previous* decision could still be served and the test would assert on
    a stale allow/deny rather than on the code under test.
    """
    from auth_tenancy.services.permission_cache import PermissionCache

    PermissionCache.clear_thread()
    yield
    PermissionCache.clear_thread()


@pytest.fixture
def env(db) -> SimpleNamespace:
    """Tenant + ``standard`` workspace + an admin context, tenant armed."""
    tenant = Tenant.objects.create(
        name=f"f44-{uuid.uuid4().hex[:6]}", slug=f"f44-{uuid.uuid4().hex[:6]}"
    )
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name=f"ws-f44-{uuid.uuid4().hex[:6]}", preset={"name": "standard"}
    )
    user = User.objects.create(
        username=f"f44-{uuid.uuid4().hex[:6]}",
        email=f"f44-{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    # ``standard`` enables baselines but keeps the CCB lightweight (no SoD), so
    # one admin context can walk draft -> submitted -> under_review -> approved.
    _provision_workflows(tenant, workspace)
    return SimpleNamespace(tenant=tenant, workspace=workspace, user=user, ctx=ctx)


def _provision_workflows(tenant: Tenant, workspace: Workspace) -> None:
    """Provision the two definitions this suite needs (cheap and targeted).

    ``ccb_approval`` for the change request, ``Requirement`` (standard preset)
    because ``workflow.services.outdate`` lazily needs an item state for the
    soft-delete test. Full workspace provisioning would seed 13 entity types x
    3 global presets per test for no gain.
    """
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(tenant.id)
    create_default_workflow(
        workspace_id=workspace.id,
        preset="ccb_approval",
        item_type="ChangeRequest",
        tenant_id=tenant.id,
    )
    create_default_workflow(
        workspace_id=workspace.id,
        preset="standard",
        item_type="Requirement",
        tenant_id=tenant.id,
    )


def _provision_link_types(tenant: Tenant, workspace: Workspace) -> None:
    from link_types.workspace_store import provision_workspace_link_types

    TenantContext.set_tenant(tenant.id)
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)


def _make_requirement(env: SimpleNamespace, title: str = "Original") -> Requirement:
    artifact = Artifact.objects.create(
        tenant=env.tenant, workspace=env.workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=env.tenant,
        artifact=artifact,
        workspace=env.workspace,
        uid=f"REQ-{uuid.uuid4().hex[:8]}",
        title=title,
        description="d",
        rationale="because",
        category="functional",
    )


def _make_adr(env: SimpleNamespace, title: str = "Original ADR"):
    from persistence.models import Adr

    artifact = Artifact.objects.create(
        tenant=env.tenant, workspace=env.workspace, artifact_type="Adr"
    )
    return Adr.objects.create(
        tenant=env.tenant,
        artifact=artifact,
        workspace_id=env.workspace.id,
        uid=f"ADR-{uuid.uuid4().hex[:8]}",
        title=title,
        description="d",
        context="c",
        decision="decided",
        consequences="k",
    )


def _baseline(env: SimpleNamespace, name: str = "B1") -> uuid.UUID:
    """Real project baseline through F4.1's build seam (no auditor gate)."""
    TenantContext.set_tenant(env.tenant.id)
    return baseline_build(
        scope="project",
        workspace_id=env.workspace.id,
        name=name,
        tenant_id=env.tenant.id,
        created_by="f4-4-test",
    )


def _document_baseline(env: SimpleNamespace, document_id, name: str = "B-doc") -> uuid.UUID:
    """Document-scope baseline — the only scope that captures TraceLinks."""
    TenantContext.set_tenant(env.tenant.id)
    return baseline_build(
        scope="document",
        workspace_id=env.workspace.id,
        name=name,
        tenant_id=env.tenant.id,
        created_by="f4-4-test",
        document_id=document_id,
    )


def _baseline_without_field(env: SimpleNamespace, artifact_id, field_name: str) -> uuid.UUID:
    """Build a baseline whose snapshot for *artifact_id* lacks *field_name*.

    An older snapshot genuinely does not carry a newer key, and the baseline
    tables are immutable (R1) — so the only honest way to produce one is to
    INSERT it that way (``persist_delta_index`` is the same writer the builder
    uses; nothing is UPDATEd).
    """
    from baseline.models import BaselineDeltaIndexEntry  # noqa: F401  (proves table)
    from baseline.state_capture import capture_states
    from baseline.store import get_store
    from baseline.types import BaselineMetadata, DeltaIndexTuple

    TenantContext.set_tenant(env.tenant.id)
    artifact = Artifact.unscoped.get(id=artifact_id)
    delta_index = [
        DeltaIndexTuple(
            item_id=str(artifact.id), version=int(artifact.version), entity_type="item"
        )
    ]
    states = capture_states(delta_index, env.tenant.id)
    states[str(artifact.id)].pop(field_name, None)

    from datetime import UTC, datetime

    return get_store().persist_delta_index(
        delta_index=delta_index,
        metadata=BaselineMetadata(
            workspace_id=env.workspace.id,
            scope="project",
            name=f"B-old-{uuid.uuid4().hex[:6]}",
            created_by="f4-4-test",
            created_at=datetime.now(tz=UTC),
        ),
        tenant_id=env.tenant.id,
        states=states,
    )


def _rename_requirement(env: SimpleNamespace, requirement: Requirement, title: str) -> None:
    from application.requirement_service import RequirementService

    RequirementService().update_requirement(
        requirement.id, env.ctx, title=title, change_reason="edit after baseline"
    )


def _approve_cr(env: SimpleNamespace, cr_id) -> None:
    service = ChangeRequestService()
    service.transition_status(
        cr_id, "submitted", env.ctx, change_reason="please review"
    )
    service.transition_status(
        cr_id, "under_review", env.ctx, change_reason="picked up"
    )
    service.transition_status(cr_id, "approved", env.ctx, change_reason="approved")


def _request_and_approve(env: SimpleNamespace, baseline_id):
    cr = BaselineRollbackService().request(
        baseline_id, env.ctx, change_reason="restore the baseline"
    )
    _approve_cr(env, cr.id)
    return cr


def _cr_status(cr_id) -> str | None:
    from workflow import state_reader

    return state_reader.current_state("ChangeRequest", cr_id)


def _revisions(artifact_id) -> int:
    from persistence.models import ArtifactVersion

    return ArtifactVersion.objects.filter(artifact_id=artifact_id).count()


# ---------------------------------------------------------------------------
# 1 — preview lists changed fields
# ---------------------------------------------------------------------------


def test_preview_lists_changed_fields(env):
    """R4 — a field changed after the baseline appears as a ``restore``."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)

    item = next(i for i in plan.items if i.item_id == str(requirement.artifact_id))
    assert item.action == "restore"
    assert item.field_changes["title"] == {"current": "Changed", "baseline": "Original"}
    assert item.artifact_type == "Requirement"
    assert item.current_version == Requirement.objects.get(id=requirement.id).version
    assert plan.summary["restore"] == 1


# ---------------------------------------------------------------------------
# 2 — apply requires an approved change request
# ---------------------------------------------------------------------------


def test_apply_requires_approved_cr(env):
    """R2/R5 — a ``draft`` CR is refused and nothing is written."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    version_after_edit = Requirement.objects.get(id=requirement.id).version

    cr = BaselineRollbackService().request(
        baseline_id, env.ctx, change_reason="restore"
    )

    with pytest.raises(RollbackNotApprovedError) as excinfo:
        BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    assert excinfo.value.code == "ROLLBACK_NOT_APPROVED"
    assert excinfo.value.http_status == 409
    requirement.refresh_from_db()
    assert requirement.title == "Changed"
    assert requirement.version == version_after_edit
    assert _cr_status(cr.id) == "draft"


# ---------------------------------------------------------------------------
# 3 — restore is a new version and keeps history
# ---------------------------------------------------------------------------


def test_apply_restores_new_version_and_keeps_history(env):
    """R1 — a restore is a *new* version; the old revisions stay readable."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    revisions_before = _revisions(requirement.artifact_id)
    version_before = Requirement.objects.get(id=requirement.id).version

    cr = _request_and_approve(env, baseline_id)
    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    requirement.refresh_from_db()
    assert requirement.title == "Original"
    assert requirement.version == version_before + 1
    assert _revisions(requirement.artifact_id) == revisions_before + 1
    assert result.restored == 1
    assert result.change_request_status == "implemented"

    # History is additive: the intermediate revision is still there.
    from persistence.models import ArtifactVersion

    payloads = [
        row.payload
        for row in ArtifactVersion.objects.filter(
            artifact_id=requirement.artifact_id
        ).order_by("revision")
    ]
    assert any(payload.get("title") == "Changed" for payload in payloads)
    assert payloads[-1].get("title") == "Original"


# ---------------------------------------------------------------------------
# 4 — the baseline tables are never written
# ---------------------------------------------------------------------------


def test_apply_never_writes_baseline_tables(env):
    """R1 — no ``UPDATE``/``DELETE`` against ``bl_%`` during the whole apply."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    cr = _request_and_approve(env, baseline_id)

    with CaptureQueriesContext(connection) as captured:
        BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    offending = [
        query["sql"]
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith(("UPDATE", "DELETE"))
        and "bl_" in query["sql"]
    ]
    assert offending == []


# ---------------------------------------------------------------------------
# 5 — reactivate / recreate link / skip system-owned link type
# ---------------------------------------------------------------------------


def test_reactivates_soft_deleted_item(env):
    """R4 — a soft-deleted item is restored via ``reactivate``."""
    from workflow.services import outdate

    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    outdate(
        item_id=requirement.id,
        item_type="Requirement",
        workspace_id=env.workspace.id,
        ctx=env.ctx,
        reason="gone",
    )
    requirement.artifact.refresh_from_db()
    assert requirement.artifact.lifecycle_status == "outdated"

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)
    item = next(i for i in plan.items if i.item_id == str(requirement.artifact_id))
    assert item.action == "reactivate"

    cr = _request_and_approve(env, baseline_id)
    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    requirement.artifact.refresh_from_db()
    assert requirement.artifact.lifecycle_status == "active"
    assert result.reactivated == 1


def test_recreates_missing_trace_link(env):
    """R4 — a link that vanished after the baseline is re-inserted.

    Link-only: no item changed, so this also proves that a plan whose only work
    is a link is not ``ROLLBACK_EMPTY`` and stays executable (R2's affected-item
    set is bound to the link endpoints).
    """
    from application.trace_link_service import TraceLinkService
    from persistence.models import TraceLink

    _provision_link_types(env.tenant, env.workspace)
    source = _make_requirement(env, title="Source")
    target = _make_requirement(env, title="Target")
    TraceLinkService().create_trace_link(
        source.artifact_id, target.artifact_id, "derives-from", env.ctx
    )
    baseline_id = _document_baseline(env, source.artifact_id)
    TraceLink.objects.filter(
        source_id=source.artifact_id, target_id=target.artifact_id
    ).delete()

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)
    assert plan.links_to_recreate == [
        {
            "source_id": str(source.artifact_id),
            "target_id": str(target.artifact_id),
            "link_type": "derives-from",
        }
    ]
    assert plan.restorable_item_ids == []

    cr = _request_and_approve(env, baseline_id)
    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    assert result.links_recreated == 1
    assert TraceLink.objects.filter(
        source_id=source.artifact_id,
        target_id=target.artifact_id,
        link_type="derives-from",
    ).exists()


def test_skips_system_owned_link_type(env):
    """R4 — a system-owned type (``diagram-ref``) is skipped *and* reported."""
    from persistence.models import TraceLink

    _provision_link_types(env.tenant, env.workspace)
    source = _make_requirement(env, title="Source")
    target = _make_requirement(env, title="Target")
    # Created directly: the manual path deliberately refuses this type.
    TraceLink.objects.create(
        tenant_id=env.tenant.id,
        source=source.artifact,
        target=target.artifact,
        link_type="diagram-ref",
    )
    baseline_id = _document_baseline(env, source.artifact_id)
    TraceLink.objects.filter(
        source_id=source.artifact_id, target_id=target.artifact_id
    ).delete()

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)

    assert plan.links_to_recreate == []
    assert [(link["link_type"], link["reason"]) for link in plan.skipped_links] == [
        ("diagram-ref", "system_owned")
    ]
    # Nothing restorable and nothing recreatable -> a pointless CR is refused.
    with pytest.raises(RollbackEmptyError):
        BaselineRollbackService().request(
            baseline_id, env.ctx, change_reason="nothing to do"
        )


# ---------------------------------------------------------------------------
# 6 — plan binding
# ---------------------------------------------------------------------------


def test_stale_plan_conflict(env):
    """R3 — an item changed after the request makes the plan stale."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed once")
    cr = BaselineRollbackService().request(
        baseline_id, env.ctx, change_reason="restore"
    )
    _approve_cr(env, cr.id)
    _rename_requirement(env, requirement, "Changed twice")
    version_now = Requirement.objects.get(id=requirement.id).version

    with pytest.raises(RollbackPlanStaleError) as excinfo:
        BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    assert excinfo.value.code == "ROLLBACK_PLAN_STALE"
    details = excinfo.value.details
    assert [entry["item_id"] for entry in details] == [str(requirement.artifact_id)]
    assert details[0]["current_version"] == version_now
    requirement.refresh_from_db()
    assert requirement.title == "Changed twice"
    assert _cr_status(cr.id) == "approved"


# ---------------------------------------------------------------------------
# 7 — artifacts created after the baseline are untouched
# ---------------------------------------------------------------------------


def test_created_since_items_untouched(env):
    """R4/ENT-F6 = a — a later artifact is reported, never deleted."""
    original = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, original, "Changed")
    later = _make_requirement(env, title="Created later")

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)
    created = [i for i in plan.items if i.action == "created_since"]

    assert [i.item_id for i in created] == [str(later.artifact_id)]
    assert plan.summary["created_since"] == 1

    cr = _request_and_approve(env, baseline_id)
    BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    later.refresh_from_db()
    assert later.title == "Created later"
    assert later.artifact.lifecycle_status == "active"


# ---------------------------------------------------------------------------
# 8 — an absent snapshot field is reported, not guessed
# ---------------------------------------------------------------------------


def test_missing_snapshot_field_is_reported_not_guessed(env):
    """R4 — an older snapshot without ``rationale`` reports it as unrestorable."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline_without_field(env, requirement.artifact_id, "rationale")
    _rename_requirement(env, requirement, "Changed")
    revision_before = _revisions(requirement.artifact_id)

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)

    item = next(i for i in plan.items if i.item_id == str(requirement.artifact_id))
    assert item.unrestorable_fields == ["rationale"]
    assert "rationale" not in item.field_changes

    cr = _request_and_approve(env, baseline_id)
    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    requirement.refresh_from_db()
    assert requirement.title == "Original"
    assert requirement.rationale == "because"
    assert result.restored == 1
    assert _revisions(requirement.artifact_id) == revision_before + 1


# ---------------------------------------------------------------------------
# 9 — the CR ends implemented with state_after
# ---------------------------------------------------------------------------


def test_cr_transitions_to_implemented_with_state_after(env):
    """R6 — ``implemented`` plus a filled ``state_after`` on every affected item."""
    from persistence.models import ChangeRequestAffectedItem

    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    cr = _request_and_approve(env, baseline_id)

    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    assert result.change_request_status == "implemented"
    assert _cr_status(cr.id) == "implemented"
    affected = ChangeRequestAffectedItem.objects.get(
        change_request_id=cr.id, item_id=str(requirement.artifact_id)
    )
    assert affected.state_after is not None
    assert affected.state_after["title"] == "Original"
    assert affected.version_after == affected.version_before + 1


# ---------------------------------------------------------------------------
# 10 — concurrent apply on the same CR
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_apply_same_cr_only_one_succeeds(env):
    """R5 (QR-S09 b) — the row lock admits exactly one apply per CR.

    Two real threads, two real connections, one approved CR: the second caller
    must observe ``implemented`` and answer ``ROLLBACK_ALREADY_APPLIED``, and
    each item must gain exactly **one** new version.
    """
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    version_before = Requirement.objects.get(id=requirement.id).version
    revisions_before = _revisions(requirement.artifact_id)
    cr = _request_and_approve(env, baseline_id)

    outcomes: list[tuple[str, str]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def _run() -> None:
        connection.close()
        try:
            TenantContext.set_tenant(env.tenant.id)
            barrier.wait(timeout=10)
            try:
                BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)
                label = ("ok", "")
            except Exception as exc:  # noqa: BLE001 - the outcome *is* the assertion
                outcome = (
                    "already_applied"
                    if isinstance(exc, RollbackAlreadyAppliedError)
                    else type(exc).__name__
                )
                label = (outcome, getattr(exc, "code", ""))
        finally:
            connection.close()
        with lock:
            outcomes.append(label)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "apply did not finish within 30 s"

    assert sorted(outcome[0] for outcome in outcomes) == ["already_applied", "ok"]
    loser = next(outcome for outcome in outcomes if outcome[0] != "ok")
    assert loser[1] == "ROLLBACK_ALREADY_APPLIED"

    requirement.refresh_from_db()
    assert requirement.title == "Original"
    assert requirement.version == version_before + 1
    assert _revisions(requirement.artifact_id) == revisions_before + 1


# ---------------------------------------------------------------------------
# 11 — a CR from another workspace is refused
# ---------------------------------------------------------------------------


def test_apply_rejects_cr_of_other_workspace(env):
    """R2 — the CR's workspace must be the baseline's workspace."""
    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")

    other = Workspace.objects.create(
        tenant=env.tenant, name=f"other-{uuid.uuid4().hex[:6]}", preset={"name": "standard"}
    )
    _provision_workflows(env.tenant, other)
    TenantContext.set_tenant(env.tenant.id)
    artifact = Artifact.objects.create(
        tenant=env.tenant, workspace=other, artifact_type="Requirement"
    )
    other_requirement = Requirement.objects.create(
        tenant=env.tenant, artifact=artifact, workspace=other, title="Other"
    )
    other_baseline = baseline_build(
        scope="project",
        workspace_id=other.id,
        name=f"B-other-{uuid.uuid4().hex[:6]}",
        tenant_id=env.tenant.id,
        created_by="f4-4-test",
    )
    # The foreign workspace needs a real change, otherwise its plan is empty.
    _rename_requirement(env, other_requirement, "Other changed")
    foreign_cr = BaselineRollbackService().request(
        other_baseline, env.ctx, change_reason="restore other"
    )
    _approve_cr(env, foreign_cr.id)

    with pytest.raises(ValidationError):
        BaselineRollbackService().apply(baseline_id, foreign_cr.id, env.ctx)

    requirement.refresh_from_db()
    assert requirement.title == "Changed"


# ---------------------------------------------------------------------------
# 12 — R7: an item the caller may not read is invisible
# ---------------------------------------------------------------------------


def test_preview_hides_item_permission_none(env):
    """R7 — a ``none`` item rule removes the item from every count."""
    hidden = _make_requirement(env, title="Hidden")
    visible = _make_requirement(env, title="Visible")
    baseline_id = _baseline(env)
    _rename_requirement(env, hidden, "Hidden changed")
    _rename_requirement(env, visible, "Visible changed")

    from auth_tenancy.models import ItemPermission
    from auth_tenancy.services.permission_cache import PermissionCache

    ItemPermission.objects.create(
        tenant=env.tenant,
        user=env.user,
        workspace=env.workspace,
        artifact_id=hidden.artifact_id,
        permission_level="none",
    )
    PermissionCache.clear_thread()

    plan = BaselineRollbackService().preview(baseline_id, env.ctx)

    ids = {item.item_id for item in plan.items}
    assert str(hidden.artifact_id) not in ids
    assert str(visible.artifact_id) in ids
    assert plan.summary["restore"] == 1
    assert sum(
        value for key, value in plan.summary.items() if key in ("restore", "reactivate")
    ) == 1


# ---------------------------------------------------------------------------
# 13 — R7: apply without WRITE is denied before the first write
# ---------------------------------------------------------------------------


def test_apply_without_item_write_is_denied_and_writes_nothing(env):
    """R7 — one item without WRITE aborts the run; ``details`` hides the rest."""
    readable_but_denied = _make_requirement(env, title="Read only")
    _make_requirement(env, title="Writable")
    baseline_id = _baseline(env)
    _rename_requirement(env, readable_but_denied, "Read only changed")

    cr = BaselineRollbackService().request(
        baseline_id, env.ctx, change_reason="restore"
    )
    _approve_cr(env, cr.id)

    from auth_tenancy.models import ItemPermission
    from auth_tenancy.services.permission_cache import PermissionCache

    ItemPermission.objects.create(
        tenant=env.tenant,
        user=env.user,
        workspace=env.workspace,
        artifact_id=readable_but_denied.artifact_id,
        permission_level="read",
    )
    PermissionCache.clear_thread()

    version_before = Requirement.objects.get(id=readable_but_denied.id).version

    with pytest.raises(RollbackForbiddenError) as excinfo:
        BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    assert isinstance(excinfo.value, PermissionDeniedError)
    assert excinfo.value.code == "PERMISSION_DENIED"
    assert excinfo.value.http_status == 403
    assert excinfo.value.details["readable_item_ids"] == [
        str(readable_but_denied.artifact_id)
    ]
    assert excinfo.value.details["denied_count"] == 1

    readable_but_denied.refresh_from_db()
    assert readable_but_denied.title == "Read only changed"
    assert readable_but_denied.version == version_before
    assert _cr_status(cr.id) == "approved"


# ---------------------------------------------------------------------------
# 14 — R8: agents may preview but not apply
# ---------------------------------------------------------------------------


def test_agent_key_cannot_apply_rollback(env):
    """R8 — ``actor_type == "agent"`` is refused, and nothing is written."""
    from dataclasses import replace

    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    cr = _request_and_approve(env, baseline_id)

    agent_ctx = replace(env.ctx, actor_type="agent", agent_label="f4-4-agent")
    version_before = Requirement.objects.get(id=requirement.id).version

    # preview is read-only, so an agent may call it.
    agent_plan = BaselineRollbackService().preview(baseline_id, agent_ctx)
    assert agent_plan.summary["restore"] == 1

    with pytest.raises(PermissionDeniedError) as excinfo:
        BaselineRollbackService().apply(baseline_id, cr.id, agent_ctx)

    assert excinfo.value.code == "PERMISSION_DENIED"
    requirement.refresh_from_db()
    assert requirement.title == "Changed"
    assert requirement.version == version_before
    assert _cr_status(cr.id) == "approved"


# ---------------------------------------------------------------------------
# 15 — R9: mass limit
# ---------------------------------------------------------------------------


def test_rollback_too_large_rejected(env, monkeypatch):
    """R9 — ``request`` and ``apply`` both enforce ``MAX_ROLLBACK_ITEMS``."""
    requirements = [_make_requirement(env, title=f"R{i}") for i in range(3)]
    baseline_id = _baseline(env)
    for index, requirement in enumerate(requirements):
        _rename_requirement(env, requirement, f"R{index} changed")

    cr = BaselineRollbackService().request(
        baseline_id, env.ctx, change_reason="restore"
    )
    _approve_cr(env, cr.id)

    monkeypatch.setattr(
        "application.baseline_rollback_service.MAX_ROLLBACK_ITEMS", 2
    )
    assert MAX_ROLLBACK_ITEMS == 2000  # the module default is untouched

    with pytest.raises(RollbackTooLargeError) as apply_exc:
        BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)
    assert apply_exc.value.code == "ROLLBACK_TOO_LARGE"
    assert apply_exc.value.http_status == 400
    assert apply_exc.value.details["count"] == 3

    with pytest.raises(RollbackTooLargeError) as request_exc:
        BaselineRollbackService().request(
            baseline_id, env.ctx, change_reason="restore again"
        )
    assert request_exc.value.code == "ROLLBACK_TOO_LARGE"

    requirements[0].refresh_from_db()
    assert requirements[0].title == "R0 changed"


# ---------------------------------------------------------------------------
# 16 — R6: exactly one rollback-level audit entry
# ---------------------------------------------------------------------------


def test_apply_writes_single_audit_entry_with_cr_id(env):
    """R6 — one ``Baseline``/``update`` audit entry, carrying the CR id."""
    from audit.models import AuditEntry

    requirement = _make_requirement(env, title="Original")
    baseline_id = _baseline(env)
    _rename_requirement(env, requirement, "Changed")
    cr = _request_and_approve(env, baseline_id)

    BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    entries = AuditEntry.objects.filter(
        entity_type="Baseline", entity_id=baseline_id, op="update"
    )
    assert entries.count() == 1
    details = entries.get().details
    assert details["rollback_change_request"] == str(cr.id)
    assert details["restored"] == 1
    assert details["reactivated"] == 0
    assert details["links_recreated"] == 0
    assert details["actor_type"] == "user"


# ---------------------------------------------------------------------------
# 17 — the write path is per type (dispatch coverage beyond Requirement)
# ---------------------------------------------------------------------------


def test_apply_restores_second_artifact_type(env):
    """R1/R4 — the ADR dispatch restores an ``Adr`` as well as a Requirement."""
    adr = _make_adr(env, title="Original ADR")
    baseline_id = _baseline(env)

    from application.adr_service import AdrService

    AdrService().update_adr(
        adr.id, env.ctx, title="Changed ADR", change_reason="edit after baseline"
    )
    cr = _request_and_approve(env, baseline_id)
    result = BaselineRollbackService().apply(baseline_id, cr.id, env.ctx)

    adr.refresh_from_db()
    assert adr.title == "Original ADR"
    assert result.restored == 1
