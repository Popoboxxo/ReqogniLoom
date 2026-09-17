"""
Django admin login tests for persistence.User (REQ-L1-010).

Verifies that the custom User model works as AUTH_USER_MODEL for Django admin:
- staff users can log in to /admin/
- non-staff users are rejected
- the admin index page is accessible after login
- password hashing round-trips correctly via set_password/check_password
"""
from __future__ import annotations

import pytest
from django.test import Client

from persistence.models import Tenant, User


@pytest.fixture
def staff_user(db) -> User:
    """An active staff+superuser for admin login tests."""
    tenant = Tenant.objects.create(name="Admin T", slug="admin-t", is_active=True)
    user = User.objects.create(
        username="staffadmin",
        email="staff@admin.test",
        tenant=tenant,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password("staffpass123")
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def regular_user(db) -> User:
    """An active user WITHOUT staff privileges."""
    tenant = Tenant.objects.create(name="Regular T", slug="regular-t", is_active=True)
    user = User.objects.create(
        username="regular",
        email="regular@test.test",
        tenant=tenant,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_password("regularpass")
    user.save(update_fields=["password"])
    return user


@pytest.mark.django_db
def test_staff_user_can_login_to_admin(staff_user: User) -> None:
    """A user with is_staff=True can authenticate via the Django admin login."""
    client = Client()
    response = client.post(
        "/admin/login/?next=/admin/",
        {"username": "staffadmin", "password": "staffpass123"},
    )
    # Successful admin login redirects to /admin/ (302).
    assert response.status_code == 302
    assert response.url in ("/admin/", "/admin")


@pytest.mark.django_db
def test_non_staff_user_rejected_from_admin(regular_user: User) -> None:
    """A user without is_staff cannot log in to the admin site."""
    client = Client()
    response = client.post(
        "/admin/login/",
        {"username": "regular", "password": "regularpass"},
    )
    # Failed login re-renders the login form (200) with an error.
    assert response.status_code == 200
    assert b"Please enter the correct username and password" in response.content


@pytest.mark.django_db
def test_admin_index_accessible_after_login(staff_user: User) -> None:
    """After login, the admin index page loads successfully."""
    client = Client()
    assert client.login(username="staffadmin", password="staffpass123")
    response = client.get("/admin/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_wrong_password_rejected(staff_user: User) -> None:
    """Wrong password is rejected at admin login."""
    client = Client()
    response = client.post(
        "/admin/login/",
        {"username": "staffadmin", "password": "wrongpassword"},
    )
    assert response.status_code == 200
    assert b"Please enter the correct username and password" in response.content


@pytest.mark.django_db
def test_user_check_password_roundtrip(db: None) -> None:
    """set_password + check_password round-trips correctly."""
    user = User(username="pwtest", email="pw@test.test")
    user.set_password("mysecretpw")
    assert user.check_password("mysecretpw")
    assert not user.check_password("wrongpw")


@pytest.mark.django_db
def test_user_auth_interface_properties(db: None) -> None:
    """is_authenticated, is_anonymous, has_perm, has_module_perms work."""
    superuser = User(
        username="su",
        email="su@test.test",
        is_superuser=True,
        is_active=True,
    )
    assert superuser.is_authenticated
    assert not superuser.is_anonymous
    assert superuser.has_perm("some.perm")
    assert superuser.has_module_perms("someapp")

    regular = User(
        username="reg",
        email="reg@test.test",
        is_superuser=False,
        is_active=True,
    )
    assert regular.is_authenticated
    assert not regular.has_perm("some.perm")
    assert not regular.has_module_perms("someapp")


# -- Session auth hash -------------------------------------------------------
#
# ``User`` implements the Django auth interface by hand rather than inheriting
# ``AbstractBaseUser``. Django 5.2 skipped session-hash verification entirely
# when the model did not provide ``get_session_auth_hash`` (a
# ``RemovedInDjango61Warning`` shim); 6.1 calls it unconditionally. These tests
# pin both halves: that the methods exist at all (otherwise every session login
# raises AttributeError on >=6.1) and that they carry real security semantics —
# returning a constant such as "" would keep login working while silently
# reintroducing "session survives a password change".


@pytest.mark.django_db
def test_session_auth_hash_is_a_stable_sha256_digest(staff_user: User) -> None:
    """get_session_auth_hash returns a stable sha256 hexdigest, not a stub."""
    digest = staff_user.get_session_auth_hash()

    assert len(digest) == 64, "expected a sha256 hexdigest"
    assert int(digest, 16) >= 0, "expected hex characters only"
    # Deterministic for an unchanged password — session verification depends on
    # it matching on every subsequent request.
    assert digest == staff_user.get_session_auth_hash()


@pytest.mark.django_db
def test_password_change_invalidates_existing_session(staff_user: User) -> None:
    """Changing the password logs out that user's existing sessions."""
    client = Client()
    assert client.login(username="staffadmin", password="staffpass123")
    assert client.get("/admin/").status_code == 200

    hash_before = staff_user.get_session_auth_hash()
    staff_user.set_password("a-completely-new-password")
    staff_user.save(update_fields=["password"])

    assert staff_user.get_session_auth_hash() != hash_before

    # The still-open session must no longer authenticate: AuthenticationMiddleware
    # compares the stored hash, fails, and flushes the session — so /admin/
    # redirects to the login page instead of returning 200.
    assert client.get("/admin/").status_code != 200


@pytest.mark.django_db
def test_session_auth_fallback_hash_follows_secret_key_fallbacks(
    staff_user: User, settings
) -> None:
    """One fallback hash is yielded per SECRET_KEY_FALLBACKS entry.

    ``django.contrib.auth.get_user()`` uses these so that rotating SECRET_KEY
    does not invalidate every session at once.
    """
    settings.SECRET_KEY_FALLBACKS = ["previous-secret-1", "previous-secret-2"]

    fallbacks = list(staff_user.get_session_auth_fallback_hash())

    assert len(fallbacks) == 2
    assert len(set(fallbacks)) == 2, "each fallback secret yields a distinct hash"
    assert staff_user.get_session_auth_hash() not in fallbacks
