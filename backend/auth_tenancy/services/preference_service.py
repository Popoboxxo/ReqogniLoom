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

Tenant isolation is enforced via ``ServiceBase._set_tenant_context`` —
every public method MUST be called with a valid ``AuthContext`` and that context
is propagated to the thread-local ORM filter so that ``TenantScopedModel.objects``
is automatically scoped (REQ-L2-AS-022).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from application.base import ServiceBase
from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserWorkspacePreference


class PreferenceService(ServiceBase):
    """Service facade for UserWorkspacePreference operations (REQ-L1-027).

    Extends :class:`ServiceBase` so each public method can call
    ``_set_tenant_context(ctx)`` and propagate the active tenant into the ORM
    filter — without it, ``TenantScopedModel.objects.get_or_create(...)`` would
    either raise ``TenantContextNotSetError`` or insert ``tenant_id=NULL`` and
    violate the NOT-NULL constraint.
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_preference(
        self,
        user_id: UUID,
        workspace_id: UUID,
        ctx: AuthContext,
    ) -> UserWorkspacePreference | None:
        """Return the preference row or ``None`` if it does not exist."""
        self._set_tenant_context(ctx)
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
        ctx: AuthContext,
    ) -> UserWorkspacePreference:
        """Return the existing preference or create a blank one.

        ``UserWorkspacePreference`` extends ``TenantScopedModel``; the
        ``TenantManager`` auto-injects ``tenant_id`` from the active context,
        which is set above via ``_set_tenant_context(ctx)``.
        """
        self._set_tenant_context(ctx)
        # NOTE: ``get_or_create`` instantiates the model and calls ``.save()``
        # internally, which bypasses ``TenantManager.create``'s auto-inject
        # for the ``tenant`` FK. We therefore pass ``tenant_id`` explicitly so
        # the NOT-NULL constraint on ``tenant_id`` is satisfied (REQ-L1-027).
        pref, _created = UserWorkspacePreference.objects.get_or_create(
            user_id=user_id,
            workspace_id=workspace_id,
            tenant_id=ctx.tenant_id,
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
        ctx: AuthContext,
    ) -> UserWorkspacePreference:
        """Merge *overrides* into the existing ``optional_artifact_visibility``.

        Keys present in *overrides* replace existing values; keys not mentioned
        are preserved.  Returns the updated preference instance.
        """
        self._set_tenant_context(ctx)
        pref = self.get_or_create_preference(user_id, workspace_id, ctx=ctx)
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
        ctx: AuthContext,
    ) -> dict[str, bool]:
        """Return preset defaults merged with user overrides.

        *preset_map* is the baseline (e.g. ``PRESET_VISIBILITY[preset]``).
        User overrides take precedence for keys that exist in both maps.
        """
        self._set_tenant_context(ctx)
        pref = self.get_preference(user_id, workspace_id, ctx=ctx)
        if pref is None:
            return dict(preset_map)
        return {**preset_map, **pref.optional_artifact_visibility}


__all__ = ["PreferenceService"]
