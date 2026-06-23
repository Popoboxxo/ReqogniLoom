"""App configuration for ARCH-L1-002 RestApiAdapter."""
from django.apps import AppConfig


class RestApiConfig(AppConfig):
    """ARCH-L1-002 RestApiAdapter — Django REST Framework HTTP/JSON Adapter.

    Responsibilities:
    - Exposes all domain operations as HTTP/JSON endpoints with Bearer Token auth.
    - Auto-generated OpenAPI specification via drf-spectacular (REQ-L1-006).
    - Translates HTTP requests into ApplicationService calls. No business logic here.
    - Backend error messages translated to DE/EN via i18n module.
    - Missing translation keys are build errors (lint rule).
    - Consults PresetConfigEngine at runtime for visible endpoints/fields (ARCH-L1-008).

    See: docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/L2_RestApiAdapterSystem_Architecture.md
    REQ-L1: REQ-L1-006 (REST API + OpenAPI)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "rest_api"
    verbose_name = "ARCH-L1-002 RestApiAdapter"
