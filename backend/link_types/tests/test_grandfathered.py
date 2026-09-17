"""Observed-but-uncovered pairs are added to the built-ins, never invented."""
from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition
from link_types.grandfathered import (
    GRANDFATHERED_PAIRS,
    apply_grandfathered_pairs,
)
from link_types.migrations._seed_helpers import seed_tenant
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from link_types.schema import validate_definition_json
from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext

#: The migration module cannot be imported with a normal ``import`` — its name
#: starts with a digit.
_migration = importlib.import_module(
    "link_types.migrations.0004_grandfather_observed_pairs"
)


def test_every_grandfathered_key_is_a_known_link_type():
    assert set(GRANDFATHERED_PAIRS) <= set(BUILTIN_LINK_TYPES)


def test_every_grandfathered_pair_has_both_sides():
    for key, pairs in GRANDFATHERED_PAIRS.items():
        for pair in pairs:
            assert set(pair) == {"source_type", "target_type"}, key
            assert pair["source_type"] and pair["target_type"], key


def test_applying_grandfathered_pairs_keeps_the_definition_valid():
    for key in BUILTIN_LINK_TYPES:
        merged = apply_grandfathered_pairs(builtin_definition(key), key)
        assert validate_definition_json(merged, key=key)


def test_applying_is_additive_and_never_removes_a_builtin_pair():
    for key in BUILTIN_LINK_TYPES:
        original = builtin_definition(key)["allowed_pairs"]
        merged = apply_grandfathered_pairs(builtin_definition(key), key)["allowed_pairs"]
        for pair in original:
            assert pair in merged, f"{key}: built-in pair {pair} was dropped"


def test_applying_does_not_duplicate_an_already_covered_pair():
    key = "verifies"
    definition = builtin_definition(key)
    merged = apply_grandfathered_pairs(definition, key)["allowed_pairs"]
    assert len(merged) == len({(p["source_type"], p["target_type"]) for p in merged})


def test_applying_is_a_no_op_for_a_key_with_no_grandfathered_pairs():
    key = next(k for k in BUILTIN_LINK_TYPES if k not in GRANDFATHERED_PAIRS)
    assert (
        apply_grandfathered_pairs(builtin_definition(key), key)["allowed_pairs"]
        == builtin_definition(key)["allowed_pairs"]
    )


def test_applying_does_not_mutate_the_input():
    key = next(iter(GRANDFATHERED_PAIRS), "verifies")
    definition = builtin_definition(key)
    before = len(definition["allowed_pairs"])
    apply_grandfathered_pairs(definition, key)
    assert len(definition["allowed_pairs"]) == before


# --------------------------------------------------------------------------
# The migration itself. Both tests run with no tenant in the thread-local
# context, which is the state a real ``manage.py migrate`` is in.
#
# Note on what these do *not* prove: the role the test suite connects as is a
# BYPASSRLS superuser, so dropping the per-tenant ``app.current_tenant``
# arming from the migration keeps them green (verified by removing it). The
# arming is there for a deployment whose DB owner is not BYPASSRLS — where the
# ``lt_*`` FORCE-RLS policy makes an unarmed UPDATE match nothing and still
# report success. That case cannot be reproduced from here; it is covered by
# keeping the shape identical to ``0003_seed_builtin_link_types``, which was
# live-verified against a real database in Task 8.
# --------------------------------------------------------------------------


class _SchemaEditor:
    """Minimal stand-in for the ``schema_editor`` a ``RunPython`` receives."""

    connection = connection


class _Apps:
    """Stand-in for the historical ``apps`` a ``RunPython`` receives.

    Historical models carry a plain manager, but the live ``lt_*`` models
    default to the tenant-scoped one, which raises without a thread-local
    tenant. Mapping ``objects`` onto ``unscoped`` reproduces what the
    migration actually sees: an unfiltered queryset whose isolation comes
    from RLS alone — exactly the condition the arming has to satisfy.
    """

    @staticmethod
    def get_model(app_label: str, model_name: str):
        model = django_apps.get_model(app_label, model_name)
        return SimpleNamespace(objects=getattr(model, "unscoped", model.objects))


@pytest.fixture
def seeded_tenant():
    row = Tenant.objects.create(name="lt-gf-test", slug=f"lt-gf-{uuid.uuid4().hex}")
    TenantContext.set_tenant(row.id)
    workspace = Workspace.objects.create(tenant=row, name="ws")
    seed_tenant(row.id, [workspace.id])
    yield row, workspace
    TenantContext.clear_tenant()


def _unarm():
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")


@pytest.mark.django_db
def test_migration_extends_the_seeded_rows_of_every_tenant(seeded_tenant):
    tenant, workspace = seeded_tenant
    key = next(iter(GRANDFATHERED_PAIRS))
    expected = apply_grandfathered_pairs(builtin_definition(key), key)["allowed_pairs"]

    TenantContext.clear_tenant()
    _unarm()
    _migration.apply_pairs(_Apps(), _SchemaEditor())

    TenantContext.set_tenant(tenant.id)
    global_row = GlobalLinkTypeDefinition.unscoped.get(tenant_id=tenant.id, key=key)
    workspace_row = WorkspaceLinkTypeDefinition.unscoped.get(
        tenant_id=tenant.id, workspace_id=workspace.id, key=key
    )
    assert global_row.definition_json["allowed_pairs"] == expected
    assert workspace_row.definition_json["allowed_pairs"] == expected


@pytest.mark.django_db
def test_0007_reapplies_a_pair_added_after_0004_already_ran(seeded_tenant):
    """A code-only widening of the allowlist never reaches an existing tenant.

    ``0004`` merges the allowlist into the seeded rows once. Issue #893 added
    ``references`` Requirement -> Requirement afterwards, so without ``0007``
    the pair would exist for freshly provisioned workspaces only and every
    already-installed tenant would keep rejecting the very rows the fix makes
    the data migration accept.
    """
    reapply = importlib.import_module(
        "link_types.migrations.0007_backfill_grandfathered_pairs_issue893"
    )
    tenant, workspace = seeded_tenant
    row = WorkspaceLinkTypeDefinition.unscoped.get(
        tenant_id=tenant.id, workspace_id=workspace.id, key="references"
    )
    # Rewind to a catalog seeded before the pair was added.
    row.definition_json = {
        **row.definition_json,
        "allowed_pairs": [
            pair
            for pair in row.definition_json["allowed_pairs"]
            if (pair["source_type"], pair["target_type"])
            != ("Requirement", "Requirement")
        ],
    }
    row.save(update_fields=["definition_json"])

    TenantContext.clear_tenant()
    _unarm()
    reapply.apply_pairs(_Apps(), _SchemaEditor())

    TenantContext.set_tenant(tenant.id)
    row.refresh_from_db()
    assert {"source_type": "Requirement", "target_type": "Requirement"} in (
        row.definition_json["allowed_pairs"]
    )


@pytest.mark.django_db
def test_migration_leaves_a_customized_workspace_row_alone(seeded_tenant):
    tenant, workspace = seeded_tenant
    key = next(iter(GRANDFATHERED_PAIRS))
    row = WorkspaceLinkTypeDefinition.unscoped.get(
        tenant_id=tenant.id, workspace_id=workspace.id, key=key
    )
    row.definition_json = {**row.definition_json, "allowed_pairs": []}
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])

    TenantContext.clear_tenant()
    _unarm()
    _migration.apply_pairs(_Apps(), _SchemaEditor())

    TenantContext.set_tenant(tenant.id)
    row.refresh_from_db()
    assert row.definition_json["allowed_pairs"] == []
