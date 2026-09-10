"""A former `refines` edge now carries hierarchy semantics (OFFENE FRAGE 2)."""
from __future__ import annotations

import pytest

from link_types.management.commands.diff_auditor_findings import summarize_findings
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Artifact, Requirement, Tenant, Workspace

    tenant = Tenant.objects.create(name="refines-impact")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def requirement(title):
        # Artifact has no `title` column (persistence/models.py) — title
        # lives on the typed Requirement sibling row only.
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, workspace=ws, artifact=art, title=title
        )

    yield {"tenant": tenant, "workspace": ws, "requirement": requirement}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_summarize_returns_counts_keyed_by_rule_id(env):
    env["requirement"]("lonely")
    summary = summarize_findings(env["workspace"].id)
    assert isinstance(summary, dict)
    assert all(isinstance(count, int) for count in summary.values())


@pytest.mark.django_db
def test_a_migrated_refines_edge_makes_the_target_a_non_root(env):
    """Before the merge both requirements were roots; now one is a child."""
    from persistence.models import TraceLink
    from traceability.audit.hierarchy import classify_requirements

    a, b = env["requirement"]("a"), env["requirement"]("b")
    TraceLink.objects.create(
        tenant=env["tenant"],
        source_id=a.artifact_id,
        target_id=b.artifact_id,
        link_type="derives-from",
    )

    classification = classify_requirements(env["workspace"].id)
    assert str(a.artifact_id) not in classification["roots"]
    assert str(b.artifact_id) in classification["roots"]


@pytest.mark.django_db
def test_the_command_reports_a_delta_between_two_snapshots(env, tmp_path):
    import json
    from io import StringIO

    from django.core.management import call_command

    before = tmp_path / "before.json"
    before.write_text(json.dumps({"TRACE-P1": 5, "VERIF-P8": 2}), encoding="utf-8")
    after = tmp_path / "after.json"
    after.write_text(json.dumps({"TRACE-P1": 3, "VERIF-P8": 2}), encoding="utf-8")

    out = StringIO()
    call_command(
        "diff_auditor_findings", "--before", str(before), "--after", str(after), stdout=out
    )
    output = out.getvalue()
    assert "TRACE-P1" in output
    assert "-2" in output
    assert "VERIF-P8" not in output.split("Unchanged")[0]
