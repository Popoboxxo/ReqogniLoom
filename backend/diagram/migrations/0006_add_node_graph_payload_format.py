# GH-353 Task 1: add payload_format=node_graph (strictly-typed node/edge
# diagram format) alongside the existing freehand canvas / mermaid / plantuml
# / json formats. Mirrors migration 0003 exactly: a single AlterField on the
# same column, additive choices list, no data migration, no new column.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagram', '0005_diagram_workspace_id_diagram_idx_diagram_workspace'),
    ]

    operations = [
        migrations.AlterField(
            model_name='diagramversion',
            name='payload_format',
            field=models.CharField(choices=[('mermaid', 'Mermaid'), ('plantuml', 'PlantUML'), ('json', 'Structured JSON'), ('canvas_stroke', 'Canvas Stroke Data (JSON)'), ('node_graph', 'Node Graph (JSON)')], max_length=16),
        ),
    ]
