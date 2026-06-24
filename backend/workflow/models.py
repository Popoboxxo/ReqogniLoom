"""
ARCH-L1-005 WorkflowEngine — App-local models.

leaf_id : ARCH-L1-005
req_id  : REQ-L2-WE-002, REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006

These models live in the *workflow* app and extend the WorkflowEngine beyond the
thin placeholder rows already in persistence.models (WorkflowDefinition,
WorkflowState).  They do NOT redefine persistence-layer entities.

Model map
---------
WorkflowEngineDefinition (COMP-WE-001)
    Per-workspace, per-item-type state-machine configuration.  Holds states and
    transitions as JSON.  The persistence.WorkflowDefinition FK is the canonical
    identity; this record carries the engine-level config.

WorkflowItemState (COMP-WE-003)
    Current state of a single tracked item (artifact / requirement / …).
    ``version`` implements Optimistic Locking (ADR-L3-WE003-02).

WorkflowHistoryEntry (COMP-WE-003)
    Append-only audit trail per item (REQ-L2-WE-003, ADR-L3-WE003-03).
    No UPDATE/DELETE path exposed in the ORM layer.

Architecture reference:
    docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/
        L2_WorkflowEngineSystem_Architecture.md
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.models import TenantScopedModel


# ---------------------------------------------------------------------------
# COMP-WE-001  WorkflowEngineDefinition
# ---------------------------------------------------------------------------


class WorkflowEngineDefinition(TenantScopedModel):
    """Per-workspace, per-item-type workflow configuration (COMP-WE-001).

    ``workflow_json`` stores the complete state-machine definition::

        {
            "states": ["draft", "in_review", "approved", "deprecated"],
            "transitions": [
                {
                    "from_state": "draft",
                    "to_state": "in_review",
                    "allowed_roles": ["editor", "approver", "admin"],
                    "requires_change_reason": false,
                    "signature_gate": false
                },
                ...
            ]
        }

    ``preset`` records the workspace tier at creation time (minimal / standard /
    extended) so orphaned-state and downgrade checks can compare states
    against preset defaults without an extra query.

    ``is_custom`` distinguishes user-supplied definitions (extended only) from
    auto-generated preset defaults.

    REQ-L2-WE-002, REQ-L3-WE001-001, REQ-L3-WE001-002.
    """

    PRESET_MINIMAL = "minimal"
    PRESET_STANDARD = "standard"
    PRESET_EXTENDED = "extended"

    PRESET_CHOICES = [
        (PRESET_MINIMAL, "Minimal"),
        (PRESET_STANDARD, "Standard"),
        (PRESET_EXTENDED, "Extended"),
    ]

    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    preset = models.CharField(max_length=32, choices=PRESET_CHOICES)
    workflow_json = models.JSONField(default=dict)
    is_custom = models.BooleanField(default=False)

    class Meta:
        db_table = "we_engine_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace_id", "item_type"],
                name="uq_we_definition_tenant_workspace_type",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "item_type"],
                name="idx_we_def_workspace_type",
            )
        ]

    def __str__(self) -> str:
        return f"WorkflowDef({self.item_type}@{self.workspace_id}, {self.preset})"


# ---------------------------------------------------------------------------
# COMP-WE-003  WorkflowItemState
# ---------------------------------------------------------------------------


class WorkflowItemState(TenantScopedModel):
    """Current workflow state of a tracked item (COMP-WE-003).

    ``item_id`` is the UUID of the item (Requirement, Artifact, …) regardless
    of type.  ``item_type`` disambiguates so one table can track multiple
    entity types.

    ``version`` is the Optimistic Lock counter.  Writers must:
        SELECT … WHERE id=? AND version=<expected>
        UPDATE … SET current_state=?, version=version+1

    If the UPDATE rowcount is 0, another writer won the race → 409 Conflict
    (REQ-L2-WE-003, ADR-L3-WE003-02).

    REQ-L2-WE-005, REQ-L2-WE-006, REQ-L3-WE003-001, REQ-L3-WE003-002.
    """

    item_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    workspace_id = models.UUIDField(db_index=True)
    definition = models.ForeignKey(
        WorkflowEngineDefinition,
        on_delete=models.PROTECT,
        related_name="item_states",
    )
    current_state = models.CharField(max_length=128)

    class Meta:
        db_table = "we_item_state"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "item_id", "item_type"],
                name="uq_we_state_tenant_item",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "current_state"],
                name="idx_we_state_workspace_state",
            )
        ]

    def __str__(self) -> str:
        return f"ItemState({self.item_type}:{self.item_id} → {self.current_state})"


# ---------------------------------------------------------------------------
# COMP-WE-003  WorkflowHistoryEntry
# ---------------------------------------------------------------------------


class WorkflowHistoryEntry(TenantScopedModel):
    """Append-only transition history entry (COMP-WE-003, REQ-L2-WE-003).

    ``transitioned_at`` is millisecond-precision UTC.  ``signature_seal`` is
    non-null only when the transition passed through a SignatureGate
    (REQ-L2-WE-009, REQ-L3-WE004-002).

    ``transitioned_by`` stores the user UUID as a string so it also accepts
    AI-agent client identifiers (REQ-L2-WE-003 MCP note).

    Append-only contract (ADR-L3-WE003-03): no service method in this app
    issues UPDATE or DELETE on this table.  The ``created_at`` field (from
    TenantScopedModel via AuditableModel) acts as the immutable timestamp.
    """

    item_state = models.ForeignKey(
        WorkflowItemState,
        on_delete=models.CASCADE,
        related_name="history",
    )
    from_state = models.CharField(max_length=128)
    to_state = models.CharField(max_length=128)
    transitioned_by = models.CharField(max_length=255)
    transitioned_at = models.DateTimeField()  # UTC, ms-precision
    change_reason = models.TextField(blank=True, default="")
    signature_seal = models.CharField(max_length=255, blank=True, default="")
    workspace_id = models.UUIDField(db_index=True)

    class Meta:
        db_table = "we_history_entry"
        indexes = [
            models.Index(
                fields=["item_state", "transitioned_at"],
                name="idx_we_history_item_time",
            )
        ]

    def __str__(self) -> str:
        return (
            f"History({self.from_state}→{self.to_state} "
            f"by {self.transitioned_by} at {self.transitioned_at})"
        )

    def save(self, *args, **kwargs) -> None:  # type: ignore[override]
        """Block UPDATE — history is append-only (REQ-L2-WE-003).

        On UPDATE the pk is already set; raise to enforce append-only semantics
        in the application layer.  Uses the unscoped manager so the check works
        regardless of whether a tenant context is active.
        """
        if self.pk and self.__class__.unscoped.filter(pk=self.pk).exists():
            raise ValueError("History is append-only")
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "WorkflowEngineDefinition",
    "WorkflowItemState",
    "WorkflowHistoryEntry",
]
