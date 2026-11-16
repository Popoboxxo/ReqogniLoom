"""Generic artifact Markdown renderer (MCP-Modernisierung Task 5)."""
import uuid

import pytest

from application.artifact_markdown import (
    ARTIFACT_MARKDOWN_MIME,
    render_artifact_markdown,
)
from application.base import NotFoundError


@pytest.fixture
def md_auth_ctx(db):
    """Minimal AuthContext for a freshly seeded tenant."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-artifact-markdown")
    TenantContext.set_tenant(tenant.id)
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


@pytest.fixture
def seeded_requirement(md_auth_ctx):
    """A Requirement with its backing Artifact, description and status set."""
    from persistence.middleware import set_request_tenant
    from persistence.models import Artifact, Requirement, Workspace

    set_request_tenant(md_auth_ctx.tenant_id)
    workspace = Workspace.objects.create(
        tenant_id=md_auth_ctx.tenant_id, name="ws-artifact-markdown"
    )
    artifact = Artifact.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        workspace=workspace,
        artifact_type="Requirement",
    )
    return Requirement.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        artifact=artifact,
        workspace=workspace,
        title="Login must be possible",
        description="The user can authenticate with email and password.",
        acceptance_criteria="Given valid credentials, a session is issued.",
        category="security",
    )


def test_mime_constant():
    assert ARTIFACT_MARKDOWN_MIME == "text/markdown"


@pytest.mark.django_db
def test_renders_requirement_title_as_h1(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert markdown.splitlines()[0] == f"# {seeded_requirement.title}"


@pytest.mark.django_db
def test_renders_type_and_artifact_id_metadata(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "- **Artifact Type:** Requirement" in markdown
    assert f"- **Artifact ID:** {seeded_requirement.artifact_id}" in markdown


@pytest.mark.django_db
def test_renders_short_scalar_fields_as_bullets(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "- **Category:** security" in markdown
    # choices resolve through get_<field>_display
    assert "- **Type:** System Requirement" in markdown


@pytest.mark.django_db
def test_renders_workflow_status_as_a_bullet(seeded_requirement, md_auth_ctx):
    """Status is engine-projected, not a column (Datenmodell-Konsolidierung)."""
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "- **Status:** draft" in markdown


@pytest.mark.django_db
def test_renders_text_fields_as_sections(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "## Description" in markdown
    assert seeded_requirement.description in markdown
    assert "## Acceptance Criteria" in markdown


@pytest.mark.django_db
def test_renders_json_fields_as_fenced_blocks(seeded_requirement, md_auth_ctx):
    seeded_requirement.acceptance_criteria_items = [
        {"text": "Session issued", "fulfilled": False, "evidence_ref": None}
    ]
    seeded_requirement.save(update_fields=["acceptance_criteria_items"])

    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)

    assert "## Acceptance Criteria Items" in markdown
    assert "```json" in markdown
    assert '"Session issued"' in markdown


@pytest.mark.django_db
def test_omits_empty_fields(seeded_requirement, md_auth_ctx):
    seeded_requirement.acceptance_criteria = ""
    seeded_requirement.save(update_fields=["acceptance_criteria"])
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "## Acceptance Criteria" not in markdown


@pytest.mark.django_db
def test_never_leaks_technical_columns(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    for hidden in ("tenant", "embedding", "**Id:**", "**Workspace:**"):
        assert hidden not in markdown


@pytest.mark.django_db
def test_unknown_artifact_id_raises_not_found(md_auth_ctx):
    with pytest.raises(NotFoundError):
        render_artifact_markdown(uuid.uuid4(), md_auth_ctx)


@pytest.mark.django_db
def test_covers_a_second_artifact_type_class_driven(md_auth_ctx):
    """The same implementation renders a StakeholderNeed (no per-type code)."""
    from persistence.middleware import set_request_tenant
    from persistence.models import Artifact, StakeholderNeed, Workspace

    set_request_tenant(md_auth_ctx.tenant_id)
    workspace = Workspace.objects.create(
        tenant_id=md_auth_ctx.tenant_id, name="ws-artifact-markdown-need"
    )
    artifact = Artifact.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        workspace=workspace,
        artifact_type="StakeholderNeed",
    )
    StakeholderNeed.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        artifact=artifact,
        workspace=workspace,
        title="Auditors must see every change",
        description="Every artifact change is traceable to an actor.",
        moscow_priority="must",
    )

    markdown = render_artifact_markdown(artifact.id, md_auth_ctx)

    assert markdown.splitlines()[0] == "# Auditors must see every change"
    assert "- **Artifact Type:** StakeholderNeed" in markdown
    assert "## Description" in markdown
    assert "Every artifact change is traceable to an actor." in markdown
