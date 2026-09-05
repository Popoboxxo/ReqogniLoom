"""Milestone M1 gate — legacy status columns are gone, end to end.

Datenmodell-Konsolidierung Phase 1. The Attribut-Definition plan
(docs/superpowers/specs/2026-09-03-attribute-definition-design.md, section 3.2)
runs a bootstrap that introspects the artifact models. Its migration MUST NOT
run before this test is green on main: a status column present at bootstrap
time is frozen into the generated core-attribute list.
"""
import pytest
from django.apps import apps
from django.db import connection

TABLES = {
    "pl_requirement",
    "pl_stakeholder_need",
    "pl_testcase",
    "pl_interview_session",
    "as_adr",
    "as_risk",
    "as_issue",
    "as_change_request",
    "as_goal",
    "as_main_goal",
}


@pytest.mark.django_db
def test_no_artifact_table_has_a_status_column():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE column_name = 'status' AND table_name = ANY(%s)
            """,
            [sorted(TABLES)],
        )
        offenders = [row[0] for row in cursor.fetchall()]

    assert offenders == []


@pytest.mark.django_db
def test_the_read_seam_is_the_only_status_source():
    from workflow import state_reader

    assert callable(state_reader.current_state)
    assert callable(state_reader.current_states)
    assert callable(state_reader.item_ids_in_state)


@pytest.mark.django_db
def test_bootstrap_introspection_sees_no_status_field():
    """Exactly the introspection the Attribut-Definition bootstrap performs."""
    for app_label, model_name in [
        ("persistence", "Requirement"),
        ("persistence", "StakeholderNeed"),
        ("persistence", "TestCase"),
        ("application", "Adr"),
        ("application", "Risk"),
        ("application", "Issue"),
        ("application", "Goal"),
    ]:
        model = apps.get_model(app_label, model_name)
        concrete = {f.name for f in model._meta.fields}
        assert "status" not in concrete, f"{app_label}.{model_name}"
