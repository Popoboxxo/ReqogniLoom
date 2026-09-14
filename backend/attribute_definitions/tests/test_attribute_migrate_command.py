"""``manage.py attribute_migrate`` interface tests (WS7 #940, spec §7).

The CLI is an operator entry point: it arms the tenant context itself, runs the
same engine as REST/MCP and raises ``CommandError`` on a failed run. These tests
drive dry-run -> apply -> rollback through the real command.
"""
from __future__ import annotations

import json
import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from attribute_definitions.plans import plan_path
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    tenant = Tenant.objects.create(name="cli-t", slug=f"cli-{uuid.uuid4().hex[:8]}")
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant_id=tenant.id,
            workspace=workspace,
            artifact_type="Requirement",
        )
        Requirement.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            title="CLI Req",
            description="Begründung: die CLI muss es können.",
        )
    finally:
        clear_request_tenant()
    yield tenant, workspace, artifact


def _custom_fields(tenant: Tenant, artifact: Artifact) -> dict:
    """Read the artifact under an armed request tenant.

    ``attribute_migrate`` clears the request tenant in its ``finally`` — as an
    operator CLI it owns the context — so a test read has to re-arm it.
    """
    set_request_tenant(tenant.id)
    try:
        return dict(Artifact.objects.get(id=artifact.id).custom_fields or {})
    finally:
        clear_request_tenant()


def _run(*args: str) -> dict:
    out = StringIO()
    call_command("attribute_migrate", *args, "--json", stdout=out)
    return json.loads(out.getvalue())


def test_dry_run_then_apply_then_rollback(env) -> None:
    tenant, _workspace, artifact = env
    plan = str(plan_path("rationale_from_description.yaml"))

    planned = _run("--plan", plan, "--tenant", str(tenant.id))
    assert planned["status"] == "planned"
    assert "rationale" not in _custom_fields(tenant, artifact)

    applied = _run("--plan", plan, "--apply", "--tenant", str(tenant.id))
    assert applied["status"] == "applied"
    assert _custom_fields(tenant, artifact)["rationale"] == "die CLI muss es können."

    rolled_back = _run(
        "--rollback", applied["run_id"], "--tenant", str(tenant.id)
    )
    assert rolled_back["status"] == "rolled_back"
    assert "rationale" not in _custom_fields(tenant, artifact)


def test_plan_and_rollback_are_mutually_exclusive(env) -> None:
    tenant, _workspace, _artifact = env
    with pytest.raises(CommandError):
        call_command(
            "attribute_migrate",
            "--plan",
            "x.yaml",
            "--rollback",
            str(uuid.uuid4()),
            "--tenant",
            str(tenant.id),
        )


def test_missing_args_raise_command_error(env) -> None:
    tenant, _workspace, _artifact = env
    with pytest.raises(CommandError):
        call_command("attribute_migrate", "--tenant", str(tenant.id))


def test_invalid_plan_raises_command_error(env, tmp_path) -> None:
    tenant, _workspace, _artifact = env
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nsteps: []\n", encoding="utf-8")
    with pytest.raises(CommandError):
        call_command(
            "attribute_migrate", "--plan", str(bad), "--tenant", str(tenant.id)
        )
