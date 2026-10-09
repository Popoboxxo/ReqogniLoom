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
the review artefact. A table whose policy has shipped but is gated behind a
DEFAULT-OFF GUC belongs in :data:`RLS_STAGED_TABLES` instead (issue #1136): it is
covered, not exempt. The four plain worker-owned ``as_*`` entries there are held
to a sharper contract by ``persistence/tests/test_rls_plain_child_models.py`` —
each staged justification must state specific, individually named claims (the
GUC + flag, the ``tenant_id`` source, orphan behaviour, the compensating-control
status and that the admin is tenant-scoped by ``TenantScopedAdminMixin`` app
code rather than by a database guarantee) rather than merely being long, so a
later edit cannot quietly shorten the record back to a generic paragraph.
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
#
# As of issue #1182 only ``audit_entry`` remains exempt. STOPP-S1's
# ``at_refresh_token`` moved out: the refresh WRITE/READ path now runs through
# the owner-privileged SECURITY DEFINER functions in
# ``auth_tenancy/0021_refresh_token_functions_and_rls`` and the table carries a
# GUC-guarded policy (see :data:`RLS_STAGED_TABLES`). The four worker-owned
# ``application`` tables that used to live here now carry a nullable
# ``tenant_id`` and a GUC-guarded policy and moved to
# :data:`RLS_STAGED_TABLES` too.
RLS_EXEMPT_TABLES: dict[str, str] = {
    "audit_entry": (
        "Append-only audit log with two tenant-context-free paths: "
        "AuditLogWriter.handle_event is dispatched by the Celery OutboxPoller "
        "(application.event_bus.poll_and_dispatch arms app.current_tenant only "
        "per outbox row and only while RLS_AS_ENFORCED=on; in the DEFAULT-OFF "
        "production state it arms nothing around the handler - see "
        "memory/projector.py's module docstring), so a WITH CHECK policy "
        "would reject those INSERTs; and AuditLogQuery.stream_entries_before "
        "reads cross-tenant from a maintenance context for the archive export, "
        "which a USING policy would silently reduce to zero rows. A "
        "SELECT-only policy fixes neither half. Needs its own change that "
        "stamps the tenant onto the outbox payload (the fix shape already used "
        "for memory.projector) before RLS can be turned on here."
    ),
}

# ---------------------------------------------------------------------------
# Staged (policy shipped, enforcement DEFAULT OFF) — issue #1136
# ---------------------------------------------------------------------------
# A table moves here when its RLS policy *exists* but is gated behind a
# connection-level GUC that is unset by default, so no production path is
# constrained until the corresponding flag is flipped. The predicate shape is
# permissive-when-unset:
#
#     current_setting('<guc>', true) IS DISTINCT FROM 'on' OR tenant_id = ...
#
# These are NOT exemptions (an exemption means "cannot carry a policy"); they
# are staged coverage. The key facts each entry must state: the GUC, the
# tenant_id source, OFF/ON behaviour, orphan behaviour, the fail-open residual
# R-7 and the definer-owner status R-8 (closed by issue #1180's dedicated
# NOLOGIN definer-owner role). The four plain ``as_*`` entries are
# additionally held to verbatim claims by
# ``persistence/tests/test_rls_plain_child_models.py``.
RLS_STAGED_TABLES: dict[str, str] = {
    "at_refresh_token": (
        "STAGED PRE-AUTH RLS (issue #1182, closing STOPP-S1 of #1136). GUC "
        "app.rls_preauth_enforced (flag RLS_PREAUTH_ENFORCED) gates the policy; "
        "while unset (the production default) the predicate is fully permissive "
        "and every login/refresh/logout is byte-identical to the pre-#1182 "
        "behaviour. The refresh WRITE/READ path (issue_refresh_token, "
        "rotate_refresh_token, _revoke_refresh_family, cleanup) moved behind the "
        "owner-privileged SECURITY DEFINER functions in "
        "auth_tenancy/0021_refresh_token_functions_and_rls: "
        "public.auth_refresh_token_insert / auth_refresh_token_claim / "
        "auth_refresh_token_spend, public.auth_revoke_refresh_family and the "
        "maintenance public.auth_purge_expired_refresh_tokens. tenant_id is the "
        "token owner's tenant_id, stamped at issue time (user.tenant_id); the "
        "rows carry no credential material (opaque jti/sid only). When armed, a "
        "row whose tenant_id does not match app.current_tenant is fail-closed "
        "(invisible); the SECURITY DEFINER functions run with owner privileges "
        "and keep the pre-auth path working. Enforcement is still not enabled in "
        "production default. Residual R-7 (app-role-settable, fail-open GUC) "
        "remains; R-8 (superuser-owned DEFINER) is closed by the dedicated "
        "NOLOGIN definer-owner role (persistence/0110, issue #1180). Dedicated "
        "auth regression suite: auth_tenancy/tests/test_refresh_token_rls_1182.py."
    ),
    "at_api_key": (
        "STAGED PRE-AUTH RLS (issue #1136). GUC app.rls_preauth_enforced "
        "(flag RLS_PREAUTH_ENFORCED) gates the policy on the table; while the "
        "GUC is unset (the production default) the predicate is fully "
        "permissive and every API-key authentication is unchanged. The lookup "
        "itself moved behind the SECURITY DEFINER function "
        "public.auth_api_key_lookup (auth_tenancy/0016) because the credential "
        "read runs before any tenant context exists; tenant identity is "
        "resolved from the joined pl_user.tenant_id. When armed, a row with "
        "NULL tenant_id is fail-closed (invisible); enforcement is still not "
        "enabled in production default. Residual R-7: the GUC is an "
        "app-role-settable, fail-open placeholder custom GUC, so RLS here is "
        "defense-in-depth against ORM mistakes, not against a compromised "
        "session. R-8 (superuser-owned DEFINER) is closed by issue #1180: the "
        "DEFINER owner is the dedicated NOLOGIN/NOSUPERUSER role "
        "(persistence/0110), so NOT rolsuper is assertable and the escalation is "
        "exactly the two read-only lookups plus that role's narrow BYPASSRLS "
        "and per-table DML grants."
    ),
    "at_user_role": (
        "STAGED PRE-AUTH RLS (issue #1136). GUC app.rls_preauth_enforced "
        "(flag RLS_PREAUTH_ENFORCED) gates the policy; while unset (the "
        "production default) the predicate is fully permissive and login role "
        "resolution is unchanged. The read moved behind the SECURITY DEFINER "
        "function public.auth_resolve_roles (auth_tenancy/0016); enforcement "
        "is still not enabled in production default. Residual R-9: the "
        "function is a tenant-agnostic bypass read - it returns a user's roles "
        "across every workspace, exactly as UserRole.unscoped did; that is "
        "faithful but broader than one row. Residual R-7 (app-role-settable, "
        "fail-open GUC) remains; R-8 (superuser-owned DEFINER) is closed by the "
        "dedicated NOLOGIN definer-owner role (issue #1180) as on at_api_key."
    ),
    "as_domain_event_outbox": (
        "STAGED WORKER RLS (issue #1136). GUC app.rls_as_enforced (flag "
        "RLS_AS_ENFORCED) gates the policy (enforcement behind flag); while unset (the production "
        "default) the predicate is fully permissive and the Celery outbox "
        "poller is unchanged. tenant_id is nullable and backfilled from "
        "pl_workspace.tenant_id via workspace_id (application/0031); a row "
        "whose workspace_id resolves to no tenant remains NULL by design "
        "(counted and logged, never deleted) and is fail-closed once enforced. "
        "Enforcement is still not enforced in production default; A4 (poller "
        "tenant arming) has landed - the poller arms app.current_tenant per row "
        "via the SECURITY DEFINER candidate-list public.as_outbox_candidates and "
        "the writer stamps tenant_id (application/0033), closing the residual R-2 "
        "precondition - but RLS_AS_ENFORCED stays DEFAULT OFF. The compensating "
        "control outside the DB is service-layer and code-path only - NOT a "
        "database guarantee: the Django admin (DomainEventOutbox is registered "
        "with TenantScopedAdminMixin) is tenant-scoped by app code, but that is "
        "not a database guarantee. Residual R-7 (app-role-settable, fail-open "
        "GUC) remains; R-8 (superuser-owned DEFINER functions) is closed by the "
        "dedicated NOLOGIN definer-owner role (persistence/0110, issue #1180). "
        "CR-17 residual risk, now staged rather than open."
    ),
    "as_domain_event_dlq": (
        "STAGED WORKER RLS (issue #1136). GUC app.rls_as_enforced (flag "
        "RLS_AS_ENFORCED) gates the policy (enforcement behind flag); while unset (the production "
        "default) the predicate is fully permissive and the poller's DLQ "
        "write-back is unchanged. tenant_id is nullable and backfilled from "
        "pl_workspace.tenant_id via workspace_id (application/0031); an "
        "unresolvable workspace leaves it NULL by design (counted and logged, "
        "never deleted), fail-closed once enforced. Enforcement is still not "
        "enforced in production default; A4 (poller tenant arming) has landed - "
        "the DLQ write-back runs inside the outbox row's armed tenant context "
        "and stamps tenant_id (application/0033) - but RLS_AS_ENFORCED stays "
        "DEFAULT OFF. The DLQ admin "
        "(DomainEventDLQAdmin via TenantScopedAdminMixin) is tenant-scoped by "
        "app code and DlqService resolves ownership through tenant-scoped "
        "Workspace.objects, but the control is service-layer and code-path "
        "only, NOT a database guarantee. Residual R-7 remains; R-8 is closed by "
        "the dedicated NOLOGIN definer-owner role (issue #1180). CR-17 residual "
        "risk, now staged rather than open."
    ),
    "as_webhook_subscription": (
        "STAGED WORKER RLS (issue #1136). GUC app.rls_as_enforced (flag "
        "RLS_AS_ENFORCED) gates the policy (enforcement behind flag); while unset (the production "
        "default) the predicate is fully permissive and outbound webhooks keep "
        "working. tenant_id is nullable and backfilled from "
        "pl_workspace.tenant_id via workspace_id (application/0031); an "
        "unresolvable workspace leaves it NULL by design (counted and logged, "
        "never deleted), fail-closed once enforced. Enforcement is still not "
        "enforced in production default; A4 (poller tenant arming) has landed - "
        "the poller reads subscriptions inside the event row's armed tenant "
        "context, and every delivery log it writes carries the subscription's "
        "tenant anchor (application/0033) - but RLS_AS_ENFORCED stays DEFAULT "
        "OFF. This is the "
        "secret-bearing table: WebhookSubscriptionAdmin (TenantScopedAdminMixin) "
        "excludes the HMAC secret from the form and makes workspace_id "
        "read-only, so the admin is tenant-scoped by app code - but that is "
        "service-layer and code-path only, NOT a database guarantee. Residual "
        "R-7 remains; R-8 is closed by the dedicated NOLOGIN definer-owner role "
        "(issue #1180). CR-17 residual risk, now staged rather than open."
    ),
    "as_webhook_delivery_log": (
        "STAGED WORKER RLS (issue #1136). GUC app.rls_as_enforced (flag "
        "RLS_AS_ENFORCED) gates the policy (enforcement behind flag); while unset (the production "
        "default) the predicate is fully permissive and delivery logging is "
        "unchanged. tenant_id is nullable and backfilled from the owning "
        "subscription's pl_workspace.tenant_id (application/0031); the table "
        "has no workspace_id of its own, an unresolvable subscription leaves "
        "tenant_id NULL by design (counted and logged, never deleted), "
        "fail-closed once enforced. Enforcement is still not enforced in "
        "production default; A4 (poller tenant arming) has landed - the "
        "delivery-log write stamps the owning subscription's tenant anchor and "
        "skips the row fail-closed when there is none (application/0033) - but "
        "RLS_AS_ENFORCED stays DEFAULT OFF. "
        "WebhookDeliveryLogAdmin (TenantScopedAdminMixin via "
        "subscription__workspace_id) is tenant-scoped by app code, but that is "
        "service-layer and code-path only, NOT a database guarantee. Residual "
        "R-7 remains; R-8 is closed by the dedicated NOLOGIN definer-owner role "
        "(issue #1180). CR-17 residual risk, now staged rather than open."
    ),
}

#: staged table -> the GUC its policy must reference (AC-19). The pre-auth
#: tables share one GUC; the four worker tables share the other.
STAGED_POLICY_GUCS: dict[str, str] = {
    "at_refresh_token": "app.rls_preauth_enforced",
    "at_api_key": "app.rls_preauth_enforced",
    "at_user_role": "app.rls_preauth_enforced",
    "as_domain_event_outbox": "app.rls_as_enforced",
    "as_domain_event_dlq": "app.rls_as_enforced",
    "as_webhook_subscription": "app.rls_as_enforced",
    "as_webhook_delivery_log": "app.rls_as_enforced",
}

#: staged table -> (app_label, migration name) that ships its CREATE POLICY.
#: Needed because a GUC name alone cannot attribute a policy to a table (both
#: pre-auth tables share ``app.rls_preauth_enforced``) - AC-19 (N-02).
STAGED_POLICY_MIGRATIONS: dict[str, tuple[str, str]] = {
    "at_refresh_token": ("auth_tenancy", "0021_refresh_token_functions_and_rls"),
    "at_api_key": ("auth_tenancy", "0017_preauth_staged_rls"),
    "at_user_role": ("auth_tenancy", "0017_preauth_staged_rls"),
    "as_domain_event_outbox": ("application", "0032_as_staged_rls"),
    "as_domain_event_dlq": ("application", "0032_as_staged_rls"),
    "as_webhook_subscription": ("application", "0032_as_staged_rls"),
    "as_webhook_delivery_log": ("application", "0032_as_staged_rls"),
}

#: Which of the :data:`RLS_EXEMPT_TABLES` entries are plain child tables rather
#: than ``TenantScopedModel`` tables. Empty since issue #1136: the four plain
#: worker-owned ``as_*`` tables moved out of ``RLS_EXEMPT_TABLES`` into
#: :data:`RLS_STAGED_TABLES` (they now carry a ``tenant_id`` column and a
#: GUC-guarded policy). No plain table remains exempt.
RLS_EXEMPT_PLAIN_TABLES: frozenset[str] = frozenset()


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


def _plain_model_tables() -> set[str]:
    """Every ``db_table`` of a concrete model that is NOT a ``TenantScopedModel``.

    These are invisible to :func:`_tenant_scoped_tables` by construction, so a
    :data:`RLS_STAGED_TABLES` entry for one cannot be validated against that
    inventory - the four worker-owned ``application`` tables are plain
    ``models.Model`` classes. As of issue #1136 they carry a nullable
    ``tenant_id`` and a GUC-guarded policy, but they remain plain models (no
    ``TenantScopedModel`` migration) by design. This inventory lets the
    staleness guard tell "the model was renamed or dropped" from "the entry is
    filed under the wrong kind of table".
    """
    return {
        model._meta.db_table
        for model in apps.get_models()
        if not issubclass(model, TenantScopedModel) and not model._meta.abstract
    }


def _forced_tables_on_live_schema() -> set[str]:
    """Tables carrying ``pg_class.relforcerowsecurity`` (FORCE RLS) on the DB."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relforcerowsecurity = true"
        )
        return {row[0] for row in cursor.fetchall()}


def _staged_policy_fragments(table: str) -> list[str]:
    """Every ``CREATE POLICY ... ON <table> ...;`` statement for *table*.

    Reads the migration named by :data:`STAGED_POLICY_MIGRATIONS` (N-02: a GUC
    alone cannot attribute a policy to a table, both pre-auth tables share one)
    and returns the full policy statement(s), so the AC-19 test can assert the
    GUC in both the USING and the WITH CHECK clause.
    """
    app_label, migration_name = STAGED_POLICY_MIGRATIONS[table]
    loader = MigrationLoader(None, ignore_no_migrations=True)
    migration = loader.disk_migrations[(app_label, migration_name)]
    fragments: list[str] = []
    for operation in migration.operations:
        if not isinstance(operation, RunSQL):
            continue
        for fragment in _sql_fragments(operation.sql):
            fragments.extend(
                match.group(0)
                for match in _CREATE_POLICY_FOR_TABLE_RE(table).finditer(fragment)
            )
    return fragments


def _CREATE_POLICY_FOR_TABLE_RE(table: str) -> re.Pattern[str]:
    # Non-greedy up to the statement-ending ``;`` so USING and WITH CHECK stay
    # inside one match.
    return re.compile(
        rf"CREATE\s+POLICY\s+\S+\s+ON\s+{re.escape(table)}\b.*?;",
        re.IGNORECASE | re.DOTALL,
    )


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
    """ANTIREGRESSION CHECK ONLY — it enforces NO isolation.

    What it actually does, and nothing more: for every entry in
    :data:`RLS_EXEMPT_TABLES` it asserts that the model still exists as a
    concrete model, that the entry is still filed under the right *kind* of
    debt (``RLS_EXEMPT_PLAIN_TABLES``), and that no ``CREATE POLICY`` for that
    table has appeared in the migration graph. That is a defence-in-depth
    tripwire: it can only ever fail when the exemption goes stale — the model
    was renamed or dropped, the debt kind flipped, or the policy finally
    shipped.

    Since issue #1182 only ``audit_entry`` (out of scope) remains exempt, a
    ``TenantScopedModel``. The pre-auth tables ``at_api_key`` / ``at_user_role``
    / ``at_refresh_token`` (STOPP-S1 closed by #1182) and the four ``as_*``
    tables are no longer exempt — they are staged
    (:data:`RLS_STAGED_TABLES`) and the invariant test below proves they are
    covered, not exempt.

    So the original wording — "a stale exemption must not silently keep hiding a
    real gap" — overclaimed: an exemption here does not hide a gap, it NAMES
    one. What is prevented is the gap becoming *unreported*, not the gap itself.
    """
    tenant_tables = set(_tenant_scoped_tables())
    plain_tables = _plain_model_tables() - tenant_tables
    declared = _tables_with_policy_in_migrations()

    unknown = sorted(set(RLS_EXEMPT_TABLES) - (tenant_tables | plain_tables))
    assert not unknown, (
        f"RLS_EXEMPT_TABLES lists table(s) that are no longer concrete models: "
        f"{unknown}. Remove the stale entr(y/ies)."
    )

    # Symmetric difference: catches an entry filed under the wrong kind of debt
    # in both directions (a plain model declared as tenant-scoped, and an
    # exempt tenant-scoped model that quietly became a plain model).
    wrong_kind = sorted(
        RLS_EXEMPT_PLAIN_TABLES ^ (plain_tables & set(RLS_EXEMPT_TABLES))
    )
    assert not wrong_kind, (
        "RLS_EXEMPT_TABLES / RLS_EXEMPT_PLAIN_TABLES disagree about which "
        f"exemptions are plain child tables: {wrong_kind}. A plain child table "
        "carries no tenant_id column at all, so its exemption is a different "
        "debt than a TenantScopedModel's - keep the two lists in step."
    )

    now_covered = sorted(set(RLS_EXEMPT_TABLES) & declared)
    assert not now_covered, (
        f"RLS_EXEMPT_TABLES lists table(s) that DO have a policy migration now: "
        f"{now_covered}. Remove the exemption so the table stays guarded."
    )


@_pg_only
@pytest.mark.django_db
def test_no_table_is_covered_and_exempt_or_staged():
    """AC-1: a table is never simultaneously exempt and covered, and staged
    tables are covered (policy shipped) but deliberately not FORCEd.

    ``declared != enforced``: the staged policy exists in the migration graph,
    so the table is covered — but ``FORCE`` is intentionally absent while the
    GUC flag is DEFAULT OFF (FORCE would bind only owner connections and blur
    the staged signal; see F-10 / security F9 and residual R-8).
    """
    declared = _tables_with_policy_in_migrations()
    forced = _forced_tables_on_live_schema()

    assert not (set(RLS_EXEMPT_TABLES) & declared), (
        "table(s) both exempt and covered by a policy: "
        f"{sorted(set(RLS_EXEMPT_TABLES) & declared)}"
    )
    assert not (set(RLS_EXEMPT_TABLES) & set(RLS_STAGED_TABLES)), (
        "table(s) both exempt and staged: "
        f"{sorted(set(RLS_EXEMPT_TABLES) & set(RLS_STAGED_TABLES))}"
    )
    assert set(RLS_STAGED_TABLES) <= declared, (
        "staged table(s) with no CREATE POLICY in the migration graph: "
        f"{sorted(set(RLS_STAGED_TABLES) - declared)}"
    )
    assert set(RLS_STAGED_TABLES).isdisjoint(forced), (
        "staged table(s) carry FORCE ROW LEVEL SECURITY; the staged ship is "
        "deliberately NO FORCE (it would bind only owner connections and not "
        f"rescue the DEFINER functions): {sorted(set(RLS_STAGED_TABLES) & forced)}"
    )


@pytest.mark.parametrize("table", sorted(RLS_STAGED_TABLES))
def test_staged_policy_uses_its_declared_guc(table):
    """AC-19 (N-01): each staged table's policy references its declared GUC in
    BOTH clauses.

    A policy contains the GUC twice — once in ``USING`` and once in
    ``WITH CHECK`` (``... IS DISTINCT FROM 'on' OR tenant_id = ...``). The
    assertion is therefore per-clause (>=1 occurrence in each), not "exactly
    one occurrence" in the whole statement.
    """
    guc = STAGED_POLICY_GUCS[table]
    marker = f"current_setting('{guc}', true)"
    fragments = _staged_policy_fragments(table)

    assert fragments, (
        f"no CREATE POLICY for staged table {table} found in migration "
        f"{STAGED_POLICY_MIGRATIONS[table]}"
    )
    for fragment in fragments:
        using_clause, separator, with_check_clause = fragment.partition("WITH CHECK")
        assert separator, (
            f"policy for {table} has no WITH CHECK clause: {fragment!r}"
        )
        assert marker in using_clause, (
            f"USING clause of the {table} policy does not reference its declared "
            f"GUC {guc!r}: {using_clause!r}"
        )
        assert marker in with_check_clause, (
            f"WITH CHECK clause of the {table} policy does not reference its "
            f"declared GUC {guc!r}: {with_check_clause!r}"
        )


@_pg_only
@pytest.mark.django_db
def test_rls_policies_exist_on_the_live_schema():
    """The declared policies actually landed — catches a misspelled table name.

    The static test above only proves a ``CREATE POLICY`` statement mentions the
    table. This one proves the statement was valid SQL against the real schema.
    Staged tables (issue #1136) are included in the policy expectation but
    excluded from the FORCE expectation — they are ENABLEd, not FORCEd.
    """
    tenant_tables = set(_tenant_scoped_tables())
    expected_policy = (tenant_tables - set(RLS_EXEMPT_TABLES)) | (
        set(RLS_STAGED_TABLES) - tenant_tables
    )
    expected_forced = tenant_tables - set(RLS_EXEMPT_TABLES) - set(RLS_STAGED_TABLES)

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

    assert not (expected_policy - with_policy), (
        "tables without an RLS policy in pg_policies: "
        f"{sorted(expected_policy - with_policy)}"
    )
    assert not (expected_forced - forced), (
        "Tenant-scoped tables missing ENABLE+FORCE ROW LEVEL SECURITY "
        "(without FORCE the table owner bypasses the policy entirely): "
        f"{sorted(expected_forced - forced)}"
    )
    assert set(RLS_STAGED_TABLES).isdisjoint(forced), (
        "staged table(s) unexpectedly have FORCE ROW LEVEL SECURITY: "
        f"{sorted(set(RLS_STAGED_TABLES) & forced)}"
    )
