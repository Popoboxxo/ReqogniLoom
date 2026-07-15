# REQ-133 — Add a dedicated ``language`` column to the Workspace model.
#
# Previously the per-workspace language was stored only inside the
# ``preset`` JSON blob. This adds a first-class column so the setting can be
# persisted, queried and indexed independently. Existing rows default to
# ``"en"``; no data backfill is required.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0035_add_token_usage_record'),
    ]

    operations = [
        migrations.AddField(
            model_name='workspace',
            name='language',
            field=models.CharField(
                blank=True,
                default='en',
                help_text='Per-workspace UI/content language (REQ-133).',
                max_length=8,
            ),
        ),
    ]
