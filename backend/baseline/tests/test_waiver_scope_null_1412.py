"""#1412 / C5-T2 — ``BaselineGateWaiver.scope_artifact_id``: NULL, never ``''``.

``""`` and ``NULL`` both meant "this waiver is not bound to one document", so
every report that counted the two states counted the same fact twice. The
column is ``null=True, default=None`` and migration
``0014_baseline_waiver_scope_artifact_null`` normalises the legacy empty strings
before it adds a ``CHECK`` constraint that forbids them from coming back.

What is pinned here:

* the constraint rejects ``''`` (the regression this wave exists to stop);
* ``NULL`` and a real document id are still accepted — the normalisation must
  not narrow the column's legitimate states;
* the migration's data step converts existing ``''`` rows and is idempotent on
  an already-clean table (running it twice is not an error — a redeploy may hit
  a database where the first pass already ran).

The migration body is invoked directly rather than by replaying the whole
migration graph: it *has* been applied to the test database, so the only way to
reproduce its pre-state is to drop the constraint for the duration of the test.
The test runs in a rolled-back transaction, so the DDL is undone afterwards
(PostgreSQL DDL is transactional).
"""
from __future__ import annotations

import importlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.db import IntegrityError, connection, transaction

from baseline.models import BaselineGateWaiver
from persistence.models import Tenant
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

_MIGRATION = "baseline.migrations.0014_baseline_waiver_scope_artifact_null"
_TABLE = "bl_baseline_gate_waiver"
_CONSTRAINT = "ck_baseline_waiver_scope_artifact_not_empty"
_CHECK_SQL = (
    f'ALTER TABLE "{_TABLE}" ADD CONSTRAINT "{_CONSTRAINT}" '
    'CHECK ("scope_artifact_id" IS NULL OR NOT ("scope_artifact_id" = \'\'))'
)

_REASON = "Accepted deviation for the beta cut, see review protocol 2026-11-08."


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="waiver-scope-1412", slug=f"waiver-scope-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def workspace(tenant: Tenant):
    with _active(tenant):
        return make_workspace(tenant, name="waiver-scope-1412-ws")


@contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


def _create(tenant: Tenant, workspace, **overrides) -> BaselineGateWaiver:
    """Persist one waiver row through the plain ORM (no write-path defaults).

    ``record_waiver`` normalises ``""`` to ``None`` before it saves, so it
    cannot produce the legacy row shape this module is about.
    """
    fields = {
        "tenant": tenant,
        "workspace_id": workspace.id,
        "rule_id": "TRACE-P1",
        "finding_key": f"TRACE-P1\x1f{uuid.uuid4()}",
        "artifact_ids": ["art-1"],
        "scope": "project",
        "scope_artifact_id": None,
        "reason": _REASON,
        "granted_by": "author-1",
    }
    fields.update(overrides)
    with _active(tenant):
        return BaselineGateWaiver.objects.create(**fields)


class _SchemaEditorStub:
    """Minimal ``schema_editor`` stand-in — the migration only calls ``execute``."""

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001 — Django's signature
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


class TestCheckConstraint:
    def test_empty_string_is_rejected(self, tenant: Tenant, workspace):
        with _active(tenant), pytest.raises(IntegrityError), transaction.atomic():
            _create(tenant, workspace, scope_artifact_id="")

    def test_null_is_allowed(self, tenant: Tenant, workspace):
        row = _create(tenant, workspace, scope_artifact_id=None)

        assert row.scope_artifact_id is None
        row.refresh_from_db()
        assert row.scope_artifact_id is None

    def test_a_real_document_id_is_allowed(self, tenant: Tenant, workspace):
        document_id = str(uuid.uuid4())

        row = _create(tenant, workspace, scope_artifact_id=document_id)

        assert row.scope_artifact_id == document_id


class TestMigrationDataStep:
    """The data step is a plain normalisation, and it must stay idempotent."""

    @contextmanager
    def _pre_0014_state(self) -> Iterator[None]:
        """Drop the constraint so a legacy ``''`` row can exist again.

        ``SET CONSTRAINTS ALL IMMEDIATE`` first: PostgreSQL refuses an
        ``ALTER TABLE`` while deferred constraint triggers queued by this
        transaction's writes are still pending ("pending trigger events").
        """
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute(f'ALTER TABLE "{_TABLE}" DROP CONSTRAINT "{_CONSTRAINT}"')
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                cursor.execute(_CHECK_SQL)

    def test_legacy_empty_strings_are_normalised_to_null(
        self, tenant: Tenant, workspace
    ):
        migration = importlib.import_module(_MIGRATION)

        # The constraint is dropped *before* the first write to this table:
        # PostgreSQL refuses ALTER TABLE after an INSERT that queued deferred
        # constraint events on the same table ("pending trigger events").
        with self._pre_0014_state():
            row = _create(tenant, workspace, scope_artifact_id="")
            assert row.scope_artifact_id == "", "precondition: the legacy shape"

            migration._normalise_empty_to_null(None, _SchemaEditorStub())

            row.refresh_from_db()
            assert row.scope_artifact_id is None

    def test_the_data_step_is_idempotent(self, tenant: Tenant, workspace):
        """A second run over a clean table must be a no-op, not an error."""
        migration = importlib.import_module(_MIGRATION)
        row = _create(tenant, workspace, scope_artifact_id=None)

        # First run on an already-clean table: this is the 0-match case the
        # plan calls out (QA gate found no legacy rows).
        migration._normalise_empty_to_null(None, _SchemaEditorStub())
        migration._normalise_empty_to_null(None, _SchemaEditorStub())

        row.refresh_from_db()
        assert row.scope_artifact_id is None
