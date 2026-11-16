"""GH-1882 — audit findings carry the standard their rule derives from.

``GET /api/v1/workspaces/<ws>/audit/`` answered findings without
``standard_ref``/``standard_title`` although the rule catalogue
(``GET /api/v1/audit/rules/``) holds that metadata — and ``ALLOC-P1`` had no
``standard_ref`` at all (it carried the dead ``standard_basis`` attribute,
which no consumer reads).

The fix resolves the metadata from the catalogue at read time (the rule stays
the single source of truth — nothing is duplicated onto the finding) and gives
``ALLOC-P1`` a reference in the same scheme as its neighbours (ADR-028 D9).

Covered here:

* every finding returned by the endpoint carries a non-empty ``standard_ref``,
* every registered rule in the catalogue declares one (the generic invariant,
  so a new rule cannot ship without it),
* an unregistered rule id degrades to ``None`` instead of raising (no KeyError).
"""
from __future__ import annotations

import uuid

import pytest

from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact

pytestmark = pytest.mark.django_db


def _make_unanchored_icd(tenant, workspace) -> None:
    """An ICD with no anchor element — the IFC-001 trigger used by #1262."""
    from icd.models import Icd

    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Icd"
        )
        Icd.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace_id=workspace.id,
            name="GH-1882 ICD",
            source_element_id=uuid.uuid4(),
            target_element_id=uuid.uuid4(),
        )
    finally:
        clear_request_tenant()


def test_every_catalogue_rule_declares_a_standard_ref(authed_client) -> None:
    """Generic invariant: no rule may ship without a standard reference.

    This is the assertion that would have caught ``ALLOC-P1``'s empty field.
    """
    resp = authed_client.get("/api/v1/audit/rules/")
    assert resp.status_code == 200, resp.content
    rules = resp.json()["rules"]
    assert rules
    missing = [rule["rule_id"] for rule in rules if not rule["standard_ref"]]
    assert missing == [], f"rules without standard_ref: {missing}"


def test_alloc_p1_cites_adr_028_d9(authed_client) -> None:
    """ALLOC-P1's reference stays in the neighbours' scheme (ADR-028 D11 for
    REL-P1, ...) rather than inventing an external standard."""
    resp = authed_client.get("/api/v1/audit/rules/")
    entry = next(
        rule for rule in resp.json()["rules"] if rule["rule_id"] == "ALLOC-P1"
    )
    assert entry["standard_ref"]
    assert "ADR-028" in entry["standard_ref"]


def test_findings_carry_standard_ref_and_title(
    authed_client, tenant, workspace
) -> None:
    """Every returned finding names the standard it violates."""
    _make_unanchored_icd(tenant, workspace)

    resp = authed_client.get(f"/api/v1/workspaces/{workspace.id}/audit/")
    assert resp.status_code == 200, resp.content
    findings = resp.json()["findings"]
    assert findings, "expected the unanchored ICD to raise IFC-001"
    for finding in findings:
        assert "standard_ref" in finding
        assert "standard_title" in finding
        assert finding["standard_ref"], finding
        assert finding["standard_title"], finding


def test_finding_without_a_catalogue_rule_stays_robust() -> None:
    """An unknown rule id (removed rule, test double) must not raise KeyError.

    Both keys stay present and ``None`` so a client never has to guard for a
    missing field.
    """
    from application.audit_service import AuditFindingView
    from traceability.audit import Finding, RemediationProposal, Severity

    view = AuditFindingView(
        index=0,
        finding=Finding(
            rule_id="NOT-A-REGISTERED-RULE",
            severity=Severity.WARNING,
            message="synthetic",
            artifact_ids=(str(uuid.uuid4()),),
        ),
        remediation=RemediationProposal.manual("NOT-A-REGISTERED-RULE", "none"),
    )
    data = view.to_dict()
    assert data["standard_ref"] is None
    assert data["standard_title"] is None
