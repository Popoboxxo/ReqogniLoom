"""REQ-L2-VS-004 EmbeddingService — best-effort embedding generation.

Generates semantic embeddings via configurable providers (default:
sentence-transformers, 384 dims; optional: ollama 768 dims, openai 1536 dims)
for Requirement/TraceLink/IcdVersion text. Kept in the LlmAdapterSystem
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

UPGRADE NOTE (ai-memory-and-search plan, Task 1): ``EMBEDDING_PROVIDER``'s
default changed from ``openai`` to ``sentence-transformers`` in this branch.
``Requirement.embedding``/``TraceLink.embedding``/``IcdVersion.embedding`` are
fixed ``vector(1536)`` columns (OpenAI-shaped, pre-dating this change).
sentence-transformers produces 384-dim vectors, so an EXISTING deployment
that relied on these columns being populated (i.e. had ``LLM_PROVIDER=openai``
configured for the old embedding path) gets NO new embeddings written for any
requirement/trace-link/ICD-version artifact created or updated after
upgrading, unless it explicitly keeps/sets ``EMBEDDING_PROVIDER=openai``.
This degrades silently, not loudly: the dimension mismatch is caught by a
guard on both the write side (``RequirementService.
_generate_and_store_embedding`` et al., Task 12) and the read side
(``application.search_service._run_semantic_query``, final whole-branch
review Finding 5) and simply skips the write / semantic search pass rather
than raising -- by design (embeddings are always best-effort here), but that
means there is no error to notice on upgrade.

    Set ``EMBEDDING_PROVIDER=openai`` to preserve the pre-existing 1536-dim
    embedding behavior for Requirement/TraceLink/IcdVersion.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)

# sentence-transformers' all-MiniLM-L6-v2 (the new default model) has 384 dims;
# this is now provider-dependent, not a single module-wide constant -- callers
# needing the dimension read it off the resolved provider instance, not a
# module constant (WorkspaceMemory/UserTenantMemory in Task 2 hardcode 384
# because they are built specifically against the default provider for v1 --
# see Global Constraints on fixed-per-tenant provider selection).


class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    def embed(self, text: str) -> Optional[List[float]]:
        ...


@dataclass
class EmbeddingProviderConfig:
    provider_name: str = ""
    model_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[float] = None


def _read_env_config() -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        provider_name=os.environ.get("EMBEDDING_PROVIDER", "sentence-transformers").strip().lower(),
        model_name=os.environ.get("EMBEDDING_MODEL_NAME") or None,
        base_url=os.environ.get("OLLAMA_BASE_URL") or None,
        api_key=os.environ.get("LLM_API_KEY") or None,  # reuses the existing LLM API key, not a new secret
        timeout=float(os.environ.get("EMBEDDING_TIMEOUT", "10")),
    )


def _apply_db_settings(cfg: EmbeddingProviderConfig) -> EmbeddingProviderConfig:
    """Overlay a persisted SystemMemorySettings override onto an env-based
    config (Memory Admin UI Phase 3). Mirrors llm_adapter.providers's own
    _apply_db_settings for LlmSettings -- same best-effort semantics: any
    failure (no row, DB unavailable) leaves cfg untouched, env stays the
    fallback. Lazy import avoids a memory<->llm_adapter circular import.
    """
    try:
        from memory.models import SystemMemorySettings

        row = SystemMemorySettings.objects.first()
        if row is None:
            return cfg
        if row.embedding_provider:
            cfg.provider_name = row.embedding_provider
        if row.embedding_model_name:
            cfg.model_name = row.embedding_model_name
        if row.ollama_base_url:
            cfg.base_url = row.ollama_base_url
        if row.embedding_timeout:
            cfg.timeout = float(row.embedding_timeout)
        return cfg
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
        logger.debug("SystemMemorySettings lookup skipped; falling back to environment.")
        return cfg


def _read_config() -> EmbeddingProviderConfig:
    return _apply_db_settings(_read_env_config())


EMBEDDING_PROVIDER_REGISTRY: Dict[str, Type[EmbeddingProvider]] = {}


def register_embedding_provider(name: str) -> Callable[[Type[EmbeddingProvider]], Type[EmbeddingProvider]]:
    def _decorator(cls: Type[EmbeddingProvider]) -> Type[EmbeddingProvider]:
        EMBEDDING_PROVIDER_REGISTRY[name] = cls
        return cls
    return _decorator


def get_embedding_provider(config: Optional[EmbeddingProviderConfig] = None) -> EmbeddingProvider:
    cfg = config or _read_config()
    provider_cls = EMBEDDING_PROVIDER_REGISTRY.get(cfg.provider_name)
    if provider_cls is None:
        raise ValueError(f"unknown embedding provider: {cfg.provider_name!r}")
    return provider_cls(cfg)


@register_embedding_provider("mock")
class MockEmbeddingProvider(EmbeddingProvider):
    dimensions = 384

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._config = config

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]


@register_embedding_provider("sentence-transformers")
class SentenceTransformersEmbeddingProvider(EmbeddingProvider):
    """Default provider: runs in-process, no extra container/service.
    Model weights are bundled into the backend/celery Docker image at build
    time (Task 12 adds the download step to the Dockerfile)."""

    dimensions = 384
    _DEFAULT_MODEL = "all-MiniLM-L6-v2"
    _model = None  # class-level lazy singleton -- loading the model is expensive (~100ms+)
    # Which model name _model was actually built from. The cache is KEYED by
    # this name: without it, an EMBEDDING_MODEL_NAME change (env or, since
    # Memory Admin UI Phase 3, a SystemMemorySettings override) would be
    # silently ignored by every worker that had already loaded some model,
    # while the admin UI reported the new value as active.
    _loaded_model_name: Optional[str] = None

    def __init__(self, config: EmbeddingProviderConfig) -> None:
        self._model_name = config.model_name or self._DEFAULT_MODEL

    def _get_model(self):
        cls = SentenceTransformersEmbeddingProvider
        if cls._model is None or cls._loaded_model_name != self._model_name:
            from sentence_transformers import SentenceTransformer
            cls._model = SentenceTransformer(self._model_name)
            cls._loaded_model_name = self._model_name
        return cls._model

    def embed(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        try:
            model = self._get_model()
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        except Exception as exc:
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

    def embed(self, text: str) -> Optional[List[float]]:
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
        except Exception as exc:
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

    def embed(self, text: str) -> Optional[List[float]]:
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
        except Exception as exc:
            logger.warning("openai embedding failed: %s", exc)
            return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """Backward-compatible facade -- existing call sites (Requirement, TraceLink,
    IcdVersion embedding generation) are unchanged, now backed by the registry."""
    if not text or not text.strip():
        return None
    try:
        return get_embedding_provider().embed(text)
    except Exception as exc:
        logger.warning("generate_embedding failed: %s", exc)
        return None


def get_embedding_text(requirement) -> str:
    """Combine a requirement's title and description into embedding input.

    Duck-typed: accepts any object exposing ``title`` / ``description``
    attributes (ORM instance or DTO).
    """
    title = getattr(requirement, "title", "") or ""
    description = getattr(requirement, "description", "") or ""
    return f"{title}\n\n{description}".strip()


def get_icd_version_embedding_text(icd_version) -> str:
    """Combine an IcdVersion's contract fields into embedding input.

    REQ-L2-VS-004. Duck-typed: accepts any object exposing the IcdVersion
    contract attributes (ORM instance or DTO). Includes the parent ICD name
    when the relation is available so structurally similar interfaces cluster.
    """
    parts: List[str] = []

    icd_name = None
    if getattr(icd_version, "icd_id", None):
        icd = getattr(icd_version, "icd", None)
        icd_name = getattr(icd, "name", None) if icd is not None else None
    if icd_name:
        parts.append(f"Interface: {icd_name}")

    parts.append(f"Type: {getattr(icd_version, 'interface_type', '') or ''}")
    parts.append(
        f"Description: {getattr(icd_version, 'semantic_description', '') or ''}"
    )

    preconditions = getattr(icd_version, "preconditions", None)
    if preconditions:
        parts.append(f"Preconditions: {' '.join(str(p) for p in preconditions)}")
    postconditions = getattr(icd_version, "postconditions", None)
    if postconditions:
        parts.append(f"Postconditions: {' '.join(str(p) for p in postconditions)}")
    invariants = getattr(icd_version, "invariants", None)
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
    "EmbeddingProvider",
    "EmbeddingProviderConfig",
    "EMBEDDING_PROVIDER_REGISTRY",
    "register_embedding_provider",
    "get_embedding_provider",
    "generate_embedding",
    "get_embedding_text",
    "get_icd_version_embedding_text",
    "get_tracelink_embedding_text",
]
