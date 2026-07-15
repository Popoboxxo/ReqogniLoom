"""
Dedicated Django settings for the pytest test suite (REQ-037).

Rationale (DEEP_SYSTEM_ANALYSIS.md BE-6):
    The default `reqflow.settings` module reads runtime configuration from the
    environment (`.env`). Running pytest against it means tests inherit the
    production cache, Celery and LLM configuration — a stray `.env` value can
    silently change test behaviour.

    This module imports everything from `reqflow.settings` and overrides ONLY
    the pieces that must be deterministic and side-effect-free during testing.
    Nothing else is changed, so the production configuration stays the single
    source of truth for all non-test settings.

Usage:
    Referenced via `django_settings_module = "reqflow.settings_test"` in
    backend/pyproject.toml — pytest-django picks it up automatically.

Note on the database:
    Production uses PostgreSQL (ARCH-L1-010). The DATABASES setting is kept on
    PostgreSQL rather than switched to in-memory SQLite: the persistence layer
    relies on PostgreSQL-specific behaviour (Row-Level tenant isolation,
    ADR-03) that SQLite cannot reproduce, which would produce false test
    results. Tests run against the PostgreSQL instance from docker-compose.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Required secrets — set before importing settings (REQ-115, REQ-081).
# settings.py reads these at module load time and fails fast
# (ImproperlyConfigured) if they are absent, so they must be set before the
# import below. Test-only values — never used outside this settings module.
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-do-not-use-in-production")
os.environ.setdefault("AUTH_JWT_SECRET", "test-auth-jwt-secret-for-pytest-do-not-use-in-production")
os.environ.setdefault(
    "FIELD_ENCRYPTION_KEY", "KzOBYC05wXl_7i1FedEC0dPI8E61uRMmXwhSVd40fis="
)

from reqflow.settings import *  # noqa: F401,F403,E402 — intentional settings re-export

# ---------------------------------------------------------------------------
# Database — explicit PostgreSQL test database (docker-compose service).
# Kept fixed here so tests do not depend on ambient DB_* environment values.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "reqflow",
        "USER": "reqflow",
        "PASSWORD": "reqflow",
        "HOST": "postgres",
        "PORT": "5432",
    }
}

# ---------------------------------------------------------------------------
# Debug — enable so template/assertion errors surface with full context.
# ---------------------------------------------------------------------------
DEBUG = True

# ---------------------------------------------------------------------------
# Cache — force a local in-memory cache so tests never touch a shared Redis
# instance and never leak state between runs. LocMemCache is per-process and
# is cleared on each start.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "reqflow-test-cache",
    }
}

# ---------------------------------------------------------------------------
# Celery — run tasks synchronously and in-process. No broker/worker required,
# and task exceptions propagate into the test instead of being swallowed.
# ---------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# ---------------------------------------------------------------------------
# LLM — always use the deterministic mock provider (ADR-02). Tests must never
# reach a real external LLM endpoint regardless of the ambient environment.
# ---------------------------------------------------------------------------
LLM_PROVIDER = "mock"
LLM_API_KEY = ""
LLM_BASE_URL = ""
LLM_MODEL = ""

# ---------------------------------------------------------------------------
# Password hashing — MD5 is much faster than the default PBKDF2 hasher and is
# acceptable because no test password needs to be secure.
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
