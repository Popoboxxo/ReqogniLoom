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
* string ids never trigger a UUID coercion error on the delete path;
* empty results are ``([], 0)`` / ``[]``.

The suite is parametrized over the real registry implementations rather than
over hand-written doubles: ``pgvector`` runs against the real table, ``honcho``
against the FakeHoncho client below (same ``peer(id).conclusions.{create,
query,list,delete}`` surface ``test_honcho_backend.py`` drives) plus its local
mirror rows -- so the contract is pinned against the actual code paths on both
providers, not a mock of them.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
from uuid import UUID, uuid4

import pytest

from memory.backends import MemoryHealth, get_memory_backend
from memory.honcho_backend import HonchoMemoryBackend
from persistence.models import Artifact
from persistence.tests.factories import active_tenant, make_user, make_workspace

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


class _FakePeer:
    def __init__(self, store: list) -> None:
        self.conclusions = _FakeConclusionScope(store)


class _FakeHonchoClient:
    def __init__(self) -> None:
        self._peers: dict[str, _FakePeer] = {}
        # Permissive, like the MagicMock client test_honcho_backend.py uses:
        # the real ``ConclusionScope.delete`` delegates to ``client._http.delete``
        # and expects any object back.
        self._http = mock.MagicMock()

    def peer(self, peer_id: str) -> _FakePeer:
        return self._peers.setdefault(peer_id, _FakePeer([]))

    def _ensure_workspace(self) -> None:
        """No-op: the real ``Honcho`` client ensures its workspace before a
        delete; this fake has no server to talk to."""
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=["pgvector", "honcho"])
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
        assert result.backend in ("pgvector", "honcho")

    def test_backend_ref_matches_backend_semantics(self, backend):
        """pgvector IS the backend (no external ref); honcho mirrors a nanoid."""
        with active_tenant() as tenant:
            scope_id = _scope_id(tenant, "user")
            ref = backend.write(tenant.id, "user", scope_id, "fact")
            if isinstance(backend, HonchoMemoryBackend):
                assert ref.backend_ref
                assert ref.backend_ref != str(ref.entry_id)
            else:
                assert ref.backend_ref is None


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
