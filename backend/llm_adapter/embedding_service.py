"""REQ-L2-VS-004 EmbeddingService — best-effort embedding generation.

Generates semantic embeddings (1536-dim, OpenAI text-embedding-3-small
compatible) for Requirement text. Kept in the LlmAdapterSystem (Layer 1) rather
than in persistence (Layer 0), because it is an LLM-provider concern and
llm_adapter is already permitted to depend on persistence — not the reverse.

Contract:
    - ``generate_embedding`` NEVER raises. On any error (missing SDK, network
      failure, unsupported provider) it logs and returns ``None`` so callers can
      persist the requirement without an embedding (best-effort, ADR: embedding
      generation must never fail the surrounding write).
    - Provider support:
        openai  -> real embeddings via the OpenAI SDK.
        mock    -> deterministic pseudo-random vector (stable per input text),
                   so local/CI similarity queries return sensible orderings.
        others  -> None (Anthropic/Ollama/Azure have no embedding path yet).
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# Dimension of the embedding vector. Must match Requirement.embedding
# (VectorField(dimensions=1536)) and the HNSW index.
EMBEDDING_DIMENSIONS = 1536

# OpenAI embedding model producing 1536-dim vectors.
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding_text(requirement) -> str:
    """Combine a requirement's title and description into embedding input.

    Duck-typed: accepts any object exposing ``title`` / ``description``
    attributes (ORM instance or DTO).
    """
    title = getattr(requirement, "title", "") or ""
    description = getattr(requirement, "description", "") or ""
    return f"{title}\n\n{description}".strip()


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate an embedding for *text* via the configured provider.

    Returns a list of ``EMBEDDING_DIMENSIONS`` floats, or ``None`` when no
    embedding could be produced. Never raises (best-effort).
    """
    if not text or not text.strip():
        return None

    provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
    try:
        if provider == "openai":
            return _openai_embedding(text)
        if provider == "mock":
            return _mock_embedding(text)
        # anthropic / ollama / azure / unset: no embedding support yet.
        logger.debug(
            "EmbeddingService: provider %r has no embedding support; "
            "skipping embedding generation",
            provider or "<unset>",
        )
        return None
    except Exception as exc:  # noqa: BLE0001 — best-effort, must not propagate
        logger.warning("EmbeddingService: embedding generation failed: %s", exc)
        return None


def _openai_embedding(text: str) -> Optional[List[float]]:
    """Call the OpenAI embeddings endpoint via the OpenAI SDK.

    Mirrors OpenAiProvider's SDK usage (llm_adapter.providers). Returns None if
    the SDK is unavailable or the response shape is unexpected.
    """
    try:
        from openai import OpenAI  # noqa: PLC0415 (lazy import intentional)
    except ImportError:
        logger.warning(
            "EmbeddingService: openai SDK not installed; cannot generate "
            "embeddings (run: pip install openai)"
        )
        return None

    api_key = os.environ.get("LLM_API_KEY", "")
    timeout = int(os.environ.get("LLM_TIMEOUT", "30"))
    client = OpenAI(api_key=api_key, timeout=timeout)
    response = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=text)
    vector = list(response.data[0].embedding)
    if len(vector) != EMBEDDING_DIMENSIONS:
        logger.warning(
            "EmbeddingService: unexpected embedding dimension %d (expected %d)",
            len(vector),
            EMBEDDING_DIMENSIONS,
        )
        return None
    return vector


def _mock_embedding(text: str) -> List[float]:
    """Return a deterministic pseudo-random unit-ish vector for *text*.

    Seeded by a stable hash of the text so identical inputs always map to the
    same vector — this lets similarity ordering be exercised without a real
    embedding provider (tests, local dev, demo data).
    """
    import random

    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIMENSIONS)]


__all__ = [
    "EMBEDDING_DIMENSIONS",
    "OPENAI_EMBEDDING_MODEL",
    "get_embedding_text",
    "generate_embedding",
]
