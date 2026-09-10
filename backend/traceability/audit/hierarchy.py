"""
Requirement-hierarchy classification shared by the SE-Auditor rules.

Issue #395. Root/leaf classification used to look at ``decomposes`` links
**only** (a private ``_DECOMPOSITION_LINK_TYPES``
constant duplicated in ``rules/trace_derivation_allocation.py`` and
``rules/coverage_consistency.py``). The Requirement hierarchy that real
workspaces actually contain is expressed predominantly through
``derives-from`` links — every hierarchy built through the guided "Ableiten"
flow before this fix, through manual linking, through the MCP tools or
through CSV import carries a ``derives-from`` edge and frequently no
``decomposes`` edge at all. Those hierarchies were invisible to the
classifier, so every Requirement in them was simultaneously classified as a
decomposition *root* (TRACE-P1: "must derive from a StakeholderNeed") and as
a *leaf* (VERIF-P8: "must have a verifying TestCase") — two blocking findings
per Requirement, both factually wrong.

Direction matters, and it is the reason ``derives-from`` cannot simply be
added to the old constant:

===================  ==========================  ==========================
link type            source                      target
===================  ==========================  ==========================
``decomposes``       parent (the decomposed)     child (the result)
``derives-from``     child (the derived)         parent (the origin)
===================  ==========================  ==========================

``derives-from`` is the *inverse* edge. Adding it to a set that is then read
as "target is the child" would have marked every parent as a child and every
child as a parent — inverting the hierarchy instead of recognising it. This
module therefore normalises both spellings into a single set of
``(parent_id, child_id)`` pairs, and root/leaf are derived from that.

``refines`` no longer exists as a link type: the migration folded it into
``derives-from``. Because ``derives-from`` *is* a hierarchy edge, every
formerly symmetric ``refines`` edge between two Requirements now carries
level semantics it did not have before — see OFFENE FRAGE 2 in
docs/superpowers/plans/2026-09-03-traceability-semantik.md.

Only edges whose *both* endpoints are Requirements in the audited set count.
A ``Requirement --derives-from--> StakeholderNeed`` link is legal and common,
but it does not make the Requirement a decomposition child — a Requirement
derived straight from a Need is precisely the root (L1) case TRACE-P1 exists
to check.

Scope of this module (do not over-read it)
------------------------------------------
This is the shared definition of **root/leaf classification for the audit
rules** — nothing broader. It is deliberately *not* the single
representation of hierarchy in the system, and unifying the others into it
would break them:

- ``rules/decomposition_consistency._decomposes_requirement_pairs`` looks at
  ``decomposes`` links *only*, on purpose: TRACE-P5 exists precisely to check
  that a ``decomposes`` edge has its ``derives-from`` counterpart. Feeding it
  normalised edges would make the rule tautologically true.
- ``ArchitectureElement.parent_id`` (and its ``Artifact.parent`` mirror) is a
  separate FK tree for architecture, never a TraceLink.

Cyclic and contradictory data
-----------------------------
Classification is a pure set difference, so it degrades quietly rather than
looping: a self-loop (``a --derives-from--> a``) or a contradictory pair
(``a --decomposes--> b`` together with ``a --derives-from--> b``, which
asserts both that b is below a and that a is below b) makes the artifacts
involved neither root nor leaf. They then escape TRACE-P1 and VERIF-P8. That
is accepted for now: such rows are a data-integrity defect that the
validated write path already rejects (``TraceLinkManager.create`` runs
per-link-type cycle detection), so they only arise from direct ORM writes or
imports. Detecting them is a rule in its own right, not the job of a
classifier.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Set, Tuple
from uuid import UUID

from traceability.audit.types import AuditContext
from traceability.types import LinkType

#: Hierarchy links stored as parent -> child (source is the parent).
#: ``parent-child`` is gone — the migration folded it into ``decomposes``,
#: which carries the same direction (source = parent).
PARENT_TO_CHILD_LINK_TYPES: FrozenSet[str] = frozenset(
    {LinkType.DECOMPOSES.value}
)

#: Hierarchy links stored as child -> parent (source is the child) — the
#: inverse spelling of the same fact.
CHILD_TO_PARENT_LINK_TYPES: FrozenSet[str] = frozenset(
    {LinkType.DERIVES_FROM.value}
)

#: Every link type that carries Requirement-hierarchy information, in either
#: direction. Exported for callers that only need membership, not direction.
HIERARCHY_LINK_TYPES: FrozenSet[str] = (
    PARENT_TO_CHILD_LINK_TYPES | CHILD_TO_PARENT_LINK_TYPES
)


def requirement_hierarchy_edges(
    context: AuditContext, requirement_ids: FrozenSet[str]
) -> Set[Tuple[str, str]]:
    """Return the ``{(parent_id, child_id), ...}`` decomposition edges.

    Both link directions (see module docstring) are normalised into the same
    parent-first orientation. Edges with an endpoint outside
    *requirement_ids* (a StakeholderNeed, an ArchitectureElement, a
    soft-deleted or out-of-workspace Requirement) are ignored.

    Args:
        context: The audit context supplying the tenant's trace links.
        requirement_ids: Artifact ids of the Requirements under audit.

    Returns:
        Set of ``(parent_artifact_id, child_artifact_id)`` pairs.
    """
    edges: Set[Tuple[str, str]] = set()
    for link in context.iter_trace_links():
        link_type = link["link_type"]
        if link_type in PARENT_TO_CHILD_LINK_TYPES:
            parent_id, child_id = link["source_id"], link["target_id"]
        elif link_type in CHILD_TO_PARENT_LINK_TYPES:
            parent_id, child_id = link["target_id"], link["source_id"]
        else:
            continue
        if parent_id in requirement_ids and child_id in requirement_ids:
            edges.add((parent_id, child_id))
    return edges


def root_requirement_ids(
    context: AuditContext, requirement_ids: FrozenSet[str]
) -> FrozenSet[str]:
    """Return the subset of *requirement_ids* that have no hierarchy parent.

    The dynamic-graph stand-in for "L1 / SystemRequirement": nothing was
    decomposed/derived *into* it from another Requirement, so it is the top of
    its subgraph and TRACE-P1 requires it to derive from a StakeholderNeed.
    """
    child_ids = {child_id for _, child_id in requirement_hierarchy_edges(
        context, requirement_ids
    )}
    return requirement_ids - frozenset(child_ids)


def leaf_requirement_ids(
    context: AuditContext, requirement_ids: FrozenSet[str]
) -> FrozenSet[str]:
    """Return the subset of *requirement_ids* that have no hierarchy child.

    The mirror image of :func:`root_requirement_ids`: nothing was
    decomposed/derived *from* it, so it is the bottom of its subgraph and
    VERIF-P8 requires it to be verified by a TestCase.
    """
    parent_ids = {parent_id for parent_id, _ in requirement_hierarchy_edges(
        context, requirement_ids
    )}
    return requirement_ids - frozenset(parent_ids)


def classify_requirements(workspace_id: str | UUID) -> Dict[str, Set[str]]:
    """Return ``{"roots": {...}, "leaves": {...}}`` for a workspace's Requirements.

    Convenience wrapper for callers that only have a bare ``workspace_id``
    (e.g. ``diff_auditor_findings`` and its tests) and would otherwise have to
    duplicate the ``AuditContext`` + Requirement-id-set construction that
    :func:`_active_requirements` in ``rules/trace_derivation_allocation.py``
    and ``rules/coverage_consistency.py`` each do for their own, rule-specific
    (active/non-L4) needs. This wrapper deliberately does NOT replicate that
    filtering — it classifies every Requirement artifact in the workspace,
    active or not, L4 or not — so it stays a thin, general-purpose entry point
    over :func:`root_requirement_ids` / :func:`leaf_requirement_ids` rather
    than a third copy of rule-specific business logic.
    """
    from persistence.models import Requirement, Workspace

    workspace_id = str(workspace_id)
    tenant_id = str(Workspace.unscoped.values_list("tenant_id", flat=True).get(id=workspace_id))
    requirement_ids = frozenset(
        str(artifact_id)
        for artifact_id in Requirement.unscoped.filter(
            tenant_id=tenant_id, artifact__workspace_id=workspace_id
        ).values_list("artifact_id", flat=True)
    )
    # tier is irrelevant here: root/leaf classification only reads trace
    # links (AuditContext.iter_trace_links), never scope_item_ids, so no
    # rigor-preset resolution is needed for this read-only wrapper.
    context = AuditContext(tier="standard", workspace_id=workspace_id, tenant_id=tenant_id)
    return {
        "roots": set(root_requirement_ids(context, requirement_ids)),
        "leaves": set(leaf_requirement_ids(context, requirement_ids)),
    }


__all__ = [
    "CHILD_TO_PARENT_LINK_TYPES",
    "HIERARCHY_LINK_TYPES",
    "PARENT_TO_CHILD_LINK_TYPES",
    "classify_requirements",
    "leaf_requirement_ids",
    "requirement_hierarchy_edges",
    "root_requirement_ids",
]
