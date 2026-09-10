"""The hard TraceLink migration, as testable functions.

Kept out of the numbered migration module so the behaviour can be tested
against real rows without replaying migration state; the migration is a thin
wrapper that calls these in order.

Order is not optional:

1. ``migrate_copy_of_links``   — deletes rows, so it runs before anything that
                                 could collide with them.
2. ``migrate_parent_child_links`` — a parent-child edge may already have a
                                 twin ``decomposes`` edge for the same pair.
3. ``migrate_renamed_links``   — after the endpoint swap two formerly distinct
                                 edges can become the same
                                 ``(source, target, link_type)`` triple, which
                                 ``uq_tracelink_edge`` (issue #126) forbids.
4. ``verify_migrated_links``  — post-condition: every surviving row must still
                                 be creatable under the new catalog.

Every step takes its models as arguments so a migration can pass the
historical ``apps.get_model`` versions instead of the live ones.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from uuid import UUID

from .builtin import BUILTIN_LINK_TYPES, LEGACY_LINK_TYPE_MAPPING, SWAPPED_LEGACY_KEYS
from .grandfathered import apply_grandfathered_pairs

logger = logging.getLogger(__name__)

#: Legacy keys that are renamed rather than restructured.
_RENAMED = {
    legacy: successor
    for legacy, successor in LEGACY_LINK_TYPE_MAPPING.items()
    if successor is not None
}

#: Rows whose *endpoint type* — not their key — decides the successor, as
#: ``(link_type, endpoint, artifact_type, successor)``. Endpoints are kept as
#: they are; only the key changes. Applied before the mechanical rename below,
#: and mirrored by :func:`predict_migrated_triple`.
#:
#: ``satisfies`` -> ``derives-from`` when the target is a StakeholderNeed: the
#: legacy key covered two relations and only one of them is an allocation, see
#: :func:`_migrate_endpoint_exceptions`.
#:
#: ``verifies`` -> ``mitigates`` when the source is a Risk (issue #893): a Risk
#: does not verify anything, and ``mitigates`` Risk -> Requirement /
#: ArchitectureElement is the built-in pair that means what those rows meant.
#: Without this they survive the migration as ``verifies`` Risk -> Requirement,
#: which no catalog entry allows — the triple that made the first real-world
#: beta.6 -> beta.7 upgrade roll back.
_ENDPOINT_EXCEPTIONS: Tuple[Tuple[str, str, str, str], ...] = (
    ("satisfies", "target", "StakeholderNeed", "derives-from"),
    ("verifies", "source", "Risk", "mitigates"),
)

#: Suffix for the second half of every counts key: rows the rename dropped
#: because they collided with an existing edge. Kept apart from the rewritten
#: count so the migration log — the only record an irreversible migration
#: leaves behind — cannot report a deleted row as a rewritten one.
_DROPPED_SUFFIX = ":dropped"

#: ``{key: ((source_type, target_type), ...)}`` — the endpoint pairs a
#: freshly provisioned workspace catalog allows, built-ins plus the
#: grandfathered legacy pairs, i.e. exactly what
#: ``link_types/0003_seed_builtin_link_types`` + ``0004_grandfather_observed_pairs``
#: write into ``WorkspaceLinkTypeDefinition``. Used by
#: :func:`verify_migrated_links`; same matching rule as
#: ``catalog.validate_link_pair``, and — through :func:`is_creatable` — by the
#: ``blocking`` section of ``manage.py inventory_link_types``.
_ALLOWED_PAIRS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    key: tuple(
        (pair["source_type"], pair["target_type"])
        for pair in apply_grandfathered_pairs(definition, key)["allowed_pairs"]
    )
    for key, definition in BUILTIN_LINK_TYPES.items()
}


def _base_type(artifact_type: str | None) -> str:
    """Strip the sub-type tag: ``"TestCase:System"`` -> ``"TestCase"``.

    Mirrors the retired ``traceability.types.normalize_artifact_type``, which
    is what the legacy endpoint matrix compared against.
    """
    return (artifact_type or "").split(":", 1)[0]


def _base_artifact_type(artifact: Any) -> str:
    """:func:`_base_type` of an artifact row's ``artifact_type``."""
    return _base_type(getattr(artifact, "artifact_type", ""))


def is_creatable(link_type: str, source_type: str, target_type: str) -> bool:
    """Would the new catalog accept this triple? ``"*"`` matches anything.

    Built-ins plus ``GRANDFATHERED_PAIRS``, i.e. exactly what
    :func:`verify_migrated_links` refuses to finish without. Public so
    ``manage.py inventory_link_types`` can answer "will migration
    ``persistence/0081`` reject this database?" with the migration's own rule
    instead of a second, drifting copy of it (issue #893).
    """
    for allowed_source, allowed_target in _ALLOWED_PAIRS.get(link_type, ()):
        if allowed_source in ("*", source_type) and allowed_target in (
            "*",
            target_type,
        ):
            return True
    return False


def predict_migrated_triple(
    link_type: str, source_type: str, target_type: str
) -> Tuple[str, str, str] | None:
    """The triple a row will carry *after* the migration, without touching it.

    The read-only mirror of :func:`migrate_renamed_links` and
    :func:`migrate_parent_child_links`, for the pre-flight in
    ``manage.py inventory_link_types``: run against a database that has not
    been migrated yet, it says which rows ``verify_migrated_links`` would
    refuse — before the deploy is attempted, rather than from inside a
    rolled-back ``migrate`` container (issue #893, proposal 1).

    Args:
        link_type: The row's current (possibly legacy) key.
        source_type: Source artifact type, sub-type tag included or not.
        target_type: Target artifact type, same.

    Returns:
        ``(link_type, source_type, target_type)`` after the rename, the
        endpoint exceptions and the endpoint swap, or ``None`` for a row that
        does not survive as a link at all (``copy-of``, which moves into
        ``Artifact.copied_from``; its losers are reported by
        ``manage.py check_copy_of_conflicts`` instead).
    """
    source, target = _base_type(source_type), _base_type(target_type)

    for key, endpoint, artifact_type, successor in _ENDPOINT_EXCEPTIONS:
        if link_type == key and (source if endpoint == "source" else target) == (
            artifact_type
        ):
            return successor, source, target

    # Restructured, not renamed: parent-child survives as a decomposes edge
    # (LEGACY_LINK_TYPE_MAPPING says None because it has no *rename*).
    if link_type == "parent-child":
        return "decomposes", source, target
    if link_type in LEGACY_LINK_TYPE_MAPPING:
        successor = LEGACY_LINK_TYPE_MAPPING[link_type]
        if successor is None:
            return None
        if link_type in SWAPPED_LEGACY_KEYS:
            return successor, target, source
        return successor, source, target
    return link_type, source, target


def find_copy_of_conflicts(TraceLink: Any) -> Dict[UUID, List[UUID]]:
    """Return ``{source_artifact_id: [link_id, ...]}`` for sources with >1 copy-of.

    ``Artifact.copied_from`` is a 1:1 field, so a source with two ``copy-of``
    links is a data conflict that has to be resolved before the migration can
    faithfully represent it (spec section 7). Run
    ``manage.py check_copy_of_conflicts`` to see them ahead of time.
    """
    by_source: Dict[UUID, List[UUID]] = {}
    for link in TraceLink.objects.filter(link_type="copy-of").order_by(
        "created_at", "id"
    ):
        by_source.setdefault(link.source_id, []).append(link.id)
    return {source: ids for source, ids in by_source.items() if len(ids) > 1}


def migrate_copy_of_links(Artifact: Any, TraceLink: Any) -> Tuple[int, int]:
    """Move ``copy-of`` links into ``Artifact.copied_from``.

    The newest link per source wins (``created_at``, then ``id`` as a stable
    tiebreak). Every other link of the same source is **kept** as a
    ``references`` link instead of being deleted, so a multi-copy conflict
    loses its 1:1 precision but never its provenance.

    Returns:
        ``(moved_to_field, downgraded_to_references)``.
    """
    moved = 0
    downgraded = 0

    by_source: Dict[UUID, List[Any]] = {}
    # Materialised before the first delete: the loop below mutates the very
    # rows this queryset selects.
    for link in list(
        TraceLink.objects.filter(link_type="copy-of").order_by("created_at", "id")
    ):
        by_source.setdefault(link.source_id, []).append(link)

    for source_id, links in by_source.items():
        winner = links[-1]  # newest
        Artifact.objects.filter(id=source_id).update(copied_from_id=winner.target_id)
        winner.delete()
        moved += 1

        for loser in links[:-1]:
            # Do not create a duplicate if a references edge already exists.
            if TraceLink.objects.filter(
                source_id=loser.source_id,
                target_id=loser.target_id,
                link_type="references",
            ).exists():
                loser.delete()
            else:
                loser.link_type = "references"
                loser.save(update_fields=["link_type"])
            downgraded += 1

    if moved or downgraded:
        logger.info(
            "copy-of migration: %d moved to Artifact.copied_from, "
            "%d downgraded to references.",
            moved,
            downgraded,
        )
    return moved, downgraded


def migrate_parent_child_links(TraceLink: Any) -> Tuple[int, int]:
    """Convert ``parent-child`` into ``decomposes``, deduplicating twins.

    Both types run parent -> child, so a pair that already carries a
    ``decomposes`` edge would violate ``uq_tracelink_edge`` on conversion. Such
    a parent-child row is redundant and is dropped rather than duplicated
    (spec section 6, step 2).

    Returns:
        ``(converted, deduplicated)``.
    """
    converted = 0
    deduplicated = 0

    for link in list(TraceLink.objects.filter(link_type="parent-child")):
        twin_exists = (
            TraceLink.objects.filter(
                source_id=link.source_id,
                target_id=link.target_id,
                link_type="decomposes",
            )
            .exclude(id=link.id)
            .exists()
        )
        if twin_exists:
            link.delete()
            deduplicated += 1
        else:
            link.link_type = "decomposes"
            link.save(update_fields=["link_type"])
            converted += 1

    if converted or deduplicated:
        logger.info(
            "parent-child migration: %d converted to decomposes, %d deduplicated.",
            converted,
            deduplicated,
        )
    return converted, deduplicated


def _rewrite(
    TraceLink: Any, link: Any, source_id: UUID, target_id: UUID, successor: str
) -> bool:
    """Retype one row to *successor*, dropping it if that duplicates an edge.

    ``uq_tracelink_edge`` (issue #126) forbids a second
    ``(source, target, link_type)`` triple, and two legacy types can collapse
    onto one successor (``documents`` + ``traces`` -> ``references``). The
    later row is redundant, not information, so it is deleted.

    Returns:
        True if the row was rewritten, False if it was dropped as a duplicate.
        The caller has to keep the two apart: an irreversible migration whose
        log counts a deleted row as a rewritten one leaves no way to find out
        afterwards.
    """
    collides = (
        TraceLink.objects.filter(
            source_id=source_id, target_id=target_id, link_type=successor
        )
        .exclude(id=link.id)
        .exists()
    )
    if collides:
        link.delete()
        return False
    link.source_id = source_id
    link.target_id = target_id
    link.link_type = successor
    link.save(update_fields=["source", "target", "link_type"])
    return True


def _migrate_endpoint_exceptions(TraceLink: Any) -> Dict[str, Tuple[int, int]]:
    """Retype the rows of ``_ENDPOINT_EXCEPTIONS``, endpoints left alone.

    Two legacy keys mean something other than what their name says, and only
    one of their endpoints reveals it — so the mechanical rename below cannot
    get them right.

    ``satisfies`` with a StakeholderNeed target. The legacy endpoint matrix
    (``traceability.types.SE_LINK_SEMANTICS``, now retired) gave ``satisfies``
    **two** pairs::

        satisfies: {(ArchitectureElement, Requirement), (Requirement, StakeholderNeed)}

    Only the first is an allocation. Blanket-applying ``SWAPPED_LEGACY_KEYS``
    to the second would produce ``allocated-to StakeholderNeed -> Requirement``
    — not a built-in pair (``allocated-to`` allows only
    ``Requirement -> ArchitectureElement``), inverted in direction, and wrong
    in kind: allocation coverage counts ArchitectureElement targets, while a
    Requirement pointing at the need it came from is a derivation. It becomes
    ``derives-from``, a built-in pair for those endpoints.

    ``verifies`` with a Risk source (issue #893). ``verifies`` is not a legacy
    key at all, so the rename loop never looks at it — a Risk-sourced row
    survives untouched into a catalog whose ``verifies`` starts at a TestCase,
    and ``verify_migrated_links`` then refuses the whole migration. ``Risk ->
    Requirement`` and ``Risk -> ArchitectureElement`` are built-in
    ``mitigates`` pairs, which is the relation those rows were reaching for.

    Neither is hypothetical: ``link_types.grandfathered`` records 40 rows of
    the first from a real inventory run (``seed_toothbrush`` still writes
    them), and the second is the QA finding of issue #893.

    Returns:
        ``{"<link_type>:<artifact_type>": (rewritten, dropped_as_duplicate)}``,
        one entry per exception that matched a row. Keyed by the endpoint type
        rather than the link type alone so the migration log keeps the two
        populations of a split key apart.
    """
    counts: Dict[str, Tuple[int, int]] = {}

    for key, endpoint, artifact_type, successor in _ENDPOINT_EXCEPTIONS:
        rewritten = 0
        dropped = 0
        for link in list(
            TraceLink.objects.filter(link_type=key)
            .select_related(endpoint)
            .order_by("created_at", "id")
        ):
            if _base_artifact_type(getattr(link, endpoint)) != artifact_type:
                continue
            if _rewrite(TraceLink, link, link.source_id, link.target_id, successor):
                rewritten += 1
            else:
                dropped += 1

        if rewritten or dropped:
            counts[f"{key}:{artifact_type}"] = (rewritten, dropped)
            logger.info(
                "link-type migration: %d '%s' row(s) whose %s is a %s -> '%s' "
                "(endpoints kept), %d dropped as a duplicate edge.",
                rewritten,
                key,
                endpoint,
                artifact_type,
                successor,
                dropped,
            )

    return counts


def migrate_renamed_links(TraceLink: Any) -> Dict[str, int]:
    """Rename the remaining legacy types, swapping endpoints where required.

    ``satisfies`` and ``implements`` both ran ArchitectureElement ->
    Requirement; ``allocated-to`` runs Requirement -> ArchitectureElement, so
    those rows have their endpoints exchanged as part of the rename
    (spec section 3.1). This silently reverses the meaning of the stored row
    for any consumer that reads ``source``/``target`` directly — see Task 17.

    The endpoint exceptions run first: rows whose *endpoint type* contradicts
    their key are retyped without a swap. See
    :func:`_migrate_endpoint_exceptions` for the two of them and why.

    A rename that would collide with an existing edge (``documents`` and
    ``traces`` between the same pair both becoming ``references``) drops the
    later row instead of violating ``uq_tracelink_edge``.

    Returns:
        ``{legacy_key: rows_rewritten}``, omitting keys with no rows. Rows
        *deleted* as duplicates are reported separately under
        ``"<legacy_key>:dropped"`` — see :func:`_rewrite`. Each endpoint
        exception reports under its own ``"<key>:<artifact_type>"`` key so the
        split populations stay visible in the migration log.
    """
    counts: Dict[str, int] = {}

    for key, (rewritten, dropped) in _migrate_endpoint_exceptions(TraceLink).items():
        if rewritten:
            counts[key] = rewritten
        if dropped:
            counts[key + _DROPPED_SUFFIX] = dropped

    for legacy, successor in _RENAMED.items():
        rewritten = 0
        dropped = 0
        for link in list(
            TraceLink.objects.filter(link_type=legacy).order_by("created_at", "id")
        ):
            source_id, target_id = link.source_id, link.target_id
            if legacy in SWAPPED_LEGACY_KEYS:
                source_id, target_id = target_id, source_id

            if _rewrite(TraceLink, link, source_id, target_id, successor):
                rewritten += 1
            else:
                dropped += 1

        if rewritten:
            counts[legacy] = rewritten
            logger.info(
                "link-type migration: %d '%s' row(s) -> '%s'%s.",
                rewritten,
                legacy,
                successor,
                " (endpoints swapped)" if legacy in SWAPPED_LEGACY_KEYS else "",
            )
        if dropped:
            counts[legacy + _DROPPED_SUFFIX] = dropped
            logger.info(
                "link-type migration: %d '%s' row(s) dropped — a '%s' edge "
                "already joined the same pair.",
                dropped,
                legacy,
                successor,
            )

    return counts


def verify_migrated_links(TraceLink: Any) -> int:
    """Post-condition: refuse to finish if a surviving row is not creatable.

    The rename and the endpoint swap are mechanical — they look at the legacy
    key, not at what the resulting endpoint pair means. A ``satisfies`` row
    that ran Requirement -> Requirement (neither of the two pairs the legacy
    matrix documented) comes out of :func:`migrate_renamed_links` as
    ``allocated-to Requirement -> Requirement``: no built-in pair, no
    grandfathered pair, and therefore a row the always-on validation of Task 11
    would reject for the rest of its life. ``link_types.grandfathered`` says so
    itself — its inventory is only as complete as the two databases it was
    taken from.

    So the same guarantee-by-``RuntimeError`` pattern ``persistence/0078`` uses
    applies here: raised from inside ``RunPython`` in an ``atomic`` migration,
    the whole rewrite rolls back and the operator gets the triples to act on,
    rather than a database full of rows nobody can recreate.

    Checked against the built-in catalog plus ``GRANDFATHERED_PAIRS``, i.e. the
    definitions ``link_types/0003`` and ``0004`` seed into every workspace. A
    workspace that has *customized* its catalog may legitimately allow more
    than this (``is_customized=True`` rows are never touched by ``0004``); such
    an installation has to extend ``GRANDFATHERED_PAIRS`` — the check fails
    closed on purpose, because the alternative on an irreversible migration is
    silent data corruption.

    Args:
        TraceLink: The (historical or live) TraceLink model.

    Returns:
        Number of rows checked.

    Raises:
        RuntimeError: if any surviving row's
            ``(link_type, source_type, target_type)`` triple is not creatable.
    """
    offenders: Dict[Tuple[str, str, str], Tuple[int, Any]] = {}
    checked = 0

    for link_id, link_type, source_type, target_type in TraceLink.objects.values_list(
        "id", "link_type", "source__artifact_type", "target__artifact_type"
    ).iterator():
        checked += 1
        triple = (link_type, _base_type(source_type), _base_type(target_type))
        if is_creatable(*triple):
            continue
        seen, first_id = offenders.get(triple, (0, link_id))
        offenders[triple] = (seen + 1, first_id)

    if offenders:
        detail = "; ".join(
            f"'{link_type}' {source or '(unknown)'} -> {target or '(unknown)'} "
            f"({rows} row(s), e.g. TraceLink {first_id})"
            for (link_type, source, target), (rows, first_id) in sorted(
                offenders.items()
            )
        )
        raise RuntimeError(
            f"{len(offenders)} migrated link triple(s) are not creatable under "
            f"the new link-type catalog: {detail}. Refusing to finish — these "
            "rows would exist but could never be recreated or edited. Run "
            "`manage.py inventory_link_types --json <path>` against this "
            "database and either fix the offending rows or extend "
            "link_types.grandfathered.GRANDFATHERED_PAIRS with the reported "
            "`blocking` list — plus a backfill migration in the shape of "
            "link_types/0007, without which already-seeded catalogs keep "
            "rejecting them — then retry."
        )

    logger.info("link-type migration: %d surviving row(s) verified.", checked)
    return checked


__all__ = [
    "find_copy_of_conflicts",
    "is_creatable",
    "migrate_copy_of_links",
    "migrate_parent_child_links",
    "migrate_renamed_links",
    "predict_migrated_triple",
    "verify_migrated_links",
]
