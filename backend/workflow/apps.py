"""App configuration for ARCH-L1-005 WorkflowEngine."""
from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    """ARCH-L1-005 WorkflowEngine — Configurable Item Lifecycle.

    Responsibilities:
    - Manages WorkflowDefinitions per item-type and workspace (ADR-06).
    - Validates state transitions against allowed roles and change_reason obligation.
    - Writes every transition into WorkflowState.history.
    - Provides default workflows for 3 presets: not configurable in Minimal,
      fully configurable in Extended.
    - Approver-role checks via AuthAndTenancy (IF-L1-011 → ARCH-L1-011).

    See: docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/L2_WorkflowEngineSystem_Architecture.md
    REQ-L1: REQ-L1-009 (Item-level workflow)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "workflow"
    verbose_name = "ARCH-L1-005 WorkflowEngine"
