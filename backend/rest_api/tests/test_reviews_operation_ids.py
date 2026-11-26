"""P2.11 (m-3) — the review routes must publish honest ``*_list`` operationIds.

All three routes are **list** operations, yet the generated schema advertised
``reviews_retrieve``, ``reviews_pending_retrieve`` and
``workspaces_reviews_pending_retrieve``. A ``*_retrieve`` id tells a generated
client (and anyone reading the spec) that the route returns a single resource;
code generated from it would deserialize a paginated envelope into one object.

The two flat routes share one handler, so the second one cannot be fixed by a
second decoration on the same function — ``@extend_schema`` decorates the
method, not the URL. The alias route therefore goes through the
behaviour-free subclass :class:`ReviewsPendingAliasView`, and this module pins
both halves of that claim: the three ids in the live schema, and the fact that
the alias is still the same handler (no forked logic).

Payload parity itself is covered where its fixtures already live —
``test_review_pending_1089`` owns the tenant/workspace/proposal setup and
asserts that the collection root and the workspace-scoped route answer
identically. This module deliberately does **not** duplicate those fixtures.
"""
from __future__ import annotations

import uuid

from django.urls import resolve, reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from rest_api.review_views import (
    ReviewsPendingAliasView,
    ReviewsPendingView,
    WorkspaceReviewsPendingView,
)

NEW_IDS = {
    "GET /api/v1/reviews/": "reviews_list",
    "GET /api/v1/reviews/pending/": "reviews_pending_list",
    "GET /api/v1/workspaces/{workspace_id}/reviews/pending/": (
        "workspaces_reviews_pending_list"
    ),
}

RETIRED_IDS = {
    "reviews_retrieve",
    "reviews_pending_retrieve",
    "workspaces_reviews_pending_retrieve",
}


def _live_operations() -> dict[str, dict]:
    schema = SchemaGenerator().get_schema(request=None, public=True)
    operations: dict[str, dict] = {}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method != "get" or not isinstance(operation, dict):
                continue
            operations[f"GET {path}"] = operation
    return operations


def test_review_list_routes_publish_honest_operation_ids() -> None:
    operations = _live_operations()

    for key, expected in NEW_IDS.items():
        assert key in operations, f"{key} missing from the generated schema"
        assert operations[key]["operationId"] == expected, (
            f"{key} publishes {operations[key]['operationId']!r}, expected "
            f"{expected!r} — both routes are list operations"
        )


def test_no_review_route_publishes_a_retrieve_operation_id() -> None:
    operations = _live_operations()

    published = {
        key: op.get("operationId")
        for key, op in operations.items()
        if "/reviews/" in key
    }
    stale = {
        key: op_id for key, op_id in published.items() if op_id in RETIRED_IDS
    }
    assert not stale, f"retired *_retrieve operationIds still published: {stale}"


def test_operation_ids_are_unique() -> None:
    """Explicit ids must not collide — spectacular would then suffix them."""
    operations = _live_operations()
    ids = [op.get("operationId") for op in operations.values()]
    duplicates = sorted({op_id for op_id in ids if ids.count(op_id) > 1})
    assert not duplicates, f"duplicate operationIds in the schema: {duplicates}"


# ---------------------------------------------------------------------------
# The alias is a schema carrier, not a second code path
# ---------------------------------------------------------------------------


def test_alias_route_resolves_to_the_behaviour_free_subclass() -> None:
    url = reverse("api-v1-reviews-pending")
    assert url == "/api/v1/reviews/pending/"

    match = resolve(url)
    assert getattr(match.func, "view_class", None) is ReviewsPendingAliasView
    assert issubclass(ReviewsPendingAliasView, ReviewsPendingView)

    assert (
        getattr(resolve(reverse("api-v1-reviews")).func, "view_class", None)
        is ReviewsPendingView
    )
    workspace_url = reverse(
        "workspace-reviews-pending", kwargs={"workspace_id": uuid.UUID(int=0)}
    )
    assert (
        getattr(resolve(workspace_url).func, "view_class", None)
        is WorkspaceReviewsPendingView
    )


def test_alias_get_delegates_to_the_shared_handler(monkeypatch) -> None:
    """The subclass adds a schema decoration and nothing else."""
    sentinel = Response({"count": 0, "results": []})
    seen: dict = {}

    def fake_get(self, request, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(ReviewsPendingView, "get", fake_get)

    request = APIRequestFactory().get(
        "/api/v1/reviews/pending/", {"workspace_id": "x"}
    )
    result = ReviewsPendingAliasView().get(request, extra="passed-through")

    assert result is sentinel
    assert seen["kwargs"] == {"extra": "passed-through"}
