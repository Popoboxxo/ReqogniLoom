"""Issue #1564: the step normalization migration and its dry-run report."""

from __future__ import annotations

import importlib
import uuid

import pytest

from application.test_steps import normalize_steps
from persistence.management.commands.normalize_testcase_steps import classify
from persistence.models import Artifact, Tenant, TestCase, Workspace

pytestmark = pytest.mark.django_db

migration = importlib.import_module(
    "persistence.migrations.0144_normalize_testcase_steps"
)

LEGACY = [{"step": "Open the page", "expected_result": "The page is visible"}]
TYPED = normalize_steps(LEGACY, testcase_id=str(uuid.uuid4()))


class _Editor:
    """Minimal schema_editor stub: the migration only needs the connection."""

    def __init__(self) -> None:
        from django.db import connection

        self.connection = connection


@pytest.fixture
def test_case() -> TestCase:
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        name="Steps Tenant", slug=f"steps-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="Steps WS", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="TestCase"
        )
        yield TestCase.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact=artifact,
            title="Login",
            steps=LEGACY,
        )
    finally:
        TenantContext.clear_tenant()


def test_the_migration_rewrites_a_legacy_row(test_case: TestCase) -> None:
    from django.apps import apps

    migration.forwards(apps, _Editor())

    test_case.refresh_from_db()
    assert [step["step_type"] for step in test_case.steps] == ["when", "then"]
    assert all(step["id"] for step in test_case.steps)


def test_the_migration_is_idempotent(test_case: TestCase) -> None:
    from django.apps import apps

    migration.forwards(apps, _Editor())
    test_case.refresh_from_db()
    once = list(test_case.steps)

    migration.forwards(apps, _Editor())

    test_case.refresh_from_db()
    assert test_case.steps == once


def test_the_migration_leaves_an_unknown_shape_untouched(test_case: TestCase) -> None:
    from django.apps import apps

    TestCase.objects.filter(id=test_case.id).update(steps=[{"foo": "bar"}])
    test_case.refresh_from_db()

    migration.forwards(apps, _Editor())

    test_case.refresh_from_db()
    assert test_case.steps == [{"foo": "bar"}]


def test_classify_distinguishes_the_four_shapes() -> None:
    assert classify([]) == "empty"
    assert classify(None) == "empty"
    assert classify(TYPED) == "typed"
    assert classify(LEGACY) == "legacy"
    assert classify([{"foo": "bar"}]) == "unknown"
    assert classify("not-a-list") == "unknown"


def test_classify_rejects_a_typed_step_without_text() -> None:
    assert classify([{"step_type": "given"}]) == "unknown"
