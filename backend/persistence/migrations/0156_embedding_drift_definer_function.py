"""Corpus-wide embedding-model drift counts behind a ``SECURITY DEFINER`` helper (#1959).

Requirements:
- ADR-010 (advisory signals never become a ``checks`` entry or a 503)
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)

Background:
    ``GET /health/ready?verbose=1`` publishes an ``embedding_model_drift``
    advisory: for each embedding table, how many rows carry a non-NULL
    ``embedding_model`` that differs from the model the active configuration
    would write today. A model change with unchanged vector width is invisible
    to a cosine query, so this count is the only early warning that the corpus
    mixes vector spaces.

    The endpoint is unauthenticated and sets no tenant, while all four embedding
    tables (``pl_requirement``, ``pl_tracelink``, ``icd_icd``,
    ``mem_memory_entry``) are ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` keyed on
    ``app.current_tenant``. The shipped app role has ``rolbypassrls=false``, and
    ``unscoped`` skips only the ORM tenant filter — so a direct aggregate reads
    zero rows and used to be reported as ``unknown`` forever (never as a false
    clean bill, but never authoritative either). The owner-only
    ``verify_embedding_dimensions --models`` command sees clean data because it
    runs as the migration/owner role.

    This migration closes that gap for operators who opt in with
    ``HEALTH_EMBEDDING_DRIFT_AUTHORITATIVE=true``: a single read-only, corpus-wide
    aggregate runs behind ``SECURITY DEFINER`` and is callable by the app role.
    The health endpoint still degrades gracefully when the flag is off or the
    helper is unavailable (see ``reqogniloom.health._embedding_model_drift``).

Security posture (matches ``application/0033`` and ``auth_tenancy/0034``):
    * ``SECURITY DEFINER`` owned by ``persistence.db_roles.DEFINER_DB_ROLE``
      (``NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS``),
      never by ``APP_DB_ROLE`` — otherwise the body would be subject to the very
      ``FORCE ROW LEVEL SECURITY`` policies it must see past.
    * ``SET search_path = pg_catalog, pg_temp`` (no ``public``) and every
      relation schema-qualified: hijack-safe. Plain ``LANGUAGE sql`` with no
      dynamic SQL (no ``EXECUTE``/``format``/``quote_ident`` in the body).
    * ``STABLE`` and read-only: the helper cannot become a cross-tenant write
      primitive. One conditional count per table, never a row scan in Python.
    * ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``;
      the only new table privilege for the definer is SELECT on the four
      tables, also declared in ``persistence/0110``'s inventory.
    * No new DB alias, no new role, no new secret.

Reverse: drop the function and revoke the grants installed here (0110's own
reverse revokes the same table grants idempotently).
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE, DEFINER_DB_ROLE

FUNCTION_SIGNATURE = "public.embedding_model_drift_counts(text)"

#: Corpus-wide, provenance-aware count for each embedding table. ``NULL``
#: ``embedding_model`` marks a legacy row written before provenance existed;
#: like the health advisory and ``verify_embedding_dimensions --models``, those
#: rows are deliberately NOT drift. ``NULL`` ``embedding`` rows are skipped too.
_EMBEDDING_TABLES: tuple[str, ...] = (
    "pl_requirement",
    "pl_tracelink",
    "icd_icd",
    "mem_memory_entry",
)


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _table_grants_sql() -> str:
    """SELECT-only grants on the four tables the definer body reads.

    Existing deployments already ran 0110 before this migration was added, so
    the grants must be (re)issued here too: 0110's forward pass is not replayed.
    """
    role = _quote_ident(DEFINER_DB_ROLE)
    tables = ", ".join(f"public.{_quote_ident(t)}" for t in _EMBEDDING_TABLES)
    return f"GRANT SELECT ON {tables} TO {role};"


def _table_revokes_sql() -> str:
    role = _quote_ident(DEFINER_DB_ROLE)
    tables = ", ".join(f"public.{_quote_ident(t)}" for t in _EMBEDDING_TABLES)
    return f"REVOKE ALL PRIVILEGES ON {tables} FROM {role};"


def _forward_sql() -> str:
    app_role = _quote_ident(APP_DB_ROLE)
    owner = _quote_ident(DEFINER_DB_ROLE)
    counts = ",\n".join(
        f"        (SELECT count(*) FROM public.{_quote_ident(table)}\n"
        "          WHERE embedding IS NOT NULL\n"
        "            AND embedding_model IS NOT NULL\n"
        "            AND embedding_model <> p_model_id)"
        for table in _EMBEDDING_TABLES
    )
    return f"""
CREATE OR REPLACE FUNCTION public.embedding_model_drift_counts(p_model_id text)
RETURNS TABLE (requirement bigint, tracelink bigint, icd bigint, memory bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT
{counts};
$func$;

ALTER FUNCTION {FUNCTION_SIGNATURE} OWNER TO {owner};
REVOKE ALL ON FUNCTION {FUNCTION_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {FUNCTION_SIGNATURE} TO {app_role};
{_table_grants_sql()}
"""


def _reverse_sql() -> str:
    return (
        f"DROP FUNCTION IF EXISTS {FUNCTION_SIGNATURE};\n"
        f"{_table_revokes_sql()}"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0155_system_artifact_vector_settings"),
        # DEFINER_DB_ROLE exists and its inventory already names this function.
        ("persistence", "0110_security_definer_owner_role"),
        # The embedding_model columns the body reads are added by these.
        ("icd", "0014_icd_embedding_model"),
        ("memory", "0009_memoryentry_embedding_model"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
