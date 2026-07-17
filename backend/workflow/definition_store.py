"""
COMP-WE-001 WorkflowDefinitionStore — CRUD, Preset Defaults, Orphaned-State,
Downgrade-Blockade, signature_gate management.

leaf_id : COMP-WE-001
req_id  : REQ-L2-WE-002, REQ-L2-WE-004, REQ-L2-WE-007
          REQ-L3-WE001-001, REQ-L3-WE001-002, REQ-L3-WE001-003, REQ-L3-WE001-004

IF-WE-EXT-IN-003 : PresetConfigEngine (get_preset / get_workflow_configurability)
IF-WE-EXT-OUT-001: PersistenceLayer (Django ORM on WorkflowEngineDefinition,
                   WorkflowItemState)
IF-WE-INT-001    : outgoing to TransitionValidator — WorkflowDefinition payload
IF-WE-INT-003    : incoming from StateLifecycleManager — StateQuery for initial_state

Architecture:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/
    COMP-WE-001_WorkflowDefinitionStore/
    L3_COMP-WE-001_WorkflowDefinitionStore_Architecture.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from presets.services import get_workflow_configurability

from .models import WorkflowEngineDefinition, WorkflowItemState


# ---------------------------------------------------------------------------
# DTOs (IF-WE-INT-001)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionDefinitionDTO:
    """Single transition in a workflow (IF-WE-INT-001).

    Attributes:
        from_state: Source state name.
        to_state:   Target state name.
        allowed_roles: Role names that may execute this transition.
        requires_change_reason: When True the caller must supply a non-empty
            change_reason string.
        signature_gate: When True a credential (password or TOTP) is required
            before the transition is accepted (REQ-L2-WE-009).
    """

    from_state: str
    to_state: str
    allowed_roles: tuple[str, ...]
    requires_change_reason: bool = False
    signature_gate: bool = False


@dataclass(frozen=True)
class WorkflowDefinitionDTO:
    """Full workflow definition delivered via IF-WE-INT-001 to TransitionValidator.

    Attributes:
        states: All valid state names.
        transitions: Ordered list of transition definitions.
        workspace_id: Owning workspace.
        item_type: Entity type this definition applies to.
        preset: Active preset tier.
        is_custom: True when the definition was user-supplied.
    """

    states: tuple[str, ...]
    transitions: tuple[TransitionDefinitionDTO, ...]
    workspace_id: UUID
    item_type: str
    preset: str
    is_custom: bool = False

    def get_transition(
        self, from_state: str, to_state: str
    ) -> TransitionDefinitionDTO | None:
        """Return the matching transition or None if not defined."""
        for t in self.transitions:
            if t.from_state == from_state and t.to_state == to_state:
                return t
        return None

    @property
    def initial_state(self) -> str:
        """Return the first state in the definition (conventional initial state)."""
        return self.states[0] if self.states else "draft"


# ---------------------------------------------------------------------------
# Preset default schemas (ADR-L3-WE001-01, REQ-L3-WE001-001)
# ---------------------------------------------------------------------------


def _minimal_transitions() -> list[dict[str, Any]]:
    return [
        {
            "from_state": "draft",
            "to_state": "done",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        }
    ]


def _standard_transitions() -> list[dict[str, Any]]:
    return [
        {
            "from_state": "draft",
            "to_state": "approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "approved",
            "to_state": "deprecated",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "draft",
            "to_state": "deprecated",
            "allowed_roles": ["admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
    ]


def _extended_transitions() -> list[dict[str, Any]]:
    return [
        {
            "from_state": "draft",
            "to_state": "in_review",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "approved",
            "to_state": "deprecated",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "draft",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        # REQ-L2-WE-011: V-model right-hand side — after approval, a
        # requirement is implemented and then verified. RBAC only defines
        # admin/editor/viewer/approver (auth_tenancy/models.py); "developer"
        # and "reviewer/verifier" are not distinct roles in this system, so
        # "editor" (implementation work) and "approver" (review/verification,
        # already used for the in_review->approved gate) are the closest
        # existing-role mapping.
        {
            "from_state": "approved",
            "to_state": "implemented",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "implemented",
            "to_state": "verified",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
    ]


# ---------------------------------------------------------------------------
# REQ-165/REQ-166: per-entity-type default workflows.
#
# Each preset below drives ONE entity type. The state name strings are
# byte-identical to that entity's ``Status.choices`` VALUE strings, because
# StateLifecycleManager._sync_status_mirror writes ``current_state`` verbatim
# into the entity's ``status`` column (a denormalized read-only mirror). The
# first state in each ``states`` list is the definition's initial_state and MUST
# equal the model field default so a freshly created row and its WorkflowItemState
# agree. Role names use the existing RBAC set (admin/editor/viewer/approver from
# auth_tenancy/models.py). ChangeRequest intentionally has no entry here — it
# reuses the existing ``ccb_approval`` preset.
# ---------------------------------------------------------------------------


def _need_transitions() -> list[dict[str, Any]]:
    # StakeholderNeed.status has no Status enum (free-text CharField, default
    # "draft"); there is no "rejected" state, so review rejection routes back to
    # "draft" instead.
    return [
        {
            "from_state": "draft",
            "to_state": "in_review",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "draft",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "approved",
            "to_state": "deprecated",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
    ]


def _architecture_transitions() -> list[dict[str, Any]]:
    # REQ-171: ArchitectureElement has no denormalized ``status`` mirror column
    # (it is not wired into _STATUS_MIRROR_MODELS, so the mirror write is a
    # silent no-op); the workflow state lives solely in WorkflowItemState. State
    # names use a lowercase lifecycle (draft -> in_review -> approved ->
    # deprecated), mirroring the StakeholderNeed lifecycle since an architecture
    # element follows the same design/review/approve/retire path. "draft" is the
    # initial_state; review rejection routes back to "draft" (no dedicated
    # "rejected" state).
    return [
        {
            "from_state": "draft",
            "to_state": "in_review",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "in_review",
            "to_state": "draft",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "approved",
            "to_state": "deprecated",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
    ]


def _adr_transitions() -> list[dict[str, Any]]:
    # State values match application.models.Adr.Status.
    return [
        {
            "from_state": "Draft",
            "to_state": "In Review",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "In Review",
            "to_state": "Approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "In Review",
            "to_state": "Rejected",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "In Review",
            "to_state": "Draft",
            "allowed_roles": ["editor", "approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Approved",
            "to_state": "Superseded",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
    ]


def _risk_transitions() -> list[dict[str, Any]]:
    # State values match application.models.Risk.RiskStatus.
    return [
        {
            "from_state": "Identified",
            "to_state": "Monitored",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Identified",
            "to_state": "Accepted",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "Monitored",
            "to_state": "Mitigated",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Monitored",
            "to_state": "Accepted",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "Mitigated",
            "to_state": "Closed",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Accepted",
            "to_state": "Closed",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
    ]


def _issue_transitions() -> list[dict[str, Any]]:
    # State values match application.models.Issue.IssueStatus.
    return [
        {
            "from_state": "Open",
            "to_state": "In Progress",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "In Progress",
            "to_state": "Resolved",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "In Progress",
            "to_state": "Wontfix",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "Resolved",
            "to_state": "Closed",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            # Reopen path.
            "from_state": "Resolved",
            "to_state": "In Progress",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Open",
            "to_state": "Wontfix",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
    ]


def _testcase_transitions() -> list[dict[str, Any]]:
    # State values match persistence.models.TestCase.Status.
    return [
        {
            "from_state": "Draft",
            "to_state": "Ready",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Ready",
            "to_state": "Approved",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": True,
            "signature_gate": False,
        },
        {
            "from_state": "Ready",
            "to_state": "Draft",
            "allowed_roles": ["editor", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
        {
            "from_state": "Approved",
            "to_state": "Deprecated",
            "allowed_roles": ["approver", "admin"],
            "requires_change_reason": False,
            "signature_gate": False,
        },
    ]


PRESET_SCHEMAS: dict[str, dict[str, Any]] = {
    "minimal": {
        "states": ["draft", "done"],
        "transitions": _minimal_transitions(),
    },
    "standard": {
        "states": ["draft", "approved", "deprecated"],
        "transitions": _standard_transitions(),
    },
    "extended": {
        # REQ-L2-WE-011: "implemented"/"verified" added after "approved" to
        # express the V-model right-hand side. "draft" stays first (used as
        # WorkflowDefinitionDTO.initial_state) and "deprecated" stays last;
        # existing items already in approved/deprecated are unaffected since
        # both states remain valid members of this preset (backward-compatible).
        "states": ["draft", "in_review", "approved", "implemented", "verified", "deprecated"],
        "transitions": _extended_transitions(),
    },
    "ccb_approval": {
        # REQ-157: CCB (Configuration Control Board) approval workflow for
        # Change Requests. Reuses the WorkflowEngine state machine with role
        # checks and change_reason enforcement on critical transitions.
        #
        # States: draft → submitted → under_review → approved|rejected → implemented
        # rejected allows rework back to draft.
        #
        # Role mapping uses existing RBAC roles (admin/editor/viewer/approver
        # from auth_tenancy/models.py). "requestor" maps to "editor" in the
        # existing role set since a dedicated requestor role does not exist.
        "states": ["draft", "submitted", "under_review", "approved", "rejected", "implemented"],
        "transitions": [
            {
                # Requestor submits the CR for CCB review.
                "from_state": "draft",
                "to_state": "submitted",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            },
            {
                # CCB reviewer takes the CR into active review.
                "from_state": "submitted",
                "to_state": "under_review",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
            {
                # CCB approves the change. change_reason documents the rationale.
                "from_state": "under_review",
                "to_state": "approved",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            },
            {
                # CCB rejects the change. change_reason mandatory (REQ-157).
                "from_state": "under_review",
                "to_state": "rejected",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            },
            {
                # Implementation team marks the approved CR as implemented.
                "from_state": "approved",
                "to_state": "implemented",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
            {
                # Requestor reworks a rejected CR and resubmits for CCB.
                "from_state": "rejected",
                "to_state": "draft",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
        ],
    },
    # REQ-165/REQ-166: per-entity-type defaults (see builders above).
    "need_default": {
        "states": ["draft", "in_review", "approved", "deprecated"],
        "transitions": _need_transitions(),
    },
    "adr_default": {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": _adr_transitions(),
    },
    "risk_default": {
        "states": ["Identified", "Monitored", "Mitigated", "Accepted", "Closed"],
        "transitions": _risk_transitions(),
    },
    "issue_default": {
        "states": ["Open", "In Progress", "Resolved", "Closed", "Wontfix"],
        "transitions": _issue_transitions(),
    },
    "testcase_default": {
        "states": ["Draft", "Ready", "Approved", "Deprecated"],
        "transitions": _testcase_transitions(),
    },
    # REQ-171: ArchitectureElement default workflow (no status mirror; state
    # lives in WorkflowItemState only). "draft" is the initial_state.
    "architecture_default": {
        "states": ["draft", "in_review", "approved", "deprecated"],
        "transitions": _architecture_transitions(),
    },
}


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class WorkflowDefinitionError(Exception):
    """Raised when a definition operation violates a constraint."""


class OrphanedStateError(WorkflowDefinitionError):
    """Raised when items exist in states that are being removed (REQ-L2-WE-004)."""

    def __init__(
        self, orphaned_state: str, count: int, item_ids: list[str]
    ) -> None:
        self.orphaned_state = orphaned_state
        self.count = count
        self.item_ids = item_ids
        msg = (
            f"Workflow change blocked: {count} items in orphaned state "
            f"'{orphaned_state}'"
        )
        super().__init__(msg)


class PresetDowngradeBlockedError(WorkflowDefinitionError):
    """Raised when a preset downgrade cannot proceed (REQ-L2-WE-007)."""

    def __init__(self, incompatible_states: list[str], count: int) -> None:
        self.incompatible_states = incompatible_states
        self.count = count
        msg = (
            f"Preset downgrade blocked: {count} items in states "
            f"{incompatible_states} not valid in target preset"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Helper: build DTO from ORM record
# ---------------------------------------------------------------------------


def _dto_from_orm(record: WorkflowEngineDefinition) -> WorkflowDefinitionDTO:
    """Convert an ORM record to a WorkflowDefinitionDTO (IF-WE-INT-001)."""
    wf = record.workflow_json
    transitions = tuple(
        TransitionDefinitionDTO(
            from_state=t["from_state"],
            to_state=t["to_state"],
            allowed_roles=tuple(t.get("allowed_roles", [])),
            requires_change_reason=bool(t.get("requires_change_reason", False)),
            signature_gate=bool(t.get("signature_gate", False)),
        )
        for t in wf.get("transitions", [])
    )
    return WorkflowDefinitionDTO(
        states=tuple(wf.get("states", [])),
        transitions=transitions,
        workspace_id=record.workspace_id,
        item_type=record.item_type,
        preset=record.preset,
        is_custom=record.is_custom,
    )


# ---------------------------------------------------------------------------
# COMP-WE-001  WorkflowDefinitionStore
# ---------------------------------------------------------------------------


class WorkflowDefinitionStore:
    """CRUD + preset defaults + migration-safety for WorkflowEngineDefinitions.

    COMP-WE-001 (REQ-L2-WE-002, REQ-L2-WE-004, REQ-L2-WE-007).

    All write operations are tenant-scoped: the caller must have set the
    tenant context (TenantContext.set_tenant) before invoking any method.
    """

    # -- Read (IF-WE-INT-001, IF-WE-INT-003) ---------------------------------

    def get_definition(
        self, workspace_id: UUID | str, item_type: str
    ) -> WorkflowDefinitionDTO:
        """Return the active WorkflowDefinitionDTO for a workspace / item-type.

        IF-WE-INT-001 — data returned to TransitionValidator.
        IF-WE-INT-003 — also used by StateLifecycleManager for initial_state.

        Raises:
            WorkflowDefinitionError: No definition found for the workspace/type.
        """
        record = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if record is None:
            raise WorkflowDefinitionError(
                f"No WorkflowDefinition found for workspace={workspace_id}, "
                f"item_type={item_type}"
            )
        return _dto_from_orm(record)

    # -- Create default (REQ-L3-WE001-001) ------------------------------------

    def create_workspace_default_workflow(
        self,
        workspace_id: UUID | str,
        preset: str,
        item_type: str = "Requirement",
        tenant_id: UUID | str | None = None,
    ) -> WorkflowDefinitionDTO:
        """Create the preset-default WorkflowDefinition for a new workspace.

        For Minimal preset the created record is locked (is_custom=False and
        preset="minimal"); update attempts are rejected by
        validate_and_persist_custom.

        Args:
            workspace_id: Target workspace UUID.
            preset: "minimal" | "standard" | "extended".
            item_type: Entity type (default "Requirement").
            tenant_id: Explicit tenant UUID; used only when TenantContext is
                not yet active (bootstrap scenarios).

        Returns:
            WorkflowDefinitionDTO for the created definition.

        Raises:
            WorkflowDefinitionError: Unknown preset.
        """
        if preset not in PRESET_SCHEMAS:
            raise WorkflowDefinitionError(f"Unknown preset: {preset!r}")

        schema = PRESET_SCHEMAS[preset]

        # Build extra kwargs when tenant_id is explicitly supplied (bootstrap).
        extra: dict[str, Any] = {}
        if tenant_id is not None:
            extra["tenant_id"] = str(tenant_id)

        record, _ = WorkflowEngineDefinition.objects.get_or_create(
            workspace_id=str(workspace_id),
            item_type=item_type,
            defaults={
                "preset": preset,
                "workflow_json": schema,
                "is_custom": False,
                **extra,
            },
        )
        return _dto_from_orm(record)

    # -- Custom definition (REQ-L3-WE001-002) ---------------------------------

    def validate_and_persist_custom(
        self,
        workspace_id: UUID | str,
        item_type: str,
        states: list[str],
        transitions: list[dict[str, Any]],
    ) -> WorkflowDefinitionDTO:
        """Validate and persist a custom WorkflowDefinition (Extended only).

        Validation rules (fail-fast):
          1. Preset must be "extended" or "full" (workflow_configurability check).
          2. At least 2 states.
          3. At least 1 transition.
          4. Every transition references only declared states.

        Orphaned-state check is run first so existing items are not stranded.

        Args:
            workspace_id: Target workspace UUID.
            item_type: Entity type.
            states: New state list.
            transitions: New transition list (dicts matching TransitionDefinitionDTO).

        Returns:
            Persisted WorkflowDefinitionDTO.

        Raises:
            WorkflowDefinitionError: Validation failure or preset mismatch.
            OrphanedStateError: Items would be stranded by the new definition.
        """
        configurability = get_workflow_configurability(str(workspace_id))
        if configurability == "fixed":
            raise WorkflowDefinitionError(
                "Workflow not configurable in minimal preset"
            )
        if configurability == "partial":
            raise WorkflowDefinitionError(
                "Custom workflows only allowed in extended preset"
            )

        # Structural validation
        if len(states) < 2:
            raise WorkflowDefinitionError(
                "Custom workflow requires at least 2 states"
            )
        if len(transitions) < 1:
            raise WorkflowDefinitionError(
                "Custom workflow requires at least 1 transition"
            )
        state_set = set(states)
        for t in transitions:
            if t.get("from_state") not in state_set:
                raise WorkflowDefinitionError(
                    f"Invalid transition: unknown state '{t.get('from_state')}'"
                )
            if t.get("to_state") not in state_set:
                raise WorkflowDefinitionError(
                    f"Invalid transition: unknown state '{t.get('to_state')}'"
                )

        # Orphaned-state check before update (REQ-L3-WE001-003)
        existing = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if existing is not None:
            old_states = set(existing.workflow_json.get("states", []))
            removed = old_states - state_set
            for orphaned in removed:
                self._check_orphaned_state(
                    workspace_id, item_type, orphaned, str(workspace_id)
                )

        workflow_json: dict[str, Any] = {
            "states": states,
            "transitions": transitions,
        }

        if existing is not None:
            existing.workflow_json = workflow_json
            existing.is_custom = True
            existing.save(update_fields=["workflow_json", "is_custom", "modified_at"])
            return _dto_from_orm(existing)
        else:
            record = WorkflowEngineDefinition.objects.create(
                workspace_id=str(workspace_id),
                item_type=item_type,
                preset="extended",
                workflow_json=workflow_json,
                is_custom=True,
            )
            return _dto_from_orm(record)

    # -- Orphaned-state check (REQ-L3-WE001-003) ------------------------------

    def _check_orphaned_state(
        self,
        workspace_id: UUID | str,
        item_type: str,
        state: str,
        _workspace_id_str: str,
    ) -> None:
        """Raise OrphanedStateError if items exist in ``state`` (REQ-L2-WE-004)."""
        qs = WorkflowItemState.objects.filter(
            workspace_id=str(workspace_id),
            item_type=item_type,
            current_state=state,
        )
        count = qs.count()
        if count == 0:
            return
        # Collect up to 100 item IDs for the error message.
        item_ids = list(
            qs.values_list("item_id", flat=True)[:100]
        )
        raise OrphanedStateError(
            orphaned_state=state,
            count=count,
            item_ids=[str(i) for i in item_ids],
        )

    # -- Preset downgrade check (REQ-L3-WE001-004) ----------------------------

    def check_downgrade_compatibility(
        self, workspace_id: UUID | str, target_preset: str, item_type: str = "Requirement"
    ) -> None:
        """Block downgrade if items exist in states not valid for target preset.

        Args:
            workspace_id: Workspace being downgraded.
            target_preset: Target tier name.
            item_type: Entity type.

        Raises:
            PresetDowngradeBlockedError: Items in incompatible states.
            WorkflowDefinitionError: Unknown target preset.
        """
        if target_preset not in PRESET_SCHEMAS:
            raise WorkflowDefinitionError(f"Unknown target preset: {target_preset!r}")

        target_states = set(PRESET_SCHEMAS[target_preset]["states"])

        # Find items in states NOT valid for target preset.
        all_item_states = WorkflowItemState.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).values("current_state").distinct()

        incompatible: list[str] = []
        total_count = 0
        for row in all_item_states:
            state = row["current_state"]
            if state not in target_states:
                count = WorkflowItemState.objects.filter(
                    workspace_id=str(workspace_id),
                    item_type=item_type,
                    current_state=state,
                ).count()
                if count > 0:
                    incompatible.append(state)
                    total_count += count

        if incompatible:
            raise PresetDowngradeBlockedError(
                incompatible_states=incompatible, count=total_count
            )


__all__ = [
    "WorkflowDefinitionStore",
    "WorkflowDefinitionDTO",
    "TransitionDefinitionDTO",
    "WorkflowDefinitionError",
    "OrphanedStateError",
    "PresetDowngradeBlockedError",
    "PRESET_SCHEMAS",
]
