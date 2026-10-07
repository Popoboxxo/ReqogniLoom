"""Vector-port abstraction for artifact ANN search (ADR-020 V2).

Four call sites used to run pgvector's ``CosineDistance`` directly on the ORM:
``search_service._run_semantic_query`` (Requirement/TraceLink/Icd branches),
``requirement_service.find_similar_requirements``,
``trace_link_service.find_similar_trace_links`` and
``icd_manager.find_similar_icds``. This module is the single seam between those
callers and the concrete vector store: a caller asks the port for the nearest
neighbours of a query vector and never builds a ``CosineDistance`` query itself.

Design contract:

* **pgvector is the default AND the fallback** and preserves the exact query
  semantics of the four sites (same filters, ordering, limits, DTO shapes and
  error contracts). Moving a site onto the port must not change a single
  observable byte for a pgvector deployment.
* **Qdrant is opt-in, never implicit.** :func:`get_vector_port` selects the
  Qdrant adapter ONLY when all of the following hold: the explicit selector
  ``ARTIFACT_VECTOR_BACKEND=qdrant``, the effective memory backend is
  ``qdrant`` (``MEMORY_BACKEND`` / ``SystemMemorySettings``), the optional
  ``qdrant_client`` package is importable, and an effective Qdrant base URL is
  configured. Anything else degrades to pgvector -- switching the artifact
  vector store requires an explicit opt-in, never a side effect of another
  knob. A pgvector-only deployment never needs the package.
* **V2 Qdrant artifact search needs a workspace scope and an artifact
  indexer.** The per-workspace ``_artifacts`` collections are populated by an
  artifact indexer that is *out of scope* for this port; without one the
  collections are empty and the Requirement/TraceLink/Icd paths return no hits.
  ``find_similar_trace_links``/``find_similar_icds`` carry no workspace scope,
  so the Qdrant adapter fails loud (``QdrantBackendUnavailableError``) for them
  rather than scanning every workspace collection -- and that error can only
  occur under the explicit ``ARTIFACT_VECTOR_BACKEND=qdrant`` opt-in above.
* ``qdrant_client`` is **never imported at module import time** -- only inside
  the Qdrant adapter's lazy helpers -- so importing this module is always safe.
* ``enable_iterative_ann_scan`` (``application.pgvector_ann``) is
  pgvector-specific. The port does not generalise it: the ``iterative_scan``
  flag carries the existing per-site inconsistency (search's three branches and
  ``find_similar_requirements`` use it; ``find_similar_trace_links`` and
  ``find_similar_icds`` do not) into one adapter-owned place instead of
  "fixing" it.

The port returns :class:`VectorHit` (id + cosine distance) only; callers that
need the full row re-fetch it by id. Keeping the port vector-store-shaped (not
ORM-shaped) is what lets the Qdrant adapter implement the same interface.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from uuid import UUID

from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError

from persistence.models import Requirement, TraceLink

logger = logging.getLogger(__name__)

#: The collections this port knows. ``collection`` selects the entity type whose
#: vectors are queried; ``_resolve_model_and_manager`` raises for anything else,
#: so an unknown value fails loud instead of silently querying the wrong table.
COLLECTION_REQUIREMENT = "Requirement"
COLLECTION_TRACE_LINK = "TraceLink"
COLLECTION_ICD = "Icd"

#: Qdrant payload keys the artifact adapter filters and reads. ``entity_id`` is
#: the canonical Postgres row id; ``entity_type`` is the ``collection`` value.
_PAYLOAD_ENTITY_ID = "entity_id"
_PAYLOAD_ENTITY_TYPE = "entity_type"
_PAYLOAD_TENANT_ID = "tenant_id"
_PAYLOAD_WORKSPACE_ID = "workspace_id"

#: Explicit selector for the ARTIFACT vector backend. Deliberately separate from
#: ``MEMORY_BACKEND`` (which governs the AI memory store) so the artifact store
#: is never switched as a side effect of another knob (ADR-020 §4). Values:
#: ``pgvector`` (default) or ``qdrant``.
ARTIFACT_VECTOR_BACKEND_ENV = "ARTIFACT_VECTOR_BACKEND"
DEFAULT_ARTIFACT_VECTOR_BACKEND = "pgvector"
_QDRANT_ARTIFACT_BACKEND = "qdrant"


class VectorBackendUnavailableError(RuntimeError):
    """Base: a vector backend cannot serve the query (package missing/unreachable)."""


class PgVectorBackendUnavailableError(VectorBackendUnavailableError):
    """The pgvector package or the ``vector`` DB extension is unavailable."""


class QdrantBackendUnavailableError(VectorBackendUnavailableError):
    """Qdrant is unreachable, misconfigured, or ``qdrant_client`` is absent."""


@dataclass(frozen=True)
class VectorHit:
    """One nearest-neighbour hit: the canonical row id and its cosine distance.

    ``distance`` follows pgvector's convention (lower = closer). The Qdrant
    adapter converts Qdrant's similarity score with ``1 - score`` so both
    adapters speak the same scale.

    ``id`` is ALWAYS the canonical row ``UUID``: the Qdrant adapter coerces the
    string payload id to ``UUID`` (``_coerce_uuid``), exactly like pgvector's
    ``row.id``, so every caller can key ORM rows by ``hit.id`` for both
    backends. A point whose id is not UUID-shaped is skipped rather than
    surfaced as an id no ORM lookup could ever resolve.
    """

    id: Any
    distance: float


class VectorPort(Protocol):
    """The vector-store surface the four artifact ANN sites depend on."""

    def query_similar(
        self,
        *,
        collection: str,
        query_vector: Sequence[float],
        tenant_id: Any,
        workspace_id: Optional[UUID] = None,
        workspace_field: Optional[str] = None,
        exclude_id: Optional[Any] = None,
        limit: int = 50,
        iterative_scan: bool = False,
    ) -> list[VectorHit]:
        """Return the ``limit`` nearest rows to ``query_vector``, closest first."""
        ...


def _resolve_model_and_manager(collection: str) -> tuple[Any, Any]:
    """Map a ``collection`` to its model + queryset manager.

    Requirement/TraceLink resolve through ``.objects`` -- the
    :class:`persistence.tenancy.TenantManager` auto-scopes to the ambient tenant
    (the explicit ``tenant_id`` filter is belt-and-braces). Icd resolves through
    ``Icd.unscoped`` with an explicit ``tenant_id``, mirroring
    ``icd_manager.find_similar_icds`` (Icd lives in the Ext layer, so the import
    stays lazy).
    """
    if collection == COLLECTION_REQUIREMENT:
        return Requirement, Requirement.objects
    if collection == COLLECTION_TRACE_LINK:
        return TraceLink, TraceLink.objects
    if collection == COLLECTION_ICD:
        from icd.models import Icd  # lazy: Ext-layer, mirrors the callers

        return Icd, Icd.unscoped
    raise ValueError(f"unknown vector collection: {collection!r}")


def _distance_from_score(score: Any) -> Optional[float]:
    """Map a Qdrant similarity score to the port's cosine-distance convention.

    Qdrant's ``score`` is a similarity (higher = closer); the port uses
    pgvector's cosine distance (lower = closer), so the mapping is ``1 - score``.
    Tolerant by design (mirrors ``memory.qdrant_backend._distance_from_score``):
    ``None`` -- meaning "skip this point" -- for a missing or non-numeric score
    rather than letting a raw ``ValueError``/``TypeError`` escape the adapter.
    """
    if score is None:
        return None
    try:
        return 1.0 - float(score)
    except (TypeError, ValueError):
        return None


def _coerce_uuid(value: Any) -> Optional[UUID]:
    """Coerce a Qdrant payload id to the ``UUID`` ORM rows are keyed by.

    Qdrant stores/returns point ids as strings, while Requirement/TraceLink/Icd
    primary keys are ``UUID``. Without this coercion every Qdrant hit id would
    be a ``str`` and the call sites' ``if hit.id in rows`` (rows keyed by
    ``UUID``) would silently drop every hit. Returns ``None`` for a value that
    is not UUID-shaped, so such a point is skipped instead of poisoning a
    hydration lookup.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


class PgVectorVectorPort:
    """Default/fallback adapter: pgvector cosine ANN over the ORM.

    Byte-for-byte the queries the four sites used to build themselves --
    ``tenant_id`` + ``embedding__isnull=False`` always, an optional workspace
    filter, ``exclude_id``, ``order_by("distance")[:limit]`` and (only when
    asked) an ``atomic()`` savepoint around ``enable_iterative_ann_scan``.
    """

    def query_similar(
        self,
        *,
        collection: str,
        query_vector: Sequence[float],
        tenant_id: Any,
        workspace_id: Optional[UUID] = None,
        workspace_field: Optional[str] = None,
        exclude_id: Optional[Any] = None,
        limit: int = 50,
        iterative_scan: bool = False,
    ) -> list[VectorHit]:
        try:
            from pgvector.django import CosineDistance  # lazy: pgvector may be absent
        except ImportError as exc:
            raise PgVectorBackendUnavailableError(
                "pgvector package not installed — similarity search unavailable"
            ) from exc

        _model, manager = _resolve_model_and_manager(collection)

        qs = manager.filter(tenant_id=tenant_id, embedding__isnull=False)
        if workspace_id is not None and workspace_field is not None:
            qs = qs.filter(**{workspace_field: workspace_id})
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        qs = (
            qs.annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:limit]
        )

        rows = self._evaluate(qs, iterative_scan=iterative_scan)
        return [VectorHit(id=row.id, distance=float(row.distance)) for row in rows]

    @staticmethod
    def _evaluate(qs: Any, *, iterative_scan: bool) -> list[Any]:
        """Evaluate *qs*, optionally inside a transaction-local iterative scan.

        The ``atomic()`` savepoint is what keeps a DB-level error (e.g. the
        dimension-mismatch ``DataError``) from poisoning the caller's ambient
        transaction -- the same protection the callers used to wrap around their
        own queryset evaluation.
        """
        try:
            if iterative_scan:
                from application.pgvector_ann import enable_iterative_ann_scan

                with transaction.atomic():
                    enable_iterative_ann_scan()
                    return list(qs)
            return list(qs)
        except (ProgrammingError, OperationalError) as exc:
            raise PgVectorBackendUnavailableError(
                "pgvector extension not available — similarity search unavailable"
            ) from exc


def _qdrant_client_available() -> bool:
    """Whether the optional ``qdrant_client`` package is importable (no import)."""
    try:
        return importlib.util.find_spec("qdrant_client") is not None
    except (ImportError, ValueError):
        return False


class QdrantVectorPort:
    """Optional Qdrant adapter over the artifact ``_artifacts`` collection.

    One collection per workspace (ADR-020 §2, Strategy A); the ``collection``
    argument (= entity type) is a payload filter, not part of the name. The
    collection name is always produced by
    :func:`persistence.qdrant_config.build_collection_name` (the security
    boundary) from the tenant/workspace ids -- a caller never supplies a name.

    ``qdrant_client`` and its ``models`` namespace are imported lazily. The
    ``client``/``models_module``/``config`` constructor seams let tests drive the
    real adapter with a fake client without the package installed.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        models_module: Any = None,
        config: Any = None,
    ) -> None:
        # Effective config (DB override over env) so the artifact port honours
        # the same SystemMemorySettings rows the memory backend does.
        self._config = config if config is not None else _effective_qdrant_config()
        self._client = client
        self._models_module = models_module

    def _models(self) -> Any:
        if self._models_module is None:
            from qdrant_client import models  # lazy: optional dependency

            self._models_module = models
        return self._models_module

    def _ensure_client(self) -> Any:
        if self._client is None:
            from qdrant_client import QdrantClient  # lazy: optional dependency

            self._client = QdrantClient(
                url=self._config.base_url,
                api_key=self._config.api_key,
                timeout=self._config.timeout,
                prefer_grpc=self._config.prefer_grpc,
            )
        return self._client

    def _collection_name(self, tenant_id: Any, workspace_id: Optional[UUID]) -> str:
        from persistence.qdrant_config import build_collection_name  # lazy: security boundary

        if workspace_id is None:
            # Strategy A has exactly one artifact collection per workspace; the
            # TraceLink/ICD similarity methods carry no workspace filter, so the
            # adapter cannot address a single collection for them. Fail loud
            # (mapped to the caller's PgVectorUnavailable-equivalent) rather than
            # scanning every workspace collection.
            raise QdrantBackendUnavailableError(
                "qdrant artifact search requires a workspace scope"
            )
        return build_collection_name(
            self._config.collection_prefix,
            tenant_id,
            workspace_id=workspace_id,
            scope="workspace",
            artifacts=True,
        )

    def _build_filter(
        self,
        collection: str,
        tenant_id: Any,
        workspace_id: Optional[UUID],
        exclude_id: Any,
    ) -> Any:
        models = self._models()
        must = [
            models.FieldCondition(
                key=_PAYLOAD_TENANT_ID, match=models.MatchValue(value=str(tenant_id))
            ),
            models.FieldCondition(
                key=_PAYLOAD_ENTITY_TYPE, match=models.MatchValue(value=collection)
            ),
        ]
        if workspace_id is not None:
            # Redundant with the per-workspace collection name, but keeps the
            # payload self-describing and defends against a mis-mapped name.
            must.append(
                models.FieldCondition(
                    key=_PAYLOAD_WORKSPACE_ID,
                    match=models.MatchValue(value=str(workspace_id)),
                )
            )
        must_not = []
        if exclude_id is not None:
            must_not.append(
                models.FieldCondition(
                    key=_PAYLOAD_ENTITY_ID,
                    match=models.MatchValue(value=str(exclude_id)),
                )
            )
        return models.Filter(must=must, must_not=must_not)

    def query_similar(
        self,
        *,
        collection: str,
        query_vector: Sequence[float],
        tenant_id: Any,
        workspace_id: Optional[UUID] = None,
        workspace_field: Optional[str] = None,
        exclude_id: Optional[Any] = None,
        limit: int = 50,
        iterative_scan: bool = False,
    ) -> list[VectorHit]:
        name = self._collection_name(tenant_id, workspace_id)
        vector = [float(component) for component in query_vector]
        query_filter = self._build_filter(collection, tenant_id, workspace_id, exclude_id)
        client = self._ensure_client()
        try:
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=name,
                    query=vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                points = list(getattr(response, "points", response) or [])
            else:
                points = list(
                    client.search(
                        collection_name=name,
                        query_vector=vector,
                        query_filter=query_filter,
                        limit=limit,
                        with_payload=True,
                    )
                )
        except QdrantBackendUnavailableError:
            raise
        except Exception as exc:  # every client failure is an outage
            raise QdrantBackendUnavailableError(
                f"qdrant query failed: {type(exc).__name__}"
            ) from exc
        return self._hits_from_points(points)

    @staticmethod
    def _hits_from_points(points: list[Any]) -> list[VectorHit]:
        hits: list[VectorHit] = []
        for point in points:
            # Tolerant distance parsing: a missing/non-numeric score skips the
            # point instead of raising a raw ValueError out of the adapter.
            distance = _distance_from_score(getattr(point, "score", None))
            if distance is None:
                continue
            payload = getattr(point, "payload", None) or {}
            # Coerce to UUID: Qdrant returns string ids while the callers key
            # ORM rows by UUID (M1 -- without this every hit is dropped).
            entity_id = _coerce_uuid(
                payload.get(_PAYLOAD_ENTITY_ID, getattr(point, "id", None))
            )
            if entity_id is None:
                continue
            hits.append(VectorHit(id=entity_id, distance=distance))
        return hits


def get_vector_port() -> VectorPort:
    """Return the active vector port: pgvector by default, Qdrant if opted in.

    Qdrant is selected ONLY when every gate condition holds (see
    :func:`_qdrant_selected`): the explicit ``ARTIFACT_VECTOR_BACKEND=qdrant``
    selector, an effective memory backend of ``qdrant``, an importable
    ``qdrant_client`` package, and a configured effective Qdrant base URL. Any
    other case -- unset selector, memory backend not qdrant, package absent,
    unconfigured, or a construction failure -- degrades to the pgvector
    adapter, so the default path is never affected by the optional backend
    (ADR-020 §4). There is deliberately no implicit switch.
    """
    if _qdrant_selected():
        try:
            return QdrantVectorPort()
        except Exception:  # optional backend must never break search
            logger.warning(
                "Qdrant is configured but the vector port could not be built; "
                "falling back to pgvector",
                exc_info=True,
            )
    return PgVectorVectorPort()


def _artifact_vector_backend() -> str:
    """Return the explicit artifact vector-backend selector (default pgvector)."""
    return os.environ.get(
        ARTIFACT_VECTOR_BACKEND_ENV, DEFAULT_ARTIFACT_VECTOR_BACKEND
    ).strip().lower()


def _effective_memory_backend_name() -> str:
    """Return the effective memory backend name (DB override over env).

    Best-effort: ``memory.backends._resolve_memory_backend_name`` reads the
    ``SystemMemorySettings`` override first and falls back to ``MEMORY_BACKEND``;
    a DB/settings problem degrades to the env value so the gate never crashes.
    """
    try:
        from memory.backends import _resolve_memory_backend_name  # lazy: gate only

        return _resolve_memory_backend_name()
    except Exception:  # noqa: BLE001 - gate is best-effort; env is the fallback
        return os.environ.get("MEMORY_BACKEND", "pgvector").strip().lower()


def _effective_qdrant_config() -> Any:
    """Resolve the effective Qdrant config (DB override over env), lazily.

    Prefers ``memory.qdrant_backend.resolve_effective_qdrant_config`` so the
    artifact port honours the same ``SystemMemorySettings`` override the memory
    backend does; if that helper is not importable it falls back to the env-only
    :func:`persistence.qdrant_config.resolve_qdrant_config`. Imported lazily on
    purpose: ``memory`` must never be a module-level dependency of the port.
    """
    try:
        from memory.qdrant_backend import (  # lazy: DB-override resolver
            resolve_effective_qdrant_config,
        )
    except ImportError:
        from persistence.qdrant_config import resolve_qdrant_config  # lazy: config seam

        return resolve_qdrant_config()
    return resolve_effective_qdrant_config()


def _qdrant_selected() -> bool:
    """Whether the Qdrant adapter should serve the artifact port.

    All four conditions must hold (ADR-020 §4); anything else degrades to
    pgvector:

    1. ``ARTIFACT_VECTOR_BACKEND=qdrant`` -- the explicit opt-in. The Qdrant
       artifact port is never selected as a side effect of ``MEMORY_BACKEND``
       or ``QDRANT_BASE_URL`` alone.
    2. The effective memory backend is ``qdrant`` (DB override over env).
    3. The optional ``qdrant_client`` package is importable.
    4. An effective Qdrant base URL is configured (DB override over env).
    """
    if _artifact_vector_backend() != _QDRANT_ARTIFACT_BACKEND:
        return False
    if not _qdrant_client_available():
        return False
    if _effective_memory_backend_name() != _QDRANT_ARTIFACT_BACKEND:
        return False
    try:
        config = _effective_qdrant_config()
    except Exception:  # noqa: BLE001 - config problems degrade to pgvector
        return False
    return bool(getattr(config, "base_url", "").strip())


__all__ = [
    "ARTIFACT_VECTOR_BACKEND_ENV",
    "COLLECTION_ICD",
    "COLLECTION_REQUIREMENT",
    "COLLECTION_TRACE_LINK",
    "DEFAULT_ARTIFACT_VECTOR_BACKEND",
    "PgVectorBackendUnavailableError",
    "PgVectorVectorPort",
    "QdrantBackendUnavailableError",
    "QdrantVectorPort",
    "VectorBackendUnavailableError",
    "VectorHit",
    "VectorPort",
    "get_vector_port",
]
