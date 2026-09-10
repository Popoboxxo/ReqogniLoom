"""Interview protocol configuration (Interview-Management-Engine spec §3.1).

Protocols are stored as PromptTemplate rows under the
"interview.protocol.<ArtifactType>" namespace, reusing that model's
existing 3-level override chain (workspace -> tenant-global ->
factory-default) instead of a new model. This module owns the YAML
structure inside a protocol's content and the factory-default registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
)
from application.base import NotFoundError
from application.interview_multi_protocol import (
    _MULTI_PROTOCOL_FACTORY_DEFAULT,
    _MULTI_PROTOCOL_SLOT,
)
from application.prompt_resolver import _as_uuid
from application.prompt_template_versioning import get_active_template

# All artifact types Spec 1 puts in scope (spec §1) -- everything except
# MainGoal, which stays read-only (matches the MCP surface: only
# main_goal.read/list_versions exist, no write tools).
IN_SCOPE_ARTIFACT_TYPES = (
    "Requirement",
    "ArchitectureElement",
    "StakeholderNeed",
    "Risk",
    "TestCase",
    "Adr",
    "Issue",
    "Goal",
)


class ProtocolValidationError(Exception):
    """Raised when protocol YAML is malformed or violates the schema."""


@dataclass
class ProtocolField:
    name: str
    type: str = "text"
    choices: "list[str] | None" = None


@dataclass
class ProtocolPhase:
    name: str
    required_fields: "list[ProtocolField]" = field(default_factory=list)
    prompt_fragment: str = ""


@dataclass
class ProtocolConfig:
    phases: "list[ProtocolPhase]"


_VALID_FIELD_TYPES = {"text", "textarea", "enum", "number"}


def parse_protocol_yaml(content: str) -> ProtocolConfig:
    """Parse and validate a protocol's YAML content.

    Raises:
        ProtocolValidationError: malformed YAML, missing required keys, or
            an ``enum`` field without ``choices``.
    """
    try:
        raw: Any = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ProtocolValidationError(f"Invalid YAML: {exc}") from exc

    if not isinstance(raw, dict) or "phases" not in raw:
        raise ProtocolValidationError("Protocol YAML must have a top-level 'phases' list.")

    raw_phases = raw["phases"]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise ProtocolValidationError(
            "Protocol YAML 'phases' must be a non-empty list of phases."
        )

    phases = []
    for raw_phase in raw_phases:
        if not isinstance(raw_phase, dict):
            raise ProtocolValidationError("Each phase must be a dict, not a list item or scalar.")
        if "name" not in raw_phase:
            raise ProtocolValidationError("Each phase needs a 'name'.")
        raw_fields = raw_phase.get("required_fields") or []
        fields = []
        for raw_field in raw_fields:
            if not isinstance(raw_field, dict):
                raise ProtocolValidationError("Each required_field must be a dict.")
            if "name" not in raw_field:
                raise ProtocolValidationError("Each required_field needs a 'name'.")
            field_type = raw_field.get("type", "text")
            if field_type not in _VALID_FIELD_TYPES:
                raise ProtocolValidationError(
                    f"Unknown field type {field_type!r} for field {raw_field['name']!r}."
                )
            choices = raw_field.get("choices")
            if field_type == "enum" and not choices:
                raise ProtocolValidationError(
                    f"Field {raw_field['name']!r} has type 'enum' but no 'choices'."
                )
            fields.append(ProtocolField(name=raw_field["name"], type=field_type, choices=choices))
        phases.append(
            ProtocolPhase(
                name=raw_phase["name"],
                required_fields=fields,
                prompt_fragment=raw_phase.get("prompt_fragment", ""),
            )
        )
    return ProtocolConfig(phases=phases)


def _default_protocol_yaml(artifact_type: str) -> str:
    """A minimal, valid factory default: one elicitation phase asking for
    title + rationale, then approval and formalization with no extra
    fields. Workspaces that need more override this via prompt_template.*
    (same mechanism as the other 7 derivation prompt types)."""
    return (
        "phases:\n"
        "  - name: elicitation\n"
        "    required_fields:\n"
        "      - name: title\n"
        "        type: text\n"
        "      - name: rationale\n"
        "        type: textarea\n"
        f"    prompt_fragment: \"Elicit the {artifact_type}'s title and rationale.\"\n"
        "  - name: approval\n"
        f"    prompt_fragment: \"Present the drafted {artifact_type} for approval.\"\n"
        "  - name: formalization\n"
        "    prompt_fragment: \"Confirm and formalize.\"\n"
    )


# Single canonical registry, same pattern as ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS
# (mcp_server.tools.prompt_template reads factory defaults from exactly one
# place per family so every read path agrees). The free-running multi-artifact
# chat registers its factory default here too so the existing
# Workspace -> Tenant -> Factory resolver chain (try_resolve_template_content)
# picks it up identically to the 8 single-type slots. Module-level import of
# interview_multi_protocol is safe: prompt_slots imports this module lazily
# inside get_prompt_slots(), so no import cycle closes.
INTERVIEW_PROTOCOL_DEFAULTS: "dict[str, str]" = {
    **{
        f"interview.protocol.{artifact_type}": _default_protocol_yaml(artifact_type)
        for artifact_type in IN_SCOPE_ARTIFACT_TYPES
    },
    _MULTI_PROTOCOL_SLOT: _MULTI_PROTOCOL_FACTORY_DEFAULT,
}


#: Attribute type -> protocol field type. The protocol validator accepts only
#: text/textarea/enum/number, so the richer attribute vocabulary is narrowed:
#: multi-enum keeps its choices as a single-select, and the reference-shaped
#: types degrade to free text rather than being dropped (the interview asks for
#: them in prose and formalize() resolves them).
_ATTRIBUTE_TO_PROTOCOL_TYPE = {
    "text": "text",
    "textarea": "textarea",
    "number": "number",
    "enum": "enum",
    "multi-enum": "enum",
    "boolean": "text",
    "date": "text",
    "reference": "text",
    "user": "text",
}


def protocol_from_definition(
    attributes: list[dict], artifact_type: str
) -> ProtocolConfig:
    """Derive an interview protocol from a resolved attribute definition.

    Spec section 7: elicitation phases ARE the definition's sections, in the
    definition's order; a phase's required fields are that section's
    ``ai_elicit=true`` attributes. ``approval`` and ``formalization`` are
    appended unchanged so the engine's phase machine is untouched.

    Resolves audit finding L2.2 as a side effect: the hardcoded default only
    ever elicited title + rationale for every type.

    Raises:
        ProtocolValidationError: the definition marks no attribute as
            ``ai_elicit`` — an interview with nothing to ask is not usable, and
            silently returning an empty protocol would strand the session.
    """
    by_section: dict[str, list[dict]] = {}
    for attribute in attributes:
        if attribute["type"] == "widget" or not attribute.get("ai_elicit"):
            continue
        by_section.setdefault(attribute["section"], []).append(attribute)

    if not by_section:
        raise ProtocolValidationError(
            f"No attribute of artifact_type={artifact_type!r} is marked "
            f"ai_elicit; nothing to interview for."
        )

    phases: list[ProtocolPhase] = []
    for section, section_attributes in by_section.items():
        fields = []
        for attribute in section_attributes:
            field_type = _ATTRIBUTE_TO_PROTOCOL_TYPE.get(attribute["type"], "text")
            choices = (
                [o["value"] for o in attribute["options"]]
                if field_type == "enum"
                else None
            )
            fields.append(
                ProtocolField(name=attribute["name"], type=field_type, choices=choices)
            )
        phases.append(
            ProtocolPhase(
                name=section,
                required_fields=fields,
                prompt_fragment=(
                    f"Elicit the {artifact_type}'s {section} attributes: "
                    f"{', '.join(f.name for f in fields)}."
                ),
            )
        )

    phases.append(
        ProtocolPhase(
            name="approval",
            required_fields=[],
            prompt_fragment=f"Present the drafted {artifact_type} for approval.",
        )
    )
    phases.append(
        ProtocolPhase(
            name="formalization", required_fields=[], prompt_fragment="Confirm and formalize."
        )
    )
    return ProtocolConfig(phases=phases)


def _validate_protocol_config(config: ProtocolConfig) -> ProtocolConfig:
    """Apply the same structural checks :func:`parse_protocol_yaml` gets for
    free while parsing raw YAML, to a :class:`ProtocolConfig` built some other
    way (I-3: tier 2's ``protocol_from_definition`` output used to skip this
    entirely, unlike tiers 1/3). Not currently reachable -- ``normalize_attribute``
    already rejects an enum with no options before a definition can be saved
    -- but keeps tier 2 honest as the attribute vocabulary grows.
    """
    if not config.phases:
        raise ProtocolValidationError("Protocol must have a non-empty 'phases' list.")
    for phase in config.phases:
        for protocol_field in phase.required_fields:
            if protocol_field.type not in _VALID_FIELD_TYPES:
                raise ProtocolValidationError(
                    f"Unknown field type {protocol_field.type!r} for field "
                    f"{protocol_field.name!r}."
                )
            if protocol_field.type == "enum" and not protocol_field.choices:
                raise ProtocolValidationError(
                    f"Field {protocol_field.name!r} has type 'enum' but no 'choices'."
                )
    return config


def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Resolution order (spec section 7):
      1. an explicit ``interview.protocol.<ArtifactType>`` PromptTemplate row
         (workspace, then tenant-global) — an admin who wrote a protocol by
         hand keeps it;
      2. the attribute definition's ``ai_elicit`` attributes;
      3. the hardcoded factory default (``INTERVIEW_PROTOCOL_DEFAULTS``), for
         a workspace with no definition yet, or an artifact_type outside the
         registry.

    Tier 1 is queried directly via :func:`get_active_template` rather than
    ``application.prompt_resolver.try_resolve_template_content``: that
    resolver's own last-resort fallback IS ``INTERVIEW_PROTOCOL_DEFAULTS``
    (via ``prompt_slots.get_slot_default``), so for every one of the 8
    in-scope artifact types it never actually returns ``None`` — it would
    always resolve to the hardcoded factory default before tier 2 got a
    chance to run, permanently hiding the attribute-definition-derived
    protocol behind the very fallback it is meant to replace. Querying the
    two ``PromptTemplate`` scopes directly distinguishes "an admin wrote an
    override" from "nothing configured, use the wider fallback chain".
    """
    name = f"interview.protocol.{artifact_type}"
    # I-2: get_active_template() filters a UUIDField by workspace_id as-is;
    # unlike tier 2 (guarded by _workspace_preset), a malformed id used to
    # reach Django's ORM raw and crash with an unhandled ValidationError
    # (500) instead of the 404 issue #271 established for every other
    # "bad workspace id" case. Coerce with the same helper prompt_resolver.py
    # itself uses for the identical filter, before either tier touches it.
    try:
        workspace_id = _as_uuid(workspace_id)
    except (ValueError, AttributeError) as exc:
        raise NotFoundError(
            f"No workspace {workspace_id!r} in the active tenant"
        ) from exc

    row = None
    if workspace_id is not None:
        row = get_active_template(tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id)
    if row is None:
        row = get_active_template(tenant_id=ctx.tenant_id, name=name, workspace_id=None)
    if row is not None:
        return parse_protocol_yaml(row.content)

    try:
        attributes = AttributeDefinitionService().elicit_attributes(
            ctx, artifact_type, workspace_id
        )
        protocol = protocol_from_definition(attributes, artifact_type)
        # I-3: tier 1 (parse_protocol_yaml) and tier 3 (below) both validate
        # phase/field structure; tier 2 built a ProtocolConfig by hand and
        # returned it unchecked. Run the same checks explicitly, inside this
        # try so a validation failure here falls through to the tier-3
        # default exactly like protocol_from_definition's own
        # ProtocolValidationError already does, instead of propagating.
        return _validate_protocol_config(protocol)
    except AttributeDefinitionNotFound as exc:
        # I-1: _workspace_preset (attribute_definition_service.py) raises
        # this same exception for two cases it cannot otherwise tell apart:
        # "no such workspace" and "workspace exists, nothing bootstrapped
        # yet". Only its own raise site's message names the former ("No
        # workspace '...' in the active tenant"); every other raise site
        # (workspace_definition_store.py, global_definition_store.py) talks
        # about a missing *definition*, never a missing *workspace*. A
        # nonexistent workspace should 404 like every other artifact lookup
        # instead of silently degrading to the factory-default protocol; a
        # narrow message check here does that without widening
        # _workspace_preset's already-hardened (Task 7/10/11) contract.
        # No cleaner distinction exists without changing that contract, so
        # this stays a targeted string check rather than a new exception type.
        if str(exc).startswith("No workspace "):
            raise NotFoundError(str(exc)) from exc
    except ProtocolValidationError:
        pass

    default_content = INTERVIEW_PROTOCOL_DEFAULTS.get(name)
    if default_content is None:
        raise ProtocolValidationError(
            f"No interview protocol configured or defaulted for artifact_type={artifact_type!r}."
        )
    return parse_protocol_yaml(default_content)
