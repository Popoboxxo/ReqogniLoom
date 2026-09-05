"""Audit-field collisions are cleared before the base-class swap.

Datenmodell-Konsolidierung Phase 2 Task 14.
"""
import pytest
from django.apps import apps

MODELS = ["Adr", "Risk", "Goal", "MainGoal", "Issue", "ChangeRequest"]


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_char_field_is_renamed(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("created_by_name")

    assert field.get_attname_column()[1] == "created_by"
    assert field.max_length == 255


@pytest.mark.parametrize("model_name", MODELS)
def test_created_by_attribute_is_free(model_name):
    model = apps.get_model("application", model_name)
    names = {f.name for f in model._meta.fields}

    assert "created_by" not in names


@pytest.mark.parametrize("model_name", MODELS)
def test_modified_at_exists_and_is_nullable(model_name):
    model = apps.get_model("application", model_name)
    field = model._meta.get_field("modified_at")

    assert field.null is True


@pytest.mark.django_db
def test_modified_at_is_backfilled_from_updated_at():
    from application.models import Adr

    row = Adr.objects.create(
        workspace_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        title="A",
        description="d",
    )
    row.refresh_from_db()

    assert row.modified_at is not None
