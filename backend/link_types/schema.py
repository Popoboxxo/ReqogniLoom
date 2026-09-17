"""Shape and range validation for a link type's ``definition_json``.

``definition_json`` is tenant-authored (a Tenant-Admin can invent
``conflicts-with`` from the UI or MCP), so it is an untrusted payload on a
trust boundary and gets validated on every write path — the REST views, the
MCP tools and the provisioning/reset helpers all funnel through
:func:`validate_definition_json`.

The only closed value range is ``suspect_rule``: the propagation engine
branches on it, so an unknown value would silently do nothing. Everything
else (``allowed_pairs``, ``label``, ``coverage_relevant``, ``impact_weight``,
``active``) is free.
"""
from __future__ import annotations

from typing import Any

from persistence.errors import ValidationError

from .builtin import SUSPECT_RULES

_LANGS = ("de", "en")
_PERSPECTIVES = ("downstream", "upstream", "neutral")

#: field -> default applied when the caller omits it.
_OPTIONAL_DEFAULTS: dict[str, Any] = {
    "coverage_relevant": False,
    "manual_creatable": True,
    "system_owned": False,
    "active": True,
    "built_in": False,
}

_REQUIRED = ("label", "allowed_pairs", "suspect_rule", "impact_weight")
_KNOWN = set(_REQUIRED) | set(_OPTIONAL_DEFAULTS)


def validate_definition_json(payload: Any, *, key: str) -> dict[str, Any]:
    """Validate and normalize one link-type definition.

    Args:
        payload: The raw ``definition_json`` mapping.
        key: The link-type key, used only to make error messages locatable.

    Returns:
        A new dict with every optional field filled in and
        ``allowed_pairs`` normalized to ``[{"source_type", "target_type"}]``.

    Raises:
        ValidationError: Any shape or range violation. The message names the
            offending field and, for closed ranges, lists the valid values.
    """
    if not isinstance(payload, dict):
        raise ValidationError(f"Link type '{key}': definition must be an object.")

    unknown = sorted(set(payload) - _KNOWN)
    if unknown:
        raise ValidationError(
            f"Link type '{key}': unknown field(s) {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(_KNOWN))}."
        )

    missing = [field for field in _REQUIRED if field not in payload]
    if missing:
        raise ValidationError(
            f"Link type '{key}': missing required field(s) {', '.join(missing)}."
        )

    result: dict[str, Any] = dict(_OPTIONAL_DEFAULTS)
    result.update({k: v for k, v in payload.items() if k in _OPTIONAL_DEFAULTS})

    result["label"] = _validate_label(payload["label"], key=key)
    result["allowed_pairs"] = _validate_pairs(payload["allowed_pairs"], key=key)
    result["suspect_rule"] = _validate_suspect_rule(payload["suspect_rule"], key=key)
    result["impact_weight"] = _validate_weight(payload["impact_weight"], key=key)

    for flag in ("coverage_relevant", "manual_creatable", "system_owned", "active", "built_in"):
        if not isinstance(result[flag], bool):
            raise ValidationError(f"Link type '{key}': '{flag}' must be a boolean.")

    return result


def _validate_label(label: Any, *, key: str) -> dict[str, dict[str, str]]:
    """Tri-label: {de,en} x {downstream,upstream,neutral}, all strings.

    The tri-label shape (not a flat ``{de, en}`` pair) is what the frontend's
    single display source, ``constants/traceLinkLabels.ts``, consumes.
    """
    if not isinstance(label, dict):
        raise ValidationError(f"Link type '{key}': 'label' must be an object.")
    out: dict[str, dict[str, str]] = {}
    for lang in _LANGS:
        entry = label.get(lang)
        if not isinstance(entry, dict):
            raise ValidationError(
                f"Link type '{key}': 'label' is missing the '{lang}' object."
            )
        out[lang] = {}
        for perspective in _PERSPECTIVES:
            value = entry.get(perspective)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(
                    f"Link type '{key}': label.{lang}.{perspective} must be a "
                    f"non-empty string."
                )
            out[lang][perspective] = value
    return out


def _validate_pairs(pairs: Any, *, key: str) -> list[dict[str, str]]:
    """``[{"source_type": str, "target_type": str}]``; ``"*"`` is a wildcard.

    An empty list is legal and means "this type currently links nothing" —
    the sane state for a freshly invented type before its pairs are filled in.
    """
    if not isinstance(pairs, list):
        raise ValidationError(f"Link type '{key}': 'allowed_pairs' must be a list.")
    out: list[dict[str, str]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            raise ValidationError(
                f"Link type '{key}': allowed_pairs[{index}] must be an object."
            )
        for side in ("source_type", "target_type"):
            value = pair.get(side)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(
                    f"Link type '{key}': allowed_pairs[{index}].{side} must be a "
                    f"non-empty string (artifact type or '*')."
                )
        out.append(
            {
                "source_type": pair["source_type"],
                "target_type": pair["target_type"],
            }
        )
    return out


def _validate_suspect_rule(rule: Any, *, key: str) -> str:
    if rule not in SUSPECT_RULES:
        raise ValidationError(
            f"Link type '{key}': unknown suspect_rule '{rule}'. "
            f"Valid values: {', '.join(sorted(SUSPECT_RULES))}. "
            f"New propagation behaviour requires a code change."
        )
    return str(rule)


def _validate_weight(weight: Any, *, key: str) -> float:
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValidationError(f"Link type '{key}': 'impact_weight' must be a number.")
    if weight < 0:
        raise ValidationError(
            f"Link type '{key}': 'impact_weight' must be >= 0 (got {weight})."
        )
    return float(weight)
