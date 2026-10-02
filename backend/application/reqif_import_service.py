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
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
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


def _map_status(current: str, valid_states: Optional[List[str]]) -> str:
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


def _parse_artifact_uuid(identifier: str) -> Optional[UUID]:
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
    items: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        """Items imported (created or updated) — the complement of skipped+failed."""
        return self.created + self.updated

    @property
    def errors(self) -> List[Dict[str, str]]:
        """Legacy additive error view derived from the structured ``items``."""
        return [
            {"identifier": item["identifier"], "message": item["cause"]["message"]}
            for item in self.items
        ]

    def add_item(
        self,
        *,
        row: Optional[int],
        identifier: Optional[str],
        kind: Optional[str],
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
    warnings: List[str] = field(default_factory=list)
    request_id: str = ""
    idempotent_replay: bool = False
    extra_items: List[Dict[str, Any]] = field(default_factory=list)

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
    def counts(self) -> Dict[str, int]:
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
    def items(self) -> List[Dict[str, Any]]:
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
    ) -> "ReqifImportResult":
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
        request_id: Optional[str] = None,
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
        warnings: List[str] = []

        tenant = workspace.tenant

        with transaction.atomic():
            identifier_to_artifact: Dict[str, Any] = {}

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
        """
        # Issue #131: ``reqif`` is an optional dependency — import lazily so a
        # missing/broken install cannot take down the whole Django URLConf.
        from reqif.parser import ReqIFParser

        try:
            bundle = ReqIFParser.parse_from_string(reqif_text)
        except Exception as exc:  # noqa: BLE001 — normalise to ReqifParseError
            raise ReqifParseError(f"Malformed ReqIF document: {exc}") from exc

        if bundle.exceptions:
            descriptions = "; ".join(
                exc.get_description() if hasattr(exc, "get_description") else str(exc)
                for exc in bundle.exceptions
            )
            raise ReqifParseError(
                f"ReqIF document has structural errors: {descriptions}"
            )

        return bundle

    # ---------- SPEC-OBJECT upsert ----------

    @staticmethod
    def _spec_object_kind(spec_object_type_ref: str) -> Optional[str]:
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
        warnings: List[str],
    ) -> tuple:
        """Create or update the Artifact + Need/Requirement for one SPEC-OBJECT.

        Runs inside a savepoint (caller's ``transaction.atomic()``); raises
        ``_SoftError`` for anything that should be failed-and-reported rather
        than aborting the whole import.

        Returns:
            (artifact, created) — created=True for a brand-new artifact.
        """
        from persistence.models import Artifact, Requirement, StakeholderNeed

        attrs = so.attribute_map

        def _attr_value(key: str) -> str:
            attribute = attrs.get(key)
            if attribute is None:
                return ""
            value = attribute.value
            if isinstance(value, str):
                return value
            return value[0] if value else ""

        title = _attr_value(_ATTR_TITLE)
        description = _attr_value(_ATTR_DESCRIPTION)
        status_raw = _attr_value(_ATTR_STATUS)
        category = _attr_value(_ATTR_CATEGORY)
        # Issue #1003: the ReqIF ATTR-UID is the *external* source-tool UID.
        # It is stored on the Artifact as `reqif_uid`, never in the local,
        # auto-generated `uid`.
        external_uid = _attr_value(_ATTR_UID) or None

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

        # ---- custom_fields: ATTR-CUSTOM-FIELDS payload, then unknown attrs ----
        custom_fields: Dict[str, Any] = {}
        cf_attr = attrs.get(_ATTR_CUSTOM_FIELDS)
        if cf_attr is not None and cf_attr.value:
            try:
                parsed = json.loads(cf_attr.value)
                if isinstance(parsed, dict):
                    custom_fields.update(parsed)
            except (TypeError, ValueError):
                warnings.append(
                    f"{so.identifier}: ATTR-CUSTOM-FIELDS is not valid JSON — ignored."
                )

        known_attrs = _NEED_KNOWN_ATTRS if kind == "StakeholderNeed" else _REQUIREMENT_KNOWN_ATTRS
        for attribute in so.attributes:
            if attribute.definition_ref in known_attrs:
                continue
            long_name = attribute.definition_ref
            if spec_type is not None:
                definition = spec_type.attribute_map.get(attribute.definition_ref)
                if definition is not None and definition.long_name:
                    long_name = definition.long_name
            custom_fields[long_name] = attribute.value

        # This import assigns ``artifact.custom_fields`` directly and calls
        # ``save(update_fields=...)``, which does not run model validators — so
        # the flat-map rules (and, since the #269 follow-up, the free-text guard
        # that keeps markup / ``javascript:`` payloads out of the map) have to
        # be applied explicitly here. A ReqIF file is untrusted input like any
        # request body. A violation is a per-object failure: the spec object is
        # not imported and is reported, the rest of the file still imports.
        try:
            custom_fields = validate_custom_fields(custom_fields)
        except DjangoValidationError as exc:
            raise _SoftError(
                exc.messages[0] if exc.messages else "Invalid custom fields.",
                code=CAUSE_INVALID_VALUE,
            ) from exc

        verification_method = (
            _attr_value(_ATTR_VERIFICATION_METHOD) or None if kind == "Requirement" else None
        )
        moscow_priority = (
            _attr_value(_ATTR_MOSCOW_PRIORITY) or None if kind == "StakeholderNeed" else None
        )

        # ---- Resolve target artifact id / existing row ----
        target_uuid = _parse_artifact_uuid(so.identifier)
        # Issue #1003: an identifier NOT in the internal `_<uuid>` form is a
        # foreign tool's identity; retain it so a re-export emits the same id.
        foreign_identifier = None if target_uuid is not None else so.identifier
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

        # REQ-147: the SPEC-OBJECT identifier encodes the *source* artifact's
        # id, so importing the same ReqIF file into a different workspace
        # never matches there — the id-based lookup above always misses and
        # every reimport minted a fresh artifact (doubling on each run).
        # Issue #1003: fall back to the Artifact's stored *external* ReqIF
        # identity (reqif_uid, then reqif_identifier) within this workspace —
        # never the local readable ``uid``, which is auto-generated per
        # artifact since #932 and carries no external meaning.
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

        if existing_artifact is not None:
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
            new_id = target_uuid or uuid.uuid4()
            try:
                # AUD-2026-09-071: each attempt runs in its own nested
                # savepoint. Without it, catching IntegrityError here left the
                # surrounding transaction aborted, so the retry below hit
                # "current transaction is aborted" and the defensive fresh-id
                # fallback silently lost the object. The nested savepoint rolls
                # the failed INSERT back before the retry runs.
                with transaction.atomic():
                    artifact = Artifact.objects.create(
                        id=new_id,
                        tenant=tenant,
                        workspace=workspace,
                        artifact_type=kind,
                        custom_fields={},
                    )
            except IntegrityError:
                # Defensive fallback for the (near-impossible with random
                # UUIDv4s) case of a cross-tenant id collision invisible to
                # the tenant-scoped query above. Runs in a fresh savepoint,
                # because the failed one was rolled back on leaving the block.
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
                # #133: workspace is denormalized onto Requirement to back the
                # (workspace, uid) DB-level UniqueConstraint.
                Requirement(tenant=tenant, artifact=artifact, workspace=workspace)
                if kind == "Requirement"
                else StakeholderNeed(tenant=tenant, artifact=artifact)
            )
            created = True

        entity.title = title
        entity.description = description
        entity.category = category
        # Issue #1003: the local, readable `uid` is NOT set from ReqIF. It is
        # auto-generated per artifact (#932); the external identity lives on the
        # Artifact's reqif_* fields below.
        if kind == "Requirement":
            entity.verification_method = verification_method
        else:
            entity.moscow_priority = moscow_priority

        # REQ-143: status is set exactly the way the reconcile migration sets
        # it — never as a bare field assignment implying direct user control.
        cls._apply_status(entity, kind, status_raw, workspace.id, tenant)

        artifact.custom_fields = custom_fields
        # Issue #1003: persist the external ReqIF identity on the Artifact.
        # `reqif_identifier` is only set for a *foreign* identifier (the
        # internal `_<uuid>` form is reproducible from the id and stays NULL);
        # `reqif_uid`/`reqif_imported_at` are refreshed on every import.
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
        entity.save()

        return artifact, created, False

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
        verification_method: Optional[str],
        moscow_priority: Optional[str],
        custom_fields: Dict[str, Any],
        external_uid: Optional[str],
        foreign_identifier: Optional[str],
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

        state_row = WorkflowItemState.objects.filter(
            item_id=entity.id, item_type=item_type
        ).first()
        if state_row is not None:
            if state_row.current_state != mapped or state_row.definition_id != definition.id:
                state_row.current_state = mapped
                state_row.definition = definition
                state_row.save(update_fields=["current_state", "definition"])
        else:
            WorkflowItemState.objects.create(
                item_id=entity.id,
                item_type=item_type,
                workspace_id=workspace_id,
                definition=definition,
                current_state=mapped,
                tenant=tenant,
            )

    # ---------- SPEC-HIERARCHY -> Artifact.parent ----------

    @staticmethod
    def _apply_hierarchy(
        specifications: Optional[List[Any]],
        identifier_to_artifact: Dict[str, Any],
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

        def walk(nodes: Optional[List[Any]], parent_artifact: Optional[Any]) -> None:
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
        spec_relations: Optional[List[Any]],
        spec_types: Optional[List[Any]],
        identifier_to_artifact: Dict[str, Any],
        tenant: Any,
        relations_report: ReqifEntityReport,
    ) -> None:
        # Issue #131: lazy import of the optional ``reqif`` package.
        from reqif.models.reqif_spec_relation_type import ReqIFSpecRelationType

        from persistence.models import TraceLink

        relation_type_long_names: Dict[str, str] = {}
        for spec_type in spec_types or []:
            if isinstance(spec_type, ReqIFSpecRelationType):
                relation_type_long_names[spec_type.identifier] = (
                    spec_type.long_name or spec_type.identifier
                )

        for position, relation in enumerate(spec_relations or [], start=1):
            try:
                with transaction.atomic():
                    source_artifact = identifier_to_artifact.get(relation.source)
                    target_artifact = identifier_to_artifact.get(relation.target)
                    if source_artifact is None or target_artifact is None:
                        raise _SoftError(
                            f"Relation {relation.identifier}: endpoint not "
                            f"resolvable (source={relation.source!r}, "
                            f"target={relation.target!r}).",
                            code=CAUSE_UNRESOLVED_REFERENCE,
                        )

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

                    _, was_created = TraceLink.objects.get_or_create(
                        tenant=tenant,
                        source=source_artifact,
                        target=target_artifact,
                        link_type=link_type,
                    )
                    if was_created:
                        relations_report.created += 1
                    else:
                        relations_report.updated += 1
            except _SoftError as exc:
                # A relation that is intentionally not imported (endpoint
                # absent, unknown link type) is a *skip* — relations are
                # documented as never a hard error, and a missing endpoint is
                # normal for partial documents.
                relations_report.skipped += 1
                relations_report.add_item(
                    row=position,
                    identifier=relation.identifier,
                    kind="TraceLink",
                    status=STATUS_SKIPPED,
                    code=getattr(exc, "code", CAUSE_UNRESOLVED_REFERENCE),
                    message=str(exc),
                )
            except Exception:  # noqa: BLE001 — per-relation failure, do not abort
                logger.exception(
                    "ReqifImportService: unexpected error importing relation %s",
                    relation.identifier,
                )
                relations_report.failed += 1
                # #697 (CWE-209): the report is part of the HTTP body, so the
                # raw exception text must not travel in it.
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
    "ReqifImportService",
    "ReqifImportResult",
    "ReqifEntityReport",
    "ReqifParseError",
]
