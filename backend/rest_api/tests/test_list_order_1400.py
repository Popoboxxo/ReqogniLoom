"""G2.1 (#1400): paginated lists must have a deterministic order.

A QuerySet without ``ORDER BY`` lets the database return rows in any order, so
``LIMIT/OFFSET`` pagination can repeat one row and drop another. ``_paginate``
now orders every unordered input by ``(created_at, pk)``; the global
``filterwarnings`` rule in ``pyproject.toml`` turns any future violation into a
test failure in every backend set.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement

pytestmark = pytest.mark.django_db


def _seed(tenant, workspace, count: int) -> list[str]:
    """Create *count* requirements that share one ``created_at`` value.

    Identical timestamps are the hard case: an order by ``created_at`` alone is
    still ambiguous, so the ``pk`` tiebreaker is what makes it deterministic.
    """
    set_request_tenant(tenant.id)
    try:
        ids: list[str] = []
        for index in range(count):
            artifact = Artifact.objects.create(
                tenant=tenant,
                workspace=workspace,
                artifact_type="Requirement",
            )
            requirement = Requirement.objects.create(
                tenant=tenant,
                artifact=artifact,
                title=f"G2.1 requirement {index:03d}",
            )
            ids.append(str(requirement.id))
        Requirement.objects.filter(artifact__workspace=workspace).update(
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        return ids
    finally:
        clear_request_tenant()


def _page(client, workspace, page_size: int, url: str | None = None) -> tuple[list[str], str | None]:
    target = url or (
        f"/api/v1/requirements/?workspace_id={workspace.id}&page_size={page_size}"
    )
    response = client.get(target)
    assert response.status_code == 200, response.content
    payload = response.json()
    return [row["id"] for row in payload["results"]], payload.get("next")


def test_pages_are_disjoint_and_complete(tenant, workspace, authed_client):
    ids = _seed(tenant, workspace, 60)

    seen: list[str] = []
    url: str | None = None
    while True:
        page_ids, url = _page(authed_client, workspace, 7, url)
        seen.extend(page_ids)
        if not url:
            break

    assert len(seen) == len(ids), "pagination must not lose or repeat rows"
    assert len(set(seen)) == len(seen), "no id may appear on two pages"
    assert set(seen) == set(ids)


def test_order_independent_of_page_size(tenant, workspace, authed_client):
    _seed(tenant, workspace, 20)

    small, _ = _page(authed_client, workspace, 3)
    large, _ = _page(authed_client, workspace, 100)

    assert small == large[:3], "the first page must not depend on page_size"
