"""DOC-P5 — Stale work state (Plan F F3-T8, #1374).

A `WorkItem` is the explicit agent state store (concept §9): "where does the
work stand, what is open, what comes next". The heartbeat A-3 stamps
``last_activity_at`` on every action, and the whole point of the heartbeat is
that an abandoned ``in_progress`` item becomes *visible* instead of silently
looking like active work. This rule is that visibility: an ``in_progress`` item
whose heartbeat is older than the workspace preset's
``work_item_stale_after_days`` threshold is reported as orphaned work state.

Tier: Standard + Extended (``_STANDARD_RULES``); Minimal maps to the empty rule
set, so a Minimal workspace never reports it (concept §6.6).

Severity: WARNING at both tiers it runs in (spec §11). Stale work state is
advisory — the work may legitimately be paused — so it must never block a
baseline. Severity comes exclusively from :meth:`severity_for_tier`; the
RuleEngine re-stamps every finding with it.

The threshold is read from the workspace preset, never a literal here
(spec §11 / RVW-2026-11-02-002-03). The rule is scope-agnostic: a work item
belongs to exactly one document and one tenant, so there is no baseline subtree
to resolve. It reads the model through the ``unscoped`` manager with an
explicit tenant filter (the audit infrastructure convention, mirrors
:mod:`traceability.audit.rules.document_references`).
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from traceability.audit.registry import DOC_P5, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity


@register_rule
class StaleWorkItemRule(Rule):
    """DOC-P5: an ``in_progress`` work item whose heartbeat went silent."""

    rule_id = DOC_P5
    is_scope_aware = False

    title = "Stale work state"
    description = (
        "A work item is still marked 'in_progress' but has not received any "
        "action (heartbeat) for longer than the preset's "
        "work_item_stale_after_days threshold. The work state is orphaned: "
        "an agent claimed the item and never continued or released it."
    )
    standard_ref = "Plan F F3-T8 / concept §9 (A-3)"
    remediation_hint = (
        "Continue the item (any write stamps the heartbeat), move it back to "
        "'todo' or into 'blocked' with a reason, or mark it 'done'/'dropped'."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """WARNING at Standard and Extended (spec §11) — advisory by design."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        from persistence.models import WorkItem
        from presets.services import get_preset
        from workflow import state_reader

        rows = list(
            WorkItem.unscoped.filter(
                tenant_id=context.tenant_id,
                workspace_id=context.workspace_id,
            ).values(
                "id",
                "artifact_id",
                "uid",
                "title",
                "last_activity_at",
                "created_at",
            )
        )
        # Short-circuit before any preset/policy read: a workspace without work
        # items cannot have stale work state, and the audit query budget
        # (#1385) must not pay for a rule that has nothing to inspect.
        if not rows:
            return []

        threshold_days = get_preset(context.workspace_id).work_item_stale_after_days
        cutoff = timezone.now() - timedelta(days=threshold_days)

        # ``current_states`` overlays soft deletes as ``"outdated"``, so a
        # deleted item can never be reported as stale work. An item without a
        # ``WorkflowItemState`` row is absent — it was never started, so it
        # cannot be an orphaned ``in_progress`` item either.
        states = state_reader.current_states(
            "WorkItem",
            [row["id"] for row in rows],
            tenant_id=context.tenant_id,
        )

        findings: list[Finding] = []
        for row in rows:
            if states.get(str(row["id"])) != "in_progress":
                continue
            # A missing heartbeat falls back to ``created_at``: an item that
            # was put into progress and never touched looks abandoned from the
            # moment it was created, and a NULL must not evade the rule.
            last_seen = row["last_activity_at"] or row["created_at"]
            if last_seen is None or last_seen > cutoff:
                continue
            label = row["uid"] or str(row["id"])
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    # Re-stamped by RuleEngine._run_rule with
                    # severity_for_tier(); the value here is a placeholder.
                    severity=Severity.WARNING,
                    message=(
                        f"[DOC-P5] Work item {label} ('{row['title']}') is "
                        f"still in_progress but its last activity was "
                        f"{last_seen.isoformat()}, more than "
                        f"{threshold_days} days ago — orphaned work state."
                    ),
                    artifact_ids=(str(row["artifact_id"]),),
                )
            )
        return findings


__all__ = ["StaleWorkItemRule"]
