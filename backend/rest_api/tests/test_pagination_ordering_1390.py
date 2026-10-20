"""Regression test for issue #1390 — paginated lists must be ordered.

DRF's ``PageNumberPagination`` emits ``UnorderedObjectListWarning`` whenever it
slices a QuerySet that carries no ``ORDER BY``. Without one, LIMIT/OFFSET pages
may overlap or skip rows between requests (and Postgres is free to return the
rows in any order). The list endpoints must therefore hand the paginator a
deterministically ordered queryset.

Every list route backed by ``BaseEntityViewSet`` — the viewsets that paginate
through ``BaseEntityViewSet._paginate`` — is requested against a real workspace
here, so a new unordered list endpoint fails this test instead of only showing
up as a warning in the suite output.
"""
from __future__ import annotations

import warnings

import pytest
from django.core.paginator import UnorderedObjectListWarning
from rest_framework.test import APIClient

from rest_api.urls import router
from rest_api.views import BaseEntityViewSet

pytestmark = pytest.mark.django_db


def _paginated_list_paths() -> list[str]:
    """Return one list URL per viewsets that paginates via ``BaseEntityViewSet``.

    The router also registers legacy aliases (``test-cases``, ``trace-links``,
    ``maingoals``, …) that point at the same ViewSet, so each class is probed
    once via the first prefix it was registered under.
    """
    seen: set[type] = set()
    paths: list[str] = []
    for prefix, viewset, _ in router.registry:
        if not (isinstance(viewset, type) and issubclass(viewset, BaseEntityViewSet)):
            continue
        if viewset in seen:
            continue
        seen.add(viewset)
        paths.append(f"/api/v1/{prefix}/")
    return sorted(paths)


def test_every_paginated_list_endpoint_uses_a_deterministic_order(
    authed_client: APIClient, workspace
) -> None:
    paths = _paginated_list_paths()
    assert paths, "router introspection found no paginated list routes"

    offenders: dict[str, str] = {}
    for path in paths:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            authed_client.get(path, {"workspace_id": str(workspace.id)})
        for warning in caught:
            if issubclass(warning.category, UnorderedObjectListWarning):
                offenders[path] = str(warning.message)

    assert not offenders, (
        "paginated list endpoints sliced an unordered queryset (#1390) — add a "
        f"deterministic order_by() to each: {sorted(offenders)}"
    )
