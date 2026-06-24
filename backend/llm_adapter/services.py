"""
ARCH-L1-009 LlmAdapter — Public Service Facade.

This module is the single public entry point for downstream consumers
(application, mcp_server, rest_api) of the LlmAdapterSystem.

Requirements:
- REQ-L2-LA-001 (LLM-Capability-Interface with provider abstraction)
- REQ-L2-LA-002 (graceful degradation when not configured)
- REQ-L2-LA-003 (selective capability activation)
- REQ-L2-LA-004 (standardised result format)
- REQ-L2-LA-005 (provider error handling)
- REQ-L2-LA-006 (audit logging via COMP-LA-004)
- REQ-L2-LA-008 (async dispatch via COMP-LA-005)

Architecture:
    docs/se/L1/Gesamtsystem/L2/LlmAdapterSystem/L2_LlmAdapterSystem_Architecture.md

Interface (IF-LA-EXT-IN-001):
    All three public functions accept the same keyword arguments that the
    CapabilityRouter expects. Async functions return a task_id dict; the sync
    function returns an LlmResult or an error dict on failure.

Public Import Paths (for downstream consumers):
    from llm_adapter.services import validate_artifact
    from llm_adapter.services import decompose_requirement
    from llm_adapter.services import check_consistency
    from llm_adapter.services import get_task_status

Usage examples::

    from llm_adapter.services import validate_artifact, decompose_requirement

    # Synchronous
    result = validate_artifact(artifact_id="req-123")
    if "error" in result:
        ...  # handle gracefully

    # Asynchronous (returns task_id immediately)
    response = decompose_requirement(requirement_id="req-456")
    task_id = response["task_id"]

    # Poll status
    from llm_adapter.services import get_task_status
    status = get_task_status(task_id)
    # {"task_id": "...", "status": "pending|running|done|failed", "result": ...}
"""
from __future__ import annotations

from typing import Any, Dict, Union

from llm_adapter.interface import LlmResult
from llm_adapter.router import CapabilityRouter

# Module-level router instance — shared across all callers in a process.
# For test isolation, callers may construct their own CapabilityRouter.
_router = CapabilityRouter()


# ---------------------------------------------------------------------------
# IF-LA-EXT-IN-001: Synchronous capability
# ---------------------------------------------------------------------------


def validate_artifact(artifact_id: str) -> Union[LlmResult, Dict[str, Any]]:
    """Validate a single artifact using the configured LLM provider.

    This call is synchronous and returns within a few seconds.
    On graceful degradation it returns an error dict rather than raising.

    Args:
        artifact_id: Identifier of the artifact to validate.

    Returns:
        LlmResult on success.
        {"error": {"code": "LLM_NOT_CONFIGURED", "message": ...}} when not configured.
        {"error": {"code": "LLM_PROVIDER_ERROR", "message": ...}} on provider failure.
    """
    return _router.execute_capability("validate_artifact", artifact_id=artifact_id)


# ---------------------------------------------------------------------------
# IF-LA-EXT-IN-001: Async capabilities
# ---------------------------------------------------------------------------


def decompose_requirement(requirement_id: str) -> Dict[str, Any]:
    """Decompose a requirement into sub-items via an async Celery task.

    Returns immediately with a task_id. The actual LLM call runs in the
    Celery worker. Poll the result with get_task_status(task_id).

    Args:
        requirement_id: Identifier of the requirement to decompose.

    Returns:
        {"task_id": "<uuid>"} on successful dispatch.
        {"error": {"code": "BROKER_NOT_CONFIGURED", ...}} if Celery is unavailable.
        {"error": {"code": "LLM_NOT_CONFIGURED", ...}} if capability is disabled.
    """
    return _router.execute_capability(
        "decompose_requirement", requirement_id=requirement_id
    )


def check_consistency(workspace_id: str) -> Dict[str, Any]:
    """Check consistency across all artifacts in a workspace via async Celery task.

    Returns immediately with a task_id. The actual LLM call runs in the
    Celery worker. Poll the result with get_task_status(task_id).

    Args:
        workspace_id: Identifier of the workspace to check.

    Returns:
        {"task_id": "<uuid>"} on successful dispatch.
        {"error": {"code": "BROKER_NOT_CONFIGURED", ...}} if Celery is unavailable.
        {"error": {"code": "LLM_NOT_CONFIGURED", ...}} if capability is disabled.
    """
    return _router.execute_capability(
        "check_consistency", workspace_id=workspace_id
    )


# ---------------------------------------------------------------------------
# Task status query
# ---------------------------------------------------------------------------


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Query the status of an async LLM task.

    Args:
        task_id: UUID string returned by decompose_requirement or check_consistency.

    Returns:
        {
            "task_id": "<uuid>",
            "status": "pending" | "running" | "done" | "failed" | "not_found",
            "result": {...},  # present when status == "done"
            "error": "...",   # present when status == "failed"
        }
    """
    return _router.get_task_status(task_id)


# ---------------------------------------------------------------------------
# Re-exports for downstream consumers
# ---------------------------------------------------------------------------

__all__ = [
    # Primary service functions
    "validate_artifact",
    "decompose_requirement",
    "check_consistency",
    "get_task_status",
    # Result dataclasses re-exported for type annotations
    "LlmResult",
]
