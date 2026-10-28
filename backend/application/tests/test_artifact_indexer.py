"""Tests for the generic artifact indexer (T-A2-3).

Real DB rows per entity type, the signature-strict ``FakeQdrantClient`` from
:mod:`memory.tests.qdrant_fakes` and no Qdrant server: the indexer's whole job is
turning an entity row into exactly one point in the versioned ``..._artifacts_v2``
collection, so every assertion here is about that point (id, payload,
``content_sha256``, sparse half) and about how many embedding calls it cost.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from application.artifact_indexer import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    SOURCES,
    ArtifactIndexer,
    recreate_artifact_collection,
)
from llm_adapter.embedding_service import (
    current_embedding_model_id,
)
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    ChangeRequest,
    GlossaryTerm,
    Goal,
    InterviewSession,
    Issue,
    MainGoal,
    Requirement,
    Risk,
    StakeholderNeed,
    TestCase,
    TraceLink,
)
from persistence.qdrant_config import (
    build_collection_alias,
    build_collection_name,
    resolve_qdrant_config,
)
from persistence.tests.factories import active_tenant, make_workspace

_EXPECTED_SOURCES = {
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "Adr",
    "Risk",
    "Issue",
    "ChangeRequest",
    "Goal",
    "MainGoal",
    "GlossaryTerm",
    "Diagram",
    "Interview",
    "Icd",
    "TraceLink",
}


def _config():
    """An env-independent config (the DB-override resolver is not under test)."""
    return resolve_qdrant_config(
        collection_prefix="reqlo",
        distance="cosine",
        hnsw_m=16,
        hnsw_ef_construct=64,
        quantization="int8",
    )


def _make_all(tenant, workspace) -> dict[str, Any]:
    """One real row per source type, all in *workspace*."""
    from diagram.models import Diagram, DiagramType
    from icd.models import Icd

    rows: dict[str, Any] = {}

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=kind
        )

    rows["Requirement"] = Requirement.objects.create(
        tenant=tenant,
        artifact=artifact("Requirement"),
        workspace=workspace,
        title="Indexed requirement",
        description="The system shall index artifacts.",
        acceptance_criteria="Every entity has a point.",
    )
    rows["StakeholderNeed"] = StakeholderNeed.objects.create(
        tenant=tenant,
        artifact=artifact("StakeholderNeed"),
        workspace=workspace,
        title="Indexed need",
        description="Stakeholders want searchable needs.",
    )
    rows["ArchitectureElement"] = ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=artifact("ArchitectureElement"),
        workspace=workspace,
        title="Indexed element",
        description="A subsystem.",
        element_type="subsystem",
    )
    rows["TestCase"] = TestCase.objects.create(
        tenant=tenant,
        artifact=artifact("TestCase"),
        workspace=workspace,
        title="Indexed test",
        description="Verifies the indexer.",
        steps=[{"action": "call index_entity"}],
    )
    rows["Adr"] = Adr.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        title="Indexed decision",
        description="Use Qdrant.",
        decision="Adopt the artifact collection.",
    )
    rows["Risk"] = Risk.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        title="Indexed risk",
        description="Stale points.",
        mitigation_strategy="Reindex on change.",
    )
    rows["Issue"] = Issue.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        title="Indexed issue",
        description="Points can go stale.",
        tags=["search"],
    )
    rows["ChangeRequest"] = ChangeRequest.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        title="Indexed change",
        description="Add an indexer.",
        impact_assessment="Search improves.",
    )
    rows["Goal"] = Goal.objects.create(
        tenant=tenant,
        artifact=artifact("Goal"),
        workspace_id=workspace.id,
        lineage_id=uuid4(),
        sequence_number=1,
        title="Indexed goal",
        description="Find every artifact.",
    )
    rows["MainGoal"] = MainGoal.objects.create(
        tenant=tenant,
        artifact=artifact("MainGoal"),
        workspace_id=workspace.id,
        sequence_number=1,
        content="Make the whole corpus searchable.",
        source="manual",
    )
    rows["GlossaryTerm"] = GlossaryTerm.objects.create(
        tenant=tenant,
        workspace=workspace,
        term="Artifact",
        definition="Any traceable entity.",
    )
    rows["Diagram"] = Diagram.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="Indexed diagram",
        diagram_type=DiagramType.BLOCK,
        description="A block diagram.",
    )
    rows["Interview"] = InterviewSession.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        session_kind=InterviewSession.SESSION_KIND_SINGLE,
        collected_fields={"title": "Indexed interview"},
    )
    rows["Icd"] = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        source_element_id=uuid4(),
        target_element_id=uuid4(),
        name="Indexed interface",
        semantic_description="Exchanges artifact metadata.",
    )
    target = ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=artifact("ArchitectureElement"),
        workspace=workspace,
        title="Trace target",
    )
    rows["TraceLink"] = TraceLink.objects.create(
        tenant=tenant,
        source=rows["Requirement"].artifact,
        target=target.artifact,
        link_type="references",
        rationale="Points at the index.",
    )
    return rows


def _indexer(client: FakeQdrantClient) -> ArtifactIndexer:
    return ArtifactIndexer(
        client,
        models_module=FakeQdrantModels,
        config=_config(),
    )


def _collection_name(tenant_id, workspace_id) -> str:
    return build_collection_name(
        "reqlo",
        tenant_id,
        workspace_id=workspace_id,
        scope="workspace",
        artifacts=True,
        version=2,
    )


def _points(client: FakeQdrantClient, tenant_id, workspace_id) -> list:
    return client.collections[_collection_name(tenant_id, workspace_id)]


def test_sources_cover_all_fifteen_entity_types() -> None:
    assert set(SOURCES) == _EXPECTED_SOURCES
    assert "Icd" in SOURCES
    assert "TraceLink" in SOURCES


@pytest.mark.django_db
def test_each_of_15_sources_produces_one_point_with_entity_type(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()
    indexer = _indexer(client)

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        rows = _make_all(tenant, workspace)

        for entity_type, row in rows.items():
            assert indexer.index_entity(tenant.id, entity_type, row.id) == "upserted"

    points = _points(client, tenant.id, workspace.id)
    assert len(points) == len(_EXPECTED_SOURCES)

    by_type = {point.payload["entity_type"]: point for point in points}
    assert set(by_type) == _EXPECTED_SOURCES
    for entity_type, row in rows.items():
        point = by_type[entity_type]
        assert point.id == str(row.id)
        assert point.payload["entity_id"] == str(row.id)
        assert point.payload["tenant_id"] == str(tenant.id)
        assert point.payload["workspace_id"] == str(workspace.id)
        assert point.payload["point_kind"] == "artifact"
        assert len(point.payload["content_sha256"]) == 64
        assert point.payload["embedding_model"]
        assert set(point.vector) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}
        assert len(point.vector[DENSE_VECTOR_NAME]) == EMBEDDING_VECTOR_DIMENSIONS
        assert point.vector[SPARSE_VECTOR_NAME].model == "qdrant/bm25"
        assert point.vector[SPARSE_VECTOR_NAME].text


@pytest.mark.django_db
def test_second_run_skips_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Idempotent requirement",
        )

        first = _indexer(client)
        assert first.index_entity(tenant.id, "Requirement", req.id) == "upserted"
        upserts_after_first = len([c for c in client.calls if c[0] == "upsert"])

        second = _indexer(client)
        assert second.index_entity(tenant.id, "Requirement", req.id) == "skipped"
        assert second.metrics.embed_calls == 0
        assert len([c for c in client.calls if c[0] == "upsert"]) == upserts_after_first

    assert len(_points(client, tenant.id, workspace.id)) == 1


@pytest.mark.django_db
def test_changed_title_reupserts(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Original title",
        )

        assert _indexer(client).index_entity(tenant.id, "Requirement", req.id) == "upserted"
        before = _points(client, tenant.id, workspace.id)[0].payload["content_sha256"]

        req.title = "Renamed title"
        req.save(update_fields=["title"])
        changed = _indexer(client)
        assert changed.index_entity(tenant.id, "Requirement", req.id) == "upserted"
        assert changed.metrics.embed_calls == 1

    point = _points(client, tenant.id, workspace.id)[0]
    assert point.payload["content_sha256"] != before
    assert len(_points(client, tenant.id, workspace.id)) == 1


@pytest.mark.django_db
def test_reuses_stored_requirement_embedding_when_model_matches(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()
    sentinel = [0.25] * EMBEDDING_VECTOR_DIMENSIONS

    def _must_not_embed(_text: str):
        raise AssertionError("a still-valid stored embedding must be reused")

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Already embedded",
        )
        req.embedding = sentinel
        req.embedding_model = current_embedding_model_id()
        req.save(update_fields=["embedding", "embedding_model"])

        indexer = ArtifactIndexer(
            client,
            models_module=FakeQdrantModels,
            config=_config(),
            embed_text=_must_not_embed,
        )
        assert indexer.index_entity(tenant.id, "Requirement", req.id) == "upserted"

    point = _points(client, tenant.id, workspace.id)[0]
    assert [round(value, 6) for value in point.vector[DENSE_VECTOR_NAME]] == [
        round(value, 6) for value in sentinel
    ]
    assert indexer.metrics.embed_calls == 0


@pytest.mark.django_db
def test_foreign_tenant_entity_is_not_indexed(monkeypatch) -> None:
    """The indexer reads through the tenant-scoped manager, never across tenants."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant_a:
        workspace_a = make_workspace(tenant_a)
        req_a = Requirement.objects.create(
            tenant=tenant_a,
            artifact=Artifact.objects.create(
                tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
            ),
            workspace=workspace_a,
            title="Tenant A requirement",
        )

    with active_tenant() as tenant_b:
        indexer = _indexer(client)
        assert indexer.index_entity(tenant_b.id, "Requirement", req_a.id) == "failed"
        assert indexer.metrics.failed == 1
        assert not client.collections


@pytest.mark.django_db
def test_legacy_diagram_with_foreign_artifact_fails_closed(monkeypatch) -> None:
    """A workspace-less row must never borrow a foreign artifact's workspace."""
    from diagram.models import Diagram, DiagramType

    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant_b:
        workspace_b = make_workspace(tenant_b)
        foreign = Artifact.objects.create(
            tenant=tenant_b, workspace=workspace_b, artifact_type="Diagram"
        )

    with active_tenant() as tenant_a:
        make_workspace(tenant_a)
        # Legacy shape: the column predates workspace scoping, and the id is stale.
        diagram = Diagram.objects.create(
            tenant=tenant_a,
            workspace_id=None,
            artifact_id=foreign.id,
            name="Legacy diagram",
            diagram_type=DiagramType.BLOCK,
        )

        indexer = _indexer(client)
        assert indexer.index_entity(tenant_a.id, "Diagram", diagram.id) == "failed"
        assert indexer.metrics.failures == {"workspace_unresolved": 1}

    assert not client.collections


@pytest.mark.django_db
def test_stale_embedding_model_forces_reembed(monkeypatch) -> None:
    """A stored vector only counts while its ``embedding_model`` is the current one."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()
    embedded: list[str] = []
    fresh = [0.5] * EMBEDDING_VECTOR_DIMENSIONS

    def _embed(text: str) -> list[float]:
        embedded.append(text)
        return fresh

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Stale embedding",
        )
        req.embedding = [0.1] * EMBEDDING_VECTOR_DIMENSIONS
        req.embedding_model = "retired-embedding-model"
        req.save(update_fields=["embedding", "embedding_model"])

        indexer = ArtifactIndexer(
            client, models_module=FakeQdrantModels, config=_config(), embed_text=_embed
        )
        assert indexer.index_entity(tenant.id, "Requirement", req.id) == "upserted"

    assert embedded == ["Stale embedding"]
    assert indexer.metrics.embed_calls == 1
    point = _points(client, tenant.id, workspace.id)[0]
    assert [round(value, 6) for value in point.vector[DENSE_VECTOR_NAME]] == [
        round(value, 6) for value in fresh
    ]


@pytest.mark.django_db
def test_blank_text_fails_with_empty_text_reason(monkeypatch) -> None:
    """An all-blank row is a named failure, not an opaque Qdrant 500."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="",
        )

        indexer = _indexer(client)
        assert indexer.index_entity(tenant.id, "Requirement", req.id) == "failed"
        assert indexer.metrics.failed == 1
        assert indexer.metrics.failures == {"empty_text": 1}

    assert not client.collections


@pytest.mark.django_db
def test_delete_entity_removes_the_point(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Removed requirement",
        )
        indexer = _indexer(client)
        assert indexer.index_entity(tenant.id, "Requirement", req.id) == "upserted"
        assert len(_points(client, tenant.id, workspace.id)) == 1

        assert indexer.delete_entity(
            tenant.id, "Requirement", req.id, workspace_id=workspace.id
        ) == "deleted"
        assert indexer.metrics.deleted == 1
        assert _points(client, tenant.id, workspace.id) == []


@pytest.mark.django_db
def test_tracelink_point_is_not_backed_by_an_artifact(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        source = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Link source",
        )
        target = ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
            ),
            workspace=workspace,
            title="Link target",
        )
        link = TraceLink.objects.create(
            tenant=tenant,
            source=source.artifact,
            target=target.artifact,
            link_type="references",
        )

        indexer = _indexer(client)
        assert indexer.index_entity(tenant.id, "TraceLink", link.id) == "upserted"

        points = _points(client, tenant.id, workspace.id)
        assert [point.id for point in points] == [str(link.id)]
        payload = points[0].payload
        assert payload["entity_type"] == "TraceLink"
        assert payload["artifact_id"] is None


@pytest.mark.django_db
def test_recreate_artifact_collection_drops_and_rebuilds(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    client = FakeQdrantClient()

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        req = Requirement.objects.create(
            tenant=tenant,
            artifact=Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            ),
            workspace=workspace,
            title="Rebuilt requirement",
        )
        assert _indexer(client).index_entity(tenant.id, "Requirement", req.id) == "upserted"
        points = _points(client, tenant.id, workspace.id)
        assert len(points) == 1

        name = recreate_artifact_collection(
            client, tenant.id, workspace.id, config=_config(), models_module=FakeQdrantModels
        )

    alias = build_collection_alias("reqlo", tenant.id, workspace_id=workspace.id,
                                   scope="workspace")
    assert name == _collection_name(tenant.id, workspace.id)
    assert client.collections[name] == []
    assert client.aliases[alias] == name
    assert any(call[0] == "delete_collection" for call in client.calls)
