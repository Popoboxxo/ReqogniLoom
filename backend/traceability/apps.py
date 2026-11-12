"""App configuration for ARCH-L1-007 TraceabilityEngine."""
from django.apps import AppConfig


class TraceabilityConfig(AppConfig):
    """ARCH-L1-007 TraceabilityEngine — TraceLink Graph Management.

    Responsibilities:
    - Manages TraceLinks between Requirements, ArchitectureElements, TestCases
      with link types: parent-child, derives-from, satisfies, verifies,
      implements, refines, documents (new), realizes (new).
    - Upstream/downstream queries and coverage reports.
    - Performance target: < 200 ms for 10,000 items.
    - Cross-project graph traversal with cross-project annotation (REQ-L1-030).
    - Cross-tenant links are rejected (validation via AuthAndTenancy, IF-L1-056).

    See: docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/L2_TraceabilityEngineSystem_Architecture.md
    REQ-L1: REQ-L1-003 (Traceability engine)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "traceability"
    verbose_name = "ARCH-L1-007 TraceabilityEngine"

    def ready(self) -> None:  # noqa: D401 - Django hook
        """Register the allocation preferences (ADR-028 D9).

        Q1 keys live in the owning app's ``ready()`` (see ``memory/apps.py``);
        allocation is a traceability concern, so the keys register here.
        """
        from application.allocation_settings import (
            CARDINALITY_CHOICES,
            CARDINALITY_KEY,
            CARDINALITY_SINGLE,
            CONFLICT_SEVERITY_KEY,
            SEVERITY_CHOICES,
        )
        from application.preference_registry import (
            PreferenceKey,
            get_preference_key,
            register_preference_key,
        )
        from auth_tenancy.models import PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE
        from persistence.errors import ValidationError

        from application.tier_naming import (
            NAMING_COMPONENT_KEY,
            NAMING_SUBSYSTEM_KEY,
            NAMING_SYSTEM_KEY,
            naming_defaults,
        )

        naming_specs = tuple(
            PreferenceKey(
                key=key,
                value_type="str",
                default=naming_defaults()[key],
                levels=frozenset({PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE}),
                owner="E",
            )
            for key in (NAMING_SYSTEM_KEY, NAMING_SUBSYSTEM_KEY, NAMING_COMPONENT_KEY)
        )

        specs = (
            *naming_specs,
            PreferenceKey(
                key=CARDINALITY_KEY,
                value_type="enum",
                default=CARDINALITY_SINGLE,
                levels=frozenset({PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE}),
                choices=CARDINALITY_CHOICES,
                ui_editor="select",
                owner="E",
            ),
            PreferenceKey(
                key=CONFLICT_SEVERITY_KEY,
                value_type="enum",
                default="warning",
                levels=frozenset({PREFERENCE_SCOPE_GLOBAL, PREFERENCE_SCOPE_WORKSPACE}),
                choices=SEVERITY_CHOICES,
                ui_editor="select",
                owner="E",
            ),
        )
        for spec in specs:
            try:
                get_preference_key(spec.key)
            except ValidationError:
                register_preference_key(spec)
