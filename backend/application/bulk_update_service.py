"""COMP-AS-048 BulkUpdateService — transactional multi-artifact write (R3.1).

leaf_id : COMP-AS-048
req_id  : REQ-L2-AS-001 (single entry point), REQ-L2-AS-018 (ACID),
          REQ-L2-AS-021 (auth), REQ-L2-AS-004 (optimistic lock)

One request, many artifacts, **all or nothing**. The editable document view (and
the table view it shares this contract with) saves a page of rows at once; a
per-row PATCH loop would leave the user with a half-saved page and no way to tell
which half. This service is that batch write path:

* :meth:`BulkUpdateService.apply` takes the entries, resolves each
  ``artifact_id`` to its typed row and calls **that type's own service** — the
  dispatch table is explicit, never a generic ``ArtifactService.update_artifact``
  (the generic path cannot write content fields such as a document ``body``).
* A single failure aborts: the enclosing transaction is rolled back, so a batch
  with one bad entry writes *nothing*, and the result names the offending entry
  by ``index`` so the client can mark the row instead of re-reading the page.

Nothing is pre-validated field by field. The typed services are the truth: they
own the freeze gate, the change-reason policy, the syntax rules and the
optimistic-lock compare, and running those twice in two places is how the two
answers eventually disagree. The only checks here are the ones a service cannot
make, because they are about the *batch*:

* the shape and size of the entry list (:data:`MAX_ENTRIES`),
* whether the target artifact exists, is in the requested workspace, and has a
  type this service knows how to write,
* whether the field names an entry sends are ones the type's update method
  actually accepts (otherwise the service call would raise ``TypeError`` — a
  500 for a client typo, the exact silent-drop class issue #851 closed for REST).

Contract (see ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``
and ``docs/superpowers/specs/2026-11-14-document-view-on-document-design.md``)::

    BulkEntry(artifact_id, expected_version, fields)
    BulkUpdateResult(updated=[{artifact_id, version}], errors=[{index, artifact_id,
                     code, message, field?}])

Error codes are the ones the transports already publish, so REST/MCP map them
without a second vocabulary: ``NOT_FOUND``, ``WORKSPACE_MISMATCH``,
``UNSUPPORTED_ARTIFACT_TYPE``, ``UNKNOWN_FIELD``, ``CONFLICT`` (stale
``expected_version``), ``FIELD_FROZEN``, ``WORKFLOW_FROZEN``,
``PERMISSION_DENIED``, ``VALIDATION_ERROR``.

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/
    L2_ApplicationServiceSystem_Architecture.md  (ADR-AS-01 single entry point)
"""
from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import transaction

from application.base import (
    FieldFrozenError,
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
    WorkflowFrozenError,
)
from application.document_service import DocumentService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Document, Requirement
from persistence.transactions import atomic_transaction

logger = logging.getLogger(__name__)

#: Upper bound for one batch. A page of an editable document / table is a few
#: dozen rows; 100 is generous enough for a "select all on this page" flow while
#: keeping the write transaction short enough that a conflict stays an exception
#: rather than the normal case. Over the limit is a *request* defect (400), not a
#: business conflict.
MAX_ENTRIES: int = 100

#: ``item_type`` -> the unbound write method of the service that owns that type.
#:
#: Deliberately explicit and deliberately short: a type joins the bulk surface
#: only together with its own service. There is **no** fallback to
#: ``ArtifactService.update_artifact`` — the generic path writes artifact
#: metadata, not the content fields an editor sends, so a silent fallback would
#: answer 200 for a write that changed nothing.
UPDATE_DISPATCH: Mapping[str, Callable[..., Any]] = {
    "Document": DocumentService.update_document,
    "Requirement": RequirementService.update_requirement,
}

#: ``item_type`` -> the service instance factory for :data:`UPDATE_DISPATCH`.
_SERVICE_FACTORY: Mapping[str, Callable[[], ServiceBase]] = {
    "Document": DocumentService,
    "Requirement": RequirementService,
}

#: ``item_type`` -> the typed row model backing the artifact. Used to translate
#: the caller-facing ``artifact_id`` into the id its service expects.
_ITEM_MODEL: Mapping[str, Any] = {
    "Document": Document,
    "Requirement": Requirement,
}

#: Dispatch argument names an entry may **not** set: the target id and the auth
#: context are positional, ``expected_version`` comes from the entry itself (a
#: second, contradicting value inside ``fields`` would be ambiguous), and ``self``
#: is bound by the call.
_RESERVED_FIELDS: frozenset[str] = frozenset(
    {"self", "ctx", "expected_version", "document_id", "requirement_id"}
)


def _accepted_fields(update: Callable[..., Any]) -> frozenset[str]:
    """Return the keyword names *update* accepts, minus :data:`_RESERVED_FIELDS`."""
    return frozenset(
        name
        for name, parameter in inspect.signature(update).parameters.items()
        if name not in _RESERVED_FIELDS
        and parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    )


#: ``item_type`` -> the field names its update method accepts. Built once at
#: import time from the real signatures, so adding a parameter to a service
#: immediately accepts it here and a removed one stops being accepted.
ACCEPTED_FIELDS: Mapping[str, frozenset[str]] = {
    item_type: _accepted_fields(update) for item_type, update in UPDATE_DISPATCH.items()
}


@dataclass(frozen=True)
class BulkEntry:
    """One requested write: which artifact, at which version, with which fields.

    Attributes:
        artifact_id: UUID of the backing ``Artifact`` (the id every transport and
            trace link uses, *not* the typed row's own id).
        expected_version: Caller's last-seen ``version`` of the typed row. Stale
            means "someone else wrote in between" and aborts the whole batch with
            ``CONFLICT``.
        fields: Service keyword arguments, e.g. ``{"title": "...", "body": "..."}``
            — ``change_reason`` and ``custom_fields`` included when the caller
            needs them.
    """

    artifact_id: UUID
    expected_version: int
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class BulkUpdateResult:
    """Outcome of :meth:`BulkUpdateService.apply`.

    ``updated`` is empty whenever ``errors`` is non-empty — the transaction was
    rolled back, so claiming a partial success would be a lie.
    """

    updated: tuple[Mapping[str, Any], ...]
    errors: tuple[Mapping[str, Any], ...]

    @property
    def ok(self) -> bool:
        """True when every entry was written."""
        return not self.errors

    def to_dict(self) -> dict[str, list[Mapping[str, Any]]]:
        """Return the transport payload (``{"updated": [...], "errors": [...]}``)."""
        return {"updated": list(self.updated), "errors": list(self.errors)}


class _EntryRejected(Exception):
    """Internal: one entry cannot be written; carries its public error payload."""

    def __init__(
        self, code: str, message: str, *, field: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _error_payload(
    index: int,
    artifact_id: UUID | None,
    code: str,
    message: str,
    *,
    field: str | None = None,
) -> dict[str, Any]:
    """Build one ``errors[]`` entry (the shape both transports publish)."""
    payload: dict[str, Any] = {
        "index": index,
        "artifact_id": str(artifact_id) if artifact_id is not None else None,
        "code": code,
        "message": message,
    }
    if field is not None:
        payload["field"] = field
    return payload


def _first_field(details: Any) -> str | None:
    """Return the first offending field name from a domain error's ``details``.

    ``FieldFrozenError`` carries ``[{"field": "title"}, …]`` and the attribute
    gateway's ``ValidationError`` carries ``[{"field": …, "errors": […]}]``; both
    let the client highlight the input instead of only showing a sentence.
    """
    if isinstance(details, list):
        for item in details:
            if isinstance(item, Mapping) and item.get("field"):
                return str(item["field"])
    if isinstance(details, Mapping) and details.get("field"):
        return str(details["field"])
    return None


def _entry_error(index: int, entry: Any, exc: Exception) -> dict[str, Any]:
    """Translate a typed-service exception into its ``errors[]`` entry.

    The mapping is by ``isinstance`` in specificity order because most of these
    are ``ValidationError`` subclasses that carry their own code; the exact-type
    dispatch used by the REST error table does not apply here (this is a
    per-entry report, not a response status).
    """
    artifact_id = getattr(entry, "artifact_id", None)
    if isinstance(exc, OptimisticLockError):
        return _error_payload(index, artifact_id, "CONFLICT", str(exc))
    if isinstance(exc, FieldFrozenError):
        return _error_payload(
            index,
            artifact_id,
            "FIELD_FROZEN",
            str(exc),
            field=_first_field(getattr(exc, "details", None)),
        )
    if isinstance(exc, WorkflowFrozenError):
        return _error_payload(index, artifact_id, "WORKFLOW_FROZEN", str(exc))
    if isinstance(exc, PermissionDeniedError):
        return _error_payload(index, artifact_id, "PERMISSION_DENIED", str(exc))
    if isinstance(exc, NotFoundError):
        return _error_payload(index, artifact_id, "NOT_FOUND", str(exc))
    if isinstance(exc, ValidationError):
        return _error_payload(
            index,
            artifact_id,
            "VALIDATION_ERROR",
            str(exc),
            field=_first_field(getattr(exc, "details", None)),
        )
    # Not a domain refusal: a bug, not a caller error. Let it escape so the
    # transaction rolls back and the defect is visible instead of being reported
    # as a tidy per-entry message.
    raise exc


class BulkUpdateService(ServiceBase):
    """Transactional batch write across the types named in :data:`UPDATE_DISPATCH`."""

    @atomic_transaction
    def apply(
        self,
        workspace_id: UUID,
        entries: Sequence[BulkEntry],
        ctx: AuthContext,
    ) -> BulkUpdateResult:
        """Write every entry or nothing at all.

        Args:
            workspace_id: Workspace every entry must belong to. An entry naming an
                artifact of another workspace is refused (``WORKSPACE_MISMATCH``)
                rather than silently written: one request must not span two
                workspaces, or the RBAC gate it passed would not describe it.
            entries: 1..:data:`MAX_ENTRIES` :class:`BulkEntry` values.
            ctx: Resolved AuthContext of the caller.

        Returns:
            :class:`BulkUpdateResult`. ``errors`` empty means every entry was
            written and ``updated`` carries the new versions.

        Raises:
            ValidationError: The entry list is empty, longer than
                :data:`MAX_ENTRIES`, or not made of :class:`BulkEntry` values
                (400 at REST).
            PermissionDeniedError: The caller holds no write role at all (403).
        """
        self._set_tenant_context(ctx)
        # Coarse gate first: a caller who may not write anywhere gets a 403
        # instead of a batch-wide entry report. Per-artifact item-level rules are
        # enforced by the typed services (and surface as a per-entry error).
        self._assert_write_permission(ctx)

        checked = self._validate_entries(entries)

        # Pre-flight: resolve every target before the first write. Structural
        # problems (unknown artifact, foreign workspace, type without a service,
        # a field name the service does not accept) are collected for the whole
        # batch, so the client learns about all of them at once instead of
        # one-per-round-trip.
        errors: list[dict[str, Any]] = []
        resolved: list[tuple[int, BulkEntry, str, UUID]] = []
        for index, entry in enumerate(checked):
            try:
                item_type, row_id = self._resolve_target(index, entry, workspace_id, ctx)
            except _EntryRejected as rejected:
                errors.append(
                    _error_payload(
                        index,
                        entry.artifact_id,
                        rejected.code,
                        rejected.message,
                        field=rejected.field,
                    )
                )
                continue
            resolved.append((index, entry, item_type, row_id))

        if errors:
            # Nothing has been written yet; the batch is refused as a whole.
            return BulkUpdateResult(updated=(), errors=tuple(errors))

        services: dict[str, ServiceBase] = {}
        updated: list[Mapping[str, Any]] = []
        for index, entry, item_type, row_id in resolved:
            service = services.get(item_type)
            if service is None:
                service = _SERVICE_FACTORY[item_type]()
                services[item_type] = service
            try:
                item = UPDATE_DISPATCH[item_type](
                    service,
                    row_id,
                    ctx,
                    expected_version=entry.expected_version,
                    **entry.fields,
                )
            except Exception as exc:  # noqa: BLE001 — classified by _entry_error
                # First failure aborts the batch: everything written so far (and
                # the failing call's own rolled-back savepoint) is discarded by
                # marking the outer transaction for rollback. No further query
                # runs after this point, which is what makes set_rollback safe.
                errors.append(_entry_error(index, entry, exc))
                transaction.set_rollback(True)
                return BulkUpdateResult(updated=(), errors=tuple(errors))
            updated.append(
                {"artifact_id": str(item.artifact_id), "version": item.version}
            )

        return BulkUpdateResult(updated=tuple(updated), errors=())

    # ------------------------------------------------------------------
    # Batch-level validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_entries(entries: Sequence[BulkEntry]) -> list[BulkEntry]:
        """Return the entries as a list, or raise the 400-class validation error."""
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            raise ValidationError("entries must be a list of bulk entries")
        checked = list(entries)
        if not checked:
            raise ValidationError("entries must not be empty")
        if len(checked) > MAX_ENTRIES:
            raise ValidationError(
                f"entries must not contain more than {MAX_ENTRIES} items "
                f"(got {len(checked)})"
            )
        for position, entry in enumerate(checked):
            if not isinstance(entry, BulkEntry):
                raise ValidationError(
                    f"entries[{position}] is not a BulkEntry"
                )
        return checked

    # ------------------------------------------------------------------
    # Target resolution
    # ------------------------------------------------------------------

    def _resolve_target(
        self,
        index: int,
        entry: BulkEntry,
        workspace_id: UUID,
        ctx: AuthContext,
    ) -> tuple[str, UUID]:
        """Return ``(item_type, typed_row_id)`` for *entry*, or raise ``_EntryRejected``.

        Tenant isolation comes from the armed tenant context (``Artifact`` is a
        ``TenantScopedModel``); the workspace compare is explicit so a foreign
        workspace answers ``WORKSPACE_MISMATCH`` rather than a misleading 404.
        """
        artifact = (
            Artifact.objects.filter(id=entry.artifact_id, tenant_id=ctx.tenant_id)
            .only("id", "artifact_type", "workspace_id")
            .first()
        )
        if artifact is None:
            raise _EntryRejected(
                "NOT_FOUND", f"Artifact {entry.artifact_id} not found"
            )
        if artifact.workspace_id != workspace_id:
            raise _EntryRejected(
                "WORKSPACE_MISMATCH",
                f"Artifact {entry.artifact_id} does not belong to workspace "
                f"{workspace_id}",
            )

        item_type = artifact.artifact_type
        if item_type not in UPDATE_DISPATCH:
            raise _EntryRejected(
                "UNSUPPORTED_ARTIFACT_TYPE",
                f"Artifact type '{item_type}' does not support bulk update",
            )

        # A name the type's update method does not accept would otherwise raise
        # TypeError inside the service — a 500 for a client typo, and the exact
        # "silently wrong or crash" gap #851 closed on the REST side. Values are
        # still the service's business; only the names are checked here.
        unknown = sorted(set(entry.fields) - ACCEPTED_FIELDS[item_type])
        if unknown:
            raise _EntryRejected(
                "UNKNOWN_FIELD",
                f"'{item_type}' does not accept the field(s) "
                f"{', '.join(unknown)}",
                field=unknown[0],
            )

        row_id = (
            _ITEM_MODEL[item_type]
            .objects.filter(artifact_id=artifact.id, tenant_id=ctx.tenant_id)
            .values_list("id", flat=True)
            .first()
        )
        if row_id is None:
            # An artifact without its typed row is a data defect, not a caller
            # error — but it is still this entry that cannot be written.
            raise _EntryRejected(
                "NOT_FOUND",
                f"No {item_type} row backs artifact {entry.artifact_id}",
            )
        logger.debug(
            "bulk update: entry %s -> %s %s (workspace %s)",
            index,
            item_type,
            row_id,
            workspace_id,
        )
        return item_type, row_id


__all__ = [
    "ACCEPTED_FIELDS",
    "MAX_ENTRIES",
    "UPDATE_DISPATCH",
    "BulkEntry",
    "BulkUpdateResult",
    "BulkUpdateService",
]
