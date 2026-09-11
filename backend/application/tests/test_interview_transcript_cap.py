"""L2.4: sliding transcript window + LLM compression of the overflow."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from application.interview_service import InterviewService
from application.prompt_slots import get_prompt_slots
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSession, Tenant, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="TC Tenant", slug="tc-tenant")


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant):
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


def _session_with_entries(ctx, workspace, entry_count: int) -> InterviewSession:
    session = InterviewService().start(ctx, "Requirement", workspace.id)
    entries = [
        {"role": "user" if i % 2 == 0 else "assistant", "text": f"m{i}", "timestamp": "t"}
        for i in range(entry_count)
    ]
    TenantContext.set_tenant(ctx.tenant_id)
    try:
        InterviewSession.objects.filter(id=session.id).update(transcript=entries)
        return InterviewSession.objects.get(id=session.id)
    finally:
        TenantContext.clear_tenant()


class TestTranscriptSummaryPrompt:
    def test_slot_is_registered_with_its_placeholders(self):
        slots = get_prompt_slots()
        assert "interview.transcript_summary" in slots
        names = set(slots["interview.transcript_summary"].data_variables)
        assert names == {"previous_summary", "overflow_json"}

    def test_factory_default_template_exists_and_uses_both_placeholders(self):
        template = PROMPT_TEMPLATE_DEFAULTS["interview.transcript_summary"]
        assert "{previous_summary}" in template
        assert "{overflow_json}" in template

    def test_chat_turn_slot_gained_the_summary_placeholder(self):
        """The chat prompt must carry the compressed history, or capping the
        transcript would silently drop context instead of condensing it."""
        slots = get_prompt_slots()
        assert "transcript_summary" in set(slots["interview.chat_turn"].data_variables)
        assert "{transcript_summary}" in slots["interview.chat_turn"].default_content


class TestTranscriptCompression:
    def test_does_nothing_below_the_window(self, ctx, workspace):
        # 10 turns = 20 entries -- exactly at the window, nothing to fold out.
        session = _session_with_entries(ctx, workspace, 20)
        with patch.object(InterviewService, "_resolve_provider") as resolver:
            InterviewService()._compress_transcript_if_needed(ctx, session)
        resolver.assert_not_called()
        assert len(session.transcript) == 20
        assert session.transcript_summary == ""

    def test_folds_the_overflow_into_the_summary(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "  Condensed history.  "
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == "Condensed history."
        # Only the newest 20 entries survive; the 6 oldest were folded in.
        assert len(session.transcript) == 20
        assert session.transcript[0]["text"] == "m6"
        assert session.transcript[-1]["text"] == "m25"

    def test_persists_the_compression(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "Condensed."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert reloaded.transcript_summary == "Condensed."
        assert len(reloaded.transcript) == 20

    def test_provider_failure_leaves_the_transcript_intact(self, ctx, workspace):
        """Spec §7: a failed LLM call must not block or truncate the
        interview -- the turn stays, compression retries next turn."""
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("provider down")
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26

    def test_no_provider_leaves_the_transcript_intact(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        with patch.object(
            InterviewService,
            "_resolve_provider",
            return_value=(None, "mock", RuntimeError("unconfigured")),
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26

    def test_empty_summary_leaves_the_transcript_intact(self, ctx, workspace):
        """An empty digest would DISCARD the overflow turns -- treat it
        exactly like a failed call."""
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "   "
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26

    def test_previous_summary_is_fed_back_in(self, ctx, workspace):
        """The second compression must supersede the first summary, not
        append to it -- otherwise the digest grows unboundedly and defeats
        the whole cap."""
        session = _session_with_entries(ctx, workspace, 26)
        session.transcript_summary = "Earlier digest."
        provider = MagicMock()
        provider.complete.return_value = "Merged digest."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "mock", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        prompt = provider.complete.call_args[0][0]
        assert "Earlier digest." in prompt
        assert session.transcript_summary == "Merged digest."
