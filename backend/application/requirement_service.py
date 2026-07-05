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
from django.db.models import F
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

# Sentinel to distinguish "not provided" from "set to None" in update calls.
_UNSET = object()

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
        type: str = "SyReq",
        moscow_priority: Optional[str] = None,
        complexity_fibonacci: Optional[int] = None,
        verification_method: Optional[str] = None,
        uid: Optional[str] = None,
    ) -> Requirement:
        """Create a Requirement with initial workflow state.

        REQ-L2-AS-003: creates Requirement + initialises WorkflowState.
        REQ-L3-RF003-005: Accepts SE mask fields (type, moscow_priority,
        complexity_fibonacci, verification_method).
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
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
            type=type,
            complexity_fibonacci=complexity_fibonacci,
            verification_method=verification_method,
            uid=uid,
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

    def derive_requirement(
        self,
        parent_requirement_id: UUID,
        architecture_element_id: UUID,
        title: str,
        ctx: AuthContext,
        description: str = "",
    ) -> DecompositionResultDTO:
        """Derive a single child Requirement from *parent_requirement_id*, allocated
        to *architecture_element_id* (decomposition onto the next system level).

        Thin single-child convenience wrapper around :meth:`decompose` — reuses its
        atomic parent-child TraceLink + allocation logic (REQ-L1-043) so the "Ableiten"
        action (UI, REST, MCP) stays consistent with AI-driven decomposition. The
        architecture target is mandatory here: derivation must always state which
        system element the derived requirement belongs to.
        """
        return self.decompose(
            requirement_id=parent_requirement_id,
            ctx=ctx,
            children=[{"title": title, "description": description}],
            target_architecture_elements=[architecture_element_id],
        )

    @atomic_transaction
    def update_requirement(
        self,
        requirement_id: UUID,
        ctx: AuthContext,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        change_reason: Optional[str] = None,
        type: Optional[str] = None,
        complexity_fibonacci: object = _UNSET,
        verification_method: object = _UNSET,
        uid: object = _UNSET,
        suspect: Optional[bool] = None,
    ) -> Requirement:
        """Update a Requirement, enforcing change_reason policy.

        REQ-L2-AS-003: change_reason required in Extended preset.
        ADR-L3-AS002-02: delegates policy check to PresetPolicyService.
        REQ-L3-RF003-005: Accepts SE mask fields (type, moscow_priority,
        complexity_fibonacci, verification_method).
        REQ-L2-RF-025 AC3: Accepts uid for stable identification.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        requirement = Requirement.objects.select_related("artifact").filter(
            id=requirement_id
        ).first()
        if requirement is None:
            raise NotFoundError(f"Requirement {requirement_id} not found")

        workspace_id = requirement.artifact.workspace_id

        # Enforce change_reason policy (ADR-L3-AS002-02)
        if self._preset_policy.is_change_reason_required(str(workspace_id)):
            if not change_reason:
                raise ValidationError("change_reason required by workspace preset policy")

        if title is not None:
            requirement.title = title
        if description is not None:
            requirement.description = description
        if category is not None:
            requirement.category = category
        if status is not None:
            requirement.status = status
        if type is not None:
            requirement.type = type
        if complexity_fibonacci is not _UNSET:
            requirement.complexity_fibonacci = complexity_fibonacci
        if verification_method is not _UNSET:
            requirement.verification_method = verification_method
        if uid is not _UNSET:
            requirement.uid = uid
        
        # SN-30: If title, description, or status changed, we will propagate suspect
        changed_critical = any(x is not None for x in [title, description, status])

        if hasattr(requirement, "suspect"):
            if suspect is not None:
                requirement.suspect = suspect

        requirement.save()
        # Atomic version increment (REQ-L3-PL001-002): requirement_service was
        # missing any version bump at all — the baseline diff engine compares
        # stored version numbers, so without this increment every update appears
        # as version=1 forever, producing incorrect/empty diffs.
        Requirement.objects.filter(id=requirement.id).update(version=F("version") + 1)
        requirement.refresh_from_db(fields=["version"])

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

        if changed_critical:
            try:
                self._trace_link_service.propagate_suspect_status(requirement.artifact_id, ctx)
            except Exception as e:
                logger.error(f"Error propagating suspect status: {e}")

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
        target_architecture_elements: Optional[List[UUID]] = None,
    ) -> DecompositionResultDTO:
        """Decompose a Requirement into child Requirements.

        If *children* are provided: validate + persist directly.
        Otherwise: delegate to LlmAdapter for AI decomposition.

        REQ-L2-AS-024: decomposition logic
        REQ-L1-043: optional allocation of children to ArchitectureElements
        ADR-L3-AS002-01 (single atomic TX).

        Args:
            requirement_id: UUID of parent requirement to decompose.
            ctx: AuthContext for tenant scoping and audit.
            children: Optional list of child requirement data dicts.
                     If None, LLM will generate decomposition.
            target_architecture_elements: Optional list of ArchitectureElement UUIDs
                                         to allocate children to (in order).
                                         If provided, must match children count.

        Returns:
            DecompositionResultDTO containing created children and trace links.

        Raises:
            NotFoundError: Parent requirement or ArchitectureElement not found.
            ValidationError: Mismatch between children and target elements count,
                            or empty target_architecture_elements list.
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

        # REQ-L1-043: Validate target_architecture_elements if provided
        if target_architecture_elements is not None:
            if len(target_architecture_elements) == 0:
                raise ValidationError(
                    "target_architecture_elements cannot be empty when provided"
                )
            if len(target_architecture_elements) != len(children):
                raise ValidationError(
                    f"Number of target_architecture_elements ({len(target_architecture_elements)}) "
                    f"must match number of children ({len(children)})"
                )

            # Validate existence and workspace membership of all ArchitectureElements
            from persistence.models import ArchitectureElement
            for arch_el_id in target_architecture_elements:
                arch_el = ArchitectureElement.objects.filter(id=arch_el_id).first()
                if arch_el is None:
                    raise NotFoundError(f"ArchitectureElement {arch_el_id} not found")
                if arch_el.artifact.workspace_id != workspace_id:
                    raise ValidationError(
                        f"ArchitectureElement {arch_el_id} is not in workspace {workspace_id}"
                    )

        # Resolve configured decomposition link type from workspace preset
        workspace = Workspace.objects.filter(id=workspace_id).first()
        decomposition_link_type = getattr(workspace, "decomposition_link_type", "parent-child")

        result = DecompositionResultDTO(parent_id=requirement_id)

        with TransactionContextManager():
            for idx, child_data in enumerate(children):
                child_req = self.create_requirement(
                    workspace_id=workspace_id,
                    title=child_data.get("title", ""),
                    ctx=ctx,
                    description=child_data.get("description", ""),
                    parent_id=parent_req.artifact_id,
                )
                result.children.append(RequirementDTO.from_orm(child_req))

                # IF-AS-INT-002: create TraceLink using configured type
                try:
                    tl = self._trace_link_service.create_trace_link(
                        source_id=UUID(str(parent_req.artifact_id)),
                        target_id=UUID(str(child_req.artifact_id)),
                        link_type=decomposition_link_type,
                        ctx=ctx,
                    )
                    if hasattr(tl, "id"):
                        result.trace_link_ids.append(tl.id)
                except Exception:
                    logger.debug(
                        "RequirementService.decompose: TraceLink creation failed "
                        "(may not exist in traceability engine yet)"
                    )

                # REQ-L1-043: Allocation to ArchitectureElements. Not caught: a
                # caller that explicitly passes target_architecture_elements
                # expects the allocation to actually happen (REQ-L1-042), so
                # NotFoundError/ValidationError must propagate rather than be
                # silently swallowed — otherwise "derive" could create the
                # child requirement while its mandatory allocation silently
                # fails.
                if target_architecture_elements is not None:
                    target_arch_id = target_architecture_elements[idx]
                    alloc_link = self._trace_link_service.allocate(
                        requirement_id=child_req.id,
                        architecture_element_id=target_arch_id,
                        ctx=ctx,
                    )
                    if hasattr(alloc_link, "id"):
                        result.trace_link_ids.append(alloc_link.id)

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
