"""Flip ``Workspace.goals_enabled`` default to True and enable active workspaces.

Cluster 5, #402 (spec section 5.1). Two parts:

* ``AlterField`` - schema-neutral state change: the model default becomes
  ``True`` so a workspace created without an explicit flag has Goals enabled.
* ``RunPython`` - data backfill: every *active* workspace that still stores
  ``goals_enabled=False`` is switched on. Closed workspaces (``is_active=False``)
  are deliberately left untouched.

RLS: ``pl_workspace`` is FORCE ROW LEVEL SECURITY keyed on
``app.current_tenant``. The data step therefore iterates tenants (``pl_tenant``
is deliberately outside RLS) and arms ``app.current_tenant`` per tenant, exactly
like ``link_types/0005_backfill_goal_reference_pairs``. Inside the armed context
it counts the rows it is about to change and raises if the ``UPDATE`` did not
touch all of them, so a non-``BYPASSRLS`` run that silently matches nothing
fails loudly instead of reporting success.

The models are resolved through ``apps.get_model`` (historical registry), never
through the live ``Workspace``: ``TenantManager.get_queryset`` reads the
thread-local ``TenantContext``, which a migration never sets - arming the DB GUC
does not touch the thread-local - so the live manager would raise
``TenantContextNotSetError``. Historical models carry a plain, unfiltered
manager (see ``0068_requirement_level_cascade_vocabulary`` for the same idiom).

Reverse: the data step is a documented one-way door (``RunPython.noop``) because
nothing records which rows were ``False`` before. The ``AlterField`` reverse
restores the previous default. ``modified_at`` is intentionally not touched -
this is a configuration migration, not a content edit.
"""
from __future__ import annotations

import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def _arm(schema_editor, tenant_id) -> None:
    """Point the RLS policies at *tenant_id* for the rest of this transaction."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])


def _disarm(schema_editor) -> None:
    """Clear the tenant GUC again so no later statement inherits it."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


def enable_goals_for_existing_workspaces(apps, schema_editor):
    """Switch ``goals_enabled`` on for every active workspace that has it off."""
    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")

    total = 0
    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _arm(schema_editor, tenant_id)
            disabled = Workspace.objects.filter(
                tenant_id=tenant_id, is_active=True, goals_enabled=False
            )
            expected = disabled.count()
            updated = disabled.update(goals_enabled=True)
            if updated != expected:
                raise RuntimeError(
                    "goals_enabled backfill for tenant %s: expected %d row(s), "
                    "updated %d - refusing to report a silent no-op."
                    % (tenant_id, expected, updated)
                )
            total += updated
    finally:
        _disarm(schema_editor)

    logger.info(
        "Workspace goals_enabled: enabled for %d active workspace(s).", total
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0099_testcase_origin_reviewed_scenario_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workspace",
            name="goals_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            enable_goals_for_existing_workspaces, migrations.RunPython.noop
        ),
    ]
