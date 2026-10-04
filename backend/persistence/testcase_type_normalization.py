"""Guarded, idempotent normalisation of the deprecated ``TestCase:<Type>`` tag.

DATA-08 (audit-review 2026-09, findings 181/189) — extracted from migration
0093 so the original migration and the residual-correction migration 0105 share
one implementation, and so the behaviour can be unit-tested against real rows
without replaying migration state (same pattern as
``link_types.migration_ops``).

Background
----------
``TestCase.test_type`` (first-class column, migration 0041) is the single
source of truth for a test case's type. Older write paths *also* tagged the
backing ``Artifact`` with a redundant ``"TestCase:<Type>"`` sub-type prefix.
Migration 0093 removed that representation for the rows that existed when it
ran, but rows imported/restored afterwards can still carry the tag — the live
database had 99 such rows (69 ``TestCase:Unit`` + 30 ``TestCase:System``).

What "guarded" means here
-------------------------
The rewrite only touches artifacts that are actually backed by a ``TestCase``
row. The original unconditional ``artifact_type__istartswith("TestCase:")``
update would also rewrite an unrelated artifact that merely happened to carry a
``TestCase:`` prefix. An artifact whose type is tagged ``TestCase:*`` but has
no backing ``TestCase`` is left untouched and logged, so it stays visible for
an operator instead of being silently relabelled (acceptance: "0 remaining
tagged artefacts *or documented residual*").

Idempotency
-----------
Both steps are filters over the current state: the column backfill fills only
NULLs, and the rewrite selects only rows still carrying the prefix. Re-running
is therefore a no-op. The functions take the (historical or live) ``Artifact``
and ``TestCase`` models as arguments.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)

#: Legacy artifact_type prefix and its canonical replacement.
PREFIX = "TestCase:"
BASE_TYPE = "TestCase"

#: Legacy lowercase suffix -> canonical ``TestCaseType`` value used by
#: ``TestCase.test_type``.
SUFFIX_TO_TEST_TYPE: Dict[str, str] = {
    "system": "system",
    "integration": "integration",
    "unit": "unit",
    "inspection": "inspection",
    "analysis": "analysis",
    "demonstration": "demonstration",
}

#: Canonical ``TestCaseType`` value -> legacy Title-case suffix (reverse).
TEST_TYPE_TO_SUFFIX: Dict[str, str] = {
    test_type: suffix.capitalize() for suffix, test_type in SUFFIX_TO_TEST_TYPE.items()
}


def _as_list(values: Iterable[Any]) -> List[Any]:
    return list(values)


def suspend_row_level_security() -> None:
    """Turn an RLS-blinded migration connection into a hard error, not a no-op.

    ``pl_artifact`` (and the other ``pl_*`` tables) have ``FORCE ROW LEVEL
    SECURITY``. A data migration run as the least-privilege app role without an
    ``app.current_tenant`` GUC sees **zero** rows and would report "nothing to
    do" — silently leaving the residual tags in place. That was observed on the
    dev stack when ``manage.py migrate`` ran in the ``backend`` runtime
    container (app role) instead of the documented ``migrate`` service (owner).

    ``row_security = off`` makes Postgres raise instead of filtering, so the
    migration either sees the whole database or fails visibly. Same idiom as
    ``persistence/management/commands/check_artifact_backing.py``. Must be
    called inside an atomic block (a migration's ``RunPython`` already is).
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def normalize_testcase_artifact_types(
    Artifact: Any, TestCase: Any
) -> Dict[str, int]:
    """Backfill ``test_type`` from the suffix, then drop the redundant tag.

    Args:
        Artifact: The (historical or live) ``Artifact`` model.
        TestCase: The (historical or live) ``TestCase`` model.

    Returns:
        Counts keyed by ``tagged`` (rows seen), ``column_backfilled``,
        ``rewritten`` and ``unbacked`` (tagged artifacts with no ``TestCase``
        row, left untouched and logged).
    """
    counts: Dict[str, int] = {
        "tagged": 0,
        "column_backfilled": 0,
        "rewritten": 0,
        "unbacked": 0,
    }

    tagged_ids = _as_list(
        Artifact.objects.filter(artifact_type__istartswith=PREFIX).values_list(
            "id", flat=True
        )
    )
    counts["tagged"] = len(tagged_ids)
    if not tagged_ids:
        logger.info("DATA-08: no residual 'TestCase:*' artifacts; nothing to do.")
        return counts

    # 1) Fold the suffix into the canonical column, but never overwrite a value
    #    that a newer write path already set.
    for suffix, test_type in SUFFIX_TO_TEST_TYPE.items():
        suffix_ids = _as_list(
            Artifact.objects.filter(
                id__in=tagged_ids, artifact_type__iexact=f"{PREFIX}{suffix}"
            ).values_list("id", flat=True)
        )
        if not suffix_ids:
            continue
        counts["column_backfilled"] += TestCase.objects.filter(
            artifact_id__in=suffix_ids, test_type__isnull=True
        ).update(test_type=test_type)

    # 2) Guarded rewrite: only artifacts backed by a TestCase row are relabelled.
    backed_ids = _as_list(
        TestCase.objects.filter(artifact_id__in=tagged_ids)
        .values_list("artifact_id", flat=True)
        .distinct()
    )
    backed = set(backed_ids)
    unbacked = [artifact_id for artifact_id in tagged_ids if artifact_id not in backed]
    counts["unbacked"] = len(unbacked)
    if unbacked:
        logger.warning(
            "DATA-08: %d artifact(s) tagged 'TestCase:*' have no backing "
            "TestCase row and are left untouched (documented residual): %s",
            len(unbacked),
            unbacked[:20],
        )

    if backed:
        counts["rewritten"] = Artifact.objects.filter(
            id__in=backed, artifact_type__istartswith=PREFIX
        ).update(artifact_type=BASE_TYPE)

    logger.info("DATA-08 testcase tag normalisation: %s", counts)
    return counts


def restore_testcase_artifact_type_tags(Artifact: Any, TestCase: Any) -> int:
    """Reverse: re-derive the legacy sub-type tag from the canonical column.

    Mirrors the 0093 reverse semantics. Rows whose ``test_type`` is NULL stay
    untagged — a faithful inverse of the forward column backfill. The column
    itself is never modified, so no information is lost either way.
    """
    restored = 0
    for test_type, suffix in TEST_TYPE_TO_SUFFIX.items():
        artifact_ids = _as_list(
            TestCase.objects.filter(test_type=test_type).values_list(
                "artifact_id", flat=True
            )
        )
        if artifact_ids:
            restored += Artifact.objects.filter(id__in=artifact_ids).update(
                artifact_type=f"{PREFIX}{suffix}"
            )
    return restored


__all__ = [
    "BASE_TYPE",
    "PREFIX",
    "SUFFIX_TO_TEST_TYPE",
    "TEST_TYPE_TO_SUFFIX",
    "normalize_testcase_artifact_types",
    "restore_testcase_artifact_type_tags",
    "suspend_row_level_security",
]
