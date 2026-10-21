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

import re
import uuid

import pytest

from persistence.models import Artifact, TraceLink
from traceability.audit import AuditScope, RuleEngine
from traceability.audit.registry import TRACE_P7
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link

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
            make_trace_link(child, sibling, tenant_a, "allocated-to")

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
            make_trace_link(child, sibling, tenant_a, "allocated-to")

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
            make_trace_link(child_a, child_b, tenant_a, "allocated-to")

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
            make_trace_link(child, sibling, tenant_a, "allocated-to")

            result = RuleEngine().run(
                tier="minimal",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        assert result.findings == []

    def test_diagram_shadow_artifact_link_does_not_falsely_leak_at_project_scope(
        self, tenant_a, workspace_a
    ):
        """Regression (Codeberg #353 follow-up fix).

        M3 excluded a Diagram's shadow Artifact (artifact_type='Diagram') from
        baseline.services.resolve_scope_item_ids's project/global scope so it
        would not appear as a spurious item in a baseline snapshot/preview.
        That exclusion is also used by AuditContext.scope_item_ids, which
        made every documents/diagram-ref TraceLink between a Diagram shadow
        Artifact and a real artifact look like a one-endpoint-in-scope leak
        (both endpoints are inside project scope conceptually — only the
        Diagram shadow Artifact was excluded from the *snapshot preview*, not
        from the domain). TRACE-P7 must NOT flag such a link as a BLOCKER.
        """
        with active_tenant(tenant_a):
            requirement = make_artifact(tenant_a, workspace_a, artifact_type="requirement")
            diagram_shadow = make_artifact(tenant_a, workspace_a, artifact_type="Diagram")
            make_trace_link(diagram_shadow, requirement, tenant_a, "references")

            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("project")],
            )

        assert _p7_findings(result) == []

    def test_standard_preset_does_not_run_p7(self, tenant_a, workspace_a):
        """TRACE-P7 is Extended-only; Standard must not emit it."""
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            child = _artifact(tenant_a, workspace_a, parent=root)
            sibling = _artifact(tenant_a, workspace_a)
            make_trace_link(child, sibling, tenant_a, "allocated-to")

            result = RuleEngine().run(
                tier="standard",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        assert _p7_findings(result) == []


#: One link per finding, and the finding message embeds the link's own id:
#: ``"[TRACE-P7] Trace link <uuid> (<type>) leaks out of ..."`
_P7_LINK_ID_RE = re.compile(r"\[TRACE-P7\] Trace link (\S+) ")


class TestTraceP7DeterministicFindingOrder:
    """Review finding F7: per-link findings follow a stable row order.

    ``AuditContext._load_trace_links`` used to read the tenant's links with no
    ``ORDER BY``, so the order of the one-finding-per-leaking-link output was
    whatever the heap happened to return. That leaks into ``offset``/``limit``
    paging of the audit report and into any message-hash baseline. The rows are
    now ordered by primary key; the links below are created in *descending* id
    order, so an accidental match of insertion order is excluded by
    construction.
    """

    def test_findings_are_ordered_by_link_id(self, tenant_a, workspace_a):
        link_ids = sorted(
            uuid.uuid5(uuid.NAMESPACE_URL, f"trace-p7-order-{index:02d}")
            for index in range(6)
        )
        # One document subtree (root -> child) plus one project-only sibling
        # per link, so *every* link below straddles that scope. Insertion order
        # is descending id, i.e. the exact reverse of the contract; an
        # unordered read would very likely replay this order.
        with active_tenant(tenant_a):
            root = _artifact(tenant_a, workspace_a)
            for link_id in reversed(link_ids):
                child = _artifact(tenant_a, workspace_a, parent=root)
                sibling = _artifact(tenant_a, workspace_a)
                TraceLink.objects.create(
                    id=link_id,
                    tenant=tenant_a,
                    source=child,
                    target=sibling,
                    link_type="allocated-to",
                )

        with active_tenant(tenant_a):
            result = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )

        findings = _p7_findings(result)
        assert len(findings) == len(link_ids), [f.message for f in findings]

        seen = []
        for finding in findings:
            match = _P7_LINK_ID_RE.search(finding.message)
            assert match, finding.message
            seen.append(match.group(1))

        assert seen == [str(link_id) for link_id in link_ids], (
            "TRACE-P7 findings are not in a deterministic link order (F7)"
        )

        # Repeating the run must reproduce the same order byte for byte.
        with active_tenant(tenant_a):
            again = RuleEngine().run(
                tier="extended",
                workspace_id=str(workspace_a.id),
                tenant_id=str(tenant_a.id),
                scopes=[AuditScope("document", artifact_id=str(root.id))],
            )
        assert [f.message for f in _p7_findings(again)] == [
            f.message for f in findings
        ]
