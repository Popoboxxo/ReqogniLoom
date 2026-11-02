"""``WorkItem`` (Plan F F3-T1, #1374): artifact contract, UID, soft-delete, RLS.

The model is the state-bearing work node inside a ``Document`` (concept §9), not
a second document type. Five properties are load-bearing and pinned here:

* **Identity.** Every work item owns a backing ``Artifact`` row and a local
  readable ``uid`` in the ``WI-NNN`` format, unique per workspace and never
  recycled (G1.1/G1.3).
* **Document binding.** ``document`` is mandatory (concept E11/O7) and
  ``PROTECT``ed: a hard delete of a document with items fails instead of
  silently discarding the work state.
* **Soft-delete is not a column.** ``WorkItem`` must not grow its own status or
  item-state field; the single flag remains ``Artifact.lifecycle_status``
  (Plan G G1.5 V1) and the workflow state lives in ``WorkflowItemState``.
* **Constraints.** ``kind`` and the 0-100 ``progress`` contract are mirrored by
  DB check constraints, and the per-workspace uid index rejects duplicates while
  allowing the same uid in another workspace.
* **RLS.** The table is FORCE ROW LEVEL SECURITY; this test asserts isolation as
  the least-privilege application role (``SET ROLE``), because the pytest
  session itself connects as a superuser and would bypass every policy — the
  pattern used by ``test_document_model.py``/``test_quality_assessment_model.py``.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from persistence.db_roles import APP_DB_ROLE
from persistence.models import Artifact, Document, WorkItem, Workspace
from persistence.tests.conftest import active_tenant
from workflow.services import outdated_item_ids

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _document(tenant, workspace, **overrides) -> Document:
    """Persist a document the way a create service will: inside the tenant."""
    data = {
        "tenant": tenant,
        "title": "Plan F F3",
        "kind": Document.Kind.PLAN,
    }
    data.update(overrides)
    with active_tenant(tenant):
        if "artifact" not in data:
            data["artifact"] = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Document"
            )
        return Document.objects.create(**data)


def _work_item(tenant, workspace, document=None, **overrides) -> WorkItem:
    """Persist a work item the way a create service will: inside the tenant."""
    document = document or _document(tenant, workspace)
    data = {
        "tenant": tenant,
        "document": document,
        "kind": WorkItem.Kind.PHASE,
        "ordinal": 1,
        "title": "Phase 1 — model",
        "body": "## Phase 1\n\nModel work.",
        "progress": 40,
    }
    data.update(overrides)
    with active_tenant(tenant):
        if "artifact" not in data:
            data["artifact"] = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="WorkItem"
            )
        return WorkItem.objects.create(**data)


# ---------------------------------------------------------------------------
# Identity and uid
# ---------------------------------------------------------------------------


def test_create_assigns_uid_and_workspace(tenant_a, workspace_a):
    """ORM create gets ``WI-001`` and the workspace from artifact.workspace_id."""
    document = _document(tenant_a, workspace_a)
    with active_tenant(tenant_a):
        artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="WorkItem"
        )
        item = WorkItem.objects.create(
            tenant=tenant_a,
            artifact=artifact,
            document=document,
            kind=WorkItem.Kind.STEP,
            ordinal=2,
            title="Step 1.1 — write the model",
        )

    assert item.uid == "WI-001"
    assert item.workspace_id == workspace_a.id
    assert item.version == 1
    assert item.artifact_id == artifact.id
    assert item.document_id == document.id


def test_uid_is_per_workspace_and_non_recycling(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """Each workspace starts at 001; deleting the row does not free the number."""
    first_a = _work_item(tenant_a, workspace_a)
    first_b = _work_item(tenant_b, workspace_b)
    assert first_a.uid == "WI-001"
    assert first_b.uid == "WI-001"

    WorkItem.unscoped.get(pk=first_a.pk).delete()
    second_a = _work_item(tenant_a, workspace_a)
    assert second_a.uid == "WI-002"


def test_uid_unique_constraint_rejects_duplicate(tenant_a, workspace_a):
    """``uq_work_item_workspace_uid`` is partial and workspace-scoped."""
    _work_item(tenant_a, workspace_a, uid="WI-500")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _work_item(tenant_a, workspace_a, uid="WI-500")


def test_same_uid_in_another_workspace_is_allowed(tenant_a, workspace_a):
    with active_tenant(tenant_a):
        other = Workspace.objects.create(tenant=tenant_a, name="WS-Other")

    _work_item(tenant_a, workspace_a, uid="WI-501")
    _work_item(tenant_a, other, uid="WI-501")

    assert WorkItem.unscoped.filter(uid="WI-501").count() == 2


# ---------------------------------------------------------------------------
# Document binding
# ---------------------------------------------------------------------------


def test_document_is_mandatory(tenant_a, workspace_a):
    """Concept E11/O7: a work item without a document is not a valid row."""
    with active_tenant(tenant_a):
        artifact = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="WorkItem"
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                WorkItem.objects.create(
                    tenant=tenant_a,
                    artifact=artifact,
                    kind=WorkItem.Kind.STEP,
                    title="Orphan step",
                )


def test_document_protect_blocks_hard_deletion(tenant_a, workspace_a):
    """PROTECT: a hard delete of a document with work state fails loudly."""
    item = _work_item(tenant_a, workspace_a)

    with pytest.raises(ProtectedError):
        Document.unscoped.get(pk=item.document_id).delete()

    assert WorkItem.unscoped.filter(pk=item.pk).exists()


# ---------------------------------------------------------------------------
# Schema constraints
# ---------------------------------------------------------------------------


def test_kind_check_constraint(tenant_a, workspace_a):
    """The DB mirrors the kind choices, not only the Python enum."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _work_item(tenant_a, workspace_a, kind="Bogus")


def test_progress_range_check_constraint(tenant_a, workspace_a):
    """0-100 is a DB contract; NULL stays allowed for items without progress."""
    _work_item(tenant_a, workspace_a, progress=0)
    _work_item(tenant_a, workspace_a, progress=100)
    _work_item(tenant_a, workspace_a, progress=None)

    for invalid in (-1, 101):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _work_item(tenant_a, workspace_a, progress=invalid)


def test_artifact_cascade_deletes_work_item(tenant_a, workspace_a):
    item = _work_item(tenant_a, workspace_a)
    Artifact.unscoped.get(pk=item.artifact_id).delete()

    assert not WorkItem.unscoped.filter(pk=item.pk).exists()


def test_no_state_field_and_soft_delete_lives_on_the_artifact(
    tenant_a, workspace_a
):
    """Plan G G1.5 V1 + REQ-143: no status/item_state column on the model."""
    names = {field.name for field in WorkItem._meta.get_fields()}
    assert "status" not in names
    assert "item_state" not in names
    assert "lifecycle_state" not in names

    item = _work_item(tenant_a, workspace_a)
    assert item.pk not in set(
        outdated_item_ids("WorkItem", tenant_id=tenant_a.id)
    )

    Artifact.unscoped.filter(pk=item.artifact_id).update(
        lifecycle_status="outdated"
    )
    assert item.pk in set(
        outdated_item_ids("WorkItem", tenant_id=tenant_a.id)
    )


# ---------------------------------------------------------------------------
# RLS tenant isolation
# ---------------------------------------------------------------------------


def _visible_ids(sql: str, params=None) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return {str(row[0]) for row in cursor.fetchall()}


@_pg_only
def test_rls_hides_a_foreign_tenants_work_item(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """As the app role: tenant B sees its own row and zero rows of tenant A."""
    item_a = _work_item(tenant_a, workspace_a)
    item_b = _work_item(tenant_b, workspace_b)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            unarmed = _visible_ids("SELECT id FROM pl_work_item")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            seen_by_a = _visible_ids("SELECT id FROM pl_work_item")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            seen_by_b = _visible_ids("SELECT id FROM pl_work_item")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert unarmed == set(), (
        "the policy is not fail-closed: rows were visible with "
        "app.current_tenant unset"
    )
    assert seen_by_a == {str(item_a.id)}
    assert seen_by_b == {str(item_b.id)}, (
        "tenant B's armed context must expose exactly B's work item and hide "
        "tenant A's — a leak here is a cross-tenant read"
    )


@_pg_only
def test_rls_rejects_a_foreign_tenant_write(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """WITH CHECK half: tenant A may not insert a row stamped for tenant B."""
    document_b = _document(tenant_b, workspace_b)
    with active_tenant(tenant_b):
        artifact_b = Artifact.objects.create(
            tenant=tenant_b, workspace=workspace_b, artifact_type="WorkItem"
        )

    with pytest.raises(Exception) as excinfo:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                cursor.execute(
                    "INSERT INTO pl_work_item "
                    "(id, created_at, modified_at, version, tenant_id, "
                    " workspace_id, document_id, artifact_id, uid, kind, "
                    " ordinal, title, body, progress, blocked_reason, "
                    " next_action, last_actor, evidence_ref, approved_by, "
                    " exit_criteria) "
                    "VALUES (%s, now(), now(), 1, %s, %s, %s, %s, 'WI-999', "
                    " 'Step', 1, 'Foreign', '', NULL, '', '', '', '', '', '')",
                    [
                        str(uuid.uuid4()),
                        str(tenant_b.id),
                        str(workspace_b.id),
                        str(document_b.id),
                        str(artifact_b.id),
                    ],
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
                cursor.execute("RESET ROLE")

    assert "row-level security" in str(excinfo.value).lower()
