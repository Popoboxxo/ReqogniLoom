"""Adapter registry: multi-artifact interview formalize() -> real create_X() calls.

Every entry MUST call the existing, production ``create_X()`` service method
for that type -- never a shortcut insert path. This is what keeps workflow
state initialization (e.g. RequirementService.create_requirement() calling
initialize_workflow_states() internally) correct for free.

Contract (Task 3): ``CreatedArtifactRef.artifact_id`` is ALWAYS the
``persistence.Artifact`` PK -- the FK target of both
``InterviewSessionArtifact.artifact`` and ``TraceLink`` endpoints. Subtype
rows (Requirement, StakeholderNeed, Risk, ...) carry their own row id next to
the artifact FK, so adapters normalize ``obj.artifact_id``/``dto.artifact_id``
rather than the subtype id. The registry covers all 9 in-scope types,
including GlossaryTerm: Datenmodell-Konsolidierung Phase 3 gave GlossaryTerm
a backing Artifact row (see ``persistence.artifact_backing.ensure_artifact``
and ``GlossaryService.create``), closing the gap that used to make this
adapter reject every proposal with a ValidationError.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict
from uuid import UUID

from application.adr_service import AdrService
from application.architecture_service import ArchitectureService
from application.glossary_service import GlossaryService
from application.goal_service import GoalService
from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_service import TestService
from auth_tenancy.context import AuthContext
from persistence.models import GlossaryTerm


@dataclass(frozen=True)
class CreatedArtifactRef:
    # Always the persistence.Artifact PK -- see module docstring contract.
    # Consumed by InterviewSessionArtifact.artifact and both TraceLink endpoints.
    artifact_id: UUID
    artifact_type: str
    # The user-facing subtype row id (Requirement.id, Goal version-row id, ...).
    # Distinct UUID from artifact_id. This is what formalize() reports in
    # resulting_artifact_ids (issue #736): the id requirement.get()/
    # RequirementService.get_requirement() resolve.
    entity_id: UUID


def _requirement(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = RequirementService().create_requirement(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="Requirement", entity_id=obj.id
    )


def _stakeholder_need(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    dto = StakeholderNeedService().create(ctx=ctx, workspace_id=workspace_id, **fields)
    return CreatedArtifactRef(
        artifact_id=dto.artifact_id, artifact_type="StakeholderNeed", entity_id=dto.id
    )


def _architecture_element(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # ArchitectureService.create_architecture_element takes `title`, NOT
    # `name` -- forwarded generically via **fields, so callers (build_adapter_fields
    # / a multi-mode proposal) must supply `title`; anything else raises
    # TypeError, which both formalize paths convert into a ValidationError.
    obj = ArchitectureService().create_architecture_element(
        workspace_id=workspace_id, ctx=ctx, **fields
    )
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="ArchitectureElement", entity_id=obj.id
    )


def _risk(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # probability/impact are required, no default, on RiskService.create_risk --
    # a KeyError here on a malformed proposal has NO per-item catch: it
    # propagates unchanged out of InterviewService._formalize_multi()'s
    # transaction.atomic(), rolling back the ENTIRE batch (the service layer
    # converts it to a ValidationError at the batch boundary -- Task 3).
    obj = RiskService().create_risk(
        workspace_id=workspace_id,
        title=fields["title"],
        probability=fields["probability"],
        impact=fields["impact"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "probability", "impact")},
    )
    return CreatedArtifactRef(artifact_id=obj.artifact_id, artifact_type="Risk", entity_id=obj.id)


def _test_case(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = TestService().create_test_case(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="TestCase", entity_id=obj.id
    )


def _adr(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # description is required (no default) on AdrService.create_adr.
    obj = AdrService().create_adr(
        workspace_id=workspace_id,
        title=fields["title"],
        description=fields["description"],
        ctx=ctx,
        **{k: v for k, v in fields.items() if k not in ("title", "description")},
    )
    return CreatedArtifactRef(artifact_id=obj.artifact_id, artifact_type="Adr", entity_id=obj.id)


def _issue(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    obj = IssueService().create_issue(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=obj.artifact_id, artifact_type="Issue", entity_id=obj.id
    )


def _goal(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # keyword-only args, returns a dict, and raises PermissionDeniedError if
    # Workspace.goals_enabled is False -- that exception propagates unchanged
    # through _formalize_multi()'s transaction (Task 3), rolling everything back.
    result = GoalService().create_version(workspace_id=workspace_id, ctx=ctx, **fields)
    return CreatedArtifactRef(
        artifact_id=result["artifact_id"], artifact_type="Goal", entity_id=result["id"]
    )


def _glossary_term(fields: dict, ctx: AuthContext, workspace_id) -> CreatedArtifactRef:
    # Datenmodell-Konsolidierung Phase 3 (PR #880): GlossaryTerm gained a
    # backing Artifact row, so the historical refusal no longer applies --
    # this plan's own Global Constraints/V11 assumed this was still blocked;
    # verified resolved against the current tree before this task ran.
    dto = GlossaryService().create(
        ctx=ctx,
        workspace_id=workspace_id,
        term=fields["term"],
        definition=fields.get("definition", ""),
        synonyms=fields.get("synonyms"),
        abbreviation=fields.get("abbreviation", ""),
    )
    # GlossaryTermDTO (unlike the sibling DTOs/ORM objects above) does not
    # expose artifact_id -- look it up directly. ensure_artifact() already
    # populated the FK inside GlossaryService.create()'s own transaction.
    artifact_id = GlossaryTerm.objects.values_list("artifact_id", flat=True).get(pk=dto.id)
    return CreatedArtifactRef(
        artifact_id=artifact_id, artifact_type="GlossaryTerm", entity_id=dto.id
    )


# Protocol field name -> create_X() kwarg name. The factory-default interview
# protocol (interview_protocol._default_protocol_yaml) elicits `title` and
# `rationale` for every in-scope type, but `rationale` is a kwarg on none of
# the create_X() signatures -- every service calls that field `description`.
# _formalize_single used to do this rename inline for Requirement only; it
# lives here so all 8 types share exactly one mapping.
_PROTOCOL_FIELD_ALIASES = {"rationale": "description"}


def build_adapter_fields(collected_fields: dict) -> dict:
    """Translate an interview session's ``collected_fields`` into adapter kwargs.

    Applies :data:`_PROTOCOL_FIELD_ALIASES` and forwards everything else
    untouched. An explicitly collected target name always wins over an alias
    (a protocol that declares ``description`` directly is authoritative).

    Unknown keys are deliberately **not** filtered: a workspace-custom
    protocol chooses its own field names, so a key the target ``create_X()``
    does not accept must surface as a ``TypeError`` -- which both
    ``_formalize_single`` and ``_formalize_multi`` convert into a clean
    ``ValidationError`` naming the offending field -- rather than being
    silently dropped, which would create an artifact missing the answer the
    user actually gave.

    Args:
        collected_fields: ``InterviewSession.collected_fields``.

    Returns:
        A new dict; the input is never mutated.
    """
    fields = dict(collected_fields)
    for source, target in _PROTOCOL_FIELD_ALIASES.items():
        if source not in fields:
            continue
        value = fields.pop(source)
        if target in fields:
            continue
        # `or ""` mirrors every create_X() default: description is NOT NULL,
        # so an unanswered optional field must become "" and never None.
        fields[target] = value or ""
    return fields


ARTIFACT_CREATION_ADAPTERS: Dict[str, Callable[[dict, AuthContext, Any], CreatedArtifactRef]] = {
    "Requirement": _requirement,
    "StakeholderNeed": _stakeholder_need,
    "ArchitectureElement": _architecture_element,
    "Risk": _risk,
    "TestCase": _test_case,
    "Adr": _adr,
    "Issue": _issue,
    "Goal": _goal,
    "GlossaryTerm": _glossary_term,
}
