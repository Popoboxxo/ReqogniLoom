"""B-0023 — ``fk_we_state_workspace`` must cascade at the database level.

The bug
-------
``workflow/0021_we_item_state_integrity`` installed the physical FK
``fk_we_state_workspace`` as::

    FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id")
    DEFERRABLE INITIALLY DEFERRED          -- confdeltype ''a'' = NO ACTION

The migration's own docstring (0021, lines 13-18) *claims* ``ON DELETE
CASCADE``, and the ORM model already declares it
(``workflow.models.WorkflowItemState.workspace`` uses
``on_delete=models.CASCADE``) — but the physical constraint never carried it.
The two layers therefore disagree, and only the ORM half is correct.

Consequence (orphan recurrence): a raw ``DELETE FROM pl_workspace`` — a DB-level
cleanup, a truncation, an operator script, any writer that bypasses the Django
ORM — is rejected for workspaces that still have ``we_item_state`` rows, or (with
the FK disabled/dropped during maintenance) leaves those rows behind as orphans.
The very orphan rows 0021/0022 had to clean up were produced by exactly that
divergence. After this migration the database enforces the cascade itself, so
application-level and database-level cascade can no longer disagree.

What this migration installs
----------------------------
The same named constraint, raised to
``ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED`` — matching 0022's treatment
of ``fk_we_engine_definition_workspace`` and the model field. ``DEFERRABLE
INITIALLY DEFERRED`` is preserved so the existing transaction/commit semantics
(and the trigger/state ordering) are unchanged.

Why ``SeparateDatabaseAndState`` with empty ``state_operations``
---------------------------------------------------------------
Django's migration *state* is already correct: the model field has carried
``on_delete=CASCADE`` since 0021. Only the physical constraint diverges, so no
model state operation is emitted (``state_operations=[]``) — which also keeps
``manage.py makemigrations --check`` clean. The DDL is hand-written through a
``RunSQL`` pair instead of ``AlterField`` so the column name ``workspace_id`` is
never touched.

Ordering safety — the in-migration orphan pre-step
--------------------------------------------------
``RunPython(delete_workspace_orphans_before_fk, ...)`` runs **before** the
``ADD CONSTRAINT``: a validated ``ADD CONSTRAINT`` re-checks every existing row,
so a database that still carries a workspace-orphaned ``we_item_state`` row would
abort the whole transaction. It reuses
:func:`workflow.workspace_orphans.delete_workspace_orphans` — the same core as
the operator-facing ``cleanup_workflow_orphans`` command and 0022's pre-step — so
the paths cannot drift. The step is idempotent (``DELETE ... WHERE NOT EXISTS``)
and a no-op on a fresh database (tables introspected first); its reverse is a
documented no-op, because the deleted rows are unreachable legacy data whose loss
the operator accepted (decision 2026-10-08).

Reversibility
-------------
Forward is idempotent/re-runnable (``DROP CONSTRAINT IF EXISTS`` followed by the
re-``ADD``). The reverse drops the cascade constraint and re-adds the *identical*
constraint **without** cascade, restoring the exact pre-0023 shape.
"""

from __future__ import annotations

import logging

from django.db import migrations

from workflow.workspace_orphans import (
    ENGINE_DEFINITION_TABLE,
    ITEM_STATE_TABLE,
    delete_workspace_orphans,
)

FK_NAME = "fk_we_state_workspace"
TABLE = "we_item_state"

#: Forward DDL: drop the cascade-less constraint (if present) and re-add it with
#: a database-level ``ON DELETE CASCADE``. Idempotent/re-runnable.
DROP_FK = f'ALTER TABLE "{TABLE}" DROP CONSTRAINT IF EXISTS "{FK_NAME}";'
ADD_FK = (
    f'ALTER TABLE "{TABLE}" '
    f'ADD CONSTRAINT "{FK_NAME}" '
    'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
    "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;"
)

#: Reverse DDL: the exact pre-0023 constraint — same name and deferrability,
#: but **without** cascade (``confdeltype`` back to ``NO ACTION``).
ADD_FK_NO_CASCADE = (
    f'ALTER TABLE "{TABLE}" '
    f'ADD CONSTRAINT "{FK_NAME}" '
    'FOREIGN KEY ("workspace_id") REFERENCES "pl_workspace" ("id") '
    "DEFERRABLE INITIALLY DEFERRED;"
)


def delete_workspace_orphans_before_fk(apps, schema_editor):
    """Remove the rows that would make the ``ADD CONSTRAINT`` below fail.

    Mirrors ``workflow/0022``'s pre-step: ``ADD CONSTRAINT`` re-validates every
    existing row, so a workspace-orphaned ``we_item_state`` row aborts the whole
    migration transaction. Reuses the shared
    :func:`workflow.workspace_orphans.delete_workspace_orphans` core (same code
    as the ``cleanup_workflow_orphans`` command) and logs the deletion loudly.

    Because the ``DELETE`` and the ``ALTER TABLE`` below share one migration
    transaction, the deferred FK triggers the deletes queued (``we_item_state``
    is referenced by ``we_history_entry.item_state_id``, and every ``we_*`` FK is
    ``DEFERRABLE INITIALLY DEFERRED``) must be forced to run **before** the DDL:
    PostgreSQL otherwise rejects the ``ALTER TABLE`` with "cannot ALTER TABLE
    because it has pending trigger events". ``SET CONSTRAINTS ALL IMMEDIATE``
    flushes that queue inside the transaction; the referenced rows are valid, so
    the checks pass.
    """
    deleted = delete_workspace_orphans(schema_editor.connection)
    if any(deleted.values()):
        logging.getLogger(__name__).warning(
            "B-0023 preflight: deleted workspace orphans before re-adding %s "
            "(we_item_state=%s, we_engine_definition=%s). Irreversible and "
            "accepted by the operator decision of 2026-10-08.",
            FK_NAME,
            deleted[ITEM_STATE_TABLE],
            deleted[ENGINE_DEFINITION_TABLE],
        )
    # Flush deferred FK checks queued by the DELETEs so the ADD/DROP below can
    # run in the same transaction (see docstring).
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def noop_reverse(apps, schema_editor):
    """Documented no-op — deleted orphan rows cannot be restored."""


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0022_we_engine_definition_workspace_fk"),
    ]

    operations = [
        # 1. Data: remove what would block the re-validating ADD CONSTRAINT.
        migrations.RunPython(delete_workspace_orphans_before_fk, noop_reverse),
        # 2. Physical DDL only — the model state already carries
        #    ``on_delete=CASCADE`` (since 0021), hence ``state_operations=[]``.
        #    The DROP-then-ADD pair makes the step idempotent; its reverse
        #    restores the non-cascade constraint byte-for-byte.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=[DROP_FK, ADD_FK],
                    reverse_sql=[DROP_FK, ADD_FK_NO_CASCADE],
                ),
            ],
            state_operations=[],
        ),
    ]
