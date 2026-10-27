"""auth_tenancy — backfill ``show_readable_ids`` into Q1 ``PreferenceValue``.

Plan C, T-C2-6 (PR-C7a), ENT-C5 = A: only ``show_readable_ids`` leaves the
``UserDisplayPreference`` column for the generic three-level preference store
(``ui.ids.show_readable``, registry default ``True``). Every account created
before the release only carries the legacy column, so this migration copies the
signal that matters — "this user hid readable ids" — into a user-scope row. A
``True`` row is deliberately not copied: ``True`` *is* the registry default, so
an absent row resolves to the same value and there is nothing to keep in sync.

Reverse
-------
The reverse direction is not "delete what the forward created": a revert
restores the column as the authoritative store, and a user may have changed the
value between the forward run and the revert. It therefore writes **every**
user-scope ``ui.ids.show_readable`` value back into the column (creating the
display row when the user never had one) and only then deletes the
``PreferenceValue`` rows — so a revert never loses a user's choice.

Idempotent
----------
Forward uses ``get_or_create`` (an existing row — e.g. one written by the
generic preference UI after the release — is never overwritten) and the reverse
uses ``update_or_create`` plus a delete, so a re-run of either direction is
safe.

RLS
---
Both tables carry ``ENABLE + FORCE ROW LEVEL SECURITY``
(``0020_user_display_preference_rls``, ``0030_preferencevalue_rls``). The
sanctioned ``migrate`` service connects as ``DB_USER`` (the Postgres
superuser), for which the ``SET LOCAL row_security = off`` below is a no-op.
On a ``NOSUPERUSER`` connection (e.g. ``docker compose exec backend python
manage.py migrate``) the same statement makes the affected query raise instead
of silently matching zero rows — which matters here because a silently empty
reverse would leave the column stale and drop every post-release choice.
"""
from __future__ import annotations

from django.db import connection, migrations

#: Registered key in ``application/preference_registry.py``.
KEY = "ui.ids.show_readable"

_SCOPE_USER = "user"


def _disable_rls_for_this_transaction() -> None:
    """Fail loudly instead of silently reading zero rows (see module docstring)."""
    with connection.cursor() as cursor:
        # ``row_security = off`` is transaction-local; RunPython always runs
        # inside the migration's transaction, so it cannot leak into later work.
        cursor.execute("SET LOCAL row_security = off")


def backfill_show_readable_ids(apps, schema_editor) -> None:
    """Create one user-scope ``False`` row per legacy hidden preference."""
    Display = apps.get_model("auth_tenancy", "UserDisplayPreference")
    PreferenceValue = apps.get_model("auth_tenancy", "PreferenceValue")

    _disable_rls_for_this_transaction()

    hidden = Display.objects.filter(show_readable_ids=False).values_list(
        "user_id", "tenant_id"
    )
    for user_id, tenant_id in hidden.iterator():
        PreferenceValue.objects.get_or_create(
            tenant_id=tenant_id,
            scope=_SCOPE_USER,
            user_id=user_id,
            key=KEY,
            defaults={"value": False},
        )


def restore_show_readable_ids(apps, schema_editor) -> None:
    """Write every user-scope value back into the column, then delete the rows."""
    Display = apps.get_model("auth_tenancy", "UserDisplayPreference")
    PreferenceValue = apps.get_model("auth_tenancy", "PreferenceValue")

    _disable_rls_for_this_transaction()

    stored = PreferenceValue.objects.filter(scope=_SCOPE_USER, key=KEY).values_list(
        "user_id", "tenant_id", "value"
    )
    for user_id, tenant_id, value in stored.iterator():
        # A hand-edited non-bool cannot represent a choice; fall back to the
        # registry default (visible) instead of guessing.
        restored = value if isinstance(value, bool) else True
        Display.objects.update_or_create(
            user_id=user_id,
            defaults={"tenant_id": tenant_id, "show_readable_ids": restored},
        )

    PreferenceValue.objects.filter(scope=_SCOPE_USER, key=KEY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0030_preferencevalue_rls"),
    ]

    operations = [
        migrations.RunPython(
            backfill_show_readable_ids,
            restore_show_readable_ids,
        ),
    ]
