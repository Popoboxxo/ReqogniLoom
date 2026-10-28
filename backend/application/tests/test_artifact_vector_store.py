"""Tests for the versioned artifact-vector collection (T-A2-2, ADR-020 §2/§5).

The artifact collection is the *vector* counterpart of the legacy memory
collection: where ``memory.qdrant_backend`` keeps artifact-scoped MEMORY in the
unchanged ``..._artifacts`` collection with one unnamed vector, the artifact
port needs a named dense vector, a BM25 sparse vector and payload indexes. That
schema lives in a new collection name (``..._artifacts_v2``) reached through a
stable alias (``..._artifacts_live``) -- see
``application.artifact_vector_store``.

Everything here is driven by the signature-strict ``FakeQdrantClient`` doubles
from :mod:`memory.tests.qdrant_fakes`, so no ``qdrant`` server and no DB are
needed. The last class pins the isolation guard: the collection name stays
derived from tenant + workspace, never passed through by a caller (ADR-020 §5).
"""
from __future__ import annotations

from uuid import UUID

import pytest

from application.artifact_vector_store import (
    DENSE_VECTOR_NAME,
    PAYLOAD_INDEX_FIELDS,
    SPARSE_VECTOR_NAME,
    ensure_artifact_collection,
)
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.qdrant_config import (
    QdrantConfig,
    build_collection_alias,
    build_collection_name,
    resolve_qdrant_config,
)

_TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
_TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
_WORKSPACE_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_WORKSPACE_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_EXPECTED_PAYLOAD_INDEX_FIELDS = {
    "tenant_id",
    "workspace_id",
    "entity_id",
    "entity_type",
    "point_kind",
}


def _config(**overrides: object) -> QdrantConfig:
    """An env-independent config (the DB-override resolver is not exercised here)."""
    return resolve_qdrant_config(
        collection_prefix="reqlo",
        distance="cosine",
        hnsw_m=16,
        hnsw_ef_construct=64,
        **overrides,
    )


def _ensure(
    client: FakeQdrantClient,
    *,
    tenant: UUID = _TENANT_A,
    workspace: UUID = _WORKSPACE_A,
    config: QdrantConfig | None = None,
) -> str:
    return ensure_artifact_collection(
        client,
        tenant,
        workspace,
        config=config if config is not None else _config(),
        models_module=FakeQdrantModels,
    )


def test_ensure_creates_named_dense_and_bm25_sparse() -> None:
    client = FakeQdrantClient()

    name = _ensure(client)

    assert name == build_collection_name(
        "reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace", artifacts=True, version=2
    )
    assert name.endswith("_artifacts_v2")

    # The dense vector is NAMED -- unlike the legacy memory collection, whose
    # single unnamed vector must keep working untouched.
    vectors = client.vector_configs[name]
    assert set(vectors) == {DENSE_VECTOR_NAME}
    dense = vectors[DENSE_VECTOR_NAME]
    assert dense.size == EMBEDDING_VECTOR_DIMENSIONS
    assert dense.distance == FakeQdrantModels.Distance.COSINE
    assert dense.hnsw_config.m == 16
    assert dense.hnsw_config.ef_construct == 64

    quantization = dense.quantization_config
    assert quantization is not None, "QDRANT_QUANTIZATION defaults to int8"
    assert quantization.scalar.type == FakeQdrantModels.ScalarType.INT8
    assert quantization.scalar.quantile == pytest.approx(0.99)
    assert quantization.scalar.always_ram is True

    sparse = client.sparse_configs[name]
    assert set(sparse) == {SPARSE_VECTOR_NAME}
    assert sparse[SPARSE_VECTOR_NAME].modifier == FakeQdrantModels.Modifier.IDF


def test_ensure_is_idempotent_and_creates_payload_indexes() -> None:
    client = FakeQdrantClient()
    name = _ensure(client)
    client.upsert(
        collection_name=name,
        points=[
            FakeQdrantModels.PointStruct(
                id=str(UUID("33333333-3333-3333-3333-333333333333")),
                vector={DENSE_VECTOR_NAME: [0.1] * EMBEDDING_VECTOR_DIMENSIONS},
                payload={
                    "tenant_id": str(_TENANT_A),
                    "workspace_id": str(_WORKSPACE_A),
                    "entity_id": str(UUID("33333333-3333-3333-3333-333333333333")),
                    "entity_type": "Requirement",
                    "point_kind": "artifact",
                },
            )
        ],
    )

    assert _ensure(client) == name

    # Reused, never recreated: exactly one create_collection over both calls and
    # the existing point survives (a destructive recreate would drop it).
    create_calls = [call for call in client.calls if call[0] == "create_collection"]
    assert len(create_calls) == 1
    assert len(client.collections[name]) == 1

    indexes = client.payload_indexes[name]
    assert set(indexes) == _EXPECTED_PAYLOAD_INDEX_FIELDS
    assert set(PAYLOAD_INDEX_FIELDS) == _EXPECTED_PAYLOAD_INDEX_FIELDS
    assert all(schema == FakeQdrantModels.PayloadSchemaType.KEYWORD for schema in indexes.values())

    # The second call adds nothing: no duplicate index writes.
    index_calls = [call for call in client.calls if call[0] == "create_payload_index"]
    assert len(index_calls) == len(_EXPECTED_PAYLOAD_INDEX_FIELDS)


def test_alias_points_to_v2() -> None:
    client = FakeQdrantClient()
    alias = build_collection_alias("reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace")
    assert alias == f"reqlo_{_TENANT_A}_{_WORKSPACE_A}_artifacts_live"

    # The legacy memory collection keeps its own (unnamed-vector) schema and its
    # points. A pre-v2 deployment may already have the alias on it; provisioning
    # v2 re-points the alias and leaves the legacy collection alone.
    legacy = build_collection_name(
        "reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace", artifacts=True
    )
    client.create_collection(
        collection_name=legacy,
        vectors_config=FakeQdrantModels.VectorParams(
            size=EMBEDDING_VECTOR_DIMENSIONS, distance=FakeQdrantModels.Distance.COSINE
        ),
    )
    client.upsert(
        collection_name=legacy,
        points=[
            FakeQdrantModels.PointStruct(
                id=str(UUID("44444444-4444-4444-4444-444444444444")),
                vector=[0.5] * EMBEDDING_VECTOR_DIMENSIONS,
                payload={"tenant_id": str(_TENANT_A), "scope": "artifact"},
            )
        ],
    )
    client.aliases[alias] = legacy

    name = _ensure(client)

    assert name.endswith("_artifacts_v2")
    assert client.aliases[alias] == name
    assert client.collections[legacy] != [], "the memory collection is never touched"
    assert client.vector_configs[legacy].size == EMBEDDING_VECTOR_DIMENSIONS


def test_concurrent_create_race_is_tolerated() -> None:
    class _RacingClient(FakeQdrantClient):
        """Another worker wins the create between our check and our call."""

        def create_collection(  # type: ignore[override]
            self, *, collection_name: str, vectors_config: object, sparse_vectors_config=None
        ) -> None:
            super().create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_vectors_config,
            )
            raise RuntimeError("Collection `%s` already exists!" % collection_name)

    client = _RacingClient()

    name = _ensure(client)

    assert len(client.collections[name]) == 0
    assert set(client.payload_indexes[name]) == _EXPECTED_PAYLOAD_INDEX_FIELDS


def test_create_failure_without_collection_still_raises() -> None:
    class _BrokenClient(FakeQdrantClient):
        def create_collection(self, **_kwargs: object) -> None:
            raise RuntimeError("connection refused")

    with pytest.raises(RuntimeError, match="connection refused"):
        _ensure(_BrokenClient())


def test_collection_name_still_tenant_derived() -> None:
    client = FakeQdrantClient()

    names = {
        _ensure(client),
        _ensure(client, workspace=_WORKSPACE_B),
        _ensure(client, tenant=_TENANT_B),
    }

    assert len(names) == 3, "tenant + workspace are the isolation boundary"
    assert all(name.startswith("reqlo_") and name.endswith("_artifacts_v2") for name in names)
    assert f"reqlo_{_TENANT_A}_{_WORKSPACE_A}_artifacts_v2" in names

    # ADR-020 §5: a non-UUID segment is rejected, never sanitize-collapsed.
    with pytest.raises(ValueError, match="tenant"):
        ensure_artifact_collection(
            client,
            "TENANT:1",
            _WORKSPACE_A,
            config=_config(),
            models_module=FakeQdrantModels,
        )


def test_quantization_none_omits_quantization_config() -> None:
    client = FakeQdrantClient()

    name = _ensure(client, config=_config(quantization="none"))

    assert client.vector_configs[name][DENSE_VECTOR_NAME].quantization_config is None
    assert client.sparse_configs[name][SPARSE_VECTOR_NAME].modifier == (
        FakeQdrantModels.Modifier.IDF
    )
