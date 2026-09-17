"""Migration 0022: rebase the six Layer-2 models on ``TenantScopedModel``.

Datenmodell-Konsolidierung Phase 2, Task 15. ``Adr``, ``Risk``, ``Goal``,
``MainGoal``, ``Issue`` and ``ChangeRequest`` stop declaring their own ``id`` /
``version`` / ``created_at`` / ``modified_at`` / ``tenant_id`` /
``created_by_id`` / ``modified_by_id`` and inherit them from
``persistence.models.TenantScopedModel`` instead.

Hand-written on purpose — ``makemigrations`` cannot produce this correctly
=========================================================================
Three fields change their Django *name* while keeping their physical column:

    tenant_id       (UUIDField) -> tenant       (FK, attname ``tenant_id``)
    created_by_id   (UUIDField) -> created_by   (FK, attname ``created_by_id``)
    modified_by_id  (UUIDField) -> modified_by  (FK, attname ``modified_by_id``)

``AlterField`` requires a stable field name, so the autodetector sees the old
name disappear and a new one appear and emits ``RemoveField`` + ``AddField`` —
which would **drop the tenant of every row**. Verified, not assumed: a
non-interactive ``makemigrations application --dry-run`` on this model state
answers

    Field 'tenant' on model 'adr' not migrated: it is impossible to add a
    non-nullable field without specifying a default.

i.e. it is treating ``tenant`` as a brand-new column.

Each rename therefore uses the pin -> rename -> alter idiom (the same one
``0021_reconcile_audit_fields`` used for ``created_by`` -> ``created_by_name``):

  1. ``AlterField`` pinning ``db_column`` to the existing column, so that
  2. ``RenameField`` finds ``old_field.column == new_field.column`` and skips
     the physical ``ALTER TABLE ... RENAME COLUMN`` entirely, and
  3. ``AlterField`` to the real FK, whose attname/column is identical again —
     so the only DDL that actually runs is ``ADD CONSTRAINT ... FOREIGN KEY``.

Zero data movement. The RLS policies on ``as_adr`` / ``as_risk`` / ``as_issue``
/ ``as_goal`` / ``as_main_goal`` / ``as_change_request``
(``application/0009``, ``0013``) are written against the physical ``tenant_id``
column, which this migration preserves byte-for-byte, so they keep matching and
no policy change is required.

``Meta.indexes`` must move from the attname to the field name
=============================================================
``models.Index(fields=["tenant_id", ...])`` resolves while ``tenant_id`` is a
real field, but once it is only an FK *attname* the two Django code paths
disagree: ``Model._check_indexes`` accepts an attname (its lookup map is built
from both ``field.name`` and ``field.attname``), whereas ``Index.create_sql``
calls ``Options.get_field``, which is keyed on ``field.name`` only and raises
``FieldDoesNotExist``. A stale ``tenant_id`` there would therefore pass
``manage.py check`` and fail during ``migrate``. The four composite indexes are
dropped and recreated against ``tenant``; same name, same columns.

``ChangeRequestAffectedItem`` is deliberately out of scope: it never received
the Task-14 audit-field reconciliation, so moving it needs its own
column-adding migration (split into a follow-up task).

leaf_id : COMP-PL-001, COMP-PL-002
req_id  : REQ-L2-PL-001, REQ-L3-PL002-001, REQ-L3-PL002-003, REQ-L2-PL-009
"""
from __future__ import annotations

import django.db.models.deletion
import django.db.models.manager
from django.db import migrations, models

#: The six models moved by this migration, as Django model_name (lowercased).
_MODELS = ("adr", "risk", "goal", "maingoal", "issue", "changerequest")

#: Composite ``(tenant, workspace)`` indexes that must be re-pointed from the
#: ``tenant_id`` attname to the ``tenant`` field. Goal/MainGoal index only
#: workspace-side columns and need no rewrite.
_TENANT_INDEXES = {
    "adr": "idx_adr_tenant_ws",
    "risk": "idx_risk_tenant_ws",
    "issue": "idx_issue_tenant_ws",
    "changerequest": "idx_cr_tenant_ws",
}


def _assert_no_orphan_refs_and_backfill(apps_registry, schema_editor):
    """Fail loudly *before* the FK constraints are added, not during them.

    Three hard FKs land in this migration (``tenant`` -> Tenant,
    ``created_by`` / ``modified_by`` -> User). A single row pointing at a
    non-existent id would abort the migration halfway through on exactly the
    environments that already carry data, so the references are checked up
    front and reported in full rather than one-at-a-time by Postgres.

    Also tops up ``modified_at``: the base class declares it NOT NULL, and the
    ``AlterField`` below emits ``SET NOT NULL``. ``0021`` already backfilled
    every row that existed then, and ``auto_now`` has covered every insert
    since, so this is belt-and-braces for databases that sat between the two
    migrations.
    """
    Tenant = apps_registry.get_model("persistence", "Tenant")
    User = apps_registry.get_model("persistence", "User")
    known = {
        "tenant_id": set(Tenant.objects.values_list("id", flat=True)),
        "created_by_id": set(User.objects.values_list("id", flat=True)),
        "modified_by_id": set(User.objects.values_list("id", flat=True)),
    }

    for model_name in ("Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"):
        model = apps_registry.get_model("application", model_name)
        # Historical models carry a plain auto-created manager: TenantManager /
        # UnscopedManager set no ``use_in_migrations``, so migration state never
        # captures them and this runs without needing a TenantContext.
        model.objects.filter(modified_at__isnull=True).update(
            modified_at=models.F("updated_at")
        )
        for column, valid_ids in known.items():
            orphans = sorted(
                str(value)
                for value in set(model.objects.values_list(column, flat=True))
                # NULL is always acceptable for a nullable FK; only a *present*
                # id that resolves to nothing is an orphan.
                if value is not None and value not in valid_ids
            )
            if orphans:
                raise RuntimeError(
                    f"{model_name}.{column} references unknown ids {orphans}; "
                    "clean these rows before adding the FK constraint."
                )


def _pin_then_rename_to_fk(model_name, old_name, new_name, pinned, target_field):
    """Return the three ops that turn a manual UUID column into a real FK.

    Args:
        model_name: Django model name, lowercased (e.g. ``"adr"``).
        old_name: Current field name, which is also the physical column.
        new_name: Field name after the move (the FK's name).
        pinned: The old field re-declared with an explicit ``db_column``, so the
            rename cannot emit a physical column rename.
        target_field: The final ``ForeignKey``.

    Returns:
        A list of three migration operations, in apply order.
    """
    return [
        migrations.AlterField(model_name=model_name, name=old_name, field=pinned),
        migrations.RenameField(
            model_name=model_name, old_name=old_name, new_name=new_name
        ),
        migrations.AlterField(model_name=model_name, name=new_name, field=target_field),
    ]


def _user_fk():
    """AuditableModel.created_by / .modified_by (persistence/models.py)."""
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="+",
        to="persistence.user",
    )


def _operations():
    ops = [migrations.RunPython(
        _assert_no_orphan_refs_and_backfill, migrations.RunPython.noop
    )]

    # Drop the attname-based indexes first: RemoveIndex resolves the old index
    # by name out of from_state, so it must run while that state still holds it.
    ops += [
        migrations.RemoveIndex(model_name=model_name, name=index_name)
        for model_name, index_name in _TENANT_INDEXES.items()
    ]

    for model_name in _MODELS:
        ops += _pin_then_rename_to_fk(
            model_name,
            "tenant_id",
            "tenant",
            models.UUIDField(db_column="tenant_id", db_index=True),
            # ``related_name`` stays the unresolved ``%(class)s_set`` and
            # ``db_index`` is omitted (True is the ForeignKey default) — this is
            # exactly what ``ForeignKey.deconstruct()`` emits for
            # ``TenantScopedModel.tenant``, so the state matches the model and
            # ``makemigrations --check`` stays clean.
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(class)s_set",
                to="persistence.tenant",
            ),
        )
        for column, field_name in (
            ("created_by_id", "created_by"),
            ("modified_by_id", "modified_by"),
        ):
            ops += _pin_then_rename_to_fk(
                model_name,
                column,
                field_name,
                models.UUIDField(blank=True, null=True, db_column=column),
                _user_fk(),
            )
        # AuditableModel.modified_at is NOT NULL; 0021 added it nullable.
        ops.append(
            migrations.AlterField(
                model_name=model_name,
                name="modified_at",
                field=models.DateTimeField(auto_now=True),
            )
        )
        # State-only: ModelState records the default and base managers as plain
        # shims (TenantManager/UnscopedManager set no ``use_in_migrations``), so
        # this emits no SQL. It exists so the recorded state matches the model
        # and historical models keep an unfiltered manager.
        ops.append(
            migrations.AlterModelManagers(
                name=model_name,
                managers=[
                    ("objects", django.db.models.manager.Manager()),
                    ("unscoped", django.db.models.manager.Manager()),
                ],
            )
        )

    ops += [
        migrations.AddIndex(
            model_name=model_name,
            index=models.Index(
                fields=["tenant", "workspace_id"], name=index_name
            ),
        )
        for model_name, index_name in _TENANT_INDEXES.items()
    ]
    return ops


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0021_reconcile_audit_fields"),
        # Supplies Tenant and User, the two FK targets.
        ("persistence", "0070_drop_status_mirror_columns"),
    ]

    operations = _operations()
