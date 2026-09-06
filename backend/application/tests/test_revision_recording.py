"""Every content write appends a revision.

Datenmodell-Konsolidierung Phase 5, spec section 6.1.
"""
import pytest

from application.artifact_version_service import snapshot_fields


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-rev-record")
    TenantContext.set_tenant(tenant.id)
    # goals_enabled: GoalService/MainGoalService gate their whole write path on
    # it (PermissionDeniedError otherwise), and it defaults to False.
    workspace = Workspace.objects.create(
        tenant=tenant, name="ws-rev-record", goals_enabled=True
    )
    # A real User row: StakeholderNeed.created_by and ArtifactVersion
    # .created_by are FKs, so a synthetic ctx.user_id fails their constraint.
    user = User.objects.create(
        username="rev-record", email="rev-record@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, workspace, ctx


def test_snapshot_uses_the_diff_field_list():
    from application.artifact_diff_service import _ENTITY_FIELDS

    class _Req:
        title = "T"
        description = "D"
        category = "C"

    assert set(snapshot_fields(_Req(), "Requirement")) == set(
        _ENTITY_FIELDS["Requirement"]
    )


def test_snapshot_of_an_unknown_type_is_empty():
    assert snapshot_fields(object(), "Nope") == {}


@pytest.mark.django_db
def test_requirement_create_records_revision_one(env):
    from application.artifact_version_service import ArtifactVersionService
    from application.requirement_service import RequirementService

    _tenant, workspace, ctx = env
    req = RequirementService().create_requirement(
        workspace_id=workspace.id, title="R", description="d", ctx=ctx
    )

    entries = ArtifactVersionService().list_revisions(req.artifact_id, ctx)
    assert [e["version"] for e in entries] == [1]


@pytest.mark.django_db
def test_requirement_update_records_revision_two(env):
    from application.artifact_version_service import ArtifactVersionService
    from application.requirement_service import RequirementService

    _tenant, workspace, ctx = env
    service = RequirementService()
    req = service.create_requirement(
        workspace_id=workspace.id, title="R", description="d", ctx=ctx
    )
    service.update_requirement(req.id, ctx, title="R2")

    entries = ArtifactVersionService().list_revisions(req.artifact_id, ctx)
    assert [e["version"] for e in entries] == [1, 2]
    assert (
        ArtifactVersionService().get_payload(req.artifact_id, 2, ctx)["title"] == "R2"
    )


@pytest.mark.django_db
def test_diagram_update_records_a_revision(env):
    from application.artifact_version_service import ArtifactVersionService
    from diagram.manager import DiagramManager

    tenant, workspace, ctx = env
    manager = DiagramManager()
    diagram = manager.create_diagram(
        name="D",
        diagram_type="block",
        payload_format="mermaid",
        content="graph TD;A-->B;",
        tenant=tenant,
        workspace_id=workspace.id,
    )
    manager.update_diagram(
        diagram_id=diagram.id,
        payload_format="mermaid",
        content="graph TD;A-->C;",
    )

    entries = ArtifactVersionService().list_revisions(diagram.artifact_id, ctx)
    assert [e["version"] for e in entries] == [1, 2]
    payload = ArtifactVersionService().get_payload(diagram.artifact_id, 2, ctx)
    assert payload["payload"] == "graph TD;A-->C;"


@pytest.mark.django_db
def test_change_request_create_and_update_record_revisions(env):
    from application.artifact_version_service import ArtifactVersionService
    from application.change_request_service import ChangeRequestService

    _tenant, workspace, ctx = env
    service = ChangeRequestService()
    cr = service.create_change_request(
        workspace_id=workspace.id,
        title="CR-1",
        description="d",
        impact_assessment="low",
        ctx=ctx,
    )
    service.update_change_request(cr.id, ctx, impact_assessment="high")

    from persistence.models import ChangeRequest

    artifact_id = ChangeRequest.objects.get(pk=cr.id).artifact_id
    versions = ArtifactVersionService()
    entries = versions.list_revisions(artifact_id, ctx)

    assert [e["version"] for e in entries] == [1, 2]
    assert versions.get_payload(artifact_id, 1, ctx)["impact_assessment"] == "low"
    assert versions.get_payload(artifact_id, 2, ctx)["impact_assessment"] == "high"


@pytest.mark.django_db
def test_goal_lineage_records_every_version_under_one_anchor(env):
    """Each Goal version owns a new Artifact, so the lineage anchors on v1."""
    from application.artifact_version_service import ArtifactVersionService
    from application.goal_service import GoalService

    _tenant, workspace, ctx = env
    service = GoalService()
    first = service.create_version(
        workspace_id=workspace.id, title="G1", description="d", ctx=ctx
    )
    service.update(first["id"], ctx, title="G2")

    from persistence.models import Goal

    anchor_artifact_id = Goal.objects.get(pk=first["id"]).artifact_id
    versions = ArtifactVersionService()
    entries = versions.list_revisions(anchor_artifact_id, ctx)

    assert [e["version"] for e in entries] == [1, 2]
    assert versions.get_payload(anchor_artifact_id, 1, ctx)["title"] == "G1"
    assert versions.get_payload(anchor_artifact_id, 2, ctx)["title"] == "G2"


@pytest.mark.django_db
def test_goal_revision_number_equals_sequence_number(env):
    from application.artifact_version_service import (
        ArtifactVersionService,
        lineage_anchor_artifact_id,
    )
    from application.goal_service import GoalService
    from persistence.models import Goal

    _tenant, workspace, ctx = env
    service = GoalService()
    first = service.create_version(
        workspace_id=workspace.id, title="G1", description="d", ctx=ctx
    )
    second = service.update(first["id"], ctx, title="G2")
    third = service.update(second["id"], ctx, title="G3")

    goal = Goal.objects.get(pk=third["id"])
    anchor = lineage_anchor_artifact_id(Goal, goal.lineage_id)
    entries = ArtifactVersionService().list_revisions(anchor, ctx)

    assert [e["version"] for e in entries] == [1, 2, 3]
    assert goal.sequence_number == 3


@pytest.mark.django_db
def test_main_goal_lineage_records_every_version(env):
    """MainGoal has no lineage_id — the workspace is its lineage."""
    from application.artifact_version_service import (
        ArtifactVersionService,
        lineage_anchor_artifact_id,
    )
    from application.main_goal_service import MainGoalService

    _tenant, workspace, ctx = env
    service = MainGoalService()
    first = service.create_manual(workspace_id=workspace.id, content="M1", ctx=ctx)
    service.create_manual(workspace_id=workspace.id, content="M2", ctx=ctx)

    from persistence.models import MainGoal

    anchor_artifact_id = MainGoal.objects.get(pk=first["id"]).artifact_id
    assert (
        lineage_anchor_artifact_id(MainGoal, workspace_id=workspace.id)
        == anchor_artifact_id
    )

    versions = ArtifactVersionService()
    entries = versions.list_revisions(anchor_artifact_id, ctx)

    assert [e["version"] for e in entries] == [1, 2]
    assert versions.get_payload(anchor_artifact_id, 1, ctx)["content"] == "M1"
    assert versions.get_payload(anchor_artifact_id, 2, ctx)["content"] == "M2"


def test_every_artifact_type_has_a_snapshot_field_list():
    """No type may record an empty payload — a silent history gap."""
    from application.artifact_diff_service import _ENTITY_FIELDS

    recorded_types = [
        "Requirement",
        "StakeholderNeed",
        "TestCase",
        "ArchitectureElement",
        "Adr",
        "Risk",
        "Issue",
        "GlossaryTerm",
        "ChangeRequest",
        "Goal",
        "MainGoal",
        "Diagram",
        "Icd",
    ]
    for item_type in recorded_types:
        assert _ENTITY_FIELDS.get(item_type), f"{item_type} has no diffable fields"


def _create_then_update(item_type, workspace, ctx):
    """Run *item_type*'s real create+update write path; return the row's pk.

    Deliberately calls the production services rather than writing rows, so a
    recording site that is missing (or placed where it never runs) shows up as
    a missing revision instead of passing on a hand-built fixture.
    """
    if item_type == "StakeholderNeed":
        from application.stakeholder_need_service import StakeholderNeedService

        service = StakeholderNeedService()
        dto = service.create(
            ctx=ctx, workspace_id=workspace.id, title="N", description="d"
        )
        service.update(ctx=ctx, need_id=dto.id, title="N2")
        return dto.id

    if item_type == "TestCase":
        from application.test_service import TestService

        service = TestService()
        row = service.create_test_case(
            workspace_id=workspace.id, title="T", ctx=ctx, description="d"
        )
        service.update_test_case(row.id, ctx, title="T2")
        return row.id

    if item_type == "ArchitectureElement":
        from application.architecture_service import ArchitectureService

        service = ArchitectureService()
        row = service.create_architecture_element(
            workspace_id=workspace.id, title="A", ctx=ctx, description="d"
        )
        service.update_architecture_element(row.id, ctx, title="A2")
        return row.id

    if item_type == "Adr":
        from application.adr_service import AdrService

        service = AdrService()
        row = service.create_adr(
            workspace_id=workspace.id, title="ADR", description="d", ctx=ctx
        )
        service.update_adr(row.id, ctx, title="ADR2")
        return row.id

    if item_type == "Risk":
        from application.risk_service import RiskService

        service = RiskService()
        row = service.create_risk(
            workspace_id=workspace.id,
            title="RK",
            probability="low",
            impact="low",
            ctx=ctx,
        )
        service.update_risk(row.id, ctx, title="RK2")
        return row.id

    if item_type == "Issue":
        from application.issue_service import IssueService

        service = IssueService()
        row = service.create_issue(
            workspace_id=workspace.id, title="IS", description="d", ctx=ctx
        )
        service.update_issue(row.id, ctx, title="IS2")
        return row.id

    if item_type == "GlossaryTerm":
        from application.glossary_service import GlossaryService

        service = GlossaryService()
        dto = service.create(
            ctx=ctx, workspace_id=workspace.id, term="G", definition="d"
        )
        service.update(ctx=ctx, term_id=dto.id, definition="d2")
        return dto.id

    raise AssertionError(f"unhandled item_type {item_type}")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "item_type",
    [
        "StakeholderNeed",
        "TestCase",
        "ArchitectureElement",
        "Adr",
        "Risk",
        "Issue",
        "GlossaryTerm",
    ],
)
def test_each_in_place_type_records_create_and_update(env, item_type):
    """Coverage rule (Decision D-4): no type is left unhistorised."""
    from application.artifact_version_service import ArtifactVersionService
    from persistence.artifact_backing import model_for

    _tenant, workspace, ctx = env
    entity = model_for(item_type).objects.get(
        pk=_create_then_update(item_type, workspace, ctx)
    )

    entries = ArtifactVersionService().list_revisions(entity.artifact_id, ctx)
    assert [e["version"] for e in entries] == [1, 2], item_type


@pytest.mark.django_db
def test_icd_create_and_update_record_revisions(env):
    from application.artifact_version_service import ArtifactVersionService
    from icd.icd_manager import IcdCreateDTO, IcdManager, IcdUpdateDTO
    from persistence.models import ArchitectureElement, Artifact

    tenant, workspace, ctx = env

    def _element(title: str) -> ArchitectureElement:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="ArchitectureElement"
        )
        return ArchitectureElement.objects.create(
            tenant=tenant, artifact=artifact, title=title, element_type="Block"
        )

    source = _element("src")
    target = _element("dst")

    manager = IcdManager()
    result = manager.create_icd(
        IcdCreateDTO(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            name="ICD-1",
            source_element_id=source.id,
            target_element_id=target.id,
            direction="bidirectional",
            interface_type="data",
            semantic_description="initial",
        )
    )
    manager.update_icd(
        result.icd.id,
        IcdUpdateDTO(semantic_description="revised"),
        tenant_id=tenant.id,
    )

    versions = ArtifactVersionService()
    artifact_id = result.icd.artifact_id
    entries = versions.list_revisions(artifact_id, ctx)

    assert [e["version"] for e in entries] == [1, 2]
    assert versions.get_payload(artifact_id, 1, ctx)["semantic_description"] == "initial"
    assert versions.get_payload(artifact_id, 2, ctx)["semantic_description"] == "revised"
