"""DATA-05 (audit-review 2026-09) — self-links and trace-link integrity.

Findings:
  * 157 — ``trace_link_manager`` only ran a per-link-type cycle check; a
    self-link (an artifact linked to itself) was never rejected anywhere.
  * 182 — the live ``pl_tracelink`` table bound ``link_type`` to nothing at the
    DB level.

Covers:
  (a) app-level self-link guard in TraceLinkManager.create / batch_create,
  (b) ``TraceLinkService`` maps the guard to a validation error (=> HTTP 400),
  (c) the DB CHECK ``ck_tracelink_no_self_link`` rejects a raw self-link insert
      that bypasses the manager,
  (d) a normal link still works,
  (e) a tenant-invented ``link_type`` is still accepted (the CHECK must never
      whitelist the built-in keys), while an empty one is rejected,
  (f) both CHECKs are present in ``pg_constraint``.

REQ-L2-TE-001, REQ-L2-TE-002, REQ-L2-TE-011.
"""
from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction

from application.requirement_service import RequirementService
from application.trace_link_service import TraceLinkService
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.errors import ValidationError
from persistence.models import (
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.exceptions import SelfLinkError
from traceability.trace_link_manager import TraceLinkManager
from traceability.tests.conftest import active_tenant, make_artifact

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> TraceLinkManager:
    return TraceLinkManager()


# ---------------------------------------------------------------------------
# Service-path fixtures (mirrors application/tests/test_allocation.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def service_tenant() -> Tenant:
    return Tenant.objects.create(name="DATA-05 Tenant", slug="data05-tenant")


@pytest.fixture
def service_user(service_tenant: Tenant) -> User:
    return User.objects.create(
        username="data05-user",
        email="data05@example.com",
        tenant=service_tenant,
    )


@pytest.fixture
def service_workspace(service_tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(service_tenant.id)
    try:
        ws = Workspace.objects.create(tenant=service_tenant, name="DATA-05 WS")
        # Link validation is always-on; an unprovisioned workspace rejects every
        # trace link before the manager's self-link guard is ever reached.
        provision_workspace_link_types(
            workspace_id=ws.id, tenant_id=service_tenant.id
        )
        return ws
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def service_ctx(service_user: User) -> AuthContext:
    return AuthContext(
        user_id=service_user.id,
        tenant_id=service_user.tenant_id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="DATA-05 Tenant",
    )


# ---------------------------------------------------------------------------
# (a) App-level self-link guard
# ---------------------------------------------------------------------------

def test_manager_create_rejects_self_link(manager, tenant_a, workspace_a):
    """A self-link is rejected with a domain error before any DB round-trip."""
    with active_tenant(tenant_a):
        artifact = make_artifact(tenant_a, workspace_a, "requirement")

        with pytest.raises(SelfLinkError) as exc_info:
            manager.create(
                source_id=artifact.id,
                target_id=artifact.id,
                link_type="references",
            )

        assert str(artifact.id) in str(exc_info.value)
        assert not TraceLink.objects.filter(source_id=artifact.id).exists()


def test_batch_create_rejects_self_link(manager, tenant_a, workspace_a):
    """The bulk write path rejects a self-link with a domain error too."""
    with active_tenant(tenant_a):
        artifact = make_artifact(tenant_a, workspace_a, "requirement")

        with pytest.raises(SelfLinkError):
            manager.batch_create(
                [
                    {
                        "source_id": artifact.id,
                        "target_id": artifact.id,
                        "link_type": "references",
                    }
                ]
            )

        assert not TraceLink.objects.filter(source_id=artifact.id).exists()


# ---------------------------------------------------------------------------
# (b) Service maps the guard to a validation error (HTTP 400)
# ---------------------------------------------------------------------------

def test_service_maps_self_link_to_validation_error(service_ctx, service_workspace):
    """TraceLinkService re-maps SelfLinkError to ValidationError (=> 4xx)."""
    req_svc = RequirementService()
    link_svc = TraceLinkService()

    requirement = req_svc.create_requirement(
        workspace_id=service_workspace.id,
        title="Self-referential requirement",
        ctx=service_ctx,
    )

    with pytest.raises(ValidationError) as exc_info:
        link_svc.create_trace_link(
            source_id=requirement.id,
            target_id=requirement.id,
            link_type="refines",
            ctx=service_ctx,
        )

    assert "self" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# (c) DB CHECK rejects a raw self-link insert
# ---------------------------------------------------------------------------

def test_db_check_rejects_raw_self_link(tenant_a, workspace_a):
    """A raw ORM insert that bypasses the manager cannot create a self-link."""
    with active_tenant(tenant_a):
        artifact = make_artifact(tenant_a, workspace_a, "requirement")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                TraceLink.objects.create(
                    source=artifact,
                    target=artifact,
                    link_type="references",
                    tenant=tenant_a,
                )


# ---------------------------------------------------------------------------
# (d) Normal link still works
# ---------------------------------------------------------------------------

def test_normal_link_still_works(manager, tenant_a, workspace_a):
    with active_tenant(tenant_a):
        source = make_artifact(tenant_a, workspace_a, "requirement")
        target = make_artifact(tenant_a, workspace_a, "requirement")

        link = manager.create(
            source_id=source.id,
            target_id=target.id,
            link_type="references",
        )

    assert link.pk is not None
    assert link.source_id == source.id
    assert link.target_id == target.id


# ---------------------------------------------------------------------------
# (e) Tenant-extensible link_type stays accepted; empty is rejected
# ---------------------------------------------------------------------------

def test_tenant_invented_link_type_is_accepted(tenant_a, workspace_a):
    """The CHECK must not whitelist built-ins — a tenant key stays insertable.

    Link types are a tenant-extensible catalog
    (``WorkspaceLinkTypeDefinition.key`` is a free string), so a CHECK listing
    the built-in keys would break every extension. This inserts a raw row with
    an invented key to prove the DB constraint accepts it.
    """
    with active_tenant(tenant_a):
        source = make_artifact(tenant_a, workspace_a, "requirement")
        target = make_artifact(tenant_a, workspace_a, "requirement")

        link = TraceLink.objects.create(
            source=source,
            target=target,
            link_type="conflicts-with",
            tenant=tenant_a,
        )

    assert link.pk is not None
    assert link.link_type == "conflicts-with"


def test_db_rejects_empty_link_type(tenant_a, workspace_a):
    """The safe ``link_type`` integrity equivalent: the column is never blank."""
    with active_tenant(tenant_a):
        source = make_artifact(tenant_a, workspace_a, "requirement")
        target = make_artifact(tenant_a, workspace_a, "requirement")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                TraceLink.objects.create(
                    source=source,
                    target=target,
                    link_type="",
                    tenant=tenant_a,
                )


# ---------------------------------------------------------------------------
# (f) Constraints are live in pg_constraint
# ---------------------------------------------------------------------------

def test_db_constraints_exist_in_pg_constraint():
    """Acceptance: ``pg_constraint`` contains the DATA-05 CHECKs."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'pl_tracelink'::regclass
              AND contype = 'c'
            """
        )
        names = {row[0] for row in cursor.fetchall()}

    assert "ck_tracelink_no_self_link" in names
    assert "ck_tracelink_link_type_nonempty" in names
