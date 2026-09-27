"""A workspace-scoped plan must not hide a tenant-wide definition change (#1083).

``ad_global_definition`` has no ``workspace_id`` and is unique per
``(tenant, item_type, preset)``; a global edit propagates into every on-default
workspace row of that preset. ``scope.workspace`` used to bound *value* rows
only, so a plan scoped to one workspace changed the definition in **all** of
them â€” while its dry-run answered ``matched: 3``, which reads as "3 presets"
rather than "3 presets x every workspace".

Option (b) from the issue is the fix: the report states the reach outright.
These tests pin that:

* every plan report carries ``target_scope`` and a ``scope_effect`` block;
* every change sample carries its own ``target_scope``;
* a workspace-scoped plan carrying a definition op is **refused** on apply
  (option (c)'s confirmation) unless the plan acknowledges it explicitly;
* a value-only workspace-scoped plan is unaffected.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.attribute_definition_service import (
    AttributeDefinitionService as DefinitionService,
)
from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import (
    DEFINITION_OPS,
    TARGET_SCOPE_TENANT,
    TARGET_SCOPE_WORKSPACE,
    VALUE_OPS,
    MigrationPlanError,
)
from attribute_definitions.models import GlobalAttributeDefinition
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_PROBE = "qa_probe_attr"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="awms1083", slug=f"awms1083-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def tenant_context(tenant):
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.fixture
def workspace_a(tenant, tenant_context) -> Workspace:
    return Workspace.objects.create(
        tenant_id=tenant.id, name="ws-a", preset={"name": "standard"}
    )


@pytest.fixture
def workspace_b(tenant, tenant_context) -> Workspace:
    """A second workspace: the one a scoped plan did NOT select."""
    return Workspace.objects.create(
        tenant_id=tenant.id, name="ws-b", preset={"name": "standard"}
    )


@pytest.fixture
def admin_ctx(tenant, workspace_a, tenant_context) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace_a.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeMigrationService:
    return AttributeMigrationService()


class _StandardPreset:
    preset = "standard"


def _global_def(tenant: Tenant) -> None:
    GlobalAttributeDefinition.objects.create(
        tenant_id=tenant.id,
        item_type="Requirement",
        preset="standard",
        definition_json={
            "attributes": [{"name": "rationale", "kind": "extended", "type": "text"}]
        },
    )


def _names(tenant: Tenant) -> list[str]:
    return [
        a["name"]
        for a in GlobalAttributeDefinition.objects.get(
            tenant_id=tenant.id, item_type="Requirement", preset="standard"
        ).definition_json["attributes"]
    ]


def _plan(steps: list[dict], workspace="*", mode="dry_run", **options) -> dict:
    plan_options = {"idempotent": True, "abort_on_error": True, "audit": True}
    plan_options.update(options)
    return {
        "version": 1,
        "id": f"1083-{uuid.uuid4().hex[:8]}",
        "description": "issue #1083 blast-radius regression",
        "scope": {
            "tenant": "current",
            "item_type": "Requirement",
            "preset": ["standard"],
            "workspace": workspace,
        },
        "mode": mode,
        "options": plan_options,
        "steps": steps,
    }


def _define_step(name: str = _PROBE) -> dict:
    return {
        "op": "define_attribute",
        "name": name,
        "kind": "extended",
        "type": "text",
    }


def _move_step() -> dict:
    return {
        "op": "migrate_value",
        "from": {"source": "custom_field", "name": "old"},
        "to": {"source": "custom_field", "name": "new"},
        "mode": "move",
    }


def _requirement(tenant: Tenant, workspace: Workspace, custom: dict) -> None:
    artifact = Artifact.objects.create(
        tenant_id=tenant.id,
        workspace=workspace,
        artifact_type="Requirement",
        custom_fields=custom,
    )
    Requirement.objects.create(
        tenant_id=tenant.id, artifact=artifact, title="R", description="d"
    )


def _resolved_names(ctx: AuthContext, workspace: Workspace, item_type: str) -> list[str]:
    with patch("presets.services.get_preset", return_value=_StandardPreset()):
        payload = DefinitionService().resolve(ctx, item_type, workspace.id)
    return [a["name"] for a in payload["attributes"]]


# ---------------------------------------------------------------------------
# The op classification the report is built on
# ---------------------------------------------------------------------------


def test_definition_and_value_ops_are_classified_and_disjoint():
    assert DEFINITION_OPS == {
        "define_attribute",
        "drop_attribute",
        "deprecate_attribute",
        "rename_attribute",
        "retype_attribute",
        "requeue_definition",
        "import_scope",
    }
    assert VALUE_OPS == {
        "migrate_value",
        "map_value",
        "backfill_value",
        "derive_value",
        "split_attribute",
        "merge_attribute",
    }
    assert not (DEFINITION_OPS & VALUE_OPS)


# ---------------------------------------------------------------------------
# Dry-run must disclose the reach
# ---------------------------------------------------------------------------


def test_dry_run_reports_the_tenant_reach_of_a_definition_op(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    """`matched: N` may not silently mean "N definitions across 2 workspaces"."""
    _global_def(tenant)

    report = service.dry_run(admin_ctx, _plan([_define_step()]))

    assert report["target_scope"] == TARGET_SCOPE_TENANT
    effect = report["scope_effect"]
    assert effect["definition_target_scope"] == TARGET_SCOPE_TENANT
    assert effect["workspaces_in_tenant"] == 2
    assert effect["workspaces_selected"] == 2
    assert effect["definition_presets"] == ["standard"]
    assert effect["definition_ops"] == ["define_attribute"]
    # A tenant-wide plan is already at the widest scope, so there is no
    # *ignored* scope to warn about — the count that used to be ambiguous is
    # stated outright instead.
    assert effect["warnings"] == []


def test_every_change_sample_states_its_own_reach(service, admin_ctx, tenant):
    _global_def(tenant)

    report = service.dry_run(admin_ctx, _plan([_define_step()]))

    step = report["steps"][0]
    assert step["target_scope"] == TARGET_SCOPE_TENANT
    assert step["changes"], step
    for sample in step["changes"]:
        assert sample["target_scope"] == TARGET_SCOPE_TENANT
        assert sample["field"].startswith("definition:")


def test_the_run_row_persists_the_disclosure(service, admin_ctx, tenant):
    """The audit trail must carry it too, not just the HTTP response."""
    _global_def(tenant)

    report = service.dry_run(admin_ctx, _plan([_define_step()]))

    stored = service.get_run(admin_ctx, report["run_id"])
    assert stored["report"]["target_scope"] == TARGET_SCOPE_TENANT
    assert stored["counts"]["target_scope"] == TARGET_SCOPE_TENANT


def test_a_workspace_scoped_definition_plan_warns_about_the_ignored_scope(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    _global_def(tenant)

    report = service.dry_run(
        admin_ctx, _plan([_define_step()], workspace=[str(workspace_a.id)])
    )

    effect = report["scope_effect"]
    assert effect["scope_workspace"] == [str(workspace_a.id)]
    assert effect["workspaces_selected"] == 1
    assert effect["workspaces_in_tenant"] == 2
    assert effect["value_target_scope"] == TARGET_SCOPE_WORKSPACE
    assert effect["definition_target_scope"] == TARGET_SCOPE_TENANT
    assert any("every workspace" in w for w in effect["warnings"]), effect


# ---------------------------------------------------------------------------
# Apply refuses the un-askable scoping
# ---------------------------------------------------------------------------


def test_apply_refuses_a_workspace_scoped_definition_plan(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    _global_def(tenant)
    plan = _plan([_define_step()], workspace=[str(workspace_a.id)], mode="apply")

    with pytest.raises(MigrationPlanError) as exc:
        service.apply(admin_ctx, plan)

    message = "; ".join(exc.value.errors)
    assert "tenant-global" in message
    assert "allow_tenant_global_definition_ops" in message
    assert _PROBE not in _names(tenant)


def test_dry_run_of_the_same_plan_still_works(
    service, admin_ctx, tenant, workspace_a
):
    """A preview is exactly where an operator has to be able to see this."""
    _global_def(tenant)
    plan = _plan([_define_step()], workspace=[str(workspace_a.id)])

    report = service.dry_run(admin_ctx, plan)

    assert report["status"] == "planned"
    assert report["target_scope"] == TARGET_SCOPE_TENANT


def test_apply_proceeds_with_the_explicit_acknowledgement(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    _global_def(tenant)
    plan = _plan(
        [_define_step()],
        workspace=[str(workspace_a.id)],
        mode="apply",
        allow_tenant_global_definition_ops=True,
    )

    report = service.apply(admin_ctx, plan)

    assert report["summary"]["changed"] == 1
    assert report["target_scope"] == TARGET_SCOPE_TENANT
    assert _PROBE in _names(tenant)


def test_a_value_only_workspace_scoped_plan_is_untouched(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    _requirement(tenant, workspace_a, {"old": "alpha"})
    plan = _plan([_move_step()], workspace=[str(workspace_a.id)], mode="apply")

    report = service.apply(admin_ctx, plan)

    assert report["target_scope"] == TARGET_SCOPE_WORKSPACE
    assert report["scope_effect"]["warnings"] == []
    assert report["summary"]["failed"] == 0
    # ``move`` writes the target and clears the source, so it reports two
    # changed fields on the one row it touched.
    assert report["summary"]["changed"] == 2


# ---------------------------------------------------------------------------
# The reach the report claims is the reach the data has
# ---------------------------------------------------------------------------


def test_a_tenant_wide_definition_apply_reaches_every_workspace_and_says_so(
    service, admin_ctx, tenant, workspace_a, workspace_b
):
    """The #1083 repro, asserted on the disclosure instead of on the surprise.

    A `define_attribute` really does land in every workspace of the preset â€”
    that is the product semantics of the tenant-wide preset catalog, which
    `ad_global_definition` encodes. What must not happen any more is that a
    report lets an operator believe it did not.
    """
    _global_def(tenant)

    report = service.dry_run(admin_ctx, _plan([_define_step()]))

    assert report["scope_effect"]["workspaces_in_tenant"] == 2
    assert report["target_scope"] == TARGET_SCOPE_TENANT

    applied = service.apply(admin_ctx, _plan([_define_step()], mode="apply"))

    assert applied["target_scope"] == TARGET_SCOPE_TENANT
    assert _PROBE in _resolved_names(admin_ctx, workspace_a, "Requirement")
    assert _PROBE in _resolved_names(admin_ctx, workspace_b, "Requirement")
