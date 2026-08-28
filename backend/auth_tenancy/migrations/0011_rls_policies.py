"""
COMP-PL-006 RLSPolicyEnforcer — RLS for the post-authentication ``at_*`` tables.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background (Systemaudit 2026-08-27, P0 finding #2 "RLS-Lücken"):
    ``persistence/0010_rls_item_permission.py`` protected ``at_item_permission``
    and explicitly deferred the rest of the AuthAndTenancy tables to "a
    different ticket". This is that ticket for the five tables that are only
    ever touched AFTER a tenant context exists.

    All five already carry a ``tenant_id`` UUID column inherited from
    ``TenantScopedModel`` — no schema change is required, this migration is
    purely additive DDL.

Policy semantics (byte-identical to persistence/0003 and 0010):
    ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the
    session variable ``app.current_tenant``. An unset/empty setting matches no
    rows (closed-world default), satisfying REQ-L2-PL-010.

Access-path review (why exactly these five):
    ``app.current_tenant`` is armed by
    ``auth_tenancy.services.tenant_context.TenantContextService.activate``,
    which runs during DRF authentication — i.e. after the bearer token / API
    key has been resolved but before any view code. Everything listed below is
    read or written strictly downstream of that point:

    * ``at_tenant_role`` — ``AuthorizationService.is_tenant_admin`` /
      ``grant_tenant_admin`` use the tenant-scoped ``objects`` manager. The one
      pre-authentication caller, ``rest_api.auth_views._resolve_is_tenant_admin``
      (LoginView/RefreshView), already arms the context itself via
      ``set_request_tenant(tenant_id)`` and restores it in a ``finally`` — the
      same pairing ``admin_ops.services.banner_service.get_login_banner`` uses
      to stay RLS-correct on a public endpoint.
    * ``at_user_workspace_preference`` — request-scoped service reads only.
    * ``at_global_permission_definition`` / ``at_workspace_permission_definition``
      / ``at_permission_decision_mismatch`` — read and written by
      ``PermissionDefinitionService`` and ``permission_shadow``, both of which
      run inside the authorization step of an authenticated request.

DELIBERATELY NOT INCLUDED — ``at_api_key`` and ``at_user_role``:
    Both are read during authentication, BEFORE any tenant context can exist,
    and adding this policy to them would be an outage, not a hardening:

    * ``AuthenticationService.validate_api_key`` looks up
      ``ApiKey.unscoped.select_related("user")`` by key hash. Resolving the
      tenant is the *purpose* of that query, so no ``app.current_tenant`` can
      be armed yet (chicken-and-egg). Under RLS the lookup returns zero rows
      and EVERY API-key authentication fails.
    * ``PasswordAuthenticationService.resolve_roles`` reads
      ``UserRole.unscoped`` at token issuance — its own docstring states "token
      issuance happens before a tenant context is active". Under RLS the JWT
      would be minted with an empty ``roles`` claim, silently stripping every
      user's permissions on login.

    Protecting these two requires a policy variant that also admits the
    pre-authentication lookup (e.g. a dedicated non-RLS lookup role, or moving
    the credential lookup behind a SECURITY DEFINER function). That is a
    behavioural change to the auth path and belongs in its own reviewed change,
    not in a defense-in-depth sweep. Until then both remain ORM-only and are
    tracked as known exceptions in
    ``persistence/tests/test_rls_coverage.py::RLS_EXEMPT_TABLES``.

leaf_id : COMP-PL-006
req_id  : REQ-L2-PL-010
"""
from __future__ import annotations

from django.db import migrations

# Tenant-scoped auth_tenancy tables that are only accessed with an active
# tenant context. ``at_item_permission`` is already covered by
# persistence/0010 and is deliberately not repeated (CREATE POLICY is not
# idempotent). ``at_api_key`` / ``at_user_role`` are excluded on purpose — see
# the module docstring.
_TENANT_TABLES = [
    "at_tenant_role",
    "at_user_workspace_preference",
    "at_global_permission_definition",
    "at_workspace_permission_definition",
    "at_permission_decision_mismatch",
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
        ("auth_tenancy", "0010_backfill_tenant_admins"),
        # Ordering parity with the original RLS sweep.
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
