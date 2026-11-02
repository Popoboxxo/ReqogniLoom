"""COMP-AS-0xx WorkItemService — work item state, resume and heartbeat.

leaf_id : COMP-AS-0xx (Plan F F3-T4)
req_id  : REQ-L2-PL-004, REQ-L2-PL-010

The single write entry point (ADR-01) for the ``WorkItem`` artifact introduced
in Plan F F3-T1 (#1374). A work item is the explicit, queryable agent state
store the concept (§9) puts in place of progress-ledger files, so this service
follows the established ``DocumentService``/``AdrService`` shape — backing
``Artifact`` + local ``uid`` + workflow initialisation + audit — and adds only
what the F3 spec makes specific:

* **``document`` is mandatory** (concept E11/O7). A work item without a
  document is not a valid state, and a document from another workspace/tenant
  is refused instead of silently re-homed.
* **Heartbeat (A-3).** Every write action stamps ``last_activity_at`` and
  ``last_actor``. ``DOC-P5`` (F3-T8) reads the timestamp to report stale
  ``in_progress`` items; without a heartbeat every write would leave the item
  looking abandoned.
* **Blocked needs a reason (rule 10).** A transition *into* ``blocked``
  requires a non-empty ``blocked_reason``. The service checks it itself
  (fail-closed, before the workflow engine) and persists the reason before the
  transition, so ``workflow.precondition_rules`` rule 10 sees it in the same
  transaction.
* **Human sign-off in ``extended``.** The workspace's WorkItem workflow marks
  its approval target with ``state_meta[...]["requires_approval"]``. Entering
  such a target requires an ``approver``/``admin`` role and records
  ``approved_by``/``approved_at`` (spec §4). Resolving the flag from the
  workspace's own graph — rather than a hard-coded tier lookup — is what keeps
  a customised lifecycle (ADR-06) honest.
* **Resume (spec §6).** :meth:`WorkItemService.resume` returns the newest
  checkpoint plus every open item, sorted ``(ordinal, id)`` — the deterministic
  answer to "where do I continue?" for an agent without repo access.
* **Optimistic locking (§9).** ``expected_version`` is the caller's last-seen
  ``WorkItem.version`` (the ETag source), checked through
  :func:`application.optimistic_lock.assert_expected_version`. It is
  deliberately *not* forwarded to ``WorkflowFacade.transition`` as the
  ``WorkflowItemState`` revision: those are two different counters.
* **Soft delete (G1.5, ENT-G1 = A).** ``WorkItem`` has no status column of its
  own: delete/restore go through the workflow engine's ``outdate``/
  ``reactivate`` escape hatch, which flips ``Artifact.lifecycle_status``.

Out of scope here (later F3 tasks): REST/MCP exposure (T5/T6), inline anchors
(T7), outbox events and ``DOC-P5``/``DOC-P7`` rules (T8), frontend (T9).
Deliberately **no** outbox event is emitted yet — ``DomainEventOutbox.EventType``
grows its WorkItem members with F3-T8; emitting a free-string event now would
publish a contract the migration later has to rewrite.

Content revisions (``ArtifactVersion``) are recorded from F3-T5 on: every path
that bumps ``version`` also appends a snapshot built from the ``WorkItem`` entry
in the diff engine's ``_ENTITY_FIELDS`` registry, so ``/versions/`` and
``/diff/`` stay aligned with the optimistic-lock counter. ``due_date`` is stored
as an ISO-8601 string because the revision payload is a ``JSONField``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import F, Q
from django.utils import timezone

from application.artifact_service import (
    _clean_custom_fields,
    clean_free_text_field,
    has_field_changes,
    snapshot_versioned_fields,
)
from application.artifact_version_service import (
    ArtifactVersionService,
    snapshot_fields,
)
from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from application.inline_anchor_service import (
    ANCHOR_FIELD_BODY,
    InlineAnchorService,
)
from application.local_uid import generate_local_uid
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from application.preset_policy_service import get_preset_policy_service
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, TraceLink, WorkItem, Workspace
from persistence.transactions import atomic_transaction
from workflow import state_reader

logger = logging.getLogger(__name__)

#: Sentinel distinguishing "argument omitted" from "clear to None / {}".
_UNSET = object()

#: The workflow item type this service owns.
WORK_ITEM_ITEM_TYPE = "WorkItem"

#: Target state that requires a non-empty ``blocked_reason`` (spec §4, rule 10).
BLOCKED_STATE = "blocked"

#: States that are no longer "open" for the resume contract (spec §6).
CLOSED_STATES: frozenset[str] = frozenset({"done", "dropped"})

#: ``state_meta`` flag marking a state that requires a human sign-off (spec §4).
_APPROVAL_STATE_META_KEY = "requires_approval"

#: Roles allowed to perform a sign-off transition.
_APPROVER_ROLES: frozenset[str] = frozenset({"approver", "admin"})

#: Model column limits mirrored by the service-side syntax gate.
_MAX_TITLE_LENGTH = 255
_MAX_NEXT_ACTION_LENGTH = 255
_MAX_EVIDENCE_REF_LENGTH = 512
_MAX_ACTOR_LENGTH = 128


# ---------------------------------------------------------------------------
# Input validation (Plan E E2.4 "syntax gate", applied at the service boundary)
# ---------------------------------------------------------------------------


def _validate_title(title: str) -> None:
    """Reject a blank/whitespace-only or over-long title."""
    if not title or not title.strip():
        raise ValidationError("Work item title is required")
    if len(title) > _MAX_TITLE_LENGTH:
        raise ValidationError(
            f"Work item title must not exceed {_MAX_TITLE_LENGTH} characters"
        )


def _validate_kind(kind: str) -> None:
    """Reject a ``kind`` outside :class:`WorkItem.Kind`."""
    if kind not in WorkItem.Kind.values:
        raise ValidationError(
            f"Unknown work item kind {kind!r}. Valid kinds: "
            f"{', '.join(WorkItem.Kind.values)}"
        )


def _validate_progress(progress: int | None) -> None:
    """Reject a ``progress`` outside ``0…100`` (``None`` clears it)."""
    if progress is None:
        return
    if isinstance(progress, bool) or not isinstance(progress, int):
        raise ValidationError("Work item progress must be an integer between 0 and 100")
    if not 0 <= progress <= 100:
        raise ValidationError(
            f"Work item progress must be between 0 and 100, got {progress}"
        )


def _validate_ordinal(ordinal: int) -> None:
    """Reject a negative or non-integer ``ordinal``."""
    if isinstance(ordinal, bool) or not isinstance(ordinal, int):
        raise ValidationError("Work item ordinal must be an integer")
    if ordinal < 0:
        raise ValidationError(
            f"Work item ordinal must not be negative, got {ordinal}"
        )


def _validate_length(value: str, field_name: str, maximum: int) -> None:
    """Reject a value that exceeds the underlying ``CharField`` limit."""
    if len(value) > maximum:
        raise ValidationError(
            f"Work item {field_name} must not exceed {maximum} characters"
        )


def _clean_text(value: str | None, field_name: str) -> str | None:
    """Apply the project free-text policy to a single optional text field.

    ``None`` passes through unchanged (the module-wide PATCH idiom: the caller
    only assigns when the value is not ``None``).
    """
    if value is None:
        return None
    cleaned = clean_free_text_field(value, field_name)
    return cleaned or ""


def _actor_label(ctx: AuthContext, actor: str | None) -> str:
    """Resolve the free-text ``last_actor``/``approved_by`` identity.

    An explicit *actor* wins. Otherwise an agent principal is named by its
    label (falling back to the user id), a human by the user id — the same
    distinction the auth layer already made when it built the context.
    """
    label = (actor or "").strip()
    if not label:
        if getattr(ctx, "actor_type", "user") == "agent":
            label = getattr(ctx, "agent_label", "") or str(ctx.user_id or "")
        else:
            label = str(ctx.user_id or "")
    return label[:_MAX_ACTOR_LENGTH]


def _isoformat(value: datetime | None) -> str | None:
    """Return an ISO-8601 string (JSON-safe) or ``None``."""
    return value.isoformat() if value is not None else None


def _work_item_snapshot(item: WorkItem) -> dict[str, Any]:
    """Return a JSON-safe content snapshot of *item* for ``ArtifactVersion``.

    ``snapshot_fields`` reads the diffable field list verbatim; ``due_date`` is
    the one ``datetime`` in it, and the version payload is a ``JSONField`` — an
    unserialisable value would turn every recorded revision into a 500. Storing
    the ISO-8601 string keeps the snapshot human-readable and stable.
    """
    payload = snapshot_fields(item, WORK_ITEM_ITEM_TYPE)
    due_date = payload.get("due_date")
    if due_date is not None:
        payload["due_date"] = due_date.isoformat()
    return payload



# ---------------------------------------------------------------------------
# WorkItemService
# ---------------------------------------------------------------------------


class WorkItemService(ServiceBase):
    """COMP-AS-0xx — work item lifecycle, resume, checkpoint and heartbeat.

    leaf_id : COMP-AS-0xx (Plan F F3-T4)
    req_id  : REQ-L2-PL-004, REQ-L2-PL-010
    """

    # ---------- Workflow helpers ----------

    @staticmethod
    def _workflow_json(workspace_id: UUID) -> dict:
        """Return the workspace's WorkItem ``workflow_json`` (``{}`` if none)."""
        from workflow.services import get_workflow_json

        return get_workflow_json(workspace_id, WORK_ITEM_ITEM_TYPE) or {}

    @classmethod
    def _requires_approval(cls, workspace_id: UUID, target_state: str) -> bool:
        """Return True when *target_state* is the workspace's sign-off state.

        Resolution goes through ``state_meta`` rather than a hard-coded tier or
        state name (spec §4): a workspace that customised its WorkItem
        lifecycle (ADR-06) may name the sign-off state anything, and the
        approval bookkeeping must follow it. An unconfigured workspace yields
        ``False`` here — the transition itself is then rejected by the engine,
        so this cannot become a silent bypass.
        """
        from workflow.definition_store import get_state_meta

        workflow_json = cls._workflow_json(workspace_id)
        if not workflow_json:
            return False
        return bool(
            get_state_meta(workflow_json, target_state).get(_APPROVAL_STATE_META_KEY)
        )

    # ---------- Row helpers ----------

    def _touch(self, item: WorkItem, *, actor: str) -> None:
        """Stamp the heartbeat on *item* (A-3) before it is saved."""
        item.last_activity_at = timezone.now()
        item.last_actor = actor

    @staticmethod
    def _bump_version(item: WorkItem) -> None:
        """Increment ``version`` atomically (REQ-L3-PL001-002).

        A Python-level ``item.version += 1`` would be the very read-modify-write
        race the counter exists to detect; the database-side increment keeps the
        ETag honest under concurrent writers.
        """
        WorkItem.objects.filter(id=item.id).update(version=F("version") + 1)
        item.refresh_from_db(fields=["version"])

    def _record_revision(
        self, item: WorkItem, ctx: AuthContext, *, change_reason: str = ""
    ) -> None:
        """Append the current content as an ``ArtifactVersion`` (F3-T5).

        Called wherever :meth:`_bump_version` runs, so the stored revision and
        the optimistic-lock counter never diverge: ``/versions/`` lists real
        revisions and ``/diff/`` can compare any two of them. A write that
        bumps ``version`` without a snapshot would make the documented
        ``to_version = version`` default answer 404.
        """
        ArtifactVersionService().record(
            item.artifact_id,
            _work_item_snapshot(item),
            ctx,
            change_reason=change_reason,
        )

    def _resolve_document(
        self, workspace_id: UUID, document_id: UUID | None, ctx: AuthContext
    ) -> Document:
        """Return the owning document, enforcing the mandatory-document rule.

        Raises:
            ValidationError: *document_id* is missing.
            NotFoundError: No such document in this workspace/tenant.
            ValidationError: The document belongs to another workspace.
        """
        if document_id is None:
            raise ValidationError(
                "A work item requires a document (document_id); work items "
                "never exist without one."
            )
        document = Document.objects.filter(
            id=document_id, tenant_id=ctx.tenant_id
        ).first()
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        if document.workspace_id != workspace_id:
            raise ValidationError(
                "A work item's document must belong to the same workspace"
            )
        return document

    # ---------- Read ----------

    def get_work_item(self, item_id: UUID, ctx: AuthContext) -> WorkItem:
        """Fetch one work item (tenant-scoped).

        Soft-deleted items are returned unchanged — G1.5 V3 makes "deleted" a
        flag on the backing artifact, and the transport layer reports it as
        ``status: "outdated"``. Hiding them here would make a re-activation
        endpoint unable to resolve its own subject.

        Raises:
            NotFoundError: No such item in the active tenant.
        """
        self._set_tenant_context(ctx)
        item = WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        return item

    def list_work_items(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        *,
        document_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> list[WorkItem]:
        """List a workspace's work items, deterministically ordered (G2.1).

        Sorted by ``(ordinal, id)`` — the same order :meth:`resume` uses, so a
        document's items render and resume identically. Soft-deleted items are
        omitted unless *include_deleted* is true.

        Args:
            workspace_id: Workspace to list.
            ctx: Resolved AuthContext.
            document_id: Optional document filter.
            include_deleted: Include soft-deleted items.
        """
        self._set_tenant_context(ctx)
        from workflow.services import outdated_item_ids

        queryset = WorkItem.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if document_id is not None:
            queryset = queryset.filter(document_id=document_id)
        if not include_deleted:
            queryset = queryset.exclude(
                id__in=outdated_item_ids(WORK_ITEM_ITEM_TYPE, tenant_id=ctx.tenant_id)
            )
        return list(queryset.order_by("ordinal", "id"))

    def current_status(self, item_id: UUID, ctx: AuthContext) -> str:
        """Return the item's workflow state (or its type's initial state)."""
        self._set_tenant_context(ctx)
        return state_reader.current_state(
            WORK_ITEM_ITEM_TYPE, item_id
        ) or state_reader.initial_state(WORK_ITEM_ITEM_TYPE)

    # ---------- Create ----------

    @atomic_transaction
    def create_work_item(
        self,
        workspace_id: UUID,
        document_id: UUID | None,
        ctx: AuthContext,
        *,
        kind: str,
        title: str,
        body: str = "",
        ordinal: int = 0,
        progress: int | None = None,
        blocked_reason: str = "",
        next_action: str = "",
        evidence_ref: str = "",
        due_date: datetime | None = None,
        exit_criteria: str = "",
        uid: str | None = None,
        custom_fields: dict | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Create a work item with its backing artifact and workflow state.

        Args:
            workspace_id: Target workspace UUID.
            document_id: Owning document (mandatory).
            ctx: Resolved AuthContext (tenant + roles).
            kind: One of ``WorkItem.Kind`` values.
            title: Item title (required, ≤ 255 characters).
            body: Markdown of the section (Step/Checkpoint).
            ordinal: Position inside the document (default 0).
            progress: Optional 0–100 progress.
            blocked_reason: Reason for a blocked item (or the dismissal reason
                of a dropped one).
            next_action: Resume hint ("where to continue").
            evidence_ref: Evidence (commit, test run, artifact id).
            due_date: Optional due date.
            exit_criteria: Definition of done.
            uid: Explicit local identifier; allocated as ``WI-NNN`` otherwise.
            custom_fields: Extended attributes on the backing Artifact.
            actor: Optional free-text actor label (defaults to the context).

        Returns:
            The persisted ``WorkItem`` (``version == 1``, heartbeat stamped).

        Raises:
            PermissionDeniedError: The caller may not write.
            ValidationError: Invalid input, missing document, or a document
                from another workspace.
            NotFoundError: Tenant, workspace or document not found.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        _validate_kind(kind)
        _validate_title(title)
        _validate_ordinal(ordinal)
        _validate_progress(progress)
        _validate_length(next_action, "next_action", _MAX_NEXT_ACTION_LENGTH)
        _validate_length(evidence_ref, "evidence_ref", _MAX_EVIDENCE_REF_LENGTH)
        body = _clean_text(body, "body") or ""
        blocked_reason = _clean_text(blocked_reason, "blocked_reason") or ""
        next_action = _clean_text(next_action, "next_action") or ""
        evidence_ref = _clean_text(evidence_ref, "evidence_ref") or ""
        exit_criteria = _clean_text(exit_criteria, "exit_criteria") or ""

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")
        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        document = self._resolve_document(workspace_id, document_id, ctx)

        actor_label = _actor_label(ctx, actor)

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=WORK_ITEM_ITEM_TYPE,
            custom_fields=_clean_custom_fields(custom_fields),
        )
        item = WorkItem.objects.create(
            artifact=artifact,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            document=document,
            uid=uid or generate_local_uid(WORK_ITEM_ITEM_TYPE, workspace_id),
            kind=kind,
            title=title,
            body=body,
            ordinal=ordinal,
            progress=progress,
            blocked_reason=blocked_reason,
            next_action=next_action,
            evidence_ref=evidence_ref,
            due_date=due_date,
            exit_criteria=exit_criteria,
            last_activity_at=timezone.now(),
            last_actor=actor_label,
        )

        # F3-T5 provenance: the initial content is revision 1 so ``/versions/``
        # and a later ``/diff/`` have a baseline to compare against.
        self._record_revision(item, ctx)

        # F3-T7 (I-1): tokens in the body get their anchor + edge in the same
        # transaction as the item.
        InlineAnchorService().sync_text(
            ctx, item.artifact_id, ANCHOR_FIELD_BODY, item.body
        )

        # Every artifact type is initialised lazily at its definition's initial
        # state. A workspace provisioned before F3-T2 (or a unit test that skips
        # provisioning) has no definition; the item then reports the type's
        # initial state via the state_reader fallback and a transition refuses
        # with the engine's own message instead of silently writing nothing.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[item.id],
                item_type=WORK_ITEM_ITEM_TYPE,
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:  # best-effort, mirrors DocumentService
            logger.warning(
                "WorkItemService: workflow init skipped for item=%s",
                item.id,
                exc_info=True,
            )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type=WORK_ITEM_ITEM_TYPE,
            entity_id=item.id,
            details={
                "kind": kind,
                "document_id": str(document.id),
                "artifact_id": str(artifact.id),
            },
        )
        return item

    # ---------- Update ----------

    @atomic_transaction
    def update_work_item(
        self,
        item_id: UUID,
        ctx: AuthContext,
        *,
        title: str | None = None,
        kind: str | None = None,
        body: str | None = None,
        ordinal: int | None = None,
        progress: object = _UNSET,
        blocked_reason: str | None = None,
        next_action: str | None = None,
        evidence_ref: str | None = None,
        due_date: object = _UNSET,
        exit_criteria: str | None = None,
        custom_fields: object = _UNSET,
        change_reason: str | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Update a work item's editable fields (heartbeat + version guarded).

        ``None`` means "keep the current value" for the optional string fields
        (the module-wide PATCH idiom). ``progress``/``due_date`` use a sentinel
        so an explicit ``None`` clears the column, while ``custom_fields=None``
        clears the extended attributes on the backing artifact.

        Args:
            item_id: UUID of the work item.
            ctx: Resolved AuthContext.
            title: New title, or ``None`` to keep.
            kind: New kind, or ``None`` to keep.
            body: New markdown, or ``None`` to keep.
            ordinal: New position, or ``None`` to keep.
            progress: New 0–100 value; ``None`` explicitly clears it.
            blocked_reason: New reason, or ``None`` to keep. Clearing it while
                the item is ``blocked`` is refused (rule 10).
            next_action: New resume hint, or ``None`` to keep.
            evidence_ref: New evidence reference, or ``None`` to keep.
            due_date: New due date; ``None`` explicitly clears it.
            exit_criteria: New definition of done, or ``None`` to keep.
            custom_fields: Extended attributes; ``None`` clears them, omit to
                keep.
            change_reason: Audit reason, recorded on the log entry.
            expected_version: Caller's last-seen ``WorkItem.version``. When
                supplied and stale, the update is refused with
                ``OptimisticLockError`` (409).
            actor: Optional free-text actor label (defaults to the context).

        Returns:
            The refreshed ``WorkItem`` (version bumped, heartbeat stamped).

        Raises:
            NotFoundError: No such item in the active tenant.
            OptimisticLockError: *expected_version* does not match.
            ValidationError: Invalid input, or clearing a blocked item's reason.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Syntax gate first (Plan E E2.4), before any lock or write.
        if title is not None:
            _validate_title(title)
        if kind is not None:
            _validate_kind(kind)
        if ordinal is not None:
            _validate_ordinal(ordinal)
        if progress is not _UNSET:
            _validate_progress(progress)  # type: ignore[arg-type]
        if next_action is not None:
            _validate_length(next_action, "next_action", _MAX_NEXT_ACTION_LENGTH)
        if evidence_ref is not None:
            _validate_length(evidence_ref, "evidence_ref", _MAX_EVIDENCE_REF_LENGTH)

        item = lock_for_version_check(
            WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        assert_expected_version(item, expected_version, entity_type="WorkItem")

        if (
            blocked_reason is not None
            and not blocked_reason.strip()
            and state_reader.current_state(WORK_ITEM_ITEM_TYPE, item.id) == BLOCKED_STATE
        ):
            raise ValidationError(
                "A blocked work item requires a non-empty blocked_reason."
            )

        before = snapshot_versioned_fields(item)
        custom_fields_changed = False

        if title is not None:
            item.title = title
        if kind is not None:
            item.kind = kind
        if body is not None:
            item.body = _clean_text(body, "body") or ""
        if ordinal is not None:
            item.ordinal = ordinal
        if progress is not _UNSET:
            item.progress = progress  # type: ignore[assignment]
        if blocked_reason is not None:
            item.blocked_reason = _clean_text(blocked_reason, "blocked_reason") or ""
        if next_action is not None:
            item.next_action = _clean_text(next_action, "next_action") or ""
        if evidence_ref is not None:
            item.evidence_ref = _clean_text(evidence_ref, "evidence_ref") or ""
        if due_date is not _UNSET:
            item.due_date = due_date  # type: ignore[assignment]
        if exit_criteria is not None:
            item.exit_criteria = _clean_text(exit_criteria, "exit_criteria") or ""

        if custom_fields is not _UNSET:
            cleaned = _clean_custom_fields(custom_fields)
            custom_fields_changed = cleaned != (item.artifact.custom_fields or {})
            item.artifact.custom_fields = cleaned
            item.artifact.save(update_fields=["custom_fields", "modified_at"])

        self._touch(item, actor=_actor_label(ctx, actor))
        item.save()

        # F3-T7 I-1/I-2: a supplied body is a text edit; other field updates
        # leave the anchor register untouched.
        if body is not None:
            InlineAnchorService().sync_text(
                ctx, item.artifact_id, ANCHOR_FIELD_BODY, item.body
            )

        # A heartbeat is a real write on every action, so ``has_field_changes``
        # is true for the timestamp alone — but keep the gate explicit so a
        # future edit that stops touching the heartbeat does not bump versions
        # for a no-op PATCH.
        if has_field_changes(item, before) or custom_fields_changed:
            self._bump_version(item)
            self._record_revision(item, ctx, change_reason=change_reason or "")

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=WORK_ITEM_ITEM_TYPE,
            entity_id=item.id,
            change_reason=change_reason,
            details={
                "artifact_id": str(item.artifact_id),
                "document_id": str(item.document_id),
            },
        )
        return item

    # ---------- Progress ----------

    @atomic_transaction
    def set_progress(
        self,
        item_id: UUID,
        progress: int,
        ctx: AuthContext,
        *,
        change_reason: str | None = None,
        expected_version: int | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Set an item's progress (0–100) and stamp the heartbeat.

        Progress is independent of the workflow state in every preset (spec
        §4), so this is a dedicated write path rather than a state transition.

        Args:
            item_id: UUID of the work item.
            progress: New progress, 0–100.
            ctx: Resolved AuthContext.
            change_reason: Optional audit reason.
            expected_version: Caller's last-seen ``WorkItem.version``.
            actor: Optional free-text actor label.

        Returns:
            The refreshed ``WorkItem``.

        Raises:
            NotFoundError: No such item in the active tenant.
            ValidationError: *progress* is not an integer in ``0…100``.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        _validate_progress(progress)

        item = lock_for_version_check(
            WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        assert_expected_version(item, expected_version, entity_type="WorkItem")

        item.progress = progress
        self._touch(item, actor=_actor_label(ctx, actor))
        item.save(update_fields=["progress", "last_activity_at", "last_actor", "modified_at"])
        self._bump_version(item)
        self._record_revision(item, ctx, change_reason=change_reason or "")

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=WORK_ITEM_ITEM_TYPE,
            entity_id=item.id,
            change_reason=change_reason,
            details={"progress": progress},
        )
        return item

    # ---------- Transition ----------

    @atomic_transaction
    def transition(
        self,
        item_id: UUID,
        target_state: str,
        ctx: AuthContext,
        *,
        blocked_reason: str | None = None,
        change_reason: str = "",
        credential: str = "",
        expected_version: int | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Move a work item through its workspace workflow.

        Side effects the service owns (and which a direct engine call would
        bypass):

        * entering ``blocked`` requires *blocked_reason* and persists it
          **before** the transition, so rule 10 sees it;
        * entering the workspace's sign-off state (``requires_approval``)
          requires an ``approver``/``admin`` role and records
          ``approved_by``/``approved_at``;
        * every transition stamps the heartbeat.

        Args:
            item_id: UUID of the work item.
            target_state: Requested workflow state.
            ctx: Resolved AuthContext.
            blocked_reason: Mandatory when *target_state* is ``blocked``;
                otherwise an optional reason/history hint.
            change_reason: Reason recorded on the transition (mandatory on
                presets whose change_reason policy says so).
            credential: Password/TOTP token for signature-gated transitions.
            expected_version: Caller's last-seen ``WorkItem.version`` (the ETag
                source). Not forwarded to the workflow engine — its counter is
                a different one.
            actor: Optional free-text actor label.

        Returns:
            The refreshed ``WorkItem``.

        Raises:
            NotFoundError: No such item in the active tenant.
            ValidationError: Missing ``blocked_reason`` for ``blocked``, or a
                transition rejected by the workflow engine.
            PermissionDeniedError: Role gate blocked the move, or a sign-off
                state was requested without ``approver``/``admin``.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if not target_state or not str(target_state).strip():
            raise ValidationError("A target state is required for a transition")

        item = lock_for_version_check(
            WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        assert_expected_version(item, expected_version, entity_type="WorkItem")

        entering_blocked = target_state == BLOCKED_STATE
        if entering_blocked:
            reason = _clean_text(blocked_reason, "blocked_reason") or ""
            if not reason.strip():
                raise ValidationError(
                    "A work item can only enter 'blocked' with a non-empty "
                    "blocked_reason."
                )
            item.blocked_reason = reason
        elif blocked_reason is not None:
            item.blocked_reason = _clean_text(blocked_reason, "blocked_reason") or ""

        approval_target = self._requires_approval(item.workspace_id, target_state)
        if approval_target:
            roles = {str(role).lower() for role in ctx.active_roles}
            if not roles & _APPROVER_ROLES:
                raise PermissionDeniedError(
                    f"Role 'approver' required to transition a work item to "
                    f"{target_state!r} (human sign-off)"
                )

        actor_label = _actor_label(ctx, actor)

        if entering_blocked or blocked_reason is not None:
            # Persist BEFORE the transition so rule 10 (and the audit trail)
            # sees the reason inside the same transaction.
            item.save(update_fields=["blocked_reason", "modified_at"])

        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=item.id,
            item_type=WORK_ITEM_ITEM_TYPE,
            target_state=target_state,
            workspace_id=item.workspace_id,
            ctx=ctx,
            change_reason=change_reason,
            credential=credential,
        )

        if approval_target:
            item.approved_by = actor_label
            item.approved_at = timezone.now()

        self._touch(item, actor=actor_label)
        item.save()
        self._bump_version(item)
        self._record_revision(item, ctx, change_reason=change_reason or "")
        return item

    # ---------- Checkpoint ----------

    @atomic_transaction
    def checkpoint(
        self,
        workspace_id: UUID,
        document_id: UUID | None,
        ctx: AuthContext,
        *,
        next_action: str,
        title: str = "Checkpoint",
        body: str = "",
        ordinal: int = 0,
        actor: str = "",
    ) -> WorkItem:
        """Create a ``Checkpoint`` item carrying the resume hint (spec §6).

        A checkpoint is a marker ("continue here"), not a work deliverable:
        ``WorkItem.informational`` derives that from the kind, which is what
        satisfies the G-2 trace-link gate for it.

        Args:
            workspace_id: Target workspace UUID.
            document_id: Owning document (mandatory).
            ctx: Resolved AuthContext.
            next_action: Where to continue — required and non-empty.
            title: Checkpoint title (default ``"Checkpoint"``).
            body: Optional markdown note.
            ordinal: Position inside the document (default 0).
            actor: Optional free-text actor label.

        Returns:
            The persisted ``Checkpoint`` work item.

        Raises:
            ValidationError: Missing/blank *next_action*, or invalid item input.
            NotFoundError: Tenant, workspace or document not found.
        """
        cleaned = _clean_text(next_action, "next_action") or ""
        if not cleaned.strip():
            raise ValidationError(
                "A checkpoint requires a non-empty next_action ('where to continue')."
            )
        return self.create_work_item(
            workspace_id,
            document_id,
            ctx,
            kind=WorkItem.Kind.CHECKPOINT,
            title=title,
            body=body,
            ordinal=ordinal,
            next_action=cleaned,
            actor=actor,
        )

    # ---------- Resume ----------

    def resume(
        self,
        workspace_id: UUID,
        document_id: UUID | None,
        ctx: AuthContext,
        *,
        actor: str = "",
    ) -> dict[str, Any]:
        """Return the newest checkpoint and every open item of a document.

        The single read an agent without repo access needs to continue (A-6):

        * ``checkpoint`` — the newest non-deleted ``Checkpoint`` item of the
          document, or ``None``;
        * ``open_items`` — every non-deleted item whose workflow state is not
          ``done``/``dropped``, sorted ``(ordinal, id)`` (G2.1).

        Read-only by contract: a resume must not create a heartbeat or bump a
        version, otherwise polling for orientation would itself look like work.
        The *actor* argument is accepted for signature parity with the REST/MCP
        surfaces and deliberately not persisted.

        Args:
            workspace_id: Workspace of the document.
            document_id: Owning document (mandatory).
            ctx: Resolved AuthContext.
            actor: Optional caller label (informational only).

        Returns:
            ``{"checkpoint": {...}|None, "open_items": [...]}``.

        Raises:
            ValidationError: *document_id* is missing.
            NotFoundError: The document is not in this workspace/tenant.
        """
        self._set_tenant_context(ctx)
        document = self._resolve_document(workspace_id, document_id, ctx)

        from workflow.services import outdated_item_ids

        deleted_ids = set(
            outdated_item_ids(WORK_ITEM_ITEM_TYPE, tenant_id=ctx.tenant_id)
        )
        items = list(
            WorkItem.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                document_id=document.id,
            )
            .exclude(id__in=deleted_ids)
            .order_by("ordinal", "id")
        )

        checkpoint = (
            WorkItem.objects.filter(
                workspace_id=workspace_id,
                tenant_id=ctx.tenant_id,
                document_id=document.id,
                kind=WorkItem.Kind.CHECKPOINT,
            )
            .exclude(id__in=deleted_ids)
            .order_by("-created_at", "-id")
            .first()
        )

        states = state_reader.current_states(
            WORK_ITEM_ITEM_TYPE, [item.id for item in items],
            tenant_id=ctx.tenant_id,
        )
        links_by_item = self._links_for_artifacts(
            [item.artifact_id for item in items], ctx
        )

        def render(item: WorkItem) -> dict[str, Any]:
            return {
                "id": str(item.id),
                "uid": item.uid,
                "kind": item.kind,
                "status": states.get(str(item.id))
                or state_reader.initial_state(WORK_ITEM_ITEM_TYPE),
                "progress": item.progress,
                "next_action": item.next_action,
                "blocked_reason": item.blocked_reason,
                "last_actor": item.last_actor,
                "last_activity_at": _isoformat(item.last_activity_at),
                "links": links_by_item.get(item.artifact_id, []),
            }

        open_items = [
            render(item)
            for item in items
            if (
                states.get(str(item.id))
                or state_reader.initial_state(WORK_ITEM_ITEM_TYPE)
            )
            not in CLOSED_STATES
        ]

        return {
            "checkpoint": render(checkpoint) if checkpoint is not None else None,
            "open_items": open_items,
        }

    def _links_for_artifacts(
        self, artifact_ids: list[UUID], ctx: AuthContext
    ) -> dict[UUID, list[dict[str, Any]]]:
        """Group a document's trace links by artifact id (one query).

        The resume payload carries each item's links so an agent can see what
        an open item already references without a second round-trip. Both
        directions are reported; ``direction`` names the item's side.
        """
        ids = [artifact_id for artifact_id in artifact_ids if artifact_id]
        if not ids:
            return {}
        rows = (
            TraceLink.objects.filter(
                tenant_id=ctx.tenant_id,
            )
            .filter(Q(source_id__in=ids) | Q(target_id__in=ids))
            .order_by("id")
        )
        grouped: dict[UUID, list[dict[str, Any]]] = {}
        for link in rows:
            entry = {
                "id": str(link.id),
                "link_type": link.link_type,
                "source_id": str(link.source_id),
                "target_id": str(link.target_id),
            }
            if link.source_id in ids:
                grouped.setdefault(link.source_id, []).append(
                    {**entry, "direction": "downstream"}
                )
            if link.target_id in ids:
                grouped.setdefault(link.target_id, []).append(
                    {**entry, "direction": "upstream"}
                )
        return grouped

    # ---------- Soft delete / restore (G1.5) ----------

    @atomic_transaction
    def delete_work_item(
        self,
        item_id: UUID,
        ctx: AuthContext,
        *,
        change_reason: str = "",
        expected_version: int | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Soft-delete a work item (``DELETE`` semantics, G1.5 V2).

        The item is never hard-deleted: ``workflow.services.outdate`` flips
        ``Artifact.lifecycle_status`` and leaves the row (and its trace links,
        revisions and audit trail) intact. A preset that mandates a
        ``change_reason`` for writes rejects a reason-less delete here.

        Args:
            item_id: UUID of the work item.
            ctx: Resolved AuthContext.
            change_reason: Justification; required when the workspace preset
                says ``change_reason == "mandatory"``.
            expected_version: Caller's last-seen ``WorkItem.version``.
            actor: Optional free-text actor label.

        Returns:
            The soft-deleted ``WorkItem``.

        Raises:
            NotFoundError: No such item in the active tenant.
            ValidationError: The preset requires a change_reason.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        item = lock_for_version_check(
            WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        assert_expected_version(item, expected_version, entity_type="WorkItem")

        if not (change_reason or "").strip() and (
            get_preset_policy_service().is_change_reason_required(
                str(item.workspace_id)
            )
        ):
            raise ValidationError(
                "This workspace requires a change_reason for deleting a "
                "work item. Please describe why it is being deleted."
            )

        self._touch(item, actor=_actor_label(ctx, actor))
        item.save(update_fields=["last_activity_at", "last_actor", "modified_at"])
        self._bump_version(item)
        self._record_revision(item, ctx, change_reason=change_reason or "")

        from workflow.services import outdate

        outdate(
            item_id=item.id,
            item_type=WORK_ITEM_ITEM_TYPE,
            workspace_id=item.workspace_id,
            ctx=ctx,
            reason=change_reason or "deleted via work_item.delete",
        )
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type=WORK_ITEM_ITEM_TYPE,
            entity_id=item.id,
            change_reason=change_reason or None,
        )
        return item

    @atomic_transaction
    def restore_work_item(
        self,
        item_id: UUID,
        ctx: AuthContext,
        *,
        expected_version: int | None = None,
        actor: str = "",
    ) -> WorkItem:
        """Clear a work item's soft-delete flag (G1.5 V5).

        Restores the workflow state the item kept throughout (soft delete is an
        orthogonal flag, not a state).

        Args:
            item_id: UUID of the soft-deleted work item.
            ctx: Resolved AuthContext.
            expected_version: Caller's last-seen ``WorkItem.version``.
            actor: Optional free-text actor label.

        Returns:
            The restored ``WorkItem``.

        Raises:
            NotFoundError: No such item in the active tenant.
            ValidationError: The item is not soft-deleted.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        item = lock_for_version_check(
            WorkItem.objects.filter(id=item_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if item is None:
            raise NotFoundError(f"Work item {item_id} not found")
        assert_expected_version(item, expected_version, entity_type="WorkItem")

        from workflow.services import reactivate

        try:
            reactivate(
                item_id=item.id,
                item_type=WORK_ITEM_ITEM_TYPE,
                workspace_id=item.workspace_id,
                ctx=ctx,
            )
        except ValueError as exc:
            raise ValidationError(
                f"Work item {item_id} cannot be restored: {exc}."
            ) from exc

        self._touch(item, actor=_actor_label(ctx, actor))
        item.save(update_fields=["last_activity_at", "last_actor", "modified_at"])
        self._bump_version(item)
        self._record_revision(item, ctx, change_reason="restored")

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=WORK_ITEM_ITEM_TYPE,
            entity_id=item.id,
            change_reason="restored",
        )
        return item


__all__ = [
    "BLOCKED_STATE",
    "CLOSED_STATES",
    "WORK_ITEM_ITEM_TYPE",
    "WorkItemService",
]
