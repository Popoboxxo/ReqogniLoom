"""
TRACE-P6, VERIF-P8, CONS-P9, CONS-P10 — verification coverage & consistency
(SysEng 2.0 SE-Auditor).

UMSETZUNGSPLAN_SYSENG_2.0.md §2.2 (Pflichtmatrix). All four rules are
scope-agnostic (``is_scope_aware = False``, the Rule default): they audit the
whole workspace graph, not a single baseline scope.

--------------------------------------------------------------------------
Level vocabulary (leaf Requirement, VERIF-P8)
--------------------------------------------------------------------------
Follows the same convention established in ``trace_derivation_allocation.py``
(see that module's docstring for the full rationale): ``Requirement.level``
is ``NULL`` for practically every Requirement created via
``RequirementService.decompose()``, so "leaf" cannot be read off that field
for the regular case. This module instead uses the *dynamic
decomposition-graph depth*: a Requirement is a "leaf" when it is not the
*source* of any ``decomposes``/``parent-child`` link to another Requirement
in scope, i.e. no other Requirement was decomposed from it. This is the
mirror image of ``trace_derivation_allocation._root_requirement_ids``
(which looks for "not a *target*").

L4 (Presentation) is out of scope for the whole §2.2 matrix (closing note
of §2.2): a Requirement with an *explicitly assigned*
``level == RequirementLevel.L4_MATERIAL`` is skipped by VERIF-P8. Rows with
``level IS NULL`` (the overwhelming majority) are never treated as L4 and are
NOT skipped — same rationale as the sibling rule modules.

--------------------------------------------------------------------------
LinkType gap: CONS-P9/CONS-P10 are deferred (verified against code, 2026-07-19)
--------------------------------------------------------------------------
CONS-P9 ("open CONFLICTS_WITH link blocks the Approval-Transition") and
CONS-P10 ("no link may reference a SUPERCEDES-replaced artifact") both
require ``LinkType`` members that do not exist. Verified against
``backend/traceability/types.py``: the ``LinkType`` enum has 14 members (see
UMSETZUNGSPLAN_SYSENG_2.0.md §2.3 — the CLAUDE.md project taxonomy names 8
link types including ``CONFLICTS_WITH`` and ``SUPERCEDES``, but the actual
code enum diverges and defines neither). ``TraceLinkManager.create_link()``
validates ``link_type`` against ``VALID_LINK_TYPES`` and would reject both
strings (``InvalidLinkTypeError``) — no real user can ever create such a
link through the validated path.

An earlier iteration of these two rules queried against raw, kebab-case
string literals (``"conflicts-with"``, ``"supersedes"``) to work around the
missing enum members. That bypasses ``TraceLinkManager._validate_link_type()``
and can only be exercised via the unvalidated ``TraceLink.objects.create()``
path (as the ``make_trace_link`` test helper did) — a path no real user
traffic reaches. Per explicit product decision (no enum extension, no string
workaround), both rules are now marked **deferred** instead: they stay
registered in the catalogue (see :attr:`traceability.audit.registry.Rule.deferred_reason`)
but the RuleEngine guarantees zero findings and never calls their ``check``
for any tier. Implementing them for real is follow-up work, gated on the
``LinkType`` enum actually gaining ``CONFLICTS_WITH``/``SUPERCEDES`` members.

--------------------------------------------------------------------------
TRACE-P6 / VERIF-P8 "supersedes" note
--------------------------------------------------------------------------
TRACE-P6 already filters trace links by the literal string ``"supersedes"``
(via :func:`_superseded_artifact_ids`) — that pre-existing behaviour is out of
scope for this change (TRACE-P6 stays active and unmodified) and is left as
is; only CONS-P9/CONS-P10 are deferred here.

None of the four rules re-implement endpoint-type legality — that is
``traceability.types.check_se_link_semantics`` territory (§2.1). They only
check existence/graph-consistency/state at audit time.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Set, Tuple

from persistence.models import (
    ArchitectureElement,
    Requirement,
    RequirementLevel,
    TestCase,
)
from traceability.audit.registry import (
    CONS_P9,
    CONS_P10,
    TRACE_P6,
    VERIF_P8,
    Rule,
    register_rule,
)
from traceability.audit.types import AuditContext, Finding, Severity
from traceability.types import LinkType
from workflow.services import outdated_item_ids

# Used by TRACE-P6 only (_superseded_artifact_ids below); see the
# "TRACE-P6 / VERIF-P8 'supersedes' note" section of the module docstring —
# out of scope for the CONS-P9/CONS-P10 deferral in this module.
_SUPERCEDES = "supersedes"

_DECOMPOSITION_LINK_TYPES: FrozenSet[str] = frozenset(
    {LinkType.DECOMPOSES.value, LinkType.PARENT_CHILD.value}
)

# ---------------------------------------------------------------------------
# Shared, read-only data access helpers (audit infrastructure — mirrors the
# ``TraceLink.unscoped.filter(tenant_id=...)`` pattern used by
# ``AuditContext.iter_trace_links()``: tenant/workspace are supplied
# explicitly by the engine, so these bypass the thread-local ``objects``
# manager deliberately).
# ---------------------------------------------------------------------------


def _active_requirements(context: AuditContext) -> Dict[str, Tuple[str, int | None]]:
    """Return ``{artifact_id: (title, level)}`` for active Requirements.

    "Active" excludes ``status="outdated"`` (the Requirement status mirror
    ``outdate()`` writes) — not the dead ``lifecycle_status`` column.
    """
    qs = Requirement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(status="outdated")
    return {
        str(artifact_id): (title, level)
        for artifact_id, title, level in qs.values_list("artifact_id", "title", "level")
    }


def _active_architecture_elements(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for active ArchitectureElements.

    ArchitectureElement has no status mirror — ``outdate()`` writes only
    ``WorkflowItemState``, so "active" is computed against that table
    (``workflow.services.outdated_item_ids``) instead of the dead
    ``lifecycle_status`` column.
    """
    qs = ArchitectureElement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(id__in=outdated_item_ids("ArchitectureElement", tenant_id=context.tenant_id))
    return {
        str(artifact_id): title
        for artifact_id, title in qs.values_list("artifact_id", "title")
    }


def _active_test_cases(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for TestCases.

    TestCase has no ``lifecycle_status`` (soft-delete) field — unlike
    Requirement/ArchitectureElement/StakeholderNeed it is never soft-deleted,
    so there is nothing to exclude here.
    """
    qs = TestCase.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    )
    return {
        str(artifact_id): title
        for artifact_id, title in qs.values_list("artifact_id", "title")
    }


def _targets_by_source(
    context: AuditContext, link_types: FrozenSet[str]
) -> Dict[str, Set[str]]:
    """Return ``{source_id: {target_id, ...}}`` for links of *link_types*."""
    result: Dict[str, Set[str]] = {}
    for link in context.iter_trace_links():
        if link["link_type"] not in link_types:
            continue
        result.setdefault(link["source_id"], set()).add(link["target_id"])
    return result


def _superseded_artifact_ids(context: AuditContext) -> FrozenSet[str]:
    """Return the artifact-id set of artifacts replaced by a SUPERCEDES link.

    Direction convention (consistent with ``DERIVES_FROM``/``ALLOCATED_TO``
    etc., §2.2 header note "Source -> Target, ... der Link zeigt aber vom
    Requirement zum Need"): source = the NEW artifact, target = the OLD
    (superseded) one — mirrors the existing Adr lifecycle
    (``Approved -> Superseded``, an approved decision is superseded by a
    later one, never the other way round).
    """
    return frozenset(
        link["target_id"]
        for link in context.iter_trace_links()
        if link["link_type"] == _SUPERCEDES
    )


def _leaf_requirement_ids(
    context: AuditContext, requirement_ids: FrozenSet[str]
) -> FrozenSet[str]:
    """Return the subset of *requirement_ids* with no decomposition child.

    A Requirement is a "leaf" (dynamic-graph stand-in for "L3/L4", see module
    docstring) when it is not the *source* of any ``decomposes``/
    ``parent-child`` link to another Requirement in *requirement_ids* — i.e.
    nothing was decomposed from it.
    """
    parent_ids: Set[str] = set()
    for link in context.iter_trace_links():
        if link["link_type"] not in _DECOMPOSITION_LINK_TYPES:
            continue
        if link["source_id"] in requirement_ids and link["target_id"] in requirement_ids:
            parent_ids.add(link["source_id"])
    return requirement_ids - frozenset(parent_ids)


# ---------------------------------------------------------------------------
# TRACE-P6 — every TestCase verifies >=1 existing, non-superseded
# Requirement/ArchitectureElement. Standard + Extended.
# ---------------------------------------------------------------------------


@register_rule
class TestCaseVerifiesExistingArtifactRule(Rule):
    """TRACE-P6: every TestCase verifies an existing, non-superseded target."""

    rule_id = TRACE_P6

    def check(self, context: AuditContext) -> List[Finding]:
        test_cases = _active_test_cases(context)
        if not test_cases:
            return []

        requirement_ids = frozenset(_active_requirements(context))
        arch_ids = frozenset(_active_architecture_elements(context))
        target_pool = requirement_ids | arch_ids
        superseded_ids = _superseded_artifact_ids(context)
        verifies = _targets_by_source(context, frozenset({LinkType.VERIFIES.value}))

        findings: List[Finding] = []
        for tc_id, title in sorted(test_cases.items()):
            targets = verifies.get(tc_id, set())
            valid_targets = (targets & target_pool) - superseded_ids
            if valid_targets:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P6] TestCase '{title}' ({tc_id}) has no "
                        "'verifies' link to an existing, non-superseded "
                        "Requirement or ArchitectureElement."
                    ),
                    artifact_ids=(tc_id,),
                )
            )
        return findings


# ---------------------------------------------------------------------------
# VERIF-P8 — every leaf Requirement (dynamic-graph leaf, non-L4) has a
# verifying TestCase. Extended only.
# ---------------------------------------------------------------------------


@register_rule
class LeafRequirementHasTestCaseRule(Rule):
    """VERIF-P8: every leaf Requirement has a verifying TestCase."""

    rule_id = VERIF_P8

    def check(self, context: AuditContext) -> List[Finding]:
        requirements = _active_requirements(context)
        if not requirements:
            return []

        non_l4_ids = frozenset(
            artifact_id
            for artifact_id, (_, level) in requirements.items()
            if level != RequirementLevel.L4_MATERIAL
        )
        if not non_l4_ids:
            return []

        leaf_ids = _leaf_requirement_ids(context, non_l4_ids)
        if not leaf_ids:
            return []

        active_test_case_ids = frozenset(_active_test_cases(context))
        verifies = _targets_by_source(context, frozenset({LinkType.VERIFIES.value}))

        verified_requirement_ids: Set[str] = set()
        for tc_id, targets in verifies.items():
            if tc_id not in active_test_case_ids:
                continue
            verified_requirement_ids.update(targets)

        findings: List[Finding] = []
        for req_id in sorted(leaf_ids):
            if req_id in verified_requirement_ids:
                continue
            title = requirements[req_id][0]
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[VERIF-P8] Leaf Requirement '{title}' ({req_id}) has "
                        "no verifying TestCase ('verifies' link)."
                    ),
                    artifact_ids=(req_id,),
                )
            )
        return findings


# ---------------------------------------------------------------------------
# CONS-P9 — open CONFLICTS_WITH links block the Approval-Transition of an
# artifact. DEFERRED: LinkType.CONFLICTS_WITH does not exist yet, see the
# "LinkType gap" section of the module docstring.
# ---------------------------------------------------------------------------


@register_rule
class OpenConflictBlocksApprovalRule(Rule):
    """CONS-P9: an artifact with an open CONFLICTS_WITH link may not be Approved.

    Deferred — see :attr:`deferred_reason` and the module docstring's
    "LinkType gap" section. Registered/visible in the catalogue, but the
    RuleEngine guarantees this never produces findings and never calls
    :meth:`check`, for any rigor tier.
    """

    rule_id = CONS_P9
    deferred_reason = (
        "LinkType.CONFLICTS_WITH is not a member of traceability.types.LinkType "
        "(14 members, verified 2026-07-19; see UMSETZUNGSPLAN_SYSENG_2.0.md "
        "§2.3). No unvalidated string workaround is used per product "
        "decision — implement this rule once the enum is extended."
    )

    def check(self, context: AuditContext) -> List[Finding]:
        """Never invoked (deferred rule) — kept only to satisfy the abstract
        :class:`Rule` interface. See :attr:`deferred_reason`.
        """
        return []


# ---------------------------------------------------------------------------
# CONS-P10 — no active TraceLink references an artifact already replaced via
# SUPERCEDES (dangling-superseded check). DEFERRED: LinkType.SUPERCEDES does
# not exist yet, see the "LinkType gap" section of the module docstring.
# ---------------------------------------------------------------------------


@register_rule
class NoDanglingSupersededReferenceRule(Rule):
    """CONS-P10: no non-SUPERCEDES link may reference a superseded artifact.

    Deferred — see :attr:`deferred_reason` and the module docstring's
    "LinkType gap" section. Registered/visible in the catalogue, but the
    RuleEngine guarantees this never produces findings and never calls
    :meth:`check`, for any rigor tier.
    """

    rule_id = CONS_P10
    deferred_reason = (
        "LinkType.SUPERCEDES is not a member of traceability.types.LinkType "
        "(14 members, verified 2026-07-19; see UMSETZUNGSPLAN_SYSENG_2.0.md "
        "§2.3). No unvalidated string workaround is used per product "
        "decision — implement this rule once the enum is extended."
    )

    def check(self, context: AuditContext) -> List[Finding]:
        """Never invoked (deferred rule) — kept only to satisfy the abstract
        :class:`Rule` interface. See :attr:`deferred_reason`.
        """
        return []


__all__ = [
    "TestCaseVerifiesExistingArtifactRule",
    "LeafRequirementHasTestCaseRule",
    "OpenConflictBlocksApprovalRule",
    "NoDanglingSupersededReferenceRule",
]
