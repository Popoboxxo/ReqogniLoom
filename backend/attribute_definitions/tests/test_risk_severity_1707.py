"""#1707 — ``Risk.severity`` has one carrier and one type.

Pins the definition side (bootstrap + stage matrix), the ``automation``
semantic in the DB-free validator, and the idempotence of the repair command
that migrates the retired extended twin.

REST behaviour lives in ``rest_api/tests/test_risk_severity_1707.py``.
"""
from __future__ import annotations

import io
import uuid

import pytest
from django.core.management import call_command

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    introspect_core_attributes,
)
from attribute_definitions.models import WorkspaceAttributeDefinition
from attribute_definitions.schema import normalize_attribute
from attribute_definitions.stage_matrix import build_stage_attributes
from persistence.models import Artifact, Risk, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_EXT_TWIN = {
    "name": "severity",
    "kind": "extended",
    "type": "number",
    "section": "classification",
    "order": 122,
    "label": {"de": "Schweregrad (RPN)", "en": "Severity (RPN)"},
    "visible": True,
    "editable": True,
}


def _tenant() -> Tenant:
    suffix = uuid.uuid4().hex[:8]
    return Tenant.objects.create(name=f"SevDef-{suffix}", slug=f"sevdef-{suffix}")


# ---------------------------------------------------------------------------
# bootstrap / stage matrix
# ---------------------------------------------------------------------------


def test_severity_is_introspected_once_as_a_core_enum() -> None:
    attributes = [
        attribute
        for attribute in introspect_core_attributes("Risk", "extended")
        if attribute["name"] == "severity"
    ]

    assert len(attributes) == 1, "exactly one carrier"
    severity = attributes[0]
    assert severity["kind"] == "core"
    assert severity["type"] == "enum"
    assert {option["value"] for option in severity["options"]} == {
        "low",
        "medium",
        "high",
    }
    assert severity["section"] == "classification"


def test_the_extended_number_twin_is_gone() -> None:
    """The matrix no longer declares a second, ``number`` severity carrier."""
    from attribute_definitions.stage_matrix import MATRIX_ATTRIBUTES, MATRIX_OVERRIDES

    for preset in ("minimal", "standard", "extended"):
        matrix_names = {
            attribute["name"] for attribute in build_stage_attributes("Risk", preset)
        }
        assert "severity" not in matrix_names, (
            f"{preset}: severity must come from introspection, not from a "
            "second matrix entry"
        )
    assert "severity" not in {
        attribute["name"] for attribute in MATRIX_ATTRIBUTES["Risk"]
    }
    # Its staged visibility is carried by the override table instead.
    assert MATRIX_OVERRIDES["Risk"]["severity"]["visible"] == {2, 3}


@pytest.mark.parametrize(
    ("preset", "visible"),
    [("minimal", False), ("standard", True), ("extended", True)],
)
def test_severity_visibility_follows_the_rigor_stage(preset: str, visible: bool) -> None:
    from attribute_definitions.stage_matrix import apply_stage_overrides

    attributes = introspect_core_attributes("Risk", preset)
    severity = next(
        attribute for attribute in attributes if attribute["name"] == "severity"
    )
    apply_stage_overrides("Risk", preset, attributes)
    assert severity["visible"] is visible


# ---------------------------------------------------------------------------
# automation semantic in the DB-free validator
# ---------------------------------------------------------------------------


def _automation_attribute(**overrides) -> dict:
    raw = {
        "name": "severity",
        "kind": "core",
        "type": "enum",
        "options": [
            {"value": "low", "label_de": "Niedrig", "label_en": "Low"},
            {"value": "medium", "label_de": "Mittel", "label_en": "Medium"},
            {"value": "high", "label_de": "Hoch", "label_en": "High"},
        ],
        "editable": "automation",
        "visible": True,
        "required": False,
        "section": "classification",
    }
    raw.update(overrides)
    return normalize_attribute(raw)


def test_automation_rejects_a_client_value_on_create_and_update() -> None:
    attribute = _automation_attribute()

    for existing in (None, {"__exists__": True}):
        with pytest.raises(FieldValidationError) as excinfo:
            validate_values([attribute], {"severity": "high"}, existing)
        assert "derived automatically" in str(excinfo.value)


def test_automation_is_never_required_from_the_client() -> None:
    attribute = _automation_attribute(required=True)

    # No exception: the server computes the value, so the client cannot be
    # asked for it (asking would be unsatisfiable — sending it is rejected).
    validate_values([attribute], {}, None)


def test_manual_severity_accepts_an_enum_value() -> None:
    attribute = _automation_attribute(editable=True)

    validate_values([attribute], {"severity": "high"}, None)


# ---------------------------------------------------------------------------
# repair command
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_risk(db) -> tuple[Tenant, Workspace, Risk, WorkspaceAttributeDefinition]:
    tenant = _tenant()
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="legacy ws", preset={"name": "extended"}
        )
        artifact = Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type="Risk",
            custom_fields={"severity": 7, "risk_type": "technical"},
        )
        risk = Risk.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            artifact=artifact,
            title="Legacy severity",
            severity="low",
        )
        definition = WorkspaceAttributeDefinition.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            item_type="Risk",
            preset="extended",
            definition_json={"attributes": [dict(_EXT_TWIN)]},
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, risk, definition


def test_repair_command_is_dry_run_by_default(legacy_risk) -> None:
    _tenant_row, _workspace, risk, definition = legacy_risk
    out = io.StringIO()

    call_command("repair_risk_severity_attribute", stdout=out)

    risk.refresh_from_db()
    definition = WorkspaceAttributeDefinition.unscoped.get(pk=definition.pk)
    assert risk.severity == "low", "dry-run must not write"
    assert "severity" in (risk.artifact.custom_fields or {}), "dry-run must not write"
    attributes = definition.definition_json["attributes"]
    assert any(
        attribute.get("name") == "severity" and attribute.get("kind") == "extended"
        for attribute in attributes
    ), "dry-run must not touch the definition"
    report = out.getvalue()
    assert "re-run with --apply" in report


def test_repair_command_moves_the_value_and_drops_the_twin(legacy_risk) -> None:
    _tenant_row, _workspace, risk, definition = legacy_risk

    call_command("repair_risk_severity_attribute", "--apply", stdout=io.StringIO())

    risk.refresh_from_db()
    risk.artifact.refresh_from_db()
    definition = WorkspaceAttributeDefinition.unscoped.get(pk=definition.pk)
    assert risk.severity == "medium", "7 >= 4 -> medium (Risk.score_to_severity)"
    assert "severity" not in (risk.artifact.custom_fields or {}), (
        "the extended key must be gone: a stale key is rejected as "
        "'not a defined attribute' on the next custom_fields write"
    )
    attributes = definition.definition_json["attributes"]
    assert not [
        attribute
        for attribute in attributes
        if attribute.get("name") == "severity" and attribute.get("kind") == "extended"
    ]
    severity = next(
        attribute for attribute in attributes if attribute.get("name") == "severity"
    )
    assert severity["kind"] == "core" and severity["type"] == "enum"


def test_repair_command_is_idempotent(legacy_risk) -> None:
    call_command("repair_risk_severity_attribute", "--apply", stdout=io.StringIO())
    out = io.StringIO()

    call_command("repair_risk_severity_attribute", "--apply", stdout=out)

    assert "Repaired 0 Risk severity value(s)" in out.getvalue()
    assert "0 workspace definition(s)" in out.getvalue()
