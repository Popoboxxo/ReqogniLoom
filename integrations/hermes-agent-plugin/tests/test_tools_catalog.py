"""Tests for the tool catalogue and its risk classification.

Run: python -m pytest tests/test_tools_catalog.py -q

The interesting part is :class:`ClassificationGuardTests`: the plugin derives
write/read from the tool *name* (MCP does not put an ``is_write`` flag on the
wire), so the derivation is pinned against the repo's generated
``docs/agent-templates/tool-manifest.json`` — the server's own write/read split
for the same 248 tools. Two invariants, both directions:

* every tool the server marks as a write is classified ``mutate`` or ``compute``
  (never ``read`` — that would drop a confirmation dialog);
* every tool the server marks as a read is classified ``read``
  (never ``mutate`` — that would add a bogus one).

A drift on either side fails here instead of surfacing as a missing dialog in
production.
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tools = _load("reqogniloom_tools_under_test", _PLUGIN_ROOT / "reqogniloom_tools.py")


class ClassificationTests(unittest.TestCase):
    def test_state_changing_tools_are_mutate(self) -> None:
        for name in (
            "requirement.create",
            "requirement.update",
            "adr.delete",
            "traceability.create_link",
            "interview.formalize",
            "workflow.transition",
            "goal.transition",
            "memory.write",
            "baseline.create",
            "workspace.close",
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_MUTATE)

    def test_llm_and_admin_reads_are_compute(self) -> None:
        for name in (
            "requirement.validate",
            "traceability.coverage",
            "memory.ask",
            "ai_derivation.derive_glossary_from_workspace",
            "attribute_migration.dry_run",
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_COMPUTE)
                self.assertEqual(tools.risk_class(name), tools.RISK_NONE)

    def test_plain_reads_are_read(self) -> None:
        for name in (
            "requirement.get",
            "requirement.query",
            "workspace.list",
            "review.list_pending",
            "requirement_bundle.export",
            "attribute_migration.plan",
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_READ)

    def test_unknown_tool_is_read_and_needs_no_confirmation(self) -> None:
        # Forward compatibility: a tool this build has never seen must not be
        # guessed into a destructive class, but must still be callable.
        self.assertEqual(tools.classify("brand_new.poke"), tools.CLASS_READ)
        self.assertEqual(tools.risk_class("brand_new.poke"), tools.RISK_NONE)

    def test_delete_suffix_is_always_destructive(self) -> None:
        self.assertTrue(tools.is_destructive("whatever.delete"))
        self.assertEqual(tools.risk_class("whatever.delete"), tools.RISK_DESTRUCTIVE)

    def test_named_destructive_tools_are_mutate_and_destructive(self) -> None:
        for name in sorted(tools.DESTRUCTIVE_TOOLS):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_MUTATE)
                self.assertEqual(tools.risk_class(name), tools.RISK_DESTRUCTIVE)

    def test_normal_writes_are_not_destructive(self) -> None:
        self.assertEqual(tools.risk_class("requirement.create"), tools.RISK_NORMAL)
        self.assertFalse(tools.is_destructive("requirement.create"))

    def test_human_tools_are_write_and_marked(self) -> None:
        for name in sorted(tools.HUMAN_TOOLS):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_MUTATE)
                self.assertTrue(tools.requires_human(name))
        self.assertFalse(tools.requires_human("requirement.create"))

    def test_group_and_verb_split(self) -> None:
        self.assertEqual(tools.group_of("requirement.acceptance_criteria.set"), "requirement")
        self.assertEqual(tools.verb_of("requirement.acceptance_criteria.set"), "acceptance_criteria.set")
        self.assertEqual(tools.group_of("nodot"), "other")


class ClassificationGuardTests(unittest.TestCase):
    """The plugin's derivation vs. the server's own write/read split."""

    @classmethod
    def setUpClass(cls) -> None:
        manifest_path = _REPO_ROOT / "docs" / "agent-templates" / "tool-manifest.json"
        if not manifest_path.exists():
            raise unittest.SkipTest(f"tool manifest not available at {manifest_path}")
        cls.manifest_tools = json.loads(manifest_path.read_text(encoding="utf-8"))["tools"]

    def test_no_server_write_is_classified_read(self) -> None:
        offenders = [
            tool["name"]
            for tool in self.manifest_tools
            if tool.get("is_write") and tools.classify(tool["name"]) == tools.CLASS_READ
        ]
        self.assertEqual(offenders, [], f"these writes would lose their confirmation: {offenders}")

    def test_no_server_read_is_classified_write(self) -> None:
        offenders = [
            tool["name"]
            for tool in self.manifest_tools
            if not tool.get("is_write") and tools.classify(tool["name"]) != tools.CLASS_READ
        ]
        self.assertEqual(offenders, [], f"these reads would demand a confirmation: {offenders}")

    def test_every_manifest_tool_is_classified(self) -> None:
        classes = {tools.classify(tool["name"]) for tool in self.manifest_tools}
        self.assertEqual(classes, {tools.CLASS_READ, tools.CLASS_COMPUTE, tools.CLASS_MUTATE})

    def test_manifest_size_is_reported(self) -> None:
        # Not a hard assertion on 248 — the server may grow. It pins that the
        # guard actually ran against a real manifest rather than an empty file.
        self.assertGreater(len(self.manifest_tools), 200)


class ArgumentTests(unittest.TestCase):
    schema = {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"},
            "title": {"type": "string"},
            "count": {"type": "integer"},
            "dry_run": {"type": "boolean"},
            "items": {"type": "array"},
        },
        "required": ["workspace_id", "title"],
    }

    def test_missing_required_parameter_is_reported(self) -> None:
        problems = tools.validate_arguments(self.schema, {"workspace_id": "ws-1"})
        self.assertEqual(problems, ["missing required parameter 'title'"])

    def test_empty_required_parameter_is_reported(self) -> None:
        problems = tools.validate_arguments(self.schema, {"workspace_id": "ws-1", "title": ""})
        self.assertIn("required parameter 'title' is empty", problems)

    def test_unknown_parameter_is_reported(self) -> None:
        problems = tools.validate_arguments(
            self.schema, {"workspace_id": "ws-1", "title": "t", "workspaceId": "typo"}
        )
        self.assertEqual(problems, ["unknown parameter 'workspaceId'"])

    def test_type_mismatch_is_reported(self) -> None:
        problems = tools.validate_arguments(
            self.schema, {"workspace_id": "ws-1", "title": "t", "count": "3", "dry_run": "yes"}
        )
        self.assertIn("parameter 'count' expects an integer", problems)
        self.assertIn("parameter 'dry_run' expects true/false", problems)

    def test_valid_arguments_produce_no_problems(self) -> None:
        self.assertEqual(
            tools.validate_arguments(
                self.schema,
                {"workspace_id": "ws-1", "title": "t", "count": 3, "dry_run": True, "items": []},
            ),
            [],
        )

    def test_schema_helpers_tolerate_missing_schema(self) -> None:
        self.assertEqual(tools.declared_parameter_names(None), [])
        self.assertEqual(tools.required_parameters(None), [])
        self.assertEqual(tools.validate_arguments(None, {"anything": 1}), ["unknown parameter 'anything'"])

    def test_summary_skips_empty_values_and_is_bounded(self) -> None:
        summary = tools.summarise_arguments(
            {"workspace_id": "ws-1", "title": "", "note": None, "big": "x" * 200}
        )
        self.assertIn("workspace_id=ws-1", summary)
        self.assertNotIn("title", summary)
        self.assertLessEqual(len(summary), 120)

    def test_summary_limits_the_number_of_pairs(self) -> None:
        summary = tools.summarise_arguments({"a": "1", "b": "2", "c": "3", "d": "4"}, limit=2)
        self.assertEqual(len(summary.split()), 2)


class ConfirmTokenTests(unittest.TestCase):
    def test_token_is_stable_across_key_order(self) -> None:
        first = tools.confirm_token("qs", "requirement.create", {"a": 1, "b": 2})
        second = tools.confirm_token("qs", "requirement.create", {"b": 2, "a": 1})
        self.assertEqual(first, second)

    def test_token_changes_with_arguments_tool_and_server(self) -> None:
        base = tools.confirm_token("qs", "requirement.create", {"title": "A"})
        self.assertNotEqual(base, tools.confirm_token("qs", "requirement.create", {"title": "B"}))
        self.assertNotEqual(base, tools.confirm_token("qs", "requirement.update", {"title": "A"}))
        self.assertNotEqual(base, tools.confirm_token("prod", "requirement.create", {"title": "A"}))

    def test_token_is_a_hex_digest(self) -> None:
        token = tools.confirm_token("qs", "requirement.create", {})
        self.assertEqual(len(token), 64)
        int(token, 16)  # raises if not hex


class CatalogueTests(unittest.TestCase):
    RAW = [
        {
            "name": "requirement.query",
            "description": "List requirements.",
            "inputSchema": {"type": "object", "properties": {"workspace_id": {"type": "string"}}},
        },
        {
            "name": "requirement.create",
            "description": "Create one.",
            "inputSchema": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
        {"name": "admin.restore", "description": "Restore.", "inputSchema": {"type": "object"}},
    ]

    def test_catalogue_counts_and_groups(self) -> None:
        catalogue = tools.build_catalogue(self.RAW, server_key="qs")
        self.assertEqual(catalogue["tool_count"], 3)
        self.assertEqual(catalogue["group_count"], 2)
        self.assertEqual(catalogue["counts"][tools.CLASS_MUTATE], 2)
        self.assertEqual(catalogue["counts"][tools.CLASS_READ], 1)
        self.assertEqual({g["name"] for g in catalogue["groups"]}, {"requirement", "admin"})

    def test_describe_tool_carries_schema_and_flags(self) -> None:
        described = tools.describe_tool(self.RAW[1])
        self.assertEqual(described["class"], tools.CLASS_MUTATE)
        self.assertEqual(described["risk"], tools.RISK_NORMAL)
        self.assertEqual(described["required"], ["title"])
        self.assertEqual(described["parameters"], ["title"])
        self.assertFalse(described["requires_human"])

    def test_destructive_flag_reaches_the_catalogue(self) -> None:
        described = tools.describe_tool(self.RAW[2])
        self.assertTrue(described["destructive"])
        self.assertEqual(described["risk"], tools.RISK_DESTRUCTIVE)

    def test_entries_are_sorted_by_name(self) -> None:
        catalogue = tools.build_catalogue(self.RAW, server_key="qs")
        names = [entry["name"] for entry in catalogue["tools"]]
        self.assertEqual(names, sorted(names))

    def test_find_tool(self) -> None:
        catalogue = tools.build_catalogue(self.RAW, server_key="qs")
        self.assertIsNotNone(tools.find_tool(catalogue, "requirement.create"))
        self.assertIsNone(tools.find_tool(catalogue, "nope.nope"))


class CatalogueCacheTests(unittest.TestCase):
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def tools_list(self):
            self.calls += 1
            return CatalogueTests.RAW

    def setUp(self) -> None:
        tools.invalidate()

    def tearDown(self) -> None:
        tools.invalidate()

    def test_second_fetch_is_served_from_cache(self) -> None:
        client = self.FakeClient()
        first = tools.fetch_catalogue(client, server_key="qs")
        second = tools.fetch_catalogue(client, server_key="qs")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(client.calls, 1)

    def test_refresh_bypasses_the_cache(self) -> None:
        client = self.FakeClient()
        tools.fetch_catalogue(client, server_key="qs")
        tools.fetch_catalogue(client, server_key="qs", refresh=True)
        self.assertEqual(client.calls, 2)

    def test_invalidate_drops_one_server_only(self) -> None:
        client = self.FakeClient()
        tools.fetch_catalogue(client, server_key="qs")
        tools.fetch_catalogue(client, server_key="prod")
        tools.invalidate("qs")
        tools.fetch_catalogue(client, server_key="qs")
        tools.fetch_catalogue(client, server_key="prod")
        self.assertEqual(client.calls, 3)

    def test_cache_key_falls_back_to_the_client(self) -> None:
        class Keyed:
            server_id = "qs"
            base_url = "http://qs.test:8001"

            def __init__(self) -> None:
                self.calls = 0

            def tools_list(self):
                self.calls += 1
                return CatalogueTests.RAW

        client = Keyed()
        tools.fetch_catalogue(client)
        tools.fetch_catalogue(client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.calls, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
