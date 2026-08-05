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

from persistence.free_text import find_free_text_violation

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
      - Neither keys nor string values may contain NUL (0x00).
      - Neither keys nor string values may contain HTML markup or a
        script-capable URI scheme (see :mod:`persistence.free_text`).

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
        # QIRK-003 (#76): Postgres cannot store NUL (0x00) in a jsonb string —
        # psycopg2 serializes it to the \u0000 escape, which jsonb rejects with a
        # raw DataError (HTTP 500). The REST layer already screens top-level text
        # fields for this, but it cannot see inside a JSON map, so the check
        # belongs here where every write path (REST, MCP, ReqIF import) passes.
        if "\x00" in key:
            raise ValidationError(
                "custom_fields keys must not contain NUL (0x00) characters."
            )
        # #269 follow-up: keys are *not* constrained by an admin-defined
        # schema. CustomFieldDefinition (REQ-066) is a separate mechanism with
        # its own table; this map accepts whatever key the caller sends, and the
        # SPA renders those keys as labels next to their values. A key is
        # therefore end-user free text at write time and gets the same guard as
        # a value.
        key_violation = find_free_text_violation(key)
        if key_violation is not None:
            raise ValidationError(f"custom_fields key '{key[:32]}' {key_violation}")

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
        # QIRK-003 (#76): see the key check above.
        if isinstance(value, str) and "\x00" in value:
            raise ValidationError(
                f"custom_fields value for '{key}' must not contain NUL (0x00) "
                "characters."
            )
        # #269 follow-up: #290 made custom_fields writable through REST for the
        # first time, which turned this map into a live stored-XSS surface —
        # values round-trip byte-identically into the SPA, PDF/ReqIF export and
        # MCP responses. The check sits here (rather than only in the
        # serializer) because this function is the single intake every write
        # path passes: REST, MCP tools, direct service calls and ReqIF import.
        # Rejecting, not stripping, matches the #269 contract.
        value_violation = find_free_text_violation(value)
        if value_violation is not None:
            raise ValidationError(
                f"custom_fields value for '{key}' {value_violation}"
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
