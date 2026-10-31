"""``amr`` claim round-trip (issue #1308, Plan E / WP E3.3).

The ``amr`` (authentication method reference, RFC 8176) claim is what lets a
downstream consumer tell a password-only session from one that also proved a
second factor. Three properties must hold, and each one is a property a refactor
could silently drop:

1. **Issuance** — ``issue_token`` / ``issue_refresh_token`` write the claim, and
   the default is ``("pwd",)`` so every existing caller keeps its meaning.
2. **Round-trip** — the validator turns the claim back into
   ``IdentityClaims.amr`` / ``AuthContext.amr`` without changing any other claim.
3. **Backward compatibility** — a token minted *before* the claim existed reads
   as ``("pwd",)``, never as ``()``: reporting an empty ``amr`` would make a
   valid old session look like an API key to the second-factor gates.
"""
from __future__ import annotations

import time
from uuid import UUID

import pytest

from auth_tenancy.context import AuthMethod, IdentityClaims, TenantContext
from auth_tenancy.jwt_tokens import decode_jwt, encode_hs256
from auth_tenancy.services import AuthenticationService, PasswordAuthenticationService
from auth_tenancy.services.tenant_context import TenantContextService
from persistence.models import User

_SECRET = "test-secret-not-a-real-key"
_ISSUER = "reqflow"
_AUDIENCE = "reqflow-api"


def _issuer() -> PasswordAuthenticationService:
    return PasswordAuthenticationService(
        jwt_secret=_SECRET,
        jwt_issuer=_ISSUER,
        jwt_audience=_AUDIENCE,
        token_ttl_seconds=3600,
    )


def _validator() -> AuthenticationService:
    return AuthenticationService(
        jwt_secret=_SECRET, jwt_issuer=_ISSUER, jwt_audience=_AUDIENCE
    )


def _claims(token: str) -> dict:
    return decode_jwt(token, secret=_SECRET, issuer=_ISSUER, audience=_AUDIENCE)


@pytest.fixture
def user(tenant_a) -> User:
    row = User.objects.create(
        username="amr-user", email="amr@a.test", tenant=tenant_a
    )
    row.set_password("pw")
    row.save(update_fields=["password"])
    return row


def _legacy_token(user: User, *, typ: str) -> str:
    """Mint a token the way the pre-E3.3 code did — without an ``amr`` claim."""
    now = int(time.time())
    claims: dict[str, object] = {
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "typ": typ,
        "iat": now,
        "exp": now + 3600,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
    }
    if typ == "access":
        claims["roles"] = ["editor"]
    else:
        claims["jti"] = "11111111-1111-1111-1111-111111111111"
        claims["sid"] = "22222222-2222-2222-2222-222222222222"
    return encode_hs256(claims, _SECRET)


# ---------------------------------------------------------------------------
# 1. Issuance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_access_token_defaults_to_pwd(user) -> None:
    token = _issuer().issue_token(user, ())

    assert _claims(token)["amr"] == ["pwd"]
    assert _validator().validate_bearer_token(token).amr == ("pwd",)


@pytest.mark.django_db
def test_access_token_carries_the_second_factor(user) -> None:
    token = _issuer().issue_token(user, (), amr=("pwd", "otp"))

    assert _claims(token)["amr"] == ["pwd", "otp"]
    claims = _validator().validate_bearer_token(token)
    assert claims.amr == ("pwd", "otp")
    # The rest of the contract is untouched by the new claim.
    assert claims.user_id == user.id
    assert claims.tenant_id == user.tenant_id
    assert claims.auth_method is AuthMethod.BEARER_TOKEN


@pytest.mark.django_db
def test_refresh_token_defaults_to_pwd(user) -> None:
    token = _issuer().issue_refresh_token(user)

    assert _claims(token)["amr"] == ["pwd"]
    assert _validator().read_refresh_amr(token) == ("pwd",)


@pytest.mark.django_db
def test_refresh_token_carries_the_second_factor(user) -> None:
    token = _issuer().issue_refresh_token(user, amr=("pwd", "otp"))

    assert _claims(token)["amr"] == ["pwd", "otp"]
    validator = _validator()
    # ``validate_refresh_token`` keeps its published 2-tuple contract …
    user_id, tenant_id = validator.validate_refresh_token(token)
    assert (user_id, tenant_id) == (user.id, user.tenant_id)
    # … while ``read_refresh_amr`` exposes the added claim separately.
    assert validator.read_refresh_amr(token) == ("pwd", "otp")


# ---------------------------------------------------------------------------
# 2. Normalisation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_amr_values_are_normalised_on_read(user) -> None:
    """Case, duplicates and non-strings are neutralised, order preserved."""
    token = _issuer().issue_token(user, (), amr=("PWD", "otp", "pwd"))

    # Issuance writes what it is given …
    assert _claims(token)["amr"] == ["PWD", "otp", "pwd"]
    # … the validator reads it as RFC 8176 values.
    assert _validator().validate_bearer_token(token).amr == ("pwd", "otp")


@pytest.mark.django_db
def test_an_empty_amr_is_never_more_permissive_than_no_claim(user) -> None:
    """``amr=[]`` degrades to ``("pwd",)`` — an absent factor list is not "none"."""
    token = _issuer().issue_token(user, (), amr=())

    assert _claims(token)["amr"] == []
    assert _validator().validate_bearer_token(token).amr == ("pwd",)


# ---------------------------------------------------------------------------
# 3. Backward compatibility — tokens minted before the claim existed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_legacy_access_token_without_amr_reads_as_pwd(user) -> None:
    token = _legacy_token(user, typ="access")
    assert "amr" not in _claims(token)

    assert _validator().validate_bearer_token(token).amr == ("pwd",)


@pytest.mark.django_db
def test_legacy_refresh_token_without_amr_reads_as_pwd(user) -> None:
    token = _legacy_token(user, typ="refresh")
    assert "amr" not in _claims(token)

    assert _validator().read_refresh_amr(token) == ("pwd",)


# ---------------------------------------------------------------------------
# 4. Propagation into AuthContext
# ---------------------------------------------------------------------------


def test_identity_claims_and_auth_context_default_to_no_factor() -> None:
    """The dataclass defaults stay non-permissive for non-token credentials.

    An API key builds ``IdentityClaims`` without ``amr``; the empty tuple is
    what makes ``"otp" in ctx.amr`` false for a key under
    ``MFA_STAFF_ENFORCEMENT=required`` (WP E3.6).
    """
    claims = IdentityClaims(
        user_id=UUID(int=1),
        tenant_id=UUID(int=2),
        roles=(),
        auth_method=AuthMethod.API_KEY,
    )
    assert claims.amr == ()


def test_build_auth_context_carries_the_amr_claim(user) -> None:
    claims = IdentityClaims(
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        amr=("pwd", "otp"),
    )
    service = TenantContextService()
    ctx = service.build_auth_context(
        claims,
        TenantContext(tenant_id=user.tenant_id, tenant_name=user.tenant.name),
        claims.roles,
    )

    assert ctx.amr == ("pwd", "otp")
