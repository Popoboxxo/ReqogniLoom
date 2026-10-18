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
import sys
import unittest
from unittest import mock
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent


def _load(module_name: str, file_path: Path):
    """Load a module copy and register it in ``sys.modules``.

    Registering is what makes the conftest fixture able to clear this copy's
    catalogue cache and token store; without the entry it is invisible to the
    isolation fixture, and state leaks into the following test.
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
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
            "attribute_migration.dry_run",
            "context.related",
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_COMPUTE)
                self.assertEqual(tools.risk_class(name), tools.RISK_NONE)

    def test_persisting_tools_are_mutate_even_without_a_write_verb(self) -> None:
        # The regression this pins: these tools persist something (a suggestion, a
        # derivation, a memory fact) but their name contains no write verb, so a
        # name-only heuristic classified them "compute" — no confirmation dialog
        # and no write gate.
        for name in (
            "traceability.suggest_links",
            "requirement.decompose",
            "requirement.suggest_level",
            "ai_derivation.derive_requirements_from_need",
            "ai_derivation.decompose_requirement_next_level",
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.classify(name), tools.CLASS_MUTATE)
                self.assertEqual(tools.risk_class(name), tools.RISK_NORMAL)

    def test_compute_class_never_contains_a_write_of_the_manifest(self) -> None:
        # COMPUTE_EXACT is the one place a misclassification would hide, so every
        # entry has to carry a stated reason and that map must match the set —
        # a new member cannot slip in without a justification a reviewer can check
        # against the tool's own description.
        self.assertEqual(
            sorted(tools.COMPUTE_JUSTIFICATIONS),
            sorted(tools.COMPUTE_EXACT),
            "every compute-class tool needs a one-line justification",
        )
        for name, reason in tools.COMPUTE_JUSTIFICATIONS.items():
            with self.subTest(name=name):
                self.assertTrue(reason.strip(), "the justification must not be empty")
                self.assertNotIn("persist", reason.lower().replace("no persistence", "").replace("persists no", ""))

    def test_compute_and_mutate_tables_are_disjoint(self) -> None:
        overlap = sorted(set(tools.COMPUTE_EXACT) & set(tools.MUTATE_EXACT))
        self.assertEqual(overlap, [], f"a tool may not be in both tables: {overlap}")

    def test_server_annotations_win_over_the_name_heuristic(self) -> None:
        # If the backend ever publishes the MCP standard hints, they are
        # authoritative — otherwise the plugin would keep overriding a fact it can
        # be told, which is how a heuristic goes stale silently.
        read_only = {"name": "requirement.frobnicate", "annotations": {"readOnlyHint": True}}
        destructive = {"name": "requirement.get", "annotations": {"destructiveHint": True}}
        self.assertEqual(tools.classify_tool(read_only), tools.CLASS_READ)
        self.assertEqual(tools.classify_tool(destructive), tools.CLASS_MUTATE)
        self.assertEqual(tools.classify_tool({"name": "requirement.get"}), tools.CLASS_READ)

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

    def test_boolean_is_not_an_integer(self) -> None:
        # bool is an int subclass in Python, so `True` would slip through a naive
        # isinstance check and reach the server as a wrong type.
        problems = tools.validate_arguments(
            {"type": "object", "properties": {"count": {"type": "integer"}}}, {"count": True}
        )
        self.assertEqual(problems, ["parameter 'count' expects an integer"])

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


class ConfirmTokenLifecycleTests(unittest.TestCase):
    """Issued → consumed once → refused afterwards."""

    def setUp(self) -> None:
        tools.reset_issued_tokens()

    def tearDown(self) -> None:
        tools.reset_issued_tokens()

    def test_issued_token_can_be_consumed_once(self) -> None:
        token = tools.issue_confirm_token("qs", "requirement.create", {"title": "A"})
        ok, reason = tools.consume_confirm_token("qs", "requirement.create", {"title": "A"}, token)
        self.assertTrue(ok, reason)
        again, reason = tools.consume_confirm_token("qs", "requirement.create", {"title": "A"}, token)
        self.assertFalse(again, "a token must not be usable twice")
        self.assertIn("already used", reason)

    def test_unissued_token_is_refused(self) -> None:
        # Skipping the preview means the token was never issued: the digest alone
        # is computable, so verification cannot be a pure hash comparison.
        token = tools.confirm_token("qs", "requirement.create", {"title": "A"})
        ok, reason = tools.consume_confirm_token("qs", "requirement.create", {"title": "A"}, token)
        self.assertFalse(ok)
        self.assertIn("already used", reason)

    def test_token_bound_to_other_arguments_is_refused(self) -> None:
        token = tools.issue_confirm_token("qs", "requirement.create", {"title": "A"})
        ok, reason = tools.consume_confirm_token("qs", "requirement.create", {"title": "B"}, token)
        self.assertFalse(ok)
        self.assertIn("mismatch", reason)

    def test_expired_token_is_refused(self) -> None:
        token = tools.issue_confirm_token("qs", "requirement.create", {})
        with mock.patch.object(
            tools.time, "monotonic", return_value=tools.time.monotonic() + tools.CONFIRM_TOKEN_TTL_SECONDS + 1
        ):
            ok, reason = tools.consume_confirm_token("qs", "requirement.create", {}, token)
        self.assertFalse(ok)
        self.assertIn("expired", reason)


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

    def test_cache_tolerates_another_instance_of_the_same_client(self) -> None:
        class Keyed:
            server_id = "qs"
            base_url = "http://qs.test:8001"

            def __init__(self) -> None:
                self.calls = 0

            def tools_list(self):
                self.calls += 1
                return CatalogueTests.RAW

        first = Keyed()
        second = Keyed()
        tools.fetch_catalogue(first)
        tools.fetch_catalogue(second)
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 0, "the cache key is the server, not the client object")

    def test_ttl_expiry_refetches(self) -> None:
        client = self.FakeClient()
        with mock.patch.object(tools.time, "monotonic", return_value=1000.0):
            tools.fetch_catalogue(client, server_key="qs")
        with mock.patch.object(
            tools.time, "monotonic", return_value=1000.0 + tools.CATALOGUE_TTL_SECONDS + 1
        ):
            refreshed = tools.fetch_catalogue(client, server_key="qs")
        self.assertFalse(refreshed["cached"])
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

class ManifestWriteInvariantTests(unittest.TestCase):
    """Every tool the server itself calls a write must be gated by this plugin.

    The previous guard only forbade ``read``. ``compute`` drops the confirmation
    dialog just as effectively (``/write`` gates ``mutate`` only), so a persisting
    tool could hide in the compute table unnoticed — which is exactly what
    happened to nine tools. The rule is now: a manifest write is either ``mutate``
    or it is on COMPUTE_EXACT *with* a justification a reviewer can check.
    """

    @classmethod
    def setUpClass(cls) -> None:
        manifest_path = _REPO_ROOT / "docs" / "agent-templates" / "tool-manifest.json"
        if not manifest_path.exists():
            raise unittest.SkipTest("tool manifest not available")
        cls.tools_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["tools"]

    def test_no_manifest_write_is_read(self) -> None:
        offenders = [
            tool["name"]
            for tool in self.tools_manifest
            if tool.get("is_write") and tools.classify(tool["name"]) == tools.CLASS_READ
        ]
        self.assertEqual(offenders, [], f"these writes would run without a gate: {offenders}")

    def test_a_manifest_write_is_mutate_or_explicitly_justified(self) -> None:
        unjustified = [
            tool["name"]
            for tool in self.tools_manifest
            if tool.get("is_write")
            and tools.classify(tool["name"]) == tools.CLASS_COMPUTE
            and tool["name"] not in tools.COMPUTE_JUSTIFICATIONS
        ]
        self.assertEqual(
            unjustified,
            [],
            "these tools are writes for the server and compute for this plugin "
            f"without a stated reason: {unjustified}",
        )

    def test_no_manifest_read_is_classified_write(self) -> None:
        offenders = [
            tool["name"]
            for tool in self.tools_manifest
            if not tool.get("is_write") and tools.classify(tool["name"]) != tools.CLASS_READ
        ]
        self.assertEqual(offenders, [], f"these reads would demand a confirmation: {offenders}")


class AnnotationPrecedenceTests(unittest.TestCase):
    """Annotations may add a mutation signal, never remove an explicit one."""

    def test_a_read_only_hint_cannot_downgrade_a_hand_verified_mutation(self) -> None:
        # A server publishing readOnlyHint for a persisting tool must not talk it
        # out of its confirmation dialog.
        entry = {"name": "traceability.suggest_links", "annotations": {"readOnlyHint": True}}
        self.assertEqual(tools.classify_tool(entry), tools.CLASS_MUTATE)

    def test_a_destructive_hint_upgrades_an_unknown_tool(self) -> None:
        entry = {"name": "requirement.frobnicate", "annotations": {"destructiveHint": True}}
        self.assertEqual(tools.classify_tool(entry), tools.CLASS_MUTATE)

    def test_a_read_only_hint_applies_to_unknown_tools(self) -> None:
        entry = {"name": "requirement.frobnicate", "annotations": {"readOnlyHint": True}}
        self.assertEqual(tools.classify_tool(entry), tools.CLASS_READ)

    def test_hints_are_ignored_when_absent_or_malformed(self) -> None:
        self.assertEqual(tools.classify_tool({"name": "requirement.get"}), tools.CLASS_READ)
        self.assertEqual(tools.classify_tool({"name": "requirement.get", "annotations": "yes"}), tools.CLASS_READ)


class DestructiveDetectionTests(unittest.TestCase):
    def test_workspace_wipes_are_destructive(self) -> None:
        # A GDPR wipe of every memory tier of a workspace is the most destructive
        # call in the catalogue; a `.delete`-suffix test missed both of these and
        # left them with a plain yes/no confirmation.
        for name in (
            "memory.delete_workspace",
            "attribute_definition.delete_workspace",
            "workspace.delete",
            "user.purge",
        ):
            with self.subTest(name=name):
                self.assertTrue(tools.is_destructive(name))
                self.assertEqual(tools.classify(name), tools.CLASS_MUTATE)

    def test_ordinary_mutations_are_not_destructive(self) -> None:
        for name in ("requirement.create", "memory.write", "traceability.create_link"):
            with self.subTest(name=name):
                self.assertFalse(tools.is_destructive(name))

    def test_approval_transitions_need_the_human_key(self) -> None:
        self.assertTrue(tools.requires_human("review.approve"))
        self.assertTrue(tools.requires_human("goal.transition"))
        self.assertFalse(tools.requires_human("requirement.create"))
