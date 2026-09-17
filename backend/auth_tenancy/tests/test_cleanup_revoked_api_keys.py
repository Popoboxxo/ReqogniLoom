"""
Tests for the ``cleanup_revoked_api_keys`` management command (#606).

Revoked ApiKey rows are never deleted, only marked ``revoked_at`` — this
command purges rows revoked more than N days ago, dry-run by default.
"""
from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from auth_tenancy.models import ApiKey
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant_and_user():
    tenant = Tenant.objects.create(name="Cleanup T", slug="cleanup-t", is_active=True)
    user = User.objects.create(username="cleanupuser", email="cu@t.test", tenant=tenant)
    set_request_tenant(tenant.id)
    try:
        yield tenant, user
    finally:
        clear_request_tenant()


def _make_key(tenant, user, *, revoked_days_ago: int | None) -> ApiKey:
    revoked_at = (
        timezone.now() - timedelta(days=revoked_days_ago)
        if revoked_days_ago is not None
        else None
    )
    return ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="k",
        key_hash=f"sha256:{revoked_days_ago}{'-active' if revoked_at is None else ''}"
        + ("x" * 50),
        revoked_at=revoked_at,
    )


def test_dry_run_reports_but_does_not_delete(tenant_and_user):
    tenant, user = tenant_and_user
    _make_key(tenant, user, revoked_days_ago=60)
    _make_key(tenant, user, revoked_days_ago=None)  # active — never a candidate

    out = io.StringIO()
    call_command("cleanup_revoked_api_keys", stdout=out)

    assert "1 revoked API key" in out.getvalue()
    assert ApiKey.unscoped.count() == 2, "dry-run must not delete anything"


def test_apply_deletes_only_keys_older_than_threshold(tenant_and_user):
    tenant, user = tenant_and_user
    old_key = _make_key(tenant, user, revoked_days_ago=60)
    recent_key = _make_key(tenant, user, revoked_days_ago=5)
    active_key = _make_key(tenant, user, revoked_days_ago=None)

    out = io.StringIO()
    call_command(
        "cleanup_revoked_api_keys", "--apply", "--older-than-days=30", stdout=out
    )

    remaining_ids = set(ApiKey.unscoped.values_list("id", flat=True))
    assert old_key.id not in remaining_ids
    assert recent_key.id in remaining_ids
    assert active_key.id in remaining_ids
    assert "Deleted 1" in out.getvalue()


def test_custom_threshold_is_respected(tenant_and_user):
    tenant, user = tenant_and_user
    _make_key(tenant, user, revoked_days_ago=10)

    out = io.StringIO()
    call_command(
        "cleanup_revoked_api_keys", "--apply", "--older-than-days=7", stdout=out
    )

    assert ApiKey.unscoped.count() == 0
