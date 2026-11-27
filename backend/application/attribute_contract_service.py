"""Single source for an artifact type's writable-field contract.

The interview prompt and the multi-artifact proposal gate both need to know
which fields a create call accepts, which of them are REQUIRED and which
choices a field offers. Before this module each caller re-derived a different
slice (``allowed_fields_for`` for the allowlist, a hardcoded prompt sentence
for the "fields for that type's create call" hint), which is exactly how the
multi prompt ended up telling the LLM to omit ``probability``/``impact`` for a
Risk and then failing at write time.

:func:`artifact_field_contract` is the one derivation:

* the field universe is the production ``create_X()`` signature, taken from
  :func:`application.interview_artifact_adapters.allowed_fields_for` -- the
  same single derivation the proposal allowlist uses, so the prompt contract
  and the write gate cannot disagree. A field the adapter cannot accept is
  never advertised, even when the attribute definition knows it;
* ``type``/``choices``/``required`` come from the workspace's resolved
  attribute definition when it knows the name, otherwise from the signature
  annotation (``str`` -> ``string``, ``int`` -> ``integer``, ...);
* ``required`` is the definition's ``required`` flag OR a signature parameter
  without a default -- the second half is what makes ``Risk.probability``
  mandatory even in a workspace that has no attribute definition yet.

The signature-derived part is computed once on first use (``_SIGNATURE_CONTRACT``)
so a test that patches a ``create_X()`` with a ``MagicMock`` cannot collapse a
contract mid-run, mirroring ``interview_artifact_adapters._ALLOWED_FIELDS_BY_TYPE``.

Known, deliberate limitations (m4 -- plan decisions, not bugs)
--------------------------------------------------------------
Two asymmetries follow from using the create signature as the field universe
while letting the attribute definition refine ``required``:

* A field the attribute definition marks ``required`` but that the
  ``create_X()`` signature does **not** accept is **not enforced**. It is never
  advertised, because the adapter could not write it anyway -- enforcing it
  would only make an artifact un-formalizable with no legal way to supply the
  value.
* A definition ``required`` flag on a signature-**defaulted** field **does**
  block formalize. The definition is deliberately allowed to be stricter than
  the signature: a workspace that marks ``description`` required means it, and
  the gate fails closed rather than silently writing the signature default.
"""
from __future__ import annotations

import datetime
import enum
import inspect
import logging
import types
from collections.abc import Mapping, Sequence
from typing import Any, Union, get_args, get_origin, get_type_hints

logger = logging.getLogger(__name__)

#: ``source`` values a contract entry may carry. Exposed so callers/tests can
#: assert against the vocabulary instead of a literal.
SOURCE_ATTRIBUTE_DEFINITION = "attribute_definition"
SOURCE_CREATE_SIGNATURE = "create_signature"


def _infer_type_from_text(annotation: str) -> str:
    """Map a string annotation (``"int | None"``) onto the contract vocabulary."""
    text = annotation.strip().split("|", 1)[0].strip().strip("'\"")
    lowered = text.lower()
    if lowered.startswith(("list", "sequence", "tuple", "set", "frozenset")):
        return "list"
    if lowered.startswith(("dict", "mapping")):
        return "object"
    if lowered == "bool":
        return "boolean"
    if lowered == "int":
        return "integer"
    if lowered == "str":
        return "string"
    if lowered in ("date", "datetime"):
        return "date"
    if lowered == "object":
        return "object"
    # UUID, enum classes and anything unknown degrade to a plain string.
    return "string"


def _infer_type(annotation: Any) -> str:
    """Infer a contract ``type`` token from a resolved annotation."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return "string"
    if isinstance(annotation, str):
        return _infer_type_from_text(annotation)

    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        # Optional[X] / X | None -> X.
        inner = [arg for arg in get_args(annotation) if arg is not type(None)]
        return _infer_type(inner[0]) if inner else "string"
    if origin in (list, tuple, set, frozenset, Sequence):
        return "list"
    if origin in (dict, Mapping):
        return "object"

    if isinstance(annotation, type):
        if issubclass(annotation, enum.Enum):
            return "enum"
        # bool before int: bool is an int subclass.
        if issubclass(annotation, bool):
            return "boolean"
        if issubclass(annotation, int):
            return "integer"
        if issubclass(annotation, str):
            return "string"
        if issubclass(annotation, (datetime.date, datetime.datetime)):
            return "date"
        if issubclass(annotation, (dict, Mapping)):
            return "object"
        if issubclass(annotation, (list, tuple, set, frozenset, Sequence)):
            return "list"
        if annotation is object:
            return "object"
    return "string"


def _build_signature_contract() -> dict[str, dict[str, dict[str, Any]]]:
    """Precompute per-type ``{field: {type, has_default, default}}``.

    The set of names is :func:`allowed_fields_for`'s -- one derivation of "what
    a create call accepts" -- while ``inspect`` only supplies each name's
    annotation and default. Filtering the signature through that allowlist
    (instead of re-deriving the exclusion rules here) is what keeps this module
    and the proposal gate on the same universe.

    The adapter import is deliberately **lazy**: at module level it would
    close an ``attribute_contract_service -> interview_artifact_adapters ->
    ... -> attribute_contract_service`` cycle, which the architecture contract
    test rejects. The result is cached on first use by
    :func:`_signature_contract`.
    """
    from application.interview_artifact_adapters import (
        _CREATE_METHODS,
        allowed_fields_for,
    )

    contract: dict[str, dict[str, dict[str, Any]]] = {}
    for artifact_type, method in _CREATE_METHODS.items():
        try:
            hints = get_type_hints(method)
        except Exception:  # noqa: BLE001 -- annotation resolution is best effort
            hints = {}
        allowed = allowed_fields_for(artifact_type)
        params: dict[str, dict[str, Any]] = {}
        for name, parameter in inspect.signature(method).parameters.items():
            if name not in allowed:
                continue
            has_default = parameter.default is not inspect.Parameter.empty
            params[name] = {
                "type": _infer_type(hints.get(name, parameter.annotation)),
                "has_default": has_default,
                "default": parameter.default if has_default else None,
            }
        contract[artifact_type] = params
    return contract


_SIGNATURE_CONTRACT: dict[str, dict[str, dict[str, Any]]] | None = None


def _signature_contract() -> dict[str, dict[str, dict[str, Any]]]:
    """Return the cached signature contract, building it on first use."""
    global _SIGNATURE_CONTRACT
    if _SIGNATURE_CONTRACT is None:
        _SIGNATURE_CONTRACT = _build_signature_contract()
    return _SIGNATURE_CONTRACT


def _definition_attributes(ctx, workspace_id, artifact_type: str) -> dict[str, dict[str, Any]]:
    """Resolved attribute-definition rows keyed by name, or ``{}`` on failure.

    A workspace that has not run ``bootstrap_attribute_definitions`` has no
    definition; that is a normal state (fresh/test workspace), so the contract
    degrades to the create signature instead of failing the prompt/gate.
    """
    from application.attribute_definition_service import AttributeDefinitionService

    try:
        definition = AttributeDefinitionService().resolve(ctx, artifact_type, workspace_id)
    except Exception:  # noqa: BLE001 -- a config read must not break a prompt/gate
        logger.debug(
            "attribute_contract_service: no resolved definition for %s in workspace %s; "
            "using create-signature contract only",
            artifact_type,
            workspace_id,
            exc_info=True,
        )
        return {}
    attributes = definition.get("attributes", []) if isinstance(definition, dict) else []
    return {
        attribute["name"]: attribute
        for attribute in attributes
        if isinstance(attribute, dict) and isinstance(attribute.get("name"), str)
    }


def _attribute_choices(attribute: dict[str, Any]) -> list[str]:
    """Option values of an enum attribute (``options`` or ``choices`` spelling)."""
    raw = attribute.get("options")
    if raw is None:
        raw = attribute.get("choices")
    if not isinstance(raw, list):
        return []
    choices: list[str] = []
    for option in raw:
        if isinstance(option, dict) and option.get("value") is not None:
            choices.append(str(option["value"]))
        elif isinstance(option, str):
            choices.append(option)
    return choices


def artifact_field_contract(ctx, workspace_id, artifact_type: str) -> list[dict[str, Any]]:
    """Return the writable-field contract of *artifact_type*.

    One entry per writable field, in create-signature order::

        {"name": str, "type": str, "choices": list[str],
         "required": bool, "default": Any | None,
         "source": "attribute_definition" | "create_signature"}

    Only fields the production ``create_X()`` accepts are returned -- a
    definition-only name would be rejected by the adapter, so it is never
    advertised. An unknown artifact type raises :class:`ValidationError`.
    """
    from application.interview_artifact_adapters import (
        ARTIFACT_CREATION_ADAPTERS,
        allowed_fields_for,
    )
    from application.base import ValidationError

    if artifact_type not in ARTIFACT_CREATION_ADAPTERS:
        raise ValidationError(
            f"unknown artifact type for a field contract: {artifact_type!r}"
        )
    # Defensive: ARTIFACT_CREATION_ADAPTERS and _CREATE_METHODS cover the same
    # keys today, but the contract must not KeyError if that ever drifts.
    signature = _signature_contract().get(artifact_type)
    if signature is None:
        allowed = allowed_fields_for(artifact_type)
        signature = {
            name: {"type": "string", "has_default": True, "default": None}
            for name in allowed
        }

    definition = _definition_attributes(ctx, workspace_id, artifact_type)

    entries: list[dict[str, Any]] = []
    for name, sig in signature.items():
        attribute = definition.get(name)
        if attribute is not None:
            entries.append(
                {
                    "name": name,
                    "type": str(attribute.get("type") or sig["type"]),
                    "choices": _attribute_choices(attribute),
                    "required": bool(attribute.get("required")) or not sig["has_default"],
                    "default": sig["default"],
                    "source": SOURCE_ATTRIBUTE_DEFINITION,
                }
            )
        else:
            entries.append(
                {
                    "name": name,
                    "type": sig["type"],
                    "choices": [],
                    "required": not sig["has_default"],
                    "default": sig["default"],
                    "source": SOURCE_CREATE_SIGNATURE,
                }
            )
    return entries


__all__ = [
    "SOURCE_ATTRIBUTE_DEFINITION",
    "SOURCE_CREATE_SIGNATURE",
    "artifact_field_contract",
]
