"""Sliding-window transcript compression (R2S-010).

Owns the LLM digest of overflowed chat turns. Best-effort by contract: any
provider/budget failure leaves the transcript untouched for the next turn.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from persistence.models import InterviewSession

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

# L2.4 spec §5: how many chat turns stay in `transcript` verbatim. Everything
# older is folded into `transcript_summary`. One turn writes TWO transcript
# entries (user + assistant, see generate_chat_turn), so the retained entry
# count is twice this. A fixed constant, deliberately not a setting: one
# threshold is enough (spec §5, YAGNI).
TRANSCRIPT_WINDOW_TURNS = 10

class InterviewTranscriptMixin:
    """Transcript overflow digest; mixed into :class:`InterviewService`."""

    @staticmethod
    def _summarise_transcript_overflow(
        ctx,
        provider,
        provider_name: str,
        audit_logger,
        entity_id: str,
        session: InterviewSession,
        overflow: list[dict[str, Any]],
    ) -> str | None:
        """Write one LLM digest of *overflow* and return it, or None if empty.

        Renders the ``interview.transcript_summary`` template, calls the
        provider, and on a non-empty digest writes the success audit row and
        records token usage. An empty digest returns None -- an empty digest
        would silently discard the overflow turns, so the caller treats it
        exactly like a failed call. Any exception propagates to the caller
        (``_compress_transcript_if_needed``), whose best-effort except clause
        handles it identically to a raising provider call.
        """
        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            record_token_usage,
        )

        template = AiDerivationService._get_template_content(
            ctx, "interview.transcript_summary", session.workspace_id
        )
        prompt = AiDerivationService._render(
            template,
            previous_summary=session.transcript_summary or "",
            overflow_json=json.dumps(overflow),
        )
        summary = provider.complete(
            prompt,
            purpose="interview.transcript_summary",
            timeout=resolve_timeout_seconds("interview.transcript_summary"),
        )

        summary = (summary or "").strip()
        if not summary:
            # An empty digest would silently DISCARD the overflow turns.
            # Treat it exactly like a failed call.
            logger.debug(
                "InterviewService: empty transcript summary for session=%s -- "
                "transcript left uncompressed",
                session.id,
            )
            return None

        audit_logger.log_llm_call(
            provider=provider_name,
            capability="interview.transcript_summary",
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        record_token_usage(
            provider=provider_name,
            capability="interview.transcript_summary",
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(summary),
        )
        return summary

    def _compress_transcript_if_needed(self, ctx, session: InterviewSession) -> None:
        """Fold turns older than the sliding window into ``transcript_summary``.

        L2.4 (spec §5): ``transcript`` used to grow without bound, and every
        chat turn resent the whole history as prompt context. Above
        ``TRANSCRIPT_WINDOW_TURNS`` turns, the overflow is replaced by one
        LLM-written digest that *supersedes* the previous digest (it is fed
        back in), so the summary itself cannot grow without bound either.

        Best-effort by contract (spec §7, issue #846): no provider, a mock
        provider, an exhausted token budget, or a provider that raises all
        mean "no compression this turn" -- the transcript is left exactly as
        it was and the next turn retries. Never raises, never blocks the
        chat. Called AFTER the triggering turn is already persisted, so a
        failure here cannot lose that turn.

        Mutates *session* in place and persists both fields; the caller does
        not need to re-save.
        """
        from application.bundle_compression_service import MOCK_PROVIDER_NAME
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.token_tracking import is_over_daily_limit

        window_entries = TRANSCRIPT_WINDOW_TURNS * 2
        if len(session.transcript) <= window_entries:
            return

        overflow = session.transcript[:-window_entries]

        provider, provider_name, _resolve_error = self._resolve_provider()
        if provider is None or provider_name == MOCK_PROVIDER_NAME:
            # Issue #442's rule, same as _rank_candidates_with_ai above: a
            # *configured* mock provider is a placeholder, not a real signal.
            # Critical here specifically -- MockLlmProvider.complete() has no
            # branch for purpose="interview.transcript_summary" and falls
            # through to its generic `json.dumps([])`, i.e. the literal "[]".
            # That is a non-empty string, so without this guard the whole
            # overflow would be replaced by "[]" and permanently deleted on
            # the project's own default deployment (LLM_PROVIDER=mock).
            logger.debug(
                "InterviewService: no real LLM provider (provider=%s) for transcript "
                "compression, session=%s -- deferring to the next turn",
                provider_name,
                session.id,
            )
            return

        # Armed before the first audit write below, not just before the
        # save(): reachable from the direct-call path too (tests, a future
        # scheduled sweep), not only from generate_chat_turn where
        # _get_session already armed it -- and AuditLogWriter needs an active
        # tenant context or it drops the entry with a RuntimeWarning.
        self._set_tenant_context(ctx)

        audit_logger = LlmAuditLogger()
        entity_id = str(session.id)

        # REQ-106: per-tenant daily token budget. This free-form flow bypasses
        # CapabilityRouter, so nothing else enforces it -- same reasoning as
        # _rank_candidates_with_ai / generate_chat_turn. Unlike the chat turn
        # this does NOT raise: compression is best-effort by contract (see
        # docstring), so an exhausted budget just defers to the next turn.
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.transcript_summary",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            logger.debug(
                "InterviewService: daily token limit exceeded, skipping transcript "
                "compression for session=%s",
                session.id,
            )
            return

        # Everything below is inside the try: the template lookup hits the DB
        # (workspace prompt override), _render and json.dumps can raise on odd
        # input, and the save() is a write -- all of them run AFTER the chat
        # turn already committed, so letting any of them escape would turn a
        # successful turn into a 500. The docstring's "never raises" contract
        # covers the whole body, not just the provider call.
        try:
            summary = self._summarise_transcript_overflow(
                ctx, provider, provider_name, audit_logger, entity_id, session, overflow
            )
            if summary is None:
                return

            # The provider call above blocks for up to ~25s. A concurrent
            # request may have appended a turn in the meantime, and the
            # in-memory `session.transcript` this method started from would
            # silently drop it. Re-read, then keep *everything the summary
            # does not already cover* -- i.e. the tail after the summarised
            # prefix, not a fixed-size window slice. `transcript` is
            # append-only on every write path, so `overflow` is still a
            # prefix; the result may briefly exceed the window when a turn
            # raced in, which the next turn's compression folds away.
            session.refresh_from_db(fields=["transcript"])
            if session.transcript[: len(overflow)] != overflow:
                # Review finding F6: `transcript` only ever *grows* by appending
                # -- the one exception is another compression run, which
                # replaces it with a shorter tail. So if the persisted row no
                # longer STARTS with the exact prefix this digest summarises, a
                # concurrent request already folded that prefix away (and wrote
                # its own digest). Slicing `len(overflow)` off that row would
                # delete live turns and overwrite the newer summary with one
                # derived from a stale `previous_summary`.
                #
                # Final-review finding I2: a pure length check missed the
                # interleaving where the other compressor finishes AND >=
                # len(overflow) new turns get appended afterwards -- long
                # enough to pass, wrong prefix all the same. Comparing the
                # prefix itself is strictly more precise at the same cost.
                logger.debug(
                    "InterviewService: transcript for session=%s was compressed "
                    "concurrently -- discarding this digest",
                    session.id,
                )
                return
            session.transcript_summary = summary
            session.transcript = session.transcript[len(overflow):]
            session.save(
                update_fields=["transcript_summary", "transcript", "modified_at"]
            )
        except Exception as error:  # noqa: BLE001 -- best-effort by contract
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.transcript_summary",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            logger.debug(
                "InterviewService: transcript compression failed for session=%s "
                "(provider=%s) -- transcript left uncompressed, retrying next turn",
                session.id,
                provider_name,
                exc_info=True,
            )
            return
