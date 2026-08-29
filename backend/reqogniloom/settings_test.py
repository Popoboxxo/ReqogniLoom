"""
Dedicated Django settings for the pytest test suite (REQ-037).

Rationale (DEEP_SYSTEM_ANALYSIS.md BE-6):
    The default `reqogniloom.settings` module reads runtime configuration from the
    environment (`.env`). Running pytest against it means tests inherit the
    production cache, Celery and LLM configuration — a stray `.env` value can
    silently change test behaviour.

    This module imports everything from `reqogniloom.settings` and overrides ONLY
    the pieces that must be deterministic and side-effect-free during testing.
    Nothing else is changed, so the production configuration stays the single
    source of truth for all non-test settings.

Usage:
    Referenced via `django_settings_module = "reqogniloom.settings_test"` in
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

from cryptography.fernet import Fernet
from decouple import config

# ---------------------------------------------------------------------------
# Required secrets — set before importing settings (REQ-115, REQ-081).
# settings.py reads these at module load time and fails fast
# (ImproperlyConfigured) if they are absent, so they must be set before the
# import below. Test-only values — never used outside this settings module.
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-do-not-use-in-production")
os.environ.setdefault("AUTH_JWT_SECRET", "test-auth-jwt-secret-for-pytest-do-not-use-in-production")

# Issue #151: the Fernet key must NOT be a literal in the repository. A
# committed key trains the "Fernet key lives in git" pattern and — because this
# module sets it via os.environ.setdefault — a process accidentally started with
# `settings_test` against a real database would encrypt LlmSettings.api_key
# values with a publicly known key.
#
# Generated per process instead. This is safe for the suite because encrypted
# columns are only ever written and read back within the same test run; nothing
# needs to decrypt data that outlives the process.
#
# An externally provided key still wins, but an *empty* value is treated as
# absent: GitHub Actions injects "" for an undeclared secret, and
# setdefault() would happily keep that empty string, leaving Fernet to fail
# with a confusing error far from the cause.
if not os.environ.get("FIELD_ENCRYPTION_KEY"):
    os.environ["FIELD_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from reqogniloom.settings import *  # noqa: F401,F403,E402 — intentional settings re-export

# ---------------------------------------------------------------------------
# Database — explicit PostgreSQL test database (docker-compose service).
# Kept fixed here so tests do not depend on ambient DB_* environment values.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        # Defaults match the CI postgres service; DB_* env vars override so
        # the suite also runs against a local compose stack whose credentials
        # come from .env (no trivial defaults there since REQ-058).
        "NAME": config("DB_NAME", default="reqogniloom"),
        "USER": config("DB_USER", default="reqogniloom"),
        "PASSWORD": config("DB_PASSWORD", default="reqogniloom"),
        "HOST": config("DB_HOST", default="postgres"),
        "PORT": config("DB_PORT", default="5432"),
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
        "LOCATION": "reqogniloom-test-cache",
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

# SA-33 url_guard: settings.py defaults LLM_ALLOW_PRIVATE_BASE_URL to
# _IS_NON_PROD, which itself depends on the ambient DJANGO_ENV var. CI's
# backend-test job never sets DJANGO_ENV, so it silently falls back to the
# "production" default and the suite's local `http://localhost:11434` /
# `http://ollama:11434` fixtures were rejected as SSRF — passing locally
# only because .env happens to set DJANGO_ENV=development there. Pinned here
# for the same reason as LLM_SYNC_TIMEOUT_SECONDS below: test behaviour must
# not depend on whichever DJANGO_ENV the runner happens to export.
LLM_ALLOW_PRIVATE_BASE_URL = True

# REQ-084 (SYSTEMAUDIT_2026-08-27 P0): pinned, independent of the ambient
# LLM_SYNC_TIMEOUT env var. settings.py reads it via config("LLM_SYNC_TIMEOUT",
# default=25) — a root .env raising it for a real deployment (e.g. to 240s)
# silently leaked into the suite and broke
# llm_adapter/tests/test_long_running_timeout.py, which asserts the
# per-artifact cap stays at the production default (<= 30s). Hardcoded here,
# matching settings.py's own default, so the assertion no longer depends on
# whichever .env happens to be on disk.
LLM_SYNC_TIMEOUT_SECONDS = 25

# REQ-138 (SYSTEMAUDIT_2026-08-27 P0): pinned, independent of the ambient
# CSRF_TRUSTED_ORIGINS env var. settings.py reads it via
# config("CSRF_TRUSTED_ORIGINS", default=...) — a root .env listing
# deployment-specific LAN origins instead of the default dropped the
# localhost origins backend/tests/test_csrf_trusted_origins.py asserts on.
# Hardcoded here, matching settings.py's own default, so the assertion no
# longer depends on whichever .env happens to be on disk.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# ---------------------------------------------------------------------------
# Password hashing — MD5 is much faster than the default PBKDF2 hasher and is
# acceptable because no test password needs to be secure.
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# Self-init (REQ-188) — disabled under test. The pytest suite migrates the test
# database on every run, which fires ``post_migrate``; letting the self-init
# receiver provision an admin here would either fail (no SYSTEM_ADMIN_PASSWORD)
# or inject unexpected base rows into a suite that builds its own fixtures.
# ---------------------------------------------------------------------------
SELF_INIT_ON_MIGRATE = False
