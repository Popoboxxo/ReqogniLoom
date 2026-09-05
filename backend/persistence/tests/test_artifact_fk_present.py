"""Every artifact type declares a backing Artifact FK.

Datenmodell-Konsolidierung Phase 3, spec section 4.
"""
import pytest
from django.apps import apps
from django.db import models

BACKED = [
    ("persistence", "Requirement"),
    ("persistence", "StakeholderNeed"),
    ("persistence", "ArchitectureElement"),
    ("persistence", "TestCase"),
    ("persistence", "GlossaryTerm"),
    ("persistence", "Adr"),
    ("persistence", "Risk"),
    ("persistence", "Issue"),
    ("persistence", "Goal"),
    ("persistence", "MainGoal"),
    ("persistence", "ChangeRequest"),
    ("diagram", "Diagram"),
    ("icd", "Icd"),
]


@pytest.mark.parametrize("app_label,model_name", BACKED)
def test_artifact_field_exists_and_is_one_to_one(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    field = model._meta.get_field("artifact")

    assert isinstance(field, models.OneToOneField)
    assert field.remote_field.model is apps.get_model("persistence", "Artifact")


# Subset of BACKED whose ``artifact`` FK follows the "optional shadow
# Artifact" pattern (nullable, backfilled later). Excludes Requirement,
# StakeholderNeed, ArchitectureElement, TestCase, Goal, MainGoal: those are
# "artifact-first" identity models where ``artifact`` has always been
# mandatory (non-nullable) by original design — not part of this task's
# scope and not safe to change here.
NULLABLE_BACKED = [
    ("persistence", "GlossaryTerm"),
    ("persistence", "Adr"),
    ("persistence", "Risk"),
    ("persistence", "Issue"),
    ("persistence", "ChangeRequest"),
    ("diagram", "Diagram"),
    ("icd", "Icd"),
]


@pytest.mark.parametrize("app_label,model_name", NULLABLE_BACKED)
def test_artifact_field_is_nullable(app_label, model_name):
    """Nullable so the schema migration stays additive; the backfill fills it."""
    model = apps.get_model(app_label, model_name)
    assert model._meta.get_field("artifact").null is True
