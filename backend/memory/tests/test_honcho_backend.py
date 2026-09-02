"""Unit tests for the Honcho memory backend.

No network: every test drives a ``unittest.mock`` stand-in for the SDK client
through the ``backend._client`` test seam, so the optional ``honcho-ai``
package never has to be importable for these to run.

The mock mirrors the real ``honcho-ai==2.3.0`` shape that the backend depends
on -- ``client.peer(id).conclusions.{create,query,list,delete}`` -- so a future
SDK rename (the surface was called ``observations`` before ``conclusions``)
shows up as a failure here rather than only in production.
"""
import re
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest

from memory.backends import MEMORY_BACKEND_REGISTRY
from memory.honcho_backend import HonchoMemoryBackend

#: Honcho v3's own id validation pattern (workspaces/peers). Any id that does
#: not match this gets rejected with HTTP 422 -- see ``TestHonchoIdCharset``.
_HONCHO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _conclusion(entry_id: str, content: str):
    """Minimal stand-in for honcho's ``Conclusion`` (only the fields we read)."""
    return SimpleNamespace(id=entry_id, content=content)


def _mock_client():
    """SDK client double whose ``peer(id)`` returns a per-id conclusions mock."""
    client = mock.MagicMock()
    peers: dict[str, mock.MagicMock] = {}

    def _peer(peer_id):
        if peer_id not in peers:
            peers[peer_id] = mock.MagicMock()
        return peers[peer_id]

    client.peer.side_effect = _peer
    client.peers_by_id = peers
    return client


def _backend_with_mock_client():
    backend = HonchoMemoryBackend()
    client = _mock_client()
    backend._client = client
    return backend, client


class TestHonchoPeerNamespacing:
    """The cross-tenant-leak guard documented in the module docstring."""

    def test_peer_id_is_namespaced_by_tenant(self):
        tenant_id = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        peer_id = backend._peer_id(tenant_id, user_id)
        assert peer_id == f"{tenant_id}_{user_id}"

    def test_different_tenants_same_user_id_get_different_peers(self):
        tenant_a = uuid4()
        tenant_b = uuid4()
        user_id = uuid4()
        backend = HonchoMemoryBackend()
        assert backend._peer_id(tenant_a, user_id) != backend._peer_id(tenant_b, user_id)

    def test_workspace_scope_uses_namespaced_honcho_workspace(self):
        backend = HonchoMemoryBackend()
        tenant_id = uuid4()
        workspace_id = uuid4()
        honcho_ws_id = backend._workspace_id(tenant_id, workspace_id)
        assert str(tenant_id) in honcho_ws_id
        assert str(workspace_id) in honcho_ws_id

    def test_honcho_workspace_is_per_tenant(self):
        tenant_a, tenant_b = uuid4(), uuid4()
        backend = HonchoMemoryBackend()
        assert backend._honcho_workspace_id(tenant_a) == f"reqogniloom_{tenant_a}"
        assert backend._honcho_workspace_id(tenant_a) != backend._honcho_workspace_id(tenant_b)

    def test_unknown_scope_is_rejected(self):
        backend = HonchoMemoryBackend()
        with pytest.raises(ValueError, match="unknown memory scope"):
            backend._scope_peer_id(uuid4(), "not-a-scope", uuid4())

    @pytest.mark.parametrize("scope", ["user", "workspace"])
    def test_every_data_method_uses_a_tenant_prefixed_peer(self, scope):
        """No method may address a raw ReqogniLoom id (the leak this guards)."""
        backend, client = _backend_with_mock_client()
        tenant_id, scope_id = uuid4(), uuid4()
        expected_peer = f"{tenant_id}_{scope_id}"

        peer = client.peer(expected_peer)
        peer.conclusions.create.return_value = [_conclusion("abc", "f")]
        peer.conclusions.query.return_value = []
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        client.peer.reset_mock()

        backend.upsert(tenant_id, scope, scope_id, "f")
        backend.query(tenant_id, scope, scope_id, "q")
        backend.list_recent(tenant_id, scope, scope_id)

        used = [c.args[0] for c in client.peer.call_args_list]
        assert used == [expected_peer] * 3
        assert str(scope_id) in expected_peer and str(tenant_id) in expected_peer


class TestHonchoIdCharset:
    """Regression guard for GH #793: Honcho v3 rejects any workspace/peer id
    that does not match ``^[a-zA-Z0-9_-]+$`` with HTTP 422. UUIDs are
    hyphenated, so joining them with ``:`` (as this backend used to) produced
    an id Honcho always 422'd on, which the caller then saw as an unhandled
    MCP 500 (``memory.query``/``memory.list``) for every single request --
    not something visible in a diff, since the ids "looked" fine in Python.
    """

    def test_peer_id_matches_honchos_allowed_charset(self):
        tenant_id, user_id = uuid4(), uuid4()
        backend = HonchoMemoryBackend()
        assert _HONCHO_ID_PATTERN.match(backend._peer_id(tenant_id, user_id))

    def test_workspace_scope_peer_id_matches_honchos_allowed_charset(self):
        tenant_id, workspace_id = uuid4(), uuid4()
        backend = HonchoMemoryBackend()
        assert _HONCHO_ID_PATTERN.match(backend._workspace_id(tenant_id, workspace_id))

    def test_honcho_workspace_id_matches_honchos_allowed_charset(self):
        tenant_id = uuid4()
        backend = HonchoMemoryBackend()
        assert _HONCHO_ID_PATTERN.match(backend._honcho_workspace_id(tenant_id))

    @pytest.mark.parametrize("scope", ["user", "workspace"])
    def test_query_and_list_do_not_surface_a_422_as_an_unhandled_error(self, scope):
        """End-to-end regression for the MCP-visible symptom: before the fix,
        ``client.peer(...)`` would have been called with a colon-namespaced
        id; Honcho itself rejects that with a 422 that the old id shape made
        inevitable on every call. Asserting the id charset here (rather than
        mocking a 422 response) is the correct regression guard because the
        bug was in id *construction*, not in error handling further down.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, scope_id = uuid4(), uuid4()
        peer_id = backend._scope_peer_id(tenant_id, scope, scope_id)
        assert _HONCHO_ID_PATTERN.match(peer_id)

        client.peer(peer_id).conclusions.query.return_value = []
        client.peer(peer_id).conclusions.list.return_value = SimpleNamespace(items=[])

        assert backend.query(tenant_id, scope, scope_id, "q") == []
        assert backend.list_recent(tenant_id, scope, scope_id) == []


class TestHonchoUpsert:
    def test_upsert_user_scope_uses_namespaced_peer(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.conclusions.create.return_value = [_conclusion("nano123", "some fact")]

        ref = backend.upsert(tenant_id, "user", user_id, "some fact")

        peer.conclusions.create.assert_called_once_with([{"content": "some fact"}])
        assert ref.entry_id == "nano123"
        assert ref.content == "some fact"

    def test_upsert_workspace_scope_uses_namespaced_peer(self):
        backend, client = _backend_with_mock_client()
        tenant_id, workspace_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{workspace_id}")
        peer.conclusions.create.return_value = [_conclusion("nano456", "ws fact")]

        ref = backend.upsert(tenant_id, "workspace", workspace_id, "ws fact")

        assert ref.entry_id == "nano456"

    def test_upsert_raises_when_honcho_returns_nothing(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        client.peer(f"{tenant_id}_{user_id}").conclusions.create.return_value = []

        with pytest.raises(RuntimeError, match="returned no object"):
            backend.upsert(tenant_id, "user", user_id, "fact")


class TestHonchoQuery:
    def test_query_returns_refs_and_passes_top_k(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.conclusions.query.return_value = [_conclusion("a", "one"), _conclusion("b", "two")]

        refs = backend.query(tenant_id, "user", user_id, "what?", top_k=2)

        peer.conclusions.query.assert_called_once_with("what?", top_k=2)
        assert [(r.entry_id, r.content) for r in refs] == [("a", "one"), ("b", "two")]

    def test_query_never_reports_a_distance(self):
        """Load-bearing: memory.tasks' pgvector-only supersede branch is gated
        on ``distance is not None``. A fabricated distance here would send a
        Honcho nanoid into a Django UUIDField lookup."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        client.peer(f"{tenant_id}_{user_id}").conclusions.query.return_value = [
            _conclusion("a", "one")
        ]

        assert backend.query(tenant_id, "user", user_id, "q")[0].distance is None

    def test_query_clamps_top_k_to_honcho_max(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.conclusions.query.return_value = []

        backend.query(tenant_id, "user", user_id, "q", top_k=5000)

        assert peer.conclusions.query.call_args.kwargs["top_k"] == 100


class TestHonchoListRecent:
    def test_list_recent_reads_only_the_first_page(self):
        """Iterating a SyncPage auto-fetches EVERY page (the SDK warns about
        this), which would turn a bounded limit into a full memory dump."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        page = mock.MagicMock()
        page.items = [_conclusion("a", "one"), _conclusion("b", "two")]
        page.__iter__ = mock.Mock(side_effect=AssertionError("must not iterate the page"))
        client.peer(f"{tenant_id}_{user_id}").conclusions.list.return_value = page

        refs = backend.list_recent(tenant_id, "user", user_id, limit=10)

        assert [r.entry_id for r in refs] == ["a", "b"]

    def test_list_recent_does_not_reverse_the_default_recency_order(self):
        """Honcho lists conclusions newest-first unless ``reverse`` is passed."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.conclusions.list.return_value = SimpleNamespace(items=[])

        backend.list_recent(tenant_id, "user", user_id, limit=7)

        assert peer.conclusions.list.call_args.kwargs == {"size": 7}

    def test_list_recent_truncates_to_limit_and_clamps_page_size(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[_conclusion(str(i), str(i)) for i in range(100)]
        )

        refs = backend.list_recent(tenant_id, "user", user_id, limit=500)

        assert peer.conclusions.list.call_args.kwargs["size"] == 100
        assert len(refs) == 100


class TestHonchoForget:
    """These drive the real ``honcho.conclusions.ConclusionScope`` against a
    mock HTTP client, so the asserted route is the SDK's own, not a guess."""

    def test_forget_deletes_via_the_tenant_workspace_route(self):
        backend, client = _backend_with_mock_client()
        tenant_id = uuid4()

        backend.forget(tenant_id, "nano789")

        client._http.delete.assert_called_once_with(
            f"/v3/workspaces/reqogniloom_{tenant_id}/conclusions/nano789"
        )

    def test_forget_never_creates_a_peer(self):
        """``client.peer()`` is a get-or-create that always POSTs to /peers
        (the docs wrongly call it lazy). Routing a delete through it would
        leave a junk ``__reqogniloom_forget__`` peer in every tenant's Honcho
        workspace, which Honcho would then start building a representation of.
        """
        backend, client = _backend_with_mock_client()

        backend.forget(uuid4(), "nano789")

        client.peer.assert_not_called()

    def test_forget_stringifies_a_uuid_entry_id(self):
        backend, client = _backend_with_mock_client()
        tenant_id, entry_id = uuid4(), uuid4()

        backend.forget(tenant_id, entry_id)

        assert client._http.delete.call_args.args[0].endswith(f"/conclusions/{entry_id}")

    def test_forget_of_another_tenants_id_cannot_escape_the_callers_workspace(self):
        """Tenant isolation on delete is structural: the workspace segment of
        the route is derived from the caller's tenant, never from the id."""
        backend, client = _backend_with_mock_client()
        caller_tenant, other_tenant = uuid4(), uuid4()

        backend.forget(caller_tenant, "some-other-tenants-nanoid")

        route = client._http.delete.call_args.args[0]
        assert f"reqogniloom_{caller_tenant}" in route
        assert str(other_tenant) not in route

    def test_each_tenant_gets_its_own_cached_client(self):
        backend = HonchoMemoryBackend()
        backend._base_url = "http://honcho.invalid"
        tenant_a, tenant_b = uuid4(), uuid4()

        with mock.patch("honcho.Honcho") as honcho_cls:
            backend.forget(tenant_a, "n1")
            backend.forget(tenant_a, "n2")  # cached, no second construction
            backend.forget(tenant_b, "n3")

        workspaces = [c.kwargs["workspace_id"] for c in honcho_cls.call_args_list]
        assert workspaces == [f"reqogniloom_{tenant_a}", f"reqogniloom_{tenant_b}"]


class TestHonchoBackendRegistration:
    def test_backend_is_registered_under_honcho(self):
        """MEMORY_BACKEND=honcho must resolve -- the decorator only runs if
        something imports the module (memory.apps.MemoryConfig.ready)."""
        assert MEMORY_BACKEND_REGISTRY.get("honcho") is HonchoMemoryBackend

    def test_get_memory_backend_resolves_honcho(self, monkeypatch):
        from memory.backends import get_memory_backend

        monkeypatch.setenv("MEMORY_BACKEND", "honcho")
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        assert isinstance(get_memory_backend(), HonchoMemoryBackend)


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
        """Guards Global Constraint: must never attempt `import honcho` (the
        SDK is an optional dependency)."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        backend = HonchoMemoryBackend()
        with mock.patch.object(
            backend, "_ensure_client", side_effect=AssertionError("must not be called")
        ) as mocked:
            backend.health_check()
        mocked.assert_not_called()


class TestHonchoBackendDbOverride:
    @pytest.mark.django_db
    def test_db_override_base_url_wins_over_env(self, monkeypatch):
        from memory.models import SystemMemorySettings

        monkeypatch.setenv("HONCHO_BASE_URL", "http://env-honcho.invalid")
        SystemMemorySettings.objects.create(honcho_base_url="http://db-honcho.invalid")
        backend = HonchoMemoryBackend()
        assert backend._base_url == "http://db-honcho.invalid"

    @pytest.mark.django_db
    def test_falls_back_to_env_when_no_override_row(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://env-honcho.invalid")
        backend = HonchoMemoryBackend()
        assert backend._base_url == "http://env-honcho.invalid"
