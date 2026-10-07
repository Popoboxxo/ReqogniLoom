"""GUC-gated DELETE exception for baselines (GH-1199).

``bl_raise_immutable`` (``0001_initial.py``) raises unconditionally on every
UPDATE *and* DELETE, so a baseline could never be removed — not by the
workspace cascade (which is why #1084 refused the whole delete), and not by any
administrative path. That left two endpoints contradicting each other: the
baseline DELETE answered "cannot be deleted", while the workspace DELETE
answered "remove them first" for something that had no reachable removal path
at all.

The administrative answer (GH-1199) is an admin-only, audited
``purge_baseline`` that deletes the snapshot together with its delta entries.
Because the runtime role must not (and cannot) run ``ALTER TABLE ... DISABLE
TRIGGER`` — that is owner-only DDL, see the repo pattern in
``docs/superpowers/plans/2026-09-03-dokumentensicht.md`` — the bypass is a
transaction-local GUC read from inside the trigger function:

    SELECT set_config('app.baseline_admin_delete', 'true', true)

``is_local=true`` makes it evaporate with the transaction, and setting a dotted
custom GUC needs no privilege. The exception is as narrow as possible:

  * UPDATE keeps raising unconditionally — content immutability is untouched.
  * DELETE raises unless the GUC is ``'true'`` in the current transaction.
  * only ``application.baseline_facade.BaselineFacade.purge_baseline`` (admin
    role required, audit entry written) ever sets it.

The function is shared by ``bl_baseline_snapshot`` and
``bl_delta_index_entry``; the trigger objects themselves are unchanged, so
their ``CREATE OR REPLACE FUNCTION`` binding keeps working across this
migration. DELETE is deliberately not scoped per-table: the ORM collector
removes the delta entries and the snapshot in one transaction under the same
GUC.
"""
from __future__ import annotations

from django.db import migrations

#: Transaction-local GUC the admin purge sets before deleting. The dotted name
#: needs no privilege and is scoped to the transaction (``is_local=true``).
ADMIN_DELETE_GUC = "app.baseline_admin_delete"

_ALLOW_ADMIN_DELETE_FN = f"""
CREATE OR REPLACE FUNCTION bl_raise_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        IF coalesce(current_setting('{ADMIN_DELETE_GUC}', true), '') = 'true' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'Baselines are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_ORIGINAL_FN = """
CREATE OR REPLACE FUNCTION bl_raise_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Baselines are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("baseline", "0010_baseline_delta_index_entry_rls"),
    ]

    operations = [
        migrations.RunSQL(sql=_ALLOW_ADMIN_DELETE_FN, reverse_sql=_ORIGINAL_FN),
    ]
