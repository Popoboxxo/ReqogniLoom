"""
Issue #128 — structural validation for ``Role.permissions`` (RBAC JSONB).

``Role.permissions`` is the only JSON column in the persistence layer that
feeds authorization decisions, so it gets a strict, explicit schema:

    {"<permission-key>": true | false | ["<scope>", ...]}

Rationale for the value types:
  - ``bool``      — an explicit grant/deny decision.
  - ``list[str]`` — a grant narrowed to named scopes (e.g. ``["own"]``).
  - Everything else (``None``, strings, numbers, nested objects) is rejected:
    an unreadable value would otherwise be coerced to "truthy" somewhere down
    the line and silently widen or drop a permission.

Keys are trimmed, non-empty, length-bounded strings so that a typo produces a
loud error instead of a silently inactive permission (the concrete failure mode
described in #128).

This module mirrors :mod:`persistence.custom_fields`: no DRF dependency
(persistence layer, ADR-03), raising
:class:`django.core.exceptions.ValidationError`. The REST adapter translates
that into a DRF error at the boundary.
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

MAX_PERMISSIONS = 200
MAX_KEY_LENGTH = 128
MAX_SCOPES = 50
MAX_SCOPE_LENGTH = 128


def validate_role_permissions(data: Any) -> dict:
    """Validate and return a cleaned ``Role.permissions`` mapping.

    Args:
        data: Raw value to validate. ``None`` is normalized to ``{}``.

    Returns:
        The validated mapping (same content, guaranteed to satisfy the schema).

    Raises:
        django.core.exceptions.ValidationError: On any rule violation.
    """
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("permissions must be an object (key-value map).")

    if len(data) > MAX_PERMISSIONS:
        raise ValidationError(
            f"permissions may contain at most {MAX_PERMISSIONS} entries "
            f"(got {len(data)})."
        )

    cleaned: dict = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValidationError("permissions keys must be strings.")
        if key != key.strip():
            raise ValidationError(
                f"permissions key '{key}' must not have leading/trailing "
                "whitespace."
            )
        if not key:
            raise ValidationError("permissions keys must not be empty.")
        if len(key) > MAX_KEY_LENGTH:
            raise ValidationError(
                f"permissions key '{key[:32]}...' exceeds {MAX_KEY_LENGTH} "
                "characters."
            )

        cleaned[key] = _validate_value(key, value)

    return cleaned


def _validate_value(key: str, value: Any) -> Any:
    """Validate a single permission value (bool or list of scope strings)."""
    # bool is a subclass of int — check it first so ``True``/``False`` are not
    # mistaken for the rejected numeric case below.
    if isinstance(value, bool):
        return value

    if isinstance(value, list):
        if len(value) > MAX_SCOPES:
            raise ValidationError(
                f"permissions value for '{key}' may list at most {MAX_SCOPES} "
                f"scopes (got {len(value)})."
            )
        for scope in value:
            if not isinstance(scope, str):
                raise ValidationError(
                    f"permissions scope list for '{key}' must contain only "
                    "strings."
                )
            if not scope.strip():
                raise ValidationError(
                    f"permissions scope list for '{key}' must not contain "
                    "empty strings."
                )
            if len(scope) > MAX_SCOPE_LENGTH:
                raise ValidationError(
                    f"permissions scope '{scope[:32]}...' for '{key}' exceeds "
                    f"{MAX_SCOPE_LENGTH} characters."
                )
        return value

    raise ValidationError(
        f"permissions value for '{key}' must be a boolean or a list of scope "
        "strings (got "
        f"{type(value).__name__})."
    )


__all__ = [
    "validate_role_permissions",
    "MAX_PERMISSIONS",
    "MAX_KEY_LENGTH",
    "MAX_SCOPES",
    "MAX_SCOPE_LENGTH",
]
