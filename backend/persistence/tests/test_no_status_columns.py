"""No artifact model carries a status column any more.

Datenmodell-Konsolidierung Phase 1 / Milestone M1. The Attribut-Definition
bootstrap (spec 2026-09-03-attribute-definition-design.md section 3.2)
introspects these models and must not find a status field.
"""
import pytest
from django.apps import apps

ARTIFACT_MODELS = [
    ("persistence", "Requirement"),
    ("persistence", "StakeholderNeed"),
    ("persistence", "TestCase"),
    ("persistence", "InterviewSession"),
    ("application", "Adr"),
    ("application", "Risk"),
    ("application", "Issue"),
    ("application", "ChangeRequest"),
    ("application", "Goal"),
    ("application", "MainGoal"),
]

KEPT_STATUS_MODELS = [
    ("persistence", "TestRun"),
    ("persistence", "TestRunResult"),
]


@pytest.mark.parametrize("app_label,model_name", ARTIFACT_MODELS)
def test_status_field_is_gone(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    names = {field.name for field in model._meta.get_fields()}
    assert "status" not in names


@pytest.mark.parametrize("app_label,model_name", ARTIFACT_MODELS)
def test_status_index_is_gone(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    for index in model._meta.indexes:
        assert "status" not in index.fields, f"{index.name} still indexes status"


@pytest.mark.parametrize("app_label,model_name", KEPT_STATUS_MODELS)
def test_execution_status_is_kept(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    names = {field.name for field in model._meta.get_fields()}
    assert "status" in names
