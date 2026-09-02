"""URL routing tests for StakeholderNeedViewSet (REQ-128, issue #710).

The DRF router's default pk pattern ([^/.]+) matches custom action segments
such as "derive-requirements" as a pk value, so
GET /api/v1/needs/derive-requirements/ resolves to retrieve() with
pk="derive-requirements". REQ-128 originally worked around the resulting 500
(UUID parsing failure) with a UUID-shaped ``lookup_value_regex`` that made
routing decline the segment outright, 404ing before the view ever ran.

Issue #710 flagged the side effect: needs answered 404 for *any* malformed
pk, including a genuinely malformed one like "not-a-uuid", while every other
BaseEntityViewSet subclass answers 400 via the generic uuid_url_kwargs guard
in initial() (issue #271). Removing the regex aligned the malformed-pk case
with the rest of the API but regressed REQ-128, whose contract is 404/405 for
``/needs/derive-requirements/`` — a *route* that does not exist, not a
malformed id (the E2E specs hermes-bugfix-campaign / ui-test-campaign pin
that and started failing with 400).

Both contracts now hold at once, without a router-level regex: the #271 guard
distinguishes the two cases by asking the ViewSet which detail-action
``url_path``s it declares. A pk segment equal to one of them is an unknown
route -> 404; anything else malformed stays a malformed id -> 400. See
``BaseEntityViewSet._reject_malformed_uuid_path_kwargs``.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient, APIRequestFactory

from rest_api.views import StakeholderNeedViewSet


def test_non_uuid_detail_segment_reaches_the_viewset() -> None:
    """A non-UUID segment now matches the needs detail route (issue #710).

    Before #710 this asserted the opposite (``api_not_found``, REQ-128's
    routing-level rejection). Removing StakeholderNeedViewSet's
    ``lookup_value_regex`` means routing no longer declines the segment —
    ``initial()``'s guard is what now rejects it, uniformly with every other
    entity ViewSet.
    """
    match = resolve("/api/v1/needs/derive-requirements/")

    assert match.func.cls is StakeholderNeedViewSet
    assert match.kwargs["pk"] == "derive-requirements"


def test_non_uuid_detail_segment_never_500s() -> None:
    """The REQ-128 safety property survives #710: never a 500 from parsing
    "derive-requirements" as a UUID. An anonymous caller is rejected by
    authentication first (401/403); the point is that it is never 500."""
    response = APIClient().get("/api/v1/needs/derive-requirements/")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_action_name_in_pk_slot_returns_404_not_400(authed_client) -> None:
    """REQ-128: ``/needs/derive-requirements/`` is an unknown *route*, not a
    malformed id, so it must answer 404 (the E2E contract accepts 404/405).

    Regression guard for the #710 fix, which removed the router-level regex and
    let the segment fall into the generic malformed-UUID guard -> 400.
    """
    response = authed_client.get("/api/v1/needs/derive-requirements/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_genuinely_malformed_pk_still_returns_400(authed_client) -> None:
    """#710: a real garbage pk is still a malformed id -> 400, so the REQ-128
    carve-out above stays limited to declared detail-action names."""
    response = authed_client.get("/api/v1/needs/not-a-uuid/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_uuid_detail_segment_resolves_to_viewset() -> None:
    """A valid UUID still resolves to the StakeholderNeedViewSet (REQ-128)."""
    match = resolve("/api/v1/needs/00000000-0000-0000-0000-000000000001/")
    assert match.func.cls.__name__ == "StakeholderNeedViewSet"
    assert match.kwargs["pk"] == "00000000-0000-0000-0000-000000000001"


def _needs_request(method: str = "get", params: dict | None = None):
    from auth_tenancy.context import AuthContext, AuthMethod

    factory = APIRequestFactory()
    req_fn = getattr(factory, method)
    url = "/api/v1/needs/"
    if params:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        req = req_fn(f"{url}?{query_string}")
    else:
        req = req_fn(url)
    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    return req


def test_flat_list_route_with_workspace_id_query_param_returns_200() -> None:
    """Regression (issue #5): GET /api/v1/needs/?workspace_id=... 500ed with
    KeyError('workspace_pk') because list() only read the nested-route kwarg."""
    ws_id = str(uuid.uuid4())
    req = _needs_request(params={"workspace_id": ws_id})
    view = StakeholderNeedViewSet.as_view({"get": "list"})
    with patch(
        "application.stakeholder_need_service.StakeholderNeedService.list_by_workspace",
        return_value=[],
    ):
        response = view(req)
    assert response.status_code == 200


def test_flat_list_route_without_workspace_id_returns_400() -> None:
    req = _needs_request()
    view = StakeholderNeedViewSet.as_view({"get": "list"})
    response = view(req)
    assert response.status_code == 400


def test_flat_create_route_with_body_workspace_id_returns_201() -> None:
    """Regression (CR-06/CR-07): POST /api/v1/needs/ (flat, no workspace_pk
    URL kwarg) must read workspace_id from the request body. Previously the
    view only looked at kwargs["workspace_pk"], so flat-route creation always
    called the service with workspace_id=None and failed with a 404
    ("Workspace None not found")."""
    from unittest.mock import MagicMock

    ws_id = str(uuid.uuid4())
    factory = APIRequestFactory()
    req = factory.post(
        "/api/v1/needs/",
        data={"workspace_id": ws_id, "title": "Flat-route need"},
        format="json",
    )
    from auth_tenancy.context import AuthContext, AuthMethod

    req.auth_context = AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    view = StakeholderNeedViewSet.as_view({"post": "create"})

    fake_dto = MagicMock()
    fake_dto.to_dict.return_value = {
        "id": str(uuid.uuid4()),
        "workspace_id": ws_id,
        "title": "Flat-route need",
        "description": "",
        "category": "",
        "status": "draft",
        "moscow_priority": None,
        "uid": None,
        "suspect": False,
        "version": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    with patch(
        "application.stakeholder_need_service.StakeholderNeedService.create",
        return_value=fake_dto,
    ) as mock_create:
        response = view(req)

    assert response.status_code == 201
    assert str(mock_create.call_args.kwargs["workspace_id"]) == ws_id


@pytest.mark.django_db
def test_flat_create_route_minimal_preset_workspace_returns_201() -> None:
    """Regression (CR-07): POST /api/v1/needs/ (flat route) must succeed for a
    workspace using the ``minimal`` rigor preset, exercising the real
    StakeholderNeedService end-to-end (no mocks). Before the CR-06 fix this
    failed identically to CR-06 with "Workspace None not found" (404) because
    the view never read ``workspace_id`` from the request body on the flat
    route; the preset itself was never the actual root cause."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(), name="cr07-minimal-tenant", slug=f"cr07-minimal-{uuid.uuid4().hex[:8]}"
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(), tenant=tenant, name="cr07-minimal-ws", preset="minimal"
        )
        user = User.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            username=f"cr07-minimal-{uuid.uuid4().hex[:8]}",
            email="cr07-minimal@example.com",
        )
    finally:
        TenantContext.clear_tenant()

    factory = APIRequestFactory()
    req = factory.post(
        "/api/v1/needs/",
        data={"workspace_id": str(workspace.id), "title": "CR-07 minimal-preset need"},
        format="json",
    )
    req.auth_context = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    view = StakeholderNeedViewSet.as_view({"post": "create"})
    response = view(req)

    assert response.status_code == 201
    assert response.data["workspace_id"] == str(workspace.id)
