"""``QualityAssessment`` (WP B5-T1, #378): append-only contract + tenant RLS.

Three properties are pinned here, all of them load-bearing for the advisory
quality feature:

* **Append-only.** One verdict is *evidence* about one artifact content at one
  point in time. Re-assessing must add a row, never rewrite one — otherwise the
  history the feature exists for is silently editable. Both the row-level
  ``save()`` and the queryset ``update()``/``delete()`` paths must refuse.
* **Tenant isolation.** The table is a ``TenantScopedModel``, so it must be
  filtered by the ORM manager **and** by PostgreSQL Row-Level Security. The
  RLS half is asserted as the least-privilege application role (``SET ROLE``),
  because the pytest session itself connects as a superuser and would bypass
  every policy — the pattern used by ``test_rls_plain_child_models.py``.
* **Score range.** ``score`` is the ``0.0``–``1.0`` scale the prompt contract
  promises to the UI (which renders percent); a verdict outside it is a
  provider bug that must not reach the database.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from persistence.db_roles import APP_DB_ROLE
from persistence.models import AppendOnlyViolation, QualityAssessment
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


def _assessment(tenant, workspace, **overrides) -> QualityAssessment:
    """Complete, unsaved assessment — only the field under test varies."""
    data = {
        "tenant": tenant,
        "workspace": workspace,
        "entity_type": "Requirement",
        "entity_id": uuid.uuid4(),
        "score": 0.42,
        "reasoning": "reason",
        "suggestions": ["tighten the wording"],
        "criteria": {"atomic": 0.9},
        "content_hash": "a" * 64,
        "prompt_slot": "quality_requirement",
        "prompt_scope": QualityAssessment.PromptScope.WORKSPACE,
        "provider": "mock",
        "model": "mock",
        "trigger": QualityAssessment.Trigger.MANUAL,
        "triggered_by": "tester",
        "status": QualityAssessment.Status.OK,
    }
    data.update(overrides)
    return QualityAssessment(**data)


def _create_assessment(tenant, workspace, **overrides) -> QualityAssessment:
    """Persist the way a real write path does: inside the tenant context."""
    row = _assessment(tenant, workspace, **overrides)
    with active_tenant(tenant):
        row.save()
    return row


# ---------------------------------------------------------------------------
# Append-only
# ---------------------------------------------------------------------------


def test_second_save_is_rejected(tenant_a, workspace_a):
    """A persisted assessment cannot be rewritten — not in place, not by PK."""
    row = _create_assessment(tenant_a, workspace_a)

    row.reasoning = "edited"
    with pytest.raises(AppendOnlyViolation):
        row.save()

    # Same PK from a fresh instance must fail too; the tenant-scoped probe needs
    # a context, exactly like a real write path.
    clone = _assessment(tenant_a, workspace_a)
    clone.pk = row.pk
    with active_tenant(tenant_a):
        with pytest.raises(AppendOnlyViolation):
            clone.save()

    stored = QualityAssessment.unscoped.get(pk=row.pk)
    assert stored.reasoning == "reason"
    assert stored.score == 0.42


def test_save_rejects_workspace_of_other_tenant(tenant_a, workspace_b):
    """A row stamped for tenant A may not point at tenant B's workspace."""
    row = _assessment(tenant_a, workspace_b)
    with active_tenant(tenant_a):
        with pytest.raises(ValidationError) as excinfo:
            row.save()

    assert "workspace" in excinfo.value.message_dict
    assert not QualityAssessment.unscoped.filter(pk=row.pk).exists()


def test_save_rejects_artifact_of_other_tenant(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """Same for the optional ``artifact`` FK (SET_NULL does not relax this)."""
    from persistence.models import Artifact

    with active_tenant(tenant_b):
        artifact_b = Artifact.objects.create(
            tenant=tenant_b, workspace=workspace_b, artifact_type="Requirement"
        )
    row = _assessment(tenant_a, workspace_a, artifact=artifact_b)

    with active_tenant(tenant_a):
        with pytest.raises(ValidationError) as excinfo:
            row.save()

    assert "artifact" in excinfo.value.message_dict
    assert not QualityAssessment.unscoped.filter(pk=row.pk).exists()


def test_queryset_refuses_update_and_delete(tenant_a, workspace_a):
    """The bulk paths cannot bypass the row-level guard."""
    row = _create_assessment(tenant_a, workspace_a)

    with active_tenant(tenant_a):
        with pytest.raises(AppendOnlyViolation):
            QualityAssessment.objects.filter(pk=row.pk).update(score=0.1)
        with pytest.raises(AppendOnlyViolation):
            QualityAssessment.objects.all().delete()

    assert QualityAssessment.unscoped.get(pk=row.pk).score == 0.42


def test_workspace_cascade_still_deletes_rows(tenant_a, workspace_a):
    """Blocking ``delete()`` must not block the FK cascade: deleting the
    workspace is a data-lifecycle event, and Django's collector uses the
    non-tenant ``_base_manager`` rather than this queryset."""
    from persistence.models import Workspace

    row = _create_assessment(tenant_a, workspace_a)
    Workspace.unscoped.get(pk=workspace_a.pk).delete()
    assert not QualityAssessment.unscoped.filter(pk=row.pk).exists()


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("out_of_range", [-0.01, 1.01, 2.0])
def test_score_validator_rejects_out_of_range(tenant_a, workspace_a, out_of_range):
    """``full_clean`` is the enforcement point (``create`` does not validate)."""
    with active_tenant(tenant_a):
        with pytest.raises(ValidationError) as excinfo:
            _assessment(tenant_a, workspace_a, score=out_of_range).full_clean()
    assert "score" in excinfo.value.message_dict


@pytest.mark.parametrize("in_range", [0.0, 0.5, 1.0])
def test_score_validator_accepts_the_scale(tenant_a, workspace_a, in_range):
    with active_tenant(tenant_a):
        _assessment(tenant_a, workspace_a, score=in_range).full_clean()


@pytest.mark.parametrize("out_of_range", [-0.01, 1.01])
def test_score_check_constraint_rejects_out_of_range(tenant_a, workspace_a, out_of_range):
    """``objects.create`` never runs ``full_clean`` — only the CHECK stands."""
    with active_tenant(tenant_a):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                QualityAssessment.objects.create(
                    tenant=tenant_a, workspace=workspace_a, score=out_of_range,
                    entity_type="Requirement", entity_id=uuid.uuid4(),
                    content_hash="c" * 64, prompt_slot="quality_requirement",
                    prompt_scope="workspace", provider="mock", model="mock",
                    trigger="manual", triggered_by="tester", status="ok",
                )


def test_entity_type_outside_choices_still_persists(tenant_a, workspace_a):
    """The loose column is deliberate: a new type needs no migration."""
    row = _create_assessment(tenant_a, workspace_a, entity_type="StakeholderNeed")

    assert QualityAssessment.unscoped.get(pk=row.pk).entity_type == "StakeholderNeed"


# ---------------------------------------------------------------------------
# RLS tenant isolation
# ---------------------------------------------------------------------------


def _visible_ids(sql: str, params=None) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return {str(row[0]) for row in cursor.fetchall()}


@_pg_only
def test_rls_hides_a_foreign_tenants_assessment(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """As the app role: tenant B sees its own row and zero rows of tenant A."""
    row_a = _create_assessment(tenant_a, workspace_a)
    row_b = _create_assessment(tenant_b, workspace_b)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            unarmed = _visible_ids("SELECT id FROM pl_quality_assessment")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            seen_by_a = _visible_ids("SELECT id FROM pl_quality_assessment")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            seen_by_b = _visible_ids("SELECT id FROM pl_quality_assessment")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert unarmed == set(), (
        "the policy is not fail-closed: rows were visible with "
        "app.current_tenant unset"
    )
    assert seen_by_a == {str(row_a.id)}
    assert seen_by_b == {str(row_b.id)}, (
        "tenant B's armed context must expose exactly B's assessment and hide "
        "tenant A's — a leak here is a cross-tenant read"
    )


@_pg_only
def test_rls_rejects_a_foreign_tenant_write(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """WITH CHECK half: tenant A may not insert a row stamped for tenant B."""
    with pytest.raises(Exception) as excinfo:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                cursor.execute(
                    "INSERT INTO pl_quality_assessment "
                    "(id, created_at, modified_at, version, tenant_id, workspace_id, "
                    " entity_type, entity_id, score, reasoning, suggestions, criteria, "
                    " content_hash, prompt_slot, prompt_scope, provider, model, "
                    " trigger, triggered_by, status, error_code) "
                    "VALUES (%s, now(), now(), 1, %s, %s, %s, %s, %s, %s, '[]', '{}', "
                    " %s, %s, %s, %s, %s, %s, %s, %s, '')",
                    [
                        str(uuid.uuid4()),
                        str(tenant_b.id),
                        str(workspace_b.id),
                        "Requirement",
                        str(uuid.uuid4()),
                        0.5,
                        "leak",
                        "b" * 64,
                        "quality_requirement",
                        "workspace",
                        "mock",
                        "mock",
                        "manual",
                        "tester",
                        "ok",
                    ],
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
                cursor.execute("RESET ROLE")

    assert "row-level security" in str(excinfo.value).lower(), (
        "writing a row for another tenant was not rejected by the policy: "
        f"{excinfo.value}"
    )
