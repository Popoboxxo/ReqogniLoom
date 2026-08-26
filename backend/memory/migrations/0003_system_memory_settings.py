# Memory Admin UI Phase 3 — SystemMemorySettings (Spec 2026-08-26).
#
# Deliberately NOT a tenant-scoped table (see Phase 3 plan Ruling 1/2): this
# is a process-wide singleton overriding EMBEDDING_PROVIDER/MEMORY_BACKEND
# env vars, which are themselves process-global (no tenant dimension). No
# RLS is added -- there is no tenant_id column to filter on.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0002_workspace_memory_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemMemorySettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("embedding_provider", models.CharField(blank=True, max_length=32, null=True)),
                ("embedding_model_name", models.CharField(blank=True, max_length=128, null=True)),
                ("ollama_base_url", models.CharField(blank=True, max_length=255, null=True)),
                ("embedding_timeout", models.PositiveIntegerField(blank=True, null=True)),
                ("memory_backend", models.CharField(blank=True, max_length=32, null=True)),
                ("honcho_base_url", models.CharField(blank=True, max_length=255, null=True)),
                ("honcho_api_key_encrypted", models.TextField(blank=True, default="")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "mem_system_memory_settings"},
        ),
    ]
