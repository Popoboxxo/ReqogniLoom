"""T-A2-8 / PR-A21b: workspace scope + caller identity for ICD similarity.

``find_similar_icds`` used to have no workspace scope and no identity, so the
Qdrant adapter failed loud (it cannot address a collection without a
workspace) and its hydration gate could never check a READ. Both are wired now:

* a scope makes the Qdrant adapter address ``..._artifacts_live``;
* without a scope the call degrades to pgvector with
  ``degraded_reason="no_workspace_scope"`` instead of raising;
* ``ctx`` reaches the QR-S07 READ gate, so an item-level ``none`` rule still
  hides the hit.

req_id: REQ-L2-VS-004
leaf_id: COMP-ICD-001
"""
from __future__ import annotations

import uuid

import pytest

from icd.models import Icd
from icd.services import find_similar_icds
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

def _qdrant_port(client):
    from application.vector_port import QdrantVectorPort
    from memory.tests.qdrant_fakes import FakeQdrantModels
    from persistence.qdrant_config import resolve_qdrant_config

    return QdrantVectorPort(
        client=client,
        models_module=FakeQdrantModels,
        config=resolve_qdrant_config(
            base_url="http://qdrant.test", collection_prefix="reqlo"
        ),
    )


def _seed_icd(client, tenant_id, workspace_id, icd, *, dense):
    from memory.tests.qdrant_fakes import FakeQdrantModels
    from persistence.qdrant_config import build_collection_alias

    client.upsert(
        collection_name=build_collection_alias(
            "reqlo", tenant_id, workspace_id=workspace_id, scope="workspace"
        ),
        points=[
            FakeQdrantModels.PointStruct(
                id=str(icd.id),
                vector={
                    "dense": dense,
                    "bm25": FakeQdrantModels.Document(text="icd", model="qdrant/bm25"),
                },
                payload={
                    "entity_id": str(icd.id),
                    "entity_type": "Icd",
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                },
            )
        ],
    )


@pytest.mark.django_db(transaction=True)
class TestFindSimilarIcdsWorkspaceScope:
    def _pair(self, workspace, *, embedding):
        query = Icd.objects.create(
            workspace_id=workspace.id,
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
            name="Query ICD",
            embedding=embedding,
        )
        neighbour = Icd.objects.create(
            workspace_id=workspace.id,
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
            name="Neighbour ICD",
            embedding=embedding,
        )
        return query, neighbour

    def test_with_workspace_uses_the_qdrant_alias(self, monkeypatch):
        from memory.tests.qdrant_fakes import FakeQdrantClient
        from persistence.qdrant_config import build_collection_alias
        from persistence.tests.factories import (
            active_tenant,
            editor_ctx,
            make_workspace,
        )

        dim = EMBEDDING_VECTOR_DIMENSIONS
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            query, neighbour = self._pair(ws, embedding=[1.0] * dim)

            client = FakeQdrantClient()
            _seed_icd(client, tenant.id, ws.id, neighbour, dense=[1.0] * dim)
            monkeypatch.setattr(
                "application.vector_port.get_vector_port",
                lambda: _qdrant_port(client),
            )

            results = find_similar_icds(
                query.id,
                tenant.id,
                limit=5,
                workspace_id=ws.id,
                ctx=editor_ctx(tenant, ws),
            )
            requests = [
                kwargs for method, kwargs in client.calls if method == "query_points"
            ]
            alias = build_collection_alias(
                "reqlo", tenant.id, workspace_id=ws.id, scope="workspace"
            )

        assert [hit.icd_id for hit in results] == [neighbour.id]
        assert requests
        assert requests[0]["collection_name"] == alias

    def test_without_workspace_degrades_not_raises(self, monkeypatch):
        from application.vector_port import get_similarity_vector_port
        from memory.tests.qdrant_fakes import FakeQdrantClient
        from persistence.tests.factories import (
            active_tenant,
            editor_ctx,
            make_workspace,
        )

        dim = EMBEDDING_VECTOR_DIMENSIONS
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            query, neighbour = self._pair(ws, embedding=[1.0] * dim)

            client = FakeQdrantClient()
            _seed_icd(client, tenant.id, ws.id, neighbour, dense=[1.0] * dim)
            monkeypatch.setattr(
                "application.vector_port.get_vector_port",
                lambda: _qdrant_port(client),
            )

            results = find_similar_icds(
                query.id,
                tenant.id,
                limit=5,
                workspace_id=None,
                ctx=editor_ctx(tenant, ws),
            )
            fallback = get_similarity_vector_port(None)

        assert [hit.icd_id for hit in results] == [neighbour.id]
        assert not [
            kwargs for method, kwargs in client.calls if method == "query_points"
        ]
        assert fallback.degraded_reason == "no_workspace_scope"

    def test_item_permission_none_hides_the_hit(self, monkeypatch):
        """QR-S07: the identity reaches the port, so a ``none`` rule wins."""
        from auth_tenancy.models import ItemPermission
        from memory.tests.qdrant_fakes import FakeQdrantClient
        from persistence.models import Artifact
        from persistence.tests.factories import (
            active_tenant,
            ctx_for_user,
            make_user,
            make_workspace,
        )

        dim = EMBEDDING_VECTOR_DIMENSIONS
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))

            query = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid.uuid4(),
                target_element_id=uuid.uuid4(),
                name="Query ICD",
                embedding=[1.0] * dim,
            )

            def _icd_with_artifact(name: str) -> Icd:
                artifact = Artifact.objects.create(
                    tenant=tenant, workspace=ws, artifact_type="icd"
                )
                return Icd.objects.create(
                    workspace_id=ws.id,
                    artifact=artifact,
                    source_element_id=uuid.uuid4(),
                    target_element_id=uuid.uuid4(),
                    name=name,
                    embedding=[1.0] * dim,
                )

            visible = _icd_with_artifact("Visible ICD")
            denied = _icd_with_artifact("Denied ICD")
            ItemPermission.objects.create(
                tenant=tenant,
                user=user,
                workspace=ws,
                artifact_id=denied.artifact_id,
                permission_level="none",
            )

            client = FakeQdrantClient()
            _seed_icd(client, tenant.id, ws.id, visible, dense=[1.0] * dim)
            _seed_icd(client, tenant.id, ws.id, denied, dense=[1.0] * dim)
            monkeypatch.setattr(
                "application.vector_port.get_vector_port",
                lambda: _qdrant_port(client),
            )

            results = find_similar_icds(
                query.id, tenant.id, limit=5, workspace_id=ws.id, ctx=ctx
            )

        assert [hit.icd_id for hit in results] == [visible.id]
