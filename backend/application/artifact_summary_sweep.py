"""Periodic artifact-type summary sweep (issue #1793 / S5).

Wiring only — the summary itself stays in
:class:`~application.artifact_summary_service.ArtifactSummaryService`. This
module decides **whether** and **when** a (workspace, artifact type) scope may
run, and under whose identity.

Spec: ``docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md`` §6
and §9/E6/E8. The gates run in this order (first hit wins, result is a
``skipped:<reason>`` string):

1. ``ARTIFACT_SUMMARY_SWEEP_ENABLED`` is off (default)  -> ``flag_off``
2. the workspace interval is ``0`` or the scope is not due -> ``interval_off`` / ``not_due``
3. the summary-only day budget is spent (``SUMMARY_DAILY_TOKEN_LIMIT``) -> ``budget_exhausted``
4. no active agent API key for the tenant               -> ``no_agent_key``
5. the same scope ran within ``ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS`` -> ``throttled``

The sweep hangs on its **own** flag, independent of the on-demand
``ARTIFACT_SUMMARY_ENABLED`` (decided 2026-11-15). A beat row left over from an
older deployment keeps firing; the task therefore reads the flag again instead
of trusting the schedule dict.

``0`` interval means "off"; values below the global minimum are clamped, never
rejected (spec §9/E6). Only ids/type strings cross the Celery boundary — never
a credential (ADR-03).

``manual=True`` (the ``summary.refresh`` path of S6) keeps everything above
except the cadence: gates 1 and 2 (sweep flag, interval, "not due yet") are the
schedule, not the brakes, so an explicit caller request skips them while the
summary budget (3), the agent key (4) and the throttle (5) still apply. The
manual run hangs on ``ARTIFACT_SUMMARY_ENABLED`` instead of the sweep flag —
the two switches are independent by design.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from application.artifact_summary_service import (
    ArtifactSummaryService,
    summary_budget_exhausted,
)
from application.summary_support import TYPE_ROSTER_KIND, upsert_summary
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import ArtifactSummary, Workspace
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)

#: Wall-clock default when a workspace has no explicit interval.
DEFAULT_INTERVAL_MINUTES = 1440

#: Absolute lower bound for any interval (spec §9/E6).
MIN_INTERVAL_MINUTES = 60

#: Artifact types the periodic sweep may summarise (spec §6.2). Deliberately a
#: subset of ``artifact_indexer.SOURCES``: a trace link is an edge, not a
#: collection, and ``MainGoal`` is already an aggregation.
DEFAULT_SUMMARY_SCOPES: tuple[str, ...] = (
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "Adr",
    "Risk",
    "Issue",
    "ChangeRequest",
    "Goal",
    "Document",
    "WorkItem",
    "Icd",
)

_DEFAULT_SCOPE_SET = frozenset(DEFAULT_SUMMARY_SCOPES)


def _setting(name: str, default: Any) -> Any:
    return getattr(settings, name, default)


def sweep_enabled() -> bool:
    """Whether the periodic sweep may run at all (its own flag, default off)."""
    return bool(_setting("ARTIFACT_SUMMARY_SWEEP_ENABLED", False))


def agent_key_id() -> UUID | None:
    """Parse ``ARTIFACT_SUMMARY_AGENT_KEY_ID``; ``None`` when unset/invalid."""
    raw = str(_setting("ARTIFACT_SUMMARY_AGENT_KEY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        logger.warning(
            "ARTIFACT_SUMMARY_AGENT_KEY_ID is not a UUID; the summary sweep stays off."
        )
        return None


def min_interval_minutes() -> int:
    try:
        value = int(_setting("ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES", MIN_INTERVAL_MINUTES))
    except (TypeError, ValueError):
        value = MIN_INTERVAL_MINUTES
    return max(1, value)


def interval_for_workspace(workspace: Any) -> int:
    """Return the effective interval in minutes; ``0`` means disabled.

    ``None`` falls back to ``ARTIFACT_SUMMARY_INTERVAL_MINUTES``. A positive
    value below the global minimum is clamped (spec §9/E6); a non-positive one
    disables the sweep for this workspace.
    """
    raw = getattr(workspace, "summary_sweep_interval_minutes", None)
    if raw is None:
        raw = _setting("ARTIFACT_SUMMARY_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_MINUTES
    if value <= 0:
        return 0
    return max(min_interval_minutes(), value)


def resolve_summary_scopes(workspace: Any) -> tuple[str, ...]:
    """Return the workspace's configured types, or the twelve defaults.

    Unknown type names are ignored with a warning rather than allowed to reach
    the prompt: the type list is tenant-editable JSON, so a typo must not turn
    a sweep into a source of noise (spec §6.2, §12/O10).
    """
    raw = getattr(workspace, "summary_scopes", None) or []
    if not isinstance(raw, (list, tuple)):
        logger.warning(
            "Workspace %s has a non-list summary_scopes; using defaults.",
            getattr(workspace, "id", "?"),
        )
        return DEFAULT_SUMMARY_SCOPES
    scopes: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        if entry not in _DEFAULT_SCOPE_SET:
            logger.warning(
                "Workspace %s lists unknown summary scope %r; ignored.",
                getattr(workspace, "id", "?"),
                entry,
            )
            continue
        if entry not in scopes:
            scopes.append(entry)
    return tuple(scopes) if scopes else DEFAULT_SUMMARY_SCOPES


def _throttle_key(artifact_type: str, workspace_id: UUID | str) -> str:
    return f"artifact_summary:sweep:{artifact_type}:{workspace_id}"


def _agent_context(tenant_id: UUID, workspace_id: UUID) -> AuthContext | None:
    """Build the agent identity the sweep writes under, or ``None``.

    Mirrors ``QualityAutoAssessor._agent_context``: an automatic run must never
    write under a real user's identity, so no active agent key means no run.
    """
    from auth_tenancy.models import ApiKey
    from auth_tenancy.services.authorization import AuthorizationService

    key_id = agent_key_id()
    if key_id is None:
        logger.warning("summary sweep skipped: ARTIFACT_SUMMARY_AGENT_KEY_ID is unset.")
        return None
    key = (
        ApiKey.objects.filter(
            id=key_id, principal_type="agent", revoked_at__isnull=True
        )
        .select_related("user")
        .first()
    )
    if key is None:
        logger.warning("summary sweep skipped: configured agent key is missing or revoked.")
        return None

    roles = AuthorizationService().active_roles_for(
        user_id=key.user_id, workspace_id=workspace_id
    )
    return AuthContext(
        user_id=key.user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=key.id,
        workspace_id=workspace_id,
        actor_type="agent",
        agent_label=key.agent_label or "",
        scope=key.scope,
        api_key_workspace_ids=tuple(key.workspace_ids or ()),
    )


def _mark_budget_exhausted(workspace: Workspace, artifact_type: str) -> None:
    """Record the budget reason on an existing scope without inventing a row."""
    existing = ArtifactSummary.objects.filter(
        workspace=workspace,
        summary_kind=TYPE_ROSTER_KIND,
        artifact_type=artifact_type,
    ).first()
    if existing is None:
        return
    upsert_summary(
        workspace=workspace,
        summary_kind=TYPE_ROSTER_KIND,
        artifact_type=artifact_type,
        values={
            "text": existing.text,
            "content_hash": existing.content_hash,
            "input_digest": existing.input_digest,
            "prompt_slot": existing.prompt_slot,
            "provider": existing.provider,
            "trigger": ArtifactSummary.Trigger.PERIODIC,
            "status": ArtifactSummary.Status.SKIPPED,
            "reason": ArtifactSummary.Reason.BUDGET_EXHAUSTED,
        },
    )


class ArtifactSummarySweeper:
    """Decides and executes one periodic summary run for one type scope."""

    def __init__(self, service: ArtifactSummaryService | None = None) -> None:
        self._service = service or ArtifactSummaryService()

    def run_for_scope(
        self,
        *,
        tenant_id: UUID | str | None,
        workspace_id: UUID | str,
        artifact_type: str,
        trigger: str = ArtifactSummary.Trigger.PERIODIC.value,
        manual: bool = False,
    ) -> str:
        """Run the gates, then summarise one (workspace, type) scope.

        ``manual=True`` is the ``summary.refresh`` path (issue #1793 / S6): the
        caller asked *now*, so the workspace cadence (global sweep flag,
        per-workspace interval, the "not due yet" check) is deliberately
        bypassed. Every brake that protects the budget stays in force — the
        on-demand switch ``ARTIFACT_SUMMARY_ENABLED``, the summary-only day
        budget, the agent key and the min-interval throttle. The two switches
        are independent by design: the sweep flag says "may this happen
        unattended", the on-demand flag says "may this happen at all".

        Returns ``summarized|skipped:<reason>|failed``.
        """
        if manual:
            if not bool(_setting("ARTIFACT_SUMMARY_ENABLED", False)):
                return "skipped:flag_off"
        elif not sweep_enabled():
            return "skipped:flag_off"
        if not tenant_id:
            logger.warning("summary sweep skipped: no tenant anchor.")
            return "skipped:no_agent_key"

        tenant_uuid = UUID(str(tenant_id))
        workspace_uuid = UUID(str(workspace_id))
        previous = TenantContext.get_tenant() if TenantContext.is_set() else None
        TenantContext.set_tenant(tenant_uuid)
        try:
            workspace = Workspace.objects.filter(id=workspace_uuid).first()
            if workspace is None:
                return "skipped:no_workspace"

            interval = interval_for_workspace(workspace)
            if interval == 0 and not manual:
                return "skipped:interval_off"

            existing = ArtifactSummary.objects.filter(
                workspace=workspace,
                summary_kind=TYPE_ROSTER_KIND,
                artifact_type=artifact_type,
            ).first()
            if (
                not manual
                and trigger
                in (
                    ArtifactSummary.Trigger.PERIODIC.value,
                    ArtifactSummary.Trigger.PERIODIC,
                )
                and existing is not None
            ):
                due_at = existing.modified_at + timedelta(minutes=interval)
                if timezone.now() < due_at:
                    return "skipped:not_due"

            if summary_budget_exhausted():
                _mark_budget_exhausted(workspace, artifact_type)
                return "skipped:budget_exhausted"

            ctx = _agent_context(tenant_uuid, workspace_uuid)
            if ctx is None:
                return "skipped:no_agent_key"

            cache_key = _throttle_key(artifact_type, workspace_uuid)
            if cache.get(cache_key):
                return "skipped:throttled"
            # Set before the call: a hanging provider must not let a second
            # run start in parallel and pay twice (spec §6.4).
            cache.set(
                cache_key,
                1,
                timeout=max(
                    1,
                    int(_setting("ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS", 3600)),
                ),
            )
            try:
                outcome = self._service.summarize_artifact_type(
                    ctx,
                    workspace_uuid,
                    artifact_type,
                    trigger=trigger,
                )
            except Exception:  # noqa: BLE001 - one scope must not abort the sweep
                logger.exception(
                    "summary sweep failed for %s/%s", workspace_uuid, artifact_type
                )
                cache.delete(cache_key)
                return "failed"

            if outcome == "summarized":
                return "summarized"
            if outcome == "failed":
                cache.delete(cache_key)
                return "failed"
            if outcome == "skipped:budget_exhausted":
                return "skipped:budget_exhausted"
            # Any other skip (unchanged/empty/unknown) is a real skip, but a
            # cache hit marker would now throttle the *content* of a later
            # change; keep the throttle only after a genuine run.
            cache.delete(cache_key)
            return outcome if outcome.startswith("skipped:") else "skipped:unknown"
        finally:
            if previous is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous)

    def run_sweep(self, tenant_id: UUID | str) -> dict[str, int | bool]:
        """Summarise the due scopes of one tenant, bounded by the global batch.

        The worker runs outside any request thread, so it must arm **both**
        isolation layers before the first query: ``set_request_tenant`` (ORM
        thread-local *and* ``SET app.current_tenant`` for Postgres RLS), not the
        bare ``TenantContext``. With only the thread-local set, RLS filters every
        row away and the tick silently reports zeros while scopes are due.
        """
        counts: dict[str, int | bool] = {
            "summarized": 0,
            "skipped": 0,
            "budget": 0,
            "failed": 0,
            "disabled": False,
        }
        if not sweep_enabled():
            counts["disabled"] = True
            return counts

        from persistence.middleware import clear_request_tenant, set_request_tenant

        tenant_uuid = UUID(str(tenant_id))
        # #522: under CELERY_TASK_ALWAYS_EAGER the task body may run inline on a
        # thread that already carries a tenant; snapshot it so the teardown does
        # not clear the caller's isolation.
        tenant_was_set = TenantContext.is_set()
        previous = TenantContext.get_tenant() if tenant_was_set else None
        try:
            set_request_tenant(tenant_uuid)
            now = timezone.now()
            workspaces = list(
                Workspace.objects.filter(tenant_id=tenant_uuid, is_active=True)
            )
            latest: dict[tuple[UUID, str], ArtifactSummary] = {
                (row.workspace_id, row.artifact_type): row
                for row in ArtifactSummary.objects.filter(
                    tenant_id=tenant_uuid, summary_kind=TYPE_ROSTER_KIND
                )
            }
            candidates: list[tuple[Any, Workspace, str]] = []
            for workspace in workspaces:
                interval = interval_for_workspace(workspace)
                if interval == 0:
                    continue
                for artifact_type in resolve_summary_scopes(workspace):
                    row = latest.get((workspace.id, artifact_type))
                    if row is not None and now < row.modified_at + timedelta(
                        minutes=interval
                    ):
                        continue
                    candidates.append(
                        (row.modified_at if row is not None else None, workspace, artifact_type)
                    )

            # Never summarised first, then the oldest stand (spec §6.4).
            candidates.sort(
                key=lambda entry: (
                    entry[0] is not None,
                    entry[0] or now,
                    str(entry[1].id),
                    entry[2],
                )
            )
            batch = max(
                1, int(_setting("ARTIFACT_SUMMARY_SWEEP_BATCH", 25))
            )
            for _updated_at, workspace, artifact_type in candidates[:batch]:
                outcome = self.run_for_scope(
                    tenant_id=tenant_uuid,
                    workspace_id=workspace.id,
                    artifact_type=artifact_type,
                    trigger=ArtifactSummary.Trigger.PERIODIC.value,
                )
                if outcome == "summarized":
                    counts["summarized"] += 1
                elif outcome == "failed":
                    counts["failed"] += 1
                elif outcome == "skipped:budget_exhausted":
                    counts["budget"] += 1
                else:
                    counts["skipped"] += 1
            return counts
        finally:
            if tenant_was_set and previous is not None:
                # Restore the caller's tenant on *both* layers.
                try:
                    set_request_tenant(previous)
                except Exception:  # noqa: BLE001 - teardown must not mask the cause
                    logger.exception(
                        "summary sweep could not restore the previous tenant context"
                    )
            elif TenantContext.is_set():
                try:
                    clear_request_tenant()
                except Exception:  # noqa: BLE001 - teardown must not mask the cause
                    logger.exception(
                        "summary sweep could not reset the tenant context"
                    )


def run_sweep_all() -> dict[str, int | bool]:
    """Run the sweep for every tenant; the tick task's entry point."""
    totals: dict[str, int | bool] = {
        "summarized": 0,
        "skipped": 0,
        "budget": 0,
        "failed": 0,
        "disabled": False,
    }
    if not sweep_enabled():
        totals["disabled"] = True
        return totals

    from persistence.models import Tenant

    sweeper = ArtifactSummarySweeper()
    for tenant_id in Tenant.objects.values_list("id", flat=True).iterator():
        counts = sweeper.run_sweep(tenant_id)
        for key in ("summarized", "skipped", "budget", "failed"):
            totals[key] += int(counts.get(key, 0))
    return totals


__all__ = [
    "DEFAULT_INTERVAL_MINUTES",
    "DEFAULT_SUMMARY_SCOPES",
    "MIN_INTERVAL_MINUTES",
    "ArtifactSummarySweeper",
    "agent_key_id",
    "interval_for_workspace",
    "min_interval_minutes",
    "resolve_summary_scopes",
    "run_sweep_all",
    "sweep_enabled",
]
