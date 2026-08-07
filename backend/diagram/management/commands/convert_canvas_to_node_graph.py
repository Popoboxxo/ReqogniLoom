"""
ARCH-L1-013 DiagramService — convert_canvas_to_node_graph management command.

GH-353 Task 7: one-shot / on-demand conversion of ``canvas_stroke`` diagrams
(free-hand Fabric.js canvases, COMP-DS-006) into the strictly-typed
``node_graph`` format (Task 1). Dry-run by default; ``--apply`` is required
to persist.

Usage::

    python manage.py convert_canvas_to_node_graph --diagram <uuid>
    python manage.py convert_canvas_to_node_graph --workspace <uuid>
    python manage.py convert_canvas_to_node_graph --workspace <uuid> --apply

Design (Task 7 brief):
  * Reads ``DiagramVersion.canvas_json`` of the CURRENT version of each
    targeted ``canvas_stroke`` diagram — never the lossy ``strokes`` array
    (see Task 2's F2 finding: ``strokes`` drops every non-freehand shape).
  * Conversion itself is a pure function
    (:func:`diagram.canvas_to_node_graph.convert_canvas_json_to_node_graph`)
    reused as-is here; this command owns only target discovery, tenant
    context and persistence.
  * Append-only: every successful conversion is written as a NEW
    ``DiagramVersion`` via :meth:`DiagramManager.update_diagram` — the same
    service-layer write path Task 1 (canonicalization) and Task 4 (the
    per-node ``artifact_ref`` -> ``DIAGRAM_REF`` TraceLink reconciler) are
    already wired into (never a hand-constructed ``DiagramVersion``). The
    source ``canvas_stroke`` version is never mutated or deleted —
    ``DiagramVersion`` is append-only by construction (diagram/models.py).
  * Refuses (does not partially convert) any diagram whose ``canvas_json``
    contains a genuine free-hand ``path`` object — reported, not converted.
  * Dry-run by default: prints a per-diagram report and writes nothing.
    ``--apply`` persists successfully-converted diagrams; a refused or
    failed diagram is reported and skipped without blocking the rest of a
    ``--workspace`` run.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

from diagram.canvas_to_node_graph import convert_canvas_json_to_node_graph
from diagram.manager import DiagramManager
from diagram.models import Diagram, PayloadFormat
from diagram.node_graph import validate_node_graph
from diagram.validator import DiagramValidationError
from persistence.tenancy import TenantContext, TenantContextNotSetError


@dataclass
class _DiagramReport:
    """Per-diagram outcome line for the dry-run / apply report."""

    diagram_id: uuid.UUID
    name: str
    convertible: bool
    reason: str = ""
    applied: bool = False


class Command(BaseCommand):
    help = (
        "Convert canvas_stroke diagrams to the node_graph format (GH-353 Task 7). "
        "Dry-run by default; pass --apply to persist as new DiagramVersion rows."
    )

    def add_arguments(self, parser) -> None:
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--diagram",
            dest="diagram_id",
            default=None,
            help="Convert a single Diagram by UUID.",
        )
        target.add_argument(
            "--workspace",
            dest="workspace_id",
            default=None,
            help="Convert every canvas_stroke Diagram in this workspace UUID.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Persist conversions as new DiagramVersion rows. Without this "
                "flag the command only prints a dry-run report and writes nothing."
            ),
        )

    def handle(self, *args, **options) -> None:
        apply_changes: bool = bool(options.get("apply"))
        diagram_id_raw: Optional[str] = options.get("diagram_id")
        workspace_id_raw: Optional[str] = options.get("workspace_id")

        # Preserve the caller's ambient tenant context (if any), mirroring
        # backfill_outdated_from_legacy_status — this command must also work
        # when invoked via call_command(...) from an already tenant-scoped
        # caller (e.g. a test).
        try:
            original_tenant_id = TenantContext.get_tenant()
        except TenantContextNotSetError:
            original_tenant_id = None

        try:
            targets = self._resolve_targets(diagram_id_raw, workspace_id_raw)
        except (ValueError, Diagram.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if original_tenant_id is not None:
                TenantContext.set_tenant(original_tenant_id)
            else:
                TenantContext.clear_tenant()

        if not targets:
            self.stdout.write("No canvas_stroke diagrams found for the given target.")
            return

        manager = DiagramManager()
        reports: list[_DiagramReport] = []

        for diagram_id, tenant_id in targets:
            TenantContext.set_tenant(tenant_id)
            try:
                reports.append(self._process_one(manager, diagram_id, apply_changes))
            finally:
                TenantContext.clear_tenant()

        if original_tenant_id is not None:
            TenantContext.set_tenant(original_tenant_id)

        self._print_report(reports, apply_changes)

    # ------------------------------------------------------------------
    # Target discovery
    # ------------------------------------------------------------------

    def _resolve_targets(
        self, diagram_id_raw: Optional[str], workspace_id_raw: Optional[str]
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Return ``[(diagram_id, tenant_id), ...]`` for canvas_stroke diagrams.

        Uses ``Diagram.unscoped`` — this is an admin/maintenance entry point
        that must be able to discover its targets across tenants before any
        ``TenantContext`` is set (mirrors
        ``backfill_outdated_from_legacy_status``'s per-tenant iteration
        pattern), unlike request-scoped code which always operates within a
        single already-active tenant.
        """
        qs = (
            Diagram.unscoped
            .select_related("current_version")
            .filter(current_version__payload_format=PayloadFormat.CANVAS_STROKE)
        )
        if diagram_id_raw is not None:
            try:
                diagram_uuid = uuid.UUID(diagram_id_raw)
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"--diagram is not a valid UUID: {diagram_id_raw!r}") from exc
            qs = qs.filter(id=diagram_uuid)
            if not qs.exists():
                raise Diagram.DoesNotExist(
                    f"No canvas_stroke Diagram found with id={diagram_uuid} "
                    "(wrong id, or its current version is not canvas_stroke)."
                )
        else:
            try:
                workspace_uuid = uuid.UUID(workspace_id_raw)
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"--workspace is not a valid UUID: {workspace_id_raw!r}") from exc
            qs = qs.filter(workspace_id=workspace_uuid)

        return [(d.id, d.tenant_id) for d in qs]

    # ------------------------------------------------------------------
    # Per-diagram conversion
    # ------------------------------------------------------------------

    def _process_one(
        self, manager: DiagramManager, diagram_id: uuid.UUID, apply_changes: bool
    ) -> _DiagramReport:
        """Convert one diagram; TenantContext is already set by the caller."""
        diagram = Diagram.objects.select_related("current_version").get(id=diagram_id)
        version = diagram.current_version

        if version is None or version.payload_format != PayloadFormat.CANVAS_STROKE:
            return _DiagramReport(
                diagram_id, diagram.name, False, "current version is not canvas_stroke"
            )

        canvas_json = version.canvas_json
        if not isinstance(canvas_json, dict) or not canvas_json.get("objects"):
            return _DiagramReport(
                diagram_id,
                diagram.name,
                False,
                "no canvas_json objects on the current version "
                "(legacy stroke-only version, nothing to convert)",
            )

        result = convert_canvas_json_to_node_graph(canvas_json)
        if not result.ok:
            return _DiagramReport(diagram_id, diagram.name, False, result.reason or "not convertible")

        # Final structural safety net: the pure converter is designed to
        # always emit a schema-valid payload, but re-validating here catches
        # any future divergence before persistence rather than after.
        validation = validate_node_graph(result.payload)
        if not validation.is_valid:
            return _DiagramReport(
                diagram_id,
                diagram.name,
                False,
                f"converted payload failed node_graph validation: {validation.error_msg}",
            )

        report = _DiagramReport(diagram_id, diagram.name, True)

        if apply_changes:
            content = json.dumps(result.payload, ensure_ascii=False)
            try:
                manager.update_diagram(
                    diagram_id=diagram_id,
                    payload_format=PayloadFormat.NODE_GRAPH,
                    content=content,
                )
                report.applied = True
            except DiagramValidationError as exc:
                report.convertible = False
                report.reason = f"write rejected: {exc}"

        return report

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_report(self, reports: list[_DiagramReport], apply_changes: bool) -> None:
        for r in reports:
            if r.convertible:
                status = "CONVERTED" if r.applied else "convertible"
            else:
                status = "SKIPPED"
            line = f"[{status}] {r.diagram_id} ({r.name})"
            if r.reason:
                line += f" - {r.reason}"
            self.stdout.write(line)

        convertible = sum(1 for r in reports if r.convertible)
        applied = sum(1 for r in reports if r.applied)
        skipped = len(reports) - convertible
        summary = (
            f"Scanned {len(reports)} canvas_stroke diagram(s): "
            f"{convertible} convertible, {skipped} skipped."
        )
        if apply_changes:
            summary += f" {applied} new node_graph DiagramVersion(s) written."
        else:
            summary += " Dry run - nothing written (pass --apply to persist)."
        self.stdout.write(self.style.SUCCESS(summary))
