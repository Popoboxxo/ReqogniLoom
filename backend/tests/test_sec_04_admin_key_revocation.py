"""SEC-04 regression tests: admin tenant scoping, key-material hiding and the
privileged API-key revocation command.

These tests pin the security contract of audit unit SEC-04
(``docs/audit/2026-09/review/plan/SECURITY_AUTHZ.md``) on top of ADR-011 and
ADR-013:

* a staff user of tenant A can neither list nor change tenant B's API keys in
  the Django admin;
* credential material (``ApiKey.key_hash`` / ``WebhookSubscription.secret``) is
  absent from the admin forms;
* the ``revoke_api_key`` management command is the ownership-independent,
  audited operator path, is idempotent and is dry-run by default;
* the REST/service self-scoped revocation is **not** weakened by the command.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory

from application.admin import WebhookSubscriptionAdmin
from application.models import WebhookSubscription
from audit.models import AuditEntry
from auth_tenancy.admin import ApiKeyAdmin
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(name="Sec04 A", slug="sec04-a", is_active=True)


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(name="Sec04 B", slug="sec04-b", is_active=True)


@pytest.fixture
def staff_a(db, tenant_a) -> User:
    """A staff (superuser) operator belonging to tenant A."""
    return User.objects.create(
        username="sec04-staff-a",
        email="sec04-staff-a@test.test",
        tenant=tenant_a,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def owner_b(db, tenant_b) -> User:
    """A key owner in tenant B — deliberately foreign to ``staff_a``."""
    return User.objects.create(
        username="sec04-owner-b",
        email="sec04-owner-b@test.test",
        tenant=tenant_b,
        is_active=True,
    )


def _make_key(*, tenant: Tenant, user: User, name: str, scope: str = "admin") -> ApiKey:
    return ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=name,
        key_hash=f"sha256:{uuid.uuid4().hex}{uuid.uuid4().hex[:32]}",
        scope=scope,
    )


def _admin_request(user: User):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


# ---------------------------------------------------------------------------
# (a) Admin tenant scoping
# ---------------------------------------------------------------------------


def test_staff_of_tenant_a_cannot_list_or_change_tenant_b_api_keys(
    staff_a: User, tenant_a: Tenant, tenant_b: Tenant, owner_b: User
) -> None:
    key_a = _make_key(tenant=tenant_a, user=staff_a, name="sec04-key-a")
    key_b = _make_key(tenant=tenant_b, user=owner_b, name="sec04-key-b")

    model_admin = ApiKeyAdmin(ApiKey, AdminSite())
    request = _admin_request(staff_a)

    visible_ids = {str(k.id) for k in model_admin.get_queryset(request)}
    assert str(key_a.id) in visible_ids
    assert str(key_b.id) not in visible_ids

    # Explicit per-object permission check, not just a filtered list.
    assert model_admin.has_view_permission(request, key_a) is True
    assert model_admin.has_change_permission(request, key_a) is True
    assert model_admin.has_view_permission(request, key_b) is False
    assert model_admin.has_change_permission(request, key_b) is False
    assert model_admin.has_delete_permission(request, key_b) is False


def test_admin_changelist_and_change_view_are_tenant_scoped(
    staff_a: User, tenant_a: Tenant, tenant_b: Tenant, owner_b: User
) -> None:
    key_a = _make_key(tenant=tenant_a, user=staff_a, name="sec04-visible-a")
    key_b = _make_key(tenant=tenant_b, user=owner_b, name="sec04-hidden-b")

    client = Client()
    client.force_login(staff_a)

    changelist = client.get("/admin/auth_tenancy/apikey/")
    assert changelist.status_code == 200
    body = changelist.content.decode()
    assert "sec04-visible-a" in body
    assert "sec04-hidden-b" not in body

    # Direct URL access to tenant B's change form must not resolve into a
    # change form: Django redirects to the admin index for an object it cannot
    # resolve from the tenant-scoped queryset (same shape as "does not exist").
    change = client.get(f"/admin/auth_tenancy/apikey/{key_b.id}/change/")
    assert change.status_code != 200
    assert change.status_code in (302, 404)
    if change.status_code == 302:
        assert change.url == "/admin/"
    # Tenant A's own row remains reachable.
    own_change = client.get(f"/admin/auth_tenancy/apikey/{key_a.id}/change/")
    assert own_change.status_code == 200


# ---------------------------------------------------------------------------
# (b) Key material absent from admin forms
# ---------------------------------------------------------------------------


def test_secret_and_key_hash_are_absent_from_admin_forms(staff_a: User) -> None:
    request = _admin_request(staff_a)

    webhook_admin = WebhookSubscriptionAdmin(WebhookSubscription, AdminSite())
    webhook_form = webhook_admin.get_form(request)
    assert "secret" not in webhook_form.base_fields
    assert "secret" not in webhook_admin.list_display
    assert webhook_admin.has_add_permission(request) is False

    key_admin = ApiKeyAdmin(ApiKey, AdminSite())
    key_form = key_admin.get_form(request)
    assert "key_hash" not in key_form.base_fields
    assert "key_hash" not in key_admin.list_display
    assert "key_hash" not in key_admin.search_fields
    assert key_admin.has_add_permission(request) is False


# ---------------------------------------------------------------------------
# (c)/(d)/(e) Privileged revocation command
# ---------------------------------------------------------------------------


def test_command_revokes_foreign_owner_key_and_audits(
    tenant_b: Tenant, owner_b: User, capsys
) -> None:
    key = _make_key(tenant=tenant_b, user=owner_b, name="sec04-foreign-admin", scope="admin")

    call_command(
        "revoke_api_key",
        "--key-id",
        str(key.id)[:8],
        "--reason",
        "SEC-04 privileged revocation test",
        "--apply",
    )
    out = capsys.readouterr().out

    revoked = ApiKey.unscoped.get(id=key.id)
    assert revoked.revoked_at is not None
    assert "Revoked API key" in out

    entries = list(
        AuditEntry.unscoped.filter(entity_type="ApiKey", entity_id=key.id)
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.op == AuditEntry.OP_DELETE
    assert entry.change_reason == "SEC-04 privileged revocation test"
    assert entry.tenant_id == tenant_b.id
    assert entry.details["owner_user_id"] == str(owner_b.id)
    assert entry.details["scope"] == "admin"
    # No secret material in the audit payload.
    assert "key_hash" not in entry.details


def test_command_is_idempotent(tenant_b: Tenant, owner_b: User, capsys) -> None:
    key = _make_key(tenant=tenant_b, user=owner_b, name="sec04-idempotent")

    call_command(
        "revoke_api_key", "--key-id", str(key.id), "--reason", "first", "--apply"
    )
    capsys.readouterr()
    first_revoked_at = ApiKey.unscoped.get(id=key.id).revoked_at
    audit_count = AuditEntry.unscoped.filter(
        entity_type="ApiKey", entity_id=key.id
    ).count()
    assert audit_count == 1

    call_command(
        "revoke_api_key", "--key-id", str(key.id), "--reason", "second", "--apply"
    )
    out = capsys.readouterr().out

    second_revoked_at = ApiKey.unscoped.get(id=key.id).revoked_at
    assert second_revoked_at == first_revoked_at
    assert (
        AuditEntry.unscoped.filter(entity_type="ApiKey", entity_id=key.id).count() == 1
    )
    assert "already revoked" in out


def test_command_is_dry_run_by_default(tenant_b: Tenant, owner_b: User, capsys) -> None:
    key = _make_key(tenant=tenant_b, user=owner_b, name="sec04-dry-run")

    call_command("revoke_api_key", "--key-id", str(key.id)[:8], "--reason", "preview")
    out = capsys.readouterr().out

    assert ApiKey.unscoped.get(id=key.id).revoked_at is None
    assert (
        AuditEntry.unscoped.filter(entity_type="ApiKey", entity_id=key.id).count() == 0
    )
    assert "Dry run" in out


def test_command_rejects_short_prefix(tenant_b: Tenant, owner_b: User) -> None:
    _make_key(tenant=tenant_b, user=owner_b, name="sec04-short-prefix")

    with pytest.raises(CommandError):
        call_command("revoke_api_key", "--key-id", "abcd", "--reason", "too short")


def test_rest_self_scoped_revocation_is_not_weakened(
    tenant_b: Tenant, owner_b: User, staff_a: User
) -> None:
    """The privileged command must not have changed the owner-scoped service."""
    key = _make_key(tenant=tenant_b, user=owner_b, name="sec04-foreign-guard")

    with pytest.raises(AuthenticationFailed):
        AuthenticationService().revoke_api_key(api_key_id=key.id, user_id=staff_a.id)

    assert ApiKey.unscoped.get(id=key.id).revoked_at is None
