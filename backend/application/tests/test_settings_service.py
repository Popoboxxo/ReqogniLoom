"""Tests for COMP-AS-SET SettingsService (REQ-066).

ReviewPolicy section (Phase 5, REQ-L2-RV-001): resolver/upsert methods for the
per-workspace (or tenant-global) AI-derivation review policy. See
``persistence.models.ReviewPolicy`` for the scoping model this wraps.
"""
from __future__ import annotations

import pytest

from application.settings_service import SettingsService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User, Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="settings-tenant", slug="settings-tenant")


@pytest.fixture
def user(tenant):
    return User.objects.create(
        username="settingsuser", email="settings@example.com", tenant=tenant
    )


@pytest.fixture
def ctx(user):
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="settings-tenant",
    )


@pytest.fixture
def workspace(tenant):
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(tenant=tenant, name="settings-ws")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace_id(workspace):
    return workspace.id


@pytest.fixture
def settings_service():
    return SettingsService()


# ---------------------------------------------------------------------------
# ReviewPolicy (Phase 5)
# ---------------------------------------------------------------------------


def test_get_effective_review_policy_defaults_to_auto(settings_service, ctx):
    policy = settings_service.get_effective_review_policy(ctx, workspace_id=None)
    assert policy.mode == "auto"
    assert policy.min_confidence == 0.7


def test_get_effective_review_policy_workspace_overrides_tenant_global(
    settings_service, ctx, workspace_id
):
    settings_service.update_review_policy(
        ctx, workspace_id=None, mode="review_all", min_confidence=0.5
    )
    settings_service.update_review_policy(
        ctx, workspace_id=workspace_id, mode="review_high_risk", min_confidence=0.8
    )
    scoped = settings_service.get_effective_review_policy(ctx, workspace_id=workspace_id)
    assert scoped.mode == "review_high_risk"
    global_only = settings_service.get_effective_review_policy(ctx, workspace_id=None)
    assert global_only.mode == "review_all"


def test_update_review_policy_rejects_unknown_mode(settings_service, ctx):
    from application.base import ValidationError

    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx, workspace_id=None, mode="bogus", min_confidence=0.5
        )


def test_update_review_policy_rejects_out_of_range_confidence(settings_service, ctx):
    from application.base import ValidationError

    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx, workspace_id=None, mode="auto", min_confidence=1.5
        )
