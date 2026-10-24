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
        """Install the admin brute-force lockout (issue #1135) and the Q1 keys.

        Connects the ``user_login_failed`` / ``user_logged_in`` receivers and
        sets ``admin.site.login_form`` to the lockout-aware subclass. Import is
        local so no model is touched before the app registry is ready. The
        receivers themselves are scoped to the admin login path, so REST
        authentication and throttling are unaffected — see
        ``auth_tenancy.admin_login``.
        """
        from auth_tenancy.admin_login import install

        install()
        _register_q1_preference_keys()


def _register_q1_preference_keys() -> None:
    """Register the Q1 core preference keys (Plan C, T-C2-2).

    The registry is code, not a DB catalogue, so the owning app registers its
    keys here: ``ui.*`` belongs to auth_tenancy (the settings/preferences
    surface), while Plan A's ``memory.*`` keys are registered by
    ``memory/apps.py`` — this function deliberately knows nothing about them.

    Idempotent by necessity: ``ready()`` may be re-entered by test tooling that
    re-runs app initialisation, while the registry (correctly) treats a duplicate
    key as a programming error. An already-registered key is therefore left
    alone instead of being re-registered.
    """
    from application.preference_registry import (
        PreferenceKey,
        get_preference_key,
        register_preference_key,
    )
    from auth_tenancy.models import (
        PREFERENCE_SCOPE_GLOBAL,
        PREFERENCE_SCOPE_USER,
        PREFERENCE_SCOPE_WORKSPACE,
    )
    from persistence.errors import ValidationError

    all_levels = frozenset(
        {
            PREFERENCE_SCOPE_GLOBAL,
            PREFERENCE_SCOPE_WORKSPACE,
            PREFERENCE_SCOPE_USER,
        }
    )
    specs = (
        # Readable IDs in the UI (Plan C T-C2-6): a display switch that applies
        # to every list/editor, so it is settable on all three levels.
        PreferenceKey(
            key="ui.ids.show_readable",
            value_type="bool",
            default=True,
            levels=all_levels,
            mode="override",
            ui_editor="checkbox",
            owner="C2",
        ),
        # Markdown formatting toolbar (Plan C T-C2-8): "auto" = show once the
        # field has three or more lines.
        PreferenceKey(
            key="ui.markdown.toolbar",
            value_type="enum",
            default="auto",
            levels=all_levels,
            mode="override",
            choices=("auto", "on", "off"),
            ui_editor="select",
            owner="C2",
        ),
        # Collapsed sidebar groups (Plan C T-C4-4): personal layout, no
        # workspace/global default, so only the user level is allowed.
        PreferenceKey(
            key="ui.sidebar.collapsed_groups",
            value_type="str_list",
            default=[],
            levels=frozenset({PREFERENCE_SCOPE_USER}),
            mode="override",
            choices=("overview", "requirements", "architecture", "test", "admin"),
            owner="C4",
        ),
    )
    for spec in specs:
        try:
            get_preference_key(spec.key)
        except ValidationError:
            register_preference_key(spec)
