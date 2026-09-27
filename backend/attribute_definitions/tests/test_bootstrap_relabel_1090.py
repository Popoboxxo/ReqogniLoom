"""``bootstrap_attribute_definitions --relabel``: the label-repair mode (#1090).

The gap this closes. The bootstrap command used to emit ``{"de": name, "en":
name}`` for every model-introspected core attribute — the raw field name as
BOTH locales. The German terms shipped afterwards in
``stage_matrix.CORE_ATTRIBUTE_LABELS_DE``, so the fix only reached definitions
bootstrapped AFTER that change: on an existing instance #1090 stays broken, and
the only current remedy was ``--reset``, which documentedly discards every admin
customization of the global rows (and, for a label repair, is the wrong tool
outright).

What is pinned here, each as its own test because each is a way this mode could
quietly become ``--reset``:

* it repairs a label that still holds the raw field name;
* an admin customization of any NON-label property survives;
* an admin-added attribute and the sections list survive;
* it is idempotent — a second run performs no write at all (no version bump),
  not merely an identical one;
* it never rewrites a customized workspace-level row, and does propagate to a
  non-customized one;
* it refuses to be combined with ``--reset`` instead of silently picking one;
* it composes with ``--sync-new-fields`` and leaves an already-current row
  completely alone by default (the flag is what opts in).
"""
from __future__ import annotations

import copy
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    RELABEL_KEYS,
)
from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
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


def _break_labels(row: GlobalAttributeDefinition, names: tuple[str, ...]) -> None:
    """Simulate a pre-#1090 row: the raw field name in BOTH label locales."""
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        if attribute["name"] in names:
            attribute["label"] = {"de": attribute["name"], "en": attribute["name"]}
    row.definition_json = payload
    row.save(update_fields=["definition_json"])


# --- the repair itself ------------------------------------------------------


@pytest.mark.django_db
def test_relabel_repairs_a_label_that_still_holds_the_raw_field_name(tenant) -> None:
    _seed(tenant)
    row = _row(tenant)
    _break_labels(row, ("title", "description"))

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    # The German term from stage_matrix.CORE_ATTRIBUTE_LABELS_DE.
    assert by_name["title"]["label"]["de"] == "Titel"
    assert by_name["description"]["label"]["de"] == "Beschreibung"
    # No core attribute may keep a label that is literally its own field name in
    # BOTH locales — that is the #1090 signature.
    leaked = [
        name
        for name, a in by_name.items()
        if a["label"] == {"de": name, "en": name} and name != "id"
    ]
    assert leaked == [], f"still a field-name leak: {sorted(leaked)}"


@pytest.mark.django_db
def test_relabel_overwrites_only_label_and_help_text(tenant) -> None:
    """The whole promise of the mode: labels yes, everything else no."""
    _seed(tenant)
    row = _row(tenant)
    _break_labels(row, ("title",))
    # An admin customization of every property class that is NOT in RELABEL_KEYS.
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        if attribute["name"] == "title":
            attribute["section"] = "header"
            attribute["order"] = 999
            attribute["audience"] = "expert"
            attribute["visible"] = False
            attribute["required"] = False
            attribute["editable"] = "automation"
    payload["attributes"].append(
        {"name": "admin_only", "kind": "extended", "type": "text", "section": "general"}
    )
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    title = by_name["title"]
    assert title["label"]["de"] == "Titel", "the label itself must be repaired"
    for key, value in (
        ("section", "header"),
        ("order", 999),
        ("audience", "expert"),
        ("visible", False),
        ("required", False),
        ("editable", "automation"),
    ):
        assert title[key] == value, f"--relabel clobbered {key!r}"
    assert "admin_only" in by_name, "--relabel dropped an admin-added attribute"
    # The stored attribute ORDER is a visible customization too.
    assert list(by_name) == [a["name"] for a in payload["attributes"]]


@pytest.mark.django_db
def test_relabel_preserves_the_sections_list(tenant) -> None:
    _seed(tenant)
    row = _row(tenant)
    _break_labels(row, ("title",))
    payload = copy.deepcopy(row.definition_json)
    payload["sections"] = [
        {"name": "header", "order": 0, "visible": True, "layout": "full"},
        {"name": "classification", "order": 1, "visible": False, "layout": "full"},
    ]
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    row.refresh_from_db()
    assert row.definition_json["sections"] == payload["sections"]


@pytest.mark.django_db
def test_relabel_is_idempotent_and_writes_nothing_on_a_second_run(tenant) -> None:
    """A second run must not merely produce the same JSON — it must not write.

    A write bumps ``version``, propagates to every derived workspace row and
    drops their caches, so a "harmless" rewrite on every invocation would be a
    cache-thrashing no-op that also hides a real change from an operator
    diffing two runs.
    """
    _seed(tenant)
    _break_labels(_row(tenant), ("title",))

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )
    first = _row(tenant)
    first_version = first.version
    first_json = copy.deepcopy(first.definition_json)

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )
    second = _row(tenant)

    assert second.definition_json == first_json
    assert second.version == first_version, "an idempotent re-run bumped version"


@pytest.mark.django_db
def test_relabel_is_a_no_op_on_an_already_current_definition(tenant) -> None:
    _seed(tenant)
    before = _row(tenant)
    before_version = before.version
    before_json = copy.deepcopy(before.definition_json)

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    after = _row(tenant)
    assert after.definition_json == before_json
    assert after.version == before_version


@pytest.mark.django_db
def test_relabel_reports_how_many_rows_it_touched(tenant) -> None:
    from io import StringIO

    _seed(tenant)
    _break_labels(_row(tenant), ("title",))
    out = StringIO()
    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        relabel=True,
        stdout=out,
    )
    # 11 item types x 3 presets; exactly one row carried a broken label.
    assert "1 relabelled" in out.getvalue(), out.getvalue()


# --- workspace rows ---------------------------------------------------------


@pytest.mark.django_db
def test_relabel_never_rewrites_a_customized_workspace_row(tenant) -> None:
    """A workspace that customized its definition owns that data."""
    _seed(tenant)
    global_row = _row(tenant)
    _break_labels(global_row, ("title",))

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_row = ws_store.resolve(tenant.id, ws_id, "Risk", "standard")
    customized = copy.deepcopy(ws_row.definition_json)
    for attribute in customized["attributes"]:
        if attribute["name"] == "title":
            attribute["label"] = {"de": "Eigenes Titel-Label", "en": "Custom"}
    ws_row.definition_json = customized
    ws_row.is_customized = True
    ws_row.save(update_fields=["definition_json", "is_customized"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    ws_row.refresh_from_db()
    assert ws_row.is_customized is True
    by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
    assert by_name["title"]["label"] == {"de": "Eigenes Titel-Label", "en": "Custom"}


@pytest.mark.django_db
def test_relabel_propagates_to_a_non_customized_workspace_row(tenant) -> None:
    """A workspace that never customized mirrors the global default, so it must
    receive the repaired label too — otherwise the fix is invisible for exactly
    the deployments that never touched the editor."""
    _seed(tenant)
    _break_labels(_row(tenant), ("title",))

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_row = ws_store.resolve(tenant.id, ws_id, "Risk", "standard")
    assert ws_row.is_customized is False

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), relabel=True
    )

    ws_row.refresh_from_db()
    by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
    assert by_name["title"]["label"]["de"] == "Titel"
    assert (
        WorkspaceAttributeDefinition.unscoped.filter(
            workspace_id=ws_id, is_customized=False
        ).exists()
    )


# --- flag interaction -------------------------------------------------------


@pytest.mark.django_db
def test_relabel_with_reset_is_refused(tenant) -> None:
    _seed(tenant)
    with pytest.raises(CommandError, match="--relabel cannot be combined"):
        call_command(
            "bootstrap_attribute_definitions",
            "--tenant",
            str(tenant.id),
            relabel=True,
            reset=True,
        )


@pytest.mark.django_db
def test_relabel_composes_with_sync_new_fields(tenant) -> None:
    """A row that predates a new model column has to be relabelled BEFORE the
    column is appended, or the appended attribute ships without its label."""
    _seed(tenant)
    row = _row(tenant)
    payload = copy.deepcopy(row.definition_json)
    payload["attributes"] = [a for a in payload["attributes"] if a["name"] != "title"]
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        relabel=True,
        sync_new_fields=True,
    )

    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert "title" in by_name, "--sync-new-fields did not run"
    assert by_name["title"]["label"]["de"] == "Titel", "appended attribute unlabelled"


@pytest.mark.django_db
def test_without_the_flag_an_existing_definition_is_untouched(tenant) -> None:
    """The regression guard for the default path: --relabel is opt-in."""
    _seed(tenant)
    row = _row(tenant)
    _break_labels(row, ("title",))
    before = copy.deepcopy(row.definition_json)

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))

    row.refresh_from_db()
    assert row.definition_json == before


def test_relabel_keys_are_labels_and_help_text_only() -> None:
    """A structural guard, so widening the write set cannot happen unnoticed."""
    assert RELABEL_KEYS == ("label", "help_text")
