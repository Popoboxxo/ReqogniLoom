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
from pathlib import Path
from typing import Any

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# Placeholder surfaced when neither the APP_VERSION env var nor the root
# VERSION file yields a usable value.
_UNKNOWN = "unknown"

# Root VERSION file, resolved relative to this module:
#   backend/reqogniloom/version.py -> backend/reqogniloom -> backend -> <repo root>
# Only present for local/non-container runs; a built image ships no repo root,
# so the container path relies on the APP_VERSION env var (stamped at build).
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"


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


def _resolve_app_version() -> str:
    """Resolve the human-facing application (release) version.

    Resolution order:
    1. ``APP_VERSION`` env var — stamped at Docker build time from the root
       ``VERSION`` file. Authoritative for a real deployed container, which
       ships no repo root. ``"unknown"`` (the docker-compose default) is
       treated as "not set" so the file fallback below runs instead.
    2. The root ``VERSION`` file, read directly — dev-convenience fallback for
       local/non-container runs where the repo root is present.
    3. The literal string ``"unknown"``.

    A missing/unreadable/empty VERSION file never crashes the endpoint: it logs
    a warning and falls back to the placeholder.
    """
    env_version = os.environ.get("APP_VERSION")
    if env_version and env_version != _UNKNOWN:
        return env_version.strip()

    try:
        content = _VERSION_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
        logger.warning("VERSION file at %s is empty; app_version unavailable", _VERSION_FILE)
    except FileNotFoundError:
        logger.warning("VERSION file not found at %s; app_version unavailable", _VERSION_FILE)
    except OSError as exc:  # unreadable file, permission error, etc.
        logger.warning("Could not read VERSION file at %s: %s", _VERSION_FILE, exc)

    return _UNKNOWN


class VersionView(APIView):
    """``GET /api/v1/version/`` — deployed build metadata.

    PUBLIC endpoint (``AllowAny``, no ``BearerTokenAuthentication``): commit
    SHA and build time are non-sensitive build metadata, useful to
    unauthenticated monitoring/operators as well.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the app version, deployed commit SHA (full + short) and build time."""
        commit = _resolve_commit_sha()
        commit_short = commit[:7] if commit != "unknown" else "unknown"
        build_time = os.environ.get("BUILD_TIME") or None
        return Response(
            {
                "app_version": _resolve_app_version(),
                "commit": commit,
                "commit_short": commit_short,
                "build_time": build_time,
            }
        )


__all__ = ["VersionView"]
