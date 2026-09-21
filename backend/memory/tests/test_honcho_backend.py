"""Unit tests for the Honcho memory backend.

No network: every test drives a ``unittest.mock`` stand-in for the SDK client
through the ``backend._client`` test seam, so the optional ``honcho-ai``
package never has to be importable for these to run.

The mock mirrors the real ``honcho-ai==2.3.0`` shape that the backend depends
on -- ``client.peer(id).conclusions.{create,query,list,delete}`` for the
pre-#1002 surface, plus ``client.session(id).add_messages(...)``,
``peer.message(...)`` and ``peer.representation(...)/get_card()`` for the F6
session/digest surface -- so a future SDK rename (the surface was called
``observations`` before ``conclusions``) shows up as a failure here rather than
only in production.
"""
import re
import sys
import types
from types import SimpleNamespace
from unittest import mock
from uuid import UUID, uuid4

import pytest
import requests

from memory.backends import MEMORY_BACKEND_REGISTRY
from memory.honcho_backend import HonchoMemoryBackend
from persistence.models import Artifact
from persistence.tests.factories import active_tenant, make_user, make_workspace

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
            peer = mock.MagicMock()
            # ``peer.message(content, metadata=...)`` must hand back something
            # whose ``content`` the session actually receives: F6's whole point
            # is that the message body reaches the engine, so the double has to
            # carry it instead of returning an opaque mock.
            peer.message.side_effect = lambda content, **kwargs: SimpleNamespace(
                peer_id=peer_id, content=content, metadata=kwargs.get("metadata")
            )
            peers[peer_id] = peer
        return peers[peer_id]

    client.peer.side_effect = _peer
    client.peers_by_id = peers
    return client


def _backend_with_mock_client():
    backend = HonchoMemoryBackend()
    client = _mock_client()
    backend._client = client
    return backend, client


def _fake_honcho_api_types() -> types.ModuleType:
    """Minimal ``honcho.api_types`` stand-in for the configuration-activation test.

    This suite deliberately never depends on the optional ``honcho-ai`` package
    (see the module docstring), yet
    ``HonchoMemoryBackend._ensure_engine_configuration`` imports the real
    configuration models lazily. Injecting a fake module keeps that import path
    -- and the get-modify-set/memo logic wrapped around it -- under test without
    making the SDK a test dependency.
    """
    module = types.ModuleType("honcho.api_types")
    for name in (
        "ReasoningConfiguration",
        "PeerCardConfiguration",
        "SummaryConfiguration",
        "DreamConfiguration",
        "SessionConfiguration",
        "WorkspaceConfiguration",
    ):
        setattr(module, name, mock.MagicMock())
    return module


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

    def test_artifact_scope_uses_the_new_a_prefix(self):
        """RFC #1002: artifact is a NEW scope, so it gets the explicit ``_a_``
        prefix from day one -- unlike user/workspace, which keep the legacy
        unprefixed shape so already-written external peers stay addressable.
        """
        backend = HonchoMemoryBackend()
        tenant_id, artifact_id = uuid4(), uuid4()
        assert backend._scope_peer_id(tenant_id, "artifact", artifact_id) == (
            f"{tenant_id}_a_{artifact_id}"
        )

    def test_user_and_workspace_scopes_keep_the_legacy_unprefixed_shape(self):
        """Backwards compatibility: introducing ``_u_``/``_w_`` would orphan
        every existing Honcho peer (there is no migration for a foreign
        service), so the prefix is used ONLY for the new artifact scope.
        """
        backend = HonchoMemoryBackend()
        tenant_id, scope_id = uuid4(), uuid4()
        assert backend._scope_peer_id(tenant_id, "user", scope_id) == f"{tenant_id}_{scope_id}"
        assert backend._scope_peer_id(tenant_id, "workspace", scope_id) == f"{tenant_id}_{scope_id}"

    def test_honcho_workspace_is_per_tenant(self):
        tenant_a, tenant_b = uuid4(), uuid4()
        backend = HonchoMemoryBackend()
        assert backend._honcho_workspace_id(tenant_a) == f"reqogniloom_{tenant_a}"
        assert backend._honcho_workspace_id(tenant_a) != backend._honcho_workspace_id(tenant_b)

    def test_unknown_scope_is_rejected(self):
        backend = HonchoMemoryBackend()
        with pytest.raises(ValueError, match="unknown memory scope"):
            backend._scope_peer_id(uuid4(), "not-a-scope", uuid4())

    @pytest.mark.django_db
    @pytest.mark.parametrize("scope", ["user", "workspace"])
    def test_every_data_method_uses_a_tenant_prefixed_peer(self, scope):
        """No method may address a raw ReqogniLoom id (the leak this guards)."""
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            scope_id = make_user(tenant).id if scope == "user" else make_workspace(tenant).id
            expected_peer = f"{tenant.id}_{scope_id}"

            peer = client.peer(expected_peer)
            peer.conclusions.create.return_value = [_conclusion("abc", "f")]
            peer.conclusions.query.return_value = []
            peer.conclusions.list.return_value = SimpleNamespace(items=[])
            client.peer.reset_mock()

            backend.upsert(tenant.id, scope, scope_id, "f")
            backend.query(tenant.id, scope, scope_id, "q")
            backend.list_recent(tenant.id, scope, scope_id)

            used = [c.args[0] for c in client.peer.call_args_list]
            assert used == [expected_peer] * 3
            assert str(scope_id) in expected_peer and str(tenant.id) in expected_peer


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

    @pytest.mark.django_db
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
    @pytest.mark.django_db
    def test_upsert_user_scope_uses_namespaced_peer_and_mirrors_locally(self):
        """RFC #1002: the returned ``entry_id`` is OUR UUID; the Honcho nanoid
        travels in ``backend_ref`` and the local mirror row persists."""
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano123", "some fact")]

            ref = backend.upsert(tenant.id, "user", user.id, "some fact")

            peer.conclusions.create.assert_called_once_with([{"content": "some fact"}])
            assert str(ref.entry_id) != "nano123"
            assert UUID(str(ref.entry_id)) == ref.entry_id
            assert ref.backend_ref == "nano123"
            assert ref.content == "some fact"
            assert MemoryEntry.objects.filter(id=ref.entry_id, backend_ref="nano123").exists()

    @pytest.mark.django_db
    def test_upsert_workspace_scope_uses_namespaced_peer(self):
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            ws = make_workspace(tenant)
            peer = client.peer(f"{tenant.id}_{ws.id}")
            peer.conclusions.create.return_value = [_conclusion("nano456", "ws fact")]

            ref = backend.upsert(tenant.id, "workspace", ws.id, "ws fact")

            assert UUID(str(ref.entry_id)) == ref.entry_id
            assert ref.backend_ref == "nano456"

    def test_upsert_raises_when_honcho_returns_nothing(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        client.peer(f"{tenant_id}_{user_id}").conclusions.create.return_value = []

        with pytest.raises(RuntimeError, match="returned no object"):
            backend.upsert(tenant_id, "user", user_id, "fact")

        # Ordering matters: the message publish runs only after the conclusion
        # was accepted, so a rejected write leaves no orphan observation in the
        # engine (and the pre-existing RuntimeError contract stays the only
        # hard failure path).
        client.session.assert_not_called()


class TestHonchoSessionIds:
    """F6 session naming: stable per scope, tenant-namespaced, charset-safe.

    A session is the unit the Deriver aggregates messages into, so its id has
    the same two hard requirements the peer ids already have: it must be shared
    by every write to one scope (otherwise the aggregation restarts per entry)
    and it must satisfy Honcho v3's ``^[a-zA-Z0-9_-]+$`` charset, or the SDK
    answers 422 on every call instead of storing the message.
    """

    def test_session_id_is_derived_from_the_scope_peer(self):
        backend = HonchoMemoryBackend()
        tenant_id, scope_id = uuid4(), uuid4()
        assert backend._scope_session_id(tenant_id, "user", scope_id) == f"s_{tenant_id}_{scope_id}"
        assert backend._scope_session_id(tenant_id, "workspace", scope_id) == (
            f"s_{tenant_id}_{scope_id}"
        )
        assert backend._scope_session_id(tenant_id, "artifact", scope_id) == (
            f"s_{tenant_id}_a_{scope_id}"
        )

    def test_session_id_is_stable_across_calls(self):
        backend = HonchoMemoryBackend()
        tenant_id, scope_id = uuid4(), uuid4()
        assert backend._scope_session_id(tenant_id, "user", scope_id) == (
            backend._scope_session_id(tenant_id, "user", scope_id)
        )

    def test_session_ids_are_namespaced_by_tenant(self):
        backend = HonchoMemoryBackend()
        tenant_a, tenant_b, scope_id = uuid4(), uuid4(), uuid4()
        assert backend._scope_session_id(tenant_a, "user", scope_id) != (
            backend._scope_session_id(tenant_b, "user", scope_id)
        )

    @pytest.mark.parametrize("scope", ["user", "workspace", "artifact"])
    def test_session_id_matches_honchos_allowed_charset(self, scope):
        backend = HonchoMemoryBackend()
        assert _HONCHO_ID_PATTERN.match(backend._scope_session_id(uuid4(), scope, uuid4()))

    def test_unknown_scope_is_rejected(self):
        backend = HonchoMemoryBackend()
        with pytest.raises(ValueError, match="unknown memory scope"):
            backend._scope_session_id(uuid4(), "not-a-scope", uuid4())


@pytest.mark.django_db
class TestHonchoMessagePublish:
    """F6: the conclusion is not enough -- the Deriver is fed by MESSAGES.

    Before F6 ``write()`` only created a conclusion, so Honcho's deriver, peer
    card, summary and dream never saw any input and ``digest()`` had nothing
    engine-derived to return. These tests pin the message path AND its
    fail-open rule (a broken session endpoint must never fail a memory write).
    """

    @pytest.mark.parametrize("scope", ["user", "workspace", "artifact"])
    def test_write_creates_the_scope_session_with_a_stable_id(self, scope):
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            if scope == "user":
                scope_id = make_user(tenant).id
            elif scope == "workspace":
                scope_id = make_workspace(tenant).id
            else:
                scope_id = Artifact.objects.create(
                    tenant=tenant, workspace=make_workspace(tenant), artifact_type="Requirement"
                ).id
            peer = client.peer(backend._scope_peer_id(tenant.id, scope, scope_id))
            peer.conclusions.create.return_value = [_conclusion("nano1", "some fact")]

            backend.write(tenant.id, scope, scope_id, "some fact")

            client.session.assert_called_once()
            session_id = client.session.call_args.args[0]
            assert session_id == backend._scope_session_id(tenant.id, scope, scope_id)
            assert _HONCHO_ID_PATTERN.match(session_id)
            assert str(tenant.id) in session_id and str(scope_id) in session_id

    def test_write_appends_the_content_as_a_message(self):
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "some fact")]
            session = client.session.return_value

            backend.write(
                tenant.id,
                "user",
                user.id,
                "some fact",
                contributor_user_id=user.id,
                language="de",
                confidence=0.5,
            )

            session.add_messages.assert_called_once()
            sent = session.add_messages.call_args.args[0]
            assert len(sent) == 1
            assert sent[0].content == "some fact"
            # Provenance travels with the observation, JSON-serialisable.
            metadata = sent[0].metadata
            assert metadata["scope"] == "user"
            assert metadata["scope_id"] == str(user.id)
            assert metadata["tenant_id"] == str(tenant.id)
            assert metadata["contributor_user_id"] == str(user.id)
            assert metadata["language"] == "de"
            assert metadata["confidence"] == 0.5

    def test_write_omits_unknown_provenance_instead_of_sending_null(self):
        """An absent ``source_event_id`` means "not derived from an event";
        sending ``null`` would claim the engine knows a key that does not
        exist."""
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            client.peer(f"{tenant.id}_{user.id}").conclusions.create.return_value = [
                _conclusion("nano1", "fact")
            ]
            session = client.session.return_value

            backend.write(tenant.id, "user", user.id, "fact")

            metadata = session.add_messages.call_args.args[0][0].metadata
            assert "source_event_id" not in metadata
            assert "source_session_id" not in metadata

    def test_a_failing_session_path_is_fail_open(self, caplog):
        """The mandatory part of a write is the conclusion (+ the local mirror
        row). The session/message publish only makes the engine smarter, so if
        the session endpoint is down the write must still return a ref -- the
        opposite behaviour would turn an observability feature into a new way
        for memory writes to fail.
        """
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "some fact")]
            client.session.side_effect = RuntimeError("session endpoint down")

            ref = backend.write(tenant.id, "user", user.id, "some fact")

            peer.conclusions.create.assert_called_once_with([{"content": "some fact"}])
            assert ref.backend_ref == "nano1"
            assert UUID(str(ref.entry_id)) == ref.entry_id
            from memory.models import MemoryEntry

            assert MemoryEntry.objects.filter(id=ref.entry_id).exists()
            # Logging must never leak memory content (it is user data).
            assert "session endpoint down" in caplog.text or "RuntimeError" in caplog.text
            assert "some fact" not in caplog.text

    def test_a_failing_message_publish_is_fail_open(self, caplog):
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "some fact")]
            peer.message.side_effect = RuntimeError("message rejected")

            ref = backend.write(tenant.id, "user", user.id, "some fact")

            assert ref.backend_ref == "nano1"
            assert "some fact" not in caplog.text

    def test_engine_configuration_is_a_memoized_get_modify_set(self, monkeypatch):
        """The Deriver features have to be ON for the message to be useful, but
        the flags must not be rewritten on every write: a get-modify-set per
        session, memoized for the process, and only when something actually
        changes.
        """
        monkeypatch.setitem(sys.modules, "honcho.api_types", _fake_honcho_api_types())
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "fact")]
            session = mock.MagicMock()
            client.session.return_value = session

            backend.write(tenant.id, "user", user.id, "fact")
            backend.write(tenant.id, "user", user.id, "another fact")

            session.get_configuration.assert_called_once()
            assert session.set_configuration.call_count == 1
            assert client.set_configuration.call_count == 1

    def test_engine_configuration_failure_never_breaks_a_write(self, monkeypatch, caplog):
        monkeypatch.setitem(sys.modules, "honcho.api_types", _fake_honcho_api_types())
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "some fact")]
            session = mock.MagicMock()
            session.get_configuration.side_effect = RuntimeError("cannot read configuration")
            client.session.return_value = session

            ref = backend.write(tenant.id, "user", user.id, "some fact")

            assert ref.backend_ref == "nano1"
            # The message still goes out: a configuration hiccup must not cost
            # the observation it was meant to configure for.
            session.add_messages.assert_called_once()
            assert "some fact" not in caplog.text


@pytest.mark.django_db
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


@pytest.mark.django_db
class TestHonchoDigest:
    """F6 ``digest()``: prefer the engine's derived artefact, degrade in steps.

    The degraded flag is the load-bearing part: ``True`` means "a backend or
    network call raised" (the engine is unreachable), ``False`` means "the peer
    answered". An empty-but-healthy answer is explicitly NOT degraded (F9).
    """

    def test_digest_prefers_the_peer_representation(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = "Knows that the answer is 42."

        digest = backend.digest(tenant_id, "user", user_id)

        assert "Knows that the answer is 42." in digest.text
        assert digest.backend == "honcho"
        assert digest.degraded is False
        # Scoped to the scope's session: the workspace-wide representation would
        # mix every scope's facts into one digest.
        peer.representation.assert_called_once_with(
            session=backend._scope_session_id(tenant_id, "user", user_id)
        )
        assert "facts=" not in digest.text  # free-form prose is not counted

    def test_digest_falls_back_to_the_peer_card(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = ["works on ReqogniLoom", "prefers dark mode"]

        digest = backend.digest(tenant_id, "user", user_id)

        assert "works on ReqogniLoom" in digest.text
        assert "prefers dark mode" in digest.text
        assert digest.degraded is False

    def test_digest_falls_back_to_the_conclusion_list_and_flags_degradation(self):
        """The engine's representation is the preferred source, but a failed
        call must not become an empty answer: the conclusion list is still
        reachable and the caller is told (via ``degraded``) that it came from a
        fallback rather than from the Deriver.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.side_effect = RuntimeError("engine unreachable")
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[_conclusion("a", "one"), _conclusion("b", "two")]
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert "- one" in digest.text
        assert "- two" in digest.text
        assert digest.backend == "honcho"
        assert digest.degraded is True

    def test_digest_falls_back_to_the_local_mirror_when_the_engine_is_down(self):
        """Last resort: the local mirror needs no network at all, so a caller
        still sees what was written even while the engine is unreachable --
        with ``degraded=True`` so nobody mistakes it for the engine's answer.
        """
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.conclusions.create.return_value = [_conclusion("nano1", "the answer is 42")]
            backend.write(tenant.id, "user", user.id, "the answer is 42")

            peer.representation.side_effect = RuntimeError("engine unreachable")
            peer.get_card.side_effect = RuntimeError("engine unreachable")
            peer.conclusions.list.side_effect = RuntimeError("engine unreachable")

            digest = backend.digest(tenant.id, "user", user.id)

            assert "- the answer is 42" in digest.text
            assert digest.degraded is True

    def test_digest_of_a_healthy_but_empty_scope_is_not_degraded(self):
        """F9 for the engine path: a peer that answers cleanly with nothing to
        summarise is not degraded -- "remembered nothing" must stay
        distinguishable from "the engine is down"."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(items=[])

        digest = backend.digest(tenant_id, "user", user_id)

        assert digest.degraded is False
        assert digest.backend == "honcho"
        assert "(no facts remembered)" in digest.text

    def test_digest_never_raises_when_engine_and_mirror_are_both_unavailable(self, monkeypatch):
        """The contract's last line of defence: if even the local mirror read
        fails, the digest is an empty degraded answer, not an exception. A
        digest is a read surface an agent drives -- raising here would be an
        unhandled 500 for a question the caller cannot retry around.
        """
        with active_tenant() as tenant:
            backend, client = _backend_with_mock_client()
            user = make_user(tenant)
            peer = client.peer(f"{tenant.id}_{user.id}")
            peer.representation.side_effect = RuntimeError("down")
            peer.conclusions.list.side_effect = RuntimeError("down")
            monkeypatch.setattr(
                HonchoMemoryBackend,
                "list_entries",
                mock.Mock(side_effect=RuntimeError("mirror down")),
            )

            digest = backend.digest(tenant.id, "user", user.id)

            assert digest.degraded is True
            assert digest.backend == "honcho"
            assert digest.text == ""

    def test_digest_clamps_its_page_request(self):
        """``_MAX_PAGE_SIZE`` discipline: Honcho 422s an oversized page size
        instead of clamping it, so the digest must never pass the raw cap
        blindly."""
        from memory.backends import _DIGEST_MAX_FACTS

        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(items=[])

        backend.digest(tenant_id, "user", user_id)

        assert peer.conclusions.list.call_args.kwargs["size"] == _DIGEST_MAX_FACTS
        assert _DIGEST_MAX_FACTS <= 100


@pytest.mark.django_db
class TestHonchoForget:
    """These drive the real ``honcho.conclusions.ConclusionScope`` against a
    mock HTTP client, so the asserted route is the SDK's own, not a guess.

    ``@pytest.mark.django_db`` is required since RFC #1002: ``forget`` now
    delegates to ``delete_entry``, which also removes the local mirror row.
    """

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
    """``health_check()`` probes the OpenAI-compatible embedding endpoint.

    Every test mocks ``requests.head``/``requests.post`` -- no live network.
    See GH #911: the old probe only did a HEAD on ``HONCHO_BASE_URL`` and so
    reported ``ok`` even when the (placeholder) embedding endpoint could not
    be reached or was not configured, which is exactly the "dishonest health"
    this class guards against.
    """

    @staticmethod
    def _configure_all(monkeypatch):
        """Point every env var the probe reads at a valid-looking config."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.setenv("HONCHO_EMBEDDING_BASE_URL", "http://embed.invalid/v1")
        monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", "nomic-embed-text")
        # Pin the probe budget to the default so the timeout assertions below
        # are independent of the ambient environment (#990).
        monkeypatch.delenv("HEALTH_PROBE_TIMEOUT", raising=False)

    def test_health_check_honours_the_configured_probe_timeout(self, monkeypatch):
        """#990: ``HEALTH_PROBE_TIMEOUT`` overrides the 10s default."""
        self._configure_all(monkeypatch)
        monkeypatch.setenv("HEALTH_PROBE_TIMEOUT", "3.5")
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=200)
        post.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        with mock.patch("requests.head", return_value=head) as head_mock, mock.patch(
            "requests.post", return_value=post
        ):
            backend.health_check()
        assert head_mock.call_args.kwargs["timeout"] == 3.5

    def test_health_check_down_when_base_url_not_configured(self, monkeypatch):
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False
        assert "not configured" in detail.lower()

    def test_health_check_reports_down_on_connection_failure(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        monkeypatch.delenv("HONCHO_EMBEDDING_BASE_URL", raising=False)
        monkeypatch.delenv("HONCHO_EMBEDDING_MODEL", raising=False)
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False

    def test_health_check_does_not_import_honcho_sdk(self, monkeypatch):
        """Guards Global Constraint: must never attempt `import honcho` (the
        SDK is an optional dependency)."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho-does-not-exist.invalid:9999")
        monkeypatch.delenv("HONCHO_EMBEDDING_BASE_URL", raising=False)
        monkeypatch.delenv("HONCHO_EMBEDDING_MODEL", raising=False)
        backend = HonchoMemoryBackend()
        with mock.patch.object(
            backend, "_ensure_client", side_effect=AssertionError("must not be called")
        ) as mocked:
            backend.health_check()
        mocked.assert_not_called()

    def test_health_check_down_when_embedding_base_url_not_configured(self, monkeypatch):
        """GH #911: an unconfigured embedding endpoint must not report ok."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.delenv("HONCHO_EMBEDDING_BASE_URL", raising=False)
        monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", "nomic-embed-text")
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False
        assert "HONCHO_EMBEDDING_BASE_URL" in detail
        assert "#911" in detail

    def test_health_check_down_when_embedding_model_not_configured(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.setenv("HONCHO_EMBEDDING_BASE_URL", "http://embed.invalid/v1")
        monkeypatch.delenv("HONCHO_EMBEDDING_MODEL", raising=False)
        backend = HonchoMemoryBackend()
        ok, detail = backend.health_check()
        assert ok is False
        assert "HONCHO_EMBEDDING_MODEL" in detail

    def test_health_check_ok_when_embedding_probe_succeeds(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=200)
        post.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        with mock.patch("requests.head", return_value=head) as head_mock, mock.patch(
            "requests.post", return_value=post
        ) as post_mock:
            ok, detail = backend.health_check()
        assert ok is True
        assert "nomic-embed-text" in detail
        # Issue #990: the probe budget is a realistic, configurable 10s now,
        # not the old hard 1s that turned normal latency into "down".
        head_mock.assert_called_once_with(
            "http://honcho.invalid", timeout=10.0, allow_redirects=False
        )
        post_mock.assert_called_once_with(
            "http://embed.invalid/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "ping"},
            timeout=10.0,
        )

    def test_health_check_down_when_embedding_probe_returns_http_error(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=500)
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post", return_value=post
        ):
            ok, detail = backend.health_check()
        assert ok is False
        assert "500" in detail

    def test_health_check_down_when_embedding_probe_returns_4xx(self, monkeypatch):
        """A non-2xx (not only >= 500) embedding response is down: the code must
        reject 3xx/4xx exactly as the docstring says (GH #911)."""
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=404)
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post", return_value=post
        ):
            ok, detail = backend.health_check()
        assert ok is False
        assert "404" in detail

    def test_health_check_skips_embedding_probe_when_model_unset(self, monkeypatch):
        """Guard ordering: an unset HONCHO_EMBEDDING_MODEL must short-circuit
        before any embedding POST is attempted."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.setenv("HONCHO_EMBEDDING_BASE_URL", "http://embed.invalid/v1")
        monkeypatch.delenv("HONCHO_EMBEDDING_MODEL", raising=False)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post"
        ) as post_mock:
            ok, _detail = backend.health_check()
        assert ok is False
        post_mock.assert_not_called()

    def test_health_check_down_when_embedding_probe_times_out(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post", side_effect=requests.Timeout("timed out")
        ):
            ok, detail = backend.health_check()
        assert ok is False
        assert "timed out" in detail

    def test_health_check_down_when_embedding_vector_is_empty(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=200)
        post.json.return_value = {"data": [{"embedding": []}]}
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post", return_value=post
        ):
            ok, detail = backend.health_check()
        assert ok is False
        assert "nomic-embed-text" in detail

    def test_health_check_down_when_embedding_response_is_unparseable(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=200)
        post = mock.Mock(status_code=200)
        post.json.side_effect = ValueError("No JSON object could be decoded")
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post", return_value=post
        ):
            ok, detail = backend.health_check()
        assert ok is False
        assert "JSON" in detail

    def test_health_check_down_when_honcho_head_returns_5xx(self, monkeypatch):
        self._configure_all(monkeypatch)
        backend = HonchoMemoryBackend()
        head = mock.Mock(status_code=503)
        with mock.patch("requests.head", return_value=head), mock.patch(
            "requests.post"
        ) as post_mock:
            ok, detail = backend.health_check()
        assert ok is False
        assert "503" in detail
        post_mock.assert_not_called()



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
