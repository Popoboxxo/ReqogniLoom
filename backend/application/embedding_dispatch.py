"""Dispatch embedding work to the queue after the surrounding write commits.

Issue #1401: the write paths used to call the embedding provider inline, so a
cold provider added up to its full timeout to a plain 201/200 — for a value
that is only a *derived search index*, never part of the row's contract.
``RequirementService.create_requirement``/``update_requirement`` capped that
with a 3 s wall-clock budget (a slow provider left the row un-embedded), and
``TraceLinkService.create_trace_link`` had no cap at all.

The ReqIF importer had already solved the same problem (Plan G G1.2,
``transaction.on_commit`` + ``application.tasks.embed_rows_task``). This module
is that pattern, extracted so every writer shares one implementation and one
broker-outage fallback instead of re-deriving it.

Contract:

* **The write is already durable** when the callback runs — a broker outage
  must never turn a 201 into a 500. It degrades to a WARNING that names the
  repair command.
* **Eventually consistent**: a freshly written row has no vector for a short
  window (until the worker runs). Read paths that need one either embed lazily
  (``RequirementService.find_similar_requirements``, #847) or report the row as
  not-yet-embedded; ``manage.py backfill_embeddings --model <model>`` is the
  documented repair path for a permanently missed dispatch.
* **Tenant isolation (ADR-03)**: only ``tenant_id``, the model key and the row
  ids cross the queue boundary. The worker re-arms both isolation layers before
  its first query — see ``application.tasks.embed_rows_task``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)

#: Operator-facing repair path, also printed by every caller's warning below.
EMBEDDING_REPAIR_COMMAND = "manage.py backfill_embeddings --model {model_name}"


def enqueue_rows_after_commit(
    model_name: str,
    ids: Iterable[Any],
    tenant_id: Any,
    *,
    source: str,
) -> None:
    """Register a post-commit ``embed_rows_task`` dispatch for *ids*.

    Returns immediately; nothing is generated here. The provider call happens in
    a Celery worker after the caller's transaction committed, so the id list is
    materialised now — the callback must not depend on a caller collection that
    may have changed (or been mutated by a later step) by the time it runs.

    Args:
        model_name: An ``EMBEDDABLE_MODELS`` key (``"requirement"``,
            ``"tracelink"``, ``"icd"``), not a Django model label — the worker
            resolves it through ``application.embedding_backfill``.
        ids: Primary keys of the rows to embed. An empty iterable is a no-op:
            dispatching a 0-row batch would only wake a worker.
        tenant_id: Tenant to re-arm in the worker. It must be the *row's*
            tenant, not the request's, or RLS returns an empty table.
        source: Caller name for the warning. The log line has to say which write
            path lost its dispatch, otherwise the only trace of a broker outage
            is a gap in the vectors.

    Example:
        >>> from application.embedding_dispatch import enqueue_rows_after_commit
        >>> enqueue_rows_after_commit(  # doctest: +SKIP
        ...     "requirement", [requirement.id], requirement.tenant_id,
        ...     source="RequirementService",
        ... )
    """
    row_ids = tuple(str(row_id) for row_id in ids)
    if not row_ids:
        return
    tenant = str(tenant_id)

    def _enqueue() -> None:
        # Imported inside the callback: ``application.tasks`` pulls in Celery,
        # which a request path should only pay for when it actually dispatches.
        from application.tasks import embed_rows_task

        try:
            embed_rows_task.delay(model_name, list(row_ids), tenant)
        except Exception:  # noqa: BLE001 — the write is already durable
            logger.warning(
                "%s: could not enqueue embedding for %d %s row(s); run %s to "
                "catch up.",
                source,
                len(row_ids),
                model_name,
                EMBEDDING_REPAIR_COMMAND.format(model_name=model_name),
                exc_info=True,
            )

    transaction.on_commit(_enqueue)
