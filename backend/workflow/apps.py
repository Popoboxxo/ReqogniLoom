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

    def ready(self) -> None:
        """Register outdated_item_ids on the Layer-0 status-provider seam.

        SA-21: persistence/models.py (Layer 0) cannot import workflow.services
        (Layer 1) directly — see persistence.status_provider's module
        docstring. Same register-on-ready() pattern as
        audit.apps.AuditConfig.ready() (DomainEventBus subscription).
        """
        from persistence.status_provider import register_outdated_item_ids_provider
        from workflow.services import outdated_item_ids

        register_outdated_item_ids_provider(outdated_item_ids)
