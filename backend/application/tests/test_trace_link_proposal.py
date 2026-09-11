"""TraceLink proposal fields and their confirm/discard semantics (spec §5)."""
from __future__ import annotations

from uuid import uuid4

import pytest
from django.utils import timezone

from application.trace_link_service import AgentSelfConfirmError, TraceLinkService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ApiKey
from persistence.models import Artifact, TraceLink, Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def graph(db):
    tenant = Tenant.objects.create(name="t-tl-proposal", slug="t-tl-proposal")
    TenantContext.set_tenant(tenant.id)
    try:
        user = User.objects.create(
            tenant=tenant, username="tl-bot", email="tl@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        src = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        tgt = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        key = ApiKey.objects.create(
            tenant=tenant,
            user=user,
            name="bot",
            key_hash="sha256p1:tl",
            principal_type="agent",
            agent_label="Claude Code",
        )
        yield tenant, src, tgt, key
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_human_link_has_no_proposal_fields(graph):
    tenant, src, tgt, _key = graph
    TenantContext.set_tenant(tenant.id)
    try:
        link = TraceLink.objects.create(
            tenant=tenant, source=src, target=tgt, link_type="derives-from"
        )
    finally:
        TenantContext.clear_tenant()
    assert link.proposed_by is None
    assert link.proposed_at is None
    assert link.is_proposal is False


@pytest.mark.django_db
def test_agent_link_carries_the_proposing_key(graph):
    tenant, src, tgt, key = graph
    now = timezone.now()
    TenantContext.set_tenant(tenant.id)
    try:
        link = TraceLink.objects.create(
            tenant=tenant,
            source=src,
            target=tgt,
            link_type="derives-from",
            proposed_by=key,
            proposed_at=now,
        )
        link.refresh_from_db()
    finally:
        TenantContext.clear_tenant()
    assert link.proposed_by_id == key.id
    assert link.proposed_at == now
    assert link.is_proposal is True


@pytest.mark.django_db
def test_deleting_the_key_keeps_the_link(graph):
    tenant, src, tgt, key = graph
    TenantContext.set_tenant(tenant.id)
    try:
        link = TraceLink.objects.create(
            tenant=tenant,
            source=src,
            target=tgt,
            link_type="derives-from",
            proposed_by=key,
            proposed_at=timezone.now(),
        )
        key.delete()
        link.refresh_from_db()
    finally:
        TenantContext.clear_tenant()
    # SET_NULL: losing the key must never cascade away a real trace edge.
    assert link.proposed_by_id is None


def _ctx(tenant_id, actor_type: str, api_key_id=None) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=api_key_id,
        actor_type=actor_type,
    )


def _create_link(tenant, src, tgt, key):
    TenantContext.set_tenant(tenant.id)
    try:
        return TraceLink.objects.create(
            tenant=tenant,
            source=src,
            target=tgt,
            link_type="derives-from",
            proposed_by=key,
            proposed_at=timezone.now(),
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_confirm_clears_both_proposal_fields(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    TraceLinkService().confirm_proposed_link(link.id, _ctx(tenant.id, "user"))
    link.refresh_from_db()
    assert link.proposed_by_id is None
    assert link.proposed_at is None
    assert link.is_proposal is False


@pytest.mark.django_db
def test_discard_deletes_the_link(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    TraceLinkService().discard_proposed_link(link.id, _ctx(tenant.id, "user"))
    assert not TraceLink.objects.filter(id=link.id).exists()


@pytest.mark.django_db
def test_agent_may_not_confirm(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    with pytest.raises(AgentSelfConfirmError):
        TraceLinkService().confirm_proposed_link(
            link.id, _ctx(tenant.id, "agent", key.id)
        )
    link.refresh_from_db()
    assert link.is_proposal is True


@pytest.mark.django_db
def test_agent_may_not_discard(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    with pytest.raises(AgentSelfConfirmError):
        TraceLinkService().discard_proposed_link(
            link.id, _ctx(tenant.id, "agent", key.id)
        )
    assert TraceLink.objects.filter(id=link.id).exists()


# --- Security review M1 -----------------------------------------------------
# discard_proposed_link refuses an agent, but delete_trace_link reaches the
# very same row. Deleting a proposal and discarding one have identical effect:
# the human review disappears.


@pytest.mark.django_db
def test_agent_may_not_hard_delete_a_proposal(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    with pytest.raises(AgentSelfConfirmError):
        TraceLinkService().delete_trace_link(link.id, _ctx(tenant.id, "agent", key.id))
    assert TraceLink.objects.filter(id=link.id).exists()


@pytest.mark.django_db
def test_human_may_hard_delete_a_proposal(graph):
    tenant, src, tgt, key = graph
    link = _create_link(tenant, src, tgt, key)
    TraceLinkService().delete_trace_link(link.id, _ctx(tenant.id, "user"))
    assert not TraceLink.objects.filter(id=link.id).exists()


@pytest.mark.django_db
def test_agent_may_hard_delete_a_confirmed_link(graph):
    """The guard is about proposals, not about agents deleting anything."""
    tenant, src, tgt, _key = graph
    TenantContext.set_tenant(tenant.id)
    try:
        link = TraceLink.objects.create(
            tenant=tenant, source=src, target=tgt, link_type="derives-from"
        )
    finally:
        TenantContext.clear_tenant()
    TraceLinkService().delete_trace_link(link.id, _ctx(tenant.id, "agent"))
    assert not TraceLink.objects.filter(id=link.id).exists()
