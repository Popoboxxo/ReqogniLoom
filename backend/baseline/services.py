"""
ARCH-L1-006 BaselineService — Public service facade.

leaf_id: COMP-BL-001, COMP-BL-002, COMP-BL-003, COMP-BL-004
req_id:  REQ-L2-BL-001 through REQ-L2-BL-009

This module is the ONLY public import surface for downstream consumers
(ApplicationService, REST API, MCP server). All BaselineService operations
are accessed through these functions.

Public import paths:
    from baseline.services import build, diff, get, list_baselines
    from baseline.services import get_item_at_baseline

Interface: IF-BL-EXT-IN-001 (ApplicationService → BaselineServiceSystem)

Architecture:
  docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Architecture.md

Scope semantics (REQ-L2-BL-001):
  document — a single Artifact + all descendants + TraceLinks
  project  — all Artifacts of a Workspace
  global   — all Artifacts of the Tenant (Extended preset only)

Preset gate (REQ-L2-BL-004):
  Minimal:  no baselines
  Standard: document, project
  Extended: document, project, global
"""
from __future__ import annotations

import uuid
from typing import Optional

from baseline.delta_index_builder import get_builder
from baseline.diff_engine import get_engine
from baseline.exceptions import (  # noqa: F401  (re-exported for callers)
    BaselineError,
    BaselineImmutableError,
    BaselineNotFoundError,
    DuplicateBaselineIdError,
    DuplicateBaselineNameError,
    EmptyBaselineNameError,
    ItemNotInBaselineError,
    ScopeMismatchError,
    ScopeNotAllowedError,
    VersionNotFoundError,
)
from baseline.store import get_store
from baseline.types import (  # noqa: F401  (re-exported)
    BaselineDetail,
    BaselineMetadata,
    BaselineSummary,
    ChangedItem,
    DeltaIndexTuple,
    DiffResult,
    ItemPayload,
)
from baseline.version_reconstructor import get_reconstructor


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: build
# ---------------------------------------------------------------------------


def build(
    scope: str,
    workspace_id: uuid.UUID,
    name: str,
    tenant_id: uuid.UUID,
    description: Optional[str] = None,
    created_by: str = "",
    document_id: Optional[uuid.UUID] = None,
) -> uuid.UUID:
    """Create and persist a new immutable Baseline.

    IF-BL-EXT-IN-001 (ApplicationService → DeltaIndexBuilder → BaselineStore).

    Args:
        scope: "document" | "project" | "global"
        workspace_id: Target workspace UUID.
        name: Human-readable name; must be unique within workspace.
        tenant_id: Active tenant UUID for row-level isolation.
        description: Optional description string.
        created_by: Agent/user identifier string.
        document_id: Root artifact UUID; required when scope="document".

    Returns:
        UUID of the newly created BaselineSnapshot.

    Raises:
        ScopeNotAllowedError: Workspace preset blocks this scope.
        EmptyBaselineNameError: Name is blank.
        DuplicateBaselineNameError: Name already exists in workspace.

    REQ-L2-BL-001, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-007
    """
    return get_builder().build(
        scope=scope,
        workspace_id=workspace_id,
        name=name,
        tenant_id=tenant_id,
        description=description,
        created_by=created_by,
        document_id=document_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: diff
# ---------------------------------------------------------------------------


def diff(
    baseline_a_id: uuid.UUID,
    baseline_b_id: uuid.UUID,
) -> DiffResult:
    """Compute the structural diff between two Baselines of the same scope.

    IF-BL-EXT-IN-001 (ApplicationService → DiffEngine → BaselineStore).

    Args:
        baseline_a_id: Reference baseline (from / older).
        baseline_b_id: Target baseline (to / newer).

    Returns:
        DiffResult with:
          added:   item_ids in B but not in A
          removed: item_ids in A but not in B
          changed: items in both with different versions

    Raises:
        BaselineNotFoundError: Either baseline does not exist.
        ScopeMismatchError: Baselines have different scopes.

    REQ-L2-BL-003
    """
    return get_engine().diff(
        baseline_a_id=baseline_a_id,
        baseline_b_id=baseline_b_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: get
# ---------------------------------------------------------------------------


def get(baseline_id: uuid.UUID) -> BaselineDetail:
    """Return the full Baseline record including all delta entries.

    IF-BL-EXT-IN-001 (ApplicationService → BaselineStore).

    Args:
        baseline_id: UUID of the target baseline.

    Returns:
        BaselineDetail with all DeltaIndexTuple entries.

    Raises:
        BaselineNotFoundError: If the baseline does not exist.

    REQ-L2-BL-006
    """
    return get_store().get(baseline_id=baseline_id)


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: list
# ---------------------------------------------------------------------------


def list_baselines(
    workspace_id: uuid.UUID,
    scope: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
) -> list[BaselineSummary]:
    """Return Baseline summaries for a workspace, sorted by created_at DESC.

    IF-BL-EXT-IN-001 (ApplicationService → BaselineStore).

    Args:
        workspace_id: Workspace to query.
        scope: Optional scope filter.
        tenant_id: Optional tenant filter.

    Returns:
        List of BaselineSummary (no delta entries — lazy loading).

    REQ-L2-BL-006
    """
    return get_store().list(
        workspace_id=workspace_id,
        scope=scope,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# IF-BL-EXT-IN-001: get_item_at_baseline
# ---------------------------------------------------------------------------


def get_item_at_baseline(
    baseline_id: uuid.UUID, item_id: str
) -> ItemPayload:
    """Reconstruct the historical payload of an item at baseline time.

    IF-BL-EXT-IN-001 (ApplicationService → VersionReconstructor).

    Args:
        baseline_id: UUID of the target baseline.
        item_id: String UUID of the item (Artifact/Requirement).

    Returns:
        ItemPayload with title, description, content at the recorded version.

    Raises:
        BaselineNotFoundError: Baseline does not exist.
        ItemNotInBaselineError: item_id is not part of this baseline.
        VersionNotFoundError: Version not found in version history.

    REQ-L2-BL-009
    """
    return get_reconstructor().get_item_at_baseline(
        baseline_id=baseline_id,
        item_id=item_id,
    )


# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------

__all__ = [
    # Operations
    "build",
    "diff",
    "get",
    "list_baselines",
    "get_item_at_baseline",
    # Exceptions (re-exported for callers)
    "BaselineError",
    "BaselineImmutableError",
    "BaselineNotFoundError",
    "DuplicateBaselineIdError",
    "DuplicateBaselineNameError",
    "EmptyBaselineNameError",
    "ItemNotInBaselineError",
    "ScopeMismatchError",
    "ScopeNotAllowedError",
    "VersionNotFoundError",
    # Types (re-exported)
    "DeltaIndexTuple",
    "BaselineMetadata",
    "BaselineDetail",
    "BaselineSummary",
    "DiffResult",
    "ChangedItem",
    "ItemPayload",
]
