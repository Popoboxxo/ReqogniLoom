"""Linkability matrix for every artifact-backing type (Plan F, F1.2-T3 / #1374).

Regression net for R-F9-4: "Kein Test garantiert Verlinkbarkeit für **jeden**
Registry-Typ; künftige Typen (Document/WorkItem) könnten still fehlen".

What is pinned here
-------------------
``persistence.artifact_backing.ARTIFACT_TYPE_MODELS`` is the single registry of
tables that own a backing ``persistence.Artifact`` row. Being in that registry
is what makes a type a valid ``TraceLink`` endpoint. The registry is the test
parameterisation itself, so a newly added type automatically becomes a case in
this matrix — it can never silently drop out.

For every registry type the test creates one object through that type's
**service** (never raw ORM), then links it from an ``Issue`` through the generic
REST surface ``POST /api/v1/trace-links/`` with ``link_type="references"``.
``Issue`` is the wildcard side of a ``references`` pair (``Issue -> *``), so the
pair is legal for every target type unless the workspace catalog says
otherwise.

The id distinction is the point: the request carries the **entity id** the
type's own read endpoint returns (``Diagram.id``, ``GlossaryTerm.id``, ...),
not the backing ``Artifact.id``. Resolution from entity id to Artifact id is
exactly the contract that used to drop types (#1075) and that this matrix
keeps honest.

Exceptions
----------
A type may only be listed in :data:`LINKABILITY_EXCEPTIONS` when the catalog
genuinely forbids the pair (the 400 message quotes the allowed pairs). The
justification must contain the catalog's ``Allowed:`` line. A type that fails
because of a *defect* (no backing row can be created, the service cannot run,
the target resolution drops the entity id) must NOT be excepted here — that is
a real gap and belongs in an issue, not in this constant.

req_id : REQ-L2-TE-001 (TraceLink management), REQ-L1-003 (bidirectional links)
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from uuid import UUID

import pytest
from rest_framework.test import APIClient

from application.workspace_provisioning import provision_workspace_defaults_scoped
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.artifact_backing import ARTIFACT_TYPE_MODELS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Issue, Tenant, TraceLink, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"

#: Registry types the ``references`` catalog genuinely cannot link from an
#: Issue. Empty today: ``Issue`` is a wildcard source for ``references``
#: (``link_types/builtin.py``), so every registry type is a legal target.
#: Each future entry maps ``artifact_type -> justification`` and MUST quote the
#: catalog's ``Allowed: ...`` line (enforced by
#: ``test_exception_justifications_quote_the_catalog_rejection``).
LINKABILITY_EXCEPTIONS: dict[str, str] = {}

#: One parametrised case per registry entry. The registry is the source of
#: truth — never a hand-maintained list of type names.
LINKABILITY_CASES: tuple[str, ...] = tuple(sorted(ARTIFACT_TYPE_MODELS))


def _scenario() -> tuple[Tenant, User, Workspace]:
    """A tenant, an admin user and a fully provisioned extended workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"LinkMatrix-{suffix}", slug=f"link-matrix-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"link-matrix-{suffix}",
        email=f"link-matrix-{suffix}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant,
            name=f"Link Matrix {suffix}",
            preset={"name": "extended"},
            # Goal/MainGoal writes are feature-gated per workspace.
            goals_enabled=True,
        )
        # Link validation is always-on: an unprovisioned workspace rejects
        # every trace link because its catalog is empty.
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    # Workflow definitions for every entity type (Requirement tier-dependent,
    # all others fixed presets). Without these the create services that seed a
    # WorkflowItemState have no definition to initialise against.
    provision_workspace_defaults_scoped(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        requirement_preset="extended",
    )
    return tenant, user, workspace


def _auth_context(user: User, tenant: Tenant, workspace: Workspace) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
        tenant_name=tenant.name,
        workspace_id=workspace.id,
    )


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _create_issue(ctx: AuthContext, workspace: Workspace) -> Issue:
    """The wildcard source endpoint, created through its service."""
    from application.issue_service import IssueService

    return IssueService().create_issue(
        workspace_id=workspace.id,
        title="Login button does not respond",
        severity="medium",
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Entity factories — one per registry type, each through the type's service.
#
# Signature: (ctx, workspace, tenant, user) -> entity id (UUID). The returned
# id is the *entity* id the type's own read endpoint exposes, deliberately not
# the backing Artifact id.
# ---------------------------------------------------------------------------


def _make_requirement(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.requirement_service import RequirementService

    entity = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Login form validates input",
        description="The login form checks both fields before submitting.",
        ctx=ctx,
    )
    return entity.id


def _make_stakeholder_need(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.stakeholder_need_service import StakeholderNeedService

    entity = StakeholderNeedService().create(
        ctx,
        workspace.id,
        "Operators sign in without assistance",
        description="Front-desk staff must reach the dashboard unaided.",
    )
    return entity.id


def _make_architecture_element(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.architecture_service import ArchitectureService

    entity = ArchitectureService().create_architecture_element(
        workspace_id=workspace.id,
        title="Authentication subsystem",
        ctx=ctx,
    )
    return entity.id


def _make_test_case(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.test_service import TestService

    entity = TestService().create_test_case(
        workspace_id=workspace.id,
        title="Login rejects an empty password",
        ctx=ctx,
    )
    return entity.id


def _make_glossary_term(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.glossary_service import GlossaryService

    entity = GlossaryService().create(
        ctx,
        workspace.id,
        term="Session token",
        definition="Opaque credential issued after a successful login.",
    )
    return entity.id


def _make_adr(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.adr_service import AdrService

    entity = AdrService().create_adr(
        workspace_id=workspace.id,
        title="Use JWT bearer tokens for sessions",
        description="Stateless session tokens signed by the auth service.",
        ctx=ctx,
    )
    return entity.id


def _make_risk(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.risk_service import RiskService

    entity = RiskService().create_risk(
        workspace_id=workspace.id,
        title="Session token replay after logout",
        probability="medium",
        impact="high",
        ctx=ctx,
    )
    return entity.id


def _make_issue(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    return _create_issue(ctx, workspace).id


def _make_goal(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.goal_service import GoalService

    entity = GoalService().create_version(
        workspace_id=workspace.id,
        title="Every user signs in within two seconds",
        ctx=ctx,
    )
    return UUID(str(entity["id"]))


def _make_main_goal(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.main_goal_service import MainGoalService

    entity = MainGoalService().create_manual(
        workspace_id=workspace.id,
        content="A login flow that no user has to think about.",
        ctx=ctx,
    )
    return UUID(str(entity["id"]))


def _make_change_request(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.change_request_service import ChangeRequestService

    entity = ChangeRequestService().create_change_request(
        workspace_id=workspace.id,
        title="Add password reset to the login page",
        ctx=ctx,
    )
    return entity.id


def _make_diagram(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from diagram.services import create_diagram

    # PR-F3b (#1374): workspace_id is required on every Diagram create — a
    # workspace-less diagram could never acquire a backing Artifact.
    entity = create_diagram(
        name="Login flow",
        diagram_type="flow",
        payload_format="mermaid",
        content="flowchart TD\n  A --> B",
        tenant=tenant,
        created_by=user,
        workspace_id=workspace.id,
    )
    return entity.id


def _make_icd(
    ctx: AuthContext, workspace: Workspace, tenant: Tenant, user: User
) -> UUID:
    from application.architecture_service import ArchitectureService
    from icd.icd_manager import IcdCreateDTO
    from icd.services import create_icd

    architecture = ArchitectureService()
    root = architecture.create_architecture_element(
        workspace_id=workspace.id,
        title="Authentication subsystem",
        ctx=ctx,
    )
    # I5 (single root per workspace) is active on every tier, so the second
    # endpoint is a child of the first rather than a second root.
    child = architecture.create_architecture_element(
        workspace_id=workspace.id,
        title="Session store",
        parent_id=root.id,
        ctx=ctx,
    )
    result = create_icd(
        IcdCreateDTO(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            name="Authentication to session store",
            source_element_id=root.id,
            target_element_id=child.id,
            interface_type="REST",
            semantic_description="The auth subsystem hands a signed token over.",
            created_by_id=user.id,
        )
    )
    return result.icd.id


_EntityFactory = Callable[[AuthContext, Workspace, Tenant, User], UUID]

#: Registry type -> its service-backed factory. Keyed by ``artifact_type`` so a
#: new registry entry without a factory fails ``test_matrix_has_one_case_per_type``
#: loudly instead of disappearing from the matrix.
_ENTITY_FACTORIES: dict[str, _EntityFactory] = {
    "Requirement": _make_requirement,
    "StakeholderNeed": _make_stakeholder_need,
    "ArchitectureElement": _make_architecture_element,
    "TestCase": _make_test_case,
    "GlossaryTerm": _make_glossary_term,
    "Adr": _make_adr,
    "Risk": _make_risk,
    "Issue": _make_issue,
    "Goal": _make_goal,
    "MainGoal": _make_main_goal,
    "ChangeRequest": _make_change_request,
    "Diagram": _make_diagram,
    "Icd": _make_icd,
}


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("artifact_type", LINKABILITY_CASES)
def test_every_backed_type_is_reachable_from_an_issue(artifact_type: str) -> None:
    """[REQ-L2-TE-001] An Issue references every artifact-backed entity by id.

    The link is created through the public REST surface and carries the
    *entity* id. A 201 proves both the entity -> Artifact resolution and the
    catalog pair; a 400 without an ``Allowed:`` line would be a defect, not a
    documented exception.
    """
    tenant, user, workspace = _scenario()
    ctx = _auth_context(user, tenant, workspace)
    issue = _create_issue(ctx, workspace)
    factory = _ENTITY_FACTORIES[artifact_type]
    target_entity_id = factory(ctx, workspace, tenant, user)

    assert target_entity_id is not None, f"{artifact_type} factory returned no id"

    response = _client(user).post(
        "/api/v1/trace-links/",
        {
            "source_id": str(issue.id),
            "target_id": str(target_entity_id),
            "link_type": "references",
        },
        format="json",
    )

    if artifact_type in LINKABILITY_EXCEPTIONS:
        assert response.status_code == 400, response.content
        payload = response.json()
        message = payload.get("error", {}).get("message", "")
        assert "Allowed:" in message, message
        return

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["link_type"] == "references"

    # Both entity ids were resolved to their backing Artifact rows.
    assert body["source_id"] == str(issue.artifact_id)

    set_request_tenant(tenant.id)
    try:
        link = TraceLink.objects.get(id=body["id"])
        assert link.source.artifact_type == "Issue"
        assert link.target.artifact_type == artifact_type
        assert str(link.target_id) == body["target_id"]
        # The stored target is the Artifact row, not the entity id that was
        # posted. This is the distinction the whole matrix is about.
        assert str(link.target_id) != str(target_entity_id)
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Anti-cheat / completeness guards
# ---------------------------------------------------------------------------


def test_matrix_has_one_case_per_type() -> None:
    """[REQ-L2-TE-001] The matrix is exactly the registry — no silent gaps.

    Asserts the number of collected cases equals ``len(ARTIFACT_TYPE_MODELS)``
    without pinning a fixed pass count (KA-F-07): the expected number is
    derived from the registry, never from a literal.
    """
    assert len(LINKABILITY_CASES) == len(ARTIFACT_TYPE_MODELS)
    assert set(LINKABILITY_CASES) == set(ARTIFACT_TYPE_MODELS)
    # A registry entry with no factory would otherwise be an unexplained
    # KeyError at run time instead of a visible completeness failure.
    assert set(_ENTITY_FACTORIES) == set(ARTIFACT_TYPE_MODELS)


def test_exception_justifications_quote_the_catalog_rejection() -> None:
    """[REQ-L2-TE-001] An exception must quote the catalog's ``Allowed:`` line.

    Keeps :data:`LINKABILITY_EXCEPTIONS` honest: a type may only be waived when
    the catalog genuinely forbids the pair, never when the failure is a defect.
    """
    for artifact_type, justification in LINKABILITY_EXCEPTIONS.items():
        assert artifact_type in ARTIFACT_TYPE_MODELS
        assert "Allowed:" in justification, (
            f"Exception for {artifact_type} must quote the catalog's "
            f"'Allowed:' line, got: {justification!r}"
        )
