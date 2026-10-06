"""Unit tests for the Honcho memory backend.

No network: every test drives a ``unittest.mock`` stand-in for the SDK client
through the ``backend._client`` test seam, so the optional ``honcho-ai``
package never has to be importable for these to run.

The mock mirrors the real ``honcho-ai==2.3.0`` shape that the backend depends
on -- ``client.peer(id).conclusions.{create,query,list,delete}`` for the
pre-#1002 surface, plus ``client.session(id).add_messages(...)``,
``peer.message(...)`` and ``peer.representation(...)/get_card()`` for the F6
session/digest surface, plus ``peer.chat(...)`` for the REQ-192 natural-language
``ask`` surface -- so a future SDK rename (the surface was called
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


class ServerError(Exception):
    """Stand-in for the Honcho SDK's ``ServerError`` (an engine/transport
    failure). The optional ``honcho-ai`` package is never imported here (see
    the module docstring), so the double is declared locally.
    """


def _conclusion(entry_id: str, content: str, level: str = "explicit"):
    """Minimal stand-in for honcho's ``Conclusion`` (only the fields we read).

    ``level`` mirrors ``honcho-ai==2.5.1``'s ``Conclusion.level`` (default
    ``"explicit"``, see the module docstring of ``memory.honcho_backend``):
    AP-B5.1's derivation probe distinguishes stored (``explicit``) from
    derived (``deductive``/``inductive``/``contradiction``) conclusions by
    exactly this field, so tests that simulate deriver output set it here.
    """
    return SimpleNamespace(id=entry_id, content=content, level=level)


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
        # AP-B5.1 (#1155): a non-empty representation IS deriver output, so the
        # digest says so machine-readably -- without a count, because the
        # prose cannot be counted without lying.
        assert digest.derivation_status == "ok"
        assert digest.derived_count is None

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
        # AP-B5.1: the engine was unreachable, so whether it had derived
        # anything is NOT determinable -- "unknown", never a silent "none".
        assert digest.derivation_status == "unknown"
        assert digest.derived_count is None

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
        # AP-B5.1 (#1155): this is the beta.18 state made machine-readable --
        # the engine answers cleanly and its Deriver produced nothing. That
        # must read as "none", NOT as an outage (degraded stays False) and NOT
        # as silent health.
        assert digest.derivation_status == "none"
        assert digest.derived_count == 0

    def test_digest_reports_failed_derivation_from_the_queue(self):
        """#1052 class on the digest surface: the read itself succeeds (the
        engine answered), but the queue accounting proves work units vanished
        without completing -- so the digest is NOT degraded yet honestly
        reports ``failed`` derivation. This is the whole point of separating
        ``degraded`` (did THIS read work) from ``derivation_status`` (did the
        Deriver produce).
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        client.queue_status.return_value = SimpleNamespace(
            total_work_units=10,
            completed_work_units=6,
            in_progress_work_units=2,
            pending_work_units=1,  # 10 > 6+2+1 -> one unit disappeared
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert digest.degraded is False
        assert digest.derivation_status == "failed"
        assert digest.derived_count == 0

    def test_digest_reports_ok_with_exact_derived_count(self):
        """Clean-but-empty engine answer + derived conclusions on the scope's
        conclusion page -> ``ok`` with the exact count (page below the probe
        budget, so the count is a total, not a floor).
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[
                _conclusion("a", "stored fact"),
                _conclusion("b", "because X, therefore Y", level="deductive"),
                _conclusion("c", "pattern noticed", level="inductive"),
            ]
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert digest.degraded is False
        assert digest.derivation_status == "ok"
        assert digest.derived_count == 2

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
        blindly. The ambiguous path's ONE list call is the derivation probe's
        page, which is itself clamped to the SDK's max page size.
        """
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE, _MAX_PAGE_SIZE

        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(items=[])

        backend.digest(tenant_id, "user", user_id)

        assert peer.conclusions.list.call_args.kwargs["size"] == _DERIVATION_PROBE_PAGE_SIZE
        assert _DERIVATION_PROBE_PAGE_SIZE <= _MAX_PAGE_SIZE

    def test_digest_renders_facts_from_the_page_the_status_came_from(self):
        """S3 (backend-reviewer F4 / code-reviewer F1): the clean-but-empty
        engine path must classify derivation and render the facts from ONE
        read. A second, differently-timed read of the same endpoint both costs
        an extra peer get-or-create POST and can produce a payload whose fact
        list does not match the page the status was derived from.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = ""
        peer.get_card.return_value = None
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[_conclusion("a", "one"), _conclusion("b", "two")]
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert peer.conclusions.list.call_count == 1, (
            "the digest must not re-read the conclusion list it already probed"
        )
        assert digest.derivation_status == "none"
        assert digest.derived_count == 0
        assert "- one" in digest.text and "- two" in digest.text
        assert "facts=2" in digest.text
        assert digest.degraded is False

    def test_digest_flags_failed_on_the_non_empty_engine_path(self):
        """M1/S1 (backend-reviewer F1, the major finding): a scope that ALREADY
        has derived output must not read ``ok`` forever while its Deriver is
        demonstrably losing work. The queue gap outranks the historical
        output; the digest text still carries that output.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = "Knows that the answer is 42."
        client.queue_status.return_value = SimpleNamespace(
            total_work_units=9,
            completed_work_units=5,
            in_progress_work_units=2,
            pending_work_units=1,  # 9 > 5+2+1 -> units vanished
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert digest.degraded is False  # the READ worked; the DERIVER is losing
        assert digest.derivation_status == "failed"
        assert "Knows that the answer is 42." in digest.text

    def test_digest_keeps_ok_on_the_non_empty_path_with_a_balanced_queue(self):
        """The complement: a healthy queue must not be downgraded -- ``ok``
        stays the answer when the scope has output and nothing is provably
        lost."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.representation.return_value = "Knows that the answer is 42."
        client.queue_status.return_value = SimpleNamespace(
            total_work_units=4,
            completed_work_units=4,
            in_progress_work_units=0,
            pending_work_units=0,
        )

        digest = backend.digest(tenant_id, "user", user_id)

        assert digest.degraded is False
        assert digest.derivation_status == "ok"

class TestHonchoDerivationState:
    """AP-B5.1 (#1155): the derivation probe on the empirically verified
    ``honcho-ai==2.5.1`` surface (``Conclusion.level`` + ``queue_status``).

    The contract these tests pin is the HONEST-CEILING one: every status is
    reported only from a signal the SDK actually returned -- ``ok`` from a
    derived conclusion, ``failed`` from a provable queue-accounting gap,
    ``none`` from a clean probe with nothing derived, ``unknown`` whenever a
    call raised. No count is ever a floor dressed up as a total.
    """

    def _setup(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        return backend, client, peer, tenant_id, user_id

    @staticmethod
    def _queue(client, total, completed, in_progress, pending):
        client.queue_status.return_value = SimpleNamespace(
            total_work_units=total,
            completed_work_units=completed,
            in_progress_work_units=in_progress,
            pending_work_units=pending,
        )

    def test_derived_conclusions_yield_ok_with_exact_count(self):
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, _client, peer, tenant_id, user_id = self._setup()
        # 98 explicit + 2 derived = 100 items would SATURATE the page; keep it
        # strictly below the budget so the count must be reported as exact.
        items = [_conclusion(str(i), f"c{i}") for i in range(_DERIVATION_PROBE_PAGE_SIZE - 3)]
        items.append(_conclusion("d1", "derived", level="deductive"))
        items.append(_conclusion("d2", "derived too", level="inductive"))
        peer.conclusions.list.return_value = SimpleNamespace(items=items)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "ok"
        assert count == 2  # page below the probe budget -> exact total

    def test_saturated_page_with_derived_yields_ok_without_a_count(self):
        """A full probe page of derived conclusions proves ``ok`` but NOT a
        total -- more may sit beyond the budget, so the count must be ``None``
        rather than a floor reported as an exact number."""
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, _client, peer, tenant_id, user_id = self._setup()
        items = [
            _conclusion(str(i), f"c{i}", level="inductive")
            for i in range(_DERIVATION_PROBE_PAGE_SIZE)
        ]
        peer.conclusions.list.return_value = SimpleNamespace(items=items)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "ok"
        assert count is None

    def test_saturated_page_confirms_derived_level_server_side(self):
        """Saturated all-explicit page: the probe must not conclude ``none``
        from a truncated view -- it re-checks each derived level with a
        server-side ``filters={"level": ...}`` query, and a hit yields ``ok``."""
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, _client, peer, tenant_id, user_id = self._setup()
        explicit = [_conclusion(str(i), f"c{i}") for i in range(_DERIVATION_PROBE_PAGE_SIZE)]

        def _list(**kwargs):
            if kwargs.get("filters"):
                assert kwargs["filters"]["level"] in (
                    "deductive",
                    "inductive",
                    "contradiction",
                )
                hit = kwargs["filters"]["level"] == "contradiction"
                return SimpleNamespace(
                    items=[_conclusion("x", "contra", level="contradiction")] if hit else []
                )
            return SimpleNamespace(items=explicit)

        peer.conclusions.list.side_effect = _list

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "ok"
        assert count is None  # confirmed existence, not an exact total

    def test_clean_queue_without_derived_yields_none(self):
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[_conclusion("a", "stored fact")]
        )
        self._queue(client, total=5, completed=5, in_progress=0, pending=0)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "none"
        assert count == 0
        # The queue is scoped to the scope's own (tenant-namespaced) peer.
        assert client.queue_status.call_args.kwargs["observer"] == f"{tenant_id}_{user_id}"

    def test_queue_accounting_gap_yields_failed(self):
        """#1052 class: work units that vanished without completing (and
        without being counted as completed) are a DEMONSTRABLE failure --
        the only honest ``failed`` signal the SDK surface offers."""
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        self._queue(client, total=10, completed=6, in_progress=1, pending=1)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "failed"
        assert count == 0

    def test_queue_probe_failure_degrades_to_none(self):
        """The queue is a best-effort EXTRA signal: if it raises, the proven
        part of the answer (no derived conclusions) still stands, so the
        status stays ``none`` rather than collapsing to ``unknown``."""
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        client.queue_status.side_effect = RuntimeError("queue endpoint unavailable")

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "none"
        assert count == 0

    def test_non_integer_queue_counters_are_ignored(self):
        """Doubles/older server shapes must not corrupt the accounting: only
        real non-negative ints count (``bool`` included -- it is an int
        subclass and ``True`` would silently pass as ``1``)."""
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        self._queue(client, total=True, completed=0, in_progress=0, pending=0)

        status, _count = self._state(backend, tenant_id, "user", user_id)

        assert status == "none"

    def test_inert_queue_counters_are_logged_not_silently_ignored(self, caplog):
        """S2 (backend-reviewer F2): a failure detector that can never fire is
        itself the #1052 failure mode ("nobody sees it"). When the queue
        surface yields unusable counters the probe must leave a trace in the
        logs, while still answering from the signal it DOES have."""
        import logging

        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(items=[])
        client.queue_status.return_value = SimpleNamespace(
            total_work_units="many",
            completed_work_units=None,
            in_progress_work_units=0,
            pending_work_units=0,
        )

        with caplog.at_level(logging.WARNING, logger="memory.honcho_backend"):
            status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "none"  # no provable gap -> never a guessed "failed"
        assert count == 0
        assert any("failure detection is inert" in rec.message for rec in caplog.records)

    def test_conclusion_list_failure_yields_unknown(self):
        """The probe's primary signal raised -> the derivation state is NOT
        determinable; ``unknown``, never a silent ``none``."""
        backend, _client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.side_effect = RuntimeError("engine unreachable")

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "unknown"
        assert count is None

    def test_unknown_scope_yields_unknown(self):
        """A rejected scope never reaches the engine; the probe reports
        ``unknown`` (a caller bug surfaced via the digest's degrade path, not
        a derivation statement)."""
        backend, _client, _peer, tenant_id, _user_id = self._setup()

        status, count = self._state(backend, tenant_id, "not-a-scope", uuid4())

        assert status == "unknown"
        assert count is None

    @staticmethod
    def _state(backend, tenant_id, scope, scope_id):
        """Two-value view of the probe (status, count).

        The loaded page only matters to ``digest``, which renders from it; the
        classification tests assert on the status/count pair, so unpacking the
        3-tuple here once keeps every test readable instead of repeating
        ``_derivation_probe(...)[0:2]`` ten times.
        """
        status, count, _items = backend._derivation_probe(tenant_id, scope, scope_id)
        return status, count

    def test_failed_outranks_ok_when_derived_output_already_exists(self):
        """M1/S1 at probe level: derived conclusions AND a provable queue gap
        -> ``failed``. "Has produced output once" must not mask "is losing
        work now"; the count still reports what exists, so no information is
        thrown away by the override."""
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[_conclusion("d1", "because X, therefore Y", level="deductive")]
        )
        self._queue(client, total=5, completed=3, in_progress=1, pending=0)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "failed"
        assert count == 1

    def test_probe_hands_back_the_page_it_classified_from(self):
        """S3: the probe returns the loaded conclusions page so the caller can
        render from the SAME read the status came from -- one peer resolution,
        one list GET, no contradicting payload."""
        from memory.backends import _DIGEST_MAX_FACTS

        backend, _client, peer, tenant_id, user_id = self._setup()
        items = [_conclusion(str(i), f"c{i}") for i in range(_DIGEST_MAX_FACTS + 5)]
        peer.conclusions.list.return_value = SimpleNamespace(items=items)

        status, count, page = backend._derivation_probe(tenant_id, "user", user_id)

        assert status == "none"
        assert count == 0
        assert page is not None and len(page) == len(items)
        assert [c.content for c in page[:_DIGEST_MAX_FACTS]][0] == "c0"

    def test_unknown_from_a_failed_level_recheck_still_returns_the_page(self):
        """The saturated-page level re-check raising makes the derivation
        ANSWER undeterminable but not the page: the caller can still render
        what was read instead of paying for another round trip."""
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, _client, peer, tenant_id, user_id = self._setup()
        explicit = [_conclusion(str(i), f"c{i}") for i in range(_DERIVATION_PROBE_PAGE_SIZE)]

        def _list(**kwargs):
            if kwargs.get("filters"):
                raise RuntimeError("level filter unsupported on this build")
            return SimpleNamespace(items=explicit)

        peer.conclusions.list.side_effect = _list

        status, count, page = backend._derivation_probe(tenant_id, "user", user_id)

        assert status == "unknown"
        assert count is None
        assert page is not None and len(page) == _DERIVATION_PROBE_PAGE_SIZE

    def test_queue_gap_outranks_unknown_on_the_level_recheck_failure_path(self):
        """N1 (AP-B5.2, follow-up to #1155): the saturated-page level
        re-check raising used to early-return ``unknown`` WITHOUT consulting
        the queue gap -- the one path where the demonstrable ``failed``
        signal was silently dropped. A provable work-unit accounting gap
        outranks the undeterminable answer here exactly like everywhere else;
        the page still travels back so the caller can render it."""
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, client, peer, tenant_id, user_id = self._setup()
        explicit = [_conclusion(str(i), f"c{i}") for i in range(_DERIVATION_PROBE_PAGE_SIZE)]

        def _list(**kwargs):
            if kwargs.get("filters"):
                raise RuntimeError("level filter unsupported on this build")
            return SimpleNamespace(items=explicit)

        peer.conclusions.list.side_effect = _list
        self._queue(client, total=10, completed=6, in_progress=1, pending=1)

        status, count, page = backend._derivation_probe(tenant_id, "user", user_id)

        assert status == "failed"
        assert count is None
        assert page is not None and len(page) == _DERIVATION_PROBE_PAGE_SIZE

    def test_balanced_queue_keeps_unknown_on_the_level_recheck_failure_path(self):
        """The complement of the N1 fix: a healthy queue must NOT upgrade the
        undeterminable re-check answer to anything provable -- it stays
        ``unknown``, never a silent ``ok`` and never a guessed ``failed``."""
        from memory.honcho_backend import _DERIVATION_PROBE_PAGE_SIZE

        backend, client, peer, tenant_id, user_id = self._setup()
        explicit = [_conclusion(str(i), f"c{i}") for i in range(_DERIVATION_PROBE_PAGE_SIZE)]

        def _list(**kwargs):
            if kwargs.get("filters"):
                raise RuntimeError("level filter unsupported on this build")
            return SimpleNamespace(items=explicit)

        peer.conclusions.list.side_effect = _list
        self._queue(client, total=4, completed=4, in_progress=0, pending=0)

        status, count, page = backend._derivation_probe(tenant_id, "user", user_id)

        assert status == "unknown"
        assert count is None
        assert page is not None and len(page) == _DERIVATION_PROBE_PAGE_SIZE

    def test_double_without_level_attribute_counts_as_explicit(self):
        """The SDK's own field default is ``"explicit"``; a double (or an
        older response) that does not model ``level`` must be treated as a
        verbatim stored conclusion, never as phantom deriver output."""
        backend, client, peer, tenant_id, user_id = self._setup()
        peer.conclusions.list.return_value = SimpleNamespace(
            items=[SimpleNamespace(id="a", content="stored")]
        )
        self._queue(client, total=1, completed=1, in_progress=0, pending=0)

        status, count = self._state(backend, tenant_id, "user", user_id)

        assert status == "none"
        assert count == 0


class TestHonchoAsk:
    """REQ-192: the engine's dialectic surface (``peer.chat``) behind ``ask()``.

    Scoped to the scope's own session, tenant-namespaced, and degrade-never-raise
    like ``digest`` -- a missing session (Honcho answers with
    ``MissingSessionID``/HTTP 400 when none is given or it does not exist) must
    become ``degraded=True``, never an unhandled 500.
    """

    def test_ask_answers_from_the_scope_session_and_forwards_reasoning_level(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.return_value = "The team prefers REST."

        answer = backend.ask(tenant_id, "user", user_id, "REST or MCP?", reasoning_level="high")

        assert answer.text == "The team prefers REST."
        assert answer.backend == "honcho"
        assert answer.degraded is False
        peer.chat.assert_called_once_with(
            "REST or MCP?",
            session=backend._scope_session_id(tenant_id, "user", user_id),
            reasoning_level="high",
        )

    def test_ask_omits_reasoning_level_when_not_given(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.return_value = "yes"

        backend.ask(tenant_id, "user", user_id, "q?")

        assert peer.chat.call_args.kwargs == {
            "session": backend._scope_session_id(tenant_id, "user", user_id)
        }

    def test_ask_degrades_when_the_engine_raises(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.side_effect = RuntimeError("engine down")

        answer = backend.ask(tenant_id, "user", user_id, "q?")

        assert answer.degraded is True
        assert answer.text == ""
        assert answer.backend == "honcho"
        # F5 (backend-reviewer): the degradation carries the (non-user-data)
        # cause so a caller can tell an outage from "nothing known" -- now
        # classified as an ENGINE error (not the bare exception name).
        assert answer.detail == "engine_error:RuntimeError"
        # Backward compatibility: a consumer that matched the old bare class
        # name still matches it as a substring.
        assert "RuntimeError" in answer.detail
        assert answer.detail != "RuntimeError"

    def test_ask_degrades_on_a_missing_session_error(self):
        """A sessionless/unknown dialectic call makes Honcho answer
        ``MissingSessionID`` (HTTP 400); that must degrade, not raise."""
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.side_effect = RuntimeError("MissingSessionID")

        answer = backend.ask(tenant_id, "user", user_id, "q?")

        assert answer.degraded is True
        assert answer.text == ""
        assert answer.detail == "engine_error:RuntimeError"

    def test_ask_marks_a_honcho_server_error_as_an_engine_error(self):
        """(a) A Honcho SDK ``ServerError`` must surface as an ENGINE error,
        never as the bare token ``"ServerError"`` -- so a caller can act on the
        failure class (retry an outage) without parsing logs.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.side_effect = ServerError("upstream 503")

        answer = backend.ask(tenant_id, "user", user_id, "q?")

        # (c) degraded is True on an engine failure.
        assert answer.degraded is True
        assert answer.text == ""
        assert answer.detail == "engine_error:ServerError"
        assert answer.detail != "ServerError"

    def test_ask_of_an_unknown_scope_carries_a_distinguishable_token(self):
        """(b) An unknown-scope rejection yields a token distinct from an
        engine outage, so the two degraded causes never collapse.
        """
        backend, _client = _backend_with_mock_client()

        answer = backend.ask(uuid4(), "not-a-scope", uuid4(), "q?")

        assert answer.degraded is True
        assert answer.text == ""
        assert answer.detail == "unknown_scope:ValueError"
        assert not answer.detail.startswith("engine_error:")

    def test_ask_degraded_detail_never_leaks_query_or_memory_content(self):
        """(d) ``detail`` is a diagnosis, not user data: neither the query nor
        any memory content (which an SDK error message can embed) may appear.
        """
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        secret_query = "how do I rotate the prod DB credentials"
        secret_content = "the answer is hunter2"
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.side_effect = ServerError(f"{secret_query} / {secret_content}")

        answer = backend.ask(tenant_id, "user", user_id, secret_query)

        assert answer.detail == "engine_error:ServerError"
        assert secret_query not in answer.detail
        assert secret_content not in answer.detail

    def test_degraded_detail_is_stable_per_exception_class(self):
        """The helper is deterministic for a given exception class, and keeps
        the class name retrievable as a substring (backward compatibility).
        """
        from memory.honcho_backend import _degraded_detail

        assert _degraded_detail(RuntimeError("a")) == _degraded_detail(RuntimeError("b"))
        assert _degraded_detail(ServerError("x")) == "engine_error:ServerError"
        assert _degraded_detail(ValueError("unknown memory scope: 'x'")) == (
            "unknown_scope:ValueError"
        )
        # An engine-side ValueError is NOT a scope rejection.
        assert _degraded_detail(ValueError("bad argument")) == "engine_error:ValueError"

    def test_ask_reports_a_none_answer_as_empty_but_not_degraded(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()
        peer = client.peer(f"{tenant_id}_{user_id}")
        peer.chat.return_value = None

        answer = backend.ask(tenant_id, "user", user_id, "q?")

        assert answer.degraded is False
        assert answer.text == ""

    def test_ask_never_passes_a_raw_scope_id_to_honcho(self):
        backend, client = _backend_with_mock_client()
        tenant_id, user_id = uuid4(), uuid4()

        backend.ask(tenant_id, "user", user_id, "q?")

        assert f"{tenant_id}_{user_id}" in client.peers_by_id

    def test_ask_timeout_defaults_and_is_env_overridable(self, monkeypatch):
        """F2 (code-reviewer): the SDK client must be built with a bounded
        request timeout, else ``peer.chat`` can block unbounded."""
        from memory.honcho_backend import (
            _DEFAULT_ASK_TIMEOUT_S,
            _ask_timeout_s,
        )

        monkeypatch.delenv("MEMORY_ASK_TIMEOUT", raising=False)
        assert _ask_timeout_s() == _DEFAULT_ASK_TIMEOUT_S

        monkeypatch.setenv("MEMORY_ASK_TIMEOUT", "7.5")
        assert _ask_timeout_s() == 7.5

    def test_ask_timeout_falls_back_on_a_bad_value(self, monkeypatch):
        from memory.honcho_backend import _DEFAULT_ASK_TIMEOUT_S, _ask_timeout_s

        for bad in ("0", "-3", "not-a-number"):
            monkeypatch.setenv("MEMORY_ASK_TIMEOUT", bad)
            assert _ask_timeout_s() == _DEFAULT_ASK_TIMEOUT_S

    def test_ensure_client_passes_a_bounded_timeout_to_the_sdk(self, monkeypatch):
        """The timeout must reach ``Honcho(...)`` at client construction."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.setenv("MEMORY_ASK_TIMEOUT", "11.0")

        captured: dict = {}

        class _FakeHoncho:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("honcho.Honcho", _FakeHoncho)
        backend = HonchoMemoryBackend()
        backend._ensure_client(uuid4())

        assert captured["timeout"] == 11.0


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
