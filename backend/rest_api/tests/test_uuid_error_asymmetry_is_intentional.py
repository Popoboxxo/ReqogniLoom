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
(2026-09-01) on the same finding, so needs was aligned with the dominant 400
contract by dropping the regex.

Dropping it alone was not enough: REQ-128's own contract is 404/405 for
``/needs/derive-requirements/`` (400 says "malformed id" about what is really
an unknown route), and the E2E specs that pin it started failing. The guard
therefore now separates the two cases itself — a pk segment matching one of
the ViewSet's declared detail-action ``url_path``s is 404, everything else
malformed stays 400 — which holds both contracts without a router-level regex
(see rest_api/tests/test_needs_routing.py).

Current, deliberate state:
  * requirements (and ~17 other BaseEntityViewSet subclasses) -> 400.
  * needs -> 400 (aligned, #710).
  * goals -> 404, still intentionally different: unlike "derive-requirements",
    "/goals/main/" is not an action name at all but a guessable *route* alias
    a caller might reach for (the actual aggregate lives at
    /main-goals/current/). Only a router-level rule can decline it, so
    GoalViewSet keeps its ``lookup_value_regex`` (#460 Finding 4).

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

    def test_needs_404s_on_a_bare_detail_action_segment(self, authed_client):
        """REQ-128: the 400 above must not swallow the routing-miss case.

        ``/needs/derive-requirements/`` is the action route without its pk, so
        it stays 404 — the property the removed regex used to provide.
        """
        response = authed_client.get("/api/v1/needs/derive-requirements/")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_goals_404s_on_non_uuid_shaped_pk_by_design(self, authed_client):
        """goals -> 404, still deliberate: lookup_value_regex rejects the
        segment at routing time to protect the /goals/main/ route-typo case
        (#460 Finding 4), independent of the needs decision above."""
        response = authed_client.get("/api/v1/goals/not-a-uuid/")
        assert response.status_code == 404
