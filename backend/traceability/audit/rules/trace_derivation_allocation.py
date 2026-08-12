"""
TRACE-P1, TRACE-P1b, TRACE-P2, TRACE-P3 — derivation & allocation completeness
(SysEng 2.0 SE-Auditor).

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2 (Pflichtmatrix). All four rules are
scope-agnostic (``is_scope_aware = False``, the Rule default): they audit the
whole workspace graph, not a single baseline scope.

Level vocabulary used here (see UMSETZUNGSPLAN_SYSENG_2.0.md §1.2, "Achsen-
Klarstellung"): the plan documents that "L0..L4" is ambiguous across four
independent, non-aligned vocabularies in this codebase and that the choice
between them for §2.2 was explicitly left open ("Diese Entscheidung ist noch
nicht getroffen"). ``Requirement.level`` (the DB enum) is NULL for
practically every Requirement created via the production path
(``RequirementService.decompose()`` never sets it — see §1.2) so a rule that
required it to be populated would never fire against real data. This module
therefore uses the *dynamic decomposition-graph depth* option the plan
names as the alternative:

- **L0** = :class:`~persistence.models.StakeholderNeed` — a distinct model,
  never a ``Requirement`` row. No Requirement is ever "L0".
- **L1 ("root" / "SystemRequirement")** = a ``Requirement`` with no
  hierarchy parent among the other Requirements — i.e. the root of a
  decomposition subgraph. This is a graph property, computed per audit run,
  not a stored field. "Hierarchy parent" spans both spellings of the same
  fact, ``parent --decomposes/parent-child--> child`` *and* the inverse
  ``child --derives-from--> parent`` (issue #395: real workspaces express the
  hierarchy predominantly through ``derives-from``); see
  :mod:`traceability.audit.hierarchy` for the direction table.
- **L2+ ("child Requirement")** = any Requirement that *does* have such a
  hierarchy parent.
- **L4 (Presentation)** is explicitly out of scope for every rule in this
  module (§2.2, "L4 (Presentation)"). There is no dynamic-graph signal for
  it (it has no architectural representation per §1.2), so the only
  data-backed way to recognise it is an explicitly assigned
  ``Requirement.level == RequirementLevel.L4_MATERIAL``. Rows with
  ``level IS NULL`` (the overwhelming majority) are never treated as L4 by
  this heuristic — they simply are not skipped.

Endpoint-type legality (may ``Requirement`` link to ``StakeholderNeed`` via
``derives-from``, may ``ArchitectureElement`` link to ``Requirement`` via
``satisfies``/``implements``, ...) is NOT re-implemented here — that is
``SE_LINK_SEMANTICS`` / ``check_se_link_semantics`` territory (§2.1),
enforced synchronously at link-creation time. These rules only check
*existence* of the required link, never re-validate its endpoint types.

--------------------------------------------------------------------------
BEHAVIOUR CHANGE — TRACE-P3 accepts an incoming ``allocated-to`` (issue #395)
--------------------------------------------------------------------------
This is a deliberate widening of a **BLOCKER** rule's semantics, decided as
part of issue #395 but *independent* of that issue's root/leaf
classification migration — it is called out here so it is reviewed on its
own merits rather than read as a side effect of the classification change.

TRACE-P3 used to accept only an outgoing ``satisfies``/``implements`` link
from the ArchitectureElement. It now also accepts an incoming
``Requirement --allocated-to--> element`` link. Rationale, trade-off and the
rejected alternative (auto-writing a reciprocal ``satisfies`` link on every
allocation) are documented on
:class:`ArchitectureElementSatisfiesRequirementRule` itself.

Net effect on existing workspaces: TRACE-P3 fires strictly less often than
before. No workspace that passed the rule can start failing it; workspaces
whose architecture was justified purely by allocation stop being blocked.

Soft-deleted artifacts are excluded from every check in this module — a
deleted Requirement/ArchitectureElement/StakeholderNeed cannot meaningfully be
"orphaned" or "unallocated". "Soft-deleted" is per-type: StakeholderNeed and
Requirement both use ``status == "outdated"`` (both are registered in
``workflow.lifecycle_manager._STATUS_MIRROR_MODELS`` and the mirror is written
by ``outdate()``); Architecture Element has no mirror at all and is checked
against ``workflow.services.outdated_item_ids`` (state lives only in
``WorkflowItemState``).
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List

from django.db.models import Q

from persistence.models import (
    ArchitectureElement,
    Requirement,
    RequirementLevel,
    StakeholderNeed,
)
from traceability.audit.hierarchy import root_requirement_ids as _root_requirement_ids
from traceability.audit.registry import (
    TRACE_P1,
    TRACE_P1B,
    TRACE_P2,
    TRACE_P3,
    Rule,
    register_rule,
)
from traceability.audit.types import AuditContext, Finding, Severity
from traceability.types import LinkType
from workflow.services import outdated_item_ids

# ---------------------------------------------------------------------------
# Shared, read-only data access helpers (audit infrastructure — mirrors the
# ``TraceLink.unscoped.filter(tenant_id=...)`` pattern already used by
# ``AuditContext.iter_trace_links()``: tenant is supplied explicitly by the
# engine, so these bypass the thread-local ``objects`` manager deliberately).
# ---------------------------------------------------------------------------


def _active_requirements(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for active, non-L4 Requirements."""
    # NOTE: plain ``.exclude(level=L4_MATERIAL)`` would also drop NULL-level
    # rows under SQL three-valued-logic semantics (``NULL = 4`` is UNKNOWN,
    # ``NOT UNKNOWN`` stays UNKNOWN, row excluded) — and NULL is the level for
    # practically every Requirement created via decompose() (see module
    # docstring). The explicit ``Q(level__isnull=True) | ~Q(...)`` keeps
    # NULL-level rows unconditionally; only an *explicitly* assigned L4 is
    # skipped.
    qs = (
        Requirement.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
        )
        .exclude(status="outdated")
        .filter(Q(level__isnull=True) | ~Q(level=RequirementLevel.L4_MATERIAL))
    )
    return {
        str(artifact_id): title
        for artifact_id, title in qs.values_list("artifact_id", "title")
    }


def _active_stakeholder_need_ids(context: AuditContext) -> FrozenSet[str]:
    """Return the artifact-id set of active StakeholderNeeds (L0).

    StakeholderNeed is registered in
    ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS`` and its ``delete()``
    path calls ``workflow.services.outdate()``, which writes ``status ==
    "outdated"`` — the same status mirror Requirement uses. The now-legacy
    ``lifecycle_status`` field is never touched by ``outdate()``, so filtering
    on it here would silently treat a deleted StakeholderNeed as still active.
    """
    qs = StakeholderNeed.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(status="outdated")
    return frozenset(str(v) for v in qs.values_list("artifact_id", flat=True))


def _active_architecture_elements(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for active ArchitectureElements."""
    qs = ArchitectureElement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(id__in=outdated_item_ids("ArchitectureElement", tenant_id=context.tenant_id))
    return {
        str(artifact_id): title
        for artifact_id, title in qs.values_list("artifact_id", "title")
    }


def _sources_by_link_type(
    context: AuditContext, link_types: FrozenSet[str]
) -> Dict[str, set]:
    """Return ``{source_id: {target_id, ...}}`` for links of *link_types*."""
    result: Dict[str, set] = {}
    for link in context.iter_trace_links():
        if link["link_type"] not in link_types:
            continue
        result.setdefault(link["source_id"], set()).add(link["target_id"])
    return result


def _targets_by_link_type(
    context: AuditContext, link_types: FrozenSet[str]
) -> Dict[str, set]:
    """Return ``{target_id: {source_id, ...}}`` for links of *link_types*.

    The reverse index of :func:`_sources_by_link_type`, for rules that have to
    read an edge from its target side (TRACE-P3 and the incoming
    ``allocated-to`` link).
    """
    result: Dict[str, set] = {}
    for link in context.iter_trace_links():
        if link["link_type"] not in link_types:
            continue
        result.setdefault(link["target_id"], set()).add(link["source_id"])
    return result


# ---------------------------------------------------------------------------
# TRACE-P1 — SystemRequirement (L1) --derives-from--> StakeholderNeed (L0)
# ---------------------------------------------------------------------------


@register_rule
class SystemRequirementDerivesFromNeedRule(Rule):
    """TRACE-P1: every root Requirement derives from a StakeholderNeed."""

    rule_id = TRACE_P1

    def check(self, context: AuditContext) -> List[Finding]:
        requirements = _active_requirements(context)
        if not requirements:
            return []

        requirement_ids = frozenset(requirements)
        root_ids = _root_requirement_ids(context, requirement_ids)
        if not root_ids:
            return []

        need_ids = _active_stakeholder_need_ids(context)
        derives_from = _sources_by_link_type(
            context, frozenset({LinkType.DERIVES_FROM.value})
        )

        findings: List[Finding] = []
        for req_id in sorted(root_ids):
            targets = derives_from.get(req_id, set())
            if targets & need_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P1] Root Requirement '{requirements[req_id]}' "
                        f"({req_id}) has no 'derives-from' link to a "
                        f"StakeholderNeed (L0)."
                    ),
                    artifact_ids=(req_id,),
                )
            )
        return findings


# ---------------------------------------------------------------------------
# TRACE-P1b — every Requirement (n > 0) has SOME upstream derives-from link
# (orphan-requirement check; also catches L2/L3 children).
# ---------------------------------------------------------------------------


@register_rule
class RequirementOrphanCheckRule(Rule):
    """TRACE-P1b: every Requirement has an upstream 'derives-from' link.

    No Requirement is ever "L0" (that is :class:`StakeholderNeed`'s role), so
    this applies to every active, non-L4 Requirement — root and child alike.
    Unlike TRACE-P1 the upstream target may be *either* a StakeholderNeed or
    another Requirement (Ln-1); this rule is the general orphan detector.
    """

    rule_id = TRACE_P1B

    def check(self, context: AuditContext) -> List[Finding]:
        requirements = _active_requirements(context)
        if not requirements:
            return []

        need_ids = _active_stakeholder_need_ids(context)
        upstream_ids = frozenset(requirements) | need_ids
        derives_from = _sources_by_link_type(
            context, frozenset({LinkType.DERIVES_FROM.value})
        )

        findings: List[Finding] = []
        for req_id, title in sorted(requirements.items()):
            targets = derives_from.get(req_id, set())
            if targets & upstream_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P1b] Requirement '{title}' ({req_id}) has no "
                        f"outgoing 'derives-from' link to any upstream "
                        f"Requirement or StakeholderNeed (orphan)."
                    ),
                    artifact_ids=(req_id,),
                )
            )
        return findings


# ---------------------------------------------------------------------------
# TRACE-P2 — every Requirement (>= L1) is allocated to an ArchitectureElement.
# Standard: WARNING. Extended: BLOCKER (severity_for_tier override).
# ---------------------------------------------------------------------------


@register_rule
class RequirementAllocatedToArchitectureRule(Rule):
    """TRACE-P2: every Requirement is allocated to an ArchitectureElement."""

    rule_id = TRACE_P2

    def severity_for_tier(self, tier: str) -> Severity:
        """Extended is a hard BLOCKER; Standard downgrades to a WARNING."""
        if tier == "extended":
            return Severity.BLOCKER
        return Severity.WARNING

    def check(self, context: AuditContext) -> List[Finding]:
        requirements = _active_requirements(context)
        if not requirements:
            return []

        arch_ids = frozenset(_active_architecture_elements(context))
        allocated_to = _sources_by_link_type(
            context, frozenset({LinkType.ALLOCATED_TO.value})
        )

        findings: List[Finding] = []
        for req_id, title in sorted(requirements.items()):
            targets = allocated_to.get(req_id, set())
            if targets & arch_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    # Re-stamped by RuleEngine._run_rule with
                    # severity_for_tier(); the value here is a placeholder.
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P2] Requirement '{title}' ({req_id}) is not "
                        f"allocated ('allocated-to') to any ArchitectureElement."
                    ),
                    artifact_ids=(req_id,),
                )
            )
        return findings


# ---------------------------------------------------------------------------
# TRACE-P3 — every ArchitectureElement satisfies/implements >= 1 Requirement.
# ---------------------------------------------------------------------------


@register_rule
class ArchitectureElementSatisfiesRequirementRule(Rule):
    """TRACE-P3: every ArchitectureElement satisfies/implements a Requirement.

    BEHAVIOUR CHANGE (issue #395) — see the module docstring. An incoming
    ``Requirement --allocated-to--> element`` link now counts as
    justification too.

    Allocation and satisfaction are the two directions of one fact. In
    ``SE_LINK_SEMANTICS`` the Requirement/ArchitectureElement pair of
    ``allocated-to`` (``(Requirement, ArchitectureElement)``) is exactly the
    reverse of the Requirement/ArchitectureElement pair of ``satisfies``
    (``(ArchitectureElement, Requirement)``). Neither entry is limited to
    that pair — ``satisfies`` also permits ``(Requirement,
    StakeholderNeed)`` and ``allocated-to`` also permits
    ``(ArchitectureElement, ArchitectureElement)`` — but those other pairs
    cannot reach this rule, which only ever intersects against the active
    Requirement set.

    Allocation is also the *only* one of the two directions the product ever
    writes (``TraceLinkService.allocate``, the guided "Ableiten" flow, the AI
    decomposition commit); no code path produces a ``satisfies`` link. Without
    this, an element carrying the whole requirement allocation of a system
    level was still reported as architecture without justification — the
    fault this rule exists to catch, inverted.

    Rejected alternative: auto-writing a reciprocal ``satisfies`` link on
    every allocation. That doubles every allocation edge in coverage
    aggregation, VCRM reports, diagrams and baselines, and
    ``TraceLinkService.allocate`` deletes a Requirement's previous allocation
    — so it would have to delete the paired ``satisfies`` too, which cannot
    be told apart from a hand-authored one. It also asserts something the
    user never stated.

    The rule keeps its teeth: an element with neither an outgoing
    satisfies/implements nor an incoming allocation is untraced architecture
    and still blocks.
    """

    rule_id = TRACE_P3

    def check(self, context: AuditContext) -> List[Finding]:
        elements = _active_architecture_elements(context)
        if not elements:
            return []

        requirement_ids = frozenset(_active_requirements(context))
        satisfies_or_implements = _sources_by_link_type(
            context,
            frozenset({LinkType.SATISFIES.value, LinkType.IMPLEMENTS.value}),
        )
        allocated_from = _targets_by_link_type(
            context, frozenset({LinkType.ALLOCATED_TO.value})
        )

        findings: List[Finding] = []
        for ae_id, title in sorted(elements.items()):
            justifying = (
                satisfies_or_implements.get(ae_id, set())
                | allocated_from.get(ae_id, set())
            )
            if justifying & requirement_ids:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P3] ArchitectureElement '{title}' ({ae_id}) "
                        f"does not satisfy/implement any Requirement and has "
                        f"no Requirement allocated to it."
                    ),
                    artifact_ids=(ae_id,),
                )
            )
        return findings


__all__ = [
    "SystemRequirementDerivesFromNeedRule",
    "RequirementOrphanCheckRule",
    "RequirementAllocatedToArchitectureRule",
    "ArchitectureElementSatisfiesRequirementRule",
]
