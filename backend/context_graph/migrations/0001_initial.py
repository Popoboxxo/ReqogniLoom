# Workspace Context Graph — initial schema (Issue #377, v1 slice).
#
# Two new tenant-scoped tables, additive to pl_artifact/pl_tracelink (never a
# replacement — see context_graph/models.py's module docstring). Operation
# order mirrors persistence/migrations/0026_add_llm_settings.py exactly:
#   1. CreateModel (both tables) + the ContextEdge unique constraint.
#   2. Enable + FORCE RLS on both new tables in the SAME migration (Global
#      Constraints: "New tenant-scoped tables require RLS in the same
#      migration that creates them").
#
# FORCE (not just ENABLE) matters here for the same reason as 0026: DDL runs
# under the DB-owner role, which bypasses a plain ENABLE-only policy: without
# FORCE, RLS would silently not apply to any connection using the owner
# role.
import uuid

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models


_EDGE_TABLE = "cg_context_edge"
_SETTINGS_TABLE = "cg_workspace_context_settings"


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


_EDGE_ENABLE_SQL, _EDGE_DISABLE_SQL = _rls_sql(_EDGE_TABLE)
_SETTINGS_ENABLE_SQL, _SETTINGS_DISABLE_SQL = _rls_sql(_SETTINGS_TABLE)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("persistence", "0063_migrate_need_to_sysreq_n_placeholder"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceContextSettings",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("enabled", models.BooleanField(default=False, help_text="Event-sourced maintenance on/off for this workspace.")),
                ("schedule_enabled", models.BooleanField(default=False, help_text="Not used until Folge-Issue B (cron scheduling) — no scheduler reads this in v1.")),
                ("refresh_interval_minutes", models.IntegerField(blank=True, null=True, help_text="Unused in v1, see schedule_enabled.")),
                ("provider", models.CharField(default="embedded", help_text='Only "embedded" is a valid value in v1 — rejected elsewhere at the write path.', max_length=32)),
                ("enabled_generators", models.JSONField(blank=True, default=list, help_text='e.g. ["glossary"].')),
                ("last_projected_at", models.DateTimeField(blank=True, null=True)),
                ("last_refresh_at", models.DateTimeField(blank=True, null=True)),
                ("last_event_id", models.UUIDField(blank=True, help_text="Watermark: the last outbox event_id this workspace projected.", null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("node_count", models.IntegerField(default=0)),
                ("edge_count", models.IntegerField(default=0)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
                ("workspace", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="persistence.workspace")),
            ],
            options={
                "db_table": "cg_workspace_context_settings",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="ContextEdge",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                ("edge_kind", models.CharField(choices=[("related", "Related"), ("influences", "Influences"), ("refines", "Refines"), ("shares-term", "Shares Term")], max_length=32)),
                ("origin", models.CharField(choices=[("derived-glossary", "Derived: Glossary"), ("derived-embedding", "Derived: Embedding"), ("derived-cochange", "Derived: Co-change"), ("llm-suggested", "LLM Suggested")], max_length=32)),
                ("confidence", models.FloatField(help_text="0..1 — always 1.0 for deterministic generators.")),
                ("evidence", models.JSONField(blank=True, default=dict, help_text="Human-verifiable justification, e.g. {'term_id': ..., 'term_name': ...}.")),
                ("generator", models.CharField(help_text="Generator name + version (e.g. 'glossary-v1'), for targeted invalidation.", max_length=64)),
                ("generated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="context_edges_from", to="persistence.artifact")),
                ("target", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="context_edges_to", to="persistence.artifact")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
            ],
            options={
                "db_table": "cg_context_edge",
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddIndex(
            model_name="contextedge",
            index=models.Index(fields=["tenant", "source"], name="idx_cg_edge_tenant_source"),
        ),
        migrations.AddIndex(
            model_name="contextedge",
            index=models.Index(fields=["tenant", "target"], name="idx_cg_edge_tenant_target"),
        ),
        migrations.AddIndex(
            model_name="contextedge",
            index=models.Index(fields=["tenant", "edge_kind"], name="idx_cg_edge_tenant_kind"),
        ),
        migrations.AddConstraint(
            model_name="contextedge",
            constraint=models.UniqueConstraint(
                fields=("source", "target", "edge_kind", "origin"), name="uq_context_edge"
            ),
        ),
        migrations.RunSQL(sql=_SETTINGS_ENABLE_SQL, reverse_sql=_SETTINGS_DISABLE_SQL),
        migrations.RunSQL(sql=_EDGE_ENABLE_SQL, reverse_sql=_EDGE_DISABLE_SQL),
    ]
