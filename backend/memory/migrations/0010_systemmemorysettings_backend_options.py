from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0009_memoryentry_embedding_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemmemorysettings",
            name="backend_options",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="backend_secrets_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
    ]
