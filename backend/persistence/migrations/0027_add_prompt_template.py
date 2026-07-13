# Generated for REQ-L2-PT-001 — PromptTemplate model (tenant-scoped singleton).
#
# Operation order mirrors 0026_add_llm_settings.py:
#   1. CreateModel + unique constraint on tenant. Slot fields carry the factory
#      default prompt content, so a plain get_or_create seeds the defaults.
#   2. Seed one PromptTemplate row per existing tenant — runs BEFORE Row-Level
#      Security is enabled so the insert is not rejected by the tenant-isolation
#      policy (which would match no rows without an active ``app.current_tenant``
#      setting during migration).
#   3. Enable + FORCE RLS on ``pl_prompt_template`` (defense-in-depth).

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.manager
import uuid


_TABLE = "pl_prompt_template"
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

# Frozen default prompt content (kept literal so the migration is independent of
# future changes to persistence.models constants).
_DEFAULT_NEED_TO_SYSREQ = (
    "Given the following stakeholder need, generate {n} system-level "
    "requirements. Each requirement must be specific, measurable, and testable. "
    "Return a JSON array of objects with fields: title (string), description "
    "(string), rationale (string).\n\nStakeholder Need:\nTitle: {need_title}\n"
    "Description: {need_description}"
)
_DEFAULT_SYSREQ_TO_ARCH_ASSIGN = (
    "Given the following system requirement and the available architecture "
    "elements, suggest which architecture elements should be responsible for "
    "implementing it. Return a JSON array of architecture element IDs from the "
    "provided list.\n\nSystem Requirement:\n{req_title}: {req_description}\n\n"
    "Available Architecture Elements:\n{arch_elements_json}"
)
_DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL = (
    "Decompose the following system requirement into more detailed requirements "
    "for the next architecture level. Requirements may be assigned to different "
    "architecture elements. Return a JSON array of objects with fields: title "
    "(string), description (string), rationale (string), "
    "suggested_arch_element_id (string or null).\n\nParent Requirement:\n"
    "{req_title}: {req_description}\n\nArchitecture Elements at this level:\n"
    "{arch_elements_json}"
)


def _seed_defaults(apps, schema_editor):
    """Create one default PromptTemplate row for every existing tenant."""
    Tenant = apps.get_model("persistence", "Tenant")
    PromptTemplate = apps.get_model("persistence", "PromptTemplate")
    for tenant in Tenant.objects.all():
        PromptTemplate.objects.get_or_create(tenant=tenant)


def _unseed_defaults(apps, schema_editor):
    """Reverse: drop all seeded rows (table is dropped by CreateModel reverse)."""
    PromptTemplate = apps.get_model("persistence", "PromptTemplate")
    PromptTemplate.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0026_add_llm_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromptTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('version', models.IntegerField(default=1)),
                ('need_to_sysreq', models.TextField(default=_DEFAULT_NEED_TO_SYSREQ, help_text='Prompt: stakeholder need -> system requirements.')),
                ('sysreq_to_arch_assign', models.TextField(default=_DEFAULT_SYSREQ_TO_ARCH_ASSIGN, help_text='Prompt: system requirement -> architecture assignment.')),
                ('sysreq_decompose_next_level', models.TextField(default=_DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL, help_text='Prompt: decompose system requirement to the next level.')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='persistence.tenant')),
            ],
            options={
                'db_table': 'pl_prompt_template',
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('unscoped', django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name='prompttemplate',
            constraint=models.UniqueConstraint(fields=('tenant',), name='uq_prompt_template_tenant'),
        ),
        migrations.RunPython(_seed_defaults, _unseed_defaults),
        migrations.RunSQL(sql=_ENABLE_RLS_SQL, reverse_sql=_DISABLE_RLS_SQL),
    ]
