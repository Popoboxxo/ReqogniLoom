"""L2.4: sliding transcript window + LLM compression of the overflow.

Note on the provider name in the ``_resolve_provider`` patches below: it has
to be a *real* provider name ("anthropic"), not "mock". Compression is
skipped entirely for a configured mock provider (issue #442's rule, review
finding F1) -- a patch returning ``(MagicMock(), "mock", None)`` would
therefore never reach the provider call at all.
"""
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
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
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
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
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
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
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
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
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
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        prompt = provider.complete.call_args[0][0]
        assert "Earlier digest." in prompt
        assert session.transcript_summary == "Merged digest."


class TestRealMockProviderNeverCompresses:
    """Review finding F1 -- the data-loss bug every other test in this module
    missed, because they all patch ``_resolve_provider`` with a MagicMock.

    These tests deliberately do NOT patch it: they go through the real
    ``get_provider()`` with ``LLM_PROVIDER=mock`` (the documented default of
    the entire dev stack, and what settings_test/docker-compose.test.yml set),
    which hands back a live MockLlmProvider.
    """

    def test_the_mock_provider_really_would_return_a_truthy_placeholder(self):
        """Why the guard is needed at all: MockLlmProvider has no branch for
        this purpose and falls through to ``json.dumps([])``. "[]" is a
        non-empty string, so the empty-summary guard does NOT catch it."""
        from llm_adapter.providers import MockLlmProvider

        assert (
            MockLlmProvider().complete("prompt", purpose="interview.transcript_summary")
            == "[]"
        )

    def test_configured_mock_provider_leaves_the_transcript_untouched(
        self, ctx, workspace, monkeypatch
    ):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        session = _session_with_entries(ctx, workspace, 26)

        # The real resolution really does yield a usable mock provider here --
        # otherwise this test would pass for the wrong reason (provider None).
        provider, provider_name, _ = InterviewService()._resolve_provider()
        assert provider is not None and provider_name == "mock"

        InterviewService()._compress_transcript_if_needed(ctx, session)

        assert session.transcript_summary == ""
        assert len(session.transcript) == 26
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert reloaded.transcript_summary == ""
        assert len(reloaded.transcript) == 26

    def test_full_chat_turn_on_the_mock_default_keeps_every_entry(
        self, ctx, workspace, monkeypatch
    ):
        """End-to-end on the project's default config, with NOTHING patched:
        a turn that pushes the transcript past the window must still leave the
        whole history intact. The chat turn deliberately does call the mock
        provider (it is not fail-open); only compression refuses to."""
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        session = _session_with_entries(ctx, workspace, 20)

        result = InterviewService().generate_chat_turn(ctx, session.id, "one more")

        # MockLlmProvider has no interview.chat_turn branch either, so the
        # reply is its generic "[]" placeholder -- the point here is the
        # transcript, not the reply.
        assert "reply" in result
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert len(reloaded.transcript) == 22
        assert reloaded.transcript_summary == ""


class TestCompressionAccounting:
    """Review finding F2 -- budget gate + audit/token accounting."""

    def test_over_budget_skips_compression_without_raising(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ), patch("llm_adapter.token_tracking.is_over_daily_limit", return_value=True):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        provider.complete.assert_not_called()
        assert len(session.transcript) == 26
        assert session.transcript_summary == ""

    def test_successful_compression_records_audit_and_tokens(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "Condensed."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ), patch(
            "llm_adapter.audit_logger.LlmAuditLogger.log_llm_call"
        ) as log_call, patch(
            "llm_adapter.token_tracking.record_token_usage"
        ) as record:
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert log_call.call_args.kwargs["capability"] == "interview.transcript_summary"
        assert log_call.call_args.kwargs["success"] is True
        assert record.call_args.kwargs["capability"] == "interview.transcript_summary"
        assert record.call_args.kwargs["input_tokens"] > 0
        assert record.call_args.kwargs["output_tokens"] > 0


class TestCompressionNeverRaises:
    """Review finding F3 -- the template lookup / render / save used to sit
    outside the try, so they could 500 an already-committed chat turn."""

    def test_template_lookup_failure_is_swallowed(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ), patch(
            "application.ai_derivation_service.AiDerivationService._get_template_content",
            side_effect=RuntimeError("prompt table unavailable"),
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        assert len(session.transcript) == 26
        assert session.transcript_summary == ""

    def test_chat_turn_survives_a_template_lookup_failure(self, ctx, workspace):
        """The turn is already committed when compression runs -- a failure
        there must not turn a successful turn into a 500."""
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.return_value = '{"extracted_fields": {}, "reply": "ok"}'
        real_template = None

        def _fail_only_for_the_summary(ctx_, name, *args, **kwargs):
            if name == "interview.transcript_summary":
                raise RuntimeError("prompt table unavailable")
            return real_template(ctx_, name, *args, **kwargs)

        from application.ai_derivation_service import AiDerivationService

        real_template = AiDerivationService._get_template_content
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ), patch.object(
            AiDerivationService,
            "_get_template_content",
            side_effect=_fail_only_for_the_summary,
        ):
            result = InterviewService().generate_chat_turn(ctx, session.id, "one more")

        assert result["reply"] == "ok"


class TestCompressionConcurrency:
    """Review finding F4 -- a turn persisted by a concurrent request during
    the (slow) compression call used to be silently dropped."""

    def test_turn_added_during_the_llm_call_is_not_lost(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)

        def _racing_complete(*args, **kwargs):
            # Stands in for a concurrent request that appended a turn while
            # provider.complete() was blocking. The tenant context stays armed
            # afterwards -- the service armed it before this call and still
            # needs it for the audit write and save() that follow.
            TenantContext.set_tenant(ctx.tenant_id)
            row = InterviewSession.objects.get(id=session.id)
            InterviewSession.objects.filter(id=session.id).update(
                transcript=[
                    *row.transcript,
                    {"role": "user", "text": "raced-in", "timestamp": "t"},
                ]
            )
            return "Condensed."

        provider = MagicMock()
        provider.complete.side_effect = _racing_complete
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert reloaded.transcript_summary == "Condensed."
        # 6 summarised entries dropped, the 20-entry window plus the raced-in
        # turn kept -- nothing silently lost.
        assert [e["text"] for e in reloaded.transcript] == [
            *[f"m{i}" for i in range(6, 26)],
            "raced-in",
        ]


    def test_a_concurrent_compression_is_not_overwritten(self, ctx, workspace):
        """Review finding F6 -- two turns compressing at once.

        The second writer used to slice ``len(overflow)`` off a transcript the
        first writer had *already* shortened, deleting live turns and replacing
        the newer digest with one built from a stale ``previous_summary``.
        """
        session = _session_with_entries(ctx, workspace, 26)

        def _concurrently_compressing_complete(*args, **kwargs):
            # Stands in for a second request that got through the whole
            # compression first: transcript replaced by its 20-entry tail,
            # transcript_summary written.
            TenantContext.set_tenant(ctx.tenant_id)
            InterviewSession.objects.filter(id=session.id).update(
                transcript=[
                    {"role": "user", "text": f"m{i}", "timestamp": "t"}
                    for i in range(6, 26)
                ],
                transcript_summary="Digest written by the other request.",
            )
            return "Digest written by this request."

        provider = MagicMock()
        provider.complete.side_effect = _concurrently_compressing_complete
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert reloaded.transcript_summary == "Digest written by the other request."
        assert [e["text"] for e in reloaded.transcript] == [f"m{i}" for i in range(6, 26)]


class TestStateSurfacesTheSummary:
    """Review finding F5 -- a compressed conversation must not *look* like it
    lost its earlier half at every facade that renders `state.transcript`."""

    def test_get_state_round_trips_the_summary(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 26)
        provider = MagicMock()
        provider.complete.return_value = "Digest of the early conversation."
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService()._compress_transcript_if_needed(ctx, session)

        state = InterviewService().get_state(ctx, session.id)
        assert state["transcript_summary"] == "Digest of the early conversation."
        assert len(state["transcript"]) == 20

    def test_state_carries_an_empty_summary_before_any_compression(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 4)
        state = InterviewService().get_state(ctx, session.id)
        assert state["transcript_summary"] == ""

    def test_chat_turn_returns_the_summary_in_its_state(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.side_effect = [
            '{"extracted_fields": {}, "reply": "ok"}',
            "Condensed history.",
        ]
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            result = InterviewService().generate_chat_turn(ctx, session.id, "one more")

        assert result["state"]["transcript_summary"] == "Condensed history."


class TestChatTurnUsesTheSummary:
    def test_prompt_carries_the_summary_and_only_the_window(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 20)
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            InterviewSession.objects.filter(id=session.id).update(
                transcript_summary="Digest of the early conversation."
            )
        finally:
            TenantContext.clear_tenant()

        provider = MagicMock()
        provider.complete.return_value = '{"extracted_fields": {}, "reply": "ok"}'
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService().generate_chat_turn(ctx, session.id, "next question")

        prompt = provider.complete.call_args_list[0][0][0]
        assert "Digest of the early conversation." in prompt
        # The freshly-appended turn is in the window; the summary is separate.
        assert "next question" in prompt

    def test_chat_turn_triggers_compression_after_persisting(self, ctx, workspace):
        """Compression runs on the persisted transcript, so the turn that
        pushed it over the window can never be lost by a compression failure."""
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.side_effect = [
            '{"extracted_fields": {}, "reply": "ok"}',  # the chat turn
            "Condensed history.",                        # the compression call
        ]
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            InterviewService().generate_chat_turn(ctx, session.id, "one more")

        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        # 20 + 2 new entries = 22, compressed back down to the 20-entry window.
        assert len(reloaded.transcript) == 20
        assert reloaded.transcript_summary == "Condensed history."

    def test_compression_failure_still_returns_the_reply(self, ctx, workspace):
        session = _session_with_entries(ctx, workspace, 20)
        provider = MagicMock()
        provider.complete.side_effect = [
            '{"extracted_fields": {}, "reply": "ok"}',
            RuntimeError("provider down"),
        ]
        with patch.object(
            InterviewService, "_resolve_provider", return_value=(provider, "anthropic", None)
        ):
            result = InterviewService().generate_chat_turn(ctx, session.id, "one more")

        assert result["reply"] == "ok"
        TenantContext.set_tenant(ctx.tenant_id)
        try:
            reloaded = InterviewSession.objects.get(id=session.id)
        finally:
            TenantContext.clear_tenant()
        assert len(reloaded.transcript) == 22  # uncompressed, nothing lost
