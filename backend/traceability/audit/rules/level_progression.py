"""
CONS-P11 — V-model cascade level progression along the decomposition graph.

SYSTEMAUDIT_2026-08-27 P1-9. This rule is **not** part of the original
UMSETZUNGSPLAN_SYSENG_2.0.md §2.2 Pflichtmatrix; it was added together with the
``persistence.models.RequirementLevel`` realignment, which is also what made the
check meaningful in the first place.

What it checks
--------------
Decomposition moves exactly one level down the cascade. So for every hierarchy
edge ``parent --> child`` between two Requirements, ``child.level`` must be
``parent.level + 1``. Anything else — a skipped tier (L1 -> L3), a repeated
tier (L2 -> L2), an inverted one (L3 -> L2) — is a data-integrity defect: the
stored level then contradicts the graph the level is supposed to describe.

``RequirementLevel``'s integers *are* the cascade levels since P1-9
(``L1_SYSTEM = 1 .. L4_PRESENTATION = 4``), so the ``+ 1`` is plain arithmetic
on the field, not a lookup through a translation table.

Why NULL is skipped, not flagged
--------------------------------
``Requirement.level`` is nullable and was never backfilled (migration ``0040``:
"a naming convention cannot be mapped to a level reliably without human
intent"). Until P1-9, ``RequirementService.decompose`` never set it either, so
NULL is the level of practically every Requirement created before that change —
see the "Level vocabulary" sections in ``trace_derivation_allocation.py`` and
``coverage_consistency.py``, and ``hierarchy.py`` for why those two rules read
the *dynamic graph depth* instead of this field.

An edge with a NULL on either end therefore says nothing about whether the
cascade is respected; flagging it would turn "we never asked you to fill this
field in" into a finding on nearly the entire existing corpus. This rule audits
only the edges where a human (or the post-P1-9 ``decompose``) actually asserted
both levels, and holds *those* to the cascade. It is the mirror image of
``decompose``'s own rule: derive a child level only when the parent's is known.

Deliberate deviation: L4 is NOT skipped
---------------------------------------
Every sibling rule module skips an explicitly-assigned
``level == RequirementLevel.L4_PRESENTATION`` (§2.2 closing note, "L4
(Presentation) is out of scope"). That exemption is about the *verification and
allocation* mandates — L4 has no architectural representation, so demanding a
satisfying ArchitectureElement or a verifying TestCase for it makes no sense.

Level progression is a different question, and applying the same exemption here
would blind the rule precisely at the boundary it exists to police: an
``L1 --> L4`` edge (two tiers skipped) or an ``L4 --> L4`` edge (decomposition
below the bottom of the cascade) would go unreported. Both endpoints are
therefore audited at every level, L4 included.

Granularity and severity
------------------------
One finding per violating **edge**, not per Requirement: a Requirement may sit
under more than one hierarchy parent (the graph is not constrained to a tree),
and collapsing those into one finding would hide which parent the level
disagrees with. ``artifact_ids`` is ``(child_id, parent_id)`` so the audit
dashboard can link both ends.

Severity is WARNING rather than the ``Rule`` default BLOCKER, at every tier it
runs in. A level that disagrees with the graph is a metadata defect, not a
broken trace: nothing downstream is *missing*, and the remediation is a
one-field edit. Shipping a brand-new rule as a BLOCKER would retroactively
block approval in existing Extended workspaces whose levels were hand-set under
the pre-P1-9 vocabulary. Promote it once the corpus has caught up.

Tier: Extended only, alongside the other stricter SE-formalism rules
(TRACE-P3/P5/P7, ARCH-003, VERIF-P8). An explicit V-model cascade level is an
Extended-rigor concern; Minimal and Standard workspaces are not expected to
maintain the field at all (ADR-04, configurable rigor).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from persistence.models import Requirement, RequirementLevel
from traceability.audit.hierarchy import requirement_hierarchy_edges
from traceability.audit.registry import CONS_P11, Rule, register_rule
from traceability.audit.types import AuditContext, Finding, Severity


def _active_requirement_levels(
    context: AuditContext,
) -> Dict[str, Tuple[str, Optional[int]]]:
    """Return ``{artifact_id: (title, level)}`` for active Requirements.

    Mirrors ``coverage_consistency._active_requirements`` (each rule module
    keeps its own read helper — the modules are deliberately independent).
    "Active" excludes ``status="outdated"``, the status mirror ``outdate()``
    writes, not the dead ``lifecycle_status`` column.

    ``unscoped`` is the audit infrastructure's convention: tenant and workspace
    are supplied explicitly by the engine, so the thread-local ``objects``
    manager is bypassed on purpose (same as ``AuditContext.iter_trace_links``).
    """
    qs = Requirement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(status="outdated")
    return {
        str(artifact_id): (title, level)
        for artifact_id, title, level in qs.values_list("artifact_id", "title", "level")
    }


def _label(level: Optional[int]) -> str:
    """Return a human-readable ``L<n> <Name>`` label for *level*.

    Falls back to the bare integer for a value that is not a member of
    :class:`~persistence.models.RequirementLevel` — a legacy ``0`` that escaped
    migration ``0067``, or anything else written past the ``choices``
    validation (``choices`` is not DB-enforced for this column). Such a value
    is exactly the kind of defect this rule should name rather than crash on.
    """
    try:
        return RequirementLevel(level).label
    except ValueError:
        return str(level)


@register_rule
class LevelProgressionRule(Rule):
    """CONS-P11: a child Requirement sits exactly one cascade level below its parent."""

    rule_id = CONS_P11

    def severity_for_tier(self, tier: str) -> Severity:
        """Always WARNING — see the "Granularity and severity" module section."""
        return Severity.WARNING

    def check(self, context: AuditContext) -> List[Finding]:
        requirements = _active_requirement_levels(context)
        if not requirements:
            return []

        edges = requirement_hierarchy_edges(context, frozenset(requirements))
        if not edges:
            return []

        findings: List[Finding] = []
        for parent_id, child_id in sorted(edges):
            parent_title, parent_level = requirements[parent_id]
            child_title, child_level = requirements[child_id]

            # Either side unset -> the edge carries no level assertion to audit.
            if parent_level is None or child_level is None:
                continue
            if child_level == parent_level + 1:
                continue

            # Naming an "expected" level only makes sense while one exists.
            # A parent already at the bottom of the cascade has no tier below
            # it, so the defect is the decomposition itself, not the child's
            # number — saying "expected L5" would invent a level.
            if parent_level >= RequirementLevel.L4_PRESENTATION:
                expectation = (
                    f"{_label(parent_level)} is the bottom of the V-model "
                    f"cascade and cannot be decomposed further."
                )
            else:
                expectation = (
                    f"A decomposition child must be exactly one V-model "
                    f"cascade level below its parent (expected "
                    f"{_label(parent_level + 1)})."
                )

            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=(
                        f"[CONS-P11] Requirement '{child_title}' ({child_id}) is "
                        f"{_label(child_level)} but is decomposed from "
                        f"'{parent_title}' ({parent_id}), which is "
                        f"{_label(parent_level)}. {expectation}"
                    ),
                    artifact_ids=(child_id, parent_id),
                )
            )
        return findings
