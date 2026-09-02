"""
Tests for the ``cleanup_e2e_artifacts`` management command (#711).

E2E/CI specs create workspaces named ``e2e-*`` (see
``e2e/helpers/auth.ts::createIsolatedWorkspace`` and
``e2e/tests/visual-regression.spec.ts``) that are never cleaned up. This
command purges them by name prefix + age, dry-run by default, mirroring
``cleanup_revoked_api_keys``.
"""
from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from baseline.models import BaselineSnapshot
from persistence.models import Artifact, Requirement, Workspace
from persistence.tests.factories import active_tenant, make_requirement, make_workspace

pytestmark = pytest.mark.django_db


def _age_workspace(workspace: Workspace, *, created_days_ago: int) -> Workspace:
    Workspace.unscoped.filter(pk=workspace.pk).update(
        created_at=timezone.now() - timedelta(days=created_days_ago)
    )
    workspace.refresh_from_db()
    return workspace


def test_dry_run_reports_but_does_not_delete():
    with active_tenant() as tenant:
        e2e_ws = _age_workspace(
            make_workspace(tenant, name="e2e-visual-regression-1234"), created_days_ago=5
        )
        real_ws = _age_workspace(
            make_workspace(tenant, name="Real Project Workspace"), created_days_ago=5
        )

        out = io.StringIO()
        call_command("cleanup_e2e_artifacts", stdout=out)

        assert "1 workspace" in out.getvalue()
        remaining_ids = set(Workspace.unscoped.values_list("id", flat=True))
        assert e2e_ws.id in remaining_ids, "dry-run must not delete anything"
        assert real_ws.id in remaining_ids


def test_apply_deletes_only_e2e_prefixed_workspaces_older_than_threshold():
    with active_tenant() as tenant:
        old_e2e = _age_workspace(
            make_workspace(tenant, name="e2e-isolated-old"), created_days_ago=10
        )
        recent_e2e = _age_workspace(
            make_workspace(tenant, name="e2e-isolated-recent"), created_days_ago=0
        )
        real_ws = _age_workspace(
            make_workspace(tenant, name="Real Project Workspace"), created_days_ago=10
        )

        out = io.StringIO()
        call_command("cleanup_e2e_artifacts", "--apply", "--older-than-days=1", stdout=out)

        remaining_ids = set(Workspace.unscoped.values_list("id", flat=True))
        assert old_e2e.id not in remaining_ids
        assert recent_e2e.id in remaining_ids
        assert real_ws.id in remaining_ids
        assert "Deleted 1" in out.getvalue()


def test_apply_cascades_to_artifacts_and_requirements():
    with active_tenant() as tenant:
        ws = _age_workspace(
            make_workspace(tenant, name="e2e-visual-regression-9999"), created_days_ago=10
        )
        requirement = make_requirement(ws, title="Stale req")
        artifact_id = requirement.artifact_id

        call_command("cleanup_e2e_artifacts", "--apply", "--older-than-days=1")

        assert Workspace.unscoped.filter(pk=ws.pk).count() == 0
        assert Artifact.unscoped.filter(workspace_id=ws.pk).count() == 0
        assert Requirement.unscoped.filter(artifact_id=artifact_id).count() == 0


def test_apply_skips_workspace_with_baseline_instead_of_crashing():
    """Issue #711 follow-up: baselines are append-only (``bl_raise_immutable``
    DB trigger, ADR-L3-BL003-01) and cannot be deleted, even indirectly via
    the ``Artifact`` -> ``BaselineSnapshot`` ``on_delete=CASCADE`` FK. The
    command must skip such a workspace (leave it, its artifact and its
    baseline fully intact) and keep processing the rest of the batch instead
    of raising ``InternalError: Baselines are immutable`` and aborting.
    """
    with active_tenant() as tenant:
        ws_with_baseline = _age_workspace(
            make_workspace(tenant, name="e2e-has-baseline"), created_days_ago=10
        )
        requirement = make_requirement(ws_with_baseline, title="Baselined req")
        BaselineSnapshot.unscoped.create(
            workspace_id=ws_with_baseline.id,
            name="snap-1",
            scope="document",
            artifact=requirement.artifact,
            tenant=tenant,
        )
        ws_without_baseline = _age_workspace(
            make_workspace(tenant, name="e2e-no-baseline"), created_days_ago=10
        )

        out = io.StringIO()
        call_command(
            "cleanup_e2e_artifacts", "--apply", "--older-than-days=1", stdout=out
        )

        remaining_ids = set(Workspace.unscoped.values_list("id", flat=True))
        assert ws_with_baseline.id in remaining_ids, (
            "workspace with a baseline must survive, not crash the command"
        )
        assert ws_without_baseline.id not in remaining_ids
        assert Artifact.unscoped.filter(workspace_id=ws_with_baseline.id).exists()
        assert BaselineSnapshot.unscoped.filter(
            workspace_id=ws_with_baseline.id
        ).exists()
        assert "Deleted 1" in out.getvalue()
        assert "Skipped 1" in out.getvalue()


def test_custom_name_prefix_is_respected():
    with active_tenant() as tenant:
        matched = _age_workspace(
            make_workspace(tenant, name="ci-scratch-1"), created_days_ago=10
        )
        unmatched = _age_workspace(
            make_workspace(tenant, name="e2e-isolated-1"), created_days_ago=10
        )

        call_command(
            "cleanup_e2e_artifacts", "--apply", "--older-than-days=1", "--name-prefix=ci-"
        )

        remaining_ids = set(Workspace.unscoped.values_list("id", flat=True))
        assert matched.id not in remaining_ids
        assert unmatched.id in remaining_ids
