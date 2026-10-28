"""Provisioning of the versioned artifact-vector collection (T-A2-2, ADR-020).

ADR-020 gives ReqogniLoom one Qdrant collection per workspace. Historically that
collection (``..._artifacts``) carries TWO different things in one schema: the
artifact-scoped *memory* rows of ``memory.qdrant_backend`` and the *entity*
vectors the artifact port queries. Splitting them in place would break the
memory backend, so the artifact vectors move to their own, versioned collection:

* ``build_collection_name(..., artifacts=True)`` -> ``..._artifacts`` -- the
  UNCHANGED legacy memory collection (one unnamed vector). This module never
  touches it.
* ``build_collection_name(..., artifacts=True, version=2)`` -> ``..._artifacts_v2``
  -- the schema below.
* ``build_collection_alias(...)`` -> ``..._artifacts_live`` -- the stable name
  readers use from T-A2-6 on, so a later schema change bumps the version
  without touching a single reader.

Schema of the v2 collection:

* one NAMED dense vector ``dense`` (``EMBEDDING_VECTOR_DIMENSIONS``, COSINE, the
  configured HNSW ``m``/``ef_construct``, and -- unless ``QDRANT_QUANTIZATION``
  is ``none`` -- int8 scalar quantization, ``quantile=0.99``, ``always_ram``);
* one sparse vector ``bm25`` with ``Modifier.IDF``;
* KEYWORD payload indexes on ``tenant_id``, ``workspace_id``, ``entity_id``,
  ``entity_type`` and ``point_kind`` (UUIDs are indexed as their string form).

:func:`ensure_artifact_collection` is create-or-reuse and idempotent: an
existing v2 collection is never dropped or recreated (it may already hold
vectors), only missing payload indexes are added, and the alias is re-pointed at
v2 atomically. It is a provisioning seam, not the indexer -- which entity gets
which point lives in T-A2-3.

The collection name is still the isolation boundary (ADR-020 §2/§5): it is
derived here from tenant + workspace via :func:`build_collection_name` and never
accepted from a caller.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from persistence.qdrant_config import (
    QDRANT_DISTANCE_ATTRS,
    QDRANT_QUANTIZATION_INT8,
    QdrantConfig,
    build_collection_alias,
    build_collection_name,
)

logger = logging.getLogger(__name__)

#: Schema version of the artifact collection. Bump it (and only it) when the
#: vector/payload shape changes; readers reach the collection via the alias.
ARTIFACT_COLLECTION_VERSION = 2

#: Name of the dense (embedding) vector inside the v2 artifact collection.
DENSE_VECTOR_NAME = "dense"

#: Name of the BM25 sparse vector inside the v2 artifact collection.
SPARSE_VECTOR_NAME = "bm25"

#: Payload fields indexed as KEYWORD. The three UUID-bearing fields
#: (``tenant_id``, ``workspace_id``, ``entity_id``) are stored as their string
#: form, which is exactly what the payload filters compare against (T-A2-2).
PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "tenant_id",
    "workspace_id",
    "entity_id",
    "entity_type",
    "point_kind",
)

#: Quantile of the int8 scalar quantizer -- Qdrant's recommended default for
#: cosine search (keeps the score tail exact).
QUANTIZATION_QUANTILE = 0.99


def _resolve_config() -> QdrantConfig:
    """Resolve the effective Qdrant config (DB override over env), lazily.

    Delegates to ``application.vector_port._effective_qdrant_config``: there is
    exactly ONE effective-config resolver (the frozen "which Qdrant does the
    backend talk to" seam, DB override over env, degrading to the env-only
    resolver when ``memory`` is not importable). Duplicating that resolution in
    a second module would let provisioning and querying drift apart on a
    security-relevant setting. Behaviour is identical -- the same fallback chain,
    in the same order -- and the import stays lazy so this module remains
    importable without the optional stack.
    """
    from application.vector_port import (  # lazy: single resolver, no fork
        _effective_qdrant_config,
    )

    return _effective_qdrant_config()


def _dense_quantization(models: Any, config: QdrantConfig) -> Any:
    """The int8 quantization config, or ``None`` when quantization is off."""
    if config.quantization != QDRANT_QUANTIZATION_INT8:
        return None
    return models.ScalarQuantization(
        scalar=models.ScalarQuantizationConfig(
            type=models.ScalarType.INT8,
            quantile=QUANTIZATION_QUANTILE,
            always_ram=True,
        )
    )


def _payload_index_fields(collection_info: Any) -> set[str]:
    """The payload fields that already have an index, per a ``CollectionInfo``."""
    schema = getattr(collection_info, "payload_schema", None) or {}
    return set(schema)


def _assert_existing_dimension(collection_info: Any, config: QdrantConfig) -> None:
    """Fail loud when a reused collection was built at another vector width.

    A ``..._artifacts_v2`` collection created under a different
    ``EMBEDDING_VECTOR_DIMENSIONS`` would accept the upsert and then return
    meaningless scores, so a drift is a configuration error (ADR-020 §6), never
    a warning. Reuses the guard the memory backend already applies rather than
    re-implementing it: ``_collection_dimension`` already tolerates the named
    vector dict shape this v2 collection uses. Imported lazily for the same
    reason as :func:`_resolve_config`.
    """
    from memory.qdrant_backend import (  # lazy: shared dimension guard
        _collection_dimension,
        assert_collection_dimension,
    )

    assert_collection_dimension(_collection_dimension(collection_info), config.vector_dimensions)


def _alias_target(client: Any, alias: str) -> str | None:
    """The collection *alias* currently points at, or ``None`` when unset."""
    aliases = {
        entry.alias_name: entry.collection_name
        for entry in (getattr(client.get_aliases(), "aliases", None) or [])
    }
    return aliases.get(alias)


def _point_alias_at(client: Any, models: Any, alias: str, collection_name: str) -> None:
    """Point *alias* at *collection_name* idempotently and atomically.

    Qdrant rejects creating an alias that already exists, so moving a stale one
    is a delete+create in ONE ``update_collection_aliases`` call -- never a
    window in which readers see no alias. The target collection is never
    touched (no drop, no recreate).
    """
    current = _alias_target(client, alias)
    if current == collection_name:
        return

    operations: list[Any] = []
    if current is not None:
        operations.append(
            models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
        )
    operations.append(
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name=collection_name,
                alias_name=alias,
            )
        )
    )
    try:
        client.update_collection_aliases(change_aliases_operations=operations)
    except Exception:
        # Same start-up race as the collection create above: two workers can both
        # read "no alias" and both try to create it, and the loser gets Qdrant's
        # "alias already exists". Only an alias that now points at
        # *collection_name* makes the error benign -- anything else (including a
        # concurrent worker that pointed it somewhere else) is re-raised
        # unchanged, so a real alias misconfiguration stays loud.
        if _alias_target(client, alias) != collection_name:
            raise
        logger.debug("qdrant artifact alias %s was pointed concurrently", alias)
    else:
        logger.info("pointed qdrant artifact alias %s at %s", alias, collection_name)


def ensure_artifact_collection(
    client: Any,
    tenant_id: UUID | str,
    workspace_id: UUID | str,
    *,
    config: QdrantConfig | None = None,
    models_module: Any = None,
) -> str:
    """Create (or reuse) the v2 artifact collection and point its alias at it.

    Idempotent: calling it twice leaves one collection, the same five payload
    indexes and one alias, and never destroys vectors already indexed.

    Args:
        client: A ``QdrantClient`` (or a duck-typed double in tests).
        tenant_id: Owning tenant UUID. Validated by
            :func:`build_collection_name` -- the isolation boundary.
        workspace_id: Owning workspace UUID (Strategy A: one collection per
            workspace).
        config: Effective Qdrant config; resolved from the DB override/env when
            omitted.
        models_module: ``qdrant_client.models`` override (test seam).

    Returns:
        The v2 collection name (``..._artifacts_v2``).

    Raises:
        ValueError: If the tenant/workspace id is missing or not UUID-shaped.
        ImproperlyConfigured: When the collection already exists at a vector
            width other than ``config.vector_dimensions`` (ADR-020 §6: a drift
            fails loud instead of degrading search scores).
        Exception: Any Qdrant error that did not leave a usable collection
            behind (e.g. an unreachable server) propagates unchanged.
    """
    config = config if config is not None else _resolve_config()
    models = models_module
    if models is None:
        from qdrant_client import models  # qdrant-client; lazy (optional dependency)

    collection_name = build_collection_name(
        config.collection_prefix,
        tenant_id,
        workspace_id=workspace_id,
        scope="workspace",
        artifacts=True,
        version=ARTIFACT_COLLECTION_VERSION,
    )
    alias = build_collection_alias(
        config.collection_prefix,
        tenant_id,
        workspace_id=workspace_id,
        scope="workspace",
    )

    if not client.collection_exists(collection_name):
        dense: dict[str, Any] = {
            "size": config.vector_dimensions,
            "distance": getattr(
                models.Distance, QDRANT_DISTANCE_ATTRS.get(config.distance, "COSINE")
            ),
            "hnsw_config": models.HnswConfigDiff(
                m=config.hnsw_m, ef_construct=config.hnsw_ef_construct
            ),
        }
        quantization = _dense_quantization(models, config)
        if quantization is not None:
            dense["quantization_config"] = quantization
        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config={DENSE_VECTOR_NAME: models.VectorParams(**dense)},
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
            )
        except Exception:
            # Provisioning also runs from every worker at start-up, so two of
            # them can race here. Only a collection that another caller just
            # created makes the error benign -- anything else (unreachable
            # server, permission error) is re-raised unchanged.
            if not client.collection_exists(collection_name):
                raise
            logger.debug("qdrant artifact collection %s was created concurrently", collection_name)
        else:
            logger.info("created qdrant artifact collection %s (alias=%s)", collection_name, alias)
        info = client.get_collection(collection_name)
    else:
        # Reuse: never dropped or recreated (it may already hold vectors), but an
        # existing collection built at another width must fail loud now rather
        # than surface much later as meaningless scores or failed upserts.
        info = client.get_collection(collection_name)
        _assert_existing_dimension(info, config)

    existing_fields = _payload_index_fields(info)
    for field_name in PAYLOAD_INDEX_FIELDS:
        if field_name in existing_fields:
            continue
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    _point_alias_at(client, models, alias, collection_name)
    return collection_name
