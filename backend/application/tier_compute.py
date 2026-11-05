"""Leaf-relative requirement tier computation (P2, V4/V6/R11).

The single writer of ``Requirement.tier_key`` and its integer alias ``level``
(the ADR-005 successor). The tier of an ArchitectureElement is decided from the
**leaf side**: a leaf is the last ladder entry, its parent the second-to-last,
and a root is the first entry regardless of how deep the tree is. Mixed-depth
branches therefore stay unambiguous.

A Requirement's tier follows the source order decided by the PO:

1. ``manual`` — an explicit human override is never overwritten;
2. ``allocation`` — the tier of the allocated ArchitectureElement;
3. hierarchy — the parent Requirement's tier moved one position toward the end
   of the ladder (no tier below the last entry);
4. type default — not modelled yet, so this falls through to unresolved;
5. unresolved — ``tier_key = NULL``, ``level_source = 'unresolved'``.

Nothing is clamped or guessed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from application.tier_ladder_service import TierLadder, TierLadderService
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    RequirementLevelSource,
    TraceLink,
    WorkspaceTierRule,
)

_ALLOCATED_TO = "allocated-to"
_HIERARCHY_PARENT_TO_CHILD = frozenset({"decomposes"})
_HIERARCHY_CHILD_TO_PARENT = frozenset({"derives-from", "refines"})


@dataclass(frozen=True)
class LevelChange:
    """One requirement whose tier/level moved."""

    artifact_id: UUID
    old_tier_key: str | None
    new_tier_key: str | None
    old_level: int | None
    new_level: int | None
    old_source: str
    new_source: str


def _element_heights(
    elements: list[tuple[UUID, UUID, UUID | None]],
) -> tuple[dict[UUID, int], set[UUID]]:
    """Return ``({element_id: longest_path_to_leaf}, root_ids)``."""
    parent_by_id: dict[UUID, UUID | None] = {}
    children: dict[UUID, list[UUID]] = defaultdict(list)
    roots: set[UUID] = set()
    for element_id, _artifact_id, parent_id in elements:
        parent_by_id[element_id] = parent_id
        if parent_id is None:
            roots.add(element_id)
        else:
            children[parent_id].append(element_id)

    heights: dict[UUID, int] = {}
    visiting: set[UUID] = set()

    def height(element_id: UUID) -> int:
        if element_id in heights:
            return heights[element_id]
        if element_id in visiting:
            # Pre-existing cycle: treat as a leaf so the walk terminates.
            return 0
        visiting.add(element_id)
        child_heights = [height(child) for child in children.get(element_id, ())]
        value = 0 if not child_heights else 1 + max(child_heights)
        visiting.discard(element_id)
        heights[element_id] = value
        return value

    for element_id in parent_by_id:
        height(element_id)
    return heights, roots


def tier_for_element(
    element_id: UUID,
    ladder: TierLadder,
    heights: dict[UUID, int],
    roots: set[UUID],
) -> str | None:
    """Return the ladder key for one ArchitectureElement, or ``None``."""
    if element_id in roots:
        return ladder.first_key()
    matched = ladder.from_end_key(heights.get(element_id, 0))
    if matched is not None:
        return matched
    if any(entry.rule == WorkspaceTierRule.MIDDLE for entry in ladder.entries):
        return ladder.middle_key()
    return None


def _requirement_parents(
    workspace_id: UUID, requirement_artifact_ids: set[UUID]
) -> dict[UUID, set[UUID]]:
    """Union of the FK tree and the derives-from/decomposes links."""
    parents: dict[UUID, set[UUID]] = defaultdict(set)

    for artifact_id, parent_id in (
        Artifact.unscoped.filter(
            workspace_id=workspace_id,
            artifact_type="Requirement",
        ).values_list("id", "parent_id")
    ):
        if parent_id is not None and artifact_id in requirement_artifact_ids:
            parents[artifact_id].add(parent_id)

    for source_id, target_id, link_type in TraceLink.unscoped.filter(
        link_type__in=_HIERARCHY_PARENT_TO_CHILD | _HIERARCHY_CHILD_TO_PARENT
    ).values_list("source_id", "target_id", "link_type"):
        if link_type in _HIERARCHY_PARENT_TO_CHILD:
            parent_id, child_id = source_id, target_id
        else:
            parent_id, child_id = target_id, source_id
        if child_id in requirement_artifact_ids and parent_id in requirement_artifact_ids:
            parents[child_id].add(parent_id)
    return parents


def _allocations(workspace_id: UUID, requirement_artifact_ids: set[UUID]) -> dict[UUID, UUID]:
    """``{requirement_artifact_id: target_element_artifact_id}``."""
    result: dict[UUID, UUID] = {}
    for source_id, target_id in TraceLink.unscoped.filter(
        link_type=_ALLOCATED_TO, source_id__in=requirement_artifact_ids
    ).values_list("source_id", "target_id"):
        result[source_id] = target_id
    return result


def _cycle_nodes(parents: dict[UUID, set[UUID]], node_ids: set[UUID]) -> set[UUID]:
    """Return every requirement id that sits on a cycle in the parent graph."""
    cycle: set[UUID] = set()
    state: dict[UUID, int] = {}

    def walk(node: UUID, stack: list[UUID]) -> None:
        if state.get(node) == 1:
            if node in stack:
                cycle.update(stack[stack.index(node):])
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        stack.append(node)
        for parent_id in parents.get(node, ()):  # type: ignore[arg-type]
            if parent_id in node_ids:
                walk(parent_id, stack)
        stack.pop()
        state[node] = 2

    for node_id in node_ids:
        walk(node_id, [])
    return cycle


def _derive_tiers(
    workspace_id: UUID,
    requirements: dict[UUID, dict],
    ladder: TierLadder,
    allocations: dict[UUID, UUID],
    element_tier_by_artifact: dict[UUID, str | None],
    parents: dict[UUID, set[UUID]],
) -> dict[UUID, tuple[str | None, int | None, str]]:
    """Return ``{artifact_id: (tier_key, level, level_source)}`` for every req."""
    resolved: dict[UUID, tuple[str | None, int | None, str]] = {}
    visiting: set[UUID] = set()
    cycle_nodes = _cycle_nodes(parents, set(requirements))

    def compute(artifact_id: UUID) -> tuple[str | None, int | None, str]:
        if artifact_id in resolved:
            return resolved[artifact_id]
        current = requirements.get(artifact_id)
        if current is None:
            return (None, None, RequirementLevelSource.UNRESOLVED)
        if current["level_source"] == RequirementLevelSource.MANUAL:
            resolved[artifact_id] = (
                current["tier_key"],
                current["level"],
                RequirementLevelSource.MANUAL,
            )
            return resolved[artifact_id]
        if artifact_id in cycle_nodes:
            resolved[artifact_id] = (None, None, RequirementLevelSource.UNRESOLVED)
            return resolved[artifact_id]
        if artifact_id in visiting:
            resolved[artifact_id] = (None, None, RequirementLevelSource.UNRESOLVED)
            return resolved[artifact_id]
        visiting.add(artifact_id)

        allocation_target = allocations.get(artifact_id)
        if allocation_target is not None:
            tier_key = element_tier_by_artifact.get(allocation_target)
            if tier_key is None:
                outcome = (None, None, RequirementLevelSource.UNRESOLVED)
            else:
                position = ladder.position_of(tier_key)
                outcome = (
                    tier_key,
                    position + 1 if position is not None else None,
                    RequirementLevelSource.DERIVED_ALLOCATION,
                )
            visiting.discard(artifact_id)
            resolved[artifact_id] = outcome
            return outcome

        parent_ids = parents.get(artifact_id) or set()
        parent_positions = [
            ladder.position_of(compute(parent_id)[0])
            for parent_id in parent_ids
            if compute(parent_id)[0] is not None
        ]
        parent_positions = [pos for pos in parent_positions if pos is not None]
        if parent_positions:
            next_position = max(parent_positions) + 1
            next_key = ladder.key_at(next_position)
            if next_key is None:
                outcome = (None, None, RequirementLevelSource.UNRESOLVED)
            else:
                outcome = (
                    next_key,
                    next_position + 1,
                    RequirementLevelSource.DERIVED_HIERARCHY,
                )
        elif parent_ids:
            # Parents exist but none resolves (cycle/unresolved). Never guess
            # a type default here: that would make a cyclic row look placed.
            outcome = (None, None, RequirementLevelSource.UNRESOLVED)
        else:
            # PO decision (2026-11-05): the type default is the first ladder
            # entry for every requirement type, so a root requirement without
            # an allocation keeps the legacy L1 starting point and its children
            # inherit +1. This is what preserves the pre-P2 level corpus while
            # allocation still wins above it.
            first_key = ladder.first_key()
            if first_key is None:
                outcome = (None, None, RequirementLevelSource.UNRESOLVED)
            else:
                position = ladder.position_of(first_key)
                outcome = (
                    first_key,
                    position + 1 if position is not None else None,
                    RequirementLevelSource.DERIVED_TYPE,
                )
        visiting.discard(artifact_id)
        resolved[artifact_id] = outcome
        return outcome

    for artifact_id in requirements:
        compute(artifact_id)
    return resolved


def recompute_workspace_tiers(
    workspace_id: UUID,
    *,
    parent_of_artifact: dict[UUID, UUID | None] | None = None,
    dry_run: bool = False,
    fill_only: bool = False,
) -> list[LevelChange]:
    """Recompute every requirement's tier in *workspace_id*.

    ``parent_of_artifact`` lets a caller that is currently moving one artifact
    supply the post-write parent map (Artifact.parent) instead of reading the
    not-yet-committed value.
    """
    ladder = TierLadderService().get(workspace_id)

    elements = list(
        ArchitectureElement.unscoped.filter(
            artifact__workspace_id=workspace_id
        ).values_list("id", "artifact_id", "parent_id")
    )
    heights, roots = _element_heights(elements)
    element_tier_by_artifact: dict[UUID, str | None] = {
        artifact_id: tier_for_element(element_id, ladder, heights, roots)
        for element_id, artifact_id, _parent_id in elements
    }

    requirements: dict[UUID, dict] = {}
    for artifact_id, level, level_source, tier_key in (
        Requirement.unscoped.filter(workspace_id=workspace_id).values_list(
            "artifact_id", "level", "level_source", "tier_key"
        )
    ):
        requirements[artifact_id] = {
            "level": level,
            "level_source": level_source,
            "tier_key": tier_key,
        }

    if parent_of_artifact is not None:
        parents: dict[UUID, set[UUID]] = defaultdict(set)
        for artifact_id in requirements:
            parent_id = parent_of_artifact.get(artifact_id)
            if parent_id is not None and parent_id in requirements:
                parents[artifact_id].add(parent_id)
    else:
        parents = _requirement_parents(workspace_id, set(requirements))

    allocations = _allocations(workspace_id, set(requirements))
    derived = _derive_tiers(
        workspace_id,
        requirements,
        ladder,
        allocations,
        element_tier_by_artifact,
        parents,
    )

    changes: list[LevelChange] = []
    grouped: dict[tuple[str | None, int | None, str], list[UUID]] = defaultdict(list)
    for artifact_id, (tier_key, level, source) in derived.items():
        current = requirements[artifact_id]
        if (
            current["tier_key"] == tier_key
            and current["level"] == level
            and current["level_source"] == source
        ):
            continue
        if fill_only and (current["level"] is not None or level is None):
            continue
        if current["level_source"] == RequirementLevelSource.MANUAL and source == RequirementLevelSource.MANUAL:
            continue
        changes.append(
            LevelChange(
                artifact_id=artifact_id,
                old_tier_key=current["tier_key"],
                new_tier_key=tier_key,
                old_level=current["level"],
                new_level=level,
                old_source=current["level_source"],
                new_source=source,
            )
        )
        grouped[(tier_key, level, source)].append(artifact_id)

    if dry_run or not grouped:
        return changes

    with transaction.atomic():
        for (tier_key, level, source), artifact_ids in grouped.items():
            Requirement.unscoped.filter(artifact_id__in=artifact_ids).update(
                tier_key=tier_key, level=level, level_source=source
            )
    return changes
