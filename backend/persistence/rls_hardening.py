"""Owner-only hard enforcement switch for the staged RLS policies (issue #1179).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Residual R-7 of ``docs/audit/2026-10/1136-rls-coverage-spec.md``.

Background — why the application role can defeat the staged switch
------------------------------------------------------------------
The staged policies (``auth_tenancy/0017_preauth_staged_rls``,
``auth_tenancy/0021_refresh_token_functions_and_rls``,
``application/0032_as_staged_rls``) gate their tenant predicate behind a
*placeholder custom GUC*::

    current_setting('app.rls_as_enforced', true) IS DISTINCT FROM 'on'
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

A placeholder GUC is session-settable by **every** role. The application role
(``reqogniloom_app``) can therefore run ``SET app.rls_as_enforced = ''`` and
flip the predicate to fully permissive — the fail-open residual R-7.

PostgreSQL 16 cannot make that GUC non-settable: parameter ACLs
(``GRANT`` / ``REVOKE SET ON PARAMETER``) gate only the *persistent* paths
(``ALTER SYSTEM``, ``ALTER ROLE ... SET``, ``ALTER DATABASE ... SET``), never a
session-local ``SET``. This was verified empirically against
``pgvector/pgvector:pg16`` (see
``persistence/tests/test_rls_hard_enforcement_1179``); the spec's honest
caveat (IC-3, security F1) is therefore correct.

The hard variant implemented here
---------------------------------
An **owner-only control row** that the application role can read through a
``SECURITY DEFINER`` function but can never write::

    pl_rls_enforcement (scope text PRIMARY KEY, hard_enforced boolean NOT NULL)
    public.rls_hard_enforced(p_scope text) RETURNS boolean

The rewritten policy predicate becomes::

    (NOT public.rls_hard_enforced('<scope>')
     AND current_setting('<guc>', true) IS DISTINCT FROM 'on')
    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid

Truth table (per scope):

    ============  ===========  ================================================
    hard_enforced  GUC          visibility (app role)
    ============  ===========  ================================================
    false          unset        permissive (DEFAULT-OFF ship, byte-identical)
    false          'on'         tenant-filtered
    true           unset        tenant-filtered
    true           'on'/'…'     tenant-filtered (``SET`` cannot disable it)
    ============  ===========  ================================================

The GUC stays the connection-time *trigger* the existing OPTIONS helper wires
(so ``RLS_AS_ENFORCED`` / ``RLS_PREAUTH_ENFORCED`` still work unchanged); the
control row only ADDS an enforcement source the app role cannot turn off. The
DEFAULT-OFF ship is untouched because the shipped control default is ``false``.
"""
from __future__ import annotations

#: Owner-only control table. One row per staged flag scope; the application
#: role holds **no** privilege on it (not even SELECT — the function reads it
#: with the owner's rights).
CONTROL_TABLE = "pl_rls_enforcement"

#: Scope key for the four worker-owned ``as_*`` tables (GUC
#: ``app.rls_as_enforced``).
SCOPE_AS = "as"

#: Scope key for the pre-auth tables (GUC ``app.rls_preauth_enforced``).
SCOPE_PREAUTH = "preauth"

#: Every scope seeded by the control migration.
CONTROL_SCOPES: tuple[str, ...] = (SCOPE_AS, SCOPE_PREAUTH)

#: ``SECURITY DEFINER`` enforcement-check function name.
CONTROL_FUNCTION = "public.rls_hard_enforced"

#: Fully qualified signature used by GRANT / REVOKE / DROP.
CONTROL_FUNCTION_SIGNATURE = f"{CONTROL_FUNCTION}(text)"


def hard_predicate(guc: str, scope: str) -> str:
    """Return the hardened policy predicate for *guc* and *scope*.

    Permissive only while the owner-controlled switch for *scope* is off **and**
    the session GUC is unset; otherwise the row must match
    ``app.current_tenant``. The expression is used verbatim in both the
    ``USING`` and the ``WITH CHECK`` clause of the seven staged policies by
    ``application/0034_rls_hard_enforcement_policy`` and
    ``auth_tenancy/0022_rls_hard_enforcement_policy``.

    The GUC literal and the scope literal are project constants, never user
    input; the predicate is schema-qualified (``public.``) so a manipulated
    ``search_path`` cannot shadow the function.
    """
    return (
        f"(NOT {CONTROL_FUNCTION}('{scope}')"
        f" AND current_setting('{guc}', true) IS DISTINCT FROM 'on')"
        " OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )


def guc_only_predicate(guc: str) -> str:
    """Return the pre-#1179 predicate, used as the migration ``reverse``.

    Byte-identical to the shape shipped by ``application/0032``,
    ``auth_tenancy/0017`` and ``auth_tenancy/0021``, so reversing the hardening
    migration restores the exact staged state instead of an approximation.
    """
    return (
        f"current_setting('{guc}', true) IS DISTINCT FROM 'on'"
        " OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
