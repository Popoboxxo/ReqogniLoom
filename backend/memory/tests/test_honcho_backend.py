from unittest import mock
from unittest.mock import patch
from uuid import uuid4

from memory.honcho_backend import HonchoMemoryBackend


class TestHonchoPeerNamespacing:
    def test_peer_id_is_namespaced_by_tenant(self):
        tenant_id = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        peer_id = backend._peer_id(tenant_id, user_id)
        assert peer_id == f"{tenant_id}:{user_id}"

    def test_different_tenants_same_user_id_get_different_peers(self):
        tenant_a = uuid4()
        tenant_b = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        assert backend._peer_id(tenant_a, user_id) != backend._peer_id(tenant_b, user_id)

    def test_upsert_user_scope_uses_namespaced_peer(self):
        backend = HonchoMemoryBackend()
        tenant_id = uuid4()
        user_id = uuid4()
        with patch.object(backend, "_client") as mock_client:
            backend.upsert(tenant_id, "user", user_id, "some fact")
            call_kwargs = mock_client.peers.get_or_create.call_args
            assert call_kwargs.kwargs.get("id") == f"{tenant_id}:{user_id}" or call_kwargs.args[0] == f"{tenant_id}:{user_id}"

    def test_workspace_scope_uses_namespaced_honcho_workspace(self):
        backend = HonchoMemoryBackend()
        tenant_id = uuid4()
        workspace_id = uuid4()
        honcho_ws_id = backend._workspace_id(tenant_id, workspace_id)
        assert str(tenant_id) in honcho_ws_id
        assert str(workspace_id) in honcho_ws_id


class TestHonchoMemoryBackendHealthCheck:
    def test_health_check_down_when_base_url_not_configured(self, monkeypatch):
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False
        assert "not configured" in detail.lower()

    def test_health_check_reports_down_on_connection_failure(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False

    def test_health_check_does_not_import_honcho_sdk(self, monkeypatch):
        """Guards Global Constraint: must never attempt `import honcho` (uninstalled SDK)."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        backend = HonchoMemoryBackend()
        with mock.patch.object(
            backend, "_ensure_client", side_effect=AssertionError("must not be called")
        ) as mocked:
            backend.health_check()
        mocked.assert_not_called()
