"""VAL-P1 — every active StakeholderNeed contributes to an active Goal (#402).

Cluster-5 spec section 5.3. The validation pillar (#402) requires that the
stakeholder layer is actually connected to the goal layer: a StakeholderNeed
that satisfies no Goal is a requirement nobody asked for.

Tier: Extended only, alongside the other stricter SE-formalism rules
(TRACE-P3/P5/P7, ARCH-003, VERIF-P8, CONS-P11). Minimal and Standard
workspaces do not maintain a goal layer at all (ADR-04, configurable rigor).

Severity: always WARNING. ``Rule.severity_for_tier`` defaults to BLOCKER, and
the RuleEngine re-stamps *every* finding with ``rule.severity_for_tier(tier)``
(``traceability.audit.rule_engine.RuleEngine._run_rule``) — the
``Finding(severity=...)`` value below is documentation of the rule's intent,
not the gate-effective severity. The override is therefore the **only**
switch that matters: ``AuditService.blocking_findings`` filters on BLOCKER, and
``BaselineFacade._enforce_audit_gate`` consumes only that method. Shipping this
rule as a BLOCKER would retroactively block the baseline build in every
existing Extended workspace that uses Goals; escalation to BLOCKER is a
separate release step (spec F8) and is done by changing
:meth:`ValidationGoalsRule.severity_for_tier` alone.

Double gate (spec section 5.3): the rule returns ``[]`` unless

1. the workspace resolves *and* has ``goals_enabled=True`` (fail-open — a
   workspace that cannot be resolved is not audited), and
2. at least one active Goal exists in the workspace.

A workspace with 2735 requirements and 0 Goals therefore never gets a finding.
"""
from __future__ import annotations

from typing import Dict, List, Set

from persistence.models import Goal, StakeholderNeed, Workspace
from traceability.audit.registry import VAL_P1, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity
from traceability.types import LinkType
from workflow.services import outdated_item_ids


def _goals_enabled(context: AuditContext) -> bool:
    """Return whether the audited workspace has Goals enabled (activation gate).

    ``unscoped`` + an explicit ``tenant_id`` is the audit infrastructure's
    convention (tenant/workspace are supplied by the engine, not by a
    thread-local). A workspace that cannot be resolved — wrong id, or a
    context without tenant arming — yields ``False`` and the rule returns
    early (fail-open, spec review finding m10).
    """
    return Workspace.unscoped.filter(
        id=context.workspace_id,
        tenant_id=context.tenant_id,
        goals_enabled=True,
    ).exists()


def _active_goal_artifact_ids(context: AuditContext) -> Set[str]:
    """Return the artifact ids of the workspace's active Goals.

    "Active" is ``Artifact.lifecycle_status != "outdated"`` — the single
    soft-delete flag (Datenmodell-Konsolidierung Phase 4, D-3). ``Goal`` is a
    registered artifact-backed type, so :func:`outdated_item_ids` resolves it.
    """
    qs = (
        Goal.unscoped.filter(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
        )
        .exclude(id__in=outdated_item_ids("Goal", tenant_id=context.tenant_id))
        .values_list("artifact_id", flat=True)
    )
    return {str(artifact_id) for artifact_id in qs}


def _active_stakeholder_needs(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for the workspace's active needs."""
    qs = StakeholderNeed.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(
        id__in=outdated_item_ids("StakeholderNeed", tenant_id=context.tenant_id)
    )
    return {
        str(row["artifact_id"]): row["title"]
        for row in qs.values("artifact_id", "title")
    }


@register_rule
class ValidationGoalsRule(Rule):
    """VAL-P1: every active StakeholderNeed satisfies >=1 active Goal."""

    rule_id = VAL_P1
    is_scope_aware = False

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — VAL-P1 is advisory and must not gate a baseline.

        This is the gate-effective severity (the engine re-stamps findings
        with it); see the module docstring. Escalation to BLOCKER is spec
        follow-up F8 and changes exactly this method.
        """
        return Severity.WARNING

    def check(self, context: AuditContext) -> List[Finding]:
        # Gate 1 (fail-open): Goals must be enabled in this workspace.
        if not _goals_enabled(context):
            return []

        # Gate 2: a workspace without any active Goal has no goal layer to
        # trace to — flagging every need there would be noise, not signal.
        active_goal_ids = _active_goal_artifact_ids(context)
        if not active_goal_ids:
            return []

        needs = _active_stakeholder_needs(context)
        if not needs:
            return []

        satisfies_targets: Dict[str, Set[str]] = {}
        for link in context.iter_trace_links():
            if link["link_type"] != LinkType.SATISFIES.value:
                continue
            satisfies_targets.setdefault(link["source_id"], set()).add(
                link["target_id"]
            )

        findings: List[Finding] = []
        for need_id in sorted(needs):
            targets = satisfies_targets.get(need_id, set())
            if targets & active_goal_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[VAL-P1] StakeholderNeed '{needs[need_id]}' ({need_id}) "
                        "trägt zu keinem aktiven Goal bei — 'satisfies'-Link "
                        "auf ein Goal fehlt."
                    ),
                    artifact_ids=(need_id,),
                )
            )
        return findings


__all__ = ["ValidationGoalsRule"]
