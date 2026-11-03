"""``auth_tenancy/0033`` drops ``UserDisplayPreference.show_readable_ids``.

Plan C T-C2-9. ``0031`` already copied the flag into Q1 and
``DisplayPreferenceService`` reads only Q1, so the column is dead weight. The
contract migration must still be reversible:

* forward removes the column and leaves the Q1 rows untouched;
* reverse recreates the column (historical ``BooleanField(default=True)``) and
  copies every user-scope Q1 value back — including users who never had a
  display row and only ever wrote the toggle after the release;
* the Q1 rows survive the reverse (state ``0032`` still has ``0031`` applied,
  where Q1 is authoritative).

Real ``MigrationExecutor``, targets addressed by migration *name*.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

PRE_TARGET = ("auth_tenancy", "0032_user_mfa")
TARGET = ("auth_tenancy", "0033_drop_userdisplaypreference_show_readable_ids")

TABLE = "at_user_display_preference"
KEY = "ui.ids.show_readable"


def _columns() -> set[str]:
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, TABLE)
        }


def _migrate(target) -> MigrationExecutor:
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    executor.loader.build_graph()
    return executor


def _make_account(apps, label: str):
    Tenant = apps.get_model("persistence", "Tenant")
    User = apps.get_model("persistence", "User")
    slug = f"{label}-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=slug, slug=slug, is_active=True)
    user = User.objects.create(
        username=slug, email=f"{slug}@t.test", tenant_id=tenant.pk
    )
    return tenant, user


@pytest.mark.django_db(transaction=True)
class TestDropShowReadableIdsColumn:
    def test_forward_drops_and_reverse_restores_from_q1(self) -> None:
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            before = _migrate(PRE_TARGET).loader.project_state(PRE_TARGET).apps
            Display = before.get_model("auth_tenancy", "UserDisplayPreference")
            PreferenceValue = before.get_model("auth_tenancy", "PreferenceValue")

            # User A: the normal post-0031 shape, column + Q1 row agree.
            tenant_a, user_a = _make_account(before, "legacy")
            Display.objects.create(
                user_id=user_a.pk, tenant_id=tenant_a.pk, show_readable_ids=False
            )
            PreferenceValue.objects.create(
                tenant_id=tenant_a.pk,
                scope="user",
                user_id=user_a.pk,
                key=KEY,
                value=False,
            )

            # User B: post-release only — no display row, Q1 holds the choice.
            tenant_b, user_b = _make_account(before, "q1-only")
            PreferenceValue.objects.create(
                tenant_id=tenant_b.pk,
                scope="user",
                user_id=user_b.pk,
                key=KEY,
                value=False,
            )

            assert "show_readable_ids" in _columns()

            _migrate(TARGET)
            assert "show_readable_ids" not in _columns()
            current = MigrationExecutor(connection).loader.project_state(TARGET).apps
            assert (
                current.get_model("auth_tenancy", "PreferenceValue")
                .objects.filter(key=KEY)
                .count()
                == 2
            )

            after = _migrate(PRE_TARGET).loader.project_state(PRE_TARGET).apps
            assert "show_readable_ids" in _columns()

            RestoredDisplay = after.get_model(
                "auth_tenancy", "UserDisplayPreference"
            )
            assert (
                RestoredDisplay.objects.get(user_id=user_a.pk).show_readable_ids
                is False
            )
            recreated = RestoredDisplay.objects.get(user_id=user_b.pk)
            assert recreated.show_readable_ids is False
            assert recreated.tenant_id == tenant_b.pk
            # Q1 rows survive: state 0032 still has 0031 applied.
            assert (
                after.get_model("auth_tenancy", "PreferenceValue")
                .objects.filter(key=KEY)
                .count()
                == 2
            )
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_forward_keeps_a_visible_default_row_untouched(self) -> None:
        """``True`` needs no Q1 row; the recreated column defaults to ``True``."""
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            before = _migrate(PRE_TARGET).loader.project_state(PRE_TARGET).apps
            tenant, user = _make_account(before, "visible")
            before.get_model("auth_tenancy", "UserDisplayPreference").objects.create(
                user_id=user.pk, tenant_id=tenant.pk, show_readable_ids=True
            )

            _migrate(TARGET)
            after = _migrate(PRE_TARGET).loader.project_state(PRE_TARGET).apps
            assert (
                after.get_model("auth_tenancy", "UserDisplayPreference")
                .objects.get(user_id=user.pk)
                .show_readable_ids
                is True
            )
        finally:
            MigrationExecutor(connection).migrate(latest)
