"""Regression test for issue #571 (write path) — review finding F7 pin.

The read-path OOM (``GET /api/v1/tracelinks/``) was fixed by deferring the
1536-dim ``embedding`` VectorField in ``TraceLinkManager._filtered_queryset``
(see ``rest_api/tests/test_tracelink_list_pagination_571.py``). Review
finding F7 pointed out that ``TraceLinkManager.create()`` calls the very same
eager, tenant-wide ``get_trace_links()`` to build the cycle-detection
adjacency list on *every single TraceLink creation* — the same OOM shape as
#571, just on the write path instead of the list endpoint.

The fix (moving ``.defer("embedding")`` into the shared ``_filtered_queryset``
helper) benefits ``get_trace_links()`` automatically, but nothing pinned that
with a test — a mutation test (reverting the F7 change) would still pass
every other suite. This test closes that gap by capturing the actual SQL
``create()`` issues and asserting the ``embedding`` column is not selected.
"""
from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from traceability.trace_link_manager import TraceLinkManager
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> TraceLinkManager:
    return TraceLinkManager()


class TestCreateDoesNotFetchUnusedEmbeddingColumn:
    """F7: the cycle-detection SELECT inside create() must defer embedding."""

    def test_create_cycle_detection_query_omits_embedding(
        self, manager, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            # A pre-existing 'satisfies' link so the cycle-detection SELECT
            # inside create() actually returns a row — proving the deferred
            # column isn't fetched even when there is data to fetch it for,
            # not just on an empty table.
            existing_src = make_artifact(tenant_a, workspace_a, "requirement")
            existing_tgt = make_artifact(
                tenant_a, workspace_a, "architecture_element"
            )
            make_trace_link(
                existing_src, existing_tgt, tenant_a, link_type="satisfies"
            )

            new_src = make_artifact(tenant_a, workspace_a, "requirement")
            new_tgt = make_artifact(tenant_a, workspace_a, "architecture_element")

            with CaptureQueriesContext(connection) as ctx:
                link = manager.create(
                    source_id=new_src.id,
                    target_id=new_tgt.id,
                    link_type="satisfies",
                )

        assert link.id is not None

        tracelink_selects = [
            q["sql"]
            for q in ctx.captured_queries
            if "pl_tracelink" in q["sql"] and q["sql"].strip().upper().startswith("SELECT")
        ]
        assert tracelink_selects, "create() never queried pl_tracelink at all"
        assert not any('"embedding"' in sql for sql in tracelink_selects), (
            "create()'s cycle-detection SELECT against pl_tracelink still "
            "fetches the unused embedding column (#571 write-path OOM, "
            "review F7):\n" + "\n".join(tracelink_selects)
        )
