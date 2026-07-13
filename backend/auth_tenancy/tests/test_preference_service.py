"""
REQ-L1-027 — UserWorkspacePreference service tests.

Covers:
* PreferenceService.get_preference — returns None when no row exists.
* PreferenceService.get_or_create_preference — idempotent creation.
* PreferenceService.update_visibility — merge semantics.
* PreferenceService.get_effective_visibility — preset + override merge.
* UserWorkspacePreference model — unique constraint.

Service methods now require an ``AuthContext`` (``ctx``) which is forwarded
to ``ServiceBase._set_tenant_context``. The test helper builds a minimal
``AuthContext`` with the right ``tenant_id`` so the thread-local ORM filter
is active and the ``TenantScopedModel.objects`` manager is happy.
"""
from __future__ import annotations

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import UserWorkspacePreference
from auth_tenancy.services import PreferenceService

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, user_id, tenant_id):
    """Build a minimal ``AuthContext`` carrying *user_id* and *tenant_id*.

    ``active_roles`` is fixed to ``("editor",)``; ``auth_method`` is
    ``BEARER_TOKEN`` because the context is frozen and every non-optional
    field must be supplied.
    """
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPreferenceService:
    """Integration tests for PreferenceService (REQ-L1-027)."""

    def test_get_preference_returns_none_when_missing(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        with active_tenant(tenant_a):
            result = svc.get_preference(user_a.id, workspace_a.id, ctx=ctx)
        assert result is None

    def test_get_or_create_preference_creates_blank(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        with active_tenant(tenant_a):
            pref = svc.get_or_create_preference(
                user_a.id, workspace_a.id, ctx=ctx
            )
            assert pref.optional_artifact_visibility == {}
            assert pref.user_id == user_a.id
            assert pref.workspace_id == workspace_a.id
            assert pref.tenant_id == tenant_a.id

    def test_get_or_create_preference_is_idempotent(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        with active_tenant(tenant_a):
            pref1 = svc.get_or_create_preference(
                user_a.id, workspace_a.id, ctx=ctx
            )
            pref2 = svc.get_or_create_preference(
                user_a.id, workspace_a.id, ctx=ctx
            )
            assert pref1.pk == pref2.pk

    def test_update_visibility_merges_overrides(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        with active_tenant(tenant_a):
            # First update: creates row with initial overrides
            pref = svc.update_visibility(
                user_a.id,
                workspace_a.id,
                {"adr": False, "risk": True},
                ctx=ctx,
            )
            assert pref.optional_artifact_visibility == {"adr": False, "risk": True}

            # Second update: merges, does not replace
            pref = svc.update_visibility(
                user_a.id, workspace_a.id, {"issue": False}, ctx=ctx
            )
            assert pref.optional_artifact_visibility == {
                "adr": False,
                "risk": True,
                "issue": False,
            }

    def test_update_visibility_overwrites_existing_key(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        with active_tenant(tenant_a):
            svc.update_visibility(
                user_a.id, workspace_a.id, {"adr": False}, ctx=ctx
            )
            pref = svc.update_visibility(
                user_a.id, workspace_a.id, {"adr": True}, ctx=ctx
            )
            assert pref.optional_artifact_visibility["adr"] is True

    def test_get_effective_visibility_no_preference(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        preset_map = {"adr": True, "risk": True, "issue": True}
        with active_tenant(tenant_a):
            result = svc.get_effective_visibility(
                user_a.id, workspace_a.id, preset_map, ctx=ctx
            )
        assert result == preset_map

    def test_get_effective_visibility_with_overrides(
        self, tenant_a, user_a, workspace_a
    ):
        svc = PreferenceService()
        ctx = _make_ctx(user_id=user_a.id, tenant_id=tenant_a.id)
        preset_map = {"adr": True, "risk": True, "issue": True}
        with active_tenant(tenant_a):
            svc.update_visibility(
                user_a.id, workspace_a.id, {"adr": False}, ctx=ctx
            )
            result = svc.get_effective_visibility(
                user_a.id, workspace_a.id, preset_map, ctx=ctx
            )
        assert result == {"adr": False, "risk": True, "issue": True}

    def test_unique_constraint_per_tenant_user_workspace(
        self, tenant_a, user_a, workspace_a
    ):
        """Creating two preferences for (tenant, user, workspace) raises."""
        from django.db import IntegrityError, transaction

        with active_tenant(tenant_a):
            UserWorkspacePreference.objects.create(
                tenant=tenant_a,
                user=user_a,
                workspace=workspace_a,
                optional_artifact_visibility={"adr": False},
            )
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    UserWorkspacePreference.objects.create(
                        tenant=tenant_a,
                        user=user_a,
                        workspace=workspace_a,
                        optional_artifact_visibility={"risk": False},
                    )
