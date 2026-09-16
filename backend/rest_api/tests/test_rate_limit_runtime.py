"""Runtime-configurable REST rate limits (GitHub #944) — enforcement + fail-safety.

Complements ``rest_api/tests/test_security_hardening_269.py`` (which pins the
*static* ceilings). Here the ceiling is changed while the process keeps running,
which is the feature #944 asks for: an admin edits a limit and the very next
request obeys it, with no redeploy.

Real DB + real JWT round-trip, same as the #269 suite — the resolution layer
reads the database and the cache, so a mock would paper over exactly the parts
under test.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from admin_ops.services.rate_limit_service import RateLimitService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from rest_api.throttling import AuthContextUserRateThrottle, DynamicRateThrottle

_SECRET = "test-secret-not-a-real-key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


class DownCache:
    """Cache stand-in whose every operation fails, as Redis does when it dies."""

    def get(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")

    def set(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("redis is down")


@pytest.fixture
def tenant(db):
    """Active tenant + admin user (password login capable) + one workspace."""
    tenant = Tenant.objects.create(name="RL T", slug="rl-t", is_active=True)
    admin = User.objects.create(username="rladmin", email="rladmin@t.test", tenant=tenant)
    admin.set_password("rlpass123")
    admin.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="RL WS", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "admin": admin, "workspace": workspace}
    finally:
        clear_request_tenant()


def _authed_client() -> APIClient:
    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"username": "rladmin", "password": "rlpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _get_workspaces(client: APIClient) -> Any:
    return client.get("/api/v1/workspaces/")


# ---------------------------------------------------------------------------
# The override governs, and a change applies without a restart
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_tenant_override_enforces_a_429(tenant):
    """A ceiling stored at runtime must actually throttle the endpoint.

    The settings layer says 20000/min here, so a 429 can only come from the
    override — which is what makes this a regression test for #944 rather than
    for #269.
    """
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": "2/min"})
    cache.clear()

    client = _authed_client()
    statuses = [_get_workspaces(client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429], statuses


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_raising_the_limit_takes_effect_without_a_restart(tenant):
    """The reported gap: "kann ich die Limits zur Laufzeit einstellen?" — now yes.

    No counter is cleared between the phases, so this is a genuine mid-flight
    reconfiguration: the same client that was refused one request earlier is
    served again purely because the ceiling changed.
    """
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": "1/min"})
    cache.clear()
    client = _authed_client()

    assert _get_workspaces(client).status_code == 200
    assert _get_workspaces(client).status_code == 429

    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": "100/min"})

    assert _get_workspaces(client).status_code == 200


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_override_wins_over_the_settings_layer(tenant):
    """Precedence guard: settings 20000/min must not shadow a 1/min override."""
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": "1/min"})
    cache.clear()

    client = _authed_client()

    assert _get_workspaces(client).status_code == 200
    assert _get_workspaces(client).status_code == 429


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_empty_override_removes_the_limit(tenant):
    """An operator must be able to switch a ceiling off at runtime."""
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": ""})
    cache.clear()

    client = _authed_client()

    assert all(_get_workspaces(client).status_code == 200 for _ in range(40))


# ---------------------------------------------------------------------------
# Global layer — the one reachable without a tenant
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_global_override_governs_tenantless_requests(tenant):
    """Login carries no auth context, so it resolves from the global layer.

    Counts only *failed* attempts (`LoginRateThrottle`), so the third wrong
    password is refused while the settings ceiling of 1000/min would have
    allowed it.
    """
    RateLimitService.set_global_overrides({"login": "2/min"})
    cache.clear()

    statuses = [
        APIClient()
        .post(
            "/api/v1/auth/login/",
            {"username": "rladmin", "password": "wrong-password"},
            format="json",
        )
        .status_code
        for _ in range(3)
    ]

    assert statuses == [401, 401, 429], statuses


@pytest.mark.django_db
def test_resolution_never_raises_when_its_cache_is_down(monkeypatch):
    """The resolver is fail-safe: a cache outage degrades to the settings value
    instead of propagating an exception into the request path."""
    from admin_ops.rate_limits import resolve_rate

    monkeypatch.setattr("admin_ops.rate_limits.cache", DownCache())

    assert resolve_rate("user", tenant_id=None, default="600/min") == "600/min"


# ---------------------------------------------------------------------------
# Fail-open policy on a counter outage
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_cache_outage_fails_open(tenant, monkeypatch):
    """Documented policy: an unreachable counter cache lets traffic through.

    The control half of this test proves the ceiling is real — with a healthy
    cache a ``0/min`` limit refuses the very first request. The second half
    kills the cache and asserts the same request is served: a rate limiter must
    not turn a Redis outage into an API-wide outage, and RBAC (enforced
    independently) is still in force either way.
    """
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"user": "0/min"})
    cache.clear()
    client = _authed_client()

    assert _get_workspaces(client).status_code == 429

    monkeypatch.setattr(DynamicRateThrottle, "cache", DownCache())

    assert _get_workspaces(client).status_code == 200


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_cache_outage_does_not_break_login(tenant, monkeypatch):
    """The failure-counting throttles must fail open too, not deny."""
    RateLimitService.set_tenant_overrides(tenant["tenant"].id, {"login": "0/min"})
    cache.clear()
    monkeypatch.setattr(DynamicRateThrottle, "cache", DownCache())

    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"username": "rladmin", "password": "rlpass123"},
        format="json",
    )

    assert resp.status_code == 200, resp.content


# ---------------------------------------------------------------------------
# Identification strategy: API key > user > IP
# ---------------------------------------------------------------------------


class TestIdentification:
    """The bucket identity, in the documented order."""

    @staticmethod
    def _request_with(ctx: AuthContext | None):
        """Minimal stand-in — ``get_cache_key`` only reads ``auth_context``."""
        return SimpleNamespace(auth_context=ctx)

    def test_api_key_is_used_when_present(self):
        key_id = uuid4()
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.API_KEY,
            api_key_id=key_id,
        )

        cache_key = AuthContextUserRateThrottle().get_cache_key(self._request_with(ctx), None)

        assert cache_key is not None
        assert str(key_id) in cache_key
        assert str(ctx.user_id) not in cache_key

    def test_user_is_used_for_a_bearer_token(self):
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.BEARER_TOKEN,
        )

        cache_key = AuthContextUserRateThrottle().get_cache_key(self._request_with(ctx), None)

        assert cache_key is not None
        assert str(ctx.user_id) in cache_key

    def test_anonymous_requests_are_not_counted_per_user(self):
        request = SimpleNamespace(auth_context=None)

        assert AuthContextUserRateThrottle().get_cache_key(request, None) is None


@pytest.mark.django_db
def test_scopes_match_settings():
    """The runtime registry and the configured rates must not drift apart."""
    from admin_ops.rate_limits import RATE_LIMIT_SCOPES

    assert set(RATE_LIMIT_SCOPES) == set(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])


# ---------------------------------------------------------------------------
# Admin API over real HTTP (routing + permission layer, not just the view body)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_admin_endpoint_is_routable_and_writable(tenant):
    """End-to-end through the URL conf, RBAC and the ADMIN-tier key gate."""
    from admin_ops.rate_limits import RATE_LIMIT_SCOPES

    client = _authed_client()

    listing = client.get("/api/v1/admin/rate-limits/")
    assert listing.status_code == 200, listing.content
    assert set(listing.json()["scopes"]) == set(RATE_LIMIT_SCOPES)

    written = client.put(
        "/api/v1/admin/rate-limits/",
        {"overrides": {"user": "7/min"}},
        format="json",
    )
    assert written.status_code == 200, written.content
    assert written.json()["scopes"]["user"]["source"] == "tenant"

    # ... and the new ceiling governs the next throttled request.
    cache.clear()
    statuses = [_get_workspaces(client).status_code for _ in range(8)]
    assert 429 in statuses, statuses
