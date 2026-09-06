"""Milestone M4 gate -- one soft-delete flag, on Artifact only.

Datenmodell-Konsolidierung Phase 4, spec section 5.
"""
import pytest
from django.apps import apps
from django.db import connection

from workflow import lifecycle_manager

FORMERLY_FLAGGED = [
    ("persistence", "StakeholderNeed", "pl_stakeholder_need"),
    ("persistence", "Requirement", "pl_requirement"),
    ("persistence", "ArchitectureElement", "pl_architecture_element"),
    ("persistence", "GlossaryTerm", "pl_glossary_term"),
]


@pytest.mark.parametrize("app_label,model_name,_table", FORMERLY_FLAGGED)
def test_entity_lifecycle_status_field_is_gone(app_label, model_name, _table):
    model = apps.get_model(app_label, model_name)
    names = {field.name for field in model._meta.fields}

    assert "lifecycle_status" not in names


@pytest.mark.django_db
@pytest.mark.parametrize("_app,_model,table", FORMERLY_FLAGGED)
def test_entity_lifecycle_status_column_is_gone(_app, _model, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = 'lifecycle_status'",
            [table],
        )
        assert cursor.fetchone() is None


@pytest.mark.django_db
def test_artifact_keeps_the_only_flag():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'pl_artifact' AND column_name = 'lifecycle_status'"
        )
        assert cursor.fetchone() is not None


def test_lifecycle_mirror_is_removed():
    assert not hasattr(lifecycle_manager, "_LIFECYCLE_MIRROR_MODELS")
    assert not hasattr(lifecycle_manager, "_LIFECYCLE_STATUS_BY_STATE")
    assert not hasattr(lifecycle_manager, "map_lifecycle_status")
    assert not hasattr(
        lifecycle_manager.StateLifecycleManager, "_sync_lifecycle_mirror"
    )
