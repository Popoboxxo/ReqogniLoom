# Additive, non-destructive migration for REQ-L2-CV-005.
# Adds an optional canvas_json field to DiagramVersion alongside the existing
# `payload` stroke data. Nullable + default None — backward-compatible, no data
# loss, no changes to existing columns.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('diagram', '0003_add_canvas_type_and_canvas_stroke_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='diagramversion',
            name='canvas_json',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
    ]
