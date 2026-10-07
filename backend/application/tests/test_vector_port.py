"""Tests for ``application.vector_port`` (ADR-020 V2).

Three layers of coverage:

* **pgvector parity** -- one test per collection asserting the adapter applies
  the same tenant/workspace/embedding-null filters, closest-first ordering,
  ``exclude_id`` and ``limit`` the four pre-port sites did.
* **factory selection** -- pgvector is the default and stays the fallback, and
  Qdrant is selected ONLY under the full explicit opt-in
  (``ARTIFACT_VECTOR_BACKEND=qdrant`` + effective memory backend ``qdrant`` +
  importable package + configured effective base URL). No implicit switch.
* **Qdrant adapter unit** -- driven by a fake client (the V1
  ``memory.tests.qdrant_fakes`` doubles plus a recording client for
  ``must_not``) so the optional package is never needed in the suite. Covers the
  string->UUID id coercion and the tolerant score parsing (M1/m3), plus a
  hydration test proving a Qdrant hit resolves an ORM row. An env-gated live
  round-trip skips unless ``QDRANT_TEST_BASE_URL`` is set.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from application.search_service import _semantic_search_hits
from application.vector_port import (
    COLLECTION_ICD,
    COLLECTION_REQUIREMENT,
    COLLECTION_TRACE_LINK,
    PgVectorVectorPort,
    QdrantBackendUnavailableError,
    QdrantVectorPort,
    get_vector_port,
)
from icd.models import Icd
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, Tenant, TraceLink
from persistence.qdrant_config import build_collection_name, resolve_qdrant_config
from persistence.tests.factories import active_tenant, make_requirement, make_workspace

_DIM = EMBEDDING_VECTOR_DIMENSIONS


# ---------------------------------------------------------------------------
# pgvector parity (default/fallback adapter)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestPgVectorRequirementParity:
    def test_filters_orders_excludes_and_limits(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            near = make_requirement(ws, title="Near")
            near.embedding = [1.0] * _DIM
            near.save(update_fields=["embedding"])
            far = make_requirement(ws, title="Far")
            far.embedding = [-1.0] * _DIM
            far.save(update_fields=["embedding"])
            other_workspace = make_requirement(other_ws, title="Other workspace")
            other_workspace.embedding = [1.0] * _DIM
            other_workspace.save(update_fields=["embedding"])
            no_embedding = make_requirement(ws, title="No embedding")

            port = PgVectorVectorPort()
            base = {
                "collection": COLLECTION_REQUIREMENT,
                "query_vector": [1.0] * _DIM,
                "tenant_id": tenant.id,
                "workspace_id": ws.id,
                "workspace_field": "artifact__workspace_id",
                "limit": 50,
            }
            hits = port.query_similar(**base)
            excluded = port.query_similar(**{**base, "exclude_id": near.id})
            limited = port.query_similar(**{**base, "limit": 1})

        # `transaction=True` gives the test a clean database and every row lives
        # in this test's freshly created tenant/workspace, so the exact
        # closest-first order is deterministic even in a full-suite run.
        ids = [hit.id for hit in hits]
        assert ids == [near.id, far.id]
        assert other_workspace.id not in ids  # workspace filter holds
        assert no_embedding.id not in ids  # embedding__isnull=False holds
        assert hits[0].distance == pytest.approx(0.0, abs=1e-5)
        assert hits[1].distance > hits[0].distance
        assert [hit.id for hit in excluded] == [far.id]
        assert [hit.id for hit in limited] == [near.id]


@pytest.mark.django_db(transaction=True)
class TestPgVectorTraceLinkParity:
    def test_filters_orders_and_excludes(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            source = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            target_near = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            target_far = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            target_empty = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            # uq_tracelink_edge is (source, target, link_type): distinct targets
            # are required for multiple links from the same source.
            near = TraceLink.objects.create(
                source=source,
                target=target_near,
                link_type="references",
                embedding=[1.0] * _DIM,
            )
            far = TraceLink.objects.create(
                source=source,
                target=target_far,
                link_type="references",
                embedding=[-1.0] * _DIM,
            )
            TraceLink.objects.create(
                source=source, target=target_empty, link_type="references"
            )

            port = PgVectorVectorPort()
            hits = port.query_similar(
                collection=COLLECTION_TRACE_LINK,
                query_vector=[1.0] * _DIM,
                tenant_id=tenant.id,
                exclude_id=near.id,
                limit=50,
            )

        # Strictly tenant-scoped to this test's fresh tenant; nothing else can
        # bleed in, so the exact result is deterministic in full-suite order.
        assert [hit.id for hit in hits] == [far.id]
        assert near.id not in {hit.id for hit in hits}


@pytest.mark.django_db(transaction=True)
class TestPgVectorIcdParity:
    def test_unscoped_query_still_filters_by_explicit_tenant(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            near = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Near",
                embedding=[1.0] * _DIM,
            )
            far = Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Far",
                embedding=[-1.0] * _DIM,
            )
            Icd.objects.create(
                workspace_id=ws.id,
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="No embedding",
            )
            # A different tenant's Icd, reachable only through the unscoped
            # manager -- the adapter must still exclude it via tenant_id.
            foreign_tenant = Tenant.objects.create(
                name="Foreign", slug=f"foreign-{uuid4().hex[:8]}", is_active=True
            )
            foreign = Icd.unscoped.create(
                tenant_id=foreign_tenant.id,
                workspace_id=uuid4(),
                source_element_id=uuid4(),
                target_element_id=uuid4(),
                name="Foreign",
                embedding=[1.0] * _DIM,
            )

            port = PgVectorVectorPort()
            hits = port.query_similar(
                collection=COLLECTION_ICD,
                query_vector=[1.0] * _DIM,
                tenant_id=tenant.id,
                limit=50,
            )

        ids = [hit.id for hit in hits]
        assert ids == [near.id, far.id]
        assert foreign.id not in ids


# ---------------------------------------------------------------------------
# Factory selection / degradation
# ---------------------------------------------------------------------------


class TestGetVectorPortFactory:
    """The Qdrant artifact port is opt-in on FOUR independent conditions.

    These are plain (non-DB) tests: ``_effective_memory_backend_name`` reads
    ``SystemMemorySettings`` best-effort and falls back to ``MEMORY_BACKEND``.
    """

    @staticmethod
    def _opt_in(monkeypatch) -> None:
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", "qdrant")
        monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid")
        monkeypatch.setattr(
            "application.vector_port._qdrant_client_available", lambda: True
        )

    def test_defaults_to_pgvector_without_explicit_selector(self, monkeypatch):
        # Even with the memory backend + base URL + package in place, no
        # ARTIFACT_VECTOR_BACKEND=qdrant means pgvector (no implicit switch).
        monkeypatch.delenv("ARTIFACT_VECTOR_BACKEND", raising=False)
        monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid")
        monkeypatch.setattr(
            "application.vector_port._qdrant_client_available", lambda: True
        )
        assert isinstance(get_vector_port(), PgVectorVectorPort)

    def test_explicit_pgvector_selector_stays_pgvector(self, monkeypatch):
        self._opt_in(monkeypatch)
        monkeypatch.setenv("ARTIFACT_VECTOR_BACKEND", "pgvector")
        assert isinstance(get_vector_port(), PgVectorVectorPort)

    def test_degrades_when_memory_backend_is_not_qdrant(self, monkeypatch):
        self._opt_in(monkeypatch)
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        assert isinstance(get_vector_port(), PgVectorVectorPort)

    def test_degrades_when_qdrant_package_absent(self, monkeypatch):
        self._opt_in(monkeypatch)
        monkeypatch.setattr(
            "application.vector_port._qdrant_client_available", lambda: False
        )
        assert isinstance(get_vector_port(), PgVectorVectorPort)

    def test_degrades_when_qdrant_unconfigured(self, monkeypatch):
        self._opt_in(monkeypatch)
        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        assert not isinstance(get_vector_port(), QdrantVectorPort)

    def test_selects_qdrant_when_fully_opted_in(self, monkeypatch):
        self._opt_in(monkeypatch)
        sentinel = object()
        monkeypatch.setattr(
            "application.vector_port.QdrantVectorPort", lambda: sentinel
        )
        assert get_vector_port() is sentinel

    def test_degrades_when_qdrant_construction_fails(self, monkeypatch):
        self._opt_in(monkeypatch)

        def _boom():
            raise RuntimeError("cannot build client")

        monkeypatch.setattr("application.vector_port.QdrantVectorPort", _boom)
        assert isinstance(get_vector_port(), PgVectorVectorPort)


# ---------------------------------------------------------------------------
# Qdrant adapter unit (fake client, no package needed)
# ---------------------------------------------------------------------------


class _RecordingFilter:
    """Minimal ``models.Filter`` stand-in that keeps ``must_not``."""

    def __init__(self, must=None, must_not=None):
        self.must = list(must or [])
        self.must_not = list(must_not or [])


_RECORDING_MODELS = SimpleNamespace(
    FieldCondition=FakeQdrantModels.FieldCondition,
    MatchValue=FakeQdrantModels.MatchValue,
    Filter=_RecordingFilter,
)


def _qdrant_port(client, models_module=None) -> QdrantVectorPort:
    config = resolve_qdrant_config(
        base_url="http://qdrant.test", collection_prefix="reqlo"
    )
    return QdrantVectorPort(client=client, models_module=models_module, config=config)


class TestQdrantVectorPortUnit:
    def test_builds_scoped_filter_and_maps_distances(self):
        tenant_id = uuid4()
        workspace_id = uuid4()
        exclude_id = uuid4()
        first_entity = uuid4()
        second_entity = uuid4()
        recorded: dict = {}

        class _Client:
            def query_points(self, **kwargs):
                recorded.update(kwargs)
                return SimpleNamespace(
                    points=[
                        SimpleNamespace(
                            id="point-1",
                            payload={"entity_id": str(first_entity)},
                            score=0.8,
                        ),
                        SimpleNamespace(
                            id="point-2",
                            payload={"entity_id": str(second_entity)},
                            score=0.2,
                        ),
                    ]
                )

        port = _qdrant_port(_Client(), models_module=_RECORDING_MODELS)
        hits = port.query_similar(
            collection=COLLECTION_REQUIREMENT,
            query_vector=[0.1, 0.2, 0.3],
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            exclude_id=exclude_id,
            limit=7,
        )

        expected_collection = build_collection_name(
            "reqlo", tenant_id, workspace_id=workspace_id, scope="workspace", artifacts=True
        )
        assert recorded["collection_name"] == expected_collection
        assert recorded["limit"] == 7
        assert recorded["query"] == [0.1, 0.2, 0.3]

        must_values = {
            condition.key: condition.match.value
            for condition in recorded["query_filter"].must
        }
        assert must_values["tenant_id"] == str(tenant_id)
        assert must_values["entity_type"] == COLLECTION_REQUIREMENT
        assert must_values["workspace_id"] == str(workspace_id)
        assert [condition.key for condition in recorded["query_filter"].must_not] == [
            "entity_id"
        ]
        assert recorded["query_filter"].must_not[0].match.value == str(exclude_id)

        assert [hit.id for hit in hits] == [first_entity, second_entity]
        assert hits[0].distance == pytest.approx(0.2, abs=1e-6)
        assert hits[1].distance == pytest.approx(0.8, abs=1e-6)

    def test_requires_a_workspace_scope(self):
        port = _qdrant_port(SimpleNamespace())
        with pytest.raises(QdrantBackendUnavailableError):
            port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[0.1] * 3,
                tenant_id=uuid4(),
            )

    def test_query_against_fake_client_filters_by_entity_type(self):
        tenant_id = uuid4()
        workspace_id = uuid4()
        first_entity = uuid4()
        second_entity = uuid4()
        collection = build_collection_name(
            "reqlo", tenant_id, workspace_id=workspace_id, scope="workspace", artifacts=True
        )
        client = FakeQdrantClient()
        client.upsert(
            collection_name=collection,
            points=[
                FakeQdrantModels.PointStruct(
                    id=str(first_entity),
                    vector=[1.0, 0.0],
                    payload={
                        "entity_id": str(first_entity),
                        "entity_type": COLLECTION_REQUIREMENT,
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                    },
                ),
                FakeQdrantModels.PointStruct(
                    id=str(second_entity),
                    vector=[0.0, 1.0],
                    payload={
                        "entity_id": str(second_entity),
                        "entity_type": COLLECTION_REQUIREMENT,
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                    },
                ),
                # Wrong entity_type -> filtered out by the payload condition.
                FakeQdrantModels.PointStruct(
                    id="icd-point",
                    vector=[1.0, 0.0],
                    payload={
                        "entity_id": "icd-point",
                        "entity_type": COLLECTION_ICD,
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                    },
                ),
            ],
        )

        port = _qdrant_port(client, models_module=FakeQdrantModels)
        hits = port.query_similar(
            collection=COLLECTION_REQUIREMENT,
            query_vector=[1.0, 0.0],
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            limit=10,
        )

        assert [hit.id for hit in hits] == [first_entity, second_entity]
        assert hits[0].distance == pytest.approx(0.0, abs=1e-6)
        assert hits[1].distance == pytest.approx(1.0, abs=1e-6)

    def test_skips_missing_and_non_numeric_scores(self):
        """m3: a bad score skips the point instead of raising out of the adapter."""
        entity = uuid4()
        points = [
            SimpleNamespace(
                id="ok",
                payload={"entity_id": str(entity)},
                score=0.25,
            ),
            SimpleNamespace(id="missing", payload={"entity_id": str(uuid4())}, score=None),
            SimpleNamespace(
                id="garbage", payload={"entity_id": str(uuid4())}, score="not-a-number"
            ),
        ]
        hits = QdrantVectorPort._hits_from_points(points)
        assert [hit.id for hit in hits] == [entity]
        assert hits[0].distance == pytest.approx(0.75, abs=1e-6)

    def test_skips_non_uuid_payload_ids(self):
        """m1: a non-UUID-shaped point id cannot address an ORM row -> skip it."""
        good = uuid4()
        points = [
            SimpleNamespace(id="x", payload={"entity_id": str(good)}, score=0.9),
            SimpleNamespace(id="y", payload={"entity_id": "not-a-uuid"}, score=0.9),
        ]
        hits = QdrantVectorPort._hits_from_points(points)
        assert [hit.id for hit in hits] == [good]

    @pytest.mark.django_db(transaction=True)
    def test_hydration_resolves_rows_from_string_qdrant_ids(self):
        """M1: string ids from Qdrant must hydrate ORM rows (not be dropped)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Hydrated")
            req.embedding = [1.0] * _DIM
            req.save(update_fields=["embedding"])

            collection = build_collection_name(
                "reqlo",
                tenant.id,
                workspace_id=ws.id,
                scope="workspace",
                artifacts=True,
            )
            client = FakeQdrantClient()
            client.upsert(
                collection_name=collection,
                points=[
                    FakeQdrantModels.PointStruct(
                        id=str(req.id),
                        vector=[1.0] * _DIM,
                        payload={
                            "entity_id": str(req.id),
                            "entity_type": COLLECTION_REQUIREMENT,
                            "tenant_id": str(tenant.id),
                            "workspace_id": str(ws.id),
                        },
                    )
                ],
            )
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0] * _DIM,
                tenant_id=tenant.id,
                workspace_id=ws.id,
                limit=10,
            )
            # The adapter coerces the string payload id to UUID ...
            assert isinstance(hits[0].id, UUID)
            assert [hit.id for hit in hits] == [req.id]
            # ... so the search hydration (rows keyed by UUID) resolves the row.
            hydrated = _semantic_search_hits("Requirement", hits)
        assert [hit.id for hit in hydrated] == [str(req.id)]


# ---------------------------------------------------------------------------
# Optional live Qdrant round-trip (skipped unless explicitly configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_qdrant_roundtrip_is_skipped_without_env():
    base_url = os.environ.get("QDRANT_TEST_BASE_URL", "").strip()
    if not base_url:
        pytest.skip("QDRANT_TEST_BASE_URL not set -- live Qdrant not available")

    qdrant_client = pytest.importorskip("qdrant_client")

    tenant_id = uuid4()
    workspace_id = uuid4()
    entity_id = uuid4()
    collection = build_collection_name(
        "reqlo", tenant_id, workspace_id=workspace_id, scope="workspace", artifacts=True
    )
    client = qdrant_client.QdrantClient(url=base_url)
    client.recreate_collection(
        collection_name=collection,
        vectors_config=qdrant_client.models.VectorParams(size=3, distance="Cosine"),
    )
    try:
        client.upsert(
            collection_name=collection,
            points=[
                qdrant_client.models.PointStruct(
                    id=str(entity_id),
                    vector=[1.0, 0.0, 0.0],
                    payload={
                        "entity_id": str(entity_id),
                        "entity_type": COLLECTION_REQUIREMENT,
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                    },
                )
            ],
            wait=True,
        )
        port = _qdrant_port(client)
        hits = port.query_similar(
            collection=COLLECTION_REQUIREMENT,
            query_vector=[1.0, 0.0, 0.0],
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            limit=5,
        )
        assert [hit.id for hit in hits] == [entity_id]
    finally:
        client.delete_collection(collection_name=collection)
