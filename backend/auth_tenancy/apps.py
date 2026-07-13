"""App configuration for ARCH-L1-011 AuthAndTenancy."""
from django.apps import AppConfig


class AuthTenancyConfig(AppConfig):
    """ARCH-L1-011 AuthAndTenancy — Token-based Auth and Tenant-Context Propagation.

    Responsibilities:
    - Bearer Token / API Key authentication (REQ-L1-010).
    - Four RBAC roles: Admin, Editor, Viewer, Approver (Approver active in Extended only).
    - Extracts active tenant from token and propagates to request context.
    - Injects tenant_id into PersistenceLayer.CustomManager query scope (ADR-03).

    See: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/L2_AuthAndTenancySystem_Architecture.md
    REQ-L1: REQ-L1-010 (RBAC), REQ-L1-015 (Tenant extraction)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "auth_tenancy"
    verbose_name = "ARCH-L1-011 AuthAndTenancy"
