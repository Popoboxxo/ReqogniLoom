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
decomposition-graph depth*: a Requirement is a "leaf" when no other
Requirement in scope hangs below it in the hierarchy, i.e. nothing was
decomposed/derived from it. Both spellings of a hierarchy edge count —
``parent --decomposes/parent-child--> child`` and the inverse
``child --derives-from--> parent`` (issue #395); see
:mod:`traceability.audit.hierarchy`, which holds the shared definition used
by both this module and ``trace_derivation_allocation``'s mirror-image root
classification (and only those two — that module's docstring lists the other
hierarchy representations it must *not* be unified with).

L4 (Presentation) is out of scope for the whole §2.2 matrix (closing note
of §2.2): a Requirement with an *explicitly assigned*
``level == RequirementLevel.L4_PRESENTATION`` is skipped by VERIF-P8. Rows with
``level IS NULL`` (the overwhelming majority) are never treated as L4 and are
NOT skipped — same rationale as the sibling rule modules.

--------------------------------------------------------------------------
LinkType gap: CONS-P9/CONS-P10 are deferred (verified against code, 2026-07-19)
--------------------------------------------------------------------------
CONS-P9 ("open CONFLICTS_WITH link blocks the Approval-Transition") and
CONS-P10 ("no link may reference a SUPERCEDES-replaced artifact") both
require ``LinkType`` members that do not exist. Verified against
``backend/traceability/types.py``: the ``LinkType`` enum had 14 members when
this was first investigated (2026-07-19, see UMSETZUNGSPLAN_SYSENG_2.0.md
§2.3) and has 15 now (``diagram-ref`` was added 2026-08-08, #353/#428) — the
CLAUDE.md project taxonomy at the time named 8 link types including
``CONFLICTS_WITH`` and ``SUPERCEDES``, but the actual code enum diverges and
still defines neither (see GitHub #404, which corrected the documentation
side of this gap). ``TraceLinkManager.create_link()``
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

TRACE-P6 used to carry its own string-literal ``"supersedes"`` exclusion
(``_superseded_artifact_ids``) on top of this — that filter could never match
a real link either (same validation gap as CONS-P9/CONS-P10), so it was
removed rather than deferred: it was live, unconditional code silently
promising an exclusion that no user-created data could ever trigger.
SYSTEMAUDIT_2026-08-27 P1-15; the mirror-image filter in
``workflow.precondition_rules.check_verifies_link`` (Rule 7) was removed for
the same reason in the same change.

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
from traceability.audit.hierarchy import leaf_requirement_ids as _leaf_requirement_ids
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
from workflow import state_reader
from workflow.services import outdated_item_ids

# ---------------------------------------------------------------------------
# Shared, read-only data access helpers (audit infrastructure — mirrors the
# ``TraceLink.unscoped.filter(tenant_id=...)`` pattern used by
# ``AuditContext.iter_trace_links()``: tenant/workspace are supplied
# explicitly by the engine, so these bypass the thread-local ``objects``
# manager deliberately. ``state_reader.current_states``'s own ``tenant_id=``
# kwarg (N1) covers this same need — no local reimplementation required.)
# ---------------------------------------------------------------------------


def _active_requirements(context: AuditContext) -> Dict[str, Tuple[str, int | None]]:
    """Return ``{artifact_id: (title, level)}`` for active Requirements.

    Datenmodell-Konsolidierung Phase 1: "active" is resolved through
    ``WorkflowItemState`` (batched), falling back to the (now write-once,
    frozen-at-creation) ``status`` column only for a Requirement that was
    never wired into a ``WorkflowItemState`` — same fallback convention as
    the REST serializers / baseline capture, needed here because (unlike
    ArchitectureElement) Requirement has no backfill-migration guarantee.
    """
    rows = list(
        Requirement.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
        ).values("id", "artifact_id", "title", "level", "status")
    )
    states = state_reader.current_states(
        "Requirement", (row["id"] for row in rows), tenant_id=context.tenant_id
    )
    return {
        str(row["artifact_id"]): (row["title"], row["level"])
        for row in rows
        if (states.get(str(row["id"])) or row["status"]) != "outdated"
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
    """Return ``{artifact_id: title}`` for active TestCases.

    Datenmodell-Konsolidierung Phase 1: "active" excludes ``"outdated"`` via
    ``WorkflowItemState``, the same seam :func:`_active_requirements` uses.

    GH-574: this helper used to return every row, on the assumption that
    TestCase is never soft-deleted. That stopped being true twice over —
    REQ-165/REQ-166 registered TestCase in
    ``workflow.lifecycle_manager._STATUS_MIRROR_MODELS`` and GH-443 routed
    ``TestService.delete_test_case`` through ``workflow.services.outdate()``,
    so a deleted TestCase does carry ``status="outdated"``. Auditing it anyway
    meant TRACE-P6 kept a workspace fail-closed on an artifact the user had
    already removed, naming an id that no longer resolves in any list view.

    Both consumers change with this: TRACE-P6 no longer flags deleted
    TestCases, and VERIF-P8 no longer accepts one as verification evidence
    (deleting the only TestCase covering a leaf Requirement re-opens VERIF-P8
    instead of leaving the Requirement silently "covered").
    """
    rows = list(
        TestCase.unscoped.filter(
            tenant_id=context.tenant_id,
            artifact__workspace_id=context.workspace_id,
        ).values("id", "artifact_id", "title", "status")
    )
    states = state_reader.current_states(
        "TestCase", (row["id"] for row in rows), tenant_id=context.tenant_id
    )
    return {
        str(row["artifact_id"]): row["title"]
        for row in rows
        if (states.get(str(row["id"])) or row["status"]) != "outdated"
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


# ---------------------------------------------------------------------------
# TRACE-P6 — every TestCase verifies >=1 existing Requirement/ArchitectureElement.
# Standard + Extended.
# ---------------------------------------------------------------------------


@register_rule
class TestCaseVerifiesExistingArtifactRule(Rule):
    """TRACE-P6: every TestCase verifies an existing target."""

    rule_id = TRACE_P6

    def check(self, context: AuditContext) -> List[Finding]:
        test_cases = _active_test_cases(context)
        if not test_cases:
            return []

        requirement_ids = frozenset(_active_requirements(context))
        arch_ids = frozenset(_active_architecture_elements(context))
        target_pool = requirement_ids | arch_ids
        verifies = _targets_by_source(context, frozenset({LinkType.VERIFIES.value}))

        findings: List[Finding] = []
        for tc_id, title in sorted(test_cases.items()):
            targets = verifies.get(tc_id, set())
            valid_targets = targets & target_pool
            if valid_targets:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[TRACE-P6] TestCase '{title}' ({tc_id}) has no "
                        "'verifies' link to an existing Requirement or "
                        "ArchitectureElement."
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
            if level != RequirementLevel.L4_PRESENTATION
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
        "(15 members as of 2026-08-08, 14 when first verified 2026-07-19; see "
        "UMSETZUNGSPLAN_SYSENG_2.0.md §2.3). No unvalidated string workaround "
        "is used per product decision — implement this rule once the enum is "
        "extended."
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
        "(15 members as of 2026-08-08, 14 when first verified 2026-07-19; see "
        "UMSETZUNGSPLAN_SYSENG_2.0.md §2.3). No unvalidated string workaround "
        "is used per product decision — implement this rule once the enum is "
        "extended."
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
