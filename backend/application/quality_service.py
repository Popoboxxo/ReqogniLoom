"""QualityService — advisory, LLM-backed quality assessment of one artifact.

leaf_id : Plan B / B5-T3 (issue #378)
req_id  : REQ-L2-AI-001, REQ-L2-AI-002, REQ-L2-AS-021, REQ-L2-AS-022

One verdict per run, one row per verdict. The model
(:class:`persistence.models.QualityAssessment`) is append-only and already
carries the provenance of a run, so this service only orchestrates: resolve the
entity **inside the addressed workspace**, fingerprint its content, reuse the
last verdict when nothing changed, otherwise render the type's ``quality_*``
slot, run one completion, validate the JSON contract and persist the result.

Workspace binding (KA-B-10, QR-S08): every lookup filters on ``workspace_id``
**in the query**, so an entity of another workspace of the same tenant is
simply absent — ``NotFoundError``, no provider call, no row. Dark-scoped
callers therefore cannot assess a foreign artifact by naming its id.

Cache: ``content_hash`` is a SHA-256 over the canonical form of the fields the
prompt sees **plus the prompt provenance the run would use** -- the slot, the
resolved scope/version and a hash of the effective template body. Hashing the
artifact alone would replay an old verdict as ``cached`` after the rubric
(template) changed; the body hash also covers the factory scope, where there is
no version number. Resolving the provenance is a local template lookup, so a
cache hit still makes no provider call. Without ``force`` and with an unchanged
hash the last *successful* verdict is returned with ``cached=True``. A
``failed`` row is never replayed as a verdict (the caller asked for a verdict;
the next call retries), mirroring
``AiDerivationService._discard_cached_completion``.

Failures write a ``status="failed"`` row with ``error_code`` and then re-raise,
so the transports map the *cause* onto 502/503/504/429 instead of a generic
500 — the failed row is a durable trace of the attempt, not a substitute.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from auth_tenancy.context import AuthContext
from llm_adapter.providers import truncate_prompt_content
from persistence.models import (
    Adr,
    QualityAssessment,
    Requirement,
    Risk,
    TestCase,
)

logger = logging.getLogger(__name__)

#: Assessable entity types and the prompt slot each one renders.
ASSESSABLE_TYPES: dict[str, str] = {
    "Requirement": "quality_requirement",
    "Adr": "quality_adr",
    "TestCase": "quality_testcase",
    "Risk": "quality_risk",
}

#: Upper bound of one history page. A client asking for more gets this many,
#: not an unbounded table scan.
MAX_HISTORY_LIMIT = 100

#: Registry lookups. ``workspace_filter`` is the field the workspace is bound
#: on -- the artifact for the two artifact-backed entities, the entity's own
#: column for ADR/Risk. Deliberately one authoritative field per type rather
#: than an ``OR`` across both: a stale denormalised copy would otherwise widen
#: the query instead of narrowing it.
_ENTITY_TYPES: dict[str, tuple[Any, str]] = {
    "Requirement": (Requirement, "artifact__workspace_id"),
    "Adr": (Adr, "workspace_id"),
    "TestCase": (TestCase, "artifact__workspace_id"),
    "Risk": (Risk, "workspace_id"),
}

#: Fields the ADR/TestCase/Risk slots receive as one JSON blob
#: (``artifact_fields_json``). Only stable, prompt-meaningful columns -- the
#: audit counters and relation ids would add noise without adding signal.
_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "Adr": ("decision", "context", "consequences", "status", "uid"),
    "TestCase": ("steps", "test_type", "execution_status", "scenario_kind", "uid"),
    "Risk": (
        "probability",
        "impact",
        "category",
        "mitigation_strategy",
        "detection",
        "status",
        "uid",
    ),
}


def _jsonable(value: Any) -> Any:
    """Best-effort JSON-safe copy of *value* (UUIDs, dates, models)."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def canonical_content(entity_type: str, entity: Any) -> dict[str, Any]:
    """Return the canonical, hashable view of *entity* the prompt renders.

    The requirement slot reviews the IEEE-29148 fields individually; every
    other type is reviewed through its serialised field map (see
    ``application.prompt_slots``). A missing column degrades to an empty
    string/object instead of raising, so a partially populated row can still be
    assessed.
    """
    title = truncate_prompt_content(str(getattr(entity, "title", "") or ""))
    description = truncate_prompt_content(
        str(getattr(entity, "description", "") or "")
    )
    if entity_type == "Requirement":
        items = getattr(entity, "acceptance_criteria_items", None)
        criteria = str(getattr(entity, "acceptance_criteria", "") or "")
        if isinstance(items, list) and items:
            criteria = json.dumps(_jsonable(items), ensure_ascii=False, sort_keys=True)
        return {
            "title": title,
            "description": description,
            "acceptance_criteria": truncate_prompt_content(criteria),
            "rationale": truncate_prompt_content(
                str(getattr(entity, "rationale", "") or "")
            ),
            "verification_method": str(
                getattr(entity, "verification_method", "") or ""
            ),
        }
    fields = {
        name: getattr(entity, name, None)
        for name in _FIELDS_BY_TYPE[entity_type]
    }
    return {
        "title": title,
        "description": description,
        "fields": _jsonable(fields),
    }


def content_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical serialisation of *payload*."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assessment_payload(
    assessment: QualityAssessment, *, cached: bool = False
) -> dict[str, Any]:
    """Wire form of one assessment row -- identical for REST and MCP.

    ``cached`` is a property of the *call*, not of the row (the same row can be
    freshly written once and later served from the hash cache), so the caller
    supplies it.
    """
    return {
        "assessment_id": str(assessment.id),
        "entity_type": assessment.entity_type,
        "entity_id": str(assessment.entity_id),
        "score": assessment.score,
        "reasoning": assessment.reasoning,
        "suggestions": list(assessment.suggestions or []),
        "criteria": dict(assessment.criteria or {}),
        "prompt_slot": assessment.prompt_slot,
        "prompt_scope": assessment.prompt_scope,
        "provider": assessment.provider,
        "model": assessment.model,
        "trigger": assessment.trigger,
        "status": assessment.status,
        "cached": cached,
        "assessed_at": assessment.created_at.isoformat(),
    }


class QualityService(ServiceBase):
    """Advisory quality assessments (see the module docstring)."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        entity_type: str,
        entity_id: UUID,
        *,
        force: bool = False,
        trigger: str = "manual",
    ) -> tuple[QualityAssessment, bool]:
        """Assess one entity; return ``(row, cached)``.

        Raises:
            ValidationError: ``entity_type`` is not assessable, or ``trigger``
                is not a known trigger.
            NotFoundError: The entity does not exist in *workspace_id*.
            LlmResponseError (and its #1416 subclasses): The provider failed or
                answered unusably. A ``status="failed"`` row is written first.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        slot = self._slot_for(entity_type)
        if trigger not in QualityAssessment.Trigger.values:
            raise ValidationError(
                f"Unknown trigger {trigger!r}; expected one of "
                f"{list(QualityAssessment.Trigger.values)}."
            )

        entity = self._load_entity(workspace_id, entity_type, entity_id)
        payload = canonical_content(entity_type, entity)
        # The cache key covers the prompt provenance as well: a rubric change
        # must invalidate the verdict of an untouched artifact. Resolved before
        # the hash, but a local template lookup -- no provider call on a hit.
        prompt_scope, prompt_version, template_hash = self._prompt_provenance(
            ctx, slot, workspace_id
        )
        digest = content_hash(
            {
                "content": payload,
                "prompt_slot": slot,
                "prompt_scope": prompt_scope,
                "prompt_version": prompt_version,
                "prompt_template_hash": template_hash,
            }
        )

        if not force:
            previous = self._latest(workspace_id, entity_type, entity_id)
            if (
                previous is not None
                and previous.status == QualityAssessment.Status.OK
                and previous.content_hash == digest
            ):
                return previous, True

        provider, model = self._provider_provenance()
        common: dict[str, Any] = {
            "tenant_id": ctx.tenant_id,
            "workspace_id": workspace_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "artifact_id": getattr(entity, "artifact_id", None),
            "content_hash": digest,
            "entity_version": getattr(entity, "version", None),
            "prompt_slot": slot,
            "prompt_scope": prompt_scope,
            "prompt_version": prompt_version,
            "provider": provider,
            "model": model,
            "trigger": trigger,
            "triggered_by": ctx.agent_label or str(ctx.user_id),
        }

        try:
            verdict = self._run_prompt(ctx, slot, workspace_id, entity_type, entity, payload)
        except Exception as exc:  # noqa: BLE001 - traced, then re-raised
            row = QualityAssessment(
                **common,
                score=0.0,
                reasoning="",
                status=QualityAssessment.Status.FAILED,
                error_code=type(exc).__name__[:64],
            )
            row.save()
            self._audit(
                ctx,
                "create",
                "QualityAssessment",
                row.id,
                details={"status": row.status, "error_code": row.error_code},
            )
            raise

        row = QualityAssessment(
            **common,
            score=verdict["score"],
            reasoning=verdict["reasoning"],
            suggestions=verdict["suggestions"],
            criteria=verdict["criteria"],
            status=QualityAssessment.Status.OK,
        )
        row.save()
        self._audit(
            ctx,
            "create",
            "QualityAssessment",
            row.id,
            details={"status": row.status, "score": row.score},
        )
        return row, False

    def history(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        entity_type: str,
        entity_id: UUID,
        *,
        limit: int = 20,
    ) -> list[QualityAssessment]:
        """Newest-first assessment history of one entity (``-created_at``, ``-id``).

        Raises:
            ValidationError: ``entity_type`` is not assessable or ``limit`` is
                outside ``1..MAX_HISTORY_LIMIT``.
            NotFoundError: The entity does not exist in *workspace_id*.
        """
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)
        self._slot_for(entity_type)
        if not isinstance(limit, int) or not 1 <= limit <= MAX_HISTORY_LIMIT:
            raise ValidationError(
                f"limit must be an integer between 1 and {MAX_HISTORY_LIMIT}."
            )
        self._load_entity(workspace_id, entity_type, entity_id)
        return list(
            QualityAssessment.objects.filter(
                workspace_id=workspace_id,
                entity_type=entity_type,
                entity_id=entity_id,
            ).order_by("-created_at", "-id")[:limit]
        )

    def latest_for(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        entity_type: str,
        entity_ids: list[UUID],
    ) -> dict[UUID, QualityAssessment]:
        """Map every id in *entity_ids* that has a verdict onto its newest row."""
        self._set_tenant_context(ctx)
        self._assert_read_permission(ctx)
        self._slot_for(entity_type)
        if not entity_ids:
            return {}
        rows = QualityAssessment.objects.filter(
            workspace_id=workspace_id,
            entity_type=entity_type,
            entity_id__in=list(entity_ids),
        ).order_by("entity_id", "-created_at", "-id")
        latest: dict[UUID, QualityAssessment] = {}
        for row in rows:
            latest.setdefault(row.entity_id, row)
        return latest

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_read_permission(ctx: AuthContext) -> None:
        """Deny a caller the RBAC matrix does not grant READ to.

        Deliberately the matrix check (not ``ctx.has_role("viewer")``, which
        only matches that one literal role name): editor/admin/approver read
        too, and an unknown/empty role set stays fail-closed.
        """
        from auth_tenancy.services.authorization import AuthorizationService, Operation

        if not AuthorizationService().decide_access(ctx.active_roles, Operation.READ).allow:
            raise PermissionDeniedError(
                f"Permission denied: read operation requires at least 'viewer' "
                f"role, user has {ctx.active_roles}"
            )

    @staticmethod
    def _slot_for(entity_type: str) -> str:
        """Return the prompt slot of *entity_type*, or raise ``ValidationError``."""
        slot = ASSESSABLE_TYPES.get(entity_type)
        if slot is None:
            raise ValidationError(
                f"{entity_type!r} is not assessable; expected one of "
                f"{sorted(ASSESSABLE_TYPES)}."
            )
        return slot

    @staticmethod
    def _load_entity(workspace_id: UUID, entity_type: str, entity_id: UUID) -> Any:
        """Load *entity_id* **inside** *workspace_id* (filter in the query)."""
        model, workspace_filter = _ENTITY_TYPES[entity_type]
        entity = model.objects.filter(
            id=entity_id, **{workspace_filter: workspace_id}
        ).first()
        if entity is None:
            # Same answer for "does not exist" and "belongs to another
            # workspace": the caller must not learn that the id exists
            # elsewhere in the tenant.
            raise NotFoundError(
                f"{entity_type} {entity_id} not found in workspace {workspace_id}."
            )
        return entity

    @staticmethod
    def _latest(
        workspace_id: UUID, entity_type: str, entity_id: UUID
    ) -> QualityAssessment | None:
        return (
            QualityAssessment.objects.filter(
                workspace_id=workspace_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            .order_by("-created_at", "-id")
            .first()
        )

    @staticmethod
    def _prompt_provenance(
        ctx: AuthContext, slot: str, workspace_id: UUID
    ) -> tuple[str, int | None, str]:
        """Return ``(scope, version, template_hash)`` of the template a run uses.

        The third element fingerprints the effective template *body*, so the
        cache key also moves when the body changes without a version number --
        the factory scope has no stored version at all.
        """
        from application.prompt_template_versioning import get_active_template

        for scope, scope_id in (
            (QualityAssessment.PromptScope.WORKSPACE, workspace_id),
            (QualityAssessment.PromptScope.GLOBAL, None),
        ):
            row = get_active_template(
                tenant_id=ctx.tenant_id, name=slot, workspace_id=scope_id
            )
            if row is not None:
                return scope, row.version, content_hash({"content": row.content})
        from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS

        factory_body = PROMPT_TEMPLATE_DEFAULTS.get(slot, "")
        return (
            QualityAssessment.PromptScope.FACTORY,
            None,
            content_hash({"content": factory_body}),
        )

    @staticmethod
    def _provider_provenance() -> tuple[str, str]:
        """Return ``(provider, model)`` of the currently effective provider."""
        from django.conf import settings

        from llm_adapter.providers import get_provider

        configured = getattr(settings, "LLM_PROVIDER", "unknown")
        try:
            provider = get_provider()
        except Exception:  # noqa: BLE001 - provenance must not block the run
            return configured, ""
        name = str(getattr(provider, "PROVIDER_NAME", configured) or configured)
        model = getattr(provider, "model_name", None) or getattr(
            provider, "MODEL_NAME", ""
        )
        return name, str(model or "")

    @staticmethod
    def _run_prompt(
        ctx: AuthContext,
        slot: str,
        workspace_id: UUID,
        entity_type: str,
        entity: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Render the slot, run one completion and validate the JSON contract."""
        from application.ai_derivation_service import (
            AiDerivationService,
            LlmResponseError,
        )

        service = AiDerivationService()
        if entity_type == "Requirement":
            data = {
                "artifact_title": payload["title"],
                "artifact_description": payload["description"],
                "acceptance_criteria": payload["acceptance_criteria"],
                "rationale": payload["rationale"],
                "verification_method": payload["verification_method"],
            }
        else:
            data = {
                "artifact_title": payload["title"],
                "artifact_description": payload["description"],
                "artifact_fields_json": json.dumps(
                    payload["fields"], ensure_ascii=False, sort_keys=True
                ),
            }
        # ``_render_slot`` in the plan is this service's ``_resolve_and_render``
        # (the resolver entry point every current flow uses; it also injects the
        # catalog config variables). ``quality_*`` is a memory HARD_OFF family,
        # so no memory block is consulted.
        prompt = service._resolve_and_render(  # noqa: SLF001 - shared flow helper
            ctx,
            slot,
            workspace_id,
            artifact_id=getattr(entity, "artifact_id", None),
            entity_type=entity_type,
            **data,
        )
        parsed, _is_mock_fallback = service._complete_json_object(  # noqa: SLF001
            prompt,
            purpose="quality_assess",
            artifact_id=getattr(entity, "artifact_id", None) or entity.id,
        )
        return _validate_verdict(parsed)


def _validate_verdict(parsed: dict[str, Any]) -> dict[str, Any]:
    """Normalise the LLM verdict, raising ``LlmResponseError`` when unusable.

    A hallucinated shape must never reach the column: ``score`` outside
    ``0..1`` (or non-numeric) is a 502 ``LLM_OUTPUT_INVALID`` at the transport
    layer, not a stored 2.0 that the DB check constraint would turn into a 500.
    ``suggestions``/``criteria`` are best-effort filtered rather than rejected,
    because a missing hint list is not an unusable verdict.
    """
    from application.ai_derivation_service import LlmResponseError

    raw_score = parsed.get("score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise LlmResponseError(
            "The LLM response carried no numeric 'score'."
        )
    score = float(raw_score)
    if not 0.0 <= score <= 1.0:
        raise LlmResponseError(
            f"The LLM response scored {score}, outside the 0..1 range."
        )
    raw_suggestions = parsed.get("suggestions")
    suggestions = (
        [str(item) for item in raw_suggestions if isinstance(item, str)]
        if isinstance(raw_suggestions, list)
        else []
    )
    raw_criteria = parsed.get("criteria")
    criteria = (
        {
            str(name): float(value)
            for name, value in raw_criteria.items()
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and 0.0 <= float(value) <= 1.0
        }
        if isinstance(raw_criteria, dict)
        else {}
    )
    return {
        "score": score,
        "reasoning": str(parsed.get("reasoning") or ""),
        "suggestions": suggestions,
        "criteria": criteria,
    }
