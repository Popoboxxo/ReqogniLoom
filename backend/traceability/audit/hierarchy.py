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
asserts both that b is below a and that a is below b — the two normalise to
``(a, b)`` *and* ``(b, a)``) makes the artifacts involved neither root nor
leaf, i.e. it makes ``root_requirement_ids`` return ∅ for the whole
subgraph. They then escape TRACE-P1 and VERIF-P8 entirely.

Since issue #1021 that state is no longer accepted silently, on either side
of the write path:

* :func:`hierarchy_cycle_nodes` names the artifacts that lie on a cycle in
  the normalised graph, and ``SystemRequirementDerivesFromNeedRule`` reports
  them (and still runs TRACE-P1 against them) instead of returning no result;
* ``TraceLinkManager.create`` rejects the write that would create the
  contradictory pair in the first place — deliberately against the *union*
  of both link types, because the per-link-type cycle check there cannot see
  a cycle whose two halves carry different link types.

Rows that predate that guard (direct ORM writes, imports, data migrations)
are exactly what :func:`hierarchy_cycle_nodes` is for.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set, Tuple, TypeVar
from uuid import UUID

from traceability.audit.types import AuditContext
from traceability.types import LinkType

#: An artifact id as it appears in the audit graph — ``str`` for
#: :class:`AuditContext` consumers, ``uuid.UUID`` for the ORM-facing callers
#: (``TraceLinkManager``). The helpers below never inspect the value.
_NodeId = TypeVar("_NodeId")

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


def normalise_hierarchy_edge(
    link_type: str, source_id: _NodeId, target_id: _NodeId
) -> Optional[Tuple[_NodeId, _NodeId]]:
    """Return the ``(parent_id, child_id)`` normalisation of one hierarchy link.

    The single direction table of this module, so every caller (the audit
    classifier *and* ``TraceLinkManager``'s write-path guard, #1021) resolves
    ``decomposes`` (parent -> child) and ``derives-from`` (child -> parent)
    the same way instead of re-implementing the inversion.

    Args:
        link_type: A link type key (``TraceLink.link_type``).
        source_id: The link's source artifact id (``str`` or ``UUID`` — the
            helper is type-agnostic and returns whatever it was given).
        target_id: The link's target artifact id.

    Returns:
        ``(parent_id, child_id)`` for a hierarchy link; ``None`` for every
        other link type (this is not a "no parent" answer, it is "this edge
        carries no hierarchy information").
    """
    if link_type in PARENT_TO_CHILD_LINK_TYPES:
        return source_id, target_id
    if link_type in CHILD_TO_PARENT_LINK_TYPES:
        return target_id, source_id
    return None


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
        normalised = normalise_hierarchy_edge(
            link["link_type"], link["source_id"], link["target_id"]
        )
        if normalised is None:
            continue
        parent_id, child_id = normalised
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


def cyclic_hierarchy_nodes(
    edges: Set[Tuple[_NodeId, _NodeId]],
) -> FrozenSet[_NodeId]:
    """Return the node ids that lie on a cycle in *edges* (issue #1021).

    Pure graph function over already-normalised ``(parent_id, child_id)``
    pairs — the counterpart of the quiet set difference in
    :func:`root_requirement_ids`, which cannot tell "no Requirement is a
    root" apart from "this subgraph is cyclic".

    A node is cyclic when it is a member of a strongly connected component of
    size > 1, or when it carries a self-loop. Both are the same
    data-integrity defect: the node is its own ancestor, so no artifact in its
    component is ever a root or a leaf and TRACE-P1/VERIF-P8 skip the whole
    component.

    Tarjan's SCC algorithm, iterative (an explicit work stack, not recursion:
    a workspace with a few thousand Requirements must not be able to exhaust
    the interpreter's recursion limit — the same reason
    ``TraceLinkManager._tarjan_find_cycle`` is written the way it is, though
    that one stops at the first cycle and returns only its nodes).

    Args:
        edges: Normalised ``(parent_id, child_id)`` pairs, e.g. from
            :func:`requirement_hierarchy_edges`.

    Returns:
        The ids of every node on a cycle; empty for a DAG (the normal case).
    """
    adjacency: Dict[_NodeId, List[_NodeId]] = {}
    cyclic: Set[_NodeId] = set()
    for parent_id, child_id in edges:
        adjacency.setdefault(parent_id, []).append(child_id)
        adjacency.setdefault(child_id, [])
        if parent_id == child_id:
            # A self-loop is an SCC of size 1 and would otherwise be missed.
            cyclic.add(parent_id)

    index: Dict[_NodeId, int] = {}
    lowlink: Dict[_NodeId, int] = {}
    on_stack: Set[_NodeId] = set()
    stack: List[_NodeId] = []
    counter = 0

    for root in adjacency:
        if root in index:
            continue
        index[root] = lowlink[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work: List[Tuple[_NodeId, int]] = [(root, 0)]

        while work:
            node, neighbour_index = work[-1]
            neighbours = adjacency.get(node, [])
            if neighbour_index < len(neighbours):
                neighbour = neighbours[neighbour_index]
                work[-1] = (node, neighbour_index + 1)
                if neighbour not in index:
                    index[neighbour] = lowlink[neighbour] = counter
                    counter += 1
                    stack.append(neighbour)
                    on_stack.add(neighbour)
                    work.append((neighbour, 0))
                elif neighbour in on_stack:
                    lowlink[node] = min(lowlink[node], index[neighbour])
                continue

            work.pop()
            if lowlink[node] == index[node]:
                component: List[_NodeId] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    cyclic.update(component)
            if work:
                parent_node = work[-1][0]
                lowlink[parent_node] = min(lowlink[parent_node], lowlink[node])

    return frozenset(cyclic)


def hierarchy_cycle_nodes(
    context: AuditContext, requirement_ids: FrozenSet[str]
) -> FrozenSet[str]:
    """Return the Requirement ids of *requirement_ids* that lie on a cycle.

    The "why is ``root_requirement_ids`` empty?" answer for the audit rules:
    a non-empty result means the normalised hierarchy graph contains a
    contradictory pair, a self-loop or a longer mixed-type cycle, and every
    returned Requirement escaped TRACE-P1/VERIF-P8 before #1021.
    """
    return cyclic_hierarchy_nodes(
        requirement_hierarchy_edges(context, requirement_ids)
    )


def classify_requirements(workspace_id: str | UUID) -> Dict[str, Set[str]]:
    """Return ``{"roots", "leaves", "cycle_nodes"}`` for a workspace's Requirements.

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

    ``cycle_nodes`` (issue #1021) is the diagnostic companion: when it is
    non-empty, ``roots``/``leaves`` are not "the hierarchy is flat", they are
    the degraded answer of a cyclic subgraph. Additive key — callers that only
    read ``roots``/``leaves`` are unaffected.
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
        "cycle_nodes": set(hierarchy_cycle_nodes(context, requirement_ids)),
    }


__all__ = [
    "CHILD_TO_PARENT_LINK_TYPES",
    "HIERARCHY_LINK_TYPES",
    "PARENT_TO_CHILD_LINK_TYPES",
    "classify_requirements",
    "cyclic_hierarchy_nodes",
    "hierarchy_cycle_nodes",
    "leaf_requirement_ids",
    "normalise_hierarchy_edge",
    "requirement_hierarchy_edges",
    "root_requirement_ids",
]
