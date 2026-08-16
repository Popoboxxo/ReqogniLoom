"""PromptVariable — prompt-variable catalog (spec §3.1).

Operation order mirrors 0027_add_prompt_template.py:
  1. CreateModel + scope index.
  2. Enable + FORCE Row-Level Security on ``pl_prompt_variable``.

No data seeding: factory defaults live in the code registry
(``application.prompt_variables.PROMPT_VARIABLE_DEFAULTS``), exactly like
``PROMPT_TEMPLATE_DEFAULTS`` does for templates. DB rows exist only for
tenant/workspace overrides and admin-created config variables, so a fresh
tenant needs no seed pass at all.
"""
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models

_TABLE = "pl_prompt_variable"
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
        ('persistence', '0061_interview_session_rls'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromptVariable',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(help_text="Variable identifier, e.g. 'max_breadth' (open-ended, not an enum).", max_length=100)),
                ('kind', models.CharField(choices=[('config', 'config'), ('data', 'data')], default='config', help_text="'config' (data-driven, UI-editable) or 'data' (code-bound, read-only).", max_length=10)),
                ('var_type', models.CharField(choices=[('int', 'int'), ('str', 'str'), ('bool', 'bool'), ('json', 'json')], default='str', help_text='int | str | bool | json — how default_value is deserialised.', max_length=20)),
                ('description', models.TextField(blank=True, default='', help_text='Human-readable purpose, shown in the catalog UI.')),
                ('default_value', models.TextField(blank=True, default='', help_text='JSON-serialised value for this scope.')),
                ('version', models.PositiveIntegerField(default=1, help_text='Version number within the (tenant, workspace_id, name) scope; starts at 1.')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this version is the active one for its scope.')),
                ('workspace_id', models.UUIDField(blank=True, help_text='Workspace override scope. NULL means tenant-wide default.', null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
            ],
            options={
                'db_table': 'pl_prompt_variable',
                'indexes': [models.Index(fields=['tenant', 'workspace_id', 'name'], name='ix_prompt_variable_scope')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunSQL(sql=_ENABLE_RLS_SQL, reverse_sql=_DISABLE_RLS_SQL),
    ]
