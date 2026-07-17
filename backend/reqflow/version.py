"""
Build/version metadata endpoint — exposes the deployed git commit.

Lets an operator/admin verify which commit is actually running in a given
container without shelling in, by comparing ``GET /api/v1/version/`` against
the release they expect to be live.

Sits alongside ``health.py`` (both are lightweight, infrastructure-facing
endpoints rather than domain resources), but is wired under ``/api/v1/`` as a
DRF ``APIView`` — like ``LoginView`` — so it is public (``AllowAny``) without
requiring a Bearer token/tenant context, and is non-sensitive build metadata.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _resolve_commit_sha() -> str:
    """Resolve the running git commit SHA.

    Resolution order:
    1. ``GIT_COMMIT_SHA`` env var — stamped at Docker build time. This is the
       authoritative source for a real deployed container, which typically
       ships no ``.git`` directory.
    2. ``git rev-parse HEAD`` against the repo — dev-convenience fallback for
       local/non-container runs where ``.git`` happens to be present.
    3. The literal string ``"unknown"``.
    """
    # REQ-158: "unknown" is the docker-compose default for GIT_COMMIT_SHA and
    # must be treated as "not set" so the git rev-parse fallback below runs
    # instead of surfacing the literal placeholder to the UI.
    env_sha = os.environ.get("GIT_COMMIT_SHA")
    if env_sha and env_sha != "unknown":
        return env_sha

    try:
        result = subprocess.run(  # noqa: S603, S607 - fixed args, no shell, no user input
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        sha = result.stdout.strip()
        if sha:
            return sha
    except Exception as exc:  # noqa: BLE001 - any git/OS failure just falls back
        logger.debug("git rev-parse HEAD unavailable: %s", exc)

    return "unknown"


class VersionView(APIView):
    """``GET /api/v1/version/`` — deployed build metadata.

    PUBLIC endpoint (``AllowAny``, no ``BearerTokenAuthentication``): commit
    SHA and build time are non-sensitive build metadata, useful to
    unauthenticated monitoring/operators as well.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the deployed commit SHA (full + short) and build time."""
        commit = _resolve_commit_sha()
        commit_short = commit[:7] if commit != "unknown" else "unknown"
        build_time = os.environ.get("BUILD_TIME") or None
        return Response(
            {
                "commit": commit,
                "commit_short": commit_short,
                "build_time": build_time,
            }
        )


__all__ = ["VersionView"]
