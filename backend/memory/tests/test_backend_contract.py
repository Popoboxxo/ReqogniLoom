"""``MemoryBackend`` contract conformance suite (RFC #1002 PR A).

Every backend must satisfy the same canonical-store contract for ALL THREE
scopes (``user`` / ``workspace`` / ``artifact``):

* ``write`` issues OUR UUID and persists the row;
* ``list_entries`` returns the page + the total, and honours ``limit`` /
  ``offset`` / ``q``;
* ``count`` matches ``list_entries``' total;
* ``query`` returns the written entry (``top_k`` honoured);
* ``delete_entry(True)`` removes it; ``delete_scope`` removes exactly one
  scope's rows and returns the count;
* ``health()`` returns a :class:`~memory.backends.MemoryHealth`;
* ``digest()`` returns a :class:`~memory.backends.MemoryDigest` for the scope,
  never raises, and reports an EMPTY scope as ``degraded=False`` (F9: "the
  engine failed" and "there is nothing to say" are different answers);
* string ids never trigger a UUID coercion error on the delete path;
* empty results are ``([], 0)`` / ``[]``.

The suite is parametrized over the real registry implementations rather than
over hand-written doubles: ``pgvector`` runs against the real table, ``honcho``
against the FakeHoncho client below (same ``peer(id).conclusions.{create,
query,list,delete}`` surface ``test_honcho_backend.py`` drives, plus the
``session``/``message``/``context`` surface the F6 write and digest paths use)
plus its local mirror rows -- so the contract is pinned against the actual code
paths on both providers, not a mock of them.

ENV LIMITATION of the coverage in this module: the derivation assertions pin
pgvector's CAPABILITY STATEMENT (``derivation_status == "unsupported"``) on the
deterministic ``mock`` embedding provider and the offline fakes above. They do
not prove real-provider derivation transitions (Honcho's ``ok``/``none``/
``failed`` depend on a live engine and its queue), real-provider answer QUALITY,
a live dialectic engine, or the end-to-end Celery queue -- the consolidation E2E
test never runs a consuming worker (``memory/tests/test_consolidation_e2e.py``).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock
from uuid import UUID, uuid4

import pytest

from memory.backends import (
    VALID_CONSOLIDATION_STATUSES,
    VALID_DERIVATION_STATUSES,
    ConsolidationResult,
    MemoryAnswer,
    MemoryDigest,
    MemoryHealth,
    PgvectorMemoryBackend,
    get_memory_backend,
)
from memory.honcho_backend import HonchoMemoryBackend
from memory.qdrant_backend import QdrantMemoryBackend
from memory.tests.qdrant_fakes import FakeQdrantClient, FakeQdrantModels
from persistence.models import Artifact, Tenant
from persistence.tests.factories import (
    active_tenant,
    make_user,
    make_workspace,
    make_workspace_id,
)

_SCOPES = ("user", "workspace", "artifact")


# ---------------------------------------------------------------------------
# Fake Honcho client (stateful, in-memory)
# ---------------------------------------------------------------------------


class _FakeConclusionScope:
    def __init__(self, store: list) -> None:
        self._store = store

    def create(self, payload: list[dict]) -> list:
        created = []
        for item in payload:
            conclusion = SimpleNamespace(id=f"nano{uuid4().hex[:12]}", content=item["content"])
            self._store.append(conclusion)
            created.append(conclusion)
        return created

    def query(self, text: str, top_k: int = 5) -> list:
        return list(self._store)[:top_k]

    def list(self, size: int = 20):
        return SimpleNamespace(items=list(self._store)[:size])

    def delete(self, conclusion_id: str) -> None:
        self._store[:] = [c for c in self._store if c.id != conclusion_id]


class _FakeSession:
    """Session double for the F6 message/deriver surface.

    ``get_configuration`` returns ``None`` on purpose: this fake has no server,
    and the backend's get-modify-set helper treats "no configuration" as "start
    from the SDK defaults" -- so a run against this fake exercises the
    fail-open path of the configuration activation instead of silently
    pretending the engine was configured.
    """

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.messages: list = []
        self.configuration = None

    def add_messages(self, messages: list) -> list:
        self.messages.extend(messages)
        return list(messages)

    def get_configuration(self):
        return None

    def set_configuration(self, configuration) -> None:
        self.configuration = configuration


class _FakePeer:
    def __init__(self, store: list) -> None:
        self.conclusions = _FakeConclusionScope(store)
        #: Messages appended by ``write()`` via the session (F6).
        self.messages: list = []
        #: Engine artefacts ``digest()`` prefers, configurable per test.
        self.representation_text = ""
        self.card: list | None = None
        #: ``ask()`` dialectic surface: the answer to return, or an exception
        #: instance to raise when the test simulates an unreachable engine.
        self.chat_answer: object = ""
        self.chat_calls: list = []

    def message(self, content: str, **kwargs):
        return SimpleNamespace(
            content=content, metadata=kwargs.get("metadata"), peer_id=kwargs.get("peer_id")
        )

    def context(self, **kwargs):
        """ONE call returning both digest fields (T-A4-4)."""
        return SimpleNamespace(
            representation=self.representation_text, peer_card=self.card
        )

    def chat(self, query, **kwargs):
        self.chat_calls.append((query, kwargs))
        if isinstance(self.chat_answer, Exception):
            raise self.chat_answer
        return self.chat_answer


class _FakeHonchoClient:
    def __init__(self) -> None:
        self._peers: dict[str, _FakePeer] = {}
        self._sessions: dict[str, _FakeSession] = {}
        self.configuration = None
        #: Dream requests recorded by ``consolidate()`` (T-A4-2), in call order.
        #: Mirrors ``Honcho.schedule_dream(observer, session=None, observed=None)``
        #: -- the SDK discards the response body, so a fake has nothing to return.
        self.dream_calls: list[dict] = []
        #: Set to an exception instance to simulate an engine that rejects the
        #: request; ``None`` means "accepted" (the documented 2xx/204).
        self.dream_error: object = None
        # Permissive, like the MagicMock client test_honcho_backend.py uses:
        # the real ``ConclusionScope.delete`` delegates to ``client._http.delete``
        # and expects any object back.
        self._http = mock.MagicMock()

    def peer(self, peer_id: str) -> _FakePeer:
        return self._peers.setdefault(peer_id, _FakePeer([]))

    def session(self, session_id: str, **kwargs) -> _FakeSession:
        return self._sessions.setdefault(session_id, _FakeSession(session_id))

    def schedule_dream(self, observer: str, session=None, observed: str | None = None) -> None:
        self.dream_calls.append(
            {"observer": observer, "observed": observed, "session": session}
        )
        if isinstance(self.dream_error, Exception):
            raise self.dream_error

    def get_configuration(self):
        return None

    def set_configuration(self, configuration) -> None:
        self.configuration = configuration

    def _ensure_workspace(self) -> None:
        """No-op: the real ``Honcho`` client ensures its workspace before a
        delete; this fake has no server to talk to."""
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=["pgvector", "honcho", "qdrant"])
def backend(request, monkeypatch):
    """Return a real backend instance for each registered implementation."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    if request.param == "honcho":
        monkeypatch.setenv("MEMORY_BACKEND", "honcho")
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.invalid")
        monkeypatch.setenv("HONCHO_EMBEDDING_BASE_URL", "http://embed.invalid/v1")
        monkeypatch.setenv("HONCHO_EMBEDDING_MODEL", "nomic-embed-text")
        # health() probes the network; keep it offline + deterministic.
        head = SimpleNamespace(status_code=200)
        post = SimpleNamespace(status_code=200, json=lambda: {"data": [{"embedding": [0.1, 0.2]}]})
        monkeypatch.setattr("requests.head", lambda *args, **kwargs: head)
        monkeypatch.setattr("requests.post", lambda *args, **kwargs: post)
        instance = HonchoMemoryBackend()
        instance._client = _FakeHonchoClient()
        return instance
    if request.param == "qdrant":
        monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
        monkeypatch.setenv("QDRANT_BASE_URL", "http://qdrant.invalid")
        # The in-memory fake client + models keep this offline, like honcho's.
        instance = QdrantMemoryBackend()
        instance._client = FakeQdrantClient()
        instance._models_module = FakeQdrantModels
        return instance
    monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
    return get_memory_backend()


def _scope_id(tenant, scope: str) -> UUID:
    """Create and return a real owner id for *scope* in *tenant*."""
    if scope == "user":
        return make_user(tenant).id
    if scope == "workspace":
        return make_workspace(tenant).id
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=make_workspace(tenant), artifact_type="Requirement"
    )
    return artifact.id


# ---------------------------------------------------------------------------
# Contract — parametrized over (backend, scope)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("scope", _SCOPES)
class TestMemoryBackendContract:
    def test_write_returns_our_uuid_and_persists(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)

            ref = backend.write(tenant.id, scope, scope_id, "first fact")

            assert UUID(str(ref.entry_id)) == ref.entry_id, (
                "write() must issue ReqogniLoom's own UUID as entry_id"
            )
            assert ref.content == "first fact"
            assert ref.scope == scope
            assert backend.count(tenant.id, scope, scope_id) == 1

            page, total = backend.list_entries(tenant.id, scope, scope_id)
            assert total == 1
            assert [r.entry_id for r in page] == [ref.entry_id]
            assert page[0].content == "first fact"
            assert page[0].created_at is not None

    def test_write_persists_provenance_columns(self, backend, scope):
        contributor = uuid4()
        session = uuid4()
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)

            backend.write(
                tenant.id,
                scope,
                scope_id,
                "provenance fact",
                contributor_user_id=contributor,
                source_session_id=session,
                language="de",
                confidence=0.25,
                entity_type="preference",
            )

            page, _ = backend.list_entries(tenant.id, scope, scope_id)
            row = page[0]
            assert row.contributor_user_id == contributor
            assert row.confidence == 0.25
            assert row.superseded_by is None

    def test_list_entries_pagination_and_filter(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            backend.write(tenant.id, scope, scope_id, "alpha widget")
            backend.write(tenant.id, scope, scope_id, "beta gadget")
            backend.write(tenant.id, scope, scope_id, "gamma widget")

            page, total = backend.list_entries(tenant.id, scope, scope_id)
            assert total == 3
            assert [r.content for r in page] == ["gamma widget", "beta gadget", "alpha widget"]

            first, first_total = backend.list_entries(tenant.id, scope, scope_id, limit=1, offset=0)
            assert first_total == 3
            assert [r.content for r in first] == ["gamma widget"]

            second, _ = backend.list_entries(tenant.id, scope, scope_id, limit=1, offset=1)
            assert [r.content for r in second] == ["beta gadget"]

            filtered, filtered_total = backend.list_entries(
                tenant.id, scope, scope_id, q="widget"
            )
            assert filtered_total == 2
            assert {r.content for r in filtered} == {"alpha widget", "gamma widget"}

    def test_count_matches_list_entries_total(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            for i in range(3):
                backend.write(tenant.id, scope, scope_id, f"fact {i}")

            page, total = backend.list_entries(tenant.id, scope, scope_id)
            assert backend.count(tenant.id, scope, scope_id) == total == len(page) == 3

    def test_query_returns_entry_with_top_k(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            ref = backend.write(tenant.id, scope, scope_id, "the answer is 42")

            results = backend.query(tenant.id, scope, scope_id, "answer", top_k=5)

            assert len(results) == 1
            assert results[0].entry_id == ref.entry_id
            assert results[0].content == "the answer is 42"

    def test_delete_entry_accepts_string_id_and_removes_it(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            ref = backend.write(tenant.id, scope, scope_id, "doomed fact")

            assert backend.delete_entry(tenant.id, str(ref.entry_id)) is True
            assert backend.count(tenant.id, scope, scope_id) == 0
            assert backend.list_entries(tenant.id, scope, scope_id) == ([], 0)

    def test_delete_entry_unknown_id_returns_false(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            assert backend.delete_entry(tenant.id, str(uuid4())) is False

    def test_delete_scope_removes_only_that_scope(self, backend, scope):
        with active_tenant() as tenant:
            scope_a = _scope_id(tenant, scope)
            scope_b = _scope_id(tenant, scope)
            backend.write(tenant.id, scope, scope_a, "a1")
            backend.write(tenant.id, scope, scope_a, "a2")
            backend.write(tenant.id, scope, scope_b, "b1")

            deleted = backend.delete_scope(tenant.id, scope, scope_a)

            assert deleted == 2
            assert backend.count(tenant.id, scope, scope_a) == 0
            assert backend.count(tenant.id, scope, scope_b) == 1

    def test_empty_results(self, backend, scope):
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            assert backend.list_entries(tenant.id, scope, scope_id) == ([], 0)
            assert backend.count(tenant.id, scope, scope_id) == 0
            assert backend.query(tenant.id, scope, scope_id, "nothing", top_k=5) == []

    def test_superseded_entries_are_excluded(self, backend, scope):
        from memory.models import MemoryEntry

        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, scope)
            older_ref = backend.write(tenant.id, scope, scope_id, "outdated fact")
            backend.write(tenant.id, scope, scope_id, "current fact")

            MemoryEntry.objects.filter(id=older_ref.entry_id).update(
                superseded_by_id=MemoryEntry.objects.get(
                    content="current fact", **{f"{scope}_id": scope_id}
                ).id
            )

            page, total = backend.list_entries(tenant.id, scope, scope_id)
            assert total == 1
            assert backend.count(tenant.id, scope, scope_id) == 1
            assert [r.content for r in page] == ["current fact"]


@pytest.mark.django_db
class TestMemoryBackendContractCommon:
    def test_health_returns_memory_health(self, backend):
        result = backend.health()
        assert isinstance(result, MemoryHealth)
        assert result.backend in ("pgvector", "honcho", "qdrant")

    def test_digest_of_an_empty_scope_is_not_degraded(self, backend):
        """F6 + F9: ``digest()`` answers for every backend, never raises, and an
        empty-but-healthy scope must NOT be reported as degraded -- otherwise a
        caller could not tell "the engine is down" from "nothing is
        remembered", which is the exact confusion F9 exists to prevent. The
        sentinel body (rather than an empty string) is what makes the answered
        emptiness visible to the agent consuming the digest.
        """
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")

            digest = backend.digest(tenant.id, "user", scope_id)

            assert isinstance(digest, MemoryDigest)
            assert digest.backend in ("pgvector", "honcho", "qdrant")
            assert digest.degraded is False
            assert digest.text
            assert "facts=0" in digest.text
            assert isinstance(digest.generated_at, datetime)

    def test_digest_carries_a_valid_derivation_status(self, backend):
        """AP-B5.1 (#1155): every digest names the DERIVER's state from the
        shared enum, separately from ``degraded`` -- "nothing derived" must
        stay machine-distinguishable from "the read failed" and from
        "healthy". pgvector has no deriver at all -> ``unsupported``; the
        Honcho fake (empty peer, no queue surface) probes cleanly -> ``none``.
        The count is only ever an exact int or ``None`` -- never fabricated.
        """
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")

            digest = backend.digest(tenant.id, "user", scope_id)

            assert digest.derivation_status in VALID_DERIVATION_STATUSES
            assert digest.derived_count is None or (
                isinstance(digest.derived_count, int)
                and not isinstance(digest.derived_count, bool)
                and digest.derived_count >= 0
            )
            if isinstance(backend, HonchoMemoryBackend):
                assert digest.derivation_status == "none"
                assert digest.derived_count == 0
            else:
                assert digest.derivation_status == "unsupported"
                assert digest.derived_count is None

    def test_digest_renders_written_facts_deterministically(self, backend):
        """Identical state ⇒ byte-identical text. This is what lets a caller
        cache a digest (or a test pin it) instead of pattern-matching a
        prompt-shaped blob; a timestamp or an unordered read would break it.
        """
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")
            backend.write(tenant.id, "user", scope_id, "the answer is 42")
            backend.write(tenant.id, "user", scope_id, "prefers dark mode")

            first = backend.digest(tenant.id, "user", scope_id)
            second = backend.digest(tenant.id, "user", scope_id)

            assert first.degraded is False
            assert first.text == second.text
            assert "facts=2" in first.text
            assert "- the answer is 42" in first.text
            assert "- prefers dark mode" in first.text

    def test_digest_caps_the_rendered_facts(self, backend):
        """A digest is prompt-sized context, not an export (module docstring:
        ``_DIGEST_MAX_FACTS``)."""
        from memory.backends import _DIGEST_MAX_FACTS

        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")
            for i in range(_DIGEST_MAX_FACTS + 5):
                backend.write(tenant.id, "user", scope_id, f"fact {i}")

            digest = backend.digest(tenant.id, "user", scope_id)

            assert f"facts={_DIGEST_MAX_FACTS}" in digest.text

    def test_digest_of_an_unknown_scope_degrades_instead_of_raising(self, backend):
        """The contract's "never raises" clause has to hold for a bad argument
        too: a digest is driven by an agent through MCP/REST, and an exception
        there is an unhandled 500 for a *read*."""
        with active_tenant() as tenant:
            digest = backend.digest(tenant.id, "not-a-scope", uuid4())

            assert digest.degraded is True
            assert digest.text == ""

    def test_ask_of_an_unknown_scope_degrades_instead_of_raising(self, backend):
        """Same "never raises" clause as the digest, for the ask surface."""
        with active_tenant() as tenant:
            answer = backend.ask(tenant.id, "not-a-scope", uuid4(), "what is it?")

            assert answer.degraded is True
            assert answer.text == ""

    def test_ask_returns_a_memory_answer(self, backend):
        """The ask contract returns a :class:`MemoryAnswer` for every backend.

        Whether the backend can actually answer is expressed by ``degraded``
        (pgvector has no dialectic engine and reports ``True``), never by
        raising.
        """
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")

            answer = backend.ask(tenant.id, "user", scope_id, "what do we know?")

            assert isinstance(answer, MemoryAnswer)
            assert answer.backend in ("pgvector", "honcho", "qdrant")
            assert isinstance(answer.degraded, bool)
            assert isinstance(answer.generated_at, datetime)

    def test_backend_ref_matches_backend_semantics(self, backend):
        """pgvector IS the backend (no external ref); honcho mirrors a nanoid;
        qdrant uses the canonical point id (``str(entry_id)``) as its ref."""
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")
            ref = backend.write(tenant.id, "user", scope_id, "fact")
            if isinstance(backend, HonchoMemoryBackend):
                assert ref.backend_ref
                assert ref.backend_ref != str(ref.entry_id)
            elif isinstance(backend, QdrantMemoryBackend):
                assert ref.backend_ref == str(ref.entry_id)
            else:
                assert ref.backend_ref is None


@pytest.mark.django_db
class TestPgvectorDerivationCapability:
    """pgvector's ``derivation_status`` is a fixed capability statement, not a
    measurement (AP-B5.1, #1155): there is no deriver at all, so it says
    ``unsupported`` on EVERY path -- including ``degraded=True``, because
    ``degraded`` already carries the outage and collapsing the two would lose
    the distinction the pair exists for.
    """

    def _pgvector(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
        return get_memory_backend()

    def test_class_level_capability_is_unsupported(self):
        assert PgvectorMemoryBackend.derivation_status == "unsupported"

    def test_digest_keeps_unsupported_on_a_healthy_scope(self, monkeypatch):
        backend = self._pgvector(monkeypatch)
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")
            backend.write(tenant.id, "user", scope_id, "a fact")

            digest = backend.digest(tenant.id, "user", scope_id)

            assert digest.degraded is False
            assert digest.derivation_status == "unsupported"
            assert digest.derived_count is None

    def test_digest_keeps_unsupported_when_the_scope_degrades(self, monkeypatch):
        """The "down" read (unknown scope) must not turn the capability statement
        into an outage -- ``degraded`` is the outage signal, ``unsupported``
        stays the honest "no deriver here"."""
        backend = self._pgvector(monkeypatch)
        with active_tenant() as tenant:
            digest = backend.digest(tenant.id, "not-a-scope", uuid4())

            assert digest.degraded is True
            assert digest.text == ""
            assert digest.derivation_status == "unsupported"
            assert digest.derived_count is None

    def test_digest_keeps_unsupported_when_the_table_is_unreachable(self, monkeypatch):
        """The unreachable-table branch (``except`` around the read) takes the
        same capability statement: an outage changes ``degraded``, never what
        the backend is able to derive."""
        backend = self._pgvector(monkeypatch)

        def _boom(_tenant_id):
            raise RuntimeError("mem_memory_entry unreachable")

        monkeypatch.setattr("memory.backends._tenant_context", _boom)
        with active_tenant() as tenant:
            digest = backend.digest(tenant.id, "user", uuid4())

            assert digest.degraded is True
            assert digest.derivation_status == "unsupported"
            assert digest.derived_count is None

    def test_degraded_status_stays_inside_the_shared_enum(self, monkeypatch):
        """The degraded pair still travels through the shared enum, so a caller
        can machine-distinguish it from Honcho's ``unknown``/``failed``."""
        backend = self._pgvector(monkeypatch)
        with active_tenant() as tenant:
            degraded = backend.digest(tenant.id, "not-a-scope", uuid4())
            scope_id = _scope_id(tenant, "user")
            healthy = backend.digest(tenant.id, "user", scope_id)

            assert degraded.derivation_status in VALID_DERIVATION_STATUSES
            assert healthy.derivation_status in VALID_DERIVATION_STATUSES
            assert degraded.derivation_status == healthy.derivation_status


@pytest.mark.django_db
class TestHonchoSpecificContract:
    """Honcho-only invariants (the mirror + external-deletion contract)."""

    def _honcho(self):
        backend = HonchoMemoryBackend()
        backend._client = _FakeHonchoClient()
        return backend

    def test_delete_entry_accepts_a_raw_nanoid_backend_ref(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            ref = backend.write(tenant.id, "user", user.id, "fact")

            assert backend.delete_entry(tenant.id, ref.backend_ref) is True
            assert backend.count(tenant.id, "user", user.id) == 0

    def test_write_publishes_a_message_into_the_scope_session(self):
        """F6: a conclusion alone gives Honcho's Deriver nothing to derive from
        (conclusions are terminal artefacts, messages are observations). The
        same content must therefore also arrive as a message, authored by the
        scope's own peer, without touching the conclusion contract.
        """
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)

            ref = backend.write(tenant.id, "user", user.id, "some fact")

            session_id = backend._scope_session_id(tenant.id, "user", user.id)
            session = backend._client._sessions[session_id]
            assert [message.content for message in session.messages] == ["some fact"]
            assert session.messages[0].metadata["scope"] == "user"
            assert session.messages[0].metadata["scope_id"] == str(user.id)
            assert ref.backend_ref, "the conclusion id must still reach backend_ref"

    def test_consecutive_writes_share_one_session_per_scope(self):
        """The Deriver aggregates many messages into ONE representation over
        time, so a session per write (or per call) would restart that
        aggregation on every entry -- the id has to be stable per scope.
        """
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "first")
            backend.write(tenant.id, "user", user.id, "second")

            assert len(backend._client._sessions) == 1
            session = next(iter(backend._client._sessions.values()))
            assert [message.content for message in session.messages] == ["first", "second"]

    def test_other_scopes_do_not_share_a_session(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            workspace = make_workspace(tenant)
            backend.write(tenant.id, "user", user.id, "user fact")
            backend.write(tenant.id, "workspace", workspace.id, "workspace fact")

            assert len(backend._client._sessions) == 2

    def test_delete_entry_deletes_the_external_conclusion(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            ref = backend.write(tenant.id, "user", user.id, "fact")

            backend.delete_entry(tenant.id, ref.entry_id)

            deleted_paths = [c.args[0] for c in backend._client._http.delete.call_args_list]
            assert any(str(ref.backend_ref) in path for path in deleted_paths), (
                "delete_entry must reach the external Honcho service via backend_ref (DSGVO)"
            )

    def test_delete_scope_deletes_all_external_conclusions(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "fact one")
            backend.write(tenant.id, "user", user.id, "fact two")

            deleted = backend.delete_scope(tenant.id, "user", user.id)

            assert deleted == 2
            assert backend._client._http.delete.call_count == 2

    def test_query_reports_an_in_process_distance(self):
        """RFC #1002 F5: honcho now returns a real cosine distance, not None."""
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            backend.write(tenant.id, "user", user.id, "the answer is 42")

            results = backend.query(tenant.id, "user", user.id, "the answer is 42", top_k=5)

            assert len(results) == 1
            assert results[0].distance is not None

    def test_ask_uses_the_scope_session_and_returns_the_answer(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            peer = backend._client.peer(f"{tenant.id}_{user.id}")
            peer.chat_answer = "The team prefers REST."

            answer = backend.ask(tenant.id, "user", user.id, "REST or MCP?", reasoning_level="medium")

            assert answer.text == "The team prefers REST."
            assert answer.backend == "honcho"
            assert answer.degraded is False
            assert peer.chat_calls == [
                (
                    "REST or MCP?",
                    {
                        "session": backend._scope_session_id(tenant.id, "user", user.id),
                        "reasoning_level": "medium",
                    },
                )
            ]

    def test_ask_degrades_when_the_engine_is_down(self):
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            peer = backend._client.peer(f"{tenant.id}_{user.id}")
            peer.chat_answer = RuntimeError("engine unreachable")

            answer = backend.ask(tenant.id, "user", user.id, "anything?")

            assert answer.degraded is True
            assert answer.text == ""
            assert answer.backend == "honcho"

    def test_ask_reports_a_none_answer_as_empty_but_not_degraded(self):
        """Honcho returns ``None`` for "nothing relevant known" -- that is an
        answer, not an outage (F9)."""
        backend = self._honcho()
        with active_tenant() as tenant:
            user = make_user(tenant)
            peer = backend._client.peer(f"{tenant.id}_{user.id}")
            peer.chat_answer = None

            answer = backend.ask(tenant.id, "user", user.id, "anything?")

            assert answer.degraded is False
            assert answer.text == ""

    def test_honcho_admits_no_scope_less_derivation_claim(self):
        """AP-B5.1 (#1155): Honcho CAN derive, but the scope-less health
        envelope has no scope to probe -- so the class-level capability stays
        ``unknown`` ("derivation possible, not measured here") and the
        per-scope truth travels on the digest. Claiming ``ok``/``none`` at
        class level would be the beta.18 lie in a new coat."""
        assert HonchoMemoryBackend.derivation_status == "unknown"


# ---------------------------------------------------------------------------
# Plan A T-A0b-4 — capability declarations + conformance registry
# ---------------------------------------------------------------------------


def test_every_registered_backend_has_conformance_fixture():
    """Every registry entry is covered, and its declaration is consistent.

    This is the meta-test T-A0b-4 asks for: adding a backend without a
    fixture fails here instead of silently skipping the contract suite.
    """
    from memory.backends import MEMORY_BACKEND_REGISTRY
    from memory.testing.conformance import (
        CONFORMANCE_FIXTURES,
        assert_capabilities_consistent,
        missing_conformance_fixtures,
    )

    assert missing_conformance_fixtures() == []
    for name in sorted(MEMORY_BACKEND_REGISTRY):
        assert_capabilities_consistent(CONFORMANCE_FIXTURES[name]())


def test_meta_check_rejects_a_backend_without_fixture(monkeypatch):
    """The registry check is live, not a static list."""
    from memory.backends import MEMORY_BACKEND_REGISTRY, MemoryBackend
    from memory.testing.conformance import missing_conformance_fixtures

    class _DummyBackend(MemoryBackend):
        """Never instantiated — only registered to prove the check reacts."""

    monkeypatch.setitem(MEMORY_BACKEND_REGISTRY, "dummy-without-fixture", _DummyBackend)
    assert "dummy-without-fixture" in missing_conformance_fixtures()


# ---------------------------------------------------------------------------
# Plan A T-A4-2 — consolidation ("dream") capability
# ---------------------------------------------------------------------------


def test_consolidation_capability_is_declared_only_where_the_port_exists():
    """T-A4-2: ``capabilities.consolidation`` must match reality on EVERY backend.

    The capability lives in the same declaration every caller reads (health,
    admin settings, this suite), so it has to be pinned here and not only in
    the Honcho test: exactly the backend with a real ``consolidate`` surface
    declares ``True``, every other one declares ``False`` and inherits the
    base class's honest ``unsupported`` answer (asserted for all of them by
    ``assert_capabilities_consistent`` in the meta-test above).
    """
    from memory.backends import MEMORY_BACKEND_REGISTRY

    declared = {
        name: backend_cls.capabilities.consolidation
        for name, backend_cls in MEMORY_BACKEND_REGISTRY.items()
    }
    assert declared.pop("honcho") is True, "honcho has schedule_dream (T-A4-1)"
    assert not any(declared.values()), (
        f"only honcho can consolidate, but these declare it too: {declared}"
    )


@pytest.mark.django_db
def test_consolidate_unsupported_on_pgvector(monkeypatch):
    """T-A4-2: a plain store answers ``unsupported`` and touches nothing.

    "This backend cannot consolidate" is a capability statement, not an outage:
    the call must return the ``unsupported`` status (never raise, never a
    ``failed``), carry a diagnostic detail, and leave the scope untouched.
    """
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
    backend = get_memory_backend()
    assert isinstance(backend, PgvectorMemoryBackend)
    assert backend.capabilities.consolidation is False

    with active_tenant() as tenant:
        workspace = make_workspace(tenant)

        outcome = backend.consolidate(tenant.id, "workspace", workspace.id)

        assert outcome.status == "unsupported"
        assert outcome.status in VALID_CONSOLIDATION_STATUSES
        assert outcome.detail, "an unsupported answer must say which backend"
        assert backend.count(tenant.id, "workspace", workspace.id) == 0

        # The periodic task reports the same answer and lists no workspace at
        # all -- "on pgvector/qdrant the task reports unsupported and does
        # nothing" (plan §8), so no dream request and no metric tick happen.
        from memory import tasks as memory_tasks
        from memory.metrics import consolidation_counts, reset_consolidation_counters

        monkeypatch.setenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, "1440")
        reset_consolidation_counters()

        result = memory_tasks.consolidate_all(tenant.id)

        assert result["status"] == "unsupported"
        assert result["backend"] == "pgvector"
        assert result["workspaces"] == 0
        assert result["scheduled"] == 0
        assert consolidation_counts() == {}


@pytest.mark.django_db
def test_honcho_consolidate_calls_schedule_dream_per_workspace(monkeypatch):
    """T-A4-2: one ``schedule_dream`` per workspace PEER, never workspace-wide.

    Two levels, one rule:

    * the backend method itself: ``observer`` and ``observed`` are both that
      workspace's own tenant-namespaced peer and no session is passed, so a
      pass can only touch the scope it was requested for (QR-S04). Scheduling
      must not create a peer -- ``client.peer()`` is a get-or-create POST,
      which would both cost a request and start a representation for a junk
      peer. An engine rejection degrades to ``failed`` (never raises);
    * the periodic task: ``memory.consolidate_all`` drives that method once per
      ACTIVE workspace peer and ticks the metric once per accepted request.
    """
    from memory import tasks as memory_tasks
    from memory.metrics import consolidation_counts, reset_consolidation_counters

    backend = HonchoMemoryBackend()
    backend._client = _FakeHonchoClient()
    client = backend._client

    with active_tenant() as tenant:
        first = make_workspace(tenant)
        second = make_workspace(tenant)

        # -- the backend method ------------------------------------------
        outcomes = [
            backend.consolidate(tenant.id, "workspace", workspace.id)
            for workspace in (first, second)
        ]

        assert [outcome.status for outcome in outcomes] == ["scheduled", "scheduled"]
        assert client.dream_calls == [
            {
                "observer": backend._workspace_id(tenant.id, workspace.id),
                "observed": backend._workspace_id(tenant.id, workspace.id),
                "session": None,
            }
            for workspace in (first, second)
        ]
        # Tenant namespacing is inherited from the unchanged peer naming, and
        # the two workspaces never share a peer.
        assert client.dream_calls[0]["observer"] != client.dream_calls[1]["observer"]
        assert client.dream_calls[0]["observer"].startswith(f"{tenant.id}_")
        assert client._peers == {}, "scheduling a dream must not create a peer"

        # Engine rejection degrades to ``failed`` -- never raises (contract).
        client.dream_error = RuntimeError("engine unreachable")
        rejected = backend.consolidate(tenant.id, "workspace", first.id)
        assert rejected.status == "failed"
        assert "RuntimeError" in rejected.detail

        # -- the periodic task -------------------------------------------
        monkeypatch.setenv("MEMORY_BACKEND", "honcho")
        monkeypatch.setenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, "1440")
        client.dream_error = None
        client.dream_calls.clear()
        monkeypatch.setattr(memory_tasks, "get_memory_backend", lambda: backend)
        reset_consolidation_counters()

        result = memory_tasks.consolidate_all(tenant.id)

        assert result["status"] == "scheduled"
        assert result["workspaces"] == 2
        assert result["scheduled"] == 2
        assert result["failed"] == 0
        # Order-insensitive (review F1): the task lists the workspace rows with
        # ``order_by("pk")`` for reproducible logs, but the assertion must not
        # depend on row order -- an unordered ``filter(is_active=True)`` is a
        # perfectly valid implementation and used to make this test flaky.
        assert sorted(call["observer"] for call in client.dream_calls) == sorted(
            backend._workspace_id(tenant.id, workspace.id)
            for workspace in (first, second)
        )
        assert consolidation_counts()["periodic_dream"] == 2


@pytest.mark.django_db
def test_consolidation_off_at_zero_minutes(monkeypatch):
    """T-A4-2: ``MEMORY_CONSOLIDATION_INTERVAL_MINUTES=0`` is a real off switch.

    "Neither scheduled nor written" has two independent halves, both pinned
    here: the scheduler builds no beat entry at all, and the task returns
    ``disabled`` BEFORE resolving the backend -- so no dream request is issued
    and no metric tick is written, even for a task still queued from a beat
    entry synced before the switch was flipped.
    """
    from memory import tasks as memory_tasks
    from memory.metrics import consolidation_counts, reset_consolidation_counters
    from reqogniloom.settings import _memory_consolidation_beat_entry

    # Half 1: the schedule entry does not exist when the cadence is off.
    assert _memory_consolidation_beat_entry(0) is None
    assert _memory_consolidation_beat_entry(-1) is None
    enabled = _memory_consolidation_beat_entry(1440)
    assert enabled == {
        "task": "memory.consolidate_all",
        "schedule": timedelta(minutes=1440),
    }

    # Half 2: the task short-circuits without touching the backend or the metric.
    monkeypatch.delenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, raising=False)
    assert memory_tasks.consolidation_interval_minutes() == 1440

    monkeypatch.setenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, "0")
    assert memory_tasks.consolidation_interval_minutes() == 0

    def _must_not_resolve():
        raise AssertionError("the backend must not be resolved when the pass is off")

    monkeypatch.setattr(memory_tasks, "get_memory_backend", _must_not_resolve)
    reset_consolidation_counters()

    result = memory_tasks.consolidate_all()

    assert result["status"] == "disabled"
    assert result["scheduled"] == 0
    assert result["workspaces"] == 0
    assert result["backend"] is None
    assert consolidation_counts() == {}


class _FakeConsolidationBackend:
    """Minimal backend stub for the ``consolidate_all`` failure branches.

    ``capabilities.consolidation`` is ``True`` so the pass reaches the loop, and
    ``consolidate`` is driven by ``behaviour(workspace_id)`` so a test can
    simulate a per-scope raise, an out-of-contract status or a full outage
    without an engine. Every requested scope is recorded in ``calls``.
    """

    class capabilities:
        consolidation = True

    def __init__(self, behaviour) -> None:
        self._behaviour = behaviour
        self.calls: list[UUID] = []

    def consolidate(self, tenant_id, scope, scope_id):
        self.calls.append(scope_id)
        return self._behaviour(scope_id)


def _patch_fake_backend(monkeypatch, memory_tasks, backend, interval="60"):
    """Wire ``backend`` into ``consolidate_all`` and pin a positive cadence."""
    monkeypatch.setenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, interval)
    monkeypatch.setattr(memory_tasks, "get_memory_backend", lambda: backend)
    monkeypatch.setattr(memory_tasks, "active_memory_backend_name", lambda: "fake")


@pytest.mark.django_db
def test_consolidate_all_isolates_a_raising_scope(monkeypatch):
    """F6: one raising scope yields ``partial`` and never stops the rest.

    Per-scope isolation is the whole point of the pass: the backend contract
    says ``consolidate`` never raises, so a raise IS a contract violation -- but
    it must cost only the affected workspace, not the remaining ones.
    """
    from memory import tasks as memory_tasks

    with active_tenant() as tenant:
        broken = make_workspace_id(tenant.id)
        healthy = make_workspace_id(tenant.id)

        def behaviour(workspace_id):
            if workspace_id == broken:
                raise RuntimeError("engine unreachable")
            return ConsolidationResult(status="scheduled", detail="accepted")

        backend = _FakeConsolidationBackend(behaviour)
        _patch_fake_backend(monkeypatch, memory_tasks, backend)

        result = memory_tasks.consolidate_all(tenant.id)

    assert result["status"] == "partial"
    assert result["workspaces"] == 2, "the pass must still visit every scope"
    assert result["scheduled"] == 1
    assert result["failed"] == 1
    # The raising scope is not the reason to skip the healthy one.
    assert set(backend.calls) == {broken, healthy}
    assert result["failures"] == [
        {
            "tenant_id": str(tenant.id),
            "workspace_id": str(broken),
            "detail": "raised:RuntimeError",
        }
    ]


@pytest.mark.django_db
def test_consolidate_all_counts_an_unexpected_status_as_failed(monkeypatch):
    """F6/F2: an out-of-contract status is a failure, never an invisible outcome.

    A capability-bearing backend answering ``unsupported`` violates the port
    contract. Counting it as neither scheduled nor failed used to let the pass
    report ``status="scheduled"`` with ``scheduled == 0``.
    """
    from memory import tasks as memory_tasks

    with active_tenant() as tenant:
        workspace_id = make_workspace_id(tenant.id)
        backend = _FakeConsolidationBackend(
            lambda _ws: ConsolidationResult(status="unsupported", detail="port violation")
        )
        _patch_fake_backend(monkeypatch, memory_tasks, backend)

        result = memory_tasks.consolidate_all(tenant.id)

    assert result["status"] == "failed"
    assert result["scheduled"] == 0
    assert result["failed"] == 1
    assert result["failures"] == [
        {
            "tenant_id": str(tenant.id),
            "workspace_id": str(workspace_id),
            "detail": "unexpected_status:unsupported",
        }
    ]


@pytest.mark.django_db
def test_consolidate_all_caps_failure_details_and_fails_the_task(monkeypatch):
    """F6/F3: ``failed`` is exact, ``failures`` is capped, and the task raises.

    The result payload travels through the Celery backend, so the detail list
    is bounded at ``_CONSOLIDATION_RESULT_DETAIL_LIMIT`` entries while the
    counter stays exact. And a pass in which every scope failed must surface as
    a Celery FAILURE, not a SUCCESS carrying ``status="failed"`` (F3).
    """
    from memory import tasks as memory_tasks

    with active_tenant() as tenant:
        workspace_ids = [make_workspace_id(tenant.id) for _ in range(22)]

        def behaviour(_workspace_id):
            raise RuntimeError("engine down")

        backend = _FakeConsolidationBackend(behaviour)
        _patch_fake_backend(monkeypatch, memory_tasks, backend)

        result = memory_tasks.consolidate_all(tenant.id)

        assert result["status"] == "failed"
        assert result["workspaces"] == 22
        assert result["scheduled"] == 0
        assert result["failed"] == 22, "the counter must stay exact"
        assert memory_tasks._CONSOLIDATION_RESULT_DETAIL_LIMIT == 20
        assert len(result["failures"]) == memory_tasks._CONSOLIDATION_RESULT_DETAIL_LIMIT
        assert {
            entry["workspace_id"] for entry in result["failures"]
        } <= {str(workspace_id) for workspace_id in workspace_ids}

        with pytest.raises(memory_tasks.ConsolidationPassFailed) as excinfo:
            memory_tasks.consolidate_all_task(str(tenant.id))

    assert excinfo.value.result["status"] == "failed"
    assert excinfo.value.result["failed"] == 22


@pytest.mark.django_db
def test_consolidate_all_skips_deactivated_tenants(monkeypatch):
    """F7: the enumeration walks ACTIVE tenants only.

    A deactivated tenant's workspaces are not consolidated; an explicitly passed
    ``tenant_id`` stays honoured (that is the operator path, exercised by the
    other tests here).
    """
    from memory import tasks as memory_tasks

    with active_tenant() as tenant:
        live_workspace = make_workspace_id(tenant.id)

    retired = Tenant.objects.create(
        name=f"Retired Tenant {uuid4().hex[:8]}",
        slug=f"retired-tenant-{uuid4().hex[:12]}",
        is_active=False,
    )
    retired_workspace = make_workspace_id(retired.id)

    backend = _FakeConsolidationBackend(
        lambda _ws: ConsolidationResult(status="scheduled", detail="accepted")
    )
    _patch_fake_backend(monkeypatch, memory_tasks, backend)

    result = memory_tasks.consolidate_all()

    assert result["tenants"] == Tenant.objects.filter(is_active=True).count()
    assert live_workspace in backend.calls
    assert retired_workspace not in backend.calls


def test_beat_schedule_registers_the_dream_task():
    """F6: the periodic dream is exposed to beat under the expected task name."""
    from django.conf import settings

    assert settings.MEMORY_CONSOLIDATION_INTERVAL_MINUTES > 0, (
        "the test environment must leave MEMORY_CONSOLIDATION_INTERVAL_MINUTES "
        "at its default; a 0 cadence correctly produces no beat entry"
    )
    entry = settings.CELERY_BEAT_SCHEDULE["memory-consolidate"]
    assert entry["task"] == "memory.consolidate_all"
    assert entry["schedule"] == timedelta(
        minutes=settings.MEMORY_CONSOLIDATION_INTERVAL_MINUTES
    )


def test_consolidation_interval_grammar_is_shared(monkeypatch):
    """F5: one parser, two documented invalid-value policies.

    The grammar (integer, whitespace-tolerant, unset -> default) is shared; a
    typo fails the boot in settings and degrades to the default at task time.
    """
    from memory import tasks as memory_tasks
    from memory.consolidation_config import (
        DEFAULT_CONSOLIDATION_INTERVAL_MINUTES,
        parse_consolidation_interval,
    )

    assert parse_consolidation_interval(None) == DEFAULT_CONSOLIDATION_INTERVAL_MINUTES
    assert parse_consolidation_interval("") == DEFAULT_CONSOLIDATION_INTERVAL_MINUTES
    assert parse_consolidation_interval(" 60 ") == 60
    with pytest.raises(ValueError):
        parse_consolidation_interval("hourly")

    monkeypatch.setenv(memory_tasks.CONSOLIDATION_INTERVAL_ENV, "hourly")
    assert (
        memory_tasks.consolidation_interval_minutes()
        == DEFAULT_CONSOLIDATION_INTERVAL_MINUTES
    )
