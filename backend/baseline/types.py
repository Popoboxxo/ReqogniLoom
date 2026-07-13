"""
ARCH-L1-006 BaselineService — Shared dataclasses and type definitions.

leaf_id: COMP-BL-001, COMP-BL-002, COMP-BL-003, COMP-BL-004
req_id:  REQ-L2-BL-001, REQ-L2-BL-003, REQ-L2-BL-009

All dataclasses used as interface contracts between BaselineService
components are defined here to avoid circular imports (interface discipline).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# COMP-BL-001: DeltaIndex types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeltaIndexTuple:
    """A single (item_id, version, entity_type) entry in a Delta Index.

    COMP-BL-001, REQ-L2-BL-001 — the index itself carries no payload; ``state``
    is an optional full-state snapshot attached on retrieval (REQ-L2-BL-012).
    It is ``None`` for legacy entries created before the snapshot feature and
    is not populated during scope resolution (state capture happens in a
    dedicated batch pass, see ``baseline.state_capture``).
    """

    item_id: str
    version: int
    entity_type: str = "item"  # "item" | "icd" | "trace_link" | "glossary_term"
    state: Optional[dict[str, Any]] = None


@dataclass
class BaselineMetadata:
    """Metadata accompanying a Delta Index before persistence.

    COMP-BL-001 — assembled by DeltaIndexBuilder and passed to BaselineStore.
    """

    workspace_id: uuid.UUID
    scope: str
    name: str
    description: Optional[str] = None
    created_by: str = ""
    created_at: Optional[datetime] = None  # set by BaselineStore if None

    # Optional: set after persistence
    baseline_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------------
# COMP-BL-002: DiffEngine types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangedItem:
    """Represents an item present in both baselines with a version change.

    COMP-BL-002, REQ-L2-BL-003, REQ-L2-BL-012.

    ``field_changes`` holds a per-field diff of the captured state, e.g.
    ``{"title": {"old": "A", "new": "B"}}``. It is populated only when BOTH
    baselines stored a full-state snapshot for the item (REQ-L2-BL-012). When
    either side is a legacy entry with no state, it stays ``None`` and callers
    fall back to the version-number delta.
    """

    id: str
    old_version: int
    new_version: int
    field_changes: Optional[dict[str, Any]] = None


@dataclass
class DiffResult:
    """Structured result of a Baseline diff operation.

    COMP-BL-002, REQ-L2-BL-003.

    added: item_ids present in B but not A.
    removed: item_ids present in A but not B.
    changed: items present in both with differing versions.
    """

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[ChangedItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": [
                {
                    "id": c.id,
                    "old_version": c.old_version,
                    "new_version": c.new_version,
                    "field_changes": c.field_changes,
                }
                for c in self.changed
            ],
        }


# ---------------------------------------------------------------------------
# COMP-BL-003: BaselineStore retrieval types
# ---------------------------------------------------------------------------


@dataclass
class BaselineDetail:
    """Full Baseline record including all delta entries.

    Returned by BaselineStore.get(). REQ-L2-BL-006.
    """

    baseline_id: uuid.UUID
    workspace_id: uuid.UUID
    scope: str
    name: str
    description: str
    created_at: datetime
    created_by: str
    entries: list[DeltaIndexTuple] = field(default_factory=list)


@dataclass
class BaselineSummary:
    """Baseline header without delta entries — returned by BaselineStore.list().

    REQ-L2-BL-006 (ADR-L3-BL003-03: Lazy Delta-Loading).
    """

    baseline_id: uuid.UUID
    workspace_id: uuid.UUID
    scope: str
    name: str
    description: str
    created_at: datetime
    created_by: str


# ---------------------------------------------------------------------------
# COMP-BL-005: ScopePreview types
# ---------------------------------------------------------------------------


@dataclass
class ScopePreviewItem:
    """A single item in the read-only scope preview.

    COMP-BL-005, REQ-L1-049. Used by ``preview_scope_items`` to communicate
    which items WOULD be included in a Baseline with a given scope, without
    actually creating the Baseline.
    """

    id: str
    title: str
    type: str  # "artifact" | "requirement" | "architecture_element" | "trace_link"
    entity_type: str = "item"


@dataclass
class ScopePreview:
    """Result of :func:`baseline.services.preview_scope_items`.

    COMP-BL-005, REQ-L1-049.

    Attributes:
        scope: The scope that was previewed (echoed back for the client).
        count: Total number of items that would be included.
        sample: Up to 10 sample items, each with id+title+type.
    """

    scope: str
    count: int
    sample: list[ScopePreviewItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {
            "scope": self.scope,
            "count": self.count,
            "sample": [
                {
                    "id": item.id,
                    "title": item.title,
                    "type": item.type,
                    "entity_type": item.entity_type,
                }
                for item in self.sample
            ],
        }


# ---------------------------------------------------------------------------
# COMP-BL-004: VersionReconstructor types
# ---------------------------------------------------------------------------


@dataclass
class ItemPayload:
    """Reconstructed historical payload for a versioned item.

    COMP-BL-004, REQ-L2-BL-009.
    """

    item_id: str
    version: int
    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    reconstructed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Return JSON-serializable representation."""
        return {
            "item_id": self.item_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "content": self.content,
        }


# ---------------------------------------------------------------------------
# Public type surface
# ---------------------------------------------------------------------------

__all__ = [
    "DeltaIndexTuple",
    "BaselineMetadata",
    "ChangedItem",
    "DiffResult",
    "BaselineDetail",
    "BaselineSummary",
    "ItemPayload",
    "ScopePreview",
    "ScopePreviewItem",
]
