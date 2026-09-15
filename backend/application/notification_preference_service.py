"""Per-user notification preference filter (Menschen-im-System spec §5, Task 27).

This module owns the single place that turns "candidate recipients + trigger
kind" into "recipients who actually want this trigger", plus the read/write
projection the self-service endpoint (Task 28) will consume.

Why it lives in ``application/`` and not next to ``auth_tenancy.services``:
that package already imports ``application.base.ServiceBase``, so putting the
filter there would create an ``application -> auth_tenancy.services ->
application`` import cycle the moment Task 10 imports it. The
``application -> auth_tenancy.models`` direction, by contrast, is an
established import (``application.memory_admin_service`` imports
``auth_tenancy.models.UserRole``).

The preference is **user-global** (OD-1/A1): one row per user across every
tenant and workspace. ``UserNotificationPreference`` is therefore a plain
``AuditableModel`` with a ``OneToOneField(user)`` and no ``tenant`` column, so
``ctx`` is only ever read for ``ctx.user_id`` here and only ``ctx.tenant_id``
is passed through for signature symmetry.

Requirements: OD-1 (2026-09-15); spec §5, §9 A3.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable
from uuid import UUID

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserNotificationPreference
from persistence.errors import ValidationError

from application.base import ServiceBase
from application.models import Notification

logger = logging.getLogger(__name__)

#: The closed trigger vocabulary (spec §6). Derived from the model so there is
#: exactly one definition — a second literal four-item list is forbidden.
ALL_KINDS: tuple[str, ...] = tuple(kind for kind, _label in Notification.KIND_CHOICES)


class NotificationPreferenceService(ServiceBase):
    """Recipient filter plus the caller's own preference projection (OD-1)."""

    # ---------- the filter ----------

    def apply_preferences(
        self, ctx: AuthContext, user_ids: Iterable[Any], kind: str
    ) -> list[UUID]:
        """Return the subset of *user_ids* that wants *kind* delivered.

        Input order is preserved, duplicates are collapsed and ``None`` entries
        are dropped. Users whose stored ``disabled_triggers`` contains *kind*
        are removed; a missing row means "enabled" for every kind. An unknown
        *kind* filters nothing (the vocabulary is closed and a caller passing a
        future kind must not silently lose every recipient).

        Fail-open by contract (spec §9 A3): any lookup failure is logged and the
        (de-duplicated) candidate list is returned unchanged. The four producers
        all carry a "never raise — a notification must not break the mutation it
        reacts to" contract, and failing *closed* here would additionally stop
        delivery for every user the moment the preference table is unreachable,
        which is a worse failure than an un-muted notification.
        """
        candidates = list(dict.fromkeys(uid for uid in user_ids if uid is not None))
        if kind not in ALL_KINDS or not candidates:
            return candidates

        try:
            self._set_tenant_context(ctx)
            rows = UserNotificationPreference.objects.filter(
                user_id__in=candidates
            ).values_list("user_id", "disabled_triggers")

            disabled_users: set[UUID] = set()
            for user_id, disabled_triggers in rows:
                if kind in self._disabled_set(disabled_triggers):
                    disabled_users.add(user_id)
        except Exception:
            logger.exception(
                "NotificationPreferenceService.apply_preferences: preference "
                "lookup failed for kind=%s; delivering unfiltered (fail-open).",
                kind,
            )
            return candidates

        return [uid for uid in candidates if uid not in disabled_users]

    # ---------- the caller's own projection ----------

    def get_effective_preferences(self, ctx: AuthContext) -> dict[str, bool]:
        """Return ``{kind: enabled}`` for all kinds, read from the caller's row.

        ``True`` for every kind when no row exists or the kind is absent from
        ``disabled_triggers`` — opting out is the deviation, not opting in.
        """
        self._set_tenant_context(ctx)
        row = UserNotificationPreference.objects.filter(user_id=ctx.user_id).first()
        disabled = self._disabled_set(row.disabled_triggers if row is not None else None)
        return {kind: kind not in disabled for kind in ALL_KINDS}

    def update_preferences(
        self, ctx: AuthContext, changes: dict[str, bool]
    ) -> dict[str, bool]:
        """Apply a partial update and return the fresh effective map.

        ``False`` adds a kind to ``disabled_triggers``, ``True`` removes it;
        kinds absent from *changes* are untouched. The stored list is
        de-duplicated in the deterministic :data:`ALL_KINDS` order.

        Raises:
            ValidationError: *changes* names an unknown kind or carries a
                non-``bool`` value (the view maps this to 400).
        """
        for kind, value in changes.items():
            if kind not in ALL_KINDS:
                raise ValidationError(f"Unknown notification trigger: {kind!r}")
            if not isinstance(value, bool):
                raise ValidationError(
                    f"Notification trigger {kind!r} must be a boolean, "
                    f"got {type(value).__name__}"
                )

        if not changes:
            return self.get_effective_preferences(ctx)

        self._set_tenant_context(ctx)
        row = UserNotificationPreference.objects.filter(user_id=ctx.user_id).first()
        disabled = self._disabled_set(row.disabled_triggers if row is not None else None)

        for kind, enabled in changes.items():
            if enabled:
                disabled.discard(kind)
            else:
                disabled.add(kind)

        ordered = [kind for kind in ALL_KINDS if kind in disabled]
        # The OneToOneField is the whole lookup — no tenant column exists on the
        # model (user-global preference, OD-1/A1).
        UserNotificationPreference.objects.update_or_create(
            user_id=ctx.user_id,
            defaults={"disabled_triggers": ordered},
        )

        return {kind: kind not in disabled for kind in ALL_KINDS}

    # ---------- helpers ----------

    @staticmethod
    def _disabled_set(raw: Any) -> set[str]:
        """Return the known kinds in a stored ``disabled_triggers`` value.

        Blank and unknown entries are ignored rather than raising: the column is
        a JSON list and its vocabulary is enforced in the serializer (A2), not
        in the database, so a stale entry must never break delivery.
        """
        if not isinstance(raw, (list, tuple)):
            return set()
        return {entry for entry in raw if isinstance(entry, str) and entry in ALL_KINDS}


__all__ = ["ALL_KINDS", "NotificationPreferenceService"]
