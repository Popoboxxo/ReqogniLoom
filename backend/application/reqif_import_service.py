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
    row) is a soft, per-object error: skipped and reported under the owning
    entity kind's ``errors``.

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
Hard errors (unparseable XML, missing CORE-CONTENT, a document exceeding the
size/object-count guards, or ``ReqIFSchemaError`` structural violations
surfaced by the ``reqif`` parser) are raised *before* — or immediately
unwind — the transaction, so nothing is written; the REST layer maps them to
400. Per-object/per-relation soft errors (bad type, oversized field, missing
endpoint, ...) are caught around a per-item ``transaction.atomic()``
savepoint so one bad SPEC-OBJECT/SPEC-RELATION cannot poison the surrounding
transaction — it is skipped and reported instead.

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
from django.db import IntegrityError, transaction

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

# Status normalisation — verbatim copy of
# workflow/migrations/0003_reconcile_status_mirror.py's constants so the
# import-time mapping stays byte-identical to what the reconcile migration
# (and therefore the rest of the system) considers a "known" status.
_GLOBAL_KNOWN_STATES = frozenset(
    {"draft", "in_review", "approved", "deprecated", "done"}
)
_FALLBACK_STATE = "draft"


def _map_status(current: str, valid_states: Optional[List[str]]) -> str:
    """Map a free-text status onto a valid workflow state.

    Verbatim port of ``0003_reconcile_status_mirror._map_status`` — see that
    migration for the authoritative rationale. Duplicated here (rather than
    imported) because Django migration modules are not a stable import
    surface; the module docstring above documents the coupling so the two
    copies are kept in sync deliberately.
    """
    if valid_states is None:
        return current if current in _GLOBAL_KNOWN_STATES else _FALLBACK_STATE
    if current in valid_states:
        return current
    return valid_states[0] if valid_states else _FALLBACK_STATE


class _SoftError(Exception):
    """Per-object/per-relation error: caller skips and reports, does not abort."""


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
    """created/updated/skipped counts + per-item errors for one entity kind."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


@dataclass
class ReqifImportResult:
    """Result of a ReqIF import (real or dry-run).

    Attributes:
        success: Always True when returned — hard errors raise instead
            (ValidationError/NotFoundError), the REST layer maps those to 400.
        dry_run: Echoes the caller's dry_run flag.
        needs: StakeholderNeed created/updated/skipped/errors.
        requirements: Requirement created/updated/skipped/errors.
        relations: TraceLink created/updated (= already existed)/skipped/errors.
        warnings: Non-fatal notes (unknown SPEC-OBJECT-TYPE skipped,
            cross-workspace identifier collisions resolved with a fresh id,
            malformed ATTR-CUSTOM-FIELDS JSON ignored, ...).
    """

    success: bool
    dry_run: bool
    needs: ReqifEntityReport
    requirements: ReqifEntityReport
    relations: ReqifEntityReport
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "dry_run": self.dry_run,
            "needs": self.needs.to_dict(),
            "requirements": self.requirements.to_dict(),
            "relations": self.relations.to_dict(),
            "warnings": list(self.warnings),
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
    ) -> ReqifImportResult:
        """Parse, validate, and (unless dry_run) atomically persist a ReqIF document.

        REQ-147.

        Args:
            reqif_text: Raw ReqIF 1.2 XML content (UTF-8 decoded string).
            workspace_id: Target workspace UUID.
            ctx: AuthContext for tenant scoping, RBAC, and audit.
            dry_run: If True, runs the whole pipeline and rolls back instead
                of committing; the returned report is otherwise identical.

        Returns:
            ReqifImportResult with per-entity-kind counts and a report of
            skipped items / warnings.

        Raises:
            NotFoundError: workspace does not exist in the active tenant.
            ValidationError: hard error — empty/oversized/malformed document,
                or a structural ReqIF violation. Nothing is persisted.
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
            raise ValidationError(
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

            for so in spec_objects:
                kind = self._spec_object_kind(so.spec_object_type)
                if kind is None:
                    warnings.append(
                        f"SPEC-OBJECT {so.identifier}: unknown SPEC-OBJECT-TYPE "
                        f"'{so.spec_object_type}' — skipped."
                    )
                    continue

                report = needs_report if kind == "StakeholderNeed" else reqs_report
                spec_type = bundle.get_spec_object_type_by_ref(so.spec_object_type)

                try:
                    with transaction.atomic():
                        artifact, created = self._upsert_spec_object(
                            so=so,
                            kind=kind,
                            spec_type=spec_type,
                            workspace=workspace,
                            tenant=tenant,
                            warnings=warnings,
                        )
                except _SoftError as exc:
                    report.skipped += 1
                    report.errors.append(
                        {"identifier": so.identifier, "message": str(exc)}
                    )
                    continue
                except Exception as exc:  # noqa: BLE001 — soft-fail per object
                    logger.exception(
                        "ReqifImportService: unexpected error importing %s",
                        so.identifier,
                    )
                    report.skipped += 1
                    report.errors.append(
                        {"identifier": so.identifier, "message": str(exc)}
                    )
                    continue

                identifier_to_artifact[so.identifier] = artifact
                if created:
                    report.created += 1
                else:
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
                    },
                )
            else:
                # Whole pipeline ran for real (including per-object
                # savepoints); undo it all at the outermost boundary so the
                # report reflects exactly what a real run would have done
                # without persisting anything (REQ-147 dry_run).
                transaction.set_rollback(True)

        return ReqifImportResult(
            success=True,
            dry_run=dry_run,
            needs=needs_report,
            requirements=reqs_report,
            relations=relations_report,
            warnings=warnings,
        )

    # ---------- Parsing ----------

    @staticmethod
    def _parse(reqif_text: str):
        """Parse *reqif_text* into a ReqIFBundle, or raise ValidationError.

        Both outright XML syntax errors and ReqIF schema-level structural
        violations collected onto ``bundle.exceptions`` by the ``reqif``
        parser are treated as hard errors (REQ-147: "unparseable XML,
        structural violation -> whole import rolled back, 400").
        """
        # Issue #131: ``reqif`` is an optional dependency — import lazily so a
        # missing/broken install cannot take down the whole Django URLConf.
        from reqif.parser import ReqIFParser

        try:
            bundle = ReqIFParser.parse_from_string(reqif_text)
        except Exception as exc:  # noqa: BLE001 — normalise to ValidationError
            raise ValidationError(f"Malformed ReqIF document: {exc}") from exc

        if bundle.exceptions:
            descriptions = "; ".join(
                exc.get_description() if hasattr(exc, "get_description") else str(exc)
                for exc in bundle.exceptions
            )
            raise ValidationError(
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
        ``_SoftError`` for anything that should be skipped-and-reported
        rather than aborting the whole import.

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
        uid = _attr_value(_ATTR_UID) or None

        if len(title) > 500:
            raise _SoftError(f"Title exceeds 500 characters ({len(title)}).")
        if len(category) > 64:
            raise _SoftError(f"Category exceeds 64 characters ({len(category)}).")
        if uid and len(uid) > 64:
            raise _SoftError(f"UID exceeds 64 characters ({len(uid)}).")

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

        verification_method = (
            _attr_value(_ATTR_VERIFICATION_METHOD) or None if kind == "Requirement" else None
        )
        moscow_priority = (
            _attr_value(_ATTR_MOSCOW_PRIORITY) or None if kind == "StakeholderNeed" else None
        )

        # ---- Resolve target artifact id / existing row ----
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

        # REQ-147: the SPEC-OBJECT identifier encodes the *source* artifact's
        # id, so importing the same ReqIF file into a different workspace
        # never matches there — the id-based lookup above always misses and
        # every reimport minted a fresh artifact (doubling on each run). Fall
        # back to matching an existing row by its stable business ``uid``
        # within this workspace, which is what makes cross-workspace reimport
        # idempotent instead of a duplicate-generating loop.
        if existing_artifact is None and uid:
            entity_model = Requirement if kind == "Requirement" else StakeholderNeed
            existing_entity = entity_model.objects.filter(
                artifact__workspace_id=workspace.id, uid=uid
            ).first()
            if existing_entity is not None:
                existing_artifact = existing_entity.artifact

        if existing_artifact is not None:
            entity = (
                Requirement.objects.filter(artifact_id=existing_artifact.id).first()
                if kind == "Requirement"
                else StakeholderNeed.objects.filter(artifact_id=existing_artifact.id).first()
            )
            if entity is None:
                raise _SoftError(
                    f"Identifier {so.identifier} matches an existing artifact of a "
                    "different type — skipped."
                )
            artifact = existing_artifact
            created = False
        else:
            new_id = target_uuid or uuid.uuid4()
            try:
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
                # the tenant-scoped query above.
                new_id = uuid.uuid4()
                warnings.append(
                    f"Identifier {so.identifier} collided with an existing "
                    f"artifact id; assigned a new id {new_id}."
                )
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
        entity.uid = uid
        if kind == "Requirement":
            entity.verification_method = verification_method
        else:
            entity.moscow_priority = moscow_priority

        # REQ-143: status is set exactly the way the reconcile migration sets
        # it — never as a bare field assignment implying direct user control.
        cls._apply_status(entity, kind, status_raw, workspace.id, tenant)

        artifact.custom_fields = custom_fields
        artifact.save(update_fields=["custom_fields"])
        entity.save()

        return artifact, created

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

        Sets ``entity.status`` (not yet saved — caller saves once at the end)
        and creates/updates the matching ``WorkflowItemState`` row IFF a
        ``WorkflowEngineDefinition`` exists for this workspace/item_type.
        ``entity.id`` is available before the first save (UUID PK default is
        assigned client-side), so this can run before ``entity.save()``.
        """
        from workflow.models import WorkflowEngineDefinition, WorkflowItemState

        definition = WorkflowEngineDefinition.objects.filter(
            workspace_id=str(workspace_id), item_type=item_type
        ).first()

        valid_states = None
        if definition is not None:
            valid_states = list((definition.workflow_json or {}).get("states", []))

        mapped = _map_status(status_raw, valid_states)
        entity.status = mapped

        if definition is None:
            return

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

        for relation in spec_relations or []:
            try:
                with transaction.atomic():
                    source_artifact = identifier_to_artifact.get(relation.source)
                    target_artifact = identifier_to_artifact.get(relation.target)
                    if source_artifact is None or target_artifact is None:
                        raise _SoftError(
                            f"Relation {relation.identifier}: endpoint not "
                            f"resolvable (source={relation.source!r}, "
                            f"target={relation.target!r})."
                        )

                    link_type = relation_type_long_names.get(relation.relation_type_ref)
                    if not link_type:
                        ref = relation.relation_type_ref or ""
                        link_type = ref[len("SRT-"):] if ref.startswith("SRT-") else ref
                    if link_type not in VALID_LINK_TYPES:
                        raise _SoftError(
                            f"Relation {relation.identifier}: unknown link type "
                            f"'{link_type}'."
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
                relations_report.skipped += 1
                relations_report.errors.append(
                    {"identifier": relation.identifier, "message": str(exc)}
                )
            except Exception as exc:  # noqa: BLE001 — soft-fail per relation
                logger.exception(
                    "ReqifImportService: unexpected error importing relation %s",
                    relation.identifier,
                )
                relations_report.skipped += 1
                relations_report.errors.append(
                    {"identifier": relation.identifier, "message": str(exc)}
                )


__all__ = ["ReqifImportService", "ReqifImportResult", "ReqifEntityReport"]
