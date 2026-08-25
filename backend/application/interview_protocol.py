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

from application.interview_multi_protocol import (
    _MULTI_PROTOCOL_FACTORY_DEFAULT,
    _MULTI_PROTOCOL_SLOT,
)

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


def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Delegates the workspace -> tenant-global -> factory-default chain to
    ``application.prompt_resolver.try_resolve_template_content`` (spec §3.3),
    then parses and validates the resolved YAML. ``try_``-flavoured because a
    missing protocol must surface as :class:`ProtocolValidationError` with an
    artifact-type-specific message, not as a generic slot error.

    Imported lazily: ``prompt_resolver`` imports ``prompt_slots``, which reads
    this module's ``INTERVIEW_PROTOCOL_DEFAULTS`` — a module-level import here
    would close that cycle at import time.
    """
    from application.prompt_resolver import try_resolve_template_content

    name = f"interview.protocol.{artifact_type}"
    content = try_resolve_template_content(name, ctx, workspace_id)
    if content is None:
        raise ProtocolValidationError(
            f"No interview protocol configured or defaulted for artifact_type={artifact_type!r}."
        )
    return parse_protocol_yaml(content)
