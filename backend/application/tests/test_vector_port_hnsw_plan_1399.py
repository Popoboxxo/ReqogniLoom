"""G2.3 (#1399): the similarity query can use the HNSW indexes.

The production path does not force an index (a sequential scan is cheaper for
small tables), but an expression/opclass drift between the model's
``HnswIndex`` and ``PgVectorVectorPort.query_similar`` would silently make the
index unusable. The test explains the exact query shape the port builds with
``enable_seqscan = off``: if either side drifts, the plan falls back to a
sequential scan and this fails.
"""
from __future__ import annotations

import pytest
from django.db import connection, transaction

from persistence.embedding_dimensions import EMBEDDING_VECTOR_DIMENSIONS
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, TraceLink

pytestmark = pytest.mark.django_db


def _explain(index_name: str, model, tenant_id) -> str:
    from pgvector.django import CosineDistance

    queryset = (
        model.objects.filter(
            tenant_id=tenant_id, embedding__isnull=False
        )
        .annotate(
            distance=CosineDistance(
                "embedding", [0.1] * EMBEDDING_VECTOR_DIMENSIONS
            )
        )
        .order_by("distance")[:5]
    )
    sql, params = queryset.query.sql_with_params()
    # SET LOCAL needs a transaction; enable_seqscan off makes the planner pick
    # the index whenever the expression and opclass actually match.
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
            # With an empty/small table the planner otherwise prefers the
            # cheap tenant_id B-tree plus a Sort. Disabling Sort leaves the
            # HNSW index as the only way to satisfy ORDER BY distance LIMIT k,
            # which is exactly the usability question this test answers.
            cursor.execute("SET LOCAL enable_sort = off")
            cursor.execute("EXPLAIN " + sql, params)
            plan = "\n".join(row[0] for row in cursor.fetchall())
    assert index_name in plan, (
        f"{index_name} is not usable for the production similarity query; "
        f"plan:\n{plan}"
    )
    return plan


def test_requirement_similarity_can_use_hnsw():
    tenant = Tenant.objects.create(name="G2.3 tenant", slug="g2-3-tenant")
    set_request_tenant(tenant.id)
    try:
        _explain("pl_req_embedding_hnsw", Requirement, tenant.id)
    finally:
        clear_request_tenant()


def test_tracelink_similarity_can_use_hnsw():
    tenant = Tenant.objects.create(name="G2.3 tenant", slug="g2-3-tenant-links")
    set_request_tenant(tenant.id)
    try:
        _explain("pl_tracelink_embedding_hnsw", TraceLink, tenant.id)
    finally:
        clear_request_tenant()
