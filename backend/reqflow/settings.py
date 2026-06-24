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
"""
from __future__ import annotations

import os
from pathlib import Path

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY: str = config("SECRET_KEY", default="CHANGE-ME-IN-PRODUCTION")
DEBUG: bool = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config(
    "ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv()
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
# LLM Provider — ARCH-L1-009 LlmAdapter (ADR-02 Provider Abstraction)
# Supported: mock | anthropic | openai | ollama | azure
# ---------------------------------------------------------------------------
LLM_PROVIDER: str = config("LLM_PROVIDER", default="mock")
LLM_API_KEY: str = config("LLM_API_KEY", default="")
LLM_BASE_URL: str = config("LLM_BASE_URL", default="")
LLM_MODEL: str = config("LLM_MODEL", default="")

# ---------------------------------------------------------------------------
# Celery — ARCH-L1-016 ResilienceOrchestrator (async task queue)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND: str = config(
    "CELERY_RESULT_BACKEND", default="redis://redis:6379/0"
)

# ---------------------------------------------------------------------------
# Tenant-Isolation placeholder — ADR-03
# In v1: single default tenant. v2-activation requires no data migration.
# TODO(ARCH-L1-011): Set DEFAULT_TENANT_ID via env once auth_tenancy is implemented.
# ---------------------------------------------------------------------------
DEFAULT_TENANT_ID: int = config("DEFAULT_TENANT_ID", default=1, cast=int)
