"""REST surface for the caller's own notification preference (OD-1, Task 28).

``GET``/``PATCH`` ``/api/v1/users/me/notification-preferences/``.

The view is invoked through ``APIRequestFactory`` with a real ``AuthContext``
whose ``auth_method`` is ``AuthMethod.BEARER_TOKEN`` — the same context a JWT
login mints (``auth_tenancy.rest.AuthTenancyAuthentication``). Same pattern as
``test_comment_endpoints.py`` / ``test_notification_endpoints.py``, the two
REST view tests of this same plan.

The real ``NotificationPreferenceService`` runs against the database on
purpose: cases (b)/(c) assert the stored ``disabled_triggers`` row, so a mocked
service would test nothing.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from application.notification_preference_service import (
    ALL_KINDS,
    NotificationPreferenceService,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import UserNotificationPreference
from persistence.errors import ValidationError
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext
from rest_api.notification_preference_views import NotificationPreferenceView

pytestmark = pytest.mark.django_db

_URL = "/api/v1/users/me/notification-preferences/"

#: The four switches, spelled out so the wire contract is explicit rather than
#: only implied by ``ALL_KINDS`` (spec §6: the vocabulary is closed at four).
_KINDS = ("assigned", "comment_added", "transition_pending", "suspect_flagged")

_ALL_ENABLED = {kind: True for kind in _KINDS}


@pytest.fixture
def factory() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        name="NotifPref T", slug=f"notifpref-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username=f"notifpref-{uuid.uuid4().hex[:6]}",
        email=f"notifpref-{uuid.uuid4().hex[:6]}@t.test",
        tenant=tenant,
    )


@pytest.fixture
def ctx(tenant: Tenant, user: User):
    """A real ``AuthContext`` for *user*, with the tenant context cleaned up."""
    context = AuthContext(
        user_id=user.pk,
        tenant_id=tenant.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    yield context
    TenantContext.clear_tenant()


def _authed_ctx(request, ctx):
    """Attach the auth context the permission layer reads during ``initial()``."""
    request.auth_context = ctx
    return request


def _call(request):
    """Dispatch *request* with ``get_auth_context`` bound to its own context."""
    with patch(
        "rest_api.notification_preference_views.get_auth_context",
        return_value=request.auth_context,
    ):
        return NotificationPreferenceView.as_view()(request)


# (a) GET with no row -> 200, all four kinds enabled
def test_get_with_no_row_returns_all_kinds_enabled(factory, ctx) -> None:
    """(a) The effective map is all-``True`` and GET creates no row."""
    assert not UserNotificationPreference.objects.exists()

    response = _call(_authed_ctx(factory.get(_URL), ctx))

    assert response.status_code == 200
    assert response.data["preferences"] == _ALL_ENABLED
    assert set(response.data["preferences"]) == set(ALL_KINDS)
    assert not UserNotificationPreference.objects.exists()


# (b) PATCH one kind false -> only that kind flips, a row appears
def test_patch_disables_one_kind_and_creates_a_row(factory, ctx, user) -> None:
    """(b) Partial update; the stored row keeps exactly the disabled kind."""
    request = _authed_ctx(
        factory.patch(_URL, {"preferences": {"comment_added": False}}, format="json"),
        ctx,
    )

    response = _call(request)

    assert response.status_code == 200
    preferences = response.data["preferences"]
    assert preferences["comment_added"] is False
    assert {k: v for k, v in preferences.items() if k != "comment_added"} == {
        "assigned": True,
        "transition_pending": True,
        "suspect_flagged": True,
    }

    # NOTE: ``UserNotificationPreference`` is a plain ``AuditableModel`` with no
    # ``tenant`` column (OD-1/A1), so it has no ``.unscoped`` escape hatch — a
    # plain ``.objects`` lookup already returns the caller's own row.
    row = UserNotificationPreference.objects.get(user_id=user.pk)
    assert row.disabled_triggers == ["comment_added"]


# (c) PATCH the same kind back -> flips back, still exactly one row
def test_patch_re_enables_without_a_duplicate_row(factory, ctx, user) -> None:
    """(c) Re-enabling returns to all-``True`` and does not add a second row."""
    _call(
        _authed_ctx(
            factory.patch(_URL, {"preferences": {"comment_added": False}}, format="json"),
            ctx,
        )
    )
    response = _call(
        _authed_ctx(
            factory.patch(_URL, {"preferences": {"comment_added": True}}, format="json"),
            ctx,
        )
    )

    assert response.status_code == 200
    assert response.data["preferences"] == _ALL_ENABLED

    assert UserNotificationPreference.objects.filter(user_id=user.pk).count() == 1
    row = UserNotificationPreference.objects.get(user_id=user.pk)
    assert row.disabled_triggers == []


# (d) an unknown kind is rejected by the serializer, not silently stored
def test_patch_rejects_an_unknown_kind(factory, ctx) -> None:
    """(d) The closed vocabulary is enforced before the service is reached."""
    request = _authed_ctx(
        factory.patch(_URL, {"preferences": {"not_a_kind": False}}, format="json"), ctx
    )

    response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


# (e) a non-bool value is rejected
def test_patch_rejects_a_non_bool_value(factory, ctx) -> None:
    """(e) Deviation from the plan's literal: ``"yes"`` is in DRF
    ``BooleanField.TRUE_VALUES`` and coerces to ``True`` instead of failing, so
    ``"maybe"`` — a value ``BooleanField`` genuinely rejects — is used here.
    The field was deliberately not weakened to make the literal pass."""
    request = _authed_ctx(
        factory.patch(_URL, {"preferences": {"assigned": "maybe"}}, format="json"), ctx
    )

    response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


# (f) unauthenticated GET and PATCH -> 401
def test_unauthenticated_get_and_patch_are_401(factory) -> None:
    """(f) ``HasOperationPermission`` rejects before either handler runs."""
    assert NotificationPreferenceView.as_view()(factory.get(_URL)).status_code == 401

    patch_request = factory.patch(
        _URL, {"preferences": {"assigned": False}}, format="json"
    )
    assert NotificationPreferenceView.as_view()(patch_request).status_code == 401


# (g) a service-raised ValidationError is translated to a 400 envelope
def test_service_validation_error_maps_to_400(factory, ctx) -> None:
    """(g) The service's ``ValidationError`` is not a 500."""
    exc = ValidationError("assigned cannot be changed right now")

    request = _authed_ctx(
        factory.patch(_URL, {"preferences": {"assigned": False}}, format="json"), ctx
    )
    with patch.object(
        NotificationPreferenceService, "update_preferences", side_effect=exc
    ):
        response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["message"] == str(exc)
