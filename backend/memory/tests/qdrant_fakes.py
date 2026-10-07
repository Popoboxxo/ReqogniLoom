"""In-memory, dependency-free stand-ins for the ``qdrant_client`` surface.

The optional ``qdrant_client`` package is deliberately NOT a test dependency
(see ``memory.qdrant_backend``'s module docstring): these doubles let the
backend's real code paths run against a duck-typed client without the package
ever being installed. They mirror the ``qdrant-client`` 1.x shapes the backend
uses: ``collection_exists`` / ``create_collection`` / ``get_collection`` /
``upsert`` / ``query_points`` / ``delete`` / ``scroll`` / ``get_collections``,
plus the small ``models`` namespace the backend builds requests with.

Kept in its own module (rather than inside a ``test_*.py`` file) so both
``test_qdrant_backend.py`` and ``test_backend_contract.py`` drive the exact
same double.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Optional


class _FakeVectorParams:
    def __init__(self, size: int, distance: Any = None, hnsw_config: Any = None) -> None:
        self.size = size
        self.distance = distance
        self.hnsw_config = hnsw_config


class _FakeHnswConfigDiff:
    def __init__(self, m: int = 16, ef_construct: int = 64) -> None:
        self.m = m
        self.ef_construct = ef_construct


class _FakePointStruct:
    def __init__(self, id: Any, vector: list, payload: Optional[dict] = None) -> None:
        self.id = id
        self.vector = vector
        self.payload = payload or {}


class _FakeMatchValue:
    def __init__(self, value: Any) -> None:
        self.value = value


class _FakeFieldCondition:
    def __init__(self, key: str, match: Any = None) -> None:
        self.key = key
        self.match = match


class _FakeFilter:
    def __init__(self, must: Optional[list] = None, **kwargs: Any) -> None:
        self.must = list(must or [])


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
    PointStruct=_FakePointStruct,
    MatchValue=_FakeMatchValue,
    FieldCondition=_FakeFieldCondition,
    Filter=_FakeFilter,
    PointIdsList=_FakePointIdsList,
    FilterSelector=_FakeFilterSelector,
    Distance=_FakeDistance,
)


def _matches(payload: dict, flt: Optional[_FakeFilter]) -> bool:
    """Whether *payload* satisfies every ``must`` condition of *flt*."""
    if flt is None:
        return True
    for condition in getattr(flt, "must", []) or []:
        matched = getattr(condition, "match", None)
        if matched is None:
            continue
        if str(payload.get(condition.key)) != str(matched.value):
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


class FakeQdrantClient:
    """Stateful in-memory Qdrant double keyed by collection name."""

    def __init__(self) -> None:
        #: collection name -> list of ``_FakePointStruct``
        self.collections: dict[str, list] = {}
        #: collection name -> declared vector width
        self.vector_sizes: dict[str, int] = {}
        #: Attributes that can be forced to raise to simulate an outage.
        self.fail_with: Optional[BaseException] = None

    def _guard(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def collection_exists(self, name: str) -> bool:
        self._guard()
        return name in self.collections

    def create_collection(
        self, *, collection_name: str, vectors_config: Any, **kwargs: Any
    ) -> None:
        self._guard()
        self.collections.setdefault(collection_name, [])
        self.vector_sizes[collection_name] = int(getattr(vectors_config, "size", 0))

    def get_collection(self, name: str) -> Any:
        self._guard()
        if name not in self.collections:
            raise ValueError(f"collection {name!r} does not exist")
        vectors = SimpleNamespace(size=self.vector_sizes[name])
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))

    def upsert(self, *, collection_name: str, points: list, **kwargs: Any) -> None:
        self._guard()
        store = self.collections.setdefault(collection_name, [])
        for point in points:
            store[:] = [existing for existing in store if str(existing.id) != str(point.id)]
            store.append(point)

    def query_points(
        self,
        *,
        collection_name: str,
        query: list,
        query_filter: Any = None,
        limit: int = 5,
        with_payload: bool = True,
        **kwargs: Any,
    ) -> Any:
        self._guard()
        store = self.collections.get(collection_name, [])
        scored = [
            _FakeScoredPoint(
                id=point.id,
                payload=point.payload,
                score=_cosine_similarity(query, point.vector),
            )
            for point in store
            if _matches(point.payload, query_filter)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return SimpleNamespace(points=scored[:limit])

    def delete(self, *, collection_name: str, points_selector: Any, **kwargs: Any) -> None:
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
        **kwargs: Any,
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
