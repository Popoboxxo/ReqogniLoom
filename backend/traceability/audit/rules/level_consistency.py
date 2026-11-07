"""
CONS-P12 / CONS-P13 — requirement tier consistency (P2, V4/V6/B10).

``Requirement.tier_key`` is the stable ladder key computed leaf-relative from
the workspace's tier ladder; ``Requirement.level`` is its **permanent integer
alias** (position + 1) and ``Requirement.level_source`` records where the value
came from (``derived_allocation``, ``derived_hierarchy``, ``derived_type``,
``unresolved`` or ``manual``). There is no fixed 1..4 V-model assumption any
more — the ladder is per workspace and of arbitrary length (V4).

Two advisory rules make the resulting gaps visible:

* **CONS-P12** — a Requirement whose tier is not determinable: its
  ``level_source`` is ``unresolved`` and/or its ``level`` alias is NULL. That is
  the honest "no allocation, no derivable parent, no type default" state (never
  guessed), reported so it can be resolved by hand or by adding a missing
  allocation/parent.
* **CONS-P13** — a Requirement whose ``level_source`` is empty/None. Every
  active Requirement must carry a provenance value: an empty source means the
  leaf-relative recompute never ran for the row (or a direct ORM/import write
  bypassed it), which is a data-integrity gap independent of the tier itself.

Both are **advisory (WARNING) at every tier they run in**: they describe a
corpus gap, not a broken artifact, and a BLOCKER would retroactively block the
baseline gate of every workspace whose Requirements predate the derivation
(ADR-005) or the ladder (P2) — the #581 calibration lesson. CONS-P12 runs at
standard + extended; the stricter data-integrity guard (CONS-P13) is
extended-only.

The rules read the graph through the shared :class:`AuditContext`; they never
re-implement hierarchy or architecture resolution (the old CONS-P13 compared
``level`` with architecture depth, which the leaf-relative ladder retired).
"""
from __future__ import annotations

from persistence.models import RequirementLevelSource
from traceability.audit.registry import CONS_P12, CONS_P13, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity
from workflow.services import outdated_item_ids


def _active_requirements(context: AuditContext) -> dict[str, dict]:
    """Return ``{artifact_id: {"uid", "level", "level_source"}}`` for active rows.

    Memoised on the audit context (#1385): CONS-P12 and CONS-P13 both project
    the same rows, so the query runs once per engine context.
    """
    return context.memoize(
        "level_consistency.active_requirements",
        lambda: _compute_active_requirements(context),
    )


def _compute_active_requirements(context: AuditContext) -> dict[str, dict]:
    """Uncached query body of :func:`_active_requirements`.

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
        .values("artifact_id", "uid", "level", "level_source")
    )
    return {
        str(row["artifact_id"]): {
            "uid": row["uid"],
            "level": row["level"],
            "level_source": row["level_source"],
        }
        for row in qs
        if row["artifact_id"] is not None
    }


@register_rule
class RequirementLevelNullRule(Rule):
    """CONS-P12: a Requirement whose tier is not determinable."""

    rule_id = CONS_P12
    is_scope_aware = False

    title = "Requirement has no determinable tier"
    description = (
        "A Requirement's tier is computed leaf-relative from its allocation, "
        "its derivable parent or a type default. 'unresolved' (with a NULL "
        "level alias) means none of those sources determines one — the "
        "requirement sits in no ladder position, which makes tier-based SE "
        "reports incomplete."
    )
    standard_ref = "P2 V4/V6 / B10 (leaf-relative tier ladder)"
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
            if (
                row["level"] is not None
                and row["level_source"] != RequirementLevelSource.UNRESOLVED
            ):
                continue
            label = row["uid"] or artifact_id
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[CONS-P12] Requirement '{label}' ({artifact_id}) has no "
                        "determinable tier — no allocation, no derivable parent "
                        "and no type default determine one."
                    ),
                    artifact_ids=(artifact_id,),
                )
            )
        return findings


@register_rule
class RequirementLevelSourceMissingRule(Rule):
    """CONS-P13: an active Requirement has no ``level_source`` provenance."""

    rule_id = CONS_P13
    is_scope_aware = False

    title = "Requirement has no level source"
    description = (
        "Every active Requirement must carry a level_source "
        "(derived_allocation, derived_hierarchy, derived_type, unresolved or "
        "manual). An empty source means the leaf-relative tier recompute never "
        "ran for the row, or a direct ORM/import write bypassed it — a "
        "data-integrity gap independent of the tier value itself."
    )
    standard_ref = "P2 V4/V6 / B10 (tier provenance)"
    remediation_hint = (
        "Re-run the tier recompute for the workspace (it writes level_source "
        "for every row), or set the source explicitly."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — a data-integrity guard, never a baseline block."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        requirements = _active_requirements(context)
        findings: list[Finding] = []
        for artifact_id in sorted(requirements):
            row = requirements[artifact_id]
            if row["level_source"]:
                continue
            label = row["uid"] or artifact_id
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[CONS-P13] Requirement '{label}' ({artifact_id}) has no "
                        "level_source — its tier provenance is empty."
                    ),
                    artifact_ids=(artifact_id,),
                )
            )
        return findings


__all__ = [
    "RequirementLevelNullRule",
    "RequirementLevelSourceMissingRule",
]
