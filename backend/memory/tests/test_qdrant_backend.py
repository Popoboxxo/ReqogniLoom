"""Unit tests for the optional Qdrant memory backend (ADR-020 V1).

No live Qdrant and no ``qdrant_client`` install are required: the happy paths
drive the in-memory ``FakeQdrantClient`` from :mod:`memory.tests.qdrant_fakes`,
and the degradation paths force the package "absent" via ``sys.modules`` or a
raising client. A single opt-in live test runs only when ``QDRANT_TEST_BASE_URL``
is set.
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO
from uuid import uuid4

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from memory.backends import MEMORY_BACKEND_REGISTRY
from memory.management.commands.memory_reconcile import Command
from memory.qdrant_backend import (
    QdrantMemoryBackend,
    assert_collection_dimension,
    resolve_effective_qdrant_config,
)
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Tenant
from persistence.qdrant_config import (
    QDRANT_DISTANCE_ATTRS,
    build_collection_name,
    resolve_qdrant_config,
)
from persistence.tests.factories import active_tenant, make_user, make_workspace

_TENANT_A = "11111111-1111-1111-1111-111111111111"
_TENANT_B = "22222222-2222-2222-2222-222222222222"
_WORKSPACE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_WORKSPACE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _backend_with_fake_client(monkeypatch, *, base_url: str = "http://qdrant.invalid"):
    """A backend whose Qdrant interactions hit the in-memory fake."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("QDRANT_BASE_URL", base_url)
    monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
    backend = QdrantMemoryBackend()
    backend._client = FakeQdrantClient()
    backend._models_module = FakeQdrantModels
    return backend


def _patch_qdrant_backend(monkeypatch, backend) -> None:
    """Make ``memory_reconcile``'s internal ``QdrantMemoryBackend()`` return *backend*."""
    monkeypatch.setattr(
        "memory.qdrant_backend.QdrantMemoryBackend", lambda *args, **kwargs: backend
    )


def _queue_orphan_points(backend, tenant_id, *, scope, scope_id, count):
    """Insert *count* orphan points (entry ids with no local row) into a collection."""
    collection = build_collection_name(
        backend._config.collection_prefix,
        tenant_id,
        workspace_id=scope_id if scope == "workspace" else None,
        scope=scope,
    )
    backend._client.upsert(
        collection_name=collection,
        points=[
            FakeQdrantModels.PointStruct(
                id=str(uuid4()),
                vector=[1.0, 0.0],
                payload={
                    "entry_id": str(uuid4()),
                    "scope": scope,
                    "scope_id": str(scope_id),
                    "tenant_id": str(tenant_id),
                },
            )
            for _ in range(count)
        ],
    )
    return collection


class TestQdrantCollectionIsolation:
    """The security boundary (ADR-020 §2/§5): every name is tenant-scoped."""

    def test_workspace_collection_name_is_exact(self):
        assert (
            build_collection_name("reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace")
            == f"reqlo_{_TENANT_A}_{_WORKSPACE_A}"
        )

    def test_user_collection_name_is_exact(self):
        assert (
            build_collection_name("reqlo", _TENANT_A, scope="user")
            == f"reqlo_{_TENANT_A}_user"
        )

    def test_artifacts_suffix(self):
        assert (
            build_collection_name(
                "reqlo", _TENANT_A, workspace_id=_WORKSPACE_A, scope="workspace", artifacts=True
            )
            == f"reqlo_{_TENANT_A}_{_WORKSPACE_A}_artifacts"
        )

    def test_requires_a_tenant_id(self):
        with pytest.raises(ValueError, match="tenant"):
            build_collection_name("reqlo", None, scope="user")
        with pytest.raises(ValueError, match="tenant"):
            build_collection_name("reqlo", "", workspace_id=_WORKSPACE_A, scope="workspace")

    def test_unknown_scope_is_rejected(self):
        with pytest.raises(ValueError, match="unknown memory scope"):
            build_collection_name("reqlo", _TENANT_A, scope="organization")

    def test_workspace_scope_requires_a_workspace_id(self):
        with pytest.raises(ValueError, match="workspace"):
            build_collection_name("reqlo", _TENANT_A, scope="workspace")

    def test_different_tenants_never_share_a_collection(self):
        assert build_collection_name("reqlo", _TENANT_A, scope="user") != build_collection_name(
            "reqlo", _TENANT_B, scope="user"
        )

    def test_non_uuid_tenant_is_rejected(self):
        with pytest.raises(ValueError, match="tenant id must be a UUID"):
            build_collection_name("reqlo", "TENANT:1", scope="user")

    def test_non_uuid_workspace_is_rejected(self):
        with pytest.raises(ValueError, match="workspace id must be a UUID"):
            build_collection_name("reqlo", _TENANT_A, workspace_id="WS/2", scope="workspace")

    def test_sanitizing_collision_is_prevented(self):
        # These inputs used to all fold to ``tenant_1`` -- distinct ids silently
        # sharing one collection is exactly the cross-tenant hazard. They are
        # now rejected instead of colliding.
        for value in ("TENANT:1", "tenant/1", "tenant 1"):
            with pytest.raises(ValueError):
                build_collection_name("reqlo", value, scope="user")

    def test_uppercase_uuid_is_normalized_to_one_collection(self):
        upper = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
        assert build_collection_name("reqlo", upper, scope="user") == (
            f"reqlo_{upper.lower()}_user"
        )

    @pytest.mark.django_db
    def test_query_does_not_cross_tenants(self, monkeypatch):
        """Write under tenant A and tenant B; a query under A sees only A."""
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant_a:
            user_a = make_user(tenant_a)
            tenant_b = Tenant.objects.create(
                name="Tenant B", slug=f"tenant-b-{uuid4().hex[:8]}", is_active=True
            )
            user_b = make_user(tenant_b)
            backend.write(tenant_a.id, "user", user_a.id, "alpha belongs to A")
            backend.write(tenant_b.id, "user", user_b.id, "beta belongs to B")

            results = backend.query(tenant_a.id, "user", user_a.id, "belongs", top_k=10)

            assert [r.content for r in results] == ["alpha belongs to A"]
            # Two distinct collections: the name IS the isolation boundary.
            assert len(backend._client.collections) == 2

    @pytest.mark.django_db
    def test_shared_user_collection_filters_by_scope_id(self, monkeypatch):
        """``scope="user"`` shares one collection per tenant; the payload
        ``scope_id`` filter is load-bearing: user A must not see user B."""
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user_a = make_user(tenant)
            user_b = make_user(tenant)
            backend.write(tenant.id, "user", user_a.id, "alpha user fact")
            backend.write(tenant.id, "user", user_b.id, "beta user fact")

            collection = build_collection_name("reqlo", tenant.id, scope="user")
            assert set(backend._client.collections) == {collection}
            assert len(backend._client.collections[collection]) == 2

            results = backend.query(tenant.id, "user", user_a.id, "user fact", top_k=10)

            assert [r.content for r in results] == ["alpha user fact"]

    @pytest.mark.django_db
    def test_query_without_a_tenant_raises_instead_of_returning_empty(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with pytest.raises(ValueError, match="tenant"):
            backend.query(None, "user", uuid4(), "anything")
        with pytest.raises(ValueError, match="tenant"):
            backend.query("", "workspace", uuid4(), "anything")

    @pytest.mark.django_db
    def test_query_does_not_cross_workspaces(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            ws_a = make_workspace(tenant)
            ws_b = make_workspace(tenant)
            backend.write(tenant.id, "workspace", ws_a.id, "alpha fact")
            backend.write(tenant.id, "workspace", ws_b.id, "beta fact")

            results = backend.query(tenant.id, "workspace", ws_a.id, "alpha", top_k=10)

            assert [r.content for r in results] == ["alpha fact"]
            assert len(backend._client.collections) == 2

    @pytest.mark.django_db
    def test_artifact_scope_uses_the_workspace_artifacts_collection(self, monkeypatch):
        from persistence.models import Artifact

        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            backend.write(tenant.id, "artifact", artifact.id, "artifact fact")

            name = backend._collection_name(tenant.id, "artifact", artifact.id)
            assert name.endswith("_artifacts")
            assert str(artifact.id) not in name
            results = backend.query(tenant.id, "artifact", artifact.id, "fact")
            assert [r.content for r in results] == ["artifact fact"]


class TestQdrantRegistration:
    def test_registered_under_qdrant(self):
        assert MEMORY_BACKEND_REGISTRY.get("qdrant") is QdrantMemoryBackend
        assert QdrantMemoryBackend.ask_available is False
        assert QdrantMemoryBackend.derivation_status == "unsupported"


class TestQdrantDegradation:
    """Missing package / unreachable service -> degraded, never a crash."""

    def test_health_check_reports_missing_package_without_importing_sdk(self, monkeypatch):
        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid")
        monkeypatch.setattr("memory.qdrant_backend._qdrant_client_available", lambda: False)
        backend = QdrantMemoryBackend()
        backend._client = None

        ok, detail = backend.health_check()

        assert ok is False
        assert "package" in detail

    def test_health_check_reports_unconfigured_without_a_base_url(self, monkeypatch):
        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        backend = QdrantMemoryBackend()
        backend._client = None

        ok, detail = backend.health_check()

        assert ok is False
        assert "QDRANT_BASE_URL" in detail

    def test_health_check_reports_a_raising_client_as_degraded(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        backend._client.fail_with = RuntimeError("qdrant down")

        ok, detail = backend.health_check()

        assert ok is False
        assert "failed" in detail
        health = backend.health()
        assert health.backend == "qdrant"
        assert health.degraded is True

    @pytest.mark.django_db
    def test_query_degrades_to_empty_when_package_is_absent(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid")
        monkeypatch.setitem(sys.modules, "qdrant_client", None)
        backend = QdrantMemoryBackend()
        backend._client = None
        backend._models_module = None
        with active_tenant() as tenant:
            user = make_user(tenant)
            assert backend.query(tenant.id, "user", user.id, "anything") == []

    @pytest.mark.django_db
    def test_digest_and_ask_degrade_instead_of_raising(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user = make_user(tenant)
            digest = backend.digest(tenant.id, "not-a-scope", user.id)
            answer = backend.ask(tenant.id, "user", user.id, "what?")

            assert digest.degraded is True
            assert answer.degraded is True
            assert answer.backend == "qdrant"
            assert answer.detail == "no dialectic engine"

    @pytest.mark.django_db
    def test_write_still_persists_canonically_when_qdrant_is_down(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        backend._client.fail_with = RuntimeError("qdrant down")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ref = backend.write(tenant.id, "user", user.id, "still canonical")

            assert backend.count(tenant.id, "user", user.id) == 1
            assert ref.backend_ref is None
            assert backend.health().degraded is True


class TestQdrantDimensionGuard:
    def test_assertion_raises_on_drift(self):
        with pytest.raises(ImproperlyConfigured, match="EMBEDDING_VECTOR_DIMENSIONS"):
            assert_collection_dimension(768, EMBEDDING_VECTOR_DIMENSIONS)

    def test_assertion_passes_on_match_or_unknown(self):
        assert_collection_dimension(EMBEDDING_VECTOR_DIMENSIONS, EMBEDDING_VECTOR_DIMENSIONS)
        assert_collection_dimension(None, EMBEDDING_VECTOR_DIMENSIONS)

    def test_vector_dimensions_always_mirror_the_ssot(self, monkeypatch):
        # A stray QDRANT_VECTOR_DIMENSIONS must be ignored: ADR-020 §6.
        monkeypatch.setenv("QDRANT_VECTOR_DIMENSIONS", "9999")
        assert resolve_qdrant_config().vector_dimensions == EMBEDDING_VECTOR_DIMENSIONS

    def test_existing_collection_dimension_drift_is_fail_loud(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        client = backend._client
        client.collections["stale"] = []
        client.vector_sizes["stale"] = EMBEDDING_VECTOR_DIMENSIONS + 1

        with pytest.raises(ImproperlyConfigured):
            backend._ensure_collection(client, "stale")

    def test_resolve_config_override_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("QDRANT_BASE_URL", "http://env.invalid")
        monkeypatch.setenv("QDRANT_DISTANCE", "euclid")
        config = resolve_qdrant_config(
            base_url="http://override.invalid", distance="cosine", prefer_grpc=False
        )
        assert config.base_url == "http://override.invalid"
        assert config.distance == "cosine"
        assert config.prefer_grpc is False


class TestQdrantHappyPath:
    @pytest.mark.django_db
    def test_write_then_query_round_trip(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            workspace = make_workspace(tenant)
            ref = backend.write(tenant.id, "workspace", workspace.id, "the answer is 42")

            assert ref.backend_ref == str(ref.entry_id)
            results = backend.query(tenant.id, "workspace", workspace.id, "the answer is 42")
            assert [r.entry_id for r in results] == [ref.entry_id]
            assert results[0].distance is not None

    @pytest.mark.django_db
    def test_health_is_ok_with_a_reachable_client(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        ok, _ = backend.health_check()
        assert ok is True

    @pytest.mark.django_db
    def test_delete_scope_removes_local_rows_and_points(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "one")
            backend.write(tenant.id, "user", user.id, "two")

            deleted = backend.delete_scope(tenant.id, "user", user.id)

            assert deleted == 2
            assert backend.count(tenant.id, "user", user.id) == 0
            collection = backend._collection_name(tenant.id, "user", user.id)
            assert backend._client.collections[collection] == []

    @pytest.mark.django_db
    def test_iter_scope_points_is_read_only_and_fails_open(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "one")
            points = list(backend.iter_scope_points(tenant.id, "user", user.id))
            assert len(points) == 1
            assert points[0]["entry_id"]

        backend._client.fail_with = RuntimeError("down")
        assert list(backend.iter_scope_points(uuid4(), "user", uuid4())) == []


class TestQdrantReconcileScan:
    """READ-ONLY orphan scan must not have blind spots (finding B2)."""

    @pytest.mark.django_db
    def test_scan_paginates_past_a_single_page(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        monkeypatch.setattr("memory.qdrant_backend._ORPHAN_SCAN_PAGE_SIZE", 2)
        with active_tenant() as tenant:
            user = make_user(tenant)
            _queue_orphan_points(backend, tenant.id, scope="user", scope_id=user.id, count=5)
            _patch_qdrant_backend(monkeypatch, backend)

            orphans, findings = Command._qdrant_orphans([tenant.id], None)

            assert findings == []
            assert len(orphans) == 5

    @pytest.mark.django_db
    def test_scan_finds_a_scope_without_any_surviving_local_rows(self, monkeypatch):
        """A deleted local row must not hide its orphaned Qdrant point."""
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            workspace_id = uuid4()
            _queue_orphan_points(
                backend, tenant.id, scope="workspace", scope_id=workspace_id, count=1
            )
            _patch_qdrant_backend(monkeypatch, backend)

            orphans, findings = Command._qdrant_orphans([tenant.id], None)

            assert findings == []
            assert len(orphans) == 1
            assert orphans[0]["scope"] == "workspace"
            assert orphans[0]["scope_id"] == str(workspace_id)

    @pytest.mark.django_db
    def test_local_rows_are_not_reported_as_orphans(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "mirrored")
            _patch_qdrant_backend(monkeypatch, backend)

            orphans, findings = Command._qdrant_orphans([tenant.id], None)

            assert findings == []
            assert orphans == []

    @pytest.mark.django_db
    def test_scan_reports_an_unscannable_collection(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            collection = build_collection_name("reqlo", tenant.id, scope="user")
            backend._client.create_collection(
                collection_name=collection,
                vectors_config=FakeQdrantModels.VectorParams(size=2),
            )

            def _raise(_name):
                raise RuntimeError("boom")

            monkeypatch.setattr(backend, "iter_collection_points", _raise)
            _patch_qdrant_backend(monkeypatch, backend)

            orphans, findings = Command._qdrant_orphans([tenant.id], None)

            assert orphans == []
            assert len(findings) == 1
            assert findings[0]["collection"] == collection
            assert "boom" in findings[0]["error"]

    @pytest.mark.django_db
    def test_command_report_surfaces_scan_findings_and_fails_ok(self, monkeypatch):
        backend = _backend_with_fake_client(monkeypatch)
        with active_tenant() as tenant:
            user = make_user(tenant)
            _queue_orphan_points(backend, tenant.id, scope="user", scope_id=user.id, count=1)
            _patch_qdrant_backend(monkeypatch, backend)

            out = StringIO()
            call_command(
                "memory_reconcile",
                "--backend",
                "qdrant",
                "--tenant",
                str(tenant.id),
                "--json",
                stdout=out,
            )

            report = json.loads(out.getvalue())
            assert "scan_findings" in report
            assert report["counts"]["backend_objects_without_local_row"] == 1
            assert report["ok"] is False
            # Qdrant points store no content -- the dead key must not reappear.
            assert "content_preview" not in report["backend_objects_without_local_row"][0]


class TestQdrantEffectiveConfig:
    """The frozen ``resolve_effective_qdrant_config`` interface (DB over env)."""

    @pytest.mark.django_db
    def test_db_override_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("QDRANT_BASE_URL", "http://env.invalid")
        monkeypatch.setenv("QDRANT_DISTANCE", "euclid")
        SystemMemorySettings.objects.create(
            qdrant_base_url="http://db.invalid",
            qdrant_distance="cosine",
        )

        config = resolve_effective_qdrant_config()

        assert config.base_url == "http://db.invalid"
        assert config.distance == "cosine"
        assert config.vector_dimensions == EMBEDDING_VECTOR_DIMENSIONS

    @pytest.mark.django_db
    def test_missing_row_falls_back_to_env_without_raising(self, monkeypatch):
        monkeypatch.setenv("QDRANT_BASE_URL", "http://env.invalid")
        assert resolve_effective_qdrant_config().base_url == "http://env.invalid"


class TestQdrantDistanceVocabulary:
    def test_serializer_and_backend_share_one_vocabulary(self):
        from memory.memory_rest import SystemMemorySettingsWriteSerializer

        choices = set(SystemMemorySettingsWriteSerializer().fields["qdrant_distance"].choices)
        assert choices == set(QDRANT_DISTANCE_ATTRS)
        # The alias the old serializer rejected is now accepted.
        assert "euclidean" in choices


@pytest.mark.skipif(
    not os.environ.get("QDRANT_TEST_BASE_URL"),
    reason="set QDRANT_TEST_BASE_URL to run the live Qdrant test",
)
@pytest.mark.django_db
def test_live_qdrant_round_trip(monkeypatch):
    """Opt-in: exercises a real Qdrant service when one is provided."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("QDRANT_BASE_URL", os.environ["QDRANT_TEST_BASE_URL"])
    monkeypatch.setenv("QDRANT_COLLECTION_PREFIX", f"reqlo_test_{uuid4().hex[:8]}")
    backend = QdrantMemoryBackend()
    with active_tenant() as tenant:
        user = make_user(tenant)
        ref = backend.write(tenant.id, "user", user.id, "live fact")
        assert backend.query(tenant.id, "user", user.id, "live fact")
        backend.delete_entry(tenant.id, ref.entry_id)
