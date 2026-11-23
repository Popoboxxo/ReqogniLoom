"""Focused guard for issue #1959: the authoritative embedding-drift definer.

``/health*`` is unauthenticated and sets no tenant, but the four embedding
tables are ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` and the app role has
``rolbypassrls=false``. A direct aggregate there is structurally ``0`` — the
original bug was that this was indistinguishable from "no drift". The fix is a
narrow, read-only ``SECURITY DEFINER`` corpus-wide count (``persistence/0156``)
that the app role may call only through a granted EXECUTE.

This module pins the security posture of that helper and proves the behavioural
difference: under an armed app role with no tenant, a direct count reads zero
while the definer function still returns the real corpus-wide numbers.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from django.db import connection

from memory.models import MemoryEntry
from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE
from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

from .conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")

FUNCTION_SIGNATURE = "public.embedding_model_drift_counts(text)"
_EMBEDDING_TABLES = ("pl_requirement", "pl_tracelink", "icd_icd", "mem_memory_entry")


def _load_migration_module():
    """Import the migration module (its filename starts with a digit)."""
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "migrations"
        / "0156_embedding_drift_definer_function.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_embedding_drift_definer_function_under_test", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")


# ---------------------------------------------------------------------------
# Security posture
# ---------------------------------------------------------------------------


@_pg_only
def test_function_is_a_read_only_definer_owned_by_the_dedicated_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.prosecdef, p.provolatile, pg_get_userbyid(p.proowner), "
            "       r.rolsuper, r.rolcanlogin, r.rolbypassrls, p.proconfig, "
            "       pg_get_function_result(p.oid) "
            "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.oid = %s::regprocedure",
            [FUNCTION_SIGNATURE],
        )
        row = cursor.fetchone()

    assert row is not None, f"{FUNCTION_SIGNATURE} is missing"
    prosecdef, provolatile, owner, superuser, canlogin, bypassrls, config, result = row
    assert prosecdef is True
    # 's' = STABLE: the helper only reads; it is never a cross-tenant write path.
    assert provolatile == "s"
    assert owner == DEFINER_DB_ROLE
    assert superuser is False, "the definer must not be a superuser (#1180 residual R-8)"
    assert canlogin is False
    assert bypassrls is True, "BYPASSRLS is the narrow mechanism that beats FORCE RLS"
    assert config is not None and any(
        item.startswith("search_path=pg_catalog") for item in config
    ), f"hijack-safe search_path missing: {config!r}"
    assert all(word in result for word in ("bigint", "requirement", "memory"))


@_pg_only
def test_only_the_app_role_can_execute_and_definer_has_select_only() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_function_privilege('public', %s, 'EXECUTE'), "
            "       has_function_privilege(%s, %s, 'EXECUTE')",
            [FUNCTION_SIGNATURE, APP_DB_ROLE, FUNCTION_SIGNATURE],
        )
        public_execute, app_execute = cursor.fetchone()
        assert public_execute is False, "EXECUTE must be revoked from PUBLIC"
        assert app_execute is True, f"{APP_DB_ROLE} needs EXECUTE on the helper"

        for table in _EMBEDDING_TABLES:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                cursor.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    [DEFINER_DB_ROLE, f"public.{table}", privilege],
                )
                assert cursor.fetchone()[0] is (privilege == "SELECT"), (
                    f"{DEFINER_DB_ROLE} must have SELECT only on public.{table}"
                )


# ---------------------------------------------------------------------------
# Behaviour: corpus-wide under an unarmed app role
# ---------------------------------------------------------------------------


@_pg_only
def test_corpus_counts_are_real_where_a_direct_aggregate_is_rls_shadowed() -> None:
    suffix = uuid.uuid4().hex[:8]
    drift_model = f"test:previous-model:{suffix}"
    current_model = f"test:current-model:{suffix}"
    vector = [0.01] * EMBEDDING_VECTOR_DIMENSIONS

    def counts(model_id: str) -> tuple[int, int, int, int]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT requirement, tracelink, icd, memory "
                "FROM public.embedding_model_drift_counts(%s)",
                [model_id],
            )
            return tuple(cursor.fetchone())

    # No row carries this model yet: the helper must return four real zeroes.
    before = counts(drift_model)
    assert before == (0, 0, 0, 0)

    for index in (0, 1):
        tenant = Tenant.objects.create(
            name=f"drift-{suffix}-{index}", slug=f"drift-{suffix}-{index}"
        )
        user = User.objects.create(
            username=f"drift-{suffix}-{index}",
            email=f"drift-{suffix}-{index}@example.test",
            tenant=tenant,
        )
        with active_tenant(tenant):
            workspace = Workspace.objects.create(
                tenant=tenant, name=f"drift-ws-{suffix}-{index}"
            )
            artifact = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            Requirement.objects.create(
                tenant=tenant,
                artifact=artifact,
                title=f"Drift requirement {index}",
                description="provenance from an older embedding model",
                category="functional",
                type="SyReq",
                level=1,
                uid=f"REQ-DRIFT-{suffix}-{index}",
                embedding=vector,
                embedding_model=drift_model,
            )
            MemoryEntry.objects.create(
                tenant=tenant,
                user=user,
                content=f"drift memory {index}",
                scope=MemoryEntry.SCOPE_USER,
                embedding=vector,
                embedding_model=drift_model,
                backend_ref=f"drift-{suffix}-{index}",
            )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM public.pl_requirement "
            "WHERE embedding_model = %s AND embedding IS NOT NULL",
            [drift_model],
        )
        written = cursor.fetchone()[0]
    assert written >= 2, f"precondition: drift rows were not persisted: {written}"
    # Compare against the *current* model: rows labelled with the old model are
    # drift relative to it (the helper's contract), not relative to themselves.
    owner_counts = counts(current_model)
    assert owner_counts[0] >= 2, f"function body missed persisted rows: {owner_counts}"

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            # What /health used to see: no tenant + RLS-bound role -> zero rows.
            cursor.execute(
                "SELECT count(*) FROM public.pl_requirement WHERE embedding_model = %s",
                [drift_model],
            )
            shadowed = cursor.fetchone()[0]
        # What the definer helper sees: the whole corpus, across both tenants.
        after = counts(current_model)
    finally:
        _disarm_app_role()

    assert shadowed == 0, "precondition: the direct count must be RLS-shadowed"
    assert after[0] >= 2, f"Requirement drift was not corpus-wide: {after}"
    assert after[3] >= 2, f"MemoryEntry drift was not corpus-wide: {after}"
    assert after[1] >= 0 and after[2] >= 0


# ---------------------------------------------------------------------------
# Migration forward/reverse round-trip
# ---------------------------------------------------------------------------


@_pg_only
def test_migration_forward_reverse_round_trip_restores_the_definer_owner() -> None:
    module = _load_migration_module()
    assert module.FUNCTION_SIGNATURE == FUNCTION_SIGNATURE

    def owner() -> str | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_userbyid(p.proowner) FROM pg_proc p "
                "WHERE p.oid = to_regprocedure(%s)",
                [FUNCTION_SIGNATURE],
            )
            row = cursor.fetchone()
            return row[0] if row else None

    assert owner() == DEFINER_DB_ROLE, "precondition: function is not definer-owned"
    try:
        with connection.cursor() as cursor:
            cursor.execute(module._reverse_sql())
        assert owner() is None, "reverse SQL did not drop the function"
    finally:
        with connection.cursor() as cursor:
            cursor.execute(module._forward_sql())

    assert owner() == DEFINER_DB_ROLE, "forward SQL did not restore the definer owner"
