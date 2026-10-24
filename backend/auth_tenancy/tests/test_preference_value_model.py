"""Q1 preference service — ``PreferenceValue`` model tests (Plan C, T-C2-1).

Covers the schema contract the preference service relies on (``#1094``):

* one global row per (tenant, key), one per (tenant, workspace, key) and one
  per (tenant, user, key) — enforced by the three partial unique indexes;
* the scope/target invariant ``ck_prefval_scope_target``: a ``global`` row
  carries neither a workspace nor a user, a ``workspace`` row requires a
  workspace, a ``user`` row requires a user;
* a valid row per level saves, and the same key may exist on several levels at
  once (the resolution chain ``user > workspace > global`` reads them side by
  side).

Real database, no mocks: every assertion is made by the PostgreSQL engine, not
by application code — these are exactly the invariants the service-layer must
be able to rely on without re-checking them.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from auth_tenancy.models import (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_USER,
    PREFERENCE_SCOPE_WORKSPACE,
    PreferenceValue,
)

from .conftest import active_tenant


@pytest.mark.django_db
class TestPreferenceValueUniqueness:
    """One row per key and level (the upsert target of every write)."""

    def test_second_global_row_for_the_same_key_is_rejected(self, tenant_a):
        """Two global rows for one (tenant, key) collide on ``uq_prefval_global``."""
        with active_tenant(tenant_a):
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_GLOBAL,
                key="ui.ids.show_readable",
                value=True,
            )
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_GLOBAL,
                        key="ui.ids.show_readable",
                        value=False,
                    )

    def test_second_workspace_row_for_the_same_key_is_rejected(
        self, tenant_a, workspace_a
    ):
        """Two rows for one (tenant, workspace, key) collide."""
        with active_tenant(tenant_a):
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_WORKSPACE,
                workspace=workspace_a,
                key="ui.markdown.toolbar",
                value="off",
            )
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_WORKSPACE,
                        workspace=workspace_a,
                        key="ui.markdown.toolbar",
                        value="on",
                    )

    def test_second_user_row_for_the_same_key_is_rejected(self, tenant_a, user_a):
        """Two rows for one (tenant, user, key) collide."""
        with active_tenant(tenant_a):
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_USER,
                user=user_a,
                key="memory.enabled",
                value=True,
            )
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_USER,
                        user=user_a,
                        key="memory.enabled",
                        value=False,
                    )

    def test_same_key_can_exist_on_every_level_at_once(
        self, tenant_a, user_a, workspace_a
    ):
        """The partial indexes are per level, so the resolution chain can read all three."""
        with active_tenant(tenant_a):
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_GLOBAL,
                key="ui.markdown.toolbar",
                value="auto",
            )
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_WORKSPACE,
                workspace=workspace_a,
                key="ui.markdown.toolbar",
                value="on",
            )
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_USER,
                user=user_a,
                key="ui.markdown.toolbar",
                value="off",
            )

            assert PreferenceValue.objects.filter(
                key="ui.markdown.toolbar"
            ).count() == 3


@pytest.mark.django_db
class TestPreferenceValueScopeTargetInvariant:
    """``ck_prefval_scope_target`` keeps scope and target presence in sync."""

    def test_user_scope_without_user_is_rejected(self, tenant_a):
        """``scope="user"`` without a user would be unreachable and unowned."""
        with active_tenant(tenant_a):
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_USER,
                        key="memory.enabled",
                        value=True,
                    )

    def test_workspace_scope_without_workspace_is_rejected(self, tenant_a):
        """``scope="workspace"`` without a workspace would shadow no workspace."""
        with active_tenant(tenant_a):
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_WORKSPACE,
                        key="ui.markdown.toolbar",
                        value="on",
                    )

    def test_global_scope_with_a_workspace_is_rejected(self, tenant_a, workspace_a):
        """A global row must not carry a workspace (it would be a second workspace row)."""
        with active_tenant(tenant_a):
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_GLOBAL,
                        workspace=workspace_a,
                        key="ui.ids.show_readable",
                        value=True,
                    )

    def test_global_scope_with_a_user_is_rejected(self, tenant_a, user_a):
        """A global row must not carry a user."""
        with active_tenant(tenant_a):
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_GLOBAL,
                        user=user_a,
                        key="ui.ids.show_readable",
                        value=True,
                    )

    def test_workspace_scope_with_a_user_is_rejected(
        self, tenant_a, user_a, workspace_a
    ):
        """A workspace row must not carry a user."""
        with active_tenant(tenant_a):
            with transaction.atomic():
                with pytest.raises(IntegrityError):
                    PreferenceValue.objects.create(
                        tenant=tenant_a,
                        scope=PREFERENCE_SCOPE_WORKSPACE,
                        workspace=workspace_a,
                        user=user_a,
                        key="ui.markdown.toolbar",
                        value="on",
                    )


@pytest.mark.django_db
class TestPreferenceValueValidRows:
    """A valid row per level saves and round-trips its JSON value."""

    def test_valid_row_per_level_saves(self, tenant_a, user_a, workspace_a):
        """One global, one workspace and one user row save independently."""
        with active_tenant(tenant_a):
            global_row = PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_GLOBAL,
                key="ui.ids.show_readable",
                value=True,
            )
            workspace_row = PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_WORKSPACE,
                workspace=workspace_a,
                key="ui.markdown.toolbar",
                value="auto",
            )
            user_row = PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_USER,
                user=user_a,
                key="ui.sidebar.collapsed_groups",
                value=["requirements", "test"],
            )

            assert {row.scope for row in (global_row, workspace_row, user_row)} == {
                PREFERENCE_SCOPE_GLOBAL,
                PREFERENCE_SCOPE_WORKSPACE,
                PREFERENCE_SCOPE_USER,
            }
            assert PreferenceValue.objects.count() == 3

        global_row.refresh_from_db()
        workspace_row.refresh_from_db()
        user_row.refresh_from_db()
        assert global_row.value is True
        assert workspace_row.value == "auto"
        assert user_row.value == ["requirements", "test"]

    def test_row_is_tenant_scoped(self, tenant_a, tenant_b):
        """The same global key may exist once per tenant (tenant is in the index)."""
        with active_tenant(tenant_a):
            PreferenceValue.objects.create(
                tenant=tenant_a,
                scope=PREFERENCE_SCOPE_GLOBAL,
                key="ui.ids.show_readable",
                value=True,
            )
        with active_tenant(tenant_b):
            PreferenceValue.objects.create(
                tenant=tenant_b,
                scope=PREFERENCE_SCOPE_GLOBAL,
                key="ui.ids.show_readable",
                value=False,
            )
            assert PreferenceValue.objects.count() == 1

        with active_tenant(tenant_a):
            assert PreferenceValue.objects.get(
                key="ui.ids.show_readable"
            ).value is True
