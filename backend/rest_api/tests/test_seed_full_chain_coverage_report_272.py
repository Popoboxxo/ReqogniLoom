"""#272 / AC-272-F3 — the full-chain seed is measurable through the product's own report.

``seed_full_chain`` builds the Extended-rigor golden path (Goals, Needs,
L1/L2 Requirements, ArchitectureElements, TestCases, TestRuns, Baseline,
ChangeRequest). That data set is only *evidence* if the shipped reporting
surface can read it: a fixture nobody can measure through the API proves the
seed writes rows, not that the chain it encodes is reportable.

AC-272-F3 therefore pairs the two halves — seed via the management command,
measure via ``GET /api/v1/requirements/coverage-report/`` — and asserts that the
result is non-empty (``total > 0``, ``covered > 0``) *and* internally
consistent with the per-requirement rows the same response carries. No absolute
counts are pinned: the seed's documented volume may legitimately grow, so the
test asserts relations between values instead of a frozen total.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_SEEDED_WORKSPACE_NAME = "SysEng Full-Chain Demo"


@pytest.fixture
def seeded_admin_client(db) -> tuple[APIClient, Workspace]:
    """Seed the full chain, then return an admin ``APIClient`` + its workspace.

    Tenant determinism: the command takes no tenant argument and resolves both
    the tenant and the well-known ``admin`` user itself (it seeds into the
    admin's tenant, falling back to ``Tenant.objects.first()``). The fixture
    therefore does **not** assume its own tenant wins — a module-scoped fixture
    elsewhere in the suite can commit a ``Tenant``/``User`` pair *outside* the
    per-test transaction, and this file's ``--reuse-db`` databases routinely
    hold more than one tenant. It reads the tenant back from the workspace the
    command actually produced, which is both order-independent and the only
    tenant the coverage report below can legitimately be asked about.

    Context: the command is request-less and clears the armed tenant context in
    its own ``finally``, so the fixture re-arms it for the ``UserRole`` write
    (``set_request_tenant`` arms both the thread-local app context *and* the
    Postgres RLS session variable) and clears it again unconditionally.

    Auth: the command's ``admin``/``full-chain-reviewer`` users have unusable
    passwords by design, so the fixture creates its own password-bearing admin
    and logs in through the real JWT endpoint.
    """
    from django.core.management import call_command

    call_command("seed_full_chain", verbosity=0)

    # The command owns tenant selection, so the workspace it produced — not a
    # fixture-chosen tenant — is the one the coverage report can legitimately be
    # asked about. Pinning a fixture tenant here went red as soon as the
    # database held a leftover tenant from another module.
    workspace = Workspace.unscoped.get(name=_SEEDED_WORKSPACE_NAME)
    tenant = Tenant.objects.get(pk=workspace.tenant_id)

    username = f"coverage-admin-{uuid.uuid4().hex[:8]}"
    try:
        set_request_tenant(tenant.id)
        user = User.objects.create(
            username=username,
            email=f"{username}@t.test",
            tenant=tenant,
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client, workspace


def test_full_chain_seed_is_measurable_via_the_coverage_report(
    seeded_admin_client: tuple[APIClient, Workspace],
) -> None:
    """AC-272-F3: the seeded chain shows up in the Requirement coverage report."""
    client, workspace = seeded_admin_client

    resp = client.get(
        "/api/v1/requirements/coverage-report/",
        {"workspace_id": str(workspace.id)},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()

    summary = body["summary"]
    assert summary["total"] > 0, "the seeded workspace has no Requirements"
    assert summary["covered"] > 0, "no seeded Requirement is verified by a TestCase"
    assert summary["covered"] <= summary["total"]

    # Internal consistency: the summary must agree with the rows it ships with.
    rows = body["requirements"]
    assert summary["total"] == len(rows)
    assert summary["covered"] == sum(1 for row in rows if row["covered"])
