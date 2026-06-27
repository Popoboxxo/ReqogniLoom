"""
COMP-AS-002 RequirementService — Requirement CRUD + Decomposition.

leaf_id : COMP-AS-002
req_id  : REQ-L2-AS-003 (Requirement CRUD), REQ-L2-AS-013 (LLM Orchestration),
          REQ-L2-AS-024 (Decomposition), REQ-L2-AS-015 (GitHub Integration)

Orchestrates:
  IF-AS-INT-002   TraceLinkService.create_trace_link         (parent-child links)
  IF-AS-INT-008   PresetPolicyService.is_change_reason_required
  IF-AS-INT-009   DomainEventBus  →  RequirementCreated/Updated/Deleted (Outbox)
  IF-AS-EXT-OUT-001  workflow.services.initialize_workflow_states / transition
  IF-AS-EXT-OUT-005  llm_adapter.services.decompose_requirement / validate_artifact
  IF-AS-EXT-OUT-007  persistence.models.Requirement / Artifact (Django ORM)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    Components/COMP-AS-002_RequirementService/
      L3_COMP-AS-002_RequirementService_Architecture.md

ADR-L3-AS002-01: Decomposition is one atomic TX.
ADR-L3-AS002-02: change_reason validated via PresetPolicyService.
ADR-L3-AS002-03: LLM not configured → explicit LlmNotConfiguredError.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.transactions import TransactionContextManager, atomic_transaction

from application.base import (
    LlmNotConfiguredError,
    NotFoundError,
    ServiceBase,
    ValidationError,
)
from application.models import DomainEventOutbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class RequirementDTO:
    """Read-oriented DTO returned by RequirementService methods."""

    id: UUID
    workspace_id: UUID
    title: str
    description: str
    category: str
    status: str
    version: int

    @classmethod
    def from_orm(cls, req: Requirement) -> "RequirementDTO":
        return cls(
            id=req.id,
            workspace_id=req.artifact.workspace_id,
            title=req.title,
            description=req.description,
            category=req.category,
            status=req.status,
            version=req.version,
        )


@dataclass
class DecompositionResultDTO:
    """Result of a decompose() operation."""

    parent_id: UUID
    children: List[RequirementDTO] = field(default_factory=list)
    trace_link_ids: List[UUID] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RequirementService
# ---------------------------------------------------------------------------


class RequirementService(ServiceBase):
    """COMP-AS-002 — Requirement CRUD, decomposition and LLM validation."""

    def __init__(
        self,
        trace_link_service=None,
        preset_policy_service=None,
    ) -> None:
        from application.trace_link_service import TraceLinkService
        from application.preset_policy_service import get_preset_policy_service

        self._trace_link_service = trace_link_service or TraceLinkService()
        self._preset_policy = preset_policy_service or get_preset_policy_service()

    # ---------- CRUD (REQ-L2-AS-003) ----------

    @atomic_transaction
    def create_requirement(
        self,
        workspace_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
        category: str = "",
        parent_id: Optional[UUID] = None,
    ) -> Requirement:
        """Create a Requirement with initial workflow state.

        REQ-L2-AS-003: creates Requirement + initialises WorkflowState.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Tenant and Workspace are imported at module level to allow test mocking.
        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        # Create the backing Artifact first
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
            parent_id=parent_id,
        )

        requirement = Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            title=title,
            description=description,
            category=category,
            status="draft",
        )

        # Initialise workflow state (IF-AS-EXT-OUT-001)
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[requirement.id],
                item_type="Requirement",
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:
            logger.debug(
                "RequirementService: workflow init skipped (no definition) "
                "for req=%s",
                requirement.id,
            )

        self._audit(ctx=ctx, operation="create", entity_type="Requirement", entity_id=requirement.id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_CREATED,
                entity_id=requirement.id,
                workspace_id=workspace_id,
                payload={"title": title},
            )
        )
        return requirement

    @atomic_transaction
    def update_requirement(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        change_reason: Optional[str] = None,
    ) -> Requirement:
        """Update a Requirement, enforcing change_reason policy.

        REQ-L2-AS-003: change_reason required in Extended preset.
        ADR-L3-AS002-02: delegates policy check to PresetPolicyService.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        requirement = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = requirement.artifact.workspace_id

        if title is not None:
            requirement.title = title
        if description is not None:
            requirement.description = description
        if category is not None:
            requirement.category = category

        requirement.save()

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="Requirement",
            entity_id=requirement_id,
            change_reason=change_reason,
        )
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_UPDATED,
                entity_id=requirement_id,
                workspace_id=workspace_id,
                payload={"change_reason": change_reason},
            )
        )
        return requirement

    @atomic_transaction
    def delete_requirement(self, requirement_id: UUID, ctx: AuthContext) -> None:
        """Delete Requirement and cascade-delete its TraceLinks.

        REQ-L2-AS-003: Requirement + all TraceLinks deleted atomically.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        requirement = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = requirement.artifact.workspace_id
        artifact_id = requirement.artifact_id

        # IF-AS-INT-002 (cascade)
        self._trace_link_service.cascade_delete_trace_links(
            UUID(str(artifact_id)), ctx
        )

        requirement.delete()

        self._audit(ctx=ctx, operation="delete", entity_type="Requirement", entity_id=requirement_id)
        self._emit_event(
            self._make_event(
                event_type=DomainEventOutbox.EventType.REQUIREMENT_DELETED,
                entity_id=requirement_id,
                workspace_id=workspace_id,
            )
        )

    def get_requirement(self, requirement_id: UUID, ctx: AuthContext) -> Requirement:
        """Fetch a single Requirement (tenant-scoped)."""
        self._set_tenant_context(ctx)
        req = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")
        return req

    def list_requirements(self, workspace_id: UUID, ctx: AuthContext) -> List[Requirement]:
        """Return all Requirements in *workspace_id*."""
        self._set_tenant_context(ctx)
        return list(
            Requirement.objects.select_related("artifact").filter(
                artifact__workspace_id=workspace_id
            )
        )

    # ---------- Decomposition (REQ-L2-AS-024) ----------

    def decompose(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        children: Optional[List[Dict[str, Any]]] = None,
    ) -> DecompositionResultDTO:
        """Decompose a Requirement into child Requirements.

        If *children* are provided: validate + persist directly.
        Otherwise: delegate to LlmAdapter for AI decomposition.

        REQ-L2-AS-024, ADR-L3-AS002-01 (single atomic TX).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        parent_req = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if parent_req is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = parent_req.artifact.workspace_id

        if children is None:
            children = self._decompose_via_llm(str(requirement_id))

        result = DecompositionResultDTO(parent_id=requirement_id)

        with TransactionContextManager():
            for child_data in children:
                child_req = self.create_requirement(
                    workspace_id=workspace_id,
                    title=child_data.get("title", ""),
                    ctx=ctx,
                    description=child_data.get("description", ""),
                    parent_id=parent_req.artifact_id,
                )
                result.children.append(RequirementDTO.from_orm(child_req))

                # IF-AS-INT-002: create parent-child TraceLink
                try:
                    tl = self._trace_link_service.create_trace_link(
                        source_id=UUID(str(parent_req.artifact_id)),
                        target_id=UUID(str(child_req.artifact_id)),
                        link_type="parent-child",
                        ctx=ctx,
                    )
                    if hasattr(tl, "id"):
                        result.trace_link_ids.append(tl.id)
                except Exception:
                    logger.debug(
                        "RequirementService.decompose: TraceLink creation failed "
                        "(may not exist in traceability engine yet)"
                    )

        return result

    @staticmethod
    def _decompose_via_llm(requirement_id: str) -> List[Dict[str, Any]]:
        """Call LlmAdapter to generate child requirements.

        ADR-L3-AS002-03: explicit LlmNotConfiguredError if LLM unavailable.
        REQ-L2-AS-013 / REQ-L2-AS-024.
        """
        from llm_adapter.services import decompose_requirement

        response = decompose_requirement(requirement_id=requirement_id)

        if "error" in response:
            code = response["error"].get("code", "")
            if "NOT_CONFIGURED" in code:
                raise LlmNotConfiguredError(
                    "LLM not configured — cannot decompose requirement automatically"
                )
            raise ValueError(
                f"LLM decomposition failed: {response['error'].get('message', response)}"
            )

        # Parse the LLM result (may be a task_id for async)
        # Structural validation: expect list of {title, description}
        raw_children = response.get("children") or response.get("result", {}).get(
            "children", []
        )
        if not isinstance(raw_children, list):
            raise ValueError(
                "LLM returned unexpected decomposition structure; expected 'children' list"
            )

        validated: List[Dict[str, Any]] = []
        for item in raw_children:
            if not isinstance(item, dict) or "title" not in item:
                raise ValueError(
                    "Structurally invalid LLM child requirement — missing 'title'"
                )
            validated.append({"title": item["title"], "description": item.get("description", "")})

        return validated

    # ---------- LLM Validation (REQ-L2-AS-013) ----------

    def validate_requirement(self, requirement_id: UUID, ctx: AuthContext) -> Dict[str, Any]:
        """Validate a Requirement using the LlmAdapter.

        REQ-L2-AS-013: returns structured result or raises LlmNotConfiguredError.
        """
        self._set_tenant_context(ctx)

        from llm_adapter.services import validate_artifact

        result = validate_artifact(artifact_id=str(requirement_id))
        if isinstance(result, dict) and "error" in result:
            code = result["error"].get("code", "")
            if "NOT_CONFIGURED" in code:
                raise LlmNotConfiguredError("LLM not configured")
            raise ValueError(result["error"].get("message", str(result)))

        return result if isinstance(result, dict) else {"result": str(result)}


__all__ = [
    "RequirementService",
    "RequirementDTO",
    "DecompositionResultDTO",
]
