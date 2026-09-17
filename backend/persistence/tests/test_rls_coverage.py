"""
COMP-PL-006 RLSPolicyEnforcer — RLS coverage guard (REQ-L2-PL-010).

Systemaudit 2026-08-27, P0 finding #2 roadmap item: "``TenantScopedModel``
without an RLS migration = CI error". Before this guard existed, every table
added after ``persistence/0003_rls_policies.py`` had to *remember* to ship its
own policy migration, and roughly twenty of them did not — the audit finding
this module closes.

Design: the primary test is STATIC. It reads the migration graph off disk and
extracts every ``CREATE POLICY ... ON <table>`` from every ``RunSQL``
operation, then diffs that against the ``db_table`` of every concrete
``TenantScopedModel`` subclass. No database connection is required, so it fails
fast in CI even on a job without PostgreSQL and it fails at the moment the
model is added rather than at deploy time.

A second, PostgreSQL-only test asserts the same expectation against
``pg_policies`` on the live test database, so a migration that declares a
policy for a misspelled table name is caught too.

Adding a new ``TenantScopedModel``? Ship an RLS migration alongside it (copy the
shape from ``persistence/0067_rls_remaining_pl_tables.py``). Only add a table to
:data:`RLS_EXEMPT_TABLES` if it genuinely cannot carry the standard policy, and
document the concrete blocking code path in the mapping's value — that string is
the review artefact.
"""
from __future__ import annotations

import re

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations.special import RunSQL

from persistence.models import TenantScopedModel

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


# ---------------------------------------------------------------------------
# Known, reviewed exceptions
# ---------------------------------------------------------------------------
# Every entry is a table whose production access path provably runs WITHOUT the
# ``app.current_tenant`` session variable armed, so the standard policy would
# break it rather than harden it. Each value names the exact code path. These
# are debt, not design: removing an entry requires reworking that path (see the
# Systemaudit follow-ups), not relaxing this test.
RLS_EXEMPT_TABLES: dict[str, str] = {
    "at_api_key": (
        "AuthenticationService.validate_api_key looks the key hash up via "
        "ApiKey.unscoped BEFORE any tenant context exists - resolving the "
        "tenant is the purpose of that query. Under the standard policy every "
        "API-key authentication would return zero rows and fail."
    ),
    "at_refresh_token": (
        "SA-32 rotation state. Written by "
        "PasswordAuthenticationService.issue_refresh_token during /auth/login/ "
        "and read+claimed by AuthenticationService.rotate_refresh_token on the "
        "public /auth/refresh/ endpoint - both run with authentication_classes "
        "= [] and therefore without app.current_tenant armed, for the same "
        "chicken-and-egg reason as at_api_key. Under the standard policy the "
        "INSERT would be rejected and every refresh would return zero rows, "
        "i.e. reuse detection would fail closed on every legitimate refresh. "
        "The rows carry no credential material (opaque jti/sid only)."
    ),
    "at_user_role": (
        "PasswordAuthenticationService.resolve_roles reads UserRole.unscoped at "
        "token issuance, which its own docstring documents as happening before "
        "a tenant context is active. Under the standard policy the JWT would be "
        "minted with an empty 'roles' claim, silently stripping permissions."
    ),
    "audit_entry": (
        "Append-only audit log with two tenant-context-free paths: "
        "AuditLogWriter.handle_event is dispatched by the Celery OutboxPoller "
        "(application.event_bus.poll_and_dispatch never arms app.current_tenant "
        "- see memory/projector.py's module docstring), so a WITH CHECK policy "
        "would reject those INSERTs; and AuditLogQuery.stream_entries_before "
        "reads cross-tenant from a maintenance context for the archive export, "
        "which a USING policy would silently reduce to zero rows. A "
        "SELECT-only policy fixes neither half. Needs its own change that "
        "stamps the tenant onto the outbox payload (the fix shape already used "
        "for memory.projector) before RLS can be turned on here."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CREATE_POLICY_RE = re.compile(
    r"CREATE\s+POLICY\s+\S+\s+ON\s+([A-Za-z0-9_]+)", re.IGNORECASE
)


def _sql_fragments(sql: object) -> list[str]:
    """Return every SQL string carried by a ``RunSQL`` ``sql``/``reverse_sql``.

    Django accepts a plain string, a list of strings, or a list of
    ``(sql, params)`` tuples. ``RunSQL.noop`` is a sentinel, not SQL.
    """
    if isinstance(sql, str):
        return [sql]
    if isinstance(sql, (list, tuple)):
        fragments: list[str] = []
        for item in sql:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                fragments.append(item[0])
        return fragments
    return []


def _tables_with_policy_in_migrations() -> set[str]:
    """Every table named by a ``CREATE POLICY`` anywhere in the migration graph."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    tables: set[str] = set()
    for migration in loader.disk_migrations.values():
        for operation in migration.operations:
            if not isinstance(operation, RunSQL):
                continue
            for fragment in _sql_fragments(operation.sql):
                tables.update(
                    match.group(1) for match in _CREATE_POLICY_RE.finditer(fragment)
                )
    return tables


def _tenant_scoped_tables() -> dict[str, str]:
    """Map ``db_table`` -> ``app_label.ModelName`` for concrete tenant-scoped models."""
    return {
        model._meta.db_table: f"{model._meta.app_label}.{model.__name__}"
        for model in apps.get_models()
        if issubclass(model, TenantScopedModel) and not model._meta.abstract
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_every_tenant_scoped_model_has_an_rls_policy_migration():
    """REQ-L2-PL-010: a TenantScopedModel without an RLS migration is a CI error."""
    declared = _tables_with_policy_in_migrations()
    missing = {
        table: label
        for table, label in _tenant_scoped_tables().items()
        if table not in declared and table not in RLS_EXEMPT_TABLES
    }

    assert not missing, (
        "TenantScopedModel(s) without a Row-Level-Security policy migration:\n"
        + "\n".join(f"  - {label} (table {table})" for table, label in sorted(missing.items()))
        + "\n\nEvery tenant-scoped table needs ENABLE + FORCE ROW LEVEL SECURITY "
        "plus a tenant_isolation policy (copy persistence/migrations/"
        "0067_rls_remaining_pl_tables.py). If the table genuinely cannot carry "
        "the policy, add it to RLS_EXEMPT_TABLES with the blocking code path."
    )


def test_rls_exemptions_are_still_tenant_scoped_tables():
    """A stale exemption must not silently keep hiding a real gap.

    If an exempt model is renamed, dropped, or finally gets its policy, the
    entry has to go — otherwise the allowlist grows into a place where future
    gaps can hide unnoticed.
    """
    tenant_tables = set(_tenant_scoped_tables())
    declared = _tables_with_policy_in_migrations()

    unknown = sorted(set(RLS_EXEMPT_TABLES) - tenant_tables)
    assert not unknown, (
        f"RLS_EXEMPT_TABLES lists table(s) that are no longer tenant-scoped "
        f"models: {unknown}. Remove the stale entr(y/ies)."
    )

    now_covered = sorted(set(RLS_EXEMPT_TABLES) & declared)
    assert not now_covered, (
        f"RLS_EXEMPT_TABLES lists table(s) that DO have a policy migration now: "
        f"{now_covered}. Remove the exemption so the table stays guarded."
    )


@_pg_only
@pytest.mark.django_db
def test_rls_policies_exist_on_the_live_schema():
    """The declared policies actually landed — catches a misspelled table name.

    The static test above only proves a ``CREATE POLICY`` statement mentions the
    table. This one proves the statement was valid SQL against the real schema.
    """
    expected = {
        table
        for table in _tenant_scoped_tables()
        if table not in RLS_EXEMPT_TABLES
    }

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_policies WHERE schemaname = 'public'"
        )
        with_policy = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT relname FROM pg_class "
            "WHERE relrowsecurity = true AND relforcerowsecurity = true"
        )
        forced = {row[0] for row in cursor.fetchall()}

    assert not (expected - with_policy), (
        "Tenant-scoped tables without an RLS policy in pg_policies: "
        f"{sorted(expected - with_policy)}"
    )
    assert not (expected - forced), (
        "Tenant-scoped tables missing ENABLE+FORCE ROW LEVEL SECURITY "
        "(without FORCE the table owner bypasses the policy entirely): "
        f"{sorted(expected - forced)}"
    )
