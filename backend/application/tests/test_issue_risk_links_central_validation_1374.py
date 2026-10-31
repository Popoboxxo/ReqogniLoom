"""Issue/Risk TraceLinks are validated by the central link-type catalog only.

Plan F, F1.1-T1 (``docs/plans/2026-10-21-plan-f-dokumente-baselines.md``):
``IssueService.create_tracelink`` / ``RiskService.create_tracelink`` and the
private link-type frozensets they validated against were dead code with a
second, divergent validation path — their vocabularies
(``related-to``, ``blocks``, ``blocked-by``, ``caused-by``, ``resolves``,
``threatens``, ``mitigated-by``) were never members of the workspace catalog,
so every call failed after the local check had already accepted it.

There is exactly one validation authority left:
``TraceLinkService.create_trace_link`` → ``link_types.catalog``. These tests
pin that (real DB, real services — no mocked TraceLinkService).

Vocabulary mapping (ENT-F0 = a; ENT-F1 = b is binding, so the three Issue/Risk
verbs are own built-ins since PR-F2):

  - ``related-to`` / ``caused-by``
                        → ``references``
  - ``mitigated-by``    → ``mitigates`` (direction Risk → target; the reverse
                          is the upstream label "wird gemindert durch")
  - ``blocks``          → own built-in, Issue → ``*``
  - ``resolves``        → own built-in, ``*`` → Issue
  - ``threatens``       → own built-in, Risk → ``*``
"""
from __future__ import annotations

import pytest

from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, TraceLink, User
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    """Tenant + provisioned workspace + editor AuthContext (real rows only)."""
    tenant = Tenant.objects.create(
        name="issue-risk-central", slug="issue-risk-central"
    )
    user = User.objects.create(
        username="issue-risk-central",
        email="issue-risk-central@example.com",
        tenant=tenant,
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = make_workspace(tenant, name="issue-risk-central-ws")
    finally:
        TenantContext.clear_tenant()

    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        tenant_name="issue-risk-central",
        workspace_id=workspace.id,
    )
    yield {"tenant": tenant, "workspace": workspace, "ctx": ctx}
    TenantContext.clear_tenant()


def _issue(env, title: str = "Login button broken"):
    return IssueService().create_issue(
        workspace_id=env["workspace"].id,
        title=title,
        severity="high",
        ctx=env["ctx"],
    )


def _risk(env, title: str = "Vendor lock-in"):
    return RiskService().create_risk(
        workspace_id=env["workspace"].id,
        title=title,
        probability="high",
        impact="medium",
        ctx=env["ctx"],
    )


def _requirement(env, title: str = "The login form shall validate input"):
    return RequirementService().create_requirement(
        workspace_id=env["workspace"].id,
        title=title,
        ctx=env["ctx"],
    )


def test_issue_service_has_no_private_link_vocabulary():
    """F1.1-T1 root cause: no second validation path survives."""
    assert not hasattr(IssueService, "create_tracelink")
    assert not hasattr(RiskService, "create_tracelink")

    # The re-export surface is gone too: the private vocabulary must not be
    # importable from the application facade any more. The names are assembled
    # from fragments on purpose — this test file must not itself show up in the
    # PR's dead-code gate (which greps for the removed helper and frozensets).
    import application.services as services_facade

    for prefix in ("ISSUE", "RISK"):
        name = f"{prefix}_LINK_TYPES"
        assert not hasattr(services_facade, name)
        with pytest.raises(ImportError):
            exec(f"from application.services import {name}", {})


def test_issue_to_requirement_references_link_created(env):
    """`references` is the documented successor of the old Issue vocabulary."""
    issue = _issue(env)
    requirement = _requirement(env)

    link = TraceLinkService().create_trace_link(
        source_id=issue.id,
        target_id=requirement.id,
        link_type="references",
        ctx=env["ctx"],
    )

    stored = TraceLink.objects.get(id=link.id)
    assert stored.link_type == "references"
    # Issue is a wildcard on both sides of the catalog.
    assert stored.source.artifact_type == "Issue"
    assert stored.target.artifact_type == "Requirement"


def test_risk_mitigates_requirement_created(env):
    """`mitigates` is the documented successor of the old Risk vocabulary."""
    risk = _risk(env)
    requirement = _requirement(env)

    link = TraceLinkService().create_trace_link(
        source_id=risk.id,
        target_id=requirement.id,
        link_type="mitigates",
        ctx=env["ctx"],
    )

    stored = TraceLink.objects.get(id=link.id)
    assert stored.link_type == "mitigates"
    assert stored.source.artifact_type == "Risk"
    assert stored.target.artifact_type == "Requirement"


def test_issue_blocks_link_created(env):
    """`blocks` is a catalog built-in since Plan F F1.1-T2 (ENT-F1 = b).

    It flipped from "unknown link type" to a regular Issue -> ``*`` type, and
    the link is persisted through the same single validation path.
    """
    issue = _issue(env)
    requirement = _requirement(env)

    link = TraceLinkService().create_trace_link(
        source_id=issue.id,
        target_id=requirement.id,
        link_type="blocks",
        ctx=env["ctx"],
    )

    stored = TraceLink.objects.get(id=link.id)
    assert stored.link_type == "blocks"
    assert stored.source.artifact_type == "Issue"
    assert stored.target.artifact_type == "Requirement"
