"""SA-15 regression tests — cross-tenant guard on the preset gate.

SYSTEMAUDIT-2026-08-27 §4.1 #6: ``presets.gate`` resolves a caller-supplied
``workspace_id`` through the ``unscoped`` escape-hatch managers. Without an
explicit tenant comparison a caller authenticated for tenant A could read and
mutate tenant B's preset configuration.

These tests pin the guard from both directions:
  * same-tenant access keeps working (no regression),
  * cross-tenant access raises,
  * a *warm* in-process cache does not become a bypass,
  * the tenant-less escape hatch (management commands / migrations) survives.
"""
from __future__ import annotations

import pytest

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from presets.exceptions import CrossTenantWorkspaceError
from presets.gate import (
    FeatureGateService,
    _invalidate_workspace,
    _workspace_tenant_cache,
)
from presets.models import WorkspacePresetConfig
from presets.registry import TIER_EXTENDED, TIER_STANDARD

from .conftest import active_tenant


@pytest.fixture
def other_tenant(db: None) -> Tenant:
    """A second tenant that must never see the first tenant's workspaces."""
    return Tenant.objects.create(name="Other Tenant", slug="other-tenant")


@pytest.fixture(autouse=True)
def _clear_owner_cache(db: None):
    """Drop the process-local workspace->tenant memo between tests."""
    _workspace_tenant_cache.clear()
    yield
    _workspace_tenant_cache.clear()


@pytest.fixture
def gate() -> FeatureGateService:
    return FeatureGateService()


@pytest.fixture
def foreign_workspace(other_tenant: Tenant) -> Workspace:
    """Workspace owned by ``other_tenant``, with an Extended preset config."""
    with active_tenant(other_tenant):
        ws = Workspace.objects.create(tenant=other_tenant, name="WS-Foreign")
    WorkspacePresetConfig.unscoped.create(
        tenant=other_tenant,
        workspace=ws,
        active_tier=TIER_EXTENDED,
        terminology_profile="se_mode",
        downgrade_policy="block",
    )
    _invalidate_workspace(str(ws.id))
    return ws


class TestCrossTenantRejected:
    """The active tenant must own the workspace it asks about."""

    def test_get_preset_rejects_foreign_workspace(
        self, gate: FeatureGateService, tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.get_preset(str(foreign_workspace.id))

    def test_is_feature_enabled_rejects_foreign_workspace(
        self, gate: FeatureGateService, tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.is_feature_enabled("baselines", str(foreign_workspace.id))

    def test_get_terminology_rejects_foreign_workspace(
        self, gate: FeatureGateService, tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.get_terminology(str(foreign_workspace.id))

    def test_switch_preset_rejects_foreign_workspace(
        self, gate: FeatureGateService, tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.switch_preset(str(foreign_workspace.id), TIER_STANDARD)

        # The write must not have landed.
        row = WorkspacePresetConfig.unscoped.get(workspace_id=foreign_workspace.id)
        assert row.active_tier == TIER_EXTENDED

    def test_switch_terminology_rejects_foreign_workspace(
        self, gate: FeatureGateService, tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.switch_terminology_profile(
                    str(foreign_workspace.id), "dev_mode"
                )

        row = WorkspacePresetConfig.unscoped.get(workspace_id=foreign_workspace.id)
        assert row.terminology_profile == "se_mode"

    def test_warm_cache_is_not_a_bypass(
        self,
        gate: FeatureGateService,
        tenant: Tenant,
        other_tenant: Tenant,
        foreign_workspace: Workspace,
    ) -> None:
        """The owning tenant warms the cache; a foreign tenant still gets 403.

        Regression guard for the ordering of the check: ``_tier_cache`` is keyed
        by workspace id only, so a guard placed *after* the cache read would let
        the second call through.
        """
        with active_tenant(other_tenant):
            assert gate.get_preset(str(foreign_workspace.id)).tier == TIER_EXTENDED

        with active_tenant(tenant):
            with pytest.raises(CrossTenantWorkspaceError):
                gate.get_preset(str(foreign_workspace.id))


class TestSameTenantUnaffected:
    """No regression for the legitimate paths."""

    def test_owning_tenant_reads_preset(
        self, gate: FeatureGateService, tenant: Tenant, workspace_standard: Workspace
    ) -> None:
        with active_tenant(tenant):
            assert gate.get_preset(str(workspace_standard.id)).tier == "standard"

    def test_owning_tenant_switches_preset(
        self, gate: FeatureGateService, tenant: Tenant, workspace_standard: Workspace
    ) -> None:
        with active_tenant(tenant):
            result = gate.switch_preset(str(workspace_standard.id), TIER_EXTENDED)
        assert result.tier == TIER_EXTENDED

    def test_no_tenant_context_still_allowed(
        self, gate: FeatureGateService, workspace_standard: Workspace
    ) -> None:
        """Tenant-less callers (seed/migration/CLI) keep the escape hatch."""
        assert not TenantContext.is_set()
        assert gate.get_preset(str(workspace_standard.id)).tier == "standard"


class TestPolicyServiceCacheGuard:
    """SA-15 follow-through: the application-layer preset cache is guarded too."""

    def test_policy_cache_does_not_leak_foreign_preset(
        self, tenant: Tenant, other_tenant: Tenant, foreign_workspace: Workspace
    ) -> None:
        from application.preset_policy_service import PresetPolicyService

        policy = PresetPolicyService()

        # Warm PresetPolicyService's own TTL cache as the owning tenant.
        with active_tenant(other_tenant):
            assert policy.is_feature_enabled(
                str(foreign_workspace.id), "global_baselines"
            ) is True

        # The foreign tenant must not be served that cached entry. The policy
        # layer is documented fail-closed, so the guard surfaces as False.
        with active_tenant(tenant):
            assert policy.is_feature_enabled(
                str(foreign_workspace.id), "global_baselines"
            ) is False
