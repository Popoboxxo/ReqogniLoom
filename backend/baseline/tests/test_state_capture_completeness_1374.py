"""Plan F F4.1 — the baseline snapshot must capture every editable field.

The baseline snapshot is the *only* thing an additive rollback (ADR-025) can
ever restore, and the only thing a baseline diff can ever see. A field that is
not in the captured state is therefore structurally invisible to both: drift in
it is not reported, and a rollback would silently leave the newer value in
place. Finding R-F4-1 (Requirement ``rationale``/``source``/
``acceptance_criteria_items``/``level_source`` plus the Artifact-hull system
fields ``owner``/``reporter``/``priority``/``stakeholder``) and R-F4-2 (Icd
content invisible in project scope) are the concrete instances.

These tests are deliberately data-driven against the live model metadata rather
than against a hand-written field list: the meta-test fails the moment a new
editable column is added without either being captured or being declared
non-restorable on purpose.

Real DB, real services — no mocks (the "old snapshot" side of the
backward-compatibility test is the genuine new state minus the not-yet-existing
keys, which is exactly what an older row holds).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from baseline.diff_engine import _field_diff
from baseline.restorable_fields import NON_RESTORABLE, RESTORABLE_FIELDS
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple

#: The eight artifact types ADR-025 restricts a rollback to.
COVERED_TYPES: tuple[str, ...] = (
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "Adr",
    "Risk",
    "Issue",
    "GlossaryTerm",
)

#: Columns that exist to bind a row to its tenant/artifact/parent storage and
#: are never user-editable content: identity (``id``), tenancy (``tenant``),
#: audit bookkeeping (``created_*``/``modified_*``), the backing Artifact
#: (``artifact``), the denormalized workspace (``workspace`` and its plain
#: ``workspace_id`` UUID variant on Adr/Risk/Issue) and the embedding vector.
_SYSTEM_FIELD_NAMES = frozenset(
    {"id", "tenant", "artifact", "workspace", "workspace_id", "embedding"}
)
_SYSTEM_FIELD_PREFIXES = ("created_", "modified_")

#: The one published-key rename the capture deliberately keeps (Attribut v3 WS7
#: #940): ``Risk.owner_name`` is captured under the published baseline key
#: ``owner``, so the meta-test must accept that key for that column.
_CAPTURE_KEY_ALIASES: dict[str, dict[str, str]] = {"Risk": {"owner_name": "owner"}}


@pytest.fixture
def workspace_env(db):
    """A real tenant + workspace with the tenant context armed for capture."""
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(
        name=f"f4-1-{uuid.uuid4().hex[:8]}",
        slug=f"f4-1-{uuid.uuid4().hex[:8]}",
    )
    TenantContext.set_tenant(tenant.id)
    # "standard" allows the project baseline scope (minimal has no baselines).
    workspace = Workspace.objects.create(
        tenant=tenant, name="f4-1-workspace", preset={"name": "standard"}
    )
    try:
        yield {"tenant": tenant, "workspace": workspace}
    finally:
        TenantContext.clear_tenant()


def _seed_and_capture(env: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Create one real row per covered type and return its captured state.

    Returns:
        ``{artifact_type: captured_state_dict}``. The state for GlossaryTerm is
        the ``glossary_term`` entry — that is the entry a rollback uses (the
        ``item`` entry of an Artifact-backed glossary term stays a bare hull).
    """
    from persistence.models import (
        Adr,
        ArchitectureElement,
        Artifact,
        GlossaryTerm,
        Issue,
        Requirement,
        Risk,
        StakeholderNeed,
        TestCase,
    )

    tenant = env["tenant"]
    workspace = env["workspace"]

    def _artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type=kind
        )

    capture_keys: dict[str, str] = {}
    tuples: list[DeltaIndexTuple] = []

    req_artifact = _artifact("Requirement")
    Requirement.objects.create(
        tenant=tenant,
        artifact=req_artifact,
        workspace=workspace,
        title="Requirement",
        description="d",
        rationale="because the stakeholder asked",
        source="stakeholder interview",
        acceptance_criteria="legacy free text",
        acceptance_criteria_items=[{"text": "legacy free text", "fulfilled": False}],
        category="functional",
        level=1,
        level_source="manual",
    )
    capture_keys["Requirement"] = str(req_artifact.id)

    need_artifact = _artifact("StakeholderNeed")
    StakeholderNeed.objects.create(
        tenant=tenant,
        artifact=need_artifact,
        workspace=workspace,
        title="StakeholderNeed",
        description="d",
        category="functional",
        moscow_priority="Must",
    )
    capture_keys["StakeholderNeed"] = str(need_artifact.id)

    arch_artifact = _artifact("ArchitectureElement")
    ArchitectureElement.objects.create(
        tenant=tenant,
        artifact=arch_artifact,
        workspace=workspace,
        title="ArchitectureElement",
        description="d",
        element_type="component",
    )
    capture_keys["ArchitectureElement"] = str(arch_artifact.id)

    test_artifact = _artifact("TestCase")
    TestCase.objects.create(
        tenant=tenant,
        artifact=test_artifact,
        workspace=workspace,
        title="TestCase",
        description="d",
        steps=[{"action": "open"}],
        test_type="unit",
    )
    capture_keys["TestCase"] = str(test_artifact.id)

    adr_artifact = _artifact("Adr")
    Adr.objects.create(
        tenant=tenant,
        artifact=adr_artifact,
        workspace_id=workspace.id,
        title="ADR",
        description="d",
        context="c",
        decision="decided",
        consequences="k",
    )
    capture_keys["Adr"] = str(adr_artifact.id)

    risk_artifact = _artifact("Risk")
    Risk.objects.create(
        tenant=tenant,
        artifact=risk_artifact,
        workspace_id=workspace.id,
        title="Risk",
        description="d",
        category="technical",
        probability="high",
        impact="high",
        mitigation_strategy="mitigate",
    )
    capture_keys["Risk"] = str(risk_artifact.id)

    issue_artifact = _artifact("Issue")
    Issue.objects.create(
        tenant=tenant,
        artifact=issue_artifact,
        workspace_id=workspace.id,
        title="Issue",
        description="d",
        severity="high",
        category="defect",
        tags=["a"],
    )
    capture_keys["Issue"] = str(issue_artifact.id)

    term = GlossaryTerm.objects.create(
        tenant=tenant,
        workspace=workspace,
        term="Term",
        definition="definition",
        synonyms=["synonym"],
        abbreviation="TRM",
    )

    for item_id in capture_keys.values():
        tuples.append(
            DeltaIndexTuple(item_id=item_id, version=1, entity_type="item")
        )
    tuples.append(
        DeltaIndexTuple(
            item_id=str(term.id), version=1, entity_type="glossary_term"
        )
    )

    states = capture_states(tuples, tenant.id)

    captured = {artifact_type: states[item_id] for artifact_type, item_id in capture_keys.items()}
    captured["GlossaryTerm"] = states[str(term.id)]
    return captured


def _editable_fields(model) -> list:
    """Editable concrete columns, minus the storage/system columns."""
    fields = []
    for field in model._meta.concrete_fields:
        if not field.editable:
            continue
        name = field.name
        if name in _SYSTEM_FIELD_NAMES:
            continue
        if any(name.startswith(prefix) for prefix in _SYSTEM_FIELD_PREFIXES):
            continue
        fields.append(field)
    return fields


def _model_for(artifact_type: str):
    from persistence.models import (
        Adr,
        ArchitectureElement,
        GlossaryTerm,
        Issue,
        Requirement,
        Risk,
        StakeholderNeed,
        TestCase,
    )

    return {
        "Requirement": Requirement,
        "StakeholderNeed": StakeholderNeed,
        "ArchitectureElement": ArchitectureElement,
        "TestCase": TestCase,
        "Adr": Adr,
        "Risk": Risk,
        "Issue": Issue,
        "GlossaryTerm": GlossaryTerm,
    }[artifact_type]


@pytest.mark.django_db
def test_capture_covers_every_editable_field(workspace_env):
    """Every editable column is either captured or explicitly non-restorable.

    This is the meta-test Finding R-F4-1 asks for: it fails the moment a new
    editable field is added without a decision about its capture, which is what
    makes "the snapshot is complete" an invariant instead of a promise.
    """
    captured = _seed_and_capture(workspace_env)

    uncovered: dict[str, list[str]] = {}
    for artifact_type in COVERED_TYPES:
        model = _model_for(artifact_type)
        captured_keys = set(captured[artifact_type])
        non_restorable = set(NON_RESTORABLE.get(artifact_type, {}))
        aliases = _CAPTURE_KEY_ALIASES.get(artifact_type, {})

        missing = []
        for field in _editable_fields(model):
            # A relation is captured under its ``<name>_id`` attname (the
            # Artifact hull stores plain UUIDs), a plain column under its name.
            candidates = {field.name, field.attname}
            alias = aliases.get(field.name)
            if alias is not None:
                candidates.add(alias)
            if not candidates & (captured_keys | non_restorable):
                missing.append(field.name)
        if missing:
            uncovered[artifact_type] = sorted(missing)

    assert uncovered == {}, f"editable fields neither captured nor declared: {uncovered}"

    # R4 precondition (F4.4): reactivating a soft-deleted artifact needs its
    # ``Artifact.lifecycle_status`` in the snapshot -- for *every* covered type,
    # not just the three that carried it before. Without it a rollback cannot
    # tell "outdated" from "active" and would silently leave a deleted item
    # deleted.
    missing_lifecycle = [
        artifact_type
        for artifact_type in COVERED_TYPES
        if "lifecycle_status" not in captured[artifact_type]
    ]
    assert missing_lifecycle == [], (
        f"lifecycle_status not captured for: {missing_lifecycle}"
    )

    # The reasons ADR-025 relies on must actually be declared somewhere.
    declared = set().union(*(set(reasons) for reasons in NON_RESTORABLE.values()))
    required = {"level", "status", "uid", "version", "suspect", "lifecycle_status"}
    assert required <= declared, f"missing non-restorable reasons for: {sorted(required - declared)}"


@pytest.mark.django_db
def test_capture_includes_artifact_system_fields(workspace_env):
    """R-F4-1: the Artifact hull must carry owner/reporter/priority/stakeholder.

    These are the cross-cutting system fields every artifact type inherits from
    the shared Artifact row (Attribut v3 WS2/#936); a rollback that cannot read
    them silently loses the attribution and the priority.
    """
    from persistence.models import Actor, Artifact, Requirement

    env = workspace_env
    tenant, workspace = env["tenant"], env["workspace"]
    owner = Actor.objects.create(
        tenant=tenant, kind="external", display_name="Owner"
    )
    reporter = Actor.objects.create(
        tenant=tenant, kind="external", display_name="Reporter"
    )

    artifact = Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        owner=owner,
        reporter=reporter,
        priority="high",
        stakeholder=["safety", "security"],
    )
    Requirement.objects.create(
        tenant=tenant, artifact=artifact, workspace=workspace, title="REQ"
    )

    states = capture_states(
        [DeltaIndexTuple(item_id=str(artifact.id), version=1)], tenant.id
    )
    state = states[str(artifact.id)]

    assert state["owner"] == str(owner.id)
    assert state["reporter"] == str(reporter.id)
    assert state["priority"] == "high"
    assert state["stakeholder"] == ["safety", "security"]


@pytest.mark.django_db
def test_icd_item_entry_carries_contract(workspace_env):
    """R-F4-2: an ICD's contract must be visible in project scope.

    The Icd's backing Artifact is part of every project baseline, but it used to
    fall through to the bare-artifact branch, so the whole Design-by-Contract
    payload was absent from the snapshot.
    """
    from baseline.services import build as baseline_build
    from baseline.store import get_store
    from icd.models import Icd
    from persistence.models import Artifact

    env = workspace_env
    tenant, workspace = env["tenant"], env["workspace"]

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Icd"
    )
    Icd.objects.create(
        tenant=tenant,
        workspace_id=workspace.id,
        artifact=artifact,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        name="IF-1",
        semantic_description="Controller reads the sensor bus",
        preconditions=["bus powered"],
        postconditions=["frame acknowledged"],
        invariants=["CRC valid"],
    )

    baseline_id = baseline_build(
        scope="project",
        workspace_id=workspace.id,
        name="BL-F41-ICD",
        tenant_id=tenant.id,
        created_by="f4-1-test",
    )
    states = get_store().load_states(baseline_id, tenant.id)
    state = states[str(artifact.id)]

    assert state["semantic_description"] == "Controller reads the sensor bus"
    assert state["direction"] == "unidirectional"
    assert state["preconditions"] == ["bus powered"]
    assert state["postconditions"] == ["frame acknowledged"]
    assert state["invariants"] == ["CRC valid"]


@pytest.mark.django_db
def test_old_snapshot_diff_unaffected(workspace_env):
    """New capture keys are backward compatible (``diff_engine`` compares
    only keys present in *both* snapshots, see ``_field_diff``).

    A baseline created before F4.1 must not suddenly report every artifact as
    changed just because the newer snapshot carries more keys.
    """
    captured = _seed_and_capture(workspace_env)
    new_state = captured["Requirement"]

    # Exactly what an older row holds: the same values, without the keys this
    # change introduced.
    added_keys = {
        "rationale",
        "source",
        "acceptance_criteria_items",
        "level_source",
        "owner",
        "reporter",
        "priority",
        "stakeholder",
    }
    old_state = {k: v for k, v in new_state.items() if k not in added_keys}
    assert added_keys <= set(new_state)
    assert not added_keys & set(old_state)

    assert _field_diff(old_state, new_state) == {}


@pytest.mark.django_db
def test_restorable_fields_subset_of_capture(workspace_env):
    """``RESTORABLE_FIELDS`` may only name keys the capture actually emits.

    A restorable field that is not captured is a rollback that silently does
    nothing for that field — the exact failure mode F4.1 exists to prevent.
    """
    captured = _seed_and_capture(workspace_env)

    assert set(RESTORABLE_FIELDS) == set(COVERED_TYPES)

    uncaptured: dict[str, list[str]] = {}
    for artifact_type in COVERED_TYPES:
        missing = sorted(
            set(RESTORABLE_FIELDS[artifact_type]) - set(captured[artifact_type])
        )
        if missing:
            uncaptured[artifact_type] = missing

    assert uncaptured == {}, f"restorable but not captured: {uncaptured}"
