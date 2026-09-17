"""Runtime-configurable rate limits (GitHub #944) — resolution, service, API.

The behaviour this pins down:

* precedence is exactly ``tenant override > global override > settings``, with
  an explicit empty value meaning "unlimited" and an absent row meaning "fall
  through";
* a write invalidates the resolution cache, so the new ceiling applies to the
  *next* request rather than after the TTL — that is the whole point of the
  feature ("change a limit without restarting the process");
* the admin API validates input and refuses non-admins;
* the change is attributed in the audit trail.

RLS for the new tenant-scoped table is covered separately in
``test_rate_limit_rls.py``; enforcement of the resolved rate is covered in
``rest_api/tests/test_rate_limit_runtime.py`` and
``mcp_server/tests/test_rate_limit_mcp_runtime.py``.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from admin_ops.models import (
    SYSTEM_RATE_LIMIT_ID,
    RateLimitOverride,
    SystemRateLimitOverride,
)
from admin_ops.rate_limit_rest import GlobalRateLimitsView, RateLimitsView
from admin_ops.rate_limits import RATE_LIMIT_SCOPES, resolve_rate
from admin_ops.services.rate_limit_service import RateLimitService
from application.base import ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.tests.conftest import tenant_b  # noqa: F401 — isolation fixture
from persistence.models import Tenant

from .conftest import active_tenant

_SETTINGS_RATE = "600/min"


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    """Overrides are cached; isolate every test from every other."""
    cache.clear()
    yield
    cache.clear()


def _request(auth: AuthContext, *, body: Optional[dict] = None, method: str = "get") -> Request:
    factory = APIRequestFactory()
    builder = getattr(factory, method)
    raw = builder("/x/", body or {}, format="json") if body is not None else builder("/x/")
    request = Request(raw, parsers=[JSONParser()])
    request.auth_context = auth
    return request


# ---------------------------------------------------------------------------
# Scope registry
# ---------------------------------------------------------------------------


class TestScopeRegistry:
    def test_registry_matches_the_configured_throttle_rates(self):
        """A scope added to settings but missing here would be silently
        un-configurable; one removed there but still here would be offered as a
        setting that controls nothing."""
        configured = set(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
        assert set(RATE_LIMIT_SCOPES) == configured


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolverPrecedence:
    def test_settings_layer_is_used_without_overrides(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            assert (
                resolve_rate("user", tenant_id=tenant_a.id, default=_SETTINGS_RATE)
                == _SETTINGS_RATE
            )
            assert (
                resolve_rate("user", tenant_id=None, default=_SETTINGS_RATE)
                == _SETTINGS_RATE
            )

    def test_global_override_beats_settings(self, tenant_a: Tenant):
        """The layer the pre-authentication MCP transport relies on."""
        with active_tenant(tenant_a):
            SystemRateLimitOverride.objects.create(scopes={"user": "5/min"})

            assert (
                resolve_rate("user", tenant_id=None, default=_SETTINGS_RATE) == "5/min"
            )

    def test_tenant_override_beats_global(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            SystemRateLimitOverride.objects.create(scopes={"user": "5/min"})
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "2/min"})

            assert (
                resolve_rate("user", tenant_id=tenant_a.id, default=_SETTINGS_RATE)
                == "2/min"
            )
            # ... while a tenant-less caller still gets the global layer.
            assert resolve_rate("user", tenant_id=None, default=_SETTINGS_RATE) == "5/min"

    def test_tenant_override_is_not_visible_to_another_tenant(self, tenant_a, tenant_b):
        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "2/min"})

        with active_tenant(tenant_b):
            assert (
                resolve_rate("user", tenant_id=tenant_b.id, default=_SETTINGS_RATE)
                == _SETTINGS_RATE
            )

    def test_empty_override_disables_the_scope(self, tenant_a: Tenant):
        """``''`` is an explicit "unlimited", distinct from "no override"."""
        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": ""})

            assert resolve_rate("user", tenant_id=tenant_a.id, default=_SETTINGS_RATE) is None

    def test_unknown_scope_is_ignored_not_fatal(self, tenant_a: Tenant):
        """A scope removed from the code later must not break resolution."""
        with active_tenant(tenant_a):
            SystemRateLimitOverride.objects.create(scopes={"retired_scope": "1/min"})

            assert (
                resolve_rate("user", tenant_id=None, default=_SETTINGS_RATE)
                == _SETTINGS_RATE
            )

    def test_write_invalidates_the_resolution_cache(self, tenant_a: Tenant):
        """Without eager invalidation the change would be invisible for the TTL
        — i.e. "I changed it and nothing happened"."""
        with active_tenant(tenant_a):
            assert resolve_rate("user", tenant_id=tenant_a.id, default=_SETTINGS_RATE) == _SETTINGS_RATE

            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "9/min"})

            assert resolve_rate("user", tenant_id=tenant_a.id, default=_SETTINGS_RATE) == "9/min"

    def test_empty_string_in_settings_means_disabled(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            assert resolve_rate("user", tenant_id=tenant_a.id, default="") is None
            assert resolve_rate("user", tenant_id=tenant_a.id, default=None) is None


# ---------------------------------------------------------------------------
# Effective view (what the admin API reports)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEffectiveRates:
    def test_origin_is_reported_per_scope(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            effective = RateLimitService.get_effective(tenant_a.id)
            assert set(effective) == set(RATE_LIMIT_SCOPES)
            assert effective["user"]["source"] == "settings"
            assert effective["user"]["tenant_override"] is None

            RateLimitService.set_global_overrides({"anon": "9/min"})
            effective = RateLimitService.get_effective(tenant_a.id)
            assert effective["anon"]["source"] == "global"
            assert effective["anon"]["effective"] == "9/min"

            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "3/min"})
            effective = RateLimitService.get_effective(tenant_a.id)
            assert effective["user"]["source"] == "tenant"
            assert effective["user"]["global_override"] is None


# ---------------------------------------------------------------------------
# Service validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestServiceValidation:
    def test_invalid_rate_is_rejected(self, tenant_a: Tenant):
        with active_tenant(tenant_a), pytest.raises(ValidationError):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "lots"})

    def test_unknown_scope_is_rejected(self, tenant_a: Tenant):
        with active_tenant(tenant_a), pytest.raises(ValidationError):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"nope": "5/min"})

    def test_global_invalid_rate_is_rejected(self, tenant_a: Tenant):
        with active_tenant(tenant_a), pytest.raises(ValidationError):
            RateLimitService.set_global_overrides({"user": "5/fortnight"})

    def test_none_clears_an_override(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "5/min"})
            assert RateLimitOverride.unscoped.filter(tenant_id=tenant_a.id).count() == 1

            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": None})

            assert RateLimitOverride.unscoped.filter(tenant_id=tenant_a.id).count() == 0

    def test_clearing_global_removes_the_row(self, tenant_a: Tenant):
        with active_tenant(tenant_a):
            RateLimitService.set_global_overrides({"user": "5/min"})
            assert SystemRateLimitOverride.objects.filter(pk=SYSTEM_RATE_LIMIT_ID).exists()

            RateLimitService.clear_global_overrides()

            assert not SystemRateLimitOverride.objects.exists()


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRateLimitsApi:
    def test_get_reports_every_scope(self, admin_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            response = RateLimitsView().get(_request(admin_ctx))

        assert response.status_code == 200
        assert set(response.data["scopes"]) == set(RATE_LIMIT_SCOPES)
        assert response.data["tenant_id"] == str(tenant_a.id)

    def test_admin_can_set_a_tenant_override(self, admin_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            response = RateLimitsView().put(
                _request(admin_ctx, body={"overrides": {"user": "42/min"}}, method="put")
            )

        assert response.status_code == 200
        assert response.data["scopes"]["user"]["effective"] == "42/min"
        assert response.data["scopes"]["user"]["source"] == "tenant"

    def test_tenant_admin_without_workspace_role_can_write(
        self, tenant_a: Tenant, admin_user
    ):
        """The gate is the tenant-admin role, not a workspace role."""
        from auth_tenancy.context import AuthMethod
        from auth_tenancy.models import TenantRole

        with active_tenant(tenant_a):
            TenantRole.objects.create(tenant=tenant_a, user=admin_user, role=TenantRole.ROLE_ADMIN)
            ctx = AuthContext(
                user_id=admin_user.id,
                tenant_id=tenant_a.id,
                active_roles=(),
                auth_method=AuthMethod.BEARER_TOKEN,
            )
            response = RateLimitsView().put(
                _request(ctx, body={"overrides": {"user": "42/min"}}, method="put")
            )

        assert response.status_code == 200

    def test_non_admin_write_is_denied(self, regular_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            response = RateLimitsView().put(
                _request(regular_ctx, body={"overrides": {"user": "42/min"}}, method="put")
            )

        assert response.status_code == 403

    def test_non_admin_delete_is_denied(self, regular_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            response = RateLimitsView().delete(_request(regular_ctx, method="delete"))

        assert response.status_code == 403

    def test_delete_clears_tenant_overrides(self, admin_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "42/min"})
            response = RateLimitsView().delete(_request(admin_ctx, method="delete"))

        assert response.status_code == 200
        assert response.data["scopes"]["user"]["source"] == "settings"

    def test_invalid_rate_is_a_400(self, admin_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a), pytest.raises(DrfValidationError):
            RateLimitsView().put(
                _request(admin_ctx, body={"overrides": {"user": "nope"}}, method="put")
            )

    def test_missing_overrides_key_is_a_400(self, admin_ctx: AuthContext, tenant_a: Tenant):
        """A client that forgot the field must not silently wipe the config."""
        with active_tenant(tenant_a), pytest.raises(DrfValidationError):
            RateLimitsView().put(_request(admin_ctx, body={}, method="put"))

    def test_global_view_is_admin_only(self, regular_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            assert GlobalRateLimitsView().get(_request(regular_ctx)).status_code == 403
            response = GlobalRateLimitsView().put(
                _request(regular_ctx, body={"overrides": {"user": "1/min"}}, method="put")
            )
        assert response.status_code == 403

    def test_admin_can_set_a_global_override(self, admin_ctx: AuthContext, tenant_a: Tenant):
        with active_tenant(tenant_a):
            response = GlobalRateLimitsView().put(
                _request(admin_ctx, body={"overrides": {"user": "11/min"}}, method="put")
            )

        assert response.status_code == 200
        assert response.data["scopes"]["user"]["effective"] == "11/min"
        assert response.data["scopes"]["user"]["source"] == "global"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAuditTrail:
    def test_tenant_change_is_audited(self, monkeypatch, admin_user, tenant_a: Tenant):
        calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "audit.services.log_write", lambda **kwargs: calls.append(kwargs)
        )

        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(
                tenant_a.id, {"user": "5/min"}, user_id=admin_user.id
            )

        assert len(calls) == 1
        assert calls[0]["entity_type"] == "RateLimitOverride"
        assert calls[0]["entity_id"] == tenant_a.id
        assert calls[0]["actor"] == str(admin_user.id)

    def test_no_attribution_means_no_audit_entry(self, monkeypatch, tenant_a: Tenant):
        """``user_id`` is attribution-only; a system caller writes nothing."""
        calls: list[Any] = []
        monkeypatch.setattr(
            "audit.services.log_write", lambda **kwargs: calls.append(kwargs)
        )

        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(tenant_a.id, {"user": "5/min"})

        assert calls == []

    def test_audit_failure_does_not_roll_back_the_change(self, monkeypatch, admin_user, tenant_a: Tenant):
        """Attribution is best-effort: a broken audit sink must not undo a
        legitimate config write."""

        def _boom(**kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr("audit.services.log_write", _boom)

        with active_tenant(tenant_a):
            RateLimitService.set_tenant_overrides(
                tenant_a.id, {"user": "5/min"}, user_id=admin_user.id
            )
            assert RateLimitOverride.unscoped.filter(
                tenant_id=tenant_a.id, scope="user"
            ).exists()
