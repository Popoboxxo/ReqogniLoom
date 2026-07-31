"""
COMP-AT-001 AuthenticationService — tests.

Covers REQ-L3-AT001-001 (JWT validation), REQ-L3-AT001-002 (constant-time API-key
comparison + revocation) and REQ-L3-AT001-003 (lifecycle, format, max keys).
"""
from __future__ import annotations

import hmac
import time
from unittest import mock

import pytest

from auth_tenancy.context import AuthMethod
from auth_tenancy.errors import AuthenticationFailed
from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import MAX_ACTIVE_API_KEYS_PER_USER, ApiKey
from auth_tenancy.services.authentication import (
    AuthenticationService,
    generate_api_key_plaintext,
    hash_api_key,
)

_SECRET = "test-secret-not-a-real-key"


def _service() -> AuthenticationService:
    return AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer="reqflow", jwt_audience="reqflow-api"
    )


# -- REQ-L3-AT001-001 JWT ------------------------------------------------


def test_valid_jwt_produces_identity_claims():
    """Valid JWT -> IdentityClaims with bearer_token method."""
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "roles": ["editor"],
            "exp": int(time.time()) + 3600,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    claims = _service().validate_bearer_token(token)
    assert claims.auth_method is AuthMethod.BEARER_TOKEN
    assert claims.api_key_id is None
    assert "editor" in claims.roles


def test_expired_jwt_raises_token_expired():
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "exp": int(time.time()) - 10,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token(token)
    assert exc.value.code == "token_expired"


def test_invalid_signature_raises_invalid_signature():
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "exp": int(time.time()) + 3600,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        "WRONG-SECRET",
    )
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token(token)
    assert exc.value.code == "invalid_signature"


def test_malformed_jwt_raises_invalid_token():
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token("not.a.jwt.token")
    assert exc.value.code == "invalid_token"


# -- GitHub #135 refresh-token / access-token isolation ------------------


def _refresh_claims(**overrides):
    claims = {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "typ": "refresh",
        "exp": int(time.time()) + 3600,
        "iss": "reqflow",
        "aud": "reqflow-api",
    }
    claims.update(overrides)
    return claims


def test_refresh_token_rejected_by_validate_bearer_token():
    """A typ="refresh" token must never authenticate a normal request."""
    token = encode_hs256(_refresh_claims(), _SECRET)
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token(token)
    assert exc.value.code == "invalid_token"


def test_validate_refresh_token_accepts_valid_refresh_token():
    token = encode_hs256(_refresh_claims(), _SECRET)
    user_id, tenant_id = _service().validate_refresh_token(token)
    assert str(user_id) == "11111111-1111-1111-1111-111111111111"
    assert str(tenant_id) == "22222222-2222-2222-2222-222222222222"


def test_validate_refresh_token_rejects_access_token():
    """An access token (no typ, or typ="access") must not work as a refresh token."""
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "typ": "access",
            "exp": int(time.time()) + 3600,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_refresh_token(token)
    assert exc.value.code == "invalid_token"


def test_validate_refresh_token_rejects_expired_refresh_token():
    token = encode_hs256(_refresh_claims(exp=int(time.time()) - 10), _SECRET)
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_refresh_token(token)
    assert exc.value.code == "token_expired"


def test_alg_none_is_rejected():
    """A token claiming alg=none must not be accepted (REQ-L3-AT001-001)."""
    import base64
    import json

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'user_id': 'x'})}."
    with pytest.raises(AuthenticationFailed):
        _service().validate_bearer_token(forged)


def test_jwt_without_exp_is_rejected():
    """A token missing ``exp`` must never be accepted indefinitely (SYSTEM_AUDIT)."""
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "iss": "reqflow",
            "aud": "reqflow-api",
            # no "exp" claim
        },
        _SECRET,
    )
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token(token)
    assert exc.value.code == "invalid_token"


def test_jwt_with_future_nbf_is_rejected():
    """A token whose ``nbf`` (not-before) is still in the future is rejected."""
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "exp": int(time.time()) + 3600,
            "nbf": int(time.time()) + 1800,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_bearer_token(token)
    assert exc.value.code == "invalid_token"


def test_jwt_with_past_nbf_is_accepted():
    """A token whose ``nbf`` has already passed is accepted (sanity check)."""
    token = encode_hs256(
        {
            "user_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "exp": int(time.time()) + 3600,
            "nbf": int(time.time()) - 10,
            "iss": "reqflow",
            "aud": "reqflow-api",
        },
        _SECRET,
    )
    claims = _service().validate_bearer_token(token)
    assert claims.auth_method is AuthMethod.BEARER_TOKEN


# -- REQ-L3-AT001-002 API key ---------------------------------------------


@pytest.mark.django_db
def test_valid_api_key_resolves_user_and_tenant(user_a):
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        user=user_a, tenant=user_a.tenant, name="ci", key_hash=hash_api_key(plaintext)
    )
    claims = _service().validate_api_key(plaintext)
    assert claims.auth_method is AuthMethod.API_KEY
    assert claims.user_id == user_a.id
    assert claims.tenant_id == user_a.tenant_id
    assert claims.api_key_id is not None


@pytest.mark.django_db
def test_unknown_api_key_raises_invalid(user_a):
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_api_key("rf_doesnotexist0000000000000000000000000000")
    assert exc.value.code == "invalid_api_key"


@pytest.mark.django_db
def test_revoked_api_key_raises_revoked(user_a):
    plaintext = generate_api_key_plaintext()
    key = ApiKey.unscoped.create(
        user=user_a, tenant=user_a.tenant, name="ci", key_hash=hash_api_key(plaintext)
    )
    _service().revoke_api_key(api_key_id=key.id)
    with pytest.raises(AuthenticationFailed) as exc:
        _service().validate_api_key(plaintext)
    assert exc.value.code == "api_key_revoked"


@pytest.mark.django_db
def test_api_key_comparison_uses_compare_digest(user_a):
    """Verify constant-time comparison is actually invoked (REQ-L3-AT001-002)."""
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        user=user_a, tenant=user_a.tenant, name="ci", key_hash=hash_api_key(plaintext)
    )
    with mock.patch.object(
        hmac, "compare_digest", wraps=hmac.compare_digest
    ) as spy:
        _service().validate_api_key(plaintext)
    assert spy.called, "hmac.compare_digest must be used for key comparison"


@pytest.mark.django_db
def test_plaintext_key_never_persisted(user_a):
    """The DB must contain only the hash, never the plaintext (REQ-L3-AT001-002)."""
    result = _service().create_api_key(
        user_id=user_a.id, tenant_id=user_a.tenant_id, name="ci"
    )
    stored = ApiKey.unscoped.get(id=result.api_key_id)
    assert stored.key_hash.startswith("sha256:")
    assert result.plaintext not in stored.key_hash


# -- REQ-L3-AT001-003 lifecycle -------------------------------------------


def test_generated_key_format():
    key = generate_api_key_plaintext()
    assert key.startswith("reqlo_")
    assert len(key) == 46  # "reqlo_" + 40


@pytest.mark.django_db
def test_create_returns_plaintext_once(user_a):
    result = _service().create_api_key(
        user_id=user_a.id, tenant_id=user_a.tenant_id, name="ci"
    )
    assert result.plaintext.startswith("reqlo_")


@pytest.mark.django_db
def test_list_returns_metadata_only(user_a):
    svc = _service()
    svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="ci")
    listing = svc.list_api_keys(user_id=user_a.id)
    assert len(listing) == 1
    assert "id" in listing[0] and "name" in listing[0]
    assert "key_hash" not in listing[0]
    assert "plaintext" not in listing[0]


@pytest.mark.django_db
def test_max_active_keys_enforced(user_a):
    svc = _service()
    for _ in range(MAX_ACTIVE_API_KEYS_PER_USER):
        svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="k")
    with pytest.raises(ValueError):
        svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="overflow")
