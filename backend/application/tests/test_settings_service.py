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
def extended_workspace(tenant):
    """Same as ``workspace`` but on the "extended" preset tier (GitHub #452).

    ``Workspace.preset`` is the JSONField ``presets.gate`` reads to resolve
    the active rigor tier via ``presets.services.get_preset()`` -- see
    ``presets/gate.py:_get_or_create_preset_config``.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        return PersistenceWorkspace.objects.create(
            tenant=tenant, name="settings-ws-extended", preset={"name": "extended"}
        )
    finally:
        TenantContext.clear_tenant()


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


# ---------------------------------------------------------------------------
# GitHub #452 regression — "extended" preset tier must floor "auto"/
# "review_changes" to "review_all" (no unsupervised approval-gate crossing).
# ---------------------------------------------------------------------------


def test_get_effective_review_policy_floors_default_to_review_all_for_extended_tier(
    settings_service, ctx, extended_workspace
):
    """The hardcoded fallback default (mode="auto", min_confidence=0.7,
    used when no ReviewPolicy row exists at all) must not apply as-is to an
    "extended"-tier workspace: this is the exact scenario from the bug
    report (extended preset + "auto" + confidence 0.7 -> auto-approve
    without a human gate). The effective mode must be floored to
    "review_all".
    """
    policy = settings_service.get_effective_review_policy(
        ctx, workspace_id=extended_workspace.id
    )
    assert policy.mode == "review_all"


def test_get_effective_review_policy_floors_stored_auto_row_for_extended_tier(
    settings_service, ctx, extended_workspace
):
    """Even a persisted row explicitly storing mode="auto" for an
    "extended"-tier workspace (e.g. written before this fix, or via direct
    ORM access bypassing ``update_review_policy``) must be floored at read
    time -- the guard must not depend on how the row was created.
    """
    from persistence.models import ReviewPolicy

    TenantContext.set_tenant(ctx.tenant_id)
    try:
        ReviewPolicy.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=extended_workspace.id,
            mode="auto",
            min_confidence=0.7,
        )
    finally:
        TenantContext.clear_tenant()

    policy = settings_service.get_effective_review_policy(
        ctx, workspace_id=extended_workspace.id
    )
    assert policy.mode == "review_all"


def test_get_effective_review_policy_does_not_floor_non_extended_tier(
    settings_service, ctx, workspace_id
):
    """Regression safety: a workspace without an "extended" tier (the
    fixture defaults to "minimal") keeps the plain "auto" default -- the
    floor must be tier-conditional, not applied unconditionally.
    """
    policy = settings_service.get_effective_review_policy(
        ctx, workspace_id=workspace_id
    )
    assert policy.mode == "auto"


def test_update_review_policy_rejects_auto_mode_for_extended_tier(
    settings_service, ctx, extended_workspace
):
    """Defense in depth: an admin must not be able to explicitly store
    mode="auto" for an "extended"-tier workspace either.
    """
    from application.base import ValidationError

    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx, workspace_id=extended_workspace.id, mode="auto", min_confidence=0.7
        )


def test_update_review_policy_rejects_review_changes_mode_for_extended_tier(
    settings_service, ctx, extended_workspace
):
    from application.base import ValidationError

    with pytest.raises(ValidationError):
        settings_service.update_review_policy(
            ctx,
            workspace_id=extended_workspace.id,
            mode="review_changes",
            min_confidence=0.7,
        )


def test_update_review_policy_still_allows_review_all_for_extended_tier(
    settings_service, ctx, extended_workspace
):
    """The guard only blocks the ungated modes -- an explicit human-gated
    mode must still be settable for "extended"."""
    policy = settings_service.update_review_policy(
        ctx, workspace_id=extended_workspace.id, mode="review_all", min_confidence=0.7
    )
    assert policy.mode == "review_all"
