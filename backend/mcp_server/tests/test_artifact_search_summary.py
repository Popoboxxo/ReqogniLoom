"""MCP wiring for the optional AI summary of ``artifact.search`` (#18, scope A).

The summary service itself is covered in
``application/tests/test_search_summary_service.py``; these tests pin the
surface: opt-in only, strict boolean, additive fields, degradation instead of
failure.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.search_service import SearchHit, SearchResult
from application.search_summary_service import SearchSummary
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

pytestmark = pytest.mark.django_db

API_KEY = "reqlo_test_key"


def _context() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _result(workspace_id: str) -> SearchResult:
    return SearchResult(
        results=[
            SearchHit(
                id="00000000-0000-0000-0000-000000000001",
                artifact_type="Requirement",
                title="Anmeldung",
                description="Die Anmeldung nutzt OAuth.",
                relevance_score=0.9,
                workspace_id=workspace_id,
            )
        ],
        total_count=1,
        page=1,
        limit=20,
    )


def _group(result: SearchResult) -> CrossCuttingToolGroup:
    service = MagicMock()
    service.search.return_value = result
    return CrossCuttingToolGroup(search_service=service)


def test_without_the_flag_the_payload_is_unchanged() -> None:
    workspace_id = str(uuid.uuid4())
    group = _group(_result(workspace_id))

    result = group.execute_tool(
        tool_name="artifact.search",
        params={"query": "Anmeldung", "workspace_id": workspace_id},
        auth_context=_context(),
        api_key=API_KEY,
    )

    assert result.success is True
    assert "ai_summary" not in result.data
    assert "summary_degraded" not in result.data


def test_include_summary_adds_both_fields() -> None:
    workspace_id = str(uuid.uuid4())
    group = _group(_result(workspace_id))

    with patch(
        "application.search_summary_service.SearchSummaryService.summarize",
        return_value=SearchSummary(
            text="Eine Anforderung betrifft die Anmeldung.",
            degraded=False,
            cache_hit=False,
            hit_count=1,
        ),
    ):
        result = group.execute_tool(
            tool_name="artifact.search",
            params={
                "query": "Anmeldung",
                "workspace_id": workspace_id,
                "include_summary": True,
            },
            auth_context=_context(),
            api_key=API_KEY,
        )

    assert result.success is True
    assert result.data["ai_summary"] == "Eine Anforderung betrifft die Anmeldung."
    assert result.data["summary_degraded"] is False


def test_a_degraded_summary_keeps_the_search_successful() -> None:
    workspace_id = str(uuid.uuid4())
    group = _group(_result(workspace_id))

    with patch(
        "application.search_summary_service.SearchSummaryService.summarize",
        return_value=SearchSummary(text=None, degraded=True, cache_hit=False, hit_count=1),
    ):
        result = group.execute_tool(
            tool_name="artifact.search",
            params={
                "query": "Anmeldung",
                "workspace_id": workspace_id,
                "include_summary": True,
            },
            auth_context=_context(),
            api_key=API_KEY,
        )

    assert result.success is True
    assert result.data["ai_summary"] is None
    assert result.data["summary_degraded"] is True
    assert result.data["results"][0]["title"] == "Anmeldung"


@pytest.mark.parametrize("value", ["true", 1, ["true"], {"include": True}])
def test_include_summary_must_be_a_boolean(value: object) -> None:
    workspace_id = str(uuid.uuid4())
    group = _group(_result(workspace_id))

    result = group.execute_tool(
        tool_name="artifact.search",
        params={
            "query": "Anmeldung",
            "workspace_id": workspace_id,
            "include_summary": value,
        },
        auth_context=_context(),
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
