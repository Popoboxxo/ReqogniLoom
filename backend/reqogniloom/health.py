"""Simple health check endpoint for container readiness and liveness probes.

COMP-RA-006 HealthEndpoint — supports Kubernetes and Docker health checks.
Implements both /health/ready (readiness) and /health/live (liveness) patterns.
"""
import logging
from django.conf import settings as django_settings
from django.http import JsonResponse
from django.db import connection
from django.views import View

logger = logging.getLogger(__name__)


def _embedding_dimension_mismatches() -> list:
    """Return the labels of embedding columns that do not match the provider.

    Mirrors ``application.management.commands.verify_embedding_dimensions``: the
    comparison is between the *physical* ``pg_attribute`` type and the
    *configured embedding provider's* output width — the actual silent-skip
    cause (#1018/#1019). Comparing against the width the *models* declare would
    miss exactly the drift this check exists for, because the models follow
    ``EMBEDDING_VECTOR_DIMENSIONS`` immediately while the physical columns only
    change when DDL runs.

    Read-only and bounded: one ``pg_attribute`` lookup per known embedding
    column. Only column labels are returned — never a type from an arbitrary
    source, never a DSN — so the result is safe to expose on the
    unauthenticated ``/health/`` endpoint (CWE-209).

    Returns:
        One label per mismatching (or missing) embedding column; empty when
        every column matches the configured provider's width.
    """
    from llm_adapter.embedding_service import (
        EMBEDDING_PROVIDER_REGISTRY,
        _read_config,
        get_embedding_provider,
    )
    from persistence.embedding_schema import column_type, embedding_columns

    cfg = _read_config()
    if cfg.provider_name not in EMBEDDING_PROVIDER_REGISTRY:
        # An unknown provider is already reported by the llm_adapter.W002
        # system check; there is no width to compare against here, so do not
        # raise a second, misleading alarm.
        return []

    expected = f"vector({get_embedding_provider(cfg).dimensions})"
    mismatches = []
    with connection.cursor() as cursor:
        for column in embedding_columns():
            if column_type(cursor, column.table, column.column) != expected:
                mismatches.append(column.label)
    return mismatches


class HealthView(View):
    """Health check endpoint for container orchestration.

    GET /health/ returns:
    - 200 OK if all checks pass: {"status": "ok", "checks": {...}}
    - 503 Service Unavailable if degraded: {"status": "degraded", "checks": {...}}

    Checks:
    - database: PostgreSQL connectivity via Django ORM
    - memory_backend: the active memory/embedding backend's bounded probe
    - embedding_dimensions: the physical pgvector column width vs. the
      configured embedding provider's output width (a mismatch silently
      disables embedding writes and semantic search, #1018/#1019)
    """

    def get(self, request):
        """Execute health checks and return aggregated status."""
        status = {"status": "ok", "checks": {}, "warnings": []}
        http_status = 200

        # Database connectivity check
        try:
            connection.ensure_connection()
            status["checks"]["database"] = "ok"
        except Exception as e:
            # #697 (CWE-209): /health/ is reachable without authentication, and
            # a psycopg error's str() carries host, port, user and DSN
            # fragments. The probe only reads the status code, so the client
            # gets a static marker while the real cause goes to the log —
            # same pattern as the workflow-definition check below.
            status["checks"]["database"] = "error"
            status["status"] = "degraded"
            http_status = 503
            logger.warning("Health check: database degraded - %s", e)

        # Memory / embedding probe (#911): a container can pass the database
        # check while its memory backend cannot embed at all — the shipped
        # defect was Honcho's embedding base URL (`HONCHO_EMBEDDING_BASE_URL`)
        # resolving to an unreachable host, so every memory WRITE failed while
        # `/health/` still reported "ok". The active backend's own bounded
        # `health_check()` performs the real embedding probe (for
        # `HonchoMemoryBackend` that is a single OpenAI-compatible
        # `/embeddings` request; for the default pgvector backend a table
        # reachability query). Only a static marker reaches the client: the
        # detail can quote a host or DSN and `/health/` is reachable without
        # authentication, so the real cause goes to the log — same CWE-209
        # handling as the database check above. Skipped when the DB is down
        # (the backend lookup reads the DB) and never allowed to raise.
        if status["checks"]["database"] == "ok":
            try:
                from memory.backends import get_memory_backend

                memory_ok, memory_detail = get_memory_backend().health_check()
            except Exception as e:  # noqa: BLE001 - health check must never crash
                memory_ok, memory_detail = False, e
            status["checks"]["memory_backend"] = "ok" if memory_ok else "error"
            if not memory_ok:
                status["status"] = "degraded"
                http_status = 503
                logger.warning(
                    "Health check: memory backend degraded - %s", memory_detail
                )

        # Embedding-column dimension check (#1018/#1019): the physical pgvector
        # column width is fixed by the last migration that ran, while the
        # configured embedding provider's width is fixed at container start.
        # When they disagree every embedding write and every semantic search
        # pass is skipped *silently* (the write guard is best-effort by
        # design), so the only symptom is an artifact.search that never returns
        # semantic hits. `manage.py verify_embedding_dimensions` and the
        # `llm_adapter.W001` system check already detect it, but both are
        # pull-based and manual; this surfaces it where a deployment is
        # actually watched.
        #
        # Deliberately a WARNING (HTTP 200), not `degraded` (503): a width
        # mismatch disables semantic search but every read and write path still
        # works, so a container/k8s liveness probe must not restart-loop a stack
        # that is otherwise serving traffic. In the aligned state (`"ok"`) this
        # adds no warning at all, so it can never trigger a 503 cascade.
        # Skipped when the DB is down (it needs the catalog) and never allowed
        # to raise. Only a static marker and column labels reach the client; the
        # detail goes to the log — same CWE-209 handling as the checks above.
        if status["checks"]["database"] == "ok":
            try:
                dimension_mismatches = _embedding_dimension_mismatches()
            except Exception as e:  # noqa: BLE001 - health check must never crash
                logger.warning(
                    "Health check: embedding-dimension check failed - %s", e
                )
                status["warnings"].append("embedding-dimension check failed")
            else:
                status["checks"]["embedding_dimensions"] = (
                    "mismatch" if dimension_mismatches else "ok"
                )
                if dimension_mismatches:
                    logger.warning(
                        "Health check: embedding dimension mismatch - %s",
                        ", ".join(dimension_mismatches),
                    )
                    status["warnings"].append(
                        "embedding columns do not match the configured embedding "
                        "provider's output width — embedding writes and semantic "
                        "search are silently skipped. Run `python manage.py "
                        "verify_embedding_dimensions` for the column list and the "
                        "provider's expected width. BEFORE resizing, set "
                        "EMBEDDING_VECTOR_DIMENSIONS to that provider width: "
                        "running `python manage.py align_embedding_dimensions` "
                        "(image deployment) or makemigrations/migrate (source "
                        "checkout) while EMBEDDING_VECTOR_DIMENSIONS still holds "
                        "a stale width would rewrite the columns at that wrong "
                        "width and discard the stored vectors — the mismatch "
                        "would remain."
                    )

        # CSRF-cookie security check: AUTH_COOKIE_SECURE must match CSRF_COOKIE_SECURE
        # to avoid CSRF failures in deployments without a TLS-terminating reverse proxy.
        csrf_matches = (
            django_settings.CSRF_COOKIE_SECURE == django_settings.AUTH_COOKIE_SECURE
        )
        status["checks"]["csrf_cookie_secure_matches_auth"] = (
            "ok" if csrf_matches else "mismatch"
        )
        if not csrf_matches:
            # Escalate via the same `warnings` mechanism the workflow check
            # below uses: status becomes "warning", http_status stays 200 so
            # container/k8s probes are unaffected.
            status["warnings"].append(
                "CSRF_COOKIE_SECURE "
                f"({django_settings.CSRF_COOKIE_SECURE}) does not match "
                f"AUTH_COOKIE_SECURE ({django_settings.AUTH_COOKIE_SECURE}) — "
                "expect CSRF failures in deployments without a "
                "TLS-terminating reverse proxy"
            )

        # Workflow-definition sanity check (#40): a GlobalWorkflowDefinition or
        # WorkflowEngineDefinition row with no `states` (empty list or missing
        # key) means the workflow was never actually initialized — items of
        # that type/workspace cannot transition. This previously went
        # unnoticed after a fresh deploy/migration until a client tried to use
        # the workflow. Only run once DB connectivity is confirmed above.
        if status["checks"]["database"] == "ok":
            try:
                from django.db.models import Q

                from workflow.models import (
                    GlobalWorkflowDefinition,
                    WorkflowEngineDefinition,
                )

                empty_states = Q(workflow_json__states=[]) | ~Q(
                    workflow_json__has_key="states"
                )
                empty_globals = GlobalWorkflowDefinition.unscoped.filter(
                    empty_states
                ).count()
                empty_workspace = WorkflowEngineDefinition.unscoped.filter(
                    empty_states
                ).count()
                if empty_globals:
                    status["warnings"].append(
                        f"{empty_globals} global workflow definition(s) have no states defined"
                    )
                if empty_workspace:
                    status["warnings"].append(
                        f"{empty_workspace} workspace workflow definition(s) have no states defined"
                    )
            except Exception as e:  # noqa: BLE001 - health check must never crash
                logger.warning("Health check: workflow-definition check failed - %s", e)
                status["warnings"].append("workflow-definition check failed")

        if status["warnings"] and status["status"] == "ok":
            status["status"] = "warning"

        return JsonResponse(status, status=http_status)
