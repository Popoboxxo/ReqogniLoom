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

from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
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
# SA-41: All cookie security settings follow the same pattern — environment-
# controlled with prod-safe defaults (not DEBUG, but overridable for local/HTTP dev).
AUTH_COOKIE_SECURE: bool = config("AUTH_COOKIE_SECURE", default=not DEBUG, cast=bool)
SESSION_COOKIE_SECURE: bool = config("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE: bool = config("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)
# TLS redirect and proxy headers — only active if a reverse proxy terminates TLS
# and forwards traffic as HTTP with X-Forwarded-Proto. SECURE_SSL_REDIRECT defaults
# to False (opt-in). Set to True ONLY if a TLS-terminating reverse proxy is in front
# (nginx, Traefik, HAProxy, etc.); otherwise every request redirects to https://
# where nothing is listening and deployment breaks. See .env.example for documentation.
SECURE_SSL_REDIRECT: bool = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
# N3: SECURE_PROXY_SSL_HEADER must be gated on SECURE_SSL_REDIRECT, not DEBUG. Only
# trust X-Forwarded-Proto if a TLS-terminating proxy is explicitly configured; otherwise
# clients can forge HTTPS headers to bypass security checks.
SECURE_PROXY_SSL_HEADER: tuple[str, str] | None = (
    ("HTTP_X_FORWARDED_PROTO", "https") if SECURE_SSL_REDIRECT else None
)
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
    "context_graph",       # Workspace Context Graph — derived soft-edge layer (Issue #377)
    "memory",              # AI Long-Term Memory — Workspace + Tenant-global (Spec 2026-08-24)
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
    # SA-40: WhiteNoise serves /static/ from Django without requiring nginx config.
    # Must sit after SecurityMiddleware, before other middleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # M3: Request-ID correlation for structured logging.
    # Moved here (right after WhiteNoise) to capture Request-ID on ALL responses,
    # including early 401/403/CSRF short-circuits — the responses we most need
    # to trace. Injects a UUID per request into X-Request-ID response header and
    # thread-local context so log messages carry the ID for tracing (SA-46).
    "reqogniloom.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # #36: activates request.LANGUAGE_CODE from the Accept-Language header
    # (or the "django_language" session/cookie value) so translatable
    # strings — Django's own and the ones DRF ships (gettext_lazy on
    # serializer/field error messages) — render in the requester's
    # language. Must sit between SessionMiddleware and CommonMiddleware
    # per Django's LocaleMiddleware placement requirement.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # SEC-008 (#75): adds Content-Security-Policy (no django-csp dependency
    # needed, Django 4.2 has no built-in CSP support yet).
    "reqogniloom.security_middleware.ContentSecurityPolicyMiddleware",
    # fix #104: teardown backstop for the tenant context set during DRF
    # authentication (auth_tenancy.rest.AuthTenancyAuthentication). Without
    # this, TenantContext.tenant_id and the PG session variable
    # app.current_tenant stay active on the worker thread after the request,
    # leaking into the next unauthenticated code path on the same thread.
    "auth_tenancy.middleware.AuthTenancyMiddleware",
]

# ---------------------------------------------------------------------------
# HSTS / Content-Security-Policy (SEC-008, #75)
# ---------------------------------------------------------------------------
# HSTS only makes sense once a deployment is actually reachable over HTTPS
# (a TLS-terminating reverse proxy in front of this app). Gated the same way
# AUTH_COOKIE_SECURE is: on by default in production, overridable per env.
SECURE_HSTS_SECONDS: int = config("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=not DEBUG, cast=bool
)
SECURE_HSTS_PRELOAD: bool = config("SECURE_HSTS_PRELOAD", default=not DEBUG, cast=bool)
# Restrictive default CSP for an API-only backend (no page rendering, no
# inline scripts expected). Override via env if a frontend origin needs to
# be added later.
CSP_POLICY: str = config(
    "CSP_POLICY",
    default="default-src 'self'; frame-ancestors 'none'; base-uri 'self'",
)

# ---------------------------------------------------------------------------
# URL Configuration
# ---------------------------------------------------------------------------
ROOT_URLCONF = "reqogniloom.urls"

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
WSGI_APPLICATION = "reqogniloom.wsgi.application"
ASGI_APPLICATION = "reqogniloom.asgi.application"

# ---------------------------------------------------------------------------
# Database — ARCH-L1-010 PersistenceLayer
# PostgreSQL via Django ORM. Tenant-Isolation via Custom Manager (ADR-03).
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="reqogniloom"),
        # fix #109: default to the least-privilege app role (commit
        # 0eb36ee2), not the Postgres superuser — RLS is bypassed for
        # superusers (see .env.example), so a missing DB_USER must not
        # silently grant a superuser connection.
        "USER": config("DB_USER", default="reqogniloom_app"),
        # fix #109: no default — a misconfigured deployment must fail fast
        # rather than silently start with the password documented in
        # .env.example (like SECRET_KEY/AUTH_JWT_SECRET already do).
        "PASSWORD": _get_required_secret("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="postgres"),
        "PORT": config("DB_PORT", default="5432"),
        # SA-43: Connection pooling to avoid exhausting available connections.
        # CONN_MAX_AGE = 60 means connections idle for >60s are recycled,
        # reducing per-request overhead. (Default 0 creates a new connection
        # per request and discards it — wasteful under load.)
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        # M2: Detect and transparently refresh stale connections after PG restart
        # or network disruption (e.g., PgBouncer reconnect). Without this, requests
        # on a recycled connection that PG no longer recognizes fail with "connection lost".
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,  # seconds
            # M1: statement_timeout (milliseconds) prevents long-running queries
            # (especially index-building migrations on large prod DBs) from blocking
            # indefinitely. Made env-configurable: DB_STATEMENT_TIMEOUT_MS (default 30000).
            # Migrations set this to 0 via environment override (docker-compose.yml)
            # to allow unbounded schema work; CONN_HEALTH_CHECKS is unaffected.
            "options": f"-c statement_timeout={config('DB_STATEMENT_TIMEOUT_MS', default=30000, cast=int)}",
        },
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

# #36: restrict LocaleMiddleware's Accept-Language negotiation to the two
# languages the frontend actually offers (see frontend/src/i18n/index.ts).
# Without this, Django's default LANGUAGES list (70+ locales) could match an
# unsupported but related tag (e.g. "de-CH") to a locale we never ship
# translations for, instead of falling back to LANGUAGE_CODE.
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
]

# ---------------------------------------------------------------------------
# Static files (SA-40: WhiteNoise)
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# SA-40: WhiteNoise serves static files with compression and manifest versioning.
# CompressedManifestStaticFilesStorage compresses on collectstatic, then
# WhiteNoise serves the compressed versions directly.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

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
# API rate limiting (GitHub #269) — every rate is operator-configurable.
#
# Each value uses DRF's "<count>/<period>" syntax (second|minute|hour|day, or
# their s/m/h/d abbreviations). Setting a variable to an EMPTY string disables
# that throttle entirely — useful for a load test or an air-gapped single-user
# deployment, and the reason the values are read as plain strings rather than
# parsed here.
#
# Defaults are environment-aware: non-prod (dev/test/CI) gets very high ceilings
# because the e2e suite legitimately logs in and paginates hundreds of times per
# run, and a 429 there is a flaky test rather than a caught attack.
# ---------------------------------------------------------------------------
_IS_NON_PROD = DJANGO_ENV in _NON_PROD_ENVS


def _throttle_rate(name: str, *, prod: str, non_prod: str) -> str:
    """Read a throttle rate from the environment with an env-aware default."""
    return config(name, default=non_prod if _IS_NON_PROD else prod).strip()


# Generic ceiling for authenticated callers (#269 finding 1). 600/min ~= 10 rps
# sustained per user, far above interactive UI usage (a dashboard load is a
# couple of dozen requests) but low enough to make bulk scraping impractical.
API_RATE_LIMIT_USER: str = _throttle_rate(
    "API_RATE_LIMIT_USER", prod="600/min", non_prod="20000/min"
)
# Unauthenticated callers only reach genuinely public endpoints (schema,
# health), so they need far less headroom.
API_RATE_LIMIT_ANON: str = _throttle_rate(
    "API_RATE_LIMIT_ANON", prod="120/min", non_prod="20000/min"
)
# #72/#269: FAILED logins per (client IP, username) pair.
LOGIN_THROTTLE_RATE: str = _throttle_rate(
    "LOGIN_THROTTLE_RATE", prod="10/min", non_prod="1000/min"
)
# #269: FAILED logins per client IP across all usernames (anti credential
# spraying). Must stay clearly above LOGIN_THROTTLE_RATE, otherwise it
# reintroduces the per-IP lockout this issue is about.
LOGIN_IP_THROTTLE_RATE: str = _throttle_rate(
    "LOGIN_IP_THROTTLE_RATE", prod="60/min", non_prod="5000/min"
)
# #135: the unauthenticated refresh endpoint.
REFRESH_THROTTLE_RATE: str = _throttle_rate(
    "REFRESH_THROTTLE_RATE", prod="30/min", non_prod="1000/min"
)
# SYSTEMAUDIT-2026-08-27 finding A: the /mcp/* endpoints are plain Django views,
# so DEFAULT_THROTTLE_CLASSES above never reached them and they accepted an
# unbounded rate. Enforced by mcp_server.throttling on the same cache backend.
#
# Per API key (or, on /mcp/messages/, per SSE session). 240/min = 4 rps
# sustained for a single credential. An MCP client that drives tools
# conversationally issues a call every few seconds, and even a scripted bulk
# import stays far below this; an LLM-backed tool takes seconds per call and
# can never approach it. Deliberately below API_RATE_LIMIT_USER (600/min)
# because an MCP call is on average far more expensive than a REST read.
MCP_RATE_LIMIT_KEY: str = _throttle_rate(
    "MCP_RATE_LIMIT_KEY", prod="240/min", non_prod="20000/min"
)
# Per client IP across all credentials, including requests presenting none.
# Bounds an unauthenticated flood against the SSE handshake (each one would
# otherwise allocate a Redis binding and a streaming connection). Must stay
# clearly above MCP_RATE_LIMIT_KEY: NUM_PROXIES is unset, so behind a proxy
# that drops X-Forwarded-For every caller shares this one bucket, and a tight
# value would become a self-inflicted outage — the same per-IP lockout trap
# #269 finding 2 documents for the login endpoint.
MCP_RATE_LIMIT_IP: str = _throttle_rate(
    "MCP_RATE_LIMIT_IP", prod="1200/min", non_prod="20000/min"
)

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
    "EXCEPTION_HANDLER": "rest_api.error_envelope.reqogniloom_exception_handler",
    # COMP-RA-002: Pagination — default 25, max 100 (REQ-L3-RA002-003)
    "DEFAULT_PAGINATION_CLASS": "rest_api.serializers.StandardPagination",
    "PAGE_SIZE": 25,
    # Filter/ordering backends (REQ-L2-RA-010)
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    # #269 finding 1: a generic cap applies to EVERY endpoint, not just the two
    # auth endpoints that used to opt in. The two classes are mutually
    # exclusive per request (one keys on the auth context, the other on the IP
    # of a request that has none).
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_api.throttling.AuthContextUserRateThrottle",
        "rest_api.throttling.AuthContextAnonRateThrottle",
    ],
    # Rates come from the env-configurable settings above. ``None`` (from an
    # empty env value) makes DRF treat the scope as unlimited.
    "DEFAULT_THROTTLE_RATES": {
        "user": API_RATE_LIMIT_USER or None,
        "anon": API_RATE_LIMIT_ANON or None,
        # #72/#269: brute-force cap on the public login endpoint. Counts only
        # failed attempts, keyed per (IP, username) — see rest_api.throttling.
        "login": LOGIN_THROTTLE_RATE or None,
        "login_ip": LOGIN_IP_THROTTLE_RATE or None,
        # #135: throttle the refresh endpoint like login — it is unauthenticated
        # (validated only via the refresh cookie) and public.
        "refresh": REFRESH_THROTTLE_RATE or None,
        # SYSTEMAUDIT-2026-08-27 finding A. The scopes live here (rather than in
        # a separate MCP-only dict) so mcp_server.throttling resolves its rates
        # through the very same DynamicRateThrottle/api_settings path as the
        # REST throttles — one mechanism, one place to reconfigure, and
        # override_settings works identically in both test suites.
        "mcp_key": MCP_RATE_LIMIT_KEY or None,
        "mcp_ip": MCP_RATE_LIMIT_IP or None,
    },
}

# ---------------------------------------------------------------------------
# drf-spectacular — OpenAPI auto-generation (COMP-RA-005)
# REQ-L3-RA005-001: securitySchemes defines Bearer token authentication.
# REQ-L3-RA005-001: Schema endpoint served without auth (SERVE_INCLUDE_SCHEMA=False
#   means drf-spectacular does not include the schema URL in its own output;
#   the schema URL is accessible publicly via the URL conf).
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "ReqogniLoom API",
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
                    "API keys (reqlo_ prefix) are also accepted via this header."
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

# SA-34 (SYSTEMAUDIT-2026-08-27 §4.6 F11) — server-side pepper for API-key
# hashes. Stored ONLY here / in the environment, never in a database column:
# the whole point is that a stolen database dump is not sufficient to test
# candidate keys offline. Keys are 40 random characters, so the bare SHA-256 was
# never brute-forceable; the pepper is defence in depth, which is why it is
# optional rather than fail-fast like SECRET_KEY / AUTH_JWT_SECRET.
#
# ROLLOUT — NOT retroactive. Setting this peppers *new* keys (stored with a
# "sha256p1:" prefix). Keys already in the database stay unpeppered ("sha256:")
# and keep working, because the plaintext needed to re-hash them is by design
# not recoverable. The fleet is mixed until every key has been rotated; until
# then the old rows carry exactly the pre-fix risk.
#
# CHANGING or UNSETTING the value invalidates every peppered key — rotating the
# pepper is a forced key-rotation event for all clients, so treat it like
# rotating FIELD_ENCRYPTION_KEY, not like a config tweak.
API_KEY_PEPPER: str = config("API_KEY_PEPPER", default="")

AUTH_JWT_ISSUER: str = config("AUTH_JWT_ISSUER", default="reqogniloom")
AUTH_JWT_AUDIENCE: str = config("AUTH_JWT_AUDIENCE", default="reqogniloom-api")
# Access-token lifetime in seconds (#77: reduced from 12h to 60min — a stolen/
# leaked access token now only has a 1h window instead of 12h. Safe to ship
# because PR #247 (silent JWT refresh via POST /api/v1/auth/refresh/, retried
# transparently by the SPA on a 401) is merged — users are not force-logged-out
# hourly.
AUTH_JWT_TTL_SECONDS: int = config("AUTH_JWT_TTL_SECONDS", default=3600, cast=int)
# Refresh-token lifetime in seconds (default 30d, GitHub #135). The refresh
# token lets the SPA silently mint a new access token when the short-lived
# access cookie expires mid-session, instead of hard-logging the user out.
AUTH_JWT_REFRESH_TTL_SECONDS: int = config(
    "AUTH_JWT_REFRESH_TTL_SECONDS", default=2592000, cast=int
)

# SA-32 (SYSTEMAUDIT-2026-08-27 §4.6 F7) — refresh-token rotation now detects
# reuse: presenting an already-exchanged token revokes the whole session family.
#
# 0 = strict (default). Raise it only if the multi-tab false positive shows up
# in practice: browser cookies are shared across tabs but the SPA's single-flight
# refresh guard is per JS context, so two tabs can legitimately submit the same
# refresh token at once, and strict detection logs both out. A non-zero window
# tolerates a replay that arrives within N seconds of the real rotation — which
# also means a thief replaying inside that window is not detected.
# See AuthenticationService.rotate_refresh_token.
AUTH_REFRESH_REUSE_GRACE_SECONDS: float = config(
    "AUTH_REFRESH_REUSE_GRACE_SECONDS", default=0, cast=float
)

# ---------------------------------------------------------------------------
# LLM Provider — ARCH-L1-009 LlmAdapter (ADR-02 Provider Abstraction)
# Supported: mock | anthropic | openai | ollama | azure
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = config("LLM_PROVIDER", default="mock")
LLM_API_KEY: str = config("LLM_API_KEY", default="")
LLM_BASE_URL: str = config("LLM_BASE_URL", default="")
LLM_MODEL: str = config("LLM_MODEL", default="")

# SA-33 (SYSTEMAUDIT-2026-08-27 §4.6 F9) — SSRF guard on the admin-configurable
# ``LlmSettings.base_url``. The backend issues server-side requests to that URL,
# so an internal address there turns the LLM adapter into a proxy into the
# private network (cloud metadata at 169.254.169.254, the DB/Redis containers…).
#
# The default is environment-dependent on purpose. A self-hosted Ollama at
# ``http://ollama:11434`` is a supported, documented configuration and lives on
# a private address by definition, so denying private targets in development
# would break the local setup for no security gain (the private network there is
# the developer's own machine). In production the flag is off and an operator
# who genuinely runs an internal model endpoint must opt in explicitly — ideally
# via the narrower LLM_BASE_URL_ALLOWED_HOSTS rather than the blanket flag.
#
# Residual risk: DNS rebinding is NOT covered — see llm_adapter/url_guard.py.
LLM_ALLOW_PRIVATE_BASE_URL: bool = config(
    "LLM_ALLOW_PRIVATE_BASE_URL", default=_IS_NON_PROD, cast=bool
)
# Comma-separated hosts that may resolve to a private address regardless of the
# flag above, e.g. "ollama,llm.internal".
LLM_BASE_URL_ALLOWED_HOSTS: str = config("LLM_BASE_URL_ALLOWED_HOSTS", default="")

# REQ-084: hard upper bound (seconds) for synchronous LLM calls executed in
# the request thread. Chosen below the typical 30s Gunicorn worker timeout so
# a slow provider can never exhaust the WSGI worker pool. Enforced centrally
# in the CapabilityRouter sync path; async Celery calls are NOT capped by this.
LLM_SYNC_TIMEOUT_SECONDS: int = config("LLM_SYNC_TIMEOUT", default=25, cast=int)

# Issue #342: workspace-wide prompts (glossary derivation from a whole
# workspace, traceability.suggest_links, audit.ai_review) legitimately need
# far more than the per-artifact cap above and always ran into it, surfacing
# as an INTERNAL_ERROR / HTTP 500. They run under this longer, separate cap
# instead; the tight default stays authoritative for every other call so a
# genuinely hung single-artifact request is still cut off quickly. The set of
# purposes this applies to lives in ``llm_adapter.timeouts``.
# NOTE: an outer HTTP proxy timeout applies on top — nginx defaults to 60s
# ``proxy_read_timeout`` (frontend/nginx.conf), so deployments that route MCP
# through the frontend container must raise that too for values above 60.
LLM_LONG_RUNNING_TIMEOUT_SECONDS: int = config(
    "LLM_LONG_RUNNING_TIMEOUT", default=180, cast=int
)

# REQ-106: per-tenant daily token budget. When set (a positive integer), the
# CapabilityRouter rejects further LLM calls for a tenant that has already
# consumed this many tokens in the last 24 hours, returning a structured
# LLM_TOKEN_LIMIT_EXCEEDED error (http_status 429). Default None = unlimited.
TENANT_TOKEN_LIMIT_PER_DAY: int | None = config(
    "TENANT_TOKEN_LIMIT_PER_DAY", default=None, cast=lambda v: int(v) if v else None
)

# #606: hard cap on a user's ACTIVE (non-revoked) API keys — was a fixed
# constant (10), too low for CI/CD environments where multiple agents/QA
# runs each create their own key for isolation. Configurable per-deployment
# instead of requiring a code change; default unchanged (10).
MAX_ACTIVE_API_KEYS_PER_USER: int = config(
    "MAX_ACTIVE_API_KEYS_PER_USER", default=10, cast=int
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
# REDIS_HOST/REDIS_PORT default to the docker-compose service name so the
# existing container setup keeps working unchanged; override for CI runners
# and other environments where redis is reachable under a different host.
_REDIS_HOST: str = config("REDIS_HOST", default="redis")
_REDIS_PORT: str = config("REDIS_PORT", default="6379")
CELERY_BROKER_URL: str = f"redis://{_CELERY_REDIS_PASSWORD_PART}{_REDIS_HOST}:{_REDIS_PORT}/0"
CELERY_RESULT_BACKEND: str = f"redis://{_CELERY_REDIS_PASSWORD_PART}{_REDIS_HOST}:{_REDIS_PORT}/0"

# Beat schedule.
#
# 1. Periodic outbox consumer (REQ-032, DEEP_SYSTEM_ANALYSIS.md BE-1).
#    Drains the domain-event outbox every 5 seconds. poll_and_dispatch claims
#    each row with SELECT FOR UPDATE (skip_locked), so overlapping runs stay
#    idempotent.
# 2. Monthly audit archiving (REQ-L3-AL003-001, SA-24 / Systemaudit 2026-08-27
#    §4.1 #9). ``audit.archive_lifecycle_manager`` existed as a registered
#    shared_task and documented its own schedule in its docstring, but was never
#    wired into this dict — so the retention job never ran, no month partition
#    was ever exported to cold storage, and ``audit_entry`` grew without bound.
#    The cadence below is the one the task's own docstring specifies (00:00 on
#    the 1st of each month); it is fail-safe by construction — it exports first
#    and only drops the partition when the export reported success, and it
#    no-ops with a warning when AUDIT_COLD_STORAGE_BACKEND is unconfigured.
CELERY_BEAT_SCHEDULE = {
    "dispatch-outbox-events": {
        "task": "application.dispatch_outbox_events",
        "schedule": timedelta(seconds=5),
    },
    "audit-monthly-archive": {
        "task": "audit.archive_lifecycle_manager",
        "schedule": crontab(day_of_month="1", hour=0, minute=0),
    },
}

# Use database scheduler for Celery Beat (REQ-030)
# Requires django_celery_beat to be in INSTALLED_APPS and initialized with migrations
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Task Time Limits (P0 Fix: SYSTEMAUDIT_2026-08-27)
# ---------------------------------------------------------------------------
# Prevent hung LLM tasks from blocking the worker indefinitely. Read from
# LLM_SYNC_TIMEOUT and LLM_LONG_RUNNING_TIMEOUT env vars (same as llm_adapter/timeouts.py).
# Soft limit (SigTerm) gives graceful shutdown; hard limit (SigKill) is final backstop.
# See dispatcher.py lines 26-27 for env var documentation.
_LLM_SYNC_TIMEOUT_ENV: int = config("LLM_SYNC_TIMEOUT", default=25, cast=int)
_LLM_LONG_RUNNING_TIMEOUT_ENV: int = config("LLM_LONG_RUNNING_TIMEOUT", default=180, cast=int)

# Global per-task timeout (applies to all tasks not explicitly routed).
# Set to the longer timeout since most tasks complete quickly and the tight
# sync default (25s) would starve long-running workspace-wide LLM calls.
# Individual tasks can override via task.apply_async(time_limit=...).
CELERY_TASK_SOFT_TIME_LIMIT: int = max(_LLM_LONG_RUNNING_TIMEOUT_ENV - 20, 160)  # Soft: 160s, or configured-20
CELERY_TASK_TIME_LIMIT: int = max(_LLM_LONG_RUNNING_TIMEOUT_ENV, 180)  # Hard: 180s or configured

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
REDIS_URL: str = f"redis://{_REDIS_PASSWORD_PART}{_REDIS_HOST}:{_REDIS_PORT}/1"
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
            "()": "pythonjsonlogger.json.JsonFormatter",
            # M4: Include request_id in every log line for distributed tracing.
            # The RequestIdMiddleware sets it in thread-local context via ContextVar;
            # the logging filter below injects it into every LogRecord.
            "format": "%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {request_id} {message}",
            "style": "{",
        },
    },
    "filters": {
        "request_id": {
            "()": "reqogniloom.middleware.RequestIdFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if DEBUG else "json",
            "filters": ["request_id"],
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
        "reqogniloom": {
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
