"""#569 — Level-1 suppression matching, expiry and GH-821 compatibility.

The specification (revision 3, APPROVED) moves the finding identity, the
suppression matcher and the two governance choke points (reason policy,
authority) into ``baseline.waivers``. This module pins the Level-1 half:

* **AC-569-COMPAT** — the byte-identical scope-less ``finding_key`` rendering
  against a really persisted ``BaselineGateWaiver`` row, the defensive R2a
  coverage of the ``scope=""`` row form and the mutation probe.
* **AC-569-16 / AC-569-26** — ``suppression_applies`` R2a/R2b/R2c precision
  against the production-real ``scope="project"`` row form.
* **AC-569-31** — expiry is evaluated at decision time with an injectable
  ``now`` (no job, no state column).
* **AC-569-27 / AC-569-24** — ``load_waived_finding_keys`` compatibility
  wrapper (two positional arguments) agrees with ``load_suppressions``.
* **AC-569-29 / AC-569-33** — the Layer-1 domain errors and the relocated,
  re-exported policy constants.
* **N5** — there is no scope-blind suppression helper.
"""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest
from unittest.mock import MagicMock

from baseline.exceptions import GovernanceAuthorityError, GovernanceReasonError
from baseline.models import BaselineGateWaiver
from baseline import waivers as waivers_module
from baseline.waivers import (
    MIN_OVERRIDE_REASON_LENGTH,
    MIN_REASON_DISTINCT_WORDS,
    MIN_REASON_WORDS,
    BlockerWaiverRequest,
    assert_gate_waiver_authority,
    finding_key,
    load_suppressions,
    load_waived_finding_keys,
    record_waiver,
    suppression_applies,
    validate_waiver_reason,
)
from persistence.models import Tenant
from persistence.tenancy import TenantContext
from persistence.tests.factories import make_workspace

pytestmark = pytest.mark.django_db

#: The unit separator the canonical key renders with. Spelled out here on
#: purpose: the literal is the *contract* with the persisted rows.
_US = "\x1f"

_REASON = "Accepted deviation for the beta cut, see review protocol 2026-09-01."


@contextlib.contextmanager
def _active(tenant: Tenant) -> Iterator[None]:
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant() -> Iterator[None]:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="waivers-569", slug="waivers-569")


@pytest.fixture
def workspace(tenant: Tenant):
    with _active(tenant):
        return make_workspace(tenant, name="waivers-569-ws")


def _persist(
    tenant: Tenant,
    workspace,
    *,
    rule_id: str = "TRACE-P1",
    artifact_ids=("art-1",),
    scope: str = "",
    scope_artifact_id: str = "",
    reason: str = _REASON,
    granted_by: str = "author-1",
    expires_at: datetime | None = None,
) -> BaselineGateWaiver:
    """Persist one waiver through the real writer (never a hand-built literal)."""
    request = BlockerWaiverRequest(
        rule_id=rule_id, artifact_ids=tuple(artifact_ids), reason=reason
    )
    row, _created = record_waiver(
        workspace_id=workspace.id,
        tenant_id=tenant.id,
        request=request,
        rule_id=rule_id,
        scope=scope or None,
        scope_artifact_id=scope_artifact_id or None,
        granted_by=granted_by,
        expires_at=expires_at,
    )
    return row


# ---------------------------------------------------------------------------
# AC-569-COMPAT (a) — byte-identical rendering, against a persisted row
# ---------------------------------------------------------------------------


class TestFindingKeyCompatibility:
    def test_unscoped_finding_key_is_byte_identical_to_persisted_gh821_rows(
        self, tenant: Tenant, workspace
    ):
        """GH-821: persisted waiver rows must keep matching after #569.

        AC-569-COMPAT(a)/(d). If this fails, every ``BaselineGateWaiver`` row on
        file silently stops matching its finding and a previously waived
        workspace starts blocking again.

        mutation-probe: removing the compatibility branch in
        ``baseline/waivers.py::finding_key`` (``if not scope_part: return base``)
        makes this test red — the rendering would become
        ``"TRACE-P1\\x1fart-1\\x1f"`` and no longer equal the persisted literal.
        """
        assert finding_key("TRACE-P1", ["b", "a"]) == f"TRACE-P1{_US}a,b"
        assert finding_key("TRACE-P1", ["a"], None) == finding_key("TRACE-P1", ["a"])
        assert finding_key("TRACE-P1", ["a"], "") == finding_key("TRACE-P1", ["a"])
        # Two positional arguments are a public legacy contract (AC-569-COMPAT).
        assert finding_key("TRACE-P1", ["a"]) == f"TRACE-P1{_US}a"

        row = _persist(tenant, workspace, rule_id="TRACE-P1", artifact_ids=("art-1",))
        assert row.finding_key == f"TRACE-P1{_US}art-1"
        assert row.finding_key == finding_key("TRACE-P1", ["art-1"])

    def test_a_mutated_key_does_not_match_a_persisted_row(
        self, tenant: Tenant, workspace
    ):
        """mutation-probe (#569/AC-569-COMPAT(d)): a mutated key must not match.

        The compatibility branch is only load-bearing if a *different* rendering
        genuinely fails to match a persisted row.
        """
        row = _persist(tenant, workspace, rule_id="TRACE-P1", artifact_ids=("art-1",))
        mutated = finding_key("TRACE-P1", ["art-1"], "project")
        assert mutated != row.finding_key
        assert f"TRACE-P1{_US}art-1{_US}" != row.finding_key


# ---------------------------------------------------------------------------
# AC-569-COMPAT (b) + AC-569-16 + AC-569-26 — the matcher
# ---------------------------------------------------------------------------


class TestSuppressionApplies:
    def test_suppression_applies_is_gh821_backward_compatible(
        self, tenant: Tenant, workspace
    ):
        """R1/R2a: an unbound ``scope=""`` row matches any finding with the key.

        AC-569-COMPAT(b): the new ``AuditService`` row form (``scope=""`` for a
        scope-agnostic finding) is defensively covered, regardless of the
        finding's scope. ``NULL`` is not representable in the
        ``CharField(blank=True, default="")``; ``load_suppressions`` normalises a
        hypothetical ``NULL`` to ``""`` anyway.
        """
        record = _load_one(tenant, workspace, _persist(tenant, workspace, scope=""))
        assert record.scope == ""
        assert suppression_applies(record, "TRACE-P1", ["art-1"]) is True
        assert suppression_applies(record, "TRACE-P1", ["art-1"], "document") is True
        assert suppression_applies(record, "TRACE-P1", ["art-1"], "project") is True

    def test_project_stamped_row_matches_the_scope_agnostic_finding(
        self, tenant: Tenant, workspace
    ):
        """R2b / AC-569-16(i): the production-real GH-821 row form keeps working.

        The gate stamps ``scope=finding.scope or scope``
        (``baseline_facade._apply_waivers``), so a scope-agnostic rule such as
        TRACE-P1 lands as ``scope="project"``/``scope_artifact_id=""``. R2b keeps
        it suppressing after the matcher switched from key-set membership to
        ``suppression_applies``.
        """
        row = _persist(
            tenant, workspace, scope="project", scope_artifact_id=""
        )
        assert row.scope == "project"
        assert row.scope_artifact_id == ""
        record = _load_one(tenant, workspace, row)
        assert suppression_applies(record, "TRACE-P1", ["art-1"]) is True

    def test_project_record_does_not_match_a_document_scoped_finding(
        self, tenant: Tenant, workspace
    ):
        """R2c / AC-569-16(iii): a project record never covers a document finding."""
        record = _load_one(
            tenant,
            workspace,
            _persist(tenant, workspace, scope="project", scope_artifact_id=""),
        )
        assert (
            suppression_applies(
                record, "TRACE-P1", ["art-1"], "document", "doc-1"
            )
            is False
        )

    def test_document_waiver_does_not_bleed_into_scope_agnostic_finding(
        self, tenant: Tenant, workspace
    ):
        """AC-569-26: a document-bound waiver must not suppress beyond its document.

        R2b only matches a scope-agnostic finding when
        ``record.scope_artifact_id == ""``; a document-bound row has a document,
        so it cannot silently cover the scope-agnostic finding of the same
        rule/artifacts (that would be the scope overflow the spec's m4 closes).
        """
        record = _load_one(
            tenant,
            workspace,
            _persist(
                tenant,
                workspace,
                scope="document",
                scope_artifact_id="doc-1",
            ),
        )
        assert (
            suppression_applies(record, "TRACE-P1", ["art-1"], "document", "doc-1")
            is True
        )
        assert suppression_applies(record, "TRACE-P1", ["art-1"]) is False
        assert (
            suppression_applies(record, "TRACE-P1", ["art-1"], "document", "doc-2")
            is False
        )

    def test_a_different_key_never_matches(self, tenant: Tenant, workspace):
        """R1 is always mandatory — a different rule/artifact set is a different finding."""
        record = _load_one(tenant, workspace, _persist(tenant, workspace))
        assert suppression_applies(record, "TRACE-P2", ["art-1"]) is False
        assert suppression_applies(record, "TRACE-P1", ["art-2"]) is False


def _load_one(tenant: Tenant, workspace, row: BaselineGateWaiver):
    records = load_suppressions(workspace.id, tenant.id, include_expired=True)
    return next(record for record in records if record.id == row.id)


# ---------------------------------------------------------------------------
# AC-569-31 — expiry at decision time (injectable now)
# ---------------------------------------------------------------------------


class TestExpiryAtDecisionTime:
    def test_expiry_is_evaluated_at_decision_time_with_injected_now(
        self, tenant: Tenant, workspace
    ):
        """AC-569-31 / V35: no job, no state column — injectable ``now``.

        A future expiry is active before the clock passes it and stops
        suppressing afterwards, evaluated purely from the persisted timestamp.
        The row is not modified by the decision.
        """
        future = datetime.now(timezone.utc) + timedelta(days=30)
        row = _persist(tenant, workspace, expires_at=future)

        before = row.expires_at - timedelta(days=1)
        after = row.expires_at + timedelta(seconds=1)

        active_record = next(
            record
            for record in load_suppressions(
                workspace.id, tenant.id, include_expired=True, now=before
            )
            if record.id == row.id
        )
        assert (
            suppression_applies(
                active_record, "TRACE-P1", ["art-1"], now=before
            )
            is True
        )
        assert (
            suppression_applies(
                active_record, "TRACE-P1", ["art-1"], now=after
            )
            is False
        )

        # The decision-time answer: expired rows drop out of the active set …
        assert load_suppressions(workspace.id, tenant.id, now=after) == ()
        # … without touching the persisted row (append-only, no state column).
        row.refresh_from_db()
        assert row.expires_at == future

    def test_an_unbounded_row_never_expires(self, tenant: Tenant, workspace):
        """``NULL`` = unbounded (GH-821 behaviour, no regression)."""
        row = _persist(tenant, workspace, expires_at=None)
        record = _load_one(tenant, workspace, row)
        far_future = datetime(2999, 1, 1, tzinfo=timezone.utc)
        assert suppression_applies(record, "TRACE-P1", ["art-1"], now=far_future) is True


# ---------------------------------------------------------------------------
# AC-569-24 — load_waived_finding_keys compatibility wrapper
# ---------------------------------------------------------------------------


class TestLoadWaivedFindingKeys:
    def test_load_waived_finding_keys_matches_load_suppressions(
        self, tenant: Tenant, workspace
    ):
        """AC-569-24 / V28: the 2-positional-argument call stays valid and active-only."""
        _persist(tenant, workspace, rule_id="TRACE-P1", artifact_ids=("art-1",))
        _persist(
            tenant,
            workspace,
            rule_id="VERIF-P8",
            artifact_ids=("art-2",),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        # Two positional arguments, no ``now`` — the public legacy contract.
        keys = load_waived_finding_keys(workspace.id, tenant.id)
        assert keys == frozenset(
            record.finding_key
            for record in load_suppressions(
                workspace.id, tenant.id, include_expired=False
            )
        )
        assert finding_key("TRACE-P1", ["art-1"]) in keys
        assert finding_key("VERIF-P8", ["art-2"]) not in keys


# ---------------------------------------------------------------------------
# AC-569-29 / AC-569-33 — Layer-1 policy, authority and constant home
# ---------------------------------------------------------------------------


class TestGovernanceChokePoints:
    def test_reason_policy_raises_the_governance_domain_error(self):
        """AC-569-29(i): ``validate_waiver_reason`` raises the L1 domain error."""
        with pytest.raises(GovernanceReasonError):
            validate_waiver_reason("ok", label="suppression justification")
        assert (
            validate_waiver_reason(_REASON, label="suppression justification")
            == _REASON
        )

    def test_authority_choke_point_rejects_an_editor(self):
        """AC-569-20: the L1 authority helper is the shared choke point."""
        editor = MagicMock()
        editor.active_roles = ("editor",)
        with pytest.raises(GovernanceAuthorityError):
            assert_gate_waiver_authority(editor)

    def test_reason_policy_constants_are_reexported_from_the_facade(self):
        """AC-569-33: constants live at L1 and remain importable from the facade."""
        from application import baseline_facade

        assert (
            baseline_facade.MIN_OVERRIDE_REASON_LENGTH
            == waivers_module.MIN_OVERRIDE_REASON_LENGTH
            == MIN_OVERRIDE_REASON_LENGTH
        )
        assert baseline_facade.MIN_REASON_WORDS == MIN_REASON_WORDS
        assert baseline_facade.MIN_REASON_DISTINCT_WORDS == MIN_REASON_DISTINCT_WORDS

    def test_no_scope_blind_suppression_helper_exists(self):
        """N5: the revoked scope-blind ``suppressed_finding_keys`` is gone.

        Key-set membership without a scope binding is exactly the bug #569
        fixes; the only matcher is ``suppression_applies``.
        """
        assert not hasattr(waivers_module, "suppressed_finding_keys")
