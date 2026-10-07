"""Per-user display preference (Issue #1096).

Server-side home of the "readable ids may be hidden" UI toggle that until now
lived only in the frontend's ``localStorage``
(``frontend/src/hooks/useReadableIdsVisible.ts``). The server value is the source
of truth; the frontend keeps ``localStorage`` only as a first-render fallback.

The preference is account-scoped and served under the same ``users/me/**``
self-service envelope as the sibling notification/theme preference endpoints:
``ctx.user_id`` is the whole authorization boundary — the view takes no
``user_id`` parameter and applies no admin gate.

Placement mirrors ``application.notification_preference_service``: Layer 2, so
the ``rest_api/*_views.py`` modules keep their no-direct-ORM ratchet
(``rest_api/tests/test_architecture.py``). The direction
``application -> auth_tenancy.models`` is an established import, not a new cycle.

Requirements: Issue #1096.
"""
from __future__ import annotations

from typing import Any

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserDisplayPreference
from persistence.errors import ValidationError

from application.base import ServiceBase

#: The closed display-preference vocabulary (Issue #1096). A new flag is added
#: here and in ``DisplayPreferenceUpdateSerializer`` together — the serializer's
#: declared fields *are* the request vocabulary, this tuple is the service-side
#: guard.
ALL_DISPLAY_PREFERENCES: tuple[str, ...] = ("show_readable_ids",)

#: Server-side default. Mirrors the frontend fallback (readable ids visible) so
#: an absent row never changes the rendered behaviour.
SHOW_READABLE_IDS_DEFAULT = True


class DisplayPreferenceService(ServiceBase):
    """Read/write the caller's own display preferences (Issue #1096)."""

    def get_display_preferences(self, ctx: AuthContext) -> dict[str, bool]:
        """Return the caller's effective display flags.

        A missing row is *not* an error: every flag falls back to its server
        default, so first access returns the same payload as an untouched
        account.
        """
        self._set_tenant_context(ctx)
        row = UserDisplayPreference.objects.filter(user_id=ctx.user_id).first()
        return {
            "show_readable_ids": (
                row.show_readable_ids
                if row is not None
                else SHOW_READABLE_IDS_DEFAULT
            )
        }

    def update_display_preferences(
        self, ctx: AuthContext, changes: dict[str, Any]
    ) -> dict[str, bool]:
        """Apply a partial display update and return the fresh effective flags.

        Only keys in :data:`ALL_DISPLAY_PREFERENCES` are accepted; anything else
        (or a non-``bool`` value) is caller input, not a server fault, and is
        rejected with :class:`ValidationError` — the view maps it to 400.

        An empty *changes* map is a read-only no-op so a PATCH with an empty body
        still answers with the caller's current flags instead of creating a row.
        """
        for key, value in changes.items():
            if key not in ALL_DISPLAY_PREFERENCES:
                raise ValidationError(f"Unknown display preference: {key!r}")
            if not isinstance(value, bool):
                raise ValidationError(
                    f"Display preference {key!r} must be a boolean, "
                    f"got {type(value).__name__}"
                )

        if not changes:
            return self.get_display_preferences(ctx)

        self._set_tenant_context(ctx)
        # ``UserDisplayPreference`` extends ``TenantScopedModel``; ``get_or_create``
        # instantiates and saves the model internally, bypassing
        # ``TenantManager.create``'s tenant auto-inject, so ``tenant_id`` is
        # passed explicitly to satisfy the NOT-NULL column (same reasoning as
        # ``auth_tenancy.services.PreferenceService.get_or_create_preference``).
        row, _created = UserDisplayPreference.objects.get_or_create(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            defaults={"show_readable_ids": SHOW_READABLE_IDS_DEFAULT},
        )
        for key, value in changes.items():
            setattr(row, key, value)
        row.save(update_fields=[*changes.keys(), "modified_at"])
        return self.get_display_preferences(ctx)


__all__ = [
    "ALL_DISPLAY_PREFERENCES",
    "SHOW_READABLE_IDS_DEFAULT",
    "DisplayPreferenceService",
]
