# Generated for Attribut v3 WS7 (#940): the legacy free-text Risk.owner column
# is renamed to owner_name so it no longer shadows the Artifact-level owner
# Actor FK (WS2, #936).

from django.db import migrations, models


class Migration(migrations.Migration):
    """State-only rename: ``db_column="owner"`` keeps the physical column.

    The rename frees the ``owner`` name for the Artifact-level Actor FK on the
    Risk *type* model (``_field_carrier`` otherwise resolves ``owner`` to the
    legacy CharField). Because the new field declares ``db_column="owner"``,
    the old and the new column name are identical, so the schema editor emits
    no column operation — existing data is retained for the AWMS fold
    ``risk_owner_to_actor``.
    """

    dependencies = [
        ("persistence", "0091_attribute_migration_rls_policy"),
    ]

    operations = [
        migrations.RenameField(
            model_name="risk",
            old_name="owner",
            new_name="owner_name",
        ),
        migrations.AlterField(
            model_name="risk",
            name="owner_name",
            field=models.CharField(blank=True, db_column="owner", max_length=255),
        ),
    ]
