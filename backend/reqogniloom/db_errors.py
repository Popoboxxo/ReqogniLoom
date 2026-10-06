"""Map PostgreSQL *connection-capacity* exhaustion to a JSON 503 (issue #1166).

Why this module exists
----------------------
When PostgreSQL runs out of non-superuser backend slots it answers a new
connection with::

    FATAL:  remaining connection slots are reserved for roles with the
            SUPERUSER attribute

(the superuser variant is ``FATAL: sorry, too many clients already``). Django
surfaces that as :class:`django.db.utils.OperationalError`, which is *not* a
DRF exception, so the request used to fall through to Django's core handler and
return an HTML 500 — a body no API client can parse and a status that wrongly
claims a server bug instead of temporary overload.

The predicate here is deliberately narrow: only an ``OperationalError`` whose
message matches one of the known capacity signatures is a *saturation* error.
Every other ``OperationalError`` (bad password, missing database, DNS failure,
…) keeps its existing handling — we must never swallow a genuine configuration
fault behind a "try again" 503.

The module has no DRF/Django-app imports beyond the exception type, so both the
DRF exception handler (``rest_api.error_envelope``), the request middleware
(``reqogniloom.middleware``) and the readiness probe (``reqogniloom.health``)
can share one definition.
"""
from __future__ import annotations

import re

from django.db.utils import OperationalError

#: Stable machine-readable code carried in the error envelope.
DB_UNAVAILABLE_CODE = "DB_UNAVAILABLE"

#: Operator/client-facing message. Deliberately static: it never embeds the raw
#: psycopg text (which can carry host/user/DSN fragments — CWE-209). The real
#: cause is logged by the caller.
DB_UNAVAILABLE_MESSAGE = (
    "The database is temporarily unable to accept new connections. "
    "This is usually transient server overload; retry the request shortly."
)

#: Narrow capacity-exhaustion signatures. PostgreSQL emits the first two; the
#: third covers a pooler (e.g. PgBouncer) refusing an upstream connection.
_SATURATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"remaining connection slots are reserved", re.IGNORECASE),
    re.compile(r"too many clients already", re.IGNORECASE),
    re.compile(r"too many connections", re.IGNORECASE),
)


def is_db_saturation_error(exc: BaseException) -> bool:
    """Return True only for a connection-capacity ``OperationalError``.

    Args:
        exc: The exception raised while serving a request.

    Returns:
        ``True`` when *exc* is a :class:`django.db.utils.OperationalError` whose
        message matches a known "no free slots / too many connections"
        signature; ``False`` for every other exception, including unrelated
        ``OperationalError``s.
    """
    if not isinstance(exc, OperationalError):
        return False
    message = str(exc)
    return any(pattern.search(message) for pattern in _SATURATION_PATTERNS)


def db_unavailable_payload() -> dict:
    """Return the existing ``{"error": {code, message, details}}`` envelope body.

    Mirrors ``rest_api.serializers.build_error_response`` (REQ-L2-RA-009) so a
    client sees the exact same shape it already handles for every other API
    error.
    """
    return {
        "error": {
            "code": DB_UNAVAILABLE_CODE,
            "message": DB_UNAVAILABLE_MESSAGE,
            "details": [],
        }
    }


__all__ = [
    "DB_UNAVAILABLE_CODE",
    "DB_UNAVAILABLE_MESSAGE",
    "db_unavailable_payload",
    "is_db_saturation_error",
]
