"""Regression tests for issue #1185 — import error answer must not leak DB internals.

CWE-209: an atomic-insert failure used to build the client-facing message from
the raw exception (``f"{type(exc).__name__}: {exc}"``), which is broadly visible
through the CSV-import response and can carry psycopg/SQL internals. The service
now returns a generic, stable message plus the stable ``PERSISTENCE_ERROR`` cause
code, while the full error (type + message + traceback) goes to the log only.

Requires a database (the natural-key dedupe runs real ORM queries); the Django
test suite is not loadable on the host Python 3.14 interpreter — run in
Docker/CI via the backend-test service.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.import_service import (
    PERSISTENCE_ERROR_MESSAGE,
    ImportService,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace

pytestmark = pytest.mark.django_db

_CSV = "title,description\nAlpha,first\nBeta,second\n"

_LEAK_MARKERS = ("psycopg", "Traceback", "password authentication failed", "FATAL")


class FakePsycopgOperationalError(Exception):
    """Mimics the kind of message a psycopg failure carries."""

    def __init__(self) -> None:
        super().__init__(
            "connection to server at \"db\" port 5432 failed: "
            "FATAL: password authentication failed for user \"reqlo\""
        )


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    return ctx


def _workspace():
    tenant = Tenant.objects.create(
        name="GH1185-T", slug=f"gh1185-t-{uuid.uuid4().hex[:8]}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="GH1185 WS", preset={"name": "standard"}
        )
    finally:
        clear_request_tenant()
    return tenant, workspace


def _run_rollback(workspace):
    """Import a valid CSV with the persistence step raising a psycopg-like error."""
    with patch(
        "application.import_service.ImportService._insert_rows",
        side_effect=FakePsycopgOperationalError(),
    ):
        return ImportService().import_csv(
            _CSV, "Requirement", workspace.id, _ctx(workspace.tenant_id)
        )


def _assert_no_db_internals(text: str) -> None:
    for marker in _LEAK_MARKERS:
        assert marker not in text, f"DB internal '{marker}' leaked to client payload"
    # No "SomeError: ..." exception-class echo anywhere in the payload.
    assert not re.search(r"\b[A-Za-z_][A-Za-z0-9_]*Error:\s", text)
    assert FakePsycopgOperationalError.__name__ not in text


class TestImportPersistenceErrorNoLeak:
    def test_rollback_payload_exposes_no_db_internals(self):
        _tenant, workspace = _workspace()

        result = _run_rollback(workspace)

        assert result.success is False
        assert result.status == "rollback"
        assert result.errors
        assert result.errors[0].field == "persistence"
        # Generic, stable client-facing text; stable machine-readable cause code.
        assert result.errors[0].message == PERSISTENCE_ERROR_MESSAGE
        assert result.items[0]["cause"]["code"] == "PERSISTENCE_ERROR"
        assert result.items[0]["cause"]["message"] == PERSISTENCE_ERROR_MESSAGE

        # The full serialized response (both legacy and v2 keys) must be clean.
        _assert_no_db_internals(json.dumps(result.to_dict()))

    def test_full_error_is_logged(self, caplog):
        _tenant, workspace = _workspace()

        with caplog.at_level(logging.ERROR, logger="application.import_service"):
            _run_rollback(workspace)

        records = [
            r for r in caplog.records if r.name == "application.import_service"
        ]
        assert records, "the persistence error must be logged"
        # The full error travels via ``exc_info`` (type + message + traceback),
        # not the client-facing result.
        exc_records = [r for r in records if r.exc_info is not None]
        assert exc_records, "the full traceback must be logged"
        # ``exc_info`` is the (type, value, traceback) triple: the class name
        # lives in ``exc_info[0]``, the message only in ``str(exc_info[1])``.
        exc_types = " ".join(r.exc_info[0].__name__ for r in exc_records)
        exc_messages = " ".join(str(r.exc_info[1]) for r in exc_records)
        # Type is logged — would fail if logging regressed to a bare string.
        assert FakePsycopgOperationalError.__name__ in exc_types
        assert "psycopg" in exc_types.lower()
        # Message content (incl. psycopg internals) is logged in full.
        assert "password authentication failed" in exc_messages
        assert "FATAL" in exc_messages
        # A traceback is attached, so the stack frame is logged as well.
        assert any(r.exc_info[2] is not None for r in exc_records)
        # The exception class name is logged as an explicit, greppable field.
        assert any(
            FakePsycopgOperationalError.__name__ in r.getMessage() for r in records
        )
