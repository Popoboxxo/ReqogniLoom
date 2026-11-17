"""API-008 ratchet: explicit production schemas + opt-in strict handlers.

Central ``inputSchema`` validation at the dispatch boundary is deliberately
NOT implemented — see the design decision at ``tools/base.py:133-138``
(``reject_unknown_params`` is opt-in; a blanket rule would break clients that
rely on extra keys being ignored, and ``jsonschema`` is only a transitive
dependency here). Instead this suite ratchets the alternative the gate chose:

1. every production group publishes explicit schemas — no ``kwargs`` fallback;
2. the ratified strict groups call ``reject_unknown_params`` on every mapped
   handler, with one documented opt-in policy for the legacy groups;
3. an unknown parameter on a strict group fails with VALIDATION_ERROR (-32602).
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any
from uuid import uuid4

import pytest

from mcp_server.protocol_handler import ErrorFormatter
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.base import BaseToolGroup, ParameterError
from mcp_server.tools.generic import GenericCrudToolGroup

pytestmark = pytest.mark.django_db

#: Prefixes whose every mapped handler calls ``reject_unknown_params``.
#: Ratchet: this set may grow, never shrink.
STRICT_PREFIXES: frozenset[str] = frozenset({
    "adr", "change_request", "glossary", "issue", "risk",
})

#: One documented policy covers the grandfathered groups. Adding a group to
#: STRICT_PREFIXES is the ratchet step that retires it from this baseline.
OPT_IN_BASELINE: dict[str, str] = {
    "reason": (
        "Per the #459 design decision strict parameter validation is opt-in "
        "per handler; legacy groups are grandfathered for one release and "
        "ratcheted into STRICT_PREFIXES one at a time."
    ),
    "issue": "#459",
}

_FALLBACK_PROPERTIES = frozenset({"kwargs"})


def _production_groups() -> list[tuple[str, Any]]:
    """Return one (prefix, group) per distinct production group."""
    registry = ToolRegistry()
    registry._ensure_groups()
    groups: list[tuple[str, Any]] = []
    seen: set[int] = set()
    for prefix, group in registry._groups.items():
        if id(group) in seen:
            continue
        seen.add(id(group))
        if getattr(group, "capability_only", False):
            continue
        groups.append((prefix, group))
    return groups


def _is_fallback_schema(schema: dict[str, Any]) -> bool:
    """True for the forbidden ``{"kwargs": {...}}`` placeholder contract."""
    properties = (schema.get("inputSchema") or {}).get("properties") or {}
    return frozenset(properties) == _FALLBACK_PROPERTIES


# ---------------------------------------------------------------------------
# 1. Explicit schemas for every production group
# ---------------------------------------------------------------------------


def test_every_production_group_publishes_explicit_schemas() -> None:
    """A production group without explicit schemas fails closed."""
    groups = _production_groups()
    assert len(groups) >= 40, "the production registry looks truncated"

    offenders: list[str] = []
    for prefix, group in groups:
        explicit = bool(getattr(group, "_TOOL_SCHEMAS", None)) or (
            type(group).get_tool_schemas is not BaseToolGroup.get_tool_schemas
        )
        if not explicit:
            offenders.append(prefix)
        schemas = group.get_tool_schemas()
        if not schemas:
            offenders.append(f"{prefix}(empty)")
        if any(_is_fallback_schema(schema) for schema in schemas):
            offenders.append(f"{prefix}(kwargs-fallback)")

    assert not offenders, (
        f"Production groups without an explicit schema contract: {offenders}. "
        "The 'kwargs' fallback is forbidden by the API-008 ratchet."
    )


def test_base_group_rejects_fallback_instead_of_emitting_it() -> None:
    """The fallback code path itself is gone, not merely unused."""
    group = BaseToolGroup()
    group._TOOL_MAP = {"probe.tool": "_handler"}
    with pytest.raises(RuntimeError, match="no explicit _TOOL_SCHEMAS"):
        group.get_tool_schemas()


def test_published_catalogue_has_no_placeholder_schema() -> None:
    """Defence in depth on the assembled 301-tool catalogue."""
    schemas = ToolRegistry().all_tool_schemas()
    assert len(schemas) == 301
    placeholders = [s["name"] for s in schemas if _is_fallback_schema(s)]
    assert not placeholders, f"placeholder schemas published: {placeholders}"
    missing_description = [
        s["name"] for s in schemas
        if not s.get("description") or s["description"] == f"Execute {s['name']}"
    ]
    assert not missing_description, (
        f"tools with a placeholder description: {missing_description}"
    )


# ---------------------------------------------------------------------------
# 2. Strict handlers (opt-in, with one documented baseline)
# ---------------------------------------------------------------------------


def test_strict_prefixes_are_ratified_and_opt_in_is_documented() -> None:
    """The strict set may grow; every other group has one policy entry."""
    production = {prefix for prefix, _ in _production_groups()}
    assert STRICT_PREFIXES <= production
    assert OPT_IN_BASELINE["issue"].startswith("#")
    assert len(OPT_IN_BASELINE["reason"]) >= 40

    groups = dict(_production_groups())
    for prefix in sorted(STRICT_PREFIXES):
        group = groups[prefix]
        handlers = {
            tool_name: getattr(group, handler)
            for tool_name, handler in group._TOOL_MAP.items()
        }
        assert handlers, f"{prefix} has no mapped handlers"
        for tool_name, method in handlers.items():
            source = textwrap.dedent(inspect.getsource(method))
            tree = ast.parse(source)
            calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "reject_unknown_params"
            ]
            assert calls, (
                f"{tool_name} does not call reject_unknown_params; add it or "
                "document a named exception"
            )


# ---------------------------------------------------------------------------
# 3. Wire-level behaviour
# ---------------------------------------------------------------------------


def test_unknown_param_on_strict_group_returns_validation_error() -> None:
    """An extra key is rejected at dispatch as VALIDATION_ERROR (-32602)."""
    from application.adr_service import AdrService
    from auth_tenancy.context import AuthContext, AuthMethod

    group = GenericCrudToolGroup("adr", AdrService)
    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )
    result = group.execute_tool(
        "adr.read",
        {"id": str(uuid4()), "not_a_declared_param": "x"},
        ctx,
        "reqlo_test_key",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"
    assert "not_a_declared_param" in result.message
    formatted = ErrorFormatter.format_error(result.error_code)
    assert formatted["code"] == -32602  # JSON-RPC Invalid params
    assert formatted["code"] != -32603

    # The guard is on the handler itself, so a direct call is strict too.
    with pytest.raises(ParameterError):
        group._handle_read(
            params={"id": str(uuid4()), "not_a_declared_param": "x"},
            auth_context=ctx,
            api_key="reqlo_test_key",
        )


def test_unknown_param_on_strict_group_fails_before_the_service_call() -> None:
    """No service method is reached when an undeclared key is present."""
    from application.adr_service import AdrService
    from auth_tenancy.context import AuthContext, AuthMethod

    group = GenericCrudToolGroup("adr", AdrService)
    ctx = AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )
    calls: list[str] = []
    original = group._read_method

    def _tracking_read(**kwargs: Any) -> Any:
        calls.append("read")
        return original(**kwargs)

    group._read_method = _tracking_read  # type: ignore[assignment]
    group.execute_tool(
        "adr.read",
        {"id": str(uuid4()), "unexpected": True},
        ctx,
        "reqlo_test_key",
    )
    assert calls == [], "the service was called despite the unknown parameter"
