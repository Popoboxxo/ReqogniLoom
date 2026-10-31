"""F4.2 — BaselineTag model + facade semantics (real DB).

Plan F (2026-10-21), F4.2. Tags are *metadata*, not content: adding, changing or
removing one must never touch ``bl_baseline_snapshot`` (whose DB trigger raises
on every UPDATE), and the denormalised ``workspace_id`` on the tag row is
derived exclusively from ``baseline.workspace_id`` (QR-S09 a) — never from
request data.

Requirements:
- REQ-L2-BL-001 (baseline persistence), REQ-L2-BL-002 (immutability),
- REQ-L2-PL-010 (tenant isolation).
"""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext
from django.db import connection

from application.base import ValidationError
from application.baseline_facade import BaselineFacade, BaselineTagValidationError
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_EDITOR, UserRole
from baseline.models import BaselineSnapshot, BaselineTag
from baseline.services import purge_baseline
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _env(tier: str = "standard"):
    """Create tenant + workspace + editor + one direct baseline snapshot."""
    slug = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"tag-{slug}", slug=f"tag-{slug}")
    user = User.objects.create(
        username=f"tag-{slug}", email=f"tag-{slug}@t.test", tenant=tenant
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"tag-ws-{slug}", preset={"name": tier}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
        baseline = BaselineSnapshot.unscoped.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope="project",
            name=f"tag-baseline-{slug}",
        )
    finally:
        clear_request_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_EDITOR,),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )
    return tenant, user, workspace, baseline, ctx


def _snapshot_updates(queries) -> list[str]:
    return [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith('UPDATE "BL_BASELINE_SNAPSHOT"')
    ]


def test_set_tags_does_not_update_the_baseline_snapshot() -> None:
    """Tags live in their own table; the immutable snapshot is never UPDATEd."""
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    with CaptureQueriesContext(connection) as captured:
        labels = facade.set_tags(baseline.id, ["Release", "RC1"], ctx)

    assert labels == ["RC1", "Release"]
    assert _snapshot_updates(captured.captured_queries) == []
    assert set(
        BaselineTag.unscoped.filter(baseline_id=baseline.id).values_list(
            "label", flat=True
        )
    ) == {"Release", "RC1"}


def test_set_tags_serialises_on_the_snapshot_row() -> None:
    """B1 (CWE-362): the replace path locks the baseline row it replaces.

    PUT has *replace* semantics, so the read that drives DELETE+INSERT must be
    serialised per baseline; otherwise two concurrent PUTs could commit the
    union of both label sets. The lock is a ``SELECT ... FOR UPDATE`` on
    ``bl_baseline_snapshot`` — and that statement must not be an ``UPDATE``,
    because the immutability trigger is declared ``BEFORE UPDATE OR DELETE``.
    """
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    with CaptureQueriesContext(connection) as captured:
        facade.set_tags(baseline.id, ["Release"], ctx)

    statements = [query["sql"] for query in captured.captured_queries]
    lock_statements = [
        sql
        for sql in statements
        if "FOR UPDATE" in sql.upper() and '"bl_baseline_snapshot"' in sql
    ]

    assert lock_statements, statements
    assert lock_statements[0].lstrip().upper().startswith("SELECT"), lock_statements[0]
    # The lock must not be an UPDATE: the trigger fires on UPDATE/DELETE only,
    # so a row lock keeps the append-only guarantee intact.
    assert _snapshot_updates(captured.captured_queries) == []


def test_tag_workspace_derived_from_baseline() -> None:
    """The tag's workspace_id is a copy of the baseline's, never caller input."""
    _, _, workspace, baseline, ctx = _env()

    BaselineFacade().set_tags(baseline.id, ["Release"], ctx)

    tag = BaselineTag.unscoped.get(baseline_id=baseline.id)
    assert tag.workspace_id == workspace.id
    # The facade signature has no workspace parameter at all — a request cannot
    # even express a conflicting value.
    with pytest.raises(TypeError):
        BaselineFacade().set_tags(  # type: ignore[call-arg]
            baseline.id, ["RC1"], ctx, workspace_id=str(uuid.uuid4())
        )


def test_replace_set_is_case_insensitive_and_sorted() -> None:
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    facade.set_tags(baseline.id, ["release", "Release", "RC1"], ctx)
    assert facade.set_tags(baseline.id, ["alpha"], ctx) == ["alpha"]

    remaining = list(
        BaselineTag.unscoped.filter(baseline_id=baseline.id).values_list(
            "label", flat=True
        )
    )
    assert remaining == ["alpha"]


def test_unique_constraint_is_case_insensitive() -> None:
    tenant, _, workspace, baseline, _ = _env()
    BaselineTag.unscoped.create(
        tenant=tenant,
        baseline=baseline,
        workspace_id=workspace.id,
        label="Release",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        BaselineTag.unscoped.create(
            tenant=tenant,
            baseline=baseline,
            workspace_id=workspace.id,
            label="release",
        )


def test_validation_rejects_bad_labels() -> None:
    _, _, _, baseline, ctx = _env()
    facade = BaselineFacade()

    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, ["bad\nlabel"], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, [""], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, ["x" * 65], ctx)
    with pytest.raises(ValidationError):
        facade.set_tags(baseline.id, [f"tag-{i}" for i in range(21)], ctx)


def test_admin_purge_removes_tags_via_cascade() -> None:
    tenant, _, _, baseline, ctx = _env()
    BaselineFacade().set_tags(baseline.id, ["Release"], ctx)
    assert BaselineTag.unscoped.filter(baseline_id=baseline.id).count() == 1

    purge_baseline(baseline.id, tenant.id)

    assert BaselineTag.unscoped.filter(baseline_id=baseline.id).count() == 0


def test_tag_label_collision_maps_to_validation_error() -> None:
    """B3: the DB's ``Lower("label")`` uniqueness must never surface as a 500.

    ``_normalise_tags`` de-duplicates with ``str.casefold()``; the constraint
    compares with ``lower()``. The two disagree for some code points and
    ``lower()`` is collation dependent, so a pair that survives normalisation
    can still violate the constraint at INSERT time. That must be a 400-shaped
    ``BaselineTagValidationError``, not an uncaught ``IntegrityError``.
    """
    tenant, _, workspace, baseline, _ = _env()

    with pytest.raises(BaselineTagValidationError) as excinfo:
        # Bypasses ``_normalise_tags`` on purpose: this is exactly the pair the
        # DB rejects while casefold-based de-duplication may let it through.
        BaselineFacade._replace_tags(
            baseline_id=baseline.id,
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            labels=["Release", "release"],
        )

    assert excinfo.value.details
    assert {entry["label"] for entry in excinfo.value.details} == {
        "Release",
        "release",
    }
    assert (
        BaselineTag.unscoped.filter(baseline_id=baseline.id).count() == 0
    ), "the failed insert must not leave a partial tag set behind"


def test_other_integrity_errors_are_not_swallowed() -> None:
    """B3: only the tag-label uniqueness violation is remapped to a 400.

    A NOT NULL violation is not a client input defect in the tag sense; turning
    it into ``BaselineTagValidationError`` would hide a real defect.
    """
    _, _, workspace, baseline, _ = _env()

    with pytest.raises(IntegrityError):
        BaselineFacade._replace_tags(
            baseline_id=baseline.id,
            tenant_id=None,  # type: ignore[arg-type]
            workspace_id=workspace.id,
            labels=["Release"],
        )

