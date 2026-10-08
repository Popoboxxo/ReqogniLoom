"""
Tests for the ADR-019 generic proposal lifecycle facade (WP2).

Covers the testable core promises of ADR-019 Decision 7:

* 7(a) a producer run leaves exactly one ``open`` suggestion with full,
  server-set provenance;
* 7(b) accept delegates to the existing M2 path and stamps ``accepted`` +
  ``decided_*``;
* 7(c) an agent accepting its own proposal fails loudly (no silent accept);
* 7(e) reject stamps ``rejected`` and destroys no target artifact;
* 7(f) production is fail-closed outside an agent/API-key context
  (``ProducerContextRequiredError``).
* plus O7 edge dedup, payload/provenance trust, and RBAC/tenant scoping.

Test-DB conventions mirror ``application/tests/test_trace_link_catalog_validation.py``
(real ``Artifact`` rows + ``provision_workspace_link_types``) and
``application/tests/test_trace_link_proposal.py`` (proposal link helpers).
"""
from __future__ import annotations

import pytest
from django.utils import timezone

from application.base import PermissionDeniedError, ProducerContextRequiredError
from application.suggestion_adapters import (
    SuggestionKindNotEnabledError,
    build_adapter_registry,
)
from application.suggestion_service import SuggestionService
from application.trace_link_service import AgentSelfConfirmError
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ApiKey
from link_types.workspace_store import provision_workspace_link_types
from persistence.models import Artifact, Suggestion, Tenant, TraceLink, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    """Provisioned tenant/workspace/artifacts/key plus agent + human contexts."""
    tenant = Tenant.objects.create(name="t-suggestion", slug="t-suggestion")
    TenantContext.set_tenant(tenant.id)
    try:
        owner = User.objects.create(
            tenant=tenant, username="sugg-owner", email="sugg@example.com"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)

        def artifact(kind: str) -> Artifact:
            return Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type=kind
            )

        source = artifact("Requirement")
        target = artifact("Requirement")

        api_key = ApiKey.objects.create(
            tenant=tenant,
            user=owner,
            name="suggestion-bot",
            key_hash="sha256p1:suggestion",
            principal_type="agent",
            agent_label="Claude Test",
        )

        agent_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
            actor_type="agent",
            agent_label="Claude Test",
        )
        human_ctx = AuthContext(
            user_id=owner.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.BEARER_TOKEN,
        )

        yield {
            "tenant": tenant,
            "owner": owner,
            "workspace": workspace,
            "source": source,
            "target": target,
            "api_key": api_key,
            "agent_ctx": agent_ctx,
            "human_ctx": human_ctx,
        }
    finally:
        TenantContext.clear_tenant()


def _trace_link_payload(source: Artifact, target: Artifact, **extra) -> dict:
    payload = {
        "rule_id": "TRACE-P1",
        "source_artifact_id": str(source.id),
        "ranked_candidates": [
            {"artifact_id": str(target.id), "artifact_type": "Requirement", "score": 3},
        ],
        "rationale": "keyword overlap",
    }
    payload.update(extra)
    return payload


def _propose(env, payload=None) -> dict:
    return SuggestionService().propose(
        "trace_link",
        env["agent_ctx"],
        workspace_id=env["workspace"].id,
        payload=payload
        if payload is not None
        else _trace_link_payload(env["source"], env["target"]),
        producer="traceability.suggest_links",
    )


# ---------------------------------------------------------------------------
# 7(a) production + provenance
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_propose_leaves_one_open_suggestion_with_server_provenance(env):
    result = _propose(env)

    assert result["status"] == "open"
    assert result["kind"] == "trace_link"
    assert result["producer"] == "traceability.suggest_links"
    # Provenance is server-set from the ApiKey/principal, never from the body.
    assert result["proposed_by"] == str(env["api_key"].id)
    assert result["proposed_at"] is not None
    assert result["decided_by"] is None
    assert result["decided_at"] is None

    assert Suggestion.objects.filter(workspace_id=env["workspace"].id).count() == 1

    # The receipt points at a real, still-unconfirmed M2 proposal link.
    link = TraceLink.objects.get(id=result["target_item_id"])
    assert link.is_proposal is True
    assert link.proposed_by_id == env["api_key"].id
    assert link.link_type == "derives-from"


@pytest.mark.django_db
def test_propose_provenance_ignores_caller_supplied_fields(env):
    """A tampered payload cannot fake `proposed_by` (server-set wins)."""
    payload = _trace_link_payload(
        env["source"],
        env["target"],
        proposed_by="00000000-0000-0000-0000-000000000000",
        decided_by="00000000-0000-0000-0000-000000000001",
        status="accepted",
    )
    result = _propose(env, payload=payload)

    assert result["proposed_by"] == str(env["api_key"].id)
    assert result["status"] == "open"
    assert result["decided_by"] is None


@pytest.mark.django_db
def test_payload_link_type_is_not_materialized(env):
    """`link_type` comes from rule_id, not from an injected payload field."""
    payload = _trace_link_payload(env["source"], env["target"], link_type="diagram-ref")
    result = _propose(env, payload=payload)

    link = TraceLink.objects.get(id=result["target_item_id"])
    assert link.link_type == "derives-from"


# ---------------------------------------------------------------------------
# 7(f) producer-context fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_produce_fails_closed_for_human_bearer_context(env):
    service = SuggestionService()
    with pytest.raises(ProducerContextRequiredError):
        service.propose(
            "trace_link",
            env["human_ctx"],
            workspace_id=env["workspace"].id,
            payload=_trace_link_payload(env["source"], env["target"]),
        )

    # Nothing was written: no receipt, no unstamped link.
    assert Suggestion.objects.filter(workspace_id=env["workspace"].id).count() == 0
    assert (
        TraceLink.objects.filter(source=env["source"], target=env["target"]).count()
        == 0
    )


@pytest.mark.django_db
def test_create_fails_closed_for_human_bearer_context(env):
    service = SuggestionService()
    with pytest.raises(ProducerContextRequiredError):
        service.create(
            kind="trace_link",
            ctx=env["human_ctx"],
            workspace_id=env["workspace"].id,
            payload={},
        )


# ---------------------------------------------------------------------------
# 7(b) accept delegates + stamps
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_delegates_and_stamps_accepted(env):
    produced = _propose(env)

    result = SuggestionService().accept(produced["id"], env["human_ctx"])

    assert result["status"] == "accepted"
    assert result["decided_by"] == str(env["owner"].id)
    assert result["decided_at"] is not None

    # The delegated M2 confirm really ran: the link is no longer a proposal.
    link = TraceLink.objects.get(id=produced["target_item_id"])
    assert link.is_proposal is False
    assert link.proposed_by_id is None
    assert link.proposed_at is None

    # No open suggestion remains.
    assert SuggestionService().list_open(env["workspace"].id, env["human_ctx"]) == []


@pytest.mark.django_db
def test_accept_is_idempotent(env):
    produced = _propose(env)
    service = SuggestionService()

    first = service.accept(produced["id"], env["human_ctx"])
    second = service.accept(produced["id"], env["human_ctx"])

    assert first["status"] == "accepted"
    assert second["status"] == "accepted"


# ---------------------------------------------------------------------------
# 7(c) agent self-accept fails loudly
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_agent_may_not_accept_its_own_proposal(env):
    produced = _propose(env)

    with pytest.raises(AgentSelfConfirmError):
        SuggestionService().accept(produced["id"], env["agent_ctx"])

    # The refusal is not silent: the receipt stays open, the link stays proposed.
    suggestion = Suggestion.objects.get(id=produced["id"])
    assert suggestion.status == "open"
    link = TraceLink.objects.get(id=produced["target_item_id"])
    assert link.is_proposal is True


# ---------------------------------------------------------------------------
# 7(e) reject destroys no target artifact
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reject_stamps_rejected_and_destroys_no_artifact(env):
    produced = _propose(env)

    result = SuggestionService().reject(
        produced["id"], env["human_ctx"], reason="not a real derivation"
    )

    assert result["status"] == "rejected"
    assert result["decided_by"] == str(env["owner"].id)
    assert result["decided_at"] is not None

    # Both linked artifacts survive untouched.
    assert Artifact.objects.filter(
        id__in=[env["source"].id, env["target"].id]
    ).count() == 2
    # The M2 discard removed the *proposal link* only.
    assert not TraceLink.objects.filter(id=produced["target_item_id"]).exists()


@pytest.mark.django_db
def test_agent_may_not_reject_its_own_proposal(env):
    produced = _propose(env)
    with pytest.raises(AgentSelfConfirmError):
        SuggestionService().reject(produced["id"], env["agent_ctx"])
    assert Suggestion.objects.get(id=produced["id"]).status == "open"


# ---------------------------------------------------------------------------
# O7 edge dedup
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_repeated_producer_run_dedupes_on_the_edge(env):
    first = _propose(env)
    second = _propose(env)

    # Exactly one proposal link on the edge survived the second run.
    links = TraceLink.objects.filter(
        source=env["source"], target=env["target"], link_type="derives-from"
    )
    assert links.count() == 1
    assert first["target_item_id"] == second["target_item_id"]

    # B-02/O7: the durable receipt is reused too — the second run must NOT
    # insert a second ``open`` row for the same edge (otherwise the inbox
    # accumulates un-rejectable / silent-no-op duplicates).
    open_receipts = Suggestion.objects.filter(
        workspace_id=env["workspace"].id, status=Suggestion.Status.OPEN
    )
    assert open_receipts.count() == 1
    assert first["id"] == second["id"]


# ---------------------------------------------------------------------------
# Registry coverage + dormant kinds
# ---------------------------------------------------------------------------


def test_registry_covers_all_four_adr_019_kinds():
    assert set(build_adapter_registry()) == {
        "artifact_create",
        "trace_link",
        "interview_grounding",
        "context_edge",
    }


@pytest.mark.django_db
def test_dormant_kind_is_registered_but_not_enabled(env):
    with pytest.raises(SuggestionKindNotEnabledError):
        SuggestionService().propose(
            "artifact_create",
            env["agent_ctx"],
            workspace_id=env["workspace"].id,
            payload={},
        )


@pytest.mark.django_db
def test_unknown_kind_is_rejected(env):
    from application.base import ValidationError

    with pytest.raises(ValidationError):
        SuggestionService().propose(
            "not_a_kind",
            env["agent_ctx"],
            workspace_id=env["workspace"].id,
            payload={},
        )


# ---------------------------------------------------------------------------
# list_open: RBAC + tenant scoping
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_open_requires_read_permission(env):
    _propose(env)
    no_role_ctx = AuthContext(
        user_id=env["owner"].id,
        tenant_id=env["tenant"].id,
        active_roles=(),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    with pytest.raises(PermissionDeniedError):
        SuggestionService().list_open(env["workspace"].id, no_role_ctx)


@pytest.mark.django_db
def test_list_open_is_tenant_scoped(env):
    _propose(env)

    other_tenant = Tenant.objects.create(name="t-other", slug="t-other")
    other_user = User.objects.create(
        tenant=other_tenant, username="other", email="other@example.com"
    )
    other_ctx = AuthContext(
        user_id=other_user.id,
        tenant_id=other_tenant.id,
        active_roles=("viewer",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )

    assert SuggestionService().list_open(env["workspace"].id, other_ctx) == []
    assert len(SuggestionService().list_open(env["workspace"].id, env["human_ctx"])) == 1


# ---------------------------------------------------------------------------
# Unrelated sanity: proposal age helper stays honest
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accept_uses_current_wall_clock(env):
    produced = _propose(env)
    before = timezone.now()
    result = SuggestionService().accept(produced["id"], env["human_ctx"])
    after = timezone.now()

    from datetime import datetime

    decided_at = datetime.fromisoformat(result["decided_at"])
    assert before <= decided_at <= after
