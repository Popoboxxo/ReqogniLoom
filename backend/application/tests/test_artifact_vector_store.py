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

import logging
from uuid import UUID

import pytest
from django.core.exceptions import ImproperlyConfigured

from application.artifact_vector_store import (
    DENSE_VECTOR_NAME,
    PAYLOAD_INDEX_FIELDS,
    SPARSE_VECTOR_NAME,
    ensure_artifact_collection,
)
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.qdrant_config import (
    DEFAULT_QDRANT_QUANTIZATION,
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


def test_concurrent_create_race_with_a_different_width_fails_loud() -> None:
    """The tolerated create race must NOT bypass the dimension guard.

    The worker that wins the race provisioned the collection at another width
    (a deployment with a different ``EMBEDDING_VECTOR_DIMENSIONS``). Our
    ``create_collection`` then fails with "already exists", which is benign --
    but the collection that is now there is not one this process can use, so
    provisioning fails loud exactly like the reuse path instead of starting up
    against a width that only yields meaningless scores.
    """

    class _MismatchedRaceClient(FakeQdrantClient):
        """The concurrent winner left a collection at the WRONG width behind."""
        def create_collection(  # type: ignore[override]
            self,
            *,
            collection_name: str,
            vectors_config: object,
            sparse_vectors_config=None,
        ) -> None:
            wrong_width = EMBEDDING_VECTOR_DIMENSIONS + 128
            self.collections.setdefault(collection_name, [])
            self.vector_configs[collection_name] = {
                DENSE_VECTOR_NAME: FakeQdrantModels.VectorParams(size=wrong_width)
            }
            self.vector_sizes[collection_name] = wrong_width
            raise RuntimeError("Collection `%s` already exists!" % collection_name)

    client = _MismatchedRaceClient()

    with pytest.raises(ImproperlyConfigured, match="EMBEDDING_VECTOR_DIMENSIONS"):
        _ensure(client)

    # The guard runs before any write: no payload index was ever created.
    assert client.payload_indexes == {}


def test_create_failure_without_collection_still_raises() -> None:
    class _BrokenClient(FakeQdrantClient):
        def create_collection(self, **_kwargs: object) -> None:
            raise RuntimeError("connection refused")

    with pytest.raises(RuntimeError, match="connection refused"):
        _ensure(_BrokenClient())


class _RacingAliasClient(FakeQdrantClient):
    """Another worker creates the alias between our ``get_aliases()`` and our call.

    Mirrors what the loser of a start-up race sees: the alias exists by the time
    our ``update_collection_aliases`` lands, so Qdrant rejects the create with
    "alias already exists". *foreign_collection* models the case where the
    concurrent worker pointed the alias somewhere else entirely.
    """

    def __init__(self, *, foreign_collection: str | None = None) -> None:
        super().__init__()
        self._foreign_collection = foreign_collection

    def update_collection_aliases(self, *, change_aliases_operations: list) -> None:
        super().update_collection_aliases(change_aliases_operations=change_aliases_operations)
        if self._foreign_collection is not None:
            for operation in change_aliases_operations:
                created = getattr(operation, "create_alias", None)
                if created is not None:
                    self.aliases[created.alias_name] = self._foreign_collection
        raise RuntimeError("Alias already exists!")


def test_concurrent_alias_create_race_is_tolerated() -> None:
    client = _RacingAliasClient()
    alias = build_collection_alias("reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace")

    name = _ensure(client)

    # The winning worker already created the same alias at the right collection:
    # provisioning continues instead of aborting the worker's start-up.
    assert client.aliases[alias] == name
    assert set(client.payload_indexes[name]) == _EXPECTED_PAYLOAD_INDEX_FIELDS


def test_alias_race_that_left_a_foreign_target_still_raises() -> None:
    foreign = build_collection_name(
        "reqlo", _TENANT_B, workspace_id=_WORKSPACE_A, scope="workspace", artifacts=True, version=2
    )
    client = _RacingAliasClient(foreign_collection=foreign)

    # An alias pointing somewhere else is NOT the benign race: fail loud.
    with pytest.raises(RuntimeError, match="already exists"):
        _ensure(client)


def test_reused_collection_with_a_different_width_fails_loud() -> None:
    client = FakeQdrantClient()
    name = _ensure(client)

    # A collection left behind by a deployment that embedded at another width.
    client.vector_sizes[name] = EMBEDDING_VECTOR_DIMENSIONS + 128

    with pytest.raises(ImproperlyConfigured, match="EMBEDDING_VECTOR_DIMENSIONS"):
        _ensure(client)

    # The guard runs before any write: the collection is never recreated.
    create_calls = [call for call in client.calls if call[0] == "create_collection"]
    assert len(create_calls) == 1


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

    # The ALIAS is the name readers address from T-A2-6 on, so it is an isolation
    # boundary in its own right: three tenant/workspace pairs must leave three
    # distinct aliases, each pointing at its own pair's collection.
    pairs = (
        (_TENANT_A, _WORKSPACE_A),
        (_TENANT_A, _WORKSPACE_B),
        (_TENANT_B, _WORKSPACE_A),
    )
    expected_aliases = {
        build_collection_alias("reqlo", tenant, workspace_id=workspace, scope="workspace"): (
            build_collection_name(
                "reqlo",
                tenant,
                workspace_id=workspace,
                scope="workspace",
                artifacts=True,
                version=2,
            )
        )
        for tenant, workspace in pairs
    }
    assert len(expected_aliases) == 3, "every tenant/workspace pair gets its own alias"
    assert all(alias.endswith("_artifacts_live") for alias in expected_aliases)
    assert client.aliases == expected_aliases

    # ADR-020 §5: a non-UUID segment is rejected, never sanitize-collapsed.
    with pytest.raises(ValueError, match="tenant"):
        ensure_artifact_collection(
            client,
            "TENANT:1",
            _WORKSPACE_A,
            config=_config(),
            models_module=FakeQdrantModels,
        )


@pytest.mark.parametrize("raw", ["off", "false", "0", "no", "OFF"])
def test_quantization_off_aliases_disable_quantization(raw: str) -> None:
    """``off``/``false``/``0``/``no`` must DISABLE quantization, not enable it."""
    config = _config(quantization=raw)
    assert config.quantization == "none"

    client = FakeQdrantClient()
    name = _ensure(client, config=config)

    assert client.vector_configs[name][DENSE_VECTOR_NAME].quantization_config is None


def test_unrecognised_quantization_falls_back_to_int8_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A typo keeps the int8 default and is reported exactly once."""
    with caplog.at_level(logging.WARNING, logger="persistence.qdrant_config"):
        config = _config(quantization="int4")

    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and record.name == "persistence.qdrant_config"
    ]
    assert len(warnings) == 1, "exactly one warning, not one per resolution step"

    client = FakeQdrantClient()
    name = _ensure(client, config=config)

    assert client.vector_configs[name][DENSE_VECTOR_NAME].quantization_config is not None


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_quantization_env_value_is_unset_and_silent(
    raw: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``QDRANT_QUANTIZATION=`` in an env file means "unset", not "unrecognised".

    The resolver is uncached and runs per ``get_vector_port()``, so reporting a
    blank value as unrecognised would log a warning on every single request.
    """
    monkeypatch.setenv("QDRANT_QUANTIZATION", raw)

    with caplog.at_level(logging.WARNING, logger="persistence.qdrant_config"):
        config = resolve_qdrant_config()

    assert config.quantization == DEFAULT_QDRANT_QUANTIZATION
    assert [r for r in caplog.records if r.name == "persistence.qdrant_config"] == [], (
        "a blank value is not a typo: no warning"
    )


def test_quantization_none_omits_quantization_config() -> None:
    client = FakeQdrantClient()

    name = _ensure(client, config=_config(quantization="none"))

    assert client.vector_configs[name][DENSE_VECTOR_NAME].quantization_config is None
    assert client.sparse_configs[name][SPARSE_VECTOR_NAME].modifier == (
        FakeQdrantModels.Modifier.IDF
    )
