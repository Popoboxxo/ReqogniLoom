"""Workspace allocation settings (D9, ADR-028).

Two Q1 keys, both workspace-overridable and audited like every preference
write:

- ``allocation.cardinality``: ``single`` (default, today's behaviour) or
  ``multiple``.
- ``allocation.conflict_severity``: ``info`` | ``warning`` (default) |
  ``blocker`` — the severity the audit reports for a multi-allocation.

Reading goes through the Q1 resolver so a global default and a workspace
override combine exactly like every other preference.
"""

from __future__ import annotations

from uuid import UUID

CARDINALITY_KEY = "allocation.cardinality"
CONFLICT_SEVERITY_KEY = "allocation.conflict_severity"

CARDINALITY_SINGLE = "single"
CARDINALITY_MULTIPLE = "multiple"
CARDINALITY_CHOICES = (CARDINALITY_SINGLE, CARDINALITY_MULTIPLE)

SEVERITY_CHOICES = ("info", "warning", "blocker")


def _value(*, tenant_id: UUID | None, workspace_id: UUID | None, key: str, default: str) -> str:
    if tenant_id is None:
        return default
    from application.preference_service import resolve_for

    try:
        value, _source = resolve_for(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=None,
            key=key,
        )
    except Exception:  # noqa: BLE001 - a missing registry entry must not break allocation
        return default
    return str(value) if value else default


def cardinality_for(*, tenant_id: UUID | None, workspace_id: UUID | None) -> str:
    """Return ``single`` or ``multiple`` for this workspace."""
    return _value(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        key=CARDINALITY_KEY,
        default=CARDINALITY_SINGLE,
    )
