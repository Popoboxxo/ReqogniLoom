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
