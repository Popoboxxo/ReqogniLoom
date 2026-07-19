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
LinkType gap: CONFLICTS_WITH / SUPERCEDES (verified against code, 2026-07-19)
--------------------------------------------------------------------------
The task brief for CONS-P9/CONS-P10 states that ``CONFLICTS_WITH`` and
``SUPERCEDES`` "are already existing LinkType values". Verified against
``backend/traceability/types.py`` and found **not to hold**: the ``LinkType``
enum has 14 members (see UMSETZUNGSPLAN_SYSENG_2.0.md §2.3 — the CLAUDE.md
project taxonomy names 8 link types including ``CONFLICTS_WITH`` and
``SUPERCEDES``, but the actual code enum diverges and does not define either
of these two). ``TraceLinkManager.create_link()`` validates ``link_type``
against ``VALID_LINK_TYPES`` and would currently reject both strings
(``InvalidLinkTypeError``) — §2.3 already flags this exact
taxonomy/implementation mismatch for ``decomposes``/``allocated-to`` and
leaves closing the remaining gaps as follow-up work.

Adding new ``LinkType`` enum members is outside this module's authorized
scope (only ``registry.py`` rule-id constants and ``rules/__init__.py``
integration are the sanctioned core-file edits for this task). These two
rules are therefore written against literal, kebab-case string constants
that match the existing ``LinkType`` naming convention
(``"conflicts-with"``, ``"supersedes"``) rather than enum members. The moment
the enum gap is closed (a small, additive follow-up mirroring how
``decomposes`` was added, §1.4) these rules keep working unchanged — they
never import the enum member, only the string value it would carry.

``TraceLink.link_type`` is a plain ``CharField`` with no DB-level enum
constraint (``persistence/models.py``) and ``TraceLink.objects.create()``
bypasses ``TraceLinkManager`` validation entirely (as the shared
``make_trace_link`` test helper already does for every other link type in
this test suite) — a row with one of these two link_type values can already
exist in the data (seeded, imported, or created once the service-layer path
is extended), and these rules audit whatever data is actually there.

--------------------------------------------------------------------------
CONS-P9: workflow-state correlation
--------------------------------------------------------------------------
"Approval-Transition" is read from ``workflow.models.WorkflowItemState``, the
single source of truth for an item's current workflow state (COMP-WE-003).
Note ``WorkflowItemState.item_id`` is **not** the artifact id: every
``...Service.create()`` calls ``initialize_workflow_states(item_ids=[<entity>.id], ...)``
with the domain entity's *own* primary key (e.g.
``application/requirement_service.py`` passes ``requirement.id``, not
``artifact.id``; same for ``architecture_service.py`` / ``arch_el.id`` and
``test_service.py`` / ``test_case.id``). TraceLink endpoints, by contrast,
always reference the Artifact id. ``_workflow_trackable_artifacts()`` below
bridges the two id spaces. Some entities additionally denormalize
``current_state`` onto a ``status`` column (REQ-165/166,
``workflow.lifecycle_manager._STATUS_MIRROR_MODELS``) but ``ArchitectureElement``
is deliberately NOT wired into that mirror map (REQ-171) — so this rule reads
``WorkflowItemState`` directly and uniformly for every entity type instead of
relying on the mirror, which would silently miss ArchitectureElement.

"Offene (nicht aufgelöste) CONFLICTS_WITH-Links" — the TraceLink model has no
resolution/ack flag, so there is no separate "resolved" state to check:
existence of the link IS "open" (nothing in this codebase currently marks a
conflict link as resolved other than deleting it).

None of the four rules re-implement endpoint-type legality — that is
``traceability.types.check_se_link_semantics`` territory (§2.1). They only
check existence/graph-consistency/state at audit time.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Set, Tuple

from persistence.models import (
    ArchitectureElement,
    LifecycleStatus,
    Requirement,
    RequirementLevel,
    StakeholderNeed,
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

# See the "LinkType gap" section of the module docstring.
_CONFLICTS_WITH = "conflicts-with"
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
    """Return ``{artifact_id: (title, level)}`` for active Requirements."""
    qs = Requirement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
    return {
        str(artifact_id): (title, level)
        for artifact_id, title, level in qs.values_list("artifact_id", "title", "level")
    }


def _active_architecture_elements(context: AuditContext) -> Dict[str, str]:
    """Return ``{artifact_id: title}`` for active ArchitectureElements."""
    qs = ArchitectureElement.unscoped.filter(
        tenant_id=context.tenant_id,
        artifact__workspace_id=context.workspace_id,
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
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


def _workflow_trackable_artifacts(
    context: AuditContext,
) -> Dict[str, Tuple[str, str]]:
    """Return ``{artifact_id: (item_type, item_id)}`` for the SE-core entity
    types that carry a ``WorkflowItemState`` (Requirement, ArchitectureElement,
    StakeholderNeed, TestCase). See the "CONS-P9: workflow-state correlation"
    section of the module docstring for why this id-space bridge is needed.
    """
    mapping: Dict[str, Tuple[str, str]] = {}

    req_qs = Requirement.unscoped.filter(
        tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
    for artifact_id, item_id in req_qs.values_list("artifact_id", "id"):
        mapping[str(artifact_id)] = ("Requirement", str(item_id))

    arch_qs = ArchitectureElement.unscoped.filter(
        tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
    for artifact_id, item_id in arch_qs.values_list("artifact_id", "id"):
        mapping[str(artifact_id)] = ("ArchitectureElement", str(item_id))

    need_qs = StakeholderNeed.unscoped.filter(
        tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
    ).exclude(lifecycle_status=LifecycleStatus.DELETED)
    for artifact_id, item_id in need_qs.values_list("artifact_id", "id"):
        mapping[str(artifact_id)] = ("StakeholderNeed", str(item_id))

    tc_qs = TestCase.unscoped.filter(
        tenant_id=context.tenant_id, artifact__workspace_id=context.workspace_id
    )
    for artifact_id, item_id in tc_qs.values_list("artifact_id", "id"):
        mapping[str(artifact_id)] = ("TestCase", str(item_id))

    return mapping


def _current_states_by_item(
    context: AuditContext, items: FrozenSet[Tuple[str, str]]
) -> Dict[Tuple[str, str], str]:
    """Return ``{(item_type, item_id): current_state}`` for *items*.

    Deferred import: ``workflow`` is a Layer-1 sibling app, mirroring the
    deferred ``baseline.services`` import in ``AuditContext.scope_item_ids``.
    """
    if not items:
        return {}
    from workflow.models import WorkflowItemState

    item_types = {t for t, _ in items}
    item_ids = {i for _, i in items}
    rows = WorkflowItemState.unscoped.filter(
        tenant_id=context.tenant_id,
        workspace_id=context.workspace_id,
        item_type__in=item_types,
        item_id__in=item_ids,
    ).values("item_type", "item_id", "current_state")
    return {
        (row["item_type"], str(row["item_id"])): row["current_state"] for row in rows
    }


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
# artifact. Standard + Extended.
# ---------------------------------------------------------------------------


@register_rule
class OpenConflictBlocksApprovalRule(Rule):
    """CONS-P9: an artifact with an open CONFLICTS_WITH link may not be Approved."""

    rule_id = CONS_P9

    def check(self, context: AuditContext) -> List[Finding]:
        conflict_links = [
            link
            for link in context.iter_trace_links()
            if link["link_type"] == _CONFLICTS_WITH
        ]
        if not conflict_links:
            return []

        trackable = _workflow_trackable_artifacts(context)
        if not trackable:
            return []

        items = frozenset(trackable.values())
        current_states = _current_states_by_item(context, items)

        findings: List[Finding] = []
        seen: Set[Tuple[str, str]] = set()  # (link_id, artifact_id) dedup
        for link in conflict_links:
            for endpoint_id in (link["source_id"], link["target_id"]):
                item = trackable.get(endpoint_id)
                if item is None:
                    continue
                state = current_states.get(item)
                if not state or state.lower() != "approved":
                    continue
                dedup_key = (link["id"], endpoint_id)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=Severity.BLOCKER,
                        message=(
                            f"[CONS-P9] Artifact {endpoint_id} is in state "
                            f"'{state}' but has an open 'conflicts-with' link "
                            f"({link['id']}) — the Approval-Transition is "
                            "blocked until the conflict is resolved."
                        ),
                        artifact_ids=(endpoint_id,),
                    )
                )
        return findings


# ---------------------------------------------------------------------------
# CONS-P10 — no active TraceLink references an artifact already replaced via
# SUPERCEDES (dangling-superseded check). Standard + Extended.
# ---------------------------------------------------------------------------


@register_rule
class NoDanglingSupersededReferenceRule(Rule):
    """CONS-P10: no non-SUPERCEDES link may reference a superseded artifact."""

    rule_id = CONS_P10

    def check(self, context: AuditContext) -> List[Finding]:
        all_links = list(context.iter_trace_links())
        superseded_ids = frozenset(
            link["target_id"] for link in all_links if link["link_type"] == _SUPERCEDES
        )
        if not superseded_ids:
            return []

        findings: List[Finding] = []
        for link in all_links:
            if link["link_type"] == _SUPERCEDES:
                continue  # the supersession link itself is not a dangling reference
            offending_id = None
            if link["source_id"] in superseded_ids:
                offending_id = link["source_id"]
            elif link["target_id"] in superseded_ids:
                offending_id = link["target_id"]
            if offending_id is None:
                continue
            findings.append(
                Finding(
                    rule_id=self.rule_id,
                    severity=Severity.BLOCKER,
                    message=(
                        f"[CONS-P10] Trace link {link['id']} "
                        f"({link['link_type']}) references artifact "
                        f"{offending_id}, which has already been replaced via "
                        "a 'supersedes' link (dangling-superseded reference)."
                    ),
                    artifact_ids=(offending_id,),
                )
            )
        return findings


__all__ = [
    "TestCaseVerifiesExistingArtifactRule",
    "LeafRequirementHasTestCaseRule",
    "OpenConflictBlocksApprovalRule",
    "NoDanglingSupersededReferenceRule",
]
