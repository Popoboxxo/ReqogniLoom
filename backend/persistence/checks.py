"""Startup system checks for the staged RLS enforcement flags (issue #1136).

Registered from :meth:`persistence.apps.PersistenceConfig.ready`, so
``manage.py check`` / ``runserver`` / ``migrate`` all surface the result.

Why a system check rather than a log line: the staging contract has two halves
that are each silent on their own. ``RLS_AS_ENFORCED`` / ``RLS_PREAUTH_ENFORCED``
are meant to arm a connection-level GUC on **every** app-role connection
(Django, Celery, scripts), but the GUC is wired into
``DATABASES['default']['OPTIONS']['options']`` by exactly one helper
(``reqogniloom.settings._build_pg_options``). A second place rebuilding the
OPTIONS — or a settings module such as ``settings_test`` that replaces
``DATABASES`` wholesale — would drop the GUC while the flag still reads True,
and the deployment would look enforced while the policy predicate stayed
permissive. That is the config drift this check fails on (AC-25).

It deliberately checks only the direction ``flag is True => GUC present``. The
DEFAULT-OFF ship must not require a GUC to be absent (an operator who explicitly
sets the OPTIONS by hand is a deliberate act, and the reverse direction is
covered by the very act of flipping the flag).
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error

#: ``manage.py check`` id for "an RLS flag is True but its GUC is missing from
#: the app-role connection OPTIONS".
RLS_GUC_MISSING = "persistence.E001"

#: flag name -> (GUC name, required libpq options clause).
_RLS_FLAG_CLAUSES: dict[str, tuple[str, str]] = {
    "RLS_AS_ENFORCED": ("app.rls_as_enforced", "-c app.rls_as_enforced=on"),
    "RLS_PREAUTH_ENFORCED": (
        "app.rls_preauth_enforced",
        "-c app.rls_preauth_enforced=on",
    ),
}


def _default_pg_options() -> str:
    """Return ``DATABASES['default']['OPTIONS']['options']`` or ``""``."""
    options = (
        settings.DATABASES.get("default", {}).get("OPTIONS", {}).get("options", "")
    )
    return options or ""


def check_rls_guc_flags_match_db_options(app_configs=None, **kwargs):
    """Fail when an RLS flag is True but its GUC is absent from the OPTIONS.

    AC-25. Both sides are read at check time (not captured at import), so
    ``override_settings`` exercises the positive branch in a unit test and an
    operator sees the failure from a plain ``manage.py check``.
    """
    options = _default_pg_options()
    errors = []
    for flag_name, (guc_name, clause) in _RLS_FLAG_CLAUSES.items():
        if not getattr(settings, flag_name, False):
            continue
        if clause not in options:
            errors.append(
                Error(
                    f"{flag_name} is True but the app-role connection OPTIONS do "
                    f"not carry '{clause}'.",
                    hint=(
                        "The flag promises enforcement of the staged RLS policy on "
                        f"'{guc_name}', but no connection sends that GUC, so the "
                        "policy predicate stays permissive. Ensure OPTIONS is built "
                        "by reqogniloom.settings._build_pg_options (the single "
                        "source of truth) and that no settings module replaces "
                        "DATABASES without it."
                    ),
                    id=RLS_GUC_MISSING,
                )
            )
    return errors
