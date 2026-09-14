"""AttributeMigrationService — AWMS engine round trips (WS7 #940, spec §3–§7)."""
from __future__ import annotations

import uuid

import pytest

from application.attribute_migration_service import (
    AttributeMigrationConflict,
    AttributeMigrationNotFound,
    AttributeMigrationService,
)
from application.base import PermissionDeniedError
from attribute_definitions.migration_plan import MigrationPlanError
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    Artifact,
    AttributeMigrationRun,
    AttributeMigrationSnapshot,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    Workspace,
)
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="awms-t", slug=f"awms-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def admin_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def editor_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_id=workspace.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def service() -> AttributeMigrationService:
    return AttributeMigrationService()


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str, custom: dict):
    artifact = Artifact.objects.create(
        tenant_id=tenant.id,
        workspace=workspace,
        artifact_type="Requirement",
        custom_fields=custom,
    )
    return Requirement.objects.create(
        tenant_id=tenant.id, artifact=artifact, title=title, description=f"{title} desc"
    )


@pytest.fixture
def requirements(tenant, workspace):
    TenantContext.set_tenant(tenant.id)
    try:
        first = _make_requirement(tenant, workspace, "R1", {"old": "alpha"})
        second = _make_requirement(tenant, workspace, "R2", {"old": ""})
        return [first, second]
    finally:
        TenantContext.clear_tenant()


def _plan(**overrides):
    base = {
        "id": overrides.pop("id", f"plan-{uuid.uuid4().hex[:8]}"),
        "scope": {"item_type": "Requirement", "preset": ["standard"]},
        "steps": [
            {
                "op": "migrate_value",
                "from": {"source": "custom_field", "name": "old"},
                "to": {"target": "custom_field", "name": "new"},
                "only_if": "source_has_text",
            }
        ],
    }
    base.update(overrides)
    return base


def _reload(requirement) -> Requirement:
    return Requirement.objects.select_related("artifact").get(id=requirement.id)


class TestPermissionGate:
    def test_dry_run_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.dry_run(editor_ctx, _plan())

    def test_apply_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.apply(editor_ctx, _plan())

    def test_rollback_requires_admin(self, service, editor_ctx) -> None:
        with pytest.raises(PermissionDeniedError):
            service.rollback(editor_ctx, uuid.uuid4())

    def test_validate_plan_needs_no_permission(self, service) -> None:
        result = service.validate_plan(_plan())
        assert result["plan"]["mode"] == "dry_run"
        assert len(result["plan_hash"]) == 64


class TestDryRun:
    def test_dry_run_reports_but_writes_no_artifacts(
        self, service, admin_ctx, requirements
    ) -> None:
        report = service.dry_run(admin_ctx, _plan())
        assert report["status"] == "planned"
        assert report["summary"]["changed"] == 1  # R2's source is empty -> only_if
        changed = [
            sample
            for sample in report["steps"][0]["changes"]
            if sample["status"] == "changed"
        ]
        assert changed[0]["before"] == "alpha"
        assert changed[0]["after"] == "alpha"

        for requirement in requirements:
            fresh = _reload(requirement)
            assert "new" not in (fresh.artifact.custom_fields or {})
        assert AttributeMigrationSnapshot.objects.count() == 0

    def test_dry_run_records_a_run_row(self, service, admin_ctx, requirements) -> None:
        report = service.dry_run(admin_ctx, _plan())
        run = AttributeMigrationRun.objects.get(id=report["run_id"])
        assert run.mode == "dry_run"
        assert run.status == "planned"
        assert run.report_json["summary"]["changed"] == 1


class TestApply:
    def test_apply_copies_and_snapshots(
        self, service, admin_ctx, requirements
    ) -> None:
        report = service.apply(admin_ctx, _plan())
        assert report["status"] == "applied"

        first = _reload(requirements[0])
        assert first.artifact.custom_fields["new"] == "alpha"
        assert first.artifact.custom_fields["old"] == "alpha"  # copy keeps source

        assert AttributeMigrationSnapshot.objects.filter(run_id=report["run_id"]).count() == 1
        snapshot = AttributeMigrationSnapshot.objects.get(run_id=report["run_id"])
        assert snapshot.custom_fields == {"old": "alpha"}

    def test_apply_writes_one_audit_entry_per_changed_artifact(
        self, service, admin_ctx, requirements
    ) -> None:
        report = service.apply(admin_ctx, _plan())
        entries = AuditEntry.objects.filter(
            op=AuditEntry.OP_ATTRIBUTE_MIGRATION_APPLY,
            entity_type="Artifact",
        )
        assert entries.count() == 1
        # entity_type="Artifact" audits the generic Artifact row (same id space
        # as ArtifactService/ArtifactService.update), i.e. its artifact_id — not
        # the type row's own PK.
        assert str(entries.first().entity_id) == str(requirements[0].artifact_id)

    def test_audit_false_suppresses_per_artifact_entries_only(
        self, service, admin_ctx, requirements
    ) -> None:
        """WS6/WS7 review (#939/#940) Medium/Low 4: ``options.audit`` is consumed.

        ``audit: false`` suppresses the per-changed-artifact ``AuditEntry``
        (spec §3/§6) while the run's own creation audit always remains.
        """
        report = service.apply(admin_ctx, _plan(options={"audit": False}))
        assert report["status"] == "applied"
        assert report["summary"]["changed"] == 1
        assert not AuditEntry.objects.filter(
            op=AuditEntry.OP_ATTRIBUTE_MIGRATION_APPLY, entity_type="Artifact"
        ).exists()
        assert AuditEntry.objects.filter(
            entity_type="AttributeMigrationRun"
        ).exists()

    def test_apply_is_idempotent(self, service, admin_ctx, requirements) -> None:
        service.apply(admin_ctx, _plan())
        second = service.apply(admin_ctx, _plan())
        assert second["summary"]["changed"] == 0
        assert second["summary"]["skipped"] >= 1

    def test_apply_refuses_a_changed_plan_with_the_same_id(
        self, service, admin_ctx, requirements
    ) -> None:
        service.apply(admin_ctx, _plan(id="stable-id"))
        changed = _plan(id="stable-id", description="now different")
        with pytest.raises(AttributeMigrationConflict):
            service.apply(admin_ctx, changed)

    def test_move_clears_the_source(self, service, admin_ctx, requirements) -> None:
        service.apply(
            admin_ctx,
            _plan(
                steps=[
                    {
                        "op": "migrate_value",
                        "from": {"source": "custom_field", "name": "old"},
                        "to": {"target": "custom_field", "name": "new"},
                        "mode": "move",
                    }
                ]
            ),
        )
        first = _reload(requirements[0])
        assert first.artifact.custom_fields["new"] == "alpha"
        assert "old" not in first.artifact.custom_fields

    def test_scope_tenant_mismatch_is_denied(self, service, admin_ctx, requirements) -> None:
        with pytest.raises(PermissionDeniedError):
            service.apply(
                admin_ctx,
                _plan(scope={"item_type": "Requirement", "tenant": str(uuid.uuid4())}),
            )

    def test_invalid_plan_raises(self, service, admin_ctx) -> None:
        with pytest.raises(MigrationPlanError):
            service.apply(admin_ctx, {"id": "x", "steps": []})


class TestBackfill:
    def test_backfill_constant_only_fills_empty(
        self, service, admin_ctx, tenant, requirements
    ) -> None:
        # Give R1 a priority so only R2 is backfilled. The `requirements`
        # fixture clears the tenant context in its finally block, so the set-up
        # read below needs it re-armed (same pattern as
        # test_backfill_derive_from_link).
        TenantContext.set_tenant(tenant.id)
        try:
            artifact = _reload(requirements[0]).artifact
            Artifact.objects.filter(id=artifact.id).update(priority="Must")
        finally:
            TenantContext.clear_tenant()

        report = service.apply(
            admin_ctx,
            _plan(
                id="backfill-1",
                steps=[
                    {
                        "op": "backfill_value",
                        "target": {"target": "model_field", "name": "priority"},
                        "value_strategy": "constant",
                        "value": "Should",
                    }
                ],
            ),
        )
        assert report["status"] == "applied"
        assert _reload(requirements[0]).artifact.priority == "Must"
        assert _reload(requirements[1]).artifact.priority == "Should"

    def test_backfill_derive_from_link(self, service, admin_ctx, tenant, workspace, requirements) -> None:
        TenantContext.set_tenant(tenant.id)
        try:
            need_artifact = Artifact.objects.create(
                tenant_id=tenant.id,
                workspace=workspace,
                artifact_type="StakeholderNeed",
                custom_fields={"moscow_priority": "Must"},
            )
            StakeholderNeed.objects.create(
                tenant_id=tenant.id, artifact=need_artifact, title="Need"
            )
            TraceLink.objects.create(
                tenant_id=tenant.id,
                source_id=requirements[0].artifact_id,
                target_id=need_artifact.id,
                link_type="derives-from",
            )
        finally:
            TenantContext.clear_tenant()

        service.apply(
            admin_ctx,
            _plan(
                id="backfill-link",
                steps=[
                    {
                        "op": "backfill_value",
                        "target": {"target": "model_field", "name": "priority"},
                        "value_strategy": "derive_from_link",
                        "via": {
                            "link_type": "derives-from",
                            "direction": "outgoing",
                            "source_attr": "moscow_priority",
                        },
                        "fallback": "Should",
                    }
                ],
            ),
        )
        assert _reload(requirements[0]).artifact.priority == "Must"
        # R2 has no link -> fallback.
        assert _reload(requirements[1]).artifact.priority == "Should"


class TestRollback:
    def test_rollback_restores_custom_fields(self, service, admin_ctx, requirements) -> None:
        report = service.apply(admin_ctx, _plan())
        assert _reload(requirements[0]).artifact.custom_fields.get("new") == "alpha"

        result = service.rollback(admin_ctx, report["run_id"])
        assert result["status"] == "rolled_back"
        assert result["restored"] == 1
        restored = _reload(requirements[0])
        assert "new" not in (restored.artifact.custom_fields or {})
        assert restored.artifact.custom_fields["old"] == "alpha"
        run = AttributeMigrationRun.objects.get(id=report["run_id"])
        assert run.status == "rolled_back"

    def test_rollback_restores_model_fields(self, service, admin_ctx, requirements) -> None:
        report = service.apply(
            admin_ctx,
            _plan(
                id="model-rollback",
                steps=[
                    {
                        "op": "backfill_value",
                        "target": {"target": "model_field", "name": "priority"},
                        "value_strategy": "constant",
                        "value": "Should",
                    }
                ],
            ),
        )
        assert _reload(requirements[0]).artifact.priority == "Should"
        service.rollback(admin_ctx, report["run_id"])
        assert _reload(requirements[0]).artifact.priority == ""

    def test_rollback_audits(self, service, admin_ctx, requirements) -> None:
        report = service.apply(admin_ctx, _plan())
        service.rollback(admin_ctx, report["run_id"])
        assert (
            AuditEntry.objects.filter(
                op=AuditEntry.OP_ATTRIBUTE_MIGRATION_ROLLBACK, entity_type="Artifact"
            ).count()
            == 1
        )

    def test_rollback_dry_run_is_rejected(self, service, admin_ctx, requirements) -> None:
        report = service.dry_run(admin_ctx, _plan())
        with pytest.raises(MigrationPlanError):
            service.rollback(admin_ctx, report["run_id"])

    def test_rollback_unknown_run_is_not_found(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeMigrationNotFound):
            service.rollback(admin_ctx, uuid.uuid4())


class TestOtherSteps:
    def test_map_value_rewrites(self, service, admin_ctx, requirements) -> None:
        service.apply(
            admin_ctx,
            _plan(
                id="map-1",
                steps=[
                    {
                        "op": "map_value",
                        "target": {"target": "custom_field", "name": "old"},
                        "value_map": {"alpha": "A"},
                        "fallback": "B",
                    }
                ],
            ),
        )
        assert _reload(requirements[0]).artifact.custom_fields["old"] == "A"
        assert _reload(requirements[1]).artifact.custom_fields["old"] == "B"

    def test_derive_value_from_expression(self, service, admin_ctx, requirements) -> None:
        service.apply(
            admin_ctx,
            _plan(
                id="derive-1",
                steps=[
                    {
                        "op": "derive_value",
                        "target": {"target": "custom_field", "name": "label"},
                        "expression": "{title}-{old}",
                    }
                ],
            ),
        )
        assert _reload(requirements[0]).artifact.custom_fields["label"] == "R1-alpha"

    def test_rename_custom_field_rewrites_values(self, service, admin_ctx, requirements) -> None:
        service.apply(
            admin_ctx,
            _plan(
                id="rename-1",
                steps=[
                    {
                        "op": "rename_attribute",
                        "from": {"source": "custom_field", "name": "old"},
                        "to": {"target": "custom_field", "name": "renamed"},
                    }
                ],
            ),
        )
        first = _reload(requirements[0]).artifact.custom_fields
        assert first["renamed"] == "alpha"
        assert "old" not in first

    def test_drop_attribute_removes_values(self, service, admin_ctx, requirements) -> None:
        service.apply(
            admin_ctx,
            _plan(
                id="drop-1",
                steps=[{"op": "drop_attribute", "name": "old", "confirm": "old"}],
            ),
        )
        assert "old" not in (_reload(requirements[0]).artifact.custom_fields or {})

    def test_verify_assertion_failure_fails_the_run(self, service, admin_ctx, requirements) -> None:
        report = service.apply(
            admin_ctx,
            _plan(id="verify-fail", steps=[{"op": "verify", "assertions": ["changed > 100"]}]),
        )
        assert report["status"] == "failed"
        assert report["summary"]["steps_failed"] == 1


class TestRunHistory:
    def test_list_and_get_runs(self, service, admin_ctx, requirements) -> None:
        report = service.dry_run(admin_ctx, _plan(id="history-1"))
        runs = service.list_runs(admin_ctx)
        assert any(run["id"] == report["run_id"] for run in runs)
        detail = service.get_run(admin_ctx, report["run_id"])
        assert detail["plan_id"] == "history-1"
        assert detail["report"]["summary"]["steps"] >= 1

    def test_get_unknown_run_is_not_found(self, service, admin_ctx) -> None:
        with pytest.raises(AttributeMigrationNotFound):
            service.get_run(admin_ctx, uuid.uuid4())
