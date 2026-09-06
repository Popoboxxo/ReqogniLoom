"""
COMP-AS-008 PDF Report Generator — Workspace-level PDF report rendering.

leaf_id: COMP-AS-008 (PDF rendering sub-component)
req_id: REQ-L2-AS-016, REQ-L1-023, REQ-L0-015

Responsibilities:
- Render a Workspace report (Requirements + Architecture + TraceLinks +
  TestCases) as a PDF document.
- Support two layouts:
  * ``requirement_document`` — requirements grouped by category.
  * ``traceability_matrix`` — requirements x tests matrix with coverage marks.
- Uses reportlab (pure-Python, no system deps) for PDF generation.

Interface contracts consumed:
- IF-TE-EXT-OUT-001: Django ORM (Requirement, ArchitectureElement, TestCase,
  TraceLink, Workspace)
- IF-AS-EXT-OUT-004: PresetPolicyService (terminology profile)

Interface contracts exposed:
- generate_pdf_report(workspace_id, layout, ctx) -> bytes

Architecture:
  docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/
    COMP-AS-008_ExportService/
"""
from __future__ import annotations

import io
import logging
import uuid
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

# Valid layout choices
VALID_LAYOUTS = frozenset({"requirement_document", "traceability_matrix"})


def generate_pdf_report(
    workspace_id: uuid.UUID,
    layout: str = "requirement_document",
    ctx: Any = None,
) -> bytes:
    """Generate a PDF report for a workspace.

    REQ-L2-AS-016:
    - ``requirement_document``: Requirements grouped by category.
    - ``traceability_matrix``: Requirements x TestCases coverage matrix.

    Args:
        workspace_id: Workspace to generate the report for.
        layout: One of ``"requirement_document"`` or ``"traceability_matrix"``.
        ctx: Optional AuthContext for tenant scoping.

    Returns:
        PDF content as bytes (starts with ``%PDF-``).

    Raises:
        ValueError: If layout is not a recognised value.
    """
    if layout not in VALID_LAYOUTS:
        raise ValueError(
            f"Unknown layout '{layout}'. Valid layouts: {sorted(VALID_LAYOUTS)}"
        )

    data = _fetch_workspace_data(workspace_id, ctx)

    if layout == "requirement_document":
        return _build_requirement_document(data)
    else:
        return _build_traceability_matrix(data)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def _fetch_workspace_data(
    workspace_id: uuid.UUID, ctx: Any
) -> dict[str, Any]:
    """Load all workspace data needed for report generation.

    Returns a dict with keys:
        workspace_name, requirements, architecture_elements,
        tracelinks, testcases, terminology_profile
    """
    from persistence.models import (
        ArchitectureElement,
        Requirement,
        TestCase,
        TraceLink,
        Workspace,
    )

    ws = Workspace.objects.filter(id=workspace_id).first()
    workspace_name = ws.name if ws else f"Workspace {workspace_id}"

    # Terminology profile (best-effort)
    terminology_profile = "default"
    try:
        from presets.services import get_preset

        preset = get_preset(str(workspace_id))
        terminology_profile = str(
            getattr(preset, "terminology_profile", "default")
        )
    except Exception:
        pass

    requirements = list(
        Requirement.objects.filter(
            artifact__workspace_id=workspace_id
        )
        .select_related("artifact")
        .order_by("category", "title")
    )

    # Datenmodell-Konsolidierung Phase 1: ``status`` is no longer written by
    # the workflow engine, so the PDF (a generated deliverable artifact) must
    # resolve it through workflow.state_reader (batched) instead of the (now
    # write-once, frozen-at-creation) column, or every requirement would
    # render as permanently "draft" in the document.
    from workflow import state_reader

    req_status_map = state_reader.current_states(
        "Requirement", (r.id for r in requirements)
    )

    architecture_elements = list(
        ArchitectureElement.objects.filter(
            artifact__workspace_id=workspace_id
        )
        .select_related("artifact")
        .order_by("title")
    )

    testcases = list(
        TestCase.objects.filter(
            artifact__workspace_id=workspace_id
        )
        .select_related("artifact")
        .order_by("title")
    )

    # TraceLinks where source is a requirement artifact in this workspace
    req_artifact_ids = [str(r.artifact_id) for r in requirements]
    tc_artifact_ids = [str(tc.artifact_id) for tc in testcases]

    tracelinks = []
    if req_artifact_ids:
        tracelinks = list(
            TraceLink.objects.filter(
                source_id__in=req_artifact_ids,
            ).order_by("link_type")
        )

    # Build a lookup: req_artifact_id -> list of (tc_artifact_id, link_type)
    req_to_tests: dict[str, list[dict[str, str]]] = {
        str(r.artifact_id): [] for r in requirements
    }
    for tl in tracelinks:
        src = str(tl.source_id)
        tgt = str(tl.target_id)
        if src in req_to_tests:
            req_to_tests[src].append(
                {"test_artifact_id": tgt, "link_type": tl.link_type}
            )

    return {
        "workspace_name": workspace_name,
        "workspace_id": str(workspace_id),
        "terminology_profile": terminology_profile,
        "requirements": requirements,
        "req_status_map": req_status_map,
        "architecture_elements": architecture_elements,
        "testcases": testcases,
        "tracelinks": tracelinks,
        "req_to_tests": req_to_tests,
    }


# ---------------------------------------------------------------------------
# Layout: Requirement Document
# ---------------------------------------------------------------------------


def _build_requirement_document(data: dict[str, Any]) -> bytes:
    """Render requirements grouped by category as a PDF document.

    REQ-L2-AS-016 AC-1: requirement_document layout.
    """
    from workflow import state_reader

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Requirement Document — {data['workspace_name']}",
        author="ReqogniLoom",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = ParagraphStyle(
        "ReqBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )
    meta_style = ParagraphStyle(
        "ReqMeta",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
    )

    story: list = []

    # Title page
    story.append(Paragraph(data["workspace_name"], title_style))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Requirement Document", styles["Heading1"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"Workspace: {data['workspace_id']}  |  "
            f"Terminology: {data['terminology_profile']}  |  "
            f"Requirements: {len(data['requirements'])}",
            meta_style,
        )
    )
    story.append(Spacer(1, 10 * mm))

    # Group requirements by category
    requirements = data["requirements"]
    req_status_map = data["req_status_map"]
    categories: dict[str, list] = {}
    for req in requirements:
        cat = req.category or "(uncategorized)"
        categories.setdefault(cat, []).append(req)

    for cat_name in sorted(categories.keys()):
        story.append(Paragraph(f"Category: {cat_name}", heading_style))
        story.append(Spacer(1, 3 * mm))

        for req in categories[cat_name]:
            story.append(
                Paragraph(
                    f"<b>{_escape_xml(req.title)}</b> "
                    f"<font color='grey'>[{_short_id(req.id)}]</font>",
                    body_style,
                )
            )
            if req.description:
                story.append(
                    Paragraph(_escape_xml(req.description), body_style)
                )
            # Task 12: the ``status`` column is dropped -- a requirement with
            # no WorkflowItemState falls back to the "draft" preset initial
            # state instead (documented, reviewed data-loss tradeoff, see
            # Task 12 report Finding 2).
            resolved_status = req_status_map.get(
                str(req.id)
            ) or state_reader.initial_state("Requirement")
            story.append(
                Paragraph(
                    f"Status: {resolved_status}  |  Version: {req.version}",
                    meta_style,
                )
            )
            story.append(Spacer(1, 3 * mm))

    # Architecture elements section
    arch_elements = data["architecture_elements"]
    if arch_elements:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Architecture Elements", styles["Heading1"]))
        story.append(Spacer(1, 3 * mm))
        for elem in arch_elements:
            story.append(
                Paragraph(
                    f"<b>{_escape_xml(elem.title)}</b> "
                    f"<font color='grey'>({elem.element_type}) "
                    f"[{_short_id(elem.id)}]</font>",
                    body_style,
                )
            )
            if elem.description:
                story.append(
                    Paragraph(_escape_xml(elem.description), body_style)
                )
            story.append(Spacer(1, 2 * mm))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Layout: Traceability Matrix
# ---------------------------------------------------------------------------


def _build_traceability_matrix(data: dict[str, Any]) -> bytes:
    """Render a requirements x tests traceability matrix as PDF.

    REQ-L2-AS-016 AC-2: traceability_matrix layout.
    """
    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Traceability Matrix — {data['workspace_name']}",
        author="ReqogniLoom",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    meta_style = ParagraphStyle(
        "MatrixMeta",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
    )
    cell_style = ParagraphStyle(
        "MatrixCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    )

    story: list = []

    # Title
    story.append(Paragraph(data["workspace_name"], title_style))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Traceability Matrix", styles["Heading1"]))
    story.append(Spacer(1, 3 * mm))

    requirements = data["requirements"]
    testcases = data["testcases"]
    req_to_tests = data["req_to_tests"]

    story.append(
        Paragraph(
            f"Requirements: {len(requirements)}  |  "
            f"Test Cases: {len(testcases)}  |  "
            f"Trace Links: {len(data['tracelinks'])}",
            meta_style,
        )
    )
    story.append(Spacer(1, 6 * mm))

    if not requirements:
        story.append(Paragraph("No requirements in this workspace.", cell_style))
        doc.build(story)
        return buf.getvalue()

    # Build the matrix table
    # Header row: ["Requirement"] + [tc_title for each testcase]
    header = [
        Paragraph("<b>Requirement</b>", cell_style),
    ]
    for tc in testcases:
        header.append(
            Paragraph(f"<b>{_escape_xml(tc.title)}</b>", cell_style)
        )

    # Data rows
    table_data = [header]
    tc_artifact_id_map = {str(tc.artifact_id): tc for tc in testcases}

    for req in requirements:
        row = [
            Paragraph(
                f"{_escape_xml(req.title)} [{_short_id(req.id)}]",
                cell_style,
            )
        ]
        # Check which test cases are linked to this requirement
        linked_tc_ids = set()
        for link_info in req_to_tests.get(str(req.artifact_id), []):
            linked_tc_ids.add(link_info["test_artifact_id"])

        for tc in testcases:
            tc_art_id = str(tc.artifact_id)
            if tc_art_id in linked_tc_ids:
                row.append(Paragraph("&#10003;", cell_style))  # checkmark
            else:
                row.append(Paragraph("", cell_style))
        table_data.append(row)

    # Calculate column widths
    n_cols = 1 + len(testcases)
    available_width = page_size[0] - 30 * mm  # page width minus margins
    req_col_width = 50 * mm
    tc_col_width = max(
        (available_width - req_col_width) / max(len(testcases), 1),
        12 + 4,  # minimum: leftPadding + rightPadding + 4pt for content
    )
    col_widths = [req_col_width] + [tc_col_width] * len(testcases)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5568")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ]
        )
    )

    story.append(table)
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_id(uid: uuid.UUID) -> str:
    """Return first 8 chars of a UUID for compact display."""
    return str(uid)[:8]


def _escape_xml(text: str) -> str:
    """Escape XML special characters for reportlab Paragraph markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


__all__ = ["generate_pdf_report", "VALID_LAYOUTS"]
