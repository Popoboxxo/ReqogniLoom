"""#1262 — audit rule catalogue endpoint + server-side finding filters.

Covers ``GET /api/v1/audit/rules/`` (metadata for every registered rule) and the
``rule_id`` / ``severity`` / ``artifact_type`` filters on
``GET /api/v1/workspaces/<id>/audit/``.
"""
from __future__ import annotations

import uuid

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact

pytestmark = pytest.mark.django_db


def test_rule_catalogue_endpoint_lists_every_registered_rule(authed_client) -> None:
    resp = authed_client.get("/api/v1/audit/rules/")
    assert resp.status_code == 200, resp.content
    rules = resp.json()["rules"]
    ids = {rule["rule_id"] for rule in rules}
    # A representative old rule and the new #1268 rule are both present.
    assert "TRACE-P1" in ids
    assert "IFC-001" in ids

    entry = next(rule for rule in rules if rule["rule_id"] == "TRACE-P1")
    for key in (
        "rule_id",
        "title",
        "description",
        "severity",
        "standard_ref",
        "remediation_hint",
        "active_tiers",
        "is_scope_aware",
        "deferred",
    ):
        assert key in entry, key
    assert entry["title"]
    assert entry["severity"] in ("blocker", "warning")
    assert "standard" in entry["active_tiers"]


def test_rule_catalogue_requires_authentication(client) -> None:
    resp = client.get("/api/v1/audit/rules/")
    assert resp.status_code in (401, 403)


def _make_icd(tenant, workspace) -> object:
    from icd.models import Icd

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Icd"
        )
        return Icd.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace_id=workspace.id,
            name="Filter ICD",
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
        )
    finally:
        clear_request_tenant()


def test_rule_id_filter_returns_only_that_rule(authed_client, tenant, workspace) -> None:
    """An unanchored ICD produces an IFC-001 finding; the filter isolates it."""
    _make_icd(tenant, workspace)

    resp = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/audit/?rule_id=IFC-001"
    )
    assert resp.status_code == 200, resp.content
    findings = resp.json()["findings"]
    assert findings, "expected the unanchored ICD to raise IFC-001"
    assert {f["rule_id"] for f in findings} == {"IFC-001"}


def test_unknown_severity_filter_is_rejected(authed_client, workspace) -> None:
    resp = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/audit/?severity=catastrophic"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_artifact_type_filter_selects_by_artifact(authed_client, tenant, workspace) -> None:
    _make_icd(tenant, workspace)

    resp = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/audit/?artifact_type=Icd"
    )
    assert resp.status_code == 200, resp.content
    findings = resp.json()["findings"]
    assert findings
    assert all(f["rule_id"] == "IFC-001" for f in findings)


def test_counts_are_ground_truth_totals_for_a_filtered_run(
    authed_client, tenant, workspace
) -> None:
    """#1382: a filter narrows the *run*; ``counts`` describes every match.

    The production path builds a predicate with ``finding_matches`` and passes
    it to ``AuditService.run_audit(finding_filter=...)``, which applies it
    *before* the cap, the totals and the window. ``counts`` therefore agrees
    with ``total_*_available`` — and, on an unwindowed run, with the returned
    ``findings``. (``apply_report_filters`` is the deprecated post-hoc helper,
    not the path exercised here.)
    """
    _make_icd(tenant, workspace)

    resp = authed_client.get(
        f"/api/v1/workspaces/{workspace.id}/audit/?rule_id=IFC-001"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()

    assert body["counts"]["total"] == body["total_findings_available"]
    assert body["counts"]["blockers"] == body["total_blockers_available"]
    assert body["counts"]["warnings"] == body["total_warnings_available"]
    assert body["counts"]["total"] == len(body["findings"])
    page_counts = body["page_counts"]
    assert page_counts["total"] == len(body["findings"])
    assert page_counts["blockers"] + page_counts["warnings"] == page_counts["total"]
    assert body["next_offset"] is None
