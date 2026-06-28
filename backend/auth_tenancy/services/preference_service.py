"""
ARCH-L1-011 AuthAndTenancy — UserWorkspacePreference service (REQ-L1-027).

Provides CRUD and merge logic for per-user visibility overrides that sit on top
of the workspace preset defaults (PRESET_VISIBILITY).

Design:
  - ``get_preference``        — read-only lookup, returns None when no row exists.
  - ``get_or_create_preference`` — idempotent creation for first-time access.
  - ``update_visibility``     — merges caller-supplied overrides into the existing
    JSON dict (shallow merge; keys not present in *overrides* are preserved).
  - ``get_effective_visibility`` — combines preset defaults with user overrides so
    callers get a single {feature: bool} map to consume.

Tenant isolation is inherited from the ``TenantScopedModel`` default manager —
all queries are automatically scoped once a tenant context is active.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from auth_tenancy.models import UserWorkspacePreference


class PreferenceService:
    """Service facade for UserWorkspacePreference operations (REQ-L1-027)."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_preference(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> UserWorkspacePreference | None:
        """Return the preference row or ``None`` if it does not exist."""
        return (
            UserWorkspacePreference.objects.filter(
                user_id=user_id,
                workspace_id=workspace_id,
            )
            .first()
        )

    # ------------------------------------------------------------------
    # Create / get-or-create
    # ------------------------------------------------------------------

    def get_or_create_preference(
        self,
        user_id: UUID,
        workspace_id: UUID,
    ) -> UserWorkspacePreference:
        """Return the existing preference or create a blank one."""
        pref, _created = UserWorkspacePreference.objects.get_or_create(
            user_id=user_id,
            workspace_id=workspace_id,
            defaults={"optional_artifact_visibility": {}},
        )
        return pref

    # ------------------------------------------------------------------
    # Update (merge)
    # ------------------------------------------------------------------

    def update_visibility(
        self,
        user_id: UUID,
        workspace_id: UUID,
        overrides: dict[str, Any],
    ) -> UserWorkspacePreference:
        """Merge *overrides* into the existing ``optional_artifact_visibility``.

        Keys present in *overrides* replace existing values; keys not mentioned
        are preserved.  Returns the updated preference instance.
        """
        pref = self.get_or_create_preference(user_id, workspace_id)
        merged = {**pref.optional_artifact_visibility, **overrides}
        pref.optional_artifact_visibility = merged
        pref.save(update_fields=["optional_artifact_visibility", "modified_at"])
        return pref

    # ------------------------------------------------------------------
    # Effective visibility (preset defaults + user overrides)
    # ------------------------------------------------------------------

    def get_effective_visibility(
        self,
        user_id: UUID,
        workspace_id: UUID,
        preset_map: dict[str, bool],
    ) -> dict[str, bool]:
        """Return preset defaults merged with user overrides.

        *preset_map* is the baseline (e.g. ``PRESET_VISIBILITY[preset]``).
        User overrides take precedence for keys that exist in both maps.
        """
        pref = self.get_preference(user_id, workspace_id)
        if pref is None:
            return dict(preset_map)
        return {**preset_map, **pref.optional_artifact_visibility}


__all__ = ["PreferenceService"]
