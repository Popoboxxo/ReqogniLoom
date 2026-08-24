"""InterviewService — core session state machine (Interview-Management-Engine spec §4-5).

start/get_state/answer/list/get here; grounding is Task 5-6,
formalize is Task 7. Kept in this one file per the spec's "one MCP
toolgroup, one engine" framing -- split further only if it grows past
a single clear responsibility.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Optional
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError
from application.interview_protocol import IN_SCOPE_ARTIFACT_TYPES, get_protocol
from persistence.models import (
    InterviewSession,
    InterviewSessionArtifact,
    Workspace,
)
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

# spec §9 "verwaiste Sessions": a session untouched this long lazily flips
# to abandoned the next time anything reads it. No scheduled job (YAGNI).
ABANDONED_TTL = timedelta(days=30)

# PromptTemplate name for the AI-assisted grounding-ranking layer (Task 6,
# spec §6 step 2). Registered in AiDerivationService.PROMPT_TEMPLATE_DEFAULTS
# (ai_derivation_service.py) -- same reasoning as
# BundleCompressionService.PROMPT_TEMPLATE_NAME: that dict is the single
# canonical registry AiDerivationService._get_template_content's fallback
# chain resolves against, so the content lives there, not here.
GROUNDING_RANK_PROMPT_TEMPLATE_NAME = "interview.grounding_rank"

# Link type rejected at multi-mode proposal-parse level (Task 3): owned by
# the diagram reconciler, never hand-authored -- see _formalize_multi.
_DIAGRAM_REF_LINK_TYPE = "diagram-ref"


class InterviewService(ServiceBase):
    @atomic_transaction
    def start(
        self,
        ctx,
        artifact_type: str,
        workspace_id: UUID,
        seed_context: "Optional[dict]" = None,
    ) -> InterviewSession:
        if artifact_type not in IN_SCOPE_ARTIFACT_TYPES:
            raise ValidationError(
                f"Interviews are not available for artifact_type={artifact_type!r} "
                f"(MainGoal stays read-only; other unknown types are unsupported)."
            )
        self._set_tenant_context(ctx)
        # Fail fast with a clean NotFoundError (same pattern as
        # RequirementService.create_requirement) rather than letting
        # InterviewSession's FK constraint raise a bare IntegrityError on an
        # unknown workspace_id, which the MCP layer's generic exception
        # handler would otherwise surface as an opaque INTERNAL_ERROR.
        if not Workspace.objects.filter(id=workspace_id).exists():
            raise NotFoundError(f"Workspace {workspace_id} not found")
        # Fail fast if the protocol config is missing/broken rather than
        # creating a session that can never progress past get_state.
        get_protocol(ctx, artifact_type, workspace_id)
        from persistence.models import Artifact
        from workflow.services import initialize_workflow_states

        artifact = Artifact.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            artifact_type="Interview",
            custom_fields={},
        )
        session = InterviewSession.objects.create(
            workspace_id=workspace_id,
            artifact=artifact,
            artifact_type=artifact_type,
            collected_fields=(seed_context or {}),
        )
        # 2026-08-20 UI-visibility fix: register with the workflow engine so
        # the session is discoverable/transitionable the same way every
        # other tracked entity is (workspace-defaults 'interview_default'
        # preset, see workflow/definition_store.py). Best-effort -- a
        # missing/misconfigured definition must not block session creation
        # (mirrors *_service.py's workflow-init try/except convention, e.g.
        # RequirementService.create_requirement).
        try:
            initialize_workflow_states(
                item_ids=[session.id],
                item_type="Interview",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "InterviewService: workflow init skipped for session=%s", session.id
            )
        return session

    def _get_session(self, ctx, session_id: UUID) -> InterviewSession:
        self._set_tenant_context(ctx)
        session = InterviewSession.objects.filter(id=session_id).first()
        if session is None:
            raise NotFoundError(f"InterviewSession {session_id} not found")
        self._lazily_abandon_if_stale(session, ctx)
        return session

    @staticmethod
    def _lazily_abandon_if_stale(session: InterviewSession, ctx) -> None:
        """spec §9: flip a stale in_progress session to abandoned on read.

        System-driven, TTL-based, not a user-permission-gated action -- uses
        ``StateLifecycleManager.force_transition`` (the same escape hatch
        ``workflow.services.outdate()`` uses) rather than the role-validated
        ``transition()``, since this can fire on behalf of a viewer-level
        ``ctx`` with no editor role. Mutates and saves *session* in place
        when it fires (via the workflow engine's status-mirror write, see
        ``lifecycle_manager._STATUS_MIRROR_MODELS``), so callers that already
        hold the returned object see the up-to-date status without
        re-fetching.
        """
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            return
        if timezone.now() - session.modified_at < ABANDONED_TTL:
            return
        from workflow.lifecycle_manager import StateLifecycleManager

        try:
            StateLifecycleManager().force_transition(
                item_id=session.id,
                item_type="Interview",
                workspace_id=session.workspace_id,
                target_state=InterviewSession.STATUS_ABANDONED,
                change_reason=f"Inactive for {ABANDONED_TTL.days}+ days (auto-abandon)",
                actor=str(getattr(ctx, "user_id", "") or "system"),
            )
        except Exception:
            # No WorkflowItemState row (e.g. a session that predates this
            # feature, or workflow init failed at creation) -- fall back to
            # the direct field write so lazy-abandon still works instead of
            # leaving the session stuck "in_progress" forever.
            logger.debug(
                "InterviewService: force_transition unavailable for session=%s, "
                "falling back to direct status write", session.id
            )
            session.status = InterviewSession.STATUS_ABANDONED
            session.version = F("version") + 1
            session.save(update_fields=["status", "modified_at", "version"])
        session.refresh_from_db()

    def _current_phase_and_missing(self, ctx, session: InterviewSession):
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        for phase in protocol.phases:
            missing = [
                f for f in phase.required_fields
                if f.name not in session.collected_fields
            ]
            if missing:
                return phase, missing
        # Every field of every phase is answered.
        return protocol.phases[-1], []

    @staticmethod
    def _serialise_field(f) -> "dict[str, Any]":
        # Spec 2 (Hermes plugin, §3-4): InterviewFormView renders one input
        # per missing field and needs its type/choices to pick the right
        # control (text/textarea/enum/number) -- a bare field-name string
        # would lose exactly the information the protocol config's `type`
        # amendment was added for. Every host consumes this same shape;
        # skill-driven hosts (Claude Code/Opencode/Antigravity) just read
        # `.name` and ignore `.type`/`.choices`.
        return {"name": f.name, "type": f.type, "choices": f.choices}

    def get_state(self, ctx, session_id: UUID) -> "dict[str, Any]":
        session = self._get_session(ctx, session_id)
        phase, missing = self._current_phase_and_missing(ctx, session)
        return {
            "session_id": str(session.id),
            "status": session.status,
            "phase": phase.name,
            "collected_fields": session.collected_fields,
            "missing_fields": [self._serialise_field(f) for f in missing],
            "grounding_snapshot": session.grounding_snapshot,
            # Web Widget spec §9 -- the chat pane needs the full transcript
            # to render conversation history on mount/resume. Additive and
            # harmless to the Hermes plugin's form view, which ignores it.
            "transcript": session.transcript,
        }

    @atomic_transaction
    def answer(self, ctx, session_id: UUID, field: str, value: Any) -> InterviewSession:
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot answer."
            )
        # issue #542: validate against the protocol's declared field type
        # before storing. A field name that isn't in the protocol at all is
        # left unvalidated on purpose -- answer() has always been permissive
        # about unknown field names; only type-check fields that resolve.
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        protocol_field = self._find_protocol_field(protocol, field)
        if protocol_field is not None:
            self._validate_field_value_type(protocol_field, value)
        session.collected_fields = {**session.collected_fields, field: value}
        session.version = F("version") + 1
        session.save(update_fields=["collected_fields", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])
        return session

    @staticmethod
    def _find_protocol_field(protocol, field_name: str):
        """Look up a field by name across every phase of *protocol*.

        Same traversal ``_current_phase_and_missing`` already does over
        ``phase.required_fields``, factored out here (issue #542) so
        ``answer()`` can resolve a single field by name without
        reimplementing the nested loop.

        Returns ``None`` if no phase declares a field with that name.
        """
        for phase in protocol.phases:
            for candidate in phase.required_fields:
                if candidate.name == field_name:
                    return candidate
        return None

    @staticmethod
    def _validate_field_value_type(field, value: Any) -> None:
        """Validate *value* against *field*'s declared protocol type -- issue #542.

        Only called for fields that resolve to a real protocol field (see
        ``_find_protocol_field``); raises ``ValidationError`` naming the
        field, its expected type, and what was actually received.
        """
        if field.type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValidationError(
                    f"Field {field.name!r} expects a number, got "
                    f"{type(value).__name__}."
                )
            if isinstance(value, str):
                try:
                    float(value)
                except ValueError:
                    raise ValidationError(
                        f"Field {field.name!r} expects a number, got a "
                        f"non-numeric string {value!r}."
                    )
        elif field.type == "enum":
            if value not in (field.choices or []):
                raise ValidationError(
                    f"Field {field.name!r} expects one of {field.choices!r}, "
                    f"got {value!r}."
                )
        elif field.type in ("text", "textarea"):
            if not isinstance(value, str):
                raise ValidationError(
                    f"Field {field.name!r} expects a string ({field.type}), "
                    f"got {type(value).__name__}."
                )

    @staticmethod
    def _structural_candidates(ctx, session: InterviewSession) -> "list[dict[str, Any]]":
        """Structural (non-AI) pre-filter — spec §6 step 1.

        Extracted from ``grounding_context`` (Task 5 -> Task 6) so the
        AI-ranking layer added in Task 6 can run this first and rank its
        output rather than reinventing the candidate search. Only
        ``Requirement`` is wired up here (YAGNI): the other 7 in-scope
        artifact types get the same shape once their equivalent read
        services are confirmed, in a later pass.

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
    def _resolve_provider() -> "tuple[Any | None, str, Exception | None]":
        """Resolve the effective LLM provider for AI-assisted grounding.

        Mirrors ``BundleCompressionService._resolve_provider`` exactly (see
        ``bundle_compression_service.py:488-520`` for the annotated original)
        -- same ``get_provider()`` call, same two caught exception types, same
        ``(provider, provider_name, resolve_error)`` return shape. Grounding
        has no cache key to namespace the way bundle compression does, so
        here the split only exists to let ``grounding_context`` decide
        up front, explicitly, whether to attempt AI ranking at all (spec §6:
        the AI layer activates only when a real provider is configured) --
        rather than relying on ``_rank_candidates_with_ai`` to notice a mock
        provider after the fact.

        Returns:
            ``(provider, provider_name, resolve_error)``. On a resolution
            failure *provider* is None, *resolve_error* carries the
            exception, and *provider_name* is ``MOCK_PROVIDER_NAME`` --
            mirroring BundleCompressionService, which treats "not
            configured" as "the mock will effectively serve this" even
            though grounding does not call the mock in that case (see
            ``_rank_candidates_with_ai``).
        """
        from application.bundle_compression_service import MOCK_PROVIDER_NAME
        from llm_adapter.providers import (
            LlmNotConfiguredError,
            LlmProviderUnknownError,
            get_provider,
        )

        try:
            provider = get_provider()
        except (LlmNotConfiguredError, LlmProviderUnknownError) as error:
            return None, MOCK_PROVIDER_NAME, error

        return provider, str(getattr(provider, "PROVIDER_NAME", "unknown")), None

    def _rank_candidates_with_ai(
        self,
        ctx,
        session: InterviewSession,
        candidates: "list[dict[str, Any]]",
        provider: Any,
        provider_name: str,
    ) -> "list[dict[str, Any]]":
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
        from application.bundle_compression_service import MOCK_PROVIDER_NAME
        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import is_over_daily_limit, record_token_usage

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

        template = AiDerivationService._get_template_content(
            ctx, GROUNDING_RANK_PROMPT_TEMPLATE_NAME, workspace_id=session.workspace_id
        )
        answers_text = "\n".join(
            f"{name}: {value}" for name, value in session.collected_fields.items()
        )
        candidates_json = json.dumps(
            [{"artifact_id": c["artifact_id"], "title": c["title"]} for c in candidates]
        )
        prompt = AiDerivationService._render(
            template, answers_text=answers_text, candidates_json=candidates_json
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
        record_token_usage(
            provider=provider_name,
            capability=GROUNDING_RANK_PROMPT_TEMPLATE_NAME,
            input_tokens=0,
        )

        return self._merge_ai_scores(candidates, raw)

    @staticmethod
    def _merge_ai_scores(
        candidates: "list[dict[str, Any]]", raw: str
    ) -> "list[dict[str, Any]]":
        """Parse the provider's JSON ranking response and merge scores back
        into *candidates* by ``artifact_id``.

        Returns *candidates* completely unchanged (still the valid Task 5
        structural output) on any parse/shape failure -- a malformed LLM
        response must never surface as an error to the interview (spec §6,
        fail-open). Candidates the response didn't score keep ``score=None``.
        """
        try:
            scored = json.loads(raw)
            if not isinstance(scored, list):
                return candidates
            score_by_id = {
                str(entry["artifact_id"]): float(entry["score"])
                for entry in scored
                if isinstance(entry, dict) and "artifact_id" in entry and "score" in entry
            }
        except Exception:  # noqa: BLE001 -- fail-open, see docstring
            return candidates

        if not score_by_id:
            return candidates

        ranked = [
            {**c, "score": score_by_id.get(c["artifact_id"], c["score"])}
            for c in candidates
        ]
        ranked.sort(key=lambda c: (c["score"] is None, -(c["score"] or 0.0)))
        return ranked

    def grounding_context(self, ctx, session_id: UUID) -> "dict[str, Any]":
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

    @atomic_transaction
    def set_target(self, ctx, session_id: UUID, artifact_id: UUID) -> "dict[str, Any]":
        """Confirm a ``grounding_context()`` candidate (or any already-known
        artifact_id) as the session's ``formalize()`` update target --
        issue #540.

        Without this, ``target_artifact_id`` was write-only dead code:
        ``grounding_context()`` surfaces candidates but nothing ever set the
        field, so ``formalize()``'s "update an existing artifact" branch was
        unreachable through the real MCP surface. This is that missing
        write path.

        Requirement-only, matching ``formalize()``'s own update branch
        (its docstring: "Only ``Requirement`` is implemented"): setting a
        target on a session whose ``artifact_type`` formalize() can't
        update yet would be a target formalize() can never use, so reject
        it here instead of silently accepting a value that goes nowhere.

        Re-checks that ``artifact_id`` resolves to a real ``Requirement``
        right now, mirroring ``formalize()``'s own target re-check
        (``Requirement.objects.filter(artifact_id=...).first()``) rather
        than trusting the caller's possibly-stale ``grounding_context()``
        snapshot -- same spec §9 staleness concern formalize() already
        guards against at write time.
        """
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot set target."
            )
        if session.artifact_type != "Requirement":
            raise ValidationError(
                f"set_target() for artifact_type={session.artifact_type!r} is not "
                "supported -- formalize()'s update branch is Requirement-only, so "
                "a target on any other artifact_type could never be used."
            )

        from persistence.models import Requirement

        if not Requirement.objects.filter(artifact_id=artifact_id).exists():
            raise NotFoundError(f"Requirement with artifact_id={artifact_id} not found")

        session.target_artifact_id = artifact_id
        session.version = F("version") + 1
        session.save(update_fields=["target_artifact_id", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])
        # Reuse get_state()'s shape rather than hand-rolling a parallel one
        # (see this method's judgment-call note in the issue #540 report):
        # every other read of "session state" already goes through
        # get_state(), and returning it here means a host sees the
        # newly-set target reflected immediately without a second round
        # trip, the same way formalize()/grounding_context() return a
        # ready-to-use result dict rather than the bare ORM object.
        return self.get_state(ctx, session_id)

    @atomic_transaction
    def formalize(
        self, ctx, session_id: UUID, confirmed_proposal: "list[dict] | None" = None
    ) -> "dict[str, Any]":
        """Turn the session's collected answers into real artifact(s) --
        spec §5 point 4.

        Single-kind sessions drive one typed artifact through the classic
        protocol: only ``Requirement`` is implemented there (YAGNI, matches
        ``_structural_candidates``); the other 8 in-scope artifact types
        raise ``ValidationError`` for now rather than being speculatively
        stubbed out, per the plan's Self-Review Notes.

        Multi-kind sessions take a caller-confirmed ``confirmed_proposal``
        (list of ``{"type", "fields", "links"}`` items) and create every
        artifact in ONE transaction via ARTIFACT_CREATION_ADAPTERS, writing
        provenance rows and proposed trace links atomically -- any failure
        rolls back the whole batch.

        The WRITE-permission check runs centrally here, BEFORE the dispatch:
        several adapters call services that perform no WRITE check of their
        own (e.g. GlossaryService.create), so this is the single enforcement
        point for every type created by an interview.

        If the single-mode session was grounded onto an existing artifact
        (``target_artifact_id`` set, e.g. by a future grounding-confirmation
        flow), that artifact is updated instead of creating a new one. Its
        existence is re-checked here, at write time -- spec §9: grounding
        may be stale by the time formalize() runs, so a deleted target must
        raise ``NotFoundError`` rather than silently creating a new artifact
        (wrong outcome) or updating a row that no longer exists (impossible).

        ``target_artifact_id`` is an ``Artifact`` PK, not a ``Requirement``
        PK -- ``Requirement.artifact`` is a ``OneToOneField`` with its own
        id (see ``reqif_import_service.py``'s identical
        ``Requirement.objects.filter(artifact_id=...)`` lookup), so it has
        to be resolved through that FK rather than passed straight to
        ``RequirementService.get_requirement``/``update_requirement``, which
        both take the Requirement's own id.
        """
        self._assert_write_permission(ctx)
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot formalize."
            )

        if session.session_kind == InterviewSession.SESSION_KIND_MULTI:
            return self._formalize_multi(ctx, session, confirmed_proposal or [])
        return self._formalize_single(ctx, session)

    def _formalize_single(self, ctx, session) -> "dict[str, Any]":
        """Single-kind path: one typed artifact from collected_fields.

        Body moved verbatim from the pre-multi-mode formalize() -- behavior
        and return shape are unchanged (single-mode regression guard:
        test_interview_formalize_multi.py::test_single_mode_formalize_unchanged).
        """
        if session.artifact_type != "Requirement":
            raise ValidationError(
                f"formalize() for artifact_type={session.artifact_type!r} is not "
                "implemented yet -- only Requirement is wired in this plan; the "
                "other 7 types follow the identical pattern in a later pass."
            )

        # Reuse get_state()'s exact missing-fields computation: a non-empty
        # `missing` here means the interview is not actually complete yet
        # (see _current_phase_and_missing's docstring/semantics -- it
        # returns the first phase still short a required field, or the
        # last phase with an empty list once everything is answered). Do
        # not proceed to create/update a real artifact -- e.g. an
        # empty-string ``title`` -- off an incomplete session.
        _, missing = self._current_phase_and_missing(ctx, session)
        if missing:
            missing_names = ", ".join(f.name for f in missing)
            raise ValidationError(
                f"InterviewSession {session.id} is not complete yet -- missing "
                f"required field(s): {missing_names}. Cannot formalize."
            )

        # The completeness guard above only trusts the *protocol*: if a
        # workspace's custom interview.protocol.Requirement override never
        # declares a `title` field in required_fields, `missing` above is
        # trivially empty (nothing named `title` was ever "missing") even
        # though `title` resolves to "" here. A Requirement must not be
        # created/updated with an empty title regardless of what the
        # protocol says is required -- check independently.
        # str(...) coercion is defense-in-depth (issue #542): answer() now
        # rejects non-string title values up front, but a stray non-string
        # could still reach here via old rows or a future caller that
        # bypasses answer() -- degrade to "empty title, rejected cleanly"
        # instead of AttributeError on .strip().
        title = str(session.collected_fields.get("title") or "").strip()
        if not title:
            raise ValidationError(
                f"InterviewSession {session.id} has no non-empty 'title' in "
                "collected_fields; cannot formalize a Requirement without a title."
            )

        from application.requirement_service import RequirementService
        from persistence.models import Requirement

        svc = RequirementService()
        resulting_ids: "list[str]" = []

        if session.target_artifact_id is not None:
            target = Requirement.objects.filter(
                artifact_id=session.target_artifact_id
            ).first()
            if target is None:
                raise NotFoundError(
                    f"Target artifact {session.target_artifact_id} no longer "
                    "exists; cannot formalize an update against it."
                )
            updated = svc.update_requirement(
                target.id,
                ctx,
                title=title,
                description=session.collected_fields.get("rationale"),
            )
            resulting_ids.append(str(updated.artifact_id))
        else:
            created = svc.create_requirement(
                workspace_id=session.workspace_id,
                title=title,
                ctx=ctx,
                description=session.collected_fields.get("rationale", ""),
            )
            resulting_ids.append(str(created.artifact_id))

        session.resulting_artifact_ids = resulting_ids
        session.version = F("version") + 1
        session.save(update_fields=["resulting_artifact_ids", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])

        from workflow.services import transition as workflow_transition

        try:
            workflow_transition(
                item_id=session.id,
                target_state=InterviewSession.STATUS_COMPLETED,
                change_reason="Interview formalized into a real artifact",
                ctx=ctx,
                item_type="Interview",
                workspace_id=session.workspace_id,
            )
            session.refresh_from_db()
        except Exception:
            # Same best-effort fallback as _lazily_abandon_if_stale -- a
            # session created before this feature (or with a failed
            # workflow init) has no WorkflowItemState row to transition.
            logger.debug(
                "InterviewService: workflow transition unavailable for session=%s, "
                "falling back to direct status write", session.id
            )
            session.status = InterviewSession.STATUS_COMPLETED
            session.version = F("version") + 1
            session.save(update_fields=["status", "modified_at", "version"])
        return {"resulting_artifact_ids": resulting_ids, "status": session.status}

    def _formalize_multi(self, ctx, session, confirmed_proposal: "list[dict]") -> "dict[str, Any]":
        """Multi-kind path: create every confirmed-proposal item atomically.

        Each item is created through its production service method via
        ARTIFACT_CREATION_ADAPTERS (never a shortcut insert path, so
        workflow state initialization etc. stays correct). Provenance rows
        (InterviewSessionArtifact) and the proposal's trace links are written
        inside ONE transaction.atomic() block: a failure on any item rolls
        back the entire batch and leaves the session in_progress.

        'diagram-ref' links are rejected BEFORE that block, at the
        proposal-parse level: they are reconciler-owned
        (diagram.traceability_connector) and would be silently deleted on
        the next node_graph save -- creating them here can only produce
        unexplained data loss later.
        """
        if not confirmed_proposal:
            raise ValidationError("confirmed_proposal is required for a multi-mode interview")

        for item in confirmed_proposal:
            for link in item.get("links", []):
                if link.get("type") == _DIAGRAM_REF_LINK_TYPE:
                    raise ValidationError(
                        "invalid link type in proposal: 'diagram-ref' is system-managed "
                        "and cannot be created by an interview"
                    )

        from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS
        from application.trace_link_service import TraceLinkService

        with transaction.atomic():
            created_refs = []
            for item in confirmed_proposal:
                adapter = ARTIFACT_CREATION_ADAPTERS.get(item["type"])
                if adapter is None:
                    raise ValidationError(f"unknown artifact type in proposal: {item['type']!r}")
                ref = adapter(item["fields"], ctx, session.workspace_id)
                InterviewSessionArtifact.objects.create(
                    session=session, artifact_id=ref.artifact_id, artifact_type=ref.artifact_type
                )
                created_refs.append(ref)

            for item in confirmed_proposal:
                for link in item.get("links", []):
                    source = created_refs[link["from"]]
                    target = created_refs[link["to"]]
                    TraceLinkService().create_trace_link(
                        source_id=source.artifact_id,
                        target_id=target.artifact_id,
                        link_type=link["type"],
                        ctx=ctx,
                    )

            session.status = InterviewSession.STATUS_COMPLETED
            session.save(update_fields=["status"])

        return {
            "created": [
                {"artifact_id": str(ref.artifact_id), "artifact_type": ref.artifact_type}
                for ref in created_refs
            ],
            "status": "completed",
        }

    @atomic_transaction
    def abandon(self, ctx, session_id: UUID) -> "dict[str, Any]":
        """User-initiated cancel (2026-08-20 UI-visibility fix).

        Before this, the only path to STATUS_ABANDONED was the 30-day lazy
        sweep (spec §9) -- a user closing/cancelling an in-progress
        interview (e.g. the Hermes plugin's ``cancelInterview()``/the web
        widget's "Cancel" button) had no way to actually mark the session
        abandoned server-side; it just silently stayed "in_progress"
        forever and kept showing up in in-progress lists. Distinct from
        formalize(): explicit user action, not a completion.
        """
        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(
                f"InterviewSession {session_id} is {session.status}, cannot abandon."
            )

        from workflow.services import transition as workflow_transition

        try:
            workflow_transition(
                item_id=session.id,
                target_state=InterviewSession.STATUS_ABANDONED,
                change_reason="Cancelled by user",
                ctx=ctx,
                item_type="Interview",
                workspace_id=session.workspace_id,
            )
            session.refresh_from_db()
        except Exception:
            logger.debug(
                "InterviewService: workflow transition unavailable for session=%s, "
                "falling back to direct status write", session.id
            )
            session.status = InterviewSession.STATUS_ABANDONED
            session.version = F("version") + 1
            session.save(update_fields=["status", "modified_at", "version"])
        return {"status": session.status}

    def generate_chat_turn(self, ctx, session_id: UUID, user_message: str) -> "dict[str, Any]":
        """Server-generated conversational turn -- Web Widget spec §5.

        Unlike grounding_context()'s AI-ranking layer, this is NOT fail-open:
        the web widget has no AI agent of its own to drive the interview
        dialogue (spec §5, Global Constraints), so "no LLM provider
        available" must surface as a ValidationError the widget can show,
        not silently do nothing. A *configured* mock provider (the default
        dev deployment shape, ``LLM_PROVIDER=mock``) is still called though
        -- only a failed provider *resolution* (``_resolve_provider()``
        returning ``None``) raises.

        Appends the user message and the assistant's reply to
        ``session.transcript`` regardless of whether any fields were
        extracted, so a resumed session always shows the full conversation.
        """
        from application.ai_derivation_service import AiDerivationService
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import is_over_daily_limit, record_token_usage

        session = self._get_session(ctx, session_id)
        if session.status != InterviewSession.STATUS_IN_PROGRESS:
            raise ValidationError(f"InterviewSession {session_id} is {session.status}, cannot chat.")

        provider, provider_name, resolve_error = self._resolve_provider()
        if provider is None:
            # NOT fail-open (spec §5) -- unlike grounding, there is no
            # meaningful degraded behavior for "have a conversation" without
            # an LLM, so this surfaces as an error rather than silently
            # doing nothing.
            raise ValidationError(f"No LLM provider available for interview chat: {resolve_error}")

        audit_logger = LlmAuditLogger()
        entity_id = str(session.id)

        # REQ-106: per-tenant daily token budget. This free-form flow
        # bypasses CapabilityRouter, so nothing else enforces it -- same
        # reasoning as _rank_candidates_with_ai / BundleCompressionService.
        # Not fail-open here either: an exhausted budget still means "cannot
        # chat right now", not "chat silently does nothing".
        if is_over_daily_limit():
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error="LLM_TOKEN_LIMIT_EXCEEDED",
            )
            raise ValidationError(
                "Daily LLM token limit exceeded for this tenant. Try again later "
                "or raise TENANT_TOKEN_LIMIT_PER_DAY."
            )

        phase, missing = self._current_phase_and_missing(ctx, session)
        template = AiDerivationService._get_template_content(ctx, "interview.chat_turn", session.workspace_id)
        prompt = AiDerivationService._render(
            template,
            artifact_type=session.artifact_type,
            transcript_json=json.dumps(session.transcript),
            current_phase_fragment=phase.prompt_fragment,
            missing_fields_json=json.dumps([self._serialise_field(f) for f in missing]),
            grounding_snapshot_json=json.dumps(session.grounding_snapshot),
            user_message=user_message,
        )

        timeout = resolve_timeout_seconds("interview.chat_turn")
        try:
            raw_response = provider.complete(prompt, purpose="interview.chat_turn", timeout=timeout)
        except Exception as error:  # noqa: BLE001 -- not fail-open, see docstring
            audit_logger.log_llm_call(
                provider=provider_name,
                capability="interview.chat_turn",
                artifact_id=entity_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            raise ValidationError(f"Interview chat LLM call failed: {error}") from error

        audit_logger.log_llm_call(
            provider=provider_name,
            capability="interview.chat_turn",
            artifact_id=entity_id,
            token_usage=None,
            success=True,
            error=None,
        )
        record_token_usage(provider=provider_name, capability="interview.chat_turn", input_tokens=0)

        try:
            parsed = json.loads(raw_response)
            extracted = parsed.get("extracted_fields", {}) or {}
            reply = parsed.get("reply", "")
        except (ValueError, AttributeError):
            # Model didn't follow the JSON contract -- degrade to "no fields
            # extracted, relay the raw text" rather than crashing the chat.
            # This is a response-shape leniency, distinct from the provider-
            # availability contract above: the call itself succeeded.
            extracted = {}
            reply = raw_response

        # Only record values for fields the protocol actually declares
        # (mirrors answer()'s own permissive-but-typed-when-known behavior)
        # -- an unresolved field name is silently skipped rather than
        # stored, since the prompt explicitly instructs the model to only
        # extract fields from the "still needed" list.
        protocol = get_protocol(ctx, session.artifact_type, session.workspace_id)
        for field_name, value in extracted.items():
            if self._find_protocol_field(protocol, field_name) is not None:
                self.answer(ctx, session_id, field_name, value)

        now = timezone.now().isoformat()
        session.refresh_from_db()
        session.transcript = [
            *session.transcript,
            {"role": "user", "text": user_message, "timestamp": now},
            {"role": "assistant", "text": reply, "timestamp": now},
        ]
        session.version = F("version") + 1
        session.save(update_fields=["transcript", "modified_at", "version"])
        session.refresh_from_db(fields=["version"])

        return {"reply": reply, "state": self.get_state(ctx, session_id)}

    def list_sessions(self, ctx, workspace_id: UUID, status: "Optional[str]" = None):
        self._set_tenant_context(ctx)
        # Flip stale rows before filtering, so a "status=in_progress" list
        # doesn't include sessions that are stale-but-not-yet-read
        # individually (list_sessions has no single row to lazily patch the
        # way _get_session does). Per-row (not a bulk .update()) since each
        # transition needs its own WorkflowItemState mutation + history
        # entry -- an infrequent housekeeping sweep over a handful of stale
        # rows, not a hot path.
        stale_ids = list(
            InterviewSession.objects.filter(
                workspace_id=workspace_id,
                status=InterviewSession.STATUS_IN_PROGRESS,
                modified_at__lt=timezone.now() - ABANDONED_TTL,
            ).values_list("id", flat=True)
        )
        for stale_id in stale_ids:
            stale_session = InterviewSession.objects.filter(id=stale_id).first()
            if stale_session is not None:
                self._lazily_abandon_if_stale(stale_session, ctx)

        qs = InterviewSession.objects.filter(workspace_id=workspace_id)
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-modified_at")

    def get(self, ctx, session_id: UUID) -> InterviewSession:
        return self._get_session(ctx, session_id)
