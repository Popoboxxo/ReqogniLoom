"""ALLOC-P1 — a Requirement with several active allocations (ADR-028 D9).

ADR-027 lets the allocation decide a Requirement's tier. D9 allows a workspace
to permit more than one allocation (``allocation.cardinality = multiple``); in
that mode the tier follows the **leading** allocation (``is_primary``) and stays
``unresolved`` when none is marked. This rule makes the state visible: it
reports every Requirement with more than one active allocation, whatever the
workspace setting.

Severity comes from ``allocation.conflict_severity``:

* ``blocker`` -> :attr:`Severity.BLOCKER` (blocks the baseline gate),
* ``warning`` (default) -> :attr:`Severity.WARNING`,
* ``info`` -> :attr:`Severity.WARNING` as well. The audit vocabulary has only
  two severities; introducing a third would change every count consumer
  (badges, baseline gate, release reports) for a purely cosmetic level. The
  distinction the setting is meant to make is kept in the finding text.

The rule reads the ``Allocation`` objects, not the edges: the "leading" flag and
the status exist only there.
"""
from __future__ import annotations

from django.db.models import Count

from traceability.audit.registry import ALLOC_P1, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity


@register_rule
class AllocationMultiplicityRule(Rule):
    """Report Requirements with more than one active allocation."""

    rule_id = ALLOC_P1
    is_scope_aware = False
    title = "Requirement mit mehreren aktiven Allokationen"
    description = (
        "Ein Requirement ist auf mehr als ein Architekturelement alloziert. "
        "Bei allocation.cardinality=multiple entscheidet die führende "
        "Allokation (is_primary) über die Spezifikationsebene; ohne führende "
        "Kante bleibt sie unresolved. Der Befund macht den Zustand sichtbar."
    )
    standard_basis = "ADR-028 D9"
    how_to_fix = (
        "Entweder eine Allokation als führend markieren (is_primary) oder die "
        "überzähligen Allokationen zurückziehen."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Default severity; the workspace preference may raise it per finding."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> list[Finding]:
        from application.allocation_settings import (
            CARDINALITY_MULTIPLE,
            CONFLICT_SEVERITY_KEY,
            _value,
            cardinality_for,
        )
        from persistence.models import Allocation, AllocationStatus

        rows = (
            Allocation.unscoped.filter(
                tenant_id=context.tenant_id,
                status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
            )
            .values("requirement_artifact_id")
            .annotate(active=Count("id"))
            .filter(active__gt=1)
        )

        # Resolve the configured severity once; the message states the level
        # because the audit vocabulary has no separate INFO.
        configured = _value(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            key=CONFLICT_SEVERITY_KEY,
            default="warning",
        )
        severity = (
            Severity.BLOCKER if configured == "blocker" else Severity.WARNING
        )
        cardinality = cardinality_for(
            tenant_id=context.tenant_id, workspace_id=context.workspace_id
        )

        findings: list[Finding] = []
        for row in rows:
            requirement_artifact_id = row["requirement_artifact_id"]
            count = row["active"]
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=severity,
                    message=(
                        f"Requirement {requirement_artifact_id} has {count} "
                        f"active allocations (cardinality={cardinality}, "
                        f"configured severity={configured}). "
                        + (
                            "Only the leading allocation decides the tier."
                            if cardinality == CARDINALITY_MULTIPLE
                            else "This workspace allows exactly one allocation."
                        )
                    ),
                    artifact_ids=(str(requirement_artifact_id),),
                )
            )
        return findings
