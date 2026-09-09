"""Inventory of the (link_type, source_type, target_type) triples in live data."""
from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from link_types.management.commands.inventory_link_types import (
    collect_observed_triples,
    uncovered_triples,
)
from persistence.tenancy import TenantContext


@pytest.fixture
def workspace_with_links(db):
    from persistence.models import Artifact, Tenant, TraceLink, Workspace

    tenant = Tenant.objects.create(name="inventory")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(tenant=tenant, workspace=ws, artifact_type=kind)

    req, arch, goal, tc, issue = (
        artifact("Requirement"),
        artifact("ArchitectureElement"),
        artifact("Goal"),
        artifact("TestCase"),
        artifact("Issue"),
    )
    TraceLink.objects.create(tenant=tenant, source=arch, target=req, link_type="satisfies")
    TraceLink.objects.create(tenant=tenant, source=tc, target=req, link_type="verifies")
    TraceLink.objects.create(tenant=tenant, source=req, target=goal, link_type="traces")
    TraceLink.objects.create(tenant=tenant, source=issue, target=arch, link_type="traces")
    yield ws
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_legacy_keys_are_reported_under_their_new_name(workspace_with_links):
    observed = {t["link_type"] for t in collect_observed_triples()}
    assert "satisfies" not in observed
    assert "allocated-to" in observed
    assert "references" in observed


@pytest.mark.django_db
def test_swapped_keys_are_reported_with_swapped_endpoints(workspace_with_links):
    entry = next(
        t for t in collect_observed_triples() if t["link_type"] == "allocated-to"
    )
    assert entry["source_type"] == "Requirement"
    assert entry["target_type"] == "ArchitectureElement"


@pytest.mark.django_db
def test_counts_are_aggregated(workspace_with_links):
    entry = next(t for t in collect_observed_triples() if t["link_type"] == "verifies")
    assert entry["count"] == 1


@pytest.mark.django_db
def test_covered_triples_are_not_reported_as_uncovered(workspace_with_links):
    uncovered = {t["link_type"] for t in uncovered_triples(collect_observed_triples())}
    assert "verifies" not in uncovered
    assert "allocated-to" not in uncovered


@pytest.mark.django_db
def test_an_issue_source_is_reported_as_uncovered(workspace_with_links):
    """``Issue --references--> ArchitectureElement`` matches no built-in pair.

    Of the four triples OFFENE FRAGE 1 grandfathered, ``Issue`` is the only
    one with no built-in successor at all — no type puts an ``Issue`` on
    either side — so it is what this test uses to prove the detection works.
    ``Goal`` used to serve that role and no longer can: it is a regular
    built-in ``references`` endpoint now (fix #237), which the second
    assertion pins from the inventory side.
    """
    uncovered = uncovered_triples(collect_observed_triples())
    assert any(
        t["link_type"] == "references" and t["source_type"] == "Issue"
        for t in uncovered
    )
    assert not any(t["target_type"] == "Goal" for t in uncovered)


@pytest.mark.django_db
def test_command_writes_json(workspace_with_links, tmp_path):
    out = tmp_path / "inventory.json"
    call_command("inventory_link_types", "--json", str(out), stdout=StringIO())
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "observed" in payload and "uncovered" in payload
    assert any(t["link_type"] == "allocated-to" for t in payload["observed"])
