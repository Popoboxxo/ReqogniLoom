"""F1.2-T2 (#1374, PR-F3b) — ``report_unbacked_diagrams`` operator report.

After F1.2-T2 no new Diagram can be created without a workspace, but rows that
predate the change (or were written outside the service layer) may still have
``workspace_id IS NULL`` and therefore ``artifact_id IS NULL`` — they can never
be linked or baselined. This read-only command reports them per tenant so the
operator can decide what to do; it never assigns anything automatically.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from diagram.manager import DiagramManager
from diagram.models import Diagram
from diagram.tests.conftest import VALID_MERMAID_BLOCK, active_tenant

pytestmark = pytest.mark.django_db


def _make_orphan_diagram(tenant) -> Diagram:
    """A workspace-less row, written directly — the service layer refuses it."""
    return Diagram.objects.create(
        name="Legacy Orphan",
        diagram_type="block",
        description="",
        tenant=tenant,
        payload_format="mermaid",
        payload=VALID_MERMAID_BLOCK,
    )


def test_counts_unbacked_diagrams_per_tenant(tenant_a, workspace_a) -> None:
    with active_tenant(tenant_a):
        # Backed row: workspace + backing Artifact -> counted nowhere.
        DiagramManager().create_diagram(
            name="Backed Diagram",
            diagram_type="block",
            payload_format="mermaid",
            content=VALID_MERMAID_BLOCK,
            tenant=tenant_a,
            workspace_id=workspace_a.id,
        )
        # Unbacked row: no workspace and, consequently, no Artifact.
        _make_orphan_diagram(tenant_a)

        out = StringIO()
        call_command("report_unbacked_diagrams", stdout=out)

    assert (
        f"tenant={tenant_a.id} without_workspace=1 without_artifact=1"
        in out.getvalue()
    )


def test_report_writes_nothing(tenant_a, workspace_a) -> None:
    with active_tenant(tenant_a):
        _make_orphan_diagram(tenant_a)
        before = list(Diagram.objects.values_list("id", "workspace_id", "artifact_id"))

        call_command("report_unbacked_diagrams", stdout=StringIO())

        after = list(Diagram.objects.values_list("id", "workspace_id", "artifact_id"))

    assert after == before
