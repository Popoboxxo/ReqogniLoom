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
    Option (a) — single-row version model. Only the current entity state is
    stored; version 0 represents the creation baseline (no data). Historical
    snapshot reconstruction is not available for these types. The response
    includes a ``note`` field documenting this limitation when applicable.

    The diff computation logic (_compute_fields_diff) is separated from the
    data-fetching logic (_resolve_entity_snapshot) so that adding historical
    snapshot support later requires only implementing the snapshot resolver —
    the diff algorithm stays unchanged.

Amendment (issue #213):
    The version number of a single-row type is ``AuditableModel.version``, an
    optimistic-lock counter — not a revision number. Originally *every*
    non-zero version resolved to the current row, so ``diff(1, 2)`` on an
    entity sitting at version 5 answered "no changes": the current state
    compared against itself. That is a wrong answer dressed as a correct one.

    Now only the current lock version resolves to a snapshot. Other non-zero
    versions resolve to ``None``, which surfaces as the ``note`` (from-side) or
    a ``NotFoundError`` (to-side), and version lists mark each entry with
    ``content_available``. Types backed by real version tables (Diagram,
    GlossaryTerm, Icd, Goal, MainGoal, PromptTemplate) are unaffected — every
    version they list has a stored snapshot. Cross-artifact point-in-time
    history remains the job of Baselines (:mod:`baseline`), and the append-only
    operation trail that of :mod:`audit`.

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
    GlossaryTerm,
    Requirement,
    StakeholderNeed,
    TestCase,
)
from traceability.types import normalize_artifact_type

from application.models import Adr, Goal, Issue, MainGoal, Risk

from application.artifact_version_service import ArtifactVersionService
from application.base import NotFoundError, ServiceBase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field definitions per entity type
# ---------------------------------------------------------------------------

# Fields that contain Markdown / multiline text → line-level diff
# "payload" holds diagram source (Mermaid/PlantUML) — also line-diffed.
# "content" holds the aggregated MainGoal text (REQ-L2-TE-020) — same shape.
_TEXT_FIELDS = frozenset({"description", "payload", "content"})

# Fields that contain JSON-serialisable data → serialise before comparison
_JSON_FIELDS = frozenset({"steps"})

# Comparable fields per entity model
#
# Issue #767 (QA Audit Follow-up #737): ``status`` was listed here for the
# seven types below, but a workflow transition writes ``status`` via
# ``StateLifecycleManager._sync_status_mirror`` with a bare ``.update()`` that
# deliberately does NOT bump ``AuditableModel.version`` — see that method's
# docstring: "a workflow transition is not a content edit". This diff service
# resolves a version number to a *fixed* snapshot only for the single-row
# model's current lock version (ADR-AS-019 / issue #213 amendment), i.e. it
# assumes "version N" is immutable once assigned. ``status`` broke that
# assumption: two calls to diff(..., to_version=N) made at different times
# could disagree about "version N"'s content purely because a transition ran
# in between, with no version bump to signal the change.
#
# Fix: ``status`` is excluded from the version-bound diff for every type it
# would otherwise apply to, so the diffable field set here matches exactly
# the fields that are guaranteed to bump ``version`` when they change. Status
# history remains available separately via ``WorkflowHistoryEntry``
# (append-only, one row per transition) — that is the correct place to show
# "status changed from X to Y", not a content diff keyed on a lock counter
# that status changes never advance.
_ENTITY_FIELDS: Dict[str, List[str]] = {
    "Requirement": ["title", "description", "category"],
    "ArchitectureElement": ["title", "description", "element_type"],
    "TestCase": ["title", "description", "steps"],
    "StakeholderNeed": ["title", "description", "category"],
    "Adr": ["title", "description", "context", "consequences"],
    "Risk": ["title", "description", "category", "probability", "impact"],
    "Issue": ["title", "description", "severity", "category"],
    "GlossaryTerm": ["term", "definition", "synonyms", "abbreviation"],
    # REQ-142: Diagram has real per-version snapshots (DiagramVersion), unlike
    # the single-row entities above — see diff_for_diagram()/list_versions_for_diagram().
    "Diagram": ["payload_format", "payload", "canvas_json"],
    # REQ-L2-TE-020: Goal/MainGoal use an immutable-row-per-version pattern
    # (list_versions_for_goal/list_versions_for_main_goal go through
    # GoalService/MainGoalService for that). These entries only cover the
    # generic entity-diff dispatch tables (issue #219), and only resolve the
    # v0 -> current comparison: Goal.version/MainGoal.version are never
    # incremented (each edit is a new row), while the *displayed* version
    # numbers are GoalService.list_versions()'s per-lineage sequence_number
    # (1..N) — the two are not the same namespace, so diff_for_entity() still
    # raises NotFoundError for any from_version/to_version pair beyond 0/1.
    # A real Goal/MainGoal version diff needs a lineage-aware
    # diff_for_goal(lineage_id, from_seq, to_seq), not this generic path.
    # Issue #767: "status" excluded here too — same reasoning as above.
    "Goal": ["title", "description"],
    "MainGoal": ["content", "source"],
    # Datenmodell-Konsolidierung Phase 5 (Task 27): these two types record
    # content revisions into ArtifactVersion and therefore need a field list —
    # `snapshot_fields()` reads exactly this table, so a missing entry would be
    # a silently empty snapshot. They have no `_ENTITY_MODELS` entry, so the
    # generic entity-diff dispatch is unaffected by their presence here.
    #
    # Icd's fields span two rows (`name` on Icd, the contract fields on the
    # current IcdVersion), so `icd_manager` assembles that payload itself
    # rather than calling `snapshot_fields` on a single entity.
    "Icd": [
        "name",
        "direction",
        "interface_type",
        "semantic_description",
        "preconditions",
        "postconditions",
        "invariants",
    ],
    "ChangeRequest": ["title", "description", "impact_assessment"],
}

_ENTITY_MODELS = {
    "Requirement": Requirement,
    "ArchitectureElement": ArchitectureElement,
    "TestCase": TestCase,
    "StakeholderNeed": StakeholderNeed,
    "Adr": Adr,
    "Risk": Risk,
    "Issue": Issue,
    "GlossaryTerm": GlossaryTerm,
    "Goal": Goal,
    "MainGoal": MainGoal,
}


# ---------------------------------------------------------------------------
# Version-list helpers (issue #213)
#
# ``version`` on AuditableModel is an optimistic-lock counter, not a revision
# number. Version-list entries therefore state explicitly whether a retrievable
# snapshot exists behind the number, so clients stop treating "v7" as "seven
# revisions I can open".
# ---------------------------------------------------------------------------


def creation_baseline_entry() -> Dict[str, Any]:
    """Return the synthetic version-0 row (empty creation baseline)."""
    return {
        "version": 0,
        "label": "Creation baseline",
        "modified_at": None,
        # Version 0 is the empty "before creation" state: diffing *against* it
        # is supported, but there is no stored content to display.
        "content_available": False,
    }


def _entity_timestamp(entity: Any) -> Optional[str]:
    """Return the entity's last-modified timestamp as ISO-8601, if any."""
    for attr in ("updated_at", "modified_at"):
        value = getattr(entity, attr, None)
        if value is not None and hasattr(value, "isoformat"):
            return value.isoformat()
    return None


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

        # #737: TestCase tags Artifact.artifact_type with a sub-type suffix
        # (e.g. "TestCase:Unit") for filtering elsewhere (TestService.list),
        # but _ENTITY_FIELDS/_ENTITY_MODELS key on the plain type name — an
        # un-normalised lookup silently fell through to "unsupported type"
        # for every real TestCase, raising NotFoundError here.
        entity_type = normalize_artifact_type(artifact.artifact_type)
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
        Current lock version → current entity state (single-row model).
        Any other version → None (no snapshot stored — issue #213).

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

        return self._resolve_entity_snapshot_for_entity(entity, entity_type, version)

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
        """List retrievable versions for an artifact.

        Single-row model: only the creation baseline (version 0, empty) and the
        current state are retrievable. The version number is the optimistic-lock
        counter and must not be read as a revision count (issue #213) — every
        entry therefore carries ``content_available``.
        """
        self._set_tenant_context(ctx)

        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError(f"Artifact {artifact_id} not found")

        # #737: same sub-type-suffix normalisation as diff() above — without
        # it, list_versions() silently degraded to "only the creation
        # baseline exists" for every TestCase (model_class resolved to None).
        entity_type = normalize_artifact_type(artifact.artifact_type)
        model_class = _ENTITY_MODELS.get(entity_type)
        if model_class is None:
            return [creation_baseline_entry()]

        entity = (
            model_class.objects.select_related("artifact")
            .filter(artifact_id=artifact_id)
            .first()
        )

        versions = [creation_baseline_entry()]
        if entity is not None:
            versions.append(self._current_version_entry(entity))
        return versions

    # ------------------------------------------------------------------
    # Entity-based version/diff helpers (no artifact FK required)
    # REQ-L1-090, REQ-L1-091, REQ-L1-095
    # ------------------------------------------------------------------

    def list_versions_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        ctx: AuthContext,
    ) -> List[Dict[str, Any]]:
        """List retrievable versions for an entity by type and ID.

        Works for entities with a ``version`` field but no artifact FK
        (ADR, Risk, Issue, GlossaryTerm). Returns the same shape as
        ``list_versions`` for consistency, including ``content_available``.
        """
        self._set_tenant_context(ctx)

        model_class = _ENTITY_MODELS.get(entity_type)
        if model_class is None:
            return [creation_baseline_entry()]

        entity = model_class.objects.filter(id=entity_id).first()
        if entity is None:
            raise NotFoundError(f"{entity_type} {entity_id} not found")

        versions = [creation_baseline_entry()]
        if hasattr(entity, "version"):
            versions.append(self._current_version_entry(entity))
        return versions

    def _current_version_entry(self, entity: Any) -> Dict[str, Any]:
        """Build the "current state" row of a version list.

        The label deliberately omits the lock-counter value: rendering
        ``Current (v7)`` invited readers to assume seven retrievable
        revisions exist (issue #213). ``version`` is still returned because
        it is the addressing token for ``/diff/`` and for baseline pinning.
        """
        return {
            "version": self._current_lock_version(entity),
            "label": "Current",
            "modified_at": _entity_timestamp(entity),
            "content_available": True,
        }

    def diff_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        from_version: int,
        to_version: int,
        ctx: AuthContext,
    ) -> Dict[str, Any]:
        """Compute structured diff for an entity by type and ID.

        Works for entities with a ``version`` field but no artifact FK.
        Returns the same shape as ``diff`` for consistency.
        """
        self._set_tenant_context(ctx)

        if entity_type not in _ENTITY_FIELDS:
            raise NotFoundError(
                f"Diff not supported for entity type '{entity_type}'"
            )

        model_class = _ENTITY_MODELS.get(entity_type)
        if model_class is None:
            raise NotFoundError(f"Entity model for '{entity_type}' not found")

        entity = model_class.objects.filter(id=entity_id).first()
        if entity is None:
            raise NotFoundError(f"{entity_type} {entity_id} not found")

        # Resolve snapshots
        from_snapshot = self._resolve_entity_snapshot_for_entity(
            entity, entity_type, from_version
        )
        to_snapshot = self._resolve_entity_snapshot_for_entity(
            entity, entity_type, to_version
        )

        if to_snapshot is None:
            raise NotFoundError(
                f"Version {to_version} not available for {entity_type} "
                f"entity {entity_id}"
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

    def _resolve_entity_snapshot_for_entity(
        self,
        entity: Any,
        entity_type: str,
        version: int,
    ) -> Optional[Dict[str, Any]]:
        """Resolve entity field values for a given version (no artifact FK).

        Version 0 → None (creation baseline, no data).
        Current lock version → current entity state (single-row model).
        Any other version → None (no snapshot stored — issue #213).

        Historical lock-counter values deliberately do **not** fall back to the
        current row. Doing so made the API answer "these two versions are
        identical" for writes it simply never stored, which is worse than
        admitting the snapshot is unavailable.
        """
        if version == 0:
            return None

        if version != self._current_lock_version(entity):
            return None

        return self._entity_to_snapshot(entity, entity_type)

    @staticmethod
    def _current_lock_version(entity: Any) -> int:
        """Return the entity's optimistic-lock counter, defaulting to 1.

        Legacy rows created before the counter was consistently maintained can
        carry ``None``; those are treated as version 1 so that the creation
        state stays addressable.
        """
        raw = getattr(entity, "version", None)
        return raw if isinstance(raw, int) else 1

    # ------------------------------------------------------------------
    # Diagram version/diff helpers (REQ-142)
    #
    # Unlike the single-row entities above, Diagram has a real immutable
    # version table (DiagramVersion). Snapshots below are read directly
    # from historical rows instead of the "current state only" fallback,
    # and the field-level comparison reuses _compute_fields_diff — no new
    # diff algorithm is introduced.
    # ------------------------------------------------------------------

    def list_versions_for_diagram(
        self,
        diagram_id: UUID,
        ctx: AuthContext,
    ) -> List[Dict[str, Any]]:
        """List all DiagramVersions for a diagram, chronologically (REQ-142)."""
        self._set_tenant_context(ctx)

        from diagram.models import Diagram, DiagramVersion

        if not Diagram.objects.filter(id=diagram_id).exists():
            raise NotFoundError(f"Diagram {diagram_id} not found")

        versions = DiagramVersion.objects.filter(diagram_id=diagram_id).order_by(
            "version_number"
        )
        return [
            {
                "version": v.version_number,
                "label": f"v{v.version_number}",
                "modified_at": v.created_at.isoformat() if v.created_at else None,
                # Real immutable snapshot rows — content is always retrievable.
                "content_available": True,
            }
            for v in versions
        ]

    def list_versions_for_goal(self, lineage_id: UUID, ctx: AuthContext) -> List[Dict[str, Any]]:
        """List all versions of a Goal lineage, chronologically (REQ-L2-TE-020, Task 6)."""
        from application.goal_service import GoalService

        return GoalService().list_versions(lineage_id, ctx)

    def list_versions_for_main_goal(
        self, workspace_id: UUID, ctx: AuthContext
    ) -> List[Dict[str, Any]]:
        """List all MainGoal versions for a workspace, chronologically (Task 6)."""
        from application.main_goal_service import MainGoalService

        return MainGoalService().list_versions(workspace_id, ctx)

    def diff_for_diagram(
        self,
        diagram_id: UUID,
        from_version: int,
        to_version: int,
        ctx: AuthContext,
    ) -> Dict[str, Any]:
        """Compute structured diff between two DiagramVersions (REQ-142).

        Both versions must actually exist (version 0 is the empty creation
        baseline). Unlike diff()/diff_for_entity(), this does not degrade to
        a "current state only" comparison — Diagram has real history.
        """
        self._set_tenant_context(ctx)

        from diagram.models import Diagram

        if not Diagram.objects.filter(id=diagram_id).exists():
            raise NotFoundError(f"Diagram {diagram_id} not found")

        from_snapshot = self._resolve_diagram_snapshot(diagram_id, from_version)
        if from_snapshot is None and from_version != 0:
            raise NotFoundError(
                f"Version {from_version} not available for diagram {diagram_id}"
            )

        to_snapshot = self._resolve_diagram_snapshot(diagram_id, to_version)
        if to_snapshot is None:
            raise NotFoundError(
                f"Version {to_version} not available for diagram {diagram_id}"
            )

        fields = self._compute_fields_diff(from_snapshot or {}, to_snapshot, "Diagram")

        return {
            "from_version": from_version,
            "to_version": to_version,
            "entity_type": "Diagram",
            "fields": fields,
        }

    @staticmethod
    def _resolve_diagram_snapshot(
        diagram_id: UUID, version_number: int
    ) -> Optional[Dict[str, Any]]:
        """Resolve field values for a specific DiagramVersion row.

        Version 0 → None (empty creation baseline).
        """
        if version_number == 0:
            return None

        from diagram.models import DiagramVersion

        v = (
            DiagramVersion.objects.filter(
                diagram_id=diagram_id, version_number=version_number
            )
            .first()
        )
        if v is None:
            return None

        return {
            "payload_format": v.payload_format,
            "payload": v.payload,
            "canvas_json": v.canvas_json,
        }

    # ------------------------------------------------------------------
    # GlossaryTerm version/diff helpers (REQ-142)
    #
    # Datenmodell-Konsolidierung Task 28b: the dedicated GlossaryTermVersion
    # table was dropped. History now lives in the generic ArtifactVersion
    # store (Task 27 records it on every create()/update(), Task 28a copied
    # the legacy rows across) — routed through ArtifactVersionService, which
    # already returns the same version/label/modified_at/content_available
    # shape this method used to build by hand.
    # ------------------------------------------------------------------

    def list_versions_for_glossary_term(
        self,
        term_id: UUID,
        ctx: AuthContext,
    ) -> List[Dict[str, Any]]:
        """List all revisions for a glossary term, chronologically (REQ-142)."""
        self._set_tenant_context(ctx)

        term = GlossaryTerm.objects.filter(id=term_id).first()
        if term is None:
            raise NotFoundError(f"GlossaryTerm {term_id} not found")

        return ArtifactVersionService().list_revisions(term.artifact_id, ctx)

    def diff_for_glossary_term(
        self,
        term_id: UUID,
        from_version: int,
        to_version: int,
        ctx: AuthContext,
    ) -> Dict[str, Any]:
        """Compute structured diff between two glossary term revisions (REQ-142).

        Both versions must actually exist (version 0 is the empty creation
        baseline).
        """
        self._set_tenant_context(ctx)

        term = GlossaryTerm.objects.filter(id=term_id).first()
        if term is None:
            raise NotFoundError(f"GlossaryTerm {term_id} not found")

        from_snapshot = self._resolve_glossary_term_snapshot(term, from_version, ctx)
        if from_snapshot is None and from_version != 0:
            raise NotFoundError(
                f"Version {from_version} not available for glossary term {term_id}"
            )

        to_snapshot = self._resolve_glossary_term_snapshot(term, to_version, ctx)
        if to_snapshot is None:
            raise NotFoundError(
                f"Version {to_version} not available for glossary term {term_id}"
            )

        fields = self._compute_fields_diff(
            from_snapshot or {}, to_snapshot, "GlossaryTerm"
        )

        return {
            "from_version": from_version,
            "to_version": to_version,
            "entity_type": "GlossaryTerm",
            "fields": fields,
        }

    @staticmethod
    def _resolve_glossary_term_snapshot(
        term: Any, version_number: int, ctx: AuthContext
    ) -> Optional[Dict[str, Any]]:
        """Resolve field values for a specific glossary term revision.

        Version 0 → None (empty creation baseline). Task 28b: reads through
        ArtifactVersionService instead of the dropped GlossaryTermVersion
        table; the stored payload already carries ``term``/``definition``/
        ``synonyms``/``abbreviation`` (see ``migrate_legacy_versions``'s
        ``_glossary_payload`` and ``glossary_service.snapshot_fields``).
        """
        if version_number == 0:
            return None

        return ArtifactVersionService().get_payload(term.artifact_id, version_number, ctx)


__all__ = [
    "ArtifactDiffService",
]
