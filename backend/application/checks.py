"""Startup system checks for the application layer.

Currently one check, for the ADR-014 §7 import-fingerprint key (decision D2a):
the idempotency fingerprint must be a keyed HMAC, and operators are told to set
an explicit ``IMPORT_FINGERPRINT_SECRET`` in production. When that setting is
empty, :mod:`application.import_idempotency` still keys the fingerprint by
deriving a domain-separated key from ``SECRET_KEY`` — correct and always keyed,
but it couples the fingerprint to the token-signing secret: rotating
``SECRET_KEY`` then invalidates stored fingerprints (a bounded 409 window until
the TTL frees the rows). This check makes the implicit fallback visible at
``manage.py check``/``runserver``/``migrate`` time.

Registered from :meth:`application.apps.ApplicationConfig.ready`, mirroring the
``llm_adapter.checks`` pattern (#794/#1050).
"""
from __future__ import annotations

from typing import Any, List

from django.conf import settings
from django.core.checks import Warning as DjangoWarning

#: ``manage.py check`` id for "no explicit import fingerprint secret".
IMPORT_FINGERPRINT_SECRET_MISSING = "application.W001"


def check_import_fingerprint_secret(
    app_configs: Any = None, **kwargs: Any
) -> List[DjangoWarning]:
    """Warn when ``IMPORT_FINGERPRINT_SECRET`` is empty (ADR-014 §7, D2a).

    A ``Warning``, not an ``Error``: the ``SECRET_KEY``-derived fallback is
    still keyed HMAC, so the feature works. This is an operational hardening
    recommendation, and a hard failure would break local development and the
    pytest suite. Never raises — a crashing check would take ``migrate`` down.
    """
    try:
        explicit = (getattr(settings, "IMPORT_FINGERPRINT_SECRET", "") or "").strip()
    except Exception:  # noqa: BLE001 - a check must never break startup.
        return []
    if explicit:
        return []
    return [
        DjangoWarning(
            "IMPORT_FINGERPRINT_SECRET is not set; the import idempotency "
            "fingerprint derives its HMAC key from SECRET_KEY.",
            hint=(
                "The fingerprint is still a keyed HMAC, but rotating SECRET_KEY "
                "invalidates stored fingerprints (a bounded 409 window until the "
                "TTL frees the rows) and the key is shared with token signing. "
                "Set IMPORT_FINGERPRINT_SECRET to a dedicated random value in "
                "production: python -c \"import secrets; "
                "print(secrets.token_urlsafe(64))\"."
            ),
            id=IMPORT_FINGERPRINT_SECRET_MISSING,
        )
    ]


__all__ = [
    "IMPORT_FINGERPRINT_SECRET_MISSING",
    "check_import_fingerprint_secret",
]
