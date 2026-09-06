"""Drop ``DiagramVersion``.

Datenmodell-Konsolidierung Task 28c-2 (Contract half of the Expand/Migrate/
Contract). By the time this runs:

* ``persistence/0078`` has copied every historical ``DiagramVersion`` row into
  ``persistence.ArtifactVersion`` (declared as a dependency of ``0011``, so the
  edge cannot be skipped);
* ``diagram/0011`` has re-copied the current payload onto ``diagram_diagram``
  and refused to proceed if any row was left behind;
* the write paths (``diagram.manager``) no longer touch
  ``diagram_diagramversion`` at all.

``DROP TABLE`` also removes the table's RLS policies
(``diagram/0008_diagram_rls_policies``), so nothing is left orphaned.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("diagram", "0011_final_backfill_before_contract"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="diagramversion",
            name="idx_diagramversion_history",
        ),
        migrations.RemoveConstraint(
            model_name="diagramversion",
            name="uq_diagram_version_number",
        ),
        migrations.RemoveField(
            model_name="diagram",
            name="current_version",
        ),
        migrations.DeleteModel(
            name="DiagramVersion",
        ),
    ]
