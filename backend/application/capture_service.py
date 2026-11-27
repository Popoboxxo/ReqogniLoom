"""``suggestion.capture`` — "text in, suggestions out" (ADR-032, plan P2/P3).

One server-side call replaces the ``interview.start → chat → propose →
formalize`` chain the Hermes plugin used to orchestrate (listen-mode spec §3,
finding 2.1). Everything that decides the behaviour lives here, so every client
relay — present and future — produces identical results by construction
(spec G3/G4):

1. switch → 2. workspace access → 3. capture right → 4. length → 5. redaction →
6. rule filter → 7. idempotency → 8. quota → 9. one stateless model call →
10. proposal validation → 11. create/update reconciliation → 12. receipts.

Why the order matters
---------------------
Cheap and *decisive* checks come first: a switched-off workspace must not cost a
database round trip beyond the switch itself, and a message that is a pasted
log must not cost a model call (spec S4). The credential checks run before any
content is touched, so an unauthorised caller learns nothing about the message
handling. The quota checks run *before* the model call, because their whole
purpose is to bound spend.

What is deliberately absent
---------------------------
* **No session, no transcript.** Every call is independent; cost per captured
  message does not grow with conversation length (the defect this replaces).
* **No raw text at rest.** Only the redacted, length-bounded excerpt and its
  SHA-256 are stored (decision D5). The excerpt is what a human needs to judge
  the suggestion; the hash is what dedup needs. Neither reconstructs the
  message.
* **No automatic accept.** The model produces *proposals*; a human accepts them
  (ADR-019 Zusage 7(c)). Prompt-injected instructions in the message can at most
  produce a harmless proposal (spec S10) — the tool calls no domain write here.
"""
from __future__ import annotations

import difflib
import hashlib
import logging
import re
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from django.core.cache import cache
from django.utils import timezone

from application.base import (
    ServiceBase,
    ValidationError,
)
from application.capture_errors import (
    CaptureDisabledError,
    CaptureRateLimitedError,
    CaptureTextTooLongError,
    WorkspaceForbiddenError,
)
from application.capture_filters import FilterVerdict, evaluate as evaluate_filter
from application.capture_redaction import MOSTLY_REDACTED_RATIO, redact
from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from persistence.models import Suggestion, Workspace

logger = logging.getLogger(__name__)

__all__ = [
    "CAPTURE_CLIENTS",
    "CAPTURE_CALLS_PER_HOUR",
    "CAPTURE_CREATE_TYPES",
    "CAPTURE_EXPIRES_DAYS",
    "CAPTURE_MAX_ITEMS",
    "CAPTURE_MAX_OPEN_SUGGESTIONS",
    "CAPTURE_MAX_TEXT_LENGTH",
    "CAPTURE_PROMPT_TEMPLATE_NAME",
    "CAPTURE_PRODUCER",
    "CaptureService",
]

#: Prompt-template slot of the single extraction call. A workspace may override
#: it (``prompt_template.create``) without a code change, like every other slot.
CAPTURE_PROMPT_TEMPLATE_NAME = "capture.extract"

#: Producer label of every capture receipt. Stable so an operator can tell
#: captured proposals from `traceability.suggest_links` ones at a glance.
CAPTURE_PRODUCER = "suggestion.capture"

#: The clients the contract names (spec §4.1). An unknown value is a request
#: defect, not a silently accepted ``other``: a relay that sends a wrong label
#: should learn about it.
CAPTURE_CLIENTS = frozenset(
    {
        "claude-code",
        "codex",
        "opencode",
        "kimi-code",
        "antigravity",
        "hermes",
        "other",
    }
)

#: Server-side maximum of ``text`` (spec §4.1 proposes 8000).
CAPTURE_MAX_TEXT_LENGTH = 8000

#: Upper bound of proposals one message may yield. A message that "contains" 20
#: artifacts is a document paste, not a requirement.
CAPTURE_MAX_ITEMS = 5

#: Open-proposal ceiling per workspace (spec §4.4 proposes 100). Exceeding it
#: means the inbox is not being worked; adding more would make it unusable.
CAPTURE_MAX_OPEN_SUGGESTIONS = 100

#: Call quota per (workspace, key) and hour (spec §4.4 proposes 30).
CAPTURE_CALLS_PER_HOUR = 30

#: How long a capture suggestion stays open before it is "expired" for dedup
#: purposes (O9 retention hook; nothing deletes rows yet).
CAPTURE_EXPIRES_DAYS = 30

#: A rejected proposal must not come back immediately (Hermes defect H7). It is
#: suppressed for this window when the same message hash arrives again.
CAPTURE_REJECTED_DEDUP_DAYS = 7

#: Artifact types a *create* proposal may target in v1 (decision D8).
CAPTURE_CREATE_TYPES = (
    "Requirement",
    "ArchitectureElement",
    "Adr",
    "StakeholderNeed",
)

#: Types whose live titles/versions are offered to the model as context and used
#: by the duplicate check. Excluded on purpose: Goal (append-only lineage, not
#: create- or update-capable here) and GlossaryTerm (never loaded, so the prompt
#: must not advertise it as an update target).
_CAPTURE_CONTEXT_TYPES = (
    "Requirement",
    "ArchitectureElement",
    "Adr",
    "StakeholderNeed",
    "Risk",
    "TestCase",
    "Issue",
)

#: Title similarity at which a proposed create is re-read as an update of the
#: existing artifact ("bestehendes Artefakt wiederholt", plan P3). A fixed,
#: deterministic threshold — no embeddings in v1 (D7 defers a second
#: classification stage; the spec's embedding match stays an open point).
CAPTURE_TITLE_MATCH_THRESHOLD = 0.85

#: How many existing artifacts of one type are offered as context.
_CAPTURE_CONTEXT_LIMIT = 200

_WHITESPACE = re.compile(r"\s+")

#: Name of the partial unique constraint on ``(workspace, idempotency_key)``.
#: Recognising it lets the dedup race answer ``skipped.duplicate`` instead of a
#: 500 — the whole point of an idempotency key is that a retry is harmless.
_IDEMPOTENCY_CONSTRAINT = "uq_suggestion_workspace_idempotency_key"

#: Column width of ``Suggestion.idempotency_key``.
_IDEMPOTENCY_KEY_MAX = 128


def _row_key(base: str, index: int) -> str:
    """Return the idempotency key for proposal *index* of one message.

    The first proposal keeps the caller's key verbatim (so a retry matches it);
    the others get an index suffix, truncated so the result always fits the
    ``varchar(128)`` column even for a maximum-length caller key.
    """
    if index == 0:
        return base[:_IDEMPOTENCY_KEY_MAX]
    suffix = f":{index}"
    return f"{base[: _IDEMPOTENCY_KEY_MAX - len(suffix)]}{suffix}"


def _normalize_for_hash(text: str) -> str:
    """Collapse whitespace so a re-sent message hashes identically."""
    return _WHITESPACE.sub(" ", (text or "").strip())


def _normalize_title(title: str) -> str:
    """Casefold + collapse + strip punctuation for the title comparison."""
    folded = _normalize_for_hash(title).casefold()
    return re.sub(r"[^\w\s]", "", folded)


class CaptureService(ServiceBase):
    """Layer-2 facade of the capture path (ADR-01: transports stay thin)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        ctx: AuthContext,
        *,
        workspace_id: str | UUID,
        text: str,
        client: str,
        source_session: str = "",
        message_id: str = "",
        idempotency_key: str = "",
    ) -> dict:
        """Turn one user message into zero or more open suggestions.

        Args:
            ctx: Authenticated caller; must carry the ``capture`` right.
            workspace_id: The target workspace. Mandatory — never guessed from
                the caller's key (Hermes defect H6).
            text: The user message. Redacted before storage and before the
                model call; never persisted as-is.
            client: One of :data:`CAPTURE_CLIENTS`.
            source_session: Optional client session id (provenance + dedup).
            message_id: Optional client message id (provenance + dedup).
            idempotency_key: Optional caller key; derived from the normalised
                content when omitted.

        Returns:
            ``{"created": [id…], "skipped": {"duplicate", "filtered",
            "invalid", "redacted"}, "request_id": str}``.

        Raises:
            WorkspaceForbiddenError: unknown/foreign/fenced workspace (403).
            CaptureDisabledError: the workspace switch is off (409).
            ProducerContextRequiredError: no API key / no write scope / no
                ``capture`` right (409).
            CaptureTextTooLongError: ``text`` exceeds the maximum (400).
            CaptureRateLimitedError: hourly quota or daily budget (429).
            LlmProviderUnavailableError: no usable provider (503).
        """
        self._set_tenant_context(ctx)
        request_id = str(uuid4())
        skipped = {"duplicate": 0, "filtered": 0, "invalid": 0, "redacted": 0}

        # 1. Request shape -------------------------------------------------
        client = str(client or "").strip()
        if client not in CAPTURE_CLIENTS:
            raise ValidationError(
                f"Unknown capture client {client!r}. Allowed: "
                f"{', '.join(sorted(CAPTURE_CLIENTS))}."
            )
        # Both columns are varchar(255) and the dedup key column is varchar(128).
        # Rejecting here (not only in the REST serializer) keeps REST and MCP
        # identical: an over-long client value is a request defect, and a silent
        # truncation would quietly change what the dedup key means.
        source_session = str(source_session or "")
        message_id = str(message_id or "")
        idempotency_key = str(idempotency_key or "")
        for field_name, value, limit in (
            ("source_session", source_session, 255),
            ("message_id", message_id, 255),
            ("idempotency_key", idempotency_key, _IDEMPOTENCY_KEY_MAX),
        ):
            if len(value) > limit:
                raise ValidationError(
                    f"{field_name} exceeds the {limit}-character limit."
                )

        # 2. Workspace, then 3. switch, then 4. credential ---------------
        workspace_id = self._assert_workspace_access(ctx, workspace_id)
        if not self._capture_enabled(ctx, workspace_id):
            raise CaptureDisabledError(
                "Listening is switched off for this workspace "
                "(capture.enabled = false)."
            )
        from application.base import require_capture_context

        require_capture_context(ctx)

        # 5. Length, then redaction --------------------------------------
        raw_text = text if isinstance(text, str) else ""
        if len(raw_text) > CAPTURE_MAX_TEXT_LENGTH:
            raise CaptureTextTooLongError(
                f"text exceeds the {CAPTURE_MAX_TEXT_LENGTH}-character limit.",
                limit=CAPTURE_MAX_TEXT_LENGTH,
                actual=len(raw_text),
            )
        if not raw_text.strip():
            skipped["filtered"] += 1
            return self._result([], skipped, request_id)

        redaction = redact(raw_text)
        if redaction.ratio(len(raw_text)) >= MOSTLY_REDACTED_RATIO:
            # Mostly secret material: dropping it is the only safe outcome.
            skipped["redacted"] += 1
            return self._result([], skipped, request_id)

        # 6. Rule filter --------------------------------------------------
        # The filter runs on the REDACTED text but BEFORE whitespace
        # normalisation: the paste rule is a line-shape signal, and collapsing
        # newlines (what the hash/excerpt path does) would hide it. This is the
        # one ordering that must not be "tidied up".
        verdict: FilterVerdict = evaluate_filter(redaction.text)
        if not verdict.keep:
            skipped["filtered"] += 1
            return self._result([], skipped, request_id)

        redacted_text = _normalize_for_hash(redaction.text)

        source_hash = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()
        key = _normalize_for_hash(idempotency_key) or hashlib.sha256(
            f"{workspace_id}|{client}|{source_session}|{source_hash}".encode()
        ).hexdigest()

        # 7. Dedup: idempotency key, then same message, then recently
        #    rejected --------------------------------------------------
        if self._duplicate_exists(workspace_id, key, source_hash):
            skipped["duplicate"] += 1
            return self._result([], skipped, request_id)

        # 8. Quotas (before spending anything) ---------------------------
        self._assert_call_quota(ctx, workspace_id)
        open_count = Suggestion.objects.filter(
            workspace_id=workspace_id, status=Suggestion.Status.OPEN
        ).count()
        if open_count >= CAPTURE_MAX_OPEN_SUGGESTIONS:
            raise CaptureRateLimitedError(
                "This workspace already has "
                f"{CAPTURE_MAX_OPEN_SUGGESTIONS} open suggestions; review them "
                "before capturing more.",
                limit="open_suggestions",
                value=CAPTURE_MAX_OPEN_SUGGESTIONS,
            )

        # 9. One stateless model call ------------------------------------
        existing = self._existing_artifacts(ctx, workspace_id)
        raw_items = self._extract_proposals(
            ctx, workspace_id, redacted_text, existing, request_id
        )

        # 10./11. Validate + reconcile -----------------------------------
        proposals, invalid, duplicate = self._reconcile(
            ctx, workspace_id, raw_items, existing
        )
        skipped["invalid"] += invalid
        skipped["duplicate"] += duplicate
        proposals = proposals[:CAPTURE_MAX_ITEMS]
        if not proposals:
            return self._result([], skipped, request_id)

        # 12. Receipts ----------------------------------------------------
        created, raced = self._persist(
            ctx,
            workspace_id,
            proposals,
            client=client,
            source_session=source_session,
            message_id=message_id,
            idempotency_key=key,
            source_excerpt=redacted_text[:500],
            source_hash=source_hash,
        )
        if raced:
            # Two concurrent captures of the same message: the partial unique
            # constraint fired. That is the duplicate the contract promises, not
            # a server fault — answer ``skipped.duplicate`` exactly like the
            # read-then-write pre-check would have.
            skipped["duplicate"] += 1
            created = []
            return self._result([], skipped, request_id)
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Suggestion",
            entity_id=created[0] if created else workspace_id,
            change_reason="suggestion.capture",
            details={
                "request_id": request_id,
                "client": client,
                "source_hash": source_hash,
                "redactions": redaction.hits,
                "created": [str(item) for item in created],
                "skipped": dict(skipped),
            },
        )
        return self._result(created, skipped, request_id)

    # ------------------------------------------------------------------
    # Gates
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_workspace_access(
        ctx: AuthContext, workspace_id: str | UUID
    ) -> UUID:
        """Resolve *workspace_id* and prove the caller may act in it.

        Three independent fences, one answer (``WORKSPACE_FORBIDDEN``): the
        workspace must exist in this tenant, the caller must hold a role in it,
        and an explicit key fence (``ApiKey.workspace_ids``) must include it.
        Distinguishing them would leak the existence of another tenant's
        workspace.
        """
        try:
            resolved = UUID(str(workspace_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise WorkspaceForbiddenError(
                "workspace_id must be the UUID of a workspace the caller may "
                "capture in."
            ) from exc

        if not Workspace.objects.filter(id=resolved).exists():
            raise WorkspaceForbiddenError(
                "The requested workspace is not available to this caller."
            )

        has_role = UserRole.objects.filter(
            user_id=ctx.user_id,
            workspace_id=resolved,
            # A suspended role is not an active role — the platform's
            # ``active_roles_for`` filters the same way. The outer gates already
            # deny first; this keeps the defence in depth honest for a future
            # non-REST/MCP caller.
            suspended_at__isnull=True,
        ).exists()
        if not has_role:
            raise WorkspaceForbiddenError(
                "The caller holds no role in the requested workspace."
            )

        if ctx.api_key_id is not None:
            from auth_tenancy.models import ApiKey

            fence = (
                ApiKey.objects.filter(id=ctx.api_key_id)
                .values_list("workspace_ids", flat=True)
                .first()
            )
            if fence and str(resolved) not in {str(item) for item in fence}:
                raise WorkspaceForbiddenError(
                    "This API key is fenced to other workspaces."
                )

        return resolved

    @staticmethod
    def _capture_enabled(ctx: AuthContext, workspace_id: UUID) -> bool:
        """Read the workspace switch (``capture.enabled``, default off).

        The key is registered in ``auth_tenancy`` (the preference surface's
        owner) with the workspace level only, so a tenant-wide default cannot
        switch listening on for workspaces nobody enabled. A resolution failure
        is treated as "off": an unreadable switch must never enable capture.
        """
        from application.preference_service import resolve_for

        try:
            value, _source = resolve_for(
                tenant_id=ctx.tenant_id,
                workspace_id=workspace_id,
                user_id=None,
                key="capture.enabled",
            )
        except Exception:  # noqa: BLE001 — fail closed, see docstring
            logger.warning(
                "capture: could not resolve capture.enabled for workspace=%s",
                workspace_id,
                exc_info=True,
            )
            return False
        return value is True

    # ------------------------------------------------------------------
    # Dedup + quotas
    # ------------------------------------------------------------------

    @staticmethod
    def _duplicate_exists(
        workspace_id: UUID, idempotency_key: str, source_hash: str
    ) -> bool:
        """Return whether this message was already captured (spec §4.2 step 4).

        Two lookups, cheapest first:

        * the idempotency key — an exact retry of the same call, regardless of
          state (an accepted proposal must not be re-proposed either),
        * the same normalised content that is still ``open`` or was rejected
          inside :data:`CAPTURE_REJECTED_DEDUP_DAYS`. A rejection is the user
          saying "not now"; letting the identical message back in immediately
          is Hermes defect H7.
        """
        now = timezone.now()
        if Suggestion.objects.filter(
            workspace_id=workspace_id, idempotency_key=idempotency_key
        ).exists():
            return True

        open_or_pending = Suggestion.objects.filter(
            workspace_id=workspace_id,
            source_hash=source_hash,
        ).filter(
            models_q_open_or_recent_rejected(now)
        )
        return open_or_pending.exists()

    @staticmethod
    def _assert_call_quota(ctx: AuthContext, workspace_id: UUID) -> None:
        """Enforce the hourly call quota for (workspace, key).

        Backed by the shared cache: capture is a per-message hot path, so a
        counter must not cost a database write. A cache outage degrades to
        "not limited" (fail-open) — the daily token budget below is the
        fail-closed backstop, and refusing every capture because the cache is
        down would be the opposite of the fail-open relay contract.
        """
        bucket = f"capture:calls:{workspace_id}:{ctx.api_key_id}:{int(timezone.now().timestamp() // 3600)}"
        try:
            cache.add(bucket, 0, 3700)
            count = cache.incr(bucket)
        except Exception:  # noqa: BLE001 — fail-open, see docstring
            logger.warning("capture: cache unavailable, call quota not enforced")
            return
        if count > CAPTURE_CALLS_PER_HOUR:
            raise CaptureRateLimitedError(
                f"Capture is limited to {CAPTURE_CALLS_PER_HOUR} calls per hour "
                "per key and workspace.",
                limit="calls_per_hour",
                value=CAPTURE_CALLS_PER_HOUR,
            )

    # ------------------------------------------------------------------
    # Existing-artifact context
    # ------------------------------------------------------------------

    def _existing_artifacts(
        self, ctx: AuthContext, workspace_id: UUID
    ) -> dict[str, dict[str, Any]]:
        """Return ``id -> {"type", "id", "title", "version"}`` of live artifacts.

        Used for two things at once, which is why it is one read: the model
        needs the existing titles to decide between "new" and "extend this one",
        and the dedup step needs the ids/versions to turn a repeated create into
        an update proposal.

        One bounded query per type — ``[:limit]`` on a ``values()`` queryset is a
        real ``LIMIT``, unlike slicing a service method that returns a
        materialised list (which would load the whole workspace on every
        captured message). Only ``id``/``title``/``version`` are read, and
        outdated rows are excluded by the same ``Artifact.lifecycle_status``
        filter the list services use. Any failure degrades that type to "no
        candidates": the context is an optimisation, never a gate.
        """
        from persistence.models import LifecycleStatus

        live = (LifecycleStatus.ACTIVE, LifecycleStatus.DEPRECATED)
        found: dict[str, dict[str, Any]] = {}

        for model_name in _CAPTURE_CONTEXT_TYPES:
            try:
                model = _context_model(model_name)
                rows = model.objects.filter(
                    workspace_id=workspace_id,
                    artifact__lifecycle_status__in=live,
                ).values("id", "title", "version")[: _CAPTURE_CONTEXT_LIMIT]
                for row in rows:
                    found[str(row["id"])] = {
                        "type": model_name,
                        "id": str(row["id"]),
                        "title": row["title"],
                        "version": int(row["version"] or 0),
                    }
            except Exception:  # noqa: BLE001 — context is best effort
                logger.warning(
                    "capture: %s context unavailable", model_name, exc_info=True
                )

        return found

    # ------------------------------------------------------------------
    # Model call
    # ------------------------------------------------------------------

    def _extract_proposals(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        redacted_text: str,
        existing: dict[str, dict[str, Any]],
        request_id: str,
    ) -> list[Any]:
        """Run the single extraction call and return the raw proposal list.

        Fail-closed here, unlike the interview chat path: a listener that
        silently does nothing is indistinguishable from a broken one (Hermes
        defect H2). No provider, a placeholder (``mock``) provider or an
        exhausted token budget therefore answers the contract's error codes
        instead of an empty success.
        """
        from application.ai_derivation_service import (
            AiDerivationService,
            LlmProviderUnavailableError,
        )
        from application.llm_provider_resolution import MOCK_PROVIDER_NAME, resolve_provider
        from llm_adapter.audit_logger import LlmAuditLogger
        from llm_adapter.json_output import JsonOutputError, parse_json_list
        from llm_adapter.providers import MockLlmProvider
        from llm_adapter.timeouts import resolve_timeout_seconds
        from llm_adapter.token_tracking import (
            approximate_token_count,
            is_over_daily_limit,
            record_token_usage,
        )

        provider, provider_name, resolve_error = resolve_provider()
        if provider is None or provider_name == MOCK_PROVIDER_NAME or isinstance(
            provider, MockLlmProvider
        ):
            logger.warning(
                "capture: no real LLM provider (%s); refusing to guess proposals",
                resolve_error,
            )
            raise LlmProviderUnavailableError(
                "suggestion.capture needs a configured LLM provider; none is "
                "available."
            )

        # Decision D7/spec §4.4: the daily budget is fail-closed on this path.
        if is_over_daily_limit():
            raise CaptureRateLimitedError(
                "The daily token budget is exhausted; capture stops until it "
                "resets.",
                limit="daily_tokens",
            )

        prompt = self._build_prompt(ctx, workspace_id, redacted_text, existing)
        timeout = resolve_timeout_seconds(CAPTURE_PROMPT_TEMPLATE_NAME)
        audit = LlmAuditLogger()
        try:
            raw = provider.complete(
                prompt, purpose=CAPTURE_PROMPT_TEMPLATE_NAME, timeout=timeout
            )
        except Exception as error:  # noqa: BLE001 — mapped to the contract code
            audit.log_llm_call(
                provider=provider_name,
                capability=CAPTURE_PROMPT_TEMPLATE_NAME,
                artifact_id=request_id,
                token_usage=None,
                success=False,
                error=str(error),
            )
            logger.warning("capture: provider call failed: %s", error)
            raise LlmProviderUnavailableError(
                "The LLM provider could not be reached; nothing was captured."
            ) from error

        audit.log_llm_call(
            provider=provider_name,
            capability=CAPTURE_PROMPT_TEMPLATE_NAME,
            artifact_id=request_id,
            token_usage=None,
            success=True,
            error=None,
        )
        # ``capture.extract`` is the accounting label required by the plan; the
        # workspace id attributes the spend to the right budget.
        record_token_usage(
            provider=provider_name,
            capability=CAPTURE_PROMPT_TEMPLATE_NAME,
            input_tokens=approximate_token_count(prompt),
            output_tokens=approximate_token_count(raw),
            workspace_id=str(workspace_id),
        )

        try:
            parsed = parse_json_list(raw, mode="tolerant")
        except JsonOutputError:
            # A model that answers prose instead of JSON produced no usable
            # proposal; that is an invalid answer, not a server fault.
            logger.info("capture: provider answer carried no JSON proposal list")
            return []
        return parsed if isinstance(parsed, list) else []

    def _build_prompt(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        redacted_text: str,
        existing: dict[str, dict[str, Any]],
    ) -> str:
        """Render the extraction prompt from the workspace-overridable slot."""
        from application.ai_derivation_service import AiDerivationService
        from application.capture_update import supports_update, update_allowlist
        from application.interview_artifact_adapters import allowed_fields_for

        # Advertise only what reconciliation will actually accept: the update
        # list is the intersection of "the shared update seam can write it" and
        # "its artifacts are in the context". Advertising a type that can never
        # be targeted only burns prompt tokens and drops proposals as invalid.
        update_types = [
            artifact_type
            for artifact_type in _CAPTURE_CONTEXT_TYPES
            if supports_update(artifact_type)
        ]

        contract_lines = []
        for artifact_type in CAPTURE_CREATE_TYPES:
            contract_lines.append(
                f"- {artifact_type} (create): "
                f"{', '.join(sorted(allowed_fields_for(artifact_type)))}"
            )
        for artifact_type in update_types:
            contract_lines.append(
                f"- {artifact_type} (update): "
                f"{', '.join(sorted(update_allowlist(artifact_type)))}"
            )

        context_lines = [
            f"- {entry['type']} {entry['id']} v{entry['version']}: {entry['title']}"
            for entry in list(existing.values())[:_CAPTURE_CONTEXT_LIMIT]
        ]

        return AiDerivationService._resolve_and_render(
            ctx,
            CAPTURE_PROMPT_TEMPLATE_NAME,
            workspace_id,
            message_text=redacted_text,
            create_types=", ".join(CAPTURE_CREATE_TYPES),
            update_types=", ".join(update_types),
            field_contract="\n".join(contract_lines),
            existing_artifacts="\n".join(context_lines) or "(none)",
        )

    # ------------------------------------------------------------------
    # Validation + reconciliation
    # ------------------------------------------------------------------

    def _reconcile(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        raw_items: list[Any],
        existing: dict[str, dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Validate the model's items and decide create vs. update.

        Returns ``(proposals, invalid_count, duplicate_count)``. Invalid entries
        are counted, not raised (spec §4.2 step 6): one hallucinated field must
        not throw away the three good proposals next to it. A proposal that is
        dropped because it merely repeats an existing artifact is counted as a
        *duplicate* — a client must be able to tell "the model proposed nothing"
        from "the proposal was dropped".
        """
        from application.capture_update import supports_update
        from application.interview_multi_formalize_service import (
            validate_capture_proposal_item,
        )

        proposals: list[dict[str, Any]] = []
        invalid = 0
        duplicate = 0

        for raw_item in raw_items:
            requested_update = False
            requested_target = ""
            rationale = ""
            if isinstance(raw_item, dict):
                requested_update = (
                    str(raw_item.get("operation") or "").strip().lower() == "update"
                )
                requested_target = str(
                    raw_item.get("target_artifact_id")
                    or raw_item.get("target_id")
                    or ""
                )
                # The model's operation/target/prompt hints are not artifact
                # fields — strip them before the field allowlist sees them. The
                # rationale survives in the payload so the accept audit can name
                # *why* the artifact changed.
                rationale = str(raw_item.get("rationale") or "")[:1000]
                raw_item = {
                    key: value
                    for key, value in raw_item.items()
                    if key
                    not in {
                        "operation",
                        "target_artifact_id",
                        "target_id",
                        "base_version",
                        "rationale",
                    }
                }

            mode = "update" if (requested_update or requested_target) else "create"
            try:
                item = validate_capture_proposal_item(
                    ctx, workspace_id, raw_item, mode=mode
                )
            except ValidationError as exc:
                logger.info("capture: dropped invalid proposal item: %s", exc)
                invalid += 1
                continue

            artifact_type = item["type"]
            fields = item["fields"]

            if mode == "update":
                target = existing.get(requested_target)
                if target is None or target["type"] != artifact_type:
                    invalid += 1
                    continue
                if not supports_update(artifact_type):
                    invalid += 1
                    continue
                proposals.append(
                    {
                        "operation": Suggestion.Operation.UPDATE,
                        "artifact_type": artifact_type,
                        "fields": fields,
                        "target_artifact_id": target["id"],
                        # The server reads the base version, never the model:
                        # a fabricated version would defeat the lock.
                        "base_version": target["version"],
                        "rationale": rationale,
                    }
                )
                continue

            if artifact_type not in CAPTURE_CREATE_TYPES:
                invalid += 1
                continue

            match = self._match_existing(artifact_type, fields, existing)
            if match is None:
                proposals.append(
                    {
                        "operation": Suggestion.Operation.CREATE,
                        "artifact_type": artifact_type,
                        "fields": fields,
                        "target_artifact_id": None,
                        "base_version": None,
                        "rationale": rationale,
                    }
                )
                continue

            # "An existing artifact, repeated" is an update, not a duplicate
            # create (plan P3). A bare title with nothing new is a duplicate.
            if not {key for key in fields if key != "title"}:
                duplicate += 1
                continue
            if not supports_update(artifact_type):
                # No update facade for this type: proposing an update would be
                # undeliverable, so the repeated title is counted as a
                # duplicate rather than silently vanishing.
                duplicate += 1
                continue
            proposals.append(
                {
                    "operation": Suggestion.Operation.UPDATE,
                    "artifact_type": artifact_type,
                    "fields": fields,
                    "target_artifact_id": match["id"],
                    "base_version": match["version"],
                    "rationale": rationale,
                }
            )

        return proposals, invalid, duplicate

    @staticmethod
    def _match_existing(
        artifact_type: str,
        fields: dict[str, Any],
        existing: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the existing artifact whose title the proposal repeats.

        Deterministic title similarity (casefold, punctuation-stripped,
        ``difflib`` ratio ≥ :data:`CAPTURE_TITLE_MATCH_THRESHOLD`). Semantic
        matching via embeddings is deliberately not in v1 — the spec leaves the
        threshold open and D7 keeps v1 rule-based.
        """
        title = fields.get("title")
        if not isinstance(title, str) or not title.strip():
            return None
        wanted = _normalize_title(title)
        for entry in existing.values():
            if entry["type"] != artifact_type:
                continue
            candidate = _normalize_title(str(entry["title"]))
            if not candidate:
                continue
            if wanted == candidate:
                return entry
            if (
                difflib.SequenceMatcher(None, wanted, candidate).ratio()
                >= CAPTURE_TITLE_MATCH_THRESHOLD
            ):
                return entry
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        proposals: list[dict[str, Any]],
        *,
        client: str,
        source_session: str,
        message_id: str,
        idempotency_key: str,
        source_excerpt: str,
        source_hash: str,
    ) -> tuple[list[UUID], bool]:
        """Store one receipt per proposal atomically, under one idempotency key.

        The first proposal takes the caller's key; the others are suffixed with
        their index, because the key is unique per workspace and one message may
        legitimately yield several proposals. The key is truncated before the
        suffix so a caller-supplied 128-character key cannot overflow the
        column on proposal #2.

        The whole batch runs in ONE transaction (fix for the review finding
        "capture() is not atomic across proposals"): a failure on proposal #3
        must not leave #1–#2 persisted while the request answers 500 — those
        surviving rows would make every retry answer ``duplicate`` and the
        remaining proposals unrecoverable.

        Returns:
            ``(created_ids, raced)``. ``raced`` is True when the partial unique
            constraint on ``(workspace, idempotency_key)`` fired: two concurrent
            captures of the same message. That is the contract's
            ``skipped.duplicate``, not a server fault, so it is reported as a
            flag instead of an exception.
        """
        from django.db import IntegrityError, transaction

        from application.suggestion_service import SuggestionService

        service = SuggestionService()
        expires_at = timezone.now() + timedelta(days=CAPTURE_EXPIRES_DAYS)
        created: list[UUID] = []

        try:
            with transaction.atomic():
                for index, proposal in enumerate(proposals):
                    is_update = proposal["operation"] == Suggestion.Operation.UPDATE
                    kind = (
                        Suggestion.Kind.ARTIFACT_UPDATE
                        if is_update
                        else Suggestion.Kind.ARTIFACT_CREATE
                    )
                    payload = {
                        "artifact_type": proposal["artifact_type"],
                        "fields": proposal["fields"],
                        "rationale": proposal.get("rationale") or "",
                        "capture": {
                            "client": client,
                            "source_session": source_session,
                            "source_hash": source_hash,
                        },
                    }
                    if is_update:
                        payload["target_artifact_id"] = proposal[
                            "target_artifact_id"
                        ]
                        payload["base_version"] = proposal["base_version"]

                    suggestion = service.create(
                        kind=kind,
                        ctx=ctx,
                        workspace_id=workspace_id,
                        payload=payload,
                        producer=CAPTURE_PRODUCER,
                        target_item_type=proposal["artifact_type"],
                        target_item_id=proposal["target_artifact_id"],
                        capture=True,
                        capture_client=client,
                        capture_session=source_session,
                        message_id=message_id,
                        idempotency_key=_row_key(idempotency_key, index),
                        source_excerpt=source_excerpt,
                        source_hash=source_hash,
                        operation=proposal["operation"],
                        target_artifact_id=proposal["target_artifact_id"],
                        base_version=proposal["base_version"],
                        expires_at=expires_at,
                    )
                    created.append(suggestion.id)
        except IntegrityError as exc:
            if _IDEMPOTENCY_CONSTRAINT in str(exc):
                return [], True
            raise

        return created, False

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _result(created: list[UUID], skipped: dict[str, int], request_id: str) -> dict:
        """Build the contract response (spec §4.3)."""
        return {
            "created": [str(item) for item in created],
            "skipped": skipped,
            "request_id": request_id,
        }


def models_q_open_or_recent_rejected(now):
    """Return the ``Q`` for "open (and not expired), or rejected recently".

    The *open* branch honours ``expires_at``: an abandoned capture must not
    suppress the same message forever, which is what a status-only predicate
    would do. ``NULL`` expiry still means "never expires" (the historical
    default for producers that are not client relays).
    """
    from django.db.models import Q

    live_open = Q(status=Suggestion.Status.OPEN) & (
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )
    return live_open | Q(
        status=Suggestion.Status.REJECTED,
        decided_at__gte=now - timedelta(days=CAPTURE_REJECTED_DEDUP_DAYS),
    )


def _context_model(model_name: str):
    """Return the ORM model of a capture-context type."""
    from persistence import models

    return getattr(models, model_name)
