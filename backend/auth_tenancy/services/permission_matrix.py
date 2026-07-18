"""Canonical role->capability permission matrix helpers (REQ-181/186/187).

Single source of truth for the *shape* and *default values* of the
``permission_json`` blob carried by
:class:`~auth_tenancy.models.GlobalPermissionDefinition` and
:class:`~auth_tenancy.models.WorkspacePermissionDefinition`.

The capability vocabulary is a 1:1, name-preserving lift of the ``Operation``
enum in :mod:`auth_tenancy.services.authorization` (the hardcoded RBAC matrix,
ADR-L3-AT002-01) — see the ``CapabilityKey`` schema in
``docs/api/workflow-permissions-global-default.openapi.yaml``. No new capability
keys are invented here.

:func:`default_permission_matrix` derives the day-1 default from the live
``_RBAC_MATRIX`` at runtime, so a workspace/tenant provisioned *after* any future
RBAC change still starts byte-identical to the coded legacy behaviour. The
historical migration ``0006_backfill_permission_defaults`` inlines the same
values as a frozen snapshot for pre-existing data.
"""
from __future__ import annotations

from typing import Iterable

from .authorization import _RBAC_MATRIX, Operation
from ..models import ROLE_ADMIN, ROLE_APPROVER, ROLE_EDITOR, ROLE_VIEWER

# Canonical role keys (closed set) — order is presentation-stable.
ROLE_KEYS: tuple[str, ...] = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ROLE_APPROVER)

# Canonical capability keys (closed set) — the six ``Operation`` values.
CAPABILITY_KEYS: tuple[str, ...] = tuple(op.value for op in Operation)


class MatrixValidationError(ValueError):
    """Raised when a permission matrix violates the closed 4x6 schema."""


def default_permission_matrix() -> dict[str, dict[str, bool]]:
    """Return the default role->capability matrix from the live RBAC matrix.

    The result is a fresh, fully-populated ``{role: {capability: bool}}`` dict
    equivalent to the coded ``_RBAC_MATRIX``, so seeding a new
    :class:`GlobalPermissionDefinition`/:class:`WorkspacePermissionDefinition`
    from it produces shadow decisions identical to legacy on day one.
    """
    matrix: dict[str, dict[str, bool]] = {}
    for role in ROLE_KEYS:
        allowed = _RBAC_MATRIX.get(role, frozenset())
        matrix[role] = {
            capability: (Operation(capability) in allowed)
            for capability in CAPABILITY_KEYS
        }
    return matrix


def validate_matrix(matrix: object) -> dict[str, dict[str, bool]]:
    """Validate and normalise a full permission matrix (closed 4x6 schema).

    Rejects unknown/missing roles, unknown/missing capabilities and non-boolean
    values so no partial or drifted matrix is ever persisted.

    Args:
        matrix: Candidate matrix (typically request JSON).

    Returns:
        A normalised, deep-copied matrix with roles/capabilities in canonical
        order and boolean values.

    Raises:
        MatrixValidationError: The candidate is not a well-formed closed matrix.
    """
    if not isinstance(matrix, dict):
        raise MatrixValidationError("permission_json must be an object")

    role_keys = set(matrix.keys())
    expected_roles = set(ROLE_KEYS)
    if role_keys != expected_roles:
        missing = sorted(expected_roles - role_keys)
        extra = sorted(role_keys - expected_roles)
        raise MatrixValidationError(
            f"permission_json roles must be exactly {sorted(expected_roles)} "
            f"(missing={missing}, unexpected={extra})"
        )

    normalised: dict[str, dict[str, bool]] = {}
    for role in ROLE_KEYS:
        caps = matrix[role]
        if not isinstance(caps, dict):
            raise MatrixValidationError(
                f"permission_json['{role}'] must be an object"
            )
        cap_keys = set(caps.keys())
        expected_caps = set(CAPABILITY_KEYS)
        if cap_keys != expected_caps:
            missing = sorted(expected_caps - cap_keys)
            extra = sorted(cap_keys - expected_caps)
            raise MatrixValidationError(
                f"permission_json['{role}'] capabilities must be exactly "
                f"{sorted(expected_caps)} (missing={missing}, unexpected={extra})"
            )
        role_caps: dict[str, bool] = {}
        for capability in CAPABILITY_KEYS:
            value = caps[capability]
            if not isinstance(value, bool):
                raise MatrixValidationError(
                    f"permission_json['{role}']['{capability}'] must be a boolean"
                )
            role_caps[capability] = value
        normalised[role] = role_caps
    return normalised


def merge_matrix(
    base: dict[str, dict[str, bool]], partial: object
) -> dict[str, dict[str, bool]]:
    """Deep-merge ``partial`` role/capability overrides onto ``base``.

    Only the roles/capabilities present in ``partial`` are changed. The merged
    result is returned unvalidated; callers must run :func:`validate_matrix` on
    it so garbage keys in ``partial`` surface as a validation error rather than
    silently persisting.

    Args:
        base: The current full matrix (assumed already valid).
        partial: A partial ``{role: {capability: bool}}`` override.

    Raises:
        MatrixValidationError: ``partial`` is not an object.
    """
    if not isinstance(partial, dict):
        raise MatrixValidationError("permission_json must be an object")
    merged = {role: dict(caps) for role, caps in base.items()}
    for role, caps in partial.items():
        if not isinstance(caps, dict):
            raise MatrixValidationError(
                f"permission_json['{role}'] must be an object"
            )
        target = merged.setdefault(role, {})
        for capability, value in caps.items():
            target[capability] = value
    return merged


def evaluate_matrix(
    matrix: dict[str, dict[str, bool]],
    roles: Iterable[str],
    capability: str,
) -> bool:
    """Return the allow/deny verdict of the new model for ``capability``.

    Allow iff at least one of the actor's ``roles`` grants ``capability`` in
    ``matrix`` — mirroring the "any role permits" semantics of
    :meth:`AuthorizationService.decide_access`.
    """
    for role in roles:
        role_caps = matrix.get(role.lower())
        if role_caps and role_caps.get(capability, False):
            return True
    return False


__all__ = [
    "ROLE_KEYS",
    "CAPABILITY_KEYS",
    "MatrixValidationError",
    "default_permission_matrix",
    "validate_matrix",
    "merge_matrix",
    "evaluate_matrix",
]
