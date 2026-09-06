"""Drop ``IcdVersion`` and flatten ``IcdParameter`` onto ``Icd``.

Datenmodell-Konsolidierung Task 28c-2 (Contract half of the Expand/Migrate/
Contract). By the time this runs:

* ``persistence/0078`` has copied every historical ``IcdVersion`` row into
  ``persistence.ArtifactVersion`` (declared as a dependency of ``0012``, so the
  edge cannot be skipped);
* ``icd/0012`` has re-copied the current contract onto ``icd_icd`` and re-owned
  every ``icd_parameter`` row, and refused to proceed if either was incomplete;
* the write paths (``icd.icd_manager``) no longer touch ``icd_version`` at all.

Hand-written rather than generated only because ``AlterField`` on
``IcdParameter.icd`` NULL -> NOT NULL is an interactive prompt for
``makemigrations``; the operation list is exactly what the autodetector
produced. Two things the autodetector would not have added:

1. ``DROP FUNCTION icd_raise_version_immutable()``. ``DROP TABLE`` removes the
   ``trg_icd_version_immutable`` trigger with the table — a trigger cannot
   outlive its table, so it never obstructs the drop (verified against a clone
   of the real dev database, not assumed) — but the *function*
   ``icd/0006_icd_version_delete_guard`` created is a standalone schema object
   and would be left behind as an orphan.
2. ``AlterField`` on ``Icd.embedding``: its ``help_text`` no longer claims the
   row is immutable, because the row it now lives on is not.
"""
from django.db import migrations, models
import django.db.models.deletion
import pgvector.django.indexes
import pgvector.django.vector

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS

#: Restores what ``icd/0006_icd_version_delete_guard`` installed, so an
#: (unsupported, data-destroying) reverse migrate at least leaves the schema
#: shaped the way the earlier migrations expect.
_RECREATE_IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION icd_raise_version_immutable()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'IcdVersion records are immutable';
    ELSIF TG_OP = 'DELETE' THEN
        IF current_setting('app.allow_icd_version_delete', true) = 'true' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'IcdVersion records are immutable';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("icd", "0012_final_backfill_before_contract"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="icdversion",
            name="idx_icd_version_icd_num",
        ),
        migrations.RemoveIndex(
            model_name="icdversion",
            name="idx_icd_version_icd_cat",
        ),
        migrations.RemoveIndex(
            model_name="icdversion",
            name="icd_version_embedding_hnsw",
        ),
        migrations.RemoveConstraint(
            model_name="icdversion",
            name="uq_icd_version_number",
        ),
        migrations.RemoveField(
            model_name="icd",
            name="current_version",
        ),
        migrations.RemoveIndex(
            model_name="icdparameter",
            name="idx_icd_param_version_order",
        ),
        migrations.AlterField(
            model_name="icd",
            name="embedding",
            field=pgvector.django.vector.VectorField(
                blank=True,
                dimensions=EMBEDDING_VECTOR_DIMENSIONS,
                help_text=(
                    "REQ-L2-VS-004: Semantic embedding for cosine similarity "
                    "search, sized by persistence.embedding_dimensions."
                    "EMBEDDING_VECTOR_DIMENSIONS (#794). This row is mutable, "
                    "so the embedding is re-generated on every contract change "
                    "and a failed generation can be retried. Best-effort: NULL "
                    "when no embedding provider is configured."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="icdparameter",
            name="icd",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="parameters",
                to="icd.icd",
            ),
        ),
        migrations.AddIndex(
            model_name="icdparameter",
            index=models.Index(
                fields=["icd", "ordering"], name="idx_icd_param_icd_order"
            ),
        ),
        migrations.RemoveField(
            model_name="icdparameter",
            name="icd_version",
        ),
        migrations.DeleteModel(
            name="IcdVersion",
        ),
        migrations.RunSQL(
            sql="DROP FUNCTION IF EXISTS icd_raise_version_immutable();",
            reverse_sql=_RECREATE_IMMUTABILITY_FUNCTION,
        ),
    ]
