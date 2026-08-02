"""Replace the icd_version immutability trigger with a GUC-gated variant.

Problem
-------
``icd.services.delete_icd`` used to run
``ALTER TABLE icd_version DISABLE TRIGGER trg_icd_version_immutable`` around the
cascade delete. ``ALTER TABLE ... DISABLE TRIGGER`` requires **table ownership**.
At runtime the application connects as the least-privilege role
``persistence.db_roles.APP_DB_ROLE`` (see persistence/migrations/0048_app_role.py,
REQ-L2-PL-010), which only holds CRUD grants — the table is owned by the
migration role. ``DELETE /api/v1/icds/{id}/`` therefore failed with
``must be owner of table icd_version``.

Fix
---
Keep the ownership separation intact and move the escape hatch *into* the
trigger function: the function now consults the transaction-local session
variable ``app.allow_icd_version_delete``. Setting a custom (dotted) GUC needs
no special privilege, so the app role can open the gate for exactly the
statements that need it.

Two deliberate properties of this design:

* Only ``DELETE`` is gated. ``UPDATE`` stays unconditionally forbidden — the
  immutability guarantee of REQ-L2-ICD-001 for historical ICD versions is
  unchanged; only the cascade delete of a whole ICD is permitted.
* The gate is transaction-local (``set_config(..., is_local => true)``), so it
  cannot leak onto a pooled connection, and it is per-session rather than
  cluster-wide. ``ALTER TABLE ... DISABLE TRIGGER`` disabled the guard for
  *every concurrent session* and took an ACCESS EXCLUSIVE lock; the GUC does
  neither.

Note on ``RETURN OLD``: in a ``BEFORE DELETE FOR EACH ROW`` trigger, returning
NULL *cancels* the row operation. The allow-path must therefore return ``OLD``,
otherwise the DELETE would silently affect zero rows.

req_id: REQ-066, REQ-L2-ICD-001, REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

GUARDED_FUNCTION = """
CREATE OR REPLACE FUNCTION icd_raise_version_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'IcdVersion records are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        -- Transaction-local escape hatch used by icd.services.delete_icd.
        -- current_setting(..., true) returns NULL when the GUC is unset.
        IF current_setting('app.allow_icd_version_delete', true) = 'true' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'IcdVersion records are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

ORIGINAL_FUNCTION = """
CREATE OR REPLACE FUNCTION icd_raise_version_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'IcdVersion records are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'IcdVersion records are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("icd", "0005_alter_icdversion_interface_type_icdparameter"),
    ]

    operations = [
        migrations.RunSQL(sql=GUARDED_FUNCTION, reverse_sql=ORIGINAL_FUNCTION),
    ]
