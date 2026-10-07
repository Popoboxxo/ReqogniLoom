"""Shared Qdrant configuration + the collection-naming security boundary.

ADR-020 (Qdrant as an optional vector backend) puts every Qdrant knob in one
Layer-0 module so the ``QdrantMemoryBackend`` (V1, ``memory``) and the vector
port (V2, ``application``/``persistence``) resolve exactly the same
configuration and build exactly the same collection names. Living in
``persistence`` (Layer 0) is deliberate, mirroring
``persistence.embedding_dimensions``: everything above persistence may import
it, persistence imports nothing upward. This module therefore imports only the
standard library and :mod:`persistence.embedding_dimensions`.

Two responsibilities:

1. :func:`resolve_qdrant_config` -- resolve the Qdrant connection settings from
   explicit overrides (the ``SystemMemorySettings`` rows) layered over the
   ``QDRANT_*`` environment variables. The **vector dimension is never an env
   knob**: it ALWAYS mirrors :data:`persistence.embedding_dimensions.
   EMBEDDING_VECTOR_DIMENSIONS` (ADR-020 §6). A drift between a Qdrant
   collection and that SSOT is a configuration error and is made loud in the
   backend, never papered over here.

2. :func:`build_collection_name` -- the **security boundary** (ADR-020 §2,
   Collection-Strategie A). Qdrant has no Postgres RLS, so tenant/workspace
   isolation rests entirely on the collection name. Every collection name this
   project ever addresses is produced here, from the tenant id and scope; a
   name is never passed through from a caller. A missing tenant id is an error,
   not an unnamed collection. Tenant and workspace segments must be UUID-shaped
   -- validating that (instead of sanitizing arbitrary text) closes the
   sanitizing-collision hole: two different non-UUID ids could otherwise fold to
   the same collection segment and silently merge two tenants' vectors.

3. :data:`QDRANT_DISTANCE_ATTRS` -- the one shared distance vocabulary. Both the
   runtime backend and the memory write serializer read it, so the accepted
   ``QDRANT_DISTANCE`` names can never drift apart again.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from uuid import UUID

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

#: Default request timeout (seconds) for the Qdrant client and the health probe.
DEFAULT_QDRANT_TIMEOUT = 5.0

#: Default distance metric. ``cosine`` matches the project-wide
#: ``vector_cosine_ops`` HNSW indexes (ADR-020 §Offene Entscheidungen O2).
DEFAULT_QDRANT_DISTANCE = "cosine"

#: Default collection prefix, matching the project's ``reqlo`` short name.
DEFAULT_QDRANT_COLLECTION_PREFIX = "reqlo"

#: Accepted ``QDRANT_DISTANCE`` names -> qdrant-client ``models.Distance``
#: attribute. The SINGLE source of truth for the distance vocabulary: the
#: runtime backend and the memory write serializer both read it, so a name the
#: serializer offers can never be unknown to the backend (and vice versa).
#: ``euclidean`` is the spelled-out alias of ``euclid``.
QDRANT_DISTANCE_ATTRS = {
    "cosine": "COSINE",
    "dot": "DOT",
    "euclid": "EUCLID",
    "euclidean": "EUCLID",
    "manhattan": "MANHATTAN",
}

#: Default HNSW build parameters, mirroring ``mem_memory_entry``'s HNSW index
#: (``m=16``, ``ef_construction=64``, see ``memory/models.py``).
DEFAULT_QDRANT_HNSW_M = 16
DEFAULT_QDRANT_HNSW_EF_CONSTRUCT = 64

#: Charset Qdrant accepts in a collection name. Everything else is folded to
#: ``_`` so a UUID (or any future id shape) can never produce an invalid name.
_UNSAFE_NAME_CHARS = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class QdrantConfig:
    """Resolved, immutable Qdrant connection configuration.

    ``vector_dimensions`` is read from
    :data:`persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS` and is
    NOT backed by an environment variable -- see the module docstring.
    """

    base_url: str
    api_key: str | None
    timeout: float
    distance: str
    collection_prefix: str
    hnsw_m: int
    hnsw_ef_construct: int
    prefer_grpc: bool
    vector_dimensions: int


def _parse_float(raw: object, default: float) -> float:
    """Return *raw* as a positive float, else *default* (a typo is not fatal)."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_int(raw: object, default: int) -> int:
    """Return *raw* as a positive int, else *default* (a typo is not fatal)."""
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_bool(raw: object, default: bool = False) -> bool:
    """Return *raw* as a bool; ``None`` falls back to *default*."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_qdrant_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    collection_prefix: str | None = None,
    distance: str | None = None,
    timeout: float | None = None,
    hnsw_m: int | None = None,
    hnsw_ef_construct: int | None = None,
    prefer_grpc: bool | None = None,
) -> QdrantConfig:
    """Resolve a :class:`QdrantConfig` from overrides layered over the env.

    Every ``None`` override falls through to the matching ``QDRANT_*``
    environment variable and then to the module-level default. A non-``None``
    override (including an explicit ``False`` for ``prefer_grpc``) wins -- this
    is how ``SystemMemorySettings`` rows override the deployment env.

    ``vector_dimensions`` is ALWAYS
    :data:`persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`; there
    is deliberately no ``QDRANT_VECTOR_DIMENSIONS`` knob.
    """
    resolved_base_url = (
        base_url if base_url is not None else os.environ.get("QDRANT_BASE_URL", "")
    ).strip()
    resolved_api_key = api_key if api_key is not None else os.environ.get("QDRANT_API_KEY")
    resolved_prefix = (
        collection_prefix
        if collection_prefix is not None
        else os.environ.get("QDRANT_COLLECTION_PREFIX", DEFAULT_QDRANT_COLLECTION_PREFIX)
    ).strip() or DEFAULT_QDRANT_COLLECTION_PREFIX
    resolved_distance = (
        distance
        if distance is not None
        else os.environ.get("QDRANT_DISTANCE", DEFAULT_QDRANT_DISTANCE)
    ).strip().lower() or DEFAULT_QDRANT_DISTANCE
    resolved_timeout = (
        _parse_float(timeout, DEFAULT_QDRANT_TIMEOUT)
        if timeout is not None
        else _parse_float(os.environ.get("QDRANT_TIMEOUT"), DEFAULT_QDRANT_TIMEOUT)
    )
    resolved_hnsw_m = (
        _parse_int(hnsw_m, DEFAULT_QDRANT_HNSW_M)
        if hnsw_m is not None
        else _parse_int(os.environ.get("QDRANT_HNSW_M"), DEFAULT_QDRANT_HNSW_M)
    )
    resolved_hnsw_ef = (
        _parse_int(hnsw_ef_construct, DEFAULT_QDRANT_HNSW_EF_CONSTRUCT)
        if hnsw_ef_construct is not None
        else _parse_int(
            os.environ.get("QDRANT_HNSW_EF_CONSTRUCT"), DEFAULT_QDRANT_HNSW_EF_CONSTRUCT
        )
    )
    resolved_prefer_grpc = (
        _parse_bool(prefer_grpc)
        if prefer_grpc is not None
        else _parse_bool(os.environ.get("QDRANT_PREFER_GRPC"), False)
    )

    return QdrantConfig(
        base_url=resolved_base_url,
        api_key=(resolved_api_key or None),
        timeout=resolved_timeout,
        distance=resolved_distance,
        collection_prefix=resolved_prefix,
        hnsw_m=resolved_hnsw_m,
        hnsw_ef_construct=resolved_hnsw_ef,
        prefer_grpc=resolved_prefer_grpc,
        vector_dimensions=EMBEDDING_VECTOR_DIMENSIONS,
    )


def is_qdrant_configured() -> bool:
    """Whether a Qdrant base URL is configured in the environment.

    Deliberately env-only (Layer 0 cannot read the ``SystemMemorySettings``
    override row). Callers that need the *effective* configuration -- including
    the DB override -- use :func:`resolve_qdrant_config` and test its
    ``base_url`` field instead.
    """
    return bool(os.environ.get("QDRANT_BASE_URL", "").strip())


def _sanitize_name_part(value: object) -> str:
    """Lowercase *value* and fold every unsafe character to ``_``.

    Used for the configurable *prefix* only. Tenant/workspace segments are NOT
    sanitized -- see :func:`_uuid_name_part` -- because folding arbitrary text
    lets two distinct ids collapse onto one segment (a cross-tenant hazard).
    """
    return _UNSAFE_NAME_CHARS.sub("_", str(value).strip().lower()).strip("_")


def _uuid_name_part(value: object, label: str) -> str:
    """Return *value* as a canonical lowercase UUID string, or raise.

    Args:
        value: The tenant/workspace id to validate.
        label: Human-readable label for the error message.

    Raises:
        ValueError: When *value* is not UUID-shaped. Validating UUID form (not
            sanitizing) closes the collision hole: two different non-UUID ids
            can no longer fold to the same collection segment and silently merge
            two tenants' vectors.
    """
    try:
        return str(UUID(str(value).strip()))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"qdrant {label} must be a UUID (got {value!r}); "
            "non-UUID segments can sanitize-collide across tenants"
        ) from exc



def build_collection_name(
    prefix: str,
    tenant_id: object,
    *,
    workspace_id: object | None = None,
    scope: str,
    artifacts: bool = False,
) -> str:
    """Build the tenant-scoped Qdrant collection name (Strategy A).

    This function is the **isolation boundary** (ADR-020 §2/§5): because Qdrant
    cannot enforce tenant isolation itself, every collection name ReqogniLoom
    addresses is derived here from the tenant id -- callers never supply a raw
    collection name.

    Mapping:

    * ``scope="workspace"`` -> ``<prefix>_<tenant>_<workspace>``
    * ``scope="user"``      -> ``<prefix>_<tenant>_user``
    * ``artifacts=True``    -> ``..._artifacts`` suffix

    Args:
        prefix: Collection prefix (``QDRANT_COLLECTION_PREFIX``); an empty or
            unusable prefix falls back to :data:`DEFAULT_QDRANT_COLLECTION_PREFIX`.
        tenant_id: The owning tenant UUID. Falsy is rejected -- a collection
            without a tenant is exactly the cross-tenant hazard this guards.
        workspace_id: Required (and UUID-shaped) for ``scope="workspace"``.
        scope: ``"workspace"`` or ``"user"``.
        artifacts: Append the ``_artifacts`` suffix (artifact vectors).

    Raises:
        ValueError: If ``tenant_id`` is falsy/not UUID-shaped, if ``scope`` is
            unknown, or if a workspace collection is requested without a
            UUID-shaped workspace id.
    """
    if not tenant_id:
        raise ValueError("qdrant collection name requires a tenant id (no tenant context)")

    tenant_segment = _uuid_name_part(tenant_id, "tenant id")

    safe_prefix = _sanitize_name_part(prefix) or DEFAULT_QDRANT_COLLECTION_PREFIX

    if scope == "user":
        name = f"{safe_prefix}_{tenant_segment}_user"
    elif scope == "workspace":
        if not workspace_id:
            raise ValueError("qdrant workspace collection requires a workspace id")
        workspace_segment = _uuid_name_part(workspace_id, "workspace id")
        name = f"{safe_prefix}_{tenant_segment}_{workspace_segment}"
    else:
        raise ValueError(f"unknown memory scope for qdrant collection: {scope!r}")

    if artifacts:
        name = f"{name}_artifacts"
    return name


__all__ = [
    "DEFAULT_QDRANT_COLLECTION_PREFIX",
    "DEFAULT_QDRANT_DISTANCE",
    "DEFAULT_QDRANT_HNSW_EF_CONSTRUCT",
    "DEFAULT_QDRANT_HNSW_M",
    "DEFAULT_QDRANT_TIMEOUT",
    "QDRANT_DISTANCE_ATTRS",
    "QdrantConfig",
    "build_collection_name",
    "is_qdrant_configured",
    "resolve_qdrant_config",
]
