"""App configuration for the LinkTypeCatalog (Layer 1)."""

from django.apps import AppConfig


class LinkTypesConfig(AppConfig):
    """Tenant-configurable trace-link type catalog.

    Layer 1, alongside ``workflow``: owns the global and per-workspace
    link-type definitions that ``application.trace_link_service`` validates
    every TraceLink against. Replaces the hardcoded ``traceability.types``
    ``SE_LINK_SEMANTICS`` matrix and its ``se_mode`` gate.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "link_types"
    verbose_name = "LinkTypeCatalog"
