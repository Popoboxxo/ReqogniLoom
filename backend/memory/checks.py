"""Startup system checks for the memory/vector backends (T-A0-4, T-A2-1).

Two unrelated findings live here because both are deployment-configuration
problems of the same subsystem, both are cheap configuration reads (environment
plus, for the Qdrant key, the persisted override), and both are
``Warning``-only:

* ``memory.W001``/``memory.W002`` — the app and Honcho embed into different
  vector spaces (see the docstring below).
* ``memory.W003`` — a production deployment runs the Qdrant artifact backend
  without ``QDRANT_API_KEY`` (QR-S23; see :func:`qdrant_api_key_missing`).

Registered from :meth:`memory.apps.MemoryConfig.ready`, so ``manage.py check`` /
``runserver`` / ``migrate`` surface the result, and published on ``/health/`` as
the advisories ``embedding_model_consistency`` and — ``?verbose=1`` only, because
the probe is unauthenticated — ``qdrant_api_key`` /
``qdrant_api_key_missing`` (``reqogniloom.health``).

Why a check rather than a log line
----------------------------------
Two independent embedding configurations used to exist (#1317, finding 2): the
app embedded with ``EMBEDDING_MODEL_NAME`` / ``EMBEDDING_VECTOR_DIMENSIONS``,
while Honcho embedded with its own ``HONCHO_EMBEDDING_*`` values. Both sides are
best-effort by design — a vector of the wrong width is silently skipped on the
write side and the semantic pass short-circuits on the read side (see
``llm_adapter.embedding_service``'s module docstring) — so a divergent pair does
not fail anything. It only degrades recall: memory entries are embedded into a
different vector space than the artifacts searched against them, and no error is
ever raised. The mismatch is therefore invisible without an explicit check.

T-A0-3 removed the *default* divergence: ``deploy/docker-compose.yml`` derives
``HONCHO_EMBEDDING_MODEL`` / ``HONCHO_EMBEDDING_VECTOR_DIMENSIONS`` from
``EMBEDDING_MODEL_NAME`` / ``EMBEDDING_VECTOR_DIMENSIONS``. The two variables
remain *overrides*, though — a deliberate (or accidental) override re-opens the
gap, which is exactly what this check reports. It never blocks ``migrate``: a
``Warning``, not an ``Error``, and never a status-code change on ``/health/``.

Scope
-----
The comparison only runs when the *effective* memory backend is ``honcho`` — the
DB override in ``SystemMemorySettings`` wins over the ``MEMORY_BACKEND``
environment variable, resolved by the same helper the backend lookup itself
uses. With any other backend there is no Honcho embedding configuration to
compare against, so there is nothing to report.

Both sides are compared only when configured: an unset/blank model or width
means "not configured" (Honcho's own default applies, and the compose nesting
already guarantees inheritance), so it is not reported as a mismatch.
"""
from __future__ import annotations

import logging
import os
from typing import Any, NamedTuple

from django.core.checks import Warning as DjangoWarning

from persistence.embedding_dimensions import (
    EMBEDDING_VECTOR_DIMENSIONS,
    EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR,
)

logger = logging.getLogger(__name__)

#: ``manage.py check`` id for "the app and Honcho embed with different models".
EMBEDDING_MODEL_MISMATCH = "memory.W001"

#: ``manage.py check`` id for "the app and Honcho embed with different widths".
EMBEDDING_DIMENSION_MISMATCH = "memory.W002"

#: ``manage.py check`` id for "Qdrant serves artifacts without an API key"
#: (QR-S23, T-A2-1; provisionally a warning — ENT-A8 = A).
QDRANT_API_KEY_MISSING = "memory.W003"

#: The explicit artifact vector-backend selector. Read from the environment
#: here instead of importing :mod:`application.vector_port` into a startup
#: check: the check only needs the selector, and the port itself must stay free
#: of a ``memory`` import cycle.
ARTIFACT_VECTOR_BACKEND_ENV_VAR = "ARTIFACT_VECTOR_BACKEND"

#: The one artifact vector backend that is an *external* store with its own auth.
QDRANT_ARTIFACT_BACKEND = "qdrant"

#: Qdrant's own API-key variable (also injected as ``QDRANT__SERVICE__API_KEY``
#: on the ``qdrant`` service — the two must match).
QDRANT_API_KEY_ENV_VAR = "QDRANT_API_KEY"

#: Safe default when ``DJANGO_ENV`` is absent. "Production" is decided by
#: exclusion (anything outside ``settings._NON_PROD_ENVS``), not by this literal
#: — see :func:`_deployment_is_production`.
PRODUCTION_ENV = "production"

#: The one memory backend that runs its own embedding service.
HONCHO_MEMORY_BACKEND = "honcho"

#: Honcho-side model id (read by ``memory.honcho_backend`` and its health probe).
HONCHO_EMBEDDING_MODEL_ENV_VAR = "HONCHO_EMBEDDING_MODEL"

#: Honcho-side vector width. Not read by the backend itself — it is the value
#: Honcho's ``configure_embeddings`` step resizes its own pgvector columns to.
HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR = "HONCHO_EMBEDDING_VECTOR_DIMENSIONS"

#: Backend name used when the effective backend cannot be resolved at all.
_UNRESOLVED_BACKEND_FALLBACK = "pgvector"

#: Operator-facing hint per check id. Kept next to the ids so the message, the
#: hint and the test cannot drift apart on the remediation wording.
_HINTS: dict[str, str] = {
    EMBEDDING_MODEL_MISMATCH: (
        "The app and Honcho must embed into the SAME vector space: Honcho embeds "
        "memory entries, the app embeds artifacts, and a semantic query compares "
        "the two. Otherwise memory retrieval silently returns worse (or no) "
        "results. Fix the deployment so both sides resolve one model — leave "
        f"{HONCHO_EMBEDDING_MODEL_ENV_VAR} unset so it inherits "
        "EMBEDDING_MODEL_NAME (deploy/docker-compose.yml), or set both to the "
        "same value. Publish on /health/ as "
        "advisory.embedding_model_consistency."
    ),
    EMBEDDING_DIMENSION_MISMATCH: (
        "The app and Honcho must embed at the SAME width; a width mismatch makes "
        "the memory and artifact vectors incomparable (and Honcho's own pgvector "
        "columns are resized to this value by honcho-migrate, so a later change "
        "discards the vectors already stored). Leave "
        f"{HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR} unset so it inherits "
        f"{EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR} (deploy/docker-compose.yml), or "
        "set both to the model's output width. Publish on /health/ as "
        "advisory.embedding_model_consistency."
    ),
    QDRANT_API_KEY_MISSING: (
        "The artifact store is configured for Qdrant ("
        f"{ARTIFACT_VECTOR_BACKEND_ENV_VAR}=qdrant) in a production deployment "
        f"and no API key resolves: neither {QDRANT_API_KEY_ENV_VAR} nor the "
        "persisted SystemMemorySettings.qdrant_api_key is set. Unless the qdrant "
        "service itself enforces QDRANT__SERVICE__API_KEY, such a store accepts "
        "unauthenticated callers, so any container on the network can read and "
        "delete every tenant's collections; tenant isolation would rest on "
        "collection names and network segmentation alone. Set "
        f"{QDRANT_API_KEY_ENV_VAR} (and the matching QDRANT__SERVICE__API_KEY on "
        "the qdrant service), then recreate backend/celery so env_file is read "
        "again. Publish on /health/ (?verbose=1) as advisory.qdrant_api_key "
        "and advisory.qdrant_api_key_missing."
    ),
}


class HonchoEmbeddingMismatch(NamedTuple):
    """One effective-config divergence between the app and Honcho.

    Attributes:
        check_id: The ``manage.py check`` id (``memory.W001``/``memory.W002``).
        message: ``manage.py check``-facing description (no values that are
            secrets — model ids and widths only).
    """

    check_id: str
    message: str


def effective_memory_backend_name() -> str:
    """Return the effective memory backend name (DB override over environment).

    Reuses ``memory.backends._resolve_memory_backend_name`` — the resolver
    ``get_memory_backend`` itself uses — so this check cannot disagree with the
    backend that is actually instantiated. Best-effort: a DB/settings problem
    (no table yet during ``migrate``, DB unreachable) degrades to the environment
    value instead of raising.

    Returns:
        The lower-cased backend name, ``"pgvector"`` when nothing is configured.
    """
    try:
        from memory.backends import _resolve_memory_backend_name

        return _resolve_memory_backend_name()
    except Exception as exc:  # noqa: BLE001 - check is best-effort; env is the fallback
        logger.debug("Effective memory backend unresolved, using env: %s", exc)
        return os.environ.get("MEMORY_BACKEND", _UNRESOLVED_BACKEND_FALLBACK).strip().lower()


def _effective_embedding_model() -> str:
    """Return the app's effective embedding model id, or ``""`` when unset.

    ``_read_config`` is the single source the embedding providers are built
    from, so it already applies the ``SystemMemorySettings`` override (Memory
    Admin UI) on top of the environment — comparing against the raw env var
    would report a mismatch for a model the app no longer uses.
    """
    try:
        from llm_adapter.embedding_service import _read_config

        return (_read_config().model_name or "").strip()
    except Exception as exc:  # noqa: BLE001 - check is best-effort; skip on failure
        logger.debug("Effective embedding model unresolved, skipping: %s", exc)
        return ""


def honcho_embedding_mismatches() -> list[HonchoEmbeddingMismatch]:
    """Return every app/Honcho embedding divergence that is configured.

    Shared by :func:`check_honcho_embedding_consistency` (``manage.py check``)
    and ``reqogniloom.health._collect_advisory`` (``/health/``), so both surfaces
    report exactly the same verdict.

    Returns:
        One entry per divergence, empty when Honcho is not the effective backend
        or when the configured values already agree. An unset/blank value on
        either side is treated as "not configured" and never reported.
    """
    if effective_memory_backend_name() != HONCHO_MEMORY_BACKEND:
        return []

    mismatches: list[HonchoEmbeddingMismatch] = []

    app_model = _effective_embedding_model()
    honcho_model = os.environ.get(HONCHO_EMBEDDING_MODEL_ENV_VAR, "").strip()
    if app_model and honcho_model and app_model != honcho_model:
        mismatches.append(
            HonchoEmbeddingMismatch(
                EMBEDDING_MODEL_MISMATCH,
                f"The app embeds with model {app_model!r} but Honcho embeds with "
                f"{honcho_model!r} ({HONCHO_EMBEDDING_MODEL_ENV_VAR}).",
            )
        )

    raw_dimensions = os.environ.get(HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR, "").strip()
    if raw_dimensions:
        try:
            honcho_dimensions = int(raw_dimensions)
        except (TypeError, ValueError):
            # A non-integer width is Honcho's own configuration error; there is
            # no number to compare against, so do not report a second, derived
            # alarm here.
            logger.debug(
                "%s=%r is not an integer; embedding-width comparison skipped.",
                HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR,
                raw_dimensions,
            )
        else:
            if honcho_dimensions != EMBEDDING_VECTOR_DIMENSIONS:
                mismatches.append(
                    HonchoEmbeddingMismatch(
                        EMBEDDING_DIMENSION_MISMATCH,
                        f"The app embeds {EMBEDDING_VECTOR_DIMENSIONS}-dim vectors "
                        f"({EMBEDDING_VECTOR_DIMENSIONS_ENV_VAR}) but Honcho embeds "
                        f"{honcho_dimensions}-dim vectors "
                        f"({HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR}).",
                    )
                )

    return mismatches


def check_honcho_embedding_consistency(
    app_configs: Any = None, **kwargs: Any
) -> list[DjangoWarning]:
    """Warn when the app and Honcho resolve different embedding configurations.

    Both halves are silent by construction (see the module docstring), which is
    why this needs a system check: nothing raises, nothing is logged, and the
    only symptom is degraded memory/semantic search. Reported as a ``Warning``,
    never an ``Error`` — the deployment still works, it just embeds into two
    spaces — so ``migrate`` is never blocked by it.

    ``app_configs``/``kwargs`` are Django's system-check calling convention and
    are unused.

    Never raises: a check that crashes would take ``migrate`` down with it.
    """
    try:
        mismatches = honcho_embedding_mismatches()
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        logger.debug("Honcho embedding consistency check skipped: %s", exc)
        return []

    return [
        DjangoWarning(
            mismatch.message,
            # ``.get`` rather than ``[]``: a missing hint must never turn a
            # warning into a startup-crashing KeyError (see "Never raises").
            hint=_HINTS.get(mismatch.check_id, ""),
            id=mismatch.check_id,
        )
        for mismatch in mismatches
    ]


def qdrant_artifact_backend_selected() -> bool:
    """Whether the artifact store is *configured* for Qdrant.

    Reads only the ``ARTIFACT_VECTOR_BACKEND`` selector. "Configured" is not
    "active": the port decides the full selection (package and base URL
    included) and degrades to pgvector for the rest, so a selected-but-gated
    deployment still serves artifacts from pgvector. This is the "is there
    anything to say about Qdrant auth at all" question, so a default (pgvector)
    deployment reports nothing.
    """
    return (
        os.environ.get(ARTIFACT_VECTOR_BACKEND_ENV_VAR, "")
        .strip()
        .lower()
        == QDRANT_ARTIFACT_BACKEND
    )


def _django_env() -> str:
    """Return the normalised deployment gate (``settings.DJANGO_ENV``).

    Same value and normalisation ``reqogniloom.settings`` uses for its DEBUG
    gate. Note that reading the value is only half of that gate:
    :func:`_deployment_is_production` applies the same membership test, so
    "production" here means exactly what it means there. Falls back to
    ``production`` (the safe default) when the setting is absent — e.g. in a
    bare check invocation.
    """
    from django.conf import settings

    return str(getattr(settings, "DJANGO_ENV", PRODUCTION_ENV)).strip().lower()


def _non_production_envs() -> frozenset[str]:
    """Return the non-production ``DJANGO_ENV`` values.

    Taken from :mod:`reqogniloom.settings` (the single definition the ``DEBUG``
    gate uses) rather than copied here: a second literal set silently drifts,
    and a drifted set was exactly the false negative this helper removes —
    ``DJANGO_ENV=staging`` (or ``prod``, or a typo) is production for settings,
    so it must be production for this check too. Imported lazily to keep the
    startup-check module free of every import-time settings dependency. An
    unreadable set degrades to "everything is production": over-warning is the
    safe direction, silence is not.
    """
    try:
        from reqogniloom.settings import _NON_PROD_ENVS
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        # Deliberately broader than ``ImportError``: the docstring's promise is
        # that an unreadable set degrades to "everything is production", and an
        # import that raises anything else (a broken settings module, an
        # ImportError from a transitive import, a partially initialised module)
        # would otherwise take ``manage.py check``/``migrate`` down instead.
        logger.warning(
            "No non-production environment set found (%s); treating all as "
            "production.",
            exc,
        )
        return frozenset()
    return frozenset(_NON_PROD_ENVS)


def _deployment_is_production() -> bool:
    """Whether this process runs outside the declared non-production envs.

    Mirrors ``reqogniloom.settings``' ``DEBUG`` gate: every value that is not
    one of ``development``/``dev``/``local``/``test`` is production. Comparing
    against ``"production"`` instead (the previous behaviour) left ``prod``,
    ``staging``, ``sandbox`` and typos in a silent no-warning zone.
    """
    return _django_env() not in _non_production_envs()


def _qdrant_api_key_configured() -> bool:
    """Whether an API key is configured for Qdrant (DB override over env).

    Resolves through the same helper the artifact port and the memory backend
    use, because a key persisted in ``SystemMemorySettings.qdrant_api_key``
    never appears in the environment — reading only ``os.environ`` reported a
    false ``memory.W003`` on every readiness probe of such a deployment.

    A non-empty ``QDRANT_API_KEY`` short-circuits BEFORE the resolver: the
    predicate is a boolean, and no DB value can turn a configured env key into
    "no key" (the resolver only lets a non-``None`` ``SystemMemorySettings``
    field replace it, and a blank field is coerced to ``None``). The DB round
    trip therefore cannot change the answer — dropping it removes one query from
    every readiness probe. The resolver still runs (and the env is still the
    fallback) for the deployment whose key lives only in the DB row, and for an
    unresolvable config: over-warning is safe, silence is not.
    """
    env_key = os.environ.get(QDRANT_API_KEY_ENV_VAR, "").strip()
    if env_key:
        return True
    try:
        from memory.qdrant_backend import resolve_effective_qdrant_config

        resolved_key = resolve_effective_qdrant_config().api_key
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        # Unresolvable config and no env key (checked above): this process cannot
        # see a key, so callers warn (`memory.W003` / `/health/`). An unreadable
        # DB is no evidence of a configured key, and over-warning is the safe
        # direction — silence would hide a keyless store.
        logger.debug("Qdrant API-key resolution failed: %s", exc)
        return False
    return bool(str(resolved_key or "").strip())


def qdrant_api_key_missing() -> bool:
    """Whether Qdrant is configured and production resolves no API key.

    The three conditions, all of which must hold (QR-S23):

    1. ``ARTIFACT_VECTOR_BACKEND=qdrant`` — the artifact store is *configured*
       for Qdrant. It is not necessarily active (a missing ``qdrant_client`` or
       ``QDRANT_BASE_URL`` still degrades to pgvector); warning in that case is
       deliberate, because the selector says Qdrant holds tenant vectors as soon
       as the gate closes.
    2. ``DJANGO_ENV`` is not a declared non-production value — an isolated
       dev/test stack with no key is the accepted case, not a finding. The test
       is the settings module's ``_NON_PROD_ENVS`` membership, so ``staging``,
       ``prod`` or a typo stays production (see
       :func:`_deployment_is_production`).
    3. No API key is resolvable — neither ``QDRANT_API_KEY`` nor the persisted
       ``SystemMemorySettings.qdrant_api_key`` (DB override over env, resolved by
       the same helper the backends use).

    Shared by :func:`check_qdrant_api_key` (``manage.py check``, ``memory.W003``)
    and ``reqogniloom.health._collect_advisory``, so both surfaces agree. A
    keyless Qdrant is only a *finding*, never a hard error: the deployment still
    serves (ENT-A8 = A, provisionally as a warning).
    """
    if not qdrant_artifact_backend_selected():
        return False
    if _qdrant_api_key_configured():
        return False
    return _deployment_is_production()


def check_qdrant_api_key(
    app_configs: Any = None, **kwargs: Any
) -> list[DjangoWarning]:
    """Warn when production configures Qdrant but resolves no API key.

    A ``Warning``, never an ``Error``: nothing is broken, the store is merely
    keyless. ``app_configs``/``kwargs`` are Django's system-check calling
    convention and are unused.

    Never raises: a check that crashes would take ``migrate`` down with it.
    """
    try:
        missing = qdrant_api_key_missing()
    except Exception as exc:  # noqa: BLE001 - a check must never break startup.
        logger.debug("Qdrant API-key check skipped: %s", exc)
        return []

    if not missing:
        return []
    return [
        DjangoWarning(
            (
                f"{ARTIFACT_VECTOR_BACKEND_ENV_VAR}=qdrant is configured in a "
                "production deployment but no Qdrant API key resolves: "
                f"{QDRANT_API_KEY_ENV_VAR} is not set and "
                "SystemMemorySettings.qdrant_api_key is empty."
            ),
            hint=_HINTS.get(QDRANT_API_KEY_MISSING, ""),
            id=QDRANT_API_KEY_MISSING,
        )
    ]


__all__ = [
    "ARTIFACT_VECTOR_BACKEND_ENV_VAR",
    "EMBEDDING_DIMENSION_MISMATCH",
    "EMBEDDING_MODEL_MISMATCH",
    "HONCHO_EMBEDDING_DIMENSIONS_ENV_VAR",
    "HONCHO_EMBEDDING_MODEL_ENV_VAR",
    "HONCHO_MEMORY_BACKEND",
    "HonchoEmbeddingMismatch",
    "QDRANT_API_KEY_ENV_VAR",
    "QDRANT_API_KEY_MISSING",
    "QDRANT_ARTIFACT_BACKEND",
    "check_honcho_embedding_consistency",
    "check_qdrant_api_key",
    "effective_memory_backend_name",
    "honcho_embedding_mismatches",
    "qdrant_api_key_missing",
    "qdrant_artifact_backend_selected",
]
