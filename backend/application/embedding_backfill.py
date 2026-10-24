"""Row-level embedding generation shared by the backfill command and tasks.

Extracted from ``management/commands/backfill_embeddings.py`` (Plan G G1.2) so
the ReqIF importer — and any future writer — can embed a known set of rows
without shelling out to a management command. The command keeps its tenant
iteration, ``--dry-run``/``--force``/``--limit`` semantics and per-model
reporting; this module owns exactly one thing: turn ids into vectors.

Kept free of any tenant arming on purpose. The caller decides the scope:

* the command arms ``app.current_tenant`` per tenant and passes the shared
  ``totals`` dict so its report stays byte-identical;
* ``application.tasks.embed_rows_task`` re-arms the tenant in the worker before
  calling here (a Celery worker has no request-scoped context).
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

#: Model keys accepted by :func:`embed_rows` (mirrors the command's choices).
EMBEDDABLE_MODELS: tuple[str, ...] = ("requirement", "tracelink", "icd")


def resolve_embedding_model(name: str):
    """Return the Django model for an ``EMBEDDABLE_MODELS`` key."""
    from icd.models import Icd
    from persistence.models import Requirement, TraceLink

    return {
        "requirement": Requirement,
        "tracelink": TraceLink,
        "icd": Icd,
    }[name]


def _rows_and_builder(model, name: str, ids: list[UUID]):
    """Load the rows for *ids* and return ``(rows, text_builder)``.

    The eager-loading shape mirrors the command's pre-extraction
    ``_embed_batch`` exactly: TraceLink needs its endpoints for the text, and
    every variant defers the (large) vector column because it is only written.
    """
    from llm_adapter.embedding_service import (
        get_embedding_text,
        get_icd_embedding_text,
        get_tracelink_embedding_text,
    )

    if name == "icd":
        rows = model.objects.filter(id__in=ids).defer("embedding")
        return rows, get_icd_embedding_text
    if name == "tracelink":
        rows = (
            model.objects.filter(id__in=ids)
            .select_related(
                "source__requirement",
                "source__architecture_element",
                "target__requirement",
                "target__architecture_element",
            )
            .defer(
                "embedding",
                "source__requirement__embedding",
                "target__requirement__embedding",
            )
        )
        return rows, get_tracelink_embedding_text
    rows = model.objects.filter(id__in=ids).defer("embedding")
    return rows, get_embedding_text


def embed_rows(
    model_name: str,
    ids: list[UUID],
    *,
    totals: dict[str, int] | None = None,
) -> int:
    """Generate and store embeddings for *ids*; return the number written.

    A single bad row never aborts the batch: a provider exception or a ``None``
    vector is counted as ``failed`` and the next row is tried. That matches the
    command's long-standing behaviour (one broken row must not strand the rest
    of a backfill).

    Args:
        model_name: One of :data:`EMBEDDABLE_MODELS`.
        ids: Primary keys of the rows to (re-)embed. Empty input is a no-op.
        totals: Optional caller-owned counters. When given, ``embedded``,
            ``skipped_empty`` and ``failed`` are incremented in place so the
            management command's report does not change; the return value is
            still the count for *this* call.
    """
    if not ids:
        return 0

    from llm_adapter.embedding_service import generate_embedding

    model = resolve_embedding_model(model_name)
    rows, build_text = _rows_and_builder(model, model_name, ids)

    embedded = 0
    for row in rows:
        text = build_text(row)
        if not text or not text.strip():
            if totals is not None:
                totals["skipped_empty"] = totals.get("skipped_empty", 0) + 1
            continue
        try:
            vector = generate_embedding(text)
        except Exception as exc:  # noqa: BLE001 — one bad row must not abort the run
            logger.warning("embed_rows: %s %s failed: %s", model_name, row.id, exc)
            if totals is not None:
                totals["failed"] = totals.get("failed", 0) + 1
            continue
        if vector is None:
            if totals is not None:
                totals["failed"] = totals.get("failed", 0) + 1
            continue
        # Bare .update(): mirrors the service write path — no version bump, no
        # domain event, no updated_at churn for a derived value.
        model.objects.filter(id=row.id).update(embedding=vector)
        embedded += 1
        if totals is not None:
            totals["embedded"] = totals.get("embedded", 0) + 1

    return embedded


__all__: list[str] = ["EMBEDDABLE_MODELS", "embed_rows", "resolve_embedding_model"]
