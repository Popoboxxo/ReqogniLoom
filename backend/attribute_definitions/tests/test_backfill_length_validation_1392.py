"""``--backfill-length-validation`` repairs pre-#1392 rows (GitHub #1392).

ROOT CAUSE this module pins
---------------------------
:func:`introspect_core_attributes` publishes each text column's own
``max_length`` as ``validation.length``, but that only reaches rows the command
*seeds*. An instance bootstrapped before #1392 shipped keeps its stored
attribute list verbatim, so its dialogs still render unbounded controls for a
column the server rejects at 200/255/500 characters.

The repair is the same shape as ``--relabel`` (#1090): an opt-in, additive,
idempotent mode that fills what is absent and preserves every admin
customization. These are real-DB tests because the mode's whole contract is
about an already-persisted row.
"""
from __future__ import annotations

import copy
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


def _seed(tenant: Tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))


def _row(tenant: Tenant, item_type: str = "Risk", preset: str = "standard"):
    return GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type=item_type, preset=preset
    )


def _by_name(row: GlobalAttributeDefinition) -> dict[str, dict]:
    return {a["name"]: a for a in row.definition_json["attributes"]}


def _strip_validation(row: GlobalAttributeDefinition) -> None:
    """Simulate a row bootstrapped before #1392: no ``validation`` block at all."""
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        attribute.pop("validation", None)
    row.definition_json = payload
    row.save(update_fields=["definition_json"])


# --- the repair itself ------------------------------------------------------


@pytest.mark.django_db
def test_backfill_publishes_the_column_limit(tenant) -> None:
    _seed(tenant)
    row = _row(tenant)
    _strip_validation(row)

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        backfill_length_validation=True,
    )

    row.refresh_from_db()
    by_name = _by_name(row)
    # The numbers are the model columns' own (`Risk.title` = 255), never a
    # literal invented by the client.
    assert by_name["title"]["validation"] == {"length": 255}
    # A TextField without a `max_length` stays unbounded, exactly as before (the
    # normalizer materialises an empty `validation` block, so assert on the
    # absence of a RULE, not of the key).
    assert not by_name["description"].get("validation")


@pytest.mark.django_db
def test_backfill_never_overwrites_an_admin_set_validation_rule(tenant) -> None:
    """`validation` is editable meta — an existing block is an admin decision."""
    _seed(tenant)
    row = _row(tenant)
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        if attribute["name"] == "title":
            attribute["validation"] = {"length": 42}
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        backfill_length_validation=True,
    )

    row.refresh_from_db()
    assert _by_name(row)["title"]["validation"] == {"length": 42}


@pytest.mark.django_db
def test_backfill_is_idempotent_and_writes_nothing_on_a_second_run(tenant) -> None:
    _seed(tenant)
    row = _row(tenant)
    _strip_validation(row)

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        backfill_length_validation=True,
    )
    first = _row(tenant)
    first_version = first.version
    first_json = copy.deepcopy(first.definition_json)

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        backfill_length_validation=True,
    )
    second = _row(tenant)

    assert second.definition_json == first_json
    assert second.version == first_version, "an idempotent re-run bumped version"


@pytest.mark.django_db
def test_without_the_flag_an_existing_definition_is_untouched(tenant) -> None:
    """The default path stays write-free for existing rows: the mode is opt-in."""
    _seed(tenant)
    row = _row(tenant)
    _strip_validation(row)
    before = copy.deepcopy(row.definition_json)

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))

    row.refresh_from_db()
    assert row.definition_json == before


@pytest.mark.django_db
def test_backfill_propagates_to_a_non_customized_workspace_row(tenant) -> None:
    _seed(tenant)
    _strip_validation(_row(tenant))

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_row = ws_store.resolve(tenant.id, ws_id, "Risk", "standard")
    assert ws_row.is_customized is False

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        backfill_length_validation=True,
    )

    ws_row.refresh_from_db()
    by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
    assert by_name["title"]["validation"] == {"length": 255}


@pytest.mark.django_db
def test_backfill_with_reset_is_refused(tenant) -> None:
    _seed(tenant)
    with pytest.raises(
        CommandError, match="--backfill-length-validation cannot be combined"
    ):
        call_command(
            "bootstrap_attribute_definitions",
            "--tenant",
            str(tenant.id),
            backfill_length_validation=True,
            reset=True,
        )
