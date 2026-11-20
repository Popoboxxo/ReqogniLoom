"""Write-side port for the artifact vector store (ADR-020 extension).

The read port (:mod:`application.vector_port`) answers nearest-neighbour
queries. This module is its write-side *contract*: it owns the neutral
:class:`VectorRecord` / :class:`VectorWriteStore` surface, so
:mod:`application.artifact_indexer` can stay backend-neutral and a new store
only has to implement the protocol.

Implementations live with the backend they belong to:

* :class:`application.artifact_vector_store.QdrantWriteStore` -- the opt-in
  external store (Qdrant provisioning already lives there).
* :class:`application.vector_backends.NoopWriteStore` -- pgvector. Its "index"
  is the ORM ``embedding`` column the service write path already maintains, so
  there is nothing to upsert.

``qdrant_client`` is never imported here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from application.vector_backends import (
    NoopWriteStore,
    build_write_store as build_registered_write_store,
    effective_qdrant_config,
)

__all__ = [
    "NoopWriteStore",
    "VectorRecord",
    "VectorWriteStore",
    "build_write_store",
    "resolve_store_config",
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


def resolve_store_config() -> Any:
    """Resolve the effective artifact Qdrant config (single source of truth).

    Delegates to :func:`application.vector_backends.effective_qdrant_config`, so
    the write store, the read port and the health diagnostic can never disagree
    about which Qdrant they talk to.
    """
    return effective_qdrant_config()


def build_write_store(name: str | None = None) -> VectorWriteStore:
    """Build the write store for ``name`` (default: the active backend).

    ``pgvector`` -- and any backend that declares no external index -- gets
    :class:`NoopWriteStore`. Unknown names fail with ``ValueError`` so a typo is
    loud rather than silently writing nowhere.
    """
    return build_registered_write_store(name)
