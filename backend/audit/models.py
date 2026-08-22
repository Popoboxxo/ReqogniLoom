"""
ARCH-L1-012 AuditLog — Domain models for the AuditLog system.

COMP-AL-001: AuditLogWriter uses AuditEntry for append-only persistence.
COMP-AL-002: AuditLogQuery reads from AuditEntry (shared model, read-only path).

Requirements:
- REQ-L2-AL-001 (complete audit fields for all write operations)
- REQ-L2-AL-002 (MCP enrichment: client_name, api_key_hash SHA-256)
- REQ-L2-AL-003 (append-only: no UPDATE/DELETE via DB trigger)
- REQ-L2-AL-006 (tenant isolation via TenantScopedModel)
- REQ-L2-AL-007 (indexes for performance: entity_id, tenant+timestamp, actor+op)
- REQ-L2-AL-008 (monthly RANGE partitioning on timestamp — migration manages partitions)

Architecture:
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/L2_AuditLogSystem_Architecture.md
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/Components/COMP-AL-001_AuditLogWriter/
- docs/se/L1/Gesamtsystem/L2/AuditLogSystem/Components/COMP-AL-002_AuditLogQuery/

ESCALATION NOTE (IF-AL-EXT-OUT-001):
  persistence.models.AuditLogEntry exists but uses a generic schema (action,
  object_type, object_id, actor FK, payload) that is incompatible with the
  L2 spec (actor_type, op, entity_type, entity_id, source, client_name,
  api_key_hash, change_reason as first-class columns). Adding those fields to
  persistence.models is outside this component's context_boundary and would
  require a persistence interface change. AuditEntry is therefore defined here
  in the audit app. Escalation target: se-interface-mgr / se-architect
  (interface IF-AL-EXT-OUT-001 needs alignment).
"""
from __future__ import annotations

import uuid

from django.db import models

from persistence.models import TenantScopedModel
from persistence.tenancy import TenantManager, UnscopedManager


# ---------------------------------------------------------------------------
# Append-only manager — COMP-AL-001 / REQ-L2-AL-003
# ---------------------------------------------------------------------------


class AppendOnlyManager(TenantManager):
    """Tenant-scoped manager that blocks bulk UPDATE/DELETE at ORM level.

    The DB-level append-only trigger (migration 0002) is the authoritative
    constraint; this manager provides an early-fail guard in the application
    layer so misuse is caught immediately with a clear error message.
    """

    def update(self, **kwargs):  # type: ignore[override]
        raise RuntimeError(
            "AuditEntry is append-only. UPDATE operations are not permitted."
        )

    def delete(self):  # type: ignore[override]
        raise RuntimeError(
            "AuditEntry is append-only. DELETE operations are not permitted."
        )


class AppendOnlyUnscopedManager(UnscopedManager):
    """Unscoped escape-hatch that also blocks UPDATE/DELETE.

    Used internally by the ArchiveLifecycleManager for partition management
    (cross-tenant maintenance context). Even the escape hatch must not allow
    UPDATE/DELETE; only the raw DDL partition-drop path is permitted for
    archiving (COMP-AL-003, ADR-AL-03).
    """

    def update(self, **kwargs):  # type: ignore[override]
        raise RuntimeError(
            "AuditEntry is append-only. UPDATE operations are not permitted."
        )

    def delete(self):  # type: ignore[override]
        raise RuntimeError(
            "AuditEntry is append-only. DELETE operations are not permitted."
        )


# ---------------------------------------------------------------------------
# AuditEntry — append-only operational log (COMP-AL-001)
# ---------------------------------------------------------------------------


class AuditEntry(TenantScopedModel):
    """Append-only audit log entry for all write operations.

    REQ-L2-AL-001: captures actor, actor_type, op, entity_type, entity_id,
                   timestamp, version, change_reason for every write.
    REQ-L2-AL-002: MCP enrichment fields client_name, api_key_hash (SHA-256
                   prefixed), source.
    REQ-L2-AL-003: append-only; no UPDATE/DELETE via manager or DB trigger.
    REQ-L2-AL-006: tenant_id injected via TenantScopedModel.

    The ``timestamp`` field is set at INSERT time (auto_now_add) and is the
    partition key for monthly RANGE partitioning (REQ-L2-AL-008).

    ``version`` here tracks the entity version at the time of the operation
    (not the audit entry's own version).
    """

    ACTOR_TYPE_USER = "user"
    ACTOR_TYPE_AGENT = "agent"
    ACTOR_TYPE_CHOICES = [
        (ACTOR_TYPE_USER, "User"),
        (ACTOR_TYPE_AGENT, "Agent"),
    ]

    OP_CREATE = "create"
    OP_UPDATE = "update"
    OP_DELETE = "delete"
    OP_TRANSITION = "transition"
    OP_BASELINE_CREATE = "baseline.create"
    OP_WORKSPACE_CLOSE = "workspace.close"
    OP_WORKSPACE_REACTIVATE = "workspace.reactivate"
    OP_WORKSPACE_DELETE = "workspace.delete"
    OP_CLONE = "clone"
    OP_ASSIGN = "assign"
    OP_ADMIN_BACKUP_CREATE = "admin.backup_create"
    OP_ADMIN_RESTORE = "admin.restore"
    OP_PERMISSIONS_SET_RULE = "permissions.set_rule"
    OP_PERMISSIONS_REVOKE = "permissions.revoke"
    OP_USER_CREATE = "user.create"
    OP_USER_ASSIGN_ROLE = "user.assign_role"
    OP_USER_DEACTIVATE = "user.deactivate"
    # Multi-user management Task 9 (#539 follow-up): these 5 ops were added
    # to ``UsersToolGroup`` without being declared here, so ``write_mcp_audit``
    # silently produced zero audit rows for all of them (see #539 above).
    OP_USER_ACTIVATE = "user.activate"
    OP_USER_SUSPEND_ROLE = "user.suspend_role"
    OP_USER_REACTIVATE_ROLE = "user.reactivate_role"
    OP_USER_ASSIGN_TENANT_ADMIN = "user.assign_tenant_admin"
    OP_USER_REVOKE_TENANT_ADMIN = "user.revoke_tenant_admin"
    # #573: LLM-backed analyses exposed as MCP tools. They have no REST
    # pendant whose op could be reused, so they get their own namespace —
    # consistent with the ``baseline.``/``workspace.``/``admin.``/
    # ``permissions.``/``user.`` families above. The MCP soft-delete
    # (``requirement.outdate`` / ``needs.outdate``) and restore
    # (``*.reactivate``) deliberately do NOT appear here: they reuse the ops
    # their REST pendants already write (``delete`` / ``transition``) so a
    # single audit query answers "who deleted this" across both surfaces.
    OP_AI_DECOMPOSE = "ai.decompose"
    OP_AI_VALIDATE = "ai.validate"
    OP_AI_CHECK_CONSISTENCY = "ai.check_consistency"
    # #626: DLQ event replay has no REST pendant (it is admin/ops machinery
    # over a DomainEventDLQ row, not a CRUD op on a business entity), so it
    # gets its own namespace — same reasoning as the ``ai.*`` family above.
    OP_EVENTS_REPLAY = "events.replay"
    # NOTE (#265): ``op`` is validated against this list by
    # ``AuditLogWriter.write`` via ``full_clean``, and ``ServiceBase._audit``
    # re-raises the resulting ValidationError — so a service that audits an
    # operation missing here fails its whole transaction with a 500 *after*
    # the business mutation already succeeded. Any new ``operation=`` string
    # passed to ``ServiceBase._audit`` MUST be added here (guarded by
    # ``audit/tests/test_op_vocabulary.py``).
    #
    # NOTE (#539): the same failure mode applies to ``write_mcp_audit``
    # (mcp_server/tools/base.py) — its ``operation=`` argument goes through
    # the identical ``full_clean()`` validation, but the resulting
    # ValidationError is caught and only logged (never re-raised), so an
    # undeclared op there silently produces zero audit rows instead of a
    # loud 500. The admin/user/permissions op values below were added for
    # that reason; any new MCP admin-style tool op must be added here too.
    #
    # NOTE (#573): the requirements/needs lifecycle + AI tools hit the same
    # silent-drop path — ``requirement.outdate|reactivate|validate|
    # check_consistency|decompose`` and ``needs.outdate|reactivate`` all
    # returned 200 while writing zero audit rows. Two different remedies were
    # applied, on purpose: operations with a REST pendant now emit that
    # pendant's op (outdate -> ``delete``, reactivate -> ``transition``), and
    # only the LLM analyses, which have no REST pendant, got new ``ai.*``
    # choices below.
    #
    # NOTE (#626): the remaining 17 call-sites from the #573 follow-up list
    # (ai_derivation.py's 6 derive/suggest tools, review.py's
    # approve/reject/request_changes, tests.py's outdate/reactivate/
    # derive_from_requirement, architecture.py's outdate/reactivate,
    # diagram.py's outdate/reactivate, audit.py's replay) hit the identical
    # gap. All but one reuse an existing pendant: the 6 ai_derivation.py
    # tools plus tests.py's derive_from_requirement each write exactly one
    # audit entry for the ONE entity they just created (a Requirement/Adr/
    # GlossaryTerm/Risk/TraceLink/TestCase row) -> ``create``, same
    # "who created this" query as their REST siblings. outdate/reactivate on
    # architecture.py/diagram.py/tests.py -> ``delete``/``transition``, same
    # convention as #573. review.py's approve/request_changes call
    # WorkflowFacade.transition() directly -> ``transition``; reject calls
    # the outdate() escape hatch -> ``delete``. Only audit.py's DLQ replay
    # has no REST pendant (it is admin/ops machinery, not a CRUD op on a
    # business entity) -> the new ``events.replay`` above.
    OP_CHOICES = [
        (OP_CREATE, "Create"),
        (OP_UPDATE, "Update"),
        (OP_DELETE, "Delete"),
        (OP_TRANSITION, "Transition"),
        (OP_BASELINE_CREATE, "Baseline Create"),
        (OP_WORKSPACE_CLOSE, "Workspace Close"),
        (OP_WORKSPACE_REACTIVATE, "Workspace Reactivate"),
        (OP_WORKSPACE_DELETE, "Workspace Delete"),
        (OP_CLONE, "Clone"),
        (OP_ASSIGN, "Assign"),
        (OP_ADMIN_BACKUP_CREATE, "Admin Backup Create"),
        (OP_ADMIN_RESTORE, "Admin Restore"),
        (OP_PERMISSIONS_SET_RULE, "Permissions Set Rule"),
        (OP_PERMISSIONS_REVOKE, "Permissions Revoke"),
        (OP_USER_CREATE, "User Create"),
        (OP_USER_ASSIGN_ROLE, "User Assign Role"),
        (OP_USER_DEACTIVATE, "User Deactivate"),
        (OP_USER_ACTIVATE, "User Activate"),
        (OP_USER_SUSPEND_ROLE, "User Suspend Role"),
        (OP_USER_REACTIVATE_ROLE, "User Reactivate Role"),
        (OP_USER_ASSIGN_TENANT_ADMIN, "User Assign Tenant Admin"),
        (OP_USER_REVOKE_TENANT_ADMIN, "User Revoke Tenant Admin"),
        (OP_AI_DECOMPOSE, "AI Decompose"),
        (OP_AI_VALIDATE, "AI Validate"),
        (OP_AI_CHECK_CONSISTENCY, "AI Consistency Check"),
        (OP_EVENTS_REPLAY, "Events Replay"),
    ]

    SOURCE_REST = "rest"
    SOURCE_MCP = "mcp"
    SOURCE_CHOICES = [
        (SOURCE_REST, "REST"),
        (SOURCE_MCP, "MCP"),
    ]

    # Actor identification
    actor = models.CharField(
        max_length=255,
        help_text="User ID or Agent ID string (not a FK to preserve history after user deletion).",
    )
    actor_type = models.CharField(
        max_length=16,
        choices=ACTOR_TYPE_CHOICES,
        help_text="'user' for human actors, 'agent' for MCP clients.",
    )

    # Operation details
    op = models.CharField(
        max_length=32,
        choices=OP_CHOICES,
        help_text="Performed operation: create, update, delete, transition.",
    )
    entity_type = models.CharField(
        max_length=128,
        help_text="Type of the affected entity (e.g. 'Requirement', 'TestCase').",
    )
    entity_id = models.UUIDField(
        help_text="Primary key of the affected entity.",
    )
    entity_version = models.IntegerField(
        null=True,
        blank=True,
        help_text="Entity version at the time of the operation (v1: operation-level).",
    )
    change_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Optional human-readable reason for the change (e.g. workflow transition).",
    )

    # Timestamp — partition key (REQ-L2-AL-008)
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="UTC timestamp of the operation; auto-set at INSERT. Partition key.",
    )

    # Source and MCP enrichment (REQ-L2-AL-002)
    source = models.CharField(
        max_length=8,
        choices=SOURCE_CHOICES,
        default=SOURCE_REST,
        help_text="'rest' for REST API callers, 'mcp' for MCP agent callers.",
    )
    client_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="MCP client identifier (e.g. 'claude-code/1.0'). NULL for REST.",
    )
    api_key_hash = models.CharField(
        max_length=71,  # "sha256:" (7) + 64 hex chars
        null=True,
        blank=True,
        help_text="SHA-256 hash of the API key with 'sha256:' prefix. NULL for REST. "
                  "NEVER store the raw API key.",
    )

    # Override managers — append-only at ORM level
    objects = AppendOnlyManager()
    unscoped = AppendOnlyUnscopedManager()

    class Meta:
        db_table = "audit_entry"
        base_manager_name = "unscoped"
        # REQ-L2-AL-007: indexes for query performance at 100k+ entries.
        indexes = [
            models.Index(fields=["entity_id"], name="idx_auditentry_entity_id"),
            models.Index(
                fields=["tenant", "timestamp"],
                name="idx_audit_tenant_ts",
            ),
            models.Index(
                fields=["actor", "op"],
                name="idx_auditentry_actor_op",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.source}] {self.actor_type}:{self.actor} {self.op} {self.entity_type}:{self.entity_id}"

    def save(self, *args, **kwargs):
        """Block UPDATE on existing instances at model level.

        REQ-L2-AL-003: INSERT is accepted; UPDATE is rejected. The DB-level
        trigger (see migration 0002_audit_append_only_trigger) is the
        authoritative constraint; this guard provides application-layer
        early-fail.
        """
        if self.pk is not None and AuditEntry.unscoped.filter(pk=self.pk).exists():
            raise RuntimeError(
                "AuditEntry is append-only. Modifying an existing entry is not permitted."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[override]
        """Block DELETE on individual instances at model level.

        REQ-L2-AL-003: the DB-level trigger rejects DELETE at the database;
        this override provides an earlier application-layer guard.
        """
        raise RuntimeError(
            "AuditEntry is append-only. DELETE operations are not permitted."
        )
