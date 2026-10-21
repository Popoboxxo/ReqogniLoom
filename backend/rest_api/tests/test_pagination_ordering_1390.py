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

Review finding F1 (why the warning capture alone is not enough): three list
routes hand the paginator a **materialised Python list**, not a queryset —
``ArchitectureService.list_architecture_elements``,
``StakeholderNeedService.list_by_workspace`` and
``TraceLinkViewSet._list_artifact_links``. An in-memory sequence can never
raise ``UnorderedObjectListWarning``, so the warning check is structurally
blind to exactly the routes that were unstable. The tests below therefore pin
the *observable* contract instead:

* :func:`test_page_windows_partition_the_full_set` — walking ``page=1..n`` with
  a fixed ``page_size`` must reproduce the unpaginated result exactly: same
  members, same order, no duplicates, no gaps.
* :func:`test_rows_with_equal_sort_keys_keep_a_stable_order` — ``created_at``
  alone is not unique (a bulk/batch-created set shares one timestamp), so the
  tie-breaker has to be part of the ordering, not luck of the physical row
  order.

Both run against all three list-backed routes.
"""
from __future__ import annotations

import warnings
from datetime import timedelta

import pytest
from django.core.paginator import UnorderedObjectListWarning
from django.utils import timezone
from rest_framework.test import APIClient

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    StakeholderNeed,
    Tenant,
    TraceLink,
    Workspace,
)
from rest_api.urls import router
from rest_api.views import BaseEntityViewSet

pytestmark = pytest.mark.django_db

#: Rows per route in the partition/tie-breaker tests. Deliberately not a
#: multiple of ``_PAGE_SIZE``, so the last page is a short one.
_ROWS = 12
_PAGE_SIZE = 5

#: Registered routes that live on a ``BaseEntityViewSet`` subclass but
#: deliberately do not serve a workspace-level list, mapped to the status/code
#: they answer with. ``/comments/`` is a 405 that points the caller at
#: ``/artifacts/<id>/comments/`` instead of listing across a workspace — a
#: documented contract, not an ordering candidate. Kept as an explicit
#: allow-list (rather than a bare ``if status != 200: continue``) so that an
#: unexpected non-200 still fails this test instead of silently skipping the
#: route, and so a route that starts answering 200 here is not missed either.
_NON_LIST_ROUTES = {"/api/v1/comments/": (405, "VALIDATION_ERROR")}

#: Registered collection routes that answer 200 with a bespoke, deliberately
#: unpaginated envelope. Pinned by their exact top-level keys, so silently
#: dropping the envelope (or paginating them without updating this map) fails
#: here instead of being skipped.
_NON_PAGINATED_ROUTES = {
    "/api/v1/notifications/": {"notifications", "unread_count"},
}


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


# ---------------------------------------------------------------------------
# Seeding — one helper per list-backed route
# ---------------------------------------------------------------------------


def _artifact(tenant: Tenant, workspace: Workspace, artifact_type: str) -> Artifact:
    return Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type=artifact_type
    )


def _seed_architecture(tenant: Tenant, workspace: Workspace, count: int) -> list[str]:
    """Create *count* root ArchitectureElements; return their ids in order."""
    ids: list[str] = []
    for index in range(count):
        element = ArchitectureElement.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "ArchitectureElement"),
            title=f"Element {index:02d}",
        )
        ids.append(str(element.id))
    return ids


def _seed_needs(tenant: Tenant, workspace: Workspace, count: int) -> list[str]:
    """Create *count* StakeholderNeeds; return their ids in order."""
    ids: list[str] = []
    for index in range(count):
        need = StakeholderNeed.objects.create(
            tenant=tenant,
            artifact=_artifact(tenant, workspace, "StakeholderNeed"),
            title=f"Need {index:02d}",
        )
        ids.append(str(need.id))
    return ids


def _seed_links(
    tenant: Tenant, workspace: Workspace, count: int, *, mixed: bool
) -> tuple[list[str], str]:
    """Create *count* links around one hub artifact.

    ``mixed=True`` alternates downstream (hub → other) and upstream
    (other → hub), which also exercises the endpoint's upstream-then-downstream
    merge. ``mixed=False`` keeps every link downstream, so the endpoint's
    output is directly comparable to one ordered sequence (the tie-breaker test
    asserts ascending id).

    Returns the created link ids (creation order) and the hub artifact id to
    query with.
    """
    hub = _artifact(tenant, workspace, "Requirement")
    ids: list[str] = []
    for index in range(count):
        other = _artifact(tenant, workspace, "Requirement")
        downstream = not mixed or index % 2 == 0
        source, target = (hub, other) if downstream else (other, hub)
        link = TraceLink.objects.create(
            tenant=tenant,
            source=source,
            target=target,
            link_type="references",
        )
        ids.append(str(link.id))
    return ids, str(hub.id)


#: route name -> seeder. ``tracelinks`` needs the hub artifact id in the URL.
_SEEDERS = {
    "architecture": _seed_architecture,
    "needs": _seed_needs,
}

_ROUTE_NAMES = ("architecture", "needs", "tracelinks")


def _seed(
    route: str,
    tenant: Tenant,
    workspace: Workspace,
    count: int,
    *,
    mixed_links: bool = True,
) -> tuple[list[str], str | None]:
    """Seed *count* rows for *route*; return ``(ids_in_creation_order, extra)``."""
    set_request_tenant(tenant.id)
    try:
        if route == "tracelinks":
            link_ids, hub_id = _seed_links(
                tenant, workspace, count, mixed=mixed_links
            )
            return link_ids, hub_id
        return _SEEDERS[route](tenant, workspace, count), None
    finally:
        clear_request_tenant()


def _list_url(route: str, workspace: Workspace, extra: str | None) -> str:
    base = f"/api/v1/{route}/?workspace_id={workspace.id}"
    if extra is not None:
        base += f"&artifact_id={extra}"
    return base


def _get_page(
    client: APIClient, route: str, workspace: Workspace, extra: str | None, **params
) -> dict:
    """GET one page and assert the envelope is a real, non-empty success."""
    query = "".join(f"&{key}={value}" for key, value in params.items())
    response = client.get(_list_url(route, workspace, extra) + query)
    # Non-vacuous: a 403/404/500 would otherwise "pass" the ordering check
    # trivially (an error body is not unordered).
    assert response.status_code == 200, (route, params, response.content)
    payload = response.json()
    assert "results" in payload, (route, payload)
    return payload


def _ids(payload: dict) -> list[str]:
    return [item["id"] for item in payload["results"]]


def _full_list(client: APIClient, route: str, workspace: Workspace, extra: str | None):
    """Return the unpaginated id list (one oversized page)."""
    return _ids(
        _get_page(client, route, workspace, extra, page_size=100, page=1)
    )


# ---------------------------------------------------------------------------
# 1) #1390 — no unordered-queryset warning on any paginated list route
# ---------------------------------------------------------------------------


def test_every_paginated_list_endpoint_uses_a_deterministic_order(
    authed_client: APIClient, workspace
) -> None:
    paths = _paginated_list_paths()
    assert paths, "router introspection found no paginated list routes"

    offenders: dict[str, str] = {}
    checked = 0
    for path in paths:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            response = authed_client.get(path, {"workspace_id": str(workspace.id)})
        # F1: an error status would make the warning scan vacuous, so the
        # response shape is asserted first. Only the documented non-list route
        # above may answer anything but a paginated 200.
        if path in _NON_LIST_ROUTES:
            expected_status, expected_code = _NON_LIST_ROUTES[path]
            assert response.status_code == expected_status, (path, response.content)
            assert response.json()["error"]["code"] == expected_code, (
                path,
                response.content,
            )
            continue
        assert response.status_code == 200, (path, response.content)
        payload = response.json()
        if path in _NON_PAGINATED_ROUTES:
            assert set(payload) == _NON_PAGINATED_ROUTES[path], (path, payload)
            continue
        assert "results" in payload, (path, response.content)
        checked += 1
        for warning in caught:
            if issubclass(warning.category, UnorderedObjectListWarning):
                offenders[path] = str(warning.message)

    assert checked >= 15, (
        f"only {checked} paginated list routes were actually exercised — the "
        "route introspection stopped covering the registered viewsets"
    )
    assert not offenders, (
        "paginated list endpoints sliced an unordered queryset (#1390) — add a "
        f"deterministic order_by() to each: {sorted(offenders)}"
    )


# ---------------------------------------------------------------------------
# 2) F1 — page windows must partition the full result set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", _ROUTE_NAMES)
def test_page_windows_partition_the_full_set(
    route: str, authed_client: APIClient, tenant: Tenant, workspace: Workspace
) -> None:
    """``page=1..n`` must reproduce the full list exactly.

    This is the observable shape of #1390: with an unstable ORDER BY the
    LIMIT/OFFSET windows can hand out a row twice and never hand out another.
    Comparing the *concatenation* (not just the set) also catches a page
    boundary that sorts differently from the full fetch.
    """
    _, extra = _seed(route, tenant, workspace, _ROWS)

    expected = _full_list(authed_client, route, workspace, extra)
    assert len(expected) == _ROWS, expected

    collected: list[str] = []
    page = 1
    while True:
        payload = _get_page(
            authed_client, route, workspace, extra, page_size=_PAGE_SIZE, page=page
        )
        assert payload["page_size"] == _PAGE_SIZE, payload
        collected.extend(_ids(payload))
        if payload["next"] is None:
            break
        page += 1
        assert page <= _ROWS, "pagination did not terminate"

    assert len(collected) == len(set(collected)), (
        f"{route}: a row appeared on more than one page — duplicate ids "
        f"{sorted({i for i in collected if collected.count(i) > 1})}"
    )
    assert collected == expected, (
        f"{route}: the page windows do not partition the full set in order — "
        "the endpoint's ordering is not deterministic (#1390)"
    )


# ---------------------------------------------------------------------------
# 3) F2 — equal sort keys need a unique tie-breaker
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", _ROUTE_NAMES)
def test_rows_with_equal_sort_keys_keep_a_stable_order(
    route: str, authed_client: APIClient, tenant: Tenant, workspace: Workspace
) -> None:
    """Rows sharing one ``created_at`` must still have a total order.

    ``created_at`` is not unique — a batch import (or any write path inside one
    transaction) can stamp every row with the same timestamp. Ordering by
    ``created_at`` alone then leaves the page boundary to the physical row
    order, which PostgreSQL may change between two requests. With the
    ``(created_at, id)`` tie-breaker the order is total: ascending id.

    The tie-breaker is asserted on the rows the route exposes *after* the
    route's own merge/annotation, so this stays an API-level contract.
    """
    # Same-direction links only: the trace-link endpoint merges an upstream and
    # a downstream block, so a mixed fixture has no single global id order.
    ids, extra = _seed(route, tenant, workspace, _ROWS, mixed_links=False)

    # Force a single timestamp onto every seeded row: ``auto_now_add`` is
    # applied in ``Model.save()`` only, so ``.update()`` writes it verbatim.
    stamp = timezone.now() - timedelta(days=1)
    set_request_tenant(tenant.id)
    try:
        if route == "architecture":
            ArchitectureElement.objects.filter(id__in=ids).update(created_at=stamp)
        elif route == "needs":
            StakeholderNeed.objects.filter(id__in=ids).update(created_at=stamp)
        else:
            TraceLink.objects.filter(id__in=ids).update(created_at=stamp)
    finally:
        clear_request_tenant()

    expected = _full_list(authed_client, route, workspace, extra)
    # No UPDATE re-orders the rows: every row shares created_at, so the
    # ordering must be the primary-key tie-breaker (ascending, byte-wise —
    # which for canonical lowercase UUID text is string order).
    assert expected == sorted(ids), (
        f"{route}: rows with an identical created_at are not ordered by their "
        f"unique tie-breaker — got {expected}, expected {sorted(ids)}"
    )

    # ... and it is stable: repeating the walk yields the same sequence.
    collected: list[str] = []
    page = 1
    while True:
        payload = _get_page(
            authed_client, route, workspace, extra, page_size=_PAGE_SIZE, page=page
        )
        collected.extend(_ids(payload))
        if payload["next"] is None:
            break
        page += 1
        assert page <= _ROWS, "pagination did not terminate"

    assert collected == expected
    again = _full_list(authed_client, route, workspace, extra)
    assert again == expected, f"{route}: repeated identical requests disagree"
