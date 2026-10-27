"""Backfill of ``show_readable_ids`` into Q1 ``PreferenceValue`` (Plan C, T-C2-6).

``DisplayPreferenceService`` stops serving ``show_readable_ids`` from the
``UserDisplayPreference`` column and reads it through the three-level Q1 store
instead. Existing accounts only carry the *legacy* column, so the migration
``0031_backfill_show_readable_ids`` copies every ``show_readable_ids = False``
row into a user-scope ``PreferenceValue``. ``True`` needs no row: the registry
default is ``True``.

The reverse direction is not a plain "delete what I created" — a revert must not
lose a user's choice, so it writes every user-scope value back into the column
(creating the display row when the user never had one) and only then deletes the
``PreferenceValue`` rows.

Both directions are exercised through the real ``MigrationExecutor`` so the test
proves the migration as written, not a re-implementation of it. Targets are
migration *names*, never bare numbers: appending a migration must not silently
retarget this test.
"""
from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

#: State before the backfill (RLS for ``at_preference_value`` is already in place).
PRE_TARGET = ("auth_tenancy", "0030_preferencevalue_rls")
TARGET = ("auth_tenancy", "0031_backfill_show_readable_ids")

KEY = "ui.ids.show_readable"
_MIGRATION = importlib.import_module(
    "auth_tenancy.migrations.0031_backfill_show_readable_ids"
)


def _apps(executor: MigrationExecutor, target: tuple[str, str]):
    """Return the historical app registry as of *target*."""
    return executor.loader.project_state([target]).apps


def _make_account(apps, label: str):
    """Create one tenant + user; return ``(tenant, user)`` (historical models)."""
    Tenant = apps.get_model("persistence", "Tenant")
    User = apps.get_model("persistence", "User")
    slug = f"{label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    user = User.objects.create(
        username=slug, email=f"{slug}@t.test", tenant_id=tenant.pk
    )
    return tenant, user


def _make_display_row(apps, *, show_readable_ids: bool):
    """Seed one legacy ``UserDisplayPreference`` row; return ``(tenant, user)``."""
    tenant, user = _make_account(apps, "display")
    Display = apps.get_model("auth_tenancy", "UserDisplayPreference")
    Display.objects.create(
        user_id=user.pk,
        tenant_id=tenant.pk,
        show_readable_ids=show_readable_ids,
    )
    return tenant, user


@pytest.mark.django_db(transaction=True)
class TestBackfillShowReadableIds:
    """Forward and reverse behaviour of ``0031_backfill_show_readable_ids``."""

    @staticmethod
    def _latest(executor: MigrationExecutor):
        return executor.loader.graph.leaf_nodes()

    def test_forward_moves_hidden_preferences_into_user_rows(self) -> None:
        """Only ``False`` rows are copied; the registry default covers ``True``."""
        latest = self._latest(MigrationExecutor(connection))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()
            before = _apps(executor, PRE_TARGET)
            hidden_tenant, hidden_user = _make_display_row(
                before, show_readable_ids=False
            )
            _, visible_user = _make_display_row(before, show_readable_ids=True)

            executor = MigrationExecutor(connection)
            executor.migrate([TARGET])
            executor.loader.build_graph()

            PreferenceValue = _apps(executor, TARGET).get_model(
                "auth_tenancy", "PreferenceValue"
            )
            rows = list(PreferenceValue.objects.filter(key=KEY))

            assert len(rows) == 1, "exactly the hidden preference is backfilled"
            row = rows[0]
            assert (row.scope, row.user_id, row.tenant_id) == (
                "user",
                hidden_user.pk,
                hidden_tenant.pk,
            )
            assert row.workspace_id is None
            assert row.value is False
            assert not PreferenceValue.objects.filter(user_id=visible_user.pk).exists()
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_reverse_restores_the_column_and_keeps_post_deploy_choices(self) -> None:
        """A revert writes every user value back and deletes the Q1 rows."""
        latest = self._latest(MigrationExecutor(connection))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()
            before = _apps(executor, PRE_TARGET)
            _, hidden_user = _make_display_row(before, show_readable_ids=False)
            _, visible_user = _make_display_row(before, show_readable_ids=True)

            executor = MigrationExecutor(connection)
            executor.migrate([TARGET])
            executor.loader.build_graph()
            forward = _apps(executor, TARGET)
            PreferenceValue = forward.get_model("auth_tenancy", "PreferenceValue")

            # A choice made *after* the release: this user never had a display
            # row, so only Q1 knows about it and the revert must recreate one.
            q1_tenant, q1_only_user = _make_account(forward, "q1-only")
            PreferenceValue.objects.create(
                tenant_id=q1_tenant.pk,
                scope="user",
                user_id=q1_only_user.pk,
                key=KEY,
                value=False,
            )

            executor = MigrationExecutor(connection)
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()
            after = _apps(executor, PRE_TARGET)

            Display = after.get_model("auth_tenancy", "UserDisplayPreference")
            HistoricalPreference = after.get_model("auth_tenancy", "PreferenceValue")

            assert Display.objects.get(user_id=hidden_user.pk).show_readable_ids is False
            assert Display.objects.get(user_id=visible_user.pk).show_readable_ids is True
            recreated = Display.objects.get(user_id=q1_only_user.pk)
            assert recreated.show_readable_ids is False
            assert recreated.tenant_id == q1_tenant.pk
            assert not HistoricalPreference.objects.filter(key=KEY).exists()
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_forward_is_idempotent(self) -> None:
        """Running the forward function twice creates no duplicate rows."""
        latest = self._latest(MigrationExecutor(connection))
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()
            before = _apps(executor, PRE_TARGET)
            _, hidden_user = _make_display_row(before, show_readable_ids=False)

            _MIGRATION.backfill_show_readable_ids(before, None)
            _MIGRATION.backfill_show_readable_ids(before, None)

            PreferenceValue = before.get_model("auth_tenancy", "PreferenceValue")
            assert PreferenceValue.objects.filter(key=KEY).count() == 1
            assert PreferenceValue.objects.get(key=KEY).user_id == hidden_user.pk
        finally:
            MigrationExecutor(connection).migrate(latest)
