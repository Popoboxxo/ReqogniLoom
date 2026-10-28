"""In-memory, dependency-free stand-ins for the ``qdrant_client`` surface.

The optional ``qdrant_client`` package is deliberately NOT a test dependency
(see ``memory.qdrant_backend``'s module docstring): these doubles let the
backend's real code paths run against a duck-typed client without the package
ever being installed. They mirror the ``qdrant-client`` 1.x shapes the backend
uses: ``collection_exists`` / ``create_collection`` / ``get_collection`` /
``upsert`` / ``query_points`` / ``delete`` / ``scroll`` / ``count`` /
``get_collections``, plus the small ``models`` namespace the backend builds
requests with.

The doubles are SIGNATURE-STRICT on purpose (issue #1250): earlier they
accepted ``**kwargs`` and silently swallowed a misspelled/mis-passed argument,
so a real client-side ``TypeError`` could never be reproduced in a test. Each
method now declares exactly the keyword arguments the backend (and the vector
port) actually passes -- an extra kwarg raises ``TypeError`` like the real
client would.

Kept in its own module (rather than inside a ``test_*.py`` file) so both
``test_qdrant_backend.py`` and ``test_backend_contract.py`` drive the exact
same double.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any


class _FakeVectorParams:
    def __init__(
        self,
        size: int,
        distance: Any = None,
        hnsw_config: Any = None,
        quantization_config: Any = None,
    ) -> None:
        self.size = size
        self.distance = distance
        self.hnsw_config = hnsw_config
        #: qdrant-client spells the field ``quantization_config`` (not
        #: ``quantization``); kept verbatim so a mis-passed kwarg still raises.
        self.quantization_config = quantization_config


class _FakeHnswConfigDiff:
    def __init__(self, m: int = 16, ef_construct: int = 64) -> None:
        self.m = m
        self.ef_construct = ef_construct


class _FakeSparseVectorParams:
    def __init__(self, index: Any = None, modifier: Any = None) -> None:
        self.index = index
        self.modifier = modifier


class _FakeScalarQuantizationConfig:
    def __init__(
        self, type: Any = None, quantile: float | None = None, always_ram: bool | None = None
    ) -> None:
        self.type = type
        self.quantile = quantile
        self.always_ram = always_ram


class _FakeScalarQuantization:
    def __init__(self, scalar: Any = None) -> None:
        self.scalar = scalar


class _FakeScalarType:
    """Mirrors the INSTALLED ``qdrant-client`` (1.19.1), which knows only INT8.

    Declaring further members here would make the double more permissive than
    reality and let a test pass against a value the real client does not have.
    """

    INT8 = "int8"


class _FakeModifier:
    NONE = "none"
    IDF = "idf"


class _FakePayloadSchemaType:
    KEYWORD = "keyword"
    INTEGER = "integer"
    FLOAT = "float"
    GEO = "geo"
    TEXT = "text"
    BOOL = "bool"


class _FakeCreateAlias:
    def __init__(self, collection_name: str, alias_name: str) -> None:
        self.collection_name = collection_name
        self.alias_name = alias_name


class _FakeCreateAliasOperation:
    def __init__(self, create_alias: Any = None) -> None:
        self.create_alias = create_alias


class _FakeDeleteAlias:
    def __init__(self, alias_name: str) -> None:
        self.alias_name = alias_name


class _FakeDeleteAliasOperation:
    def __init__(self, delete_alias: Any = None) -> None:
        self.delete_alias = delete_alias


class _FakePointStruct:
    def __init__(self, id: Any, vector: list, payload: dict | None = None) -> None:
        self.id = id
        self.vector = vector
        self.payload = payload or {}


class _FakeDocument:
    """Mirrors ``models.Document`` (the server-side BM25 sparse input).

    ``qdrant-client`` sends ``Document(text=..., model="qdrant/bm25")`` as a
    sparse vector value; the double keeps the two fields a caller can inspect so
    an indexer test can assert the sparse half was actually populated.
    """

    def __init__(self, text: str, model: str | None = None, options: Any = None) -> None:
        self.text = text
        self.model = model
        self.options = options


class _FakeMatchValue:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeFieldCondition:
    def __init__(self, key: str, match: Any = None) -> None:
        self.key = key
        self.match = match


class _FakeMatchAny:
    def __init__(self, any: list | None = None) -> None:
        self.any = list(any or [])


class _FakeFilter:
    def __init__(
        self,
        must: list | None = None,
        should: list | None = None,
        must_not: list | None = None,
        **kwargs: Any,
    ) -> None:
        self.must = list(must or [])
        self.should = list(should or []) if should is not None else None
        self.must_not = list(must_not or [])


class _FakePrefetch:
    """Mirrors ``models.Prefetch`` (one leg of a hybrid query)."""

    def __init__(
        self,
        query: Any = None,
        using: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.query = query
        self.using = using
        self.limit = limit


class _FakeFusion:
    RRF = "rrf"
    DBSF = "dbsf"


class _FakeFusionQuery:
    def __init__(self, fusion: Any = None) -> None:
        self.fusion = fusion


class _FakePointIdsList:
    def __init__(self, points: list) -> None:
        self.points = list(points)


class _FakeFilterSelector:
    def __init__(self, filter: Any = None, **kwargs: Any) -> None:
        self.filter = filter


class _FakeDistance:
    COSINE = "cosine"
    DOT = "dot"
    EUCLID = "euclid"
    MANHATTAN = "manhattan"


#: The subset of ``qdrant_client.models`` the backend constructs requests with.
FakeQdrantModels = SimpleNamespace(
    VectorParams=_FakeVectorParams,
    HnswConfigDiff=_FakeHnswConfigDiff,
    SparseVectorParams=_FakeSparseVectorParams,
    ScalarQuantization=_FakeScalarQuantization,
    ScalarQuantizationConfig=_FakeScalarQuantizationConfig,
    ScalarType=_FakeScalarType,
    Modifier=_FakeModifier,
    PayloadSchemaType=_FakePayloadSchemaType,
    CreateAlias=_FakeCreateAlias,
    CreateAliasOperation=_FakeCreateAliasOperation,
    DeleteAlias=_FakeDeleteAlias,
    DeleteAliasOperation=_FakeDeleteAliasOperation,
    PointStruct=_FakePointStruct,
    Document=_FakeDocument,
    MatchValue=_FakeMatchValue,
    MatchAny=_FakeMatchAny,
    FieldCondition=_FakeFieldCondition,
    Filter=_FakeFilter,
    Prefetch=_FakePrefetch,
    Fusion=_FakeFusion,
    FusionQuery=_FakeFusionQuery,
    PointIdsList=_FakePointIdsList,
    FilterSelector=_FakeFilterSelector,
    Distance=_FakeDistance,
)


def _matches(payload: dict, flt: _FakeFilter | None) -> bool:
    """Whether *payload* satisfies every ``must`` condition of *flt*."""
    if flt is None:
        return True
    for condition in getattr(flt, "must", []) or []:
        matched = getattr(condition, "match", None)
        if matched is None:
            continue
        if hasattr(matched, "any"):  # MatchAny -> membership test
            if str(payload.get(condition.key)) not in {str(v) for v in matched.any}:
                return False
            continue
        if str(payload.get(condition.key)) != str(matched.value):
            return False
    for condition in getattr(flt, "must_not", []) or []:
        matched = getattr(condition, "match", None)
        if matched is None:
            continue
        if str(payload.get(condition.key)) == str(matched.value):
            return False
    return True


def _cosine_similarity(a: list, b: list) -> float:
    """Cosine similarity of two equal-width vectors; 0.0 when undefined."""
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class _FakeScoredPoint(SimpleNamespace):
    """Mirrors ``qdrant_client``'s ``ScoredPoint`` (only the fields we read)."""


def _dense_vector(vector: Any) -> list:
    """The ``dense`` leg of a named-vector point (plain lists pass through)."""
    if isinstance(vector, dict):
        return list(vector.get("dense") or [])
    return list(vector or [])


def _sparse_text(vector: Any) -> str:
    """The text a BM25 ``Document`` leg was built from, for token matching."""
    if not isinstance(vector, dict):
        return ""
    sparse = vector.get("bm25")
    if isinstance(sparse, _FakeDocument):
        return sparse.text
    if isinstance(sparse, dict):
        return str(sparse.get("text") or "")
    return sparse if isinstance(sparse, str) else ""


def _prefetch_score(leg: Any, point: Any) -> float:
    """One leg's similarity for *point*: cosine for dense, token overlap for BM25."""
    query = getattr(leg, "query", None)
    if isinstance(query, list):
        return _cosine_similarity(query, _dense_vector(point.vector))
    text = str(getattr(query, "text", "") or "").lower()
    wanted = {token for token in text.split() if token}
    if not wanted:
        return 0.0
    present = set(_sparse_text(point.vector).lower().split())
    return float(len(wanted & present))



class FakeQdrantClient:
    """Stateful in-memory Qdrant double keyed by collection name."""

    def __init__(self) -> None:
        #: collection name -> list of ``_FakePointStruct``
        self.collections: dict[str, list] = {}
        #: collection name -> declared vector width
        self.vector_sizes: dict[str, int] = {}
        #: collection name -> the ``vectors_config`` it was created with (a
        #: ``VectorParams`` for the legacy collections, a ``{name: VectorParams}``
        #: mapping for the v2 artifact collection)
        self.vector_configs: dict[str, Any] = {}
        #: collection name -> the ``sparse_vectors_config`` it was created with
        self.sparse_configs: dict[str, Any] = {}
        #: collection name -> ``{field_name: field_schema}``
        self.payload_indexes: dict[str, dict[str, Any]] = {}
        #: alias name -> collection name
        self.aliases: dict[str, str] = {}
        #: Every mutating/reading call in order, as ``(method, kwargs)`` -- lets a
        #: test assert "created once, never recreated" without reaching into state.
        self.calls: list[tuple[str, dict]] = []
        #: Attributes that can be forced to raise to simulate an outage.
        self.fail_with: BaseException | None = None

    def _guard(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def _record(self, method: str, **kwargs: Any) -> None:
        self.calls.append((method, kwargs))

    def collection_exists(self, name: str) -> bool:
        self._guard()
        self._record("collection_exists", collection_name=name)
        return name in self.collections

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: Any,
        sparse_vectors_config: Any = None,
    ) -> None:
        self._guard()
        self._record(
            "create_collection",
            collection_name=collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )
        self.collections.setdefault(collection_name, [])
        if isinstance(vectors_config, dict):
            self.vector_configs[collection_name] = dict(vectors_config)
            primary = next(iter(vectors_config.values()), None)
        else:
            self.vector_configs[collection_name] = vectors_config
            primary = vectors_config
        self.vector_sizes[collection_name] = int(getattr(primary, "size", 0))
        if sparse_vectors_config is not None:
            self.sparse_configs[collection_name] = dict(sparse_vectors_config)

    def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: Any = None,
        wait: bool = True,
    ) -> Any:
        """Like the real client: idempotent, an existing index is kept."""
        self._guard()
        self._record(
            "create_payload_index",
            collection_name=collection_name,
            field_name=field_name,
            field_schema=field_schema,
        )
        indexes = self.payload_indexes.setdefault(collection_name, {})
        indexes.setdefault(field_name, field_schema)
        return SimpleNamespace(status="completed")

    def update_collection_aliases(self, *, change_aliases_operations: list) -> None:
        self._guard()
        self._record(
            "update_collection_aliases",
            change_aliases_operations=list(change_aliases_operations),
        )
        for operation in change_aliases_operations:
            created = getattr(operation, "create_alias", None)
            if created is not None:
                self.aliases[created.alias_name] = created.collection_name
                continue
            deleted = getattr(operation, "delete_alias", None)
            if deleted is not None:
                self.aliases.pop(deleted.alias_name, None)

    def get_aliases(self) -> Any:
        self._guard()
        self._record("get_aliases")
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=alias, collection_name=collection)
                for alias, collection in self.aliases.items()
            ]
        )

    def get_collection(self, name: str) -> Any:
        self._guard()
        self._record("get_collection", collection_name=name)
        if name not in self.collections:
            raise ValueError(f"collection {name!r} does not exist")
        # ``vector_sizes`` stays the mutable source of truth, so a test can widen
        # a collection behind the backend's back. The SHAPE, however, follows what
        # ``create_collection`` recorded: real Qdrant returns a
        # ``{vector_name: VectorParams}`` dict for a named-vector collection (the
        # v2 artifact collection) and a bare ``VectorParams`` for the legacy
        # unnamed-vector ones. Flattening both to the unnamed shape would leave
        # the named-vector branch of ``_collection_dimension`` untested.
        size_holder = SimpleNamespace(size=self.vector_sizes[name])
        recorded = self.vector_configs.get(name)
        vectors = (
            {vector_name: size_holder for vector_name in recorded}
            if isinstance(recorded, dict)
            else size_holder
        )
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=vectors,
                    sparse_vectors=self.sparse_configs.get(name),
                )
            ),
            payload_schema=dict(self.payload_indexes.get(name, {})),
        )

    def upsert(self, *, collection_name: str, points: list, wait: bool = False) -> None:
        self._guard()
        store = self.collections.setdefault(collection_name, [])
        for point in points:
            store[:] = [existing for existing in store if str(existing.id) != str(point.id)]
            store.append(point)

    def retrieve(
        self,
        *,
        collection_name: str,
        ids: list,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> list:
        """Return the stored points among *ids* (mirrors ``client.retrieve``)."""
        self._guard()
        self._record("retrieve", collection_name=collection_name, ids=list(ids))
        wanted = {str(point_id) for point_id in ids}
        return [
            SimpleNamespace(
                id=point.id,
                payload=point.payload if with_payload else None,
                vector=point.vector if with_vectors else None,
            )
            for point in self.collections.get(collection_name, [])
            if str(point.id) in wanted
        ]

    def delete_collection(self, *, collection_name: str) -> None:
        """Drop *collection_name* and every alias that pointed at it."""
        self._guard()
        self._record("delete_collection", collection_name=collection_name)
        self.collections.pop(collection_name, None)
        self.vector_sizes.pop(collection_name, None)
        self.vector_configs.pop(collection_name, None)
        self.sparse_configs.pop(collection_name, None)
        self.payload_indexes.pop(collection_name, None)
        self.aliases = {
            alias: target
            for alias, target in self.aliases.items()
            if target != collection_name
        }

    def count(self, *, collection_name: str, exact: bool = True) -> Any:
        """Number of points in *collection_name* (mirrors ``client.count``)."""
        self._guard()
        return SimpleNamespace(count=len(self.collections.get(collection_name, [])))

    def query_points(
        self,
        *,
        collection_name: str,
        query: Any,
        query_filter: Any = None,
        limit: int = 5,
        with_payload: bool = True,
        prefetch: list | None = None,
    ) -> Any:
        """Hybrid-capable ``query_points``.

        ``query`` is either a plain vector (dense search, unchanged) or a
        ``FusionQuery`` accompanied by ``prefetch`` legs. The double does NOT
        implement Qdrant's RRF arithmetic: a fused leg contributes the point's
        own per-leg score and the point's fused score is the best leg (a point
        matching at least one leg is returned, points matching none are not).
        That is enough to prove *which* legs were requested and that a sparse
        match alone surfaces a hit -- the exact fusion weights are the server's
        business, not the adapter's.
        """
        self._guard()
        self._record(
            "query_points",
            collection_name=collection_name,
            query=query,
            query_filter=query_filter,
            limit=limit,
            prefetch=prefetch,
        )
        store = [
            point for point in self.collections.get(collection_name, [])
            if _matches(point.payload, query_filter)
        ]
        if prefetch:
            scored = []
            for point in store:
                score = max((_prefetch_score(leg, point) for leg in prefetch), default=0.0)
                if score > 0.0:
                    scored.append(
                        _FakeScoredPoint(id=point.id, payload=point.payload, score=score)
                    )
        else:
            scored = [
                _FakeScoredPoint(
                    id=point.id,
                    payload=point.payload,
                    score=_cosine_similarity(query, _dense_vector(point.vector)),
                )
                for point in store
            ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return SimpleNamespace(points=scored[:limit])

    def delete(self, *, collection_name: str, points_selector: Any, wait: bool = False) -> None:
        self._guard()
        store = self.collections.get(collection_name, [])
        if isinstance(points_selector, _FakePointIdsList):
            ids = {str(point_id) for point_id in points_selector.points}
            self.collections[collection_name] = [
                point for point in store if str(point.id) not in ids
            ]
        elif isinstance(points_selector, _FakeFilterSelector):
            self.collections[collection_name] = [
                point for point in store if not _matches(point.payload, points_selector.filter)
            ]

    def scroll(
        self,
        *,
        collection_name: str,
        scroll_filter: Any = None,
        limit: int = 1000,
        offset: Any = None,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> Any:
        """Page like the real client: ``offset`` is an exclusive start point id
        and the second return value is the next page offset (``None`` at the
        end). Without this, a caller that honours ``next_page_offset`` would
        loop forever on a fake that always returned the same page.
        """
        self._guard()
        store = self.collections.get(collection_name, [])
        matched = [point for point in store if _matches(point.payload, scroll_filter)]
        start = 0
        if offset is not None:
            ids = [str(point.id) for point in matched]
            start = ids.index(str(offset)) + 1 if str(offset) in ids else len(matched)
        page = matched[start : start + limit]
        end = start + len(page)
        next_offset = str(page[-1].id) if page and end < len(matched) else None
        records = [SimpleNamespace(id=point.id, payload=point.payload) for point in page]
        return records, next_offset

    def get_collections(self) -> Any:
        self._guard()
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in self.collections]
        )
