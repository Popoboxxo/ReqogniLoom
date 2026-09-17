"""Regression test for #36: API responses must honour Accept-Language (DE/EN).

Before this fix, ``django.middleware.locale.LocaleMiddleware`` was not
installed, so ``request.LANGUAGE_CODE`` was never activated from the
``Accept-Language`` header. Two message sources were affected:

1. DRF's own field-level validation messages (``ErrorDetail`` values wrapped
   in ``gettext_lazy`` inside ``rest_framework``, e.g. "This field is
   required.") — these only translate once Django activates the request's
   language via ``django.utils.translation.activate()``, which
   ``LocaleMiddleware`` does.
2. The project's own DE/EN catalog (``rest_api.serializers.detect_lang`` /
   ``build_error_response``) — already worked independently of
   ``LocaleMiddleware`` (it reads ``Accept-Language`` itself), so this test
   also pins that it keeps working alongside the middleware fix.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace


@pytest.fixture
def authed_client(db):
    """An APIClient authenticated as an admin user with a JWT bearer token."""
    tenant = Tenant.objects.create(name="Locale T", slug="locale-t", is_active=True)
    user = User.objects.create(
        username="localeadmin", email="localeadmin@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": "localeadmin", "password": "hunter2pass"},
        format="json",
    )
    assert login.status_code == 200, login.content
    token = login.json()["token"]
    authed = APIClient()
    authed.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return authed


@pytest.mark.django_db
def test_drf_field_validation_error_translated_to_german(authed_client):
    """#36: a missing-required-field DRF validation error is in German
    when the caller sends ``Accept-Language: de``."""
    resp = authed_client.post(
        "/api/v1/issues/",
        {},
        format="json",
        HTTP_ACCEPT_LANGUAGE="de-DE,de;q=0.9",
    )
    assert resp.status_code == 400
    body = resp.json()
    field_errors = {
        item["field"]: item["errors"] for item in body["error"]["details"]
    }
    assert any(
        "erforderlich" in msg
        for errors in field_errors.values()
        for msg in errors
    ), f"Expected a German field error, got: {field_errors}"


@pytest.mark.django_db
def test_drf_field_validation_error_stays_english_by_default(authed_client):
    """Same request without a German Accept-Language stays in English."""
    resp = authed_client.post(
        "/api/v1/issues/",
        {},
        format="json",
        HTTP_ACCEPT_LANGUAGE="en-US",
    )
    assert resp.status_code == 400
    body = resp.json()
    field_errors = {
        item["field"]: item["errors"] for item in body["error"]["details"]
    }
    assert any(
        "required" in msg
        for errors in field_errors.values()
        for msg in errors
    ), f"Expected an English field error, got: {field_errors}"


@pytest.mark.django_db
def test_custom_error_catalog_still_translates_top_level_message(authed_client):
    """The project's own DE/EN catalog (build_error_response) keeps working
    alongside LocaleMiddleware — it reads Accept-Language independently."""
    resp = authed_client.post(
        "/api/v1/issues/",
        {},
        format="json",
        HTTP_ACCEPT_LANGUAGE="de",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["message"] == "Validierung fehlgeschlagen."
