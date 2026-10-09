"""Worker ``SECURITY DEFINER`` helpers for the staged ``as_*`` RLS policy (#1183, A4).

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as a second isolation layer behind the ORM tenant filter)

Background:
    ``application/0032`` puts a GUC-guarded, permissive RLS policy on the four
    worker-owned ``as_*`` tables. When ``RLS_AS_ENFORCED=on`` the Celery outbox
    poller (``application.event_bus.poll_and_dispatch``) can no longer select
    its candidate rows without a tenant context — and it cannot know *which*
    tenant to arm before it has read the rows' ``tenant_id``. That is the
    chicken-and-egg this migration solves (A4, residual R-2).

    ``public.as_outbox_candidates`` is a read-only ``SECURITY DEFINER``
    candidate-list/tenant-resolver: it runs with the owner's privileges (the
    migration/bootstrap role, which bypasses the policy) and returns the
    ``(id, tenant_id)`` of every unpublished, claimable outbox row. The poller
    then arms ``app.current_tenant`` *per row* before claim/dispatch/write-back,
    so the policy's ``USING``/``WITH CHECK`` clauses pass.

    Orphan rows (``tenant_id IS NULL``) are **excluded** from the candidate
    list. They are invisible to the armed app role anyway, so the poller could
    only ever skip them — but because the candidate query is
    ``ORDER BY created_at LIMIT batch_size``, a head-of-line block of orphans
    would otherwise consume the whole batch and starve legitimate events behind
    them (a silent event-bus stall under ``RLS_AS_ENFORCED=on``). Excluding them
    at the source closes that head-of-line hazard; they stay surfaced (counted,
    never hidden) through the companion backlog read below.

    ``public.as_worker_backlog`` is the companion cross-tenant monitoring read:
    the backlog/DLQ counters at the end of the poll cycle must aggregate across
    tenants (the poller is tenant-agnostic), which a plain app-role query cannot
    do under enforcement. Its ``orphan_pending`` column counts the unpublished
    NULL-tenant rows excluded from the candidate list, so the fail-closed
    orphans O-2 requires to be "counted and logged, never deleted" remain
    observable even though they can no longer block the poller.

Security posture (mirrors ``auth_tenancy/0016`` and its documented residuals):
    * ``SECURITY DEFINER``; owner is the table owner (the migration/bootstrap
      role) at creation time, NOT ``APP_DB_ROLE`` — otherwise the definer would
      be subject to the very policy it must bypass. ``persistence/0110`` (issue
      #1180) then transfers ownership to the dedicated non-superuser
      ``DEFINER_DB_ROLE``, closing residual R-8.
    * ``SET search_path = pg_catalog, pg_temp`` (no ``public``): hijack-safe.
    * Every relation is schema-qualified; the bodies are plain ``LANGUAGE sql``
      with no dynamic SQL (no ``EXECUTE``/``format``/``quote_ident``).
    * ``REVOKE ALL ... FROM PUBLIC`` then ``GRANT EXECUTE ... TO APP_DB_ROLE``
      (``0048_app_role`` grants only CRUD, no function EXECUTE).
    * Read-only: the functions cannot be turned into a cross-tenant write
      primitive.

Reverse: drop both functions.
"""
from __future__ import annotations

from django.db import migrations

from persistence.db_roles import APP_DB_ROLE

CANDIDATES_SIGNATURE = "public.as_outbox_candidates(integer, timestamp with time zone)"
BACKLOG_SIGNATURE = "public.as_worker_backlog()"


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier, doubling embedded double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _forward_sql() -> str:
    role = _quote_ident(APP_DB_ROLE)
    return f"""
CREATE OR REPLACE FUNCTION public.as_outbox_candidates(
    p_batch_size integer, p_reclaim_cutoff timestamptz
)
RETURNS TABLE (id uuid, tenant_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT o.id, o.tenant_id
    FROM public.as_domain_event_outbox AS o
    WHERE o.published = false
      AND (o.claimed_at IS NULL OR o.claimed_at < p_reclaim_cutoff)
      -- F3 (#1183 review): an orphan can never be claimed (no tenant to arm),
      -- so including it here would only consume a batch slot and, at the head
      -- of the ORDER BY created_at window, starve legitimate events behind it.
      AND o.tenant_id IS NOT NULL
    ORDER BY o.created_at
    LIMIT p_batch_size;
$func$;
REVOKE ALL ON FUNCTION {CANDIDATES_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {CANDIDATES_SIGNATURE} TO {role};

-- F3 (#1183 review): the return type gained ``orphan_pending``; CREATE OR
-- REPLACE cannot change a function's return type, so drop the function first.
-- Safe because 0033 is the only creator and 0110 (ownership transfer) runs
-- after it on a fresh deploy.
DROP FUNCTION IF EXISTS {BACKLOG_SIGNATURE};
CREATE OR REPLACE FUNCTION public.as_worker_backlog()
RETURNS TABLE (outbox_pending bigint, dlq_total bigint, orphan_pending bigint)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $func$
    SELECT
        (SELECT count(*) FROM public.as_domain_event_outbox
          WHERE published = false),
        (SELECT count(*) FROM public.as_domain_event_dlq),
        -- The rows the candidate list deliberately excludes: surfaced so they
        -- are counted (never hidden) and can be backfilled/stamped by an
        -- operator (O-2: never deleted).
        (SELECT count(*) FROM public.as_domain_event_outbox
          WHERE published = false AND tenant_id IS NULL);
$func$;
REVOKE ALL ON FUNCTION {BACKLOG_SIGNATURE} FROM PUBLIC;
GRANT EXECUTE ON FUNCTION {BACKLOG_SIGNATURE} TO {role};
"""


def _reverse_sql() -> str:
    return (
        f"DROP FUNCTION IF EXISTS {CANDIDATES_SIGNATURE};\n"
        f"DROP FUNCTION IF EXISTS {BACKLOG_SIGNATURE};"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0032_as_staged_rls"),
        # Guarantees APP_DB_ROLE exists before it is granted EXECUTE.
        ("persistence", "0048_app_role"),
    ]

    operations = [
        migrations.RunSQL(sql=_forward_sql(), reverse_sql=_reverse_sql()),
    ]
