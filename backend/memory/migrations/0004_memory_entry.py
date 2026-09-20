# AI Long-Term Memory — unified MemoryEntry table (RFC #1002, PR A).
#
# One tenant-scoped table replaces the former WorkspaceMemory /
# UserTenantMemory split (see 0001_initial.py). Provenance travels as COLUMNS
# (language, confidence, contributor_user_id, source_event_id,
# source_session_id, entity_type, backend_ref) rather than in a sidecar table;
# ``scope`` selects which of the three nullable owner FKs (workspace/user/
# artifact) is meaningful. Legacy rows are copied over by 0005 before the old
# tables are dropped by 0006, so no data is lost.
#
# Operation order mirrors 0001_initial.py:
#   1. CreateModel + all indexes (btree + HNSW).
#   2. Enable + FORCE RLS in the SAME migration (Global Constraint: "New
#      tenant-scoped tables require RLS in the same migration that creates
#      them").
#
# FORCE (not just ENABLE) matters here for the same reason as 0001: DDL and
# data migrations run under the DB-owner role, which bypasses a plain
# ENABLE-only policy.
import uuid

import django.db.models.deletion
import django.db.models.manager
import pgvector.django
from django.conf import settings
from django.db import migrations, models


_MEMORY_ENTRY_TABLE = "mem_memory_entry"


def _rls_sql(table: str) -> tuple[str, str]:
    policy = f"{table}_tenant_isolation"
    enable_sql = (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )
    disable_sql = (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )
    return enable_sql, disable_sql


_MEMORY_ENTRY_ENABLE_SQL, _MEMORY_ENTRY_DISABLE_SQL = _rls_sql(_MEMORY_ENTRY_TABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0003_system_memory_settings"),
        ("persistence", "0098_requirement_rationale_requirement_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MemoryEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "scope",
                    models.CharField(
                        choices=[("user", "user"), ("workspace", "workspace"), ("artifact", "artifact")],
                        max_length=16,
                    ),
                ),
                ("content", models.TextField()),
                (
                    "embedding",
                    pgvector.django.VectorField(blank=True, dimensions=384, null=True),
                ),
                ("language", models.CharField(blank=True, default="", max_length=8)),
                ("confidence", models.FloatField(default=1.0)),
                ("contributor_user_id", models.UUIDField(blank=True, null=True)),
                ("source_event_id", models.UUIDField(blank=True, null=True)),
                ("source_session_id", models.UUIDField(blank=True, null=True)),
                ("entity_type", models.CharField(blank=True, default="", max_length=32)),
                ("backend_ref", models.CharField(blank=True, max_length=64, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "superseded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supersedes",
                        to="memory.memoryentry",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="persistence.tenant",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_entries",
                        to="persistence.workspace",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "artifact",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_entries",
                        to="persistence.artifact",
                    ),
                ),
            ],
            options={"db_table": "mem_memory_entry"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(
                fields=["tenant", "scope", "workspace", "created_at"],
                name="idx_mem_entry_ws_created",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(
                fields=["tenant", "scope", "user", "created_at"],
                name="idx_mem_entry_user_created",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(
                fields=["tenant", "scope", "artifact", "created_at"],
                name="idx_mem_entry_artifact_created",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=models.Index(fields=["backend_ref"], name="idx_mem_entry_backend_ref"),
        ),
        migrations.AddIndex(
            model_name="memoryentry",
            index=pgvector.django.HnswIndex(
                name="mem_entry_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.RunSQL(sql=_MEMORY_ENTRY_ENABLE_SQL, reverse_sql=_MEMORY_ENTRY_DISABLE_SQL),
    ]
