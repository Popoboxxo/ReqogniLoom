"""Harden the three staged pre-auth RLS policies against a session ``SET`` (#1179).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Residual R-7 of ``docs/audit/2026-10/1136-rls-coverage-spec.md``.

``auth_tenancy/0017_preauth_staged_rls`` (``at_api_key``, ``at_user_role``) and
``auth_tenancy/0021_refresh_token_functions_and_rls`` (``at_refresh_token``)
gate the tenant predicate behind the placeholder GUC
``app.rls_preauth_enforced``; any app-role session can clear it with ``SET``
and make the policy fully permissive. This migration rewrites the three
policies to additionally require the owner-only control switch
(``persistence/0109_rls_hard_enforcement_control``) to be *off* before the GUC
may unarm them:

    (NOT public.rls_hard_enforced('preauth')
     AND current_setting('app.rls_preauth_enforced', true) IS DISTINCT FROM 'on')
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

The credential/refresh paths keep working in the hardened state because they
run through the owner-privileged ``SECURITY DEFINER`` functions from ``0016``
and ``0021``. While ``hard_enforced`` is ``false`` (the shipped default) the
predicate is byte-identical to the pre-#1179 behaviour, so the DEFAULT-OFF
ship is untouched.

``ALTER POLICY`` (not DROP + CREATE) keeps the migration reversible in place:
the reverse restores the exact pre-#1179 predicate.

leaf_id : COMP-PL-006, COMP-AT-001
req_id  : REQ-L2-PL-010, REQ-L2-AT-002, Issue #1179
"""
from __future__ import annotations

from django.db import migrations

from persistence.rls_hardening import (
    SCOPE_PREAUTH,
    guc_only_predicate,
    hard_predicate,
)

_TABLES = [
    "at_api_key",
    "at_user_role",
    "at_refresh_token",
]

_GUC = "app.rls_preauth_enforced"


def _alter_policy_sql(predicate: str) -> str:
    parts = []
    for table in _TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER POLICY {policy} ON {table}\n"
            f"    USING (\n        {predicate}\n    )\n"
            f"    WITH CHECK (\n        {predicate}\n    );"
        )
    return "\n".join(parts)


def _forward_sql() -> str:
    return _alter_policy_sql(hard_predicate(_GUC, SCOPE_PREAUTH))


def _reverse_sql() -> str:
    return _alter_policy_sql(guc_only_predicate(_GUC))


class Migration(migrations.Migration):

    dependencies = [
        ("auth_tenancy", "0021_refresh_token_functions_and_rls"),
        # The hardened predicate calls public.rls_hard_enforced(text).
        ("persistence", "0109_rls_hard_enforcement_control"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
