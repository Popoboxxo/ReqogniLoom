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

``refines`` is a **live built-in** link type (``link_types/builtin.py``,
re-introduced by issue #950 as ``Requirement -> Requirement`` with
``source = refining (lower-level) requirement, target = refined``). It is a
hierarchy *candidate* — the same direction as ``derives-from``, but a weaker
claim — and is deliberately **not** part of the hierarchy link-type sets
below. This is now a **decided** position (ADR-016, decision 3), not an open
question: a refinement is a semantic (impact/analysis) relation, not a
V-model level or ``document``-baseline edge, so it contributes no
``(parent, child)`` pair here. Reopening it would supersede ADR-016; this
module must not decide it on its own. Background: OFFENE FRAGE 2 in
``docs/superpowers/plans/Archive/2026-09-03-traceability-semantik.md``.

Only edges whose *both* endpoints are Requirements in the audited set count.
A ``Requirement --derives-from--> StakeholderNeed`` link is legal and common,
but it does not make the Requirement a decomposition child — a Requirement
derived straight from a Need is precisely the root (L1) case TRACE-P1 exists
to check.

Scope of this module (do not over-read it)
------------------------------------------
This module owns **two** things that are deliberately *not* unified into one
"hierarchy" abstraction, because unifying them would break them:

1. **root/leaf classification for the audit rules** — nothing broader. It is
   deliberately *not* the single representation of hierarchy in the system:

   - ``rules/decomposition_consistency._decomposes_requirement_pairs`` looks at
     ``decomposes`` links *only*, on purpose: TRACE-P5 exists precisely to check
     that a ``decomposes`` edge has its ``derives-from`` counterpart. Feeding it
     normalised edges would make the rule tautologically true.
   - ``ArchitectureElement.parent_id`` (and its ``Artifact.parent`` mirror) is a
     separate FK tree for architecture, never a TraceLink.

2. **the derivation of ``Requirement.level``** (ADR-005) —
   :func:`derive_requirement_levels` (pure) plus :func:`recompute_requirement_levels`
   (the single ORM writer). See "Level derivation (ADR-005)" below for why the
   writer lives in this module rather than in ``application/``.

Level derivation (ADR-005)
--------------------------
``Requirement.level`` is a **derived, read-only** field: it is recomputed from
the hierarchy on *every* hierarchy change, on all three write paths
(``RequirementService.decompose``, the ``Artifact.parent_id`` write path, and
TraceLink create/delete for ``decomposes``/``derives-from``). ``CONS-P11``,
which used to assert that the field agrees with the graph, was removed with it
— a rule that checks a derived field against its own source can never fire
(the same argument the bullet above already makes for TRACE-P5).

The derivation reads the **union** of the two hierarchy sources, because the
defect ADR-005 fixes is precisely that a change to *either* one used to leave
the field untouched:

* the TraceLink edges, normalised by :func:`normalise_hierarchy_edge` (both
  spellings), and
* the ``Artifact.parent_id`` FK tree, which the audit graph does **not**
  normalise and never did (see the module docstring above).

Conventions, derived from what the codebase already asserts — not invented
here:

* **A Requirement with no hierarchy parent is ``L1_SYSTEM``.** The seeded full
  chain gives ``level=L1_SYSTEM`` to exactly the Requirements that derive only
  from a StakeholderNeed (``auth_tenancy/management/commands/seed_full_chain.py``
  line ~182) and ``level=L2_SUBSYSTEM`` to their children (~219), and
  :func:`root_requirement_ids` already documents the root as the "L1 /
  SystemRequirement" stand-in. ``L0`` is not available: StakeholderNeed is a
  separate model, so ``Requirement.level`` spans L1..L4 only.
* **A child sits exactly one level below its parent** — the rule ``decompose``
  already applied via ``parent.level + 1``.

A node is left **NULL** (``level`` is nullable, and NULL is the honest
"not derivable" answer rather than a guess) when:

* the graph is cyclic among its ancestors, or the node hangs off such a cycle —
  the write path already rejects cycles for TraceLinks
  (``TraceLinkManager._reject_hierarchy_contradiction``) and for
  ``Artifact.parent_id`` (``ArtifactService._validate_no_cycle``), but rows
  predating those guards, direct ORM writes and imports can still be cyclic;
* its hierarchy parents **disagree** about where it sits (e.g. one parent at L1
  and another at L2). A converging DAG whose parents agree — the common,
  legal case — is derived normally; only genuine depth disagreement yields NULL,
  because any concrete value would be wrong for at least one parent edge;
* its parent is already at ``L4_PRESENTATION``, which has no tier below it.
  Clamping to L4 would emit a child at the *same* level as its parent, i.e. a
  data-integrity defect; NULL ("not assigned") is the honest answer. This
  preserves the pre-ADR-005 ``decompose`` behaviour, which also refused to guess
  here.

Why the writer lives here
-------------------------
:func:`recompute_requirement_levels` writes to ``Requirement.level`` from all
three hierarchy write paths, one of which (``TraceLinkManager.create`` /
``.delete``) lives in **Layer 1** (``traceability``). A Layer-1 module may not
import ``application`` (Layer 2, ADR-01), so the single writer cannot live
there. This module is the lowest layer that already owns the hierarchy
normalisation every one of those paths needs, which is what makes "exactly one
writer, reachable from every path" structural rather than a convention.

Like :func:`classify_requirements` below, the ORM access is deferred into the
function bodies so this module stays importable without pulling Django models
into the pure graph helpers above.

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

from collections import defaultdict
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Set, Tuple, TypeVar
from uuid import UUID

from persistence.models import RequirementLevel
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
#: ``refines`` is deliberately excluded — decided by ADR-016 (decision 3):
#: refinement is a weaker, semantic relation, not a hierarchy edge. See the
#: module docstring.
HIERARCHY_LINK_TYPES: FrozenSet[str] = (
    PARENT_TO_CHILD_LINK_TYPES | CHILD_TO_PARENT_LINK_TYPES
)

#: The V-model cascade level of a Requirement that has no hierarchy parent.
#: ``RequirementLevel`` spells the cascade as L1..L4 with the integer *being*
#: the level, and L0 is deliberately absent (StakeholderNeed is a separate
#: model, never a ``Requirement`` row) — so a Requirement can only ever be
#: L1..L4 and the top of the cascade is 1. ADR-005.
ROOT_REQUIREMENT_LEVEL: int = int(RequirementLevel.L1_SYSTEM)

#: Deepest level the cascade can express. A child of an L4 node has no legal
#: level, so :func:`derive_requirement_levels` leaves it NULL rather than
#: clamping it to 4 — a clamped child would sit at the *same* level as its
#: parent, which is the data-integrity defect CONS-P11 used to report.
CASCADE_TOP_LEVEL: int = int(RequirementLevel.L4_PRESENTATION)


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


def derive_requirement_levels(
    edges: Set[Tuple[_NodeId, _NodeId]],
    node_ids: Optional[Iterable[_NodeId]] = None,
    *,
    root_level: int = ROOT_REQUIREMENT_LEVEL,
    cascade_top: int = CASCADE_TOP_LEVEL,
) -> Dict[_NodeId, Optional[int]]:
    """Return ``{node_id: level_or_None}`` for the V-model cascade (ADR-005).

    The pure half of the ``Requirement.level`` derivation: given already
    normalised ``(parent_id, child_id)`` pairs, work out where each node sits
    in the V-model cascade. A node's level is ``parent.level + 1`` for every
    hierarchy parent it has, and :data:`ROOT_REQUIREMENT_LEVEL` when it has
    none — see the "Level derivation" section of the module docstring for why
    those two conventions are the ones the codebase already asserts.

    **Not derivable → ``None``.** A ``None`` in the result means "the graph does
    not determine a level for this node", never "level 0": the caller stores
    SQL ``NULL`` for it. That happens for a node on (or below) a cycle, for a
    node whose parents disagree about its depth, and for a child of
    *cascade_top*, which has no tier below it. See the module docstring for the
    reasoning; in short, any concrete value for those cases would be *wrong*,
    and a derived field that can be wrong is the defect this wave removes.

    Iterative, not recursive: a post-order DFS over an explicit frame stack, for
    the same reason :func:`cyclic_hierarchy_nodes` avoids recursion — a chain of
    a few thousand derived Requirements must not be able to exhaust the
    interpreter's recursion limit. The visited set makes every frame resolve
    exactly once, and an ancestor already on the current path is treated as the
    cycle it is.

    Args:
        edges: Normalised ``(parent_id, child_id)`` pairs. Both directions are
            the caller's job to normalise — this function is the same pure
            graph function as :func:`cyclic_hierarchy_nodes`.
        node_ids: The nodes to report on. Defaults to every node mentioned by
            *edges*. Nodes outside the subgraph are never consulted, so a
            caller recomputing a subtree must close it under *ancestors* (see
            :func:`recompute_requirement_levels`, which does) or the topmost
            node of the subgraph would be misread as a root.
        root_level: Level assigned to a node with no hierarchy parent.
        cascade_top: Deepest expressible level; a child below it is not
            derivable.

    Returns:
        ``{node_id: level}`` with ``level`` an ``int`` in
        ``root_level..cascade_top`` or ``None`` when not derivable.
    """
    parents: Dict[_NodeId, Set[_NodeId]] = defaultdict(set)
    for parent_id, child_id in edges:
        parents[child_id].add(parent_id)

    nodes: List[_NodeId] = (
        sorted({node for edge in edges for node in edge}, key=repr)
        if node_ids is None
        else list(dict.fromkeys(node_ids))
    )

    resolved: Dict[_NodeId, Optional[int]] = {}
    for start in nodes:
        if start in resolved:
            continue
        # Frame: [node, parents still to visit, set of their resolved levels].
        # An empty level set means "no hierarchy parent in this subgraph".
        stack: List[List[Any]] = [[start, list(parents.get(start, ())), set()]]
        on_path = {start}
        while stack:
            frame = stack[-1]
            if frame[1]:
                parent_id = frame[1].pop()
                if parent_id in resolved:
                    frame[2].add(resolved[parent_id])
                elif parent_id in on_path:
                    # Reached an ancestor: this component is cyclic, so the
                    # ancestor's own level is what is unknown, not this edge.
                    frame[2].add(None)
                else:
                    on_path.add(parent_id)
                    stack.append([parent_id, list(parents.get(parent_id, ())), set()])
                continue
            levels = frame[2]
            if not levels:
                level: Optional[int] = root_level
            elif len(levels) > 1:
                level = None  # parents disagree about this node's depth
            else:
                parent_level = next(iter(levels))
                if parent_level is None or parent_level + 1 > cascade_top:
                    level = None
                else:
                    level = parent_level + 1
            resolved[frame[0]] = level
            stack.pop()
            on_path.discard(frame[0])
            if stack:
                stack[-1][2].add(level)

    return {node_id: resolved.get(node_id) for node_id in nodes}


def _tenant_hierarchy_subgraph(
    tenant_id: UUID,
) -> Tuple[Dict[UUID, Optional[int]], Set[Tuple[UUID, UUID]]]:
    """Return ``({artifact_id: current level}, {(parent, child), ...})``.

    The tenant's Requirement hierarchy as the union of its **two** sources (see
    the module docstring): the ``Artifact.parent_id`` FK tree and the
    normalised TraceLink edges. Only pairs whose *both* endpoints are
    Requirements of this tenant become edges — an
    ``ArchitectureElement --decomposes--> Requirement`` link carries no
    cascade position for a Requirement, exactly as
    :func:`requirement_hierarchy_edges` already declines to read it for
    root/leaf classification.

    ``current level`` is read in the same pass so the caller can report which
    rows a write actually changed.

    Deferred imports and ``unscoped``: same convention as
    :func:`classify_requirements` below — tenant and workspace are supplied
    explicitly by the caller, so the thread-local ``objects`` manager is
    bypassed on purpose; Row-Level Security remains the DB-level backstop.
    """
    from persistence.models import Requirement, TraceLink

    rows = list(
        Requirement.unscoped.filter(tenant_id=tenant_id).values(
            "artifact_id", "level", "artifact__parent_id"
        )
    )
    current: Dict[UUID, Optional[int]] = {}
    fk_edges: Set[Tuple[UUID, UUID]] = set()
    for row in rows:
        artifact_id = row["artifact_id"]
        current[artifact_id] = row["level"]
        parent_id = row["artifact__parent_id"]
        if parent_id is not None:
            fk_edges.add((parent_id, artifact_id))

    edges = {edge for edge in fk_edges if edge[0] in current}
    for source_id, target_id, link_type in TraceLink.unscoped.filter(
        tenant_id=tenant_id, link_type__in=HIERARCHY_LINK_TYPES
    ).values_list("source_id", "target_id", "link_type"):
        normalised = normalise_hierarchy_edge(link_type, source_id, target_id)
        if normalised is None:  # pragma: no cover — filtered above
            continue
        parent_id, child_id = normalised
        if parent_id in current and child_id in current:
            edges.add((parent_id, child_id))
    return current, edges


def _close_under(
    seeds: Iterable[_NodeId],
    adjacency: Mapping[_NodeId, Set[_NodeId]],
) -> Set[_NodeId]:
    """Return *seeds* plus everything reachable from them along *adjacency*."""
    reached: Set[_NodeId] = set()
    frontier = list(seeds)
    while frontier:
        node = frontier.pop()
        if node in reached:
            continue
        reached.add(node)
        frontier.extend(adjacency.get(node, ()))
    return reached


def recompute_requirement_levels(
    changed_artifact_ids: Iterable[UUID | str],
    *,
    fill_only: bool = False,
) -> Dict[UUID, Optional[int]]:
    """Recompute ``Requirement.level`` for the hierarchy around *changed ids*.

    **The single writer of ``Requirement.level``** (ADR-005). Every hierarchy
    write path calls it: ``RequirementService.create_requirement`` /
    ``update_requirement`` (the ``parent_id`` path),
    ``ArtifactService.update_artifact`` and ``TraceLinkManager.create`` /
    ``.delete`` / ``.batch_create`` / ``.batch_delete``. One implementation is
    what makes "derived, never hand-maintained" true rather than aspirational.

    What is recomputed: the changed nodes, **their whole descendant subtree**
    (a multi-level move shifts every level below it, not just the moved node —
    the recommendation ADR-005 left open), and their **ancestor chain** so the
    topmost node of the recomputed subgraph is a genuine hierarchy root rather
    than a subgraph boundary that would be misread as one. Siblings of a moved
    node are *not* touched: their parents, and therefore their levels, did not
    change.

    Args:
        changed_artifact_ids: Artifact ids whose position in the hierarchy
            changed. Ids that do not address a Requirement of a single tenant
            are ignored (a no-op), so a caller does not have to know the artifact
            type — ``TraceLinkManager`` passes both endpoints of every
            hierarchy link and lets this filter.
        fill_only: Never overwrite a level that is already set; only fill
            ``NULL``. This is the **calibration** contract and is deliberately
            *not* the write-path contract:

            * *calibration* (``fill_only=True``) exists to give the pre-ADR-005
              corpus — which was never backfilled, migration ``0040`` — a
              derived level, and it must not silently overwrite a hand-set
              value such as a pre-existing ``level == L4``, which three audit
              rules (TRACE-P5, ARCH-003, VERIF-P8) use as their only L4 filter
              and which no derivation can distinguish from a deliberate choice;
            * the *write path* (``fill_only=False``) does overwrite, because the
              user has just changed the hierarchy and a field that keeps its old
              value across a re-parent is the very defect ADR-005 removes.

            Either way a row is only ever written with a value the current
            graph justifies at the moment of the write, so a ``NULL`` can never
            become a wrong non-``NULL`` value and a hierarchy that does not
            determine a level leaves the row ``NULL``.

    Returns:
        ``{artifact_id: level}`` for the rows whose stored value this call
        actually changed (``None`` for a row set back to ``NULL``). Empty when
        nothing moved.
    """
    from persistence.models import Requirement

    seed_ids = {
        artifact_id
        for artifact_id in (
            raw if isinstance(raw, UUID) else UUID(str(raw)) for raw in changed_artifact_ids
        )
    }
    if not seed_ids:
        return {}

    tenant_id = _seed_tenant(seed_ids)
    if tenant_id is None:
        return {}
    current, edges = _tenant_hierarchy_subgraph(tenant_id)
    if not current:
        return {}
    seeds = seed_ids & set(current)
    if not seeds:
        return {}

    parents: Dict[UUID, Set[UUID]] = defaultdict(set)
    children: Dict[UUID, Set[UUID]] = defaultdict(set)
    for parent_id, child_id in edges:
        children[parent_id].add(child_id)
        parents[child_id].add(parent_id)

    # Ancestors up, descendants down — the smallest subgraph in which the
    # topmost node is a true root and every shifted level is covered.
    scope = _close_under(seeds, parents) | _close_under(seeds, children)
    scope_edges = {edge for edge in edges if edge[1] in scope}
    derived = derive_requirement_levels(scope_edges, sorted(scope, key=repr))

    grouped: Dict[Optional[int], List[UUID]] = defaultdict(list)
    for artifact_id, level in derived.items():
        if level == current.get(artifact_id):
            continue
        if fill_only and current.get(artifact_id) is not None:
            continue
        grouped[level].append(artifact_id)

    changed: Dict[UUID, Optional[int]] = {}
    for level, artifact_ids in grouped.items():
        # A bulk UPDATE, not save(): ``level`` is a derived field, so a
        # hierarchy edit must not append a content revision or bump the version
        # counter of every node in the moved subtree. The cost of that choice
        # is recorded in the ADR-005 report — the baseline diff engine sees a
        # level change at the next content write, not at the hierarchy write.
        Requirement.unscoped.filter(artifact_id__in=artifact_ids).update(level=level)
        changed.update({artifact_id: level for artifact_id in artifact_ids})
    return changed


def _seed_tenant(seed_ids: Set[UUID]) -> Optional[UUID]:
    """Return the tenant that owns *seed_ids*, or ``None`` if none resolves.

    Read from the artifacts rather than from :class:`TenantContext` so the
    derivation does not depend on a thread-local being set by the caller, and so
    a stray cross-tenant id cannot make the queries span tenants: any id that
    does not belong to the returned tenant is simply not in ``current`` and is
    dropped.

    ``None`` — rather than a raise — for an id that addresses no Artifact at
    all. All three write paths call this right after writing the row, so a
    missing one means "already gone" (a concurrent delete, or a caller that
    never had a real id): there is no hierarchy left to re-derive, and turning
    that into an exception would roll back an otherwise successful, unrelated
    write.
    """
    from persistence.models import Artifact

    return (
        Artifact.unscoped.filter(id__in=seed_ids)
        .values_list("tenant_id", flat=True)
        .first()
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
    "CASCADE_TOP_LEVEL",
    "CHILD_TO_PARENT_LINK_TYPES",
    "HIERARCHY_LINK_TYPES",
    "PARENT_TO_CHILD_LINK_TYPES",
    "ROOT_REQUIREMENT_LEVEL",
    "classify_requirements",
    "cyclic_hierarchy_nodes",
    "derive_requirement_levels",
    "hierarchy_cycle_nodes",
    "leaf_requirement_ids",
    "normalise_hierarchy_edge",
    "recompute_requirement_levels",
    "requirement_hierarchy_edges",
    "root_requirement_ids",
]
