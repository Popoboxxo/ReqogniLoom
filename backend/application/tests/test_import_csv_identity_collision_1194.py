"""Regression tests for issue #1194 — CSV export -> import identity collision.

An exported CSV carries the identity/audit columns produced by
:class:`~application.export_service.ExportService` (``id``, ``artifact_id``,
``version``, timestamps). Re-importing that file used to adopt those primary
keys verbatim, so importing the file into another workspace of the same
database (or into a workspace whose record still exists) collided on the
global ``pl_artifact_pkey`` constraint: the whole transaction rolled back and
the REST layer answered ``422`` with a ``PERSISTENCE_ERROR`` envelope.

Per ADR-014 the import must:

* (a) work as a migration path — an exported file imported into another
  workspace gets a **new** identity (no PK collision), and
* (b) treat a hit on an already-existing natural key as an idempotent
  ``DUPLICATE`` (``skipped``), never a rollback, and
* (c) keep the client-facing envelope generic (no raw SQL / constraint text).

These are real-DB tests (the natural-key dedupe and the insert path run real
ORM queries); run them in Docker via the ``backend-test`` service.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.export_service import ExportService
from application.import_service import PERSISTENCE_ERROR_MESSAGE, ImportService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db

# Substrings of a psycopg/SQLite integrity failure that must never reach the
# client-facing envelope (CWE-209, issue #1185 / #1194).
_LEAK_MARKERS = (
    "pl_artifact_pkey",
    "duplicate key value",
    "UNIQUE constraint",
    "IntegrityError",
    "psycopg",
    "Traceback",
)


class FakePsycopgIntegrityError(Exception):
    """Mimics the exact psycopg failure issue #1194 reports."""

    def __init__(self) -> None:
        super().__init__(
            'duplicate key value violates unique constraint "pl_artifact_pkey"\n'
            "DETAIL:  Key (id)=(...) already exists."
        )


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture(autouse=True)
def _clear_ctx():
    clear_request_tenant()
    yield
    clear_request_tenant()


@pytest.fixture
def env():
    tenant = Tenant.objects.create(
        name="GH1194-T", slug=f"gh1194-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    # Keep the tenant context set for the whole test: the ORM writes in the
    # fixture body, the export and the import all run under it.
    set_request_tenant(tenant.id)
    ws_a = Workspace.objects.create(
        tenant=tenant, name="GH1194 A", preset={"name": "standard"}
    )
    ws_b = Workspace.objects.create(
        tenant=tenant, name="GH1194 B", preset={"name": "standard"}
    )
    yield {"tenant": tenant, "a": ws_a, "b": ws_b, "ctx": _ctx(tenant.id)}
    clear_request_tenant()


def _make_requirement(workspace, title, uid):
    """Create a Requirement (plus backing Artifact) directly in *workspace*."""
    artifact = Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=workspace.tenant,
        artifact=artifact,
        title=title,
        description="migrated description",
        category="functional",
        type="SyReq",
        level=1,
        uid=uid,
    )


def _export_csv(workspace, ctx):
    with patch(
        "application.export_service.ExportService._get_terminology_profile",
        return_value="standard",
    ):
        return ExportService().export_csv("Requirement", workspace.id, ctx)


def _assert_no_db_internals(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text, f"DB internal '{marker}' leaked to client payload"


class TestExportImportIdentityCollision:
    def test_cross_workspace_import_assigns_new_identity(self, env):
        """(a) export(A) -> import(B): new identity, no PK collision."""
        source = _make_requirement(env["a"], "Migrated Req", "REQ-1194-1")
        export = _export_csv(env["a"], env["ctx"])
        assert export.record_count == 1

        result = ImportService().import_csv(
            csv_text=export.content,
            entity_type="Requirement",
            workspace_id=env["b"].id,
            ctx=env["ctx"],
        )

        assert result.success, result.errors
        assert result.imported_count == 1
        assert result.counts["failed"] == 0

        copy = Requirement.objects.get(
            artifact__workspace_id=env["b"].id, uid="REQ-1194-1"
        )
        assert copy.title == "Migrated Req"
        assert copy.description == "migrated description"
        # NEW identity: neither the entity PK nor the Artifact PK is reused.
        assert copy.id != source.id
        assert copy.artifact_id != source.artifact_id
        # The source row is untouched and still owns its own artifact.
        assert Artifact.objects.filter(id=source.artifact_id).exists()
        _assert_no_db_internals(json.dumps(result.to_dict()))

    def test_cross_workspace_import_without_uid_assigns_new_identity(self, env):
        """(a) without a ``uid`` the exported ``id`` is the natural key; a hit in
        the source workspace must not be mistaken for a duplicate in the target
        workspace, or the migration silently drops every row."""
        source = _make_requirement(env["a"], "No UID Req", None)
        export = _export_csv(env["a"], env["ctx"])

        result = ImportService().import_csv(
            csv_text=export.content,
            entity_type="Requirement",
            workspace_id=env["b"].id,
            ctx=env["ctx"],
        )

        assert result.success, result.errors
        assert result.imported_count == 1
        assert result.duplicate_count == 0
        copy = Requirement.objects.get(artifact__workspace_id=env["b"].id)
        assert copy.id != source.id
        assert copy.artifact_id != source.artifact_id
        assert not copy.uid

    def test_same_workspace_reimport_is_duplicate_skip(self, env):
        """(b) export(A) -> import(A): idempotent DUPLICATE, not a rollback."""
        _make_requirement(env["a"], "Reimport Req", "REQ-1194-2")
        export = _export_csv(env["a"], env["ctx"])

        result = ImportService().import_csv(
            csv_text=export.content,
            entity_type="Requirement",
            workspace_id=env["a"].id,
            ctx=env["ctx"],
        )

        assert result.success, result.errors
        assert result.status == "ok"
        assert result.imported_count == 0
        assert result.duplicate_count == 1
        assert result.counts["skipped"] == 1
        assert result.counts["failed"] == 0
        assert [i["cause"]["code"] for i in result.items] == ["DUPLICATE"]
        assert not result.errors

    def test_same_workspace_reimport_without_uid_is_duplicate_skip(self, env):
        """(b) the workspace-scoped ``id`` match still dedupes same-workspace."""
        _make_requirement(env["a"], "No UID Dup Req", None)
        export = _export_csv(env["a"], env["ctx"])

        result = ImportService().import_csv(
            csv_text=export.content,
            entity_type="Requirement",
            workspace_id=env["a"].id,
            ctx=env["ctx"],
        )

        assert result.success, result.errors
        assert result.imported_count == 0
        assert result.duplicate_count == 1
        assert [i["cause"]["code"] for i in result.items] == ["DUPLICATE"]

    def test_persistence_error_envelope_stays_generic(self, env):
        """(c) a PK-collision failure must not leak constraint/SQL internals."""
        _make_requirement(env["a"], "Leak Req", "REQ-1194-3")
        export = _export_csv(env["a"], env["ctx"])

        with patch(
            "application.import_service.ImportService._insert_rows",
            side_effect=FakePsycopgIntegrityError(),
        ):
            result = ImportService().import_csv(
                csv_text=export.content,
                entity_type="Requirement",
                workspace_id=env["b"].id,
                ctx=env["ctx"],
            )

        assert result.success is False
        assert result.errors[0].message == PERSISTENCE_ERROR_MESSAGE
        assert result.items[0]["cause"]["code"] == "PERSISTENCE_ERROR"
        _assert_no_db_internals(json.dumps(result.to_dict()))
