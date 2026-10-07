"""Optional external vector backend for memory (``MEMORY_BACKEND=qdrant``).

ADR-020 V1. Like :mod:`memory.honcho_backend`, this is an *optional* second
operating mode: the default stays ``pgvector`` and the whole system keeps
working WITHOUT Qdrant. The module is imported unconditionally from
:meth:`memory.apps.MemoryConfig.ready` for its ``@register_memory_backend``
side effect, but the ``qdrant_client`` package is imported LAZILY, only inside
:meth:`QdrantMemoryBackend._ensure_client` -- so a deployment that never selects
this backend never needs the package installed, and an absent package degrades
instead of crashing.

Canonical source of truth stays Postgres
----------------------------------------
``mem_memory_entry`` (FORCE RLS) is the source of truth; Qdrant is *only* a
vector index. Every :meth:`write` first persists the canonical mirror row under
:func:`memory.backends._tenant_context` -- exactly like the Honcho backend --
and THEN upserts the vector, with the point id equal to ``str(MemoryEntry.id)``.
``list_entries``/``count``/``digest`` therefore read the local mirror with no
network call at all. ``backend_ref`` carries ``str(entry_id)`` once the point has
been written, so a failed index is visible to ``memory_reconcile``.

Isolation is application-enforced (ADR-020 §5)
----------------------------------------------
Qdrant has no Postgres RLS. Tenant/workspace isolation rests entirely on the
collection name, which is always produced by
:func:`persistence.qdrant_config.build_collection_name` (the security boundary)
and never accepted from a caller. Every operation addresses exactly ONE
collection, and each query additionally filters by ``scope`` + ``scope_id`` +
``tenant_id`` payload fields, so even the shared ``_artifacts`` collection can
never leak across artifacts.

No auto-fallback (ADR-020 §4)
-----------------------------
A configured-but-unreachable Qdrant is reported as ``degraded`` by
:meth:`health`; it is never silently replaced by pgvector. Reads fail open
(return ``[]``) and writes still land in the canonical mirror, but the health
signal stays honest so the outage is visible.
"""
from __future__ import annotations

import importlib.util
import logging
from collections.abc import Iterator
from typing import Any, List, Optional, Tuple
from uuid import UUID

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from llm_adapter.embedding_service import generate_embedding
from memory.backends import (
    _DIGEST_MAX_FACTS,
    MemoryAnswer,
    MemoryBackend,
    MemoryDigest,
    MemoryEntryId,
    MemoryEntryRef,
    MemoryHealth,
    _digest_text,
    _maybe_uuid,
    _ref_from_entry,
    _render_digest_facts,
    _scope_filter,
    _tenant_context,
    register_memory_backend,
)
from memory.models import MemoryEntry
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.qdrant_config import (
    QDRANT_DISTANCE_ATTRS,
    QdrantConfig,
    build_collection_name,
    resolve_qdrant_config,
)

logger = logging.getLogger(__name__)

#: Distance-name -> qdrant-client ``models.Distance`` attribute. Sourced from
#: :data:`persistence.qdrant_config.QDRANT_DISTANCE_ATTRS` (the SSOT) so the
#: memory write serializer and this backend can never disagree on the accepted
#: vocabulary. Unknown values fall back to cosine (the project default) rather
#: than raising: a typo in an optional knob must not take the backend down.
_DISTANCE_ATTRS = QDRANT_DISTANCE_ATTRS

#: Payload keys every Qdrant point carries. ``entry_id`` is the canonical
#: ``MemoryEntry.id``; the other three make the point self-describing for the
#: scope filter and for reconciliation.
_PAYLOAD_ENTRY_ID = "entry_id"
_PAYLOAD_SCOPE = "scope"
_PAYLOAD_SCOPE_ID = "scope_id"
_PAYLOAD_TENANT_ID = "tenant_id"

#: Page size used by :meth:`QdrantMemoryBackend.iter_scope_points` (the READ-ONLY
#: reconciliation scan). Bounded so the report cannot enumerate an unbounded
#: collection into memory.
_ORPHAN_SCAN_PAGE_SIZE = 1000


def _qdrant_client_available() -> bool:
    """Whether the optional ``qdrant_client`` package is importable.

    Uses :func:`importlib.util.find_spec`, which locates the package WITHOUT
    importing it -- so the health probe can honestly report "backend not
    usable, package missing" without making ``qdrant_client`` a hard dependency.
    """
    try:
        return importlib.util.find_spec("qdrant_client") is not None
    except (ImportError, ValueError):
        return False


def assert_collection_dimension(actual: Optional[int], expected: int) -> None:
    """Fail loud when an existing Qdrant collection's width drifts.

    The configured width ALWAYS mirrors
    :data:`persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`
    (ADR-020 §6). A Qdrant collection built with a different width would accept
    the upsert and then return meaningless similarity results, so a drift is a
    configuration error, not a warning. ``actual is None`` (the width could not
    be read) is tolerated -- failing a live deployment because the client could
    not introspect the collection would be worse than proceeding.

    Raises:
        ImproperlyConfigured: When a readable ``actual`` differs from ``expected``.
    """
    if actual is not None and actual != expected:
        raise ImproperlyConfigured(
            f"Qdrant collection vector width {actual} != "
            f"EMBEDDING_VECTOR_DIMENSIONS {expected}. Recreate the collection or "
            f"align the embedding provider; there is deliberately no "
            f"QDRANT_VECTOR_DIMENSIONS override (ADR-020 §6)."
        )


def _collection_dimension(info: Any) -> Optional[int]:
    """Extract a collection's vector width from a qdrant ``CollectionInfo``.

    Tolerates both the unnamed-vector shape (``params.vectors.size``) and the
    named-vector dict shape. Returns ``None`` when the width cannot be read, so
    :func:`assert_collection_dimension` can treat that as "unknown, proceed".
    """
    try:
        vectors = info.config.params.vectors
    except AttributeError:
        return None
    size = getattr(vectors, "size", None)
    if size is not None:
        return int(size)
    if isinstance(vectors, dict):
        sizes = {int(v.size) for v in vectors.values() if getattr(v, "size", None) is not None}
        if len(sizes) == 1:
            return sizes.pop()
    return None


def _safe_generate_embedding(text: str) -> Optional[List[float]]:
    """Best-effort local embedding; ``None`` on any provider failure.

    A missing embedding provider must never fail a memory write (the canonical
    row is still persisted), so every error degrades to ``None``.
    """
    try:
        return generate_embedding(text)
    except Exception:  # noqa: BLE001 - best-effort, see docstring
        return None


def _distance_from_score(score: Any) -> Optional[float]:
    """Map a Qdrant similarity score to the project's cosine-distance convention.

    Qdrant's ``score`` is a similarity (higher = closer) for cosine, while
    :class:`memory.backends.MemoryEntryRef.distance` follows pgvector's cosine
    distance (lower = closer). ``1 - score`` is therefore the same scale the
    pgvector backend reports under the default metric; ``None`` when the client
    returned no score.
    """
    if score is None:
        return None
    try:
        return 1.0 - float(score)
    except (TypeError, ValueError):
        return None


def resolve_effective_qdrant_config() -> QdrantConfig:
    """The Qdrant connection the backend actually uses.

    Overlays the ``SystemMemorySettings`` ``qdrant_*`` fields onto the
    ``QDRANT_*`` env defaults -- a non-``None`` DB field WINS over the env value
    (ADR-020 §6). Best-effort and non-raising for a missing DB row or an
    unavailable DB: the env defaults are the fallback, mirroring
    :meth:`memory.honcho_backend.HonchoMemoryBackend._resolve_config`.

    This is the frozen cross-agent interface for "which Qdrant does the backend
    talk to" -- the one place that resolves DB override over env.
    """
    overrides: dict[str, Any] = {}
    try:
        from memory.models import SystemMemorySettings

        row = SystemMemorySettings.objects.first()
        if row is not None:
            for field, value in (
                ("base_url", row.qdrant_base_url),
                ("api_key", row.qdrant_api_key or None),
                ("collection_prefix", row.qdrant_collection_prefix),
                ("distance", row.qdrant_distance),
                ("timeout", row.qdrant_timeout),
                ("hnsw_m", row.qdrant_hnsw_m),
                ("hnsw_ef_construct", row.qdrant_hnsw_ef_construct),
                ("prefer_grpc", row.qdrant_prefer_grpc),
            ):
                if value is not None:
                    overrides[field] = value
    except Exception:  # noqa: BLE001 - settings are best-effort; env is the fallback.
        overrides = {}
    return resolve_qdrant_config(**overrides)


@register_memory_backend("qdrant")
class QdrantMemoryBackend(MemoryBackend):
    """Memory backend indexing vectors in an external Qdrant service.

    See the module docstring for the source-of-truth, isolation and
    no-auto-fallback contracts.
    """

    #: Qdrant has no generative/dialectic surface: :meth:`ask` degrades by design.
    ask_available = False

    #: No deriver of any kind -- every point is exactly the written vector, so
    #: :meth:`digest` answers ``unsupported`` (mirrors pgvector).
    derivation_status = "unsupported"

    def __init__(self) -> None:
        self._config: QdrantConfig = self._resolve_config()
        # Test seam: a duck-typed stand-in for the real ``QdrantClient`` set via
        # ``backend._client = fake``. When set, no ``qdrant_client`` import runs.
        self._client: Any = None
        # Test seam: a duck-typed stand-in for ``qdrant_client.models``. When
        # None, the real models are imported lazily on first use.
        self._models_module: Any = None

    # -- configuration ---------------------------------------------------

    @staticmethod
    def _resolve_config() -> QdrantConfig:
        """Resolve Qdrant config via the shared :func:`resolve_effective_qdrant_config`.

        Mirrors :meth:`memory.honcho_backend.HonchoMemoryBackend._resolve_config`
        -- best-effort (a DB read here must never crash backend construction) and
        only non-``None`` override fields win, so an unset row field keeps the
        environment value.
        """
        return resolve_effective_qdrant_config()

    def _models(self) -> Any:
        """Return the qdrant ``models`` namespace, importing it lazily."""
        if self._models_module is None:
            from qdrant_client import models  # qdrant-client; lazy, see module docstring

            self._models_module = models
        return self._models_module

    def _ensure_client(self) -> Any:
        """Return a live ``QdrantClient``, constructing it on first use."""
        if self._client is None:
            from qdrant_client import QdrantClient  # qdrant-client; lazy (see module docstring)

            self._client = QdrantClient(
                url=self._config.base_url,
                api_key=self._config.api_key,
                timeout=self._config.timeout,
                prefer_grpc=self._config.prefer_grpc,
            )
        return self._client

    # -- collection selection (security boundary) ------------------------

    def _artifact_workspace_id(self, tenant_id: UUID, artifact_id: UUID) -> Optional[UUID]:
        """Resolve the owning workspace of *artifact_id* from the local DB.

        Arms the tenant context itself (RLS): callers such as ``query``/
        ``reconcile`` may invoke collection selection outside an already-active
        request/test tenant context, and an unarmed lookup would silently hide
        the artifact row.
        """
        from persistence.models import Artifact

        try:
            with _tenant_context(tenant_id):
                return (
                    Artifact.objects.filter(id=artifact_id)
                    .values_list("workspace_id", flat=True)
                    .first()
                )
        except Exception:  # noqa: BLE001 - an unresolvable artifact cannot be indexed
            return None

    def _collection_name(self, tenant_id: UUID, scope: str, scope_id: UUID) -> str:
        """Resolve the ONE collection that owns ``(scope, scope_id)``.

        ``artifact`` memory shares its workspace's ``_artifacts`` collection, so
        it is resolved to the artifact's workspace before naming. Unknown scopes
        and missing ids raise ``ValueError`` via
        :func:`persistence.qdrant_config.build_collection_name`.
        """
        prefix = self._config.collection_prefix
        if scope == MemoryEntry.SCOPE_USER:
            return build_collection_name(prefix, tenant_id, scope="user")
        if scope == MemoryEntry.SCOPE_WORKSPACE:
            return build_collection_name(
                prefix, tenant_id, workspace_id=scope_id, scope="workspace"
            )
        if scope == MemoryEntry.SCOPE_ARTIFACT:
            workspace_id = self._artifact_workspace_id(tenant_id, scope_id)
            if workspace_id is None:
                raise ValueError(
                    f"cannot resolve a workspace for artifact-scoped qdrant collection: {scope_id}"
                )
            return build_collection_name(
                prefix, tenant_id, workspace_id=workspace_id, scope="workspace", artifacts=True
            )
        raise ValueError(f"unknown memory scope: {scope!r}")

    def _qdrant_filter(self, tenant_id: UUID, scope: str, scope_id: UUID) -> Any:
        """Build the Qdrant payload filter pinning one scope within one collection."""
        models = self._models()
        return models.Filter(
            must=[
                models.FieldCondition(
                    key=_PAYLOAD_TENANT_ID, match=models.MatchValue(value=str(tenant_id))
                ),
                models.FieldCondition(key=_PAYLOAD_SCOPE, match=models.MatchValue(value=scope)),
                models.FieldCondition(
                    key=_PAYLOAD_SCOPE_ID, match=models.MatchValue(value=str(scope_id))
                ),
            ]
        )

    def _ensure_collection(self, client: Any, name: str) -> None:
        """Create the collection if absent; enforce the dimension guard if present."""
        models = self._models()
        if not client.collection_exists(name):
            distance = getattr(
                models.Distance, _DISTANCE_ATTRS.get(self._config.distance, "COSINE")
            )
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=self._config.vector_dimensions,
                    distance=distance,
                    hnsw_config=models.HnswConfigDiff(
                        m=self._config.hnsw_m,
                        ef_construct=self._config.hnsw_ef_construct,
                    ),
                ),
            )
            return
        assert_collection_dimension(
            _collection_dimension(client.get_collection(name)), self._config.vector_dimensions
        )

    # -- canonical-store API (RFC #1002) --------------------------------

    def write(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        *,
        contributor_user_id: Optional[UUID] = None,
        source_event_id: Optional[UUID] = None,
        source_session_id: Optional[UUID] = None,
        language: str = "",
        confidence: float = 1.0,
        entity_type: str = "",
        backend_ref: Optional[str] = None,
    ) -> MemoryEntryRef:
        """Persist *content* canonically and index its vector in Qdrant.

        The canonical ``mem_memory_entry`` row is written first and is what
        ``entry_id`` returns; the Qdrant point is an ADDITIVE index. If the
        embedding provider is unavailable or Qdrant is unreachable, the row is
        still written and ``backend_ref`` stays NULL so reconciliation can flag
        it -- the outage is surfaced by :meth:`health`, never hidden.
        """
        embedding = _safe_generate_embedding(content)
        with _tenant_context(tenant_id):
            entry = MemoryEntry.objects.create(
                tenant_id=tenant_id,
                content=content,
                embedding=embedding,
                contributor_user_id=contributor_user_id,
                source_event_id=source_event_id,
                source_session_id=source_session_id,
                language=language,
                confidence=confidence,
                entity_type=entity_type,
                backend_ref=backend_ref,
                **_scope_filter(scope, scope_id),
            )
            entry_id = entry.id

        if embedding is not None and self._index_point(
            tenant_id, scope, scope_id, entry_id, embedding
        ):
            with _tenant_context(tenant_id):
                MemoryEntry.objects.filter(id=entry_id).update(backend_ref=str(entry_id))
                entry.refresh_from_db()
        return _ref_from_entry(entry)

    def _index_point(
        self, tenant_id: UUID, scope: str, scope_id: UUID, entry_id: UUID, vector: List[float]
    ) -> bool:
        """Upsert one point; fail-open (returns whether the point was written)."""
        try:
            name = self._collection_name(tenant_id, scope, scope_id)
            client = self._ensure_client()
            self._ensure_collection(client, name)
            models = self._models()
            point = models.PointStruct(
                id=str(entry_id),
                vector=[float(component) for component in vector],
                payload={
                    _PAYLOAD_ENTRY_ID: str(entry_id),
                    _PAYLOAD_SCOPE: scope,
                    _PAYLOAD_SCOPE_ID: str(scope_id),
                    _PAYLOAD_TENANT_ID: str(tenant_id),
                },
            )
            client.upsert(collection_name=name, points=[point], wait=True)
            return True
        except Exception as exc:  # noqa: BLE001 - fail-open: the canonical row is safe
            logger.warning(
                "qdrant memory index failed for tenant=%s scope=%s entry=%s (error type %s)",
                tenant_id,
                scope,
                entry_id,
                type(exc).__name__,
            )
            return False

    def list_entries(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        *,
        limit: int = 25,
        offset: int = 0,
        q: Optional[str] = None,
    ) -> Tuple[List[MemoryEntryRef], int]:
        """Page the LOCAL canonical mirror (no Qdrant call), newest first."""
        with _tenant_context(tenant_id):
            qs = MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            )
            if q:
                qs = qs.filter(content__icontains=q)
            total = qs.count()
            if limit <= 0:
                return [], total
            rows = qs.order_by("-created_at")[max(0, offset) : max(0, offset) + max(0, limit)]
            return [_ref_from_entry(e) for e in rows], total

    def count(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        with _tenant_context(tenant_id):
            return MemoryEntry.objects.filter(
                **_scope_filter(scope, scope_id), superseded_by__isnull=True
            ).count()

    def delete_entry(self, tenant_id: UUID, entry_id: MemoryEntryId) -> bool:
        """Delete the canonical row AND its Qdrant point (best-effort)."""
        removed = False
        point_id: Optional[str] = None
        scope: Optional[str] = None
        scope_id: Optional[UUID] = None
        with _tenant_context(tenant_id):
            uid = _maybe_uuid(entry_id)
            row = MemoryEntry.objects.filter(id=uid).first() if uid is not None else None
            if row is None:
                row = MemoryEntry.objects.filter(backend_ref=str(entry_id)).first()
            if row is not None:
                point_id = str(row.backend_ref or row.id)
                scope = row.scope
                scope_id = getattr(row, f"{scope}_id", None)
                row.delete()
                removed = True

        if removed and scope is not None and scope_id is not None:
            self._delete_points(tenant_id, scope, scope_id, point_ids=[point_id or str(entry_id)])
        return removed

    def delete_scope(self, tenant_id: UUID, scope: str, scope_id: UUID) -> int:
        """Delete every canonical row for the scope and its Qdrant points."""
        with _tenant_context(tenant_id):
            deleted, _ = MemoryEntry.objects.filter(**_scope_filter(scope, scope_id)).delete()
        self._delete_points(tenant_id, scope, scope_id)
        return deleted

    def _delete_points(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        *,
        point_ids: Optional[List[str]] = None,
    ) -> None:
        """Delete Qdrant points by id, or the whole scope when ``point_ids`` is None."""
        try:
            name = self._collection_name(tenant_id, scope, scope_id)
            client = self._ensure_client()
            if not client.collection_exists(name):
                return
            models = self._models()
            if point_ids is not None:
                selector = models.PointIdsList(points=[str(pid) for pid in point_ids])
            else:
                selector = models.FilterSelector(
                    filter=self._qdrant_filter(tenant_id, scope, scope_id)
                )
            client.delete(collection_name=name, points_selector=selector, wait=True)
        except Exception as exc:  # noqa: BLE001 - fail-open: the canonical row is gone
            logger.warning(
                "qdrant memory delete failed for tenant=%s scope=%s (error type %s)",
                tenant_id,
                scope,
                type(exc).__name__,
            )

    def health(self) -> MemoryHealth:
        ok, detail = self.health_check()
        return MemoryHealth(ok=ok, backend="qdrant", detail=detail, degraded=not ok)

    def health_check(self) -> tuple[bool, str]:
        """Probe Qdrant without raising and without importing ``qdrant_client``.

        A configured-but-unreachable service, a missing package or a dimension
        drift all yield ``(False, detail)`` -- never an exception and never a
        silent fallback to pgvector (ADR-020 §4).
        """
        try:
            config = self._config
            if not config.base_url:
                return False, "QDRANT_BASE_URL is not configured"
            if config.vector_dimensions != EMBEDDING_VECTOR_DIMENSIONS:
                return False, (
                    "qdrant/embedding dimension drift: "
                    f"{config.vector_dimensions} != {EMBEDDING_VECTOR_DIMENSIONS}"
                )
            if self._client is not None:
                self._client.get_collections()
                return True, "qdrant reachable"
            if not _qdrant_client_available():
                return False, "qdrant_client package is not installed"
            return self._http_health_probe(config)
        except Exception as exc:  # noqa: BLE001 - health must never raise
            return False, f"qdrant health check failed: {type(exc).__name__}"

    @staticmethod
    def _http_health_probe(config: QdrantConfig) -> tuple[bool, str]:
        """Raw REST reachability probe (no :mod:`qdrant_client` import)."""
        import requests  # noqa: PLC0415 - lazy import, matches the honcho health-probe convention

        headers = {"api-key": config.api_key} if config.api_key else {}
        try:
            response = requests.get(
                config.base_url.rstrip("/") + "/collections",
                headers=headers,
                timeout=config.timeout,
            )
        except requests.RequestException as exc:
            return False, f"qdrant unreachable: {type(exc).__name__}"
        if 200 <= response.status_code < 300:
            return True, "qdrant reachable"
        return False, f"qdrant returned HTTP {response.status_code}"

    def digest(self, tenant_id: UUID, scope: str, scope_id: UUID) -> MemoryDigest:
        """Digest the canonical mirror's newest live facts (Qdrant has no deriver)."""
        generated_at = timezone.now()
        try:
            with _tenant_context(tenant_id):
                rows = (
                    MemoryEntry.objects.filter(
                        **_scope_filter(scope, scope_id), superseded_by__isnull=True
                    )
                    .order_by("-created_at", "-id")[:_DIGEST_MAX_FACTS]
                )
                contents = [row.content for row in rows]
        except Exception:  # noqa: BLE001 - a digest must never raise
            return MemoryDigest(
                text="",
                generated_at=generated_at,
                backend="qdrant",
                degraded=True,
                derivation_status="unsupported",
            )
        return MemoryDigest(
            text=_digest_text(
                "qdrant", scope, facts=len(contents), body=_render_digest_facts(contents)
            ),
            generated_at=generated_at,
            backend="qdrant",
            degraded=False,
            derivation_status="unsupported",
        )

    def ask(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        query: str,
        *,
        reasoning_level: Optional[str] = None,
    ) -> MemoryAnswer:
        """Always degrade: Qdrant has no generative/dialectic surface."""
        return MemoryAnswer(
            text="",
            generated_at=timezone.now(),
            backend="qdrant",
            degraded=True,
            detail="no dialectic engine",
        )

    # -- legacy facade ---------------------------------------------------

    def upsert(
        self,
        tenant_id: UUID,
        scope: str,
        scope_id: UUID,
        content: str,
        source_event_id: Optional[UUID] = None,
    ) -> MemoryEntryRef:
        return self.write(tenant_id, scope, scope_id, content, source_event_id=source_event_id)

    def query(
        self, tenant_id: UUID, scope: str, scope_id: UUID, query_text: str, top_k: int = 5
    ) -> List[MemoryEntryRef]:
        """Vector search inside the scope's collection.

        Fail-open on a network/provider outage (``[]``), but a missing tenant --
        or any other collection-boundary ``ValueError`` -- is an ERROR and is
        re-raised (ADR-020 §5): a cross-tenant / no-tenant query must never be
        masked as "nothing remembered".
        """
        if not tenant_id:
            raise ValueError("qdrant memory query requires a tenant id (no tenant context)")
        try:
            query_vector = _safe_generate_embedding(query_text)
            if query_vector is None:
                return []
            name = self._collection_name(tenant_id, scope, scope_id)
            client = self._ensure_client()
            self._ensure_collection(client, name)
            hits = self._search(client, name, query_vector, scope, scope_id, tenant_id, top_k)
        except ValueError:
            # The collection boundary (ADR-020 §2/§5) -- never a silent empty result.
            raise
        except Exception as exc:  # noqa: BLE001 - fail-open on outages, never raise
            logger.warning(
                "qdrant memory query failed for tenant=%s scope=%s (error type %s)",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            return []
        return self._refs_from_hits(tenant_id, hits)

    def _search(
        self,
        client: Any,
        name: str,
        vector: List[float],
        scope: str,
        scope_id: UUID,
        tenant_id: UUID,
        top_k: int,
    ) -> List[Any]:
        """Query the collection, tolerating both the modern and legacy client API."""
        query_filter = self._qdrant_filter(tenant_id, scope, scope_id)
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=name,
                query=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
            return list(getattr(response, "points", response) or [])
        return list(
            client.search(
                collection_name=name,
                query_vector=vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        )

    @staticmethod
    def _refs_from_hits(tenant_id: UUID, hits: List[Any]) -> List[MemoryEntryRef]:
        """Map Qdrant hits back to canonical rows (the source of content)."""
        by_entry: dict[UUID, Any] = {}
        for hit in hits:
            payload = getattr(hit, "payload", None) or {}
            entry_id = _maybe_uuid(payload.get(_PAYLOAD_ENTRY_ID))
            if entry_id is not None:
                by_entry[entry_id] = hit
        if not by_entry:
            return []
        with _tenant_context(tenant_id):
            rows = {row.id: row for row in MemoryEntry.objects.filter(id__in=list(by_entry))}
        refs: List[MemoryEntryRef] = []
        for entry_id, hit in by_entry.items():
            row = rows.get(entry_id)
            if row is None:
                # Orphan point (no canonical row) -- memory_reconcile reports it.
                continue
            refs.append(
                _ref_from_entry(row, distance=_distance_from_score(getattr(hit, "score", None)))
            )
        return refs

    def list_recent(
        self, tenant_id: UUID, scope: str, scope_id: UUID, limit: int = 20
    ) -> List[MemoryEntryRef]:
        with _tenant_context(tenant_id):
            rows = (
                MemoryEntry.objects.filter(
                    **_scope_filter(scope, scope_id), superseded_by__isnull=True
                )
                .order_by("-created_at")[:limit]
            )
            return [_ref_from_entry(e) for e in rows]

    def forget(self, tenant_id: UUID, entry_id: MemoryEntryId) -> None:
        self.delete_entry(tenant_id, entry_id)

    # -- reconciliation support (READ-ONLY) ------------------------------

    def list_collection_names(self) -> list[str]:
        """Names of every Qdrant collection under the configured prefix.

        Enumerating collections lets ``memory_reconcile`` scan scopes that have
        NO surviving local rows (a scope whose rows were all deleted still has
        an orphaned collection). Deliberately NOT fail-open: a failure to list
        collections is a blind spot the caller must surface as a finding, so it
        propagates.
        """
        client = self._ensure_client()
        response = client.get_collections()
        prefix = f"{self._config.collection_prefix}_"
        candidates = [
            getattr(collection, "name", None)
            for collection in (getattr(response, "collections", None) or [])
        ]
        return sorted(
            name for name in candidates if isinstance(name, str) and name.startswith(prefix)
        )

    def iter_collection_points(self, collection_name: str) -> Iterator[dict]:
        """Stream every point payload of *collection_name*, paginating ``scroll``.

        Raises on any client error so the caller can surface an unscannable
        collection as a finding instead of silently under-reporting. Streams
        (does not accumulate) so an unbounded collection cannot exhaust memory.
        """
        client = self._ensure_client()
        if not client.collection_exists(collection_name):
            return
        yield from self._scroll_payloads(client, collection_name, None)

    def iter_scope_points(
        self, tenant_id: UUID, scope: str, scope_id: UUID
    ) -> Iterator[dict]:
        """Stream the payloads of every Qdrant point in ``scope`` (fail-open).

        Used by ``manage.py memory_reconcile`` for point-level scans. Fails open
        (logs and stops) so a reconciliation run never aborts on an unreachable
        backend; it never mutates anything. Paginates ``scroll`` via
        ``next_page_offset`` so a collection larger than one page is fully
        covered.
        """
        try:
            name = self._collection_name(tenant_id, scope, scope_id)
            client = self._ensure_client()
            if not client.collection_exists(name):
                return
            scroll_filter = self._qdrant_filter(tenant_id, scope, scope_id)
            yield from self._scroll_payloads(client, name, scroll_filter)
        except Exception as exc:  # noqa: BLE001 - reconciliation is best-effort
            logger.warning(
                "qdrant memory reconciliation scan failed for tenant=%s scope=%s (error type %s)",
                tenant_id,
                scope,
                type(exc).__name__,
            )
            return

    @staticmethod
    def _scroll_payloads(client: Any, name: str, scroll_filter: Any) -> Iterator[dict]:
        """Yield every point payload in *name*, following ``next_page_offset``.

        A single ``scroll`` call returns at most ``_ORPHAN_SCAN_PAGE_SIZE``
        points; the returned ``next_page_offset`` must be fed back in or every
        point past the first page is silently dropped. Raises on a client error.
        """
        offset: Any = None
        while True:
            records, next_offset = client.scroll(
                collection_name=name,
                scroll_filter=scroll_filter,
                limit=_ORPHAN_SCAN_PAGE_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not records:
                break
            for record in records:
                yield dict(getattr(record, "payload", None) or {})
            if next_offset is None:
                break
            offset = next_offset


__all__ = [
    "QdrantMemoryBackend",
    "assert_collection_dimension",
    "resolve_effective_qdrant_config",
]
