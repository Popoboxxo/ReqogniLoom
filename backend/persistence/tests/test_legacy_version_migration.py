"""The three legacy version tables' history survives the move to ArtifactVersion.

Datenmodell-Konsolidierung Phase 5, spec section 6.2 ("ohne Historienverlust").

Exercises ``persistence/migrations/0078_migrate_legacy_versions.migrate_history``
directly against the live registry rather than replaying the migration graph:
the test database already has 0078 applied (and against an empty database it is
a no-op), so a fixture-built history is the only way to observe what the copy
actually does with rows.

The function is registry-agnostic — it only calls ``get_model``/``.objects`` —
so handing it ``django.apps.apps`` exercises the same code path the migration
runs, with the live models standing in for the historical ones.
"""
import uuid
from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection

pytestmark = pytest.mark.django_db

# The migration module's name starts with a digit, so it cannot be imported
# with an ``import`` statement.
_MIGRATION = "persistence.migrations.0078_migrate_legacy_versions"


def _migrate_history():
    """Run the migration's copy step against the live models."""
    module = import_module(_MIGRATION)
    with connection.schema_editor() as schema_editor:
        module.migrate_history(apps, schema_editor)


@pytest.fixture
def env(db):
    """Tenant + workspace + user, with an armed TenantContext."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="t-legacy-versions")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws-legacy-versions")
    user = User.objects.create(
        username="legacy-versions",
        email="legacy-versions@example.com",
        tenant=tenant,
    )
    return tenant, workspace, user


def _artifact(tenant, workspace, artifact_type):
    from persistence.models import Artifact

    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


@pytest.fixture
def legacy_diagram(env):
    """A Diagram with two legacy DiagramVersion rows and no ArtifactVersion."""
    from diagram.models import Diagram, DiagramVersion

    tenant, workspace, user = env
    diagram = Diagram.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="D",
        diagram_type="block",
        artifact=_artifact(tenant, workspace, "Diagram"),
    )
    for number, payload in ((1, "graph TD;A-->B;"), (2, "graph TD;A-->C;")):
        DiagramVersion.objects.create(
            tenant=tenant,
            diagram=diagram,
            version_number=number,
            payload_format="mermaid",
            payload=payload,
            created_by=user,
        )
    return diagram


def test_migrated_history_is_readable(env, legacy_diagram):
    from application.artifact_version_service import ArtifactVersionService

    tenant, workspace, user = env
    ctx = _ctx(tenant, workspace, user)

    _migrate_history()

    service = ArtifactVersionService()
    entries = service.list_revisions(legacy_diagram.artifact_id, ctx)
    assert [entry["version"] for entry in entries] == [1, 2]
    assert (
        service.get_payload(legacy_diagram.artifact_id, 1, ctx)["payload"]
        == "graph TD;A-->B;"
    )
    assert (
        service.get_payload(legacy_diagram.artifact_id, 2, ctx)["payload"]
        == "graph TD;A-->C;"
    )


def test_migrated_payload_key_set_matches_the_differ(env, legacy_diagram):
    """A migrated snapshot must carry exactly the fields the differ reads."""
    from application.artifact_diff_service import _ENTITY_FIELDS
    from application.artifact_version_service import ArtifactVersionService

    tenant, workspace, user = env
    ctx = _ctx(tenant, workspace, user)

    _migrate_history()

    payload = ArtifactVersionService().get_payload(
        legacy_diagram.artifact_id, 1, ctx
    )
    assert set(payload) == set(_ENTITY_FIELDS["Diagram"])


def test_original_timestamps_are_preserved(env, legacy_diagram):
    """History must not collapse onto the migration's own timestamp."""
    from diagram.models import DiagramVersion
    from persistence.models import ArtifactVersion

    _migrate_history()

    source = {
        row.version_number: row.created_at
        for row in DiagramVersion.objects.filter(diagram=legacy_diagram)
    }
    migrated = {
        row.revision: row.created_at
        for row in ArtifactVersion.objects.filter(
            artifact_id=legacy_diagram.artifact_id
        )
    }
    assert migrated == source


def test_rerun_is_idempotent(env, legacy_diagram):
    """An identical mirror row counts as migrated, never as a duplicate."""
    from persistence.models import ArtifactVersion

    _migrate_history()
    _migrate_history()

    assert (
        ArtifactVersion.objects.filter(
            artifact_id=legacy_diagram.artifact_id
        ).count()
        == 2
    )


def test_unbacked_owner_fails_the_migration(env, legacy_diagram):
    """A version row whose entity has no Artifact must not be dropped."""
    from diagram.models import Diagram

    Diagram.objects.filter(pk=legacy_diagram.pk).update(artifact=None)

    with pytest.raises(RuntimeError, match="without a backing Artifact"):
        _migrate_history()


def test_conflicting_revision_fails_the_migration(env, legacy_diagram):
    """A differing row at the same (artifact, revision) must not be skipped."""
    from persistence.models import ArtifactVersion

    tenant, _workspace, _user = env
    ArtifactVersion.objects.create(
        tenant=tenant,
        artifact_id=legacy_diagram.artifact_id,
        revision=1,
        payload={"payload_format": "mermaid", "payload": "other", "canvas_json": None},
    )

    with pytest.raises(RuntimeError, match="collide with a differing"):
        _migrate_history()


def test_icd_payload_reads_the_name_from_the_header(env):
    """IcdVersion has no ``name`` column — it lives on the Icd header."""
    from application.artifact_version_service import ArtifactVersionService
    from icd.models import Icd, IcdVersion

    tenant, workspace, user = env
    icd = Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        name="I-1",
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        artifact=_artifact(tenant, workspace, "Icd"),
    )
    IcdVersion.objects.create(
        tenant=tenant,
        icd=icd,
        version_number=1,
        direction="unidirectional",
        interface_type="provides",
        semantic_description="s",
        preconditions=["p"],
        postconditions=["q"],
        invariants=["i"],
    )

    _migrate_history()

    payload = ArtifactVersionService().get_payload(
        icd.artifact_id, 1, _ctx(tenant, workspace, user)
    )
    assert payload["name"] == "I-1"
    assert payload["preconditions"] == ["p"]


def test_glossary_payload_reads_the_term_from_the_owner(env):
    """GlossaryTermVersion snapshots the definition, not the term itself."""
    from application.artifact_version_service import ArtifactVersionService
    from persistence.models import GlossaryTerm, GlossaryTermVersion

    tenant, workspace, user = env
    term = GlossaryTerm.objects.create(
        tenant=tenant,
        workspace=workspace,
        term="Widget",
        definition="v2",
        artifact=_artifact(tenant, workspace, "GlossaryTerm"),
    )
    GlossaryTermVersion.objects.create(
        tenant=tenant, term_fk=term, term_version=1, definition="v1"
    )

    _migrate_history()

    payload = ArtifactVersionService().get_payload(
        term.artifact_id, 1, _ctx(tenant, workspace, user)
    )
    assert payload == {
        "term": "Widget",
        "definition": "v1",
        "synonyms": [],
        "abbreviation": "",
    }


def _ctx(tenant, workspace, user):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
