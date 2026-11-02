"""``Document`` (Plan F F2-T1, #1374): artifact contract, UID, soft-delete, RLS.

The model is the document artifact itself, not the read-only ``DocumentView``
projection. Four properties are load-bearing and pinned here:

* **Identity.** Every document owns a backing ``Artifact`` row and a local
  readable ``uid`` in the ``DOC-NNN`` format, unique per workspace and never
  recycled (G1.1/G1.3).
* **Soft-delete is not a column.** ``Document`` must not grow its own status
  field; the single flag remains ``Artifact.lifecycle_status`` (Plan G G1.5 V1).
* **Constraints.** ``kind`` is mirrored by a DB check constraint, and the
  per-workspace uid index rejects duplicates while allowing the same uid in
  another workspace.
* **RLS.** The table is FORCE ROW LEVEL SECURITY; this test asserts isolation as
  the least-privilege application role (``SET ROLE``), because the pytest
  session itself connects as a superuser and would bypass every policy — the
  pattern used by ``test_quality_assessment_model.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from persistence.db_roles import APP_DB_ROLE
from persistence.models import Artifact, Document, Workspace
from persistence.tests.conftest import active_tenant
from workflow.services import outdated_item_ids

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _artifact(tenant, workspace) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Document"
    )


def _document(tenant, workspace, **overrides) -> Document:
    """Persist a document the way a create service will: inside the tenant."""
    data = {
        "tenant": tenant,
        "title": "Document artifact design",
        "kind": Document.Kind.CONCEPT,
        "description": "Design record for the document artifact.",
        "body": "# Design\n\nA document is an artifact.",
    }
    data.update(overrides)
    with active_tenant(tenant):
        if "artifact" not in data:
            data["artifact"] = _artifact(tenant, workspace)
        return Document.objects.create(**data)


# ---------------------------------------------------------------------------
# Identity and uid
# ---------------------------------------------------------------------------


def test_create_assigns_uid_and_workspace(tenant_a, workspace_a):
    """ORM create gets ``DOC-001`` and the workspace from artifact.workspace_id."""
    with active_tenant(tenant_a):
        artifact = _artifact(tenant_a, workspace_a)
        document = Document.objects.create(
            tenant=tenant_a,
            artifact=artifact,
            title="Document artifact design",
            kind=Document.Kind.CONCEPT,
        )

    assert document.uid == "DOC-001"
    assert document.workspace_id == workspace_a.id
    assert document.version == 1
    assert document.artifact_id == artifact.id


def test_uid_is_per_workspace_and_non_recycling(tenant_a, tenant_b, workspace_a, workspace_b):
    """Each workspace starts at 001; deleting the row does not free the number."""
    first_a = _document(tenant_a, workspace_a)
    first_b = _document(tenant_b, workspace_b)
    assert first_a.uid == "DOC-001"
    assert first_b.uid == "DOC-001"

    Document.unscoped.get(pk=first_a.pk).delete()
    second_a = _document(tenant_a, workspace_a)
    assert second_a.uid == "DOC-002"


def test_uid_unique_constraint_rejects_duplicate(tenant_a, workspace_a):
    """``uq_document_workspace_uid`` is partial and workspace-scoped."""
    _document(tenant_a, workspace_a, uid="DOC-500")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _document(tenant_a, workspace_a, uid="DOC-500")


def test_same_uid_in_another_workspace_is_allowed(tenant_a, workspace_a):
    with active_tenant(tenant_a):
        other = Workspace.objects.create(tenant=tenant_a, name="WS-Other")

    _document(tenant_a, workspace_a, uid="DOC-501")
    _document(tenant_a, other, uid="DOC-501")

    assert Document.unscoped.filter(uid="DOC-501").count() == 2


# ---------------------------------------------------------------------------
# Schema constraints
# ---------------------------------------------------------------------------


def test_kind_check_constraint(tenant_a, workspace_a):
    """The DB mirrors the kind choices, not only the Python enum."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _document(tenant_a, workspace_a, kind="Bogus")


def test_artifact_cascade_deletes_document(tenant_a, workspace_a):
    document = _document(tenant_a, workspace_a)
    Artifact.unscoped.get(pk=document.artifact_id).delete()

    assert not Document.unscoped.filter(pk=document.pk).exists()


def test_no_status_field_and_soft_delete_lives_on_the_artifact(tenant_a, workspace_a):
    """Plan G G1.5 V1: the only soft-delete flag is Artifact.lifecycle_status."""
    names = {field.name for field in Document._meta.get_fields()}
    assert "status" not in names

    document = _document(tenant_a, workspace_a)
    assert document.pk not in set(
        outdated_item_ids("Document", tenant_id=tenant_a.id)
    )

    Artifact.unscoped.filter(pk=document.artifact_id).update(
        lifecycle_status="outdated"
    )
    assert document.pk in set(
        outdated_item_ids("Document", tenant_id=tenant_a.id)
    )


# ---------------------------------------------------------------------------
# RLS tenant isolation
# ---------------------------------------------------------------------------


def _visible_ids(sql: str, params=None) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return {str(row[0]) for row in cursor.fetchall()}


@_pg_only
def test_rls_hides_a_foreign_tenants_document(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """As the app role: tenant B sees its own row and zero rows of tenant A."""
    document_a = _document(tenant_a, workspace_a)
    document_b = _document(tenant_b, workspace_b)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            unarmed = _visible_ids("SELECT id FROM pl_document")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            seen_by_a = _visible_ids("SELECT id FROM pl_document")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            seen_by_b = _visible_ids("SELECT id FROM pl_document")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert unarmed == set(), (
        "the policy is not fail-closed: rows were visible with "
        "app.current_tenant unset"
    )
    assert seen_by_a == {str(document_a.id)}
    assert seen_by_b == {str(document_b.id)}, (
        "tenant B's armed context must expose exactly B's document and hide "
        "tenant A's — a leak here is a cross-tenant read"
    )


@_pg_only
def test_rls_rejects_a_foreign_tenant_write(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """WITH CHECK half: tenant A may not insert a row stamped for tenant B."""
    with active_tenant(tenant_b):
        artifact_b = Artifact.objects.create(
            tenant=tenant_b, workspace=workspace_b, artifact_type="Document"
        )

    with pytest.raises(Exception) as excinfo:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                cursor.execute(
                    "INSERT INTO pl_document "
                    "(id, created_at, modified_at, version, tenant_id, "
                    " workspace_id, uid, title, kind, description, body, "
                    " frozen_fields, artifact_id) "
                    "VALUES (%s, now(), now(), 1, %s, %s, 'DOC-999', 'Foreign', "
                    " 'Spec', '', '', '[]'::jsonb, %s)",
                    [
                        str(uuid.uuid4()),
                        str(tenant_b.id),
                        str(workspace_b.id),
                        str(artifact_b.id),
                    ],
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
                cursor.execute("RESET ROLE")

    assert "row-level security" in str(excinfo.value).lower()
