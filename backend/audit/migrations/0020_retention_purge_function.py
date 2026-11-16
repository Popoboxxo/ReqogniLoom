"""Bounded, owner-controlled audit retention purge (S0.3-A / L0-001).

Problem
-------
The append-only trigger installed by ``0002_append_only_trigger`` rejects every
``DELETE`` on ``audit_entry`` (BEFORE UPDATE OR DELETE, FOR EACH ROW). The raw
``DELETE`` that ``PartitionDropper`` used to issue therefore failed on the first
row: the monthly job exported the same old rows again and again while retention
silently never removed anything (duplicate exports, unbounded table growth).
``AuditEntry`` is not natively partitioned in v1, so ``DETACH/DROP PARTITION``
is not available either.

Solution
--------
A single ``SECURITY DEFINER`` maintenance function that, inside one transaction:

* disables **only** ``trg_audit_entry_append_only`` (never
  ``session_replication_role = replica`` — that would also disable FK triggers),
* deletes rows strictly older than a caller-supplied cutoff in **bounded
  batches**, summing the per-batch ``ROW_COUNT``,
* re-enables the trigger on both the success and the error path,
* returns the total number of deleted rows.

The function lives in a dedicated ``audit_ops`` schema rather than ``public``:
it is deliberately a superuser-owned definer (only the table owner may
``ALTER TABLE ... DISABLE TRIGGER``), and the #1180 guard intentionally keeps
``public`` free of superuser-owned definers. Keeping it out of ``public`` is a
conscious scope decision, not a way to skip review — see the DECISION note in
``docs/audit/gates/2026-11-16/mvp-gates.md`` (section S0.3-A).

EXECUTE is revoked from ``PUBLIC`` and from the runtime app role and granted
only to the archiver role. The app role inherits that single capability through
explicit, revocable membership (the default Django/Celery connection runs as the
app role; the migration runner is the superuser that owns the table).

Cluster-level objects and the elevated capability (DBE-03)
----------------------------------------------------------
Both the archiver ROLE and the ``GRANT archiver TO app`` membership live in
cluster-level catalogs shared by every database on the server. Reversing this
migration therefore never drops the role and never revokes the membership:
doing either from one ephemeral ``test_*`` database would tear down state other
databases still rely on. Because the app role inherits the archiver role, any
code running as the app role can call the definer with an **arbitrary cutoff** —
an elevated capability, not a benign one. It is bounded inside the function
itself: a cutoff more recent than ``_MIN_PURGE_AGE`` is rejected, so the
inherited capability cannot be used to erase recent audit history.

Lock window (DBE-05)
--------------------
``ALTER TABLE ... DISABLE TRIGGER`` takes ACCESS EXCLUSIVE on ``audit_entry``
and holds it until the surrounding transaction ends. Batching bounds each
individual DELETE (statement duration, row-lock footprint, WAL) but does **not**
shorten that table-lock window — the whole bounded loop runs under one lock.
Callers must keep the cutoff narrow: this is a monthly maintenance job over a
bounded retention window, never an unbounded online cleanup.

Reversibility (DBE-03): only this database's function/schema objects are
removed; the cluster-level archiver role and its membership in the app role are
left untouched.
"""
from __future__ import annotations

from decouple import config
from django.db import DatabaseError, migrations, transaction

from persistence.db_roles import APP_DB_ROLE

#: Dedicated maintenance role. Only this role may execute the purge function.
ARCHIVER_DB_ROLE = config("DB_ARCHIVER_USER", default="reqogniloom_archiver")

#: Isolated schema — keeps this privileged definer out of the #1180 public inventory.
_MAINTENANCE_SCHEMA = "audit_ops"
_TRIGGER_NAME = "trg_audit_entry_append_only"
_FUNCTION_NAME = f"{_MAINTENANCE_SCHEMA}.purge_entries_before"
#: Signature used by GRANT/REVOKE (input argument types, no parameter name).
_FUNCTION_SIGNATURE = f"{_FUNCTION_NAME}(timestamptz)"

#: Maximum rows removed by one DELETE inside the bounded loop.
_PURGE_BATCH_SIZE = 10_000
#: The inherited archiver capability must not be able to erase recent audit
#: history. A cutoff more recent than this is rejected by the function itself.
_MIN_PURGE_AGE = "30 days"


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _duplicate_role_pgcode(exc: Exception) -> str | None:
    """SQLSTATE of a duplicate-role error, unwrapping Django's psycopg2 cause.

    Django raises ``django.db.utils.ProgrammingError`` and keeps the psycopg2
    exception on ``__cause__``; the ``pgcode`` lives there, not on the wrapper.
    Reading only the wrapper makes the duplicate 23505/42710 invisible and the
    migration aborts exactly in the xdist race this guard exists for (mirrors
    ``persistence/migrations/0048_app_role.py``).
    """
    return getattr(exc, "pgcode", None) or getattr(
        getattr(exc, "__cause__", None), "pgcode", None
    )


def _create_archiver_role(apps, schema_editor) -> None:
    """Create the cluster-level archiver role, race-safe under xdist (DBE-02).

    Mirrors ``persistence/migrations/0048_app_role.py``: a cluster-wide session
    advisory lock serialises the check/create across xdist workers that share
    one role namespace but use separate test databases; a savepoint and a
    pgcode 42710/23505 guard absorb the race for any caller that bypasses the
    lock. The role is never dropped on reverse (cluster-level object).
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    lock_key = f"{ARCHIVER_DB_ROLE}:create"
    role = _quote_ident(ARCHIVER_DB_ROLE)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [lock_key])
        try:
            cursor.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", [ARCHIVER_DB_ROLE]
            )
            if cursor.fetchone() is None:
                try:
                    with transaction.atomic(using=schema_editor.connection.alias):
                        cursor.execute(
                            f"CREATE ROLE {role} WITH NOLOGIN NOSUPERUSER "
                            f"NOCREATEDB NOCREATEROLE NOREPLICATION"
                        )
                except DatabaseError as exc:
                    # The loser gets duplicate_object (42710) or, on
                    # pg_authid_rolname_index, unique_violation (23505).
                    if _duplicate_role_pgcode(exc) not in {"42710", "23505"}:
                        raise
        finally:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [lock_key])


def _forward_sql() -> str:
    """Build the idempotent forward SQL (schema, function, least-privilege grants).

    Role creation is handled by :func:`_create_archiver_role` (RunPython) so the
    advisory-lock/savepoint/pgcode race guard can be expressed in Python.
    """
    archiver = _quote_ident(ARCHIVER_DB_ROLE)
    app = _quote_ident(APP_DB_ROLE)
    return f"""
CREATE SCHEMA IF NOT EXISTS {_MAINTENANCE_SCHEMA};

GRANT USAGE ON SCHEMA {_MAINTENANCE_SCHEMA} TO {archiver}, {app};

CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}(p_cutoff timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
DECLARE
    v_batch integer;
    v_total integer := 0;
BEGIN
    -- Bound the elevated (inherited) capability: a caller may choose any
    -- cutoff, but never one that would erase audit history newer than the
    -- minimum purge age. This keeps the archiver membership from becoming an
    -- arbitrary audit-erase primitive.
    IF p_cutoff > now() - INTERVAL '{_MIN_PURGE_AGE}' THEN
        RAISE EXCEPTION
            'purge cutoff % is too recent; must be older than %',
            p_cutoff, INTERVAL '{_MIN_PURGE_AGE}'
            USING ERRCODE = '22023';
    END IF;

    -- ACCESS EXCLUSIVE is held for the whole transaction (module docstring).
    -- Batching bounds each DELETE; sum the per-batch ROW_COUNT.
    ALTER TABLE public.audit_entry DISABLE TRIGGER {_TRIGGER_NAME};
    LOOP
        DELETE FROM public.audit_entry
         WHERE id IN (
             SELECT id FROM public.audit_entry
              WHERE timestamp < p_cutoff
              ORDER BY id
              LIMIT {_PURGE_BATCH_SIZE}
         );
        GET DIAGNOSTICS v_batch = ROW_COUNT;
        v_total := v_total + v_batch;
        EXIT WHEN v_batch = 0;
    END LOOP;
    ALTER TABLE public.audit_entry ENABLE TRIGGER {_TRIGGER_NAME};
    RETURN v_total;
EXCEPTION WHEN OTHERS THEN
    -- The trigger must survive a failed DELETE. Re-enable before re-raising;
    -- the exception propagates so the caller's transaction still rolls back.
    ALTER TABLE public.audit_entry ENABLE TRIGGER {_TRIGGER_NAME};
    RAISE;
END;
$func$;

REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC;
REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM {app};
GRANT EXECUTE ON FUNCTION {_FUNCTION_SIGNATURE} TO {archiver};
-- Runtime connects as APP_DB_ROLE. Direct EXECUTE was revoked above; the
-- capability is reachable only through this explicit, revocable membership.
-- The membership is cluster-level and is deliberately NOT revoked on reverse.
GRANT {archiver} TO {app};
"""


def _reverse_sql() -> str:
    """Build the reverse SQL — drops this DB's objects, never the cluster role.

    Neither the archiver role nor its membership in the app role is removed:
    both are cluster-level objects shared by every database on the server
    (mirroring ``persistence/migrations/0048_app_role.py`` and ``0110``).
    """
    archiver = _quote_ident(ARCHIVER_DB_ROLE)
    app = _quote_ident(APP_DB_ROLE)
    return f"""
REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM {archiver};
DROP FUNCTION IF EXISTS {_FUNCTION_SIGNATURE};
REVOKE USAGE ON SCHEMA {_MAINTENANCE_SCHEMA} FROM {archiver}, {app};
DROP SCHEMA IF EXISTS {_MAINTENANCE_SCHEMA};
"""


class Migration(migrations.Migration):
    """Install the bounded audit-retention purge helper.

    Depends on the append-only trigger (0002) and on the least-privilege app
    role (persistence 0048) so all referenced objects exist before grants.
    """

    dependencies = [
        ("audit", "0019_auditentry_op_artifact_summary_generate"),
        ("audit", "0002_append_only_trigger"),
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunPython(
            _create_archiver_role, reverse_code=migrations.RunPython.noop
        ),
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
