"""Write-side port for the artifact vector store (ADR-020 extension).

The read port (:mod:`application.vector_port`) answers nearest-neighbour
queries. This module is its write-side counterpart: it owns *how* an artifact
record physically reaches a store, so :mod:`application.artifact_indexer` can
stay backend-neutral and a new store only has to implement
:class:`VectorWriteStore`.

Implementations:

* :class:`QdrantWriteStore` -- the opt-in external store. It maps a neutral
  :class:`VectorRecord` onto a Qdrant point with a named dense vector plus the
  server-side ``qdrant/bm25`` sparse vector, and keeps collection provisioning
  (and the ``..._artifacts_live`` alias) in one place.
* :class:`NoopWriteStore` -- pgvector. Its "index" is the ORM ``embedding``
  column the service write path already maintains, so there is nothing to
  upsert; :attr:`NoopWriteStore.available` is ``False`` and callers must not
  treat it as an indexable external store.

``qdrant_client`` is never imported at module import time; the optional package
is only touched inside :class:`QdrantWriteStore`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.artifact_vector_store import (
    ARTIFACT_COLLECTION_VERSION,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    alias_target,
    ensure_artifact_collection,
)
from persistence.qdrant_config import (
    QdrantConfig,
    build_collection_alias,
    build_collection_name,
)

logger = logging.getLogger(__name__)

__all__ = [
    "NoopWriteStore",
    "QdrantWriteStore",
    "VectorRecord",
    "VectorWriteStore",
    "build_write_store",
]


@dataclass(frozen=True)
class VectorRecord:
    """One backend-neutral record to index.

    ``dense`` is the embedding; ``text`` is the source text the store may use
    for its own sparse/BM25 representation; ``payload`` is store-agnostic
    metadata (ids, hashes, model provenance) that must survive a round trip so
    :meth:`VectorWriteStore.read_signature` can compare it on the next run.
    """

    entity_id: UUID
    dense: list[float]
    text: str
    payload: dict[str, Any]


class VectorWriteStore(Protocol):
    """The write surface :class:`~application.artifact_indexer.ArtifactIndexer` needs."""

    #: Stable backend name (``"qdrant"``, ``"pgvector"``).
    name: str
    #: ``False`` for a store whose index is maintained elsewhere (pgvector).
    available: bool

    def ensure_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str, *, dry_run: bool = False
    ) -> str:
        """Return the handle for one workspace, provisioning it unless ``dry_run``."""
        ...

    def read_signature(self, handle: str, entity_id: UUID) -> dict[str, Any] | None:
        """Return the stored payload for ``entity_id``, or ``None`` when absent."""
        ...

    def upsert(self, handle: str, record: VectorRecord) -> None:
        """Insert or replace ``record`` in ``handle``."""
        ...

    def delete(self, handle: str, entity_id: UUID) -> None:
        """Remove ``entity_id`` from ``handle``."""
        ...

    def recreate_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> str:
        """DESTRUCTIVELY rebuild one workspace's store and return its handle."""
        ...


class NoopWriteStore:
    """pgvector: the ORM column is the index, so no external write exists."""

    name = "pgvector"
    available = False

    def ensure_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str, *, dry_run: bool = False
    ) -> str:
        return ""

    def read_signature(self, handle: str, entity_id: UUID) -> dict[str, Any] | None:
        return None

    def upsert(self, handle: str, record: VectorRecord) -> None:
        return None

    def delete(self, handle: str, entity_id: UUID) -> None:
        return None

    def recreate_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> str:
        return ""


class QdrantWriteStore:
    """Qdrant implementation of :class:`VectorWriteStore`.

    ``client`` and ``models_module`` are test/seam overrides. The client is
    built lazily from the effective config when omitted, so importing this
    module never requires the optional ``qdrant_client`` package.
    """

    name = "qdrant"
    available = True

    def __init__(
        self,
        client: Any = None,
        *,
        config: QdrantConfig | None = None,
        models_module: Any = None,
    ) -> None:
        self._client = client
        self._config = config
        self._models_module = models_module
        self._ensured: set[tuple[str, str]] = set()

    # -- lazy seams ---------------------------------------------------------
    def _models(self) -> Any:
        if self._models_module is None:
            from qdrant_client import models  # lazy: optional dependency

            self._models_module = models
        return self._models_module

    def _client_or_build(self) -> Any:
        if self._client is None:
            from qdrant_client import QdrantClient  # lazy: optional dependency

            config = self._config or resolve_store_config()
            self._client = QdrantClient(
                url=config.base_url,
                api_key=config.api_key,
                timeout=config.timeout,
                prefer_grpc=config.prefer_grpc,
            )
        return self._client

    def _config_or_resolve(self) -> QdrantConfig:
        if self._config is None:
            self._config = resolve_store_config()
        return self._config

    def _collection_name(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> str:
        config = self._config_or_resolve()
        return build_collection_name(
            config.collection_prefix,
            tenant_id,
            workspace_id=workspace_id,
            scope="workspace",
            artifacts=True,
            version=ARTIFACT_COLLECTION_VERSION,
        )

    # -- VectorWriteStore ---------------------------------------------------
    def ensure_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str, *, dry_run: bool = False
    ) -> str:
        config = self._config_or_resolve()
        handle = self._collection_name(tenant_id, workspace_id)
        if dry_run:
            # Provisioning is a Qdrant write: a dry run addresses the name only.
            return handle
        key = (str(tenant_id), str(workspace_id))
        if key not in self._ensured:
            ensure_artifact_collection(
                self._client_or_build(),
                tenant_id,
                workspace_id,
                config=config,
                models_module=self._models(),
            )
            self._ensured.add(key)
        return handle

    def read_signature(self, handle: str, entity_id: UUID) -> dict[str, Any] | None:
        client = self._client_or_build()
        if not client.collection_exists(handle):
            return None
        records = client.retrieve(collection_name=handle, ids=[str(entity_id)])
        payload = getattr(records[0], "payload", None) if records else None
        return payload if isinstance(payload, dict) else None

    def upsert(self, handle: str, record: VectorRecord) -> None:
        models = self._models()
        self._client_or_build().upsert(
            collection_name=handle,
            points=[
                models.PointStruct(
                    id=str(record.entity_id),
                    vector={
                        DENSE_VECTOR_NAME: record.dense,
                        SPARSE_VECTOR_NAME: models.Document(
                            text=record.text, model="qdrant/bm25"
                        ),
                    },
                    payload=record.payload,
                )
            ],
            wait=True,
        )

    def delete(self, handle: str, entity_id: UUID) -> None:
        models = self._models()
        self._client_or_build().delete(
            collection_name=handle,
            points_selector=models.PointIdsList(points=[str(entity_id)]),
            wait=True,
        )

    def recreate_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> str:
        client = self._client_or_build()
        config = self._config_or_resolve()
        models = self._models()
        collection = self._collection_name(tenant_id, workspace_id)
        alias = build_collection_alias(
            config.collection_prefix,
            tenant_id,
            workspace_id=workspace_id,
            scope="workspace",
        )
        if client.collection_exists(collection):
            if alias_target(client, alias) == collection:
                client.update_collection_aliases(
                    change_aliases_operations=[
                        models.DeleteAliasOperation(
                            delete_alias=models.DeleteAlias(alias_name=alias)
                        )
                    ]
                )
            client.delete_collection(collection_name=collection)
        # A rebuilt collection is provisioned on the next ensure; drop the cache
        # entry so this instance does not believe the old one is still usable.
        self._ensured.discard((str(tenant_id), str(workspace_id)))
        return ensure_artifact_collection(
            client, tenant_id, workspace_id, config=config, models_module=models
        )


def resolve_store_config() -> QdrantConfig:
    """Resolve the effective artifact Qdrant config (single source of truth).

    Delegates to :func:`application.vector_backends.effective_qdrant_config`, so
    the write store, the read port and the health diagnostic can never disagree
    about which Qdrant they talk to.
    """
    from application.vector_backends import (  # lazy: avoids an import cycle
        effective_qdrant_config,
    )

    return effective_qdrant_config()


def build_write_store(name: str | None = None) -> VectorWriteStore:
    """Build the write store for ``name`` (default: the active backend).

    ``pgvector`` -- and any backend that declares no external index -- gets
    :class:`NoopWriteStore`. Unknown names fail with ``ValueError`` so a typo is
    loud rather than silently writing nowhere.
    """
    from application.vector_backends import (  # lazy: avoids an import cycle
        build_write_store as _build,
    )

    return _build(name)
