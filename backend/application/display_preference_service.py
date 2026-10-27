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

Storage split (Plan C, T-C2-6; ENT-C5 = A)
------------------------------------------
Only ``show_readable_ids`` moved onto the generic three-level preference store
(Q1, ``application.preference_service``): it is a display switch that also has
a meaningful tenant-wide default, so it is read as
``user > global > registry default`` through ``resolve_for`` and written to the
caller's user level through ``set_level``. The response contract did not change.

``visible_metrics`` stays on the ``UserDisplayPreference`` column: it is a
per-user widget selection with no tenant-wide meaning, so Q1 would only add
churn (see the plan's O3 / ENT-C5 decision).

The legacy ``show_readable_ids`` column is not read here any more; migration
``auth_tenancy/0031_backfill_show_readable_ids`` copied the pre-existing
``False`` values into Q1 and its reverse restores the column, so a rollback of
this change keeps every user's choice.

Requirements: Issue #1096, Plan C T-C2-6.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction

from application.base import ServiceBase
from application.preference_service import PreferenceService, resolve_for
from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserDisplayPreference
from persistence.errors import ValidationError

#: The closed display-preference vocabulary. A new flag is added here and in
#: ``DisplayPreferenceUpdateSerializer`` together — the serializer's declared
#: fields *are* the request vocabulary, this tuple is the service-side guard.
#:
#: * ``show_readable_ids`` (Issue #1096) — bool.
#: * ``visible_metrics`` (Issue #1265) — list of metric keys, or ``None`` for
#:   "no explicit selection" (render the registry default set).
ALL_DISPLAY_PREFERENCES: tuple[str, ...] = ("show_readable_ids", "visible_metrics")

#: Q1 key that now backs ``show_readable_ids`` (Plan C, T-C2-6).
SHOW_READABLE_IDS_KEY = "ui.ids.show_readable"

#: Server-side default. Mirrors the frontend fallback (readable ids visible) so
#: an absent row never changes the rendered behaviour. The Q1 registry entry
#: declares the same default; this constant only seeds a display row.
SHOW_READABLE_IDS_DEFAULT = True

#: Sentinel returned for ``visible_metrics`` when the caller has no explicit
#: selection. The client resolves it against
#: ``se_metrics.registry.DEFAULT_METRIC_KEYS``.
VISIBLE_METRICS_DEFAULT: None = None


def _validate_visible_metrics(value: Any) -> None:
    """Reject anything that is neither ``None`` nor a list of known keys.

    Issue #1265: the stored list is the widget selection *and* its order, so it
    must stay a plain list of registry keys. Validating against the registry
    (not just "is a list of strings") means a typo can never be persisted and
    silently render an empty dashboard.
    """
    if value is None:
        return
    if not isinstance(value, list):
        raise ValidationError("Display preference 'visible_metrics' must be a list or null.")
    # Imported lazily: keeps this module importable without Django app loading
    # and documents the registry as the owning authority for metric keys.
    from se_metrics.registry import is_known_metric

    unknown = [str(k) for k in value if not (isinstance(k, str) and is_known_metric(k))]
    if unknown:
        raise ValidationError(
            f"Unknown metric key(s) in 'visible_metrics': {sorted(unknown)}"
        )


class DisplayPreferenceService(ServiceBase):
    """Read/write the caller's own display preferences (Issue #1096)."""

    def get_display_preferences(self, ctx: AuthContext) -> dict[str, Any]:
        """Return the caller's effective display flags.

        ``show_readable_ids`` is resolved through Q1 (Plan C, T-C2-6) as
        ``user > global > registry default`` — the caller's own user level is
        the whole boundary, and a tenant-wide default now applies to accounts
        that never touched the switch.

        ``visible_metrics`` still comes from the ``UserDisplayPreference``
        column. A missing row is *not* an error: every flag falls back to its
        default, so first access returns the same payload as an untouched
        account.
        """
        self._set_tenant_context(ctx)
        row = UserDisplayPreference.objects.filter(user_id=ctx.user_id).first()
        show_readable_ids, _source = resolve_for(
            tenant_id=ctx.tenant_id,
            # Account-wide view: Q1's workspace level does not participate.
            workspace_id=None,
            user_id=ctx.user_id,
            key=SHOW_READABLE_IDS_KEY,
        )
        return {
            "show_readable_ids": show_readable_ids,
            "visible_metrics": (
                row.visible_metrics if row is not None else VISIBLE_METRICS_DEFAULT
            ),
        }

    def update_display_preferences(
        self, ctx: AuthContext, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply a partial display update and return the fresh effective flags.

        Only keys in :data:`ALL_DISPLAY_PREFERENCES` are accepted; anything else
        — an unknown key, a non-``bool`` ``show_readable_ids``, or a
        ``visible_metrics`` value that is not a known-key list — is caller
        input, not a server fault, and is rejected with
        :class:`ValidationError` (the view maps it to 400). ``None`` is not part
        of this contract for ``show_readable_ids``: the display toggle has no
        "inherit" state (reset happens on Q1's own route).

        Each key is written to its own store (Q1 for ``show_readable_ids``, the
        column for ``visible_metrics``) inside one transaction, so a PATCH
        carrying both is all-or-nothing. An empty *changes* map is a read-only
        no-op so a PATCH with an empty body still answers with the caller's
        current flags instead of creating a row.
        """
        for key, value in changes.items():
            if key not in ALL_DISPLAY_PREFERENCES:
                raise ValidationError(f"Unknown display preference: {key!r}")
            if key == "show_readable_ids" and not isinstance(value, bool):
                raise ValidationError(
                    f"Display preference {key!r} must be a boolean, "
                    f"got {type(value).__name__}"
                )
            if key == "visible_metrics":
                _validate_visible_metrics(value)

        if not changes:
            return self.get_display_preferences(ctx)

        self._set_tenant_context(ctx)
        with transaction.atomic():
            if "show_readable_ids" in changes:
                # Self-service user level: ``ctx.user_id`` is the whole
                # boundary, exactly as for the legacy column before T-C2-6.
                PreferenceService().set_level(
                    ctx,
                    scope="user",
                    values={SHOW_READABLE_IDS_KEY: changes["show_readable_ids"]},
                )
            if "visible_metrics" in changes:
                self._write_visible_metrics(ctx, changes["visible_metrics"])

        return self.get_display_preferences(ctx)

    @staticmethod
    def _write_visible_metrics(ctx: AuthContext, value: Any) -> None:
        """Persist *value* on the display row (the column Q1 does not carry)."""
        # ``UserDisplayPreference`` extends ``TenantScopedModel``; ``get_or_create``
        # instantiates and saves the model internally, bypassing
        # ``TenantManager.create``'s tenant auto-inject, so ``tenant_id`` is
        # passed explicitly to satisfy the NOT-NULL column (same reasoning as
        # ``auth_tenancy.services.PreferenceService.get_or_create_preference``).
        row, created = UserDisplayPreference.objects.get_or_create(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            defaults={
                "show_readable_ids": SHOW_READABLE_IDS_DEFAULT,
                "visible_metrics": value,
            },
        )
        if not created:
            row.visible_metrics = value
            row.save(update_fields=["visible_metrics", "modified_at"])


__all__ = [
    "ALL_DISPLAY_PREFERENCES",
    "SHOW_READABLE_IDS_DEFAULT",
    "SHOW_READABLE_IDS_KEY",
    "VISIBLE_METRICS_DEFAULT",
    "DisplayPreferenceService",
]
