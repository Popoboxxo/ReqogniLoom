"""Issues #127 / #130: missing indexes on Workspace, WorkflowState and
WorkflowDefinition, plus the missing (tenant, name) uniqueness invariant on
Workspace.

The unique constraint is preceded by an idempotent de-duplication pass
(``_dedupe_workspace_names``), because tenants can legitimately hold duplicate
workspace names today — the constraint would otherwise fail to apply on any
existing database. Duplicates are *renamed*, never deleted: the oldest row
keeps its name, every later row gets a `` (n)`` suffix.

Rollback: ``AddIndex``/``AddConstraint`` reverse cleanly. The rename pass is a
no-op on reverse (renamed workspaces keep their new, unique names) — reversing
it would mean deliberately re-introducing ambiguous data.
"""

from django.db import migrations, models

_NAME_MAX_LENGTH = 255


def _dedupe_workspace_names(apps, schema_editor):
    """Rename duplicate (tenant, name) workspaces so the constraint can apply.

    Deterministic ordering (created_at, id) keeps the result reproducible: the
    oldest workspace of a duplicate group keeps the original name, subsequent
    ones become ``"<name> (2)"``, ``"<name> (3)"`` and so on. Suffixed names are
    themselves checked against the already-taken set, so a pre-existing
    ``"Foo (2)"`` does not collide.
    """
    Workspace = apps.get_model("persistence", "Workspace")

    duplicate_keys = (
        Workspace.objects.values("tenant_id", "name")
        .annotate(n=models.Count("id"))
        .filter(n__gt=1)
    )

    for key in duplicate_keys:
        tenant_id = key["tenant_id"]
        name = key["name"]
        taken = set(
            Workspace.objects.filter(tenant_id=tenant_id).values_list(
                "name", flat=True
            )
        )
        rows = list(
            Workspace.objects.filter(tenant_id=tenant_id, name=name).order_by(
                "created_at", "id"
            )
        )
        # rows[0] keeps the original name.
        for index, workspace in enumerate(rows[1:], start=2):
            candidate = _suffixed(name, index)
            while candidate in taken:
                index += 1
                candidate = _suffixed(name, index)
            taken.add(candidate)
            workspace.name = candidate
            workspace.save(update_fields=["name"])


def _suffixed(name: str, index: int) -> str:
    """Return ``name`` with a `` (index)`` suffix, capped at the column width."""
    suffix = f" ({index})"
    return name[: _NAME_MAX_LENGTH - len(suffix)] + suffix


def _noop(apps, schema_editor):
    """Reverse of the rename pass — intentionally does nothing."""


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0052_workspace_goals_toggles"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="workflowdefinition",
            index=models.Index(
                fields=["tenant", "artifact"], name="idx_wfdef_tnt_artifact"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowstate",
            index=models.Index(
                fields=["tenant", "current_state"], name="idx_wfstate_tnt_state"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowstate",
            index=models.Index(
                fields=["tenant", "requirement"], name="idx_wfstate_tnt_req"
            ),
        ),
        migrations.AddIndex(
            model_name="workspace",
            index=models.Index(
                fields=["tenant", "is_active"], name="idx_workspace_tnt_active"
            ),
        ),
        migrations.AddIndex(
            model_name="workspace",
            index=models.Index(
                fields=["tenant", "parent_workspace"],
                name="idx_workspace_tnt_parent",
            ),
        ),
        # Must run before AddConstraint — see module docstring.
        migrations.RunPython(_dedupe_workspace_names, _noop),
        migrations.AddConstraint(
            model_name="workspace",
            constraint=models.UniqueConstraint(
                fields=("tenant", "name"), name="uq_workspace_tenant_name"
            ),
        ),
    ]
