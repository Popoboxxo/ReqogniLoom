"""A3 / T-A3-1: the search ``mode`` parameter is honest.

``hybrid`` keeps the historical behaviour, ``keyword`` makes no embedding call,
``vector`` runs only the semantic pass, and an unknown value is a
``ValidationError`` (→ HTTP 400) instead of a silent hybrid fallback.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from application.base import ValidationError
from application.search_service import SearchHit, SearchService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace

pytestmark = pytest.mark.django_db


def _setup():
    tenant = Tenant.objects.create(name="A3", slug=f"a3-{uuid.uuid4().hex[:8]}")
    set_request_tenant(tenant.id)
    workspace = Workspace.objects.create(
        tenant=tenant, name="A3 WS", preset={"name": "standard"}
    )
    ctx = SimpleNamespace(
        tenant_id=tenant.id,
        user_id=uuid.uuid4(),
        active_roles=("admin",),
    )
    return tenant, workspace, ctx


def test_mode_keyword_skips_embedding():
    _tenant, workspace, ctx = _setup()
    try:
        with patch("application.search_service.generate_embedding") as spy:
            SearchService().search(
                "REST", ctx, workspace_id=workspace.id, mode="keyword"
            )
        spy.assert_not_called()
    finally:
        clear_request_tenant()


def test_invalid_mode_raises_validation_error():
    _tenant, workspace, ctx = _setup()
    try:
        with pytest.raises(ValidationError, match="mode must be one of"):
            SearchService().search(
                "REST", ctx, workspace_id=workspace.id, mode="fuzzy"
            )
    finally:
        clear_request_tenant()


def test_mode_vector_runs_only_the_semantic_pass():
    _tenant, workspace, ctx = _setup()
    hit = SearchHit(
        id="00000000-0000-0000-0000-000000000001",
        artifact_type="Requirement",
        title="REST",
        description="",
        relevance_score=0.9,
        workspace_id=str(workspace.id),
    )
    def _semantic(entity_type, *_args, **_kwargs):
        return [hit] if entity_type == "Requirement" else []

    try:
        with (
            patch(
                "application.search_service.generate_embedding",
                return_value=[0.1] * 384,
            ),
            patch(
                "application.search_service._run_fulltext_query",
                return_value=[],
            ) as fulltext,
            patch(
                "application.search_service._run_lexical_query",
                return_value=[],
            ) as lexical,
            patch(
                "application.search_service._run_semantic_query",
                side_effect=_semantic,
            ) as semantic,
        ):
            result = SearchService().search(
                "REST", ctx, workspace_id=workspace.id, mode="vector"
            )
    finally:
        clear_request_tenant()

    assert result.results == [hit]
    fulltext.assert_not_called()
    lexical.assert_not_called()
    assert semantic.called
