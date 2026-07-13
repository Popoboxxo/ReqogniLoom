"""App configuration for ARCH-L1-008 PresetConfigEngine."""
from django.apps import AppConfig


class PresetsConfig(AppConfig):
    """ARCH-L1-008 PresetConfigEngine — Configurable Rigor.

    Responsibilities:
    - Manages Workspace presets: Minimal / Standard / Extended (ADR-04).
    - Manages Terminology profiles: Dev-mode / SE-mode (REQ-L1-014).
    - Runtime decisions on mandatory fields, visible tools, baseline-scope
      availability, workflow configurability, and change_reason obligation.
    - Consulted by: WorkflowEngine, BaselineService, ApplicationService,
      RestApiAdapter, ReactFrontend.

    See: docs/se/L1/Gesamtsystem/L2/PresetConfigEngineSystem/L2_PresetConfigEngineSystem_Architecture.md
    REQ-L1: REQ-L1-007 (Configurable Rigor), REQ-L1-014 (Terminology profiles)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "presets"
    verbose_name = "ARCH-L1-008 PresetConfigEngine"
