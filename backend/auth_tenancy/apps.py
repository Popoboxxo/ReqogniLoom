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

    def ready(self) -> None:
        """Install the admin brute-force lockout (issue #1135).

        Connects the ``user_login_failed`` / ``user_logged_in`` receivers and
        sets ``admin.site.login_form`` to the lockout-aware subclass. Import is
        local so no model is touched before the app registry is ready. The
        receivers themselves are scoped to the admin login path, so REST
        authentication and throttling are unaffected — see
        ``auth_tenancy.admin_login``.
        """
        from auth_tenancy.admin_login import install

        install()
