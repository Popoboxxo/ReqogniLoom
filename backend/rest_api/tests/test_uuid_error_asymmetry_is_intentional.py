"""Pins the resolved 400-vs-404 UUID-error state for requirements/needs/goals.

History: #710 originally flagged requirements' 400 vs needs' 404 for a
malformed (non-UUID-shaped) path segment as an inconsistency. A first pass
(2026-08-24) investigated and closed it as working-as-intended, reasoning
that needs'/goals' 404 was a deliberate side effect of their
``lookup_value_regex`` (added for #128 / #460 Finding 4 to stop a
custom-action path missing its pk, e.g. ``/needs/derive-requirements/``,
from reaching ``retrieve()`` and 500ing on ``UUID(pk)``) and that removing it
would re-open those two bugs. That reasoning missed that #271's later,
generic ``uuid_url_kwargs`` guard in ``BaseEntityViewSet.initial()`` already
converts *any* malformed pk (including a bare action name reaching
``retrieve()``) into a clean 400 — never the original 500. QA reopened #710
(2026-09-01) on the same finding, which prompted re-verifying that premise;
it does not hold, so needs was aligned with the dominant 400 contract.

Current, deliberate state:
  * requirements (and ~17 other BaseEntityViewSet subclasses) -> 400.
  * needs -> 400 (aligned, #710).
  * goals -> 404, still intentionally different: unlike "derive-requirements",
    "/goals/main/" is a real, guessable *route* a caller might reach for
    (the actual aggregate lives at /main-goals/current/), and 400 would
    misreport "route does not exist" as "malformed id" (#460 Finding 4).
    GoalViewSet keeps its ``lookup_value_regex`` for that reason alone.

If a future decision changes the goals trade-off, update this test's
expectations deliberately, not accidentally.
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


class TestUuidErrorHandlingIsConsistentAcrossEntities:
    """requirements and needs now share the 400-on-malformed-pk contract;
    goals remains a deliberate, documented exception."""

    def test_requirements_400s_on_malformed_pk(self, authed_client):
        """requirements -> 400: the BaseEntityViewSet guard fires."""
        response = authed_client.get("/api/v1/requirements/not-a-uuid/")
        assert response.status_code == 400

    def test_needs_400s_on_malformed_pk(self, authed_client):
        """needs -> 400 (issue #710): aligned with requirements. Before the
        fix, StakeholderNeedViewSet's lookup_value_regex rejected the segment
        at routing time and this answered a generic 404."""
        response = authed_client.get("/api/v1/needs/not-a-uuid/")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_goals_404s_on_non_uuid_shaped_pk_by_design(self, authed_client):
        """goals -> 404, still deliberate: lookup_value_regex rejects the
        segment at routing time to protect the /goals/main/ route-typo case
        (#460 Finding 4), independent of the needs decision above."""
        response = authed_client.get("/api/v1/goals/not-a-uuid/")
        assert response.status_code == 404
