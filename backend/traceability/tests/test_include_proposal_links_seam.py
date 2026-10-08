"""``AuditContext.include_proposal_links`` seam (ADR-019 WP5 / review B-05).

A repeated ``traceability.suggest_links`` producer run must audit the
*confirmed* trace state: the unconfirmed proposal TraceLink it persisted on the
first run is not a real trace edge, so counting it would make the missing-link
finding vanish and the O7 dedup would return nothing. The seam that expresses
this is ``AuditContext.include_proposal_links`` (``traceability/audit/types.py``)
and its forwarding through ``RuleEngine.run``.

These tests pin it at the two levels that matter:

* the filter itself on ``AuditContext.iter_trace_links`` (``proposed_at IS NOT
  NULL`` rows are excluded when the flag is off);
* the forwarding — ``RuleEngine.run(include_proposal_links=False)`` must build
  every internal context with the flag off, or the first test would be moot.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from persistence.models import TraceLink
from traceability.audit import rule_engine
from traceability.audit.rule_engine import RuleEngine
from traceability.audit.types import AuditContext
from traceability.tests.conftest import active_tenant, make_artifact

pytestmark = pytest.mark.django_db


def _link(tenant, source, target, *, proposed: bool) -> TraceLink:
    return TraceLink.objects.create(
        tenant=tenant,
        source=source,
        target=target,
        link_type="derives-from",
        proposed_at=timezone.now() if proposed else None,
    )


def test_iter_trace_links_excludes_proposals_when_disabled(tenant_a, workspace_a):
    """The flag filters ``proposed_at IS NOT NULL`` links out of the graph."""
    with active_tenant(tenant_a):
        a1 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        a2 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        a3 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        confirmed = _link(tenant_a, a1, a2, proposed=False)
        proposal = _link(tenant_a, a2, a3, proposed=True)

    with_proposals = {
        row["id"]
        for row in AuditContext(
            tier="standard",
            workspace_id=str(workspace_a.id),
            tenant_id=str(tenant_a.id),
            include_proposal_links=True,
        ).iter_trace_links()
    }
    confirmed_only = {
        row["id"]
        for row in AuditContext(
            tier="standard",
            workspace_id=str(workspace_a.id),
            tenant_id=str(tenant_a.id),
            include_proposal_links=False,
        ).iter_trace_links()
    }

    assert str(confirmed.id) in with_proposals
    assert str(proposal.id) in with_proposals
    assert str(confirmed.id) in confirmed_only
    assert str(proposal.id) not in confirmed_only


def test_rule_engine_forwards_include_proposal_links_to_every_context():
    """``RuleEngine.run`` must pass the flag to each constructed context.

    Rules are not executed (``_run_rule`` is stubbed) so this stays a pure
    forwarding test: only the ``AuditContext`` construction is observed.
    """
    seen: list[bool | None] = []
    real_context = rule_engine.AuditContext

    class _RecordingContext(real_context):
        def __init__(self, **kwargs):
            seen.append(kwargs.get("include_proposal_links"))
            super().__init__(**kwargs)

    with patch.object(rule_engine, "AuditContext", _RecordingContext), patch.object(
        rule_engine.RuleEngine, "_run_rule", return_value=[]
    ):
        RuleEngine().run(
            tier="standard",
            workspace_id=str(uuid4()),
            tenant_id=str(uuid4()),
            include_proposal_links=False,
        )

    assert seen, "the engine must construct at least one AuditContext for 'standard'"
    assert all(flag is False for flag in seen)
