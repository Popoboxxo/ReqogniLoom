"""Inventory of the (link_type, source_type, target_type) triples in live data."""
from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from django.core.management.base import CommandError

from link_types.management.commands.inventory_link_types import (
    blocking_triples,
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

    req, arch, goal, tc, issue, risk = (
        artifact("Requirement"),
        artifact("ArchitectureElement"),
        artifact("Goal"),
        artifact("TestCase"),
        artifact("Issue"),
        artifact("Risk"),
    )
    TraceLink.objects.create(tenant=tenant, source=arch, target=req, link_type="satisfies")
    TraceLink.objects.create(tenant=tenant, source=tc, target=req, link_type="verifies")
    TraceLink.objects.create(tenant=tenant, source=req, target=goal, link_type="traces")
    TraceLink.objects.create(tenant=tenant, source=issue, target=arch, link_type="traces")
    TraceLink.objects.create(tenant=tenant, source=risk, target=req, link_type="traces")
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
def test_a_risk_source_is_reported_as_uncovered(workspace_with_links):
    """``Risk --references--> Requirement`` matches no built-in pair.

    ``references`` puts no ``Risk`` on either side (``mitigates`` owns that
    relation under a *different* key, so the key-level legacy mapping of
    ``traces`` cannot reach it), which makes this triple the specimen that
    proves the detection works.

    Two artifact types used to serve that role and no longer can — both are
    regular built-in ``references`` endpoints now: ``Goal`` (fix #237) and
    ``Issue`` (the final-review fix that made ``seed_toothbrush`` runnable on
    a fresh workspace). The last two assertions pin both from the inventory
    side, so a regression that drops either pair fails here too.
    """
    uncovered = uncovered_triples(collect_observed_triples())
    assert any(
        t["link_type"] == "references" and t["source_type"] == "Risk"
        for t in uncovered
    )
    assert not any(t["target_type"] == "Goal" for t in uncovered)
    assert not any(t["source_type"] == "Issue" for t in uncovered)


@pytest.mark.django_db
def test_command_writes_json(workspace_with_links, tmp_path):
    out = tmp_path / "inventory.json"
    call_command("inventory_link_types", "--json", str(out), stdout=StringIO())
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "observed" in payload and "uncovered" in payload
    assert any(t["link_type"] == "allocated-to" for t in payload["observed"])


# ---------- the pre-flight (issue #893) ----------


@pytest.mark.django_db
def test_a_grandfathered_triple_is_uncovered_but_not_blocking(workspace_with_links):
    """The two lists answer different questions.

    ``references`` Risk -> Requirement is not a built-in pair — so it stays in
    ``uncovered``, which is what decides the contents of
    ``GRANDFATHERED_PAIRS``. It *is* grandfathered, so the migration accepts
    it and it must not show up as blocking.
    """
    observed = collect_observed_triples()
    assert any(
        t["link_type"] == "references" and t["source_type"] == "Risk"
        for t in uncovered_triples(observed)
    )
    assert blocking_triples(observed) == []


@pytest.mark.django_db
def test_the_issue_893_rows_are_predicted_as_non_blocking(workspace_with_links):
    """Both QA triples, seen from the pre-flight side, before any upgrade."""
    from persistence.models import Artifact, TraceLink

    ws = workspace_with_links

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(tenant=ws.tenant, workspace=ws, artifact_type=kind)

    req_a, req_b = artifact("Requirement"), artifact("Requirement")
    risk, req_c = artifact("Risk"), artifact("Requirement")
    TraceLink.objects.create(
        tenant=ws.tenant, source=req_a, target=req_b, link_type="traces"
    )
    TraceLink.objects.create(
        tenant=ws.tenant, source=risk, target=req_c, link_type="verifies"
    )

    observed = collect_observed_triples()
    # `verifies` from a Risk is predicted under the type the migration retypes
    # it to, not under the one the row still carries.
    assert ("mitigates", "Risk", "Requirement") in {
        (t["link_type"], t["source_type"], t["target_type"]) for t in observed
    }
    assert blocking_triples(observed) == []


@pytest.mark.django_db
def test_the_command_exits_non_zero_on_a_blocking_triple(workspace_with_links, tmp_path):
    """A deploy script gates on this: fail before ``migrate``, not inside it."""
    from persistence.models import Artifact, TraceLink

    ws = workspace_with_links
    source = Artifact.objects.create(
        tenant=ws.tenant, workspace=ws, artifact_type="Requirement"
    )
    target = Artifact.objects.create(
        tenant=ws.tenant, workspace=ws, artifact_type="Requirement"
    )
    # -> `allocated-to` Requirement -> Requirement, which nothing allows.
    TraceLink.objects.create(
        tenant=ws.tenant, source=source, target=target, link_type="satisfies"
    )

    out = tmp_path / "inventory.json"
    with pytest.raises(CommandError, match="blocking triple"):
        call_command("inventory_link_types", "--json", str(out), stdout=StringIO())

    # The report is still written — the verdict comes last on purpose.
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert any(t["link_type"] == "allocated-to" for t in payload["blocking"])
