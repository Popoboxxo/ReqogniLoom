"""Generic artifact indexer for the versioned Qdrant artifact collection (T-A2-3).

``application.artifact_vector_store`` provisions one ``..._artifacts_v2``
collection per workspace; this module decides which entity becomes which point.
Fifteen sources are indexed: Requirement, StakeholderNeed, ArchitectureElement,
TestCase, Adr, Risk, Issue, ChangeRequest, Goal, MainGoal, GlossaryTerm, Diagram,
Interview (``InterviewSession``), Icd and TraceLink. Fourteen sit behind a
``persistence.Artifact`` row; ``TraceLink`` has its own table and no backing
artifact, so its workspace is the workspace of its *source* artifact.

Point: ``id`` = entity UUID; ``vector`` = ``{"dense": v, "bm25": Document(text,
model="qdrant/bm25")}``; payload = ``tenant_id, workspace_id, entity_type,
entity_id, artifact_id|None, content_sha256, embedding_model,
point_kind="artifact"``.

The stored payload is read before every upsert; an unchanged ``content_sha256``
*and* ``embedding_model`` is a skip. Requirement, TraceLink and Icd also carry a
stored pgvector column with provenance (PR-A3), reused when it matches the
current model -- no embedding call for those three while their vector is valid.
An unresolved workspace fails closed (``failed``), never guessed. Failures count
in ``IndexerMetrics.failed`` with exactly ONE ``logger.error`` per process; no
entity text and no vector is logged. Reads run inside ``TenantContext``, restored
in ``finally`` (Index §f.8); the command also arms the DB-level RLS variable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

from application.artifact_vector_store import (
    ARTIFACT_COLLECTION_VERSION,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    ensure_artifact_collection,
)
from persistence.models import Artifact
from persistence.qdrant_config import QdrantConfig, build_collection_alias, build_collection_name
from persistence.tenancy import TenantContext

logger = logging.getLogger(__name__)

#: ``point_kind`` of every point this module writes (readers filter on it).
POINT_KIND_ARTIFACT = "artifact"

IndexOutcome = Literal["upserted", "skipped", "deleted", "failed"]

#: Set once a failure has been logged: a bulk run emits one line, not one per
#: entity (the counter is the per-entity signal).
_failure_logged = False


@dataclass(frozen=True)
class SourceSpec:
    """One indexed entity type: its table, its text, and its workspace."""

    app_label: str
    model_name: str
    workspace: Callable[[Any], UUID | None]
    text_fields: tuple[str, ...] = ()
    text: Callable[[Any], str] | None = None
    select_related: tuple[str, ...] = ()

    def model(self) -> Any:
        return apps.get_model(self.app_label, self.model_name)

    def render(self, row: Any) -> str:
        return self.text(row) if self.text is not None else _fields_text(row, self.text_fields)


@dataclass
class IndexerMetrics:
    """Per-run counters; ``would_embed`` predicts a dry run's embedding cost."""

    upserted: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0
    embed_calls: int = 0
    would_embed: int = 0


def _join(*parts: Any) -> str:
    return "\n".join(str(part).strip() for part in parts if part).strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value else ""


def _fields_text(row: Any, names: tuple[str, ...]) -> str:
    """Join named attributes; lists/dicts render as sorted JSON."""
    values = (getattr(row, name, None) for name in names)
    return _join(*(_json(value) if isinstance(value, (list, dict)) else value for value in values))


def _workspace_of(row: Any) -> UUID | None:
    """The row's mirrored workspace column, else its backing artifact's."""
    workspace_id = getattr(row, "workspace_id", None)
    if workspace_id is None and getattr(row, "artifact_id", None) is not None:
        workspace_id = (Artifact.unscoped.filter(pk=row.artifact_id)
                        .values_list("workspace_id", flat=True).first())
    return workspace_id


def _artifact_label(artifact: Any) -> str:
    """Readable TraceLink endpoint id: the specialised uid, else the Artifact id.

    ``Artifact`` has no ``uid`` column, so the reverse OneToOne accessor (the
    snake_case of ``artifact_type``; ``Interview`` is the exception) is the source.
    """
    kind = getattr(artifact, "artifact_type", "") or ""
    accessor = "".join(f"_{c.lower()}" if c.isupper() else c for c in kind).lstrip("_")
    accessor = "interview_session" if accessor == "interview" else accessor
    try:
        related = getattr(artifact, accessor) if accessor else None
    except (AttributeError, ObjectDoesNotExist):
        related = None
    uid = getattr(related, "uid", None) if related is not None else None
    return str(uid or getattr(artifact, "id", ""))


def _tracelink_text(row: Any) -> str:
    endpoints = f"{_artifact_label(row.source)} → {_artifact_label(row.target)}"
    return _join(f"{row.link_type}: {endpoints}", row.rationale)


SOURCES: dict[str, SourceSpec] = {
    "Requirement": SourceSpec("persistence", "Requirement", _workspace_of,
        ("title", "description", "acceptance_criteria", "acceptance_criteria_items")),
    "StakeholderNeed": SourceSpec("persistence", "StakeholderNeed", _workspace_of,
        ("title", "description", "category", "moscow_priority")),
    "ArchitectureElement": SourceSpec("persistence", "ArchitectureElement", _workspace_of,
        ("title", "description", "element_type", "asil_level", "make_or_buy")),
    "TestCase": SourceSpec("persistence", "TestCase", _workspace_of,
        ("title", "description", "steps")),
    "Adr": SourceSpec("persistence", "Adr", _workspace_of,
        ("title", "description", "context", "decision", "consequences")),
    "Risk": SourceSpec("persistence", "Risk", _workspace_of,
        ("title", "description", "mitigation_strategy")),
    "Issue": SourceSpec("persistence", "Issue", _workspace_of, ("title", "description", "tags")),
    "ChangeRequest": SourceSpec("persistence", "ChangeRequest", _workspace_of,
        ("title", "description", "impact_assessment", "change_reason")),
    "Goal": SourceSpec("persistence", "Goal", _workspace_of, ("title", "description")),
    "MainGoal": SourceSpec("persistence", "MainGoal", _workspace_of, ("content",)),
    "GlossaryTerm": SourceSpec("persistence", "GlossaryTerm", _workspace_of,
        ("term", "definition", "synonyms", "abbreviation")),
    "Diagram": SourceSpec("diagram", "Diagram", _workspace_of,
        ("name", "description", "diagram_type")),
    "Interview": SourceSpec("persistence", "InterviewSession", _workspace_of,
        ("artifact_type", "session_kind", "collected_fields", "transcript_summary")),
    "Icd": SourceSpec("icd", "Icd", _workspace_of, ("name", "semantic_description")),
    "TraceLink": SourceSpec("persistence", "TraceLink",
        lambda row: _workspace_of(getattr(row, "source", None)),
        text=_tracelink_text, select_related=("source", "target")),
}


@contextmanager
def tenant_scope(tenant_id: UUID | str) -> Iterator[None]:
    """Arm ``TenantContext`` for *tenant_id*; restore the previous state in ``finally``."""
    was_set = TenantContext.is_set()
    previous = TenantContext.get_tenant() if was_set else None
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        if was_set and previous is not None:
            TenantContext.set_tenant(previous)
        else:
            TenantContext.clear_tenant()


def _resolve_config() -> QdrantConfig:
    from application.vector_port import _effective_qdrant_config  # lazy: one resolver

    return _effective_qdrant_config()


def _collection_name(config: QdrantConfig, tenant_id: Any, workspace_id: Any) -> str:
    return build_collection_name(config.collection_prefix, tenant_id, workspace_id=workspace_id,
                                 scope="workspace", artifacts=True,
                                 version=ARTIFACT_COLLECTION_VERSION)


class ArtifactIndexer:
    """Turns entities into points, skips unchanged ones and counts failures.

    ``client`` is a ``QdrantClient`` (or a signature-strict double in tests).
    ``models_module`` and ``config`` are test/seam overrides, ``embed_text`` is
    the embedding callable (defaults to the LLM adapter's ``generate_embedding``,
    resolved per call so the command's rate limiter can wrap it), ``dry_run``
    predicts without any Qdrant write, and ``metrics`` collects the counters.
    """

    def __init__(self, client: Any, *, models_module: Any = None,
                 config: QdrantConfig | None = None,
                 embed_text: Callable[[str], list[float] | None] | None = None,
                 dry_run: bool = False, metrics: IndexerMetrics | None = None) -> None:
        self._client = client
        self._models_module = models_module
        self._config = config
        self._embed_text = embed_text
        self._dry_run = dry_run
        self.metrics = metrics if metrics is not None else IndexerMetrics()
        self._ensured: set[tuple[str, str]] = set()

    def index_entity(
        self, tenant_id: UUID | str, entity_type: str, entity_id: Any
    ) -> IndexOutcome:
        """Index one entity into its workspace collection."""
        spec = SOURCES.get(entity_type)
        if spec is None:
            return self._fail("unknown_entity_type")
        tenant_id, entity_id = UUID(str(tenant_id)), UUID(str(entity_id))
        try:
            with tenant_scope(tenant_id):
                queryset = spec.model().objects.all()
                if spec.select_related:
                    queryset = queryset.select_related(*spec.select_related)
                row = queryset.filter(pk=entity_id).first()
                if row is None:
                    return self._fail("entity_not_found")
                workspace_id = spec.workspace(row)
                if workspace_id is None:
                    return self._fail("workspace_unresolved")

                text = spec.render(row)
                content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
                model_id = self._current_model_id()
                collection = self._collection(tenant_id, workspace_id)
                if self._is_unchanged(collection, entity_id, content_sha256, model_id):
                    self.metrics.skipped += 1
                    return "skipped"

                dense = self._dense_for(row, text, model_id)
                if dense is None and not self._dry_run:
                    return self._fail("embedding_unavailable")
                if self._dry_run:
                    self.metrics.upserted += 1
                    return "upserted"

                self._client.upsert(
                    collection_name=collection,
                    points=[self._point(
                        entity_id, row, text, dense, tenant_id, workspace_id,
                        entity_type, content_sha256, model_id,
                    )],
                    wait=True,
                )
                self.metrics.upserted += 1
                return "upserted"
        except Exception as exc:  # noqa: BLE001 - one counter, one log per process
            return self._fail(type(exc).__name__)

    def delete_entity(self, tenant_id: UUID | str, entity_type: str, entity_id: Any,
                      *, workspace_id: UUID | str | None = None) -> IndexOutcome:
        """Remove one entity's point.

        ``workspace_id`` is required when the row is already gone (the projector's
        delete path); otherwise it comes from the row. Without either the call
        fails closed instead of scanning every workspace collection.
        """
        spec = SOURCES.get(entity_type)
        if spec is None:
            return self._fail("unknown_entity_type")
        tenant_id, entity_id = UUID(str(tenant_id)), UUID(str(entity_id))
        try:
            with tenant_scope(tenant_id):
                if workspace_id is None:
                    row = spec.model().objects.filter(pk=entity_id).first()
                    workspace_id = spec.workspace(row) if row is not None else None
                if workspace_id is None:
                    return self._fail("workspace_unresolved")
                collection = self._collection(tenant_id, workspace_id)
                if not self._dry_run:
                    self._client.delete(
                        collection_name=collection,
                        points_selector=self._models().PointIdsList(points=[str(entity_id)]),
                        wait=True,
                    )
                self.metrics.deleted += 1
                return "deleted"
        except Exception as exc:  # noqa: BLE001 - see _fail
            return self._fail(type(exc).__name__)

    # -- internals ----------------------------------------------------------

    def _models(self) -> Any:
        if self._models_module is None:
            from qdrant_client import models  # lazy: optional dependency

            self._models_module = models
        return self._models_module

    def _collection(self, tenant_id: UUID, workspace_id: UUID) -> str:
        config = self._config or _resolve_config()
        self._config = config
        if self._dry_run:
            # Provisioning is a Qdrant write: a dry run addresses the name only.
            return _collection_name(config, tenant_id, workspace_id)
        key = (str(tenant_id), str(workspace_id))
        if key not in self._ensured:
            ensure_artifact_collection(
                self._client, tenant_id, workspace_id, config=config,
                models_module=self._models(),
            )
            self._ensured.add(key)
        return _collection_name(config, tenant_id, workspace_id)

    def _is_unchanged(
        self, collection: str, entity_id: UUID, content_sha256: str, model_id: str
    ) -> bool:
        if not self._client.collection_exists(collection):
            return False
        records = self._client.retrieve(collection_name=collection, ids=[str(entity_id)])
        payload = getattr(records[0], "payload", None) if records else None
        return bool(payload) and payload.get("content_sha256") == content_sha256 \
            and payload.get("embedding_model") == model_id

    def _dense_for(self, row: Any, text: str, model_id: str) -> list[float] | None:
        """Reuse the stored pgvector column when it matches, else embed."""
        vector = getattr(row, "embedding", None)
        if vector is not None and getattr(row, "embedding_model", None) == model_id:
            return [float(component) for component in vector]
        if self._dry_run:
            self.metrics.would_embed += 1
            return None
        self.metrics.embed_calls += 1
        if self._embed_text is not None:
            return self._embed_text(text)
        from llm_adapter.embedding_service import generate_embedding  # lazy: no cycle

        return generate_embedding(text)

    def _point(self, entity_id: UUID, row: Any, text: str, dense: list[float] | None,
               tenant_id: UUID, workspace_id: UUID, entity_type: str,
               content_sha256: str, model_id: str) -> Any:
        artifact_id = getattr(row, "artifact_id", None)
        return self._models().PointStruct(
            id=str(entity_id),
            vector={DENSE_VECTOR_NAME: dense,
                    SPARSE_VECTOR_NAME: self._models().Document(text=text, model="qdrant/bm25")},
            payload={"tenant_id": str(tenant_id), "workspace_id": str(workspace_id),
                     "entity_type": entity_type, "entity_id": str(entity_id),
                     "artifact_id": str(artifact_id) if artifact_id else None,
                     "content_sha256": content_sha256, "embedding_model": model_id,
                     "point_kind": POINT_KIND_ARTIFACT},
        )

    @staticmethod
    def _current_model_id() -> str:
        from llm_adapter.embedding_service import current_embedding_model_id

        return current_embedding_model_id()

    def _fail(self, reason: str) -> IndexOutcome:
        global _failure_logged
        self.metrics.failed += 1
        if not _failure_logged:
            _failure_logged = True
            logger.error("artifact vector indexing failed (%s); further failures are "
                         "counted in IndexerMetrics.failed, not logged per entity.", reason)
        return "failed"


def recreate_artifact_collection(
    client: Any, tenant_id: UUID | str, workspace_id: UUID | str, *,
    config: QdrantConfig | None = None, models_module: Any = None,
) -> str:
    """DESTRUCTIVELY rebuild one workspace's artifact collection and alias.

    Drops ``..._artifacts_v2`` and its ``..._artifacts_live`` alias, then
    provisions an empty collection. Only ``--recreate`` reaches this.
    """
    config = config if config is not None else _resolve_config()
    models = models_module
    if models is None:
        from qdrant_client import models  # lazy: optional dependency

    collection = _collection_name(config, tenant_id, workspace_id)
    alias = build_collection_alias(
        config.collection_prefix, tenant_id, workspace_id=workspace_id, scope="workspace"
    )
    if client.collection_exists(collection):
        aliases = {
            entry.alias_name: entry.collection_name
            for entry in (getattr(client.get_aliases(), "aliases", None) or [])
        }
        if aliases.get(alias) == collection:
            client.update_collection_aliases(change_aliases_operations=[
                models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))
            ])
        client.delete_collection(collection_name=collection)
    return ensure_artifact_collection(
        client, tenant_id, workspace_id, config=config, models_module=models
    )


__all__ = ["DENSE_VECTOR_NAME", "IndexOutcome", "IndexerMetrics", "POINT_KIND_ARTIFACT",
           "SOURCES", "SPARSE_VECTOR_NAME", "ArtifactIndexer", "SourceSpec",
           "recreate_artifact_collection", "tenant_scope"]
