"""Focused guard for issue #1180: dedicated owner of every ``SECURITY DEFINER`` function.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Residual R-8 / security-F8 of
  ``docs/audit/2026-10/1136-rls-coverage-spec.md``.

Before issue #1180 every ``SECURITY DEFINER`` function of the staged-RLS work
was owned by the bootstrap/migration **superuser**, so ``NOT rolsuper`` was not
assertable for the definer (residual R-8). ``persistence/0110`` transfers all of
them to the dedicated ``persistence.db_roles.DEFINER_DB_ROLE`` role
(``NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS`` with
explicit, per-table DML grants).

This module is the machine-checkable half of that change:

* the ``pg_proc.prosecdef`` inventory is exhaustive and every such function is
  owned by ``DEFINER_DB_ROLE`` and **not** a superuser;
* the role is ``NOLOGIN``/``NOSUPERUSER`` and the app role cannot ``SET ROLE``
  into it;
* the definer's privilege surface is exactly the minimal per-table grant set —
  nothing on unrelated tables, no schema ``CREATE``;
* all ten function-backed paths still work under an armed app role;
* the migration forward/reverse round-trips back to the dedicated owner.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from application.models import DomainEventOutbox
from auth_tenancy.models import ApiKey, UserRole
from auth_tenancy.services.authentication import (
    api_key_hash_candidates,
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

#: The full, independently-declared #1180 contract. Kept hard-coded (not
#: imported from the migration) so the inventory test is a real guard: a
#: definer function the migration forgets shows up as untransferred instead of
#: silently agreeing with a shared constant. The round-trip test below asserts
#: the migration's own ``DEFINER_SIGNATURES`` matches this tuple, so the two
#: cannot drift apart without a failure.
DEFINER_SIGNATURES: tuple[str, ...] = (
    "public.auth_api_key_lookup(text[])",
    "public.auth_resolve_roles(uuid)",
    "public.auth_refresh_token_claim(uuid)",
    "public.auth_refresh_token_spend(uuid)",
    "public.auth_revoke_refresh_family(uuid, text)",
    "public.auth_refresh_token_insert(uuid, uuid, uuid, uuid, timestamptz)",
    "public.auth_purge_expired_refresh_tokens(timestamptz, boolean)",
    "public.as_outbox_candidates(integer, timestamptz)",
    "public.as_worker_backlog()",
    "public.rls_hard_enforced(text)",
)

#: The minimal per-table DML grant set the migration must install.
DEFINER_TABLE_PRIVILEGES: dict[str, tuple[str, ...]] = {
    "at_api_key": ("SELECT",),
    "at_user_role": ("SELECT",),
    "at_refresh_token": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "as_domain_event_outbox": ("SELECT",),
    "as_domain_event_dlq": ("SELECT",),
    "pl_rls_enforcement": ("SELECT",),
    "pl_user": ("SELECT",),
}

#: Privileges the ten bodies never use on their tables. Asserted absent so the
#: grant model cannot silently widen to ``ALL``.
_ALL_DML = ("SELECT", "INSERT", "UPDATE", "DELETE")

#: Unrelated tables the definer must never be able to touch. A representative
#: tenant-scoped table plus the tenant root.
_UNRELATED_TABLES = ("pl_tenant", "pl_workspace")


def _arm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_preauth_enforced = 'on'")
        cursor.execute("SET app.rls_as_enforced = 'on'")


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_preauth_enforced")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET ROLE")


# ---------------------------------------------------------------------------
# Exhaustive inventory
# ---------------------------------------------------------------------------


@_pg_only
def test_prosecdef_inventory_matches_the_migration_contract():
    """Every ``SECURITY DEFINER`` function is in ``DEFINER_SIGNATURES`` — no
    more, no less — so a future definer cannot be added without being
    transferred to the dedicated owner."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.proname || '(' || "
            "       pg_get_function_identity_arguments(p.oid) || ')' "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.prosecdef "
            "ORDER BY 1"
        )
        live = {row[0] for row in cursor.fetchall()}

        expected: set[str] = set()
        for signature in DEFINER_SIGNATURES:
            cursor.execute(
                "SELECT p.proname || '(' || "
                "       pg_get_function_identity_arguments(p.oid) || ')' "
                "FROM pg_proc p WHERE p.oid = %s::regprocedure",
                [signature],
            )
            row = cursor.fetchone()
            assert row is not None, f"{signature} does not exist"
            expected.add(row[0])

    assert live == expected, (
        "the SECURITY DEFINER inventory drifted from the #1180 contract: "
        f"untransferred={sorted(live - expected)} "
        f"missing={sorted(expected - live)}"
    )


@_pg_only
@pytest.mark.parametrize("signature", DEFINER_SIGNATURES)
def test_definer_is_owned_by_the_dedicated_non_superuser_role(signature):
    """``pg_get_userbyid(proowner) == DEFINER_DB_ROLE`` and ``NOT rolsuper``."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_userbyid(p.proowner) AS owner, r.rolsuper, "
            "       r.rolcanlogin, r.rolbypassrls "
            "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.oid = %s::regprocedure",
            [signature],
        )
        owner, rolsuper, rolcanlogin, rolbypassrls = cursor.fetchone()

    assert owner == DEFINER_DB_ROLE, (
        f"{signature} is owned by {owner!r}, not the dedicated "
        f"{DEFINER_DB_ROLE!r} (issue #1180)"
    )
    assert rolsuper is False, (
        f"{signature} is owned by superuser {owner!r}; NOT rolsuper is the point "
        "of issue #1180 (residual R-8)"
    )
    assert rolcanlogin is False, f"{owner!r} must be NOLOGIN"
    assert rolbypassrls is True, (
        f"{owner!r} is the selected RLS-bypass mechanism but rolsuper=False and "
        "rolbypassrls=False would make the bodies subject to the policy"
    )


# ---------------------------------------------------------------------------
# Role attributes + app-role reachability
# ---------------------------------------------------------------------------


@_pg_only
def test_definer_role_has_the_minimal_attribute_set():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
            "       rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = %s",
            [DEFINER_DB_ROLE],
        )
        row = cursor.fetchone()

    assert row is not None, f"{DEFINER_DB_ROLE} does not exist"
    canlogin, superuser, createdb, createrole, replication, bypassrls = row
    assert canlogin is False, "the definer owner must be NOLOGIN"
    assert superuser is False, "the definer owner must be NOSUPERUSER"
    assert createdb is False, "the definer owner must be NOCREATEDB"
    assert createrole is False, "the definer owner must be NOCREATEROLE"
    assert replication is False, "the definer owner must be NOREPLICATION"
    assert bypassrls is True, (
        "the definer owner needs BYPASSRLS to read/write the non-FORCE staged "
        "tables from within the bodies"
    )
    assert DEFINER_DB_ROLE != APP_DB_ROLE


@_pg_only
def test_app_role_is_not_a_member_of_and_cannot_set_role_into_the_definer():
    """The app role has no membership in the definer role.

    ``pg_has_role(..., 'MEMBER')`` / ``'USAGE'`` is the exact predicate
    PostgreSQL uses to authorise ``SET ROLE``: a non-member, non-superuser
    session cannot assume the definer identity. (The live ``SET ROLE`` itself
    cannot be exercised here because the pytest session authenticates as the
    ``DB_USER`` superuser, and a superuser session may ``SET ROLE`` into any
    role regardless of membership — the membership check is the meaningful
    assertion.)
    """
    with connection.cursor() as cursor:
        for mode in ("MEMBER", "USAGE"):
            cursor.execute(
                "SELECT pg_has_role(%s, %s, %s)",
                [APP_DB_ROLE, DEFINER_DB_ROLE, mode],
            )
            assert cursor.fetchone()[0] is False, (
                f"{APP_DB_ROLE} has {mode} on {DEFINER_DB_ROLE}; it could "
                "SET ROLE into it and bypass RLS"
            )
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = %s", [APP_DB_ROLE])
        assert cursor.fetchone()[0] is False, (
            f"{APP_DB_ROLE} is a superuser; it could SET ROLE into the definer"
        )


# ---------------------------------------------------------------------------
# Minimal privilege surface
# ---------------------------------------------------------------------------


@_pg_only
def test_definer_privilege_surface_is_exactly_the_minimal_grants():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_schema_privilege(%s, 'public', 'USAGE'), "
            "       has_schema_privilege(%s, 'public', 'CREATE')",
            [DEFINER_DB_ROLE, DEFINER_DB_ROLE],
        )
        has_usage, has_create = cursor.fetchone()
        assert has_usage is True, "the definer needs USAGE on schema public"
        assert has_create is False, "the definer must not CREATE in schema public"

        for table, privileges in DEFINER_TABLE_PRIVILEGES.items():
            for privilege in _ALL_DML:
                cursor.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    [DEFINER_DB_ROLE, f"public.{table}", privilege],
                )
                granted = cursor.fetchone()[0]
                expected = privilege in privileges
                assert granted is expected, (
                    f"{DEFINER_DB_ROLE} on public.{table}: {privilege} is "
                    f"{granted!r}, expected {expected!r} (minimal grant model)"
                )

        for table in _UNRELATED_TABLES:
            for privilege in _ALL_DML:
                cursor.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    [DEFINER_DB_ROLE, f"public.{table}", privilege],
                )
                assert cursor.fetchone()[0] is False, (
                    f"{DEFINER_DB_ROLE} has {privilege} on unrelated public.{table}"
                )


# ---------------------------------------------------------------------------
# Every function-backed path still works under an armed app role
# ---------------------------------------------------------------------------


@_pg_only
def test_all_function_backed_paths_work_under_an_armed_app_role():
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"definer-{suffix}", slug=f"definer-{suffix}")
    user = User.objects.create(
        username=f"definer-{suffix}",
        email=f"definer-{suffix}@example.test",
        tenant=tenant,
    )
    workspace = Workspace.unscoped.create(tenant=tenant, name=f"definer-ws-{suffix}")
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name="definer-smoke",
        key_hash=hash_api_key(plaintext),
    )
    UserRole.unscoped.create(
        tenant=tenant, user=user, workspace=workspace, role="admin"
    )
    outbox = DomainEventOutbox.objects.create(
        event_type=DomainEventOutbox.EventType.REQUIREMENT_CREATED,
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        entity_id=uuid.uuid4(),
        payload={},
    )

    jti = uuid.uuid4()
    session_id = uuid.uuid4()
    expires_at = timezone.now() + timedelta(hours=1)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            # Pre-auth credential lookup + role resolution (0016).
            cursor.execute(
                "SELECT id, user_id, tenant_id FROM public.auth_api_key_lookup(%s)",
                [list(api_key_hash_candidates(plaintext))],
            )
            lookup = cursor.fetchall()
            assert len(lookup) == 1 and lookup[0][1] == user.id

            cursor.execute(
                "SELECT role FROM public.auth_resolve_roles(%s)", [user.id]
            )
            assert [row[0] for row in cursor.fetchall()] == ["admin"]

            # Refresh write/read path (0021).
            cursor.execute(
                "SELECT public.auth_refresh_token_insert(%s, %s, %s, %s, %s)",
                [user.id, tenant.id, jti, session_id, expires_at],
            )
            inserted_id = cursor.fetchone()[0]
            assert inserted_id is not None

            cursor.execute(
                "SELECT id, jti FROM public.auth_refresh_token_claim(%s)", [jti]
            )
            claimed = cursor.fetchall()
            assert len(claimed) == 1 and claimed[0][1] == jti

            cursor.execute("SELECT public.auth_refresh_token_spend(%s)", [jti])

            cursor.execute(
                "SELECT public.auth_revoke_refresh_family(%s, %s)",
                [session_id, "definer-smoke"],
            )
            assert cursor.fetchone()[0] == 1

            cursor.execute(
                "SELECT public.auth_purge_expired_refresh_tokens(%s, false)",
                [timezone.now()],
            )
            assert cursor.fetchone()[0] >= 0

            # Worker candidate list + backlog (0033).
            cursor.execute(
                "SELECT id, tenant_id FROM public.as_outbox_candidates(%s, %s)",
                [50, timezone.now() - timedelta(minutes=5)],
            )
            candidates = cursor.fetchall()
            assert (outbox.id, tenant.id) in candidates

            cursor.execute("SELECT outbox_pending, dlq_total FROM public.as_worker_backlog()")
            assert len(cursor.fetchall()) == 1

            # Owner-only enforcement switch read (0109).
            cursor.execute("SELECT public.rls_hard_enforced('preauth')")
            assert cursor.fetchone()[0] is False
    finally:
        _disarm_app_role()


# ---------------------------------------------------------------------------
# Migration forward/reverse round-trip
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "0110_security_definer_owner_role.py"
)


def _load_migration_module():
    """Import the migration module (its filename starts with a digit)."""
    spec = importlib.util.spec_from_file_location(
        "_security_definer_owner_role_under_test", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@_pg_only
def test_migration_forward_reverse_round_trip_restores_ownership():
    """Apply the reverse SQL, assert the dedicated owner is gone, apply the
    forward SQL again and assert it is back.

    This runs the migration's own SQL builders, so the round-trip exercises the
    exact statements ``migrate`` executes — not a re-implementation. The
    ``finally`` block always re-applies the forward pass so the schema is left
    exactly as the (still-recorded) migration applied it.
    """
    module = _load_migration_module()
    # The independently-declared contract above and the migration's own list
    # must not drift.
    assert tuple(module.DEFINER_SIGNATURES) == DEFINER_SIGNATURES, (
        "the migration's DEFINER_SIGNATURES differs from the #1180 test contract"
    )
    assert dict(module.DEFINER_TABLE_PRIVILEGES) == DEFINER_TABLE_PRIVILEGES, (
        "the migration's DEFINER_TABLE_PRIVILEGES differs from the #1180 contract"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.prosecdef AND r.rolname = %s",
            [DEFINER_DB_ROLE],
        )
        assert cursor.fetchone()[0] == len(DEFINER_SIGNATURES), (
            "precondition: not every definer function is owned by the dedicated role"
        )

    try:
        with connection.cursor() as cursor:
            cursor.execute(module._reverse_sql())
            cursor.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
                "WHERE p.prosecdef AND r.rolname = %s",
                [DEFINER_DB_ROLE],
            )
            assert cursor.fetchone()[0] == 0, (
                "the reverse pass did not restore the previous owner"
            )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(module._forward_sql())

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.prosecdef AND r.rolname = %s",
            [DEFINER_DB_ROLE],
        )
        assert cursor.fetchone()[0] == len(DEFINER_SIGNATURES), (
            "the forward pass did not re-transfer ownership after the round-trip"
        )
