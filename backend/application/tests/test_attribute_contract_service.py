"""Plan P0.1 — one field contract for prompts and proposal validation.

``artifact_field_contract`` is the single derivation both the multi-artifact
prompt and the proposal gate read. These tests pin the two sources it fuses:
the production ``create_X()`` signature (required = no default) and the
workspace's resolved attribute definition (type/choices/required override).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.attribute_contract_service import (
    SOURCE_ATTRIBUTE_DEFINITION,
    SOURCE_CREATE_SIGNATURE,
    artifact_field_contract,
)
from application.base import ValidationError
from application.interview_artifact_adapters import allowed_fields_for
from attribute_definitions.global_definition_store import AttributeDefinitionNotFound

pytestmark = pytest.mark.django_db

_RESOLVE = "application.attribute_definition_service.AttributeDefinitionService.resolve"


def _by_name(entries: list[dict]) -> dict[str, dict]:
    return {entry["name"]: entry for entry in entries}


class TestRiskSignatureContract:
    """No attribute definition -> the create signature is the whole contract."""

    @pytest.fixture(autouse=True)
    def _no_definition(self):
        with patch(_RESOLVE, side_effect=AttributeDefinitionNotFound()):
            yield

    def _contract(self) -> dict[str, dict]:
        return _by_name(artifact_field_contract(object(), "ws-1", "Risk"))

    def test_required_fields_come_from_parameters_without_a_default(self):
        contract = self._contract()
        assert contract["title"]["required"] is True
        assert contract["probability"]["required"] is True
        assert contract["impact"]["required"] is True

    def test_optional_field_keeps_its_signature_default(self):
        contract = self._contract()
        assert contract["description"]["required"] is False
        assert contract["description"]["default"] == ""
        assert contract["description"]["choices"] == []

    def test_source_is_create_signature_without_a_definition(self):
        contract = self._contract()
        assert {entry["source"] for entry in contract.values()} == {
            SOURCE_CREATE_SIGNATURE
        }

    def test_every_advertised_name_is_writable_by_the_adapter(self):
        contract = self._contract()
        assert set(contract) <= allowed_fields_for("Risk")

    def test_type_string_present_on_every_entry(self):
        contract = self._contract()
        assert all(isinstance(entry["type"], str) and entry["type"] for entry in contract.values())


class TestDefinitionOverrides:
    def test_definition_supplies_type_choices_and_required(self):
        definition = {
            "attributes": [
                {"name": "title", "type": "text", "required": True},
                {
                    "name": "probability",
                    "type": "enum",
                    "required": True,
                    "options": [
                        {"value": "low", "label_de": "niedrig", "label_en": "low"},
                        {"value": "medium", "label_de": "mittel", "label_en": "medium"},
                        {"value": "high", "label_de": "hoch", "label_en": "high"},
                    ],
                },
                {"name": "description", "type": "textarea", "required": False},
                # Not a create_risk() kwarg: must never be advertised.
                {"name": "tenant_only_field", "type": "text", "required": True},
            ]
        }
        with patch(_RESOLVE, return_value=definition):
            contract = _by_name(artifact_field_contract(object(), "ws-1", "Risk"))

        assert contract["probability"]["type"] == "enum"
        assert contract["probability"]["choices"] == ["low", "medium", "high"]
        assert contract["probability"]["required"] is True
        assert contract["probability"]["source"] == SOURCE_ATTRIBUTE_DEFINITION
        assert contract["title"]["source"] == SOURCE_ATTRIBUTE_DEFINITION
        assert contract["description"]["required"] is False
        assert contract["description"]["type"] == "textarea"
        assert "tenant_only_field" not in contract

    def test_definition_required_flag_wins_over_a_signature_default(self):
        definition = {
            "attributes": [{"name": "description", "type": "text", "required": True}]
        }
        with patch(_RESOLVE, return_value=definition):
            contract = _by_name(artifact_field_contract(object(), "ws-1", "Risk"))
        assert contract["description"]["required"] is True
        assert contract["description"]["source"] == SOURCE_ATTRIBUTE_DEFINITION


class TestRobustness:
    def test_unknown_artifact_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            artifact_field_contract(object(), "ws-1", "NoSuchArtifact")

    def test_definition_resolution_failure_degrades_to_signature(self):
        with patch(_RESOLVE, side_effect=RuntimeError("definition store unavailable")):
            contract = _by_name(artifact_field_contract(object(), "ws-1", "Risk"))
        assert contract["probability"]["required"] is True
        assert contract["probability"]["source"] == SOURCE_CREATE_SIGNATURE
