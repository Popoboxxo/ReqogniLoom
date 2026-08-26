"""
Tests for GET /api/v1/admin/health/ — admin-only system health dashboard.

Follows the same request-construction pattern as ``test_rest.py``
(:func:`_make_request` builds a DRF ``Request`` with ``auth_context``
attached directly, matching how :class:`HasOperationPermission` reads it).

Covers:
* :class:`HasOperationPermission` denies a non-admin caller (403).
* An admin caller gets 200 with the full ``components`` + ``recent_events``
  shape.
* All infra checks (redis, celery worker/beat, mcp server) are mocked —
  this test suite never talks to a live Redis/Celery broker.
* ``recent_events`` reflects real ``AuditEntry`` rows for the active tenant.
"""
from __future__ import annotations

from unittest.mock import patch

from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.health_rest import STATUS_DOWN, STATUS_OK, STATUS_UNKNOWN, SystemHealthView
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext
from auth_tenancy.rest import HasOperationPermission

from .conftest import active_tenant

_URL = "/api/v1/admin/health/"

# Fixed, deterministic stand-ins for the infra checks so this suite never
# touches a live Redis/Celery/MCP dependency.
_MOCKED_REDIS = {"name": "redis", "status": STATUS_OK, "detail": "PING ok"}
_MOCKED_CELERY_WORKER = {
    "name": "celery_worker",
    "status": STATUS_OK,
    "detail": "1 worker(s) responding",
}
_MOCKED_CELERY_BEAT = {
    "name": "celery_beat",
    "status": "unknown",
    "detail": "0 periodic task(s) configured (process liveness not verified)",
}
_MOCKED_MCP_SERVER = {
    "name": "mcp_server",
    "status": STATUS_OK,
    "detail": "11 tool group(s), 42 tool(s) registered",
}


def _make_request(auth: AuthContext | None) -> Request:
    """Build a DRF Request for GET /api/v1/admin/health/ with auth_context attached."""
    raw = APIRequestFactory().get(_URL)
    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = auth
    request.parser_context = {"kwargs": {}, "args": (), "view": None}
    return request


def _patch_infra_checks():
    """Patch every infra-dependent check so the view never touches real infra."""
    return (
        patch("admin_ops.health_rest._check_redis", return_value=_MOCKED_REDIS),
        patch(
            "admin_ops.health_rest._check_celery_worker",
            return_value=_MOCKED_CELERY_WORKER,
        ),
        patch(
            "admin_ops.health_rest._check_celery_beat",
            return_value=_MOCKED_CELERY_BEAT,
        ),
        patch(
            "admin_ops.health_rest._check_mcp_server",
            return_value=_MOCKED_MCP_SERVER,
        ),
    )


class TestSystemHealthPermission:
    """HasOperationPermission gates GET /api/v1/admin/health/ to admins only."""

    def test_non_admin_denied(self, regular_ctx: AuthContext) -> None:
        request = _make_request(regular_ctx)
        allowed = HasOperationPermission().has_permission(request, SystemHealthView())
        assert allowed is False

    def test_no_auth_context_denied(self) -> None:
        request = _make_request(None)
        allowed = HasOperationPermission().has_permission(request, SystemHealthView())
        assert allowed is False

    def test_admin_allowed(self, admin_ctx: AuthContext) -> None:
        request = _make_request(admin_ctx)
        allowed = HasOperationPermission().has_permission(request, SystemHealthView())
        assert allowed is True


class TestSystemHealthResponseShape:
    """GET returns the components + recent_events shape for an admin caller."""

    def test_admin_gets_200_with_expected_shape(
        self, admin_ctx: AuthContext, tenant_a, monkeypatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        assert response.status_code == 200
        body = response.data
        assert "components" in body
        assert "recent_events" in body

        names = [c["name"] for c in body["components"]]
        assert names == [
            "database",
            "redis",
            "celery_worker",
            "celery_beat",
            "mcp_server",
            "llm_provider",
            "memory_embedding",
            "memory_backend",
        ]
        for component in body["components"]:
            assert set(component.keys()) == {"name", "status", "detail"}
            assert component["status"] in {"ok", "degraded", "down", "unknown"}

        # database check runs for real against the test DB and must be ok.
        db_component = next(c for c in body["components"] if c["name"] == "database")
        assert db_component["status"] == STATUS_OK

        # The mocked components come back verbatim.
        assert {c["name"]: c for c in body["components"]}["redis"] == _MOCKED_REDIS

        assert isinstance(body["recent_events"], list)

    def test_recent_events_reflects_audit_entries(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                AuditEntry.objects.create(
                    actor="user-1",
                    actor_type=AuditEntry.ACTOR_TYPE_USER,
                    op=AuditEntry.OP_CREATE,
                    entity_type="Requirement",
                    entity_id="00000000-0000-0000-0000-0000000000aa",
                    source=AuditEntry.SOURCE_REST,
                )
                AuditEntry.objects.create(
                    actor="user-2",
                    actor_type=AuditEntry.ACTOR_TYPE_USER,
                    op=AuditEntry.OP_UPDATE,
                    entity_type="Requirement",
                    entity_id="00000000-0000-0000-0000-0000000000aa",
                    source=AuditEntry.SOURCE_REST,
                )

                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        assert response.status_code == 200
        events = response.data["recent_events"]
        assert len(events) >= 2
        # Newest first.
        ops = [e["op"] for e in events[:2]]
        assert ops == ["update", "create"]
        assert events[0]["actor"] == "user-2"
        assert events[0]["entity_type"] == "Requirement"

    def test_infra_failure_reports_down_without_500(
        self, admin_ctx: AuthContext, tenant_a
    ) -> None:
        """A failing infra check must surface as a 'down' row, never a 500."""
        broken_redis = {
            "name": "redis",
            "status": STATUS_DOWN,
            "detail": "Error 111 connecting to redis:6379. Connection refused.",
        }
        patches = (
            patch("admin_ops.health_rest._check_redis", return_value=broken_redis),
            patch(
                "admin_ops.health_rest._check_celery_worker",
                return_value=_MOCKED_CELERY_WORKER,
            ),
            patch(
                "admin_ops.health_rest._check_celery_beat",
                return_value=_MOCKED_CELERY_BEAT,
            ),
            patch(
                "admin_ops.health_rest._check_mcp_server",
                return_value=_MOCKED_MCP_SERVER,
            ),
        )
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        assert response.status_code == 200
        redis_component = next(
            c for c in response.data["components"] if c["name"] == "redis"
        )
        assert redis_component["status"] == STATUS_DOWN


class TestIndividualCheckGuards:
    """Each check function must never let an exception escape (down/unknown instead)."""

    def test_check_redis_guards_connection_errors(self) -> None:
        from admin_ops import health_rest

        with patch("redis.Redis.from_url", side_effect=OSError("connection refused")):
            result = health_rest._check_redis()

        assert result["name"] == "redis"
        assert result["status"] == STATUS_DOWN

    def test_check_celery_worker_guards_broker_errors(self) -> None:
        from admin_ops import health_rest

        with patch("reqogniloom.celery.app.control") as mock_control:
            mock_control.inspect.side_effect = OSError("broker unreachable")
            result = health_rest._check_celery_worker()

        assert result["name"] == "celery_worker"
        assert result["status"] == STATUS_DOWN

    def test_check_mcp_server_reports_ok_with_real_registry(self) -> None:
        """No mocking here — the real ToolRegistry must load in-process."""
        from admin_ops import health_rest

        result = health_rest._check_mcp_server()

        assert result["name"] == "mcp_server"
        assert result["status"] == STATUS_OK
        assert "tool" in result["detail"]

    def test_check_llm_provider_defaults_to_mock_and_ok(self) -> None:
        from admin_ops import health_rest

        result = health_rest._check_llm_provider()

        assert result["name"] == "llm_provider"
        # Default settings run with LLM_PROVIDER=mock -> always ok.
        assert result["status"] == STATUS_OK


class TestSystemHealthMemoryComponents:
    """The two new memory-admin-phase-2 component checks."""

    def test_memory_embedding_ok_with_mock_provider(
        self, admin_ctx: AuthContext, tenant_a, monkeypatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        component = next(
            c for c in response.data["components"] if c["name"] == "memory_embedding"
        )
        assert component["status"] == STATUS_OK

    def test_memory_embedding_honours_the_db_override(self, tenant_a, monkeypatch) -> None:
        """The embedding check must health-check the EFFECTIVE provider.

        Regression test for I-1: it used to read ``_read_env_config()``, so
        after a SystemMemorySettings override it reported on the wrong
        provider (unlike the sibling backend check, which already resolved
        the override). Env here is deliberately unresolvable, so passing
        proves the override — not the env var — was used.
        """
        from admin_ops import health_rest
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("EMBEDDING_PROVIDER", "not-a-real-provider")
        SystemMemorySettings.objects.create(embedding_provider="mock")

        result = health_rest._check_memory_embedding()

        assert result["status"] == STATUS_OK

    def test_memory_embedding_skips_cold_load_when_override_names_a_new_model(
        self, tenant_a, monkeypatch
    ) -> None:
        """Regression test for N-1.

        I-2's fix keyed the sentence-transformers model cache by model
        name. That means the cold-load guard here must ALSO compare names,
        not just check ``_model is None`` — otherwise a worker that already
        loaded model "A" sails past the guard when a SystemMemorySettings
        override requests a different, not-yet-loaded model "B", and
        ``.embed()`` triggers a real in-request cold load. Proven here by
        installing a fake ``sentence_transformers`` module and asserting
        its constructor is never called.
        """
        import sys
        import types

        from llm_adapter.embedding_service import SentenceTransformersEmbeddingProvider
        from memory.models import SystemMemorySettings

        constructed: list[str] = []

        module = types.ModuleType("sentence_transformers")

        class _FakeSentenceTransformer:
            def __init__(self, model_name):
                constructed.append(model_name)

        module.SentenceTransformer = _FakeSentenceTransformer
        monkeypatch.setitem(sys.modules, "sentence_transformers", module)

        # Simulate a worker that already loaded model "A" by real usage.
        monkeypatch.setattr(SentenceTransformersEmbeddingProvider, "_model", object())
        monkeypatch.setattr(
            SentenceTransformersEmbeddingProvider, "_loaded_model_name", "model-a"
        )

        monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence-transformers")
        SystemMemorySettings.objects.create(
            embedding_provider="sentence-transformers", embedding_model_name="model-b"
        )

        from admin_ops import health_rest

        result = health_rest._check_memory_embedding()

        assert result["status"] == STATUS_UNKNOWN
        assert constructed == []  # no cold load was triggered

    def test_memory_backend_ok_with_pgvector(
        self, admin_ctx: AuthContext, tenant_a, monkeypatch
    ) -> None:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        patches = _patch_infra_checks()
        for p in patches:
            p.start()
        try:
            with active_tenant(tenant_a):
                request = _make_request(admin_ctx)
                response = SystemHealthView().get(request)
        finally:
            for p in patches:
                p.stop()

        component = next(
            c for c in response.data["components"] if c["name"] == "memory_backend"
        )
        assert component["status"] == STATUS_OK
