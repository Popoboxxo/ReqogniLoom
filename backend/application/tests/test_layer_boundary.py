"""The seven domain models are owned by Layer 0 (persistence).

Datenmodell-Konsolidierung Phase 2 / Milestone M2, spec section 3.

The move is a Django ``SeparateDatabaseAndState`` pair: the ``as_*`` tables are
never touched, only the app registry entry changes. These tests pin both halves
of that claim — the new registry location *and* the untouched physical table.

``application.models`` keeps a re-export, so the ~40 existing
``from application.models import Adr`` call sites keep working; the move is
about ownership, not call-site churn.
"""
import inspect

import pytest
from django.apps import apps
from django.db import connection

MODELS = [
    "Adr",
    "Risk",
    "Goal",
    "MainGoal",
    "Issue",
    "ChangeRequest",
    "ChangeRequestAffectedItem",
]

TABLES = {
    "Adr": "as_adr",
    "Risk": "as_risk",
    "Goal": "as_goal",
    "MainGoal": "as_main_goal",
    "Issue": "as_issue",
    "ChangeRequest": "as_change_request",
    "ChangeRequestAffectedItem": "as_change_request_affected_item",
}


@pytest.mark.parametrize("model_name", MODELS)
def test_model_is_registered_under_persistence(model_name):
    model = apps.get_model("persistence", model_name)
    assert model._meta.app_label == "persistence"


@pytest.mark.parametrize("model_name", MODELS)
def test_application_no_longer_owns_the_model(model_name):
    with pytest.raises(LookupError):
        apps.get_model("application", model_name)


@pytest.mark.parametrize("model_name", MODELS)
def test_application_re_export_is_the_same_class(model_name):
    from application import models as application_models

    assert getattr(application_models, model_name) is apps.get_model(
        "persistence", model_name
    )


@pytest.mark.parametrize("model_name", MODELS)
def test_table_name_is_unchanged(model_name):
    model = apps.get_model("persistence", model_name)
    assert model._meta.db_table == TABLES[model_name]


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_table_still_exists_with_its_data_shape(model_name):
    """The table survived the move — this database was migrated from zero."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            [TABLES[model_name]],
        )
        columns = {row[0] for row in cursor.fetchall()}

    assert "tenant_id" in columns
    assert "id" in columns


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", MODELS)
def test_row_level_security_policy_survived_the_move(model_name):
    """RLS is written against the *table*, so an app-label change must not
    disturb it. Milestone M1 left every one of these tables force-enabled."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = %s",
            [TABLES[model_name]],
        )
        row = cursor.fetchone()

    assert row is not None, f"{TABLES[model_name]} missing"
    assert row[0] is True, f"RLS disabled on {TABLES[model_name]}"


@pytest.mark.parametrize(
    "app_label,migration_name",
    [
        ("persistence", "0071_adopt_layer2_models"),
        ("application", "0024_release_layer2_models"),
    ],
)
def test_the_move_migrations_emit_no_sql(app_label, migration_name):
    """The move is state-only — neither migration may touch the database.

    Structural rather than a ``sqlmigrate`` diff so it runs in CI without a
    migrated database. A stray operation outside the
    ``SeparateDatabaseAndState`` wrapper, or a non-empty
    ``database_operations``, would drop and re-create seven populated tables.
    """
    from importlib import import_module

    from django.db.migrations import SeparateDatabaseAndState

    module = import_module(f"{app_label}.migrations.{migration_name}")
    operations = module.Migration.operations

    assert len(operations) == 1
    assert isinstance(operations[0], SeparateDatabaseAndState)
    assert operations[0].database_operations == []


def test_application_models_declares_no_domain_model():
    from application import models as application_models

    source = inspect.getsource(application_models)
    for model_name in MODELS:
        assert f"class {model_name}(" not in source
