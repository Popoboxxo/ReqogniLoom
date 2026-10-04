"""Bootstrap command: introspection output and idempotency."""
from __future__ import annotations

import copy
import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from attribute_definitions.global_definition_store import (
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    ARTIFACT_LEVEL_CORE_ATTRIBUTES,
    BOOTSTRAP_ITEM_TYPES,
    EXCLUDED_MODEL_FIELDS,
    PRESETS,
    SYSTEM_FIELDS_ENABLED_ITEM_TYPES,
    Command,
    introspect_core_attributes,
    synthetic_status_attribute,
)
from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


def test_eleven_item_types_are_covered() -> None:
    assert BOOTSTRAP_ITEM_TYPES == (
        "Requirement", "StakeholderNeed", "ArchitectureElement", "TestCase",
        "Adr", "Risk", "Issue", "Goal", "Icd", "GlossaryTerm", "ChangeRequest",
    )


def test_synthetic_status_is_locked_and_workflow_editable() -> None:
    status = synthetic_status_attribute()
    assert status["name"] == "status"
    assert status["kind"] == "core"
    assert status["locked"] is True
    assert status["editable"] == "workflow"
    assert status["visible"] is True


# --- Attribut v3 WS2 (#936): Artifact-level system attributes ---------------


@pytest.mark.django_db
def test_artifact_level_system_attributes_are_discovered_for_every_type() -> None:
    """Spec section 3: ``id``/``owner``/``reporter``/``priority`` live on
    ``Artifact``, so every item type must expose them as core attributes even
    though they are not columns of the per-type model."""
    expected = {entry["name"] for entry in ARTIFACT_LEVEL_CORE_ATTRIBUTES}
    assert expected == {"id", "owner", "reporter", "priority"}
    for item_type in BOOTSTRAP_ITEM_TYPES:
        by_name = {
            a["name"]: a for a in introspect_core_attributes(item_type, "standard")
        }
        for name in sorted(expected):
            assert name in by_name, f"{item_type}.{name}"
            assert by_name[name]["kind"] == "core", f"{item_type}.{name}"


@pytest.mark.django_db
def test_id_is_a_synthetic_system_attribute() -> None:
    """Spec sections 3/5/6: ``id`` is server-owned, locked and hidden."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        by_name = {
            a["name"]: a for a in introspect_core_attributes(item_type, "standard")
        }
        id_attr = by_name["id"]
        assert id_attr["editable"] == "system", item_type
        assert id_attr["locked"] is True, item_type
        assert id_attr["visible"] is False, item_type
        assert id_attr["required"] is False, item_type
        # Spec section 5 / WS3 #937: the id field is the first consumer of the
        # generic display properties.
        assert id_attr["reveal"] == "click", item_type
        assert id_attr["copyable"] is True, item_type
        assert id_attr["mask"] == "short", item_type


@pytest.mark.django_db
def test_priority_carries_the_default_scale_as_enum_options() -> None:
    """Spec section 3: priority is an enum with the default
    ``low|medium|high|critical`` scale, configurable per definition."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        by_name = {
            a["name"]: a for a in introspect_core_attributes(item_type, "standard")
        }
        priority = by_name["priority"]
        assert priority["type"] == "enum", item_type
        assert [o["value"] for o in priority["options"]] == [
            "low",
            "medium",
            "high",
            "critical",
        ], item_type
        assert all(o["label_de"] and o["label_en"] for o in priority["options"])


@pytest.mark.django_db
def test_system_field_visibility_follows_the_transport_rollout_gate() -> None:
    """WS2 gates ``owner``/``reporter``/``priority`` per item type (#936).

    A field is flipped visible/writable only for the types whose REST **and**
    MCP transports carry it; the rest keep the hidden, read-only carrier so the
    contract matrix (#934 WS0) never demands a round-trip no transport can
    satisfy. WS7 (#940) added ``Risk`` to the gate after renaming its legacy
    free-text ``owner`` column to ``owner_name``.
    """
    for item_type in BOOTSTRAP_ITEM_TYPES:
        by_name = {
            a["name"]: a for a in introspect_core_attributes(item_type, "standard")
        }
        enabled = item_type in SYSTEM_FIELDS_ENABLED_ITEM_TYPES
        for name in ("owner", "reporter", "priority"):
            assert by_name[name]["visible"] is enabled, f"{item_type}.{name}"
            assert by_name[name]["editable"] is enabled, f"{item_type}.{name}"
        # owner/reporter are the actor type in both states (spec section 4).
        assert by_name["owner"]["type"] == "actor", item_type
        assert by_name["reporter"]["type"] == "actor", item_type
        assert by_name["owner"]["multiple"] is False, item_type
        assert by_name["owner"]["allow_external"] is False, item_type



@pytest.mark.django_db
def test_every_attribute_is_core_or_extended_and_names_are_unique() -> None:
    """Epic #934 WS6 (#939): the definition mixes model-backed ``core``
    attributes with the matrix's ``extended`` ones (``custom_fields`` carrier),
    but a name is still defined exactly once."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        assert attributes, f"{item_type} produced no attributes"
        assert all(a["kind"] in ("core", "extended") for a in attributes)
        names = [a["name"] for a in attributes]
        assert len(names) == len(set(names)), item_type


@pytest.mark.django_db
def test_dropped_status_columns_are_never_introspected() -> None:
    """P1/D6: the Datenmodell-Konsolidierung drops these columns; the bootstrap
    must produce the same output before and after that migration."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        by_name = {a["name"]: a for a in attributes}
        assert "lifecycle_status" not in by_name, item_type
        assert by_name["status"]["locked"] is True, item_type
        assert by_name["status"]["editable"] == "workflow", item_type


@pytest.mark.django_db
def test_infrastructure_columns_are_excluded() -> None:
    attributes = introspect_core_attributes("Requirement", "standard")
    names = {a["name"] for a in attributes}
    # ``status`` and the artifact-level ``id`` are deliberately re-introduced
    # from their synthetic sources (synthetic_status_attribute /
    # ARTIFACT_LEVEL_CORE_ATTRIBUTES) even though they sit in
    # EXCLUDED_MODEL_FIELDS, which governs the *model* introspection loop only.
    synthetic = {"status"} | {
        entry["name"] for entry in ARTIFACT_LEVEL_CORE_ATTRIBUTES
    }
    assert not (names & (EXCLUDED_MODEL_FIELDS - synthetic))


@pytest.mark.django_db
def test_choices_become_enum_options() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    probability = attributes["probability"]
    assert probability["type"] == "enum"
    assert {o["value"] for o in probability["options"]} == {"low", "medium", "high"}
    assert all(o["label_de"] and o["label_en"] for o in probability["options"])


@pytest.mark.django_db
def test_text_field_becomes_textarea_and_charfield_becomes_text() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert attributes["title"]["type"] == "text"
    assert attributes["description"]["type"] == "textarea"


@pytest.mark.django_db
def test_curated_widgets_are_added_with_their_bound_fields() -> None:
    risk = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    assert risk["risk_matrix"]["type"] == "widget"
    assert risk["risk_matrix"]["widget_key"] == "risk_matrix_rpz"
    assert risk["risk_matrix"]["fields"] == ["probability", "impact", "detection"]

    adr = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert adr["decision_record"]["widget_key"] == "markdown_tab_group"
    assert adr["decision_record"]["fields"] == ["description", "context", "consequences"]

    testcase = {a["name"]: a for a in introspect_core_attributes("TestCase", "standard")}
    assert testcase["steps"]["widget_key"] == "steps_editor"
    assert testcase["steps"]["fields"] == ["steps_data"]

    # Task 25: same single-field `markdown_tab_group` binding
    # ArchitectureElement's `description_editor` uses (Task 24) — parity fix
    # for the deleted `RequirementForm`'s `<MarkdownPreview>` edit/preview
    # toggle, which the generic `textarea` field type has no equivalent for.
    requirement = {a["name"]: a for a in introspect_core_attributes("Requirement", "standard")}
    assert requirement["description_editor"]["widget_key"] == "markdown_tab_group"
    assert requirement["description_editor"]["fields"] == ["description"]
    # The raw `description` attribute still exists; the widget only claims it
    # client-side (`ArtifactForm.tsx`'s `widgetOwned`).
    assert "description" in requirement


@pytest.mark.django_db
def test_widget_claimed_json_columns_are_not_duplicated_as_raw_textareas() -> None:
    """Task 22 finding: a JSONField a widget's ``fields`` list claims (TestCase
    ``steps`` -> ``steps_data``, Issue ``tags``) used to ALSO survive as a bare
    ``textarea`` core attribute bound to the same key — a second, competing
    editor for one value. For TestCase this was worse: the fallback surfaced
    under the alias name ``steps_data``, which the backend has never accepted
    as a real field. Neither alias name should appear as its own attribute;
    only the widget entry represents the column.
    """
    testcase = {a["name"]: a for a in introspect_core_attributes("TestCase", "standard")}
    assert "steps_data" not in testcase
    assert testcase["steps"]["type"] == "widget"

    issue = {a["name"]: a for a in introspect_core_attributes("Issue", "standard")}
    assert "tags" not in issue
    assert issue["tag_list"]["type"] == "widget"


@pytest.mark.django_db
def test_preset_mandatory_fields_do_not_drive_create_required_on_requirement() -> None:
    """``required`` is a create-payload contract, ``mandatory_fields`` is not.

    The introspector used to force ``required=True`` on every Requirement
    attribute named in the preset's ``mandatory_fields``. Since Task 11 makes
    ``required`` an enforced **create** gate, that turned a policy about
    *approval readiness* into a policy about *create payloads* and 400'd every
    minimal Requirement create on standard/extended with
    "acceptance_criteria: is required".

    ``workflow.precondition_rules`` rule 5 gates the approval transition and
    reads the definition-scoped source (#912: ``required`` flags, with the
    legacy Requirement list folded in). Only the model can make a field required
    at create time, so ``title`` (``blank=False``, no default) stays required on
    every preset while ``description``/``acceptance_criteria`` (both
    ``blank=True``) do not.
    """
    by_preset = {
        preset: {a["name"]: a for a in introspect_core_attributes("Requirement", preset)}
        for preset in ("minimal", "standard", "extended")
    }
    for preset, attributes in by_preset.items():
        assert attributes["title"]["required"] is True, preset
        assert attributes["description"]["required"] is False, preset
        assert attributes["acceptance_criteria"]["required"] is False, preset


@pytest.mark.django_db
def test_command_seeds_one_row_per_item_type_and_preset(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    rows = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id)
    assert rows.count() == len(BOOTSTRAP_ITEM_TYPES) * len(PRESETS)


@pytest.mark.django_db
def test_command_warns_about_mandatory_fields_only_for_requirement(tenant) -> None:
    """#912: the migrate-time warning fired for 10/11 item types (22 lines).

    Two scoping passes are pinned here:

    * the legacy list is Requirement-only, so no other item type may be
      reported at all;
    * even Requirement's list is fully *consumed* by the time this check runs —
      ``priority`` is an artifact-level attribute (Attribut v3 WS2, #936),
      ``classification`` aliases the ``type`` column, ``change_reason`` is
      evaluated by rule 5 and ``traceability_target`` is rule 7's Extended
      lever — so a clean migrate is silent. The pre-#912 output claimed all of
      them were "ignored" while the approval gate enforced them.

    The check is still alive for a genuinely dead entry; see
    ``workflow/tests/test_policy_field_consumers.py``.
    """
    from io import StringIO

    out = StringIO()
    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), stdout=out
    )
    output = out.getvalue()
    assert "mandatory_fields" not in output, output
    for item_type in BOOTSTRAP_ITEM_TYPES:
        assert f"{item_type}/" not in output, output


@pytest.mark.django_db
def test_command_is_idempotent_and_preserves_curated_meta(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    attributes = row.definition_json["attributes"]
    for attribute in attributes:
        if attribute["name"] == "title":
            attribute["section"] = "header"
    row.definition_json = {"attributes": attributes}
    row.save(update_fields=["definition_json"])

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert by_name["title"]["section"] == "header"
    assert GlobalAttributeDefinition.unscoped.filter(
        tenant_id=tenant.id
    ).count() == len(BOOTSTRAP_ITEM_TYPES) * len(PRESETS)


@pytest.mark.django_db
def test_sync_new_fields_appends_without_touching_existing_entries(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    for attribute in kept:
        attribute["audience"] = "expert"
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert "detection" in by_name
    assert by_name["probability"]["audience"] == "expert"


@pytest.mark.django_db
def test_sync_new_fields_propagates_to_non_customized_workspace_rows(tenant) -> None:
    """Ledger binding (k), Task 6 review I-1: ``_append_missing`` used to write

    via a bare ``row.save()``, bypassing ``GlobalAttributeDefinitionStore
    .update()``'s ``_propagate()`` step, leaving every non-customized
    workspace row permanently out of sync with the global default."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_row = ws_store.resolve(tenant.id, ws_id, "Risk", "standard")
    assert "detection" not in {a["name"] for a in ws_row.definition_json["attributes"]}

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    ws_row.refresh_from_db()
    assert "detection" in {a["name"] for a in ws_row.definition_json["attributes"]}


@pytest.mark.django_db
def test_sync_new_fields_invalidates_the_cache_for_propagated_workspaces(
    tenant, monkeypatch
) -> None:
    """Task 7 review I-2: ``_append_missing`` calls ``store._propagate()``
    directly, a bulk ``QuerySet.update()`` that bypasses save()/signals and
    therefore the shared cache. Without an explicit invalidation, a warm
    worker keeps serving the pre-sync definition for the propagated
    workspace."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    ws_store = WorkspaceAttributeDefinitionStore()
    ws_id = uuid.uuid4()
    ws_store.resolve(tenant.id, ws_id, "Risk", "standard")

    calls: list[str] = []
    monkeypatch.setattr(
        "attribute_definitions.management.commands.bootstrap_attribute_definitions."
        "invalidate_workspace_caches",
        lambda workspace_id: calls.append(workspace_id),
    )
    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    assert str(ws_id) in calls


@pytest.mark.django_db
def test_command_arms_and_clears_tenant_context(tenant, monkeypatch) -> None:
    """Ledger binding (l), Task 6 review I-2: regression for the tenant-arming

    fix — testable without an RLS-enabled DB role (unlike the RLS policy
    itself) by spying on the two isolation calls the command must pair around
    each tenant's work."""
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "persistence.middleware.set_request_tenant",
        lambda tenant_id: calls.append(("set", tenant_id)),
    )
    monkeypatch.setattr(
        "persistence.middleware.clear_request_tenant",
        lambda: calls.append(("clear", None)),
    )
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    assert calls == [("set", str(tenant.id)), ("clear", None)]


# --- Ledger item (e), site 3: _append_missing normalizes the STORED row -----


@pytest.mark.django_db
def test_sync_new_fields_on_a_legacy_shaped_row_is_a_schema_error(tenant) -> None:
    """`{a["name"] for a in stored}` used to take the command down with KeyError."""
    from attribute_definitions.models import GlobalAttributeDefinition
    from attribute_definitions.schema import AttributeSchemaError

    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant.id, "Risk", "standard", [{"name": "title", "kind": "core", "type": "text"}]
    )
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    row.definition_json = {"attributes": [{"type": "text", "kind": "core"}]}
    row.save(update_fields=["definition_json"])
    with pytest.raises(AttributeSchemaError):
        Command._append_missing(
            store, row, [{"name": "title", "kind": "core", "type": "text"}]
        )


# --- Ledger item (f): --reset is the operator-facing recovery path ----------


@pytest.mark.django_db
def test_reset_rebuilds_a_definition_a_bad_seed_had_made_unrepairable(tenant) -> None:
    from django.core.management import call_command

    store = GlobalAttributeDefinitionStore()
    store.initialize(
        tenant.id, "Risk", "standard",
        [{"name": "oops", "kind": "core", "type": "text", "locked": True}],
    )
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id), reset=True)
    names = {
        a["name"]
        for a in store.get(tenant.id, "Risk", "standard").definition_json["attributes"]
    }
    assert "oops" not in names
    assert "title" in names


# --- Task 11: server-owned columns are not user-facing attributes -----------


def test_server_owned_columns_are_not_introspected_as_required() -> None:
    """They are blank=False, so they used to make their own type uncreatable."""
    for item_type, column in (
        ("Requirement", "suspect"),
        ("Goal", "lineage_id"),
        ("Goal", "sequence_number"),
        ("Icd", "current_revision"),
    ):
        names = {a["name"] for a in introspect_core_attributes(item_type, "standard")}
        assert column not in names, f"{item_type}.{column}"


# --- Task 19 fix round: no introspected attribute may be PATCH-protected ----
# and simultaneously editable. C-1: `uid` was introspected as editable=True
# for every item type while also being a `_PROTECTED_PATCH_FIELDS` entry
# (rest_api/mixins/workflow_transitions.py) that the REST layer rejects
# outright on PATCH — a 400 on every single save through any
# ArtifactForm-driven item type. This is a structural, reusable check (not
# just a Risk/uid special case) so a future bootstrapped column landing in
# both sets fails the suite immediately instead of shipping silently, as this
# one did.


def _protected_patch_fields() -> frozenset[str]:
    from rest_api.mixins.workflow_transitions import _PROTECTED_PATCH_FIELDS

    return _PROTECTED_PATCH_FIELDS


@pytest.mark.django_db
def test_no_introspected_attribute_is_both_protected_and_editable() -> None:
    protected = _protected_patch_fields()
    for item_type in BOOTSTRAP_ITEM_TYPES:
        for preset in PRESETS:
            for attribute in introspect_core_attributes(item_type, preset):
                # Scoped to ``core``: the protected set describes *top-level*
                # PATCH keys, and only core attributes travel top-level. An
                # extended attribute (e.g. the matrix's Icd ``version``) is
                # nested under ``custom_fields`` and validated by
                # ``field_validation`` against the definition instead.
                if attribute["kind"] == "core" and attribute["name"] in protected:
                    # ``system`` (spec section 6) and ``workflow`` are both
                    # "never a client PATCH field"; plain ``False`` is the
                    # third non-writable value. Only True is a violation.
                    assert attribute["editable"] in (False, "system", "workflow", "automation"), (
                        f"{item_type}/{preset}: '{attribute['name']}' is "
                        "PATCH-protected but introspected as editable "
                        f"({attribute['editable']!r})"
                    )


@pytest.mark.django_db
def test_uid_is_visible_but_not_editable_on_every_item_type() -> None:
    """uid is a real, serializer-declared, read-only column everywhere it
    exists — it must stay VISIBLE (unlike created_by_name, which is excluded
    entirely because no serializer exposes it at all) but never editable."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        by_name = {a["name"]: a for a in introspect_core_attributes(item_type, "standard")}
        if "uid" not in by_name:
            continue
        assert by_name["uid"]["visible"] is True, item_type
        assert by_name["uid"]["editable"] is False, item_type


# --- Task 22 review round 1, C-1: editable core attribute must be a real, -----
# writable serializer field. Broader than the uid-specific check above: this
# would have caught C-1 (TestCase.test_type introspected as editable, but
# TestCaseSerializer never declared it -> 400 on every PATCH that touched it)
# AND, retroactively, Task 19's owner_user and Task 24's parent bug classes
# (both fixed by aliasing the introspected attribute name onto the real FK-id
# serializer field name, e.g. "owner_user" -> "owner_user_id").
#
# Scoped to real per-field attributes (`type != "widget"`) on purpose:
# WIDGET_ATTRIBUTES entries (TestCase's `steps` widget bound to the
# internal-only form key `steps_data`, ArchitectureElement's
# `description_editor`, Issue's `tag_list`) are `kind == "core"` too but are
# a deliberate, separate translation layer the owning ArtifactForm component
# handles itself (see TestCaseArtifactForm's STEPS_WIRE_FIELD/STEPS_FORM_FIELD
# docstring) — their `name` is intentionally not a serializer field (that is
# the point of the alias/split), so this check would false-positive on every
# one of them without the `type != "widget"` exclusion.


def _serializer_for_item_type(item_type: str):
    """Return the DRF serializer class backing *item_type*'s PATCH endpoint,
    or None if the item type has no DRF serializer (Icd: its REST layer
    parses `request.data` directly, see icd/contract_validator.py)."""
    from rest_api import serializers as rest_serializers

    return {
        "Requirement": rest_serializers.RequirementSerializer,
        "StakeholderNeed": rest_serializers.StakeholderNeedSerializer,
        "ArchitectureElement": rest_serializers.ArchitectureElementSerializer,
        "TestCase": rest_serializers.TestCaseSerializer,
        "Adr": rest_serializers.AdrSerializer,
        "Risk": rest_serializers.RiskSerializer,
        "Issue": rest_serializers.IssueSerializer,
        "Goal": rest_serializers.GoalSerializer,
        "GlossaryTerm": rest_serializers.GlossaryTermSerializer,
        "ChangeRequest": rest_serializers.ChangeRequestSerializer,
    }.get(item_type)


@pytest.mark.django_db
def test_no_introspected_attribute_is_both_editable_and_not_writable() -> None:
    """Every editable=True, kind="core" attribute must correspond to a real,
    non-read_only field on the item type's serializer — otherwise the
    definition-driven ArtifactForm renders a control whose PATCH the
    serializer either rejects outright (unknown-field 400, C-1's failure
    mode) or silently drops (read_only field)."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        serializer_cls = _serializer_for_item_type(item_type)
        if serializer_cls is None:
            continue
        fields = serializer_cls().fields
        for preset in PRESETS:
            for attribute in introspect_core_attributes(item_type, preset):
                if (
                    attribute["kind"] != "core"
                    or attribute["type"] == "widget"
                    or attribute["editable"] is not True
                ):
                    continue
                name = attribute["name"]
                assert name in fields, (
                    f"{item_type}/{preset}: '{name}' is introspected as an "
                    f"editable core attribute but {serializer_cls.__name__} "
                    "declares no such field."
                )
                assert fields[name].read_only is False, (
                    f"{item_type}/{preset}: '{name}' is introspected as "
                    f"editable but {serializer_cls.__name__}.{name} is "
                    "read_only."
                )


@pytest.mark.django_db
def test_testcase_provenance_controls_are_not_exposed_as_editable() -> None:
    """#424/#402 review finding M-A: the bootstrap must not render edit
    controls for controls its own serializer/form owns.

    Two distinct mechanisms, asserted separately and for **every** preset:

    * ``origin`` stays in the definition (complete, still validated) but is
      ``editable=False``. It is write-once after creation, so an editable
      control would silently discard/crash every save; the definition layer
      rejects *updates* carrying a non-editable attribute while the create
      path stays intact.
    * ``scenario_kind`` is owned by the ``TestCaseArtifactForm`` adapter, which
      renders its own select, so it must not be introspected a second time.

    This assertion goes red if ``origin`` is dropped from
    ``READ_ONLY_MODEL_FIELDS`` (it would be introspected ``editable=True``) or
    if ``scenario_kind`` is re-added to the introspection for ``TestCase``.
    """
    for preset in PRESETS:
        by_name = {
            attribute["name"]: attribute
            for attribute in introspect_core_attributes("TestCase", preset)
        }

        assert "origin" in by_name, (
            f"TestCase/{preset}: 'origin' must stay declared in the definition"
        )
        assert by_name["origin"]["editable"] is False, (
            f"TestCase/{preset}: 'origin' is write-once after creation but is "
            "introspected as an editable control (editable="
            f"{by_name['origin']['editable']!r}); it must be listed in "
            "READ_ONLY_MODEL_FIELDS."
        )

        scenario_kind = by_name.get("scenario_kind")
        assert scenario_kind is None or scenario_kind["editable"] is not True, (
            f"TestCase/{preset}: 'scenario_kind' is owned by the "
            "TestCaseArtifactForm adapter and must not be introspected as an "
            "editable control."
        )


# --- #1112: --reconcile-field-kinds migrates field kinds / retired entries ---


def _attrs_by_name(row: GlobalAttributeDefinition) -> dict[str, dict]:
    return {a["name"]: a for a in row.definition_json["attributes"]}


def _legacy_stakeholder(row: GlobalAttributeDefinition) -> None:
    """Rewrite ``stakeholder`` to its pre-ADR-006 free-text shape.

    ADR-006 (#1111) turned ``StakeholderNeed.stakeholder`` from a flat
    free-text field into a catalogue-backed ``multi-enum``. An instance
    bootstrapped before that cut keeps the old shape forever because the
    additive bootstrap diff is name-based only (#1112).
    """
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        if attribute["name"] == "stakeholder":
            attribute["kind"] = "extended"
            attribute["type"] = "text"
            attribute["options"] = []
            attribute["multiple"] = False
            attribute["allow_external"] = False
            # An admin presentation customization that must survive.
            attribute["label"] = {"de": "Eigenes Label", "en": "Custom label"}
            attribute["order"] = 321
    row.definition_json = payload
    row.save(update_fields=["definition_json"])


def _add_legacy_origin_link(row: GlobalAttributeDefinition) -> None:
    """Append the pre-ADR-006 ``origin_link`` phantom to a row.

    It was a matrix ``_new(...)`` entry (``kind="extended"``) with zero writers,
    removed in ADR-006 (#1111); a pre-cut instance still carries it.
    """
    payload = copy.deepcopy(row.definition_json)
    payload["attributes"].append(
        {
            "name": "origin_link",
            "kind": "extended",
            "type": "text",
            "section": "traceability",
            "order": 120,
            "label": {"de": "Quellverweis", "en": "Origin link"},
        }
    )
    row.definition_json = payload
    row.save(update_fields=["definition_json"])


@pytest.mark.django_db
def test_reconcile_field_kinds_migrates_a_stale_type_and_keeps_admin_meta(
    tenant,
) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
    )
    _legacy_stakeholder(row)

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )

    row.refresh_from_db()
    stakeholder = _attrs_by_name(row)["stakeholder"]
    fresh = {
        a["name"]: a
        for a in introspect_core_attributes("StakeholderNeed", "standard")
    }["stakeholder"]
    assert stakeholder["kind"] == "core"
    assert stakeholder["type"] == "multi-enum"
    assert stakeholder["options"] == fresh["options"]
    assert stakeholder["options"], "a multi-enum must carry catalogue options"
    # Admin-owned presentation metadata is untouched by the reconcile.
    assert stakeholder["label"] == {"de": "Eigenes Label", "en": "Custom label"}
    assert stakeholder["order"] == 321


@pytest.mark.django_db
def test_reconcile_field_kinds_migrates_an_actor_reference(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Adr", preset="standard"
    )
    payload = copy.deepcopy(row.definition_json)
    for attribute in payload["attributes"]:
        if attribute["name"] == "deciders":
            attribute["kind"] = "extended"
            attribute["type"] = "text"
            attribute["multiple"] = False
            attribute["allow_external"] = False
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )

    row.refresh_from_db()
    deciders = _attrs_by_name(row)["deciders"]
    assert deciders["kind"] == "core"
    assert deciders["type"] == "actor"
    assert deciders["multiple"] is True


@pytest.mark.django_db
def test_reconcile_keeps_and_previews_a_retired_attribute_without_the_opt_in(
    tenant,
) -> None:
    """F-1112-1: a name absent from the catalogue is previewed, never deleted.

    An attribute the current introspection does not produce may be a retired
    catalogue entry (the ``origin_link`` phantom) OR an admin-added global
    attribute — the stored blob cannot tell them apart. The default reconcile
    therefore keeps it and only prints the blast radius.
    """
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Requirement", preset="standard"
    )
    _add_legacy_origin_link(row)

    out = StringIO()
    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
        stdout=out,
    )

    row.refresh_from_db()
    assert "origin_link" in _attrs_by_name(row), "deleted without the opt-in"
    preview = out.getvalue()
    assert "origin_link" in preview, "the blast radius must be previewed"
    assert "--allow-attribute-removal" in preview
    assert "Requirement/standard" in preview


@pytest.mark.django_db
def test_reconcile_removes_a_retired_attribute_only_with_the_opt_in(
    tenant,
) -> None:
    """F-1112-1: with the explicit opt-in the removal is previewed and applied."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Requirement", preset="standard"
    )
    _add_legacy_origin_link(row)

    out = StringIO()
    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
        allow_attribute_removal=True,
        stdout=out,
    )

    row.refresh_from_db()
    by_name = _attrs_by_name(row)
    assert "origin_link" not in by_name
    assert "title" in by_name, "the catalogue-owned attribute set must survive"
    preview = out.getvalue()
    assert "origin_link" in preview, "removal must be previewed before it happens"
    assert "removing attribute" in preview


@pytest.mark.django_db
def test_reconcile_spares_an_admin_added_global_attribute_by_default(
    tenant,
) -> None:
    """F-1112-1: admin-added GLOBAL extended attributes survive by default.

    ``attribute_definition_service.create_global`` appends a ``kind="extended"``
    name that no model/matrix walk produces, exactly like a retired catalogue
    entry. The reconcile must not delete it unless the operator asks.
    """
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    payload = copy.deepcopy(row.definition_json)
    payload["attributes"].append(
        {
            "name": "admin_added_field",
            "kind": "extended",
            "type": "text",
            "section": "general",
            "order": 900,
            "label": {"de": "Admin-Feld", "en": "Admin field"},
        }
    )
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )

    row.refresh_from_db()
    assert "admin_added_field" in _attrs_by_name(row)


@pytest.mark.django_db
def test_allow_attribute_removal_without_reconcile_is_refused(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    with pytest.raises(
        CommandError, match="--allow-attribute-removal requires --reconcile"
    ):
        call_command(
            "bootstrap_attribute_definitions",
            "--tenant",
            str(tenant.id),
            allow_attribute_removal=True,
        )


@pytest.mark.django_db
def test_sync_new_fields_preserves_other_top_level_definition_keys(tenant) -> None:
    """F-1112-4: the write must not discard unrelated top-level keys."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    payload = copy.deepcopy(row.definition_json)
    payload["section_flow"] = [
        {"kind": "section", "name": section["name"]}
        for section in payload["sections"]
    ]
    payload["attributes"] = [
        a for a in payload["attributes"] if a["name"] != "detection"
    ]
    row.definition_json = payload
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        sync_new_fields=True,
    )

    row.refresh_from_db()
    assert row.definition_json["section_flow"] == payload["section_flow"]
    assert "detection" in _attrs_by_name(row)


@pytest.mark.django_db
def test_reconcile_field_kinds_is_idempotent(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    _legacy_stakeholder(
        GlobalAttributeDefinition.unscoped.get(
            tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
        )
    )

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
    )
    version = row.version
    payload = copy.deepcopy(row.definition_json)

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )
    row.refresh_from_db()
    assert row.version == version, "an idempotent re-run bumped version"
    assert row.definition_json == payload


@pytest.mark.django_db
def test_reconcile_field_kinds_propagates_but_spares_customized_workspaces(
    tenant,
) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    global_row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
    )
    _legacy_stakeholder(global_row)

    ws_store = WorkspaceAttributeDefinitionStore()
    mirrored_id = uuid.uuid4()
    mirrored = ws_store.resolve(
        tenant.id, mirrored_id, "StakeholderNeed", "standard"
    )
    assert mirrored.is_customized is False

    customized_id = uuid.uuid4()
    customized = ws_store.resolve(
        tenant.id, customized_id, "StakeholderNeed", "standard"
    )
    custom_payload = copy.deepcopy(customized.definition_json)
    for attribute in custom_payload["attributes"]:
        if attribute["name"] == "stakeholder":
            attribute["type"] = "text"
            attribute["label"] = {"de": "Lokal", "en": "Local"}
    customized.definition_json = custom_payload
    customized.is_customized = True
    customized.save(update_fields=["definition_json", "is_customized"])

    call_command(
        "bootstrap_attribute_definitions",
        "--tenant",
        str(tenant.id),
        reconcile_field_kinds=True,
    )

    mirrored.refresh_from_db()
    assert _attrs_by_name(mirrored)["stakeholder"]["type"] == "multi-enum"

    customized.refresh_from_db()
    local = _attrs_by_name(customized)["stakeholder"]
    assert customized.is_customized is True
    assert local["type"] == "text", "a customized workspace row was rewritten"
    assert local["label"] == {"de": "Lokal", "en": "Local"}


@pytest.mark.django_db
def test_without_the_flag_a_stale_field_kind_is_left_alone(tenant) -> None:
    """The mode is opt-in: the default path must not retype anything."""
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
    )
    _legacy_stakeholder(row)
    before = copy.deepcopy(row.definition_json)

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))

    row.refresh_from_db()
    assert row.definition_json == before
    assert _attrs_by_name(row)["stakeholder"]["type"] == "text"


@pytest.mark.django_db
def test_reconcile_field_kinds_with_reset_is_refused(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    with pytest.raises(
        CommandError, match="--reconcile-field-kinds cannot be combined"
    ):
        call_command(
            "bootstrap_attribute_definitions",
            "--tenant",
            str(tenant.id),
            reconcile_field_kinds=True,
            reset=True,
        )


def test_field_kind_keys_cover_the_structural_identity_only() -> None:
    """A structural guard so widening the write set cannot happen unnoticed."""
    from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
        FIELD_KIND_KEYS,
        FIELD_KIND_TYPE_PAYLOAD_KEYS,
    )
    from attribute_definitions.schema import CORE_EDITABLE_META_PROPERTIES

    assert FIELD_KIND_KEYS == (
        "kind",
        "type",
        "multiple",
        "allow_external",
        "widget_key",
        "fields",
    )
    assert set(FIELD_KIND_KEYS).isdisjoint(CORE_EDITABLE_META_PROPERTIES)
    # ``options`` is admin-editable on a core enum, so it is only copied when
    # the kind/type changes (see FIELD_KIND_TYPE_PAYLOAD_KEYS).
    assert "options" in FIELD_KIND_TYPE_PAYLOAD_KEYS
    assert "options" in CORE_EDITABLE_META_PROPERTIES

