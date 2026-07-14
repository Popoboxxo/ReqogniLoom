# REQ-106 — TokenUsageRecord model (tenant-scoped, append-only).
#
# Operation order mirrors 0026_add_llm_settings.py:
#   1. CreateModel + composite index on (tenant, created_at).
#   2. Enable + FORCE Row-Level Security on ``pl_token_usage_record``
#      (defense-in-depth, mirrors 0003_rls_policies.py / 0026_add_llm_settings.py).
#
# No data seeding is required: the table starts empty and is populated at
# runtime by the LLM adapter after each successful call.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.manager
import uuid


_TABLE = "pl_token_usage_record"
_POLICY = f"{_TABLE}_tenant_isolation"

_ENABLE_RLS_SQL = (
    f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
    f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
    f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
)

_DISABLE_RLS_SQL = (
    f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
    f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0034_add_composite_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='TokenUsageRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('workspace_id', models.UUIDField(blank=True, help_text='Optional workspace this call is attributed to (soft reference).', null=True)),
                ('provider', models.CharField(help_text="Provider name that served the call (e.g. 'anthropic', 'mock').", max_length=64)),
                ('capability', models.CharField(help_text="Capability invoked (e.g. 'validate_artifact').", max_length=64)),
                ('input_tokens', models.IntegerField(default=0, help_text='Prompt/input tokens (holds the combined total when a provider only exposes a single token count).')),
                ('output_tokens', models.IntegerField(default=0, help_text='Completion/output tokens (0 when only a combined total is known).')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
            ],
            options={
                'db_table': 'pl_token_usage_record',
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddIndex(
            model_name='tokenusagerecord',
            index=models.Index(fields=['tenant', 'created_at'], name='idx_tokenusage_tnt_created'),
        ),
        migrations.RunSQL(sql=_ENABLE_RLS_SQL, reverse_sql=_DISABLE_RLS_SQL),
    ]
