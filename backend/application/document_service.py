"""COMP-AS-023 DocumentService — document lifecycle, freeze and release gates.

leaf_id : COMP-AS-023 (Plan F F2-T4)
req_id  : REQ-L2-PL-004, REQ-L2-PL-010

The single write entry point (ADR-01) for the ``Document`` artifact introduced
in Plan F F2-T1 (#1374). A document is an ordinary artifact-backed entity, so
this service follows the established ``AdrService``/``GoalService`` shape —
backing ``Artifact`` + local ``uid`` + workflow initialisation + audit + a
recorded content revision — and adds only what ADR-026 makes specific:

* **Freeze (F-1/F-2/F-3).** Entering the release state (the state the
  workspace's Document workflow marks with ``state_meta.freeze_on_enter``)
  stamps ``frozen_at`` and ``frozen_fields``. From then on every write attempt
  on one of those fields is refused with ``FieldFrozenError`` (``409``
  ``FIELD_FROZEN``). Loom-owned fields — ``doc_date``, the backing artifact's
  ``custom_fields``, trace links, comments — stay writable (F-2).
* **Release gates (G-1…G-4).** The gates are a workflow precondition rule, not
  a service check (ADR-026 §4.2): ``workflow.precondition_rules.
  check_document_gates`` runs on the same transition. They therefore apply to
  *every* path into the release state, including a future direct REST/MCP
  transition, not only to :meth:`DocumentService.release`.
* **Re-opening (F-5).** ``Freigegeben -> In Prüfung`` lifts the freeze and
  increments ``Document.version`` by one. The released content stays provable
  through the ``ArtifactVersion`` snapshot recorded at release.
* **Soft delete (G1.5, ENT-G1 = A).** ``Document`` has no status column of its
  own: delete/restore go through the workflow engine's ``outdate``/
  ``reactivate`` escape hatch, which flips ``Artifact.lifecycle_status`` — the
  single soft-delete flag.

Optimistic locking (ADR-026 §9): ``expected_version`` is always the caller's
last-seen ``Document.version`` — the ETag source. It is deliberately **not**
forwarded to ``WorkflowFacade.transition`` as the ``WorkflowItemState``
revision: those are two different counters, and a client that read an ETag off
the document would otherwise get spurious 409s.

Out of scope here (later F2 tasks): REST/MCP exposure (T5/T6), outbox events
and indexer registration (T7), projection/adoption (F5). No event is emitted,
because ``DomainEventOutbox.EventType`` gains its ``DOCUMENT_*`` members in
T7 with their own choices migration — emitting an unknown type would silently
break every outbox consumer.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import F
from django.utils import timezone

from application.artifact_service import (
    _clean_custom_fields,
    clean_free_text_field,
    has_field_changes,
    snapshot_versioned_fields,
)
from application.artifact_version_service import ArtifactVersionService, snapshot_fields
from application.base import FieldFrozenError, NotFoundError, ServiceBase, ValidationError
from application.local_uid import generate_local_uid
from application.optimistic_lock import (
    assert_expected_version,
    lock_for_version_check,
)
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Tenant, Workspace
from persistence.transactions import atomic_transaction
from workflow import state_reader

logger = logging.getLogger(__name__)

#: Sentinel distinguishing "argument omitted" from "clear to None / {}".
_UNSET = object()

#: The workflow item type this service owns.
DOCUMENT_ITEM_TYPE = "Document"

#: F-1: the content fields a release freezes. ``doc_date`` is deliberately
#: absent — it is derived metadata, not authored content, and the spec's F-1
#: list does not name it. Everything outside this tuple stays writable while the
#: document is frozen (F-2): ``doc_date`` on ``pl_document``, the backing
#: Artifact's ``custom_fields`` (handled separately — it lives on
#: ``pl_artifact``), trace links, comments and item state. Item structure and
#: inline anchors join this tuple with F3.
FROZEN_FIELDS: tuple[str, ...] = ("title", "description", "body", "kind")

#: ``state_meta`` flag marking the release state (spec §4, F-1).
_FREEZE_STATE_META_KEY = "freeze_on_enter"

#: Title limit mirrors ``Document.title``'s ``max_length``.
_MAX_TITLE_LENGTH = 255

#: Human-readable fallback for the "no workflow configured" error.
_NO_WORKFLOW_MESSAGE = (
    "This workspace has no 'Document' workflow definition, so a document "
    "cannot be released or re-opened. Provision the workspace workflow first."
)


# ---------------------------------------------------------------------------
# Input validation (Plan E E2.4 "syntax gate", applied at the service boundary)
# ---------------------------------------------------------------------------


def _validate_title(title: str) -> None:
    """Reject a blank/whitespace-only or over-long title."""
    if not title or not title.strip():
        raise ValidationError("Document title is required")
    if len(title) > _MAX_TITLE_LENGTH:
        raise ValidationError(
            f"Document title must not exceed {_MAX_TITLE_LENGTH} characters"
        )


def _validate_kind(kind: str) -> None:
    """Reject a ``kind`` outside :class:`Document.Kind`."""
    if kind not in Document.Kind.values:
        raise ValidationError(
            f"Unknown document kind {kind!r}. Valid kinds: "
            f"{', '.join(Document.Kind.values)}"
        )


def _clean_body(body: str) -> str:
    """Apply the project free-text policy to the markdown body (#820).

    The REST layer's ``SanitizedCharField`` covers requests that pass through a
    DRF serializer; this service is also reachable from MCP and service calls
    (ADR-01), which never touch that seam. Rejecting markup/script URIs here is
    the same stored-XSS closure the sibling write paths apply.
    """
    cleaned = clean_free_text_field(body, "body")
    return cleaned or ""


def _document_snapshot(document: Document) -> dict[str, Any]:
    """Return a JSON-safe content snapshot of *document* for ``ArtifactVersion``.

    ``snapshot_fields`` reads the diffable field list verbatim; ``doc_date`` is
    the one ``date`` in it, and the version payload is a JSONField — an
    unserialisable value would turn every recorded revision into a 500. Storing
    the ISO-8601 string keeps the snapshot human-readable and stable.
    """
    payload = snapshot_fields(document, DOCUMENT_ITEM_TYPE)
    doc_date = payload.get("doc_date")
    if doc_date is not None:
        payload["doc_date"] = doc_date.isoformat()
    return payload


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------


class DocumentService(ServiceBase):
    """COMP-AS-023 — ``Document`` lifecycle, freeze enforcement and soft delete.

    leaf_id : COMP-AS-023 (Plan F F2-T4)
    req_id  : REQ-L2-PL-004, REQ-L2-PL-010
    """

    # ---------- Workflow helpers ----------

    @staticmethod
    def _workflow_json(workspace_id: UUID) -> dict:
        """Return the workspace's Document ``workflow_json`` (``{}`` if none)."""
        from workflow.services import get_workflow_json

        return get_workflow_json(workspace_id, DOCUMENT_ITEM_TYPE) or {}

    @classmethod
    def _resolve_release_state(cls, workspace_id: UUID) -> str | None:
        """Return the state flagged ``freeze_on_enter``, or ``None``.

        Resolution goes through ``state_meta`` rather than a hard-coded label
        (spec §4): a workspace that customised its Document lifecycle (ADR-06)
        may name the release state anything, and the freeze must follow it.
        ``None`` is fail-closed — the caller refuses the operation instead of
        guessing a state name.
        """
        from workflow.definition_store import get_state_meta

        workflow_json = cls._workflow_json(workspace_id)
        for state in workflow_json.get("states", []) or []:
            if get_state_meta(workflow_json, state).get(_FREEZE_STATE_META_KEY):
                return str(state)
        return None

    @classmethod
    def _resolve_rework_state(cls, workspace_id: UUID, release_state: str) -> str | None:
        """Return the single non-terminal target reachable from *release_state*.

        F-5 re-opens an approved document by moving it back into review. The
        target is derived from the workspace's own transitions (not hard-coded
        ``"In Prüfung"``), restricted to states that are not flagged
        ``is_outdated_equivalent`` (``Abgelöst``/``Archiviert`` would retire the
        document instead of re-opening it). More than one candidate is fail-closed
        (``None``): silently picking one could retire a document.
        """
        from workflow.definition_store import get_state_meta

        workflow_json = cls._workflow_json(workspace_id)
        candidates = {
            str(transition.get("to_state"))
            for transition in workflow_json.get("transitions", []) or []
            if transition.get("from_state") == release_state
            and transition.get("to_state") != release_state
            and not get_state_meta(
                workflow_json, str(transition.get("to_state"))
            ).get("is_outdated_equivalent")
        }
        if len(candidates) != 1:
            return None
        return candidates.pop()

    # ---------- Freeze helpers ----------

    @staticmethod
    def _assert_fields_writable(document: Document, supplied: set[str]) -> None:
        """Raise :class:`FieldFrozenError` for every frozen field in *supplied*.

        F-3 is a *write-attempt* rule, not a change-detection rule: even a value
        identical to the stored one is refused while the field is frozen, so a
        released document cannot be "rewritten" to its current value by a client
        that does not know it is frozen. The check is skipped when the document
        is not frozen (``frozen_at is None``), which is the case for drafts and
        for re-opened documents.
        """
        if document.frozen_at is None:
            return
        frozen = set(document.frozen_fields or [])
        offending = sorted(field for field in supplied if field in frozen)
        if not offending:
            return
        raise FieldFrozenError(
            "This document is released; its frozen field(s) cannot be changed: "
            + ", ".join(offending)
            + ". Re-open it (Freigegeben -> In Prüfung) to start a new version.",
            details=[{"field": field} for field in offending],
        )

    @staticmethod
    def _supplied_fields(
        *,
        title: str | None,
        kind: str | None,
        description: str | None,
        body: str | None,
        doc_date: object,
    ) -> set[str]:
        """Return the field names the caller actually supplied.

        ``None`` means "keep the current value" for the string fields (the
        module-wide PATCH idiom), so only a non-``None`` value counts. For
        ``doc_date`` the sentinel decides: an explicit ``None`` is a request to
        clear the date and therefore *is* a write.
        """
        supplied: set[str] = set()
        for name, value in (
            ("title", title),
            ("kind", kind),
            ("description", description),
            ("body", body),
        ):
            if value is not None:
                supplied.add(name)
        if doc_date is not _UNSET:
            supplied.add("doc_date")
        return supplied

    # ---------- Read ----------

    def get_document(self, document_id: UUID, ctx: AuthContext) -> Document:
        """Fetch one document (tenant-scoped).

        Soft-deleted documents are returned unchanged — G1.5 V3 makes "deleted"
        a flag on the backing artifact, and the transport layer reports it as
        ``status: "outdated"``. Hiding them here would make a re-activation
        endpoint unable to resolve its own subject.

        Raises:
            NotFoundError: No such document in the active tenant.
        """
        self._set_tenant_context(ctx)
        document = Document.objects.filter(
            id=document_id, tenant_id=ctx.tenant_id
        ).first()
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        return document

    def list_documents(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        *,
        include_deleted: bool = False,
    ) -> list[Document]:
        """List a workspace's documents, deterministically ordered (G1.5 V4).

        Sorted by ``-modified_at, id`` (the index ``idx_doc_workspace_modified``
        backs the first key; ``id`` makes ties stable — Plan G G2.1). Soft-deleted
        documents are omitted unless *include_deleted* is true.
        """
        self._set_tenant_context(ctx)
        from workflow.services import outdated_item_ids

        queryset = Document.objects.filter(
            workspace_id=workspace_id, tenant_id=ctx.tenant_id
        )
        if not include_deleted:
            queryset = queryset.exclude(
                id__in=outdated_item_ids(DOCUMENT_ITEM_TYPE, tenant_id=ctx.tenant_id)
            )
        return list(queryset.order_by("-modified_at", "id"))

    def current_status(self, document_id: UUID, ctx: AuthContext) -> str:
        """Return the document's workflow state (or its type's initial state)."""
        self._set_tenant_context(ctx)
        return state_reader.current_state(
            DOCUMENT_ITEM_TYPE, document_id
        ) or state_reader.initial_state(DOCUMENT_ITEM_TYPE)

    # ---------- Create ----------

    @atomic_transaction
    def create_document(
        self,
        workspace_id: UUID,
        ctx: AuthContext,
        *,
        title: str,
        kind: str,
        description: str = "",
        body: str = "",
        doc_date: date | None = None,
        uid: str | None = None,
        custom_fields: dict | None = None,
    ) -> Document:
        """Create a document with its backing artifact and workflow state.

        Args:
            workspace_id: Target workspace UUID.
            ctx: Resolved AuthContext (tenant + roles).
            title: Document title (required, ≤ 255 characters).
            kind: One of ``Document.Kind`` values.
            description: Optional purpose/summary (not the content).
            body: Markdown content.
            doc_date: Optional document date.
            uid: Explicit local identifier; allocated as ``DOC-NNN`` otherwise.
            custom_fields: Extended attributes persisted on the backing Artifact.

        Returns:
            The persisted ``Document`` (``version == 1``).

        Raises:
            PermissionDeniedError: The caller may not write.
            ValidationError: Blank title, unknown kind, markup/script URI in a
                free-text field, or invalid ``custom_fields``.
            NotFoundError: Tenant or workspace not found.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        _validate_title(title)
        _validate_kind(kind)
        clean_free_text_field(description, "description")
        _clean_body(body)

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")
        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=DOCUMENT_ITEM_TYPE,
            custom_fields=_clean_custom_fields(custom_fields),
        )
        document = Document.objects.create(
            artifact=artifact,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
            uid=uid or generate_local_uid(DOCUMENT_ITEM_TYPE, workspace_id),
            title=title,
            kind=kind,
            description=description,
            body=body,
            doc_date=doc_date,
        )

        # F-1/F-5 provenance: the initial content is revision 1 so a later
        # release snapshot has a baseline to differ against.
        ArtifactVersionService().record(
            document.artifact_id, _document_snapshot(document), ctx
        )

        # Every artifact type is initialised lazily at its definition's initial
        # state. A workspace provisioned before F2-T2 (or a unit test that skips
        # provisioning) has no definition; the document then reports the type's
        # initial state via the state_reader fallback and the release path refuses
        # with a clear message instead of silently writing nothing.
        try:
            from workflow.services import initialize_workflow_states

            initialize_workflow_states(
                item_ids=[document.id],
                item_type=DOCUMENT_ITEM_TYPE,
                workspace_id=workspace_id,
                ctx=ctx,
            )
        except Exception:  # noqa: BLE001 — best-effort, mirrors GoalService
            logger.warning(
                "DocumentService: workflow init skipped for document=%s",
                document.id,
                exc_info=True,
            )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type=DOCUMENT_ITEM_TYPE,
            entity_id=document.id,
        )
        return document

    # ---------- Update ----------

    @atomic_transaction
    def update_document(
        self,
        document_id: UUID,
        ctx: AuthContext,
        *,
        title: str | None = None,
        kind: str | None = None,
        description: str | None = None,
        body: str | None = None,
        doc_date: object = _UNSET,
        change_reason: str | None = None,
        custom_fields: object = _UNSET,
        expected_version: int | None = None,
    ) -> Document:
        """Update a document's editable fields (freeze-aware, version-guarded).

        Check order follows ADR-026 F-3 exactly: syntax validation, then the
        frozen-field gate, then the optimistic-lock compare. Freeze therefore
        wins over a stale version — a client that edits a released document
        learns *why* it may not, not merely that it raced someone.

        Args:
            document_id: UUID of the document.
            ctx: Resolved AuthContext.
            title: New title, or ``None`` to keep the current one.
            kind: New kind, or ``None`` to keep the current one.
            description: New summary, or ``None`` to keep the current one.
            body: New markdown content, or ``None`` to keep the current one.
            doc_date: New date; pass ``None`` explicitly to clear it. Omit the
                argument to leave it unchanged (F-2: ``doc_date`` stays writable
                while the document is frozen).
            change_reason: Audit reason, recorded on the revision and the log.
            custom_fields: Extended attributes on the backing Artifact. ``None``
                means "clear to ``{}``"; omit the argument to leave it unchanged.
            expected_version: Caller's last-seen ``Document.version``. When
                supplied and stale, the update is refused with
                ``OptimisticLockError`` (409).

        Returns:
            The refreshed ``Document``.

        Raises:
            NotFoundError: No such document in the active tenant.
            FieldFrozenError: A supplied field is frozen (409 ``FIELD_FROZEN``).
            OptimisticLockError: *expected_version* does not match.
            ValidationError: Invalid input, or an unsupported field.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        # Syntax gate first (Plan E E2.4), before any lock or write.
        if title is not None:
            _validate_title(title)
        if kind is not None:
            _validate_kind(kind)
        if description is not None:
            clean_free_text_field(description, "description")
        if body is not None:
            _clean_body(body)

        supplied = self._supplied_fields(
            title=title,
            kind=kind,
            description=description,
            body=body,
            doc_date=doc_date,
        )

        document = lock_for_version_check(
            Document.objects.filter(id=document_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")

        # F-3 before the version compare (ADR-026 F-3 ordering).
        self._assert_fields_writable(document, supplied)
        assert_expected_version(document, expected_version, entity_type="Document")

        before = snapshot_versioned_fields(document)
        custom_fields_changed = False

        if title is not None:
            document.title = title
        if kind is not None:
            document.kind = kind
        if description is not None:
            document.description = description
        if body is not None:
            document.body = body
        if doc_date is not _UNSET:
            document.doc_date = doc_date

        if custom_fields is not _UNSET:
            cleaned = _clean_custom_fields(custom_fields)
            custom_fields_changed = cleaned != (document.artifact.custom_fields or {})
            document.artifact.custom_fields = cleaned
            document.artifact.save(update_fields=["custom_fields", "modified_at"])

        document.save()
        if has_field_changes(document, before) or custom_fields_changed:
            # Atomic DB-side increment (REQ-L3-PL001-002) — never ``version += 1``
            # on a read-modify-write, which is exactly the lost update this
            # counter exists to detect.
            Document.objects.filter(id=document.id).update(version=F("version") + 1)
            document.refresh_from_db(fields=["version"])
            ArtifactVersionService().record(
                document.artifact_id,
                _document_snapshot(document),
                ctx,
                change_reason=change_reason or "",
            )

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=DOCUMENT_ITEM_TYPE,
            entity_id=document.id,
            change_reason=change_reason,
        )
        return document

    # ---------- Release / re-open ----------

    @atomic_transaction
    def transition_status(
        self,
        document_id: UUID,
        target_state: str,
        ctx: AuthContext,
        *,
        change_reason: str = "",
        credential: str = "",
        expected_version: int | None = None,
    ) -> Document:
        """Move a document through its workflow, applying the freeze effects.

        The single path every state change takes, so the F-1/F-5 side effects
        cannot be bypassed by a caller that uses the generic transition instead
        of :meth:`release`/:meth:`reopen` (the shape :class:`AdrService` and
        :class:`GoalService` already publish for their REST/MCP transition
        endpoints):

        * on entering the release state (``state_meta.freeze_on_enter``):
          :meth:`release`'s freeze is applied and the approved content is
          snapshotted as an ``ArtifactVersion`` revision (F-1, F-5);
        * on leaving the release state for its rework state: the freeze is
          lifted and ``Document.version`` is incremented (F-5);
        * leaving for a terminal state (``Abgelöst``/``Archiviert``) keeps the
          freeze — a superseded release stays frozen (F-6).

        The gates G-1…G-4 are enforced by the workflow validator on the same
        transition, so they apply here as well.

        Args:
            document_id: UUID of the document.
            target_state: Requested workflow state.
            ctx: Resolved AuthContext.
            change_reason: Reason recorded on the transition/revision.
            credential: Password/TOTP token for signature-gated transitions.
            expected_version: Caller's last-seen ``Document.version`` (the ETag
                source). Not forwarded to the workflow engine — its counter is
                a different one, and mixing the two would answer spurious 409s.

        Returns:
            The refreshed ``Document``.

        Raises:
            NotFoundError: No such document in the active tenant.
            ValidationError: Transition rejected by the workflow engine.
            DocumentGateFailedError: A release gate is not satisfied.
            PermissionDeniedError: Role gate blocked the move.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        document = lock_for_version_check(
            Document.objects.filter(id=document_id, tenant_id=ctx.tenant_id),
            expected_version,
        ).first()
        if document is None:
            raise NotFoundError(f"Document {document_id} not found")
        assert_expected_version(document, expected_version, entity_type="Document")

        release_state = self._resolve_release_state(document.workspace_id)
        previous_state = state_reader.current_state(DOCUMENT_ITEM_TYPE, document.id)

        from application.workflow_facade import WorkflowFacade

        WorkflowFacade().transition(
            item_id=document.id,
            item_type=DOCUMENT_ITEM_TYPE,
            target_state=target_state,
            workspace_id=document.workspace_id,
            ctx=ctx,
            change_reason=change_reason,
            credential=credential,
        )

        new_state = state_reader.current_state(DOCUMENT_ITEM_TYPE, document.id)

        if release_state is not None and new_state == release_state:
            document.frozen_at = timezone.now()
            document.frozen_fields = list(FROZEN_FIELDS)
            document.save(
                update_fields=["frozen_at", "frozen_fields", "modified_at"]
            )
            # F-5 provenance: the approved content becomes an append-only
            # revision, which keeps it provable after a later re-open.
            ArtifactVersionService().record(
                document.artifact_id,
                _document_snapshot(document),
                ctx,
                change_reason=change_reason or "released",
            )
        elif (
            release_state is not None
            and previous_state == release_state
            and new_state == self._resolve_rework_state(
                document.workspace_id, release_state
            )
        ):
            document.frozen_at = None
            document.frozen_fields = []
            document.save(
                update_fields=["frozen_at", "frozen_fields", "modified_at"]
            )
            # F-5: a re-open is version v+1. The workflow transition bumps its
            # own ``WorkflowItemState`` counter, which is a different axis.
            Document.objects.filter(id=document.id).update(version=F("version") + 1)
            document.refresh_from_db(fields=["version"])
        return document

    @atomic_transaction
    def release(
        self,
        document_id: UUID,
        ctx: AuthContext,
        *,
        change_reason: str = "",
        expected_version: int | None = None,
    ) -> Document:
        """Approve a document: enter the release state and freeze its content.

        Thin wrapper over :meth:`transition_status` that resolves the release
        state from the workspace's workflow (``state_meta.freeze_on_enter``) and
        fails closed when the workspace has none. The gate check is rule 9 of the
        workflow validator, so this method cannot bypass G-1…G-4 — and neither
        can a direct transition.

        Args:
            document_id: UUID of the document.
            ctx: Resolved AuthContext.
            change_reason: Required by the ``document_default`` release
                transition.
            expected_version: Caller's last-seen ``Document.version``.

        Returns:
            The released ``Document`` with ``frozen_at``/``frozen_fields`` set.

        Raises:
            NotFoundError: No such document in the active tenant.
            ValidationError: No Document workflow / no state flagged
                ``freeze_on_enter``, or the transition itself is rejected.
            DocumentGateFailedError: G-1…G-4 not satisfied.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        document = self.get_document(document_id, ctx)
        release_state = self._resolve_release_state(document.workspace_id)
        if release_state is None:
            raise ValidationError(_NO_WORKFLOW_MESSAGE)
        return self.transition_status(
            document.id,
            release_state,
            ctx,
            change_reason=change_reason,
            expected_version=expected_version,
        )

    @atomic_transaction
    def reopen(
        self,
        document_id: UUID,
        ctx: AuthContext,
        *,
        change_reason: str = "",
        expected_version: int | None = None,
    ) -> Document:
        """Re-open a released document (``Freigegeben -> In Prüfung``, F-5).

        Thin wrapper over :meth:`transition_status`; lifts the freeze and
        increments ``Document.version`` by one, so a re-open is a new version of
        the document rather than a silent edit of the released one. The released
        content stays retrievable from the ``ArtifactVersion`` snapshot written
        on release.

        Args:
            document_id: UUID of the released document.
            ctx: Resolved AuthContext.
            change_reason: Required by the ``document_default`` re-open
                transition (the "why is the release withdrawn" rationale).
            expected_version: Caller's last-seen ``Document.version``.

        Returns:
            The re-opened ``Document`` (freeze cleared, ``version`` + 1).

        Raises:
            NotFoundError: No such document in the active tenant.
            ValidationError: The document is not released, or its workflow has
                no unambiguous re-open target.
            OptimisticLockError: *expected_version* does not match.
        """
        self._set_tenant_context(ctx)
        document = self.get_document(document_id, ctx)
        release_state = self._resolve_release_state(document.workspace_id)
        if release_state is None:
            raise ValidationError(_NO_WORKFLOW_MESSAGE)

        rework_state = self._resolve_rework_state(document.workspace_id, release_state)
        if rework_state is None:
            raise ValidationError(
                "This workspace's Document workflow has no unambiguous state to "
                f"re-open into from {release_state!r}. Move the document with an "
                "explicit workflow transition instead."
            )
        return self.transition_status(
            document.id,
            rework_state,
            ctx,
            change_reason=change_reason,
            expected_version=expected_version,
        )

    # ---------- Soft delete / restore (G1.5) ----------

    @atomic_transaction
    def delete_document(
        self,
        document_id: UUID,
        ctx: AuthContext,
        *,
        change_reason: str = "",
    ) -> Document:
        """Soft-delete a document (``DELETE`` semantics, G1.5 V2).

        The document is never hard-deleted: ``workflow.services.outdate`` flips
        ``Artifact.lifecycle_status`` and leaves the row (and its trace links,
        revisions and audit trail) intact. A preset that mandates a
        ``change_reason`` for writes rejects a reason-less delete here, so the
        REST/MCP layers only have to forward the value — the gate lives in the
        service (ADR-01).

        Args:
            document_id: UUID of the document.
            ctx: Resolved AuthContext.
            change_reason: Justification; required when the workspace preset
                says ``change_reason == "mandatory"``.

        Returns:
            The soft-deleted ``Document``.

        Raises:
            NotFoundError: No such document in the active tenant.
            ValidationError: The preset requires a change_reason.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        document = self.get_document(document_id, ctx)
        if not (change_reason or "").strip():
            from application.preset_policy_service import get_preset_policy_service

            if get_preset_policy_service().is_change_reason_required(
                str(document.workspace_id)
            ):
                raise ValidationError(
                    "This workspace requires a change_reason for deleting a "
                    "document. Please describe why it is being deleted."
                )

        from workflow.services import outdate

        outdate(
            item_id=document.id,
            item_type=DOCUMENT_ITEM_TYPE,
            workspace_id=document.workspace_id,
            ctx=ctx,
            reason=change_reason or "deleted via document.delete",
        )
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type=DOCUMENT_ITEM_TYPE,
            entity_id=document.id,
            change_reason=change_reason or None,
        )
        return document

    @atomic_transaction
    def restore_document(self, document_id: UUID, ctx: AuthContext) -> Document:
        """Clear a document's soft-delete flag (G1.5 V5).

        Restores the workflow state the document kept throughout (soft delete is
        an orthogonal flag, not a state), so a previously released document comes
        back released *and still frozen*.

        Args:
            document_id: UUID of the soft-deleted document.
            ctx: Resolved AuthContext.

        Returns:
            The restored ``Document``.

        Raises:
            NotFoundError: No such document in the active tenant.
            ValidationError: The document is not soft-deleted.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        document = self.get_document(document_id, ctx)

        from workflow.services import reactivate

        try:
            reactivate(
                item_id=document.id,
                item_type=DOCUMENT_ITEM_TYPE,
                workspace_id=document.workspace_id,
                ctx=ctx,
            )
        except ValueError as exc:
            # ``reactivate`` raises a bare ValueError both for "no backing
            # artifact" (impossible here) and "not outdated" (a client error).
            raise ValidationError(
                f"Document {document_id} cannot be restored: {exc}."
            ) from exc

        self._audit(
            ctx=ctx,
            operation="update",
            entity_type=DOCUMENT_ITEM_TYPE,
            entity_id=document.id,
            change_reason="restored",
        )
        return document


__all__ = [
    "DOCUMENT_ITEM_TYPE",
    "FROZEN_FIELDS",
    "DocumentService",
]
