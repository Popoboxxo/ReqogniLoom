"""
admin_ops — REST adapter for the system health dashboard (admin-only).

Drives ``GET /api/v1/admin/health/``: a single, fast, non-blocking snapshot
of the runtime infrastructure (database, redis, celery worker/beat, MCP
server, LLM provider config, memory embedding provider, memory backend)
plus the most recent audit-log entries.

Design constraints:

* Admin-only — reuses the exact same RBAC pattern as
  :mod:`admin_ops.rest` (:class:`HasOperationPermission` with
  :attr:`Operation.WORKSPACE_CONFIG`, the only operation reserved to
  ``ROLE_ADMIN`` in the RBAC matrix).
* Every component check is wrapped so a single failing dependency never
  raises past the view — a broken Redis must not turn this into a 500,
  it must show up as one ``"down"`` row in the response.
* Every check uses short, explicit timeouts (socket/inspect timeouts of
  ~1s) for network-backed dependencies; the in-process embedding check
  avoids probing an unloaded model instead of blocking (see
  ``_check_memory_embedding``).
* ``celery_beat`` cannot verify that a beat *process* is actually
  running from inside a web worker without side effects (e.g. writing a
  heartbeat key), so it intentionally reports ``"unknown"`` rather than
  a potentially-misleading ``"ok"``/``"down"`` — it only confirms that
  the periodic-task schedule table is reachable.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import connection
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditEntry
from auth_tenancy.context import AuthContext
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import Operation
from application.base import PermissionDeniedError

logger = logging.getLogger(__name__)

# Socket-level timeouts (seconds) for infra checks — this endpoint must
# stay fast even when a dependency is unreachable.
_CHECK_TIMEOUT_S = 1.0

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_DOWN = "down"
STATUS_UNKNOWN = "unknown"

_RECENT_EVENTS_LIMIT = 20


# ---------------------------------------------------------------------------
# Component checks — each is independently try/except-guarded so one
# failing dependency cannot break the others or the response as a whole.
# ---------------------------------------------------------------------------


def _check_database() -> dict[str, str]:
    """Check PostgreSQL connectivity (mirrors reqogniloom.health.HealthView)."""
    try:
        connection.ensure_connection()
        return {"name": "database", "status": STATUS_OK, "detail": "connected"}
    except Exception as exc:  # noqa: BLE001 - any DB failure is a "down" row
        logger.warning("System health: database check failed - %s", exc)
        return {"name": "database", "status": STATUS_DOWN, "detail": str(exc)}


def _check_redis() -> dict[str, str]:
    """Check Redis (Celery broker) connectivity via a bounded PING."""
    try:
        import redis  # noqa: PLC0415 - lazy import, only needed here

        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=_CHECK_TIMEOUT_S,
            socket_timeout=_CHECK_TIMEOUT_S,
        )
        client.ping()
        return {"name": "redis", "status": STATUS_OK, "detail": "PING ok"}
    except Exception as exc:  # noqa: BLE001 - unreachable/misconfigured redis
        logger.warning("System health: redis check failed - %s", exc)
        return {"name": "redis", "status": STATUS_DOWN, "detail": str(exc)}


def _check_celery_worker() -> dict[str, str]:
    """Check for at least one responding Celery worker via a bounded ping."""
    try:
        from reqogniloom.celery import app as celery_app  # noqa: PLC0415 - avoids circular import

        replies = celery_app.control.inspect(timeout=_CHECK_TIMEOUT_S).ping()
        if not replies:
            return {
                "name": "celery_worker",
                "status": STATUS_DOWN,
                "detail": "no worker responded",
            }
        return {
            "name": "celery_worker",
            "status": STATUS_OK,
            "detail": f"{len(replies)} worker(s) responding",
        }
    except Exception as exc:  # noqa: BLE001 - broker unreachable, etc.
        logger.warning("System health: celery worker check failed - %s", exc)
        return {"name": "celery_worker", "status": STATUS_DOWN, "detail": str(exc)}


def _check_celery_beat() -> dict[str, str]:
    """Check that the periodic-task schedule is reachable.

    This does NOT confirm a beat *process* is actually running — doing so
    would require a side-effecting heartbeat mechanism outside this
    endpoint's scope. It only confirms the schedule table is queryable,
    hence the deliberately non-committal ``"unknown"`` status.
    """
    try:
        from django_celery_beat.models import PeriodicTask  # noqa: PLC0415

        enabled_count = PeriodicTask.objects.filter(enabled=True).count()
        return {
            "name": "celery_beat",
            "status": STATUS_UNKNOWN,
            "detail": f"{enabled_count} periodic task(s) configured "
            "(process liveness not verified)",
        }
    except Exception as exc:  # noqa: BLE001 - table missing/unmigrated, etc.
        logger.warning("System health: celery beat check failed - %s", exc)
        return {"name": "celery_beat", "status": STATUS_UNKNOWN, "detail": str(exc)}


def _check_mcp_server() -> dict[str, str]:
    """Check that the MCP tool registry loads and exposes tools.

    Uses the same group-loading path as the real dispatcher
    (:meth:`ToolRegistry._ensure_groups`) but only reads tool schemas —
    no API-key auth is required for this in-process introspection.
    """
    try:
        from mcp_server.tool_registry import ToolRegistry  # noqa: PLC0415

        registry = ToolRegistry()
        registry._ensure_groups()  # noqa: SLF001 - intentional internal use for health check
        seen_group_ids: set[int] = set()
        tool_count = 0
        for group in registry._groups.values():  # noqa: SLF001
            if id(group) in seen_group_ids:
                continue
            seen_group_ids.add(id(group))
            tool_count += len(group.get_tool_schemas())
        if tool_count == 0:
            return {
                "name": "mcp_server",
                "status": STATUS_DOWN,
                "detail": "no tools registered",
            }
        return {
            "name": "mcp_server",
            "status": STATUS_OK,
            "detail": f"{len(seen_group_ids)} tool group(s), {tool_count} tool(s) registered",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("System health: MCP server check failed - %s", exc)
        return {"name": "mcp_server", "status": STATUS_DOWN, "detail": str(exc)}


def _check_llm_provider() -> dict[str, str]:
    """Check LLM adapter configuration (no network call — config-only)."""
    provider = settings.LLM_PROVIDER
    if provider == "mock":
        return {
            "name": "llm_provider",
            "status": STATUS_OK,
            "detail": "provider=mock (no external calls)",
        }
    if settings.LLM_API_KEY:
        return {
            "name": "llm_provider",
            "status": STATUS_OK,
            "detail": f"provider={provider}, API key configured",
        }
    return {
        "name": "llm_provider",
        "status": STATUS_DEGRADED,
        "detail": f"provider={provider}, but LLM_API_KEY is not set",
    }


def _check_memory_embedding() -> dict[str, str]:
    """Check the configured EmbeddingProvider by embedding a short string.

    Uses the normal env-derived config but overrides ``timeout`` to
    ``_CHECK_TIMEOUT_S``. This bounds *network-backed* providers (``ollama``,
    ``openai``) to ~1s. The default in-process ``sentence-transformers``
    provider ignores ``config.timeout`` entirely -- its ``encode()`` call is
    local/CPU-bound, not network I/O, so there is nothing to time out; a cold
    model load or a slow CPU can still take longer than ~1s for that provider.

    Special case: the in-process sentence-transformers provider's model is a
    lazy class-level singleton (see SentenceTransformersEmbeddingProvider).
    If it has not been loaded yet by real usage, this check deliberately
    does NOT trigger a cold load — that can take 20-30s (dominated by the
    torch/sentence_transformers import + model construction), which would
    race this dashboard's own frontend request timeout and could blank out
    every OTHER row on the dashboard too. Reports "unknown" instead,
    mirroring _check_celery_beat's existing side-effect-avoidance policy.
    """
    try:
        import dataclasses

        from llm_adapter.embedding_service import (  # noqa: PLC0415
            SentenceTransformersEmbeddingProvider,
            _read_env_config,
            get_embedding_provider,
        )

        cfg = dataclasses.replace(_read_env_config(), timeout=_CHECK_TIMEOUT_S)
        provider = get_embedding_provider(cfg)

        if (
            isinstance(provider, SentenceTransformersEmbeddingProvider)
            and SentenceTransformersEmbeddingProvider._model is None
        ):
            return {
                "name": "memory_embedding",
                "status": STATUS_UNKNOWN,
                "detail": (
                    "in-process sentence-transformers model not yet loaded in "
                    "this worker process; skipped to avoid a slow cold load "
                    "(will report ok/down once loaded by real usage)"
                ),
            }

        vector = provider.embed("ping")
        if vector is None:
            return {
                "name": "memory_embedding",
                "status": STATUS_DOWN,
                "detail": "embed() returned no vector",
            }
        if len(vector) != provider.dimensions:
            return {
                "name": "memory_embedding",
                "status": STATUS_DEGRADED,
                "detail": f"expected {provider.dimensions} dims, got {len(vector)}",
            }
        return {
            "name": "memory_embedding",
            "status": STATUS_OK,
            "detail": f"{provider.dimensions}-dim vector returned",
        }
    except Exception as exc:  # noqa: BLE001 - provider unreachable/misconfigured
        logger.warning("System health: memory embedding check failed - %s", exc)
        return {"name": "memory_embedding", "status": STATUS_DOWN, "detail": str(exc)}


def _check_memory_backend() -> dict[str, str]:
    """Check the configured MemoryBackend via its own health_check()."""
    try:
        from memory.backends import get_memory_backend  # noqa: PLC0415

        backend = get_memory_backend()
        ok, detail = backend.health_check()
        return {
            "name": "memory_backend",
            "status": STATUS_OK if ok else STATUS_DOWN,
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 - backend unreachable/misconfigured
        logger.warning("System health: memory backend check failed - %s", exc)
        return {"name": "memory_backend", "status": STATUS_DOWN, "detail": str(exc)}


def _recent_audit_events(limit: int = _RECENT_EVENTS_LIMIT) -> list[dict[str, Any]]:
    """Return the most recent audit-log entries, newest first.

    ``AuditEntry`` is a :class:`TenantScopedModel`; the default manager is
    already scoped to the current request's tenant via the standard
    tenant-context middleware, matching how every other admin view reads
    tenant-scoped data.
    """
    rows = AuditEntry.objects.order_by("-timestamp")[:limit]
    return [
        {
            "id": str(row.id),
            "actor": row.actor,
            "actor_type": row.actor_type,
            "op": row.op,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "source": row.source,
            "change_reason": row.change_reason or "",
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# SystemHealthView
# ---------------------------------------------------------------------------


class SystemHealthView(APIView):
    """``GET /api/v1/admin/health/`` — admin-only system health snapshot.

    Permissions:
        :class:`HasOperationPermission` with ``Operation.WORKSPACE_CONFIG``
        — the same admin-only RBAC gate used by
        :class:`admin_ops.rest.BackupListCreateView`.

    Returns 200::

        {
          "components": [
            {"name": "database", "status": "ok", "detail": "..."},
            {"name": "redis", "status": "ok", "detail": "..."},
            {"name": "celery_worker", "status": "ok", "detail": "..."},
            {"name": "celery_beat", "status": "unknown", "detail": "..."},
            {"name": "mcp_server", "status": "ok", "detail": "..."},
            {"name": "llm_provider", "status": "ok", "detail": "..."},
            {"name": "memory_embedding", "status": "ok", "detail": "..."},
            {"name": "memory_backend", "status": "ok", "detail": "..."}
          ],
          "recent_events": [ {...AuditEntry...}, ... ]
        }

    ``status`` is one of ``ok`` / ``degraded`` / ``down`` / ``unknown``.
    """

    permission_classes = [HasOperationPermission]
    required_operation = Operation.WORKSPACE_CONFIG

    @staticmethod
    def _auth_context(request: Request) -> AuthContext:
        """Return the request's auth context (populated by BearerTokenAuthentication)."""
        ctx = getattr(request, "auth_context", None)
        if ctx is None:
            raise PermissionDeniedError("Authentication required.")
        return ctx

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Run all component checks and return the aggregated snapshot."""
        # DRF's HasOperationPermission already enforces the admin gate before
        # dispatch() reaches here; this call is a defensive backstop matching
        # the pattern used by the other admin_ops views.
        try:
            self._auth_context(request)
        except PermissionDeniedError as exc:
            return Response(
                {"error": "PERMISSION_DENIED", "message": str(exc)},
                status=403,
            )

        components = [
            _check_database(),
            _check_redis(),
            _check_celery_worker(),
            _check_celery_beat(),
            _check_mcp_server(),
            _check_llm_provider(),
            _check_memory_embedding(),
            _check_memory_backend(),
        ]
        return Response(
            {
                "components": components,
                "recent_events": _recent_audit_events(),
            }
        )


__all__ = ["SystemHealthView"]
