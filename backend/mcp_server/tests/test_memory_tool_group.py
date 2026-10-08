"""Tests for the ``memory.*`` MCP tool group (Task 7, extended RFC #1002 PR B).

ENV LIMITATION of the coverage in this module: the tests pin the CONTRACT of
the tool group (envelope keys, delegation, permissions) against the
deterministic ``mock`` LLM/embedding provider that ``settings_test.py`` forces
(ADR-02). Where a backend cannot answer at all (pgvector has no dialectic
engine) the patched seam below supplies the answer, so the answered branch is
CI-testable without Honcho. What this does NOT replace, and what no test here
proves: real-provider answer QUALITY, quota-dependent derivation transitions
(``derivation_status`` beyond pgvector's fixed ``unsupported``), a live
dialectic engine, and the end-to-end Celery queue -- the consolidation E2E test
never runs a consuming worker (see ``memory/tests/test_consolidation_e2e.py``).
"""
from datetime import datetime
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry, _READ_ONLY_TOOL_NAMES, _WRITE_TOOL_PREFIXES
from mcp_server.tools.memory import MemoryToolGroup
from memory.backends import MemoryHealth
from memory.models import MemoryEntry
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)


class TestMemoryToolGroupRegistration:
    def test_registered_in_registry(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "memory" in registry._groups

    def test_read_tools_are_read_only(self):
        assert "memory.query" in _READ_ONLY_TOOL_NAMES
        assert "memory.list" in _READ_ONLY_TOOL_NAMES
        assert "memory.get" in _READ_ONLY_TOOL_NAMES
        assert "memory.digest" in _READ_ONLY_TOOL_NAMES
        assert "memory.forget" not in _READ_ONLY_TOOL_NAMES
        assert "memory.write" not in _READ_ONLY_TOOL_NAMES
        # REQ-192/#1154 (code-review F1): memory.ask is NOT read-only -- it
        # invokes a generative LLM call, so a read_only/Viewer key must not be
        # able to drive LLM spend (same rule as interview.grounding_context).
        assert "memory.ask" not in _READ_ONLY_TOOL_NAMES
        assert "memory.ask" in _WRITE_TOOL_PREFIXES

    def test_write_tools_are_catalogued(self):
        assert "memory.forget" in _WRITE_TOOL_PREFIXES
        assert "memory.write" in _WRITE_TOOL_PREFIXES
        assert "memory.ask" in _WRITE_TOOL_PREFIXES


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """Keep the cached backend health from leaking between tests."""
    from memory.health import invalidate_health_cache

    invalidate_health_cache()
    yield
    invalidate_health_cache()


def _key_scoped_tools(monkeypatch, scope: str, roles=("editor",)) -> set:
    """Return the tool names a key of *scope* / *roles* would see advertised."""
    registry = ToolRegistry()
    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=tuple(roles),
        auth_method=AuthMethod.API_KEY,
        scope=scope,
    )
    monkeypatch.setattr(registry, "_validate_api_key", lambda _key: (ctx, None))
    monkeypatch.setattr(registry, "_resolve_list_roles", lambda _c, _ws: tuple(roles))
    return {tool["name"] for tool in registry.list_tools("reqlo_x")}


def _fake_dialectic(
    monkeypatch, *, degraded=False, detail="", answer="Because X, therefore Y."
) -> list[dict]:
    """Patch the active pgvector backend's ``ask`` to answer like a dialectic
    engine and record every call.

    Adapted from the identical seam in ``memory/tests/test_memory_rest.py``
    (REST mirror): pgvector cannot answer, so the ANSWERED branch of
    ``memory.ask`` would otherwise be untestable on the deterministic CI
    stack. Patches ``PgvectorMemoryBackend.ask`` only -- no new mock provider,
    no LLM involvement.

    Returns the call list; each entry carries the positional args the service
    passed to the backend.
    """
    from django.utils import timezone

    from memory.backends import MemoryAnswer, PgvectorMemoryBackend

    calls: list[dict] = []

    def _ask(self, tenant_id, scope, scope_id, query, *, reasoning_level=None):
        calls.append(
            {
                "tenant_id": tenant_id,
                "scope": scope,
                "scope_id": scope_id,
                "query": query,
                "reasoning_level": reasoning_level,
            }
        )
        return MemoryAnswer(
            text="" if degraded else answer,
            generated_at=timezone.now(),
            backend="pgvector",
            degraded=degraded,
            detail=detail,
        )

    monkeypatch.setattr(PgvectorMemoryBackend, "ask", _ask)
    return calls


@pytest.mark.django_db
class TestMemoryKeyScopeVisibility:
    def test_read_only_key_sees_neither_write_nor_forget(self, monkeypatch):
        names = _key_scoped_tools(monkeypatch, "read_only")
        assert "memory.write" not in names
        assert "memory.forget" not in names
        assert "memory.query" in names
        assert "memory.get" in names
        assert "memory.digest" in names
        # REQ-192/#1154 (code-review F1): memory.ask is write-gated (LLM spend),
        # so a read_only key must NOT see it.
        assert "memory.ask" not in names

    def test_author_key_sees_memory_write(self, monkeypatch):
        names = _key_scoped_tools(monkeypatch, "author")
        assert "memory.write" in names
        assert "memory.forget" in names
        assert "memory.ask" in names


@pytest.mark.django_db
class TestMemoryToolGroupHandlers:
    def test_query_returns_relevant_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "workspace", "workspace_id": str(ws.id), "query": "fact"},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert len(result.data["entries"]) == 1
            assert result.data["backend"] == "pgvector"
            assert result.data["degraded"] is False

    def test_list_returns_recent_entries(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact two.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "workspace", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert len(result.data["entries"]) == 2
            assert result.data["backend"] == "pgvector"
            assert "degraded" in result.data
            # AP-B5.1 (#1155): the envelope's derivation capability rides on
            # every envelope-carrying MCP memory response.
            assert result.data["derivation_status"] == "unsupported"

    def test_digest_returns_workspace_summary(self, monkeypatch):
        """``memory.digest`` answers the four-key digest shape (RFC #1002 F6)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Fact one.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_digest(
                params={"workspace_id": str(ws.id)}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert set(result.data) == {
                "digest",
                "generated_at",
                "backend",
                "degraded",
                "derivation_status",
                "derived_count",
            }
            assert "Fact one." in result.data["digest"]
            assert result.data["backend"] == "pgvector"
            assert result.data["degraded"] is False
            # AP-B5.1 (#1155): the derivation pair rides on the MCP digest too;
            # pgvector never derives, so it is "unsupported" with no count.
            assert result.data["derivation_status"] == "unsupported"
            assert result.data["derived_count"] is None
            # generated_at must be an ISO-8601 string, not a raw datetime.
            assert isinstance(result.data["generated_at"], str)
            datetime.fromisoformat(result.data["generated_at"])

    def test_digest_artifact_scope_via_execute_tool(self, monkeypatch):
        """An ``artifact_id`` narrows the digest to that artifact's memory."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            from persistence.models import Artifact

            ws = make_workspace(tenant)
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement"
            )
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "artifact", artifact.id, "Artifact fact.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group.execute_tool(
                "memory.digest",
                {"workspace_id": str(ws.id), "artifact_id": str(artifact.id)},
                ctx,
                None,
            )
            assert result.success
            assert set(result.data) == {
                "digest",
                "generated_at",
                "backend",
                "degraded",
                "derivation_status",
                "derived_count",
            }
            assert "Artifact fact." in result.data["digest"]
            datetime.fromisoformat(result.data["generated_at"])

    def test_digest_without_workspace_is_validation_error(self, monkeypatch):
        """``workspace_id`` is required by the input schema."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group.execute_tool("memory.digest", {}, ctx, None)
            assert not result.success
            assert result.error_code == "VALIDATION_ERROR"

    def test_digest_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", other_ws.id, "Secret fact.")
            ctx = editor_ctx(tenant, ws)  # role in `ws`, not in `other_ws`
            group = MemoryToolGroup()
            result = group._handle_digest(
                params={"workspace_id": str(other_ws.id)}, auth_context=ctx, api_key=None
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_ask_returns_degraded_answer_on_pgvector(self, monkeypatch):
        """REQ-192: ``memory.ask`` mirrors the digest's four keys. pgvector has
        no dialectic engine, so the answer is explicitly degraded rather than
        an empty non-degraded answer."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_ask(
                params={"query": "what do we know?", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert set(result.data) == {
                "answer",
                "generated_at",
                "backend",
                "degraded",
                "detail",
            }
            assert result.data["answer"] == ""
            assert result.data["backend"] == "pgvector"
            assert result.data["degraded"] is True
            # F5 (backend-reviewer): the degradation cause is passed through as
            # a non-user-data hint, so "cannot ask here" is distinguishable from
            # an outage.
            assert result.data["detail"] == "no dialectic engine"
            assert isinstance(result.data["generated_at"], str)
            datetime.fromisoformat(result.data["generated_at"])

    def test_ask_requires_query_and_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()

            without_query = group.execute_tool(
                "memory.ask", {"workspace_id": str(ws.id)}, ctx, None
            )
            assert not without_query.success
            assert without_query.error_code == "VALIDATION_ERROR"

            without_workspace = group.execute_tool("memory.ask", {"query": "hi"}, ctx, None)
            assert not without_workspace.success
            assert without_workspace.error_code == "VALIDATION_ERROR"

    def test_ask_unknown_reasoning_level_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup()._handle_ask(
                params={
                    "query": "q",
                    "workspace_id": str(ws.id),
                    "reasoning_level": "turbo",
                },
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "VALIDATION_ERROR"

    def test_ask_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)  # role in `ws`, not in `other_ws`
            group = MemoryToolGroup()
            result = group._handle_ask(
                params={"query": "secret?", "workspace_id": str(other_ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_ask_returns_answered_envelope_when_the_engine_can_answer(self, monkeypatch):
        """ANSWERED branch of ``memory.ask`` (MCP level).

        The degraded branch is covered above; this is the other half -- the
        branch that a dialectic engine (Honcho) produces in production. Because
        no engine runs on the deterministic CI stack, the backend's ``ask`` is
        patched with the same recording fake the REST mirror uses
        (``memory/tests/test_memory_rest.py``), so the tool's envelope AND its
        delegation (query/scope/reasoning_level forwarding, one backend call)
        are observable and pinned here too.

        ENV LIMITATION: this proves the CONTRACT of a successful answer, not
        answer QUALITY, and not the engine itself -- see the module docstring.
        """
        calls = _fake_dialectic(monkeypatch)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group.execute_tool(
                "memory.ask",
                {
                    "query": "why do we prefer REST?",
                    "workspace_id": str(ws.id),
                    "reasoning_level": "medium",
                },
                ctx,
                None,
            )

            assert result.success
            assert set(result.data) == {
                "answer",
                "generated_at",
                "backend",
                "degraded",
                "detail",
            }
            assert result.data["answer"] == "Because X, therefore Y."
            assert result.data["backend"] == "pgvector"
            assert result.data["degraded"] is False
            # An answered envelope carries no degradation cause.
            assert result.data["detail"] == ""
            assert isinstance(result.data["generated_at"], str)
            datetime.fromisoformat(result.data["generated_at"])

            # Exactly one backend call, with the resolved workspace scope and
            # the caller's reasoning level forwarded untouched.
            assert len(calls) == 1
            assert calls[0]["query"] == "why do we prefer REST?"
            assert calls[0]["scope"] == "workspace"
            assert calls[0]["scope_id"] == ws.id
            assert calls[0]["tenant_id"] == tenant.id
            assert calls[0]["reasoning_level"] == "medium"

    def test_ask_artifact_scope_reaches_the_artifact_backend_call(self, monkeypatch):
        """An ``artifact_id`` narrows the ask to that artifact's memory: the
        scope that reaches the backend is ``artifact`` with the artifact's own
        id, not the workspace scope the same call takes without one.
        """
        calls = _fake_dialectic(monkeypatch)
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            from persistence.models import Artifact

            ws = make_workspace(tenant)
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="Requirement"
            )
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup().execute_tool(
                "memory.ask",
                {
                    "query": "what does the requirement say?",
                    "workspace_id": str(ws.id),
                    "artifact_id": str(artifact.id),
                },
                ctx,
                None,
            )

            assert result.success
            assert result.data["degraded"] is False
            assert [(c["scope"], c["scope_id"]) for c in calls] == [
                ("artifact", artifact.id)
            ]

    def test_ask_degrades_when_the_engine_answers_with_a_failure(self, monkeypatch):
        """The answered branch is not "always healthy": when the patched engine
        reports a DEGRADED answer (engine outage, quota, ...), the tool must pass
        that through verbatim instead of re-shaping it into a success."""
        calls = _fake_dialectic(monkeypatch, degraded=True, detail="engine_error:Boom")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            result = MemoryToolGroup().execute_tool(
                "memory.ask",
                {"query": "anything?", "workspace_id": str(ws.id)},
                ctx,
                None,
            )

            assert result.success
            assert result.data["answer"] == ""
            assert result.data["degraded"] is True
            assert result.data["detail"] == "engine_error:Boom"
            assert len(calls) == 1

    def test_write_and_get_round_trip_with_provenance(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()

            written = group._handle_write(
                params={"content": "team fact", "scope": "workspace", "workspace_id": str(ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert written.success
            assert written.data["scope"] == "workspace"
            assert written.data["backend"] == "pgvector"
            assert written.data["degraded"] is False

            fetched = group._handle_get(
                params={"entry_id": written.data["entry_id"]}, auth_context=ctx, api_key=None
            )
            assert fetched.success
            assert fetched.data["content"] == "team fact"
            assert fetched.data["contributor_user_id"] == str(ctx.user_id)

    def test_write_user_scope_requires_no_workspace(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            result = MemoryToolGroup()._handle_write(
                params={"content": "my fact", "scope": "user"},
                auth_context=ctx,
                api_key=None,
            )
            assert result.success
            assert result.data["user_id"] == str(user.id)

    def test_forget_by_owner_succeeds(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "user", user.id, "A user fact.")
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(ref.entry_id)}, auth_context=ctx, api_key=None)
            assert result.success
            assert "degraded" in result.data

    def test_forget_accepts_a_honcho_style_nanoid(self, monkeypatch):
        """``entry_id`` is a String: an external nanoid resolves via backend_ref."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            entry = MemoryEntry.objects.create(
                tenant=tenant,
                scope=MemoryEntry.SCOPE_USER,
                user=user,
                content="mirrored honcho fact",
                backend_ref="nanoid0000000000000abc",
            )
            ctx = ctx_for_user(tenant, user)
            result = MemoryToolGroup()._handle_forget(
                params={"entry_id": "nanoid0000000000000abc"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert MemoryEntry.objects.filter(id=entry.id).count() == 0

    def test_forget_by_non_owner_is_denied(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            owner = make_user(tenant)
            other = make_user(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "user", owner.id, "Owner's fact.")
            ctx = ctx_for_user(tenant, other)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(ref.entry_id)}, auth_context=ctx, api_key=None)
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_forget_workspace_memory_requires_admin(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            ref = get_memory_backend().upsert(tenant.id, "workspace", ws.id, "Team fact.")
            editor = make_user(tenant)
            editor_context = ctx_for_user(tenant, editor, workspace=ws, roles=("editor",))
            group = MemoryToolGroup()
            denied = group._handle_forget(
                params={"entry_id": str(ref.entry_id)}, auth_context=editor_context, api_key=None
            )
            assert not denied.success
            assert denied.error_code == "PERMISSION_DENIED"

            admin = make_user(tenant)
            admin_context = ctx_for_user(tenant, admin, workspace=ws, roles=("admin",))
            allowed = group._handle_forget(
                params={"entry_id": str(ref.entry_id)}, auth_context=admin_context, api_key=None
            )
            assert allowed.success

    def test_query_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        """Final whole-branch review Finding 6: a caller valid for tenant T
        must not read memory content from a workspace in T it has no role
        in -- scope="workspace" used to trust any caller-supplied
        workspace_id outright."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", other_ws.id, "Secret fact.")
            # ctx has a role in `ws`, NOT in `other_ws`.
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "workspace", "workspace_id": str(other_ws.id), "query": "secret"},
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_list_denies_workspace_caller_has_no_role_in(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            other_ws = make_workspace(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "workspace", other_ws.id, "Secret fact.")
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "workspace", "workspace_id": str(other_ws.id)},
                auth_context=ctx,
                api_key=None,
            )
            assert not result.success
            assert result.error_code == "PERMISSION_DENIED"

    def test_query_scope_user_never_needs_workspace_membership(self, monkeypatch):
        """scope="user" was already safe (forces scope_id=auth_context.user_id)
        -- pin that the new membership check does not regress it."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            from memory.backends import get_memory_backend

            get_memory_backend().upsert(tenant.id, "user", user.id, "A user fact.")
            ctx = ctx_for_user(tenant, user)  # no workspace, no UserRole row at all
            group = MemoryToolGroup()
            result = group._handle_query(
                params={"scope": "user", "query": "fact"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert len(result.data["entries"]) == 1

    def test_query_malformed_workspace_id_is_validation_error(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            group = MemoryToolGroup()
            result = group.execute_tool(
                "memory.query",
                {"scope": "workspace", "workspace_id": "not-a-uuid", "query": "fact"},
                ctx,
                None,
            )
            assert not result.success
            assert result.error_code == "VALIDATION_ERROR"

    def test_forget_unresolvable_entry_id_is_not_found(self, monkeypatch):
        """``entry_id`` is a String, so a non-UUID value is a lookup, not a
        validation error (RFC #1002 PR B changed this deliberately)."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group.execute_tool("memory.forget", {"entry_id": "not-a-uuid"}, ctx, None)
            assert not result.success
            assert result.error_code == "NOT_FOUND"

    def test_forget_unknown_entry_not_found(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_forget(params={"entry_id": str(uuid4())}, auth_context=ctx, api_key=None)
            assert not result.success
            assert result.error_code == "NOT_FOUND"

    def test_degraded_is_reported_when_backend_is_unhealthy(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.setattr(
            "memory.health._probe",
            lambda: MemoryHealth(ok=False, backend="pgvector", detail="boom", degraded=True),
        )
        from memory.health import invalidate_health_cache

        invalidate_health_cache()
        with active_tenant() as tenant:
            user = make_user(tenant)
            ctx = ctx_for_user(tenant, user)
            group = MemoryToolGroup()
            result = group._handle_list(
                params={"scope": "user"}, auth_context=ctx, api_key=None
            )
            assert result.success
            assert result.data["entries"] == []
            assert result.data["degraded"] is True
