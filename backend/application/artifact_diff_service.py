"""
COMP-AS-019 ArtifactDiffService — Structured field-level diff for artifacts.

leaf_id : COMP-AS-019
req_id  : REQ-L2-AS-032 (diff calculation),
          REQ-L1-040 (visual artifact diff),
          REQ-L2-RF-014 (visual diff rendering support)

Provides structured JSON diff output comparing artifact field values between
two versions. Supports Requirement, ArchitectureElement, and TestCase entities.

Interface:
    IF-AS-EXT-IN-001: GET /artifacts/{id}/diff?from=v1&to=v2

Architecture decision (ADR-AS-019):
    Option (a) — single-row version model. The current entity state represents
    any valid version; version 0 represents the creation baseline (no data).
    Historical snapshot reconstruction is not yet available. The response
    includes a ``note`` field documenting this limitation when applicable.

    The diff computation logic (_compute_fields_diff) is separated from the
    data-fetching logic (_resolve_entity_snapshot) so that adding historical
    snapshot support later requires only implementing the snapshot resolver —
    the diff algorithm stays unchanged.

Diff library: Python stdlib ``difflib`` (no external dependency).
"""
from __future__ import annotations

import difflib
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    TestCase,
)

from application.base import NotFoundError, ServiceBase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field definitions per entity type
# ---------------------------------------------------------------------------

# Fields that contain Markdown / multiline text → line-level diff
_TEXT_FIELDS = frozenset({"description"})

# Fields that contain JSON-serialisable data → serialise before comparison
_JSON_FIELDS = frozenset({"steps"})

# Comparable fields per entity model
_ENTITY_FIELDS: Dict[str, List[str]] = {
    "Requirement": ["title", "description", "category", "status"],
    "ArchitectureElement": ["title", "description", "element_type"],
    "TestCase": ["title", "description", "steps"],
}

_ENTITY_MODELS = {
    "Requirement": Requirement,
    "ArchitectureElement": ArchitectureElement,
    "TestCase": TestCase,
}


# ---------------------------------------------------------------------------
# ArtifactDiffService
# ---------------------------------------------------------------------------


class ArtifactDiffService(ServiceBase):
    """COMP-AS-019 — Structured field-level diff for artifacts.

    Supports Requirement, ArchitectureElement, and TestCase entities.
    Uses Python stdlib ``difflib`` for line-level text comparison.
    """

    def diff(
        self,
        artifact_id: UUID,
        from_version: int,
        to_version: int,
        ctx: AuthContext,
    ) -> Dict[str, Any]:
        """Compute structured diff between two versions of an artifact.

        Args:
            artifact_id: UUID of the Artifact (not the entity PK).
            from_version: Source version (0 = creation baseline / no data).
            to_version: Target version.
            ctx: Auth context for tenant scoping.

        Returns:
            Structured diff dict with ``from_version``, ``to_version``,
            ``fields`` list, and optional ``note``.

        Raises:
            NotFoundError: If the artifact or entity does not exist.
        """
        self._set_tenant_context(ctx)

        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        entity_type = artifact.artifact_type
        if entity_type not in _ENTITY_FIELDS:
            raise NotFoundError(
                f"Diff not supported for artifact type '{entity_type}'"
            )

        # Resolve snapshots
        from_snapshot = self._resolve_entity_snapshot(
            artifact_id, entity_type, from_version
        )
        to_snapshot = self._resolve_entity_snapshot(
            artifact_id, entity_type, to_version
        )

        if to_snapshot is None:
            raise NotFoundError(
                f"Version {to_version} not available for {entity_type} "
                f"artifact {artifact_id}"
            )

        # Compute field-level diff
        fields = self._compute_fields_diff(
            from_snapshot or {},
            to_snapshot,
            entity_type,
        )

        result: Dict[str, Any] = {
            "from_version": from_version,
            "to_version": to_version,
            "entity_type": entity_type,
            "fields": fields,
        }

        # Document limitation when historical data is not available
        if from_version > 0 and from_snapshot is None:
            result["note"] = (
                f"Historical version {from_version} is not available. "
                "Only the current state is stored. "
                "Use version 0 to compare against the creation baseline."
            )

        return result

    # ------------------------------------------------------------------
    # Snapshot resolution
    # ------------------------------------------------------------------

    def _resolve_entity_snapshot(
        self,
        artifact_id: UUID,
        entity_type: str,
        version: int,
    ) -> Optional[Dict[str, Any]]:
        """Resolve entity field values for a given version.

        Version 0 → None (creation baseline, no data).
        Any valid version → current entity state (single-row model).

        Returns None when the version cannot be resolved.
        """
        if version == 0:
            return None

        model_class = _ENTITY_MODELS.get(entity_type)
        if model_class is None:
            return None

        entity = (
            model_class.objects.select_related("artifact")
            .filter(artifact_id=artifact_id)
            .first()
        )
        if entity is None:
            return None

        return self._entity_to_snapshot(entity, entity_type)

    @staticmethod
    def _entity_to_snapshot(
        entity: Any, entity_type: str
    ) -> Dict[str, Any]:
        """Extract comparable field values from an entity instance."""
        fields = _ENTITY_FIELDS.get(entity_type, [])
        snapshot: Dict[str, Any] = {}
        for field_name in fields:
            value = getattr(entity, field_name, None)
            # Serialise JSON fields to a stable string representation
            if field_name in _JSON_FIELDS and value is not None:
                value = json.dumps(value, sort_keys=True, ensure_ascii=False)
            snapshot[field_name] = value if value is not None else ""
        return snapshot

    # ------------------------------------------------------------------
    # Diff computation (pure function — no DB access)
    # ------------------------------------------------------------------

    def _compute_fields_diff(
        self,
        from_data: Dict[str, Any],
        to_data: Dict[str, Any],
        entity_type: str,
    ) -> List[Dict[str, Any]]:
        """Compare two snapshots field-by-field.

        Returns a list of field diff entries, each with:
          - ``name``: field name
          - ``status``: one of ``added``, ``removed``, ``modified``, ``unchanged``
          - ``from``: old value (absent for ``added``)
          - ``to``: new value (absent for ``removed``)
          - ``lines``: unified diff lines (only for text fields with changes)
        """
        fields = _ENTITY_FIELDS.get(entity_type, [])
        result: List[Dict[str, Any]] = []

        all_field_names = list(
            dict.fromkeys(fields + list(from_data.keys()) + list(to_data.keys()))
        )

        for field_name in all_field_names:
            has_old = field_name in from_data
            has_new = field_name in to_data

            if not has_old and has_new:
                entry: Dict[str, Any] = {
                    "name": field_name,
                    "status": "added",
                    "to": to_data[field_name],
                }
                result.append(entry)
                continue

            if has_old and not has_new:
                result.append(
                    {
                        "name": field_name,
                        "status": "removed",
                        "from": from_data[field_name],
                    }
                )
                continue

            old_val = from_data[field_name]
            new_val = to_data[field_name]

            # Normalise for comparison
            old_cmp = self._normalise(old_val)
            new_cmp = self._normalise(new_val)

            if old_cmp == new_cmp:
                result.append(
                    {
                        "name": field_name,
                        "status": "unchanged",
                        "from": old_val,
                        "to": new_val,
                    }
                )
            else:
                entry = {
                    "name": field_name,
                    "status": "modified",
                    "from": old_val,
                    "to": new_val,
                }
                # Line-level diff for text fields
                if field_name in _TEXT_FIELDS:
                    entry["lines"] = self._compute_line_diff(
                        str(old_val), str(new_val)
                    )
                result.append(entry)

        return result

    @staticmethod
    def _normalise(value: Any) -> str:
        """Normalise a value for comparison."""
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        return str(value).strip()

    @staticmethod
    def _compute_line_diff(old_text: str, new_text: str) -> List[str]:
        """Compute unified diff lines between two text blocks.

        Returns a list of diff lines with standard prefixes:
          ``-`` removed, ``+`` added, ``@@`` hunk header.
        """
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="before",
                tofile="after",
                lineterm="",
            )
        )
        return [line.rstrip("\n") for line in diff]

    # ------------------------------------------------------------------
    # Version listing helper
    # ------------------------------------------------------------------

    def list_versions(
        self,
        artifact_id: UUID,
        ctx: AuthContext,
    ) -> List[Dict[str, Any]]:
        """List available versions for an artifact.

        Currently returns only the current version (single-row model).
        Version 0 is always available as the creation baseline.
        """
        self._set_tenant_context(ctx)

        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        entity_type = artifact.artifact_type
        model_class = _ENTITY_MODELS.get(entity_type)
        if model_class is None:
            return [{"version": 0, "label": "Creation baseline"}]

        entity = (
            model_class.objects.select_related("artifact")
            .filter(artifact_id=artifact_id)
            .first()
        )

        versions = [{"version": 0, "label": "Creation baseline"}]
        if entity is not None:
            versions.append(
                {
                    "version": entity.version,
                    "label": f"Current (v{entity.version})",
                    "modified_at": entity.modified_at.isoformat()
                    if entity.modified_at
                    else None,
                }
            )
        return versions


__all__ = [
    "ArtifactDiffService",
]
