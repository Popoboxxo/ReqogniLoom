"""NotificationService — read side plus the shared producer.

Adapted from Plan #6 Task 10 Step 1. The only change against the original block
is the ``AuthContext`` construction (``auth_method`` is required, not defaulted)
and the ``active_roles`` tuple, matching every other test in this suite.
"""
from __future__ import annotations

import uuid

import pytest

from application.models import Notification
from application.notification_service import NotificationService, create_notifications
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, User


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def alice(db, tenant):
    return User.objects.create(
        username=f"alice-{uuid.uuid4().hex[:6]}",
        email=f"a{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def bob(db, tenant):
    return User.objects.create(
        username=f"bob-{uuid.uuid4().hex[:6]}",
        email=f"b{uuid.uuid4().hex[:6]}@example.com",
        tenant=tenant,
    )


@pytest.fixture
def ctx(alice, tenant):
    return AuthContext(
        user_id=alice.pk,
        tenant_id=tenant.pk,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.mark.django_db
def test_create_notifications_writes_one_row_per_user(tenant, alice, bob):
    written = create_notifications(
        user_ids=[alice.pk, bob.pk],
        kind=Notification.KIND_ASSIGNED,
        message="you were assigned",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 2
    assert Notification.unscoped.filter(tenant_id=tenant.pk).count() == 2


@pytest.mark.django_db
def test_create_notifications_skips_the_acting_user(tenant, alice, bob):
    written = create_notifications(
        user_ids=[alice.pk, bob.pk],
        kind=Notification.KIND_COMMENT_ADDED,
        message="new comment",
        artifact_id=None,
        tenant_id=tenant.pk,
        exclude_user_id=alice.pk,
    )
    assert written == 1
    assert Notification.unscoped.get(tenant_id=tenant.pk).user_id == bob.pk


@pytest.mark.django_db
def test_create_notifications_deduplicates_user_ids(tenant, alice):
    """owner == assignee must produce one notification, not two."""
    written = create_notifications(
        user_ids=[alice.pk, alice.pk],
        kind=Notification.KIND_SUSPECT_FLAGGED,
        message="suspect",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 1


@pytest.mark.django_db
def test_create_notifications_ignores_none_user_ids(tenant):
    """Unset owner/assignee are passed straight through as None by every trigger."""
    written = create_notifications(
        user_ids=[None, None],
        kind=Notification.KIND_ASSIGNED,
        message="x",
        artifact_id=None,
        tenant_id=tenant.pk,
    )
    assert written == 0


@pytest.mark.django_db
def test_list_for_user_returns_only_own_notifications(ctx, tenant, alice, bob):
    create_notifications(
        user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
        message="mine", artifact_id=None, tenant_id=tenant.pk,
    )
    create_notifications(
        user_ids=[bob.pk], kind=Notification.KIND_ASSIGNED,
        message="theirs", artifact_id=None, tenant_id=tenant.pk,
    )

    rows = NotificationService().list_for_user(ctx)
    assert [r.message for r in rows] == ["mine"]


@pytest.mark.django_db
def test_mark_read_flips_the_flag(ctx, tenant, alice):
    create_notifications(
        user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
        message="m", artifact_id=None, tenant_id=tenant.pk,
    )
    row = NotificationService().list_for_user(ctx)[0]

    updated = NotificationService().mark_read(row.pk, ctx)
    assert updated.read is True


@pytest.mark.django_db
def test_mark_read_refuses_another_users_notification(ctx, tenant, bob):
    from persistence.errors import NotFoundError

    create_notifications(
        user_ids=[bob.pk], kind=Notification.KIND_ASSIGNED,
        message="m", artifact_id=None, tenant_id=tenant.pk,
    )
    other = Notification.unscoped.get(user_id=bob.pk)

    with pytest.raises(NotFoundError):
        NotificationService().mark_read(other.pk, ctx)


@pytest.mark.django_db
def test_mark_all_read_and_unread_count(ctx, tenant, alice):
    for message in ("a", "b"):
        create_notifications(
            user_ids=[alice.pk], kind=Notification.KIND_ASSIGNED,
            message=message, artifact_id=None, tenant_id=tenant.pk,
        )

    svc = NotificationService()
    assert svc.unread_count(ctx) == 2
    assert svc.mark_all_read(ctx) == 2
    assert svc.unread_count(ctx) == 0
