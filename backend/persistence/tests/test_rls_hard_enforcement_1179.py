"""R-7 hardening proof: the app role cannot disable staged RLS via ``SET`` (#1179).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Residual R-7 of ``docs/audit/2026-10/1136-rls-coverage-spec.md``.

The staged policies gate their tenant predicate behind a *placeholder custom
GUC* (``app.rls_as_enforced`` / ``app.rls_preauth_enforced``). Any session can
clear that GUC with ``SET`` and flip the predicate to fully permissive — the
fail-open residual R-7. PostgreSQL 16 cannot make a placeholder GUC
non-settable (parameter ACLs gate only the persistent
``ALTER SYSTEM`` / ``ALTER ROLE/DATABASE ... SET`` paths, never a session
``SET``), so the hard variant is an owner-only control row plus a
``SECURITY DEFINER`` reader (``persistence/0109_rls_hard_enforcement_control``,
rewritten by ``application/0034`` and ``auth_tenancy/0022``).

These tests prove, against the live database:

* the residual attack really does work while the shipped control default is
  ``false`` (non-vacuity: the negative below is not a tautology);
* once ``hard_enforced`` is set, the same ``SET`` attack no longer leaks rows,
  while the legitimate tenant-armed path still filters exactly;
* the application role cannot write (or read) the control table, cannot flip
  the switch, and the ``SECURITY DEFINER`` reader is least-privilege;
* every one of the seven staged policies references the hard switch.

All database assertions run as the least-privilege application role via
``SET ROLE`` after seeding rows with the superuser test role (which bypasses
RLS unconditionally). The control table is reset around every test because it
is not a Django model and therefore is not covered by the test-database flush.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import DatabaseError, connection

from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.rls_hardening import (
    CONTROL_FUNCTION_SIGNATURE,
    CONTROL_TABLE,
    SCOPE_AS,
    SCOPE_PREAUTH,
)
from persistence.tests.test_rls_plain_child_models import _seed_two_tenants

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

#: Every table whose staged policy was rewritten by #1179, mapped to its scope.
_HARDENED_TABLES: dict[str, str] = {
    "at_api_key": SCOPE_PREAUTH,
    "at_user_role": SCOPE_PREAUTH,
    "at_refresh_token": SCOPE_PREAUTH,
    "as_domain_event_outbox": SCOPE_AS,
    "as_domain_event_dlq": SCOPE_AS,
    "as_webhook_subscription": SCOPE_AS,
    "as_webhook_delivery_log": SCOPE_AS,
}


def _set_hard(scope: str, value: bool) -> None:
    """Flip the owner-only switch for *scope* (runs on the owner connection)."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE public.{CONTROL_TABLE} SET hard_enforced = %s WHERE scope = %s",
            [value, scope],
        )


def _arm_app_role() -> None:
    """Switch to the application role and arm both staged-enforcement GUCs."""
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_as_enforced = 'on'")
        cursor.execute("SET app.rls_preauth_enforced = 'on'")


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET app.rls_preauth_enforced")
        cursor.execute("RESET ROLE")


@pytest.fixture(autouse=True)
def _reset_hard_switch(db):
    """Pin both control scopes to ``false`` before and after every test.

    ``pl_rls_enforcement`` is not a Django model, so the ``transaction=True``
    post-test flush does not reset it; a leaked ``true`` would silently enforce
    (and break) every later RLS test in the session.
    """
    for scope in (SCOPE_AS, SCOPE_PREAUTH):
        _set_hard(scope, False)
    yield
    for scope in (SCOPE_AS, SCOPE_PREAUTH):
        _set_hard(scope, False)


def _seed_preauth_keys() -> list:
    """One active ``at_api_key`` row per tenant, hashed uniquely per row."""
    from auth_tenancy.models import ApiKey
    from persistence.models import Tenant, User

    tenants = []
    for slot in ("a", "b"):
        tenant = Tenant.objects.create(
            name=f"hard-{slot}-{uuid.uuid4().hex[:6]}",
            slug=f"hard-{slot}-{uuid.uuid4().hex[:10]}",
        )
        user = User.objects.create(
            username=f"hard-{slot}-{uuid.uuid4().hex[:6]}",
            email=f"hard-{slot}@example.test",
            tenant=tenant,
        )
        ApiKey.unscoped.create(
            tenant=tenant,
            user=user,
            name=f"hard-{slot}",
            key_hash="sha256p1:" + uuid.uuid4().hex + uuid.uuid4().hex,
        )
        tenants.append(tenant)
    return tenants


# ---------------------------------------------------------------------------
# Non-vacuity: the residual R-7 attack works while the shipped default is OFF
# ---------------------------------------------------------------------------


@_pg_only
def test_default_off_state_is_permissive_and_the_set_attack_would_succeed():
    """DEFAULT-OFF ship unchanged: with ``hard_enforced=false`` and the GUC
    unset the policy is fully permissive, and a single ``SET`` still disables
    it. This is the residual R-7 the hard switch exists to close.
    """
    _seed_two_tenants("hard1179-default")

    # Permissive default: no GUC, no hard switch -> every tenant's row visible.
    _disarm_app_role()
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        try:
            cursor.execute("SELECT count(*) FROM as_domain_event_outbox")
            permissive = cursor.fetchone()[0]
        finally:
            cursor.execute("RESET ROLE")

    # The attack: arm the GUC then clear it -> the predicate un-arms again.
    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.rls_as_enforced = ''")
            cursor.execute("SELECT count(*) FROM as_domain_event_outbox")
            after_attack = cursor.fetchone()[0]
    finally:
        _disarm_app_role()

    assert permissive >= 2, (
        "the DEFAULT-OFF staged policy is not permissive — the two-seed "
        "fixture must show both tenants' rows before enforcement is armed"
    )
    assert after_attack >= 2, (
        "clearing app.rls_as_enforced did not make the staged policy permissive; "
        "the residual-R-7 non-vacuity premise of this module is no longer true"
    )


# ---------------------------------------------------------------------------
# The hard fix: the same SET attack can no longer leak rows
# ---------------------------------------------------------------------------


@_pg_only
def test_hard_switch_makes_the_set_attack_fail_closed():
    """With ``hard_enforced=true`` for the ``as`` scope, an app-role session
    that arms the GUC and then clears it (``SET ... = ''``) must still see zero
    rows — the switch, not the GUC, decides enforcement."""
    _seed_two_tenants("hard1179-attack")
    _set_hard(SCOPE_AS, True)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.rls_as_enforced = ''")
            cursor.execute("SELECT count(*) FROM as_domain_event_outbox")
            leaked = cursor.fetchone()[0]
    finally:
        _disarm_app_role()

    assert leaked == 0, (
        "the app role cleared app.rls_as_enforced and the hardened stake policy "
        f"still exposed {leaked} row(s); R-7 is not closed"
    )


@_pg_only
def test_hard_switch_still_filters_to_the_armed_tenant():
    """The hardened predicate must not become a blanket deny: with the switch
    on and ``app.current_tenant`` armed it exposes exactly that tenant's rows.
    """
    seeded = _seed_two_tenants("hard1179-filter")
    tenant_a, tenant_b = seeded["tenants"]
    _set_hard(SCOPE_AS, True)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            # The attack is applied first: it must not matter.
            cursor.execute("SET app.rls_as_enforced = ''")
            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            cursor.execute(
                "SELECT count(*) FROM as_domain_event_outbox WHERE tenant_id = %s",
                [str(tenant_a.id)],
            )
            own = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM as_domain_event_outbox WHERE tenant_id = %s",
                [str(tenant_b.id)],
            )
            foreign = cursor.fetchone()[0]
    finally:
        _disarm_app_role()

    assert own == 1, (
        f"tenant A saw {own} of its own outbox rows under the hard switch "
        "(expected exactly 1)"
    )
    assert foreign == 0, (
        f"tenant A saw {foreign} of tenant B's rows under the hard switch"
    )


@_pg_only
def test_preauth_scope_hard_switch_closes_the_same_attack():
    """The ``preauth`` scope is independent: flipping it does not require the
    ``as`` scope, and the ``at_api_key`` policy fails closed under the same
    ``SET`` attack."""
    tenants = _seed_preauth_keys()
    _set_hard(SCOPE_PREAUTH, True)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.rls_preauth_enforced = ''")
            cursor.execute("SELECT count(*) FROM at_api_key")
            unarmed_leak = cursor.fetchone()[0]

            cursor.execute("SET app.current_tenant = %s", [str(tenants[0].id)])
            cursor.execute(
                "SELECT count(*) FROM at_api_key WHERE tenant_id = %s",
                [str(tenants[0].id)],
            )
            own = cursor.fetchone()[0]
    finally:
        _disarm_app_role()

    assert unarmed_leak == 0, (
        "clearing app.rls_preauth_enforced leaked at_api_key rows under the "
        "preauth hard switch"
    )
    assert own == 1, "the preauth hard switch hid the tenant's own key"


# ---------------------------------------------------------------------------
# The control table is owner-only; the app role cannot flip the switch
# ---------------------------------------------------------------------------


@_pg_only
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT hard_enforced FROM public.pl_rls_enforcement",
        "UPDATE public.pl_rls_enforcement SET hard_enforced = false",
        (
            "INSERT INTO public.pl_rls_enforcement (scope, hard_enforced) "
            "VALUES ('x', false)"
        ),
        "DELETE FROM public.pl_rls_enforcement",
    ],
)
def test_app_role_has_no_privilege_on_the_control_table(statement):
    """The app role must not even be able to read the switch, let alone write
    it — otherwise it could re-enable the fail-open default itself."""
    _arm_app_role()
    try:
        with connection.cursor() as cursor, pytest.raises(DatabaseError) as excinfo:
            cursor.execute(statement)
    finally:
        _disarm_app_role()

    message = str(excinfo.value).lower()
    assert "permission denied" in message, (
        f"the app role was not denied on pl_rls_enforcement for {statement!r}: "
        f"{excinfo.value}"
    )


@_pg_only
def test_app_role_cannot_flip_the_switch_away_from_enforcement():
    """End-to-end: with enforcement on, the app role's best write attempt is
    denied and the switch stays ``true`` (checked back on the owner session)."""
    _set_hard(SCOPE_AS, True)

    _arm_app_role()
    try:
        with connection.cursor() as cursor, pytest.raises(DatabaseError):
            cursor.execute(
                f"UPDATE public.{CONTROL_TABLE} SET hard_enforced = false "
                "WHERE scope = 'as'"
            )
    finally:
        _disarm_app_role()

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT hard_enforced FROM public.{CONTROL_TABLE} WHERE scope = %s",
            [SCOPE_AS],
        )
        still_enforced = cursor.fetchone()[0]
    assert still_enforced is True, "the app role managed to disable enforcement"


# ---------------------------------------------------------------------------
# Posture + live wiring
# ---------------------------------------------------------------------------


@_pg_only
def test_hard_enforcement_function_security_posture():
    """``SECURITY DEFINER``, pinned ``search_path``, no dynamic SQL,
    schema-qualified relation, EXECUTE for the app role and not for PUBLIC,
    owned by the dedicated non-superuser definer role (issue #1180 / R-8)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.prosecdef, p.proconfig, p.prosrc, "
            "       pg_get_userbyid(p.proowner), r.rolsuper "
            "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.oid = %s::regprocedure",
            [CONTROL_FUNCTION_SIGNATURE],
        )
        prosecdef, proconfig, prosrc, owner, owner_is_superuser = cursor.fetchone()

        cursor.execute(
            "SELECT a.grantee::regrole::text, a.privilege_type "
            "FROM pg_proc p, aclexplode(p.proacl) a "
            "WHERE p.oid = %s::regprocedure",
            [CONTROL_FUNCTION_SIGNATURE],
        )
        acl = {(grantee, priv) for grantee, priv in cursor.fetchall()}

    assert prosecdef is True, f"{CONTROL_FUNCTION_SIGNATURE} is not SECURITY DEFINER"
    assert proconfig and any(
        "search_path=pg_catalog, pg_temp" in clause for clause in proconfig
    ), f"{CONTROL_FUNCTION_SIGNATURE} does not pin search_path: {proconfig}"
    assert owner.strip('"') == DEFINER_DB_ROLE, (
        f"{CONTROL_FUNCTION_SIGNATURE} is owned by {owner}, not the dedicated "
        f"{DEFINER_DB_ROLE} (issue #1180 / residual R-8)"
    )
    assert owner_is_superuser is False, (
        f"{CONTROL_FUNCTION_SIGNATURE} is owned by a superuser ({owner}); "
        "NOT rolsuper must hold"
    )
    assert owner.strip('"') != APP_DB_ROLE, (
        f"{CONTROL_FUNCTION_SIGNATURE} is owned by {owner}, which must not be "
        "the app role (residual R-8)"
    )
    for forbidden in ("EXECUTE", "format(", "quote_ident"):
        assert forbidden not in prosrc, (
            f"{CONTROL_FUNCTION_SIGNATURE} body contains dynamic-SQL marker "
            f"{forbidden!r}"
        )
    assert "public." in prosrc, (
        f"{CONTROL_FUNCTION_SIGNATURE} body has no schema-qualified relation"
    )
    assert (APP_DB_ROLE, "EXECUTE") in acl, (
        f"{CONTROL_FUNCTION_SIGNATURE} does not grant EXECUTE to {APP_DB_ROLE}: "
        f"{acl}"
    )
    assert not any(grantee.upper() == "PUBLIC" for grantee, _ in acl), (
        f"{CONTROL_FUNCTION_SIGNATURE} still grants EXECUTE to PUBLIC: {acl}"
    )


@_pg_only
@pytest.mark.parametrize("table", sorted(_HARDENED_TABLES))
def test_every_staged_policy_references_the_hard_switch(table):
    """The live ``USING``/``WITH CHECK`` clauses must carry the switch call —
    proves the ``ALTER POLICY`` migrations landed and not just the table."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT qual, with_check FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = %s "
            "  AND policyname = %s",
            [table, f"{table}_tenant_isolation"],
        )
        policy = cursor.fetchone()

    assert policy is not None, f"{table} has no tenant_isolation policy"
    qual, with_check = policy
    assert "rls_hard_enforced" in qual, (
        f"{table}: USING clause does not reference the hard switch: {qual!r}"
    )
    assert "rls_hard_enforced" in with_check, (
        f"{table}: WITH CHECK clause does not reference the hard switch: "
        f"{with_check!r}"
    )
