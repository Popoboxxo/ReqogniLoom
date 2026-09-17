"""Migration 0006 backfills the Issue pairs into already-seeded rows.

Same caveat as ``test_backfill_goal_reference_pairs.py``: the suite connects as
a BYPASSRLS role, so these tests do not prove the per-tenant
``app.current_tenant`` arming is needed — they prove the merge is additive,
idempotent and respects ``is_customized``. The arming is kept identical in
shape to ``0003``/``0004``/``0005``, which were live-verified.
"""
from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.migrations._seed_helpers import seed_tenant
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

_migration = importlib.import_module(
    "link_types.migrations.0006_backfill_issue_reference_pairs"
)

KEY = _migration.KEY

#: What the seeded rows looked like before the built-in gained the Issue pairs.
_PRE_MIGRATION_PAIRS = [
    {"source_type": "*", "target_type": "GlossaryTerm"},
    {"source_type": "*", "target_type": "Diagram"},
    {"source_type": "*", "target_type": "Icd"},
    {"source_type": "*", "target_type": "Goal"},
    {"source_type": "Goal", "target_type": "*"},
]

_NEW_PAIRS = [("*", "Issue"), ("Issue", "*")]


class _SchemaEditor:
    connection = connection


class _Apps:
    @staticmethod
    def get_model(app_label: str, model_name: str):
        model = django_apps.get_model(app_label, model_name)
        return SimpleNamespace(objects=getattr(model, "unscoped", model.objects))


def _pairs_of(row):
    return {
        (p["source_type"], p["target_type"])
        for p in row.definition_json["allowed_pairs"]
    }


def _rewind(row):
    """Put a seeded row back into its pre-0006 shape."""
    row.definition_json = {
        **row.definition_json,
        "allowed_pairs": [dict(p) for p in _PRE_MIGRATION_PAIRS],
    }
    row.save(update_fields=["definition_json"])


@pytest.fixture
def rewound_tenant():
    tenant = Tenant.objects.create(name="lt-bfi-test", slug=f"lt-bfi-{uuid.uuid4().hex}")
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name="ws")
    seed_tenant(tenant.id, [workspace.id])

    global_row = GlobalLinkTypeDefinition.unscoped.get(tenant_id=tenant.id, key=KEY)
    workspace_row = WorkspaceLinkTypeDefinition.unscoped.get(
        tenant_id=tenant.id, workspace_id=workspace.id, key=KEY
    )
    _rewind(global_row)
    _rewind(workspace_row)

    yield tenant, workspace, global_row, workspace_row
    TenantContext.clear_tenant()


def _run_migration():
    TenantContext.clear_tenant()
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
    _migration.apply_pairs(_Apps(), _SchemaEditor())


def test_the_builtin_is_the_source_of_truth_for_what_gets_backfilled():
    """Guards the migration against a later edit of the built-in it copies."""
    pairs = {
        (p["source_type"], p["target_type"])
        for p in BUILTIN_LINK_TYPES[KEY]["allowed_pairs"]
    }
    assert set(_NEW_PAIRS) <= pairs


@pytest.mark.django_db
def test_migration_adds_the_issue_pairs_to_global_and_workspace_rows(rewound_tenant):
    tenant, _workspace, global_row, workspace_row = rewound_tenant

    _run_migration()

    TenantContext.set_tenant(tenant.id)
    global_row.refresh_from_db()
    workspace_row.refresh_from_db()
    for row in (global_row, workspace_row):
        pairs = _pairs_of(row)
        assert set(_NEW_PAIRS) <= pairs
        # additive: everything 0003/0004/0005 put there survives
        assert ("*", "GlossaryTerm") in pairs
        assert ("Goal", "*") in pairs


@pytest.mark.django_db
def test_migration_is_idempotent(rewound_tenant):
    tenant, _workspace, global_row, _workspace_row = rewound_tenant

    _run_migration()
    TenantContext.set_tenant(tenant.id)
    global_row.refresh_from_db()
    after_first = list(global_row.definition_json["allowed_pairs"])

    _run_migration()
    TenantContext.set_tenant(tenant.id)
    global_row.refresh_from_db()

    assert global_row.definition_json["allowed_pairs"] == after_first


@pytest.mark.django_db
def test_migration_leaves_a_customized_workspace_row_alone(rewound_tenant):
    tenant, _workspace, _global_row, workspace_row = rewound_tenant
    workspace_row.is_customized = True
    workspace_row.save(update_fields=["is_customized"])

    _run_migration()

    TenantContext.set_tenant(tenant.id)
    workspace_row.refresh_from_db()
    assert _pairs_of(workspace_row) == {
        (p["source_type"], p["target_type"]) for p in _PRE_MIGRATION_PAIRS
    }
