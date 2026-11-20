"""The reconcile command dispatches through the backend, not its name (P4).

A backend that declares ``capabilities.external_store`` and implements
``reconcile_external`` is consulted regardless of its name; the command no
longer knows about Honcho or Qdrant.
"""
from __future__ import annotations

import json

import pytest
from django.core.management import call_command

from memory.backends import MEMORY_BACKEND_REGISTRY, MemoryCapabilities, PgvectorMemoryBackend

pytestmark = pytest.mark.django_db


class _ReconcileDummy(PgvectorMemoryBackend):
    """A concrete backend with a synthetic external store."""

    capabilities = MemoryCapabilities(external_store=True)

    def reconcile_external(self, tenant_ids, workspace_id):
        return (
            [
                {
                    "backend_ref": "sentinel-orphan",
                    "scope": "user",
                    "scope_id": None,
                    "severity": "warning",
                }
            ],
            [{"collection": "dummy", "error": "boom", "severity": "warning"}],
        )


@pytest.fixture()
def dummy_backend():
    MEMORY_BACKEND_REGISTRY["reconcile_dummy"] = _ReconcileDummy
    try:
        yield
    finally:
        MEMORY_BACKEND_REGISTRY.pop("reconcile_dummy", None)


def test_command_calls_the_backend_reconciler(dummy_backend, capsys):
    call_command("memory_reconcile", backend="reconcile_dummy", as_json=True)
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{") :])

    assert report["backend"] == "reconcile_dummy"
    assert report["external_store"] is True
    refs = [row.get("backend_ref") for row in report["backend_objects_without_local_row"]]
    assert "sentinel-orphan" in refs
    assert report["scan_findings"], "scan findings must surface the blind spot"


def test_pgvector_is_not_an_external_store() -> None:
    assert PgvectorMemoryBackend.capabilities.external_store is False
    assert PgvectorMemoryBackend().reconcile_external([], None) == ([], [])
