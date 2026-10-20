"""Query-budget regression tests for the governance list endpoints (#1398).

``GET /api/v1/issues/``, ``/risks/`` and ``/adrs/`` used to issue a query per
row: the DTO builders reach the backing ``Artifact`` for ``custom_fields`` and
for the Artifact-level ``owner``/``reporter`` system fields, and the
carrier-backed actor selections (``Adr.deciders``, ``Issue.assignee``) plus the
``Risk.owner_user`` FK are relations of their own. None of them were eager
loaded by the service list querysets, so the cost grew with the page size (the
issue reported 121 queries for 55 rows).

The contract these tests pin down: the number of queries a list response costs
must not grow with the number of rows on the page. The scale test compares a
small page with a twice-as-large one and asserts the same count; both tests also
assert an absolute ceiling, so an accidental new per-row accessor is caught even
before the scale comparison is read.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Actor,
    Adr,
    Artifact,
    Issue,
    Risk,
    Tenant,
    User,
    Workspace,
)

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
#: ``page_size`` large enough to return the whole fixture set in one request.
_PAGE = "?page_size=100&workspace_id={workspace_id}"
_ENDPOINTS = ("adrs", "risks", "issues")


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"qb-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"qb-{suffix}", email=f"qb-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="QB WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _seed(
    tenant: Tenant,
    workspace: Workspace,
    user: User,
    *,
    per_type: int,
    attributed: bool = True,
) -> None:
    """Create *per_type* ADRs, Risks and Issues, attributed and assigned.

    With ``attributed`` every row carries what the DTO builders actually read:
    a backing ``Artifact`` with a non-null ``owner``/``reporter`` (NULL FKs
    would not query at all), the carrier-backed actor selection of its item
    type, and (for Risks) the owning user.
    """
    set_request_tenant(tenant.id)
    try:
        owner = reporter = None
        if attributed:
            owner, _ = Actor.objects.get_or_create(
                tenant=tenant, kind="external", display_name="Owner"
            )
            reporter, _ = Actor.objects.get_or_create(
                tenant=tenant, kind="external", display_name="Reporter"
            )
        for index in range(per_type):
            for item_type in ("Adr", "Risk", "Issue"):
                artifact = Artifact.objects.create(
                    tenant=tenant,
                    workspace=workspace,
                    artifact_type=item_type,
                    owner=owner,
                    reporter=reporter,
                )
                if item_type == "Adr":
                    adr = Adr.objects.create(
                        tenant=tenant,
                        artifact=artifact,
                        workspace_id=workspace.id,
                        title=f"ADR {index}",
                    )
                    if owner is not None:
                        adr.deciders.add(owner, reporter)
                elif item_type == "Risk":
                    Risk.objects.create(
                        tenant=tenant,
                        artifact=artifact,
                        workspace_id=workspace.id,
                        title=f"Risk {index}",
                        owner_user=user if attributed else None,
                    )
                else:
                    issue = Issue.objects.create(
                        tenant=tenant,
                        artifact=artifact,
                        workspace_id=workspace.id,
                        title=f"Issue {index}",
                    )
                    if owner is not None:
                        issue.assignee.add(owner)
    finally:
        clear_request_tenant()


def _url(endpoint: str, workspace: Workspace) -> str:
    return f"/api/v1/{endpoint}/" + _PAGE.format(workspace_id=workspace.id)


def _measure(client: APIClient, workspace: Workspace) -> dict[str, int]:
    """Return the query count per endpoint for one full page.

    Each endpoint is called once first: the very first request of a test warms
    per-process caches (tenant, permissions), so measuring on a cold call would
    compare two different baselines rather than two row counts.
    """
    for endpoint in _ENDPOINTS:
        assert client.get(_url(endpoint, workspace)).status_code == 200
    counts: dict[str, int] = {}
    for endpoint in _ENDPOINTS:
        with CaptureQueriesContext(connection) as captured:
            response = client.get(_url(endpoint, workspace))
        assert response.status_code == 200, response.content
        counts[endpoint] = len(captured)
    return counts


def test_governance_list_query_count_is_independent_of_row_count() -> None:
    """Twice the rows must not mean more queries (#1398)."""
    tenant, user, workspace = _scenario()
    client = _client(user)

    _seed(tenant, workspace, user, per_type=10)
    small = _measure(client, workspace)

    _seed(tenant, workspace, user, per_type=10)
    large = _measure(client, workspace)

    # 30 rows vs 60 rows on the same endpoint. Equality is the contract; before
    # the fix the count grew by four queries per row (30 rows already cost 50).
    assert large == small, (
        f"list query counts grew with the row count: {small} for 30 rows vs "
        f"{large} for 60 rows — a per-row accessor is back (#1398)"
    )
    # Absolute ceiling: the whole response (auth/tenant resolution, count,
    # list, batched workflow states, soft-delete filter) is a fixed budget.
    for endpoint, count in large.items():
        assert count <= 20, f"{endpoint} list costs {count} queries for 60 rows"


def test_governance_list_query_budget_without_attribution() -> None:
    """Rows without owner/reporter/assignee must stay within the same budget.

    The issue's 121/55 case was this shape (backing Artifact + carrier
    selection only). It is the smaller baseline, so it guards against a fix
    that only pays off for fully attributed rows.
    """
    tenant, user, workspace = _scenario()
    client = _client(user)

    _seed(tenant, workspace, user, per_type=55, attributed=False)
    counts = _measure(client, workspace)

    for endpoint, count in counts.items():
        assert count <= 20, f"{endpoint} list costs {count} queries for 55 rows"
