"""
Migration 0014: ChangeRequest configuration-management traceability.

Adds
  * ``ChangeRequest.baseline`` — nullable FK to ``baseline.BaselineSnapshot``,
    the configuration baseline of record a change request is evaluated /
    implemented against (ISO 15288 §6.4.9). Nullable because the ``minimal``
    rigor preset has no baselines at all.
  * ``ChangeRequestAffectedItem`` — the machine-readable answer to "what does
    this CR change", mirroring ``baseline.BaselineDeltaIndexEntry``
    (artifact-UUID string + entity_type discriminator + JSON state snapshot),
    extended with before/after version + state pairs.

RLS: the new table carries its own ``tenant_id`` so it joins the policy set
established by ``application/0009`` and ``application/0013`` — every
tenant-scoped ``as_*`` table is row-level protected (REQ-L2-PL-010, ADR-PL-03).

leaf_id : COMP-AS-021
req_id  : REQ-157, REQ-L2-PL-010
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid

_RLS_TABLE = "as_change_request_affected_item"
_RLS_POLICY = f"{_RLS_TABLE}_tenant_isolation"

_ENABLE_RLS = (
    f"ALTER TABLE {_RLS_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_RLS_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_RLS_POLICY} ON {_RLS_TABLE}\n"
    "    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
    "    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
)

_DISABLE_RLS = (
    f"DROP POLICY IF EXISTS {_RLS_POLICY} ON {_RLS_TABLE};\n"
    f"ALTER TABLE {_RLS_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_RLS_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ('baseline', '0005_baselinedeltaindexentry_state'),
        ('application', '0013_goal_adr_change_request_rls_policies'),
    ]

    operations = [
        migrations.AddField(
            model_name='changerequest',
            name='baseline',
            field=models.ForeignKey(blank=True, help_text='Configuration baseline this change request is evaluated / implemented against. Linked on approval when the workspace preset enables baselines.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='change_requests', to='baseline.baselinesnapshot'),
        ),
        migrations.CreateModel(
            name='ChangeRequestAffectedItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tenant_id', models.UUIDField(db_index=True)),
                ('item_id', models.CharField(db_index=True, max_length=64)),
                ('entity_type', models.CharField(default='item', max_length=32)),
                ('version_before', models.IntegerField(blank=True, help_text='Artifact version when the item was attached to the CR.', null=True)),
                ('version_after', models.IntegerField(blank=True, help_text='Artifact version when the CR was approved / implemented.', null=True)),
                ('state_before', models.JSONField(default=None, help_text='Full curated entity state when attached (see state_capture).', null=True)),
                ('state_after', models.JSONField(default=None, help_text='Full curated entity state at approval / implementation time.', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('change_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='affected_items', to='application.changerequest')),
            ],
            options={
                'db_table': 'as_change_request_affected_item',
                'indexes': [models.Index(fields=['change_request', 'item_id'], name='idx_cr_affected_cr_item'), models.Index(fields=['tenant_id'], name='idx_cr_affected_tenant')],
            },
        ),
        migrations.AddConstraint(
            model_name='changerequestaffecteditem',
            constraint=models.UniqueConstraint(fields=('change_request', 'item_id'), name='uq_cr_affected_item'),
        ),
        migrations.RunSQL(sql=_ENABLE_RLS, reverse_sql=_DISABLE_RLS),
    ]
