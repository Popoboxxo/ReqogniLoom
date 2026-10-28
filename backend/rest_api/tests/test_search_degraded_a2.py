"""T-A2-7: a Qdrant outage degrades ``/api/v1/search/``, it never answers 500.

The service-level flag is covered in ``application/tests/test_vector_port.py``;
this test pins the *contract* the plan states explicitly ("HTTP bleibt 200, ein
500 ist ausgeschlossen") at the transport boundary, where a raised
``QdrantBackendUnavailableError`` would otherwise be mapped to an error
response by the view's catch-all handler.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from application.vector_port import (
    COLLECTION_REQUIREMENT,
    FallbackVectorPort,
    QdrantBackendUnavailableError,
    QdrantVectorPort,
)
from memory.tests.qdrant_fakes import FakeQdrantModels
from persistence.qdrant_config import resolve_qdrant_config
from persistence.tests.factories import active_tenant, editor_ctx, make_requirement, make_workspace
from rest_api.views import SearchViewSet


def _outage_port() -> FallbackVectorPort:
    """A FallbackVectorPort whose primary is an unreachable Qdrant."""

    def _unreachable(**_kwargs):
        raise QdrantBackendUnavailableError("qdrant is unreachable")

    primary = QdrantVectorPort(
        client=SimpleNamespace(query_points=_unreachable),
        models_module=FakeQdrantModels,
        config=resolve_qdrant_config(base_url="http://qdrant.test"),
    )
    return FallbackVectorPort(primary)


@pytest.mark.django_db(transaction=True)
def test_qdrant_outage_keeps_search_at_http_200_with_degraded_flag(monkeypatch):
    from rest_framework.test import APIRequestFactory

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        req_row = make_requirement(ws, title="Survives the outage")
        # A title hit lets the pgvector/keyword passes produce a result even
        # though the semantic leg is gone.
        ctx = editor_ctx(tenant, ws)

        monkeypatch.setattr(
            "application.search_service.get_fallback_vector_port", _outage_port
        )

        factory = APIRequestFactory()
        request = factory.get(
            f"/api/v1/search/?q=survives&workspace_id={ws.id}&type={COLLECTION_REQUIREMENT}"
        )
        request.auth_context = ctx
        response = SearchViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert response.data["degraded"] is True
    assert response.data["vector_backend"] == "pgvector"
    assert response.data["degraded_reason"] == "qdrant_unavailable"
    assert [hit["id"] for hit in response.data["results"]] == [str(req_row.id)]
