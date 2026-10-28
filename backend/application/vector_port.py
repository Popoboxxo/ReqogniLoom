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
  ``ARTIFACT_VECTOR_BACKEND=qdrant``, the optional ``qdrant_client`` package is
  importable, and an effective Qdrant base URL is configured. Anything else
  degrades to pgvector -- switching the artifact vector store requires an
  explicit opt-in, never a side effect of another knob. A pgvector-only
  deployment never needs the package.
* **The artifact store is decoupled from ``MEMORY_BACKEND`` (T-A2-1).**
  ``MEMORY_BACKEND`` governs the AI-memory store only; the artifact port reads
  it nowhere. An artifact Qdrant store therefore works in front of a Honcho (or
  pgvector) memory backend without a second, unrelated switch. Rollout is an
  operational gate, not a code gate: enable ``ARTIFACT_VECTOR_BACKEND=qdrant``
  on a deployment only after ``manage.py index_artifact_vectors`` has run there
  with ``failed:0`` and the index hooks are active (see ``deploy/README.md``).
* **V2 Qdrant artifact search needs a workspace scope and an artifact
  indexer.** The per-workspace collections are populated by
  :mod:`application.artifact_indexer`; without one they are empty and the
  Requirement/TraceLink/Icd paths return no hits. Readers address the ALIAS
  ``..._artifacts_live`` (T-A2-6), never a versioned collection name, so a later
  schema bump needs no reader change.
  Every similarity site now carries that scope (T-A2-8). The two legacy
  ``find_similar_trace_links``/``find_similar_icds`` entry points take it as an
  optional argument and resolve their port through
  :func:`get_similarity_vector_port`: with a scope Qdrant addresses the alias,
  without one the call degrades to pgvector with
  ``degraded_reason="no_workspace_scope"`` instead of raising.
* **Hybrid query (T-A2-6).** ``query_similar``/``query_entities`` take an
  optional ``query_text``; the Qdrant adapter fuses it with the dense leg
  (``Prefetch(using="dense")`` + ``Prefetch(using="bm25")`` over
  ``FusionQuery(fusion=RRF)``, server-side ``qdrant/bm25`` inference). The
  pgvector adapter ignores it, so a default deployment stays byte-identical.
* **Hit hydration (QR-S07).** Qdrant returns ids only. Every hit is hydrated
  through the ORM under ``TenantContext`` with a workspace filter and checked
  for READ via :class:`~application.effective_permission_service.EffectivePermissionService`;
  missing, soft-deleted, superseded-MainGoal and permission-denied hits are
  dropped. Payload fields (``workspace_id``, ``entity_type``, title) are never
  the source of truth. **A caller identity (``ctx``) is required**: the READ
  check fails closed, so a call without one yields no hits at all rather than
  unchecked ones. All four similarity sites pass their identity; T-A2-8 wired
  the last two (``find_similar_trace_links``/``find_similar_icds``).
* **Fallback (T-A2-7).** :class:`FallbackVectorPort` wraps the Qdrant adapter
  for the search path: a ``QdrantBackendUnavailableError`` degrades the request
  to pgvector and sets a request-local ``degraded``/``degraded_reason`` pair.
  ``degraded`` aggregates two facts that stay separate on the instance:
  ``serving_from_fallback`` (the actual outage -- the only thing
  :func:`serves_from_fallback` reports) and ``partial_semantics`` (a cross-type
  leg failed while Qdrant still served everything else). Precedence is
  **outage > partial**: ``_degrade()`` always writes ``qdrant_unavailable``,
  ``mark_request_degraded()`` never overwrites it.
  :func:`get_vector_port` itself still returns the bare adapter, keeping the
  three similarity call sites' loud-failure contract. Because the pgvector
  adapter cannot enforce the QR-S07 READ check (it has no ``ctx`` semantics),
  ``SearchService`` applies :func:`hydrate_vector_hits` to the hits of a
  fallback-serving port -- see :func:`serves_from_fallback`.
* ``qdrant_client`` is **never imported at module import time** -- only inside
  the Qdrant adapter's lazy helpers -- so importing this module is always safe.
* ``enable_iterative_ann_scan`` (``application.pgvector_ann``) is
  pgvector-specific. The port does not generalise it: the ``iterative_scan``
  flag carries the existing per-site inconsistency (search's three branches and
  ``find_similar_requirements`` use it; ``find_similar_trace_links`` and
  ``find_similar_icds`` do not) into one adapter-owned place instead of
  "fixing" it. The ONE exception is provenance filtering (T-A0-6): strict mode
  adds a predicate to the query, which makes the post-filter truncation the
  iterative scan exists for apply to every site, so ``query_similar`` forces it
  on whenever it had to filter by ``embedding_model`` (``warn``, the default,
  changes nothing).

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
from typing import Any, Protocol
from uuid import UUID

from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError

from application.artifact_vector_store import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME
from llm_adapter.embedding_service import (
    embedding_model_filter,
    note_foreign_embedding_models,
)
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

#: Server-side BM25 inference (T-A2-6 spike: `qdrant/qdrant:v1.19.2` computes
#: the sparse vector itself, so no ``fastembed`` is needed on the client).
_BM25_MODEL = "qdrant/bm25"

#: ``degraded_reason`` value a Qdrant outage reports (stable wire token).
DEGRADED_QDRANT_UNAVAILABLE = "qdrant_unavailable"

#: ``degraded_reason`` value :func:`get_similarity_vector_port` reports when a
#: similarity call arrives without a workspace scope (T-A2-8, stable wire token).
#: Distinct from :data:`DEGRADED_QDRANT_UNAVAILABLE` on purpose: nothing failed,
#: the caller simply supplied no scope, so pgvector serves instead.
DEGRADED_NO_WORKSPACE_SCOPE = "no_workspace_scope"

#: ``degraded_reason`` value ``SearchService`` reports when the cross-type
#: semantic leg (``query_entities``) failed for a reason the port did not
#: classify as an outage (stable wire token). Distinct from
#: :data:`DEGRADED_QDRANT_UNAVAILABLE` on purpose: the search result is
#: incomplete, but no fallback happened -- ``vector_backend`` still names the
#: backend that served the other legs.
DEGRADED_CROSS_TYPE_QUERY_FAILED = "cross_type_query_failed"

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
    adapters speak the same scale -- **which is only a cosine scale for a
    dense-only query**. With a ``query_text`` the Qdrant score is an RRF *fused*
    score, so ``distance`` is then a rank-derived quantity, NOT a cosine
    distance: it is comparable within one result list (ordering is preserved),
    but not across backends and not against a cosine threshold. Callers that
    turn it into a ``relevance_score`` (``SearchService``) inherit exactly that
    -- see :func:`_distance_from_score` and the ``/api/v1/search/`` response
    description for the consequence (``min_score`` is backend-dependent).

    ``id`` is ALWAYS the canonical row ``UUID``: the Qdrant adapter coerces the
    string payload id to ``UUID`` (``_coerce_uuid``), exactly like pgvector's
    ``row.id``, so every caller can key ORM rows by ``hit.id`` for both
    backends. A point whose id is not UUID-shaped is skipped rather than
    surfaced as an id no ORM lookup could ever resolve.
    """

    id: Any
    distance: float


@dataclass(frozen=True)
class TypedVectorHit:
    """A ``VectorHit`` that also carries the entity type and its ORM-derived row.

    Produced by :meth:`VectorPort.query_entities`, the only query that spans
    several entity types at once. ``entity_type`` is the type whose ORM lookup
    actually resolved the id (QR-S07): the payload only *routes* the lookup, it
    never proves one. ``title``/``description``/``workspace_id`` therefore come
    from that row, not from the payload.
    """

    id: Any
    entity_type: str
    distance: float
    title: str = ""
    description: str = ""
    workspace_id: UUID | None = None


class VectorPort(Protocol):
    """The vector-store surface the artifact ANN sites depend on.

    ``degraded``/``degraded_reason``/``vector_backend`` describe how THIS call
    was served (T-A2-7). The pgvector adapter is never degraded; the Qdrant
    adapter reports ``"qdrant"``; :class:`FallbackVectorPort` flips to
    ``"pgvector"`` + ``degraded_reason="qdrant_unavailable"`` for the rest of
    the request when its primary fails.
    """

    degraded: bool
    degraded_reason: str
    vector_backend: str
    #: Whether the backend can answer :meth:`query_entities` (Qdrant only).
    supports_entity_queries: bool

    def query_similar(
        self,
        *,
        collection: str,
        query_vector: Sequence[float],
        tenant_id: Any,
        workspace_id: UUID | None = None,
        workspace_field: str | None = None,
        exclude_id: Any | None = None,
        limit: int = 50,
        iterative_scan: bool = False,
        query_text: str | None = None,
        ctx: Any = None,
    ) -> list[VectorHit]:
        """Return the ``limit`` nearest rows to ``query_vector``, closest first.

        ``query_text`` is the hybrid (BM25) leg: the Qdrant adapter fuses it
        with the dense leg via prefetch + RRF, the pgvector adapter ignores it
        (its results are byte-identical with and without it).

        ``ctx`` is the caller identity the QR-S07 READ check needs. **It is a
        precondition, not an optional refinement**: adapters that hydrate (and
        :func:`hydrate_vector_hits` itself) fail closed, so a call without an
        identity returns no hits instead of unchecked ones. All four similarity
        sites (``find_similar_requirements``, ``find_similar_trace_links``,
        ``find_similar_icds`` and the search branches) pass their identity.
        """
        ...

    def query_entities(
        self,
        *,
        tenant_id: Any,
        workspace_id: UUID,
        query_vector: Sequence[float] | None,
        query_text: str | None,
        entity_types: Sequence[str],
        limit: int = 50,
        ctx: Any = None,
    ) -> list[TypedVectorHit]:
        """Semantic hits across *entity_types*, including types with no embedding column.

        Qdrant only; the pgvector adapter returns ``[]`` (its semantic data
        lives in per-type ``embedding`` columns, which a cross-type query cannot
        read).
        """
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


def _distance_from_score(score: Any) -> float | None:
    """Map a Qdrant similarity score to the port's cosine-distance convention.

    Qdrant's ``score`` is a similarity (higher = closer); the port uses
    pgvector's cosine distance (lower = closer), so the mapping is ``1 - score``.
    Tolerant by design (mirrors ``memory.qdrant_backend._distance_from_score``):
    ``None`` -- meaning "skip this point" -- for a missing or non-numeric score
    rather than letting a raw ``ValueError``/``TypeError`` escape the adapter.

    Scope of the mapping: ``score`` is a cosine similarity ONLY for a dense-only
    query. A hybrid query (``query_text`` set) returns an RRF **fused** score,
    so ``1 - score`` is then a rank-derived quantity on an opaque scale. It
    still orders the hits correctly (monotone in Qdrant's ranking) and stays
    bounded, but it is not a cosine similarity: it is not comparable to a
    pgvector distance and not comparable across deployments. Deliberately not
    "fixed" here -- re-deriving a cosine scale would require a second dense-only
    round-trip per hit and would make the two legs disagree about ranking.
    """
    if score is None:
        return None
    try:
        return 1.0 - float(score)
    except (TypeError, ValueError):
        return None


def _coerce_uuid(value: Any) -> UUID | None:
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


# ---------------------------------------------------------------------------
# QR-S07 — hit hydration (Qdrant returns ids; the ORM row is the truth)
# ---------------------------------------------------------------------------

#: ``entity_type`` -> the ORM path that carries its workspace. Everything the
#: artifact indexer writes resolves through ``workspace_id`` (a UUID column, or
#: the attname of a ``workspace`` FK) except ``TraceLink``, whose own workspace
#: *is* its source's (mirrors ``ArtifactIndexer``'s resolver).
_HYDRATION_WORKSPACE_FIELDS: dict[str, str] = {
    "TraceLink": "source__workspace_id",
}


def _read_target_id(entity_type: str, row: Any) -> UUID | None:
    """The artifact id the item-permission layer is asked about for *row*."""
    artifact_id = getattr(row, "artifact_id", None)
    if artifact_id is None and entity_type == "TraceLink":
        # A link has no backing artifact of its own; its SOURCE is the artifact
        # whose visibility governs the link (same rule as T-A3-3's filter).
        artifact_id = getattr(row, "source_id", None)
    return artifact_id


def _workspace_of_row(entity_type: str, row: Any) -> Any:
    """The row's own workspace (never the payload's), via the indexer's resolver."""
    from application.artifact_indexer import SOURCES  # lazy: registry

    spec = SOURCES.get(entity_type)
    return spec.workspace(row) if spec is not None else getattr(row, "workspace_id", None)


def _current_main_goal_ids(rows: dict[UUID, Any]) -> set[UUID]:
    """Ids of the CURRENT (highest ``sequence_number``) MainGoal versions.

    A superseded version emits no ``*_DELETED`` event, so its point stays in the
    collection and its row stays in the table (PR-A19 review finding). It must
    never be presented as a current hit, so "current" is resolved per workspace
    exactly like ``MainGoalService`` does.
    """
    from django.db.models import Max

    from persistence.models import MainGoal  # lazy: import-light

    latest = {
        entry["workspace_id"]: entry["latest"]
        for entry in MainGoal.objects.filter(
            workspace_id__in={row.workspace_id for row in rows.values()}
        )
        .values("workspace_id")
        .annotate(latest=Max("sequence_number"))
    }
    return {
        row.pk
        for row in rows.values()
        if latest.get(row.workspace_id) == row.sequence_number
    }


def _read_allowed(
    ctx: Any,
    workspace_id: Any,
    artifact_id: Any,
    roles_cache: dict[str, tuple[str, ...]],
    decision_cache: dict[tuple[str, str | None], bool],
) -> bool:
    """QR-S07 READ decision — the ONE implementation lives in ``search_service``.

    Delegating instead of re-implementing keeps the QR-S07 (port hydration) and
    T-A3-3 (SQL hit visibility) gates from drifting: workspace fence, per
    workspace roles and the item-level rule must agree, and two copies of that
    merge inevitably would not.
    """
    from application.search_service import _may_read_artifact

    return _may_read_artifact(ctx, workspace_id, artifact_id, roles_cache, decision_cache)


def _hydrate_rows(
    entity_type: str,
    ids: Sequence[Any],
    tenant_id: Any,
    workspace_id: UUID | None,
    ctx: Any,
) -> dict[UUID, Any]:
    """Resolve *ids* to ORM rows that may be presented for this tenant/workspace.

    Every step is a fence, not a lookup: the row must exist in the ambient
    tenant, in the requested workspace, not be soft-deleted, be the current
    version (MainGoal) and be READ-allowed for the caller. A payload that claims
    another workspace cannot survive the workspace filter, which is exactly why
    the payload is never trusted.

    ``ctx`` is required, not optional: without a caller identity there is no
    provable READ, so every id is dropped (:func:`_read_allowed` returns
    ``False`` for ``ctx is None``). This is the fail-closed contract the QR-S07
    gate is documented with -- a caller that cannot supply an identity gets an
    empty result, never an unchecked one.
    """
    from application.artifact_indexer import SOURCES, tenant_scope  # lazy: registry
    from persistence.models import Artifact, LifecycleStatus  # lazy: import-light

    spec = SOURCES.get(entity_type)
    if spec is None:
        return {}
    workspace_field = _HYDRATION_WORKSPACE_FIELDS.get(entity_type, "workspace_id")
    with tenant_scope(tenant_id):
        query = spec.model()._default_manager.filter(
            pk__in=list(ids), tenant_id=tenant_id
        )
        if workspace_id is not None:
            query = query.filter(**{workspace_field: workspace_id})
        if spec.select_related:
            query = query.select_related(*spec.select_related)
        rows = {row.pk: row for row in query}
        if not rows:
            return {}
        targets = {
            target
            for target in (_read_target_id(entity_type, row) for row in rows.values())
            if target is not None
        }
        outdated = set(
            Artifact.objects.filter(
                id__in=targets, lifecycle_status=LifecycleStatus.OUTDATED
            ).values_list("id", flat=True)
        )
        current_main_goals = (
            _current_main_goal_ids(rows) if entity_type == "MainGoal" else None
        )
        roles_cache: dict[str, tuple[str, ...]] = {}
        decision_cache: dict[tuple[str, str | None], bool] = {}
        visible: dict[UUID, Any] = {}
        for row_id, row in rows.items():
            target = _read_target_id(entity_type, row)
            if current_main_goals is not None and row_id not in current_main_goals:
                continue
            if target is not None and target in outdated:
                continue
            row_workspace = _workspace_of_row(entity_type, row)
            # Workspace fence on the ROW's own workspace: the payload's claim
            # must never be the reason a row from another workspace survives.
            if workspace_id is not None and str(row_workspace) != str(workspace_id):
                continue
            # Unconditional on purpose (QR-S07): the READ decision is not an
            # opt-in refinement of the fence. No identity -> no provable READ
            # -> the hit is dropped.
            if not _read_allowed(
                ctx, row_workspace, target, roles_cache, decision_cache
            ):
                continue
            visible[row_id] = row
        return visible


def hydrate_vector_hits(
    *,
    collection: str,
    hits: Sequence[VectorHit],
    tenant_id: Any,
    workspace_id: UUID | None = None,
    ctx: Any = None,
) -> list[VectorHit]:
    """Keep only the hits whose ORM row is present and READable (QR-S07).

    Fail closed: with no ``ctx`` there is no caller identity to check a READ
    against, so nothing is returned. Used by the Qdrant adapter and by
    ``SearchService`` for the hits of a DEGRADED fallback port (whose pgvector
    adapter cannot check permissions itself).
    """
    if not hits:
        return []
    rows = _hydrate_rows(collection, [hit.id for hit in hits], tenant_id, workspace_id, ctx)
    return [hit for hit in hits if hit.id in rows]


def _row_text(row: Any) -> tuple[str, str]:
    """(title, description) from the ORM row, across the indexed entity shapes."""
    title = next(
        (
            str(getattr(row, attribute))[:200]
            for attribute in ("title", "term", "name", "content")
            if getattr(row, attribute, None)
        ),
        "",
    )
    description = next(
        (
            str(getattr(row, attribute))
            for attribute in ("description", "semantic_description", "content")
            if getattr(row, attribute, None)
        ),
        "",
    )
    return title, description


class PgVectorVectorPort:
    """Default/fallback adapter: pgvector cosine ANN over the ORM.

    Byte-for-byte the queries the four sites used to build themselves --
    ``tenant_id`` + ``embedding__isnull=False`` always, an optional workspace
    filter, ``exclude_id``, ``order_by("distance")[:limit]`` and (only when
    asked) an ``atomic()`` savepoint around ``enable_iterative_ann_scan``.
    """

    degraded = False
    degraded_reason = ""
    vector_backend = DEFAULT_ARTIFACT_VECTOR_BACKEND
    supports_entity_queries = False

    def query_similar(
        self,
        *,
        collection: str,
        query_vector: Sequence[float],
        tenant_id: Any,
        workspace_id: UUID | None = None,
        workspace_field: str | None = None,
        exclude_id: Any | None = None,
        limit: int = 50,
        iterative_scan: bool = False,
        query_text: str | None = None,
        ctx: Any = None,
    ) -> list[VectorHit]:
        # ``query_text``/``ctx`` are accepted and deliberately IGNORED: pgvector
        # has no BM25 leg (that lives in SearchService for pgvector, A3) and the
        # rows already come from the ORM under the caller's tenant context, so
        # the results stay byte-identical with and without a query text. ``ctx``
        # is NOT used for a READ check here (that would change the default
        # path); a caller that serves these hits to a user -- SearchService on
        # the degraded-fallback path -- applies the QR-S07 gate itself via
        # :func:`hydrate_vector_hits`.
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
        # T-A0-6 read comparison (#1317, ADR-024 O3). A model change that keeps
        # the same vector width is invisible to a cosine query, so rows carry
        # their provenance: strict mode drops rows written by another model,
        # warn mode (default) leaves the result set byte-identical and samples
        # the drift once per process. Legacy rows (embedding_model IS NULL) stay
        # visible in BOTH modes.
        model_filter = embedding_model_filter()
        if model_filter is None:
            note_foreign_embedding_models(
                qs, site=f"PgVectorVectorPort.query_similar[{collection}]"
            )
        else:
            qs = qs.filter(model_filter)
        qs = (
            qs.annotate(distance=CosineDistance("embedding", query_vector))
            .order_by("distance")[:limit]
        )

        # T-A0-6: strict mode adds a provenance predicate the HNSW index cannot
        # satisfy, i.e. another post-filter — with ``hnsw.iterative_scan = off``
        # (the default) the index yields ``ef_search`` candidates, strict mode
        # can drop every one of them and the caller then gets FEWER than
        # ``limit`` rows (or none) although matching rows exist. The iterative
        # scan is the existing hardening for exactly that shape (#977/#978,
        # already used by the search branches), so it is forced on whenever this
        # call filters by provenance. Warn mode adds no predicate, so the
        # caller's flag keeps its historical meaning there.
        rows = self._evaluate(
            qs, iterative_scan=iterative_scan or model_filter is not None
        )
        return [VectorHit(id=row.id, distance=float(row.distance)) for row in rows]

    def query_entities(
        self,
        *,
        tenant_id: Any,
        workspace_id: UUID,
        query_vector: Sequence[float] | None,
        query_text: str | None,
        entity_types: Sequence[str],
        limit: int = 50,
        ctx: Any = None,
    ) -> list[TypedVectorHit]:
        """Always ``[]``: pgvector has no cross-type semantic index.

        Its semantic data is the per-type ``embedding`` column, which only the
        per-type branches (and the A3 hybrid search) can read. Returning an
        empty list keeps the default deployment byte-identical: ``SearchService``
        calls this unconditionally and simply gets no extra hits.
        """
        return []

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

    degraded = False
    degraded_reason = ""
    vector_backend = _QDRANT_ARTIFACT_BACKEND
    supports_entity_queries = True

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

    def _collection_name(self, tenant_id: Any, workspace_id: UUID | None) -> str:
        from persistence.qdrant_config import build_collection_alias  # lazy: boundary

        if workspace_id is None:
            # Strategy A has exactly one artifact collection per workspace, so
            # there is no collection this query could name. Fail loud (mapped to
            # the caller's PgVectorUnavailable-equivalent) rather than scanning
            # every workspace collection. The similarity call sites avoid this
            # by resolving their port through ``get_similarity_vector_port``.
            raise QdrantBackendUnavailableError(
                "qdrant artifact search requires a workspace scope"
            )
        # Readers address the ALIAS from T-A2-6 on (never the versioned name), so
        # a later schema bump (``..._artifacts_v3``) needs no reader change.
        return build_collection_alias(
            self._config.collection_prefix,
            tenant_id,
            workspace_id=workspace_id,
            scope="workspace",
        )

    def _build_filter(
        self,
        collection: str,
        tenant_id: Any,
        workspace_id: UUID | None,
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
        workspace_id: UUID | None = None,
        workspace_field: str | None = None,
        exclude_id: Any | None = None,
        limit: int = 50,
        iterative_scan: bool = False,
        query_text: str | None = None,
        ctx: Any = None,
    ) -> list[VectorHit]:
        """Hybrid (dense + BM25 via RRF) query against the workspace alias.

        Every returned id is then hydrated through the ORM (QR-S07): a point
        whose row is missing, soft-deleted, superseded (MainGoal) or not
        READ-allowed for *ctx* is dropped, so the payload can never smuggle a
        foreign or deleted artifact into the result set.
        """
        name = self._collection_name(tenant_id, workspace_id)
        query_filter = self._build_filter(collection, tenant_id, workspace_id, exclude_id)
        points = self._query_points(
            name=name,
            query_filter=query_filter,
            limit=limit,
            query_vector=query_vector,
            query_text=query_text,
        )
        return hydrate_vector_hits(
            collection=collection,
            hits=self._hits_from_points(points),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            ctx=ctx,
        )

    def query_entities(
        self,
        *,
        tenant_id: Any,
        workspace_id: UUID,
        query_vector: Sequence[float] | None,
        query_text: str | None,
        entity_types: Sequence[str],
        limit: int = 50,
        ctx: Any = None,
    ) -> list[TypedVectorHit]:
        """Hybrid semantic hits across *entity_types* (T-A2-6).

        This is the only pass that can reach the entity types WITHOUT an
        ``embedding`` column (StakeholderNeed, Adr, Risk, ...) — the
        counter-check to A-L19. Hydration (QR-S07) is per entity type, so the
        payload's ``entity_type`` only *routes* the ORM lookup; a point whose id
        does not resolve in that type's table is dropped, and title/description
        always come from the resolved row.
        """
        if not entity_types or workspace_id is None:
            return []
        models = self._models()
        name = self._collection_name(tenant_id, workspace_id)
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key=_PAYLOAD_TENANT_ID, match=models.MatchValue(value=str(tenant_id))
                ),
                models.FieldCondition(
                    key=_PAYLOAD_WORKSPACE_ID, match=models.MatchValue(value=str(workspace_id))
                ),
                models.FieldCondition(
                    key=_PAYLOAD_ENTITY_TYPE,
                    match=models.MatchAny(any=sorted(set(entity_types))),
                ),
            ]
        )
        points = self._query_points(
            name=name,
            query_filter=query_filter,
            limit=limit,
            query_vector=query_vector,
            query_text=query_text,
        )

        allowed = set(entity_types)
        grouped: dict[str, list[TypedVectorHit]] = {}
        for point in points:
            distance = _distance_from_score(getattr(point, "score", None))
            payload = getattr(point, "payload", None) or {}
            entity_type = payload.get(_PAYLOAD_ENTITY_TYPE)
            entity_id = _coerce_uuid(
                payload.get(_PAYLOAD_ENTITY_ID, getattr(point, "id", None))
            )
            if distance is None or entity_type not in allowed or entity_id is None:
                continue
            grouped.setdefault(str(entity_type), []).append(
                TypedVectorHit(id=entity_id, entity_type=str(entity_type), distance=distance)
            )

        visible: list[TypedVectorHit] = []
        for entity_type, group in grouped.items():
            rows = _hydrate_rows(
                entity_type, [hit.id for hit in group], tenant_id, workspace_id, ctx
            )
            for hit in group:
                row = rows.get(hit.id)
                if row is None:
                    continue
                title, description = _row_text(row)
                visible.append(
                    TypedVectorHit(
                        id=hit.id,
                        entity_type=entity_type,
                        distance=hit.distance,
                        title=title,
                        description=description,
                        workspace_id=_workspace_of_row(entity_type, row),
                    )
                )
        return sorted(visible, key=lambda hit: hit.distance)

    def _query_points(
        self,
        *,
        name: str,
        query_filter: Any,
        limit: int,
        query_vector: Sequence[float] | None,
        query_text: str | None,
    ) -> list[Any]:
        """Run one dense or hybrid query and return the raw points.

        With a ``query_text`` this is the plan's hybrid shape:
        ``prefetch=[Prefetch(using="dense"), Prefetch(using="bm25")]`` with
        ``query=FusionQuery(fusion=RRF)``. Without it the query stays the plain
        dense vector (unchanged pre-T-A2-6 behaviour).
        """
        models = self._models()
        dense = [float(component) for component in query_vector] if query_vector else None
        text = (query_text or "").strip()
        prefetch: list[Any] | None = None
        query: Any = dense
        if text:
            prefetch = [
                models.Prefetch(query=leg, using=name_, limit=limit)
                for leg, name_ in (
                    (dense, DENSE_VECTOR_NAME),
                    (models.Document(text=text, model=_BM25_MODEL), SPARSE_VECTOR_NAME),
                )
                if leg is not None
            ]
            query = models.FusionQuery(fusion=models.Fusion.RRF)
        if query is None:
            return []

        client = self._ensure_client()
        try:
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=name,
                    query=query,
                    prefetch=prefetch,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True,
                )
                return list(getattr(response, "points", response) or [])
            if prefetch is not None:
                # The legacy ``search`` API cannot express a prefetch/fusion
                # query; a client that old cannot serve hybrid search.
                raise QdrantBackendUnavailableError("qdrant_client is too old for hybrid search")
            return list(
                client.search(
                    collection_name=name,
                    query_vector=query,
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


class FallbackVectorPort:
    """Qdrant primary with a pgvector fallback and a request-local degraded flag.

    T-A2-7. ``get_vector_port()`` still returns the bare adapter (the three
    similarity call sites keep their loud-failure contract); the SEARCH path
    wraps the Qdrant adapter in this one instead, so a Qdrant outage costs the
    semantic hits of the eleven embedding-less types -- documented -- rather
    than the whole search request, and the caller can say so.

    Two DIFFERENT facts are tracked separately, because they answer different
    questions (one flag for both made ``SearchService`` re-hydrate the hits of a
    healthy Qdrant primary after an unrelated cross-type failure):

    * ``serving_from_fallback`` -- this request is being served by the pgvector
      fallback because Qdrant is unavailable. Only :meth:`_degrade` sets it.
      :func:`serves_from_fallback` reads exactly this, and it is the signal that
      makes ``SearchService`` apply the QR-S07 gate.
    * ``partial_semantics`` -- the cross-type semantic leg failed; Qdrant still
      served every other leg. Set by :func:`mark_request_degraded`.
    * ``degraded`` -- the aggregate the wire reports (``True`` when either of the
      two holds), together with ``degraded_reason``/``vector_backend``.

    Precedence is **outage > partial**: an outage is the stronger claim (nothing
    came from Qdrant at all) and it is written unconditionally by
    :meth:`_degrade`, while a later :func:`mark_request_degraded` never
    overwrites a recorded outage.

    The flag is request-local by construction: an instance is built per call
    (``get_vector_port()`` already constructs a fresh adapter per call), so two
    concurrent requests never see each other's degradation and nothing is
    cached across a recovery. No module-level state.

    What the FALLBACK path enforces, exactly (it is not the Qdrant path's
    gate): ``PgVectorVectorPort`` applies the tenant filter, the optional
    workspace filter, ``embedding__isnull=False``, ``exclude_id`` and the
    embedding-provenance filter (T-A0-6) -- all in SQL. It does **not** apply
    the QR-S07 gate: it ignores ``ctx`` entirely, so it neither checks
    item-level READ nor excludes ``OUTDATED``/superseded rows. Those two are
    therefore applied by the caller: ``SearchService`` routes the hits of a
    fallback-serving port through :func:`hydrate_vector_hits`. A caller that
    uses this wrapper outside ``SearchService`` gets the raw pgvector set and
    must apply the same gate itself.

    ``query_entities`` has no pgvector equivalent at all: an outage degrades it
    to ``[]`` (the eleven embedding-less types simply contribute no semantic
    hits), it never falls back to another data source.
    """

    supports_entity_queries = True

    def __init__(
        self, primary: VectorPort, fallback: VectorPort | None = None
    ) -> None:
        self._primary = primary
        self._fallback = fallback if fallback is not None else PgVectorVectorPort()
        #: Set only by :meth:`_degrade` -- "Qdrant is down, pgvector serves".
        self.serving_from_fallback = False
        #: Set only by :func:`mark_request_degraded` -- "a non-outage leg failed".
        self.partial_semantics = False
        self.degraded = False
        self.degraded_reason = ""
        self.vector_backend = getattr(
            primary, "vector_backend", _QDRANT_ARTIFACT_BACKEND
        )

    def _degrade(self, exc: QdrantBackendUnavailableError) -> None:
        """Switch this request to the fallback after a real Qdrant outage.

        The outage reason is written unconditionally: it SUPERSEDES a
        ``partial_semantics`` reason recorded earlier (a failing cross-type leg
        does not make a later outage less of an outage, and reporting
        ``cross_type_query_failed`` next to ``vector_backend="pgvector"`` would
        be a lie). The warning is gated on the recorded reason -- not on
        ``degraded`` -- so a cross-type failure that already flagged the request
        does not swallow the one line an operator needs; a second outage in the
        same request stays quiet.
        """
        if self.degraded_reason != DEGRADED_QDRANT_UNAVAILABLE:
            # One line per request, never the entity text or the payload.
            logger.warning(
                "Qdrant artifact backend unavailable, degrading to pgvector (%s)",
                type(exc).__name__,
            )
        self._mark_outage()

    def _mark_outage(self) -> None:
        """Record "Qdrant is unavailable, pgvector serves this request".

        Shared by :meth:`_degrade` (runtime outage) and the construction-failure
        port :func:`get_fallback_vector_port` builds (where the warning was
        already emitted with its traceback, so only the state is set).
        """
        self.serving_from_fallback = True
        self.degraded = True
        self.degraded_reason = DEGRADED_QDRANT_UNAVAILABLE
        self.vector_backend = DEFAULT_ARTIFACT_VECTOR_BACKEND

    def query_similar(self, **kwargs: Any) -> list[VectorHit]:
        """Primary first; on a Qdrant outage the pgvector leg serves the call.

        ``kwargs`` are forwarded verbatim -- this is a transparent proxy, so a
        hand-copied signature could only drift from the port contract. pgvector
        ignores ``query_text``, so the fallback call is byte-identical to the
        pre-T-A2-7 default path; ``ctx`` is forwarded but unused by pgvector --
        the caller (``SearchService``) applies the QR-S07 gate instead.
        """
        try:
            return self._primary.query_similar(**kwargs)
        except QdrantBackendUnavailableError as exc:
            self._degrade(exc)
            return self._fallback.query_similar(**kwargs)

    def query_entities(self, **kwargs: Any) -> list[TypedVectorHit]:
        """Primary first; ``[]`` on an outage (pgvector has no cross-type index)."""
        try:
            return self._primary.query_entities(**kwargs)
        except QdrantBackendUnavailableError as exc:
            self._degrade(exc)
            return []


def serves_from_fallback(port: Any) -> bool:
    """Whether *port* is a :class:`FallbackVectorPort` serving from its fallback.

    The single place that answers the question that MATTERS for the gate: "is
    this request's data coming from pgvector because Qdrant is unavailable?".
    ``SearchService`` uses it to decide whether the QR-S07 gate still has to be
    applied to the returned hits: the Qdrant adapter hydrates its own hits, but
    the pgvector adapter the wrapper falls back to does not (it ignores
    ``ctx``).

    Deliberately reads ``serving_from_fallback`` and not ``degraded``: after a
    cross-type failure a HEALTHY Qdrant wrapper also reports ``degraded=True``,
    and gating on that made every later per-type semantic leg re-hydrate hits
    the Qdrant adapter had already hydrated (one extra ORM lookup plus
    permission resolution per embeddable type per workspace).

    For a plain :class:`PgVectorVectorPort` -- the default deployment, which is
    never wrapped -- this is ``False``, so the default path keeps taking no gate
    at all and stays byte-identical.
    """
    return isinstance(port, FallbackVectorPort) and bool(
        getattr(port, "serving_from_fallback", False)
    )


def mark_request_degraded(port: Any, reason: str) -> None:
    """Flag *port* as serving PARTIAL semantics for the rest of the request.

    For failures the port itself cannot classify (e.g. a cross-type semantic
    query that raised something other than
    :class:`QdrantBackendUnavailableError`): the request served partial semantic
    results and must say so instead of looking complete.

    This records ``partial_semantics`` -- NOT ``serving_from_fallback``: Qdrant
    is healthy and served every other leg, so the hits it returned are already
    hydrated and must not be gated a second time.

    Precedence (see :class:`FallbackVectorPort`): **outage > partial**. A
    recorded ``qdrant_unavailable`` is never overwritten -- re-labelling an
    outage as ``cross_type_query_failed`` would contradict
    ``vector_backend="pgvector"`` -- while :meth:`FallbackVectorPort._degrade`
    always overwrites a partial reason, because an outage is the stronger
    claim. Among partial reasons the first one wins (it is the causal one).

    Best-effort by design -- a read-only port double must never turn a degraded
    search into a failed one, so an ``AttributeError`` is swallowed.
    """
    if port is None:
        return
    if getattr(port, "degraded_reason", "") == DEGRADED_QDRANT_UNAVAILABLE:
        return
    if getattr(port, "degraded", False) and getattr(port, "degraded_reason", ""):
        return
    try:
        port.degraded = True
        port.degraded_reason = reason
        port.partial_semantics = True
    except AttributeError:  # frozen/immutable port double -- never fail search
        logger.debug("vector port does not accept a degraded flag", exc_info=True)


def _construct_qdrant_port() -> tuple[QdrantVectorPort | None, Exception | None]:
    """Build the Qdrant adapter when it is selected, else report why not.

    Returns ``(port, None)`` when the adapter was built, ``(None, exc)`` when
    Qdrant was selected but construction failed, and ``(None, None)`` when
    Qdrant was not selected at all. Keeping the two failure modes apart is what
    lets :func:`get_fallback_vector_port` distinguish "pgvector was requested"
    (not degraded) from "Qdrant was requested but could not be built" (an
    outage: pgvector serves, so the request is degraded).
    """
    if not _qdrant_selected():
        return None, None
    try:
        return QdrantVectorPort(), None
    except Exception as exc:  # optional backend must never break search
        logger.warning(
            "Qdrant is configured but the vector port could not be built; "
            "falling back to pgvector",
            exc_info=True,
        )
        return None, exc


def get_fallback_vector_port() -> VectorPort:
    """The search-facing port: Qdrant (with pgvector fallback) if opted in.

    Returns the plain pgvector adapter -- byte-identical to
    :func:`get_vector_port` -- when Qdrant is not selected, so the default
    deployment sees ``degraded=False``, ``vector_backend="pgvector"`` and the
    exact same hits as before.

    When Qdrant IS selected but its adapter cannot be constructed, this returns
    a :class:`FallbackVectorPort` that already reports
    ``degraded=True``/``degraded_reason="qdrant_unavailable"`` and
    ``vector_backend="pgvector"`` -- the same state a runtime outage produces
    (Qdrant intended, pgvector serving), so ``SearchService`` applies the QR-S07
    gate to the pgvector hits. Returning a BARE ``PgVectorVectorPort`` here --
    as an earlier version did -- reported ``degraded=False`` and served ungated
    rows: exactly the hole the fallback gate closes elsewhere.
    """
    port, construction_error = _construct_qdrant_port()
    if port is not None:
        return FallbackVectorPort(port)
    if construction_error is not None:
        # Already logged with the traceback above; only the state is set, so the
        # request reports the same outage an unreachable Qdrant would.
        degraded = FallbackVectorPort(PgVectorVectorPort())
        degraded._mark_outage()
        return degraded
    return PgVectorVectorPort()


def get_vector_port() -> VectorPort:
    """Return the active vector port: pgvector by default, Qdrant if opted in.

    Qdrant is selected ONLY when every gate condition holds (see
    :func:`_qdrant_selected`): the explicit ``ARTIFACT_VECTOR_BACKEND=qdrant``
    selector, an importable ``qdrant_client`` package, and a configured
    effective Qdrant base URL. Any other case -- unset selector, package
    absent, unconfigured, or a construction failure -- degrades to the pgvector
    adapter, so the default path is never affected by the optional backend
    (ADR-020 §4). There is deliberately no implicit switch, and
    ``MEMORY_BACKEND`` is not consulted at all (T-A2-1).

    Deliberately unchanged by the T-A2-7 fallback wrapper: the three legacy
    similarity call sites keep their loud-failure contract (a Qdrant outage
    raises ``QdrantBackendUnavailableError`` out of the adapter instead of
    being silently served from pgvector). Only
    :func:`get_fallback_vector_port` -- the search path -- wraps.
    """
    port, _construction_error = _construct_qdrant_port()
    if port is not None:
        return port
    return PgVectorVectorPort()


def _artifact_vector_backend() -> str:
    """Return the explicit artifact vector-backend selector (default pgvector)."""
    return os.environ.get(
        ARTIFACT_VECTOR_BACKEND_ENV, DEFAULT_ARTIFACT_VECTOR_BACKEND
    ).strip().lower()


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


def _qdrant_selection_reason() -> str:
    """Return the first gate that keeps Qdrant from serving, or ``""``.

    The conditions are evaluated in the same order as :func:`_qdrant_selected`
    (ADR-020 §4, decoupled from ``MEMORY_BACKEND`` by T-A2-1), so the diagnostic
    can never disagree with the selector. The value is a stable,
    machine-readable token — never free text — because it is exposed verbatim
    in the ``/health/`` advisory.
    """
    if _artifact_vector_backend() != _QDRANT_ARTIFACT_BACKEND:
        # No explicit opt-in: pgvector is the requested backend, so this is not
        # a fallback and there is no reason to report.
        return ""
    if not _qdrant_client_available():
        return "qdrant_client_missing"
    try:
        config = _effective_qdrant_config()
    except Exception:  # noqa: BLE001 - config problems degrade to pgvector
        return "qdrant_config_error"
    if not getattr(config, "base_url", "").strip():
        return "qdrant_base_url_missing"
    return ""


def _qdrant_selected() -> bool:
    """Whether the Qdrant adapter should serve the artifact port.

    All three conditions must hold (ADR-020 §4; ``MEMORY_BACKEND`` is
    deliberately not one of them, T-A2-1); anything else degrades to pgvector:

    1. ``ARTIFACT_VECTOR_BACKEND=qdrant`` -- the explicit opt-in. The Qdrant
       artifact port is never selected as a side effect of ``MEMORY_BACKEND``
       or ``QDRANT_BASE_URL`` alone.
    2. The optional ``qdrant_client`` package is importable.
    3. An effective Qdrant base URL is configured (DB override over env).
    """
    if _artifact_vector_backend() != _QDRANT_ARTIFACT_BACKEND:
        return False
    return _qdrant_selection_reason() == ""


def vector_backend_diagnostic() -> dict[str, str]:
    """Return the requested/active artifact vector backend (issue #1437).

    Read-only: it never selects or constructs an adapter and never changes the
    behaviour of :func:`get_vector_port` (same gates, same order). The result
    makes the documented silent fallback visible:

    * ``requested`` -- the explicit ``ARTIFACT_VECTOR_BACKEND`` selector.
    * ``active`` -- ``"qdrant"`` exactly when :func:`_qdrant_selected` is true,
      else ``"pgvector"``.
    * ``reason`` -- ``""`` when the request is honoured (or pgvector was
      requested); otherwise the first failing gate:
      ``unknown_artifact_vector_backend``, ``qdrant_client_missing``,
      ``qdrant_config_error`` or ``qdrant_base_url_missing``.
    """
    requested = _artifact_vector_backend()
    if requested not in {DEFAULT_ARTIFACT_VECTOR_BACKEND, _QDRANT_ARTIFACT_BACKEND}:
        # An unknown selector is also served by pgvector; naming it as a
        # fallback is more useful than reporting a phantom "pgvector
        # requested".
        return {
            "requested": requested,
            "active": DEFAULT_ARTIFACT_VECTOR_BACKEND,
            "reason": "unknown_artifact_vector_backend",
        }
    reason = _qdrant_selection_reason()
    active = (
        _QDRANT_ARTIFACT_BACKEND
        if requested == _QDRANT_ARTIFACT_BACKEND and reason == ""
        else DEFAULT_ARTIFACT_VECTOR_BACKEND
    )
    return {"requested": requested, "active": active, "reason": reason}


def get_similarity_vector_port(workspace_id: UUID | None) -> VectorPort:
    """Port for the per-entity similarity sites, scoped or degraded (T-A2-8).

    The two legacy similarity entry points
    (``TraceLinkService.find_similar_trace_links`` and
    ``icd_manager.IcdManager.find_similar_icds``) take an OPTIONAL workspace
    scope. A Qdrant adapter cannot name a collection without one
    (:meth:`QdrantVectorPort._collection_name` raises), so the missing-scope
    case must not be answered with a loud 503:

    * **with** ``workspace_id``: exactly :func:`get_vector_port`. Under Qdrant
      that is the per-workspace ALIAS ``..._artifacts_live``; under pgvector the
      scope is a no-op unless the caller also names a ``workspace_field``, so
      the default deployment stays byte-identical.
    * **without** ``workspace_id``: an explicit :class:`PgVectorVectorPort`
      serves the request and reports ``degraded=True`` /
      ``degraded_reason="no_workspace_scope"`` -- nothing failed, the caller
      supplied no scope, so the optional backend cannot be addressed.

    A pgvector deployment is unaffected either way: the very same
    :func:`get_vector_port` object is returned, undegraded, in both cases.
    """
    port = get_vector_port()
    if workspace_id is not None:
        return port
    if (
        getattr(port, "vector_backend", DEFAULT_ARTIFACT_VECTOR_BACKEND)
        != _QDRANT_ARTIFACT_BACKEND
    ):
        # pgvector was requested (or is the fallback): it never needed a scope.
        return port
    degraded = PgVectorVectorPort()
    degraded.degraded = True
    degraded.degraded_reason = DEGRADED_NO_WORKSPACE_SCOPE
    logger.info(
        "similarity search called without a workspace scope; serving from "
        "pgvector (%s)",
        DEGRADED_NO_WORKSPACE_SCOPE,
    )
    return degraded


__all__ = [
    "ARTIFACT_VECTOR_BACKEND_ENV",
    "COLLECTION_ICD",
    "COLLECTION_REQUIREMENT",
    "COLLECTION_TRACE_LINK",
    "DEFAULT_ARTIFACT_VECTOR_BACKEND",
    "DEGRADED_CROSS_TYPE_QUERY_FAILED",
    "DEGRADED_NO_WORKSPACE_SCOPE",
    "DEGRADED_QDRANT_UNAVAILABLE",
    "FallbackVectorPort",
    "PgVectorBackendUnavailableError",
    "PgVectorVectorPort",
    "QdrantBackendUnavailableError",
    "QdrantVectorPort",
    "TypedVectorHit",
    "VectorBackendUnavailableError",
    "VectorHit",
    "VectorPort",
    "get_fallback_vector_port",
    "get_similarity_vector_port",
    "get_vector_port",
    "hydrate_vector_hits",
    "mark_request_degraded",
    "serves_from_fallback",
    "vector_backend_diagnostic",
]
