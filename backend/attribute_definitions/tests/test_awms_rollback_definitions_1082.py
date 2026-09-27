"""AWMS rollback must actually roll back definition changes (issue #1082).

Before this change a plan with ``define_attribute`` wrote into
``ad_global_definition`` and the rollback answered
``{"status": "rolled_back", "restored": 0, "samples": []}`` while the
definitions survived â€” ``_flush()`` only ever wrote a
``pl_attribute_migration_snapshot`` row for *value* changes
(``custom_fields``/``model_fields``), so a definition op left no before-image
at all.

These tests pin the three properties the issue demands:

* a definition that did not exist before the apply is **gone** afterwards
  (deleted, not blanked);
* a definition that did exist is restored to its previous content;
* ``restored: 0`` alongside ``changed: N`` is unreachable â€” an uncovered
  changed target yields ``partially_rolled_back`` plus a named
  ``not_reverted`` entry.

Value-op rollback is pinned too, so the fix cannot have been bought by
regressing the path that already worked.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.utils import timezone

from application.attribute_definition_service import (
    AttributeDefinitionService as DefinitionService,
)
from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import MigrationPlanError
from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from attribute_definitions.schema import AttributeDefinitionConflictError
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Artifact,
    AttributeDefinitionSnapshot,
    AttributeMigrationRun,
    Requirement,
    Tenant,
    Workspace,
)
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_PROBE = "qa_probe_attr"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="awms1082", slug=f"awms1082-{uuid.uuid4().hex[:8]}"
    )


@pytest.fixture
def tenant_context(tenant):
    TenantContext.set_tenant(tenant.id)
    yield tenant.id
    TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant, tenant_context) -> Workspace:
    return Workspace.objects.create(
        tenant_id=tenant.id, name="ws", preset={"name": "standard"}
    )


@pytest.fixture
def admin_ctx(tenant, workspace, tenant_context) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeMigrationService:
    return AttributeMigrationService()


def _global_def(tenant: Tenant, attributes: list[dict] | None = None) -> None:
    GlobalAttributeDefinition.objects.create(
        tenant_id=tenant.id,
        item_type="Requirement",
        preset="standard",
        definition_json={
            "attributes": attributes
            if attributes is not None
            else [{"name": "rationale", "kind": "extended", "type": "text"}]
        },
    )


def _load(tenant: Tenant) -> GlobalAttributeDefinition:
    return GlobalAttributeDefinition.objects.get(
        tenant_id=tenant.id, item_type="Requirement", preset="standard"
    )


def _names(tenant: Tenant) -> list[str]:
    return [a["name"] for a in _load(tenant).definition_json["attributes"]]


def _entry(tenant: Tenant, name: str) -> dict:
    return next(
        a for a in _load(tenant).definition_json["attributes"] if a["name"] == name
    )


def _plan(steps: list[dict], **options) -> dict:
    plan_options = {"idempotent": True, "abort_on_error": True, "audit": True}
    plan_options.update(options)
    return {
        "version": 1,
        "id": f"1082-{uuid.uuid4().hex[:8]}",
        "description": "issue #1082 rollback regression",
        "scope": {
            "tenant": "current",
            "item_type": "Requirement",
            "preset": ["standard"],
            "workspace": "*",
        },
        "mode": "apply",
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


def _requirement(tenant: Tenant, workspace: Workspace, custom: dict) -> Artifact:
    artifact = Artifact.objects.create(
        tenant_id=tenant.id,
        workspace=workspace,
        artifact_type="Requirement",
        custom_fields=custom,
    )
    Requirement.objects.create(
        tenant_id=tenant.id, artifact=artifact, title="R", description="d"
    )
    return artifact


def _custom_fields(artifact_id) -> dict:
    return dict(Artifact.objects.get(id=artifact_id).custom_fields or {})


def _move_step(mode: str = "move") -> dict:
    return {
        "op": "migrate_value",
        "from": {"source": "custom_field", "name": "old"},
        "to": {"source": "custom_field", "name": "new"},
        "mode": mode,
    }


class _StandardPreset:
    preset = "standard"


# ---------------------------------------------------------------------------
# A definition that did not exist is removed again
# ---------------------------------------------------------------------------


def test_apply_with_a_definition_op_snapshots_the_definition_target(
    service, admin_ctx, tenant
):
    """The before-image must exist at apply time, not only at rollback time.

    Regression for the root cause: `_flush()` snapshotted value changes only,
    so no definition row was ever recorded for the run to restore from.
    """
    _global_def(tenant)

    report = service.apply(admin_ctx, _plan([_define_step()]))

    assert report["summary"]["changed"] == 1
    snapshot = AttributeDefinitionSnapshot.objects.get(run_id=report["run_id"])
    assert snapshot.target_key == "global:Requirement:standard"
    assert snapshot.target_kind == "global"
    assert snapshot.existed is True
    assert "rationale" in [
        a["name"] for a in snapshot.definition_json["attributes"]
    ]


def test_rollback_removes_a_definition_the_apply_created(service, admin_ctx, tenant):
    _global_def(tenant)
    assert _PROBE not in _names(tenant)

    applied = service.apply(admin_ctx, _plan([_define_step()]))
    assert _PROBE in _names(tenant)

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "rolled_back"
    assert result["restored"] >= 1
    assert result["restored_definitions"] == 1
    assert result["not_reverted"] == []
    assert _PROBE not in _names(tenant)


def test_restored_zero_over_a_definition_change_is_impossible(
    service, admin_ctx, tenant
):
    """`changed: N` must never come back as `restored: 0` + `rolled_back`."""
    _global_def(tenant)

    applied = service.apply(admin_ctx, _plan([_define_step()]))
    result = service.rollback(admin_ctx, applied["run_id"])

    changed = applied["summary"]["changed"]
    assert changed > 0
    assert not (changed > 0 and result["restored"] == 0), result
    assert result["status"] != "rolled_back" or result["restored"] > 0


def test_rollback_of_a_legacy_run_without_definition_snapshots_is_partial(
    service, admin_ctx, tenant
):
    """A run applied before #1082 has no definition before-image to restore.

    The honest answer is `partially_rolled_back` naming the op â€” not
    `rolled_back` with `restored: 0` over a change that is still in place.
    """
    _global_def(tenant)
    applied = service.apply(admin_ctx, _plan([_define_step()]))
    # Simulate the pre-#1082 state: the report claims a definition change, but
    # no definition snapshot row backs it.
    AttributeDefinitionSnapshot.objects.filter(run_id=applied["run_id"]).delete()

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "partially_rolled_back"
    assert result["restored"] == 0
    assert result["not_reverted"], result
    assert any(
        entry["op"] == "define_attribute" for entry in result["not_reverted"]
    ), result["not_reverted"]
    # ... and the run row carries that status, not a lying "rolled_back".
    assert (
        AttributeMigrationRun.objects.get(id=applied["run_id"]).status
        == "partially_rolled_back"
    )


# ---------------------------------------------------------------------------
# A definition that did exist is restored to its previous content
# ---------------------------------------------------------------------------


def test_rollback_restores_a_dropped_definition_to_its_previous_content(
    service, admin_ctx, tenant
):
    _global_def(
        tenant,
        [
            {"name": "rationale", "kind": "extended", "type": "text"},
            {
                "name": _PROBE,
                "kind": "extended",
                "type": "text",
                "help_text": {"de": "Vorher", "en": "before"},
            },
        ],
    )

    applied = service.apply(
        admin_ctx, _plan([{"op": "drop_attribute", "name": _PROBE, "confirm": _PROBE}])
    )
    assert _PROBE not in _names(tenant)

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "rolled_back"
    assert result["restored_definitions"] == 1
    assert _names(tenant) == ["rationale", _PROBE]
    assert _entry(tenant, _PROBE)["help_text"] == {"de": "Vorher", "en": "before"}


def test_rollback_restores_a_workspace_definition_and_its_customized_flag(
    service, admin_ctx, tenant, workspace
):
    """A workspace override is content *and* flag, not just content.

    `update_workspace` flips `is_customized` on every write; a rollback that
    restored only `definition_json` would leave the row customized and thereby
    permanently excluded from global propagation.
    """
    _global_def(tenant)
    WorkspaceAttributeDefinition.objects.create(
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        item_type="Requirement",
        preset="standard",
        definition_json={
            "attributes": [
                {"name": "rationale", "kind": "extended", "type": "text"},
                {"name": "ws_only", "kind": "extended", "type": "text"},
            ]
        },
        source_global=_load(tenant),
        is_customized=True,
    )

    applied = service.apply(
        admin_ctx, _plan([{"op": "drop_attribute", "name": "ws_only", "confirm": "ws_only"}])
    )
    row = WorkspaceAttributeDefinition.objects.get(
        tenant_id=tenant.id, workspace_id=workspace.id, item_type="Requirement"
    )
    assert "ws_only" not in [a["name"] for a in row.definition_json["attributes"]]

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "rolled_back"
    row.refresh_from_db()
    assert [a["name"] for a in row.definition_json["attributes"]] == [
        "rationale",
        "ws_only",
    ]
    assert row.is_customized is True


def test_a_definition_created_by_the_run_is_deleted_not_blanked(
    service, admin_ctx, tenant
):
    """`existed=False` must DELETE the target row.

    Writing an empty `definition_json` over it would leave a row that claims an
    empty attribute set â€” still a change the operator asked to undo, and one
    that would make the item type resolve to nothing.
    """
    run = AttributeMigrationRun.objects.create(
        tenant_id=tenant.id,
        plan_id="1082-synthetic",
        plan_hash="0" * 64,
        mode="apply",
        status="applied",
        started_at=timezone.now(),
    )
    snapshot = AttributeDefinitionSnapshot.objects.create(
        tenant_id=tenant.id,
        run=run,
        target_key="workspace:synthetic:Requirement",
        target_kind="workspace",
        item_type="Requirement",
        preset="standard",
        workspace_id=uuid.uuid4(),
        existed=False,
        definition_json=None,
    )
    created = WorkspaceAttributeDefinition.objects.create(
        tenant_id=tenant.id,
        workspace_id=snapshot.workspace_id,
        item_type="Requirement",
        preset="standard",
        definition_json={"attributes": []},
    )

    assert service._restore_definition_snapshot(admin_ctx, snapshot) is True
    assert not WorkspaceAttributeDefinition.objects.filter(pk=created.pk).exists()


# ---------------------------------------------------------------------------
# Value-op rollback: no regression
# ---------------------------------------------------------------------------


def test_value_op_rollback_still_restores_custom_fields(
    service, admin_ctx, tenant, workspace
):
    artifact = _requirement(tenant, workspace, {"old": "alpha"})

    applied = service.apply(admin_ctx, _plan([_move_step()]))
    assert _custom_fields(artifact.id) == {"new": "alpha"}

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "rolled_back"
    assert result["restored"] == 1
    assert result["restored_artifacts"] == 1
    assert result["restored_definitions"] == 0
    assert _custom_fields(artifact.id) == {"old": "alpha"}


def test_a_value_only_run_reports_no_unreverted_ops(
    service, admin_ctx, tenant, workspace
):
    _requirement(tenant, workspace, {"old": "alpha"})
    applied = service.apply(admin_ctx, _plan([_move_step("copy")]))

    result = service.rollback(admin_ctx, applied["run_id"])

    assert result["status"] == "rolled_back"
    assert result["not_reverted"] == []


# ---------------------------------------------------------------------------
# reset/ must either reset or say why it cannot
# ---------------------------------------------------------------------------


def test_reset_refuses_a_no_op_reset_instead_of_bumping_the_version(
    service, admin_ctx, tenant, workspace
):
    """The #1082 "reset that does not reset" case.

    After a tenant-wide `define_attribute` the workspace row is not customized
    and already mirrors the global default. Resetting it re-copies the very same
    content: the old code answered 200 + a version bump and the attribute
    survived, so the operator believed the undo had worked.
    """
    _global_def(tenant)
    service.apply(admin_ctx, _plan([_define_step()]))
    assert _PROBE in _names(tenant)

    definitions = DefinitionService()
    with patch("presets.services.get_preset", return_value=_StandardPreset()):
        payload = definitions.resolve(admin_ctx, "Requirement", workspace.id)
        assert _PROBE in [a["name"] for a in payload["attributes"]]
        assert payload["is_customized"] is False

        with pytest.raises(AttributeDefinitionConflictError) as exc:
            definitions.reset_workspace(admin_ctx, "Requirement", workspace.id)

    assert "nothing to reset" in str(exc.value)
    # The definition is still there â€” the point of the conflict is that the
    # operator learns the change lives in the global default, not in this
    # workspace, instead of getting a 200 that changed nothing.
    assert _PROBE in _names(tenant)


def test_reset_still_resets_a_customized_workspace_override(
    service, admin_ctx, tenant, workspace
):
    """The legitimate reset keeps working â€” the guard is narrow on purpose."""
    _global_def(tenant)
    definitions = DefinitionService()
    with patch("presets.services.get_preset", return_value=_StandardPreset()):
        definitions.resolve(admin_ctx, "Requirement", workspace.id)
        definitions.update_workspace(
            admin_ctx,
            "Requirement",
            workspace.id,
            [
                {"name": "rationale", "kind": "extended", "type": "text"},
                {"name": "ws_only", "kind": "extended", "type": "text"},
            ],
        )

        payload = definitions.reset_workspace(admin_ctx, "Requirement", workspace.id)

    assert payload["is_customized"] is False
    assert [a["name"] for a in payload["attributes"]] == ["rationale"]


# ---------------------------------------------------------------------------
# Plan-level: the guard raises a plan error the REST layer already maps
# ---------------------------------------------------------------------------


def test_scope_refusal_is_a_plan_error_not_a_silent_apply(
    service, admin_ctx, tenant, workspace
):
    _global_def(tenant)
    plan = _plan([_define_step()])
    plan["scope"]["workspace"] = [str(workspace.id)]

    with pytest.raises(MigrationPlanError) as exc:
        service.apply(admin_ctx, plan)
    assert "tenant-global" in "; ".join(exc.value.errors)
