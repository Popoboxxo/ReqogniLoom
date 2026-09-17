"""SA-34 regression tests — peppered API-key hashes.

SYSTEMAUDIT-2026-08-27 §4.6 F11: API keys were stored as a bare SHA-256 digest.
The keys are 40 random characters, so that was never brute-forceable — but it
also gave no protection against *offline* testing of candidate keys by someone
holding a database dump. A server-side pepper (kept in the environment, never in
a column) closes that.

The rollout constraint is the interesting part and is pinned explicitly below:
existing rows cannot be re-hashed (the plaintext is gone by design), so old and
new keys must coexist and both must authenticate.
"""
from __future__ import annotations

import pytest
from django.test import override_settings

from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import (
    AuthenticationService,
    api_key_hash_candidates,
    hash_api_key,
    hash_api_key_legacy,
)

_PEPPER = "test-pepper-not-a-real-secret"


# ---------------------------------------------------------------------------
# Hash format
# ---------------------------------------------------------------------------


@override_settings(API_KEY_PEPPER="")
def test_without_pepper_the_legacy_format_is_produced():
    plaintext = "reqlo_abc"
    assert hash_api_key(plaintext) == hash_api_key_legacy(plaintext)
    assert hash_api_key(plaintext).startswith("sha256:")


@override_settings(API_KEY_PEPPER=_PEPPER)
def test_with_pepper_a_versioned_format_is_produced():
    plaintext = "reqlo_abc"
    peppered = hash_api_key(plaintext)

    assert peppered.startswith("sha256p1:")
    assert peppered != hash_api_key_legacy(plaintext)
    # Must fit the column (ApiKey.key_hash is CharField(max_length=80)).
    assert len(peppered) <= 80


@override_settings(API_KEY_PEPPER=_PEPPER)
def test_pepper_actually_keys_the_digest():
    """A different pepper must yield a different hash — otherwise it is decoration."""
    with_a = hash_api_key("reqlo_abc")
    with override_settings(API_KEY_PEPPER="a-completely-different-pepper"):
        with_b = hash_api_key("reqlo_abc")
    assert with_a != with_b


@override_settings(API_KEY_PEPPER=_PEPPER)
def test_candidates_cover_both_formats():
    candidates = api_key_hash_candidates("reqlo_abc")
    assert candidates == (hash_api_key("reqlo_abc"), hash_api_key_legacy("reqlo_abc"))


@override_settings(API_KEY_PEPPER="")
def test_candidates_collapse_to_one_without_a_pepper():
    assert api_key_hash_candidates("reqlo_abc") == (hash_api_key_legacy("reqlo_abc"),)


# ---------------------------------------------------------------------------
# Authentication against a mixed fleet
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db, tenant_a):
    from persistence.models import User

    return User.objects.create(
        username="pepperuser", email="pepper@a.test", tenant=tenant_a
    )


@override_settings(API_KEY_PEPPER=_PEPPER)
@pytest.mark.django_db
def test_new_keys_are_stored_peppered(user):
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=user.tenant_id, name="new"
    )
    row = ApiKey.unscoped.get(id=result.api_key_id)
    assert row.key_hash.startswith("sha256p1:")
    # And the plaintext still authenticates.
    claims = AuthenticationService().validate_api_key(result.plaintext)
    assert claims.user_id == user.id


@override_settings(API_KEY_PEPPER=_PEPPER)
@pytest.mark.django_db
def test_pre_pepper_keys_keep_working(user):
    """The rollout is non-breaking: old rows cannot be re-hashed, so they must
    keep authenticating until they are rotated."""
    plaintext = "reqlo_legacy_key_issued_before_the_pepper"
    ApiKey.unscoped.create(
        user=user,
        tenant=user.tenant,
        name="legacy",
        key_hash=hash_api_key_legacy(plaintext),
    )

    claims = AuthenticationService().validate_api_key(plaintext)
    assert claims.user_id == user.id


@override_settings(API_KEY_PEPPER=_PEPPER)
@pytest.mark.django_db
def test_wrong_key_is_still_rejected(user):
    AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=user.tenant_id, name="k"
    )
    with pytest.raises(AuthenticationFailed):
        AuthenticationService().validate_api_key("reqlo_not_a_real_key")


@pytest.mark.django_db
def test_rotating_the_pepper_invalidates_peppered_keys(user):
    """Documented consequence: changing API_KEY_PEPPER is a forced key rotation.

    Legacy (unpeppered) rows are unaffected, which is exactly why they survive
    the rollout — and exactly why they must eventually be rotated away.
    """
    with override_settings(API_KEY_PEPPER=_PEPPER):
        result = AuthenticationService().create_api_key(
            user_id=user.id, tenant_id=user.tenant_id, name="k"
        )

    with override_settings(API_KEY_PEPPER="rotated-pepper"):
        with pytest.raises(AuthenticationFailed):
            AuthenticationService().validate_api_key(result.plaintext)
