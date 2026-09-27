"""Startup system checks for the LLM/embedding configuration (#794, #1050).

Registered from :meth:`llm_adapter.apps.LlmAdapterConfig.ready`, so
``manage.py check``/``runserver``/``migrate`` all surface the result.

Why a system check rather than a log line: both failure modes guarded here are
*silent by construction*.

**Embedding dimensions (#794).** Embedding generation is best-effort everywhere
(``embedding_service``'s module docstring), so a vector whose width does not
match the ``vector(N)`` column it is destined for is skipped, not raised — on
the write side (``RequirementService._generate_and_store_embedding`` et al.)
and on the read side (``search_service._run_semantic_query``). Before #794 that
was the *shipped default* configuration, and it produced exactly one observable
symptom: ``artifact.search`` returned nothing, forever, with no error anywhere.
#794 fixes the default by resizing the columns; this check covers the
remaining, still-reachable variants of the same trap — an operator switching
``EMBEDDING_PROVIDER`` to ``ollama`` (768-dim) or ``openai`` (1536-dim) without
also resizing the columns.

**OpenCode Go session (#1050).** ``LLM_OPENCODE_SESSION`` is *required* by the
Zen-Go endpoint (a request without the ``x-opencode-session`` header gets
``400 MissingSessionID``), but the provider's docstring called it optional and
the provider deliberately omits the header when it is unset. The 4xx is
permanent as far as the resilience wrapper is concerned, so nothing retries and
nothing surfaces: the deployment looks healthy and every LLM call fails.
:func:`check_opencode_session_required` is the in-process half of the
compose-level preflight gate that already exists for the image deployment.
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

#: ``manage.py check`` id for "``opencode_go`` is selected but the session id
#: it requires is missing" (issue #1050).
OPENCODE_SESSION_MISSING = "llm_adapter.W003"

#: The one provider that has a non-credential REQUIRED variable. Kept as a
#: module constant so the check, the provider docstring and the test cannot
#: drift apart on the spelling.
OPENCODE_PROVIDER_NAME = "opencode_go"


def _embedding_columns() -> List[tuple[str, int]]:
    """Return ``(label, declared_dimensions)`` for every ``VectorField`` in the
    project, discovered through the shared ``persistence.embedding_schema``
    helper.

    Discovery rather than a hardcoded model list for two reasons. Layering
    (ADR-01): ``llm_adapter`` is Layer 1 and must not import ``icd``/``memory``
    (Ext/Layer 2) — the same backwards dependency
    ``register_settings_override_provider`` exists to avoid; importing
    ``persistence`` (Layer 0) is allowed. And coverage: a model added later with
    an embedding column is checked automatically, which is the whole failure
    mode of #794 (independently declared widths that nothing compared against
    each other). Reusing the single implementation keeps this check, the
    ``verify_embedding_dimensions`` command and the ``/health/`` endpoint from
    drifting apart.
    """
    from persistence.embedding_schema import embedding_columns

    return [(column.label, column.field.dimensions) for column in embedding_columns()]


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
                f"{provider_dimensions}-dim vectors, but {detail}. The columns "
                f"are sized from the EMBEDDING_VECTOR_DIMENSIONS environment "
                f"variable.",
                hint=(
                    "Every embedding write and every semantic search pass for "
                    "those columns is silently skipped, so search results will "
                    "be missing them entirely (issue #794). To fix, set the "
                    f"EMBEDDING_VECTOR_DIMENSIONS environment variable to "
                    f"{provider_dimensions} (#826), then resize the columns — "
                    "image deployment: `python manage.py "
                    "align_embedding_dimensions`; source checkout: "
                    "`python manage.py makemigrations` + `python manage.py "
                    "migrate`. Then run `python manage.py backfill_embeddings`. "
                    "pgvector cannot cast between widths, so the resize "
                    "discards existing vectors and the backfill regenerates "
                    "them. Alternatively switch back to a provider whose "
                    "output width matches the columns."
                ),
                id=EMBEDDING_DIMENSION_MISMATCH,
            )
        ]
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        logger.debug("Embedding dimension system check skipped: %s", exc)
        return []


def check_opencode_session_required(
    app_configs: Any = None, **kwargs: Any
) -> List[DjangoWarning]:
    """Warn when ``opencode_go`` is selected without its REQUIRED session id.

    GitHub #1050. The Zen-Go endpoint rejects a chat completion that carries no
    ``x-opencode-session`` header with ``400 MissingSessionID``. The failure is
    silent by construction, which is why it needs a system check rather than a
    log line:

    * :meth:`llm_adapter.providers.OpencodeGoProvider._chat` *omits* the header
      when the variable is unset (correct — a whitespace-only or absent value
      must not be sent as an empty header), so the request goes out well-formed
      and is refused by the endpoint;
    * the resilience wrapper treats 4xx as permanent, so there is no retry that
      might mask or surface it;
    * the provider-side log is the only place the 400 appears. Nothing in the
      product says "your LLM is dead".

    A compose-level preflight gate already exists for the image deployment; this
    is the in-process half, so a source checkout and every ``manage.py check`` /
    ``runserver`` / ``migrate`` report it too.

    A ``Warning``, not an ``Error``: the deployment may be fine right now (no
    request has used the provider yet, or a DB ``LlmSettings`` row for the
    active tenant overrides ``LLM_PROVIDER``), and a system check that blocks
    ``migrate`` over an unused optional provider would be the wrong severity.
    It must still be loud, which is what the hint is for.

    Never raises: same contract as :func:`check_embedding_dimensions` — a check
    that crashes would take ``migrate`` down with it.
    """
    try:
        from llm_adapter.providers import resolve_provider_config

        cfg = resolve_provider_config()
        if cfg.provider_name != OPENCODE_PROVIDER_NAME:
            return []
        if (cfg.opencode_session or "").strip():
            return []

        return [
            DjangoWarning(
                f"LLM_PROVIDER={OPENCODE_PROVIDER_NAME!r} is selected but "
                "LLM_OPENCODE_SESSION is not set.",
                hint=(
                    "The variable is REQUIRED for this provider, not optional: "
                    "the OpenCode Zen-Go endpoint answers every chat completion "
                    "with `400 MissingSessionID` when the `x-opencode-session` "
                    "header is absent, so every LLM call fails (decomposition, "
                    "validation, consistency check) while the UI shows nothing "
                    "but a provider-side log line (issue #1050). Set "
                    "LLM_OPENCODE_SESSION=<session-id> in the environment and "
                    "restart the process. The session id is treated as a "
                    "credential: it is never logged or echoed in an error "
                    "message."
                ),
                id=OPENCODE_SESSION_MISSING,
            )
        ]
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        logger.debug("OpenCode session system check skipped: %s", exc)
        return []


__all__ = [
    "EMBEDDING_DIMENSION_MISMATCH",
    "EMBEDDING_PROVIDER_UNKNOWN",
    "OPENCODE_PROVIDER_NAME",
    "OPENCODE_SESSION_MISSING",
    "check_embedding_dimensions",
    "check_opencode_session_required",
]
