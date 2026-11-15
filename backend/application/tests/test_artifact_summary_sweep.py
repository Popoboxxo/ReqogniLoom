"""Sweep + beat + workspace cadence for periodic artifact summaries (#1793, S5).

What is pinned here, and why it matters:

* **The flag is the first gate.** With ``ARTIFACT_SUMMARY_SWEEP_ENABLED`` off a
  run must be a no-op with **zero** provider calls — this feature spends money
  on a schedule, so "off" has to be literal.
* **Cadence is clamped, not rejected.** A workspace interval below the global
  minimum behaves like the minimum, and ``0`` means off (spec §9/E6).
* **The roster and the batch are bounded.** A workspace with 40 due scopes and
  a batch of 25 performs 25 calls, never 40; an unknown type in the JSON list
  never becomes a candidate.
* **Budget and identity are separate gates.** The summary-only budget is
  independent of ``TENANT_TOKEN_LIMIT_PER_DAY``, and no agent key means no run
  (an automatic run must never write under a real user's identity).
* **Unchanged input is not a call.** A second run over the same content leaves
  ``modified_at`` alone (spec §6.5).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from application.artifact_summary_service import ArtifactSummaryService
from application.artifact_summary_sweep import (
    DEFAULT_SUMMARY_SCOPES,
    ArtifactSummarySweeper,
    interval_for_workspace,
    resolve_summary_scopes,
)
from application.summary_support import TYPE_ROSTER_KIND, upsert_summary
from auth_tenancy.models import ApiKey, UserRole
from persistence.models import ArtifactSummary, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_requirement, make_workspace

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_state():
    cache.clear()
    TenantContext.clear_tenant()
    yield
    cache.clear()
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="Summary Sweep", slug=f"summary-sweep-{uuid.uuid4().hex[:8]}"
    )


def _workspace(tenant: Tenant, **kwargs) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return make_workspace(tenant, **kwargs)
    finally:
        TenantContext.clear_tenant()


def _agent_key(tenant: Tenant, workspace: Workspace) -> ApiKey:
    TenantContext.set_tenant(tenant.id)
    try:
        suffix = uuid.uuid4().hex[:8]
        user = User.objects.create(
            username=f"summary-agent-{suffix}",
            email=f"summary-agent-{suffix}@example.com",
            tenant=tenant,
        )
        UserRole.objects.create(
            tenant=tenant, workspace=workspace, user=user, role="editor"
        )
        return ApiKey.objects.create(
            tenant=tenant,
            user=user,
            name="summary-bot",
            key_hash=f"sha256p1:{uuid.uuid4().hex}",
            principal_type="agent",
            agent_label="Summary Bot",
            scope="write",
        )
    finally:
        TenantContext.clear_tenant()


def _enable(settings, *, key: ApiKey | None = None, batch: int = 25) -> None:
    settings.ARTIFACT_SUMMARY_SWEEP_ENABLED = True
    settings.ARTIFACT_SUMMARY_SWEEP_BATCH = batch
    settings.SUMMARY_DAILY_TOKEN_LIMIT = 0
    settings.ARTIFACT_SUMMARY_AGENT_KEY_ID = str(key.id) if key is not None else ""


def _call_spy(outcome: str = "summarized"):
    return patch(
        "application.artifact_summary_service.ArtifactSummaryService.summarize_artifact_type",
        return_value=outcome,
    )


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def test_flag_off_is_a_no_op(settings, tenant):
    """Flag off: run_sweep reports disabled and the service is never called."""
    settings.ARTIFACT_SUMMARY_SWEEP_ENABLED = False
    workspace = _workspace(tenant, summary_scopes=["Requirement"])

    with _call_spy() as summarize:
        counts = ArtifactSummarySweeper().run_sweep(tenant.id)

        outcome = ArtifactSummarySweeper().run_for_scope(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="Requirement",
        )

    assert counts["disabled"] is True
    assert outcome == "skipped:flag_off"
    summarize.assert_not_called()


def test_interval_zero_disables_one_workspace(settings, tenant):
    settings.ARTIFACT_SUMMARY_SWEEP_ENABLED = True
    workspace = _workspace(tenant, summary_sweep_interval_minutes=0)

    with _call_spy() as summarize:
        outcome = ArtifactSummarySweeper().run_for_scope(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="Requirement",
        )

    assert outcome == "skipped:interval_off"
    summarize.assert_not_called()


def test_interval_below_the_minimum_is_clamped(settings, tenant):
    workspace = _workspace(tenant, summary_sweep_interval_minutes=30)

    assert interval_for_workspace(workspace) == 60


def test_a_scope_inside_its_interval_is_not_due(settings, tenant):
    """30 minutes after a run with the clamped 60-minute cadence: not due."""
    workspace = _workspace(tenant, summary_sweep_interval_minutes=30)
    TenantContext.set_tenant(tenant.id)
    try:
        upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type="Requirement",
            values={
                "text": "old",
                "content_hash": "a" * 64,
                "status": ArtifactSummary.Status.OK,
                "reason": "",
            },
        )
        ArtifactSummary.objects.filter(workspace=workspace).update(
            modified_at=timezone.now() - timedelta(minutes=30)
        )
    finally:
        TenantContext.clear_tenant()
    _enable(settings, key=_agent_key(tenant, workspace))

    with _call_spy() as summarize:
        outcome = ArtifactSummarySweeper().run_for_scope(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="Requirement",
        )

    assert outcome == "skipped:not_due"
    summarize.assert_not_called()


# ---------------------------------------------------------------------------
# Scope list and batch
# ---------------------------------------------------------------------------


def test_empty_scope_list_means_all_defaults(tenant):
    workspace = _workspace(tenant)

    assert resolve_summary_scopes(workspace) == DEFAULT_SUMMARY_SCOPES
    assert len(DEFAULT_SUMMARY_SCOPES) == 12


def test_configured_scope_list_wins_and_unknown_entries_are_ignored(tenant):
    workspace = _workspace(tenant, summary_scopes=["Requirement", "TraceLink", "Nope"])

    assert resolve_summary_scopes(workspace) == ("Requirement",)


def test_batch_ceiling_caps_the_number_of_calls(settings, tenant):
    """40 due scopes, batch 25 -> exactly 25 calls."""
    workspaces = [_workspace(tenant) for _ in range(4)]  # 4 x 12 = 48 scopes
    _enable(settings, key=_agent_key(tenant, workspaces[0]), batch=25)

    with _call_spy("summarized") as summarize:
        counts = ArtifactSummarySweeper().run_sweep(tenant.id)

    assert summarize.call_count == 25
    assert counts["summarized"] == 25


def test_only_the_configured_type_is_a_candidate(settings, tenant):
    workspace = _workspace(tenant, summary_scopes=["Requirement"])
    _enable(settings, key=_agent_key(tenant, workspace))

    with _call_spy("summarized") as summarize:
        ArtifactSummarySweeper().run_sweep(tenant.id)

    assert summarize.call_count == 1
    assert summarize.call_args.args[2] == "Requirement"


# ---------------------------------------------------------------------------
# Budget and identity
# ---------------------------------------------------------------------------


def test_summary_budget_stops_before_the_provider(settings, tenant):
    workspace = _workspace(tenant, summary_scopes=["Requirement"])
    _enable(settings, key=_agent_key(tenant, workspace))
    TenantContext.set_tenant(tenant.id)
    try:
        upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type="Requirement",
            values={
                "text": "last good",
                "content_hash": "b" * 64,
                "status": ArtifactSummary.Status.OK,
                "reason": "",
            },
        )
        ArtifactSummary.objects.filter(workspace=workspace).update(
            modified_at=timezone.now() - timedelta(hours=25)
        )
    finally:
        TenantContext.clear_tenant()

    with patch(
        "application.artifact_summary_sweep.summary_budget_exhausted",
        return_value=True,
    ), _call_spy() as summarize:
        outcome = ArtifactSummarySweeper().run_for_scope(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="Requirement",
        )

    assert outcome == "skipped:budget_exhausted"
    summarize.assert_not_called()
    TenantContext.set_tenant(tenant.id)
    try:
        row = ArtifactSummary.objects.get(workspace=workspace)
    finally:
        TenantContext.clear_tenant()
    assert row.reason == ArtifactSummary.Reason.BUDGET_EXHAUSTED
    assert row.status == ArtifactSummary.Status.SKIPPED
    assert row.text == "last good"


def test_no_agent_key_means_no_run(settings, tenant):
    workspace = _workspace(tenant, summary_scopes=["Requirement"])
    _enable(settings, key=None)

    with _call_spy() as summarize:
        outcome = ArtifactSummarySweeper().run_for_scope(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            artifact_type="Requirement",
        )

    assert outcome == "skipped:no_agent_key"
    summarize.assert_not_called()


# ---------------------------------------------------------------------------
# Service: upsert per type, unchanged input
# ---------------------------------------------------------------------------


class _FakeProvider:
    PROVIDER_NAME = "fake"
    MODEL_NAME = "fake-model"

    def __init__(self) -> None:
        self.complete = MagicMock(return_value="Eine Zusammenfassung.")

    def __call__(self, *args, **kwargs):  # pragma: no cover - not a callable API
        return self.complete(*args, **kwargs)


def test_summarize_artifact_type_upserts_one_row_per_type(settings, tenant):
    workspace = _workspace(tenant)
    TenantContext.set_tenant(tenant.id)
    try:
        make_requirement(workspace, title="Login")
        make_requirement(workspace, title="Logout")
    finally:
        TenantContext.clear_tenant()

    provider = _FakeProvider()
    service = ArtifactSummaryService()
    ctx = SimpleNamespace(tenant_id=tenant.id, user_id=uuid.uuid4())

    with patch.object(
        ArtifactSummaryService,
        "_resolve_provider",
        staticmethod(lambda: (provider, "fake", None)),
    ), patch(
        "application.ai_derivation_service.AiDerivationService._resolve_and_render",
        return_value="PROMPT",
    ):
        first = service.summarize_artifact_type(ctx, workspace.id, "Requirement")
        second = service.summarize_artifact_type(ctx, workspace.id, "Requirement")

    assert first == "summarized"
    assert second == "skipped:unchanged"
    assert provider.complete.call_count == 1
    TenantContext.set_tenant(tenant.id)
    try:
        row = ArtifactSummary.objects.get(workspace=workspace, artifact_type="Requirement")
    finally:
        TenantContext.clear_tenant()
    assert row.summary_kind == TYPE_ROSTER_KIND
    assert row.token_usage and row.token_usage > 0
    assert row.input_digest["item_count"] == 2
    assert row.status == ArtifactSummary.Status.OK
    assert row.trigger == ArtifactSummary.Trigger.PERIODIC


# ---------------------------------------------------------------------------
# Beat entry
# ---------------------------------------------------------------------------


def test_beat_entry_exists_only_with_the_flag(settings):
    from reqogniloom.settings import _artifact_summary_beat_entry

    assert _artifact_summary_beat_entry(
        enabled=False, tick_minutes=60, min_interval_minutes=60
    ) is None
    assert _artifact_summary_beat_entry(
        enabled=True, tick_minutes=0, min_interval_minutes=60
    ) is None


def test_beat_entry_clamps_the_tick(settings):
    from reqogniloom.settings import _artifact_summary_beat_entry

    entry = _artifact_summary_beat_entry(
        enabled=True, tick_minutes=30, min_interval_minutes=60
    )

    assert entry is not None
    assert entry["task"] == "application.artifact_summary_sweep_tick"
    assert entry["schedule"].total_seconds() == 3600


# ---------------------------------------------------------------------------
# Workspace fields
# ---------------------------------------------------------------------------


def test_workspace_summary_fields_have_documented_defaults(tenant):
    workspace = _workspace(tenant)

    assert workspace.summary_trace_depth == 1
    assert workspace.summary_scopes == []
    assert workspace.summary_sweep_interval_minutes == 1440
