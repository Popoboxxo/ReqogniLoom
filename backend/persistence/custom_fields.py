"""
REQ-L2-AS-037 — Validation for Artifact.custom_fields (dynamic JSONB attributes).

The custom_fields map is intentionally *flat*: keys are strings, values are
scalars (str/int/float/bool/None). Nested dicts/lists are rejected to keep the
data queryable via simple JSONB paths and to bound the payload size.

This module has no DRF dependency (persistence layer, ADR-03). It raises
:class:`django.core.exceptions.ValidationError`; the REST serializer translates
that into a DRF error at the adapter boundary.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

# bool is a subclass of int — list it explicitly so callers reading this see
# that booleans are allowed on purpose.
ALLOWED_VALUE_TYPES = (str, int, float, bool, type(None))
MAX_KEYS = 50
MAX_KEY_LENGTH = 128
MAX_VALUE_STRING_LENGTH = 2000


def validate_custom_fields(data: Any) -> dict:
    """Validate and return a cleaned custom_fields dict.

    Rules (REQ-L2-AS-037):
      - ``data`` must be a dict (``None`` is normalized to ``{}``).
      - At most ``MAX_KEYS`` entries.
      - Keys are non-empty strings, max ``MAX_KEY_LENGTH`` chars, without
        leading/trailing whitespace and without dots (dots would enable
        JSONB path traversal / ambiguous nested access).
      - Values are scalars only: str, int, float, bool or None. Nested dicts
        and lists are rejected.
      - String values are capped at ``MAX_VALUE_STRING_LENGTH`` chars.

    Args:
        data: Raw value to validate (typically from request payload).

    Returns:
        The validated dict (same content, guaranteed to satisfy the rules).

    Raises:
        django.core.exceptions.ValidationError: On any rule violation.
    """
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("custom_fields must be an object (key-value map).")

    if len(data) > MAX_KEYS:
        raise ValidationError(
            f"custom_fields may contain at most {MAX_KEYS} entries "
            f"(got {len(data)})."
        )

    cleaned: dict = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValidationError("custom_fields keys must be strings.")
        if key != key.strip():
            raise ValidationError(
                f"custom_fields key '{key}' must not have leading/trailing "
                "whitespace."
            )
        if not key:
            raise ValidationError("custom_fields keys must not be empty.")
        if len(key) > MAX_KEY_LENGTH:
            raise ValidationError(
                f"custom_fields key '{key[:32]}...' exceeds "
                f"{MAX_KEY_LENGTH} characters."
            )
        if "." in key:
            raise ValidationError(
                f"custom_fields key '{key}' must not contain dots."
            )

        # bool must be checked before the generic isinstance chain would
        # otherwise pass; it is already in ALLOWED_VALUE_TYPES so this is fine.
        if not isinstance(value, ALLOWED_VALUE_TYPES):
            raise ValidationError(
                f"custom_fields value for '{key}' must be a string, number, "
                "boolean or null (nested objects/arrays are not allowed)."
            )
        if isinstance(value, str) and len(value) > MAX_VALUE_STRING_LENGTH:
            raise ValidationError(
                f"custom_fields value for '{key}' exceeds "
                f"{MAX_VALUE_STRING_LENGTH} characters."
            )

        cleaned[key] = value

    return cleaned


__all__ = [
    "validate_custom_fields",
    "ALLOWED_VALUE_TYPES",
    "MAX_KEYS",
    "MAX_KEY_LENGTH",
    "MAX_VALUE_STRING_LENGTH",
]
