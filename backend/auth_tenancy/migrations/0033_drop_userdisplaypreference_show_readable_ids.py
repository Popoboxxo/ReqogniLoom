"""auth_tenancy — drop ``UserDisplayPreference.show_readable_ids`` (contract).

Plan C T-C2-9, ENT-C5 = A. ``0031_backfill_show_readable_ids`` copied the flag
into the generic three-level preference store (``ui.ids.show_readable``) and
``application.display_preference_service`` has read Q1 — never this column —
since T-C2-6. The column is the last consumer-less remnant, so this migration
removes it.

Reverse
-------
The reverse direction recreates the column with its historical definition
(``BooleanField(default=True)`` — Django's ``RemoveField`` reverse restores it
and fills existing rows with the default) and then copies the user-scope Q1
values back into it. A user who changed the toggle after the release must find
their choice intact after a code revert.

The ``PreferenceValue`` rows are deliberately **not** deleted on reverse: the
target state (``0032_user_mfa``) still has ``0031`` applied, where Q1 remains
the authoritative store and the recreated column is the compatibility copy.
``0031``'s own reverse is the migration that deletes them.

Ordering: ``RunPython`` sits FIRST in ``operations`` because Django reverses
the list — the columns exist again by the time the backfill runs.

RLS
---
``at_user_display_preference`` and ``at_preference_value`` both carry
``ENABLE + FORCE ROW LEVEL SECURITY``. The sanctioned ``migrate`` service
connects as ``DB_USER`` (superuser), for which ``SET LOCAL row_security = off``
is a no-op; on a ``NOSUPERUSER`` connection it makes the query raise instead of
silently matching zero rows (same reasoning as ``0031``).
"""
from __future__ import annotations

from django.db import connection, migrations

#: Registered key in ``application/preference_registry.py``.
KEY = "ui.ids.show_readable"

_SCOPE_USER = "user"


def _disable_rls_for_this_transaction() -> None:
    """Fail loudly instead of silently reading zero rows (see module docstring)."""
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def restore_show_readable_ids(apps, schema_editor) -> None:
    """Copy every user-scope Q1 value back into the recreated column."""
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


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0032_user_mfa"),
    ]

    operations = [
        # Must stay first: on reverse the column is recreated by the
        # RemoveField below (run backwards) before this backfill runs.
        migrations.RunPython(migrations.RunPython.noop, restore_show_readable_ids),
        migrations.RemoveField(
            model_name="userdisplaypreference",
            name="show_readable_ids",
        ),
    ]
