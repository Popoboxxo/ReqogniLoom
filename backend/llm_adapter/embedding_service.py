"""REQ-L2-VS-004 EmbeddingService — best-effort embedding generation.

Generates semantic embeddings via configurable providers (default:
sentence-transformers, 384 dims; optional: ollama 768 dims, openai 1536 dims)
for Requirement/TraceLink/Icd text. Kept in the LlmAdapterSystem
(Layer 1) rather than in persistence (Layer 0), because it is an LLM-provider
concern and llm_adapter is already permitted to depend on persistence — not
the reverse.

Contract:
    - ``generate_embedding`` NEVER raises. On any error (missing SDK, network
      failure, unsupported provider) it logs and returns ``None`` so callers can
      persist the requirement without an embedding (best-effort, ADR: embedding
      generation must never fail the surrounding write).
    - Provider support:
        sentence-transformers  -> real embeddings via sentence-transformers SDK
                                  (default, 384 dims, in-process).
        ollama                 -> real embeddings via ollama remote service
                                  (768 dims, optional external service).
        openai                 -> real embeddings via the OpenAI SDK
                                  (1536 dims, requires API key).
        mock                   -> deterministic pseudo-random vector (stable per
                                  input text), so local/CI similarity queries
                                  return sensible orderings.

DIMENSIONS (#794, #1149): every ``VectorField`` in this project is sized from
``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`` (default
384). The ``mock`` and ``sentence-transformers`` providers emit exactly that
configured width instead of a hardcoded 384 (#1149): ``mock`` generates
``EMBEDDING_VECTOR_DIMENSIONS`` values directly, and the
``sentence-transformers`` provider adapts its native model output to the
configured width via :func:`_fit_vector_to_dimensions` (zero-pad when the
model is narrower, truncate when it is wider). Zero padding preserves cosine
similarity exactly — zero components contribute nothing to either the dot
product or the L2 norm — and truncation, though lossy, is explicit. Both are
preferable to the silently skipped write a hardcoded width mismatch used to
cause.

    History: ``EMBEDDING_PROVIDER``'s default changed from ``openai`` to
    ``sentence-transformers`` (Task 1 of the ai-memory-and-search plan) while
    ``Requirement.embedding``/``TraceLink.embedding``/``Icd.embedding``
    stayed hardcoded ``vector(1536)``. Because every write site guards
    ``len(vector) == column.dimensions`` before touching the DB (a mismatched
    width is a pgvector ``DataError`` that poisons the caller's ambient
    transaction) and the read side short-circuits identically, the shipped
    default silently skipped 100% of embedding writes and left semantic
    ``artifact.search`` permanently empty. #794 resized the columns and made
    the residual mismatch loud rather than silent.

The ``ollama`` (native 768) and ``openai`` (native 1536) providers still
validate their response against their own native width and do NOT adapt to
``EMBEDDING_VECTOR_DIMENSIONS``. Selecting one whose native width differs from
the configured column width reintroduces the mismatch, which is loud rather
than silent: ``llm_adapter.checks.check_embedding_dimensions`` reports it via
``manage.py check`` at startup, and the first skipped write logs at WARNING
(:func:`warn_dimension_mismatch`). To run such a provider, set
``EMBEDDING_VECTOR_DIMENSIONS`` to its native width, generate the resulting
``AlterField`` migrations for every embedding column and re-run ``manage.py
backfill_embeddings`` (existing vectors cannot be cast between widths and are
discarded). On an image deployment, use
``python manage.py align_embedding_dimensions`` instead of
``makemigrations``/``migrate``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from django.db.models import Q

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

logger = logging.getLogger(__name__)

# sentence-transformers' all-MiniLM-L6-v2 (the new default model) has 384 dims;
# this is now provider-dependent, not a single module-wide constant -- callers
# needing the dimension read it off the resolved provider instance, not a
# module constant (memory.MemoryEntry in Task 2 hardcoded 384
# because they are built specifically against the default provider for v1 --
# see Global Constraints on fixed-per-tenant provider selection).


class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    def embed(self, text: str) -> list[float] | None:
        ...


@dataclass
class EmbeddingProviderConfig:
    provider_name: str = ""
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float | None = None


def _read_env_config() -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        provider_name=os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers").strip().lower(),
        model_name=os.environ.get("EMBEDDING_MODEL_NAME") or None,
        base_url=os.environ.get("OLLAMA_BASE_URL") or None,
        api_key=os.environ.get("LLM_API_KEY") or None,  # reuses the existing LLM API key, not a new secret
        timeout=float(os.environ.get("EMBEDDING_TIMEOUT", "10")),
    )


#: SA-21: DI seam so this Layer-1 module never imports ``memory`` (an
#: ADR-01 Layer-2-placed app, per memory.apps.MemoryConfig's own docstring)
#: directly. ``memory.apps.MemoryConfig.ready()`` registers the real
#: SystemMemorySettings lookup here at startup -- the same
#: register-on-``ready()`` pattern ``audit.apps.AuditConfig`` uses for
#: ``AuditLogWriter``/``DomainEventBus``. Replaces the previous lazy
#: ``from memory.models import SystemMemorySettings`` import, which only
#: avoided *crashing* on the memory<->llm_adapter circular import (memory
#: itself imports ``llm_adapter.embedding_service.generate_embedding`) --
#: it did not remove the backwards dependency.
_settings_override_provider: Callable[[EmbeddingProviderConfig], EmbeddingProviderConfig] | None = None


def register_settings_override_provider(
    provider: Callable[[EmbeddingProviderConfig], EmbeddingProviderConfig],
) -> None:
    """Register the Layer-2/Ext settings-override lookup. Called once from
    ``memory.apps.MemoryConfig.ready()`` at Django startup."""
    global _settings_override_provider
    _settings_override_provider = provider


def _apply_db_settings(cfg: EmbeddingProviderConfig) -> EmbeddingProviderConfig:
    """Overlay a persisted SystemMemorySettings override onto an env-based
    config (Memory Admin UI Phase 3). Mirrors llm_adapter.providers's own
    _apply_db_settings for LlmSettings -- same best-effort semantics: any
    failure (no row, DB unavailable, provider not yet registered) leaves cfg
    untouched, env stays the fallback.

    Unlike LlmSettings (#1190), this override is **process-wide**, not
    tenant-scoped: ``SystemMemorySettings`` is an ``AuditableModel`` (a single
    global row, per its own docstring), so its lookup does not require a
    :class:`~persistence.tenancy.TenantContext` and must not be gated on one --
    doing so would drop the global embedding override on worker/management
    paths that legitimately run without a tenant. Failures are already quiet
    (DEBUG, no traceback), so the alarming-WARNING half of #1190 does not
    apply here.
    """
    if _settings_override_provider is None:
        return cfg
    try:
        return _settings_override_provider(cfg)
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
        logger.debug("SystemMemorySettings lookup skipped; falling back to environment.")
        return cfg


def _read_config() -> EmbeddingProviderConfig:
    return _apply_db_settings(_read_env_config())


EMBEDDING_PROVIDER_REGISTRY: dict[str, type[EmbeddingProvider]] = {}


def register_embedding_provider(name: str) -> Callable[[type[EmbeddingProvider]], type[EmbeddingProvider]]:
    def _decorator(cls: type[EmbeddingProvider]) -> type[EmbeddingProvider]:
        EMBEDDING_PROVIDER_REGISTRY[name] = cls
        return cls
    return _decorator


def get_embedding_provider(config: EmbeddingProviderConfig | None = None) -> EmbeddingProvider:
    cfg = config or _read_config()
    provider_cls = EMBEDDING_PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise ValueError(f"unknown embedding provider: {cfg.provider_name!r}")
    return provider_cls(cfg)


def _fit_vector_to_dimensions(vector: list[float], dimensions: int) -> list[float]:
    """Resize ``vector`` to exactly ``dimensions`` entries (#1149).

    Every embedding column is sized from ``EMBEDDING_VECTOR_DIMENSIONS`` and
    pgvector rejects a write whose width differs with a ``DataError`` that
    would poison the caller's ambient transaction — so a provider must emit
    exactly the configured width. A provider whose underlying model has a
    fixed native width (``sentence-transformers``' ``all-MiniLM-L6-v2`` is
    384-dim) cannot otherwise honour a non-default
    ``EMBEDDING_VECTOR_DIMENSIONS`` (e.g. the ambient 768):

    * **shorter than configured** -> zero-pad. Zero components contribute
      nothing to a dot product or an L2 norm, so cosine similarity — the
      metric every embedding search in this project uses — is preserved
      exactly.
    * **longer than configured** -> truncate. Lossy, but explicit and still
      far better than the write being silently skipped, which is what a
      hardcoded width produced before #1149.

    Args:
        vector: The provider's native embedding.
        dimensions: The configured output width (a positive integer).

    Returns:
        A new list of length ``dimensions``.
    """
    if len(vector) == dimensions:
        return list(vector)
    if len(vector) > dimensions:
        return list(vector[:dimensions])
    return list(vector) + [0.0] * (dimensions - len(vector))


@register_embedding_provider("mock")
class MockEmbeddingProvider(EmbeddingProvider):
    # Emit the configured width directly (issue #1149). Hardcoding 384 here
    # made every test/dev run structurally dimension-inconsistent whenever
    # EMBEDDING_VECTOR_DIMENSIONS was 768, which triggered the write-side
    # warn_dimension_mismatch and skipped the embedding.
    dimensions = EMBEDDING_VECTOR_DIMENSIONS
    # Not a real model, but the provenance id names one anyway: every provider
    # resolves it the same way (``cfg.model_name or _DEFAULT_MODEL``), so
    # ``mock:mock:<dims>`` falls out of one rule instead of the provider-name
    # fallback in :func:`current_embedding_model_id`.
    _DEFAULT_MODEL = "mock"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._config = config

    def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]


@register_embedding_provider("sentence-transformers")
class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Default provider: runs in-process, no extra container/service.
    Model weights are bundled into the backend/celery Docker image at build
    time (Task 12 adds the download step to the Dockerfile).

    The model's native width (384 for ``all-MiniLM-L6-v2``) is adapted to the
    configured ``EMBEDDING_VECTOR_DIMENSIONS`` by
    :func:`_fit_vector_to_dimensions`, so the emitted vector always matches
    the embedding columns (issue #1149)."""

    dimensions = EMBEDDING_VECTOR_DIMENSIONS
    _DEFAULT_MODEL = "all-MiniLM-L6-v2"
    _model = None  # class-level lazy singleton -- loading the model is expensive (~100ms+)
    # Which model name _model was actually built from. The cache is KEYED by
    # this name: without it, an EMBEDDING_MODEL_NAME change (env or, since
    # Memory Admin UI Phase 3, a SystemMemorySettings override) would be
    # silently ignored by every worker that had already loaded some model,
    # while the admin UI reported the new value as active.
    _loaded_model_name: str | None = None

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._model_name = config.model_name or self._DEFAULT_MODEL

    def _get_model(self):
        cls = SentenceTransformersEmbeddingProvider
        if cls._model is None or cls._loaded_model_name != self._model_name:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(self._model_name)
            cls._loaded_model_name = self._model_name
        return cls._model

    def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        try:
            model = self._get_model()
            vector = model.encode(text, normalize_embeddings=True)
            # #1149: adapt the model's native width to the configured column
            # width so a non-default EMBEDDING_VECTOR_DIMENSIONS does not make
            # every write get skipped by the dimension guard.
            return _fit_vector_to_dimensions(vector.tolist(), self.dimensions)
        except Exception as exc:  # noqa: BLE001 — embedding best-effort; None (logged)
            logger.warning("sentence-transformers embedding failed: %s", exc)
            return None


@register_embedding_provider("ollama")
class OllamaEmbeddingProvider(EmbeddingProvider):
    """Optional, externally-connectable -- requires a reachable Ollama service."""

    dimensions = 768  # nomic-embed-text's native dimension
    _DEFAULT_MODEL = "nomic-embed-text"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self._model_name = config.model_name or self._DEFAULT_MODEL
        self._timeout = config.timeout or 10

    def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        import requests
        try:
            response = requests.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model_name, "prompt": text},
                timeout=self._timeout,
            )
            response.raise_for_status()
            vector = response.json().get("embedding")
            if not vector or len(vector) != self.dimensions:
                logger.warning("ollama embedding returned unexpected shape")
                return None
            return vector
        except Exception as exc:  # noqa: BLE001 — embedding best-effort; None (logged)
            logger.warning("ollama embedding failed: %s", exc)
            return None


@register_embedding_provider("openai")
class OpenAiEmbeddingProvider(EmbeddingProvider):
    """Existing provider, kept as an optional higher-quality alternative."""

    dimensions = 1536
    _DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._api_key = config.api_key
        self._model_name = config.model_name or self._DEFAULT_MODEL
        self._timeout = config.timeout or 10

    def embed(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        try:
            import openai
            client = openai.OpenAI(api_key=self._api_key, timeout=self._timeout)
            response = client.embeddings.create(model=self._model_name, input=text)
            vector = response.data[0].embedding
            if len(vector) != self.dimensions:
                logger.warning("openai embedding returned unexpected dimension %d", len(vector))
                return None
            return vector
        except Exception as exc:  # noqa: BLE001 — embedding best-effort; None (logged)
            logger.warning("openai embedding failed: %s", exc)
            return None


def generate_embedding(text: str) -> list[float] | None:
    """Backward-compatible facade -- existing call sites (Requirement, TraceLink,
    Icd embedding generation) are unchanged, now backed by the registry."""
    if not text or not text.strip():
        return None
    try:
        return get_embedding_provider().embed(text)
    except Exception as exc:  # noqa: BLE001 — embedding best-effort; None (logged)
        logger.warning("generate_embedding failed: %s", exc)
        return None


#: Sites that have already warned about a dimension mismatch this process,
#: keyed by ``(site, produced_dimensions, expected_dimensions)``. See
#: :func:`warn_dimension_mismatch`.
_warned_dimension_mismatches: set = set()


def warn_dimension_mismatch(site: str, produced: int, expected: int) -> None:
    """Log a dimension mismatch once per process, at WARNING level (#794).

    Every embedding write site guards ``len(vector) == column.dimensions``
    before touching the DB, because pgvector rejects a mismatched width with a
    ``DataError`` that would poison the caller's ambient transaction. Those
    guards used to log at DEBUG, which is why the shipped default
    configuration could skip *100% of embedding writes* — for months, on every
    deployment — with no operator-visible signal at all beyond an
    ``artifact.search`` that never returned semantic hits.

    WARNING, not DEBUG: a skipped embedding is a silent loss of a feature, not
    routine bookkeeping. Deduplicated per process rather than logged per write
    so that a bulk operation (import, ``backfill_embeddings``) reporting a real
    misconfiguration does not emit one line per row — the condition is a
    static config property, so the first occurrence carries all the
    information the thousandth would.
    """
    key = (site, produced, expected)
    if key in _warned_dimension_mismatches:
        logger.debug(
            "%s: embedding skipped, dimension mismatch (got %d, column expects %d)",
            site,
            produced,
            expected,
        )
        return
    _warned_dimension_mismatches.add(key)
    logger.warning(
        "%s: embedding skipped and semantic search will be incomplete -- "
        "dimension mismatch: the configured embedding provider produced a "
        "%d-dim vector but the column expects %d dims. Run `manage.py check` "
        "for the full report (#794). Further occurrences of this exact "
        "mismatch log at DEBUG.",
        site,
        produced,
        expected,
    )


#: Provenance id for an embedding whose model could not be resolved. Never
#: raised, never persisted for a *successful* vector: a write path must not fail
#: because the provenance metadata is unavailable (T-A0-6).
UNKNOWN_EMBEDDING_MODEL_ID = "unknown:unknown:0"

#: Environment variable selecting the read-side comparison mode: ``warn``
#: (default) leaves every result set untouched and logs one WARNING per process
#: when rows were written by a different model; ``strict`` additionally excludes
#: those rows from similarity queries. ``NULL`` (legacy rows, written before the
#: column existed, T-A0-5) stays visible in BOTH modes (#1317, ADR-024 O3).
EMBEDDING_MODEL_STRICT_ENV = "EMBEDDING_MODEL_STRICT"
EMBEDDING_MODEL_MODE_STRICT = "strict"
EMBEDDING_MODEL_MODE_WARN = "warn"

#: Set once the unresolved-config warning has been logged — see
#: :func:`current_embedding_model_id`.
_unknown_model_id_warned = False

#: Set once the warn-mode drift sample has been taken (see
#: :func:`note_foreign_embedding_models`).
_foreign_model_sample_taken = False


def current_embedding_model_id() -> str:
    """Return the provenance id of the vector the active config produces.

    Format: ``"<provider>:<model_name>:<dims>"`` — e.g.
    ``"ollama:nomic-embed-text:768"`` or
    ``"sentence-transformers:all-MiniLM-L6-v2:384"``. The three components come
    from the SAME resolved configuration :func:`generate_embedding` uses
    (``_read_config()``: ``SystemMemorySettings`` override first, environment as
    the fallback) and the width the resolved provider class actually emits
    (``EmbeddingProvider.dimensions``; the columns are sized from it), so the id
    can never disagree with the vector it labels.

    Never raises (write-path contract, T-A0-6): an unresolvable provider or a
    broken settings lookup yields :data:`UNKNOWN_EMBEDDING_MODEL_ID` and logs
    one WARNING per process. A missing/mistyped provider name is already
    reported loudly by ``llm_adapter.checks`` and ``manage.py
    verify_embedding_dimensions``; provenance must not add a second failure
    mode to every write.

    Returns:
        ``"<provider>:<model_name>:<dims>"``, or ``"unknown:unknown:0"``.
    """
    global _unknown_model_id_warned
    try:
        cfg = _read_config()
        # Resolving through the registry's own factory keeps this id and
        # ``generate_embedding`` on ONE lookup/instantiation path: a provider
        # that overrides its effective model name in ``__init__`` (or refuses an
        # unknown name) behaves identically in both.
        provider = get_embedding_provider(cfg)
        dimensions = int(getattr(provider, "dimensions", 0) or 0)
        model_name = (
            cfg.model_name
            or getattr(type(provider), "_DEFAULT_MODEL", None)
            or cfg.provider_name
        )
        return f"{cfg.provider_name}:{model_name}:{dimensions}"
    except Exception as exc:  # noqa: BLE001 - provenance is best-effort by contract
        if not _unknown_model_id_warned:
            _unknown_model_id_warned = True
            logger.warning(
                "current_embedding_model_id: cannot resolve the embedding "
                "provider configuration (%s); using %r. Embedding provenance "
                "will be unusable until EMBEDDING_PROVIDER / the memory "
                "settings override is fixed.",
                exc,
                UNKNOWN_EMBEDDING_MODEL_ID,
            )
        return UNKNOWN_EMBEDDING_MODEL_ID


def generate_embedding_with_model(text: str) -> tuple[list[float] | None, str]:
    """Generate a vector and the provenance id of the model that produced it.

    Thin wrapper around :func:`generate_embedding` (all provider logic stays
    there; this function never duplicates it) so a write site can persist
    ``embedding`` and ``embedding_model`` from ONE call and the two can never
    drift apart.

    Args:
        text: The embedding input.

    Returns:
        ``(vector, model_id)``. ``vector`` is ``None`` whenever
        :func:`generate_embedding` would return ``None`` (empty text, provider
        failure, unknown provider); ``model_id`` is still the resolved id in that
        case, and callers MUST NOT persist it without a vector.
    """
    model_id = current_embedding_model_id()
    return generate_embedding(text), model_id


def embedding_model_strict_mode() -> str:
    """Return the read-side comparison mode: ``"warn"`` (default) or ``"strict"``.

    Reads :data:`EMBEDDING_MODEL_STRICT_ENV`. Any value other than an exact
    ``strict`` — unset, empty, a typo, different casing after normalisation
    (``STRICT`` normalises to ``strict``) — is treated as ``warn``, so a
    deployment can never be crashed or silently filtered by a mistyped flag. The
    default is ``warn`` because it is the only mode that provably keeps the
    result set byte-identical to the pre-T-A0-6 behaviour.
    """
    raw = (os.environ.get(EMBEDDING_MODEL_STRICT_ENV) or "").strip().lower()
    if raw == EMBEDDING_MODEL_MODE_STRICT:
        return EMBEDDING_MODEL_MODE_STRICT
    return EMBEDDING_MODEL_MODE_WARN


def embedding_model_filter() -> Q | None:
    """Return the strict-mode provenance filter, or ``None`` in ``warn`` mode.

    ``strict`` keeps the rows this process would write (``embedding_model`` ==
    :func:`current_embedding_model_id`) and every legacy ``NULL`` row, and
    excludes rows written by a *different* model — the case ADR-024 O3 exists
    for: a model change that keeps the same dimension is otherwise invisible to
    a cosine query.

    Returns:
        ``Q(embedding_model=<current>) | Q(embedding_model__isnull=True)`` in
        strict mode; ``None`` in warn mode (callers then leave the queryset
        untouched).
    """
    if embedding_model_strict_mode() != EMBEDDING_MODEL_MODE_STRICT:
        return None
    return Q(embedding_model=current_embedding_model_id()) | Q(
        embedding_model__isnull=True
    )


def note_foreign_embedding_models(queryset, *, site: str = "") -> int:
    """Warn once per process about rows embedded by a different model (#1317).

    Warn mode must not change a single result set, so the comparison is
    observation only: one aggregate ``COUNT`` for rows whose
    ``embedding_model`` is non-``NULL`` and differs from
    :func:`current_embedding_model_id`. The count runs at most ONCE per process
    and emits at most ONE WARNING — a per-query count on the hot search path
    would cost more than the signal is worth.

    WHICH SCOPE IS COUNTED (deliberately not "the corpus" by default): a
    similarity query only ever sees its caller's tenant, and an aggregate over
    that queryset cannot say anything about the other tenants. So the count
    follows the role's actual visibility, probed through
    :func:`persistence.rls_visibility.count_scope`:

    * role bypasses RLS (superuser / ``BYPASSRLS``) -> the model's ``unscoped``
      manager, i.e. the whole corpus;
    * otherwise (RLS-bound role, with or without a tenant context) -> *queryset*
      as given, i.e. only the caller's own scope.

    The log line names the scope it counted, and ``/health/?verbose=1``
    (``advisory.embedding_model_drift``) plus
    ``manage.py verify_embedding_dimensions --models`` remain the per-table
    views an operator reads for the authoritative numbers.

    A no-op in strict mode (the rows are filtered out instead) and never raises:
    a broken count must not break a search.

    Args:
        queryset: A queryset over a model carrying ``embedding`` /
            ``embedding_model``, already scoped to what the caller would see.
        site: Caller label for the log line (e.g. ``"PgVectorVectorPort"``).

    Returns:
        The number of drifting rows found, or ``0`` when the sample was already
        taken this process / strict mode is active / the count failed.
    """
    global _foreign_model_sample_taken
    if embedding_model_strict_mode() != EMBEDDING_MODEL_MODE_WARN:
        return 0
    if _foreign_model_sample_taken:
        return 0

    from persistence.rls_visibility import COUNT_SCOPE_CORPUS, count_scope

    model_id = current_embedding_model_id()
    corpus_wide = count_scope() == COUNT_SCOPE_CORPUS
    sample = queryset
    if corpus_wide:
        unscoped = getattr(queryset.model, "unscoped", None)
        if unscoped is not None:
            sample = unscoped.all()
    scope_label = (
        "the whole corpus (this role bypasses RLS)"
        if corpus_wide
        else "this caller's scope only (the role is RLS-bound)"
    )
    try:
        drifting = (
            sample.filter(embedding__isnull=False)
            .exclude(embedding_model=model_id)
            .exclude(embedding_model__isnull=True)
            .count()
        )
    except Exception as exc:  # noqa: BLE001 - the advisory must never break a read
        # The flag is deliberately NOT set here: a transient DB error must not
        # disable drift reporting for the rest of the process lifetime. Two
        # concurrent first queries can therefore both count and both log — that
        # duplicate is benign, and cheaper than a lock on the search hot path.
        logger.debug("%s: embedding-model drift count skipped: %s", site, exc)
        return 0
    _foreign_model_sample_taken = True

    if drifting:
        logger.warning(
            "%s: %d embedding row(s) in %s were written by a different model "
            "than the current %s; they remain visible because "
            "EMBEDDING_MODEL_STRICT defaults to 'warn'. Set "
            "EMBEDDING_MODEL_STRICT=strict to exclude them from similarity "
            "search, or re-embed them with `manage.py backfill_embeddings "
            "--force` (#1317).",
            site or "embedding read",
            drifting,
            scope_label,
            model_id,
        )
    return drifting


def get_embedding_text(requirement) -> str:
    """Combine a requirement's title and description into embedding input.

    Duck-typed: accepts any object exposing ``title`` / ``description``
    attributes (ORM instance or DTO).
    """
    title = getattr(requirement, "title", "") or ""
    description = getattr(requirement, "description", "") or ""
    return f"{title}\n\n{description}".strip()


def get_icd_embedding_text(icd) -> str:
    """Combine an ICD's contract fields into embedding input.

    REQ-L2-VS-004. Duck-typed: accepts any object exposing the ICD contract
    attributes (ORM instance, ``IcdRevision`` or DTO). Includes the interface
    name when present so structurally similar interfaces cluster.

    Task 28c-2: renamed from ``get_icd_version_embedding_text`` and reads
    ``name`` directly — the contract and the name now live on the same row,
    so the old ``icd_id``/``icd.name`` relation walk is gone.
    """
    parts: list[str] = []

    name = getattr(icd, "name", None)
    if name:
        parts.append(f"Interface: {name}")

    parts.append(f"Type: {getattr(icd, 'interface_type', '') or ''}")
    parts.append(
        f"Description: {getattr(icd, 'semantic_description', '') or ''}"
    )

    preconditions = getattr(icd, "preconditions", None)
    if preconditions:
        parts.append(f"Preconditions: {' '.join(str(p) for p in preconditions)}")
    postconditions = getattr(icd, "postconditions", None)
    if postconditions:
        parts.append(f"Postconditions: {' '.join(str(p) for p in postconditions)}")
    invariants = getattr(icd, "invariants", None)
    if invariants:
        parts.append(f"Invariants: {' '.join(str(p) for p in invariants)}")

    return "\n".join(p for p in parts if p).strip()


def get_tracelink_embedding_text(tracelink) -> str:
    """Combine a TraceLink's endpoints and type into embedding input.

    REQ-L2-VS-004. Resolves source/target Artifact titles via the OneToOne
    relations (``requirement`` / ``architecture_element``, matching the
    related_name declared on the persistence models). Falls back to the raw
    endpoint IDs when no title is resolvable (best-effort, never raises for a
    missing relation).
    """
    def _endpoint_title(artifact, artifact_id) -> str:
        if artifact is not None:
            req = getattr(artifact, "requirement", None)
            if req is not None and getattr(req, "title", None):
                return req.title
            arch = getattr(artifact, "architecture_element", None)
            if arch is not None and getattr(arch, "title", None):
                return arch.title
        return str(artifact_id)

    source_title = _endpoint_title(
        getattr(tracelink, "source", None), getattr(tracelink, "source_id", "")
    )
    target_title = _endpoint_title(
        getattr(tracelink, "target", None), getattr(tracelink, "target_id", "")
    )
    link_type = getattr(tracelink, "link_type", "") or ""
    return f"{link_type}: {source_title} → {target_title}".strip()


__all__ = [
    "EMBEDDING_MODEL_MODE_STRICT",
    "EMBEDDING_MODEL_MODE_WARN",
    "EMBEDDING_MODEL_STRICT_ENV",
    "EMBEDDING_PROVIDER_REGISTRY",
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "UNKNOWN_EMBEDDING_MODEL_ID",
    "current_embedding_model_id",
    "embedding_model_filter",
    "embedding_model_strict_mode",
    "generate_embedding",
    "generate_embedding_with_model",
    "get_embedding_provider",
    "get_embedding_text",
    "get_icd_embedding_text",
    "get_tracelink_embedding_text",
    "note_foreign_embedding_models",
    "register_embedding_provider",
    "warn_dimension_mismatch",
]
