"""NotificationPreferenceService — the recipient filter (OD-1, Task 27).

Database-backed on purpose: the contract is "one query against the preference
table, subtract the users who disabled the kind", so a mocked ORM would test
nothing. Case (f) deliberately simulates that one query failing to pin the
fail-open contract (spec §9 A3).
"""
from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError
from unittest.mock import patch

from application.models import Notification
from application.notification_preference_service import (
    ALL_KINDS,
    NotificationPreferenceService,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import UserNotificationPreference
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


def _user(tenant: Tenant, label: str) -> User:
    return User.objects.create(
        username=f"{label}-{uuid.uuid4().hex[:6]}",
        email=f"{label}{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def alice(tenant: Tenant) -> User:
    return _user(tenant, "alice")


@pytest.fixture
def bob(tenant: Tenant) -> User:
    return _user(tenant, "bob")


@pytest.fixture
def ctx(alice: User, tenant: Tenant) -> AuthContext:
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# (a) no row -> everything on, filter is a pass-through
def test_no_row_means_all_kinds_enabled(ctx) -> None:
    """(a) A missing row is "all on", and the filter returns the input unchanged."""
    # §6: one definition of the vocabulary, derived from the model.
    assert ALL_KINDS == tuple(kind for kind, _label in Notification.KIND_CHOICES)

    svc = NotificationPreferenceService()

    effective = svc.get_effective_preferences(ctx)
    assert set(effective) == {
        Notification.KIND_ASSIGNED,
        Notification.KIND_COMMENT_ADDED,
        Notification.KIND_TRANSITION_PENDING,
        Notification.KIND_SUSPECT_FLAGGED,
    }
    assert all(effective.values())

    candidates = [ctx.user_id]
    assert svc.apply_preferences(ctx, candidates, Notification.KIND_COMMENT_ADDED) == candidates


# (b) one disabled kind removes exactly that kind
def test_disabled_kind_removes_only_that_user_for_that_kind(ctx, alice, bob) -> None:
    """(b) ``comment_added`` disabled -> removed there, other kinds pass through."""
    UserNotificationPreference.objects.create(
        user=alice, disabled_triggers=[Notification.KIND_COMMENT_ADDED]
    )
    svc = NotificationPreferenceService()

    candidates = [alice.pk, bob.pk]
    assert svc.apply_preferences(ctx, candidates, Notification.KIND_COMMENT_ADDED) == [bob.pk]

    for other_kind in (
        Notification.KIND_ASSIGNED,
        Notification.KIND_TRANSITION_PENDING,
        Notification.KIND_SUSPECT_FLAGGED,
    ):
        assert svc.apply_preferences(ctx, candidates, other_kind) == candidates


# (c) disabling one kind does not silence another
def test_user_disabled_for_assigned_still_receives_transition_pending(
    ctx, alice
) -> None:
    """(c) The switches are independent."""
    UserNotificationPreference.objects.create(
        user=alice, disabled_triggers=[Notification.KIND_ASSIGNED]
    )
    svc = NotificationPreferenceService()

    assert svc.apply_preferences(ctx, [alice.pk], Notification.KIND_ASSIGNED) == []
    assert svc.apply_preferences(
        ctx, [alice.pk], Notification.KIND_TRANSITION_PENDING
    ) == [alice.pk]


# (d) junk in the stored list is ignored, not an error
def test_blank_and_unknown_entries_are_ignored(ctx, alice) -> None:
    """(d) A stale/unknown entry never breaks delivery (A2: no DB vocabulary).

    An unknown *kind argument* is likewise a pass-through: the vocabulary is
    closed and a future kind must not silently lose every recipient.
    """
    UserNotificationPreference.objects.create(
        user=alice, disabled_triggers=["", "   ", "no_such_kind", None, 42]
    )
    svc = NotificationPreferenceService()

    assert svc.get_effective_preferences(ctx) == {kind: True for kind in ALL_KINDS}
    assert svc.apply_preferences(ctx, [alice.pk], Notification.KIND_ASSIGNED) == [alice.pk]
    assert svc.apply_preferences(ctx, [alice.pk], "not_a_kind") == [alice.pk]


# (e) order preserved, duplicates collapsed
def test_apply_preferences_preserves_order_and_deduplicates(ctx, alice, bob) -> None:
    """(e) Input order wins; a repeated id is one candidate, ``None`` is dropped."""
    svc = NotificationPreferenceService()

    assert svc.apply_preferences(
        ctx, [bob.pk, alice.pk, bob.pk, None], Notification.KIND_COMMENT_ADDED
    ) == [bob.pk, alice.pk]


# (f) fail-open: a broken lookup delivers unfiltered
def test_lookup_failure_returns_the_candidates_unchanged(ctx, alice, bob) -> None:
    """(f) Fail-open (A3): a lookup crash must not silently stop delivery."""
    svc = NotificationPreferenceService()
    candidates = [alice.pk, bob.pk]

    with patch(
        "application.notification_preference_service.UserNotificationPreference"
    ) as model:
        model.objects.filter.side_effect = DatabaseError("preference table unreachable")
        result = svc.apply_preferences(ctx, candidates, Notification.KIND_COMMENT_ADDED)

    assert result == candidates


# (g) update round-trip leaves no duplicate entry
def test_update_preferences_round_trips_without_duplicates(ctx, alice) -> None:
    """(g) False then True returns to all-enabled, storing ``[]`` once."""
    svc = NotificationPreferenceService()

    disabled = svc.update_preferences(ctx, {Notification.KIND_COMMENT_ADDED: False})
    assert disabled[Notification.KIND_COMMENT_ADDED] is False
    assert disabled[Notification.KIND_ASSIGNED] is True

    row = UserNotificationPreference.objects.get(user=alice)
    assert row.disabled_triggers == [Notification.KIND_COMMENT_ADDED]

    enabled = svc.update_preferences(ctx, {Notification.KIND_COMMENT_ADDED: True})
    assert enabled == {kind: True for kind in ALL_KINDS}

    row.refresh_from_db()
    assert row.disabled_triggers == []
    assert UserNotificationPreference.objects.filter(user=alice).count() == 1
