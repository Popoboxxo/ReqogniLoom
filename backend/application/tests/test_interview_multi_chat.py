"""InterviewService.generate_chat_turn() multi-mode branch + propose().

Plan Task 5 (docs/superpowers/plans/2026-08-24-multi-artifact-interview.md,
lines 756-871). Three binding scenarios:

  1. A multi-session chat turn stores the LLM's parsed fenced-JSON proposal
     into ``grounding_snapshot["pending_proposal"]``.
  2. ``propose()`` returns None when nothing is pending yet.
  3. ``propose()`` returns the stored proposal.

Adaptations to real code vs. the plan's sketch:

  * The plan patches ``InterviewService._call_llm`` -- no such method exists.
    The real LLM call site is ``self._resolve_provider()`` followed by
    ``provider.complete(prompt, purpose=..., timeout=...)`` (the exact seam
    single-mode generate_chat_turn already uses), so the fake provider is
    injected through ``_resolve_provider`` like test_interview_service.py's
    chat-turn tests do.
  * Fixtures are local (no persistence.tests.factories): same pattern as
    test_architecture_decompose.py / test_interview_formalize_multi.py --
    TenantContext.set_tenant/clear_tenant in try/finally plus an editor
    AuthContext constructed inline.
"""
from __future__ import annotations

import contextlib
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from application.base import ValidationError
from application.interview_service import InterviewService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    InterviewSession,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures + helpers (local -- same pattern as test_architecture_decompose.py)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="IV-Multi-Chat Tenant", slug="iv-multi-chat")


@pytest.fixture
def editor_user(tenant: Tenant) -> User:
    # Real User row: service writes reference ctx.user_id and pytest-django's
    # flush would hit FK constraints on a phantom id otherwise.
    return User.objects.create(
        username="iv-multi-chat-editor", email="chat-editor@example.com", tenant=tenant
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    with _active(tenant):
        return Workspace.objects.create(tenant=tenant, name="IV-Multi-Chat-WS")


@pytest.fixture
def editor_ctx(editor_user: User) -> AuthContext:
    return AuthContext(
        user_id=editor_user.id,
        tenant_id=editor_user.tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _multi_session(tenant: Tenant, ws: Workspace) -> InterviewSession:
    with _active(tenant):
        return InterviewSession.objects.create(
            tenant=tenant,
            workspace=ws,
            artifact_type=None,
            session_kind=InterviewSession.SESSION_KIND_MULTI,
            status=InterviewSession.STATUS_IN_PROGRESS,
        )


class _MultiFakeProvider:
    """Provider double whose .complete() returns a fixed multi-protocol reply.

    Non-vacuous double principle (cf. test_interview_service._ChatFakeProvider):
    the reply carries a real fenced ```json block exactly as a provider
    following interview.protocol.multi would emit one."""

    def __init__(self, reply: str):
        self._reply = reply
        self.last_prompt = None

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        self.last_prompt = prompt
        return self._reply


_FENCED_PROPOSAL_REPLY = """Sounds good, here is the proposal:
```json
[{"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []}]
```"""


class _FailingProvider:
    """Provider double whose .complete() always raises -- mirrors how the
    single-mode path tests surface provider outages as ValidationError."""

    def __init__(self, error: Exception):
        self._error = error

    def complete(self, prompt, *, purpose="", context=None, timeout=None):
        raise self._error


class _AuditSpy:
    """Stands in for LlmAuditLogger and records every log_llm_call payload."""

    def __init__(self):
        self.calls: list[dict] = []

    def log_llm_call(self, **kwargs):
        self.calls.append(kwargs)


class TestMultiChatGuards:
    """Review-2 fixes on the multi chat path (M1/M2/M3/n2):

    * M1 -- a non-in_progress multi session is rejected by the same
      hoisted status guard as single mode, BEFORE any provider call.
    * M2 -- the REQ-106 daily token budget gates the multi path too.
    * M3 -- every exit (budget-exceeded / provider failure / success)
      writes an LlmAuditLogger.log_llm_call entry like single mode.
    * n2 -- the transcript save bumps ``version`` (+ modified_at) exactly
      like every other session write.
    """

    def test_completed_multi_session_rejects_chat(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type=None,
                session_kind=InterviewSession.SESSION_KIND_MULTI,
                status=InterviewSession.STATUS_COMPLETED,
            )
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().generate_chat_turn(editor_ctx, session.id, "hello?")

        # Same message shape as the single-mode guard, and the guard must
        # fire BEFORE the provider call (last_prompt stays unset).
        assert "completed" in str(excinfo.value)
        assert "cannot chat." in str(excinfo.value)
        assert provider.last_prompt is None

    def test_abandoned_multi_session_rejects_chat(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type=None,
                session_kind=InterviewSession.SESSION_KIND_MULTI,
                status=InterviewSession.STATUS_ABANDONED,
            )
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().generate_chat_turn(editor_ctx, session.id, "hello?")

        assert "abandoned" in str(excinfo.value)
        assert provider.last_prompt is None

    def test_exhausted_budget_rejects_chat_and_audits_limit_exceeded(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        """M2/M3: budget check runs before the provider call and the
        rejection is audited exactly like single mode's."""
        session = _multi_session(tenant, workspace)
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )
        monkeypatch.setattr(
            "llm_adapter.token_tracking.is_over_daily_limit", lambda: True
        )
        spy = _AuditSpy()
        monkeypatch.setattr("llm_adapter.audit_logger.LlmAuditLogger", lambda: spy)

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().generate_chat_turn(editor_ctx, session.id, "another turn")

        assert "Daily LLM token limit exceeded" in str(excinfo.value)
        # Guard fires BEFORE the provider call.
        assert provider.last_prompt is None
        assert len(spy.calls) == 1
        assert spy.calls[0] == {
            "provider": "anthropic",
            "capability": "interview.chat_turn",
            "artifact_id": str(session.id),
            "token_usage": None,
            "success": False,
            "error": "LLM_TOKEN_LIMIT_EXCEEDED",
        }

    def test_successful_turn_audits_success_and_records_tokens(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        session = _multi_session(tenant, workspace)
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )
        monkeypatch.setattr(
            "llm_adapter.token_tracking.is_over_daily_limit", lambda: False
        )
        record_mock = MagicMock()
        monkeypatch.setattr(
            "llm_adapter.token_tracking.record_token_usage", record_mock
        )
        spy = _AuditSpy()
        monkeypatch.setattr("llm_adapter.audit_logger.LlmAuditLogger", lambda: spy)

        result = InterviewService().generate_chat_turn(editor_ctx, session.id, "I need something for X")

        assert result["proposal"][0]["type"] == "StakeholderNeed"
        assert len(spy.calls) == 1
        assert spy.calls[0]["success"] is True
        assert spy.calls[0]["error"] is None
        record_mock.assert_called_once_with(
            provider="anthropic", capability="interview.chat_turn", input_tokens=0
        )

    def test_provider_failure_audits_failure_then_raises(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        session = _multi_session(tenant, workspace)
        monkeypatch.setattr(
            InterviewService,
            "_resolve_provider",
            lambda self: (_FailingProvider(RuntimeError("kaboom")), "anthropic", None),
        )
        monkeypatch.setattr(
            "llm_adapter.token_tracking.is_over_daily_limit", lambda: False
        )
        spy = _AuditSpy()
        monkeypatch.setattr("llm_adapter.audit_logger.LlmAuditLogger", lambda: spy)

        with pytest.raises(ValidationError) as excinfo:
            InterviewService().generate_chat_turn(editor_ctx, session.id, "turn")

        assert "Interview chat LLM call failed" in str(excinfo.value)
        assert len(spy.calls) == 1
        assert spy.calls[0]["success"] is False
        assert spy.calls[0]["error"] == "kaboom"

    def test_multi_chat_save_bumps_version(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        """n2: the multi chat save uses the same F('version') + 1 bump as
        the single-mode chat save and _formalize_multi."""
        session = _multi_session(tenant, workspace)
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        with _active(tenant):
            version_before = InterviewSession.objects.get(id=session.id).version

            InterviewService().generate_chat_turn(editor_ctx, session.id, "turn")

            session.refresh_from_db()
            assert session.version == version_before + 1


class TestMultiChatTurn:
    def test_chat_turn_stores_parsed_proposal(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext, monkeypatch
    ):
        session = _multi_session(tenant, workspace)
        provider = _MultiFakeProvider(_FENCED_PROPOSAL_REPLY)
        monkeypatch.setattr(
            InterviewService, "_resolve_provider", lambda self: (provider, "anthropic", None)
        )

        with _active(tenant):
            result = InterviewService().generate_chat_turn(
                editor_ctx, session.id, "I need something for X"
            )

        assert result["proposal"][0]["type"] == "StakeholderNeed"
        session.refresh_from_db()
        assert session.grounding_snapshot["pending_proposal"][0]["type"] == "StakeholderNeed"

    def test_propose_returns_none_when_nothing_pending(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        session = _multi_session(tenant, workspace)

        with _active(tenant):
            assert InterviewService().propose(editor_ctx, session.id) is None

    def test_propose_returns_stored_proposal(
        self, tenant: Tenant, workspace: Workspace, editor_ctx: AuthContext
    ):
        proposal = [
            {"type": "StakeholderNeed", "title": "Need A", "fields": {"title": "Need A"}, "links": []}
        ]
        with _active(tenant):
            session = InterviewSession.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type=None,
                session_kind=InterviewSession.SESSION_KIND_MULTI,
                status=InterviewSession.STATUS_IN_PROGRESS,
                grounding_snapshot={"pending_proposal": proposal},
            )

        with _active(tenant):
            assert InterviewService().propose(editor_ctx, session.id) == proposal
