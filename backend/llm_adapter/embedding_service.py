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
    "get_icd_version_embedding_text",
    "get_tracelink_embedding_text",
    "generate_embedding",
]
