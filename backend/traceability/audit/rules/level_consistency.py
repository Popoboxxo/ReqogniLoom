"""
CONS-P12 / CONS-P13 — V-model level consistency (#1289).

``Requirement.level`` is derived (ADR-005): from the requirement hierarchy on
every hierarchy write. #1289 adds the *architecture* axis (an ``allocated-to``
link to an ``ArchitectureElement`` maps the element's tree depth to a cascade
level) and two advisory rules that make the resulting gaps visible:

* **CONS-P12** — a Requirement whose ``level`` is NULL: neither the requirement
  hierarchy nor an architecture allocation determines a level. This is the
  honest "not derivable" state (never guessed), reported so it can be resolved
  by hand or by adding a missing allocation.
* **CONS-P13** — a Requirement whose stored ``level`` disagrees with the level
  implied by its architecture allocation depth. A conflict between the two
  sources means one of them is stale.

Both are **advisory (WARNING) at every tier they run in**: they describe a
corpus gap, not a broken artifact, and a BLOCKER would retroactively block the
baseline gate of every workspace whose Requirements predate the derivation
(ADR-005) or the allocation (the #581 calibration lesson). CONS-P12 runs at
standard + extended; the stricter architecture-conflict rule (CONS-P13) is
extended-only.

The rules read the graph through the shared :class:`AuditContext` and the
existing derivation helpers — they never re-implement hierarchy or architecture
resolution.
"""
from __future__ import annotations

from traceability.audit.hierarchy import architecture_allocated_levels
from traceability.audit.registry import CONS_P12, CONS_P13, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity
from workflow.services import outdated_item_ids


def _active_requirements(context: AuditContext) -> dict[str, dict]:
    """Return ``{artifact_id: {"uid", "level"}}`` for the workspace's active rows.

    "Active" excludes soft-deleted rows via ``workflow.services.outdated_item_ids``
    (the same convention ``rules/interface_coverage.py`` uses). Tenant/workspace
    are supplied explicitly by the engine, so this reads ``unscoped`` (audit
    infrastructure convention).
    """
    from persistence.models import Requirement

    qs = (
        Requirement.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
        )
        .exclude(id__in=outdated_item_ids("Requirement", tenant_id=context.tenant_id))
        .values("artifact_id", "uid", "level")
    )
    return {
        str(row["artifact_id"]): {"uid": row["uid"], "level": row["level"]}
        for row in qs
        if row["artifact_id"] is not None
    }


def _architecture_levels(context: AuditContext) -> dict[str, int | None]:
    """Return ``{requirement_artifact_id: architecture_level}`` for the tenant.

    Thin string-keyed projection of
    :func:`traceability.audit.hierarchy.architecture_allocated_levels` so the
    rules can look a requirement up by the (string) artifact id the audit graph
    uses. Only Requirements allocated to at least one element appear.
    """
    levels = architecture_allocated_levels(context.tenant_id)
    return {str(artifact_id): level for artifact_id, level in levels.items()}


@register_rule
class RequirementLevelNullRule(Rule):
    """CONS-P12: a Requirement whose V-model level is NULL."""

    rule_id = CONS_P12
    is_scope_aware = False

    title = "Requirement has no V-model level"
    description = (
        "Requirement.level is derived from the requirement hierarchy and from an "
        "'allocated-to' architecture allocation. A NULL level means neither "
        "source determines one — the requirement sits in no V-model tier, which "
        "makes level-based SE reports incomplete."
    )
    standard_ref = "ADR-005 / #1289 (derived V-model level)"
    remediation_hint = (
        "Decompose the requirement under a parent, allocate it to an "
        "ArchitectureElement, or set an explicit manual override."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — a corpus gap, never a baseline block (#581 lesson)."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        requirements = _active_requirements(context)
        findings: list[Finding] = []
        for artifact_id in sorted(requirements):
            row = requirements[artifact_id]
            if row["level"] is not None:
                continue
            label = row["uid"] or artifact_id
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[CONS-P12] Requirement '{label}' ({artifact_id}) has a "
                        "NULL V-model level — no hierarchy parent and no "
                        "'allocated-to' architecture allocation determine one."
                    ),
                    artifact_ids=(artifact_id,),
                )
            )
        return findings


@register_rule
class RequirementLevelArchitectureMismatchRule(Rule):
    """CONS-P13: ``level`` disagrees with the architecture allocation depth."""

    rule_id = CONS_P13
    is_scope_aware = False

    title = "Requirement level contradicts architecture depth"
    description = (
        "The stored Requirement.level must agree with the V-model level implied "
        "by the depth of the ArchitectureElement the requirement is allocated "
        "to. A disagreement means the level or the allocation is stale."
    )
    standard_ref = "ADR-005 / #1289 (architecture depth -> cascade level)"
    remediation_hint = (
        "Re-derive the level (move the requirement or re-run the level backfill) "
        "or correct the allocation to an element at the intended depth."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — advisory conflict report, never a baseline block."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        requirements = _active_requirements(context)
        if not requirements:
            return []

        architecture_levels = _architecture_levels(context)
        findings: list[Finding] = []
        for artifact_id in sorted(architecture_levels):
            architecture_level = architecture_levels[artifact_id]
            if architecture_level is None:
                continue
            row = requirements.get(artifact_id)
            if row is None or row["level"] is None:
                continue
            if row["level"] == architecture_level:
                continue
            label = row["uid"] or artifact_id
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[CONS-P13] Requirement '{label}' ({artifact_id}) has "
                        f"level={row['level']} but its architecture allocation "
                        f"implies level={architecture_level}."
                    ),
                    artifact_ids=(artifact_id,),
                )
            )
        return findings


__all__ = [
    "RequirementLevelArchitectureMismatchRule",
    "RequirementLevelNullRule",
]
