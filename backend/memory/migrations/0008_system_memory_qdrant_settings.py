# AI Long-Term Memory — Qdrant optional vector backend settings (ADR-020 V1).
#
# Plain ``AddField`` operations: ``SystemMemorySettings`` is deliberately NOT a
# ``TenantScopedModel`` (see its model docstring), so no RLS policy applies to
# the table and none has to be extended here. NULL means "no override, env
# default wins"; the effective value is resolved in
# ``memory.qdrant_backend.QdrantMemoryBackend._resolve_config``.
#
# Deliberately NO dimension field: the Qdrant vector width always mirrors
# ``persistence.embedding_dimensions.EMBEDDING_VECTOR_DIMENSIONS`` (ADR-020 §6).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0007_system_memory_write_ratelimit"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_base_url",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_collection_prefix",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_distance",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_timeout",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_hnsw_m",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_hnsw_ef_construct",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_prefer_grpc",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemmemorysettings",
            name="qdrant_api_key_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
    ]
