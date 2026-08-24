"""Pins the documented, intentional difference between requirements' 400
and needs'/goals' 404 for a malformed (non-UUID-shaped) path segment.

See #710 for the QA report that initially flagged this as inconsistent,
and #128 / #460 (Finding 4) for why needs/goals deliberately differ:
their lookup_value_regex must 404 on non-UUID segments so a custom-action
path (e.g. /needs/derive-requirements/, missing its pk) doesn't get
mistaken for a malformed pk and reach retrieve()'s UUID(pk) call.

DO NOT "fix" this asymmetry by removing needs'/goals' lookup_value_regex --
doing so re-opens #128 and #460 Finding 4 (a 500 on custom-action paths
without a pk). If a future decision changes this trade-off, update this
test's expectations deliberately, not accidentally.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext


pytestmark = pytest.mark.django_db


@pytest.fixture()
def _setup(authed_client: APIClient, tenant: Tenant, workspace: Workspace):
    """Expose the authenticated client and tenant for each test."""
    return authed_client, tenant, workspace


class TestUuidErrorAsymmetryIsIntentional:
    """Document the 400-vs-404 asymmetry as intentional behaviour.

    requirements (BaseEntityViewSet) returns 400 on a malformed pk because
    its uuid_url_kwargs guard in initial() catches non-UUID segments early.

    needs / goals (StakeholderNeedViewSet / GoalViewSet) return 404 because
    their lookup_value_regex constrains the detail route to UUID-shaped
    segments only -- non-UUID segments never reach retrieve() and instead
    404 at the router level.  This was itself the fix for #128 and #460
    Finding 4 (a custom-action path like /needs/derive-requirements/ was
    being parsed as a pk and 500ing on UUID()).
    """

    def test_requirements_400s_on_malformed_pk(self, authed_client):
        """requirements -> 400: the BaseEntityViewSet guard fires."""
        response = authed_client.get("/api/v1/requirements/not-a-uuid/")
        assert response.status_code == 400

    def test_needs_404s_on_non_uuid_shaped_pk_by_design(self, authed_client):
        """needs -> 404: lookup_value_regex rejects the segment at routing time."""
        response = authed_client.get("/api/v1/needs/not-a-uuid/")
        assert response.status_code == 404

    def test_goals_404s_on_non_uuid_shaped_pk_by_design(self, authed_client):
        """goals -> 404: lookup_value_regex rejects the segment at routing time."""
        response = authed_client.get("/api/v1/goals/not-a-uuid/")
        assert response.status_code == 404
