"""
Django settings for ReqFlow.

Architecture: ARCH-L1-010 (PersistenceLayer) — PostgreSQL via Django ORM
Tenant-Isolation: ADR-03 — Row-Level via Custom Django Manager (placeholder, see ARCH-L1-011)
Preset/Rigor: ADR-04 — PresetConfigEngine is registered as installed app (ARCH-L1-008)

Environment variables (see .env.example for full list):
  DATABASE_URL or individual DB_* vars
  SECRET_KEY
  ALLOWED_HOSTS
  LLM_PROVIDER (mock|anthropic|openai|ollama)
  LLM_API_KEY
  DEBUG
  FIELD_ENCRYPTION_KEY (REQ-081 — Fernet key, required, no default)
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, UndefinedValueError, config
from django.core.exceptions import ImproperlyConfigured


def _get_required_secret(key: str) -> str:
    """
    Retrieve a required secret from the environment.

    If the environment variable is not set, raise ImproperlyConfigured
    with a clear error message including generation instructions.

    Args:
        key: Environment variable name (e.g., 'SECRET_KEY', 'AUTH_JWT_SECRET')

    Raises:
        ImproperlyConfigured: If the environment variable is not set.
    """
    # Use decouple so values from a local .env file keep working (not only
    # process environment variables, e.g. for manage.py outside Docker).
    value = config(key, default=None)
    if not value:
        raise ImproperlyConfigured(
            f"The {key} environment variable must be set and non-empty in production. "
            f"Generate a value with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    return value

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY: str = _get_required_secret("SECRET_KEY")

# Deployment environment gate (REQ-115 hardening). The safe default is
# "production": DEBUG can NEVER be True there, even if a misconfigured .env
# sets DEBUG=True. Only a deployment that explicitly opts into a non-production
# environment (DJANGO_ENV=development|dev|local|test) may honour DEBUG=True.
# This prevents an accidental prod DEBUG leak (verbose error pages, SQL, etc.).
DJANGO_ENV: str = config("DJANGO_ENV", default="production").strip().lower()
_NON_PROD_ENVS = {"development", "dev", "local", "test"}
_debug_requested: bool = config("DEBUG", default=False, cast=bool)
DEBUG: bool = _debug_requested and DJANGO_ENV in _NON_PROD_ENVS
# Deliberately decoupled from DEBUG: some deployments run with DEBUG=False
# (the correct production default, REQ-115) but are only reachable over plain
# HTTP (e.g. an internal/sandbox IP with no TLS-terminating reverse proxy).
# Browsers silently drop a `Secure` cookie on such a connection, so the
# httpOnly access cookie would never round-trip. This lets those deployments
# opt out of `Secure` without disabling other DEBUG-driven behavior.
AUTH_COOKIE_SECURE: bool = config("AUTH_COOKIE_SECURE", default=not DEBUG, cast=bool)
ALLOWED_HOSTS: list[str] = config(
    "ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv()
)

# ---------------------------------------------------------------------------
# APPEND_SLASH (CR-03 security fix)
# ---------------------------------------------------------------------------
# Django's default APPEND_SLASH=True makes CommonMiddleware try to redirect
# any unmatched non-slash URL to its slash-terminated counterpart. For
# unsafe methods (POST/PUT/PATCH) this is a double hazard:
#   1. With DEBUG=True, django.middleware.common.CommonMiddleware raises a
#      bare RuntimeError ("Django can't redirect to the slash URL while
#      maintaining POST data") which surfaces as an HTTP 500 rendered by
#      Django's technical debug page — a full settings/traceback disclosure
#      (CWE-489 / CWE-200), on top of DEBUG already being hard-failed in
#      production (see above).
#   2. With DEBUG=False no exception is raised, but the 301 redirect still
#      silently drops the POST body, and most HTTP clients downgrade the
#      method to GET on the redirected request — a confusing, unsafe
#      fallback rather than a clean error.
# Every route in this project (DRF's DefaultRouter, all explicit `path()`
# entries, admin, health, schema) is already defined WITH a trailing slash,
# so disabling APPEND_SLASH has no effect on correctly-formed requests: a
# non-slash URL now returns a plain, immediate 404 instead of attempting a
# lossy redirect.
APPEND_SLASH = False

# ---------------------------------------------------------------------------
# Field-level encryption key (REQ-081)
# ---------------------------------------------------------------------------
# Encrypts persistence.LlmSettings.api_key at rest (see persistence/encryption.py
# and persistence/migrations/0037_encrypt_llm_api_key.py). Fails fast at process
# start rather than lazily the first time a key is encrypted/decrypted — a
# missing key would otherwise surface as a confusing crash deep inside a
# request. There is no safe default: a key generated on the fly here would
# silently differ across processes/restarts and permanently orphan any
# ciphertext already stored under the real key.
try:
    FIELD_ENCRYPTION_KEY: str = config("FIELD_ENCRYPTION_KEY")
except UndefinedValueError as exc:
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY is not set. Generate one with:\n"
        '  python3 -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"\n'
        "and set it as the FIELD_ENCRYPTION_KEY environment variable "
        "(see .env.example)."
    ) from exc

# ---------------------------------------------------------------------------
# CORS (REQ-081)
# ---------------------------------------------------------------------------
# SECURITY: Reflecting an arbitrary Origin together with
# Access-Control-Allow-Credentials: true lets any site issue credentialed
# cross-origin requests. Restrict allowed origins to an explicit allowlist
# sourced from the environment instead of using a wildcard.
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:5173",
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# CSRF (REQ-138)
# ---------------------------------------------------------------------------
# The cookie-based session auth path enforces Django's CSRF origin check.
# Browser SPA origins (Vite dev server, production frontend) must be listed
# here or all state-changing requests (POST/PATCH/PUT/DELETE) fail with 403.
CSRF_TRUSTED_ORIGINS: list[str] = config(
    "CSRF_TRUSTED_ORIGINS",
    default=(
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000"
    ),
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Installed Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
]

# ReqFlow L2 system apps — one per ARCH-L1 subsystem.
# See backend/README.md for the ARCH-L1 → app-name mapping.
REQFLOW_APPS = [
    "persistence",         # ARCH-L1-010 PersistenceLayer
    "auth_tenancy",        # ARCH-L1-011 AuthAndTenancy (ADR-03 Tenant-Isolation hook)
    "presets",             # ARCH-L1-008 PresetConfigEngine (ADR-04 Configurable Rigor)
    "audit",               # ARCH-L1-012 AuditLog
    "llm_adapter",         # ARCH-L1-009 LlmAdapter (ADR-02 Provider Abstraction)
    "traceability",        # ARCH-L1-007 TraceabilityEngine
    "workflow",            # ARCH-L1-005 WorkflowEngine (ADR-06 Configurable Lifecycle)
    "baseline",            # ARCH-L1-006 BaselineService (ADR-07 Multi-scope Baselines)
    "application",         # ARCH-L1-004 ApplicationService (domain facade)
    "rest_api",            # ARCH-L1-002 RestApiAdapter
    "mcp_server",          # ARCH-L1-003 McpServer (ADR-01 Dual-Interface, Single Domain-Core)
    "diagram",             # ARCH-L1-013 DiagramService
    "icd",                 # ARCH-L1-014 IcdManagement
    "se_metrics",          # ARCH-L1-015 SeMetrics
    "resilience",          # ARCH-L1-016 ResilienceOrchestrator
    "admin_ops",           # AdminOps — Disaster Recovery foundation (REQ-L1-046)
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + REQFLOW_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # TODO(ARCH-L1-011): Add TenantMiddleware here once auth_tenancy is implemented.
    # The middleware must extract tenant_id from the Bearer Token / API Key
    # and inject it into the request context so PersistenceLayer.CustomManager
    # can apply Row-Level isolation automatically. See ADR-03.
]

# ---------------------------------------------------------------------------
# URL Configuration
# ---------------------------------------------------------------------------
ROOT_URLCONF = "reqflow.urls"

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# WSGI / ASGI
# ---------------------------------------------------------------------------
WSGI_APPLICATION = "reqflow.wsgi.application"
ASGI_APPLICATION = "reqflow.asgi.application"

# ---------------------------------------------------------------------------
# Database — ARCH-L1-010 PersistenceLayer
# PostgreSQL via Django ORM. Tenant-Isolation via Custom Manager (ADR-03).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="reqflow"),
        "USER": config("DB_USER", default="reqflow"),
        "PASSWORD": config("DB_PASSWORD", default="reqflow"),
        "HOST": config("DB_HOST", default="postgres"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Auth user model — use the persistence-layer User (REQ-L1-010).
# This lets Django admin, session auth and DRF SessionAuthentication work
# with the same user table that the ReqFlow API authenticates against.
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "persistence.User"

# ---------------------------------------------------------------------------
# Default primary key type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework — ARCH-L1-002 RestApiAdapter
# COMP-RA-003 AuthEnforcer: AuthTenancyAuthentication provides Bearer+API-Key auth.
# COMP-RA-003 RbacPermission: enforces RBAC matrix (REQ-L2-RA-005, REQ-L2-RA-006).
# COMP-RA-002 StandardPagination: offset-based, default 25, max 100 (REQ-L2-RA-010).
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # COMP-RA-003: Delegates token validation to auth_tenancy (IF-RA-EXT-OUT-004)
        "rest_api.auth_enforcer.BearerTokenAuthentication",
        # Fallback for admin UI and browsable API
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        # COMP-RA-003: RBAC enforcement before ApplicationService delegation
        "rest_api.auth_enforcer.RbacPermission",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # REQ-071: unify all DRF errors into {"error": {"code", "message", "details"}}
    "EXCEPTION_HANDLER": "rest_api.error_envelope.reqflow_exception_handler",
    # COMP-RA-002: Pagination — default 25, max 100 (REQ-L3-RA002-003)
    "DEFAULT_PAGINATION_CLASS": "rest_api.serializers.StandardPagination",
    "PAGE_SIZE": 25,
    # Filter/ordering backends (REQ-L2-RA-010)
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
}

# ---------------------------------------------------------------------------
# drf-spectacular — OpenAPI auto-generation (COMP-RA-005)
# REQ-L3-RA005-001: securitySchemes defines Bearer token authentication.
# REQ-L3-RA005-001: Schema endpoint served without auth (SERVE_INCLUDE_SCHEMA=False
#   means drf-spectacular does not include the schema URL in its own output;
#   the schema URL is accessible publicly via the URL conf).
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "ReqFlow API",
    "DESCRIPTION": (
        "AI-native Requirements Management Tool. "
        "Dual-interface: REST API + MCP Server (ADR-01). "
        "All endpoints require Bearer Token authentication (REQ-L2-RA-005). "
        "Schema endpoints (/api/v1/schema/, /api/v1/schema/swagger-ui/) are public."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # REQ-L3-RA005-001: Bearer token security scheme
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1/",
    # Security schemes for OpenAPI spec
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Bearer token authentication. "
                    "Use 'Authorization: Bearer <token>' header. "
                    "API keys (rf_ prefix) are also accepted via this header."
                ),
            }
        }
    },
}

# ---------------------------------------------------------------------------
# AuthAndTenancy JWT — ARCH-L1-011 (REQ-L1-010, COMP-AT-001)
# Shared HS256 secret + issuer/audience used by BOTH the issuer
# (AuthenticationService.issue_token, password login) and the validator
# (AuthenticationService.validate_bearer_token). Both ends MUST read these same
# values so issued tokens round-trip through BearerTokenAuthentication.
# No secret is hard-coded in code; this MUST be set via the AUTH_JWT_SECRET env var
# in all environments (both test and production).
# ---------------------------------------------------------------------------
AUTH_JWT_SECRET: str = _get_required_secret("AUTH_JWT_SECRET")
AUTH_JWT_ISSUER: str = config("AUTH_JWT_ISSUER", default="reqflow")
AUTH_JWT_AUDIENCE: str = config("AUTH_JWT_AUDIENCE", default="reqflow-api")
# Access-token lifetime in seconds (default 12h).
AUTH_JWT_TTL_SECONDS: int = config("AUTH_JWT_TTL_SECONDS", default=43200, cast=int)

# ---------------------------------------------------------------------------
# LLM Provider — ARCH-L1-009 LlmAdapter (ADR-02 Provider Abstraction)
# Supported: mock | anthropic | openai | ollama | azure
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = config("LLM_PROVIDER", default="mock")
LLM_API_KEY: str = config("LLM_API_KEY", default="")
LLM_BASE_URL: str = config("LLM_BASE_URL", default="")
LLM_MODEL: str = config("LLM_MODEL", default="")
# REQ-084: hard upper bound (seconds) for synchronous LLM calls executed in
# the request thread. Chosen below the typical 30s Gunicorn worker timeout so
# a slow provider can never exhaust the WSGI worker pool. Enforced centrally
# in the CapabilityRouter sync path; async Celery calls are NOT capped by this.
LLM_SYNC_TIMEOUT_SECONDS: int = config("LLM_SYNC_TIMEOUT", default=25, cast=int)

# REQ-106: per-tenant daily token budget. When set (a positive integer), the
# CapabilityRouter rejects further LLM calls for a tenant that has already
# consumed this many tokens in the last 24 hours, returning a structured
# LLM_TOKEN_LIMIT_EXCEEDED error (http_status 429). Default None = unlimited.
TENANT_TOKEN_LIMIT_PER_DAY: int | None = config(
    "TENANT_TOKEN_LIMIT_PER_DAY", default=None, cast=lambda v: int(v) if v else None
)

# ---------------------------------------------------------------------------
# Celery — ARCH-L1-016 ResilienceOrchestrator (async task queue)
# REQ-057: Support Redis authentication. If REDIS_PASSWORD is set, both URLs
# will include credentials. The password is optional for local development.
# ---------------------------------------------------------------------------
# REQ-057: Redis authentication support. REDIS_PASSWORD env var is optional;
# if set, the URLs will include :password@ before the host. In development
# (empty password), Redis operates without requirepass. Defined here because
# it is consumed by both the Celery URLs below and the cache REDIS_URL.
_REDIS_PASSWORD: str = config("REDIS_PASSWORD", default="")
_CELERY_REDIS_PASSWORD_PART = f":{_REDIS_PASSWORD}@" if _REDIS_PASSWORD else ""
CELERY_BROKER_URL: str = f"redis://{_CELERY_REDIS_PASSWORD_PART}redis:6379/0"
CELERY_RESULT_BACKEND: str = f"redis://{_CELERY_REDIS_PASSWORD_PART}redis:6379/0"

# Beat schedule — periodic outbox consumer (REQ-032, DEEP_SYSTEM_ANALYSIS.md BE-1).
# Drains the domain-event outbox every 5 seconds. poll_and_dispatch claims each
# row with SELECT FOR UPDATE (skip_locked), so overlapping runs stay idempotent.
CELERY_BEAT_SCHEDULE = {
    "dispatch-outbox-events": {
        "task": "application.dispatch_outbox_events",
        "schedule": timedelta(seconds=5),
    },
}

# Use database scheduler for Celery Beat (REQ-030)
# Requires django_celery_beat to be in INSTALLED_APPS and initialized with migrations
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Cache — Redis-backed shared cache (REQ-033, DEEP_SYSTEM_ANALYSIS.md BE-2)
#
# Without an explicit CACHES setting Django falls back to LocMemCache, which is
# per-process and never synchronised between workers. That is the root cause of
# the four in-process caches becoming inconsistent under a multi-worker
# deployment. Configuring a shared Redis backend gives every worker one cache.
#
# Uses django.core.cache.backends.redis.RedisCache (built into Django 4.0+);
# no third-party django-redis dependency is required. A dedicated Redis logical
# database (db 1) is used so cache keys never collide with the Celery
# broker/result backend (db 0).
#
# WARNING — Multi-Worker Deployment Constraint (REQ-040, BE-9):
#   A shared cache backend removes the per-process split, but it does NOT by
#   itself guarantee consistency. Until the cache-invalidation strategy
#   (REQ-038 / BE-7, signal- or TTL-based post_save/post_delete invalidation)
#   is fully implemented, a stale entry written by one worker can remain visible
#   to others. Deployments with more than one worker MUST be treated as
#   potentially inconsistent until REQ-038 is closed. Do not scale beyond a
#   single worker for correctness-critical cached reads before then.
# ---------------------------------------------------------------------------
# REQ-057: _REDIS_PASSWORD is defined above (Celery section) because the
# Celery broker URLs are constructed first during module import.
_REDIS_PASSWORD_PART = f":{_REDIS_PASSWORD}@" if _REDIS_PASSWORD else ""
REDIS_URL: str = f"redis://{_REDIS_PASSWORD_PART}redis:6379/1"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# ---------------------------------------------------------------------------
# Tenant-Isolation placeholder — ADR-03
# In v1: single default tenant. v2-activation requires no data migration.
# TODO(ARCH-L1-011): Set DEFAULT_TENANT_ID via env once auth_tenancy is implemented.
# ---------------------------------------------------------------------------
DEFAULT_TENANT_ID: int = config("DEFAULT_TENANT_ID", default=1, cast=int)

# ---------------------------------------------------------------------------
# Logging — Structured JSON logging for observability (REQ-063)
# REQ-074: SQL query logging in DEBUG mode for visibility into N+1 queries.
# REQ-063: All environments use JSON format except DEBUG (verbose for local dev).
# Emits structured logs to console for container aggregation and analysis.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if DEBUG else "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "WARNING",
            "propagate": False,
        },
        "reqflow": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Self-initialisation on first start (REQ-188)
# ---------------------------------------------------------------------------
# When True (production/dev default), the ``application`` app connects a
# ``post_migrate`` receiver that provisions the base admin, workspace and the
# default workflow/permission definitions on a fresh database — replacing the
# former dedicated ``bootstrap`` docker-compose service and the manual
# ``provision_workflow_definitions`` step. The receiver fires inside the
# single one-shot ``migrate`` container, so it runs exactly once per deploy
# with no cross-process race. Overridden to False in ``settings_test`` so the
# pytest suite (which builds its own fixtures and runs without
# SYSTEM_ADMIN_PASSWORD) is never provisioned implicitly.
SELF_INIT_ON_MIGRATE: bool = config("SELF_INIT_ON_MIGRATE", default=True, cast=bool)
