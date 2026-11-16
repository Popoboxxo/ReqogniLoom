"""Writable-field adapters for the artifact update seam (Tabellenansicht S1, Task 1.1).

Every specialised type has its own ``update_X`` service with its own keyword
names and its own return type (ORM entity or DTO). The seam
(:mod:`application.artifact_fields_update`) must not know those differences, so
this module is the one place that does: one :class:`UpdateAdapter` per type with

* an **explicit allowlist** of content fields (never signature introspection —
  a parameter added to ``update_X`` for another purpose must not silently become
  bulk-writable),
* the callable that adapts ``(ctx, entity_id, fields, expected_version,
  change_reason)`` to that service's signature and normalises the result to
  ``(entity_id, new_version)``,
* the structural names no adapter may write (:data:`NEVER_BULK_WRITABLE`) and
  the workflow-owned fallback (:data:`WORKFLOW_OWNED_FALLBACK`).

Split rule: names in an adapter's allowlist go to the typed ``update_X``;
:data:`GATEWAY_FIELDS` (the Artifact-level system fields, the carrier-backed
actor fields and ``custom_fields``) go through
:class:`application.artifact_attribute_gateway.ArtifactAttributeGateway`;
anything else is refused with ``ValidationError`` naming the field.

The guard (:func:`assert_no_forbidden_fields`) is the single enforcement point
for "never writable through a bulk/inline path": ``parent_id``, ``uid``,
``sort_key`` and the structural identifiers, plus every attribute whose resolved
``editable`` is not ``True`` (``workflow`` = only a transition may change it,
``system`` = server-owned, ``automation`` = server-derived, ``False`` =
read-only). :data:`WORKFLOW_OWNED_FALLBACK` keeps ``status``/
``lifecycle_status`` closed even when the workspace has no definition.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from application.artifact_attribute_gateway import transport_field_names
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from persistence.models import Artifact

logger = logging.getLogger(__name__)

__all__ = [
    "ARTIFACT_UPDATE_ADAPTERS",
    "GATEWAY_FIELDS",
    "NEVER_BULK_WRITABLE",
    "WORKFLOW_OWNED_FALLBACK",
    "UpdateAdapter",
    "adapter_for",
    "assert_no_forbidden_fields",
    "classify_fields",
]

#: Names that address storage/structure, never editable content. Rejected for
#: the whole request (400), not per item.
NEVER_BULK_WRITABLE: frozenset[str] = frozenset(
    {
        "parent_id",
        "uid",
        "sort_key",
        "id",
        "version",
        "artifact_id",
        "workspace_id",
        "tenant_id",
    }
)

#: Rejected even when the workspace has no attribute definition: the state axis
#: belongs to the workflow engine.
WORKFLOW_OWNED_FALLBACK: frozenset[str] = frozenset({"status", "lifecycle_status"})

#: Fields the gateway writes (Artifact columns, carrier-backed actor fields,
#: extended attributes). ``custom_fields`` carries the extended part.
GATEWAY_FIELDS: frozenset[str] = frozenset(transport_field_names()) | {"custom_fields"}

UpdateCallable = Callable[
    [AuthContext, UUID, Mapping[str, Any], "int | None", "str | None"],
    tuple[UUID, int],
]


@dataclass(frozen=True)
class UpdateAdapter:
    """How one item type is written by the seam."""

    item_type: str
    entity_key: str
    #: ``Artifact`` related name of the typed row (``artifact.<accessor>``).
    accessor: str
    writable_fields: frozenset[str]
    update: UpdateCallable


def _version_of(result: Any) -> int:
    version = getattr(result, "version", None)
    if version is None:  # pragma: no cover - defensive
        raise ValidationError("The update service returned no version")
    return int(version)


def _requirement(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.requirement_service import RequirementService

    result = RequirementService().update_requirement(
        entity_id,
        ctx,
        expected_version=expected_version,
        change_reason=change_reason,
        **dict(fields),
    )
    return result.id, _version_of(result)


def _stakeholder_need(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.stakeholder_need_service import StakeholderNeedService

    result = StakeholderNeedService().update(
        ctx,
        entity_id,
        expected_version=expected_version,
        change_reason=change_reason or "",
        **dict(fields),
    )
    return result.id, _version_of(result)


def _architecture_element(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.architecture_service import ArchitectureService

    result = ArchitectureService().update_architecture_element(
        entity_id, ctx, expected_version, **dict(fields)
    )
    return result.id, _version_of(result)


def _test_case(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.test_service import TestService

    result = TestService().update_test_case(
        entity_id,
        ctx,
        expected_version=expected_version,
        change_reason=change_reason,
        **dict(fields),
    )
    return result.id, _version_of(result)


def _adr(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.adr_service import AdrService

    result = AdrService().update_adr(
        entity_id,
        ctx,
        expected_version=expected_version,
        change_reason=change_reason,
        **dict(fields),
    )
    return result.id, _version_of(result)


def _risk(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.risk_service import RiskService

    result = RiskService().update_risk(
        entity_id,
        ctx,
        expected_version=expected_version,
        change_reason=change_reason,
        **dict(fields),
    )
    return result.id, _version_of(result)


def _issue(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.issue_service import IssueService

    result = IssueService().update_issue(
        entity_id,
        ctx,
        expected_version=expected_version,
        change_reason=change_reason,
        **dict(fields),
    )
    return result.id, _version_of(result)


def _glossary_term(
    ctx: AuthContext, entity_id: UUID, fields: Mapping[str, Any], expected_version, change_reason
) -> tuple[UUID, int]:
    from application.glossary_service import GlossaryService

    result = GlossaryService().update(
        ctx, entity_id, expected_version=expected_version, **dict(fields)
    )
    return result.id, _version_of(result)


def _adapter(
    item_type: str,
    entity_key: str,
    accessor: str,
    writable: Sequence[str],
    update: UpdateCallable,
) -> UpdateAdapter:
    return UpdateAdapter(
        item_type=item_type,
        entity_key=entity_key,
        accessor=accessor,
        writable_fields=frozenset(writable),
        update=update,
    )


#: The eight table types (plan Task 1.1 Step 1: verified signatures; the
#: allowlists below are content-only and deliberately exclude ``parent_id``,
#: ``uid``, ``sort_key``, ``level`` and every gateway field).
ARTIFACT_UPDATE_ADAPTERS: dict[str, UpdateAdapter] = {
    "Requirement": _adapter(
        "Requirement",
        "requirement",
        "requirement",
        (
            "title",
            "description",
            "acceptance_criteria",
            "rationale",
            "source",
            "category",
            "type",
            "complexity_fibonacci",
            "verification_method",
        ),
        _requirement,
    ),
    "StakeholderNeed": _adapter(
        "StakeholderNeed",
        "need",
        "stakeholder_need",
        ("title", "description", "category", "moscow_priority"),
        _stakeholder_need,
    ),
    "ArchitectureElement": _adapter(
        "ArchitectureElement",
        "architecture",
        "architecture_element",
        ("title", "description", "element_type", "asil_level", "make_or_buy"),
        _architecture_element,
    ),
    "TestCase": _adapter(
        "TestCase",
        "testcase",
        "test_case",
        ("title", "description", "steps", "test_type", "scenario_kind"),
        _test_case,
    ),
    "Adr": _adapter(
        "Adr",
        "adr",
        "adr",
        ("title", "description", "context", "decision", "consequences"),
        _adr,
    ),
    "Risk": _adapter(
        "Risk",
        "risk",
        "risk",
        (
            "title",
            "description",
            "probability",
            "impact",
            "category",
            "mitigation_strategy",
            "detection",
        ),
        _risk,
    ),
    "Issue": _adapter(
        "Issue",
        "issue",
        "issue",
        ("title", "description", "severity", "category", "due_date", "tags"),
        _issue,
    ),
    "GlossaryTerm": _adapter(
        "GlossaryTerm",
        "glossary",
        "glossary_term",
        ("term", "definition", "synonyms", "abbreviation"),
        _glossary_term,
    ),
}


def classify_fields(
    item_type: str, fields: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split *fields* into ``(entity_fields, gateway_fields)``.

    Raises:
        ValidationError: *item_type* has no adapter, *fields* is empty, or a
            name is neither allowlisted nor a gateway field. The message names
            the field, so a client can point at it.
    """
    adapter = ARTIFACT_UPDATE_ADAPTERS.get(item_type)
    if adapter is None:
        known = ", ".join(sorted(ARTIFACT_UPDATE_ADAPTERS))
        raise ValidationError(
            f"Unknown item_type {item_type!r} for an update; expected one of {known}"
        )
    if not fields:
        raise ValidationError("No fields given")
    entity_fields: dict[str, Any] = {}
    gateway_fields: dict[str, Any] = {}
    for raw_name, value in fields.items():
        name = str(raw_name)
        if name in GATEWAY_FIELDS:
            gateway_fields[name] = value
        elif name in adapter.writable_fields:
            entity_fields[name] = value
        else:
            raise ValidationError(f"Unknown field '{name}' for item type '{item_type}'")
    return entity_fields, gateway_fields


def assert_no_forbidden_fields(
    attributes: Sequence[Mapping[str, Any]],
    fields: Mapping[str, Any],
) -> None:
    """Raise unless every name in *fields* is writable content.

    Args:
        attributes: The resolved attribute list (empty when the workspace has no
            definition — the fallback set still applies).
        fields: The names about to be written.

    Raises:
        ValidationError: the field is structural (:data:`NEVER_BULK_WRITABLE`),
            workflow-owned (:data:`WORKFLOW_OWNED_FALLBACK`, always), or its
            resolved attribute is not ``editable == True``.
    """
    by_name = {str(attribute.get("name")): attribute for attribute in attributes}
    for raw_name in fields:
        name = str(raw_name)
        if name in NEVER_BULK_WRITABLE:
            raise ValidationError(
                f"Field '{name}' cannot be written here: it is structural "
                "(use the dedicated endpoint)"
            )
        if name in WORKFLOW_OWNED_FALLBACK:
            raise ValidationError(
                f"Field '{name}' can only change through a workflow transition"
            )
        attribute = by_name.get(name)
        if attribute is None:
            continue
        editable = attribute.get("editable", True)
        if editable is True:
            continue
        if editable == "workflow":
            raise ValidationError(
                f"Field '{name}' can only change through a workflow transition"
            )
        if editable == "automation":
            raise ValidationError(
                f"Field '{name}' is server-derived and cannot be written"
            )
        raise ValidationError(f"Field '{name}' is server-owned and cannot be written")


def adapter_for(artifact: Artifact) -> UpdateAdapter:
    """Return the adapter for *artifact*'s type (``ValidationError`` if none)."""
    adapter = ARTIFACT_UPDATE_ADAPTERS.get(getattr(artifact, "artifact_type", ""))
    if adapter is None:
        raise ValidationError(
            f"Artifact type {getattr(artifact, 'artifact_type', None)!r} is not "
            "writable through this endpoint"
        )
    return adapter
