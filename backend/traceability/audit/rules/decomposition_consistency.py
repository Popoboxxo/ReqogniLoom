"""
TRACE-P4, TRACE-P5, ARCH-003 — decomposition graph consistency (SysEng 2.0 SE-Auditor).

UMSETZUNGSPLAN_SYSENG_2.0.md Section 2.2. All three rules police the consistency
of the two parallel hierarchy tracks the plan establishes (Section 1.1):

  - Track (a): ``ArchitectureElement.parent_id`` — SSOT for the architecture
    tree (never expressed as a TraceLink).
  - Track (b): ``TraceLink(decomposes)`` — created by
    ``RequirementService.decompose()`` for the Requirement/Need tree, source =
    parent requirement's artifact id, target = child requirement's artifact id
    (see ``requirement_service.py`` around line 620-646).

None of the three rules re-implement endpoint-type legality — that is
``traceability.types.check_se_link_semantics`` territory (Section 2.1). They
only check graph-wide structural/derivation consistency at audit time, reading
raw TraceLink rows via ``AuditContext.iter_trace_links()``.

L4 (Presentation) is out of scope for the whole Section 2.2 matrix (Section 2.2
closing note): a Requirement with ``level == RequirementLevel.L4_PRESENTATION`` is
never required to carry a ``derives-from`` link by TRACE-P5/ARCH-003.

--------------------------------------------------------------------------
TRACE-P4 — ArchitectureElement decomposition orphan check
--------------------------------------------------------------------------
"Jeder subsystem/component hat mindestens einen decomposes-Parent (kein
architektonisches Waisenelement ausser der Wurzel system)." The structural role
(system/subsystem/component) is *derived* from ``parent_id is None`` (see
``persistence.models.derive_architecture_role``), so any element with role
subsystem/component tautologically has a non-NULL ``parent_id`` — the actual
failure mode this rule catches is a **dangling** parent reference: ``parent_id``
points at an id that does not resolve to an existing, non-deleted
ArchitectureElement in the same tenant/workspace (soft-deleted parent, or a
data-integrity gap). ``ArchitectureElement.get_role()`` never verifies the
parent side actually exists, so this is a real, non-tautological gap it misses.

--------------------------------------------------------------------------
TRACE-P5 vs. ARCH-003 — related but distinct graph-consistency checks
--------------------------------------------------------------------------
Both rules ask "does architecture decomposition track requirement derivation on
the new level", but from different anchors (kept as two rules per the delivery
brief, not merged — the trigger conditions genuinely differ):

  - TRACE-P5 (Requirement-side): for every ``decomposes`` TraceLink between two
    Requirements (parent -> child, as created by ``decompose()``), the child
    must carry a ``derives-from`` link back to that same parent. This is a pure
    Requirement-tree check — it never touches ArchitectureElement data and
    fires even in workspaces with no architecture allocation at all.
  - ARCH-003 (ArchitectureElement-side): for every ArchitectureElement
    parent/child pair (Track a, ``parent_id``), every Requirement allocated
    (``allocated-to``) to the child must ``derive-from`` some Requirement
    allocated to the parent. This fires even when the two requirements were
    never linked by a ``decomposes`` TraceLink at all (e.g. independently
    authored/allocated requirements) — a case TRACE-P5 cannot see because it
    has no ``decomposes`` link to anchor on.

Because their trigger conditions differ (a ``decomposes`` Requirement link vs.
an ``allocated-to`` + ArchitectureElement-parent combination), a workspace can
fail one without failing the other — see the two rules' respective negative
tests in ``traceability/tests/test_trace_p4_p5_arch003.py``.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from traceability.audit.registry import (
    ARCH_003,
    TRACE_P4,
    TRACE_P5,
    Rule,
    register_rule,
)
from traceability.audit.types import AuditContext, Finding, Severity
from traceability.types import LinkType


def _l4_level() -> int:
    """Return ``RequirementLevel.L4_PRESENTATION`` (deferred import — persistence is
    Layer 0 but the audit package defers model imports to check-time, mirroring
    ``AuditContext.iter_trace_links``)."""
    from persistence.models import RequirementLevel

    return RequirementLevel.L4_PRESENTATION


def _fetch_architecture_elements(context: AuditContext) -> Dict[str, Dict[str, Optional[str]]]:
    """Return ``{element_id: {"parent_id": ..., "artifact_id": ...}}`` for
    non-deleted elements in scope.

    ``element_id`` (ArchitectureElement's own PK, used by the self-referential
    ``parent_id`` tree, Track a) and ``artifact_id`` (the backing Artifact row,
    used by every TraceLink endpoint) are two distinct id spaces — TraceLinks
    never reference an ArchitectureElement PK directly, only its Artifact.
    Both are needed here: TRACE-P4 only uses ``parent_id``; ARCH-003 also needs
    ``artifact_id`` to correlate ``allocated-to`` TraceLinks (which point at
    Artifact ids) back to a tree position.
    """
    # ArchitectureElement has no status mirror — outdate() writes only
    # WorkflowItemState (dead lifecycle_status column for this type), so
    # "non-deleted" is computed against that table instead.
    from persistence.models import ArchitectureElement
    from workflow.services import outdated_item_ids

    rows = (
        ArchitectureElement.unscoped.filter(
            tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
        )
        .exclude(id__in=outdated_item_ids("ArchitectureElement", tenant_id=context.tenant_id))
        .values("id", "parent_id", "artifact_id")
    )
    return {
        str(row["id"]): {
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "artifact_id": str(row["artifact_id"]),
        }
        for row in rows
    }


def _fetch_requirement_levels(context: AuditContext) -> Dict[str, Optional[int]]:
    """Return ``{requirement_artifact_id: level_or_None}`` for non-deleted requirements.

    Requirement has a status mirror — ``outdate()`` writes
    ``Requirement.status``, not the dead ``lifecycle_status`` column.
    """
    from persistence.models import Requirement

    rows = (
        Requirement.unscoped.filter(
            tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
        )
        .exclude(status="outdated")
        .values("artifact_id", "level")
    )
    return {str(row["artifact_id"]): row["level"] for row in rows}


def _derives_from_pairs(context: AuditContext) -> Set[Tuple[str, str]]:
    """Return the set of ``(source_id, target_id)`` derives-from pairs.

    Per SE_LINK_SEMANTICS the source is the "deriving" (child) requirement and
    the target is the requirement/need it derives from (parent).
    """
    return {
        (link["source_id"], link["target_id"])
        for link in context.iter_trace_links()
        if link["link_type"] == LinkType.DERIVES_FROM.value
    }


@register_rule
class ArchitectureDecompositionOrphanRule(Rule):
    """TRACE-P4: no subsystem/component may have a dangling decomposes-parent."""

    rule_id = TRACE_P4
    is_scope_aware = False

    def check(self, context: AuditContext) -> List[Finding]:
        """Flag ArchitectureElements whose ``parent_id`` does not resolve.

        Root elements (``parent_id is None``, role SYSTEM) are never orphans by
        definition and are skipped.
        """
        elements = _fetch_architecture_elements(context)
        findings: List[Finding] = []
        for element_id, data in elements.items():
            parent_id = data["parent_id"]
            if parent_id is None:
                continue
            if parent_id not in elements:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=Severity.BLOCKER,
                        message=(
                            f"[TRACE-P4] ArchitectureElement {element_id} references "
                            f"decomposes-parent {parent_id}, which does not exist "
                            "(deleted or outside this workspace) — the element is "
                            "an architectural orphan."
                        ),
                        artifact_ids=(element_id, parent_id),
                    )
                )
        return findings


def _decomposes_requirement_pairs(
    context: AuditContext, requirement_levels: Dict[str, Optional[int]]
) -> List[Tuple[str, str]]:
    """Return ``[(parent_req_id, child_req_id), ...]`` for ``decomposes`` links
    between two Requirements, skipping any pair touching an L4 requirement.
    """
    pairs: List[Tuple[str, str]] = []
    l4 = _l4_level()
    for link in context.iter_trace_links():
        if link["link_type"] != LinkType.DECOMPOSES.value:
            continue
        parent_id, child_id = link["source_id"], link["target_id"]
        if parent_id not in requirement_levels or child_id not in requirement_levels:
            continue  # not a Requirement<->Requirement decomposition
        if requirement_levels[parent_id] == l4 or requirement_levels[child_id] == l4:
            continue  # L4 (Presentation) is out of scope for the whole matrix
        pairs.append((parent_id, child_id))
    return pairs


@register_rule
class RequirementDecompositionDerivationRule(Rule):
    """TRACE-P5: a Requirement decomposes-link must have a matching derives-from."""

    rule_id = TRACE_P5
    is_scope_aware = False

    def check(self, context: AuditContext) -> List[Finding]:
        levels = _fetch_requirement_levels(context)
        derives_from = _derives_from_pairs(context)

        findings: List[Finding] = []
        for parent_id, child_id in _decomposes_requirement_pairs(context, levels):
            if (child_id, parent_id) not in derives_from:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=Severity.BLOCKER,
                        message=(
                            f"[TRACE-P5] Requirement {child_id} was decomposed from "
                            f"{parent_id} ('decomposes' link) but carries no matching "
                            "'derives-from' link back to it — the Requirement tree "
                            "is graph-inconsistent with its decomposition."
                        ),
                        artifact_ids=(child_id, parent_id),
                    )
                )
        return findings


def _allocated_to_map(
    context: AuditContext,
    requirement_ids: FrozenSet[str],
    architecture_artifact_ids: FrozenSet[str],
) -> Dict[str, Set[str]]:
    """Return ``{architecture_artifact_id: {requirement_id, ...}}`` from
    allocated-to links (source = Requirement, target = ArchitectureElement's
    Artifact, matching ``TraceLinkService.allocate()``).

    Keyed by the ArchitectureElement's *Artifact* id (what the TraceLink
    endpoint actually stores) — callers that need the ArchitectureElement's
    own PK (the ``parent_id`` tree, Track a) must translate via the
    ``artifact_id`` field returned by :func:`_fetch_architecture_elements`.
    """
    allocations: Dict[str, Set[str]] = {}
    for link in context.iter_trace_links():
        if link["link_type"] != LinkType.ALLOCATED_TO.value:
            continue
        req_id, arch_artifact_id = link["source_id"], link["target_id"]
        if req_id not in requirement_ids or arch_artifact_id not in architecture_artifact_ids:
            continue
        allocations.setdefault(arch_artifact_id, set()).add(req_id)
    return allocations


@register_rule
class ArchitectureDecompositionRequirementDerivationRule(Rule):
    """ARCH-003: architecture decomposition must carry Requirement derivation."""

    rule_id = ARCH_003
    is_scope_aware = False

    def check(self, context: AuditContext) -> List[Finding]:
        elements = _fetch_architecture_elements(context)
        levels = _fetch_requirement_levels(context)
        l4 = _l4_level()
        requirement_ids: FrozenSet[str] = frozenset(levels)
        architecture_artifact_ids: FrozenSet[str] = frozenset(
            data["artifact_id"] for data in elements.values()
        )
        # allocations keyed by ArchitectureElement Artifact id (TraceLink
        # endpoint space) -> translate to element PK (tree space) below.
        allocations_by_artifact = _allocated_to_map(
            context, requirement_ids, architecture_artifact_ids
        )
        allocations_by_element: Dict[str, Set[str]] = {
            element_id: allocations_by_artifact.get(data["artifact_id"], set())
            for element_id, data in elements.items()
        }
        derives_from = _derives_from_pairs(context)

        findings: List[Finding] = []
        for child_id, data in elements.items():
            parent_id = data["parent_id"]
            if parent_id is None or parent_id not in elements:
                continue  # root, or already an orphan (TRACE-P4's responsibility)
            parent_requirements = allocations_by_element.get(parent_id, set())
            for req_child in allocations_by_element.get(child_id, ()):
                if levels.get(req_child) == l4:
                    continue
                if not any(
                    (req_child, req_parent) in derives_from
                    for req_parent in parent_requirements
                ):
                    findings.append(
                        Finding(
                            rule_id=self.rule_id,
                            severity=Severity.BLOCKER,
                            message=(
                                f"[ARCH-003] Requirement {req_child} is allocated to "
                                f"ArchitectureElement {child_id} (decomposed from "
                                f"{parent_id}) but does not derive-from any "
                                "Requirement allocated to the parent element — the "
                                "architecture decomposition has no matching "
                                "Requirement derivation on the new level."
                            ),
                            artifact_ids=(req_child, child_id, parent_id),
                        )
                    )
        return findings


__all__ = [
    "ArchitectureDecompositionOrphanRule",
    "RequirementDecompositionDerivationRule",
    "ArchitectureDecompositionRequirementDerivationRule",
]
