"""
ASGI config for ReqFlow project.

It exposes the ASGI callable as a module-level variable named ``application``.

This is the entry point for *both* deployments:

* production — ``gunicorn reqogniloom.asgi:application -k
  uvicorn.workers.UvicornWorker`` (see ``backend/Dockerfile``), and
* development — ``uvicorn reqogniloom.asgi:application --reload`` (see
  ``docker-compose.override.yml``).

ASGI is mandatory rather than a preference: the MCP SSE transport
(``GET /mcp/sse/``) is an async streaming view, and Django can only serve an
async iterator over WSGI by buffering it in full — which never terminates for
an endless event stream (issue #455).
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reqogniloom.settings")

application = get_asgi_application()

# Serve ``/static/`` in development only.
#
# ``manage.py runserver`` wraps its handler in a StaticFilesHandler; a plain
# ASGI server does not, so switching the dev stack from runserver to uvicorn
# would otherwise 404 every asset behind ``/admin/`` and the drf-spectacular
# Swagger UI. Mirror runserver's behaviour under the same condition it uses
# (``DEBUG``). In production ``DJANGO_ENV`` forces ``DEBUG = False``
# (REQ-115 hardening), so this wrapper is never installed there and static
# files stay the reverse proxy's job — unchanged from before.
from django.conf import settings  # noqa: E402  (settings need the app registry)

if settings.DEBUG:
    from django.contrib.staticfiles.handlers import (  # noqa: E402
        ASGIStaticFilesHandler,
    )

    application = ASGIStaticFilesHandler(application)
