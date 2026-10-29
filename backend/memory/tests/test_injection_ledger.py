"""Plan A T-A1-5 / ADR-024 AC-6 — ``memory_injected`` transparency field.

The ledger is the single record of "what memory actually went into this AI
call". ``build_memory_context`` writes exactly one entry per call (including the
``inject=False`` ones, which become ``suppressed`` with their policy reason);
three thin wrappers expose the result:

* :class:`memory.middleware.MemoryInjectionLedgerMiddleware` for REST dict
  responses (2xx only),
* the MCP dispatch wrapper in ``mcp_server.tool_registry.ToolRegistry`` for
  successful ``ToolResult`` payloads,
* ``llm_adapter.tasks.run_capability`` for the Celery result dict.

Everything is additive: a response that involved no memory-capable slot must
stay byte-identical (``test_non_ai_endpoint_unchanged``).

req_id : REQ-L2-AI-001 / ADR-024 AC-6
"""
from __future__ import annotations

import hashlib

import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory

from application.preference_service import PreferenceService
from application.prompt_resolver import resolve_and_render
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.services.authentication import AuthenticationService
from memory.backends import get_memory_backend
from memory.context_builder import build_memory_context
from memory.injection_ledger import Ledger, current_ledger, open_ledger, record
from memory.injection_policy import DISABLED_SLOTS_KEY, InjectionDecision
from memory.middleware import MemoryInjectionLedgerMiddleware
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, StakeholderNeed
from persistence.tests.factories import (
    active_tenant,
    editor_user_and_token,
    make_user,
    make_workspace,
)

_DERIVE_URL = "/api/v1/needs/{need}/derive-requirements/"
_MCP_DERIVE_TOOL = "ai_derivation.derive_requirements_from_need"


def _pinned_embedding(text: str) -> list[float] | None:
    """Deterministic embedding for *text*, independent of any provider.

    Same rationale (and same construction) as ``test_context_builder``'s
    helper: the hit set must not depend on which embedding provider happens to
    resolve, and the mock provider's hash-seeded RNG vectors are semantically
    meaningless.
    """
    if not text or not text.strip():
        return None
    raw = hashlib.shake_256(text.encode("utf-8")).digest(EMBEDDING_VECTOR_DIMENSIONS)
    return [byte / 255.0 * 2.0 - 1.0 for byte in raw]


@pytest.fixture(autouse=True)
def _deterministic_memory_embeddings(monkeypatch):
    """Pin the memory backend + embeddings these tests write and query by."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("MEMORY_BACKEND", "pgvector")
    monkeypatch.setattr("memory.backends.generate_embedding", _pinned_embedding)
    monkeypatch.setattr(
        "memory.backends.generate_embedding_with_model",
        lambda text: (_pinned_embedding(text), "mock:test:384"),
    )


def _make_need(tenant, workspace, title: str = "A need") -> StakeholderNeed:
    """Create a StakeholderNeed (with its backing Artifact) via the ORM."""
    artifact = Artifact.objects.create(
        workspace=workspace, artifact_type="StakeholderNeed", tenant_id=tenant.id
    )
    return StakeholderNeed.objects.create(
        artifact=artifact, tenant_id=tenant.id, title=title, description="desc"
    )


# ---------------------------------------------------------------------------
# Unit level: the ledger itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_suppressed_reason_is_recorded():
    """A blocked slot lands under ``suppressed`` with its policy reason."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        with open_ledger() as ledger:
            # ``bundle_compression`` is a HARD_OFF slot (T-A1-1): the policy
            # answers inject=False/reason="hard_off" and nothing is rendered.
            text = build_memory_context(
                tenant.id, ws.id, user.id, "anything", slot_name="bundle_compression"
            )

        assert text == ""
        assert ledger.as_contract() == {
            "slots": [],
            "scopes": [],
            "count": 0,
            "suppressed": [{"slot": "bundle_compression", "reason": "hard_off"}],
        }


def test_nested_ledger_keeps_outer_entries():
    """A nested ``open_ledger`` reuses the outer ledger and never closes it."""
    with open_ledger() as outer:
        outer_contract_before = outer.as_contract()
        assert outer_contract_before is None  # no entry yet

        with open_ledger() as inner:
            assert inner is outer
            record(
                "testcase_derive",
                InjectionDecision(inject=True, scopes=("workspace",), reason="ok"),
                {"workspace": 2},
            )

        # The inner block ended: the outer ledger is still the active one and
        # its entries survived.
        assert current_ledger() is outer
        assert outer.as_contract() == {
            "slots": ["testcase_derive"],
            "scopes": ["workspace"],
            "count": 2,
            "suppressed": [],
        }

    # The outermost block closed the ledger for good.
    assert current_ledger() is None


def test_record_without_an_open_ledger_is_a_noop():
    """Recording outside any ledger must not raise or leak state."""
    assert current_ledger() is None
    record(
        "need_to_sysreq",
        InjectionDecision(inject=True, scopes=("workspace",), reason="ok"),
        {"workspace": 3},
    )
    assert current_ledger() is None


def test_zero_hit_call_does_not_list_the_slot():
    """``slots`` means "slots that injected content", not "slots consulted".

    The policy allowed memory but every scope came back empty, so nothing
    reached the prompt — the slot must not be reported as an injection and no
    contract is produced at all (the response stays byte-identical).
    """
    ledger = Ledger()
    ledger.record(
        "testcase_derive",
        InjectionDecision(inject=True, scopes=("workspace",), reason="ok"),
        {"workspace": 0},
    )

    assert ledger.slots == []
    assert ledger.count == 0
    assert ledger.as_contract() is None


@pytest.mark.django_db
def test_resolver_suppressed_path_records_reason():
    """A workspace-disabled slot is reported through the real resolver path.

    Unlike the direct HARD_OFF call above, this is the reachable suppression
    path: ``resolve_and_render`` -> ``_auto_memory_context`` ->
    ``build_memory_context``, i.e. what a production AI call actually does.
    """
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            # Admin: writing a workspace-wide preference requires the
            # WORKSPACE_CONFIG operation (application.permissions).
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=ws.id,
        )
        # Content that WOULD be injected if the slot were allowed — so the
        # "nothing was injected" assertion below cannot pass vacuously.
        get_memory_backend().upsert(
            tenant.id, "workspace", ws.id, "SECRET-FACT-MUST-NOT-APPEAR"
        )
        PreferenceService().set_level(
            ctx,
            scope="workspace",
            values={DISABLED_SLOTS_KEY: ["testcase_derive"]},
            workspace_id=ws.id,
        )

        with open_ledger() as ledger:
            rendered = resolve_and_render(
                "testcase_derive", ctx, ws.id, testcase_title="t"
            )

        contract = ledger.as_contract()
        assert contract == {
            "slots": [],
            "scopes": [],
            "count": 0,
            "suppressed": [{"slot": "testcase_derive", "reason": "workspace_slot_disabled"}],
        }
        assert "SECRET-FACT-MUST-NOT-APPEAR" not in rendered
        assert "Workspace context:" not in rendered


# ---------------------------------------------------------------------------
# REST: a real AI endpoint reports the field, a non-AI one does not
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rest_ai_endpoint_reports_memory_injected():
    """POST .../derive-requirements/ (mock LLM) reports slot/scope/count."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user, token = editor_user_and_token(tenant, ws)
        # One workspace-scope fact so ``count``/``scopes`` are non-empty.
        get_memory_backend().upsert(
            tenant.id, "workspace", ws.id, "Project uses hexagonal architecture."
        )
        need = _make_need(tenant, ws)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post(_DERIVE_URL.format(need=need.id), {"n": 2}, format="json")

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["memory_injected"] == {
            "slots": ["need_to_sysreq"],
            "scopes": ["workspace"],
            "count": 1,
            "suppressed": [],
        }
        # The AI payload itself is unchanged by the addition.
        assert len(body["drafts"]) == 2


@pytest.mark.django_db
def test_non_ai_endpoint_unchanged():
    """A plain CRUD read carries no ``memory_injected`` key."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        _user, token = editor_user_and_token(tenant, ws)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get("/api/v1/requirements/", {"workspace_id": str(ws.id)})

        assert response.status_code == 200, response.content
        assert "memory_injected" not in response.json()


@pytest.mark.django_db
def test_middleware_leaves_list_and_error_payloads_untouched():
    """Only a 2xx dict response is augmented — lists and errors stay as they are."""
    middleware = MemoryInjectionLedgerMiddleware(lambda request: None)
    request = APIRequestFactory().get("/")
    decision = InjectionDecision(inject=True, scopes=("workspace",), reason="ok")

    with open_ledger():
        record("need_to_sysreq", decision, {"workspace": 1})

        list_response = middleware.process_template_response(
            request, Response([{"id": 1}], status=200)
        )
        error_response = middleware.process_template_response(
            request, Response({"error": {"code": "NOT_FOUND"}}, status=404)
        )

    assert list_response.data == [{"id": 1}]
    assert error_response.data == {"error": {"code": "NOT_FOUND"}}


# ---------------------------------------------------------------------------
# MCP: the dispatch wrapper reports the field on a successful dict payload
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_mcp_tool_reports_memory_injected():
    """A real memory-consuming MCP tool returns ``memory_injected`` in its payload."""
    from mcp_server.tool_registry import ToolRegistry

    with active_tenant() as tenant:
        ws = make_workspace(tenant, preset={"name": "extended"})
        user, _token = editor_user_and_token(tenant, ws)
        # One workspace-scope fact, so the slot really injects something and
        # therefore belongs in ``slots`` (a consulted-but-empty slot does not —
        # see ``test_zero_hit_call_does_not_list_the_slot``).
        get_memory_backend().upsert(
            tenant.id, "workspace", ws.id, "Project uses hexagonal architecture."
        )
        need = _make_need(tenant, ws)
        api_key = AuthenticationService().create_api_key(
            user_id=user.id, tenant_id=tenant.id, name="ledger-test-key"
        )

        result = ToolRegistry().dispatch_request(
            tool_name=_MCP_DERIVE_TOOL,
            params={"need_id": str(need.id), "n": 2},
            api_key=api_key.plaintext,
        )

    assert result.success, result.message
    assert result.data["memory_injected"] == {
        "slots": ["need_to_sysreq"],
        "scopes": ["workspace"],
        "count": 1,
        "suppressed": [],
    }
    assert len(result.data["drafts"]) == 2
