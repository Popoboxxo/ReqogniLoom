"""
IFC-001 — Interface coverage: every Icd is anchored to an ArchitectureElement.

#1268. Not part of the original §2.2 Pflichtmatrix: it is the interface-coverage
rule the ICD (Interface Control Document) feature was missing. A5 property of
``Icd`` is that it *describes the interface between two architecture elements*
(``source_element_id``/``target_element_id``), but the trace graph only carried
the ``decomposes`` link between those two elements
(``icd/traceability_connector.py``) — the ICD itself was reachable from the
architecture only if a user hand-authored a link. This rule makes that gap
visible: an ICD with no ``references`` link to any ArchitectureElement is not
anchored in the architecture.

Tier: Standard + Extended (``_STANDARD_RULES``). Minimal maps to the empty rule
set, so a Minimal workspace never runs it.

Severity: always WARNING. ``Rule.severity_for_tier`` defaults to BLOCKER, and
the RuleEngine re-stamps *every* finding with it
(``traceability.audit.rule_engine.RuleEngine._run_rule``). Shipping this rule as
a BLOCKER would retroactively block the baseline gate in every existing
workspace that already contains ICDs created before #1268 (they carry no
``references`` link yet) — the #581 calibration break. The rule is therefore
advisory and surfaces the gap through the report/metrics; escalation to BLOCKER
is a separate decision.

Direction: the link may be written in either direction and with either anchor
role. The catalog's ``references`` pairs cover ``("*", "Icd")``, i.e. an
ArchitectureElement (or Requirement) *sourcing* a link to the Icd; the connector
writes that direction. The rule reads the edge without assuming a direction so a
hand-authored ``Icd -> ArchitectureElement`` reference counts too.

This rule does NOT re-implement endpoint-type legality — that is
``link_types.catalog.validate_link_pair`` territory, enforced at link-creation
time. It only checks *existence* of the anchoring link at audit time.

Follow-up (documented, not implemented here): a dedicated interface-coverage
metric (anchored ICDs / total ICDs) is a separate ``se_metrics`` read-model
work item. This rule deliberately does not touch ``se_metrics`` — interface
coverage is surfaced through the IFC-001 findings until that metric lands.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Set

from traceability.audit.registry import IFC_001, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity
from traceability.types import LinkType
from workflow.services import outdated_item_ids


def _active_icds(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: name}`` for the workspace's active ICDs.

    "Active" excludes soft-deleted rows via ``workflow.services.outdated_item_ids``
    — ``Icd`` is a registered artifact-backed type, so a deleted ICD cannot be
    "unanchored". Tenant/workspace are supplied explicitly by the engine, so the
    query uses ``unscoped`` (the audit infrastructure convention; mirrors
    ``AuditContext.iter_trace_links``).
    """
    from icd.models import Icd

    qs = (
        Icd.unscoped.filter(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
        )
        .exclude(
            id__in=outdated_item_ids("Icd", tenant_id=context.tenant_id)
        )
        .values("artifact_id", "name")
    )
    return {
        str(row["artifact_id"]): row["name"]
        for row in qs
        if row["artifact_id"] is not None
    }


def _active_architecture_element_ids(context: AuditContext) -> FrozenSet[str]:
    """Return the artifact-id set of the workspace's active ArchitectureElements."""
    from persistence.models import ArchitectureElement

    qs = (
        ArchitectureElement.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
        )
        .exclude(
            id__in=outdated_item_ids(
                "ArchitectureElement", tenant_id=context.tenant_id
            )
        )
        .values_list("artifact_id", flat=True)
    )
    return frozenset(str(artifact_id) for artifact_id in qs)


@register_rule
class IcdAnchoredInArchitectureRule(Rule):
    """IFC-001: every Icd carries a ``references`` link to an ArchitectureElement."""

    rule_id = IFC_001
    is_scope_aware = False

    title = "ICD not anchored in the architecture"
    description = (
        "Every Interface Control Document must be reachable from the "
        "architecture through a 'references' link to at least one "
        "ArchitectureElement. An ICD whose interface is described in isolation "
        "cannot be traced from the system decomposition."
    )
    standard_ref = "UMSETZUNGSPLAN_SYSENG_2.0.md (interface coverage, #1268)"
    remediation_hint = (
        "Recreate the ICD or add a 'references' link between the ICD and one of "
        "its source/target ArchitectureElements."
    )

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — advisory interface coverage, never a baseline block.

        See the module docstring: a BLOCKER here would retroactively block every
        workspace whose ICDs predate the anchoring connector (#1268). Escalation
        is a separate decision and changes exactly this method.
        """
        return Severity.WARNING

    def check(self, context: AuditContext) -> List[Finding]:
        icds = _active_icds(context)
        if not icds:
            return []

        arch_ids = _active_architecture_element_ids(context)
        icd_ids = frozenset(icds)

        anchored: Set[str] = set()
        for link in context.iter_trace_links():
            if link["link_type"] != LinkType.REFERENCES.value:
                continue
            source_id, target_id = link["source_id"], link["target_id"]
            if target_id in icd_ids and source_id in arch_ids:
                anchored.add(target_id)
            if source_id in icd_ids and target_id in arch_ids:
                anchored.add(source_id)

        findings: List[Finding] = []
        for icd_id in sorted(icd_ids):
            if icd_id in anchored:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    # Re-stamped by RuleEngine._run_rule with
                    # severity_for_tier(); the value here is a placeholder.
                    severity=Severity.WARNING,
                    message=(
                        f"[IFC-001] ICD '{icds[icd_id]}' ({icd_id}) has no "
                        "'references' link to any ArchitectureElement — the "
                        "interface is not anchored in the architecture."
                    ),
                    artifact_ids=(icd_id,),
                )
            )
        return findings


__all__ = ["IcdAnchoredInArchitectureRule"]
