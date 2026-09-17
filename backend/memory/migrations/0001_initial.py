# AI Long-Term Memory — initial schema (Spec 2026-08-24, Task 2).
#
# Two new tenant-scoped tables holding consolidated, embeddable memory
# facts. Operation order mirrors context_graph/migrations/0001_initial.py
# (itself mirroring persistence/migrations/0026_add_llm_settings.py):
#   1. CreateModel (both tables) + their indexes (btree + HNSW).
#   2. Enable + FORCE RLS on both new tables in the SAME migration (Global
#      Constraints: "New tenant-scoped tables require RLS in the same
#      migration that creates them").
#
# FORCE (not just ENABLE) matters here for the same reason as 0026: DDL runs
# under the DB-owner role, which bypasses a plain ENABLE-only policy: without
# FORCE, RLS would silently not apply to any connection using the owner
# role.
#
# NOTE: this file was reconciled against `manage.py makemigrations memory
# --check --dry-run` output rather than hand-copied verbatim from the
# implementation-plan draft — the draft's field list omitted the
# `AuditableModel`-inherited `created_by`/`modified_by`/`version` columns
# and used `on_delete=CASCADE` for `tenant` (the real base class uses
# `PROTECT`, REQ-L2-PL-009) and a nonexistent `auth_tenancy.User` FK target
# (the real user model is `persistence.User` / `settings.AUTH_USER_MODEL`).
import uuid

import django.db.models.deletion
import django.db.models.manager
import pgvector.django
from django.conf import settings
from django.db import migrations, models


_WORKSPACE_MEMORY_TABLE = "mem_workspace_memory"
_USER_TENANT_MEMORY_TABLE = "mem_user_tenant_memory"


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


_WORKSPACE_MEMORY_ENABLE_SQL, _WORKSPACE_MEMORY_DISABLE_SQL = _rls_sql(_WORKSPACE_MEMORY_TABLE)
_USER_TENANT_MEMORY_ENABLE_SQL, _USER_TENANT_MEMORY_DISABLE_SQL = _rls_sql(_USER_TENANT_MEMORY_TABLE)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persistence", "0066_interview_multi_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceMemory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=384, null=True)),
                ("source_event_id", models.UUIDField(blank=True, null=True)),
                ("confidence", models.FloatField(default=1.0)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memory_entries", to="persistence.workspace")),
                ("superseded_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="supersedes", to="memory.workspacememory",
                )),
            ],
            options={"db_table": "mem_workspace_memory"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="UserTenantMemory",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("content", models.TextField()),
                ("embedding", pgvector.django.VectorField(blank=True, dimensions=384, null=True)),
                ("source_event_id", models.UUIDField(blank=True, null=True)),
                ("confidence", models.FloatField(default=1.0)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tenant_memory_entries", to=settings.AUTH_USER_MODEL)),
                ("superseded_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="supersedes", to="memory.usertenantmemory",
                )),
            ],
            options={"db_table": "mem_user_tenant_memory"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddIndex(
            model_name="workspacememory",
            index=models.Index(fields=["tenant", "workspace", "created_at"], name="idx_mem_ws_created"),
        ),
        migrations.AddIndex(
            model_name="workspacememory",
            index=pgvector.django.HnswIndex(
                name="mem_ws_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="usertenantmemory",
            index=models.Index(fields=["tenant", "user", "created_at"], name="idx_mem_user_created"),
        ),
        migrations.AddIndex(
            model_name="usertenantmemory",
            index=pgvector.django.HnswIndex(
                name="mem_user_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ),
        migrations.RunSQL(sql=_WORKSPACE_MEMORY_ENABLE_SQL, reverse_sql=_WORKSPACE_MEMORY_DISABLE_SQL),
        migrations.RunSQL(sql=_USER_TENANT_MEMORY_ENABLE_SQL, reverse_sql=_USER_TENANT_MEMORY_DISABLE_SQL),
    ]
