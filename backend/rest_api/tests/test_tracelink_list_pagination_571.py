"""Regression tests for issue #571 — GET /api/v1/tracelinks/ OOM-kills workers.

QA finding (2026-08-16, v1.6.0 STABLE): with 1980 TraceLinks in a workspace,
``GET /api/v1/tracelinks/?workspace_id=<ws>&page_size=2`` (and 5/20/100) killed
a Gunicorn worker via SIGKILL/OOM inside a 512 MB container. Only
``page_size=1`` returned 200.

Root cause: ``TraceLinkViewSet.list()``'s workspace-only branch
(``rest_api/views.py``) called ``TraceLinkService.list_links_for_workspace()``,
which materializes *every* matching TraceLink row via
``TraceLinkManager.get_trace_links()`` — ``list(qs.select_related("source",
"target"))`` with no ``LIMIT``/``OFFSET`` — before pagination is applied. It
then resolved titles and built a plain Python dict for *every* link, and only
handed that fully-materialized list to ``self._paginate()``, which can only
slice an already-in-memory list at that point (the requested ``page_size``
never reaches the database as a ``LIMIT``). Each ``TraceLink`` row also
carries a 1536-dim pgvector ``embedding`` column that the endpoint never
serializes but that ``select_related``/full-row fetch pulled into memory for
every single row regardless of page size — the actual OOM driver at ~2000
links in a 512 MB container.

These tests assert genuine DB-level pagination: the SQL issued against
``pl_tracelink`` must carry a ``LIMIT`` matching the requested page size (not
a full-table fetch followed by in-Python slicing), and must not select the
unused ``embedding`` column.

Reopen (QA deep-dive 2026-09-01, v1.8.0-beta.5): the per-response fix held,
but the endpoint stayed pinned to the shared ceiling of 100 items/page *and
clamped silently* — ``?page_size=5000`` answered 200 with 100 results and
nothing in the payload said so. Since the traceability view needs the whole
link graph, the client walks every page: ~1980 links meant 20 serial
round-trips, and that pile-up is what still reproduced the OOM kill on a
memory-starved host. ``TestTraceLinkPageSizeCeiling`` covers both halves —
the raised, DB-pushed-down ceiling and the now-visible cap.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, TraceLink

pytestmark = pytest.mark.django_db


def _make_requirement(tenant, workspace, title: str) -> Requirement:
    art = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, artifact=art, workspace=workspace, title=title, status="draft"
    )


def _make_tracelinks(tenant, workspace, count: int) -> None:
    """Create *count* independent TraceLinks (each its own req pair) so no
    cycle-detection edge case interferes — this test only cares about the
    listing/pagination path, not link creation semantics."""
    set_request_tenant(tenant.id)
    try:
        for i in range(count):
            src = _make_requirement(tenant, workspace, f"Source {i}")
            tgt = _make_requirement(tenant, workspace, f"Target {i}")
            TraceLink.objects.create(
                tenant=tenant,
                source=src.artifact,
                target=tgt.artifact,
                link_type="satisfies",
            )
    finally:
        clear_request_tenant()


LINK_COUNT = 60
PAGE_SIZE = 5

#: Reopen (#571): a page size above the shared ``StandardPagination`` ceiling
#: of 100, plus enough links that the slice is *not* shortened to the total
#: count on the last page — otherwise the SQL LIMIT could not tell a raised
#: ceiling apart from a clamped one.
OVER_CAP_PAGE_SIZE = 110
OVER_CAP_LINK_COUNT = 120


class TestTraceLinkWorkspaceListPagination:
    """GET /api/v1/tracelinks/?workspace_id=...&page_size=... (#571)."""

    def test_query_applies_db_level_limit(self, authed_client, tenant, workspace):
        """The SQL issued must actually LIMIT to page_size — proving the
        endpoint no longer materializes every workspace link before slicing.
        """
        _make_tracelinks(tenant, workspace, LINK_COUNT)

        with CaptureQueriesContext(connection) as ctx:
            resp = authed_client.get(
                f"/api/v1/tracelinks/?workspace_id={workspace.id}&page_size={PAGE_SIZE}"
            )

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["count"] == LINK_COUNT, body
        assert len(body["results"]) == PAGE_SIZE, body

        tracelink_queries = [
            q["sql"] for q in ctx.captured_queries if "pl_tracelink" in q["sql"]
        ]
        assert tracelink_queries, "no query touched pl_tracelink at all"

        select_queries = [
            sql
            for sql in tracelink_queries
            if sql.strip().upper().startswith("SELECT")
        ]
        assert select_queries, tracelink_queries
        assert any(f"LIMIT {PAGE_SIZE}" in sql for sql in select_queries), (
            "no SELECT against pl_tracelink carries 'LIMIT %d' — the endpoint "
            "is materializing the full workspace result set in Python instead "
            "of letting the DB paginate (#571 OOM root cause). Queries:\n"
            + "\n".join(select_queries)
        )

    def test_query_does_not_fetch_unused_embedding_column(
        self, authed_client, tenant, workspace
    ):
        """The 1536-dim `embedding` VectorField is never serialized by
        TraceLinkSerializer — fetching it for every row is dead weight that
        made the OOM worse. The SELECT must defer it."""
        _make_tracelinks(tenant, workspace, LINK_COUNT)

        with CaptureQueriesContext(connection) as ctx:
            resp = authed_client.get(
                f"/api/v1/tracelinks/?workspace_id={workspace.id}&page_size={PAGE_SIZE}"
            )

        assert resp.status_code == 200, resp.content

        select_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if "pl_tracelink" in q["sql"] and q["sql"].strip().upper().startswith("SELECT")
        ]
        assert select_queries
        assert not any('"embedding"' in sql for sql in select_queries), (
            "SELECT against pl_tracelink still fetches the unused embedding "
            "column:\n" + "\n".join(select_queries)
        )

    def test_response_content_correct_across_pages(
        self, authed_client, tenant, workspace
    ):
        """Sanity: pagination still returns the right total/shape once it is
        pushed down to the DB (no off-by-one / missing rows)."""
        _make_tracelinks(tenant, workspace, LINK_COUNT)

        seen_ids: set[str] = set()
        page = 1
        while True:
            resp = authed_client.get(
                f"/api/v1/tracelinks/?workspace_id={workspace.id}"
                f"&page_size={PAGE_SIZE}&page={page}"
            )
            assert resp.status_code == 200, resp.content
            body = resp.json()
            for item in body["results"]:
                assert item["id"] not in seen_ids, "duplicate item across pages"
                seen_ids.add(item["id"])
            if body["next"] is None:
                break
            page += 1

        assert len(seen_ids) == LINK_COUNT


class TestTraceLinkPageSizeCeiling:
    """#571 reopen: fewer round-trips, and never a silent clamp."""

    def test_page_size_above_shared_hundred_is_honoured(
        self, authed_client, tenant, workspace
    ):
        """The traceability client walks every page, so the ceiling decides the
        round-trip count. 110 (> the shared ``StandardPagination`` max of 100)
        must reach the database as the LIMIT, not be clamped down to 100.

        More links than the requested page size exist on purpose: Django's
        ``Paginator`` shrinks the slice to the total count on the last page, so
        a LIMIT below the request would otherwise be indistinguishable from a
        clamp.
        """
        _make_tracelinks(tenant, workspace, OVER_CAP_LINK_COUNT)

        with CaptureQueriesContext(connection) as ctx:
            resp = authed_client.get(
                f"/api/v1/tracelinks/?workspace_id={workspace.id}"
                f"&page_size={OVER_CAP_PAGE_SIZE}"
            )

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["page_size"] == OVER_CAP_PAGE_SIZE, body
        assert body["count"] == OVER_CAP_LINK_COUNT, body
        assert len(body["results"]) == OVER_CAP_PAGE_SIZE, body

        select_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if "pl_tracelink" in q["sql"]
            and q["sql"].strip().upper().startswith("SELECT")
        ]
        assert any(
            f"LIMIT {OVER_CAP_PAGE_SIZE}" in sql for sql in select_queries
        ), (
            f"page_size={OVER_CAP_PAGE_SIZE} did not reach the DB as "
            f"'LIMIT {OVER_CAP_PAGE_SIZE}' — the endpoint is either clamped to "
            "the shared 100 ceiling or paginating in Python:\n"
            + "\n".join(select_queries)
        )

    def test_envelope_reports_the_applied_page_size_and_ceiling(
        self, authed_client, tenant, workspace
    ):
        """An over-large ``page_size`` is still clamped, but the response now
        says which size was applied and where the ceiling sits — the silent
        truncation was the whole reopen finding."""
        _make_tracelinks(tenant, workspace, 3)

        resp = authed_client.get(
            f"/api/v1/tracelinks/?workspace_id={workspace.id}&page_size=5000"
        )

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["max_page_size"] == 500, body
        assert body["page_size"] == 500, (
            "requested page_size=5000 was clamped without saying so", body
        )
        # Sanity: clamping must not drop data that fits.
        assert body["count"] == 3
        assert len(body["results"]) == 3

    def test_envelope_reports_page_size_on_the_default_path_too(
        self, authed_client, tenant, workspace
    ):
        """No ``page_size`` given — the applied default must still be echoed so
        a client never has to guess what it got."""
        _make_tracelinks(tenant, workspace, 2)

        resp = authed_client.get(
            f"/api/v1/tracelinks/?workspace_id={workspace.id}"
        )

        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["page_size"] == 25, body
        assert body["max_page_size"] == 500, body
