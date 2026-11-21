"""
COMP-AS-008 ReqifExportService — ReqIF 1.2 export (REQ-146).

leaf_id : COMP-AS-008 (ExportService family — sibling of application.export_service)
req_id  : REQ-146 (ReqIF 1.2 export — DOORS/Polarion interoperability)

Exports a workspace's StakeholderNeeds, Requirements, and TraceLinks as a
ReqIF 1.2 (Requirements Interchange Format) XML document, built with the
``reqif`` PyPI package (StrictDoc project, Apache-2.0 license — verified via
``pip show reqif``; pinned in backend/requirements.txt).

ReqFlow -> ReqIF 1.2 mapping
=============================

SPEC-OBJECT-TYPEs (one per exported artifact type)
---------------------------------------------------
  ``ST-StakeholderNeed`` — for ``persistence.models.StakeholderNeed``
  ``ST-Requirement``     — for ``persistence.models.Requirement``
  ``ST-TestCase``        — for ``persistence.models.TestCase`` (D14d)
  ``ST-Icd``             — for ``icd.models.Icd`` (D14d)

  Both additional types are *standard* SPEC-OBJECTs: their data is carried by
  ``ATTRIBUTE-DEFINITION-STRING`` declarations on their own SPEC-OBJECT-TYPE
  (plus shared definitions declared once on the Need type and resolved via
  ``xsd:IDREF``). No private ``THE-OTHER-CONTENT``/``TOOL-EXTENSIONS`` payload
  is used, so the document stays valid against the ReqIF 1.2 XSD.

  Shared attribute definitions (all types, ``DATATYPE-DEFINITION-STRING``):
    ATTR-UID           <- {StakeholderNeed,Requirement}.uid
    ATTR-TITLE         <- .title
    ATTR-DESCRIPTION   <- .description
    ATTR-STATUS        <- workflow.state_reader.current_state(...) / .initial_state(...)
                           (Task 12: the `status` column is dropped; resolved
                           through the workflow engine, not a model field)
    ATTR-CATEGORY      <- .category
    ATTR-CUSTOM-FIELDS <- Artifact.custom_fields, JSON-serialised (sorted keys)
                           into a single opaque STRING attribute — see
                           "Known limitations" below.

  Requirement-only attributes:
    ATTR-VERIFICATION-METHOD <- Requirement.verification_method
    ATTR-TIER-KEY            <- Requirement.tier_key (stable ladder key)
    ATTR-TIER-NAME           <- the workspace ladder entry's display label
                                (P2/V4/V5; ``level`` stays the internal
                                integer alias and is not exported)

  StakeholderNeed-only attribute:
    ATTR-MOSCOW-PRIORITY <- StakeholderNeed.moscow_priority

  Attribute VALUES are omitted (not emitted as an empty ATTRIBUTE-VALUE-STRING)
  when the underlying field is None/blank, except title/uid/status/description/
  category which are always emitted (blank string when empty) for a
  predictable, always-present attribute set.

SPEC-OBJECTs
------------
  One SPEC-OBJECT per exported StakeholderNeed/Requirement row.
  IDENTIFIER = ``_<Artifact.id>`` (UUID prefixed with ``_`` for XML NCName
  validity — UUIDs may start with a digit, which is not a legal NCName start
  character). Re-exporting the same workspace yields byte-identical
  IDENTIFIERs because they are derived deterministically from the stable
  Artifact primary key.

SPECIFICATION / SPEC-HIERARCHY (artifact parent tree)
-------------------------------------------------------
  Exactly one SPECIFICATION per workspace, IDENTIFIER = ``_spec-<Workspace.id>``,
  of SPECIFICATION-TYPE ``ST-Specification-Default``.

  ``Artifact.parent`` forms the decomposition tree. Only artifacts that are
  themselves exported (StakeholderNeed/Requirement) get a SPEC-HIERARCHY node,
  IDENTIFIER = ``_h-<Artifact.id>``. When an exported artifact's immediate
  Artifact.parent is *not* itself exported (e.g. an intervening
  ArchitectureElement/TestCase, out of scope for REQ-146), the algorithm walks
  up the parent chain to the nearest exported ancestor and attaches there
  (flattening around non-exported intermediate nodes) so no descendant is
  dropped from the hierarchy. Artifacts with no exported ancestor become
  top-level children of the SPECIFICATION.

SPEC-RELATIONs / SPEC-RELATION-TYPEs (TraceLinks)
----------------------------------------------------
  One SPEC-RELATION-TYPE per distinct ``TraceLink.link_type`` value that
  appears among the *exported* links (see ``traceability.types.LinkType`` for
  the core built-in keys: derives-from, decomposes, refines, allocated-to,
  verifies, validates, decides, mitigates, satisfies, realizes, references,
  diagram-ref — a workspace may define more, which export the same way).
  IDENTIFIER = ``SRT-<sanitised link_type>`` — non-NCName characters replaced
  with ``-`` (link_type values are already lower-kebab-case so this is a no-op
  in practice).

  One SPEC-RELATION per TraceLink whose ``source`` AND ``target`` both resolve
  to an exported SPEC-OBJECT (a link touching a non-exported artifact type,
  e.g. ArchitectureElement or TestCase, is skipped — out of scope for
  REQ-146). IDENTIFIER = ``_r-<TraceLink.id>``.

Stable identifiers
-------------------
  All IDENTIFIERs are deterministic functions of stable primary keys
  (Artifact.id, Workspace.id, TraceLink.id, link_type). A second export of an
  unmodified workspace therefore produces identical IDENTIFIER values
  (verified by ``rest_api/tests/test_reqif_export.py``); only the ReqIF
  header's CREATION-TIME timestamp legitimately differs between exports.

Known limitations
-------------------
  - Descriptions are exported as plain ``ATTRIBUTE-VALUE-STRING`` (not XHTML).
    ReqFlow stores description as unstructured text; a true XHTML/rich-text
    round trip (DOORS/Polarion often use ``ATTRIBUTE-DEFINITION-XHTML``) is a
    follow-up enhancement.
  - ``custom_fields`` (an arbitrary JSON map per REQ-L2-AS-037) is exported as
    one opaque JSON-encoded STRING attribute rather than individually typed
    ReqIF attributes, since the underlying field has no fixed schema.
  - Hierarchy nesting only considers StakeholderNeed/Requirement artifacts;
    ArchitectureElement/TestCase nodes are invisible to the exported
    SPEC-HIERARCHY (their descendants are reparented to the nearest exported
    ancestor, or promoted to the SPECIFICATION root).

Interface contracts implemented:
  IF-AS-EXT-IN-001  — inbound: export_reqif
  IF-AS-EXT-OUT-007 — outbound: persistence ORM queries (Artifact, Requirement,
                       StakeholderNeed, TraceLink, Workspace)

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-008_ExportService/
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.utils import timezone
from django.utils.text import slugify

from application.base import NotFoundError, ServiceBase
from application.export_service import ExportResult
from auth_tenancy.context import AuthContext

if TYPE_CHECKING:  # pragma: no cover - resolved by type checkers only
    from reqif.models.reqif_core_content import ReqIFCoreContent
    from reqif.models.reqif_data_type import ReqIFDataTypeDefinitionString
    from reqif.models.reqif_namespace_info import ReqIFNamespaceInfo
    from reqif.models.reqif_req_if_content import ReqIFReqIFContent
    from reqif.models.reqif_reqif_header import ReqIFReqIFHeader
    from reqif.models.reqif_spec_hierarchy import ReqIFSpecHierarchy
    from reqif.models.reqif_spec_object import (
        ReqIFSpecObject,
        SpecObjectAttribute,
    )
    from reqif.models.reqif_spec_object_type import (
        ReqIFSpecObjectType,
        SpecAttributeDefinition,
    )
    from reqif.models.reqif_spec_relation import ReqIFSpecRelation
    from reqif.models.reqif_spec_relation_type import ReqIFSpecRelationType
    from reqif.models.reqif_specification import ReqIFSpecification
    from reqif.models.reqif_specification_type import ReqIFSpecificationType
    from reqif.models.reqif_types import SpecObjectAttributeType
    from reqif.reqif_bundle import ReqIFBundle
    from reqif.unparser import ReqIFUnparser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional dependency: ``reqif`` (issue #131)
# ---------------------------------------------------------------------------
# ``reqif`` is an optional, API-unstable (0.0.x) export dependency. Importing it
# at module level made it a hard boot requirement for the *entire* Django
# process: rest_api/urls.py transitively imports this module, so a missing or
# broken ``reqif`` install killed every REST route and every ``manage.py``
# command (including ``migrate`` and ``makemigrations --check``).
#
# The names below are therefore bound lazily into module globals on first use.
# ``from __future__ import annotations`` (see top of file) keeps the type
# annotations that reference them strings, so nothing resolves at import time.


def _load_reqif() -> None:
    """Bind the optional ``reqif`` symbols into this module's globals.

    Idempotent and cheap after the first call. Raises a descriptive
    ``ImportError`` when the optional dependency is unavailable, so the failure
    surfaces when ReqIF export is actually invoked instead of at Django start.
    """
    global ReqIFCoreContent, ReqIFDataTypeDefinitionString, ReqIFNamespaceInfo
    global ReqIFReqIFContent, ReqIFReqIFHeader, ReqIFSpecHierarchy
    global ReqIFSpecObject, SpecObjectAttribute, ReqIFSpecObjectType
    global SpecAttributeDefinition, ReqIFSpecRelation, ReqIFSpecRelationType
    global ReqIFSpecification, ReqIFSpecificationType, SpecObjectAttributeType
    global ReqIFBundle, ReqIFUnparser

    if "ReqIFBundle" in globals():
        return

    try:
        from reqif.models.reqif_core_content import (  # noqa: F401
            ReqIFCoreContent,
        )
        from reqif.models.reqif_data_type import (  # noqa: F401
            ReqIFDataTypeDefinitionString,
        )
        from reqif.models.reqif_namespace_info import (  # noqa: F401
            ReqIFNamespaceInfo,
        )
        from reqif.models.reqif_req_if_content import (  # noqa: F401
            ReqIFReqIFContent,
        )
        from reqif.models.reqif_reqif_header import (  # noqa: F401
            ReqIFReqIFHeader,
        )
        from reqif.models.reqif_spec_hierarchy import (  # noqa: F401
            ReqIFSpecHierarchy,
        )
        from reqif.models.reqif_spec_object import (  # noqa: F401
            ReqIFSpecObject,
            SpecObjectAttribute,
        )
        from reqif.models.reqif_spec_object_type import (  # noqa: F401
            ReqIFSpecObjectType,
            SpecAttributeDefinition,
        )
        from reqif.models.reqif_spec_relation import (  # noqa: F401
            ReqIFSpecRelation,
        )
        from reqif.models.reqif_spec_relation_type import (  # noqa: F401
            ReqIFSpecRelationType,
        )
        from reqif.models.reqif_specification import (  # noqa: F401
            ReqIFSpecification,
        )
        from reqif.models.reqif_specification_type import (  # noqa: F401
            ReqIFSpecificationType,
        )
        from reqif.models.reqif_types import (  # noqa: F401
            SpecObjectAttributeType,
        )
        from reqif.reqif_bundle import ReqIFBundle  # noqa: F401
        from reqif.unparser import ReqIFUnparser  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "ReqIF export/import requires the optional 'reqif' package "
            "(see backend/requirements.txt). Install it to enable ReqIF "
            "interoperability; all other functionality is unaffected."
        ) from exc

# ---------------------------------------------------------------------------
# Stable, deterministic ReqIF identifiers
# ---------------------------------------------------------------------------

_DATATYPE_STRING = "DT-String"
_SPEC_OBJECT_TYPE_NEED = "ST-StakeholderNeed"
_SPEC_OBJECT_TYPE_REQUIREMENT = "ST-Requirement"
# D14d: TestCase and Icd as standard-conformant SPEC-OBJECTs.
_SPEC_OBJECT_TYPE_TESTCASE = "ST-TestCase"
_SPEC_OBJECT_TYPE_ICD = "ST-Icd"
_SPECIFICATION_TYPE = "ST-Specification-Default"

_ATTR_UID = "ATTR-UID"
_ATTR_TITLE = "ATTR-TITLE"
_ATTR_DESCRIPTION = "ATTR-DESCRIPTION"
_ATTR_STATUS = "ATTR-STATUS"
_ATTR_CATEGORY = "ATTR-CATEGORY"
_ATTR_CUSTOM_FIELDS = "ATTR-CUSTOM-FIELDS"
_ATTR_VERIFICATION_METHOD = "ATTR-VERIFICATION-METHOD"
_ATTR_MOSCOW_PRIORITY = "ATTR-MOSCOW-PRIORITY"
#: P2/V4/V5 — the Requirement's tier: stable ladder key plus the ladder's
#: display label. Requirement-only (a StakeholderNeed carries no tier).
_ATTR_TIER_KEY = "ATTR-TIER-KEY"
_ATTR_TIER_NAME = "ATTR-TIER-NAME"

# D14d: TestCase-only attributes (all STRING, JSON-encoded where structured).
_ATTR_TEST_TYPE = "ATTR-TEST-TYPE"
_ATTR_SCENARIO_KIND = "ATTR-SCENARIO-KIND"
_ATTR_STEPS_JSON = "ATTR-STEPS-JSON"
_ATTR_ORIGIN = "ATTR-ORIGIN"
_ATTR_REVIEWED = "ATTR-REVIEWED"
_ATTR_TEST_SUSPECT = "ATTR-TEST-SUSPECT"

# D14d: Icd-only attributes (all STRING, JSON-encoded where structured).
_ATTR_ICD_NAME = "ATTR-ICD-NAME"
_ATTR_ICD_SOURCE_ELEMENT = "ATTR-ICD-SOURCE-ELEMENT"
_ATTR_ICD_TARGET_ELEMENT = "ATTR-ICD-TARGET-ELEMENT"
_ATTR_ICD_DIRECTION = "ATTR-ICD-DIRECTION"
_ATTR_ICD_INTERFACE_TYPE = "ATTR-ICD-INTERFACE-TYPE"
_ATTR_ICD_SEMANTIC_DESCRIPTION = "ATTR-ICD-SEMANTIC-DESCRIPTION"
_ATTR_ICD_PRECONDITIONS = "ATTR-ICD-PRECONDITIONS"
_ATTR_ICD_POSTCONDITIONS = "ATTR-ICD-POSTCONDITIONS"
_ATTR_ICD_INVARIANTS = "ATTR-ICD-INVARIANTS"
_ATTR_ICD_CURRENT_REVISION = "ATTR-ICD-CURRENT-REVISION"

# INT-06 finding 076: the ReqIF XSD declares LAST-CHANGE (xsd:dateTime) and,
# for DATATYPE-DEFINITION-STRING, MAX-LENGTH as *required* on the elements this
# exporter emits. Omitting them made the document XSD-invalid. The value is a
# real timestamp (export time) rather than a fabricated epoch: ReqIF's
# LAST-CHANGE means "when the element last changed", and the exporter
# materialises the document now.
_MAX_STRING_LENGTH = "65535"

_NCNAME_INVALID_RE = re.compile(r"[^A-Za-z0-9_.\-]")


def _now_iso() -> str:
    """Return the current time as an XSD ``dateTime`` string (UTC)."""
    return timezone.now().isoformat()


def _sanitize_ncname_fragment(value: str) -> str:
    """Replace characters illegal in an XML NCName fragment with '-'.

    Used only for the (already-static-prefixed) link_type suffix, so the
    result never needs to satisfy the "must not start with a digit" rule on
    its own — the static "SRT-" prefix guarantees a legal first character.
    """
    cleaned = _NCNAME_INVALID_RE.sub("-", (value or "").strip())
    return cleaned or "unknown"


def _artifact_spec_object_id(artifact_id: UUID) -> str:
    return f"_{artifact_id}"


def _icd_spec_object_id(icd_id: UUID) -> str:
    """SPEC-OBJECT IDENTIFIER for an Icd (which may have no backing Artifact).

    An ICD always has its own entity id, so this stays deterministic even when
    ``Icd.artifact`` is NULL. The ``_icd-`` prefix keeps it an NCName and keeps
    it distinct from the ``_<uuid>`` artifact-backed form.
    """
    return f"_icd-{icd_id}"


def _bool_text(value: bool | None) -> str:
    """Serialise a boolean as an explicit ReqIF STRING token."""
    return "true" if value else "false"


def _spec_object_identifier(
    artifact_id: UUID, reqif_identifier_by_id: dict[UUID, str]
) -> str:
    """SPEC-OBJECT IDENTIFIER for *artifact_id* (issue #1003).

    A stored external ``reqif_identifier`` wins, so a re-export back to the
    foreign tool keeps that tool's identity; otherwise the deterministic
    internal ``_<Artifact.id>`` form is used (the pre-#1003 behaviour, and the
    reason existing exports/tests are unchanged).
    """
    stored = reqif_identifier_by_id.get(artifact_id)
    return stored if stored else _artifact_spec_object_id(artifact_id)


def _artifact_hierarchy_id(artifact_id: UUID) -> str:
    return f"_h-{artifact_id}"


def _specification_id(workspace_id: UUID) -> str:
    return f"_spec-{workspace_id}"


def _header_id(workspace_id: UUID) -> str:
    return f"_header-{workspace_id}"


def _relation_id(tracelink_id: UUID) -> str:
    return f"_r-{tracelink_id}"


def _relation_type_id(link_type: str) -> str:
    return f"SRT-{_sanitize_ncname_fragment(link_type)}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ReqifExportService(ServiceBase):
    """ReqIF 1.2 export for Needs, Requirements, TestCases, Icds and TraceLinks.

    COMP-AS-008 (ExportService family). REQ-146 / D14d.

    Usage::

        svc = ReqifExportService()
        result = svc.export_reqif(workspace_id=ws_uuid, ctx=auth_ctx)
        response.write(result.content)
    """

    def export_reqif(self, workspace_id: UUID | str, ctx: AuthContext) -> ExportResult:
        """Export a workspace as a ReqIF 1.2 document.

        REQ-146.

        Args:
            workspace_id: Workspace UUID.
            ctx: AuthContext for tenant scoping.

        Returns:
            ExportResult with media_type="application/xml", content=str (XML).

        Raises:
            NotFoundError: workspace does not exist in the active tenant.
            ImportError: the optional ``reqif`` package is not installed.
        """
        _load_reqif()
        self._set_tenant_context(ctx)

        from persistence.models import Workspace

        ws_uuid = UUID(str(workspace_id))
        try:
            workspace = Workspace.objects.get(id=ws_uuid, tenant_id=ctx.tenant_id)
        except Workspace.DoesNotExist:
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        # INT-06 finding 076: one export timestamp, reused as LAST-CHANGE on
        # every element the ReqIF XSD marks it required.
        now = _now_iso()
        (
            spec_objects,
            hierarchy_children,
            exported_ids,
            reqif_identifier_by_id,
            spec_object_ids,
        ) = self._build_spec_objects(ws_uuid, last_change=now)
        spec_relations, relation_types = self._build_spec_relations(
            ws_uuid,
            exported_ids,
            reqif_identifier_by_id,
            spec_object_ids,
            last_change=now,
        )

        spec_types: list[Any] = [
            self._build_need_type(now),
            self._build_requirement_type(now),
            self._build_test_case_type(now),
            self._build_icd_type(now),
            ReqIFSpecificationType(
                identifier=_SPECIFICATION_TYPE,
                long_name="Default Specification",
                # LAST-CHANGE (required by the ReqIF XSD) also serves
                # StrictDoc's SPECIFICATION-TYPE round-trip — see
                # reqif.parsers.spec_types.specification_type_parser.
                last_change=now,
            ),
        ]
        spec_types.extend(relation_types)

        specification = ReqIFSpecification(
            identifier=_specification_id(ws_uuid),
            long_name=f"{workspace.name} — Artifact Hierarchy",
            specification_type=_SPECIFICATION_TYPE,
            # LAST-CHANGE is required by the ReqIF XSD's SPECIFICATION type.
            last_change=now,
            children=hierarchy_children,
        )

        content = ReqIFReqIFContent(
            data_types=[
                # MAX-LENGTH is required by the ReqIF XSD's
                # DATATYPE-DEFINITION-STRING; LAST-CHANGE likewise.
                ReqIFDataTypeDefinitionString(
                    identifier=_DATATYPE_STRING,
                    last_change=now,
                    max_length=_MAX_STRING_LENGTH,
                )
            ],
            spec_types=spec_types,
            spec_objects=spec_objects,
            spec_relations=spec_relations,
            specifications=[specification],
        )

        bundle = ReqIFBundle(
            namespace_info=ReqIFNamespaceInfo.create_default(),
            req_if_header=ReqIFReqIFHeader(
                identifier=_header_id(ws_uuid),
                title=f"ReqogniLoom Export — {workspace.name}",
                comment="Generated by ReqogniLoom ReqifExportService (REQ-146).",
                creation_time=_now_iso(),
                req_if_tool_id="ReqogniLoom-ReqifExportService",
                # INT-06 finding 076: the ReqIF XSD fixes REQ-IF-VERSION to
                # "1.0" (``reqif/reqif_schema/reqif.xsd``:
                # ``<xsd:element fixed="1.0" name="REQ-IF-VERSION">``). The
                # value denotes the ReqIF *schema* version (always 1.0 for the
                # 2011 namespace); the 1.2 interoperability profile lives in
                # the namespace/tool ids, not here. Emitting "1.2" produced an
                # XSD violation.
                req_if_version="1.0",
                source_tool_id="ReqogniLoom",
            ),
            core_content=ReqIFCoreContent(req_if_content=content),
            tool_extensions_tag_exists=False,
            lookup=None,
            exceptions=[],
        )

        xml = ReqIFUnparser.unparse(bundle)

        slug = slugify(workspace.name) or str(workspace.id)
        return ExportResult(
            content=xml,
            media_type="application/xml",
            filename=f"{slug}.reqif",
            record_count=len(spec_objects),
        )

    # ---------- SPEC-OBJECT-TYPE builders ----------

    @staticmethod
    def _attribute_definition(
        identifier: str, long_name: str, last_change: str
    ) -> SpecAttributeDefinition:
        """A STRING attribute definition with the XSD-required LAST-CHANGE."""
        _load_reqif()
        return SpecAttributeDefinition(
            attribute_type=SpecObjectAttributeType.STRING,
            identifier=identifier,
            datatype_definition=_DATATYPE_STRING,
            long_name=long_name,
            last_change=last_change,
        )

    @classmethod
    def _build_need_type(cls, last_change: str) -> ReqIFSpecObjectType:
        _load_reqif()
        return ReqIFSpecObjectType(
            identifier=_SPEC_OBJECT_TYPE_NEED,
            long_name="Stakeholder Need",
            last_change=last_change,
            # INT-06 finding 076: the attribute definitions are declared once,
            # in this type. The ReqIF XSD types IDENTIFIER as ``xsd:ID`` (a
            # document-global unique id), so the shared attributes (UID, TITLE,
            # DESCRIPTION, STATUS, CATEGORY, CUSTOM-FIELDS) cannot be re-declared
            # in the Requirement type without a duplicate-id violation. ReqIF
            # resolves ``ATTRIBUTE-DEFINITION-STRING-REF`` as ``xsd:IDREF``
            # (document-wide), so the Requirement SPEC-OBJECTs reference these
            # same definitions — the pre-fix behaviour, where both types
            # declared the same ids, was the XSD violation.
            attribute_definitions=[
                cls._attribute_definition(_ATTR_UID, "UID", last_change),
                cls._attribute_definition(_ATTR_TITLE, "Title", last_change),
                cls._attribute_definition(
                    _ATTR_DESCRIPTION, "Description", last_change
                ),
                cls._attribute_definition(_ATTR_STATUS, "Status", last_change),
                cls._attribute_definition(_ATTR_CATEGORY, "Category", last_change),
                cls._attribute_definition(
                    _ATTR_MOSCOW_PRIORITY, "MoSCoW Priority", last_change
                ),
                cls._attribute_definition(
                    _ATTR_CUSTOM_FIELDS, "Custom Fields (JSON)", last_change
                ),
            ],
        )

    @classmethod
    def _build_requirement_type(cls, last_change: str) -> ReqIFSpecObjectType:
        _load_reqif()
        return ReqIFSpecObjectType(
            identifier=_SPEC_OBJECT_TYPE_REQUIREMENT,
            long_name="Requirement",
            last_change=last_change,
            # See _build_need_type: the shared attribute definitions live in the
            # Need type; this type declares only its own (unique) definition and
            # its SPEC-OBJECTs reference the shared ids via xsd:IDREF.
            attribute_definitions=[
                cls._attribute_definition(
                    _ATTR_VERIFICATION_METHOD,
                    "Verification Method",
                    last_change,
                ),
                cls._attribute_definition(_ATTR_TIER_KEY, "Tier Key", last_change),
                cls._attribute_definition(_ATTR_TIER_NAME, "Tier Name", last_change),
            ],
        )

    @classmethod
    def _build_test_case_type(cls, last_change: str) -> ReqIFSpecObjectType:
        """D14d: SPEC-OBJECT-TYPE for TestCase (standard STRING attributes)."""
        _load_reqif()
        return ReqIFSpecObjectType(
            identifier=_SPEC_OBJECT_TYPE_TESTCASE,
            long_name="Test Case",
            last_change=last_change,
            # Only this type's own definitions are declared here; the shared
            # ones (UID/TITLE/DESCRIPTION/STATUS/CATEGORY/CUSTOM-FIELDS) live
            # on the Need type and are referenced document-wide via xsd:IDREF.
            attribute_definitions=[
                cls._attribute_definition(_ATTR_TEST_TYPE, "Test Type", last_change),
                cls._attribute_definition(
                    _ATTR_SCENARIO_KIND, "Scenario Kind", last_change
                ),
                cls._attribute_definition(_ATTR_STEPS_JSON, "Steps (JSON)", last_change),
                cls._attribute_definition(_ATTR_ORIGIN, "Origin", last_change),
                cls._attribute_definition(_ATTR_REVIEWED, "Reviewed", last_change),
                cls._attribute_definition(
                    _ATTR_TEST_SUSPECT, "Suspect", last_change
                ),
            ],
        )

    @classmethod
    def _build_icd_type(cls, last_change: str) -> ReqIFSpecObjectType:
        """D14d: SPEC-OBJECT-TYPE for Icd (standard STRING attributes)."""
        _load_reqif()
        return ReqIFSpecObjectType(
            identifier=_SPEC_OBJECT_TYPE_ICD,
            long_name="Interface Control Document",
            last_change=last_change,
            attribute_definitions=[
                cls._attribute_definition(_ATTR_ICD_NAME, "ICD Name", last_change),
                cls._attribute_definition(
                    _ATTR_ICD_SOURCE_ELEMENT, "Source Element", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_TARGET_ELEMENT, "Target Element", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_DIRECTION, "Direction", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_INTERFACE_TYPE, "Interface Type", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_SEMANTIC_DESCRIPTION,
                    "Semantic Description",
                    last_change,
                ),
                cls._attribute_definition(
                    _ATTR_ICD_PRECONDITIONS, "Preconditions (JSON)", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_POSTCONDITIONS, "Postconditions (JSON)", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_INVARIANTS, "Invariants (JSON)", last_change
                ),
                cls._attribute_definition(
                    _ATTR_ICD_CURRENT_REVISION, "Current Revision", last_change
                ),
            ],
        )

    # ---------- SPEC-OBJECT + SPEC-HIERARCHY builders ----------

    @classmethod
    def _build_spec_objects(
        cls, workspace_id: UUID, last_change: str | None = None
    ) -> tuple[list[ReqIFSpecObject], list[ReqIFSpecHierarchy], dict[UUID, str]]:
        """Fetch all exportable entities, build SPEC-OBJECTs and the hierarchy.

        D14d adds TestCase and Icd to the two original types. Returns:
            (spec_objects, root_hierarchy_children, exported_artifact_ids)
            where exported_artifact_ids maps Artifact.id -> artifact_type for
            every artifact-backed exported entity (Need/Requirement/TestCase
            and Icd-with-artifact) — used by _build_spec_relations to decide
            which TraceLinks are in scope.
        """
        from icd.models import Icd
        from persistence.models import Artifact, Requirement, StakeholderNeed, TestCase

        # All artifacts in the workspace (any type) — needed to walk parent
        # chains through non-exported intermediate types (ArchitectureElement,
        # TestCase, ...).
        all_artifacts = list(
            Artifact.objects.filter(workspace_id=workspace_id).values(
                "id",
                "parent_id",
                "artifact_type",
                "custom_fields",
                # Issue #1003: the external ReqIF identity, preferred over the
                # internal `_<Artifact.id>` fallback when present.
                "reqif_identifier",
                "reqif_uid",
            )
        )
        parent_by_id: dict[UUID, UUID | None] = {
            a["id"]: a["parent_id"] for a in all_artifacts
        }
        custom_fields_by_id: dict[UUID, dict] = {
            a["id"]: (a["custom_fields"] or {}) for a in all_artifacts
        }
        reqif_identifier_by_id: dict[UUID, str] = {
            a["id"]: (a["reqif_identifier"] or "") for a in all_artifacts
        }
        reqif_uid_by_id: dict[UUID, str] = {
            a["id"]: (a["reqif_uid"] or "") for a in all_artifacts
        }

        needs = StakeholderNeed.objects.filter(
            artifact__workspace_id=workspace_id
        ).select_related("artifact")
        reqs = Requirement.objects.filter(
            artifact__workspace_id=workspace_id
        ).select_related("artifact")
        test_cases = TestCase.objects.filter(
            artifact__workspace_id=workspace_id
        ).select_related("artifact")
        icds = Icd.objects.filter(workspace_id=workspace_id)

        exported_ids: dict[UUID, str] = {}
        spec_objects: list[ReqIFSpecObject] = []

        # Datenmodell-Konsolidierung Phase 1: ``status`` is no longer written
        # by the workflow engine, so it is resolved through
        # workflow.state_reader (batched) instead of the (now write-once,
        # frozen-at-creation) column — ReqIF is an interchange format
        # consumed by external tools, so exporting a stale status is worse
        # here than in an internal-only view.
        from workflow import state_reader

        need_states = state_reader.current_states(
            "StakeholderNeed", (need.id for need in needs)
        )
        req_states = state_reader.current_states("Requirement", (req.id for req in reqs))
        tc_states = state_reader.current_states("TestCase", (tc.id for tc in test_cases))
        icd_states = state_reader.current_states("Icd", (icd.id for icd in icds))

        # Task 12: the ``status`` column is dropped, so an item with no
        # WorkflowItemState falls back to its preset's initial state instead
        # (documented, reviewed data-loss tradeoff, see Task 12 report
        # Finding 2).
        need_initial_state = state_reader.initial_state("StakeholderNeed")
        req_initial_state = state_reader.initial_state("Requirement")
        tc_initial_state = state_reader.initial_state("TestCase")
        icd_initial_state = state_reader.initial_state("Icd")

        # P2/V4/V5: one ladder lookup per export (never per Requirement), so
        # every SPEC-OBJECT can publish its tier_key and the ladder display
        # name next to it.
        from application.export_service import tier_display_name
        from application.tier_ladder_service import TierLadderService

        tier_names = {
            entry.tier_key: tier_display_name(entry)
            for entry in TierLadderService().get(workspace_id).entries
        }

        now = last_change if last_change is not None else _now_iso()
        # artifact id -> the SPEC-OBJECT identifier actually emitted. Icd uses
        # `_icd-<entity-id>` while the other types use `_<artifact-id>`; using
        # the generic form for Icd produced dangling IDREFs in SPEC-HIERARCHY
        # and SPEC-RELATION (XSD violation).
        spec_object_ids: dict[UUID, str] = {}
        for need in needs:
            exported_ids[need.artifact_id] = "StakeholderNeed"
            spec_object_ids[need.artifact_id] = _spec_object_identifier(
                need.artifact_id, reqif_identifier_by_id
            )
            spec_objects.append(
                cls._spec_object_from_need(
                    need,
                    custom_fields_by_id.get(need.artifact_id, {}),
                    need_states.get(str(need.id)) or need_initial_state,
                    identifier=_spec_object_identifier(
                        need.artifact_id, reqif_identifier_by_id
                    ),
                    external_uid=reqif_uid_by_id.get(need.artifact_id, ""),
                    last_change=now,
                )
            )

        for req in reqs:
            exported_ids[req.artifact_id] = "Requirement"
            spec_object_ids[req.artifact_id] = _spec_object_identifier(
                req.artifact_id, reqif_identifier_by_id
            )
            spec_objects.append(
                cls._spec_object_from_requirement(
                    req,
                    custom_fields_by_id.get(req.artifact_id, {}),
                    req_states.get(str(req.id)) or req_initial_state,
                    identifier=_spec_object_identifier(
                        req.artifact_id, reqif_identifier_by_id
                    ),
                    external_uid=reqif_uid_by_id.get(req.artifact_id, ""),
                    tier_name=tier_names.get(req.tier_key),
                    last_change=now,
                )
            )

        for tc in test_cases:
            exported_ids[tc.artifact_id] = "TestCase"
            spec_object_ids[tc.artifact_id] = _spec_object_identifier(
                tc.artifact_id, reqif_identifier_by_id
            )
            spec_objects.append(
                cls._spec_object_from_test_case(
                    tc,
                    custom_fields_by_id.get(tc.artifact_id, {}),
                    tc_states.get(str(tc.id)) or tc_initial_state,
                    identifier=_spec_object_identifier(
                        tc.artifact_id, reqif_identifier_by_id
                    ),
                    external_uid=reqif_uid_by_id.get(tc.artifact_id, ""),
                    last_change=now,
                )
            )

        for icd in icds:
            # Only artifact-backed ICDs participate in the hierarchy/relations
            # (their id is stable through the backing Artifact). An ICD with no
            # artifact is still exported as a standalone SPEC-OBJECT.
            if icd.artifact_id is not None:
                exported_ids[icd.artifact_id] = "Icd"
                spec_object_ids[icd.artifact_id] = _icd_spec_object_id(icd.id)
            spec_objects.append(
                cls._spec_object_from_icd(
                    icd,
                    custom_fields_by_id.get(icd.artifact_id, {})
                    if icd.artifact_id
                    else {},
                    icd_states.get(str(icd.id)) or icd_initial_state,
                    external_uid=reqif_uid_by_id.get(icd.artifact_id, "")
                    if icd.artifact_id
                    else "",
                    last_change=now,
                )
            )

        # Sort spec_objects by identifier for a deterministic document order
        # independent of DB fetch order.
        spec_objects.sort(key=lambda so: so.identifier)

        hierarchy_children = cls._build_hierarchy(
            exported_ids,
            parent_by_id,
            reqif_identifier_by_id,
            spec_object_ids,
            last_change=now,
        )

        return (
            spec_objects,
            hierarchy_children,
            exported_ids,
            reqif_identifier_by_id,
            spec_object_ids,
        )

    @staticmethod
    def _string_attr(definition_ref: str, value: str) -> SpecObjectAttribute:
        _load_reqif()
        return SpecObjectAttribute(
            attribute_type=SpecObjectAttributeType.STRING,
            definition_ref=definition_ref,
            value=value or "",
        )

    @classmethod
    def _spec_object_from_need(
        cls,
        need: Any,
        custom_fields: dict,
        status: str | None = None,
        *,
        identifier: str | None = None,
        external_uid: str = "",
        last_change: str | None = None,
    ) -> ReqIFSpecObject:
        _load_reqif()
        from workflow import state_reader

        attributes = [
            # Issue #1003: the external ReqIF UID wins; the local readable
            # `uid` is only the fallback for artifacts with no ReqIF origin.
            cls._string_attr(_ATTR_UID, external_uid or need.uid or ""),
            cls._string_attr(_ATTR_TITLE, need.title or ""),
            cls._string_attr(_ATTR_DESCRIPTION, need.description or ""),
            cls._string_attr(
                _ATTR_STATUS,
                (status if status is not None else state_reader.initial_state("StakeholderNeed"))
                or "",
            ),
            cls._string_attr(_ATTR_CATEGORY, need.category or ""),
        ]
        if need.moscow_priority:
            attributes.append(cls._string_attr(_ATTR_MOSCOW_PRIORITY, need.moscow_priority))
        if custom_fields:
            attributes.append(
                cls._string_attr(
                    _ATTR_CUSTOM_FIELDS,
                    json.dumps(custom_fields, sort_keys=True, ensure_ascii=False),
                )
            )
        # INT-06 finding 076: LAST-CHANGE is a required SPEC-OBJECT attribute in
        # the ReqIF XSD; ReqIFSpecObject.create() omits it.
        return ReqIFSpecObject(
            identifier=identifier or _artifact_spec_object_id(need.artifact_id),
            spec_object_type=_SPEC_OBJECT_TYPE_NEED,
            attributes=attributes,
            last_change=last_change,
        )

    @classmethod
    def _spec_object_from_requirement(
        cls,
        req: Any,
        custom_fields: dict,
        status: str | None = None,
        *,
        identifier: str | None = None,
        external_uid: str = "",
        tier_name: str | None = None,
        last_change: str | None = None,
    ) -> ReqIFSpecObject:
        _load_reqif()
        from workflow import state_reader

        attributes = [
            # Issue #1003: external ReqIF UID wins, local `uid` is the fallback.
            cls._string_attr(_ATTR_UID, external_uid or req.uid or ""),
            cls._string_attr(_ATTR_TITLE, req.title or ""),
            cls._string_attr(_ATTR_DESCRIPTION, req.description or ""),
            cls._string_attr(
                _ATTR_STATUS,
                (status if status is not None else state_reader.initial_state("Requirement"))
                or "",
            ),
            cls._string_attr(_ATTR_CATEGORY, req.category or ""),
        ]
        if req.verification_method:
            attributes.append(
                cls._string_attr(_ATTR_VERIFICATION_METHOD, req.verification_method)
            )
        # P2/V4/V5: publish the stable ladder key and its display label. The
        # integer alias ``level`` stays internal (position in the ladder); the
        # key is the interchange-stable value.
        if getattr(req, "tier_key", None):
            attributes.append(cls._string_attr(_ATTR_TIER_KEY, req.tier_key))
            attributes.append(
                cls._string_attr(_ATTR_TIER_NAME, tier_name or req.tier_key)
            )
        if custom_fields:
            attributes.append(
                cls._string_attr(
                    _ATTR_CUSTOM_FIELDS,
                    json.dumps(custom_fields, sort_keys=True, ensure_ascii=False),
                )
            )
        # INT-06 finding 076: LAST-CHANGE is required by the ReqIF XSD.
        return ReqIFSpecObject(
            identifier=identifier or _artifact_spec_object_id(req.artifact_id),
            spec_object_type=_SPEC_OBJECT_TYPE_REQUIREMENT,
            attributes=attributes,
            last_change=last_change,
        )

    @classmethod
    def _spec_object_from_test_case(
        cls,
        tc: Any,
        custom_fields: dict,
        status: str | None = None,
        *,
        identifier: str | None = None,
        external_uid: str = "",
        last_change: str | None = None,
    ) -> ReqIFSpecObject:
        """D14d: encode a TestCase as a standard SPEC-OBJECT."""
        _load_reqif()
        from workflow import state_reader

        attributes = [
            cls._string_attr(_ATTR_UID, external_uid or tc.uid or ""),
            cls._string_attr(_ATTR_TITLE, tc.title or ""),
            cls._string_attr(_ATTR_DESCRIPTION, tc.description or ""),
            cls._string_attr(
                _ATTR_STATUS,
                (status if status is not None else state_reader.initial_state("TestCase"))
                or "",
            ),
        ]
        for ref, value in (
            (_ATTR_TEST_TYPE, tc.test_type),
            (_ATTR_SCENARIO_KIND, tc.scenario_kind),
            (_ATTR_ORIGIN, tc.origin),
        ):
            if value:
                attributes.append(cls._string_attr(ref, value))
        attributes.append(
            cls._string_attr(
                _ATTR_STEPS_JSON,
                json.dumps(tc.steps or [], sort_keys=True, ensure_ascii=False),
            )
        )
        attributes.append(cls._string_attr(_ATTR_REVIEWED, _bool_text(tc.reviewed)))
        attributes.append(
            cls._string_attr(_ATTR_TEST_SUSPECT, _bool_text(tc.suspect))
        )
        if custom_fields:
            attributes.append(
                cls._string_attr(
                    _ATTR_CUSTOM_FIELDS,
                    json.dumps(custom_fields, sort_keys=True, ensure_ascii=False),
                )
            )
        return ReqIFSpecObject(
            identifier=identifier or _artifact_spec_object_id(tc.artifact_id),
            spec_object_type=_SPEC_OBJECT_TYPE_TESTCASE,
            attributes=attributes,
            last_change=last_change,
        )

    @classmethod
    def _spec_object_from_icd(
        cls,
        icd: Any,
        custom_fields: dict,
        status: str | None = None,
        *,
        external_uid: str = "",
        last_change: str | None = None,
    ) -> ReqIFSpecObject:
        """D14d: encode an Icd as a standard SPEC-OBJECT."""
        _load_reqif()
        from workflow import state_reader

        attributes = [
            cls._string_attr(_ATTR_UID, external_uid or ""),
            cls._string_attr(_ATTR_TITLE, icd.name or ""),
            cls._string_attr(_ATTR_DESCRIPTION, icd.semantic_description or ""),
            cls._string_attr(
                _ATTR_STATUS,
                (status if status is not None else state_reader.initial_state("Icd"))
                or "",
            ),
            cls._string_attr(_ATTR_ICD_NAME, icd.name or ""),
            cls._string_attr(_ATTR_ICD_SOURCE_ELEMENT, str(icd.source_element_id)),
            cls._string_attr(_ATTR_ICD_TARGET_ELEMENT, str(icd.target_element_id)),
            cls._string_attr(_ATTR_ICD_DIRECTION, icd.direction or ""),
            cls._string_attr(
                _ATTR_ICD_CURRENT_REVISION, str(icd.current_revision or 0)
            ),
        ]
        for ref, value in (
            (_ATTR_ICD_INTERFACE_TYPE, icd.interface_type),
            (_ATTR_ICD_SEMANTIC_DESCRIPTION, icd.semantic_description),
        ):
            if value:
                attributes.append(cls._string_attr(ref, value))
        for ref, value in (
            (_ATTR_ICD_PRECONDITIONS, icd.preconditions),
            (_ATTR_ICD_POSTCONDITIONS, icd.postconditions),
            (_ATTR_ICD_INVARIANTS, icd.invariants),
        ):
            attributes.append(
                cls._string_attr(
                    ref,
                    json.dumps(value or [], sort_keys=True, ensure_ascii=False),
                )
            )
        if custom_fields:
            attributes.append(
                cls._string_attr(
                    _ATTR_CUSTOM_FIELDS,
                    json.dumps(custom_fields, sort_keys=True, ensure_ascii=False),
                )
            )
        return ReqIFSpecObject(
            identifier=_icd_spec_object_id(icd.id),
            spec_object_type=_SPEC_OBJECT_TYPE_ICD,
            attributes=attributes,
            last_change=last_change,
        )

    @staticmethod
    def _build_hierarchy(
        exported_ids: dict[UUID, str],
        parent_by_id: dict[UUID, UUID | None],
        reqif_identifier_by_id: dict[UUID, str],
        spec_object_ids: dict[UUID, str] | None = None,
        last_change: str | None = None,
    ) -> list[ReqIFSpecHierarchy]:
        """Build nested SPEC-HIERARCHY nodes from the Artifact.parent tree.

        Only exported (Need/Requirement) artifacts get a hierarchy node. When
        an exported artifact's nearest exported ancestor is not its direct
        Artifact.parent (because of an intervening non-exported artifact
        type), it is reparented to that ancestor — see module docstring
        "Known limitations".

        ``last_change`` is required by the ReqIF XSD on SPEC-HIERARCHY.
        """

        def nearest_exported_ancestor(artifact_id: UUID) -> UUID | None:
            seen: set = set()
            current = parent_by_id.get(artifact_id)
            while current is not None and current not in seen:
                if current in exported_ids:
                    return current
                seen.add(current)
                current = parent_by_id.get(current)
            return None

        # hierarchy_parent[artifact_id] = nearest exported ancestor, or None
        # (=> top-level child of the SPECIFICATION).
        children_by_parent: dict[UUID | None, list[UUID]] = {}
        for artifact_id in exported_ids:
            hp = nearest_exported_ancestor(artifact_id)
            children_by_parent.setdefault(hp, []).append(artifact_id)

        # Deterministic ordering within each level.
        for kids in children_by_parent.values():
            kids.sort(
                key=lambda aid: (spec_object_ids or {}).get(aid)
                or _spec_object_identifier(aid, reqif_identifier_by_id)
            )

        def build_nodes(parent: UUID | None, level: int) -> list[ReqIFSpecHierarchy]:
            _load_reqif()
            nodes = []
            for artifact_id in children_by_parent.get(parent, []):
                child_nodes = build_nodes(artifact_id, level + 1)
                nodes.append(
                    ReqIFSpecHierarchy(
                        identifier=_artifact_hierarchy_id(artifact_id),
                        spec_object=(spec_object_ids or {}).get(artifact_id)
                        or _spec_object_identifier(artifact_id, reqif_identifier_by_id),
                        level=level,
                        last_change=last_change,
                        children=child_nodes or None,
                    )
                )
            return nodes

        return build_nodes(None, 1)

    # ---------- SPEC-RELATION + SPEC-RELATION-TYPE builders ----------

    @staticmethod
    def _build_spec_relations(
        workspace_id: UUID,
        exported_ids: dict[UUID, str],
        reqif_identifier_by_id: dict[UUID, str],
        spec_object_ids: dict[UUID, str] | None = None,
        last_change: str | None = None,
    ) -> tuple[list[ReqIFSpecRelation], list[ReqIFSpecRelationType]]:
        _load_reqif()
        from persistence.models import TraceLink

        links = TraceLink.objects.filter(
            source__workspace_id=workspace_id, target__workspace_id=workspace_id
        ).values("id", "source_id", "target_id", "link_type")

        relations: list[ReqIFSpecRelation] = []
        used_link_types: set = set()

        for link in links:
            if link["source_id"] not in exported_ids or link["target_id"] not in exported_ids:
                # Link touches a type that is not exported (e.g.
                # ArchitectureElement) — out of scope. Need/Requirement/
                # TestCase and artifact-backed Icd are all in exported_ids.
                continue
            link_type = link["link_type"]
            used_link_types.add(link_type)
            relations.append(
                ReqIFSpecRelation(
                    identifier=_relation_id(link["id"]),
                    relation_type_ref=_relation_type_id(link_type),
                    source=(spec_object_ids or {}).get(link["source_id"])
                    or _spec_object_identifier(link["source_id"], reqif_identifier_by_id),
                    target=(spec_object_ids or {}).get(link["target_id"])
                    or _spec_object_identifier(link["target_id"], reqif_identifier_by_id),
                    # LAST-CHANGE is required by the ReqIF XSD on SPEC-RELATION.
                    last_change=last_change,
                )
            )

        relations.sort(key=lambda r: r.identifier)

        relation_types = [
            ReqIFSpecRelationType(
                identifier=_relation_type_id(lt),
                long_name=lt,
                # LAST-CHANGE is required by the ReqIF XSD on
                # SPEC-RELATION-TYPE.
                last_change=last_change,
            )
            for lt in sorted(used_link_types)
        ]

        return relations, relation_types


__all__ = ["ReqifExportService"]
