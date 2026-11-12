"""Release cascade for architecture elements and requirements (ADR-028 A1/D10).

Decision A1: **release is a workflow transition** into the state that carries
``state_meta.freeze_on_enter``. There is no second lock; ``Allocation.status`` is
not consulted here.

Scope of this module:

* the read-only impact preview (what a release would touch),
* the element release (the element, its descendants and every requirement
  allocated to them),
* the single-requirement release (D10's special case; a requirement already
  covered by a released element is a no-op success).

Deliberately not here yet: the extended-tier content freeze (``ArtifactVersion``
snapshots) and the baseline pin. Both belong to the follow-up PR on top of the
same transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.db import transaction

from application.base import ReleaseStateError, ServiceBase, ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import (
    Allocation,
    AllocationStatus,
    ArchitectureElement,
    Requirement,
    Workspace,
)
from workflow.definition_store import WorkflowDefinitionStore, get_state_meta
from workflow.state_reader import current_states

FREEZE_META_KEY = "freeze_on_enter"

#: Above this many items a synchronous release refuses and asks for the async
#: job (not built yet). Kept as a constant so REST/MCP/UI share one number.
MAX_SYNC_RELEASE_ITEMS = 5000

_ELEMENT_TYPE = "ArchitectureElement"
_REQUIREMENT_TYPE = "Requirement"
_RELEASE_ROLES = frozenset({"admin", "approver"})


@dataclass(frozen=True)
class ReleaseImpact:
    """What one element release would touch (read-only)."""

    element_id: str
    release_state: str | None
    allowed_source_states: tuple[str, ...]
    descendant_elements: int
    requirements_total: int
    requirements_releasable: int
    requirements_by_state: dict[str, int] = field(default_factory=dict)
    content_freeze: bool = False
    async_required: bool = False
    conflicts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "release_state": self.release_state,
            "allowed_source_states": list(self.allowed_source_states),
            "descendant_elements": self.descendant_elements,
            "requirements_total": self.requirements_total,
            "requirements_releasable": self.requirements_releasable,
            "requirements_by_state": dict(self.requirements_by_state),
            "content_freeze": self.content_freeze,
            "async_required": self.async_required,
            "conflicts": self.conflicts,
        }


class ReleaseService(ServiceBase):
    """Workflow-driven release of elements and requirements (ADR-028)."""

    # ------------------------------------------------------------------
    # Read-only impact preview
    # ------------------------------------------------------------------

    def impact(self, *, element_id: UUID, ctx: AuthContext) -> ReleaseImpact:
        """Return what releasing *element_id* would touch. Changes nothing."""
        self._set_tenant_context(ctx)
        workspace, element = self._load_element(element_id, ctx)

        workflow_json = self._workflow_json(workspace.id, _ELEMENT_TYPE)
        release_state = self._release_state(workflow_json)
        allowed_sources = self._allowed_sources(workflow_json, release_state)

        scope = self._element_scope(element, workspace.id)
        scope_artifacts = [row.artifact_id for row in scope]
        requirement_artifacts = self._allocated_requirement_artifacts(scope_artifacts)

        # Workflow states are keyed by the Requirement row id, not by the
        # backing Artifact id.
        requirement_ids = self._requirement_ids(requirement_artifacts)
        states = (
            current_states(
                _REQUIREMENT_TYPE,
                list(requirement_ids.values()),
                tenant_id=ctx.tenant_id,
            )
            if requirement_ids
            else {}
        )
        by_state: dict[str, int] = {}
        for state in states.values():
            by_state[state] = by_state.get(state, 0) + 1

        releasable_sources = self._allowed_sources(
            self._workflow_json(workspace.id, _REQUIREMENT_TYPE),
            self._release_state(self._workflow_json(workspace.id, _REQUIREMENT_TYPE)),
        )
        releasable = sum(1 for state in states.values() if state in releasable_sources)
        total = len(requirement_artifacts)
        conflicts = self._conflict_count(workspace.id, requirement_artifacts)

        return ReleaseImpact(
            element_id=str(element.id),
            release_state=release_state,
            allowed_source_states=tuple(sorted(allowed_sources)),
            descendant_elements=max(0, len(scope) - 1),
            requirements_total=total,
            requirements_releasable=releasable,
            requirements_by_state=dict(sorted(by_state.items())),
            content_freeze=self._is_extended(workspace),
            async_required=total > MAX_SYNC_RELEASE_ITEMS,
            conflicts=conflicts,
        )

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------

    def release_element(
        self, *, element_id: UUID, ctx: AuthContext, change_reason: str
    ) -> dict[str, Any]:
        """Release one element, its descendants and their allocated requirements."""
        self._assert_release_role(ctx)
        self._set_tenant_context(ctx)
        workspace, element = self._load_element(element_id, ctx)

        element_json = self._workflow_json(workspace.id, _ELEMENT_TYPE)
        release_state = self._require_release_state(element_json, "ArchitectureElement")
        element_sources = self._allowed_sources(element_json, release_state)

        requirement_json = self._workflow_json(workspace.id, _REQUIREMENT_TYPE)
        requirement_state = self._release_state(requirement_json)
        requirement_sources = self._allowed_sources(requirement_json, requirement_state)

        scope = self._element_scope(element, workspace.id)
        requirement_artifacts = self._allocated_requirement_artifacts(
            [row.artifact_id for row in scope]
        )
        total_items = len(scope) + len(requirement_artifacts)
        if total_items > MAX_SYNC_RELEASE_ITEMS:
            raise ValidationError(
                f"Releasing {total_items} items exceeds the synchronous limit of "
                f"{MAX_SYNC_RELEASE_ITEMS}; the async release job is not available "
                "in this build."
            )

        # Validate everything BEFORE the first transition: a half-released tree
        # is worse than a rejected request.
        element_states = current_states(
            _ELEMENT_TYPE, [row.id for row in scope], tenant_id=ctx.tenant_id
        )
        for row in scope:
            state = element_states.get(str(row.id))
            if state == release_state:
                continue
            if state not in element_sources:
                raise ReleaseStateError(
                    f"ArchitectureElement {row.id} is in state {state!r}; release "
                    f"is only allowed from {sorted(element_sources)}."
                )

        requirement_ids = self._requirement_ids(requirement_artifacts)
        requirement_states = (
            current_states(
                _REQUIREMENT_TYPE, list(requirement_ids.values()), tenant_id=ctx.tenant_id
            )
            if requirement_ids
            else {}
        )
        if requirement_state is not None:
            for artifact_id, requirement_id in requirement_ids.items():
                state = requirement_states.get(str(requirement_id))
                if state in (None, requirement_state):
                    continue
                if state not in requirement_sources:
                    raise ReleaseStateError(
                        f"Requirement {requirement_id} is in state {state!r}; release "
                        f"is only allowed from {sorted(requirement_sources)}."
                    )

        released_elements = 0
        released_requirements = 0
        with transaction.atomic():
            for row in scope:
                if element_states.get(str(row.id)) == release_state:
                    continue
                self._transition(
                    item_id=row.id,
                    item_type=_ELEMENT_TYPE,
                    target=release_state,
                    workspace_id=workspace.id,
                    ctx=ctx,
                    change_reason=change_reason,
                )
                released_elements += 1

            if requirement_state is not None:
                for requirement_id in requirement_ids.values():
                    if requirement_states.get(str(requirement_id)) == requirement_state:
                        continue
                    self._transition(
                        item_id=requirement_id,
                        item_type=_REQUIREMENT_TYPE,
                        target=requirement_state,
                        workspace_id=workspace.id,
                        ctx=ctx,
                        change_reason=change_reason,
                    )
                    released_requirements += 1

        return {
            "element_id": str(element.id),
            "release_state": release_state,
            "elements_released": released_elements,
            "requirements_released": released_requirements,
            "content_freeze": self._is_extended(workspace),
        }

    def release_requirement(
        self, *, requirement_id: UUID, ctx: AuthContext, change_reason: str
    ) -> dict[str, Any]:
        """Release one requirement (D10 special case)."""
        self._assert_release_role(ctx)
        self._set_tenant_context(ctx)

        requirement = (
            Requirement.objects.select_related("artifact")
            .filter(id=requirement_id)
            .first()
        )
        if requirement is None:
            raise ValidationError(f"Requirement {requirement_id} not found")
        workspace = Workspace.objects.filter(id=requirement.workspace_id).first()
        if workspace is None:
            raise ValidationError(f"Workspace of requirement {requirement_id} not found")

        workflow_json = self._workflow_json(workspace.id, _REQUIREMENT_TYPE)
        release_state = self._require_release_state(workflow_json, "Requirement")
        allowed = self._allowed_sources(workflow_json, release_state)

        state = current_states(
            _REQUIREMENT_TYPE, [requirement.id], tenant_id=ctx.tenant_id
        ).get(str(requirement.id))
        if state == release_state:
            return {
                "requirement_id": str(requirement.id),
                "release_state": release_state,
                "released": False,
                "reason": "already released",
            }
        if state not in allowed:
            raise ReleaseStateError(
                f"Requirement {requirement.id} is in state {state!r}; release is "
                f"only allowed from {sorted(allowed)}."
            )

        self._transition(
            item_id=requirement.id,
            item_type=_REQUIREMENT_TYPE,
            target=release_state,
            workspace_id=workspace.id,
            ctx=ctx,
            change_reason=change_reason,
        )
        return {
            "requirement_id": str(requirement.id),
            "release_state": release_state,
            "released": True,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition(
        self,
        *,
        item_id: UUID,
        item_type: str,
        target: str,
        workspace_id: UUID,
        ctx: AuthContext,
        change_reason: str,
    ) -> None:
        from workflow.services import transition

        transition(
            item_id=item_id,
            target_state=target,
            change_reason=change_reason,
            ctx=ctx,
            item_type=item_type,
            workspace_id=workspace_id,
        )

    @staticmethod
    def _workflow_json(workspace_id: UUID, item_type: str) -> dict[str, Any]:
        return WorkflowDefinitionStore().get_workflow_json(workspace_id, item_type) or {}

    @staticmethod
    def _release_state(workflow_json: dict[str, Any]) -> str | None:
        for state in workflow_json.get("states") or []:
            if (get_state_meta(workflow_json, state) or {}).get(FREEZE_META_KEY):
                return state
        return None

    @classmethod
    def _require_release_state(cls, workflow_json: dict[str, Any], item_type: str) -> str:
        state = cls._release_state(workflow_json)
        if state is None:
            raise ValidationError(
                f"The workspace defines no release state (state_meta.freeze_on_enter) "
                f"for {item_type}."
            )
        return state

    @staticmethod
    def _allowed_sources(workflow_json: dict[str, Any], target: str | None) -> set[str]:
        if target is None:
            return set()
        return {
            t.get("from_state")
            for t in workflow_json.get("transitions") or []
            if t.get("to_state") == target and t.get("from_state")
        }

    def _load_element(
        self, element_id: UUID, ctx: AuthContext
    ) -> tuple[Workspace, ArchitectureElement]:
        element = ArchitectureElement.objects.filter(id=element_id).first()
        if element is None:
            raise ValidationError(f"ArchitectureElement {element_id} not found")
        workspace = Workspace.objects.filter(id=element.workspace_id).first()
        if workspace is None:
            raise ValidationError(f"Workspace of element {element_id} not found")
        return workspace, element

    @staticmethod
    def _element_scope(root: ArchitectureElement, workspace_id: UUID) -> list[ArchitectureElement]:
        """Return *root* and every descendant element (workspace-scoped)."""
        by_parent: dict[UUID | None, list[ArchitectureElement]] = {}
        rows = list(
            ArchitectureElement.objects.filter(workspace_id=workspace_id).only(
                "id", "parent_id"
            )
        )
        for row in rows:
            by_parent.setdefault(row.parent_id, []).append(row)
        ordered: list[ArchitectureElement] = []
        stack = [root]
        while stack:
            current = stack.pop()
            ordered.append(current)
            stack.extend(by_parent.get(current.id, []))
        return ordered

    @staticmethod
    def _allocated_requirement_artifacts(element_artifacts: list[UUID]) -> set[UUID]:
        if not element_artifacts:
            return set()
        rows = Allocation.objects.filter(
            element_artifact_id__in=element_artifacts,
            status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
        ).values_list("requirement_artifact_id", flat=True)
        return {row for row in rows}

    @staticmethod
    def _requirement_ids(artifact_ids: set[UUID]) -> dict[UUID, UUID]:
        if not artifact_ids:
            return {}
        rows = Requirement.unscoped.filter(
            artifact_id__in=artifact_ids
        ).values_list("artifact_id", "id")
        return {artifact_id: req_id for artifact_id, req_id in rows}

    @staticmethod
    def _conflict_count(workspace_id: UUID, artifact_ids: set[UUID]) -> int:
        if not artifact_ids:
            return 0
        from django.db.models import Count

        rows = (
            Allocation.objects.filter(
                workspace_id=workspace_id,
                requirement_artifact_id__in=artifact_ids,
                status__in=[AllocationStatus.DRAFT, AllocationStatus.RELEASED],
            )
            .values("requirement_artifact_id")
            .annotate(active=Count("id"))
            .filter(active__gt=1)
        )
        return rows.count()

    @staticmethod
    def _is_extended(workspace: Workspace) -> bool:
        preset = workspace.preset or {}
        if isinstance(preset, dict):
            return preset.get("name") == "extended"
        return preset == "extended"

    @staticmethod
    def _assert_release_role(ctx: AuthContext) -> None:
        if not (_RELEASE_ROLES & set(ctx.active_roles)):
            raise ValidationError(
                "Releasing requires the approver or admin role."
            )
