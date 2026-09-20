"""Issue #932 — local readable ``uid`` allocation.

Eight artifact models carry a local, human-readable identifier (``REQ-001``,
``NEED-014``, …). These tests pin the two contracts the issue asks for:

* ``generate_local_uid`` is sequential, per ``(workspace, item_type)``, and
  never recycles a number (a counter, not ``MAX+1``);
* every artifact-create service allocates one automatically when the caller
  does not supply it.

ReqIF's external identity is *not* involved here — it lives on the Artifact's
``reqif_*`` fields (#1003).
"""
from __future__ import annotations

import re

import pytest

from application.local_uid import generate_local_uid, uid_prefix
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_service import TestService
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace


def test_uid_prefix_map():
    assert uid_prefix("Requirement") == "REQ"
    assert uid_prefix("StakeholderNeed") == "NEED"
    assert uid_prefix("TestCase") == "TC"
    assert uid_prefix("TestRun") == "RUN"
    # Unknown types still get a deterministic, upper-cased prefix.
    assert uid_prefix("Widget") == "WIDGET"


@pytest.mark.django_db
def test_generate_local_uid_is_sequential_and_non_recycling():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)

        assert generate_local_uid("Requirement", ws.id) == "REQ-001"
        assert generate_local_uid("Requirement", ws.id) == "REQ-002"
        assert generate_local_uid("Requirement", ws.id) == "REQ-003"

        # A separate counter per item_type — the NEED sequence is untouched.
        assert generate_local_uid("StakeholderNeed", ws.id) == "NEED-001"
        assert generate_local_uid("StakeholderNeed", ws.id) == "NEED-002"

        # Non-recycling: the next Requirement number follows 003 even though
        # nothing has been persisted at these numbers.
        assert generate_local_uid("Requirement", ws.id) == "REQ-004"


@pytest.mark.django_db
def test_generate_local_uid_is_scoped_per_workspace():
    with active_tenant() as tenant:
        ws1 = make_workspace(tenant)
        ws2 = make_workspace(tenant)

        assert generate_local_uid("Requirement", ws1.id) == "REQ-001"
        assert generate_local_uid("Requirement", ws2.id) == "REQ-001"
        assert generate_local_uid("Requirement", ws1.id) == "REQ-002"


@pytest.mark.django_db
def test_create_requirement_assigns_a_local_uid():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        first = RequirementService().create_requirement(
            workspace_id=ws.id, title="First", ctx=ctx
        )
        second = RequirementService().create_requirement(
            workspace_id=ws.id, title="Second", ctx=ctx
        )

        assert re.fullmatch(r"REQ-\d{3}", first.uid or ""), first.uid
        assert first.uid != second.uid
        assert re.fullmatch(r"REQ-\d{3}", second.uid or ""), second.uid


@pytest.mark.django_db
def test_create_stakeholder_need_assigns_a_local_uid():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        need = StakeholderNeedService().create(ctx, ws.id, "A need")

        assert re.fullmatch(r"NEED-\d{3}", need.uid or ""), need.uid


@pytest.mark.django_db
def test_create_test_case_assigns_a_local_uid():
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        test_case = TestService().create_test_case(
            workspace_id=ws.id, title="A test", ctx=ctx
        )

        assert re.fullmatch(r"TC-\d{3}", test_case.uid or ""), test_case.uid


@pytest.mark.django_db
def test_explicit_uid_wins_over_generation():
    """A caller-supplied uid is honoured (ReqIF import and API callers)."""
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        req = RequirementService().create_requirement(
            workspace_id=ws.id, title="Pinned", ctx=ctx, uid="REQ-ENGINE-1"
        )

        assert req.uid == "REQ-ENGINE-1"
