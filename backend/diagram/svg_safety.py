"""
ARCH-L1-013 DiagramService — Shared SVG-safety primitives.

GH-353 (Task 6): ``_escape_xml_attr`` was defined in ``canvas_editor.py``
(Task 2 / PR #351 XSS hardening) and is reused as-is by
``node_graph_renderer.py`` (Task 6) rather than re-implemented — a second,
divergent escaping function would be exactly the kind of drift that
reintroduces the attribute-injection bug class this module exists to
prevent.

Extracted to its own leaf module (no dependency on ``diagram.manager`` /
``diagram.validator`` / etc.) specifically so both ``canvas_editor.py`` and
``node_graph_renderer.py`` can import it without creating an import cycle
through ``diagram.manager`` <-> ``diagram.renderer`` (``canvas_editor``
imports ``diagram.manager``, which imports ``diagram.renderer`` — if
``node_graph_renderer`` imported ``canvas_editor`` directly and
``diagram.renderer`` imported ``node_graph_renderer``, that would close a
cycle back on itself).

Numeric coercion is intentionally NOT shared here: ``canvas_editor``'s
``_num_attr`` silently substitutes a caller-supplied default for
non-finite/non-numeric values (canvas stroke data is fully untrusted and
was never validated before reaching the renderer), whereas
``node_graph_renderer``'s ``_num_attr`` raises (node_graph payloads are
expected to have already passed ``node_graph.validate_node_graph``, so a
non-finite number reaching the renderer means validation was bypassed —
the safe response is to refuse to render, not guess a fallback). Sharing
one function across both would force one of these two, deliberately
different safety contracts to be wrong.
"""
from __future__ import annotations


def escape_xml_text(value: object) -> str:
    """Escape special characters for XML attribute/text content.

    Safe both as an attribute value (inside ``"..."``) and as ``<text>``
    element content — used by both diagram SVG renderers as the single
    source of truth for XML escaping.

    Args:
        value: Any value; coerced to ``str`` before escaping.

    Returns:
        The escaped string.
    """
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


__all__ = ["escape_xml_text"]
