"""AWMS plan schema — validation, conditions, hashing (WS7 #940, spec §3–§4)."""
from __future__ import annotations

import json

import pytest

from attribute_definitions.migration_plan import (
    MigrationPlanError,
    evaluate_condition,
    load_plan_document,
    normalize_plan,
    parse_verify_assertion,
    plan_hash,
)


def _plan(**overrides):
    base = {
        "id": "2026-09-test",
        "scope": {"item_type": "Requirement", "preset": ["standard"]},
        "steps": [
            {
                "op": "migrate_value",
                "from": {"source": "custom_field", "name": "old"},
                "to": {"target": "custom_field", "name": "new"},
            }
        ],
    }
    base.update(overrides)
    return base


class TestDefaults:
    def test_minimal_plan_gets_documented_defaults(self) -> None:
        plan = normalize_plan(_plan())
        assert plan["version"] == 1
        assert plan["mode"] == "dry_run"
        assert plan["options"] == {
            "idempotent": True,
            "abort_on_error": True,
            "audit": True,
        }
        assert plan["scope"]["workspace"] == "*"
        step = plan["steps"][0]
        assert step["mode"] == "copy"
        assert step["transform"] is None


class TestOptions:
    """WS6/WS7 review (#939/#940) Medium/Low 4: no inert options contract."""

    def test_idempotent_false_is_rejected_as_unsupported(self) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(options={"idempotent": False}))
        message = "; ".join(exc.value.errors)
        assert "idempotent" in message
        assert "true" in message

    def test_audit_false_is_accepted_and_normalized(self) -> None:
        plan = normalize_plan(_plan(options={"audit": False}))
        assert plan["options"]["audit"] is False
        assert plan["options"]["idempotent"] is True
        assert plan["options"]["abort_on_error"] is True


    def test_scope_preset_string_is_normalized_to_a_list(self) -> None:
        plan = normalize_plan(_plan(scope={"item_type": "Risk", "preset": "extended"}))
        assert plan["scope"]["preset"] == ["extended"]

    def test_unknown_plan_key_is_a_validation_error(self) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(surprise=True))
        assert "unknown key" in "; ".join(exc.value.errors)

    def test_unknown_item_type_is_rejected(self) -> None:
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(scope={"item_type": "Nope"}))

    def test_invalid_mode_is_rejected(self) -> None:
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(mode="sideways"))

    def test_empty_steps_is_rejected(self) -> None:
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(steps=[]))


class TestOperations:
    @pytest.mark.parametrize(
        "op",
        ["derive_entity", "rollback"],
    )
    def test_unsupported_ops_name_the_reason(self, op) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[{"op": op, "name": "x", "confirm": "x"}]))
        message = "; ".join(exc.value.errors)
        assert op in message

    def test_unknown_op_is_rejected(self) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[{"op": "launch_missiles"}]))
        assert "unknown op" in "; ".join(exc.value.errors)

    def test_unknown_step_key_is_rejected(self) -> None:
        step = {"op": "map_value", "target": {"target": "custom_field", "name": "p"}, "value_map": {"a": "b"}, "extra": 1}
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[step]))
        assert "unknown key" in "; ".join(exc.value.errors)

    def test_missing_required_key_is_rejected(self) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[{"op": "migrate_value", "from": {"source": "custom_field", "name": "a"}}]))
        assert "missing required" in "; ".join(exc.value.errors)

    def test_bad_reference_kind_is_rejected(self) -> None:
        step = {"op": "migrate_value", "from": {"source": "sql", "name": "a"}, "to": {"target": "custom_field", "name": "b"}}
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(steps=[step]))

    def test_define_attribute_defaults_kind_and_type(self) -> None:
        step = {"op": "define_attribute", "name": "rationale", "section": "attribution", "required_on": ["standard"]}
        plan = normalize_plan(_plan(steps=[step]))
        attribute = plan["steps"][0]["attribute"]
        assert attribute["kind"] == "extended"
        assert attribute["type"] == "text"
        assert attribute["section"] == "attribution"

    def test_drop_requires_confirm_to_repeat_the_name(self) -> None:
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[{"op": "drop_attribute", "name": "old", "confirm": "nope"}]))
        assert "confirm" in "; ".join(exc.value.errors)

    def test_split_and_merge_normalize(self) -> None:
        plan = normalize_plan(
            _plan(
                steps=[
                    {
                        "op": "split_attribute",
                        "from": {"source": "custom_field", "name": "combo"},
                        "targets": [{"to": {"target": "custom_field", "name": "a"}, "transform": "trim"}],
                        "separator": ",",
                    },
                    {
                        "op": "merge_attribute",
                        "sources": [{"source": "custom_field", "name": "a"}],
                        "to": {"target": "custom_field", "name": "b"},
                    },
                ]
            )
        )
        assert plan["steps"][0]["targets"][0]["transform"]["name"] == "trim"
        assert plan["steps"][1]["sources"][0]["name"] == "a"

    def test_unknown_transform_is_rejected(self) -> None:
        step = {
            "op": "migrate_value",
            "from": {"source": "custom_field", "name": "a"},
            "to": {"target": "custom_field", "name": "b"},
            "transform": "does_not_exist",
        }
        with pytest.raises(MigrationPlanError) as exc:
            normalize_plan(_plan(steps=[step]))
        assert "unknown transform" in "; ".join(exc.value.errors)

    def test_backfill_requires_a_known_strategy(self) -> None:
        step = {"op": "backfill_value", "target": {"target": "custom_field", "name": "p"}, "value_strategy": "wish"}
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(steps=[step]))


class TestConditions:
    def test_unknown_atom_is_rejected(self) -> None:
        step = {
            "op": "migrate_value",
            "from": {"source": "custom_field", "name": "a"},
            "to": {"target": "custom_field", "name": "b"},
            "only_if": "the_stars_align",
        }
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(steps=[step]))

    @pytest.mark.parametrize(
        ("expression", "facts", "expected"),
        [
            ("always", {}, True),
            ("source_has_text", {"source_has_text": True}, True),
            ("source_has_text", {"source_has_text": False}, False),
            ("source_has_text and to_is_empty", {"source_has_text": True, "to_is_empty": True}, True),
            ("source_has_text and to_is_empty", {"source_has_text": True, "to_is_empty": False}, False),
            ("not to_is_empty", {"to_is_empty": False}, True),
            ("to_is_empty or source_has_text", {"to_is_empty": False, "source_has_text": True}, True),
        ],
    )
    def test_evaluate_condition(self, expression, facts, expected) -> None:
        assert evaluate_condition(expression, facts) is expected

    def test_unknown_atom_fails_closed_at_runtime(self) -> None:
        assert evaluate_condition("mystery_atom", {}) is False


class TestVerify:
    def test_verify_assertion_parses(self) -> None:
        assert parse_verify_assertion("changed <= 5") == ("changed", "<=", 5)

    def test_verify_rejects_unknown_metric(self) -> None:
        step = {"op": "verify", "assertions": ["rows_dropped == 0"]}
        with pytest.raises(MigrationPlanError):
            normalize_plan(_plan(steps=[step]))

    def test_verify_accepts_known_metric(self) -> None:
        plan = normalize_plan(_plan(steps=[{"op": "verify", "assertions": ["failed == 0"]}]))
        assert plan["steps"][0]["assertions"] == ["failed == 0"]


class TestHash:
    def test_hash_is_stable_and_key_order_independent(self) -> None:
        plan_a = normalize_plan(_plan(description="a"))
        plan_b = normalize_plan(_plan(description="a"))
        assert plan_hash(plan_a) == plan_hash(plan_b)
        assert len(plan_hash(plan_a)) == 64

    def test_hash_changes_with_content(self) -> None:
        assert plan_hash(normalize_plan(_plan(description="a"))) != plan_hash(
            normalize_plan(_plan(description="b"))
        )


class TestDocumentLoading:
    def test_json_document(self) -> None:
        parsed = load_plan_document(json.dumps(_plan()), filename="plan.json")
        assert parsed["id"] == "2026-09-test"

    def test_json_document_without_filename(self) -> None:
        assert load_plan_document(json.dumps(_plan()))["id"] == "2026-09-test"

    def test_yaml_document(self) -> None:
        pytest.importorskip("yaml")
        text = "id: 2026-09-test\nscope:\n  item_type: Requirement\nsteps:\n  - op: map_value\n"
        parsed = load_plan_document(text, filename="plan.yaml")
        assert parsed["id"] == "2026-09-test"

    def test_invalid_json_is_a_plan_error(self) -> None:
        with pytest.raises(MigrationPlanError):
            load_plan_document("{not json", filename="plan.json")
