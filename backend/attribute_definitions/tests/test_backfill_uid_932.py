"""Issue #932 — AWMS backfill of the local uid on pre-#932 rows.

`value_strategy: sequence` (issue #932) allocates the next local readable uid
for a row's `(workspace, item_type)` through the same monotonic allocator the
create path uses, so a legacy row without a `uid` can be brought up to date and
a re-run changes nothing.
"""
from __future__ import annotations

import re
import uuid

import pytest

from application.attribute_migration_service import AttributeMigrationService
from attribute_definitions.migration_plan import load_plan_file
from attribute_definitions.plans import plan_path
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(
        name="uid932", slug=f"uid932-{uuid.uuid4().hex[:8]}"
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


def _legacy_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    """A Requirement as it existed before #932: no local uid."""
    artifact = Artifact.objects.create(
        tenant_id=tenant.id, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant_id=tenant.id,
        workspace=workspace,
        artifact=artifact,
        title=title,
        uid=None,
    )


def _plan(steps: list[dict]) -> dict:
    return {
        "version": 1,
        "id": f"uid932-{uuid.uuid4().hex[:8]}",
        "description": "uid backfill test",
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


def test_the_shipped_uid_backfill_plan_validates(service) -> None:
    payload = load_plan_file(plan_path("backfill_requirement_uid.yaml"))
    result = service.validate_plan(payload)
    assert result["plan"]["scope"]["item_type"] == "Requirement"
    assert result["plan"]["steps"][0]["value_strategy"] == "sequence"


def test_backfill_allocates_uids_and_is_idempotent(service, admin_ctx, tenant, workspace):
    first = _legacy_requirement(tenant, workspace, "First")
    second = _legacy_requirement(tenant, workspace, "Second")
    plan = _plan(
        [
            {
                "op": "backfill_value",
                "target": {"target": "model_field", "name": "uid"},
                "value_strategy": "sequence",
                "only_if": "target_is_empty",
            }
        ]
    )

    report = service.apply(admin_ctx, plan)
    assert report["status"] == "applied", report
    assert report["summary"]["changed"] == 2

    first.refresh_from_db()
    second.refresh_from_db()
    assert re.fullmatch(r"REQ-\d{3}", first.uid or ""), first.uid
    assert re.fullmatch(r"REQ-\d{3}", second.uid or ""), second.uid
    assert first.uid != second.uid

    # Idempotent: a second run finds no empty target.
    again = service.apply(admin_ctx, plan)
    assert again["summary"]["changed"] == 0
    assert again["summary"]["skipped"] == 2


def test_sequence_strategy_fails_closed_on_a_non_uid_target(
    service, admin_ctx, tenant, workspace
):
    _legacy_requirement(tenant, workspace, "Only")
    plan = _plan(
        [
            {
                "op": "backfill_value",
                "target": {"target": "model_field", "name": "title"},
                "value_strategy": "sequence",
                "only_if": "always",
            }
        ]
    )

    report = service.apply(admin_ctx, plan)

    assert report["status"] == "failed"
    assert report["summary"]["failed"] == 1
    assert "target name 'uid'" in str(report)
