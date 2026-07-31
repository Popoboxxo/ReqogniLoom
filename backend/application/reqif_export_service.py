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

  Shared attribute definitions (both types, ``DATATYPE-DEFINITION-STRING``):
    ATTR-UID           <- {StakeholderNeed,Requirement}.uid
    ATTR-TITLE         <- .title
    ATTR-DESCRIPTION   <- .description
    ATTR-STATUS        <- .status
    ATTR-CATEGORY      <- .category
    ATTR-CUSTOM-FIELDS <- Artifact.custom_fields, JSON-serialised (sorted keys)
                           into a single opaque STRING attribute — see
                           "Known limitations" below.

  Requirement-only attribute:
    ATTR-VERIFICATION-METHOD <- Requirement.verification_method

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
  the canonical set: parent-child, derives-from, satisfies, verifies,
  implements, refines, documents, realizes, traces, copy-of, allocated-to,
  uses-term, decides). IDENTIFIER = ``SRT-<sanitised link_type>`` — non-NCName
  characters replaced with ``-`` (link_type values are already lower-kebab-case
  so this is a no-op in practice).

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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from uuid import UUID

from django.utils import timezone
from django.utils.text import slugify

from auth_tenancy.context import AuthContext

from application.base import NotFoundError, ServiceBase
from application.export_service import ExportResult

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
_SPECIFICATION_TYPE = "ST-Specification-Default"

_ATTR_UID = "ATTR-UID"
_ATTR_TITLE = "ATTR-TITLE"
_ATTR_DESCRIPTION = "ATTR-DESCRIPTION"
_ATTR_STATUS = "ATTR-STATUS"
_ATTR_CATEGORY = "ATTR-CATEGORY"
_ATTR_CUSTOM_FIELDS = "ATTR-CUSTOM-FIELDS"
_ATTR_VERIFICATION_METHOD = "ATTR-VERIFICATION-METHOD"
_ATTR_MOSCOW_PRIORITY = "ATTR-MOSCOW-PRIORITY"

_NCNAME_INVALID_RE = re.compile(r"[^A-Za-z0-9_.\-]")


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
    """ReqIF 1.2 export for StakeholderNeeds, Requirements and TraceLinks.

    COMP-AS-008 (ExportService family). REQ-146.

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

        spec_objects, hierarchy_children, exported_ids = self._build_spec_objects(ws_uuid)
        spec_relations, relation_types = self._build_spec_relations(ws_uuid, exported_ids)

        spec_types: List[Any] = [
            self._build_need_type(),
            self._build_requirement_type(),
            ReqIFSpecificationType(
                identifier=_SPECIFICATION_TYPE,
                long_name="Default Specification",
                # StrictDoc's SPECIFICATION-TYPE (un)parser requires
                # LAST-CHANGE to round-trip through parse() — see
                # reqif.parsers.spec_types.specification_type_parser.
                last_change=timezone.now().isoformat(),
            ),
        ]
        spec_types.extend(relation_types)

        specification = ReqIFSpecification(
            identifier=_specification_id(ws_uuid),
            long_name=f"{workspace.name} — Artifact Hierarchy",
            specification_type=_SPECIFICATION_TYPE,
            children=hierarchy_children,
        )

        content = ReqIFReqIFContent(
            data_types=[
                ReqIFDataTypeDefinitionString.create(identifier=_DATATYPE_STRING)
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
                creation_time=timezone.now().isoformat(),
                req_if_tool_id="ReqogniLoom-ReqifExportService",
                req_if_version="1.2",
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
    def _build_need_type() -> ReqIFSpecObjectType:
        _load_reqif()
        return ReqIFSpecObjectType.create(
            identifier=_SPEC_OBJECT_TYPE_NEED,
            long_name="Stakeholder Need",
            attribute_definitions=[
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_UID,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="UID",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_TITLE,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Title",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_DESCRIPTION,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Description",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_STATUS,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Status",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_CATEGORY,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Category",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_MOSCOW_PRIORITY,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="MoSCoW Priority",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_CUSTOM_FIELDS,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Custom Fields (JSON)",
                ),
            ],
        )

    @staticmethod
    def _build_requirement_type() -> ReqIFSpecObjectType:
        _load_reqif()
        return ReqIFSpecObjectType.create(
            identifier=_SPEC_OBJECT_TYPE_REQUIREMENT,
            long_name="Requirement",
            attribute_definitions=[
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_UID,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="UID",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_TITLE,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Title",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_DESCRIPTION,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Description",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_STATUS,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Status",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_CATEGORY,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Category",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_VERIFICATION_METHOD,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Verification Method",
                ),
                SpecAttributeDefinition.create(
                    attribute_type=SpecObjectAttributeType.STRING,
                    identifier=_ATTR_CUSTOM_FIELDS,
                    datatype_definition=_DATATYPE_STRING,
                    long_name="Custom Fields (JSON)",
                ),
            ],
        )

    # ---------- SPEC-OBJECT + SPEC-HIERARCHY builders ----------

    @classmethod
    def _build_spec_objects(
        cls, workspace_id: UUID
    ) -> Tuple[List[ReqIFSpecObject], List[ReqIFSpecHierarchy], Dict[UUID, str]]:
        """Fetch Needs+Requirements, build SPEC-OBJECTs and the hierarchy tree.

        Returns:
            (spec_objects, root_hierarchy_children, exported_artifact_ids)
            where exported_artifact_ids maps Artifact.id -> artifact_type for
            every exported (StakeholderNeed/Requirement) artifact — used by
            _build_spec_relations to decide which TraceLinks are in scope.
        """
        from persistence.models import Artifact, Requirement, StakeholderNeed

        # All artifacts in the workspace (any type) — needed to walk parent
        # chains through non-exported intermediate types (ArchitectureElement,
        # TestCase, ...).
        all_artifacts = list(
            Artifact.objects.filter(workspace_id=workspace_id).values(
                "id", "parent_id", "artifact_type", "custom_fields"
            )
        )
        parent_by_id: Dict[UUID, Optional[UUID]] = {
            a["id"]: a["parent_id"] for a in all_artifacts
        }
        custom_fields_by_id: Dict[UUID, dict] = {
            a["id"]: (a["custom_fields"] or {}) for a in all_artifacts
        }

        needs = StakeholderNeed.objects.filter(
            artifact__workspace_id=workspace_id
        ).select_related("artifact")
        reqs = Requirement.objects.filter(
            artifact__workspace_id=workspace_id
        ).select_related("artifact")

        exported_ids: Dict[UUID, str] = {}
        spec_objects: List[ReqIFSpecObject] = []

        for need in needs:
            exported_ids[need.artifact_id] = "StakeholderNeed"
            spec_objects.append(
                cls._spec_object_from_need(need, custom_fields_by_id.get(need.artifact_id, {}))
            )

        for req in reqs:
            exported_ids[req.artifact_id] = "Requirement"
            spec_objects.append(
                cls._spec_object_from_requirement(
                    req, custom_fields_by_id.get(req.artifact_id, {})
                )
            )

        # Sort spec_objects by identifier for a deterministic document order
        # independent of DB fetch order.
        spec_objects.sort(key=lambda so: so.identifier)

        hierarchy_children = cls._build_hierarchy(exported_ids, parent_by_id)

        return spec_objects, hierarchy_children, exported_ids

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
        cls, need: Any, custom_fields: dict
    ) -> ReqIFSpecObject:
        _load_reqif()
        attributes = [
            cls._string_attr(_ATTR_UID, need.uid or ""),
            cls._string_attr(_ATTR_TITLE, need.title or ""),
            cls._string_attr(_ATTR_DESCRIPTION, need.description or ""),
            cls._string_attr(_ATTR_STATUS, need.status or ""),
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
        return ReqIFSpecObject.create(
            identifier=_artifact_spec_object_id(need.artifact_id),
            spec_object_type=_SPEC_OBJECT_TYPE_NEED,
            attributes=attributes,
        )

    @classmethod
    def _spec_object_from_requirement(
        cls, req: Any, custom_fields: dict
    ) -> ReqIFSpecObject:
        _load_reqif()
        attributes = [
            cls._string_attr(_ATTR_UID, req.uid or ""),
            cls._string_attr(_ATTR_TITLE, req.title or ""),
            cls._string_attr(_ATTR_DESCRIPTION, req.description or ""),
            cls._string_attr(_ATTR_STATUS, req.status or ""),
            cls._string_attr(_ATTR_CATEGORY, req.category or ""),
        ]
        if req.verification_method:
            attributes.append(
                cls._string_attr(_ATTR_VERIFICATION_METHOD, req.verification_method)
            )
        if custom_fields:
            attributes.append(
                cls._string_attr(
                    _ATTR_CUSTOM_FIELDS,
                    json.dumps(custom_fields, sort_keys=True, ensure_ascii=False),
                )
            )
        return ReqIFSpecObject.create(
            identifier=_artifact_spec_object_id(req.artifact_id),
            spec_object_type=_SPEC_OBJECT_TYPE_REQUIREMENT,
            attributes=attributes,
        )

    @staticmethod
    def _build_hierarchy(
        exported_ids: Dict[UUID, str],
        parent_by_id: Dict[UUID, Optional[UUID]],
    ) -> List[ReqIFSpecHierarchy]:
        """Build nested SPEC-HIERARCHY nodes from the Artifact.parent tree.

        Only exported (Need/Requirement) artifacts get a hierarchy node. When
        an exported artifact's nearest exported ancestor is not its direct
        Artifact.parent (because of an intervening non-exported artifact
        type), it is reparented to that ancestor — see module docstring
        "Known limitations".
        """

        def nearest_exported_ancestor(artifact_id: UUID) -> Optional[UUID]:
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
        children_by_parent: Dict[Optional[UUID], List[UUID]] = {}
        for artifact_id in exported_ids:
            hp = nearest_exported_ancestor(artifact_id)
            children_by_parent.setdefault(hp, []).append(artifact_id)

        # Deterministic ordering within each level.
        for kids in children_by_parent.values():
            kids.sort(key=lambda aid: _artifact_spec_object_id(aid))

        def build_nodes(parent: Optional[UUID], level: int) -> List[ReqIFSpecHierarchy]:
            _load_reqif()
            nodes = []
            for artifact_id in children_by_parent.get(parent, []):
                child_nodes = build_nodes(artifact_id, level + 1)
                nodes.append(
                    ReqIFSpecHierarchy(
                        identifier=_artifact_hierarchy_id(artifact_id),
                        spec_object=_artifact_spec_object_id(artifact_id),
                        level=level,
                        children=child_nodes or None,
                    )
                )
            return nodes

        return build_nodes(None, 1)

    # ---------- SPEC-RELATION + SPEC-RELATION-TYPE builders ----------

    @staticmethod
    def _build_spec_relations(
        workspace_id: UUID, exported_ids: Dict[UUID, str]
    ) -> Tuple[List[ReqIFSpecRelation], List[ReqIFSpecRelationType]]:
        _load_reqif()
        from persistence.models import TraceLink

        links = TraceLink.objects.filter(
            source__workspace_id=workspace_id, target__workspace_id=workspace_id
        ).values("id", "source_id", "target_id", "link_type")

        relations: List[ReqIFSpecRelation] = []
        used_link_types: set = set()

        for link in links:
            if link["source_id"] not in exported_ids or link["target_id"] not in exported_ids:
                # Out of scope for REQ-146: link touches a non-exported
                # artifact type (e.g. ArchitectureElement, TestCase).
                continue
            link_type = link["link_type"]
            used_link_types.add(link_type)
            relations.append(
                ReqIFSpecRelation(
                    identifier=_relation_id(link["id"]),
                    relation_type_ref=_relation_type_id(link_type),
                    source=_artifact_spec_object_id(link["source_id"]),
                    target=_artifact_spec_object_id(link["target_id"]),
                )
            )

        relations.sort(key=lambda r: r.identifier)

        relation_types = [
            ReqIFSpecRelationType(
                identifier=_relation_type_id(lt),
                long_name=lt,
            )
            for lt in sorted(used_link_types)
        ]

        return relations, relation_types


__all__ = ["ReqifExportService"]
