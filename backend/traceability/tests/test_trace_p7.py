"""
SysEng 2.0 SE-Auditor — TRACE-P7 (baseline-scope consistency) tests.

Verifies the reference rule end-to-end against a real database:
  - Positive: a trace link that straddles the document-scope boundary is
    flagged (one endpoint inside the document subtree, one outside).
  - Negative (scope differentiation): the *same* data audited at project scope
    produces no finding, because both endpoints are inside the wider scope.
  - Fully-contained links produce no finding.
  - Minimal preset produces no findings even on leaking data (structural).

Document-subtree membership is resolved via ``pl_artifact.parent_id`` (the CTE
in ``baseline.services.resolve_scope_item_ids``), so the fixtures set
``Artifact.parent`` explicitly to build the subtree.
"""
from __future__ import annotations

import pytest

from persistence.models import Artifact
from traceability.audit import AuditScope, RuleEngine
from traceability.audit.registry import TRACE_P7
from traceability.tests.conftest import active_tenant, make_trace_link

pytestmark = pytest.mark.django_db


def _artifact(tenant, workspace, parent=None) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="requirement",
        parent=parent,
    )


def _p7_findings(result):
    return [f for f in result.findings if f.rule_id == TRACE_P7]


class TestTraceP7:
    def test_document_scope_flags_cross_scope_leak(self, tenant_a, workspace_a):
        """child (in document A) -> sibling (project-only) leaks at doc scope."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child = _artifact(tenant_a, workspace_a, parent=root)
            sibling = _artifact(tenant_a, workspace_a)  # no parent → not in doc A
            make_trace_link(child, sibling, tenant_a, "satisfies")

            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        findings = _p7_findings(result)
        assert len(findings) == 1
        finding = findings[0]
        assert finding.scope == "document"
        assert finding.scope_artifact_id == str(root.id)
        assert str(child.id) in finding.artifact_ids
        assert str(sibling.id) in finding.artifact_ids

    def test_project_scope_has_no_leak_for_same_data(
        self, tenant_a, workspace_a
    ):
        """The same link is fully contained at project scope → no finding."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child = _artifact(tenant_a, workspace_a, parent=root)
            sibling = _artifact(tenant_a, workspace_a)
            make_trace_link(child, sibling, tenant_a, "satisfies")

            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("project")],
            )

        assert _p7_findings(result) == []

    def test_link_fully_inside_document_scope_is_clean(
        self, tenant_a, workspace_a
    ):
        """A link between two document-subtree members is not a leak."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child_a = _artifact(tenant_a, workspace_a, parent=root)
            child_b = _artifact(tenant_a, workspace_a, parent=root)
            make_trace_link(child_a, child_b, tenant_a, "satisfies")

            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        assert _p7_findings(result) == []

    def test_minimal_preset_yields_no_findings_on_leaking_data(
        self, tenant_a, workspace_a
    ):
        """Minimal has no SE-Auditor mandate — even a real leak is not flagged."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child = _artifact(tenant_a, workspace_a, parent=root)
            sibling = _artifact(tenant_a, workspace_a)
            make_trace_link(child, sibling, tenant_a, "satisfies")

            result = RuleEngine().run(
                tier="minimal",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        assert result.findings == []

    def test_standard_preset_does_not_run_p7(self, tenant_a, workspace_a):
        """TRACE-P7 is Extended-only; Standard must not emit it."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child = _artifact(tenant_a, workspace_a, parent=root)
            sibling = _artifact(tenant_a, workspace_a)
            make_trace_link(child, sibling, tenant_a, "satisfies")

            result = RuleEngine().run(
                tier="standard",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        assert _p7_findings(result) == []
