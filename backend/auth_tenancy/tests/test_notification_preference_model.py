"""
OD-1 (2026-09-15) — UserNotificationPreference model tests.

Covers the user-global opt-out model that gates in-app notification delivery:

* (a) ``disabled_triggers`` defaults to ``[]`` and survives a save/refresh
  round-trip.
* (b) a second row for the same ``user`` is rejected — the ``OneToOneField`` is
  both the uniqueness rule and the access path.
* (c) two users each get their own row.
* (d) the same user reading the row under a *different* tenant/workspace context
  still sees the SAME single row — this is what "user-global" means (§9, A1).

The model is intentionally NOT tenant-scoped and has no RLS policy, so the
default (unfiltered) manager is used throughout.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from auth_tenancy.models import UserNotificationPreference
from persistence.models import Workspace

from .conftest import active_tenant


@pytest.mark.django_db
class TestUserNotificationPreference:
    """Model behaviour for the per-user notification opt-out (OD-1)."""

    def test_disabled_triggers_default_and_round_trip(self, user_a):
        """(a) Defaults to ``[]`` and survives a save/refresh round-trip."""
        pref = UserNotificationPreference.objects.create(user=user_a)
        assert pref.disabled_triggers == []

        pref.refresh_from_db()
        assert pref.disabled_triggers == []

        pref.disabled_triggers = ["assigned", "comment_added"]
        pref.save()
        pref.refresh_from_db()
        assert pref.disabled_triggers == ["assigned", "comment_added"]

    def test_second_row_for_the_same_user_is_rejected(self, user_a):
        """(b) The OneToOneField rejects a second row for one user."""
        UserNotificationPreference.objects.create(user=user_a)
        with transaction.atomic():
            with pytest.raises(IntegrityError):
                UserNotificationPreference.objects.create(user=user_a)

    def test_two_users_get_their_own_rows(self, user_a, user_b):
        """(c) Distinct users own distinct preference rows."""
        pref_a = UserNotificationPreference.objects.create(
            user=user_a, disabled_triggers=["suspect_flagged"]
        )
        pref_b = UserNotificationPreference.objects.create(user=user_b)

        assert pref_a.pk != pref_b.pk
        assert UserNotificationPreference.objects.count() == 2
        assert UserNotificationPreference.objects.get(user=user_a).pk == pref_a.pk
        assert UserNotificationPreference.objects.get(user=user_b).pk == pref_b.pk

    def test_row_is_visible_from_a_different_tenant_context(self, user_a, tenant_b):
        """(d) The row is user-global: another active tenant sees the same one."""
        pref = UserNotificationPreference.objects.create(
            user=user_a, disabled_triggers=["transition_pending"]
        )

        with active_tenant(tenant_b):
            Workspace.objects.create(tenant=tenant_b, name="WS-B")
            rows = list(UserNotificationPreference.objects.filter(user=user_a))

        assert len(rows) == 1
        assert rows[0].pk == pref.pk
        assert rows[0].disabled_triggers == ["transition_pending"]
