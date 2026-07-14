"""Simple health check endpoint for container readiness and liveness probes.

COMP-RA-006 HealthEndpoint — supports Kubernetes and Docker health checks.
Implements both /health/ready (readiness) and /health/live (liveness) patterns.
"""
import logging
from django.http import JsonResponse
from django.db import connection
from django.views import View

logger = logging.getLogger(__name__)


class HealthView(View):
    """Health check endpoint for container orchestration.

    GET /health/ returns:
    - 200 OK if all checks pass: {"status": "ok", "checks": {...}}
    - 503 Service Unavailable if degraded: {"status": "degraded", "checks": {...}}

    Checks:
    - database: PostgreSQL connectivity via Django ORM
    """

    def get(self, request):
        """Execute health checks and return aggregated status."""
        status = {"status": "ok", "checks": {}}
        http_status = 200

        # Database connectivity check
        try:
            connection.ensure_connection()
            status["checks"]["database"] = "ok"
        except Exception as e:
            status["checks"]["database"] = f"error: {str(e)}"
            status["status"] = "degraded"
            http_status = 503
            logger.warning("Health check: database degraded - %s", e)

        return JsonResponse(status, status=http_status)
