"""
COMP-AS-008b ReqifImportService — ReqIF 1.2 import (REQ-147).

leaf_id : COMP-AS-008b (ImportService family sibling application.import_service,
          counterpart to COMP-AS-008 application.reqif_export_service)
req_id  : REQ-147 (ReqIF 1.2 import — DOORS/Polarion interoperability)

Imports a ReqIF 1.2 XML document into a workspace's StakeholderNeeds,
Requirements, and TraceLinks, inverting the mapping documented in
``application.reqif_export_service`` (which this module intentionally shares
the ``_ATTR_*`` / ``_SPEC_OBJECT_TYPE_*`` identifier constants and the
``_artifact_spec_object_id`` scheme with, to keep both directions in lock
step). Built on the same ``reqif`` PyPI package (StrictDoc project,
Apache-2.0) used for export.

Upsert semantics
=================
SPEC-OBJECT IDENTIFIER is expected in the export's ``_<Artifact.id>`` form
(a leading underscore followed by a UUID — XML NCNames cannot start with a
digit, see ``reqif_export_service._artifact_spec_object_id``):

  - Identifier parses to a UUID that matches an existing Artifact in *this*
    workspace (same tenant) -> UPDATE that Need/Requirement's mapped fields.
  - Identifier does not parse as a UUID, or parses but does not match any
    Artifact in this workspace -> CREATE a new artifact.
  - Identifier parses to a UUID that matches an Artifact in a *different*
    workspace (same tenant) -> that artifact belongs to someone else; it is
    NEVER touched. A new artifact is created with a **fresh** random UUID
    instead (the original id cannot be reused — it is already an existing
    primary key), and a note is added to the report's ``warnings``. The same
    fallback (via an ``IntegrityError`` catch on ``Artifact.objects.create``)
    also covers the — with random UUIDv4s astronomically unlikely, but
    handled defensively — case of a collision with a row in a different
    tenant, which row-level tenant scoping makes invisible to the query above.
  - SPEC-OBJECT-TYPE outside {``ST-StakeholderNeed``, ``ST-Requirement``} is
    out of scope for REQ-147 (mirrors REQ-146's export scope): skipped, noted
    in ``warnings``, no DB write.
  - An identifier that resolves to an existing Artifact of the *other* kind
    (e.g. a Requirement identifier now pointing at what is a StakeholderNeed
    row) is a per-object *failure*: the object is not imported, it counts
    under the owning entity kind's ``failed`` and is reported in its
    ``errors``. Import continues with the remaining objects.

Status handling (REQ-143 — status is a read-only workflow mirror)
===================================================================
``status`` must never be written as an ordinary field update through this
service; that would bypass the WorkflowEngine, which is the ADR-status-
single-source single source of truth (docs/architecture/ADR-status-single-
source.md). Instead, ``_apply_status`` reproduces **exactly** the mapping
performed by ``workflow/migrations/0003_reconcile_status_mirror.py``
(``reconcile_status_mirror`` / ``_map_status``):

  1. A ``WorkflowEngineDefinition`` exists for this workspace/item_type
     -> the imported status is mapped onto one of the definition's
     ``workflow_json["states"]`` (kept if valid, else the definition's first
     / initial state) and a ``WorkflowItemState`` row is created or updated
     to mirror it.
  2. No definition exists -> the imported status is only normalised against
     the global known-state set (``draft``, ``in_review``, ``approved``,
     ``deprecated``, ``done``); anything else becomes ``"draft"``. No
     ``WorkflowItemState`` row is created (its FK to the definition is
     ``PROTECT`` and requires one to exist, same constraint the migration
     documents).

Unknown attributes
===================
Any SPEC-OBJECT attribute whose ``definition_ref`` is not one of the mapped
ATTR-* identifiers (see ``reqif_export_service`` module docstring's mapping
table) is merged into ``Artifact.custom_fields`` under its SPEC-ATTRIBUTE-
DEFINITION long-name (falling back to the raw ``definition_ref`` if no
long-name is declared for it). ``ATTR-CUSTOM-FIELDS`` (ReqFlow's own
JSON-encoded custom_fields payload) is parsed and merged in first; unknown
attributes are layered on top.

Hierarchy
==========
SPEC-HIERARCHY nesting (under each SPECIFICATION's ``children``) is applied
as ``Artifact.parent`` within the workspace. A hierarchy node whose
SPEC-OBJECT-REF was skipped (unknown type / soft error) is transparently
elided — its own children attach to the nearest ancestor that *was*
imported, mirroring the "nearest exported ancestor" collapsing the exporter
performs in the opposite direction.

Relations
==========
SPEC-RELATIONs become TraceLinks, resolved via the SPEC-RELATION-TYPE's
long-name (falling back to stripping the ``SRT-`` prefix, then the raw ref)
to recover the canonical ``traceability.types.LinkType`` value. A relation
whose source or target identifier was not imported (skipped SPEC-OBJECT, or
simply absent from the document) is skipped and reported — never a hard
error. Upsert is by the ``(tenant, source, target, link_type)`` tuple via
``get_or_create`` so re-importing the same document is idempotent (no
duplicate TraceLinks).

Dry-run
========
``import_reqif(..., dry_run=True)`` runs the *entire* pipeline (parsing,
upserts, hierarchy, relations, status/workflow reconciliation) inside a
transaction and then calls ``transaction.set_rollback(True)`` instead of
letting it commit — the returned report is identical in shape and content to
a real run, but nothing is persisted.

Atomicity
==========
Hard errors are raised *before* — or immediately unwind — the transaction, so
nothing is written. They are split by the REST layer (ADR-014 §2): request-level
problems (0-byte/empty body, size/object-count guard, unreadable body) map to
**400**; a file-level parse/structural error (``ReqifParseError``, cause
``PARSE_ERROR``) maps to **422** (REQ-L2-RQ-001 AC5). Per-object/per-relation
errors (bad type, oversized field, missing endpoint, persistence conflict, ...)
are caught around a per-item ``transaction.atomic()`` savepoint so one bad
SPEC-OBJECT/SPEC-RELATION cannot poison the surrounding transaction — the rest
of the document still imports.

A SPEC-OBJECT that cannot be imported because of invalid data or a
persistence conflict counts as ``failed`` (it was *meant* to import); a
SPEC-RELATION that is intentionally not imported (endpoint absent from the
document, unknown link type) counts as ``skipped``. The import as a whole is
successful only when no object failed: ``success ⇔ counts.failed == 0`` across
all three entity kinds (AUD-2026-09-071; see ``ReqifImportResult.success``).

ReqIF upsert / dedupe (ADR-014 §3)
==================================
A SPEC-OBJECT that matches an existing Artifact over the identifier triad
(``_<Artifact.id>`` -> ``reqif_uid`` -> ``reqif_identifier``) is an **upsert**:
divergent content is an update (``succeeded``), *identical* content is an
idempotent no-op (``skipped`` with ``cause.code = DUPLICATE``, no write
effect). ``duplicate_policy`` (skip/error) applies to the CSV path only.

AUD-2026-09-071 savepoint fix: the defensive fresh-id fallback for a
cross-tenant primary-key collision previously caught ``IntegrityError``
*inside* the per-object savepoint and retried in the same, already aborted,
transaction — PostgreSQL then rejected every following statement with
"current transaction is aborted", so the fallback silently lost the object.
Each create attempt now runs in its own nested savepoint, so the failed
INSERT is rolled back before the retry runs (see ``_upsert_spec_object``).

Contract v2 (ADR-014, accepted)
===============================
The result DTO exposes the full v2 envelope (``contract``/``counts``/
``items``/``idempotent_replay``/``request_id``) and ``http_status`` implements
the 200/207/422 mapping. The REST layer additionally owns the optional
``Idempotency-Key`` replay contract (``application/import_idempotency.py``).
Legacy keys stay additive during the deprecation window (§5).

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: import_reqif(reqif_text, workspace_id, ctx, dry_run)
  IF-AS-EXT-OUT-007 — outbound: persistence ORM (Artifact + entity upserts)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-008_ExportService/ (sibling component; import shares its docs home)
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from application.base import NotFoundError, ServiceBase, ValidationError
from application.reqif_export_service import (
    _ATTR_CATEGORY,
    _ATTR_CUSTOM_FIELDS,
    _ATTR_DESCRIPTION,
    _ATTR_MOSCOW_PRIORITY,
    _ATTR_STATUS,
    _ATTR_TITLE,
    _ATTR_UID,
    _ATTR_VERIFICATION_METHOD,
    _SPEC_OBJECT_TYPE_NEED,
    _SPEC_OBJECT_TYPE_REQUIREMENT,
)
from auth_tenancy.context import AuthContext
from persistence.custom_fields import validate_custom_fields
from traceability.types import VALID_LINK_TYPES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Size guards (REQ-147, mirrors application.import_service._MAX_ROWS intent)
# ---------------------------------------------------------------------------

# ReqIF interchange documents (DOORS/Polarion exports) commonly contain
# thousands of SPEC-OBJECTs; 5000 is a generous-but-bounded ceiling that
# still protects against pathological/malicious payloads.
_MAX_SPEC_OBJECTS = 5000
# 20 MB of XML text — comfortably above any realistic single-workspace
# export, small enough to bound worst-case parse memory/time.
_MAX_DOCUMENT_CHARS = 20 * 1024 * 1024

# Known ATTR-* identifiers per SPEC-OBJECT-TYPE (mirrors reqif_export_service
# SpecAttributeDefinition lists). Anything else -> custom_fields.
_NEED_KNOWN_ATTRS = frozenset(
    {
        _ATTR_UID,
        _ATTR_TITLE,
        _ATTR_DESCRIPTION,
        _ATTR_STATUS,
        _ATTR_CATEGORY,
        _ATTR_CUSTOM_FIELDS,
        _ATTR_MOSCOW_PRIORITY,
    }
)
_REQUIREMENT_KNOWN_ATTRS = frozenset(
    {
        _ATTR_UID,
        _ATTR_TITLE,
        _ATTR_DESCRIPTION,
        _ATTR_STATUS,
        _ATTR_CATEGORY,
        _ATTR_CUSTOM_FIELDS,
        _ATTR_VERIFICATION_METHOD,
    }
)

# Status normalisation — copy of
# workflow/migrations/0003_reconcile_status_mirror.py's constants so the
# import-time mapping stays aligned with what the reconcile migration (and
# therefore the rest of the system) considers a "known" status. The frozen
# migration copy is intentionally NOT updated in lockstep; see the GH-453 note
# on _map_status for the one behavioural divergence.
_GLOBAL_KNOWN_STATES = frozenset(
    {"draft", "in_review", "approved", "deprecated", "done"}
)
_FALLBACK_STATE = "draft"

# ---------------------------------------------------------------------------
# Import contract v2 — stable, machine-readable cause codes (ADR-014 §1)
#
# SCREAMING_SNAKE, shared vocabulary documented in
# docs/se/ADR/ADR-014_import_erfolgssemantik_idempotenz.md §1. The localized
# ``message`` travels next to the code; clients branch on the code only.
# ---------------------------------------------------------------------------
CAUSE_DUPLICATE = "DUPLICATE"
CAUSE_UNKNOWN_TYPE = "UNKNOWN_TYPE"
CAUSE_MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
CAUSE_INVALID_VALUE = "INVALID_VALUE"
CAUSE_TYPE_MISMATCH = "TYPE_MISMATCH"
CAUSE_QUOTING_ERROR = "QUOTING_ERROR"
CAUSE_PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
CAUSE_PARSE_ERROR = "PARSE_ERROR"
#: Relation endpoint absent from the document — intentionally not imported.
#: (ADR-014's §1 catalog predates the ReqIF relation path; Folgeaufgabe 5
#: coordinates the catalog with INT-06. Documented here, not invented silently.)
CAUSE_UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"

#: Status values of an item in the v2 result model (ADR-014 §1).
STATUS_SUCCEEDED = "succeeded"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"


def _apply_imported_workflow_state(
    *,
    entity_id: UUID,
    item_type: str,
    workspace_id: UUID,
    tenant: Any,
    definition: Any,
    mapped_state: str,
    source: str,
) -> None:
    """Create/align the ``WorkflowItemState`` for an imported row, CAS-correct.

    An import is a system-level operation, not a user transition, so it does
    not run the preset transition graph. It must still not be a *silent* state
    bypass (AUD-2026-09-167/168): whenever the imported state actually differs
    from what the row already holds, this bumps the optimistic-lock counter
    (``version = version + 1``) and appends a ``WorkflowHistoryEntry`` -- the
    same observable contract the canonical writer
    (``StateLifecycleManager.perform_transition``) guarantees.

    A newly created state row starts at the definition's initial state
    (``states[0]``, the project-wide convention) and is only moved to the
    imported value through that same CAS write, so ``version`` reflects the
    number of state changes rather than the raw insert. An unchanged import
    stays at whatever the row already held and does not touch ``version``.

    Args:
        entity_id:    PK of the imported entity (its ``WorkflowItemState.item_id``).
        item_type:    Entity type string (e.g. ``"Requirement"``).
        workspace_id: Workspace UUID.
        tenant:       Owning tenant (used for the create).
        definition:   The workspace's ``WorkflowEngineDefinition`` for *item_type*.
        mapped_state: The imported status already normalised via ``_map_status``.
        source:       Import source label ("ReqIF" / "CSV"), recorded in history.
    """
    from django.db.models import F

    from workflow.models import WorkflowHistoryEntry, WorkflowItemState

    valid_states = list((definition.workflow_json or {}).get("states", [])) or [
        mapped_state
    ]
    initial_state = valid_states[0]

    state_row = WorkflowItemState.objects.filter(
        item_id=entity_id, item_type=item_type
    ).first()
    if state_row is None:
        state_row = WorkflowItemState.objects.create(
            item_id=entity_id,
            item_type=item_type,
            workspace_id=workspace_id,
            definition=definition,
            current_state=initial_state,
            tenant=tenant,
        )

    previous_state = state_row.current_state
    definition_changed = state_row.definition_id != definition.id
    if previous_state == mapped_state and not definition_changed:
        return

    updated = WorkflowItemState.objects.filter(pk=state_row.pk).update(
        current_state=mapped_state,
        definition=definition,
        version=F("version") + 1,
    )
    if not updated:
        # Row vanished under us (concurrent hard delete) -- nothing to record.
        return

    if previous_state != mapped_state:
        WorkflowHistoryEntry.unscoped.create(
            item_state=state_row,
            from_state=previous_state,
            to_state=mapped_state,
            transitioned_by="import",
            transitioned_at=timezone.now(),
            change_reason=f"Imported state ({source})",
            workspace_id=workspace_id,
            tenant_id=state_row.tenant_id,
        )


def _map_status(current: str, valid_states: list[str] | None) -> str:
    """Map a free-text status onto a valid workflow state.

    Ported from ``0003_reconcile_status_mirror._map_status`` — see that
    migration for the authoritative rationale. Duplicated here (rather than
    imported) because Django migration modules are not a stable import
    surface; the module docstring above documents the coupling so the two
    copies are kept in sync deliberately.

    GH-453 divergence from the frozen migration copy: an exact miss now retries
    case-insensitively before falling back to the initial state. Without it, a
    CSV/ReqIF file exported *before* TestCase states were lowercased carries
    "Approved", finds no exact match in the workspace's now-lowercase
    ``["draft", "ready", "approved", "deprecated"]`` and silently lands on
    ``valid_states[0]`` — i.e. every approved test case would come back in as a
    draft. The retry only runs where the previous behaviour was outright data
    loss, so it can never downgrade an existing exact match.
    """
    if valid_states is None:
        return current if current in _GLOBAL_KNOWN_STATES else _FALLBACK_STATE
    if current in valid_states:
        return current
    folded = (current or "").strip().casefold()
    for state in valid_states:
        if state.casefold() == folded:
            return state
    return valid_states[0] if valid_states else _FALLBACK_STATE


class _SoftError(Exception):
    """Per-object/per-relation error: caller reports it, does not abort.

    A ``_SoftError`` on a SPEC-OBJECT counts as ``failed`` (the object was
    meant to import but its data is invalid or conflicts); on a SPEC-RELATION
    it counts as ``skipped`` (the relation is intentionally not imported —
    e.g. an endpoint absent from the document).

    ``code`` is the stable, machine-readable v2 ``cause.code`` (ADR-014 §1);
    ``message`` is the localized human text.
    """

    def __init__(self, message: str, code: str = CAUSE_INVALID_VALUE) -> None:
        super().__init__(message)
        self.code = code


class ReqifParseError(ValidationError):
    """File-level ReqIF parse error (ADR-014 §2, REQ-L2-RQ-001 AC5).

    A subclass of ``ValidationError`` so every existing ``except
    ValidationError`` caller keeps behaving, but a distinct type so the REST
    layer can map it to **422** with ``cause.code = PARSE_ERROR`` (the file is
    syntactically well-formed as a multipart request but its *content* is not
    processable) instead of the request-level **400** reserved for 0-byte /
    size-limit / unreadable-body cases.
    """


def _parse_artifact_uuid(identifier: str) -> UUID | None:
    """Recover the Artifact UUID from a ``_<uuid>`` SPEC-OBJECT identifier.

    Returns None for anything that is not exactly the export's own scheme
    (foreign/hand-authored ReqIF identifiers, e.g. "OBJ-123") — those always
    take the create-with-fresh-uuid path.
    """
    if not identifier or not identifier.startswith("_"):
        return None
    try:
        return UUID(identifier[1:])
    except (ValueError, AttributeError, TypeError):
        return None


def _parse_relation_uuid(identifier: str | None) -> UUID | None:
    """Recover the TraceLink UUID from a ``_r-<uuid>`` SPEC-RELATION identifier.

    The relation-scheme counterpart of :func:`_parse_artifact_uuid`, matching
    ``reqif_export_service._relation_id`` (issue #1242). Returns None for any
    other identifier (foreign/hand-authored relation ids), which then relies
    solely on the endpoint-pair idempotency key.
    """
    if not identifier or not identifier.startswith("_r-"):
        return None
    try:
        return UUID(identifier[3:])
    except (ValueError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Report DTOs
# ---------------------------------------------------------------------------


@dataclass
class ReqifEntityReport:
    """Per-entity-kind counts + structured per-item outcomes.

    The three outcome counters are mutually exclusive per imported item:
    ``succeeded`` (= ``created + updated``) imported the item (created it or
    updated an existing one), ``skipped`` intentionally did not import it
    (e.g. an unresolvable relation endpoint), ``failed`` hit an error while
    importing it (invalid data, persistence conflict, unexpected exception).

    ``items`` carries one structured entry per non-succeeded outcome
    (``{"row", "identifier", "kind", "status", "cause": {"code", "message"}}``,
    ADR-014 §1). ``errors`` is the legacy additive view derived from ``items``
    (``{"identifier", "message"}``) so existing consumers keep working during
    the deprecation window.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        """Items imported (created or updated) — the complement of skipped+failed."""
        return self.created + self.updated

    @property
    def errors(self) -> list[dict[str, str]]:
        """Legacy additive error view derived from the structured ``items``.

        ADR-014 §5: the legacy keys are *additive* and must not change meaning.
        The pre-ADR ``errors`` list contained only genuine failures, so skips
        (``DUPLICATE``/``UNKNOWN_TYPE``) are deliberately excluded here — they
        remain visible via the v2 ``items``/``counts`` instead.
        """
        return [
            {"identifier": item["identifier"], "message": item["cause"]["message"]}
            for item in self.items
            if item["status"] == STATUS_FAILED
        ]

    def add_item(
        self,
        *,
        row: int | None,
        identifier: str | None,
        kind: str | None,
        status: str,
        code: str,
        message: str,
    ) -> None:
        """Record one structured outcome entry (ADR-014 §1)."""
        self.items.append(
            {
                "row": row,
                "identifier": identifier,
                "kind": kind,
                "status": status,
                "cause": {"code": code, "message": message},
            }
        )

    def to_dict(self) -> dict:
        return {
            "succeeded": self.succeeded,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
            "items": list(self.items),
        }


@dataclass
class ReqifImportResult:
    """Result of a ReqIF import (real or dry-run) — contract v2 (ADR-014 §1).

    Attributes:
        success: ``True`` iff no imported object failed, i.e.
            ``success == (counts.failed == 0)`` summed over ``needs``,
            ``requirements`` and ``relations`` (AUD-2026-09-071, ADR-014 §1).
            It is *not* hard-coded: a document where one object has invalid
            data (or cannot be persisted) reports ``success=False`` together
            with the structured per-object ``items``, while the remaining
            objects are still imported. Only hard document errors (unparseable
            XML, no CORE-CONTENT, size/object-count guards) raise instead
            (``ReqifParseError``/``ValidationError``/``NotFoundError``) and are
            mapped by the REST layer to 422/400 — nothing is persisted then.
        dry_run: Echoes the caller's dry_run flag.
        needs: StakeholderNeed succeeded/created/updated/skipped/failed/items.
        requirements: Requirement succeeded/created/updated/skipped/failed/items.
        relations: TraceLink succeeded/created/updated (= already existed)/
            skipped/failed/items.
        warnings: Non-fatal notes (unknown SPEC-OBJECT-TYPE skipped,
            cross-workspace identifier collisions resolved with a fresh id,
            malformed ATTR-CUSTOM-FIELDS JSON ignored, ...). Warnings do not
            affect ``success``.
        request_id: Correlation id for this import request (INT-06).
        idempotent_replay: ``True`` when the response is served from the
            ``Idempotency-Key`` replay cache instead of a fresh import.
        extra_items: File-level entries without an owning ``ReqifEntityReport``
            (e.g. the synthetic ``PARSE_ERROR`` item). Counted into
            ``counts.failed``/``items``.

    Contract v2 (ADR-014, `accepted`): ``contract="v2"``, ``counts`` and
    ``items`` are first-class; the legacy ``needs``/``requirements``/``relations``
    keys stay additive during the deprecation window (§5).
    """

    success: bool
    dry_run: bool
    needs: ReqifEntityReport
    requirements: ReqifEntityReport
    relations: ReqifEntityReport
    warnings: list[str] = field(default_factory=list)
    request_id: str = ""
    idempotent_replay: bool = False
    extra_items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failed_total(self) -> int:
        """Total failed objects across all three entity kinds + extra items."""
        return (
            self.needs.failed
            + self.requirements.failed
            + self.relations.failed
            + sum(1 for item in self.extra_items if item["status"] == STATUS_FAILED)
        )

    @property
    def counts(self) -> dict[str, int]:
        """v2 result counters (ADR-014 §1). ``total`` includes skipped."""
        succeeded = (
            self.needs.succeeded
            + self.requirements.succeeded
            + self.relations.succeeded
        )
        skipped = self.needs.skipped + self.requirements.skipped + self.relations.skipped
        failed = (
            self.needs.failed
            + self.requirements.failed
            + self.relations.failed
            + sum(1 for item in self.extra_items if item["status"] == STATUS_FAILED)
        )
        return {
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
            "total": succeeded + skipped + failed,
        }

    @property
    def items(self) -> list[dict[str, Any]]:
        """Combined structured item list (failures + skips), ADR-014 §1."""
        return [
            *self.needs.items,
            *self.requirements.items,
            *self.relations.items,
            *self.extra_items,
        ]

    @property
    def http_status(self) -> int:
        """ReqIF HTTP mapping (ADR-014 §2).

        ``failed == 0`` -> 200 (success with or without write effect; a
        skipped-only document is still a success, never a Created).
        ``succeeded > 0 and failed > 0`` -> 207 Multi-Status (partial success).
        ``failed > 0 and succeeded == 0`` -> 422 Unprocessable Entity.
        """
        counts = self.counts
        if counts["failed"] > 0:
            return 207 if counts["succeeded"] > 0 else 422
        return 200

    @classmethod
    def parse_failure(
        cls, message: str, *, dry_run: bool, request_id: str
    ) -> ReqifImportResult:
        """Build the v2 result for a file-level PARSE_ERROR (ADR-014 §2).

        No object was persisted; the single synthetic item makes ``items``
        non-empty and pinpoints the cause code for a 422 response.
        """
        return cls(
            success=False,
            dry_run=dry_run,
            needs=ReqifEntityReport(),
            requirements=ReqifEntityReport(),
            relations=ReqifEntityReport(),
            warnings=[],
            request_id=request_id,
            extra_items=[
                {
                    "row": None,
                    "identifier": None,
                    "kind": None,
                    "status": STATUS_FAILED,
                    "cause": {"code": CAUSE_PARSE_ERROR, "message": message},
                }
            ],
        )

    def to_dict(self) -> dict:
        return {
            # --- v2 envelope (ADR-014 §1) ---
            "success": self.success,
            "contract": "v2",
            "dry_run": self.dry_run,
            "counts": self.counts,
            "items": self.items,
            "warnings": list(self.warnings),
            "idempotent_replay": self.idempotent_replay,
            "request_id": self.request_id,
            # --- legacy additive keys (deprecation window §5) ---
            "needs": self.needs.to_dict(),
            "requirements": self.requirements.to_dict(),
            "relations": self.relations.to_dict(),
        }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ReqifImportService(ServiceBase):
    """ReqIF 1.2 import for StakeholderNeeds, Requirements and TraceLinks.

    COMP-AS-008b (ImportService family). REQ-147.

    Usage::

        svc = ReqifImportService()
        result = svc.import_reqif(
            reqif_text=uploaded_file.read().decode("utf-8"),
            workspace_id=ws_uuid,
            ctx=auth_ctx,
            dry_run=False,
        )
        print(result.to_dict())
    """

    def import_reqif(
        self,
        reqif_text: str,
        workspace_id: UUID | str,
        ctx: AuthContext,
        dry_run: bool = False,
        request_id: str | None = None,
    ) -> ReqifImportResult:
        """Parse, validate, and (unless dry_run) atomically persist a ReqIF document.

        REQ-147.

        Args:
            reqif_text: Raw ReqIF 1.2 XML content (UTF-8 decoded string).
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant scoping, RBAC, and audit.
            dry_run: If True, runs the whole pipeline and rolls back instead
                of committing; the returned report is otherwise identical.
            request_id: Optional correlation id (INT-06); generated when absent.

        Returns:
            ReqifImportResult (contract v2) with per-entity-kind outcome counts
            (succeeded/created/updated/skipped/failed), a structured per-item
            report, warnings and the v2 envelope (``counts``/``items``).
            ``success`` is False as soon as one object failed
            (``success ⇔ counts.failed == 0``); the remaining objects are still
            persisted.

        Raises:
            NotFoundError: workspace does not exist in the active tenant.
            ReqifParseError: file-level parse/structural error (→ 422).
            ValidationError: request-level hard error — empty/oversized
                document. Nothing is persisted.
            PermissionDeniedError: ctx lacks write permission (viewer-only).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        from persistence.models import Workspace

        ws_uuid = UUID(str(workspace_id))
        try:
            workspace = Workspace.objects.get(id=ws_uuid, tenant_id=ctx.tenant_id)
        except Workspace.DoesNotExist:
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        if not reqif_text or not reqif_text.strip():
            raise ValidationError("ReqIF document is empty.")
        if len(reqif_text) > _MAX_DOCUMENT_CHARS:
            raise ValidationError(
                f"ReqIF document exceeds the maximum size of "
                f"{_MAX_DOCUMENT_CHARS} characters."
            )

        bundle = self._parse(reqif_text)

        content = bundle.core_content.req_if_content if bundle.core_content else None
        if content is None:
            raise ReqifParseError(
                "ReqIF document has no CORE-CONTENT/REQ-IF-CONTENT section."
            )

        spec_objects = content.spec_objects or []
        if len(spec_objects) > _MAX_SPEC_OBJECTS:
            raise ValidationError(
                f"ReqIF document exceeds the maximum of {_MAX_SPEC_OBJECTS} "
                f"SPEC-OBJECTs (got {len(spec_objects)})."
            )

        needs_report = ReqifEntityReport()
        reqs_report = ReqifEntityReport()
        relations_report = ReqifEntityReport()
        warnings: list[str] = []

        tenant = workspace.tenant

        with transaction.atomic():
            identifier_to_artifact: dict[str, Any] = {}
            # Plan G G1.2 (#1386): requirements written by this import are
            # embedded after commit. Collected here, dispatched below — the
            # request thread must not wait for the provider.
            requirement_ids: list[Any] = []

            for position, so in enumerate(spec_objects, start=1):
                kind = self._spec_object_kind(so.spec_object_type)
                if kind is None:
                    warnings.append(
                        f"SPEC-OBJECT {so.identifier}: unknown SPEC-OBJECT-TYPE "
                        f"'{so.spec_object_type}' — skipped."
                    )
                    # ADR-014 §1: unknown SPEC-OBJECT-TYPE is a *skip*, never a
                    # failure — it does not influence success. Reported for
                    # completeness so a client sees why an object was not written.
                    needs_report.add_item(
                        row=position,
                        identifier=so.identifier,
                        kind=None,
                        status=STATUS_SKIPPED,
                        code=CAUSE_UNKNOWN_TYPE,
                        message=(
                            f"Unknown SPEC-OBJECT-TYPE '{so.spec_object_type}' — skipped."
                        ),
                    )
                    needs_report.skipped += 1
                    continue

                report = needs_report if kind == "StakeholderNeed" else reqs_report
                spec_type = bundle.get_spec_object_type_by_ref(so.spec_object_type)

                try:
                    with transaction.atomic():
                        artifact, created, deduplicated = self._upsert_spec_object(
                            so=so,
                            kind=kind,
                            spec_type=spec_type,
                            workspace=workspace,
                            tenant=tenant,
                            warnings=warnings,
                        )
                except _SoftError as exc:
                    # AUD-2026-09-071: a SPEC-OBJECT that errors on invalid
                    # data/conflict was meant to import — it is a *failure*,
                    # not a skip, so it drives success=False.
                    report.failed += 1
                    report.add_item(
                        row=position,
                        identifier=so.identifier,
                        kind=kind,
                        status=STATUS_FAILED,
                        code=getattr(exc, "code", CAUSE_INVALID_VALUE),
                        message=str(exc),
                    )
                    continue
                except Exception:  # noqa: BLE001 — per-object failure, do not abort
                    logger.exception(
                        "ReqifImportService: unexpected error importing %s",
                        so.identifier,
                    )
                    report.failed += 1
                    # #697 (CWE-209): the report is part of the HTTP body, so
                    # the raw exception text must not travel in it.
                    report.add_item(
                        row=position,
                        identifier=so.identifier,
                        kind=kind,
                        status=STATUS_FAILED,
                        code=CAUSE_PERSISTENCE_ERROR,
                        message=(
                            "An internal error occurred while importing this object."
                        ),
                    )
                    continue

                identifier_to_artifact[so.identifier] = artifact
                if kind == "Requirement" and not deduplicated:
                    requirement_ids.append(artifact.requirement.id)
                if created:
                    report.created += 1
                elif deduplicated:
                    # ADR-014 §3: identical content -> idempotent no-op.
                    report.skipped += 1
                    report.add_item(
                        row=position,
                        identifier=so.identifier,
                        kind=kind,
                        status=STATUS_SKIPPED,
                        code=CAUSE_DUPLICATE,
                        message=(
                            "Identical object already imported — no write effect."
                        ),
                    )
                else:
                    # ADR-014 §3 / REQ-147: a reqif_identifier match with
                    # divergent content is an *update* (succeeded), not a skip.
                    report.updated += 1

            self._apply_hierarchy(content.specifications, identifier_to_artifact)
            self._apply_relations(
                content.spec_relations,
                content.spec_types,
                identifier_to_artifact,
                tenant,
                relations_report,
            )

            if not dry_run:
                self._audit(
                    ctx=ctx,
                    operation="create",
                    entity_type="ReqifImport",
                    entity_id=ws_uuid,
                    details={
                        "workspace_id": str(ws_uuid),
                        "needs_created": needs_report.created,
                        "needs_updated": needs_report.updated,
                        "requirements_created": reqs_report.created,
                        "requirements_updated": reqs_report.updated,
                        "relations_created": relations_report.created,
                        "failed": (
                            needs_report.failed
                            + reqs_report.failed
                            + relations_report.failed
                        ),
                        "skipped": (
                            needs_report.skipped
                            + reqs_report.skipped
                            + relations_report.skipped
                        ),
                    },
                )
            else:
                # Whole pipeline ran for real (including per-object
                # savepoints); undo it all at the outermost boundary so the
                # report reflects exactly what a real run would have done
                # without persisting anything (REQ-147 dry_run).
                transaction.set_rollback(True)

            if not dry_run and requirement_ids:
                # Plan G G1.2: embedding runs after the import commits, never on
                # the request thread. A broker outage must not fail an
                # otherwise-persisted import (fallback: the operator re-runs
                # ``manage.py backfill_embeddings --model requirement``).
                def _enqueue_embeddings(
                    ids: tuple[Any, ...] = tuple(requirement_ids),
                    tid: Any = tenant.id,
                ) -> None:
                    from application.tasks import embed_rows_task

                    try:
                        embed_rows_task.delay(
                            "requirement", [str(row_id) for row_id in ids], str(tid)
                        )
                    except Exception:  # noqa: BLE001 — import is already durable
                        logger.warning(
                            "ReqifImportService: could not enqueue embedding for "
                            "%d imported requirement(s); run backfill_embeddings "
                            "--model requirement to catch up.",
                            len(ids),
                            exc_info=True,
                        )

                transaction.on_commit(_enqueue_embeddings)

        # AUD-2026-09-071 / ADR-014 §1: success is derived from the actual
        # per-object outcome, never hard-coded. Any object that failed to
        # import makes the whole import unsuccessful while the successfully
        # imported objects stay persisted (no total abort). The HTTP mapping
        # (200/207/422) is exposed via ``ReqifImportResult.http_status`` and
        # applied by the REST layer (ADR-014 §2).
        return ReqifImportResult(
            success=(
                needs_report.failed
                + reqs_report.failed
                + relations_report.failed
            )
            == 0,
            dry_run=dry_run,
            needs=needs_report,
            requirements=reqs_report,
            relations=relations_report,
            warnings=warnings,
            request_id=request_id or str(uuid.uuid4()),
        )

    # ---------- Parsing ----------

    @staticmethod
    def _parse(reqif_text: str):
        """Parse *reqif_text* into a ReqIFBundle, or raise ReqifParseError.

        Both outright XML syntax errors and ReqIF schema-level structural
        violations collected onto ``bundle.exceptions`` by the ``reqif``
        parser are treated as file-level parse errors (ADR-014 §2,
        REQ-L2-RQ-001 AC5). The REST layer maps ``ReqifParseError`` to **422**
        with ``cause.code = PARSE_ERROR`` — the multipart request is
        syntactically well-formed, the file content is not processable.

        The raised message is deliberately generic: the raw parser text can
        echo document content and must not travel in the HTTP 422 body
        (CWE-209, F9). The detail is logged here for operators.
        """
        # Issue #131: ``reqif`` is an optional dependency — import lazily so a
        # missing/broken install cannot take down the whole Django URLConf.
        from reqif.parser import ReqIFParser

        generic = "Malformed ReqIF document: the file is not a valid ReqIF 1.2 XML document."
        try:
            bundle = ReqIFParser.parse_from_string(reqif_text)
        except Exception as exc:  # noqa: BLE001 — normalise to ReqifParseError
            logger.warning("ReqifImportService: ReqIF parse failed: %s", exc)
            raise ReqifParseError(generic) from exc

        if bundle.exceptions:
            descriptions = "; ".join(
                exc.get_description() if hasattr(exc, "get_description") else str(exc)
                for exc in bundle.exceptions
            )
            logger.warning(
                "ReqifImportService: ReqIF structural errors: %s", descriptions
            )
            raise ReqifParseError(
                "Malformed ReqIF document: the file has structural ReqIF errors."
            )

        return bundle

    # ---------- SPEC-OBJECT upsert ----------

    @staticmethod
    def _spec_object_kind(spec_object_type_ref: str) -> str | None:
        if spec_object_type_ref == _SPEC_OBJECT_TYPE_NEED:
            return "StakeholderNeed"
        if spec_object_type_ref == _SPEC_OBJECT_TYPE_REQUIREMENT:
            return "Requirement"
        return None

    @classmethod
    def _upsert_spec_object(
        cls,
        so: Any,
        kind: str,
        spec_type: Any,
        workspace: Any,
        tenant: Any,
        warnings: list[str],
    ) -> tuple:
        """Create or update the Artifact + Need/Requirement for one SPEC-OBJECT.

        Runs inside a savepoint (caller's ``transaction.atomic()``); raises
        ``_SoftError`` for anything that should be failed-and-reported rather
        than aborting the whole import.

        Returns:
            ``(artifact, created, deduplicated)`` — ``created=True`` for a
            brand-new artifact, ``deduplicated=True`` for an in-place match
            with identical content (idempotent no-op, ADR-014 §3). At most one
            of the two flags is true; both false means an update.
        """
        title, description, status_raw, category, external_uid = (
            ReqifImportService._spec_object_text_values(so)
        )
        ReqifImportService._check_spec_object_limits(title, category, external_uid)
        custom_fields = ReqifImportService._collect_custom_fields(
            so,
            spec_type,
            kind,
            warnings,
        )
        verification_method, moscow_priority = ReqifImportService._kind_specific_values(
            kind,
            so,
        )

        # ---- Resolve target artifact id / existing row ----
        target_uuid, foreign_identifier, existing_artifact = (
            ReqifImportService._resolve_spec_object_target(
                so,
                workspace,
                external_uid,
                warnings,
            )
        )

        if existing_artifact is not None:
            entity = ReqifImportService._load_existing_entity(
                existing_artifact,
                kind,
                so,
            )
            # ADR-014 §3 (ReqIF upsert): a match over the identifier triad
            # (Artifact id -> reqif_uid -> reqif_identifier) with *identical*
            # content is an idempotent no-op -> skipped DUPLICATE, no second
            # write effect. Divergent content stays an update (succeeded) —
            # never a silent discard (that would be REQ-147 data loss).
            if cls._is_identical_reqif_object(
                entity=entity,
                artifact=existing_artifact,
                kind=kind,
                title=title,
                description=description,
                category=category,
                verification_method=verification_method,
                moscow_priority=moscow_priority,
                custom_fields=custom_fields,
                external_uid=external_uid,
                foreign_identifier=foreign_identifier,
                status_raw=status_raw,
                workspace_id=workspace.id,
            ):
                return existing_artifact, False, True
            artifact = existing_artifact
            created = False
        else:
            artifact, entity = ReqifImportService._create_spec_object(
                so,
                kind,
                target_uuid,
                workspace,
                tenant,
                warnings,
            )
            created = True

        cls._apply_spec_object_values(
            entity,
            kind,
            title,
            description,
            category,
            verification_method,
            moscow_priority,
            status_raw,
            workspace.id,
            tenant,
        )
        ReqifImportService._apply_artifact_external_identity(
            artifact,
            custom_fields,
            foreign_identifier,
            external_uid,
        )
        entity.save()

        return artifact, created, False

    @staticmethod
    def _attr_text(attrs: dict[str, Any], key: str) -> str:
        """Read one ReqIF attribute as plain text (first value, or ``""``)."""
        attribute = attrs.get(key)
        if attribute is None:
            return ""
        value = attribute.value
        if isinstance(value, str):
            return value
        return value[0] if value else ""

    @staticmethod
    def _spec_object_text_values(so: Any) -> tuple[str, str, str, str, str | None]:
        """Read the well-known SPEC-OBJECT attributes as import payload.

        Returns ``(title, description, status_raw, category, external_uid)``.
        Issue #1003: the ReqIF ATTR-UID is the *external* source-tool UID. It
        is stored on the Artifact as ``reqif_uid``, never in the local,
        auto-generated ``uid``.
        """
        attrs = so.attribute_map
        return (
            ReqifImportService._attr_text(attrs, _ATTR_TITLE),
            ReqifImportService._attr_text(attrs, _ATTR_DESCRIPTION),
            ReqifImportService._attr_text(attrs, _ATTR_STATUS),
            ReqifImportService._attr_text(attrs, _ATTR_CATEGORY),
            ReqifImportService._attr_text(attrs, _ATTR_UID) or None,
        )

    @staticmethod
    def _check_spec_object_limits(
        title: str,
        category: str,
        external_uid: str | None,
    ) -> None:
        """Reject field values the model columns cannot hold (per-object)."""
        if len(title) > 500:
            raise _SoftError(
                f"Title exceeds 500 characters ({len(title)}).",
                code=CAUSE_INVALID_VALUE,
            )
        if len(category) > 64:
            raise _SoftError(
                f"Category exceeds 64 characters ({len(category)}).",
                code=CAUSE_INVALID_VALUE,
            )
        if external_uid and len(external_uid) > 255:
            raise _SoftError(
                f"External ReqIF UID exceeds 255 characters ({len(external_uid)}).",
                code=CAUSE_INVALID_VALUE,
            )

    @staticmethod
    def _collect_custom_fields(
        so: Any,
        spec_type: Any,
        kind: str,
        warnings: list[str],
    ) -> dict[str, Any]:
        """Assemble ``Artifact.custom_fields`` for one SPEC-OBJECT.

        ``ATTR-CUSTOM-FIELDS`` payload first, then every attribute the
        document does not cover with a well-known field. The flat map is
        validated explicitly: this import assigns
        ``artifact.custom_fields`` directly and calls
        ``save(update_fields=...)``, which does not run model validators — so
        the flat-map rules (and, since the #269 follow-up, the free-text guard
        that keeps markup / ``javascript:`` payloads out of the map) have to
        be applied explicitly here. A ReqIF file is untrusted input like any
        request body. A violation is a per-object failure: the spec object is
        not imported and is reported, the rest of the file still imports.
        """
        attrs = so.attribute_map
        custom_fields: dict[str, Any] = ReqifImportService._custom_fields_from_payload(
            attrs,
            so,
            warnings,
        )
        custom_fields.update(
            ReqifImportService._custom_fields_from_unknown_attrs(so, spec_type, kind)
        )

        try:
            return validate_custom_fields(custom_fields)
        except DjangoValidationError as exc:
            raise _SoftError(
                exc.messages[0] if exc.messages else "Invalid custom fields.",
                code=CAUSE_INVALID_VALUE,
            ) from exc

    @staticmethod
    def _custom_fields_from_payload(
        attrs: dict[str, Any],
        so: Any,
        warnings: list[str],
    ) -> dict[str, Any]:
        """Parse the ``ATTR-CUSTOM-FIELDS`` JSON payload into a dict.

        A missing attribute, an empty value or a non-object payload yields
        ``{}``; invalid JSON adds a warning — never an import failure.
        """
        cf_attr = attrs.get(_ATTR_CUSTOM_FIELDS)
        if cf_attr is None or not cf_attr.value:
            return {}
        try:
            parsed = json.loads(cf_attr.value)
        except (TypeError, ValueError):
            warnings.append(
                f"{so.identifier}: ATTR-CUSTOM-FIELDS is not valid JSON — ignored."
            )
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _custom_fields_from_unknown_attrs(
        so: Any,
        spec_type: Any,
        kind: str,
    ) -> dict[str, Any]:
        """Collect every attribute not covered by a well-known field.

        The key is the attribute's long name when the document's
        SPEC-OBJECT-TYPE defines one, else the raw ``definition_ref``.
        """
        known_attrs = _NEED_KNOWN_ATTRS if kind == "StakeholderNeed" else _REQUIREMENT_KNOWN_ATTRS
        custom_fields: dict[str, Any] = {}
        for attribute in so.attributes:
            if attribute.definition_ref in known_attrs:
                continue
            long_name = attribute.definition_ref
            if spec_type is not None:
                definition = spec_type.attribute_map.get(attribute.definition_ref)
                if definition is not None and definition.long_name:
                    long_name = definition.long_name
            custom_fields[long_name] = attribute.value
        return custom_fields

    @staticmethod
    def _kind_specific_values(kind: str, so: Any) -> tuple[str | None, str | None]:
        """Read the kind-specific entity fields (verification / priority).

        ``verification_method`` belongs to a Requirement, ``moscow_priority``
        to a StakeholderNeed; the other stays ``None``.
        """
        attrs = so.attribute_map
        verification_method = (
            ReqifImportService._attr_text(attrs, _ATTR_VERIFICATION_METHOD) or None
            if kind == "Requirement"
            else None
        )
        moscow_priority = (
            ReqifImportService._attr_text(attrs, _ATTR_MOSCOW_PRIORITY) or None
            if kind == "StakeholderNeed"
            else None
        )
        return verification_method, moscow_priority

    @staticmethod
    def _resolve_spec_object_target(
        so: Any,
        workspace: Any,
        external_uid: str | None,
        warnings: list[str],
    ) -> tuple[Any, str | None, Any]:
        """Locate the artifact this SPEC-OBJECT maps to, if any.

        REQ-147: the SPEC-OBJECT identifier encodes the *source* artifact's
        id, so importing the same ReqIF file into a different workspace
        never matches there — the id-based lookup always misses and every
        reimport minted a fresh artifact (doubling on each run).
        Issue #1003: an identifier NOT in the internal ``_<uuid>`` form is a
        foreign tool's identity; retain it so a re-export emits the same id.
        The fallback matches the Artifact's stored *external* ReqIF identity
        (``reqif_uid``, then ``reqif_identifier``) within this workspace —
        never the local readable ``uid``, which is auto-generated per
        artifact since #932 and carries no external meaning.

        Issue #1242: a ``_<uuid>`` that matches an artifact in *another*
        workspace is foreign too — it cannot be reproduced locally, so it is
        returned as ``foreign_identifier`` and persisted (see the derivation
        below), which is what keeps a re-import idempotent when the document
        carries no external ATTR-UID.

        Returns ``(target_uuid, foreign_identifier, existing_artifact)``.
        ``target_uuid`` becomes ``None`` when the id matches an artifact
        outside this workspace (the object is imported as a new artifact).
        """
        from persistence.models import Artifact

        target_uuid = _parse_artifact_uuid(so.identifier)
        existing_artifact = None
        if target_uuid is not None:
            existing_artifact = Artifact.objects.filter(
                id=target_uuid, workspace_id=workspace.id
            ).first()
            if existing_artifact is None and Artifact.objects.filter(
                id=target_uuid
            ).exclude(workspace_id=workspace.id).exists():
                warnings.append(
                    f"Identifier {so.identifier} matches an artifact outside this "
                    "workspace; imported as a new artifact with a fresh id."
                )
                target_uuid = None

        # Issue #1242: the identifier is "foreign" exactly when it does NOT
        # resolve to a local artifact id. Deriving it *after* the cross-workspace
        # reset above is what makes a re-import idempotent: a `_<uuid>` from
        # another workspace must be persisted as the Artifact's
        # ``reqif_identifier`` (the old code fixed it as ``None`` before the
        # reset, so with an empty ATTR-UID the second import found no match and
        # minted a duplicate artifact, dragging every relation along).
        foreign_identifier = None if target_uuid is not None else so.identifier

        if existing_artifact is None:
            by_workspace = Artifact.objects.filter(workspace_id=workspace.id)
            if external_uid:
                existing_artifact = by_workspace.filter(
                    reqif_uid=external_uid
                ).first()
            if existing_artifact is None and foreign_identifier:
                existing_artifact = by_workspace.filter(
                    reqif_identifier=foreign_identifier
                ).first()
        return target_uuid, foreign_identifier, existing_artifact

    @staticmethod
    def _load_existing_entity(existing_artifact: Any, kind: str, so: Any) -> Any:
        """Load the Need/Requirement behind a matched artifact.

        Raises ``_SoftError(TYPE_MISMATCH)`` when the artifact carries an
        entity of the other kind — a partial row that cannot be updated.
        """
        from persistence.models import Requirement, StakeholderNeed

        entity = (
            Requirement.objects.filter(artifact_id=existing_artifact.id).first()
            if kind == "Requirement"
            else StakeholderNeed.objects.filter(artifact_id=existing_artifact.id).first()
        )
        if entity is None:
            raise _SoftError(
                f"Identifier {so.identifier} matches an existing artifact of a "
                "different type — not imported.",
                code=CAUSE_TYPE_MISMATCH,
            )
        return entity

    @staticmethod
    def _create_spec_object(
        so: Any,
        kind: str,
        target_uuid: Any,
        workspace: Any,
        tenant: Any,
        warnings: list[str],
    ) -> tuple[Any, Any]:
        """Create the Artifact + entity rows for a not-yet-known SPEC-OBJECT.

        The identifier's ``_<uuid>`` form is kept as the new artifact id
        when present. Each create runs in its own nested savepoint: without
        it, catching IntegrityError here left the surrounding transaction
        aborted, so the retry below hit "current transaction is aborted"
        and the defensive fresh-id fallback silently lost the object. The
        nested savepoint rolls the failed INSERT back before the retry runs.
        The retry itself is a defensive fallback for the (near-impossible
        with random UUIDv4s) case of a cross-tenant id collision invisible
        to the tenant-scoped query above (AUD-2026-09-071).
        """
        from persistence.models import Artifact, Requirement, StakeholderNeed

        new_id = target_uuid or uuid.uuid4()
        try:
            with transaction.atomic():
                artifact = Artifact.objects.create(
                    id=new_id,
                    tenant=tenant,
                    workspace=workspace,
                    artifact_type=kind,
                    custom_fields={},
                )
        except IntegrityError:
            new_id = uuid.uuid4()
            warnings.append(
                f"Identifier {so.identifier} collided with an existing "
                f"artifact id; assigned a new id {new_id}."
            )
            with transaction.atomic():
                artifact = Artifact.objects.create(
                    id=new_id,
                    tenant=tenant,
                    workspace=workspace,
                    artifact_type=kind,
                    custom_fields={},
                )
        entity = (
            # #133/#1402: ``workspace`` is denormalized onto the Artifact-backed
            # entity to back its (workspace, uid) partial UniqueConstraint. It
            # is set for every kind, not just Requirement — a NULL would
            # silently exempt the imported row from the constraint.
            Requirement(tenant=tenant, artifact=artifact, workspace=workspace)
            if kind == "Requirement"
            else StakeholderNeed(tenant=tenant, artifact=artifact, workspace=workspace)
        )
        return artifact, entity

    @classmethod
    def _apply_spec_object_values(
        cls,
        entity: Any,
        kind: str,
        title: str,
        description: str,
        category: str,
        verification_method: str | None,
        moscow_priority: str | None,
        status_raw: str,
        workspace_id: Any,
        tenant: Any,
    ) -> None:
        """Copy the parsed values onto the entity and apply workflow status.

        REQ-143: status is set exactly the way the reconcile migration sets
        it — never as a bare field assignment implying direct user control.
        Issue #1003: the local, readable ``uid`` is NOT set from ReqIF; the
        external identity lives on the Artifact's reqif_* fields.
        """
        entity.title = title
        entity.description = description
        entity.category = category
        if kind == "Requirement":
            entity.verification_method = verification_method
        else:
            entity.moscow_priority = moscow_priority
        cls._apply_status(entity, kind, status_raw, workspace_id, tenant)

    @staticmethod
    def _apply_artifact_external_identity(
        artifact: Any,
        custom_fields: dict[str, Any],
        foreign_identifier: str | None,
        external_uid: str | None,
    ) -> None:
        """Set custom_fields + external ReqIF identity and save the artifact.

        Issue #1003: persist the external ReqIF identity on the Artifact.
        ``reqif_identifier`` is set for a *foreign* identifier. Issue #1242: the
        internal ``_<uuid>`` form is only reproducible from the id when the
        artifact actually carries that id, so a ``_<uuid>`` that resolved to an
        artifact in *another* workspace (and therefore got a fresh local id) is
        persisted here too — otherwise the next import of the same file has no
        identity to match on. ``reqif_uid``/``reqif_imported_at`` are refreshed
        on every import.
        """
        artifact.custom_fields = custom_fields
        if foreign_identifier:
            artifact.reqif_identifier = foreign_identifier
        if external_uid:
            artifact.reqif_uid = external_uid
        artifact.reqif_imported_at = timezone.now()
        artifact.save(
            update_fields=[
                "custom_fields",
                "reqif_identifier",
                "reqif_uid",
                "reqif_imported_at",
            ]
        )

    # ---------- Identical-content detection (ADR-014 §3, ReqIF upsert) -------

    @classmethod
    def _is_identical_reqif_object(
        cls,
        *,
        entity: Any,
        artifact: Any,
        kind: str,
        title: str,
        description: str,
        category: str,
        verification_method: str | None,
        moscow_priority: str | None,
        custom_fields: dict[str, Any],
        external_uid: str | None,
        foreign_identifier: str | None,
        status_raw: str,
        workspace_id: UUID,
    ) -> bool:
        """Return True when the incoming SPEC-OBJECT matches the stored one.

        Compares every field the import would write (entity content, the
        Artifact's custom_fields and external ReqIF identity, and the mapped
        workflow state). A True result lets the caller count ``skipped``
        (``DUPLICATE``) and return without any write effect.
        """
        if entity.title != title or entity.description != description:
            return False
        if entity.category != category:
            return False
        if kind == "Requirement":
            if entity.verification_method != verification_method:
                return False
        else:
            if entity.moscow_priority != moscow_priority:
                return False
        if (artifact.custom_fields or {}) != custom_fields:
            return False
        # Only compare the external identity we would actually (re)write;
        # an incoming internal `_<uuid>` identifier leaves reqif_* untouched.
        if external_uid and (artifact.reqif_uid or None) != external_uid:
            return False
        if foreign_identifier and (
            artifact.reqif_identifier or None
        ) != foreign_identifier:
            return False
        return cls._status_matches(entity, kind, status_raw, workspace_id)

    @staticmethod
    def _status_matches(
        entity: Any, item_type: str, status_raw: str, workspace_id: UUID
    ) -> bool:
        """Return True when the mapped status would not change stored state.

        Mirrors ``_apply_status``: with no ``WorkflowEngineDefinition`` the
        imported status is discarded, so it can never make an otherwise
        identical object differ.
        """
        from workflow.models import WorkflowEngineDefinition, WorkflowItemState

        definition = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if definition is None:
            return True
        valid_states = list((definition.workflow_json or {}).get("states", []))
        desired = _map_status(status_raw, valid_states)
        state_row = WorkflowItemState.objects.filter(
            item_id=entity.id, item_type=item_type
        ).first()
        if state_row is None:
            return False
        return (
            state_row.current_state == desired
            and state_row.definition_id == definition.id
        )

    # ---------- Status / WorkflowItemState (REQ-143) ----------

    @staticmethod
    def _apply_status(
        entity: Any,
        item_type: str,
        status_raw: str,
        workspace_id: UUID,
        tenant: Any,
    ) -> None:
        """Mirror ``0003_reconcile_status_mirror.reconcile_status_mirror``.

        Creates/updates the matching ``WorkflowItemState`` row IFF a
        ``WorkflowEngineDefinition`` exists for this workspace/item_type.
        ``entity.id`` is available before the first save (UUID PK default is
        assigned client-side), so this can run before ``entity.save()``.

        Task 12: the ``status`` column is dropped, so a mapped value can no
        longer be persisted on ``entity`` itself -- without a
        ``WorkflowEngineDefinition`` there is nowhere left to record it, and
        the imported status is discarded (documented, reviewed data-loss
        tradeoff, see the Task 12 report Finding 2; mirrors the identical
        ``definition is None`` discard in ``import_service._insert_rows``'s
        CSV import path).
        """
        from workflow.models import WorkflowEngineDefinition, WorkflowItemState

        definition = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()
        if definition is None:
            return

        valid_states = list((definition.workflow_json or {}).get("states", []))
        mapped = _map_status(status_raw, valid_states)

        # AUD-2026-09-168: this used to flip ``current_state`` without touching
        # ``version`` (a CAS blind spot) and without a history entry. Route every
        # imported state change through the shared CAS writer so an importer can
        # no longer silently overwrite a concurrent transition.
        _apply_imported_workflow_state(
            entity_id=entity.id,
            item_type=item_type,
            workspace_id=workspace_id,
            tenant=tenant,
            definition=definition,
            mapped_state=mapped,
            source="ReqIF",
        )

    # ---------- SPEC-HIERARCHY -> Artifact.parent ----------

    @staticmethod
    def _apply_hierarchy(
        specifications: list[Any] | None,
        identifier_to_artifact: dict[str, Any],
    ) -> None:
        """Apply SPEC-HIERARCHY nesting as Artifact.parent within the workspace.

        A node whose SPEC-OBJECT-REF was not imported (unknown type / soft
        error) is elided: its children attach to the nearest ancestor that
        *was* imported (mirrors the exporter's inverse "nearest exported
        ancestor" collapsing).

        TODO (hierarchy consolidation): Artifact.parent is deprecated
        project-wide in favor of 'derives-from' TraceLinks (see
        persistence/models.py Artifact.parent docstring). ReqIF SPEC-HIERARCHY
        is a positional tree structure external to this project, so this
        remains the pragmatic 1:1 mapping target for the export/import
        roundtrip (REQ-146/REQ-147); revisit if/when TraceLinks become the
        canonical roundtrip representation too.
        """

        def walk(nodes: list[Any] | None, parent_artifact: Any | None) -> None:
            for node in nodes or []:
                child_artifact = identifier_to_artifact.get(node.spec_object)
                next_parent = parent_artifact
                if child_artifact is not None:
                    desired_parent_id = parent_artifact.id if parent_artifact else None
                    if child_artifact.parent_id != desired_parent_id:
                        child_artifact.parent = parent_artifact
                        try:
                            child_artifact.save(update_fields=["parent"])
                        except Exception:  # noqa: BLE001 — best-effort hierarchy
                            logger.exception(
                                "ReqifImportService: failed to set parent for %s",
                                node.spec_object,
                            )
                    next_parent = child_artifact
                walk(getattr(node, "children", None), next_parent)

        for specification in specifications or []:
            walk(getattr(specification, "children", None), None)

    # ---------- SPEC-RELATION -> TraceLink ----------

    @staticmethod
    def _apply_relations(
        spec_relations: list[Any] | None,
        spec_types: list[Any] | None,
        identifier_to_artifact: dict[str, Any],
        tenant: Any,
        relations_report: ReqifEntityReport,
    ) -> None:
        relation_type_long_names = ReqifImportService._relation_type_long_names(spec_types)

        for position, relation in enumerate(spec_relations or [], start=1):
            try:
                with transaction.atomic():
                    source_artifact, target_artifact = (
                        ReqifImportService._resolve_relation_endpoints(
                            relation,
                            identifier_to_artifact,
                        )
                    )
                    link_type = ReqifImportService._resolve_link_type(
                        relation,
                        relation_type_long_names,
                    )
                    ReqifImportService._ensure_relation_link(
                        relation.identifier,
                        link_type,
                        source_artifact,
                        target_artifact,
                        tenant,
                        relations_report,
                    )
            except _SoftError as exc:
                ReqifImportService._record_relation_skip(
                    exc,
                    relation,
                    position,
                    relations_report,
                )
            except Exception:  # noqa: BLE001 — per-relation failure, do not abort
                logger.exception(
                    "ReqifImportService: unexpected error importing relation %s",
                    relation.identifier,
                )
                ReqifImportService._record_relation_failure(
                    relation,
                    position,
                    relations_report,
                )

    @staticmethod
    def _relation_type_long_names(spec_types: list[Any] | None) -> dict[str, str]:
        """Collect SPEC-RELATION-TYPE long names as identifier -> link-type mapping.

        A relation's ``relation_type_ref`` is resolved against this mapping
        first (REQ-147): the document's own long name is the canonical
        link-type name. A document that omits the long name falls back to the
        stripped/raw ref (see ``_resolve_link_type``).
        """
        # Issue #131: lazy import of the optional ``reqif`` package.
        from reqif.models.reqif_spec_relation_type import ReqIFSpecRelationType

        long_names: dict[str, str] = {}
        for spec_type in spec_types or []:
            if isinstance(spec_type, ReqIFSpecRelationType):
                long_names[spec_type.identifier] = spec_type.long_name or spec_type.identifier
        return long_names

    @staticmethod
    def _resolve_relation_endpoints(
        relation: Any,
        identifier_to_artifact: dict[str, Any],
    ) -> tuple[Any, Any]:
        """Resolve a relation's source/target identifiers to imported Artifacts.

        Raises ``_SoftError(UNRESOLVED_REFERENCE)`` when either endpoint is
        absent from this document — normal for partial documents, so the
        caller records a skip instead of aborting the import (ADR-014 §1).
        """
        source_artifact = identifier_to_artifact.get(relation.source)
        target_artifact = identifier_to_artifact.get(relation.target)
        if source_artifact is None or target_artifact is None:
            raise _SoftError(
                f"Relation {relation.identifier}: endpoint not "
                f"resolvable (source={relation.source!r}, "
                f"target={relation.target!r}).",
                code=CAUSE_UNRESOLVED_REFERENCE,
            )
        return source_artifact, target_artifact

    @staticmethod
    def _resolve_link_type(
        relation: Any,
        relation_type_long_names: dict[str, str],
    ) -> str:
        """Resolve a relation's link type from its SPEC-RELATION-TYPE reference.

        Prefers the document's long name, then falls back to stripping a
        ``SRT-`` prefix, then the raw ref. Anything outside
        ``VALID_LINK_TYPES`` raises ``_SoftError(UNKNOWN_TYPE)`` (ADR-014 §1)
        — the relation stays skipped rather than creating an unknown link.
        """
        link_type = relation_type_long_names.get(relation.relation_type_ref)
        if not link_type:
            ref = relation.relation_type_ref or ""
            link_type = ref[len("SRT-"):] if ref.startswith("SRT-") else ref
        if link_type not in VALID_LINK_TYPES:
            raise _SoftError(
                f"Relation {relation.identifier}: unknown link type "
                f"'{link_type}'.",
                code=CAUSE_UNKNOWN_TYPE,
            )
        return link_type

    @staticmethod
    def _ensure_relation_link(
        relation_identifier: str | None,
        link_type: str,
        source_artifact: Any,
        target_artifact: Any,
        tenant: Any,
        relations_report: ReqifEntityReport,
    ) -> None:
        """Create the TraceLink for a relation, idempotently.

        Two idempotency keys, in order (issue #1242):

        1. The external relation identity ``_r-<uuid>`` (the id the exporter
           derives from the TraceLink row) — honoured when a link carrying that
           id already exists *in the same workspace*. Previously this identity
           was parsed away and discarded, so a relation whose endpoints had been
           re-created produced a second edge.
        2. The canonical ``(tenant, source, target, link_type)`` edge, backed by
           the ``uq_tracelink_edge`` constraint.

        ``get_or_create`` keeps re-importing the same document a no-op (the
        link either exists -> ``updated``, or is inserted now -> ``created``).
        Runs inside the caller's per-relation savepoint, so a persistence
        error rolls back exactly this relation.
        """
        from persistence.models import TraceLink

        external_id = _parse_relation_uuid(relation_identifier)
        if external_id is not None:
            # Tenant-scoped AND workspace-checked: a UUID that happens to belong
            # to a different workspace (e.g. the source workspace's own link, or
            # another workspace that imported the same file) must never be
            # mistaken for this relation — that would silently drop the edge.
            existing = TraceLink.unscoped.filter(
                id=external_id, tenant=tenant
            ).first()
            if (
                existing is not None
                and existing.source.workspace_id == source_artifact.workspace_id
            ):
                relations_report.updated += 1
                return

        defaults: dict[str, Any] = {}
        # Persist the external relation identity on create when the id is free
        # anywhere in the table. A globally taken id (the source workspace's own
        # link) must not collide with the primary key, so it is left to a fresh
        # UUID in that case — the endpoint-pair key still deduplicates.
        if external_id is not None and not TraceLink.unscoped.filter(
            id=external_id
        ).exists():
            defaults["id"] = external_id

        _, was_created = TraceLink.objects.get_or_create(
            tenant=tenant,
            source=source_artifact,
            target=target_artifact,
            link_type=link_type,
            defaults=defaults,
        )
        if was_created:
            relations_report.created += 1
        else:
            relations_report.updated += 1

    @staticmethod
    def _record_relation_skip(
        exc: _SoftError,
        relation: Any,
        position: int,
        relations_report: ReqifEntityReport,
    ) -> None:
        """Report an intentionally not-imported relation as *skipped*.

        A relation that is intentionally not imported (endpoint absent,
        unknown link type) is a *skip* — relations are documented as never a
        hard error, and a missing endpoint is normal for partial documents.
        """
        relations_report.skipped += 1
        relations_report.add_item(
            row=position,
            identifier=relation.identifier,
            kind="TraceLink",
            status=STATUS_SKIPPED,
            code=getattr(exc, "code", CAUSE_UNRESOLVED_REFERENCE),
            message=str(exc),
        )

    @staticmethod
    def _record_relation_failure(
        relation: Any,
        position: int,
        relations_report: ReqifEntityReport,
    ) -> None:
        """Report a relation that hit an unexpected error as *failed*.

        #697 (CWE-209): the report is part of the HTTP body, so the raw
        exception text must not travel in it.
        """
        relations_report.failed += 1
        relations_report.add_item(
            row=position,
            identifier=relation.identifier,
            kind="TraceLink",
            status=STATUS_FAILED,
            code=CAUSE_PERSISTENCE_ERROR,
            message=(
                "An internal error occurred while importing this relation."
            ),
        )


__all__ = [
    "ReqifEntityReport",
    "ReqifImportResult",
    "ReqifImportService",
    "ReqifParseError",
]
