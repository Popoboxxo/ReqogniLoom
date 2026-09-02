"""Startup system checks for the embedding configuration (issue #794).

Registered from :meth:`llm_adapter.apps.LlmAdapterConfig.ready`, so
``manage.py check``/``runserver``/``migrate`` all surface the result.

Why a system check rather than a log line: the failure mode this guards
against is *silent by construction*. Embedding generation is best-effort
everywhere (``embedding_service``'s module docstring), so a vector whose width
does not match the ``vector(N)`` column it is destined for is skipped, not
raised — on the write side (``RequirementService._generate_and_store_embedding``
et al.) and on the read side (``search_service._run_semantic_query``). Before
#794 that was the *shipped default* configuration, and it produced exactly one
observable symptom: ``artifact.search`` returned nothing, forever, with no
error anywhere. #794 fixes the default by resizing the columns; this check
covers the remaining, still-reachable variants of the same trap — an operator
switching ``EMBEDDING_PROVIDER`` to ``ollama`` (768-dim) or ``openai``
(1536-dim) without also resizing the columns.
"""
from __future__ import annotations

import logging
from typing import Any, List

from django.core.checks import Warning as DjangoWarning

logger = logging.getLogger(__name__)

#: ``manage.py check`` id for "provider width != column width".
EMBEDDING_DIMENSION_MISMATCH = "llm_adapter.W001"

#: ``manage.py check`` id for "EMBEDDING_PROVIDER names a provider that does
#: not exist" — a plain typo silently disables embeddings entirely, because
#: ``generate_embedding`` swallows the resulting ``ValueError`` and returns
#: ``None``.
EMBEDDING_PROVIDER_UNKNOWN = "llm_adapter.W002"


def _embedding_columns() -> List[tuple[str, int]]:
    """Return ``(label, declared_dimensions)`` for every ``VectorField`` in the
    project, discovered through Django's app registry.

    Discovery rather than a hardcoded model list for two reasons. Layering
    (ADR-01): ``llm_adapter`` is Layer 1 and must not import ``icd``/``memory``
    (Ext/Layer 2) — the same backwards dependency
    ``register_settings_override_provider`` exists to avoid. And coverage: a
    model added later with an embedding column is checked automatically, which
    is the whole failure mode of #794 (five independently declared widths that
    nothing compared against each other).
    """
    from django.apps import apps
    from pgvector.django import VectorField

    return [
        (f"{model.__name__}.{field.name}", field.dimensions)
        for model in apps.get_models()
        for field in model._meta.get_fields()
        if isinstance(field, VectorField)
    ]


def check_embedding_dimensions(app_configs: Any = None, **kwargs: Any) -> List[DjangoWarning]:
    """Warn when the configured embedding provider cannot fill the columns.

    Never raises and never touches the database beyond what
    ``get_embedding_provider`` already does best-effort (a
    ``SystemMemorySettings`` override lookup that swallows its own failures):
    a system check that crashes would take ``migrate`` down with it.
    """
    try:
        from llm_adapter.embedding_service import (
            EMBEDDING_PROVIDER_REGISTRY,
            _read_config,
            get_embedding_provider,
        )

        cfg = _read_config()
        if cfg.provider_name not in EMBEDDING_PROVIDER_REGISTRY:
            return [
                DjangoWarning(
                    f"EMBEDDING_PROVIDER={cfg.provider_name!r} is not a known "
                    f"embedding provider.",
                    hint=(
                        "No embeddings will be generated at all and semantic "
                        "search will stay empty; generate_embedding() swallows "
                        "the lookup error by design. Valid values: "
                        + ", ".join(sorted(EMBEDDING_PROVIDER_REGISTRY))
                        + "."
                    ),
                    id=EMBEDDING_PROVIDER_UNKNOWN,
                )
            ]

        provider_dimensions = get_embedding_provider(cfg).dimensions
        mismatched = [
            (label, dimensions)
            for label, dimensions in _embedding_columns()
            if dimensions != provider_dimensions
        ]
        if not mismatched:
            return []

        detail = ", ".join(f"{label} is vector({dimensions})" for label, dimensions in mismatched)
        return [
            DjangoWarning(
                f"EMBEDDING_PROVIDER={cfg.provider_name!r} produces "
                f"{provider_dimensions}-dim vectors, but {detail}.",
                hint=(
                    "Every embedding write and every semantic search pass for "
                    "those columns is silently skipped, so search results will "
                    "be missing them entirely (issue #794). Either switch back "
                    "to a provider with matching output width, or change "
                    "persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS, "
                    "generate the resulting migrations and re-run "
                    "`manage.py backfill_embeddings`."
                ),
                id=EMBEDDING_DIMENSION_MISMATCH,
            )
        ]
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        logger.debug("Embedding dimension system check skipped: %s", exc)
        return []


__all__ = [
    "EMBEDDING_DIMENSION_MISMATCH",
    "EMBEDDING_PROVIDER_UNKNOWN",
    "check_embedding_dimensions",
]
