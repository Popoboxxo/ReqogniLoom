"""Issue #271: a malformed UUID in a REST URL must be 400, not 404.

Before this change every ``BaseEntityViewSet`` detail handler caught the
``ValueError`` raised by ``UUID(pk)`` and mapped it onto ``404 NOT_FOUND``,
which is indistinguishable from the legitimate "well-formed id, no such row"
case. Clients could not tell "you sent garbage" from "it is gone".

The fix adds one shared guard on ``BaseEntityViewSet`` (``uuid_url_kwargs`` +
``initial()``), so it applies to every subclass at once rather than being
repeated in ~20 ViewSets. This module therefore proves the *generic* behaviour
on a representative sample of ViewSets, plus the two properties that make the
guard safe:

  * a well-formed-but-unknown UUID still yields 404 (the distinction is real);
  * the guard runs *after* authentication, so an anonymous caller still gets
    401/403 and cannot use the 400-vs-401 difference to probe routes.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient, APIRequestFactory

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from rest_api.views import (
    AdrViewSet,
    ArchitectureElementViewSet,
    RequirementViewSet,
    RiskViewSet,
    WorkspaceViewSet,
)
# Aliased: pytest tries to collect any imported name starting with "Test".
from rest_api.views import TestCaseViewSet as TESTCASE_VIEWSET

pytestmark = pytest.mark.django_db


MALFORMED_PKS = ("not-a-uuid", "xyz", "undefined", "123", "null")


def _make_auth_context(*, tenant_id, roles=("admin",)):
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _tenant_and_workspace(name: str):
    tenant = Tenant.objects.create(name=name)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"WS-{name}")
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace


def _retrieve(viewset, pk, *, tenant_id, url="/api/v1/x/"):
    req = APIRequestFactory().get(f"{url}{pk}/")
    req.auth_context = _make_auth_context(tenant_id=tenant_id)
    return viewset.as_view({"get": "retrieve"})(req, pk=pk)


# ---------------------------------------------------------------------------
# The core contract: malformed -> 400, well-formed-but-absent -> 404
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "viewset",
    [
        RequirementViewSet,
        ArchitectureElementViewSet,
        TESTCASE_VIEWSET,
        AdrViewSet,
        RiskViewSet,
        WorkspaceViewSet,
    ],
)
def test_malformed_uuid_pk_returns_400_across_viewsets(viewset):
    """The shared guard applies to every BaseEntityViewSet subclass."""
    tenant, _ = _tenant_and_workspace(f"T-{viewset.__name__}")

    response = _retrieve(viewset, "not-a-uuid", tenant_id=tenant.id)

    assert response.status_code == 400, (
        f"{viewset.__name__} returned {response.status_code} for a malformed pk"
    )


@pytest.mark.parametrize("bad_pk", MALFORMED_PKS)
def test_various_malformed_pk_shapes_all_return_400(bad_pk):
    tenant, _ = _tenant_and_workspace(f"T-shape-{bad_pk}")

    response = _retrieve(RequirementViewSet, bad_pk, tenant_id=tenant.id)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "viewset",
    [RequirementViewSet, ArchitectureElementViewSet, TESTCASE_VIEWSET, AdrViewSet],
)
def test_wellformed_but_unknown_uuid_still_returns_404(viewset):
    """The 400 must not swallow the genuine not-found case (the whole point)."""
    tenant, _ = _tenant_and_workspace(f"T404-{viewset.__name__}")

    response = _retrieve(viewset, str(uuid.uuid4()), tenant_id=tenant.id)

    assert response.status_code == 404, (
        f"{viewset.__name__} returned {response.status_code} for an absent UUID"
    )


def test_valid_uuid_of_existing_row_is_unaffected():
    """No-regression: the happy path still resolves."""
    tenant, workspace = _tenant_and_workspace("T-happy")

    response = _retrieve(WorkspaceViewSet, str(workspace.id), tenant_id=tenant.id)

    assert response.status_code == 200
    assert response.data["id"] == str(workspace.id)


# ---------------------------------------------------------------------------
# Response shape + safety properties
# ---------------------------------------------------------------------------


def test_400_body_uses_the_standard_error_envelope():
    """REQ-071: the guard must not bypass the unified {"error": {...}} envelope."""
    tenant, _ = _tenant_and_workspace("T-envelope")

    response = _retrieve(RequirementViewSet, "not-a-uuid", tenant_id=tenant.id)

    assert response.status_code == 400
    assert "error" in response.data
    assert str(response.data["error"]["code"]) == "VALIDATION_ERROR"


def test_400_body_does_not_echo_the_raw_path_segment():
    """No reflection of attacker-controlled input into the response body."""
    tenant, _ = _tenant_and_workspace("T-noecho")
    payload = "<script>alert(1)</script>"

    response = _retrieve(RequirementViewSet, payload, tenant_id=tenant.id)

    assert response.status_code == 400
    response.render()
    assert payload not in response.content.decode(errors="replace")


def test_guard_runs_after_authentication_so_anonymous_is_not_told_400():
    """An unauthenticated caller must still be rejected as unauthenticated.

    If the UUID guard ran before auth, a malformed pk would answer 400 while a
    well-formed one answered 401/403 — handing an anonymous prober a signal.
    """
    response = APIClient().get("/api/v1/requirements/not-a-uuid/")

    assert response.status_code in (401, 403), (
        f"anonymous malformed-pk request returned {response.status_code}"
    )


def test_anonymous_malformed_and_wellformed_pk_are_indistinguishable():
    client = APIClient()

    malformed = client.get("/api/v1/requirements/not-a-uuid/")
    wellformed = client.get(f"/api/v1/requirements/{uuid.uuid4()}/")

    assert malformed.status_code == wellformed.status_code


# ---------------------------------------------------------------------------
# REQ-128 must not regress
# ---------------------------------------------------------------------------


def test_req128_non_uuid_action_segment_still_routes_to_404_not_400():
    """StakeholderNeedViewSet pins ``lookup_value_regex`` to a UUID shape.

    ``GET /api/v1/needs/derive-requirements/`` must keep failing at *routing*
    time (404/405), never reach retrieve() and never 500 — see REQ-128. The new
    guard must not change that, because it never gets the chance to run.
    """
    client = APIClient()

    response = client.get("/api/v1/needs/derive-requirements/")

    assert response.status_code in (401, 403, 404, 405)
