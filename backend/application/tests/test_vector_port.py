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

import logging
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from application.search_service import _semantic_search_hits
from application.vector_port import (
    COLLECTION_ICD,
    COLLECTION_REQUIREMENT,
    COLLECTION_TRACE_LINK,
    DEGRADED_CROSS_TYPE_QUERY_FAILED,
    FallbackVectorPort,
    PgVectorVectorPort,
    QdrantBackendUnavailableError,
    QdrantVectorPort,
    get_fallback_vector_port,
    get_vector_port,
    mark_request_degraded,
    serves_from_fallback,
)
from icd.models import Icd
from llm_adapter import embedding_service
from llm_adapter.embedding_service import (
    EmbeddingProviderConfig,
    MockEmbeddingProvider,
)
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, Requirement, Tenant, TraceLink
from persistence.qdrant_config import build_collection_alias, resolve_qdrant_config
from persistence.tests.factories import (
    active_tenant,
    editor_ctx,
    make_requirement,
    make_workspace,
)

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
# T-A0-6: embedding-model provenance on read (warn default / strict opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestEmbeddingModelReadComparison:
    """``EMBEDDING_MODEL_STRICT`` at the pgvector port (T-A0-6, ADR-024 O3).

    A model change that keeps the same vector width is invisible to a cosine
    query, so every vector row carries its provenance ("<provider>:<model>:<dims>").
    These two tests pin the *read* half of that contract on REAL ``Requirement``
    rows, with vectors produced by ``MockEmbeddingProvider`` and two distinct
    model ids:

    * ``strict`` drops the foreign-model row while current-model and legacy
      ``NULL`` rows stay visible;
    * ``warn`` (the default) returns a set that is identical to the unfiltered
      baseline and emits exactly ONE warning across two consecutive queries —
      the module-level "already sampled" guard.
    """

    _PROVIDER = "mock"
    _MODEL = "vector-port-current"
    _FOREIGN_MODEL = "vector-port-previous"
    _CURRENT_ID = f"{_PROVIDER}:{_MODEL}:{_DIM}"
    _FOREIGN_ID = f"{_PROVIDER}:{_FOREIGN_MODEL}:{_DIM}"

    def _configure(self, monkeypatch, mode: str) -> None:
        """Pin the effective embedding config to the two ids used below."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", self._PROVIDER)
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", self._MODEL)
        monkeypatch.setenv(embedding_service.EMBEDDING_MODEL_STRICT_ENV, mode)
        # No SystemMemorySettings row in the test DB, so the env above would
        # already win; pinning the overlay keeps the test honest if a fixture
        # ever seeds one.
        monkeypatch.setattr(embedding_service, "_apply_db_settings", lambda cfg: cfg)
        # The process-level guards are module globals: without a reset, an
        # earlier test in the same worker would silence the warn-mode warning.
        monkeypatch.setattr(embedding_service, "_foreign_model_sample_taken", False)
        monkeypatch.setattr(embedding_service, "_unknown_model_id_warned", False)

    def _provider(self) -> MockEmbeddingProvider:
        return MockEmbeddingProvider(
            EmbeddingProviderConfig(provider_name=self._PROVIDER, model_name=self._MODEL)
        )

    def _seed(self, workspace):
        """Create three embedded requirements: current, foreign, legacy NULL."""
        provider = self._provider()
        query_vector = provider.embed("near text")
        current = make_requirement(workspace, title="Current model")
        current.embedding = provider.embed("near text")
        current.embedding_model = self._CURRENT_ID
        current.save(update_fields=["embedding", "embedding_model"])

        foreign = make_requirement(workspace, title="Foreign model")
        foreign.embedding = provider.embed("foreign text")
        foreign.embedding_model = self._FOREIGN_ID
        foreign.save(update_fields=["embedding", "embedding_model"])

        legacy = make_requirement(workspace, title="Legacy row")
        legacy.embedding = provider.embed("legacy text")
        legacy.embedding_model = None
        legacy.save(update_fields=["embedding", "embedding_model"])
        return current, foreign, legacy, query_vector

    def test_strict_mode_excludes_foreign_model_rows(self, monkeypatch):
        self._configure(monkeypatch, "strict")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            current, foreign, legacy, query_vector = self._seed(ws)

            hits = PgVectorVectorPort().query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=query_vector,
                tenant_id=tenant.id,
                workspace_id=ws.id,
                workspace_field="artifact__workspace_id",
                limit=50,
            )

        ids = [hit.id for hit in hits]
        assert current.id in ids  # written by the current model
        assert legacy.id in ids  # NULL provenance stays visible in strict mode
        assert foreign.id not in ids  # the only row strict mode may drop
        assert ids[0] == current.id  # same query vector -> distance 0.0

    def test_warn_mode_keeps_rows_and_logs_once(self, monkeypatch, caplog):
        self._configure(monkeypatch, "warn")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            current, foreign, legacy, query_vector = self._seed(ws)

            # The unfiltered baseline: no provenance predicate at all.
            baseline = set(
                Requirement.objects.filter(
                    tenant_id=tenant.id,
                    artifact__workspace_id=ws.id,
                    embedding__isnull=False,
                ).values_list("id", flat=True)
            )

            port = PgVectorVectorPort()
            query = {
                "collection": COLLECTION_REQUIREMENT,
                "query_vector": query_vector,
                "tenant_id": tenant.id,
                "workspace_id": ws.id,
                "workspace_field": "artifact__workspace_id",
                "limit": 50,
            }
            with caplog.at_level(
                logging.WARNING, logger="llm_adapter.embedding_service"
            ):
                first = port.query_similar(**query)
                second = port.query_similar(**query)

        first_ids = [hit.id for hit in first]
        # Byte-for-byte unchanged: same rows, same order, as without any
        # provenance comparison.
        assert set(first_ids) == baseline
        assert [hit.id for hit in second] == first_ids
        assert foreign.id in first_ids

        drift_warnings = [
            record
            for record in caplog.records
            if record.name == "llm_adapter.embedding_service"
            and record.levelno == logging.WARNING
            and "were written by a different model" in record.getMessage()
        ]
        # One WARNING for two queries -- the count runs once per process.
        assert len(drift_warnings) == 1
        message = drift_warnings[0].getMessage()
        assert "1 embedding row(s)" in message  # only `foreign` drifts
        assert self._CURRENT_ID in message


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

    def test_construction_failure_yields_degraded_fallback_for_search(self, monkeypatch):
        """Qdrant intended + not constructible == an outage, not "pgvector".

        A bare ``PgVectorVectorPort`` here reported ``degraded=False`` and made
        ``SearchService`` serve ungated pgvector hits: the same hole the runtime
        outage path closes. ``get_vector_port()`` keeps returning the bare
        adapter -- the three similarity call sites' loud-failure contract is
        unchanged.
        """
        self._opt_in(monkeypatch)

        def _boom():
            raise RuntimeError("cannot build client")

        monkeypatch.setattr("application.vector_port.QdrantVectorPort", _boom)
        port = get_fallback_vector_port()

        assert isinstance(port, FallbackVectorPort)
        assert port.degraded is True
        assert port.degraded_reason == "qdrant_unavailable"
        assert port.vector_backend == "pgvector"
        assert serves_from_fallback(port) is True  # -> SearchService gates
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


def _qdrant_port(client, models_module=None, config=None) -> QdrantVectorPort:
    config = config if config is not None else resolve_qdrant_config(
        base_url="http://qdrant.test", collection_prefix="reqlo"
    )
    return QdrantVectorPort(client=client, models_module=models_module, config=config)


def _raise_unavailable(**_kwargs):
    """Stand-in for a Qdrant client whose server is unreachable."""
    raise QdrantBackendUnavailableError("qdrant is unreachable")


def _unreachable_fallback() -> FallbackVectorPort:
    """A ``FallbackVectorPort`` whose Qdrant primary always raises an outage.

    Every Qdrant call fails before it touches the ORM, so the precedence tests
    below need no database fixture at all.
    """
    primary = QdrantVectorPort(
        client=SimpleNamespace(query_points=_raise_unavailable),
        models_module=FakeQdrantModels,
        config=resolve_qdrant_config(base_url="http://qdrant.test"),
    )
    return FallbackVectorPort(primary)


class TestQdrantVectorPortUnit:
    @pytest.mark.django_db(transaction=True)
    def test_builds_scoped_filter_and_maps_distances(self):
        # Hydration (QR-S07) makes even this request-shape test touch the ORM:
        # the two reported ids must exist as rows, otherwise they are dropped.
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            first = make_requirement(ws, title="First")
            second = make_requirement(ws, title="Second")
            exclude_id = uuid4()
            recorded: dict = {}

            class _Client:
                def query_points(self, **kwargs):
                    recorded.update(kwargs)
                    return SimpleNamespace(
                        points=[
                            SimpleNamespace(
                                id="point-1",
                                payload=_payload(tenant.id, ws.id, first.id),
                                score=0.8,
                            ),
                            SimpleNamespace(
                                id="point-2",
                                payload=_payload(tenant.id, ws.id, second.id),
                                score=0.2,
                            ),
                        ]
                    )

            port = _qdrant_port(_Client(), models_module=_RECORDING_MODELS)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[0.1, 0.2, 0.3],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                exclude_id=exclude_id,
                limit=7,
                # QR-S07: hydration is fail-closed without a caller identity.
                ctx=editor_ctx(tenant, ws),
            )

        expected_collection = _alias(tenant.id, ws.id)
        assert recorded["collection_name"] == expected_collection
        assert recorded["limit"] == 7
        assert recorded["query"] == [0.1, 0.2, 0.3]

        must_values = {
            condition.key: condition.match.value
            for condition in recorded["query_filter"].must
        }
        assert must_values["tenant_id"] == str(tenant.id)
        assert must_values["entity_type"] == COLLECTION_REQUIREMENT
        assert must_values["workspace_id"] == str(ws.id)
        assert [condition.key for condition in recorded["query_filter"].must_not] == [
            "entity_id"
        ]
        assert recorded["query_filter"].must_not[0].match.value == str(exclude_id)

        assert [hit.id for hit in hits] == [first.id, second.id]
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

    @pytest.mark.django_db(transaction=True)
    def test_query_against_fake_client_filters_by_entity_type(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            first = make_requirement(ws, title="Nearest")
            second = make_requirement(ws, title="Farther")
            collection = _alias(tenant.id, ws.id)
            client = FakeQdrantClient()
            client.upsert(
                collection_name=collection,
                points=[
                    FakeQdrantModels.PointStruct(
                        id=str(first.id),
                        vector=[1.0, 0.0],
                        payload=_payload(tenant.id, ws.id, first.id),
                    ),
                    FakeQdrantModels.PointStruct(
                        id=str(second.id),
                        vector=[0.0, 1.0],
                        payload=_payload(tenant.id, ws.id, second.id),
                    ),
                    # Wrong entity_type -> filtered out by the payload condition.
                    FakeQdrantModels.PointStruct(
                        id=str(uuid4()),
                        vector=[1.0, 0.0],
                        payload=_payload(
                            tenant.id, ws.id, uuid4(), entity_type=COLLECTION_ICD
                        ),
                    ),
                ],
            )

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                limit=10,
                # QR-S07: hydration is fail-closed without a caller identity.
                ctx=editor_ctx(tenant, ws),
            )

        assert [hit.id for hit in hits] == [first.id, second.id]
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
            ctx = editor_ctx(tenant, ws)

            collection = _alias(tenant.id, ws.id)
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
                # QR-S07: the READ gate is fail-closed without an identity.
                ctx=ctx,
            )
            # The adapter coerces the string payload id to UUID ...
            assert isinstance(hits[0].id, UUID)
            assert [hit.id for hit in hits] == [req.id]
            # ... so the search hydration (rows keyed by UUID) resolves the row.
            hydrated = _semantic_search_hits("Requirement", hits)
        assert [hit.id for hit in hydrated] == [str(req.id)]


# ---------------------------------------------------------------------------
# Hybrid (dense + BM25) query and QR-S07 hit hydration
# ---------------------------------------------------------------------------


def _alias(tenant_id, workspace_id) -> str:
    """The stable artifact alias the port reads (never the versioned name)."""
    return build_collection_alias(
        "reqlo", tenant_id, workspace_id=workspace_id, scope="workspace"
    )


def _payload(tenant_id, workspace_id, entity_id, entity_type=COLLECTION_REQUIREMENT) -> dict:
    return {
        "entity_id": str(entity_id),
        "entity_type": entity_type,
        "tenant_id": str(tenant_id),
        "workspace_id": str(workspace_id),
    }


def _seed_point(
    client,
    tenant_id,
    workspace_id,
    entity_id,
    *,
    dense,
    text,
    entity_type=COLLECTION_REQUIREMENT,
):
    client.upsert(
        collection_name=_alias(tenant_id, workspace_id),
        points=[
            FakeQdrantModels.PointStruct(
                id=str(entity_id),
                vector={
                    "dense": dense,
                    "bm25": FakeQdrantModels.Document(text=text, model="qdrant/bm25"),
                },
                payload=_payload(tenant_id, workspace_id, entity_id, entity_type),
            )
        ],
    )


class TestQdrantHybridQuery:
    """T-A2-6: hybrid query against the alias, dense-only when no ``query_text``."""

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_hybrid_uses_prefetch_and_rrf(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Mobile push notifications")
            ctx = editor_ctx(tenant, ws)
            client = FakeQdrantClient()
            _seed_point(
                client, tenant.id, ws.id, req.id,
                dense=[1.0, 0.0], text="mobile push notifications",
            )
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_text="mobile push",
                ctx=ctx,
            )
            alias = _alias(tenant.id, ws.id)

        requests = [kwargs for method, kwargs in client.calls if method == "query_points"]
        assert len(requests) == 1
        request = requests[0]
        # Readers address the alias, never a versioned collection name.
        assert request["collection_name"] == alias
        assert [leg.using for leg in request["prefetch"]] == ["dense", "bm25"]
        assert request["prefetch"][0].query == [1.0, 0.0]
        assert request["prefetch"][1].query.model == "qdrant/bm25"
        assert request["prefetch"][1].query.text == "mobile push"
        assert request["query"].fusion == "rrf"
        assert [hit.id for hit in hits] == [req.id]

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_without_query_text_stays_dense_only(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Dense only")
            ctx = editor_ctx(tenant, ws)
            client = FakeQdrantClient()
            _seed_point(client, tenant.id, ws.id, req.id, dense=[1.0, 0.0], text="dense only")
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=ctx,
            )

        request = [kwargs for method, kwargs in client.calls if method == "query_points"][0]
        assert request["prefetch"] is None
        assert request["query"] == [1.0, 0.0]
        assert [hit.id for hit in hits] == [req.id]

    @pytest.mark.django_db(transaction=True)
    def test_pgvector_ignores_query_text_bytes_identical(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            near = make_requirement(ws, title="Near")
            near.embedding = [1.0] * _DIM
            near.save(update_fields=["embedding"])
            far = make_requirement(ws, title="Far")
            far.embedding = [-1.0] * _DIM
            far.save(update_fields=["embedding"])

            query = {
                "collection": COLLECTION_REQUIREMENT,
                "query_vector": [1.0] * _DIM,
                "tenant_id": tenant.id,
                "workspace_id": ws.id,
                "workspace_field": "artifact__workspace_id",
                "limit": 50,
            }
            without_text = PgVectorVectorPort().query_similar(**query)
            with_text = PgVectorVectorPort().query_similar(**query, query_text="irrelevant")

        as_tuples = [(hit.id, hit.distance) for hit in without_text]
        assert as_tuples == [(hit.id, hit.distance) for hit in with_text]
        assert [hit.id for hit in with_text] == [near.id, far.id]

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_fused_score_keeps_order_but_is_not_a_cosine_scale(self):
        """Fused (RRF) scores are a RANK quantity -- ordering is the contract.

        With ``query_text`` the semantic leg's ``distance`` is ``1 - <fused
        score>``, not a cosine distance. The two points below have the SAME
        dense leg (so a cosine distance could not tell them apart); only the
        fused score separates them. Pinning an absolute value would pin
        Qdrant's fusion arithmetic, which is not this adapter's contract -- so
        this asserts the ordering (and that the scale demonstrably is not a
        cosine scale), never a specific number.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            both_legs = make_requirement(ws, title="Mobile push notifications")
            dense_only = make_requirement(ws, title="Unrelated billing")
            ctx = editor_ctx(tenant, ws)
            client = FakeQdrantClient()
            _seed_point(
                client, tenant.id, ws.id, both_legs.id,
                dense=[1.0, 0.0], text="mobile push notifications",
            )
            _seed_point(
                client, tenant.id, ws.id, dense_only.id,
                dense=[1.0, 0.0], text="unrelated billing",
            )
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_text="mobile push",
                ctx=ctx,
            )

        assert [hit.id for hit in hits] == [both_legs.id, dense_only.id]
        # Ordering is monotone in the port's own scale ...
        assert hits[0].distance < hits[1].distance
        # ... but that scale is not a cosine distance: identical dense legs
        # would have equal cosine distances, and the fused value falls outside
        # the [0, 2] cosine-distance range.
        assert hits[0].distance != pytest.approx(hits[1].distance)
        assert hits[0].distance < 0.0


class TestQdrantHitHydration:
    """QR-S07: Qdrant returns ids only; the ORM row is the source of truth."""

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_hit_with_foreign_workspace_payload_is_dropped(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            foreign_ws = make_workspace(tenant)
            mine = make_requirement(ws, title="Mine")
            foreign = make_requirement(foreign_ws, title="Foreign workspace row")
            ctx = editor_ctx(tenant, ws)

            client = FakeQdrantClient()
            for row in (mine, foreign):
                # The payload of BOTH points claims the caller's workspace --
                # exactly what a mis-indexed or crafted point looks like.
                _seed_point(client, tenant.id, ws.id, row.id, dense=[1.0, 0.0], text="row")

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=ctx,
            )

        ids = {hit.id for hit in hits}
        assert mine.id in ids
        assert foreign.id not in ids

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_hit_item_permission_none_is_dropped(self):
        from auth_tenancy.models import ItemPermission
        from persistence.tests.factories import ctx_for_user, make_user

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            denied = make_requirement(ws, title="Item-level denied")
            visible = make_requirement(ws, title="Visible")
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            ItemPermission.objects.create(
                tenant=tenant,
                user=user,
                workspace=ws,
                artifact_id=denied.artifact_id,
                permission_level="none",
            )

            client = FakeQdrantClient()
            for row in (denied, visible):
                _seed_point(client, tenant.id, ws.id, row.id, dense=[1.0, 0.0], text="row")

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=ctx,
            )

        ids = {hit.id for hit in hits}
        assert denied.id not in ids  # explicit "none" rule wins
        assert visible.id in ids

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_similarity_without_ctx_fails_closed(self):
        """QR-S07: no caller identity means no provable READ.

        The gate must not degrade into "unchecked" when a caller forgets the
        identity: the Qdrant path's answer is then *empty*, not the tenant/
        workspace/lifecycle-fenced set. Two of the legacy similarity callers
        (``find_similar_trace_links``, ``find_similar_icds``) are still in that
        state until PR-A21b -- this is the pinned consequence.
        """
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            row = make_requirement(ws, title="Would be found with an identity")

            client = FakeQdrantClient()
            _seed_point(client, tenant.id, ws.id, row.id, dense=[1.0, 0.0], text="row")
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            without_ctx = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
            )
            entities_without_ctx = port.query_entities(
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_vector=[1.0, 0.0],
                query_text="row",
                entity_types=[COLLECTION_REQUIREMENT],
            )
            # Sanity: the very same call WITH an identity does return the row,
            # so the empty results above are the gate, not a broken fixture.
            with_ctx = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=editor_ctx(tenant, ws),
            )

        assert without_ctx == []
        assert entities_without_ctx == []
        assert [hit.id for hit in with_ctx] == [row.id]

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_hit_with_foreign_tenant_payload_is_dropped(self):
        """QR-S07: the payload may claim the caller's tenant; the row may not.

        A point whose payload says "tenant A, workspace A" but whose entity id
        belongs to a row in tenant B must not hydrate -- the ORM lookup is
        tenant-scoped, so the payload's claim can never resurrect a foreign row.
        """
        with active_tenant() as foreign_tenant:
            foreign_ws = make_workspace(foreign_tenant)
            foreign = make_requirement(foreign_ws, title="Row of another tenant")

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            mine = make_requirement(ws, title="Mine")
            ctx = editor_ctx(tenant, ws)

            client = FakeQdrantClient()
            # The local row, indexed normally.
            _seed_point(client, tenant.id, ws.id, mine.id, dense=[1.0, 0.0], text="row")
            # A point in THIS tenant's collection whose payload claims this
            # tenant/workspace but points at the other tenant's row id.
            _seed_point(
                client, tenant.id, ws.id, foreign.id, dense=[1.0, 0.0], text="row"
            )

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=ctx,
            )

        ids = {hit.id for hit in hits}
        assert mine.id in ids
        assert foreign.id not in ids

    @pytest.mark.django_db(transaction=True)
    def test_stale_point_after_failed_delete_not_returned(self):
        from persistence.models import Artifact, LifecycleStatus

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            stale = make_requirement(ws, title="Soft-deleted row")
            live = make_requirement(ws, title="Live row")
            ctx = editor_ctx(tenant, ws)

            client = FakeQdrantClient()
            for row in (stale, live):
                _seed_point(client, tenant.id, ws.id, row.id, dense=[1.0, 0.0], text="row")
            # The delete hook never ran (or failed): the point persists.
            Artifact.objects.filter(id=stale.artifact_id).update(
                lifecycle_status=LifecycleStatus.OUTDATED
            )

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0, 0.0],
                tenant_id=tenant.id,
                workspace_id=ws.id,
                ctx=ctx,
            )

        ids = {hit.id for hit in hits}
        assert stale.id not in ids
        assert live.id in ids

    @pytest.mark.django_db(transaction=True)
    def test_query_entities_skips_superseded_main_goal_version(self):
        from persistence.models import Artifact, MainGoal

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            old_artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="MainGoal"
            )
            new_artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="MainGoal"
            )
            superseded = MainGoal.objects.create(
                tenant=tenant, artifact=old_artifact, workspace_id=ws.id,
                sequence_number=1, content="old goal", source="manual",
            )
            current = MainGoal.objects.create(
                tenant=tenant, artifact=new_artifact, workspace_id=ws.id,
                sequence_number=2, content="current goal", source="manual",
            )

            client = FakeQdrantClient()
            for row in (superseded, current):
                # A superseded version emits no DELETE event, so its point stays.
                _seed_point(
                    client, tenant.id, ws.id, row.id,
                    dense=[1.0, 0.0], text="goal", entity_type="MainGoal",
                )

            port = _qdrant_port(client, models_module=FakeQdrantModels)
            hits = port.query_entities(
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_vector=[1.0, 0.0],
                query_text="goal",
                entity_types=["MainGoal"],
                ctx=editor_ctx(tenant, ws),
            )

        ids = {hit.id for hit in hits}
        assert current.id in ids
        assert superseded.id not in ids


class TestRequirementSimilarityWiring:
    """``find_similar_requirements`` passes its identity to the port (QR-S07).

    ``ctx=ctx`` at the port call is the ONLY thing that makes the Qdrant
    adapter's READ gate run for this call site. Deleting it would leave the
    default pgvector path byte-identical (pgvector ignores ``ctx``) while the
    Qdrant path silently served an item-level ``none`` hit -- so this pins the
    WIRING, not merely the gate it triggers.
    """

    @pytest.mark.django_db(transaction=True)
    def test_item_denied_similar_requirement_is_absent(self, monkeypatch):
        from auth_tenancy.models import ItemPermission
        from persistence.tests.factories import ctx_for_user, make_user

        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            query = make_requirement(ws, title="Query requirement")
            query.embedding = [1.0] * _DIM
            query.save(update_fields=["embedding"])
            denied = make_requirement(ws, title="Denied neighbour")
            visible = make_requirement(ws, title="Visible neighbour")

            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user, workspace=ws, roles=("editor",))
            ItemPermission.objects.create(
                tenant=tenant,
                user=user,
                workspace=ws,
                artifact_id=denied.artifact_id,
                permission_level="none",
            )

            client = FakeQdrantClient()
            for row in (denied, visible):
                _seed_point(
                    client, tenant.id, ws.id, row.id, dense=[1.0] * _DIM, text="row"
                )
            port = _qdrant_port(client, models_module=FakeQdrantModels)
            monkeypatch.setattr(
                "application.requirement_service.get_vector_port", lambda: port
            )

            from application.requirement_service import RequirementService

            results = RequirementService().find_similar_requirements(
                query.id, ctx, limit=10, workspace_id=ws.id
            )

        ids = {result.id for result in results}
        assert denied.id not in ids  # the identity reached the port's READ gate
        assert visible.id in ids


class TestFallbackVectorPort:
    """T-A2-7: an outage degrades to pgvector with a request-local flag."""

    @pytest.mark.django_db(transaction=True)
    def test_qdrant_outage_falls_back_with_degraded_flag(self):
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Still found")
            req.embedding = [1.0] * _DIM
            req.save(update_fields=["embedding"])

            primary = QdrantVectorPort(
                client=SimpleNamespace(query_points=_raise_unavailable),
                models_module=FakeQdrantModels,
                config=resolve_qdrant_config(base_url="http://qdrant.test"),
            )
            port = FallbackVectorPort(primary)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0] * _DIM,
                tenant_id=tenant.id,
                workspace_id=ws.id,
                workspace_field="artifact__workspace_id",
                query_text="still found",
            )
            entities = port.query_entities(
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_vector=[1.0] * _DIM,
                query_text="still found",
                entity_types=["StakeholderNeed"],
            )

        assert [hit.id for hit in hits] == [req.id]  # pgvector served
        assert entities == []  # no cross-type semantic pass on pgvector
        assert port.degraded is True
        assert port.degraded_reason == "qdrant_unavailable"
        assert port.vector_backend == "pgvector"
        assert serves_from_fallback(port) is True

    def test_partial_cross_type_failure_is_not_a_fallback(self):
        """One flag, two questions: a healthy Qdrant is NOT serving a fallback.

        ``degraded`` alone cannot drive the QR-S07 gate -- after a cross-type
        failure a healthy Qdrant wrapper is ``degraded`` too, and gating on that
        re-hydrated hits the Qdrant adapter had already hydrated.
        """
        port = FallbackVectorPort(SimpleNamespace(vector_backend="qdrant"))
        mark_request_degraded(port, DEGRADED_CROSS_TYPE_QUERY_FAILED)

        assert port.degraded is True
        assert port.degraded_reason == "cross_type_query_failed"
        assert port.vector_backend == "qdrant"
        assert port.partial_semantics is True
        assert serves_from_fallback(port) is False

    def test_outage_after_cross_type_failure_logs_once_and_wins(self, caplog):
        """Precedence: outage > partial, and the outage WARNING is not swallowed.

        Ordering: a cross-type failure flags the request first (``degraded`` was
        already ``True``), then a real outage happens. Gating the warning on
        ``degraded`` lost that line entirely; the reason must also end up as the
        outage, never as the earlier partial one.
        """
        port = _unreachable_fallback()
        mark_request_degraded(port, DEGRADED_CROSS_TYPE_QUERY_FAILED)
        assert port.degraded_reason == "cross_type_query_failed"

        with caplog.at_level(logging.WARNING, logger="application.vector_port"):
            entities = port.query_entities(
                tenant_id=uuid4(),
                workspace_id=uuid4(),
                query_vector=[1.0] * _DIM,
                query_text="row",
                entity_types=["StakeholderNeed"],
            )

        outage_lines = [
            record
            for record in caplog.records
            if "Qdrant artifact backend unavailable" in record.getMessage()
        ]
        assert entities == []
        assert len(outage_lines) == 1  # exactly once, not lost and not doubled
        assert port.degraded is True
        assert port.degraded_reason == "qdrant_unavailable"  # outage supersedes
        assert port.vector_backend == "pgvector"
        assert serves_from_fallback(port) is True

    def test_outage_reason_survives_a_later_cross_type_failure(self):
        """The other direction: a partial reason must never overwrite the outage."""
        port = _unreachable_fallback()
        port.query_entities(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            query_vector=[1.0] * _DIM,
            query_text="row",
            entity_types=["StakeholderNeed"],
        )
        assert port.degraded_reason == "qdrant_unavailable"

        mark_request_degraded(port, DEGRADED_CROSS_TYPE_QUERY_FAILED)

        assert port.degraded is True
        assert port.degraded_reason == "qdrant_unavailable"  # not re-labelled
        assert port.vector_backend == "pgvector"
        assert port.partial_semantics is False

    @pytest.mark.django_db(transaction=True)
    def test_no_qdrant_configured_has_degraded_false_and_bytes_identical(self, monkeypatch):
        monkeypatch.delenv("ARTIFACT_VECTOR_BACKEND", raising=False)
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            req = make_requirement(ws, title="Default path")
            req.embedding = [1.0] * _DIM
            req.save(update_fields=["embedding"])

            port = get_fallback_vector_port()
            query = {
                "collection": COLLECTION_REQUIREMENT,
                "query_vector": [1.0] * _DIM,
                "tenant_id": tenant.id,
                "workspace_id": ws.id,
                "workspace_field": "artifact__workspace_id",
            }
            fallback_hits = port.query_similar(**query, query_text="ignored")
            plain_hits = get_vector_port().query_similar(**query)

        assert isinstance(port, PgVectorVectorPort)  # no wrapper without Qdrant
        assert port.degraded is False
        assert port.degraded_reason == ""
        assert port.vector_backend == "pgvector"
        assert [(h.id, h.distance) for h in fallback_hits] == [
            (h.id, h.distance) for h in plain_hits
        ]
        assert [hit.id for hit in fallback_hits] == [req.id]


# ---------------------------------------------------------------------------
# Optional live Qdrant round-trip (skipped unless explicitly configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_live_qdrant_roundtrip_is_skipped_without_env():
    base_url = os.environ.get("QDRANT_TEST_BASE_URL", "").strip()
    if not base_url:
        pytest.skip("QDRANT_TEST_BASE_URL not set -- live Qdrant not available")

    qdrant_client = pytest.importorskip("qdrant_client")
    from application.artifact_vector_store import ensure_artifact_collection

    config = resolve_qdrant_config(base_url=base_url, collection_prefix="reqlo")
    client = qdrant_client.QdrantClient(url=base_url)
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        req = make_requirement(ws, title="Live hybrid round-trip")
        collection = ensure_artifact_collection(
            client, tenant.id, ws.id, config=config
        )
        try:
            client.upsert(
                collection_name=_alias(tenant.id, ws.id),
                points=[
                    qdrant_client.models.PointStruct(
                        id=str(req.id),
                        vector={
                            "dense": [1.0] * _DIM,
                            "bm25": qdrant_client.models.Document(
                                text="live hybrid round-trip", model="qdrant/bm25"
                            ),
                        },
                        payload=_payload(tenant.id, ws.id, req.id),
                    )
                ],
                wait=True,
            )
            port = _qdrant_port(client, config=config)
            hits = port.query_similar(
                collection=COLLECTION_REQUIREMENT,
                query_vector=[1.0] * _DIM,
                tenant_id=tenant.id,
                workspace_id=ws.id,
                query_text="hybrid",
                limit=5,
                ctx=editor_ctx(tenant, ws),
            )
            assert [hit.id for hit in hits] == [req.id]
        finally:
            client.delete_collection(collection_name=collection)
