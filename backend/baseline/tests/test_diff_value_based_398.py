"""Issue #398 — baseline diff must be driven by captured values, not a counter.

Regression coverage for the most severe configuration-management defect found
in the 2026-08-07 SE-methodology audit: ``GET /baselines/diff/`` answered
``{"added": 0, "removed": 0, "changed": 0}`` for a Requirement that had
demonstrably been edited between the two baselines.

Cause: :class:`baseline.diff_engine.DiffEngine` classified an item as changed
iff its delta-index ``version`` differed. That number is ``Artifact.version`` —
the shadow/base-table counter, which stays at 1 when a *subtype* row
(``pl_requirement``) is edited. Both snapshots reported ``version=1`` for the
same, genuinely different requirement.

The tests below therefore do NOT assert "the other version column is read".
They assert the stronger property the fix is built on: **content drift is
detected from the snapshotted field values, even when no version counter moves
at all.** That is what makes the whole "trusted the wrong counter" bug class
impossible rather than fixing one instance of it.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from baseline.diff_engine import DiffEngine, _effective_version, _field_diff
from baseline.exceptions import BaselineNotFoundError
from baseline.services import build as baseline_build
from baseline.services import diff as baseline_diff
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple


# ---------------------------------------------------------------------------
# Pure unit tests — classification logic
# ---------------------------------------------------------------------------


class _StubStore:
    """Minimal BaselineStore stand-in: canned index + state maps per baseline."""

    def __init__(self, index: dict, states: dict) -> None:
        self._index = index
        self._states = states

    def load_delta_index(self, baseline_id, tenant_id=None):
        return self._index[baseline_id]

    def load_states(self, baseline_id, tenant_id=None, item_ids=None):
        states = self._states[baseline_id]
        if item_ids is None:
            return dict(states)
        return {k: v for k, v in states.items() if k in item_ids}


def _engine(index, states, scope="project"):
    """Return (engine, patcher). The caller must ``patcher.stop()``."""
    engine = DiffEngine(store=_StubStore(index, states))
    snap = MagicMock()
    snap.scope = scope
    patcher = patch("baseline.diff_engine.BaselineSnapshot")
    mock_snap = patcher.start()
    mock_snap.unscoped.only.return_value.get.return_value = snap
    return engine, patcher


class TestValueBasedClassification:
    """The captured state — not the version counter — decides 'changed'."""

    def setup_method(self):
        self.a = uuid.uuid4()
        self.b = uuid.uuid4()
        self.item = str(uuid.uuid4())
        self.tenant_id = uuid.uuid4()

    def test_content_drift_with_identical_versions_is_reported(self):
        """THE bug: same recorded version on both sides, different content.

        On the pre-#398 engine this returned ``changed == []``.
        """
        index = {
            self.a: [(self.item, 1, "item")],
            self.b: [(self.item, 1, "item")],
        }
        states = {
            self.a: {self.item: {"title": "Zustandsanzeige", "version": 1}},
            self.b: {self.item: {"title": "CHANGED AFTER BASELINE", "version": 1}},
        }
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert [c.id for c in result.changed] == [self.item]
        assert result.changed[0].field_changes == {
            "title": {"old": "Zustandsanzeige", "new": "CHANGED AFTER BASELINE"}
        }

    def test_identical_content_with_differing_versions_is_not_reported(self):
        """A bumped counter without content drift is not a baseline change.

        ``version`` is an optimistic-concurrency counter (see
        ``AuditableModel``): any save bumps it, including saves that change
        nothing a user would recognise as content.
        """
        index = {
            self.a: [(self.item, 1, "item")],
            self.b: [(self.item, 7, "item")],
        }
        payload = {"title": "Unverändert", "description": "x"}
        states = {self.a: {self.item: dict(payload)}, self.b: {self.item: dict(payload)}}
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert result.changed == []
        assert result.added == []
        assert result.removed == []

    def test_reported_versions_come_from_the_snapshot_not_the_index(self):
        """old/new_version must show the entity's own counter, not Artifact's."""
        index = {
            self.a: [(self.item, 1, "item")],
            self.b: [(self.item, 1, "item")],
        }
        states = {
            self.a: {self.item: {"title": "A", "version": 1}},
            self.b: {self.item: {"title": "B", "version": 2}},
        }
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert (result.changed[0].old_version, result.changed[0].new_version) == (1, 2)

    def test_legacy_null_state_falls_back_to_version_comparison(self):
        """Entries predating REQ-L2-BL-012 have no values to compare."""
        index = {
            self.a: [(self.item, 1, "item")],
            self.b: [(self.item, 2, "item")],
        }
        states = {self.a: {self.item: None}, self.b: {self.item: None}}
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert [c.id for c in result.changed] == [self.item]
        assert result.changed[0].field_changes is None
        assert (result.changed[0].old_version, result.changed[0].new_version) == (1, 2)

    def test_legacy_null_state_with_equal_versions_is_unchanged(self):
        index = {
            self.a: [(self.item, 3, "item")],
            self.b: [(self.item, 3, "item")],
        }
        states = {self.a: {self.item: None}, self.b: {}}
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert result.changed == []

    def test_added_and_removed_still_classified_by_membership(self):
        only_a = str(uuid.uuid4())
        only_b = str(uuid.uuid4())
        index = {self.a: [(only_a, 1, "item")], self.b: [(only_b, 1, "item")]}
        states = {self.a: {only_a: {"title": "x"}}, self.b: {only_b: {"title": "y"}}}
        engine, patcher = _engine(index, states)
        try:
            result = engine.diff(self.a, self.b, self.tenant_id)
        finally:
            patcher.stop()

        assert result.added == [only_b]
        assert result.removed == [only_a]
        assert result.changed == []


class TestFieldDiffSchemaEvolution:
    """``_field_diff`` compares the intersection of the captured key sets."""

    def test_field_added_to_the_capture_schema_is_not_a_change(self):
        """A baseline taken before a field existed must not report it as drift.

        The capture schema decides the key set, never the data — so a key on
        one side only means the schema grew between the two baseline dates.
        Diffing the union instead would flag every historical artifact as
        changed the moment ``acceptance_criteria`` was added to the capture.
        """
        old = {"title": "T", "version": 1}
        new = {"title": "T", "version": 1, "acceptance_criteria": "Given/When/Then"}
        assert _field_diff(old, new) == {}

    def test_new_field_is_compared_between_two_new_baselines(self):
        old = {"title": "T", "acceptance_criteria": ""}
        new = {"title": "T", "acceptance_criteria": "Given/When/Then"}
        assert _field_diff(old, new) == {
            "acceptance_criteria": {"old": "", "new": "Given/When/Then"}
        }

    def test_adr_captured_before_and_after_the_richer_schema_is_unchanged(self):
        """The concrete straddling case this project will actually hit.

        ADRs used to snapshot as ``{"artifact_type": "Adr"}``. A baseline taken
        after the richer capture must not make every pre-existing ADR look
        edited — which is why the new capture echoes the raw artifact_type
        instead of a normalized "adr".
        """
        old = {"artifact_type": "Adr"}
        new = {
            "artifact_type": "Adr",
            "title": "ADR-1",
            "decision": "d",
            "custom_fields": {},
            "artifact_parent_id": None,
            "version": 1,
        }
        assert _field_diff(old, new) == {}

    def test_missing_snapshot_on_either_side_returns_none(self):
        assert _field_diff(None, {"title": "T"}) is None
        assert _field_diff({"title": "T"}, None) is None
        assert _field_diff(None, None) is None


class TestEffectiveVersion:
    def test_prefers_snapshotted_entity_version(self):
        assert _effective_version({"version": 4}, 1) == 4

    def test_falls_back_when_absent_or_not_an_int(self):
        assert _effective_version(None, 9) == 9
        assert _effective_version({}, 9) == 9
        assert _effective_version({"version": "2"}, 9) == 9
        # bool is an int subclass and must not be mistaken for a version
        assert _effective_version({"version": True}, 9) == 9


# ---------------------------------------------------------------------------
# DB integration — the exact audit scenario, end to end
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace_fixture(db):
    """Tenant + workspace + a single Requirement, in a tenant context."""
    from persistence.models import (
        Artifact,
        Requirement,
        Tenant,
        Workspace,
    )
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        id=uuid.uuid4(),
        name="issue398-tenant",
        slug=f"issue398-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            name=f"issue398-ws-{uuid.uuid4().hex[:6]}",
            preset={"name": "standard"},
        )
        artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            workspace=workspace,
            artifact_type="Requirement",
        )
        requirement = Requirement.objects.create(
            id=uuid.uuid4(),
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            uid="REQ-398-001",
            title="Zustandsanzeige",
            description="Original description",
            acceptance_criteria="Original criteria",
            category="functional",
            status="draft",
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "artifact": artifact,
            "requirement": requirement,
        }
    finally:
        TenantContext.clear_tenant()


def _build(name: str, fx) -> uuid.UUID:
    return baseline_build(
        scope="project",
        workspace_id=fx["workspace"].id,
        name=name,
        tenant_id=fx["tenant"].id,
        created_by="issue398-test",
    )


@pytest.mark.django_db
class TestBaselineDriftEndToEnd:
    """The audit's reproduction, as a test."""

    def test_edited_requirement_shows_up_as_changed(self, workspace_fixture):
        fx = workspace_fixture
        artifact_id = str(fx["artifact"].id)

        baseline_a = _build("BL-398-A", fx)

        # Edit exactly what the audit edited: title + acceptance_criteria.
        # Crucially, Artifact.version is NOT touched — that is what production
        # does, and what made the old diff blind.
        req = fx["requirement"]
        req.title = "REQ-398-001 CHANGED AFTER BASELINE"
        req.acceptance_criteria = "Changed criteria"
        req.version = 2
        req.save()

        baseline_b = _build("BL-398-B", fx)

        from persistence.models import Artifact

        assert Artifact.unscoped.get(id=fx["artifact"].id).version == 1, (
            "precondition: the base-table counter must be unchanged, otherwise "
            "this test would also pass on the buggy version-based engine"
        )

        result = baseline_diff(baseline_a, baseline_b, tenant_id=fx["tenant"].id)

        assert [c.id for c in result.changed] == [artifact_id]
        changes = result.changed[0].field_changes
        assert changes is not None
        assert changes["title"]["old"] == "Zustandsanzeige"
        assert changes["title"]["new"] == "REQ-398-001 CHANGED AFTER BASELINE"
        assert changes["acceptance_criteria"] == {
            "old": "Original criteria",
            "new": "Changed criteria",
        }
        assert (result.changed[0].old_version, result.changed[0].new_version) == (1, 2)

    def test_drift_without_any_version_bump_is_still_detected(self, workspace_fixture):
        """An out-of-band data fix bumps no counter at all — still drift."""
        fx = workspace_fixture
        baseline_a = _build("BL-398-C", fx)

        from persistence.models import Requirement

        Requirement.unscoped.filter(id=fx["requirement"].id).update(
            description="silently repaired by a data migration"
        )

        baseline_b = _build("BL-398-D", fx)
        result = baseline_diff(baseline_a, baseline_b, tenant_id=fx["tenant"].id)

        assert len(result.changed) == 1
        assert result.changed[0].field_changes["description"] == {
            "old": "Original description",
            "new": "silently repaired by a data migration",
        }

    def test_untouched_workspace_reports_no_drift(self, workspace_fixture):
        """The other half of the promise: no false positives."""
        fx = workspace_fixture
        baseline_a = _build("BL-398-E", fx)
        baseline_b = _build("BL-398-F", fx)

        result = baseline_diff(baseline_a, baseline_b, tenant_id=fx["tenant"].id)

        assert (result.added, result.removed, result.changed) == ([], [], [])

    def test_diff_across_tenant_boundary_raises_not_found(self, workspace_fixture):
        """ADR-03 (issue #464): a baseline_id valid for tenant A must not be
        diffable by passing a different tenant's tenant_id.

        Regression guard for the cross-tenant leak this project fixed: before
        #464, ``_validate_scopes`` looked baselines up via ``.unscoped.get(id=...)``
        with no tenant filter, so any tenant could probe/read another
        tenant's baseline by UUID alone. The tenant_id argument — not the
        UUID — must decide existence.
        """
        from persistence.models import Tenant

        fx = workspace_fixture
        baseline_a = _build("BL-398-TENANT-A1", fx)
        baseline_b = _build("BL-398-TENANT-A2", fx)

        other_tenant = Tenant.objects.create(
            id=uuid.uuid4(),
            name="issue398-tenant-other",
            slug=f"issue398-other-{uuid.uuid4().hex[:8]}",
        )

        with pytest.raises(BaselineNotFoundError):
            baseline_diff(baseline_a, baseline_b, tenant_id=other_tenant.id)


# ---------------------------------------------------------------------------
# State capture completeness (issue #398, sub-problem 2)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStateCaptureCompleteness:
    """Fields that are not captured are fields whose drift is invisible."""

    def test_requirement_state_captures_the_previously_missing_fields(
        self, workspace_fixture
    ):
        fx = workspace_fixture
        req = fx["requirement"]
        req.level = 1
        req.save()

        states = capture_states(
            [DeltaIndexTuple(item_id=str(fx["artifact"].id), version=1)],
            fx["tenant"].id,
        )
        state = states[str(fx["artifact"].id)]

        # Regression list from the audit: these three were absent.
        assert state["acceptance_criteria"] == "Original criteria"
        assert state["level"] == 1
        assert state["lifecycle_status"] == req.lifecycle_status
        # The shared Artifact envelope — where a user-defined "rationale"
        # custom field would live.
        assert "custom_fields" in state
        assert "artifact_parent_id" in state

    def test_custom_fields_drift_is_captured(self, workspace_fixture):
        fx = workspace_fixture
        from persistence.models import Artifact

        Artifact.unscoped.filter(id=fx["artifact"].id).update(
            custom_fields={"rationale": "because the stakeholder asked"}
        )

        states = capture_states(
            [DeltaIndexTuple(item_id=str(fx["artifact"].id), version=1)],
            fx["tenant"].id,
        )
        assert states[str(fx["artifact"].id)]["custom_fields"] == {
            "rationale": "because the stakeholder asked"
        }

    def test_adr_content_is_captured_instead_of_a_bare_artifact_type(
        self, workspace_fixture
    ):
        """ADR/Risk/Issue/Goal used to snapshot as ``{"artifact_type": "Adr"}``.

        With no content in the snapshot, no ADR edit could ever surface in a
        baseline diff — the same blindness as the Requirement case, but total.
        """
        fx = workspace_fixture
        from application.models import Adr
        from persistence.models import Artifact

        adr_artifact = Artifact.objects.create(
            id=uuid.uuid4(),
            tenant=fx["tenant"],
            workspace=fx["workspace"],
            artifact_type="Adr",
        )
        Adr.objects.create(
            id=uuid.uuid4(),
            artifact=adr_artifact,
            workspace_id=fx["workspace"].id,
            tenant_id=fx["tenant"].id,
            title="ADR-398 Use value-based diffs",
            description="d",
            context="c",
            decision="compare snapshotted values",
            consequences="counters stop being load-bearing",
        )

        states = capture_states(
            [DeltaIndexTuple(item_id=str(adr_artifact.id), version=1)],
            fx["tenant"].id,
        )
        state = states[str(adr_artifact.id)]

        # The raw Artifact.artifact_type is echoed on purpose: it is exactly
        # what the old bare-artifact branch stored, so a diff straddling this
        # change sees only added keys instead of a spurious type change.
        assert state["artifact_type"] == "Adr"
        assert state["title"] == "ADR-398 Use value-based diffs"
        assert state["decision"] == "compare snapshotted values"
        assert state["consequences"] == "counters stop being load-bearing"
