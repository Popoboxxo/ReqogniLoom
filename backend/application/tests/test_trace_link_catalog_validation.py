"""create_trace_link validates against the workspace catalog, always.

Task 11 of docs/superpowers/plans/2026-09-03-traceability-semantik.md: the
``se_mode`` gate and the ``SE_CORE_ARTIFACT_TYPES`` allow-list are gone, so
every workspace and every artifact type is validated by
``link_types.catalog.validate_link_pair``.
"""
from __future__ import annotations

import uuid

import pytest

from application.trace_link_service import TraceLinkService
from link_types.workspace_store import provision_workspace_link_types
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Artifact, Tenant, Workspace
    from presets.models import WorkspacePresetConfig

    tenant = Tenant.objects.create(name="catalog-validation")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind
        )

    # user_id stays None: TraceLink.created_by is a real FK to pl_user and this
    # suite is about the catalog gate, not about authorship.
    ctx = AuthContext(
        user_id=None,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=ws.id,
    )
    yield {
        "tenant": tenant,
        "workspace": ws,
        "ctx": ctx,
        "artifact": artifact,
        "preset_model": WorkspacePresetConfig,
    }
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_a_valid_link_is_created(env):
    svc = TraceLinkService()
    tc, req = env["artifact"]("TestCase"), env["artifact"]("Requirement")
    link = svc.create_trace_link(tc.id, req.id, "verifies", env["ctx"])
    assert link.link_type == "verifies"


@pytest.mark.django_db
def test_verifies_from_a_risk_is_rejected_in_dev_mode_too(env):
    """Audit finding U2: Risk was outside SE_CORE_ARTIFACT_TYPES and passed."""
    env["preset_model"].objects.update_or_create(
        workspace_id=env["workspace"].id,
        defaults={
            "tenant_id": env["tenant"].id,
            "terminology_profile": "dev_mode",
        },
    )
    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="verifies"):
        svc.create_trace_link(risk.id, req.id, "verifies", env["ctx"])


@pytest.mark.django_db
def test_validation_applies_without_any_preset_config_row(env):
    """No WorkspacePresetConfig used to mean 'skip enforcement' entirely."""
    env["preset_model"].objects.filter(workspace_id=env["workspace"].id).delete()
    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError):
        svc.create_trace_link(risk.id, req.id, "verifies", env["ctx"])


@pytest.mark.django_db
def test_a_retired_link_type_is_rejected(env):
    svc = TraceLinkService()
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="Unknown link type 'satisfies'"):
        svc.create_trace_link(arch.id, req.id, "satisfies", env["ctx"])


@pytest.mark.django_db
def test_allocated_to_only_runs_requirement_to_architecture(env):
    svc = TraceLinkService()
    req, arch = env["artifact"]("Requirement"), env["artifact"]("ArchitectureElement")
    assert svc.create_trace_link(req.id, arch.id, "allocated-to", env["ctx"])
    with pytest.raises(ValidationError, match="allocated-to"):
        svc.create_trace_link(arch.id, req.id, "allocated-to", env["ctx"])


@pytest.mark.django_db
def test_architecture_to_architecture_allocation_is_gone(env):
    svc = TraceLinkService()
    a, b = env["artifact"]("ArchitectureElement"), env["artifact"]("ArchitectureElement")
    with pytest.raises(ValidationError, match="allocated-to"):
        svc.create_trace_link(a.id, b.id, "allocated-to", env["ctx"])


@pytest.mark.django_db
def test_derives_from_now_accepts_architecture_pairs(env):
    """Inherited from the retired `refines` type."""
    svc = TraceLinkService()
    a, b = env["artifact"]("ArchitectureElement"), env["artifact"]("ArchitectureElement")
    assert svc.create_trace_link(a.id, b.id, "derives-from", env["ctx"])


@pytest.mark.django_db
def test_diagram_ref_is_still_rejected_on_the_manual_path(env):
    svc = TraceLinkService()
    diagram, req = env["artifact"]("Diagram"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="system-managed"):
        svc.create_trace_link(diagram.id, req.id, "diagram-ref", env["ctx"])


@pytest.mark.django_db
def test_a_deactivated_type_cannot_be_used(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    disabled = builtin_definition("mitigates")
    disabled["active"] = False
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, env["workspace"].id, "mitigates", disabled
    )

    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="Unknown link type"):
        svc.create_trace_link(risk.id, req.id, "mitigates", env["ctx"])


@pytest.mark.django_db
def test_a_workspace_override_widens_what_is_accepted(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    widened = builtin_definition("mitigates")
    widened["allowed_pairs"].append(
        {"source_type": "Risk", "target_type": "TestCase"}
    )
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, env["workspace"].id, "mitigates", widened
    )

    svc = TraceLinkService()
    risk, tc = env["artifact"]("Risk"), env["artifact"]("TestCase")
    assert svc.create_trace_link(risk.id, tc.id, "mitigates", env["ctx"])


@pytest.mark.django_db
def test_a_missing_endpoint_is_a_hard_error_not_a_skipped_gate(env):
    """The old gate returned early when an endpoint row was absent."""
    from application.base import NotFoundError

    svc = TraceLinkService()
    req = env["artifact"]("Requirement")
    with pytest.raises(NotFoundError):
        svc._check_link_pair(req.id, uuid.uuid4(), "verifies")


def test_the_se_matrix_is_gone():
    import traceability.types as types

    for removed in (
        "SE_LINK_SEMANTICS",
        "SE_CORE_ARTIFACT_TYPES",
        "SAME_TYPE",
        "check_se_link_semantics",
    ):
        assert not hasattr(types, removed), f"{removed} must be deleted"
