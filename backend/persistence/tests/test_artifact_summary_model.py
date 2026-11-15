"""``ArtifactSummary`` (issue #1793 / S4): one row per scope, RLS, upsert.

What is pinned here, and why it is load-bearing:

* **Upsert, not history (E5).** The table is *state*: a second write for the
  same scope must change the row, never add one. Both partial unique
  constraints are the DB-level guarantee behind that, so the test inserts
  around the helper too.
* **Two scopes coexist.** ``artifact`` and ``type_roster`` rows of the same
  workspace are different scopes and must not collide; ``artifact IS NULL`` on
  roster rows is exactly the Postgres NULL-is-distinct case the partial
  constraints rely on.
* **Degradation is data, not an error.** A degraded run records the closed
  E11 reason and keeps ``generated_at`` pointing at the last successful text.
* **Tenant isolation.** Enforced twice: by the model guard (cross-tenant FK is
  rejected) and by PostgreSQL RLS, asserted as the least-privilege app role
  (the pytest session connects as superuser and would bypass every policy).
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from application.summary_support import (
    ARTIFACT_KIND,
    TYPE_ROSTER_KIND,
    scope_lookup,
    upsert_summary,
)
from persistence.db_roles import APP_DB_ROLE
from persistence.models import Artifact, ArtifactSummary, Workspace
from persistence.tests.conftest import active_tenant

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="PostgreSQL-only assertion")


@pytest.fixture
def artifact_a(tenant_a, workspace_a) -> Artifact:
    with active_tenant(tenant_a):
        return Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
        )


def _values(**overrides):
    """Complete write payload — only the field under test varies."""
    data = {
        "text": "first summary",
        "content_hash": "a" * 64,
        "input_digest": {"item_count": 3, "latest_updated_at": "2026-11-15T00:00:00Z"},
        "prompt_slot": "artifact_type_summary",
        "prompt_scope": ArtifactSummary.PromptScope.WORKSPACE,
        "prompt_version": 1,
        "provider": "mock",
        "model": "mock",
        "token_usage": 42,
        "trigger": ArtifactSummary.Trigger.PERIODIC,
        "status": ArtifactSummary.Status.OK,
        "reason": "",
    }
    data.update(overrides)
    return data


def _upsert_roster(tenant, workspace, artifact_type="Requirement", **overrides):
    with active_tenant(tenant):
        return upsert_summary(
            workspace=workspace,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=artifact_type,
            values=_values(**overrides),
        )


# ---------------------------------------------------------------------------
# Upsert semantics (E5)
# ---------------------------------------------------------------------------


def test_second_upsert_overwrites_the_row(tenant_a, workspace_a):
    """One scope keeps exactly one row; the second write updates it in place."""
    first = _upsert_roster(tenant_a, workspace_a, text="first summary")
    second = _upsert_roster(tenant_a, workspace_a, text="second summary")

    assert first.pk == second.pk
    assert ArtifactSummary.unscoped.filter(workspace=workspace_a).count() == 1
    stored = ArtifactSummary.unscoped.get(pk=first.pk)
    assert stored.text == "second summary"
    assert stored.modified_at >= stored.created_at


def test_artifact_and_type_scopes_coexist(tenant_a, workspace_a, artifact_a):
    """The two partial constraints address different columns, so no collision."""
    roster = _upsert_roster(tenant_a, workspace_a)
    with active_tenant(tenant_a):
        artifact_row = upsert_summary(
            workspace=workspace_a,
            summary_kind=ARTIFACT_KIND,
            artifact=artifact_a,
            values=_values(text="one artifact"),
        )

    assert roster.pk != artifact_row.pk
    assert ArtifactSummary.unscoped.filter(workspace=workspace_a).count() == 2


def test_two_type_scopes_coexist(tenant_a, workspace_a):
    """Different artifact types are different scopes."""
    _upsert_roster(tenant_a, workspace_a, artifact_type="Requirement")
    _upsert_roster(tenant_a, workspace_a, artifact_type="TestCase")

    assert ArtifactSummary.unscoped.filter(workspace=workspace_a).count() == 2


def test_two_artifact_scopes_coexist(tenant_a, workspace_a, artifact_a):
    """Two artifacts of one workspace are two scopes."""
    with active_tenant(tenant_a):
        other = Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="TestCase"
        )
        for artifact in (artifact_a, other):
            upsert_summary(
                workspace=workspace_a,
                summary_kind=ARTIFACT_KIND,
                artifact=artifact,
                values=_values(),
            )

    assert ArtifactSummary.unscoped.filter(workspace=workspace_a).count() == 2


def test_null_artifact_rows_do_not_collide(tenant_a, workspace_a):
    """``artifact IS NULL`` is distinct in Postgres — the roster rows rely on it.

    A roster row and a second roster row of another type both carry
    ``artifact = NULL``; they must not trip the artifact-scope constraint.
    """
    first = _upsert_roster(tenant_a, workspace_a, artifact_type="Requirement")
    second = _upsert_roster(tenant_a, workspace_a, artifact_type="Risk")

    assert first.artifact_id is None and second.artifact_id is None
    assert ArtifactSummary.unscoped.filter(
        workspace=workspace_a, artifact__isnull=True
    ).count() == 2


# ---------------------------------------------------------------------------
# Unique constraints
# ---------------------------------------------------------------------------


def _raw_create(tenant, workspace, *, summary_kind, artifact=None, artifact_type=""):
    with active_tenant(tenant), transaction.atomic():
        ArtifactSummary.objects.create(
            tenant=tenant,
            workspace=workspace,
            summary_kind=summary_kind,
            artifact=artifact,
            artifact_type=artifact_type,
            text="raw",
            content_hash="b" * 64,
        )


def test_type_scope_constraint_rejects_a_duplicate(tenant_a, workspace_a):
    _raw_create(tenant_a, workspace_a, summary_kind=TYPE_ROSTER_KIND,
                artifact_type="Requirement")

    with pytest.raises(IntegrityError):
        _raw_create(tenant_a, workspace_a, summary_kind=TYPE_ROSTER_KIND,
                    artifact_type="Requirement")


def test_artifact_scope_constraint_rejects_a_duplicate(
    tenant_a, workspace_a, artifact_a
):
    _raw_create(tenant_a, workspace_a, summary_kind=ARTIFACT_KIND,
                artifact=artifact_a)

    with pytest.raises(IntegrityError):
        _raw_create(tenant_a, workspace_a, summary_kind=ARTIFACT_KIND,
                    artifact=artifact_a)


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


def test_degraded_reason_is_persisted(tenant_a, workspace_a):
    """A degraded run keeps the closed E11 reason; no free text, no success time."""
    row = _upsert_roster(
        tenant_a,
        workspace_a,
        status=ArtifactSummary.Status.SKIPPED,
        reason=ArtifactSummary.Reason.BUDGET_EXHAUSTED,
        text="",
        provider="",
        model="",
    )

    stored = ArtifactSummary.unscoped.get(pk=row.pk)
    assert stored.status == "skipped"
    assert stored.reason == "budget_exhausted"
    assert stored.generated_at is None


@pytest.mark.parametrize(
    "reason",
    ["", "budget_exhausted", "provider_unavailable", "stale", "disabled"],
)
def test_reason_check_constraint_accepts_the_closed_enum(
    tenant_a, workspace_a, reason
):
    """The CHECK mirrors the E11 enum; ``""`` is the ``ok`` value."""
    with active_tenant(tenant_a):
        ArtifactSummary.objects.create(
            tenant=tenant_a,
            workspace=workspace_a,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type=f"Requirement-{reason or 'ok'}",
            text="summary",
            content_hash="c" * 64,
            reason=reason,
        )


def test_reason_check_constraint_rejects_free_text(tenant_a, workspace_a):
    """CWE-209: the degradation column cannot become a provider error dump."""
    with pytest.raises(IntegrityError), active_tenant(tenant_a), transaction.atomic():
        ArtifactSummary.objects.create(
            tenant=tenant_a,
            workspace=workspace_a,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type="TestCase",
            text="leak",
            content_hash="d" * 64,
            reason="Traceback: connection refused",
        )


# ---------------------------------------------------------------------------
# Helper contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "artifact", "artifact_type"),
    [
        (ARTIFACT_KIND, None, ""),
        (TYPE_ROSTER_KIND, None, ""),
        ("unknown", None, ""),
    ],
)
def test_scope_lookup_rejects_incomplete_scopes(kind, artifact, artifact_type):
    with pytest.raises(ValueError):
        scope_lookup(None, kind, artifact=artifact, artifact_type=artifact_type)


def test_upsert_strips_a_caller_supplied_tenant(tenant_a, workspace_a):
    """The tenant always follows the workspace, never the payload."""
    other = uuid.uuid4()
    with active_tenant(tenant_a):
        row = upsert_summary(
            workspace=workspace_a,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type="Requirement",
            values=_values(tenant=other),
        )

    assert row.tenant_id == tenant_a.id


def test_save_rejects_a_workspace_of_another_tenant(tenant_a, tenant_b, workspace_b):
    with active_tenant(tenant_a), pytest.raises(ValidationError) as excinfo:
        ArtifactSummary.objects.create(
            tenant=tenant_a,
            workspace=workspace_b,
            summary_kind=TYPE_ROSTER_KIND,
            artifact_type="Requirement",
            text="cross-tenant",
            content_hash="e" * 64,
        )

    assert "workspace" in excinfo.value.message_dict


def test_workspace_cascade_deletes_rows(tenant_a, workspace_a):
    row = _upsert_roster(tenant_a, workspace_a)
    Workspace.unscoped.get(pk=workspace_a.pk).delete()

    assert not ArtifactSummary.unscoped.filter(pk=row.pk).exists()


# ---------------------------------------------------------------------------
# RLS tenant isolation
# ---------------------------------------------------------------------------


def _visible_ids(sql: str, params=None) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return {str(row[0]) for row in cursor.fetchall()}


@_pg_only
def test_rls_hides_a_foreign_tenants_summary(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """As the app role: each armed tenant sees exactly its own row."""
    row_a = _upsert_roster(tenant_a, workspace_a)
    row_b = _upsert_roster(tenant_b, workspace_b)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')

            unarmed = _visible_ids("SELECT id FROM pl_artifact_summary")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
            seen_by_a = _visible_ids("SELECT id FROM pl_artifact_summary")

            cursor.execute("SET app.current_tenant = %s", [str(tenant_b.id)])
            seen_by_b = _visible_ids("SELECT id FROM pl_artifact_summary")
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET app.current_tenant")
            cursor.execute("RESET ROLE")

    assert unarmed == set(), (
        "the policy is not fail-closed: rows were visible with "
        "app.current_tenant unset"
    )
    assert seen_by_a == {str(row_a.id)}
    assert seen_by_b == {str(row_b.id)}


@_pg_only
def test_rls_rejects_a_foreign_tenant_write(
    tenant_a, tenant_b, workspace_a, workspace_b
):
    """WITH CHECK half: tenant A may not write a row stamped for tenant B."""
    with pytest.raises(Exception) as excinfo:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
                cursor.execute("SET app.current_tenant = %s", [str(tenant_a.id)])
                cursor.execute(
                    "INSERT INTO pl_artifact_summary "
                    "(id, created_at, modified_at, version, tenant_id, workspace_id, "
                    " summary_kind, artifact_type, text, content_hash, input_digest, "
                    " prompt_slot, prompt_scope, provider, model, trigger, status, "
                    " reason) "
                    "VALUES (%s, now(), now(), 1, %s, %s, %s, %s, %s, %s, '{}', "
                    " '', '', '', '', '', '', '')",
                    [
                        str(uuid.uuid4()),
                        str(tenant_b.id),
                        str(workspace_b.id),
                        TYPE_ROSTER_KIND,
                        "Requirement",
                        "leak",
                        "f" * 64,
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
