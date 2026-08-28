"""
COMP-PL-006 RLSPolicyEnforcer — RLS for ``pc_workspace_preset_config``.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``WorkspacePresetConfig`` is a ``TenantScopedModel`` whose table shipped
    without an RLS policy. It already carries a ``tenant_id`` UUID column, so
    no schema change is required; this migration is purely additive DDL.

Policy semantics (byte-identical to persistence/0003):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows, satisfying REQ-L2-PL-010.

Access-path review:
    Every writer of this table sits directly next to a write/read of the
    already-RLS-protected ``pl_workspace``:

    * ``auth_tenancy.provisioning._ensure_workspace`` calls
      ``Workspace.objects.get_or_create`` (RLS-protected since 0003) and then
      ``WorkspacePresetConfig.unscoped.update_or_create`` in the same block.
      ``provision_tenant`` arms ``set_request_tenant(tenant.id)`` beforehand,
      which is why the ``pl_workspace`` write succeeds today — the preset write
      inherits the same armed context.
    * ``presets.gate`` reads ``Workspace.unscoped.get(pk=...)`` immediately
      before ``WorkspacePresetConfig.unscoped.get_or_create``; the former is
      already RLS-protected, so the latter is reached only when the context is
      armed.
    * ``application.workspace_service`` and ``application.self_init`` run inside
      request-scoped services.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

_TABLE = "pc_workspace_preset_config"
_POLICY = f"{_TABLE}_tenant_isolation"

_ENABLE_SQL = (
    f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;\n"
    f"CREATE POLICY {_POLICY} ON {_TABLE}\n"
    f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
    f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
)

_DISABLE_SQL = (
    f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE};\n"
    f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;\n"
    f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;"
)


class Migration(migrations.Migration):

    dependencies = [
        ("presets", "0002_alter_workspacepresetconfig_options_and_more"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_ENABLE_SQL, reverse_sql=_DISABLE_SQL),
    ]
