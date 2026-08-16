"""Factory registry of prompt variables (spec §3.1/§3.2).

This module is the code-side counterpart to ``PromptVariable`` DB rows,
mirroring exactly how ``PROMPT_TEMPLATE_DEFAULTS`` relates to
``PromptTemplate``: the registry below carries the factory default for every
variable the product ships with, and DB rows exist only to *override* those
per tenant or per workspace — plus to hold ``config`` variables an admin
invents at runtime, which have no factory entry at all.

Why a code registry instead of a per-tenant DB seed (spec §3.1 wording):
seeding would have to run for every existing tenant in a data migration *and*
for every tenant created afterwards, duplicating the factory values into N
copies that then drift. Deriving them from code keeps exactly one source of
truth and makes "reset to factory" a deletion rather than a rewrite — the
same reasoning that already governs prompt templates.

``kind="data"`` entries are documentation only: their values are computed by
the code that builds the render call, never read from here.

req_id: REQ-L2-PT-001
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from persistence.models import (
    PROMPT_VARIABLE_KIND_CONFIG,
    PROMPT_VARIABLE_KIND_DATA,
    PROMPT_VARIABLE_TYPES,
)


class VariableTypeError(ValueError):
    """Raised when a stored value does not match its declared ``var_type``."""


@dataclass(frozen=True)
class PromptVariableSpec:
    """One factory-registered variable.

    Attributes:
        name:          Placeholder name as it appears in prompt bodies, i.e.
                       ``{name}``.
        kind:          ``"config"`` or ``"data"``.
        var_type:      ``"int"``, ``"str"``, ``"bool"`` or ``"json"``.
        description:   Human-readable purpose, rendered in the catalog UI.
        default_value: Factory value (already typed, not JSON text).
    """

    name: str
    kind: str
    var_type: str
    description: str
    default_value: Any


def _data(name: str, description: str, var_type: str = "str") -> PromptVariableSpec:
    """Build a code-bound (``kind="data"``) spec with an empty default."""
    return PromptVariableSpec(
        name=name,
        kind=PROMPT_VARIABLE_KIND_DATA,
        var_type=var_type,
        description=description,
        default_value="",
    )


def _config(name: str, description: str, var_type: str, default: Any) -> PromptVariableSpec:
    """Build a data-driven (``kind="config"``) spec."""
    return PromptVariableSpec(
        name=name,
        kind=PROMPT_VARIABLE_KIND_CONFIG,
        var_type=var_type,
        description=description,
        default_value=default,
    )


#: Factory catalog. Every ``{placeholder}`` any shipped prompt template uses
#: appears here exactly once, so the UI can document it and the resolver can
#: tell a typo apart from a known name.
PROMPT_VARIABLE_DEFAULTS: Dict[str, PromptVariableSpec] = {
    # --- data (code-bound) -------------------------------------------------
    "n": _data("n", "Number of requirement drafts requested by the caller.", "int"),
    "need_title": _data("need_title", "Title of the source stakeholder need."),
    "need_description": _data(
        "need_description", "Description of the source stakeholder need."
    ),
    "req_title": _data("req_title", "Title of the source requirement."),
    "req_description": _data(
        "req_description", "Description of the source requirement."
    ),
    "arch_elements_json": _data(
        "arch_elements_json",
        "JSON array of the candidate architecture elements (id, name, description).",
        "json",
    ),
    "goals": _data("goals", "Newline-joined list of the workspace's Goal statements."),
    "ae_title": _data("ae_title", "Title of the source architecture element."),
    "ae_description": _data(
        "ae_description", "Description of the source architecture element."
    ),
    "workspace_text": _data(
        "workspace_text",
        "Concatenated requirement/architecture titles and descriptions of a workspace.",
    ),
    "decision_description": _data(
        "decision_description", "Free-text description of the decision to structure."
    ),
    "bundle_markdown": _data(
        "bundle_markdown", "The raw Markdown requirement bundle to compress."
    ),
    "answers_text": _data(
        "answers_text", "The interview answers collected so far, as text."
    ),
    "candidates_json": _data(
        "candidates_json",
        "JSON array of candidate artifacts that passed the structural pre-filter.",
        "json",
    ),
    "artifact_type": _data(
        "artifact_type", "PascalCase artifact type the interview is capturing."
    ),
    "phase_name": _data("phase_name", "Name of the current interview protocol phase."),
    "transcript_json": _data(
        "transcript_json",
        "JSON list of {role, text, timestamp} interview turns so far.",
        "json",
    ),
    "current_phase_fragment": _data(
        "current_phase_fragment", "Prompt fragment of the current interview phase."
    ),
    "collected_fields_json": _data(
        "collected_fields_json",
        "JSON object of interview field values collected so far.",
        "json",
    ),
    "missing_fields_json": _data(
        "missing_fields_json",
        "JSON list of {name, type, choices} for fields still needed.",
        "json",
    ),
    "grounding_snapshot_json": _data(
        "grounding_snapshot_json",
        "JSON snapshot of possibly related existing artifacts.",
        "json",
    ),
    "user_message": _data("user_message", "The user's latest interview message."),
    "element_title": _data(
        "element_title", "Title of the architecture element being decomposed."
    ),
    # --- config (data-driven, admin-editable) ------------------------------
    "max_breadth": _config(
        "max_breadth",
        "Upper bound on child elements the AI may propose per level. Not a "
        "target — the AI decides the real number from the content.",
        "int",
        5,
    ),
    "max_depth": _config(
        "max_depth",
        "Upper bound on decomposition levels the AI may propose in one draft.",
        "int",
        3,
    ),
}


def serialize_variable_value(value: Any) -> str:
    """Return the JSON text stored in ``PromptVariable.default_value``."""
    return json.dumps(value)


def deserialize_variable_value(var_type: str, raw: str) -> Any:
    """Return the typed value encoded in *raw* for *var_type*.

    ``"str"`` tolerates a bare, unquoted body so a hand-edited row (or an
    older import) is still readable instead of hard-failing.

    Raises:
        VariableTypeError: Unknown *var_type*, malformed JSON, or a value
            whose Python type does not match *var_type*.
    """
    if var_type not in PROMPT_VARIABLE_TYPES:
        raise VariableTypeError(
            f"Unknown var_type {var_type!r}; expected one of {PROMPT_VARIABLE_TYPES}."
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        if var_type == "str":
            return raw
        raise VariableTypeError(
            f"Value for a {var_type!r} variable is not valid JSON: {raw!r}"
        ) from exc

    if var_type == "int":
        # bool is a subclass of int — reject it explicitly.
        if isinstance(parsed, bool) or not isinstance(parsed, int):
            raise VariableTypeError(f"Expected an int value, got {parsed!r}.")
        return parsed
    if var_type == "bool":
        if not isinstance(parsed, bool):
            raise VariableTypeError(f"Expected a bool value, got {parsed!r}.")
        return parsed
    if var_type == "str":
        return parsed if isinstance(parsed, str) else raw
    return parsed


__all__ = [
    "PROMPT_VARIABLE_DEFAULTS",
    "PromptVariableSpec",
    "VariableTypeError",
    "deserialize_variable_value",
    "serialize_variable_value",
]
