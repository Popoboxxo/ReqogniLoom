"""#1388 ratchet: the untyped fallback stays at zero.

The burndown typed every REST view, so ``UNTYPED_VIEW_ALLOWLIST`` is empty and
``untyped_views_used()`` records nothing. That is the *end state*, not a
snapshot: ENT-E1 = A ("burn down to zero, no permanent allowlist") holds, so a
view that starts using the permissive fallback again is a regression and must
fail the build rather than land in a list.

This module is the permanent ratchet for that state. It is deliberately
independent of the main gate
(``rest_api.tests.test_schema_completeness_1388``): it does not import that
module's helpers or constants, so it keeps guarding even if the gate is
restructured. Both files traverse the generated document themselves.

No absolute document counts appear here on purpose — the invariant is "zero
fallbacks", not a frozen inventory size.

The second invariant is just as absolute: every operation that answers a 2xx
with a body must publish the shape it returns. There is no pin and no exemption
set for that either — a single operation that drops its `content` schema fails
the build.
"""
from __future__ import annotations

import pytest
from drf_spectacular.drainage import reset_generator_stats
from drf_spectacular.generators import SchemaGenerator

from rest_api.schema import (
    UNTYPED_VIEW_ALLOWLIST,
    untyped_operation_count,
    untyped_views_used,
)

_NON_OPERATION_KEYS = {"parameters", "summary", "description", "servers", "$ref"}

#: Operations that *always* answer a 4xx by design, so they carry no success
#: response to describe. Local copy (not imported from the gate test):
#: ``Baseline`` is immutable, ``PATCH`` is documented as 405 and never 2xx.
_ALWAYS_4XX_OPERATIONS = {
    ("/api/v1/baselines/{id}/", "patch"),
}

#: Success statuses that answer without a body by definition.
_BODYLESS_STATUSES = {"204", "205"}


@pytest.fixture(scope="module")
def generated() -> dict:
    """Generate the document once and capture what the generator recorded."""
    reset_generator_stats()
    schema = SchemaGenerator().get_schema(request=None, public=True)
    # Lower bound for every assertion below. They all *walk* the document, so a
    # generator that emitted an empty one (``{"paths": {}}``) would satisfy
    # "zero untyped / zero fallback" without ever looking at an operation —
    # a vacuous pass, which is exactly the failure mode a ratchet must not
    # have. The bound is "not empty", deliberately not an operation count: the
    # inventory size is not what this module pins (see the module docstring).
    assert schema.get("paths"), (
        "the generator produced a document without any paths; every ratchet "
        "assertion below would pass without inspecting a single operation"
    )
    assert next(_operations(schema), None) is not None, (
        "the generated document declares no operations; the ratchet has "
        "nothing to check"
    )
    return {
        "schema": schema,
        "used": untyped_views_used(),
        "operation_count": untyped_operation_count(),
    }


def _operations(schema: dict):
    """Yield ``(path, method, operation)`` for every real operation."""
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in _NON_OPERATION_KEYS or not isinstance(operation, dict):
                continue
            yield path, method, operation


def _iter_reachable_schemas(node: object, document: dict, seen: set[int] | None = None):
    """Yield every schema dict reachable from *node*, following one ``$ref`` hop.

    A fallback nested inside a paginated envelope or a component is only
    reachable through ``#/components/schemas/``, so an inline-only walk would
    miss it.
    """
    seen = set() if seen is None else seen
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if id(current) in seen:
                continue
            seen.add(id(current))
            yield current
            ref = current.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                component = (
                    (document.get("components") or {})
                    .get("schemas", {})
                    .get(ref.rsplit("/", 1)[-1])
                )
                if component is not None:
                    stack.append(component)
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend(
                value for value in current if isinstance(value, (dict, list))
            )


def _is_fallback(node: dict) -> bool:
    """Whether *node* is the permissive fallback (marker or its description)."""
    if node.get("x-reqlo-untyped") is True:
        return True
    return "Permissive fallback" in (node.get("description") or "")


def test_allowlist_is_empty() -> None:
    """A permanent allowlist is not the target state (ENT-E1 = A).

    An entry is admissible only with a documented justification for that
    specific view; while ENT-E1 = A holds, any entry counts as a regression.
    """
    assert UNTYPED_VIEW_ALLOWLIST == {}, (
        "UNTYPED_VIEW_ALLOWLIST must stay empty: every view is typed, and an "
        "entry is only admissible with a documented reason for that view. "
        f"Offending entries: {sorted(UNTYPED_VIEW_ALLOWLIST)}"
    )


def test_no_view_uses_the_fallback(generated: dict) -> None:
    """No view may reach the permissive fallback during a real generation."""
    assert generated["used"] == frozenset(), (
        "these views fell back to the permissive schema and need a serializer:\n"
        + "\n".join(sorted(generated["used"]))
    )
    assert generated["operation_count"] == 0, (
        f"{generated['operation_count']} operations used the permissive "
        "fallback; the burndown requires zero"
    )


def test_no_operation_carries_the_fallback_marker(generated: dict) -> None:
    """The published document contains no fallback schema at all.

    Walks the whole document (paths and components) so a fallback hidden in a
    paginated envelope or a shared component is caught as well.
    """
    document = generated["schema"]
    offenders = [
        (node.get("description") or "")[:120]
        for node in _iter_reachable_schemas(document, document)
        if _is_fallback(node)
    ]
    assert offenders == [], (
        "the document still carries permissive fallback schemas "
        "(x-reqlo-untyped / 'Permissive fallback'):\n" + "\n".join(offenders)
    )


def test_every_operation_with_a_body_response_declares_content(
    generated: dict,
) -> None:
    """A 2xx that is not 204/205 must publish the shape it returns.

    This is the contract the burndown was about: a status code alone leaves a
    generated client unable to tell a body from no body. Operations whose only
    success status is bodyless (``204``/``205``) are exempt, as is the
    documented always-4xx route, which has no success response to describe.
    Nothing else is: there is no exemption set, so any operation that stops
    declaring its body fails the build (ENT-E1 = A).
    """
    document = generated["schema"]
    missing: set[tuple[str, str]] = set()
    for path, method, operation in _operations(document):
        if (path, method) in _ALWAYS_4XX_OPERATIONS:
            continue
        responses = operation.get("responses") or {}
        success = [code for code in responses if str(code).startswith("2")]
        if not success:
            continue
        if all(code in _BODYLESS_STATUSES for code in success):
            continue
        if not any((responses[code] or {}).get("content") for code in success):
            missing.add((path, method))
    assert missing == set(), (
        "these operations answer a 2xx with a body but publish no content "
        "schema:\n" + "\n".join(f"{m.upper()} {p}" for p, m in sorted(missing))
    )
