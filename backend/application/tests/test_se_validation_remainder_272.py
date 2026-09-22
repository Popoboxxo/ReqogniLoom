"""#272 — remainder: verification_method gate, v0 semantics, deleted endpoints.

Cluster-5 spec section 7 (the "already satisfied / not satisfied" table's open
rows):

  * §7.2 — ``verification_method`` joins the Extended approval gate,
  * §7.3 — a *manual* link may not be attached to a soft-deleted endpoint,
  * §7.4.2 — ``content_available`` stays ``False`` for the synthetic v0 row and
    ``is_creation_baseline`` is emitted by all three producer sources.
"""
from __future__ import annotations

import pytest

from persistence.models import Artifact, Requirement, TestCase, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User

    tenant = Tenant.objects.create(name="t-272", slug="t-272")
    TenantContext.set_tenant(tenant.id)
    user = User.objects.create(username="u-272", email="u-272@example.com", tenant=tenant)
    from application.workspace_service import WorkspaceService

    def _ctx(workspace_id=None):
        return AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("admin",),
            auth_method=AuthMethod.BEARER_TOKEN,
            workspace_id=workspace_id,
        )

    extended = WorkspaceService().create_workspace(
        _ctx(), name="ws-272-extended", preset="extended"
    )
    return tenant, user, extended, _ctx


def _make_requirement(tenant, workspace, title="Req", **fields):
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, artifact=artifact, title=title, **fields
    )


# ---------------------------------------------------------------------------
# §7.2 — verification_method in the Extended approval gate
# ---------------------------------------------------------------------------


def test_extended_preset_requires_verification_method(env):
    """Extended gains the field; Standard stays lightweight (ADR-04)."""
    from presets.registry import _EXTENDED, _STANDARD
    from presets.services import get_preset

    tenant, user, workspace, ctx_factory = env
    assert "verification_method" in _EXTENDED.mandatory_fields
    assert "verification_method" not in _STANDARD.mandatory_fields

    resolved = get_preset(str(workspace.id))
    assert "verification_method" in resolved.mandatory_fields


def test_verification_method_is_a_live_policy_field(env):
    """It must not be reported as dead configuration."""
    from workflow.precondition_rules import policy_fields_without_consumer

    assert (
        policy_fields_without_consumer(
            ["verification_method"],
            item_type="Requirement",
            attribute_names=(),
            model_field_names=(
                "title",
                "description",
                "acceptance_criteria",
                "verification_method",
            ),
        )
        == []
    )


def test_approval_gate_blocks_a_missing_verification_method(env):
    from workflow.precondition_rules import (
        EC_MANDATORY_FIELDS_MISSING,
        check_mandatory_fields,
    )

    tenant, user, workspace, _ctx = env
    requirement = _make_requirement(tenant, workspace, title="No method")

    error = check_mandatory_fields(
        item_type="Requirement",
        item_id=requirement.id,
        target_state="approved",
        workspace_id=str(workspace.id),
        change_reason="Fixture reason",
    )

    assert error is not None
    code, message = error
    assert code == EC_MANDATORY_FIELDS_MISSING
    assert "verification_method" in message


def test_approval_gate_passes_once_every_field_is_filled(env):
    from workflow.precondition_rules import check_mandatory_fields

    tenant, user, workspace, _ctx = env
    requirement = _make_requirement(
        tenant,
        workspace,
        title="Complete",
        description="Beschreibung",
        acceptance_criteria="Akzeptanzkriterium",
        verification_method="Test",
        type="SyReq",
    )

    assert (
        check_mandatory_fields(
            item_type="Requirement",
            item_id=requirement.id,
            target_state="approved",
            workspace_id=str(workspace.id),
            change_reason="Fixture reason",
        )
        is None
    )


# ---------------------------------------------------------------------------
# §7.4.2 — content_available stays False; is_creation_baseline is explicit
# ---------------------------------------------------------------------------


def test_creation_baseline_entry_keeps_content_unavailable():
    from application.artifact_diff_service import creation_baseline_entry

    entry = creation_baseline_entry()

    assert entry["content_available"] is False
    assert entry["is_creation_baseline"] is True
    assert entry["version"] == 0


def test_all_version_list_producers_flag_the_creation_baseline(env):
    from application.artifact_diff_service import ArtifactDiffService
    from application.artifact_version_service import ArtifactVersionService
    from application.requirement_service import RequirementService

    tenant, user, workspace, ctx_factory = env
    ctx = ctx_factory(workspace.id)
    requirement = RequirementService().create_requirement(
        workspace_id=workspace.id,
        title="Versioned",
        ctx=ctx,
        description="d",
    )

    # Producer (b): the stored revisions.
    revisions = ArtifactVersionService().list_revisions(requirement.artifact_id, ctx)
    assert revisions
    assert all(r["is_creation_baseline"] is False for r in revisions)
    assert all(r["content_available"] is True for r in revisions)

    # Producer (a): the synthetic v0 row, from list_versions.
    versions = ArtifactDiffService().list_versions(requirement.artifact_id, ctx)
    assert versions[0] == {
        "version": 0,
        "label": "Creation baseline",
        "modified_at": None,
        "content_available": False,
        "is_creation_baseline": True,
    }
    assert all(v["is_creation_baseline"] is False for v in versions[1:])

    # Producer (c): the entity-based path (_current_version_entry).
    entity_versions = ArtifactDiffService().list_versions_for_entity(
        "Requirement", requirement.id, ctx
    )
    assert entity_versions[0]["is_creation_baseline"] is True
    assert entity_versions[0]["content_available"] is False
    assert entity_versions[-1]["is_creation_baseline"] is False


# ---------------------------------------------------------------------------
# §7.3 — no manual link onto a soft-deleted endpoint
# ---------------------------------------------------------------------------


def _link_pair(tenant, workspace):
    from application.trace_link_service import TraceLinkService
    from link_types.workspace_store import provision_workspace_link_types

    provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    target = _make_requirement(tenant, workspace, title="Target")
    source_artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="TestCase"
    )
    source = TestCase.objects.create(
        tenant=tenant, artifact=source_artifact, title="Source TC"
    )
    return TraceLinkService(), source, target


def test_manual_link_to_a_deleted_endpoint_is_refused(env):
    from application.base import ValidationError

    tenant, user, workspace, ctx_factory = env
    ctx = ctx_factory(workspace.id)
    service, source, target = _link_pair(tenant, workspace)

    # A live pair creates fine.
    service.create_trace_link(
        source_id=source.artifact_id,
        target_id=target.artifact_id,
        link_type="verifies",
        ctx=ctx,
    )

    target.artifact.lifecycle_status = "outdated"
    target.artifact.save(update_fields=["lifecycle_status"])

    with pytest.raises(ValidationError) as exc_info:
        service.create_trace_link(
            source_id=source.artifact_id,
            target_id=target.artifact_id,
            link_type="verifies",
            ctx=ctx,
        )
    assert "outdated" in str(exc_info.value)


def test_reactivating_the_endpoint_makes_it_linkable_again(env):
    tenant, user, workspace, ctx_factory = env
    ctx = ctx_factory(workspace.id)
    service, source, target = _link_pair(tenant, workspace)

    target.artifact.lifecycle_status = "outdated"
    target.artifact.save(update_fields=["lifecycle_status"])

    target.artifact.lifecycle_status = "active"
    target.artifact.save(update_fields=["lifecycle_status"])

    link = service.create_trace_link(
        source_id=source.artifact_id,
        target_id=target.artifact_id,
        link_type="verifies",
        ctx=ctx,
    )
    assert link is not None


def test_system_writer_path_is_unaffected(env):
    """``manual=False`` (the diagram reconciler) keeps its old behaviour."""
    from application.base import ValidationError

    tenant, user, workspace, ctx_factory = env
    ctx = ctx_factory(workspace.id)
    service, source, target = _link_pair(tenant, workspace)
    target.artifact.lifecycle_status = "outdated"
    target.artifact.save(update_fields=["lifecycle_status"])

    # No exception on the system path (the pair itself is still legal).
    service._check_link_pair(
        source.artifact_id,
        target.artifact_id,
        "verifies",
        source_artifact=source.artifact,
        target_artifact=target.artifact,
        manual=False,
    )
    # Sanity: the manual path does raise for the same pair.
    with pytest.raises(ValidationError):
        service._check_link_pair(
            source.artifact_id,
            target.artifact_id,
            "verifies",
            source_artifact=source.artifact,
            target_artifact=target.artifact,
            manual=True,
        )
