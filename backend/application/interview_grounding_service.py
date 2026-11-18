"""Interview grounding and AI-assisted evidence ranking (R2S-010).

Owns structural candidate discovery, provider resolution and the fail-open
LLM ranking layer that produces ``grounding_snapshot``. Both layers are
best-effort by contract; no caller-visible error behaviour changes here.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F

from persistence.models import InterviewSession

# Keep the original log category: operators filter on it, and the split must
# not change observable logging behaviour.
logger = logging.getLogger("application.interview_service")

# PromptTemplate name for the AI-assisted grounding-ranking layer (Task 6,
# spec §6 step 2). Registered in AiDerivationService.PROMPT_TEMPLATE_DEFAULTS
# (ai_derivation_service.py) -- same reasoning as
# BundleCompressionService.PROMPT_TEMPLATE_NAME: that dict is the single
# canonical registry AiDerivationService._get_template_content's fallback
# chain resolves against, so the content lives there, not here.
GROUNDING_RANK_PROMPT_TEMPLATE_NAME = "interview.grounding_rank"

class InterviewGroundingMixin:
    """Grounding candidate discovery/ranking; mixed into :class:`InterviewService`."""

    @staticmethod
    def _structural_candidates(ctx, session: InterviewSession) -> list[dict[str, Any]]:
        """Structural (non-AI) pre-filter — spec §6 step 1.

        Extracted from ``grounding_context`` (Task 5 -> Task 6) so the
        AI-ranking layer added in Task 6 can run this first and rank its
        output rather than reinventing the candidate search. Only
        ``Requirement`` is wired up here (YAGNI): grounding the other 7
        in-scope artifact types is out of scope for the Interview-Engine-Fix
        spec, which covers ``formalize()``'s create path -- not a leftover of
        it. Grounding only feeds ``set_target()``, whose update branch is
        Requirement-only by design anyway.

        Takes *ctx* (unlike the brief's inline sketch) because
        ``RequirementService.list_requirements`` requires it as a mandatory
        keyword argument -- it is not implicitly picked up from the
        already-set TenantContext the way row-level filtering is.
        """
        title = session.collected_fields.get("title")
        if not title or session.artifact_type != "Requirement":
            return []

        from application.requirement_service import RequirementService

        # Structural pre-filter: substring match on title within the
        # workspace. Cheap, always available, no AI required. list_requirements()
        # returns a lazy QuerySet of Requirement ORM objects (title/artifact_id
        # attrs) -- not dicts, and excludes soft-deleted rows by default.
        matches = RequirementService().list_requirements(
            workspace_id=session.workspace_id, ctx=ctx
        )
        return [
            {"artifact_id": str(r.artifact_id), "title": r.title, "score": None}
            for r in matches
            if title.lower() in r.title.lower()
        ]

    @staticmethod
    def _resolve_provider() -> tuple[Any | None, str, Exception | None]:
        """Resolve the effective LLM provider for AI-assisted grounding.

        The executable core is shared with the other three ANPASSEN-scope
        services (S4.1 WP-1) via
        :func:`application.llm_provider_resolution.resolve_provider`. Grounding
        has no cache key to namespace the way bundle compression does, so
        this method only exists as the patchable seam that lets
        ``grounding_context`` decide up front, explicitly, whether to attempt
        AI ranking at all (spec §6: the AI layer activates only when a real
        provider is configured) -- rather than relying on
        ``_rank_candidates_with_ai`` to notice a mock provider after the fact.

        Returns:
            ``(provider, provider_name, resolve_error)``. On a resolution
            failure *provider* is None, *resolve_error* carries the
            exception, and *provider_name* is ``MOCK_PROVIDER_NAME`` --
            mirroring BundleCompressionService, which treats "not
            configured" as "the mock will effectively serve this" even
            though grounding does not call the mock in that case (see
            ``_rank_candidates_with_ai``).
        """
        from application.llm_provider_resolution import resolve_provider

        return resolve_provider()

    def _rank_candidates_with_ai(
        self,
        ctx,
        session: InterviewSession,
        candidates: list[dict[str, Any]],
        provider: Any,
        provider_name: str,
    ) -> list[dict[str, Any]]:
        """AI-assisted ranking on top of ``_structural_candidates`` — spec §6 step 2.

        Ports ``BundleCompressionService._call_provider``'s exact
        token-budget-check / audit-logging / mock-fallback-marker pattern
        (``bundle_compression_service.py:522-671``), adapted to a ranking
        prompt: instead of returning compressed text, the provider's JSON
        response is merged back into *candidates* as a ``score``. Every exit
        path in this method returns *candidates* -- either re-scored, or
        completely unchanged -- and NONE of them raise; ranking is a pure
        enhancement on top of the Task 5 structural result, never a gate
        (spec §6). The one caller-visible difference from
        ``_call_provider``'s pattern: that method falls back to
        ``MockLlmProvider().complete()`` and marks the result as a mock
        fallback on failure, because it must always produce *some* text.
        Ranking has no such obligation -- the correct "fallback" for a
        ranking call that cannot be trusted is simply the unranked
        candidates already computed, so failures here return early instead
        of calling the mock.
        """
        from application.ai_derivation_service import AiDerivationService
        from application.bundle_compression_service import MOCK_PROVIDER_NAME
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            is_over_daily_limit,
            record_token_usage,
        )

        if provider_name == MOCK_PROVIDER_NAME:
            # Issue #442's rule (bundle_compression_service.py) applies here
            # too: a *configured* mock provider is a placeholder, not a real
            # ranking signal. Skip the call entirely rather than "ranking"
            # against MockLlmProvider's generic fallback text -- spec §6
            # says the AI layer activates only when a real provider is
            # configured, and the mock is never that.
            logger.info(
                "InterviewService: mock provider configured, skipping AI-assisted "
                "grounding ranking for session=%s", session.id,
            )
            return candidates

        audit_logger = LlmAuditLogger()
        entity_id = str(session.id)

        answers_text = "\n".join(
            f"{name}: {value}" for name, value in session.collected_fields.items()
        )
        candidates_json = json.dumps(
            [{"artifact_id": c["artifact_id"], "title": c["title"]} for c in candidates]
        )
        # RFC #1002 PR C: routed through _resolve_and_render so the slot's
        # declared {memory_context} is auto-injected by the central resolver
        # (this flow used to render the raw template, which would now leave
        # the placeholder literal).
        prompt = AiDerivationService._resolve_and_render(
            ctx,
            GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
            session.workspace_id,
            answers_text=answers_text,
            candidates_json=candidates_json,
            artifact_id=session.artifact_id,
            entity_type=session.artifact_type or "",
        )

        # REQ-106: per-tenant daily token budget, checked here for the same
        # reason BundleCompressionService._call_provider checks it -- this
        # free-form flow bypasses CapabilityRouter, so nothing else enforces
        # the budget. Unlike that method, exceeding the budget does not raise
        # here: it is recorded via the same audit call, and grounding simply
        # stays structural-only for this request (spec §6, fail-open).
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            return candidates

        timeout = resolve_timeout_seconds(GROUNDING_RANK_PROMPT_TEMPLATE_NAME)
        try:
            raw = provider.complete(
                prompt, purpose=GROUNDING_RANK_PROMPT_TEMPLATE_NAME, timeout=timeout
            )
        except Exception as error:  # noqa: BLE001 -- fail-open, see docstring
            logger.warning(
                "InterviewService: AI grounding ranking call failed for session=%s: %s",
                session.id, error,
            )
            audit_logger.log_llm_call(
                provider=provider_name,
                capability=GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            return candidates

        # provider.complete() only returns text (no token counts), same
        # limitation BundleCompressionService._call_provider documents.
        audit_logger.log_llm_call(
            provider=provider_name,
            capability=GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        # SA-26: this used to hardcode input_tokens=0, leaving the daily
        # budget (is_over_daily_limit above) blind to this call's real
        # spend. Estimate both sides client-side, matching every other
        # free-form path (see ``approximate_token_count``).
        record_token_usage(
            provider=provider_name,
            capability=GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(raw),
        )

        return self._merge_ai_scores(candidates, raw)

    @staticmethod
    def _merge_ai_scores(
        candidates: list[dict[str, Any]], raw: str
    ) -> list[dict[str, Any]]:
        """Parse the provider's JSON ranking response and merge scores back
        into *candidates* by ``artifact_id``.

        Returns *candidates* completely unchanged (still the valid Task 5
        structural output) on any parse/shape failure -- a malformed LLM
        response must never surface as an error to the interview (spec §6,
        fail-open). Candidates the response didn't score keep ``score=None``.
        """
        score_by_id = InterviewGroundingMixin._parse_score_map(raw)
        if not score_by_id:
            return candidates

        ranked = [
            {**c, "score": score_by_id.get(c["artifact_id"], c["score"])}
            for c in candidates
        ]
        ranked.sort(key=lambda c: (c["score"] is None, -(c["score"] or 0.0)))
        return ranked

    @staticmethod
    def _parse_score_map(raw: str) -> dict[str, float] | None:
        """Score map (``artifact_id`` -> float score) parsed from the provider's
        JSON ranking response, or None on any parse/shape failure -- a
        malformed LLM response must never surface as an error to the
        interview (spec §6, fail-open).
        """
        try:
            scored = json.loads(raw)
            if not isinstance(scored, list):
                return None
            return {
                str(entry["artifact_id"]): float(entry["score"])
                for entry in scored
                if isinstance(entry, dict) and "artifact_id" in entry and "score" in entry
            }
        except Exception:  # noqa: BLE001 -- fail-open, see docstring
            return None

    def grounding_context(self, ctx, session_id: UUID) -> dict[str, Any]:
        """Structural + AI-assisted grounding — spec §6.

        Always computes the Task 5 structural candidates first. The Task 6
        AI-ranking layer only runs on top of a non-empty structural result,
        and only when a real (non-mock) LLM provider is configured; any
        failure anywhere in that layer -- provider resolution, the call
        itself, or a malformed response -- degrades silently back to the
        structural-only candidates. This method itself never raises because
        of the grounding layer; the outer ``except Exception`` is
        belt-and-suspenders on top of ``_resolve_provider`` and
        ``_rank_candidates_with_ai`` already being fail-open internally,
        matching the plan's own sketch for this step.

        No longer wrapped in ``@atomic_transaction`` as a whole (issue
        #541): only the final ``session.save()`` below needs atomicity, so
        the DB transaction is opened just around that block, not around the
        ``provider.complete()`` network round-trip above it.
        """
        session = self._get_session(ctx, session_id)
        candidates = self._structural_candidates(ctx, session)

        try:
            provider, provider_name, resolve_error = self._resolve_provider()
            if provider is None:
                # Mirrors BundleCompressionService._call_provider's "provider
                # is None" branch (a debug-level log, no audit entry -- there
                # is no call to record yet). Not configured at all is the
                # expected default deployment shape (LLM_PROVIDER=mock), so
                # this stays a debug log rather than a warning.
                logger.debug(
                    "InterviewService: no LLM provider resolved for session=%s "
                    "(%s), grounding stays structural-only",
                    session_id, resolve_error,
                )
            elif candidates:
                candidates = self._rank_candidates_with_ai(
                    ctx, session, candidates, provider, provider_name
                )
        except Exception:  # noqa: BLE001 -- grounding must never block the interview (spec §6)
            logger.warning(
                "InterviewService: AI-assisted grounding failed for session=%s, "
                "falling back to structural-only candidates",
                session_id, exc_info=True,
            )

        # LLM call happens outside the transaction (issue #541) -- only the final save needs atomicity.
        with transaction.atomic():
            session.grounding_snapshot = {"candidates": candidates}
            session.version = F("version") + 1
            session.save(update_fields=["grounding_snapshot", "modified_at", "version"])
            session.refresh_from_db(fields=["version"])
        return session.grounding_snapshot
