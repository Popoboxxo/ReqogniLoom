"""Release the seven domain models from the application app — **state only**.

Datenmodell-Konsolidierung Phase 2 / Milestone M2 (spec section 3). Paired with
``persistence/0071_adopt_layer2_models``, which re-creates the same seven models
in Layer 0.

**No SQL runs.** The tables (``as_adr``, ``as_risk``, ``as_goal``,
``as_main_goal``, ``as_issue``, ``as_change_request``,
``as_change_request_affected_item``) — created and populated by
``application/0006``..``application/0023``, together with their row-level
security policies — are untouched. Only Django's model registry changes.

The delete order is load-bearing: ``ChangeRequestAffectedItem`` carries an FK to
``ChangeRequest``, and ``ProjectState.remove_model`` re-renders every model that
still references the one being removed. Dropping the parent first would leave a
dangling reference mid-operation.
"""
from django.db import migrations

#: Child before parent — see the module docstring.
MOVED = [
    "ChangeRequestAffectedItem",
    "ChangeRequest",
    "Adr",
    "Risk",
    "Goal",
    "MainGoal",
    "Issue",
]


class Migration(migrations.Migration):

    dependencies = [
        ("application", "0023_crai_tenant_scoped"),
        # Layer 0 must have adopted the models before this app lets go of them.
        ("persistence", "0071_adopt_layer2_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Intentionally empty: the tables stay exactly as they are.
            database_operations=[],
            state_operations=[migrations.DeleteModel(name=name) for name in MOVED],
        ),
    ]
