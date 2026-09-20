"""AWMS operations completed for issue #930.

Covers the three ops that moved out of ``UNSUPPORTED_OPS`` into the engine:

* ``deprecate_attribute`` — flag a definition entry as superseded, values kept;
* ``export_scope`` — serialize a definition scope into the run report;
* ``import_scope`` — merge a definition document into a target scope.

``derive_entity`` stays unsupported (blocked on #393) and is asserted as such.
"""
from __future__ import annotations

import uuid

import pytest

from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import (
    OPS,
    UNSUPPORTED_OPS,
    MigrationPlanError,
    normalize_plan,
)
from attribute_definitions.models import GlobalAttributeDefinition
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="awms930", slug=f"awms930-{uuid.uuid4().hex[:8]}"
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


def _global_def(tenant: Tenant, attributes: list[dict] | None = None):
    return GlobalAttributeDefinition.objects.create(
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


def _plan(steps: list[dict]) -> dict:
    return {
        "version": 1,
        "id": f"930-{uuid.uuid4().hex[:8]}",
        "description": "issue #930 op test",
        "scope": {
            "tenant": "current",
            "item_type": "Requirement",
            "preset": ["standard"],
            "workspace": "*",
        },
        "mode": "apply",
        "options": {"idempotent": True, "abort_on_error": True, "audit": True},
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Plan schema
# ---------------------------------------------------------------------------


def test_the_three_ops_are_supported_and_only_derive_entity_stays_blocked():
    assert "deprecate_attribute" in OPS
    assert "export_scope" in OPS
    assert "import_scope" in OPS
    assert "deprecate_attribute" not in UNSUPPORTED_OPS
    assert set(UNSUPPORTED_OPS) == {"derive_entity", "rollback"}


def test_deprecate_attribute_requires_a_reason():
    with pytest.raises(MigrationPlanError) as exc:
        normalize_plan(_plan([{"op": "deprecate_attribute", "name": "rationale"}]))
    assert any("reason" in error for error in exc.value.errors)


def test_deprecate_attribute_rejects_unknown_keys():
    with pytest.raises(MigrationPlanError) as exc:
        normalize_plan(
            _plan(
                [
                    {
                        "op": "deprecate_attribute",
                        "name": "rationale",
                        "reason": "x",
                        "typo": True,
                    }
                ]
            )
        )
    assert any("typo" in error for error in exc.value.errors)


def test_export_scope_requires_exactly_one_scope_key():
    with pytest.raises(MigrationPlanError) as exc:
        normalize_plan(
            _plan(
                [
                    {
                        "op": "export_scope",
                        "source": {
                            "preset": "standard",
                            "workspace": str(uuid.uuid4()),
                        },
                    }
                ]
            )
        )
    assert any("exactly one" in error for error in exc.value.errors)


def test_import_scope_normalizes_its_scope_ref_and_collision_mode():
    document = {
        "schema_version": 1,
        "item_type": "Requirement",
        "attributes": [],
    }
    normalized = normalize_plan(
        _plan(
            [
                {
                    "op": "import_scope",
                    "document": document,
                    "target": {"preset": "standard"},
                    "on_collision": "rename",
                }
            ]
        )
    )
    step = normalized["steps"][0]
    assert step["target"] == {"kind": "preset", "value": "standard"}
    assert step["on_collision"] == "rename"


def test_import_scope_rejects_an_unknown_collision_mode():
    with pytest.raises(MigrationPlanError) as exc:
        normalize_plan(
            _plan(
                [
                    {
                        "op": "import_scope",
                        "document": {"schema_version": 1, "attributes": []},
                        "target": {"preset": "standard"},
                        "on_collision": "explode",
                    }
                ]
            )
        )
    assert any("on_collision" in error for error in exc.value.errors)


# ---------------------------------------------------------------------------
# deprecate_attribute
# ---------------------------------------------------------------------------


def test_deprecate_attribute_flags_the_entry_and_is_idempotent(
    service, admin_ctx, tenant
):
    _global_def(tenant)
    plan = _plan(
        [{"op": "deprecate_attribute", "name": "rationale", "reason": "superseded"}]
    )

    first = service.apply(admin_ctx, plan)
    assert first["summary"]["failed"] == 0
    assert first["summary"]["changed"] == 1
    entry = _load(tenant).definition_json["attributes"][0]
    assert entry["deprecated"] is True
    assert entry["deprecated_reason"] == "superseded"

    # Idempotent: the second run skips, it does not change the row again.
    second = service.apply(admin_ctx, plan)
    assert second["summary"]["changed"] == 0
    assert second["summary"]["skipped"] == 1


def test_deprecate_attribute_dry_run_writes_nothing(service, admin_ctx, tenant):
    _global_def(tenant)
    plan = _plan(
        [{"op": "deprecate_attribute", "name": "rationale", "reason": "x"}]
    )

    report = service.dry_run(admin_ctx, plan)

    assert report["summary"]["changed"] == 1
    assert not _load(tenant).definition_json["attributes"][0].get("deprecated")


def test_deprecate_attribute_skips_a_missing_attribute(service, admin_ctx, tenant):
    _global_def(tenant)
    plan = _plan(
        [{"op": "deprecate_attribute", "name": "does_not_exist", "reason": "x"}]
    )

    report = service.apply(admin_ctx, plan)

    assert report["summary"]["failed"] == 0
    assert report["summary"]["skipped"] == 1


# ---------------------------------------------------------------------------
# export_scope / import_scope
# ---------------------------------------------------------------------------


def test_export_scope_returns_the_definition_document(service, admin_ctx, tenant):
    _global_def(tenant)
    plan = _plan([{"op": "export_scope", "source": {"preset": "standard"}}])

    report = service.dry_run(admin_ctx, plan)

    document = report["steps"][0]["document"]
    assert document["item_type"] == "Requirement"
    assert [attribute["name"] for attribute in document["attributes"]] == ["rationale"]


def test_import_scope_merges_the_document_into_the_target(service, admin_ctx, tenant):
    _global_def(tenant)
    document = {
        "schema_version": 1,
        "item_type": "Requirement",
        "attributes": [
            {
                "name": "rationale",
                "kind": "extended",
                "type": "text",
                "help_text": {"de": "Begruendung", "en": "Rationale"},
            }
        ],
    }
    plan = _plan(
        [
            {
                "op": "import_scope",
                "document": document,
                "target": {"preset": "standard"},
                "on_collision": "overwrite",
            }
        ]
    )

    report = service.apply(admin_ctx, plan)

    assert report["summary"]["failed"] == 0
    assert report["summary"]["changed"] == 1
    entry = next(
        attribute
        for attribute in _load(tenant).definition_json["attributes"]
        if attribute["name"] == "rationale"
    )
    assert entry["help_text"]["en"] == "Rationale"


def test_import_scope_dry_run_writes_nothing(service, admin_ctx, tenant):
    _global_def(tenant)
    document = {
        "schema_version": 1,
        "item_type": "Requirement",
        "attributes": [
            {
                "name": "rationale",
                "kind": "extended",
                "type": "text",
                "help_text": {"de": "d", "en": "new"},
            }
        ],
    }
    plan = _plan(
        [
            {
                "op": "import_scope",
                "document": document,
                "target": {"preset": "standard"},
                "on_collision": "overwrite",
            }
        ]
    )

    report = service.dry_run(admin_ctx, plan)

    assert report["summary"]["changed"] == 1
    entry = _load(tenant).definition_json["attributes"][0]
    assert entry.get("help_text", {}).get("en") != "new"
