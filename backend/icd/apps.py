"""App configuration for ARCH-L1-014 IcdManagement."""
from django.apps import AppConfig


class IcdConfig(AppConfig):
    """ARCH-L1-014 IcdManagement — Interface Control Document Management.

    Responsibilities:
    - Manages ICDs between ArchitectureElements as versioned, immutable
      interface contracts (Design-by-Contract: preconditions, postconditions, invariants).
    - Detects incompatible changes via semantic diff analysis (Breaking-Change warnings).
    - ICD versions are baseline-capable (collected by BaselineService, IF-L1-038).
    - Links ICDs to source/target ArchitectureElements via TraceabilityEngine
      with link_type='realizes' (IF-L1-039).

    See: docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/L2_IcdManagementSystem_Architecture.md
    REQ-L1: REQ-L1-028 (ICD management)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "icd"
    verbose_name = "ARCH-L1-014 IcdManagement"

    def ready(self) -> None:
        """Register Icd on the Layer-0 domain-model registry.

        SA-21: baseline/state_capture.py (Layer 1) used to lazy-import
        ``icd.models`` directly to capture ICD state in baselines
        (IF-L1-038). Same register-on-ready() pattern as
        ``application.apps.ApplicationConfig`` and ``audit.apps.AuditConfig``
        — see persistence.domain_model_registry's module docstring.

        Task 28c-2: ``Icd`` replaces ``IcdVersion`` here — the contract now
        lives on the header, and the version table is gone.
        """
        from icd.models import Icd
        from persistence.domain_model_registry import register_models

        register_models({"Icd": Icd})
