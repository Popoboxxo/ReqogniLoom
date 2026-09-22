"""#424 — every TestCase producer marks provenance explicitly.

Cluster-5 spec section 4.8/4.9. Complements the service-level tests in
``test_testcase_origin_reviewed_424.py`` with the producer enumeration:

  * P4 — the interview formalisation adapter (``_test_case``) must create
    ``ai_generated``/unreviewed rows and must not be swayed by an ``origin``
    key in the proposal dict (R1: the dict filter is the normative mechanism).
  * P3 — the MCP ``test.derive_from_requirement`` write path must mark the
    persisted row the same way (AC-424-15).
  * P2 — MCP ``test.create`` keeps the ``manual`` default (AC-424-17).
  * AC-424-16 — the productive ``create_test_case(`` call-site set is frozen
    as ``{P1..P6}`` so a future producer cannot silently default to ``manual``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from persistence.models import ScenarioKind, TestCaseOrigin

pytestmark = pytest.mark.django_db

#: Repository root of the backend package (``.../backend``).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-424-prod", slug="t-424-prod")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-424-prod")
    user = User.objects.create(
        username="u-424-prod", email="u-424-prod@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, workspace, user, ctx


# ---------------------------------------------------------------------------
# P4 — interview adapter
# ---------------------------------------------------------------------------


def test_interview_adapter_marks_ai_generated(env):
    """AC-424-14 (first half)."""
    from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

    _tenant, workspace, _user, ctx = env
    adapter = ARTIFACT_CREATION_ADAPTERS["TestCase"]

    ref = adapter({"title": "TC from interview"}, ctx, workspace.id)

    from persistence.models import TestCase

    row = TestCase.objects.get(id=ref.entity_id)
    assert row.origin == TestCaseOrigin.AI_GENERATED
    assert row.reviewed is False


def test_interview_adapter_ignores_origin_in_proposal(env):
    """AC-424-14 (overwrite protection, R1: the dict filter is normative)."""
    from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS

    _tenant, workspace, _user, ctx = env
    adapter = ARTIFACT_CREATION_ADAPTERS["TestCase"]

    ref = adapter(
        {
            "title": "TC from interview",
            "origin": "manual",
            "reviewed": True,
            "scenario_kind": ScenarioKind.OFF_NOMINAL,
        },
        ctx,
        workspace.id,
    )

    from persistence.models import TestCase

    row = TestCase.objects.get(id=ref.entity_id)
    assert row.origin == TestCaseOrigin.AI_GENERATED
    assert row.reviewed is False
    # Non-provenance proposal fields still pass through.
    assert row.scenario_kind == ScenarioKind.OFF_NOMINAL


def test_interview_adapter_result_counts_after_review(env):
    """AC-424-14 (second half): review makes it verification evidence."""
    from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS
    from application.test_service import TestService

    _tenant, workspace, _user, ctx = env
    ref = ARTIFACT_CREATION_ADAPTERS["TestCase"](
        {"title": "TC from interview"}, ctx, workspace.id
    )

    reviewed = TestService().mark_reviewed(ref.entity_id, ctx, reviewed=True)
    assert reviewed.reviewed is True


# ---------------------------------------------------------------------------
# P3 — MCP derive_from_requirement (write mode)
# ---------------------------------------------------------------------------


def test_mcp_derive_write_marks_ai_generated(env):
    """AC-424-15: the productive LLM persistence path is marked."""
    from link_types.workspace_store import provision_workspace_link_types
    from mcp_server.tools.tests import McpTestToolGroup
    from persistence.models import Artifact, Requirement

    tenant, workspace, _user, ctx = env
    # The derive write path creates a 'verifies' TraceLink, which the
    # workspace's materialized link-type catalog must allow.
    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    req_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    req = Requirement.objects.create(
        tenant=tenant, artifact=req_artifact, title="R for derive"
    )

    group = McpTestToolGroup()
    result = group._handle_derive_from_requirement(
        params={"requirement_id": str(req.id), "mode": "write"},
        auth_context=ctx,
        api_key="test",
    )

    assert result.success, result.message
    written_id = result.data["written"]["id"]

    from persistence.models import TestCase

    row = TestCase.objects.get(id=written_id)
    assert row.origin == TestCaseOrigin.AI_GENERATED
    assert row.reviewed is False


# ---------------------------------------------------------------------------
# P2 — MCP test.create keeps the manual default (AC-424-17)
# ---------------------------------------------------------------------------


def test_mcp_test_create_defaults_to_manual(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    group = McpTestToolGroup()
    result = group._handle_create(
        params={"workspace_id": str(workspace.id), "title": "Manual TC"},
        auth_context=ctx,
        api_key="test",
    )

    assert result.success, result.message
    payload = result.data["test_case"]
    assert payload["origin"] == TestCaseOrigin.MANUAL
    assert payload["reviewed"] is True


def test_mcp_test_create_accepts_ai_generated(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    group = McpTestToolGroup()
    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "AI TC",
            "origin": "ai_generated",
        },
        auth_context=ctx,
        api_key="test",
    )

    assert result.success, result.message
    payload = result.data["test_case"]
    assert payload["origin"] == TestCaseOrigin.AI_GENERATED
    assert payload["reviewed"] is False


# ---------------------------------------------------------------------------
# MCP test.mark_reviewed (AC-424-11, MCP surface)
# ---------------------------------------------------------------------------


def test_mcp_mark_reviewed_is_idempotent(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    group = McpTestToolGroup()
    created = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "AI TC",
            "origin": "ai_generated",
        },
        auth_context=ctx,
        api_key="test",
    )
    tc_id = created.data["test_case"]["id"]

    first = group._handle_mark_reviewed(
        params={"test_case_id": tc_id, "reviewed": True},
        auth_context=ctx,
        api_key="test",
    )
    assert first.success, first.message
    assert first.data["reviewed"] is True

    second = group._handle_mark_reviewed(
        params={"test_case_id": tc_id, "reviewed": True},
        auth_context=ctx,
        api_key="test",
    )
    assert second.success, second.message
    assert second.data["version"] == first.data["version"]


def test_mcp_mark_reviewed_requires_a_boolean(env):
    from mcp_server.tools.tests import McpTestToolGroup

    _tenant, workspace, _user, ctx = env
    group = McpTestToolGroup()
    result = group._handle_mark_reviewed(
        params={"test_case_id": "00000000-0000-0000-0000-000000000000", "reviewed": "yes"},
        auth_context=ctx,
        api_key="test",
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# AC-424-16 — additivity watch test (frozen producer set)
# ---------------------------------------------------------------------------


def _productive_create_test_case_call_sites() -> dict[str, int]:
    """Return ``{relative_path: call_count}`` for productive call sites.

    ``create_test_case(`` calls outside ``*/tests/``, ``*/conftest.py`` and the
    migrations; the *definition* (``def create_test_case``) and comment lines
    are excluded, mirroring the spec's enumeration scope. A file path is the
    stable key; the count catches a second call site added to a file that
    already has one.
    """
    pattern = re.compile(r"create_test_case\s*\(")
    counts: dict[str, int] = {}

    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT).as_posix()
        if "/tests/" in f"/{rel}" or rel.endswith("/conftest.py"):
            continue
        if rel.startswith("migrations/") or "/migrations/" in rel:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover — defensive
            continue
        hits = 0
        for line in text.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "def create_test_case" in line:
                continue
            if pattern.search(line):
                hits += 1
        if hits:
            counts[rel] = hits
    return counts


def test_create_test_case_producer_set_is_frozen():
    """AC-424-16: exactly the P1..P6 producers from spec section 4.8.

    A new productive call site (or a second one in an existing file) must turn
    this test red so its author makes an explicit ``origin``/``reviewed``
    decision (and extends the enumeration) instead of silently inheriting the
    ``manual`` service default.
    """
    assert _productive_create_test_case_call_sites() == {
        # P1 REST TestCaseViewSet.create
        "rest_api/views.py": 1,
        # P3 MCP test.derive_from_requirement (write mode)
        # P2 MCP test.create
        "mcp_server/tools/tests.py": 2,
        # P4 interview formalisation adapter
        "application/interview_artifact_adapters.py": 1,
        # P5 seed_toothbrush fixture command
        "auth_tenancy/management/commands/seed_toothbrush.py": 1,
        # P6 seed_full_chain fixture command (#272, review finding R2). The
        # fixture is human-authored demo material, so it pins
        # origin="manual"/reviewed=True explicitly.
        "auth_tenancy/management/commands/seed_full_chain.py": 1,
    }
