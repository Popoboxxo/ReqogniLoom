"""
ARCH-L1-006 BaselineService — Django ORM models for Baseline persistence.

leaf_id: COMP-BL-003 (BaselineStore)
req_id:  REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-005, REQ-L2-BL-007

Two new models are defined here (ADR-BL-02: Delta-Storage):

    BaselineSnapshot  — immutable Baseline header record
    BaselineDeltaIndexEntry — one (item_id, version, entity_type) tuple per entry

Immutability is enforced at two levels (ADR-L3-BL003-01):
  1. Application layer: ``BaselineStore.update()`` / ``delete()`` raise
     ``BaselineImmutableError`` before any SQL is executed.
  2. Database level (PostgreSQL): the migration installs BEFORE UPDATE and
     BEFORE DELETE triggers that raise an exception from within PostgreSQL,
     preventing bypasses through raw SQL or direct ORM abuse.

Unique constraints:
  - BaselineSnapshot: UNIQUE(workspace_id, name) — REQ-L2-BL-005
  - BaselineDeltaIndexEntry: UNIQUE(baseline, item_id) — prevents duplicates

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/Components/
  COMP-BL-003_BaselineStore/L3_COMP-BL-003_BaselineStore_Architecture.md
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.models import TenantScopedModel


class BaselineSnapshot(TenantScopedModel):
    """Immutable Baseline header (COMP-BL-003, REQ-L2-BL-001/002/005).

    Stores metadata only; the actual item/version pairs live in
    :class:`BaselineDeltaIndexEntry`.  Once created, this record MUST NOT be
    modified or deleted — enforced by DB triggers (see migration) and the
    application-layer :class:`baseline.store.BaselineStore`.

    Inherits from TenantScopedModel:
        id, tenant, created_at, created_by, modified_at, modified_by, version
    """

    # Baseline scope (REQ-L2-BL-001, REQ-L1-049):
    #   document — a single Artifact + all descendants + TraceLinks
    #   project  — all Artifacts of a Workspace
    #   global   — all Artifacts of the Tenant (Extended preset only)
    SCOPE_DOCUMENT = "document"
    SCOPE_PROJECT = "project"
    SCOPE_GLOBAL = "global"
    SCOPE_CHOICES = (
        (SCOPE_DOCUMENT, "Document"),
        (SCOPE_PROJECT, "Project"),
        (SCOPE_GLOBAL, "Global"),
    )

    # Workspace scope for tenant-internal partitioning.
    workspace_id = models.UUIDField(db_index=True)

    # Baseline scope with restricted choices (REQ-L1-049). Default is
    # ``project`` because that is the most common workspace-wide baseline.
    scope = models.CharField(
        max_length=32,
        choices=SCOPE_CHOICES,
        default=SCOPE_PROJECT,
    )

    # Human-readable name — unique within a workspace (REQ-L2-BL-005)
    name = models.CharField(max_length=500)

    # Optional free-text description
    description = models.TextField(blank=True, default="")

    # User / agent identifier that triggered creation (stored as string)
    created_by_ref = models.CharField(max_length=255, blank=True, default="")

    # Optional link to the root Artifact (nullable for project/global scope).
    # Migrated from legacy persistence.Baseline (REQ-L2-BL-001).
    artifact = models.ForeignKey(
        "persistence.Artifact",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="baseline_snapshots",
    )

    class Meta:
        db_table = "bl_baseline_snapshot"
        constraints = [
            # REQ-L2-BL-005: name unique per workspace
            models.UniqueConstraint(
                fields=["workspace_id", "name"],
                name="uq_baseline_ws_name",
            ),
        ]
        indexes = [
            # Listing queries filter by workspace_id + created_at DESC
            models.Index(
                fields=["workspace_id", "-created_at"],
                name="idx_baseline_snapshot_ws_cat",
            ),
            models.Index(
                fields=["workspace_id", "scope"],
                name="idx_baseline_snapshot_ws_scope",
            ),
        ]

    def __str__(self) -> str:
        return f"BaselineSnapshot({self.name!r}, scope={self.scope}, id={self.id})"


class BaselineDeltaIndexEntry(models.Model):
    """Single (item_id, version, entity_type) tuple in a Baseline.

    Each entry is one atomic reference captured at Baseline creation time.
    The entry MUST NOT be modified or deleted after creation (immutability
    mirrors :class:`BaselineSnapshot`).

    entity_type differentiates items from ICD versions and TraceLinks
    ("item" | "icd" | "trace_link").

    COMP-BL-003 (REQ-L2-BL-001, ADR-BL-02)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Foreign key to the owning Baseline — CASCADE so that if a snapshot is
    # ever physically removed (maintenance-only), orphan rows are cleaned up.
    # Application-layer immutability prevents normal delete paths.
    baseline = models.ForeignKey(
        BaselineSnapshot,
        on_delete=models.CASCADE,
        related_name="delta_entries",
        db_index=True,
    )

    # The entity being versioned (Requirement/Artifact UUID as string to avoid
    # coupling to specific persistence models from other apps)
    item_id = models.CharField(max_length=64, db_index=True)

    # Version number at snapshot time (from AuditableModel.version)
    version = models.IntegerField()

    # Discriminator for entity kind
    entity_type = models.CharField(max_length=32, default="item")

    # Full entity state captured at Baseline creation time (REQ-L2-BL-012).
    # Enables field-level reconstruction and diffing of a Baseline's contents
    # without depending on the audit log. Nullable so that legacy entries
    # created before this feature remain valid with a NULL state (no backfill,
    # no data loss). New entries always populate it via BaselineStore.
    state = models.JSONField(
        null=True,
        default=None,
        help_text=(
            "Full entity state at baseline creation time. Null for legacy "
            "entries created before this feature."
        ),
    )

    class Meta:
        db_table = "bl_delta_index_entry"
        constraints = [
            # UNIQUE(baseline, item_id) prevents duplicate entries for the same
            # item within a single baseline (REQ-L3-BL003-001)
            models.UniqueConstraint(
                fields=["baseline", "item_id"],
                name="uq_delta_entry_baseline_item",
            ),
        ]
        indexes = [
            # Lookup by (baseline_id, item_id) — used by VersionReconstructor
            models.Index(
                fields=["baseline", "item_id"],
                name="idx_delta_entry_baseline_item",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"DeltaEntry(baseline={self.baseline_id}, "
            f"item={self.item_id}, v={self.version})"
        )


class BaselineGateWaiver(TenantScopedModel):
    """Per-blocker waiver for the SE-Auditor baseline gate (GH-821).

    leaf_id: COMP-BL-003 (BaselineStore extension)
    req_id:  REQ-L2-BL-001, REQ-L2-AL-001

    The gate (``application.baseline_facade.BaselineFacade._enforce_audit_gate``)
    only ever had an all-or-nothing exit: either every BLOCKER was resolved, or
    a single ``override_reason`` waived the entire verdict. A workspace with 47
    findings therefore had exactly one lever — accept all of them, with one
    sentence of justification — while the findings themselves stayed
    unwirtschaftbar (issue #821).

    This row records the *per-finding* answer: one accepted deviation, for one
    rule/artifact combination, with its own mandatory justification. Rows are
    append-only governance records — the ``ChangeReason``/``AuditLog`` pair
    around them is the authoritative trail, and the row is what makes the
    decision durable, so a later baseline build does not have to re-state a
    waiver that was already granted and argued for.

    Identity is ``(workspace_id, finding_key)`` where ``finding_key`` is the
    canonical ``rule_id|sorted(artifact_ids)`` rendering produced by
    :func:`baseline.waivers.finding_key` — deliberately *not* an audit-run id,
    because a finding has no stable id across runs: the same TRACE-P1 on the
    same artifact is the same blocker tomorrow.
    """

    # Workspace scope (tenant-internal partition), mirroring BaselineSnapshot.
    workspace_id = models.UUIDField(db_index=True)

    #: Originating SE-Auditor rule (e.g. "TRACE-P1").
    rule_id = models.CharField(max_length=64)

    #: Canonical finding identity, see :func:`baseline.waivers.finding_key`.
    finding_key = models.CharField(max_length=255)

    #: Artifacts the waived finding concerns (empty for graph-level findings).
    artifact_ids = models.JSONField(default=list, blank=True)

    #: Baseline scope the finding was reported in ("document"|"project"|...).
    scope = models.CharField(max_length=32, blank=True, default="")
    scope_artifact_id = models.CharField(max_length=64, blank=True, default="")

    #: Mandatory justification — a waiver without a stated reason is not a
    #: governance record. Enforced here (non-blank) AND by the DB constraint
    #: below, so no code path can persist an unexplained suppression.
    reason = models.TextField()

    # User *or* agent identifier that granted the waiver, stored as a string —
    # same reason as ``BaselineSnapshot.created_by_ref``: an MCP agent has no
    # ``persistence.User`` row, and a waiver must keep naming its author even
    # if that user is later deleted (AuditableModel.created_by is SET_NULL).
    granted_by = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "bl_baseline_gate_waiver"
        constraints = [
            # One waiver per finding per workspace: re-sending the same waiver
            # is idempotent instead of accumulating duplicate justification.
            models.UniqueConstraint(
                fields=["workspace_id", "finding_key"],
                name="uq_baseline_waiver_ws_finding",
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="ck_baseline_waiver_reason_not_blank",
            ),
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "rule_id"],
                name="idx_baseline_waiver_ws_rule",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"BaselineGateWaiver(ws={self.workspace_id}, "
            f"rule={self.rule_id}, key={self.finding_key})"
        )


__all__ = [
    "BaselineSnapshot",
    "BaselineDeltaIndexEntry",
    "BaselineGateWaiver",
]
