"""Migration 0008 — backfill the Artifact ``id`` display properties.

Teaching ``bootstrap_attribute_definitions`` about the spec section 5 display
properties fixes every *fresh* tenant. It fixes no *already bootstrapped* one:
the ``id`` attribute exists from WS2 (#936) but the stored row has no
``reveal``/``copyable``/``mask``, and the bootstrap command's contract is
"existing rows are left alone". This migration is that repair, so its unit is
the repair itself — same split as migration 0005/0007.
"""
from __future__ import annotations

import importlib
import uuid

import pytest
from django.apps import apps as django_apps

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from persistence.models import Tenant

migration = importlib.import_module(
    "attribute_definitions.migrations.0008_backfill_id_display_props"
)


def _stale_id_attribute(**over) -> dict:
    """The ``id`` system attribute exactly as a pre-WS3 bootstrap stored it."""
    attribute = {
        "name": "id",
        "kind": "core",
        "type": "text",
        "editable": "system",
        "locked": True,
        "visible": False,
        "required": False,
        "section": "general",
        "order": -300,
        "label": {"de": "ID", "en": "ID"},
    }
    attribute.update(over)
    return attribute


def _definition() -> dict:
    return {
        "attributes": [
            _stale_id_attribute(),
            {"name": "title", "kind": "core", "type": "text", "section": "general", "order": 1},
        ]
    }


def test_backfill_sets_the_spec_props_on_the_system_id_only() -> None:
    definition = _definition()
    assert migration._backfill(definition) is True
    by_name = {a["name"]: a for a in definition["attributes"]}
    assert by_name["id"]["reveal"] == "click"
    assert by_name["id"]["copyable"] is True
    assert by_name["id"]["mask"] == "short"
    # An ordinary attribute is untouched.
    assert "reveal" not in by_name["title"]


def test_backfill_ignores_an_id_that_is_not_the_system_field() -> None:
    definition = {"attributes": [_stale_id_attribute(editable=True)]}
    assert migration._backfill(definition) is False
    assert "reveal" not in definition["attributes"][0]


def test_backfill_is_idempotent_and_survives_an_unreadable_row() -> None:
    definition = _definition()
    migration._backfill(definition)
    assert migration._backfill(definition) is False

    # A hand-edited/older row must not take the whole migration down.
    assert migration._backfill({"attributes": ["not-a-dict"]}) is False
    assert migration._backfill({"attributes": "broken"}) is False
    assert migration._backfill(None) is False


@pytest.mark.django_db
def test_forwards_backfills_an_existing_global_and_workspace_row() -> None:
    """The actual repair, run against a real stored row in both tables."""
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    global_row = GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id,
        item_type="Requirement",
        preset="standard",
        definition_json=_definition(),
    )
    ws_row = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id,
        workspace_id=uuid.uuid4(),
        item_type="Requirement",
        preset="standard",
        definition_json=_definition(),
    )

    migration.forwards(django_apps, None)

    for row in (global_row, ws_row):
        row.refresh_from_db()
        by_name = {a["name"]: a for a in row.definition_json["attributes"]}
        assert by_name["id"]["reveal"] == "click"
        assert by_name["id"]["copyable"] is True
        assert by_name["id"]["mask"] == "short"
        assert by_name["title"] == {"name": "title", "kind": "core", "type": "text", "section": "general", "order": 1}
