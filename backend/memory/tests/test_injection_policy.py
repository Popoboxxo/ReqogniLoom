"""Central slot-level memory-injection policy (Plan A T-A1-2, ADR-024 AC-3/AC-4).

Deliberately database-backed and mock-free for the policy itself: the contract
under test *is* the interaction between the Q1 three-level preference store
(``PreferenceService``), the ``WorkspaceMemorySettings`` facade and the slot
vocabulary, so an in-memory Q1 replacement would assert little more than the
test's own assumptions. Only the memory *backend* is faked (the policy's job is
to decide whether the backend is called at all, not what it answers).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from application.preference_service import PreferenceService
from application.prompt_slots import MEMORY_HARD_OFF_SLOTS, get_prompt_slots
from auth_tenancy.context import AuthContext, AuthMethod
from memory.backends import MemoryEntryRef
from memory.injection_policy import (
    ALLOW_USER_OPT_OUT_KEY,
    DISABLED_SLOTS_KEY,
    MEMORY_CONSUMER_SLOTS,
    USER_ENABLED_KEY,
    InjectionDecision,
    resolve_injection,
    validate_disabled_slots,
)
from memory.models import WorkspaceMemorySettings
from persistence.errors import ValidationError
from persistence.tests.factories import active_tenant, make_user, make_workspace

pytestmark = pytest.mark.django_db

_HARD_OFF_NAMES = (
    "interview.transcript_summary",
    "memory.extract",
    "bundle_compression",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(tenant, user, workspace=None, *roles: str) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=tuple(roles),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id if workspace is not None else None,
    )


class _RecordingBackend:
    """Minimal ``MemoryBackend`` double that records which scopes were queried."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def query(self, tenant_id, scope, scope_id, query_text, *, top_k):
        self.calls.append(scope)
        return [
            MemoryEntryRef(
                entry_id=uuid.uuid4(),
                content=f"{scope} memory fact",
                contributor_user_id=None,
            )
        ]


# ---------------------------------------------------------------------------
# Slot vocabulary
# ---------------------------------------------------------------------------


def test_consumer_slots_are_the_registry_memory_slots_plus_ai_review():
    """``MEMORY_CONSUMER_SLOTS`` is derived, not hand-maintained."""
    declared = {
        name
        for name, spec in get_prompt_slots().items()
        if "memory_context" in spec.data_variables
    }
    assert MEMORY_CONSUMER_SLOTS == declared | {"audit.ai_review"}


@pytest.mark.parametrize("name", _HARD_OFF_NAMES)
def test_hard_off_slots_are_not_consumers(name):
    assert name not in MEMORY_CONSUMER_SLOTS


def test_interview_protocol_slots_are_consumers():
    """Every ``interview.protocol.*`` slot declares ``memory_context``."""
    protocol = {s for s in MEMORY_CONSUMER_SLOTS if s.startswith("interview.protocol.")}
    assert protocol, "the interview protocol slots must be part of the policy vocabulary"


# ---------------------------------------------------------------------------
# Matrix: every consumer slot x {system, workspace, user} x {on, off}
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["system", "workspace", "user"])
@pytest.mark.parametrize("slot_name", sorted(MEMORY_CONSUMER_SLOTS))
def test_matrix_slot_toggle_at_each_level(level, slot_name):
    """A slot disabled at any level never injects; enabled it always does."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")
        service = PreferenceService()

        # "off" side of the matrix, baseline first so both halves are proven.
        enabled_decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name=slot_name,
        )
        assert enabled_decision == InjectionDecision(
            inject=True,
            scopes=("artifact", "workspace", "user"),
            reason="ok",
        )

        if level == "system":
            service.set_level(
                ctx, scope="global", values={DISABLED_SLOTS_KEY: [slot_name]}
            )
            expected_reason = "system_disabled"
        elif level == "workspace":
            service.set_level(
                ctx,
                scope="workspace",
                values={DISABLED_SLOTS_KEY: [slot_name]},
                workspace_id=ws.id,
            )
            expected_reason = "workspace_slot_disabled"
        else:
            service.set_level(
                ctx, scope="user", values={DISABLED_SLOTS_KEY: [slot_name]}
            )
            expected_reason = "user_slot_disabled"

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name=slot_name,
        )
        assert decision.inject is False
        assert decision.scopes == ()
        assert decision.reason == expected_reason


def test_disabled_workspace_blocks_injection():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        WorkspaceMemorySettings.objects.create(
            tenant_id=tenant.id, workspace=ws, enabled=False
        )

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name="testcase_derive",
        )

        assert decision.inject is False
        assert decision.reason == "workspace_disabled"


def test_missing_workspace_row_means_enabled():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name="testcase_derive",
        )

        assert decision.inject is True
        assert decision.reason == "ok"


@pytest.mark.parametrize("slot_name", ["", None])
def test_missing_slot_name_injects_nothing(slot_name):
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name=slot_name,
        )

        assert decision == InjectionDecision(False, (), "slot_missing")


@pytest.mark.parametrize(
    "slot_name",
    ["no_such_slot", "testcase_deriv", "interview.protocol", "audit.ai_review "],
)
def test_unknown_slot_name_fails_closed(slot_name):
    """A misspelled/renamed slot must never bypass the per-slot switches.

    Failing open would be invisible: no level of ``memory.disabled_slots`` can
    name a slot that is not in :data:`MEMORY_CONSUMER_SLOTS`, so every disable
    would be ignored for exactly the consumer that had the typo.
    """
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")
        # Even an explicit disable of every known slot leaves nothing to match.
        PreferenceService().set_level(
            ctx,
            scope="workspace",
            values={DISABLED_SLOTS_KEY: sorted(MEMORY_CONSUMER_SLOTS)},
            workspace_id=ws.id,
        )

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name=slot_name,
        )

        assert decision == InjectionDecision(False, (), "slot_missing")


@pytest.mark.parametrize("slot_name", sorted(MEMORY_HARD_OFF_SLOTS))
def test_hard_off_slot_injects_nothing(slot_name):
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name=slot_name,
        )

        assert decision == InjectionDecision(False, (), "hard_off")


def test_policy_lookup_failure_is_fail_safe(monkeypatch):
    """A broken Q1 lookup must never break the AI call: inject nothing."""

    def _boom(**kwargs):
        raise RuntimeError("preference store unreachable")

    monkeypatch.setattr("memory.injection_policy.levels_for", _boom)

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name="testcase_derive",
        )

        assert decision == InjectionDecision(False, (), "policy_unavailable")


def test_user_disabled_reports_user_opted_out():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")

        PreferenceService().set_level(ctx, scope="user", values={USER_ENABLED_KEY: False})

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name="testcase_derive",
        )

        assert decision.inject is False
        assert decision.reason == "user_opted_out"


def test_opt_out_forbidden_still_excludes_user_scope():
    """ENT-A7 = B: an opt-out the workspace forbids is overridden, but the
    personal ``user`` scope is never injected against the user's wish."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")
        service = PreferenceService()

        service.set_level(
            ctx,
            scope="workspace",
            values={ALLOW_USER_OPT_OUT_KEY: False},
            workspace_id=ws.id,
        )
        service.set_level(ctx, scope="user", values={USER_ENABLED_KEY: False})

        decision = resolve_injection(
            tenant_id=tenant.id,
            workspace_id=ws.id,
            user_id=user.id,
            slot_name="testcase_derive",
        )

        assert decision.inject is True
        assert decision.reason == "ok"
        assert decision.scopes == ("artifact", "workspace")
        assert "user" not in decision.scopes


# ---------------------------------------------------------------------------
# The validator behind ``memory.disabled_slots``
# ---------------------------------------------------------------------------


def test_validator_accepts_known_slots():
    validate_disabled_slots(["testcase_derive", "audit.ai_review"])


def test_validator_rejects_unknown_slot():
    with pytest.raises(ValidationError):
        validate_disabled_slots(["no_such_slot"])


@pytest.mark.parametrize("slot_name", _HARD_OFF_NAMES)
def test_validator_rejects_hard_off_slot(slot_name):
    with pytest.raises(ValidationError, match="slot is hard-off"):
        validate_disabled_slots([slot_name])


# ---------------------------------------------------------------------------
# Production consumers honour the policy
# ---------------------------------------------------------------------------


def test_ai_review_respects_workspace_slot_disabled(monkeypatch):
    """``audit.ai_review`` is a consumer slot like any other."""
    from application.ai_review_service import AiReviewService

    backend = _RecordingBackend()
    monkeypatch.setattr("memory.context_builder.get_memory_backend", lambda: backend)

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")
        findings = [{"rule_id": "TRACE-P1", "index": 0}]

        enabled = AiReviewService._build_memory_context(ctx, ws.id, findings)
        assert "Workspace context:" in enabled
        assert backend.calls == ["workspace", "user"]

        PreferenceService().set_level(
            ctx,
            scope="workspace",
            values={DISABLED_SLOTS_KEY: ["audit.ai_review"]},
            workspace_id=ws.id,
        )
        backend.calls.clear()

        blocked = AiReviewService._build_memory_context(ctx, ws.id, findings)
        assert blocked == ""
        assert backend.calls == []


def test_interview_chat_turn_respects_user_opt_out(monkeypatch):
    """The bypass path (InterviewService builds its own prompt) is covered too."""
    from application.interview_service import InterviewService

    backend = _RecordingBackend()
    monkeypatch.setattr("memory.context_builder.get_memory_backend", lambda: backend)

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "editor")
        session = SimpleNamespace(
            workspace_id=ws.id,
            artifact_id=None,
            artifact_type="Requirement",
            transcript=[],
            transcript_summary="",
            grounding_snapshot={},
        )
        phase = SimpleNamespace(prompt_fragment="Phase 1")

        enabled_prompt = InterviewService()._chat_turn_prompt(
            ctx, session, "Which problem?", phase, []
        )
        assert "Workspace context:" in enabled_prompt
        assert "User context:" in enabled_prompt

        PreferenceService().set_level(
            ctx, scope="user", values={USER_ENABLED_KEY: False}
        )
        backend.calls.clear()

        opted_out_prompt = InterviewService()._chat_turn_prompt(
            ctx, session, "Which problem?", phase, []
        )
        assert "Workspace context:" not in opted_out_prompt
        assert "User context:" not in opted_out_prompt
        assert backend.calls == []


def test_build_memory_context_without_slot_injects_nothing(monkeypatch):
    """A dynamic ``**kwargs`` caller that omits ``slot_name`` degrades."""
    from memory.context_builder import build_memory_context

    backend = _RecordingBackend()
    monkeypatch.setattr("memory.context_builder.get_memory_backend", lambda: backend)

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        dynamic_kwargs: dict[str, object] = {}

        context = build_memory_context(
            tenant.id, ws.id, user.id, "architecture question", **dynamic_kwargs
        )

        assert context == ""
        assert backend.calls == []


def test_build_memory_context_never_queries_the_user_scope_when_forbidden(
    monkeypatch,
):
    """ENT-A7 = B end-to-end: opt-out + forbidden opt-out = no user scope."""
    from memory.context_builder import build_memory_context

    backend = _RecordingBackend()
    monkeypatch.setattr("memory.context_builder.get_memory_backend", lambda: backend)

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        ctx = _ctx(tenant, user, ws, "admin")
        service = PreferenceService()
        service.set_level(
            ctx,
            scope="workspace",
            values={ALLOW_USER_OPT_OUT_KEY: False},
            workspace_id=ws.id,
        )
        service.set_level(ctx, scope="user", values={USER_ENABLED_KEY: False})

        context = build_memory_context(
            tenant.id, ws.id, user.id, "architecture question", slot_name="testcase_derive"
        )

        assert "Workspace context:" in context
        assert "User context:" not in context
        assert backend.calls == ["workspace"]
