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

    phases = []
    for raw_phase in raw["phases"]:
        if "name" not in raw_phase:
            raise ProtocolValidationError("Each phase needs a 'name'.")
        raw_fields = raw_phase.get("required_fields") or []
        fields = []
        for raw_field in raw_fields:
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
# place per family so every read path agrees).
INTERVIEW_PROTOCOL_DEFAULTS: "dict[str, str]" = {
    f"interview.protocol.{artifact_type}": _default_protocol_yaml(artifact_type)
    for artifact_type in IN_SCOPE_ARTIFACT_TYPES
}


def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Follows PromptTemplate's existing workspace -> tenant-global ->
    factory-default chain, then parses+validates the resolved YAML.

    Note: this deliberately does *not* call
    ``AiDerivationService._get_template_content`` -- that staticmethod's
    factory-default fallback is hardcoded to
    ``ai_derivation_service.PROMPT_TEMPLATE_DEFAULTS`` (``return
    PROMPT_TEMPLATE_DEFAULTS[name]``, unconditionally, no ``.get()``), so
    calling it with an ``interview.protocol.*`` name that has no active DB
    row would raise ``KeyError`` instead of falling back to
    ``INTERVIEW_PROTOCOL_DEFAULTS``. Instead this mirrors the same
    workspace -> tenant-global -> factory-default chain via
    ``application.prompt_template_versioning.get_active_template``, the
    same lower-level helper ``mcp_server.tools.prompt_template`` itself
    uses for exactly this reason (see that module's docstring: "reads the
    PromptTemplate model directly rather than going through that
    service").
    """
    from application.prompt_template_versioning import get_active_template

    name = f"interview.protocol.{artifact_type}"

    if workspace_id is not None:
        row = get_active_template(
            tenant_id=ctx.tenant_id, name=name, workspace_id=workspace_id
        )
        if row is not None:
            return parse_protocol_yaml(row.content)

    row = get_active_template(tenant_id=ctx.tenant_id, name=name, workspace_id=None)
    if row is not None:
        return parse_protocol_yaml(row.content)

    content = INTERVIEW_PROTOCOL_DEFAULTS.get(name)
    if content is None:
        raise ProtocolValidationError(
            f"No interview protocol configured or defaulted for artifact_type={artifact_type!r}."
        )
    return parse_protocol_yaml(content)
