"""REST surface for the caller's own display preference (Issue #1096).

``GET``/``PATCH`` ``/api/v1/users/me/display-preferences/``.

The view is invoked through ``APIRequestFactory`` with a real ``AuthContext``
whose ``auth_method`` is ``AuthMethod.BEARER_TOKEN`` — the same context a JWT
login mints (``auth_tenancy.rest.AuthTenancyAuthentication``), matching the
sibling ``test_notification_preference_views.py`` / ``test_theme_preference_rest.py``
patterns.

The real ``DisplayPreferenceService`` runs against the database on purpose:
the round-trip and tenant-isolation cases assert the stored row, so a mocked
service would test nothing.

NOTE: the table ships in ``auth_tenancy/migrations/0019_userdisplaypreference.py``
(authored, pending human approval — see the hand-off report). Run these with the
migration applied once approved.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory

from application.display_preference_service import DisplayPreferenceService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import UserDisplayPreference
from persistence.errors import ValidationError
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext
from rest_api.display_preference_views import DisplayPreferenceView

pytestmark = pytest.mark.django_db

_URL = "/api/v1/users/me/display-preferences/"


@pytest.fixture
def factory() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        name="DisplayPref T", slug=f"displaypref-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(
        username=f"displaypref-{uuid.uuid4().hex[:6]}",
        email=f"displaypref-{uuid.uuid4().hex[:6]}@t.test",
        tenant=tenant,
    )


@pytest.fixture
def ctx(tenant: Tenant, user: User) -> AuthContext:
    """A real ``AuthContext`` for *user*, tenant context active for the test.

    ``UserDisplayPreference`` is a ``TenantScopedModel``: its default ``.objects``
    manager raises ``TenantContextNotSetError`` until a tenant is active, exactly
    as it would before the request lifecycle sets it
    (``AuthAndTenancyAuthentication`` / ``ServiceBase._set_tenant_context``). A
    real authenticated request always runs with the tenant context established, so
    the fixture mirrors that (Issue #1096 regression guard); teardown clears it.
    """
    context = AuthContext(
        user_id=user.pk,
        tenant_id=tenant.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    TenantContext.set_tenant(tenant.pk)
    yield context
    TenantContext.clear_tenant()


def _authed_ctx(request, ctx):
    """Attach the auth context the permission layer reads during ``initial()``."""
    request.auth_context = ctx
    return request


def _call(request):
    """Dispatch *request* with ``get_auth_context`` bound to its own context."""
    with patch(
        "rest_api.display_preference_views.get_auth_context",
        return_value=request.auth_context,
    ):
        return DisplayPreferenceView.as_view()(request)


# (a) GET with no row -> 200, server default, GET creates no row
def test_get_with_no_row_returns_server_default(factory, ctx) -> None:
    """(a) The default comes from the server and a read never materialises it."""
    assert not UserDisplayPreference.objects.exists()

    response = _call(_authed_ctx(factory.get(_URL), ctx))

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": True}
    assert not UserDisplayPreference.objects.exists()


# (b) PATCH false -> stored, returned, row created
def test_patch_false_persists_and_creates_a_row(factory, ctx, user) -> None:
    """(b) The write reaches the DB, not just the response."""
    request = _authed_ctx(
        factory.patch(_URL, {"show_readable_ids": False}, format="json"), ctx
    )

    response = _call(request)

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": False}

    row = UserDisplayPreference.unscoped.get(user_id=user.pk)
    assert row.show_readable_ids is False


# (c) PATCH true -> flips back, still exactly one row
def test_patch_true_re_enables_without_a_duplicate_row(factory, ctx, user) -> None:
    """(c) Re-enabling does not add a second row."""
    _call(
        _authed_ctx(
            factory.patch(_URL, {"show_readable_ids": False}, format="json"), ctx
        )
    )
    response = _call(
        _authed_ctx(
            factory.patch(_URL, {"show_readable_ids": True}, format="json"), ctx
        )
    )

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": True}
    assert UserDisplayPreference.unscoped.filter(user_id=user.pk).count() == 1
    assert UserDisplayPreference.unscoped.get(user_id=user.pk).show_readable_ids is True


# (d) the value survives a fresh session / device (the acceptance criterion)
def test_toggle_survives_a_new_session(factory, ctx, user, tenant) -> None:
    """(d) A second, independent request sees the persisted value."""
    _call(
        _authed_ctx(
            factory.patch(_URL, {"show_readable_ids": False}, format="json"), ctx
        )
    )

    # A brand-new context for the same account (new browser/device, same user).
    fresh_ctx = AuthContext(
        user_id=user.pk,
        tenant_id=tenant.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    response = _call(_authed_ctx(factory.get(_URL), fresh_ctx))

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": False}


# (e) an unknown key is rejected by the serializer, not silently stored
def test_patch_rejects_an_unknown_key(factory, ctx) -> None:
    """(e) The closed vocabulary is enforced before the service is reached (#851)."""
    request = _authed_ctx(
        factory.patch(_URL, {"readable_ids": False}, format="json"), ctx
    )

    response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["details"][0]["field"] == "readable_ids"


# (f) a non-bool value is rejected
def test_patch_rejects_a_non_bool_value(factory, ctx) -> None:
    """(f) ``"maybe"`` is a value ``BooleanField`` genuinely rejects."""
    request = _authed_ctx(
        factory.patch(_URL, {"show_readable_ids": "maybe"}, format="json"), ctx
    )

    response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


# (g) an empty PATCH body is a read-only no-op
def test_patch_with_empty_body_is_a_noop(factory, ctx) -> None:
    """(g) No flag named -> current values returned, no row created."""
    request = _authed_ctx(factory.patch(_URL, {}, format="json"), ctx)

    response = _call(request)

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": True}
    assert not UserDisplayPreference.objects.exists()


# (h) unauthenticated GET and PATCH -> 401
def test_unauthenticated_get_and_patch_are_401(factory) -> None:
    """(h) ``HasOperationPermission`` rejects before either handler runs."""
    assert DisplayPreferenceView.as_view()(factory.get(_URL)).status_code == 401

    patch_request = factory.patch(
        _URL, {"show_readable_ids": False}, format="json"
    )
    assert DisplayPreferenceView.as_view()(patch_request).status_code == 401


# (i) another account's / tenant's value is not disclosed
def test_no_row_is_content_independent_for_another_account(factory, ctx) -> None:
    """(i) The row is keyed by ``ctx.user_id``; a different caller sees the default."""
    other_tenant = Tenant.objects.create(
        name="DisplayPref Other", slug=f"displaypref-other-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    other_user = User.objects.create(
        username=f"displaypref-other-{uuid.uuid4().hex[:6]}",
        email=f"displaypref-other-{uuid.uuid4().hex[:6]}@t.test",
        tenant=other_tenant,
    )
    _call(
        _authed_ctx(
            factory.patch(_URL, {"show_readable_ids": False}, format="json"), ctx
        )
    )
    assert UserDisplayPreference.unscoped.get(user_id=ctx.user_id).show_readable_ids is False

    other_ctx = AuthContext(
        user_id=other_user.pk,
        tenant_id=other_tenant.pk,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    response = _call(_authed_ctx(factory.get(_URL), other_ctx))

    assert response.status_code == 200
    assert response.data == {"show_readable_ids": True}
    TenantContext.clear_tenant()


# (j) a service-raised ValidationError is translated to a 400 envelope
def test_service_validation_error_maps_to_400(factory, ctx) -> None:
    """(j) The service's ``ValidationError`` is not a 500."""
    exc = ValidationError("show_readable_ids cannot be changed right now")

    request = _authed_ctx(
        factory.patch(_URL, {"show_readable_ids": False}, format="json"), ctx
    )
    with patch.object(
        DisplayPreferenceService, "update_display_preferences", side_effect=exc
    ):
        response = _call(request)

    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"
    assert response.data["error"]["message"] == str(exc)
