"""GlossaryTermVersion is fully retired (Datenmodell-Konsolidierung Task 28b).

Verifies all three legs of the retirement:
  1. The model no longer exists in the live app registry.
  2. The table it backed (``pl_glossary_term_version``) no longer exists in
     the database.
  3. The replacement path — GlossaryTerm history via ArtifactVersionService —
     genuinely works end to end (create + update -> readable revisions), not
     just "the old thing is gone".
"""
import pytest
from django.apps import apps
from django.db import connection

pytestmark = pytest.mark.django_db


def test_glossary_term_version_model_is_gone():
    with pytest.raises(LookupError):
        apps.get_model("persistence", "GlossaryTermVersion")


def test_glossary_term_version_table_is_gone():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'pl_glossary_term_version'"
        )
        assert cursor.fetchone() is None


def test_glossary_history_readable_via_artifact_version_service():
    """End-to-end replacement check: create() + update() -> list_revisions()."""
    from application.artifact_version_service import ArtifactVersionService
    from application.glossary_service import GlossaryService
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-glossary-drop")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-glossary-drop")
    user = User.objects.create(
        username="glossary-drop", email="glossary-drop@example.com", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )

    service = GlossaryService()
    term = service.create(
        ctx,
        workspace_id=workspace.id,
        term="Latency",
        definition="v1 definition",
    )
    updated = service.update(ctx, term.id, definition="v2 definition")

    from persistence.models import GlossaryTerm

    artifact_id = GlossaryTerm.objects.get(id=updated.id).artifact_id

    version_service = ArtifactVersionService()
    revisions = version_service.list_revisions(artifact_id, ctx)
    assert [r["version"] for r in revisions] == [1, 2]
    assert all(r["content_available"] for r in revisions)

    payload_v1 = version_service.get_payload(artifact_id, 1, ctx)
    payload_v2 = version_service.get_payload(artifact_id, 2, ctx)
    assert payload_v1["definition"] == "v1 definition"
    assert payload_v2["definition"] == "v2 definition"
