"""
COMP-PL-006 RLSPolicyEnforcer — close the remaining ``pl_*`` RLS gaps.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind COMP-PL-002 TenantManager)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``persistence/0003_rls_policies.py`` protected the eleven ``pl_*`` tables
    that existed at the time. Every table added afterwards had to opt in via
    its own migration (``0010`` at_item_permission, ``0026`` pl_llm_settings,
    ``0027`` pl_prompt_template, ``0035`` pl_token_usage_record, ``0061``
    pl_interview_session, ``0062`` pl_prompt_variable). Ten ``pl_*`` tables
    never did — their tenant isolation rests solely on the ORM-layer
    ``TenantManager`` filter. That is a defense-in-depth gap: any query that
    bypasses the manager (raw SQL, ``unscoped`` without an explicit
    ``tenant_id``, a future ORM call that forgets the filter) can read across
    tenants.

    All ten tables already carry a ``tenant_id`` UUID column inherited from
    ``TenantScopedModel`` — no schema change is required, this migration is
    purely additive DDL.

Policy semantics (byte-identical to persistence/0003, application/0009+0013,
admin_ops/0003+0006, context_graph/0001, memory/0001+0002):
    ENABLE + FORCE ROW LEVEL SECURITY, plus one ``ALL`` policy exposing only
    rows whose ``tenant_id`` equals the session variable
    ``app.current_tenant`` (armed by ``persistence.middleware.set_request_tenant``
    per request, and explicitly by Celery/worker-thread entry points such as
    ``llm_adapter.tasks.run_capability`` and ``se_metrics.aggregator``). An
    unset/empty setting matches no rows, satisfying REQ-L2-PL-010's "direct DB
    access without the setting -> empty result" criterion.

    A superuser bypasses RLS unconditionally even with FORCE; only connections
    authenticated as the least-privilege ``persistence.db_roles.APP_DB_ROLE``
    (created in persistence/0048) are actually constrained — which is what
    production, Celery and the MCP server use.

Access-path review (why these ten are safe to constrain):
    Every production read/write path for these tables runs with
    ``app.current_tenant`` already armed:

    * Request paths go through ``TenantContextService.activate`` /
      ``persistence.middleware`` (both isolation layers set together).
    * ``baseline.state_capture`` reads ``StakeholderNeed``, ``GlossaryTerm``,
      ``TestRun`` and ``TestRunResult`` via ``unscoped`` with an explicit
      ``tenant_id=``. That module already reads ``Artifact``, ``Requirement``,
      ``ArchitectureElement``, ``TraceLink`` and ``TestCase`` the same way —
      all five of which have been RLS-protected since ``0003``. Baselines
      demonstrably capture those artefacts today, which proves the session
      variable is armed on that path.
    * ``traceability.audit.*`` and ``application.traceability_suggest_service``
      read ``StakeholderNeed`` inside request-scoped services.
    * ``persistence/admin.py`` uses ``unscoped`` for cross-tenant Django-admin
      listings. Those listings are ALREADY constrained by RLS for every table
      covered by ``0003`` (``pl_artifact``, ``pl_requirement``, …), so this
      migration introduces no new behaviour class there.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

# Tenant-scoped ``pl_*`` tables that still lacked an RLS policy. Tables already
# covered by 0003/0010/0026/0027/0035/0061/0062 are deliberately NOT repeated
# here — CREATE POLICY is not idempotent and re-declaring them would fail on an
# already-migrated database.
_TENANT_TABLES = [
    "pl_stakeholder_need",
    "pl_test_run",
    "pl_test_run_result",
    "pl_glossary_term",
    "pl_glossary_term_version",
    "pl_custom_field_definition",
    "pl_custom_field_value",
    "pl_attribute_visibility_config",
    "pl_review_policy",
    "pl_interview_session_artifact",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        # Current persistence leaf: guarantees every table above exists.
        ("persistence", "0066_interview_multi_mode"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
