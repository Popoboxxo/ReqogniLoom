"""Migration 0023: rebase ``ChangeRequestAffectedItem`` on ``TenantScopedModel``.

Datenmodell-Konsolidierung Phase 2, Task 15b — the follow-up ``0022`` deferred.

Why this one is not the state-only move ``0022`` was
====================================================
``0022`` could rename six models' existing ``tenant_id`` / ``created_by_id`` /
``modified_by_id`` UUID columns into FKs because Task 14 (``0021``) had already
created them. ``ChangeRequestAffectedItem`` never went through Task 14, so it
genuinely *lacks* four of the ``AuditableModel`` columns:

    version        -> new, NOT NULL, DEFAULT 1
    modified_at    -> new, NOT NULL (auto_now)
    created_by_id  -> new, nullable FK -> pl_user
    modified_by_id -> new, nullable FK -> pl_user

Those are plain ``AddField``\\ s. Only ``tenant_id`` already exists (declared by
``0014`` as a denormalised UUID column so the RLS policy could apply), so only
*it* needs ``0022``'s pin -> rename -> alter idiom:

  1. ``AlterField`` pinning ``db_column="tenant_id"``, so that
  2. ``RenameField`` sees ``old_field.column == new_field.column`` and skips the
     physical ``ALTER TABLE ... RENAME COLUMN``, and
  3. ``AlterField`` to the real FK, whose attname/column is identical again — so
     the only DDL that runs is ``ADD CONSTRAINT ... FOREIGN KEY``.

The physical ``tenant_id`` column therefore survives byte-for-byte and the
``as_change_request_affected_item_tenant_isolation`` RLS policy from ``0014``
(written against the column, not the Django field) keeps matching. No policy
migration is required.

Orphan guard
============
Only ``tenant_id`` can carry a pre-existing orphan: the other two FKs are new
columns and are therefore NULL on every row. The guard runs before the FK
constraint so a bad row is reported by id instead of aborting the migration
mid-flight on a ``ForeignKeyViolation``.

``modified_at`` backfill
========================
``AddField`` needs a one-off default for a NOT NULL column, which would stamp
every historical row with the migration's wall-clock time. The ``RunPython``
copies ``updated_at`` over it instead — the truthful value, and the same
source ``0021`` used for the six siblings. ``QuerySet.update()`` never fires
``auto_now``, so the copy is not immediately overwritten.

leaf_id : COMP-AS-021, COMP-PL-001, COMP-PL-002
req_id  : REQ-157, REQ-L2-PL-001, REQ-L3-PL002-001, REQ-L3-PL002-003,
          REQ-L2-PL-009, REQ-L2-PL-010
"""
from __future__ import annotations

import django.db.models.deletion
import django.db.models.manager
import django.utils.timezone
from django.db import migrations, models

_MODEL = "changerequestaffecteditem"
_TENANT_INDEX = "idx_cr_affected_tenant"


def _guard_tenants_and_backfill_modified_at(apps_registry, schema_editor):
    """Reject orphaned tenants, then set ``modified_at`` from ``updated_at``.

    Args:
        apps_registry: Historical app registry supplied by ``RunPython``.
        schema_editor: Unused; required by the ``RunPython`` signature.

    Raises:
        RuntimeError: A row references a ``tenant_id`` that has no ``Tenant``.
            Reported in full rather than one-at-a-time by Postgres, and raised
            *before* the FK constraint so nothing is half-applied.
    """
    Tenant = apps_registry.get_model("persistence", "Tenant")
    model = apps_registry.get_model("application", "ChangeRequestAffectedItem")
    # Historical models carry a plain auto-created manager: TenantManager /
    # UnscopedManager set no ``use_in_migrations``, so migration state never
    # captures them and this runs without needing a TenantContext.
    known = set(Tenant.objects.values_list("id", flat=True))
    orphans = sorted(
        str(value)
        for value in set(model.objects.values_list("tenant_id", flat=True))
        if value is not None and value not in known
    )
    if orphans:
        raise RuntimeError(
            f"ChangeRequestAffectedItem.tenant_id references unknown ids "
            f"{orphans}; clean these rows before adding the FK constraint."
        )

    model.objects.update(modified_at=models.F("updated_at"))


def _user_fk():
    """AuditableModel.created_by / .modified_by (persistence/models.py)."""
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="+",
        to="persistence.user",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0022_tenant_scoped_base"),
        # Supplies Tenant and User, the three FK targets.
        ("persistence", "0070_drop_status_mirror_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name=_MODEL,
            name="version",
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name=_MODEL,
            name="modified_at",
            # ``preserve_default=False``: the one-off default exists only to
            # populate existing rows; the model field is a bare ``auto_now``.
            field=models.DateTimeField(
                auto_now=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name=_MODEL, name="created_by", field=_user_fk()
        ),
        migrations.AddField(
            model_name=_MODEL, name="modified_by", field=_user_fk()
        ),
        migrations.RunPython(
            _guard_tenants_and_backfill_modified_at, migrations.RunPython.noop
        ),
        # RemoveIndex resolves the index by name out of from_state, so it must
        # run while that state still records ``fields=["tenant_id"]``.
        migrations.RemoveIndex(model_name=_MODEL, name=_TENANT_INDEX),
        migrations.AlterField(
            model_name=_MODEL,
            name="tenant_id",
            field=models.UUIDField(db_column="tenant_id", db_index=True),
        ),
        migrations.RenameField(
            model_name=_MODEL, old_name="tenant_id", new_name="tenant"
        ),
        migrations.AlterField(
            model_name=_MODEL,
            name="tenant",
            # ``related_name`` stays the unresolved ``%(class)s_set`` and
            # ``db_index`` is omitted (True is the ForeignKey default) — that is
            # exactly what ``ForeignKey.deconstruct()`` emits for
            # ``TenantScopedModel.tenant``, so ``makemigrations --check`` stays
            # clean.
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(class)s_set",
                to="persistence.tenant",
            ),
        ),
        migrations.AddIndex(
            model_name=_MODEL,
            index=models.Index(fields=["tenant"], name=_TENANT_INDEX),
        ),
        # State-only, emits no SQL. ModelState records the default and base
        # managers as plain shims (TenantManager/UnscopedManager set no
        # ``use_in_migrations``). ``unscoped`` newly appears here because
        # TenantScopedModel.Meta.base_manager_name promotes it to the base
        # manager — before this migration it was neither default nor base, so
        # ModelState skipped it. Historical models keep an unfiltered manager
        # either way, which is what the RunPython above relies on.
        migrations.AlterModelManagers(
            name=_MODEL,
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]
