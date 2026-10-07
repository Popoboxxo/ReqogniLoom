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

from unittest.mock import MagicMock, patch

import pytest
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.health_rest import (
    STATUS_DEGRADED,
    STATUS_DOWN,
    STATUS_OK,
    STATUS_UNKNOWN,
    SystemHealthView,
)
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
_MOCKED_QDRANT = {
    "name": "qdrant",
    "status": STATUS_UNKNOWN,
    "detail": "not_configured",
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
        patch(
            "admin_ops.health_rest._check_qdrant",
            return_value=_MOCKED_QDRANT,
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
            "memory",
            "qdrant",
        ]
        for component in body["components"]:
            assert {"name", "status", "detail"} <= set(component.keys())
            assert component["status"] in {"ok", "degraded", "down", "unknown"}

        # RFC #1002 PR B/F6: the dedicated ``memory`` component carries the
        # structured backend envelope alongside the dashboard's status.
        memory_component = next(c for c in body["components"] if c["name"] == "memory")
        assert set(memory_component.keys()) == {
            "name",
            "status",
            "detail",
            "backend",
            "ok",
            "degraded",
            "digest_available",
            "ask_available",
            "derivation_status",
        }
        assert isinstance(memory_component["degraded"], bool)
        assert isinstance(memory_component["digest_available"], bool)
        assert isinstance(memory_component["ask_available"], bool)
        # AP-B5.1 (#1155): the scope-less derivation capability is a status
        # word from the shared enum, never user data.
        assert memory_component["derivation_status"] in {
            "ok",
            "none",
            "failed",
            "unsupported",
            "unknown",
        }

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
            patch(
                "admin_ops.health_rest._check_qdrant",
                return_value=_MOCKED_QDRANT,
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

    def test_check_llm_provider_reports_down_on_auth_failure(self, settings) -> None:
        """R5/R7: a real probe call must surface a bad API key, not 'ok'.

        Regression test for the live audit finding (systemaudit 2026-09-02):
        /health/ reported llm_provider: ok for an entire session while every
        real call was failing with 401 -- the old check only verified that
        LLM_API_KEY was a non-empty string, never made a real call.
        """
        from admin_ops import health_rest

        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = "sk-invalid-key-for-this-test"

        fake_provider = MagicMock()
        fake_provider.complete.side_effect = Exception("authentication failed (HTTP 401)")

        with patch("llm_adapter.providers.get_provider", return_value=fake_provider):
            result = health_rest._check_llm_provider()

        assert result["name"] == "llm_provider"
        assert result["status"] != STATUS_OK
        assert "401" in result["detail"] or "authentication" in result["detail"].lower()

    def test_check_llm_provider_reports_ok_on_successful_probe(self, settings) -> None:
        """A real, successful probe call reports ok (not just 'key configured')."""
        from admin_ops import health_rest

        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = "sk-valid-key-for-this-test"

        fake_provider = MagicMock()
        fake_provider.complete.return_value = "pong"

        with patch("llm_adapter.providers.get_provider", return_value=fake_provider):
            result = health_rest._check_llm_provider()

        assert result["name"] == "llm_provider"
        assert result["status"] == STATUS_OK
        fake_provider.complete.assert_called_once()

    def test_llm_probe_uses_its_own_larger_timeout(self, settings) -> None:
        """Final review: the probe must NOT reuse _CHECK_TIMEOUT_S (1.0s).

        A real completion round-trip needs seconds, so a 1s budget would
        report a healthy provider as "down" on nearly every poll — the exact
        inverse of the bug this check exists to fix. The previous test only
        asserted "complete was called", never *how*, which is why this slipped
        through; assert the actual argument values here.
        """
        from admin_ops import health_rest

        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = "sk-valid-key-for-this-test"

        assert health_rest._LLM_PROBE_TIMEOUT_S > health_rest._CHECK_TIMEOUT_S

        fake_provider = MagicMock()
        fake_provider.complete.return_value = "pong"

        with patch(
            "llm_adapter.providers.get_provider", return_value=fake_provider
        ) as get_provider_mock:
            result = health_rest._check_llm_provider()

        assert result["status"] == STATUS_OK
        # The per-attempt timeout actually handed to the provider call.
        assert (
            fake_provider.complete.call_args.kwargs["timeout"]
            == health_rest._LLM_PROBE_TIMEOUT_S
        )
        # ...and the same budget on the ProviderConfig the SDK client is built from.
        cfg = get_provider_mock.call_args.args[0]
        assert cfg.timeout == health_rest._LLM_PROBE_TIMEOUT_S

    def test_llm_probe_does_not_use_shared_resilience_transport(
        self, settings
    ) -> None:
        """Final review: the probe must not book failures against the shared
        per-provider-class circuit breaker (``llm:<provider>``) that real
        traffic uses — a repeatedly-failing probe would otherwise trip that
        breaker Open and fast-fail production LLM calls.

        The fake provider mirrors the real ``_chat`` shape (every transport
        call goes through ``self._resilient``); if the probe did not
        neutralise that hook, the call would raise and the check would report
        "down".
        """
        from admin_ops import health_rest

        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = "sk-valid-key-for-this-test"

        class _FakeProvider:
            def __init__(self) -> None:
                self.completed_with: dict | None = None

            def _resilient(self, call, timeout_seconds=None):  # noqa: ANN001
                raise AssertionError(
                    "health probe routed through the shared resilience "
                    "transport / circuit breaker"
                )

            def complete(self, prompt, *, purpose="", context=None, timeout=None):  # noqa: ANN001
                self.completed_with = {"prompt": prompt, "timeout": timeout}
                # Mirrors the real providers: the transport call goes through
                # self._resilient(...).
                return self._resilient(lambda: "pong", timeout_seconds=timeout)

        fake_provider = _FakeProvider()
        with patch("llm_adapter.providers.get_provider", return_value=fake_provider):
            result = health_rest._check_llm_provider()

        assert result["status"] == STATUS_OK, result["detail"]
        assert fake_provider.completed_with == {
            "prompt": "ping",
            "timeout": health_rest._LLM_PROBE_TIMEOUT_S,
        }


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

    def test_memory_probe_timeout_is_configurable(self, settings) -> None:
        """#990: the external memory/embedding probes use HEALTH_PROBE_TIMEOUT.

        The hard 1s budget made normal embedding latency read as "AUSGEFALLEN".
        """
        from admin_ops import health_rest

        settings.HEALTH_PROBE_TIMEOUT_SECONDS = 12.5
        assert health_rest._memory_probe_timeout_s() == 12.5

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

    def test_memory_component_carries_digest_available(self) -> None:
        """F6: the admin ``memory`` row must propagate ``digest_available``.

        ``health_view()`` reports the capability flag, but the admin
        projection re-builds a fixed dict; it used to drop the key.
        """
        from admin_ops import health_rest

        payload = {
            "backend": "pgvector",
            "ok": True,
            "detail": "pgvector reachable",
            "degraded": False,
            "digest_available": True,
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["digest_available"] is True
        assert result["backend"] == "pgvector"

    def test_memory_component_defaults_digest_available_when_absent(self) -> None:
        """A partial/older payload without the flag must degrade, never 500."""
        from admin_ops import health_rest

        payload = {
            "backend": "pgvector",
            "ok": True,
            "detail": "pgvector reachable",
            "degraded": False,
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["derivation_status"] == "unknown"
        assert result["status"] == STATUS_OK


class TestSystemHealthQdrant:
    """The optional Qdrant vector backend component (ADR-020).

    Qdrant is an optional second vector backend: not being configured is not a
    failure (``unknown``, never ``ok``/``down``) and a configured-but-
    unreachable Qdrant is ``degraded`` (visible, never fatal). All probes are
    mocked so this suite stays offline.
    """

    def test_not_configured_is_unknown_not_ok_or_down(self, monkeypatch) -> None:
        from admin_ops import health_rest

        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        result = health_rest._check_qdrant()

        assert result["name"] == "qdrant"
        assert result["status"] == STATUS_UNKNOWN
        assert result["status"] not in {STATUS_OK, STATUS_DOWN}
        assert result["detail"] == "not_configured"

    def test_configured_unreachable_is_degraded_not_down(self, monkeypatch) -> None:
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend

        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid:6333")
        with patch.object(
            QdrantMemoryBackend,
            "_http_health_probe",
            return_value=(False, "qdrant unreachable: ConnectionError"),
        ):
            result = health_rest._check_qdrant()

        assert result["status"] == STATUS_DEGRADED
        assert result["status"] != STATUS_DOWN
        assert "unreachable" in result["detail"]

    def test_configured_reachable_is_ok(self, monkeypatch) -> None:
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend

        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid:6333")
        with patch.object(
            QdrantMemoryBackend,
            "_http_health_probe",
            return_value=(True, "qdrant reachable"),
        ):
            result = health_rest._check_qdrant()

        assert result["status"] == STATUS_OK

    def test_db_override_only_config_is_treated_as_configured(self, monkeypatch) -> None:
        """B1: the gate must use the EFFECTIVE config, not the env-only flag.

        A Qdrant configured solely via ``SystemMemorySettings.qdrant_base_url``
        has no ``QDRANT_BASE_URL`` env var, so the old env-only gate reported
        ``not_configured`` while ``QdrantMemoryBackend`` was actually talking to
        Qdrant -- a split-brain. The effective resolver is mocked to return a
        DB-override URL with the env deliberately empty; the check must probe
        and report the reachable result.
        """
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend
        from persistence.qdrant_config import resolve_qdrant_config

        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        effective = resolve_qdrant_config(base_url="http://qdrant.from-db:6333")

        with (
            patch(
                "memory.qdrant_backend.resolve_effective_qdrant_config",
                return_value=effective,
            ),
            patch.object(
                QdrantMemoryBackend,
                "_http_health_probe",
                return_value=(True, "qdrant reachable"),
            ) as probe,
        ):
            result = health_rest._check_qdrant()

        assert result["detail"] != "not_configured"
        assert result["status"] == STATUS_OK
        probe.assert_called_once()

    def test_db_override_only_unreachable_is_degraded_not_down(self, monkeypatch) -> None:
        """B1: a DB-override-only, unreachable Qdrant degrades -- never down."""
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend
        from persistence.qdrant_config import resolve_qdrant_config

        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        effective = resolve_qdrant_config(base_url="http://qdrant.from-db:6333")

        with (
            patch(
                "memory.qdrant_backend.resolve_effective_qdrant_config",
                return_value=effective,
            ),
            patch.object(
                QdrantMemoryBackend,
                "_http_health_probe",
                return_value=(False, "qdrant unreachable: ConnectionError"),
            ),
        ):
            result = health_rest._check_qdrant()

        assert result["detail"] != "not_configured"
        assert result["status"] == STATUS_DEGRADED
        assert result["status"] != STATUS_DOWN

    def test_empty_effective_base_url_is_not_configured(self, monkeypatch) -> None:
        """An effective config with no base URL is ``not_configured``/``unknown``.

        Guards the other half of B1: switching to the effective resolver must
        not turn a genuinely unconfigured deployment into a probe (or into
        ``ok``/``down``).
        """
        from admin_ops import health_rest
        from persistence.qdrant_config import resolve_qdrant_config

        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid:6333")
        empty = resolve_qdrant_config(base_url="")

        with patch(
            "memory.qdrant_backend.resolve_effective_qdrant_config",
            return_value=empty,
        ):
            result = health_rest._check_qdrant()

        assert result["status"] == STATUS_UNKNOWN
        assert result["status"] not in {STATUS_OK, STATUS_DOWN}
        assert result["detail"] == "not_configured"

    @pytest.mark.django_db
    def test_real_db_override_without_env_is_configured(self, monkeypatch) -> None:
        """End-to-end B1: a real ``SystemMemorySettings`` override (no mock).

        The mocked-resolver tests above prove the check *consumes* the effective
        resolver; this one proves the resolver actually feeds a DB-only Qdrant
        through to a probe, so an operator's admin-UI override is never reported
        as ``not_configured``.
        """
        from admin_ops import health_rest
        from memory.models import SystemMemorySettings
        from memory.qdrant_backend import QdrantMemoryBackend

        monkeypatch.delenv("QDRANT_BASE_URL", raising=False)
        SystemMemorySettings.objects.create(qdrant_base_url="http://qdrant.from-db:6333")

        with patch.object(
            QdrantMemoryBackend,
            "_http_health_probe",
            return_value=(True, "qdrant reachable"),
        ) as probe:
            result = health_rest._check_qdrant()

        assert result["detail"] != "not_configured"
        assert result["status"] == STATUS_OK
        probe.assert_called_once()

    def test_probe_uses_the_memory_probe_budget(self, monkeypatch, settings) -> None:
        """#990: the budget is ``_memory_probe_timeout_s()``, not a hard 1s."""
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend

        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid:6333")
        settings.HEALTH_PROBE_TIMEOUT_SECONDS = 7.5
        with patch.object(
            QdrantMemoryBackend,
            "_http_health_probe",
            return_value=(True, "qdrant reachable"),
        ) as probe:
            health_rest._check_qdrant()

        assert probe.call_args.args[0].timeout == 7.5

    def test_qdrant_backend_degraded_propagates_as_degraded(self) -> None:
        """ADR-020 §4: a failed qdrant memory backend degrades, never fails."""
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend

        fake_backend = MagicMock(spec=QdrantMemoryBackend)
        fake_backend.health_check.return_value = (False, "qdrant unreachable")
        with patch("memory.backends.get_memory_backend", return_value=fake_backend):
            result = health_rest._check_memory_backend()

        assert result["status"] == STATUS_DEGRADED
        assert result["status"] != STATUS_DOWN

    def test_qdrant_backend_ok_still_reports_ok(self) -> None:
        from admin_ops import health_rest
        from memory.qdrant_backend import QdrantMemoryBackend

        fake_backend = MagicMock(spec=QdrantMemoryBackend)
        fake_backend.health_check.return_value = (True, "qdrant reachable")
        with patch("memory.backends.get_memory_backend", return_value=fake_backend):
            result = health_rest._check_memory_backend()

        assert result["status"] == STATUS_OK

    def test_memory_component_carries_ask_available(self) -> None:
        """REQ-192: the admin ``memory`` row must propagate ``ask_available``.

        ``health_view()`` reports the capability flag, but the admin projection
        re-builds a fixed dict; it used to drop the key.
        """
        from admin_ops import health_rest

        payload = {
            "backend": "honcho",
            "ok": True,
            "detail": "honcho reachable",
            "degraded": False,
            "digest_available": True,
            "ask_available": True,
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["ask_available"] is True
        assert result["digest_available"] is True

    def test_memory_component_defaults_ask_available_when_absent(self) -> None:
        """A partial/older payload without the flag must degrade, never 500."""
        from admin_ops import health_rest

        payload = {
            "backend": "pgvector",
            "ok": True,
            "detail": "pgvector reachable",
            "degraded": False,
            "digest_available": True,
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["ask_available"] is False
        assert result["status"] == STATUS_OK

    def test_memory_component_carries_derivation_status(self) -> None:
        """AP-B5.1 (#1155): the admin ``memory`` row must propagate
        ``derivation_status`` -- the scope-less capability answer, so the
        dashboard can tell "will never derive" (pgvector) apart from
        "derivable, not probed here" (honcho) without a scope probe.
        """
        from admin_ops import health_rest

        payload = {
            "backend": "pgvector",
            "ok": True,
            "detail": "pgvector reachable",
            "degraded": False,
            "digest_available": True,
            "ask_available": False,
            "derivation_status": "unsupported",
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["derivation_status"] == "unsupported"
        assert result["backend"] == "pgvector"

    def test_memory_component_coerces_rogue_derivation_status(self) -> None:
        """S4: the row must never forward a value outside the shared enum --
        a rogue/future-version payload reads as ``unknown`` ("cannot tell"),
        exactly like the ``bool()`` coercion of the capability flags above it.
        """
        from admin_ops import health_rest

        payload = {
            "backend": "honcho",
            "ok": True,
            "detail": "honcho reachable",
            "degraded": False,
            "digest_available": True,
            "ask_available": True,
            "derivation_status": "healthy",  # not a VALID_DERIVATION_STATUSES value
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["derivation_status"] == "unknown"
        assert result["status"] == STATUS_OK

    def test_memory_component_defaults_derivation_status_when_absent(self) -> None:
        """A partial/older payload without the field must default to
        ``unknown`` -- never 500, and never a claimed capability the probe
        did not report."""
        from admin_ops import health_rest

        payload = {
            "backend": "pgvector",
            "ok": True,
            "detail": "pgvector reachable",
            "degraded": False,
            "digest_available": True,
            "ask_available": False,
        }
        with patch("memory.health.health_view", return_value=payload):
            result = health_rest._check_memory()

        assert result["derivation_status"] == "unknown"
        assert result["status"] == STATUS_OK
