"""Dedicate every ``SECURITY DEFINER`` function to a minimal-owner role (issue #1180).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)
- Residual R-8 / security-F8 of
  ``docs/audit/2026-10/1136-rls-coverage-spec.md`` (line 673): the definer
  functions were owned by the bootstrap/migration **superuser**, so
  ``NOT rolsuper`` was not assertable for their owner.

Background:
    Every ``SECURITY DEFINER`` function shipped by the staged-RLS work
    (``auth_tenancy/0016`` + ``0021``, ``application/0033``,
    ``persistence/0109``) is an *intentional* RLS escape hatch: its body must
    read/write RLS-protected tables (``at_api_key``, ``at_user_role``,
    ``at_refresh_token``, ``as_domain_event_outbox``, ``as_domain_event_dlq``,
    ``pl_rls_enforcement``) without a tenant context. Before this migration the
    owner was ``DB_USER``/``POSTGRES_USER``, i.e. a superuser, which bypasses
    RLS unconditionally — a larger privilege escalation than the functions
    need (R-8).

    This migration creates a dedicated, non-superuser owner role
    (``persistence.db_roles.DEFINER_DB_ROLE``) and transfers ownership of every
    definer function to it. The role is ``NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOREPLICATION BYPASSRLS``:

    * ``NOLOGIN`` — no session can authenticate as it.
    * ``NOSUPERUSER`` — ``NOT rolsuper`` is now assertable for the definer.
    * ``BYPASSRLS`` — the narrowest RLS-bypass mechanism that is *independent
      of ``FORCE ROW LEVEL SECURITY``* (a table-owner bypass would silently
      stop working the moment someone FORCEs one of the staged tables). The
      bypass is combined with **explicit, per-table DML grants** below, so the
      definer can only reach exactly the tables the bodies touch — no blanket
      ``ALL`` and no table ownership (ownership would implicitly grant DDL,
      ``TRUNCATE`` and every DML right, which the bodies never use).
    * ``NOCREATEDB NOCREATEROLE NOREPLICATION`` — explicitly minimal.

    The app role (``APP_DB_ROLE``) is never granted membership in the definer
    role, so it cannot ``SET ROLE`` into it; only a superuser could, and a
    superuser already bypasses RLS.

    Issue #1959 (additive extension, mirroring the #1739 pattern): the inventory
    below also names ``public.embedding_model_drift_counts(text)``, created by
    the later ``persistence/0156`` migration, and grants SELECT on the four
    embedding tables it reads. Ownership/grant statements are existence-guarded
    so both fresh and already-migrated databases end in the same state; no
    migration history is rewritten.

Rejected alternative — table ownership (``ALTER TABLE ... OWNER TO``):
    Transferring the seven tables to the definer would also bypass RLS (tables
    are not FORCEd), but it implicitly grants ``ALL`` privileges including
    ``TRUNCATE`` and the full DDL surface (``ALTER``/``DROP``/index ownership),
    it couples the bypass to the absence of FORCE, and it would move the tables
    out from under ``0048_app_role``'s default-privilege role. It is strictly
    broader than the explicit-grant model chosen here.

Security posture of the transfer:
    * Forward is idempotent: the role is created or re-asserted, grants are
      (re)issued, ownership is (re)set.
    * Reverse restores the previous owner (``CURRENT_USER``, i.e. the migration
      role that created the functions in every supported deployment), revokes
      this database's grants, and — mirroring ``0048_app_role`` — **never
      drops the role**: ``DEFINER_DB_ROLE`` is a cluster-level object shared by
      every database on the server (the persistent dev DB and each ephemeral
      pytest ``test_*`` DB), so a blind ``DROP ROLE`` would fail cluster-wide.
    * The migration must run as a superuser: both ``CREATE ROLE ... BYPASSRLS``
      and ``ALTER FUNCTION ... OWNER TO`` require it. The migration runner in
      every deployment (``migrate`` service, CI) connects as ``DB_USER`` /
      ``POSTGRES_USER``.

Deploy note (logged residual):
    A logical backup/restore with ``--no-owner`` (the project's backup service)
    reassigns object ownership to the restoring role, so after a restore the
    definer functions are owned by that superuser again while this migration
    still reads as applied. Re-assert ownership after such a restore (replay
    this migration's forward SQL, or ``ALTER FUNCTION ... OWNER TO
    <DEFINER_DB_ROLE>``) — see the residual section of
    ``docs/audit/2026-10/1136-rls-coverage-spec.md`` (the #1180 addendum,
    "Implementierungs-Addendum (Issue #1180 — Residual R-8 geschlossen)").

leaf_id : COMP-PL-006, COMP-AT-001
req_id  : REQ-L2-PL-010, REQ-L2-AT-002, Issue #1180
"""
from __future__ import annotations

from django.db import DatabaseError, migrations, transaction

from persistence.db_roles import DEFINER_DB_ROLE

#: Every ``SECURITY DEFINER`` function shipped by the staged-RLS work, keyed by
#: its fully qualified signature (accepted verbatim by ``regprocedure``). The
#: focused test ``persistence/tests/test_definer_owner_role_1180.py`` asserts
#: this list is exhaustive against ``pg_proc.prosecdef``.
DEFINER_SIGNATURES: tuple[str, ...] = (
    "public.auth_api_key_lookup(text[])",
    "public.auth_resolve_roles(uuid)",
    "public.auth_refresh_token_claim(uuid)",
    "public.auth_refresh_token_spend(uuid)",
    "public.auth_revoke_refresh_family(uuid, text)",
    "public.auth_revoke_refresh_families_for_user(uuid, text, uuid)",
    "public.auth_refresh_token_insert(uuid, uuid, uuid, uuid, timestamptz)",
    "public.auth_purge_expired_refresh_tokens(timestamptz, boolean)",
    "public.as_outbox_candidates(integer, timestamptz)",
    "public.as_worker_backlog()",
    "public.rls_hard_enforced(text)",
    # Issue #1959: corpus-wide embedding-model drift counts for /health. The
    # function is created by persistence/0156 (later than this migration), so
    # the ownership transfer below is existence-guarded — the later migration
    # transfers its own function on creation. Listing it here keeps the guard
    # exhaustive and re-asserts ownership when this migration is replayed.
    "public.embedding_model_drift_counts(text)",
)

#: Minimal per-table DML grant the definer bodies actually need. Derived from
#: the ten bodies: the pre-auth lookups/role read/worker reads/RLS-control read
#: are SELECT-only; ``at_refresh_token`` additionally needs INSERT (issue),
#: UPDATE (spend / family revoke / ``SELECT FOR UPDATE`` row lock) and DELETE
#: (maintenance purge). No ``ALL``, no other table.
DEFINER_TABLE_PRIVILEGES: dict[str, tuple[str, ...]] = {
    "at_api_key": ("SELECT",),
    "at_user_role": ("SELECT",),
    "at_refresh_token": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "as_domain_event_outbox": ("SELECT",),
    "as_domain_event_dlq": ("SELECT",),
    "pl_rls_enforcement": ("SELECT",),
    # ``pl_user`` is joined by auth_api_key_lookup for tenant_id / is_active.
    "pl_user": ("SELECT",),
    # Issue #1959: the drift-count function only reads these four embedding
    # tables. BYPASSRLS (role attribute) plus these explicit SELECT grants are
    # the whole surface it needs — no DML, no table ownership.
    "pl_requirement": ("SELECT",),
    "pl_tracelink": ("SELECT",),
    "icd_icd": ("SELECT",),
    "mem_memory_entry": ("SELECT",),
}

#: Tables above that are created by *other* apps' migrations which this
#: already-applied migration cannot safely depend on (adding a dependency to an
#: applied migration would flip its position in the graph). Their grants are
#: guarded with ``to_regclass`` so a fresh install that has not reached those
#: apps yet still migrates cleanly; the 0156 migration grants them itself too.
_LATE_EMBEDDING_TABLES: frozenset[str] = frozenset(
    {"pl_requirement", "pl_tracelink", "icd_icd", "mem_memory_entry"}
)


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    """Quote a PostgreSQL string literal, doubling embedded single quotes."""
    return "'" + value.replace("'", "''") + "'"


def _duplicate_role_pgcode(exc: BaseException) -> str | None:
    """SQLSTATE of a duplicate-role error, unwrapping Django's psycopg2 cause."""
    return getattr(exc, "pgcode", None) or getattr(
        getattr(exc, "__cause__", None), "pgcode", None
    )


def _create_definer_role(apps, schema_editor) -> None:
    """Create/re-assert the cluster-level definer role, race-safe under xdist.

    ``DEFINER_DB_ROLE`` lives in the PostgreSQL cluster, not in one database.
    xdist workers migrate separate test databases against the same cluster, so
    a SELECT-then-CREATE without a cluster-wide lock races exactly like
    ``0048_app_role`` did: two workers both see "absent" and one loses on
    ``pg_authid_rolname_index``. Mirror 0048's advisory lock plus savepoint /
    pgcode guard so a fresh parallel test run cannot fail at migration time.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    role = _quote_ident(DEFINER_DB_ROLE)
    lock_key = f"{DEFINER_DB_ROLE}:create"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [lock_key])
        try:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [DEFINER_DB_ROLE])
            if cursor.fetchone() is not None:
                cursor.execute(
                    f"ALTER ROLE {role} WITH NOLOGIN NOSUPERUSER NOCREATEDB "
                    f"NOCREATEROLE NOREPLICATION BYPASSRLS"
                )
            else:
                try:
                    with transaction.atomic(using=schema_editor.connection.alias):
                        cursor.execute(
                            f"CREATE ROLE {role} WITH NOLOGIN NOSUPERUSER "
                            f"NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS"
                        )
                except DatabaseError as exc:
                    if _duplicate_role_pgcode(exc) not in {"42710", "23505"}:
                        raise
                    cursor.execute(
                        f"ALTER ROLE {role} WITH NOLOGIN NOSUPERUSER "
                        f"NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS"
                    )
        finally:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [lock_key])


def _grant_sql() -> str:
    """USAGE on the schema plus the explicit per-table DML grants.

    The embedding tables added for #1959 are created by other apps' migrations
    that this already-applied migration cannot depend on, so those statements
    are existence-guarded (``to_regclass``) instead. On a fresh install where
    they are already present the grants are applied here; where they are not,
    persistence/0156 installs its own function and grants when it runs.
    """
    role = _quote_ident(DEFINER_DB_ROLE)
    statements = [f"GRANT USAGE ON SCHEMA public TO {role};"]
    for table, privileges in DEFINER_TABLE_PRIVILEGES.items():
        grant = f"GRANT {', '.join(privileges)} ON public.{_quote_ident(table)} TO {role};"
        if table in _LATE_EMBEDDING_TABLES:
            statements.append(
                "DO $do$\nBEGIN\n"
                f"    IF to_regclass('public.{table}') IS NOT NULL THEN\n"
                f"        {grant}\n"
                "    END IF;\n"
                "END $do$;"
            )
        else:
            statements.append(grant)
    return "\n".join(statements)


def _revoke_sql() -> str:
    """Revoke exactly the grants above (this database's privileges only)."""
    role = _quote_ident(DEFINER_DB_ROLE)
    statements = []
    for table in DEFINER_TABLE_PRIVILEGES:
        revoke = f"REVOKE ALL PRIVILEGES ON public.{_quote_ident(table)} FROM {role};"
        if table in _LATE_EMBEDDING_TABLES:
            statements.append(
                "DO $do$\nBEGIN\n"
                f"    IF to_regclass('public.{table}') IS NOT NULL THEN\n"
                f"        {revoke}\n"
                "    END IF;\n"
                "END $do$;"
            )
        else:
            statements.append(revoke)
    statements.append(f"REVOKE USAGE ON SCHEMA public FROM {role};")
    return "\n".join(statements)


def _ownership_sql() -> str:
    """Transfer every definer function to the dedicated role.

    Existence-guarded (``to_regprocedure``): since #1739 this list also names a
    function created by a *later* migration (``auth_tenancy/0034``), which
    depends on this one. A bare ``ALTER FUNCTION`` would therefore abort a fresh
    ``migrate`` with "function does not exist"; the block is a no-op for
    not-yet-created functions and still transfers every existing one. The
    later migration transfers its own function on creation, so the end state is
    identical for fresh and already-migrated databases.
    """
    role = _quote_ident(DEFINER_DB_ROLE)
    return "\n".join(
        "DO $do$\nBEGIN\n"
        f"    IF to_regprocedure({_quote_literal(signature)}) IS NOT NULL THEN\n"
        f"        ALTER FUNCTION {signature} OWNER TO {role};\n"
        "    END IF;\n"
        "END $do$;"
        for signature in DEFINER_SIGNATURES
    )


def _restore_ownership_sql() -> str:
    """Reverse ownership transfer: back to the role running the migration.

    ``CURRENT_USER`` is the migration/bootstrap role in every supported
    deployment — the role that created these functions — so it restores the
    exact pre-#1180 owner without hard-coding ``DB_USER``.

    Existence-guarded for the same #1739 reason as :func:`_ownership_sql`: the
    reverse of *this* migration runs after the reverse of ``auth_tenancy/0034``,
    i.e. after that function was dropped.
    """
    return "\n".join(
        "DO $do$\nBEGIN\n"
        f"    IF to_regprocedure({_quote_literal(signature)}) IS NOT NULL THEN\n"
        f"        ALTER FUNCTION {signature} OWNER TO CURRENT_USER;\n"
        "    END IF;\n"
        "END $do$;"
        for signature in DEFINER_SIGNATURES
    )


def _forward_sql() -> str:
    # Role creation is handled by :func:`_create_definer_role` (RunPython) so
    # the cluster-wide advisory-lock/savepoint race guard can be expressed in
    # Python, matching 0048_app_role and audit/0020.
    return f"{_grant_sql()}\n{_ownership_sql()}"


def _reverse_sql() -> str:
    # Ownership is restored *before* the grants are revoked: while the definer
    # still owns a function it has implicit rights, but revoking its explicit
    # table grants is independent of that. Order is kept ownership-first so a
    # partially applied reverse never leaves a function owned by a role whose
    # schema USAGE was already revoked (the body would then fail to resolve
    # ``public.*``).
    return f"{_restore_ownership_sql()}\n{_revoke_sql()}"


class Migration(migrations.Migration):

    dependencies = [
        # The functions themselves: 0016/0021 (auth), 0033 (worker), 0109 (RLS
        # control). ``0048_app_role`` is transitive but named explicitly so the
        # role-ordering intent (app role exists before the definer role) stays
        # readable.
        ("persistence", "0048_app_role"),
        ("persistence", "0109_rls_hard_enforcement_control"),
        ("auth_tenancy", "0021_refresh_token_functions_and_rls"),
        ("application", "0033_as_outbox_worker_functions"),
    ]

    operations = [
        migrations.RunPython(
            _create_definer_role, reverse_code=migrations.RunPython.noop
        ),
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
