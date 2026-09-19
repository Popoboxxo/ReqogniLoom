"""pgvector approximate-nearest-neighbour scan hardening (issue #977).

The semantic search paths (``search_service._run_semantic_query`` and
``requirement_service.find_similar_requirements``) issue a *filtered* cosine
nearest-neighbour query::

    WHERE artifact__workspace_id = :workspace
    ORDER BY embedding <=> :query
    LIMIT N

With an HNSW index and pgvector's defaults (``hnsw.ef_search = 40``,
``hnsw.iterative_scan = off``), PostgreSQL asks the index for ~40 candidates
*first* and applies the workspace filter *afterwards*. On a table that holds
rows from many workspaces — production, or a shared ``--reuse-db`` schema —
that post-filtering can discard every candidate and return fewer rows than the
``LIMIT`` asked for, or none at all, even though matching rows exist. The same
default also caps any result set at ``ef_search``, so a ``LIMIT 50`` can never
yield 50 rows.

That is the nondeterminism behind issue #977: the two pgvector tests flake
alternately, never reproducibly, and a plain re-run goes green.

pgvector 0.8 added ``hnsw.iterative_scan``: the index keeps producing
candidates until the filtered ``LIMIT`` is satisfied, bounded by
``hnsw.max_scan_tuples``. ``strict_order`` preserves exact distance ordering.

The setting is transaction-local (``SET LOCAL``), so it is applied inside the
caller's ``transaction.atomic()`` and cannot leak into unrelated queries. On
pgvector < 0.8 the GUC does not exist and the helper is a silent no-op, which
keeps the previous behaviour instead of turning an optional optimisation into a
hard version requirement.
"""
from __future__ import annotations

import logging

from django.db import connection

logger = logging.getLogger(__name__)

#: Preserve exact distance ordering while the index keeps scanning. The
#: alternative, ``relaxed_order``, is faster but may return rows slightly out
#: of distance order, which these nearest-neighbour callers cannot tolerate.
_ITERATIVE_SCAN_MODE = "strict_order"


def enable_iterative_ann_scan() -> None:
    """Ask HNSW for enough filtered candidates to satisfy the ``LIMIT``.

    Must be called inside an open transaction (``SET LOCAL`` is
    transaction-scoped). No-op when the running pgvector does not expose
    ``hnsw.iterative_scan`` (< 0.8) or when anything about the setting fails:
    this is an accuracy hardening, never allowed to break a search.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('hnsw.iterative_scan', true)")
            row = cursor.fetchone()
            if row is None or row[0] is None:
                return
            # Constant interpolation (not a bound parameter): the value is a
            # fixed literal from this module, never caller input.
            cursor.execute(f"SET LOCAL hnsw.iterative_scan = {_ITERATIVE_SCAN_MODE}")
    except Exception:  # noqa: BLE001 - optional optimisation, never break a search
        logger.debug("Could not enable hnsw.iterative_scan", exc_info=True)


__all__ = ["enable_iterative_ann_scan"]
