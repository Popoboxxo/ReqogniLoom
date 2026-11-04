"""C7 / #1399 — the ANALYZE helper runs against the real test DB."""
from __future__ import annotations

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_analyze_embedding_indexes_runs(capsys):
    call_command("analyze_embedding_indexes")

    out = capsys.readouterr().out
    assert "ANALYZE completed" in out
    for table in ("pl_requirement", "pl_tracelink", "icd_icd", "mem_memory_entry"):
        assert table in out
