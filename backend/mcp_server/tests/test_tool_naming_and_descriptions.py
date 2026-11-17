"""R2A-003 (tool naming) and R2A-004 (descriptions) ratchets.

R2A-003: one canonical fetch verb and one canonical list verb per entity
prefix. Legacy verb spellings are kept as *hidden* aliases (metadata only,
``deprecated: true`` + ``replacedBy`` → a real published tool) for one release;
aliases neither add a ``tools/list`` entry nor a route, so the catalogue stays
at 301 and the #1376 no-shadow-tools guard keeps holding.

R2A-004: the generic CRUD factory used to emit ``"Delete a adr entity"`` and
hide the hard-delete vs. soft-delete distinction. Per-prefix descriptions now
carry both; the manifest-length/grammar ratchet lives in
``test_tool_manifest_drift.py``.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import pytest

from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.base import (
    CANONICAL_FETCH_VERB,
    CANONICAL_LIST_VERB,
    FETCH_VERBS,
    LIST_VERBS,
    tool_verb,
    verb_operation,
)
from mcp_server.tools.generic import GenericCrudToolGroup

pytestmark = pytest.mark.django_db


def _all_tools() -> list[dict[str, Any]]:
    """Return the 301 published tool schemas (before any RBAC gating)."""
    return ToolRegistry().all_tool_schemas()


# ---------------------------------------------------------------------------
# R2A-003 — canonical verbs + hidden aliases
# ---------------------------------------------------------------------------


def test_at_most_one_canonical_fetch_and_list_verb_per_prefix() -> None:
    """No prefix publishes two ``get`` tools or two ``list`` tools.

    ``read``/``query`` are the legacy aliases of the same two operations;
    counting only the canonical spellings keeps the gate meaningful while
    grandfathering the existing prefixes' chosen spelling.
    """
    counts: dict[tuple[str, str], list[str]] = defaultdict(list)
    for schema in _all_tools():
        name = schema["name"]
        verb = tool_verb(name)
        if verb == CANONICAL_FETCH_VERB:
            counts[(name.split(".", 1)[0], "fetch")].append(name)
        elif verb == CANONICAL_LIST_VERB:
            counts[(name.split(".", 1)[0], "list")].append(name)

    violations = {key: names for key, names in counts.items() if len(names) > 1}
    assert not violations, (
        f"Prefixes with more than one canonical verb: {violations}. "
        "Keep one get and one list tool per prefix; declare the others as "
        "hidden aliases."
    )


def test_verb_vocabulary_classifies_only_crud_family() -> None:
    """The vocabulary distinguishes nested tools and non-CRUD verbs."""
    assert verb_operation("adr.read") == "fetch"
    assert verb_operation("architecture.get") == "fetch"
    assert verb_operation("issue.query") == "list"
    assert verb_operation("milestone.list") == "list"
    # Nested namespace, not a second fetch verb for the requirement prefix.
    assert verb_operation("requirement.acceptance_criteria.get") is None
    assert verb_operation("memory.query") == "list"
    assert verb_operation("requirement.create") is None


def test_hidden_aliases_are_well_formed_and_invisible() -> None:
    """Every hidden alias is deprecated and points at a real published tool."""
    published = {schema["name"] for schema in _all_tools()}
    assert len(published) == 301

    aliases = ToolRegistry().hidden_tool_aliases()
    assert aliases, "the legacy verb aliases disappeared — republish the metadata"

    bad_targets = {
        alias: meta for alias, meta in aliases.items()
        if meta.get("replacedBy") not in published
    }
    assert not bad_targets, (
        f"Aliases with a replacedBy that is not a real tool: {bad_targets}"
    )
    not_deprecated = sorted(
        alias for alias, meta in aliases.items() if meta.get("deprecated") is not True
    )
    assert not not_deprecated, (
        f"Aliases missing deprecated:true: {not_deprecated}"
    )
    shadowed = sorted(set(aliases) & published)
    assert not shadowed, (
        f"Aliases leaked into the published catalogue: {shadowed}"
    )

    # All four legacy spellings occur across the catalogue.
    alias_verbs = {tool_verb(alias) for alias in aliases}
    assert alias_verbs == FETCH_VERBS | LIST_VERBS, (
        f"Expected aliases for every legacy verb, got {sorted(alias_verbs)}"
    )
    counts = Counter(alias.split(".", 1)[0] for alias in aliases)
    assert "adr" in counts and "architecture" in counts


def test_generic_groups_publish_one_fetch_and_one_list_verb() -> None:
    """The five factory-built groups cover the two verb families explicitly."""
    registry = ToolRegistry()
    registry._ensure_groups()
    for prefix in ("adr", "risk", "issue", "glossary", "change_request"):
        group = registry._groups[prefix]
        assert isinstance(group, GenericCrudToolGroup)
        names = {schema["name"] for schema in group.get_tool_schemas()}
        assert f"{prefix}.read" in names and f"{prefix}.query" in names
        assert f"{prefix}.get" not in names and f"{prefix}.list" not in names
        aliases = ToolRegistry().hidden_tool_aliases()
        assert aliases[f"{prefix}.get"]["replacedBy"] == f"{prefix}.read"
        assert aliases[f"{prefix}.list"]["replacedBy"] == f"{prefix}.query"


# ---------------------------------------------------------------------------
# R2A-004 — generic descriptions
# ---------------------------------------------------------------------------


def test_generic_descriptions_are_grammatical_and_disclose_lifecycle() -> None:
    """Per-prefix overrides replace the placeholder article template."""
    registry = ToolRegistry()
    registry._ensure_groups()
    published = {schema["name"] for schema in _all_tools()}
    tool_ref = re.compile(
        r"\b([a-z_]+\.(?:read|query|get|list|create|update|delete|outdate|reactivate))\b"
    )
    bad_articles: list[str] = []
    for prefix in ("adr", "risk", "issue", "glossary", "change_request"):
        group = registry._groups[prefix]
        descriptions = {
            schema["name"].split(".", 1)[1]: schema["description"]
            for schema in group.get_tool_schemas()
        }
        for action, description in descriptions.items():
            assert len(description) >= 40, f"{prefix}.{action} is too short"
            assert f"a {prefix} entity" not in description
            for referenced_tool in tool_ref.findall(description):
                assert referenced_tool in published, (
                    f"{prefix}.{action} references a non-existent tool: "
                    f"{referenced_tool}"
                )
            if " a adr" in description or " a issue" in description or " a risk" in description:
                bad_articles.append(f"{prefix}.{action}")
        delete = descriptions["delete"].lower()
        assert "hard delete" in delete, f"{prefix}.delete hides lifecycle semantics"
        assert "soft-delete" in delete, f"{prefix}.delete lacks the soft-delete pointer"
        assert f"{prefix}.outdate" in delete and f"{prefix}.reactivate" in delete
        assert "soft-delete" in descriptions["outdate"].lower()
        assert "previous workflow state" in descriptions["reactivate"].lower()
    assert not bad_articles, f"broken articles: {bad_articles}"
