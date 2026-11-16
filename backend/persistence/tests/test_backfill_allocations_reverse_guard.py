"""S0.3-A / L0-002: the 0141 allocation backfill is a deliberate one-way door.

The old reverse issued a bulk ``DELETE`` against ``pl_allocation``. Backfilled
draft rows carry no provenance marker, so it could not target only the rows this
migration created — it would also delete allocations created later through the
API, including released ones. This module pins the ``RunSQL.noop`` reverse so a
future edit cannot silently reintroduce the data-loss path.

Structural only: no database is touched, so the guard stays cheap.
"""
from __future__ import annotations

import importlib
import pathlib

from django.db import migrations

_MIGRATION = importlib.import_module("persistence.migrations.0141_backfill_allocations")
_SOURCE_PATH = pathlib.Path(_MIGRATION.__file__)


def test_backfill_reverse_is_noop() -> None:
    """The single RunSQL operation must declare ``RunSQL.noop`` as its reverse."""
    operations = _MIGRATION.Migration.operations
    assert len(operations) == 1
    operation = operations[0]
    assert isinstance(operation, migrations.RunSQL)
    assert operation.reverse_sql is migrations.RunSQL.noop


def test_module_contains_no_unqualified_bulk_delete() -> None:
    """No statement in the module may wipe the allocation table on reversal."""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    forbidden = "DELETE FROM pl_allocation"
    assert forbidden not in source, (
        "0141 must stay a one-way door: a broad delete cannot distinguish "
        "backfilled drafts from API-created (possibly released) allocations"
    )
