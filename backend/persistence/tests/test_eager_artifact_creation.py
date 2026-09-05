"""New rows of every artifact type are Artifact-backed on creation.

Datenmodell-Konsolidierung Phase 3, spec section 4.3.
"""
import pytest

from persistence.tests.factories import editor_ctx, make_workspace


@pytest.fixture
def env(db):
    from persistence.models import Tenant
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-eager", slug="t-eager")
    TenantContext.set_tenant(tenant.id)
    workspace = make_workspace(tenant)
    ctx = editor_ctx(tenant, workspace)
    return tenant, workspace, ctx


@pytest.mark.django_db
def test_new_diagram_is_backed(env):
    from diagram.manager import DiagramManager

    tenant, workspace, _ctx = env
    diagram = DiagramManager().create_diagram(
        name="D",
        diagram_type="block",
        payload_format="mermaid",
        content="graph TD;A-->B;",
        tenant=tenant,
        workspace_id=workspace.id,
    )

    assert diagram.artifact_id is not None
    assert diagram.artifact.artifact_type == "Diagram"


@pytest.mark.django_db
def test_new_icd_is_backed(env):
    from icd.icd_manager import IcdCreateDTO, IcdManager
    from persistence.models import ArchitectureElement, Artifact

    tenant, workspace, _ctx = env

    source_artifact = Artifact.objects.create(
        artifact_type="ArchitectureElement", tenant=tenant, workspace_id=workspace.id
    )
    target_artifact = Artifact.objects.create(
        artifact_type="ArchitectureElement", tenant=tenant, workspace_id=workspace.id
    )
    source = ArchitectureElement.objects.create(
        artifact=source_artifact, tenant=tenant, title="Source"
    )
    target = ArchitectureElement.objects.create(
        artifact=target_artifact, tenant=tenant, title="Target"
    )

    result = IcdManager().create_icd(
        IcdCreateDTO(
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            name="ICD",
            source_element_id=source.id,
            target_element_id=target.id,
        )
    )

    assert result.icd.artifact_id is not None
    assert result.icd.artifact.artifact_type == "Icd"


@pytest.mark.django_db
def test_new_glossary_term_is_backed(env):
    from application.glossary_service import GlossaryService
    from persistence.models import GlossaryTerm

    _tenant, workspace, ctx = env
    dto = GlossaryService().create(
        ctx=ctx, workspace_id=workspace.id, term="Widget", definition="a thing"
    )
    row = GlossaryTerm.objects.get(pk=dto.id)

    assert row.artifact_id is not None
    assert row.artifact.artifact_type == "GlossaryTerm"


@pytest.mark.django_db
def test_new_change_request_is_backed(env):
    from application.change_request_service import ChangeRequestService
    from persistence.models import ChangeRequest

    _tenant, workspace, ctx = env
    created = ChangeRequestService().create_change_request(
        workspace_id=workspace.id, title="Change request", description="d", ctx=ctx
    )
    row = ChangeRequest.objects.get(pk=created.id)

    assert row.artifact_id is not None
    assert row.artifact.artifact_type == "ChangeRequest"
