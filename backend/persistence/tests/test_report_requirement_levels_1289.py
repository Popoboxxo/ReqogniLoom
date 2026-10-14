"""#1289 — the ``report_requirement_levels`` backfill command."""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    RequirementLevel,
    RequirementLevelSource,
    Tenant,
    TraceLink,
    Workspace,
)
from persistence.tenancy import TenantContext
from traceability.types import LinkType


@pytest.fixture
def env(db):
    tenant = Tenant.objects.create(name="t-backfill", slug="t-backfill")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="ws")
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        TenantContext.clear_tenant()


def _requirement(env, title="R", level=None, source=None):
    artifact = Artifact.objects.create(
        tenant=env["tenant"],
        workspace=env["workspace"],
        artifact_type="Requirement",
    )
    kwargs = {"tenant": env["tenant"], "artifact": artifact, "title": title}
    if level is not None:
        kwargs["level"] = level
    if source is not None:
        kwargs["level_source"] = source
    return artifact, Requirement.objects.create(**kwargs)


def test_report_flags_a_null_level(env):
    _requirement(env, "No level")
    out = StringIO()
    call_command("report_requirement_levels", stdout=out)
    assert "level NULL" in out.getvalue()


def test_apply_fills_a_null_level_from_the_architecture_allocation(env):
    element_artifact = Artifact.objects.create(
        tenant=env["tenant"],
        workspace=env["workspace"],
        artifact_type="architecture-element",
    )
    element = ArchitectureElement.objects.create(
        tenant=env["tenant"], artifact=element_artifact, title="System"
    )
    artifact, requirement = _requirement(env, "Allocated")
    TraceLink.objects.create(
        tenant=env["tenant"],
        source=artifact,
        target=element_artifact,
        link_type=LinkType.ALLOCATED_TO.value,
    )

    call_command("report_requirement_levels", "--apply", stdout=StringIO())

    requirement.refresh_from_db()
    assert requirement.level == RequirementLevel.L1_SYSTEM
    assert requirement.level_source == RequirementLevelSource.DERIVED


def test_apply_never_overwrites_a_manual_level(env):
    artifact, requirement = _requirement(
        env,
        "Manual",
        level=RequirementLevel.L4_PRESENTATION,
        source=RequirementLevelSource.MANUAL,
    )
    call_command("report_requirement_levels", "--apply", stdout=StringIO())
    requirement.refresh_from_db()
    assert requirement.level == RequirementLevel.L4_PRESENTATION
    assert requirement.level_source == RequirementLevelSource.MANUAL
