"""Free-text content rules — HTML markup and script-capable URI schemes.

This is the *detection core* behind the #269 free-text guard. It lives in the
persistence layer (Layer 0) and has **no DRF dependency**, mirroring
:mod:`persistence.custom_fields` and :mod:`persistence.role_permissions`, so
that write paths which never touch a serializer can apply the very same rules:

* ``rest_api.sanitization`` wraps it for the DRF field / ViewSet seam and
  re-exports every symbol below — that module stays the entry point for the
  REST layer.
* ``persistence.custom_fields.validate_custom_fields`` calls it directly, which
  is what closes the ``Artifact.custom_fields`` stored-XSS surface on *all*
  write paths (REST, MCP, service calls, ReqIF import) rather than REST only.

Two rule families are enforced:

``HTML markup``
    Any value whose ``strip_tags`` result differs from the input is rejected.
    That is deliberately stricter than "reject known-dangerous tags": an
    allow-list of safe tags invites bypasses, and the API stores plain text
    everywhere (no field is rendered as HTML by design).

``Dangerous URI schemes``
    ``javascript:``, ``vbscript:`` and ``data:text/html`` are rejected even
    though they contain no markup: the frontend renders Markdown descriptions
    via ``MarkdownPreview``, which turns ``[x](javascript:alert(1))`` into a
    real ``<a href>``. Matching is done on an *unescaped, control-character
    stripped* copy so ``&#106;avascript:`` and ``java\\tscript:`` cannot slip
    through.

Trade-off (documented deliberately): prose that legitimately contains
tag-shaped text (``if <input> is empty``) or the literal token ``javascript:``
is a ``400`` instead of being silently mangled. Rejecting is the safer and more
honest of the two — the caller keeps its data and gets an actionable message,
whereas silent stripping destroyed it.
"""
from __future__ import annotations

import html
import re
from itertools import chain
from typing import Any, Iterable, Mapping

from django.utils.html import strip_tags

__all__ = [
    "DANGEROUS_URI_MESSAGE",
    "HTML_MARKUP_MESSAGE",
    "MAX_SCAN_DEPTH",
    "find_free_text_violation",
]

#: Message returned when the value contains HTML/XML markup.
HTML_MARKUP_MESSAGE = (
    "contains disallowed content: HTML markup is not permitted in free-text "
    "fields. Submit plain text (the value is rejected instead of silently "
    "stripped so nothing is lost)."
)

#: Message returned when the value carries a script-capable URI scheme.
DANGEROUS_URI_MESSAGE = (
    "contains disallowed content: script-capable URI schemes "
    "(javascript:, vbscript:, data:text/html) are not permitted."
)

#: Schemes that can execute script when a value ends up in an ``href``/``src``.
_DANGEROUS_SCHEMES = ("javascript:", "vbscript:", "data:text/html")

#: Characters an attacker may interleave to break up a scheme token without
#: changing how a browser parses it: C0 controls (which include TAB, LF and CR
#: — browsers strip those from a URL), DEL and the zero-width/BOM code points.
#:
#: The plain space (U+0020) is deliberately NOT in this set. A space inside a
#: scheme makes it invalid for a browser too, so collapsing it would buy no
#: security while turning ordinary prose ("Java Script: an overview") into a
#: false positive.
_OBFUSCATION_CHARS_RE = re.compile(
    "[\x00-\x1f\x7f\u200b-\u200f\u2060\ufeff]+"
)

#: How deep the scan follows nested JSON containers. Free-text JSON fields in
#: this codebase are flat lists of strings; the bound exists only so a
#: hand-crafted deeply nested body cannot turn the guard into a CPU sink.
MAX_SCAN_DEPTH = 6


def _normalize_for_scheme_check(value: str) -> str:
    """Return *value* in the form a browser would resolve a URI from.

    HTML entities are decoded (twice, to catch ``&amp;#106;``) and the
    obfuscation characters above are removed, so ``&#106;avascript&#58;`` and
    ``java\\tscript:`` both normalise to ``javascript:``.
    """
    unescaped = html.unescape(html.unescape(value))
    return _OBFUSCATION_CHARS_RE.sub("", unescaped).lower()


def _find_scalar_violation(value: str) -> str | None:
    """Apply both rule families to a single string."""
    if not value:
        return None

    normalized = _normalize_for_scheme_check(value)
    if any(scheme in normalized for scheme in _DANGEROUS_SCHEMES):
        return DANGEROUS_URI_MESSAGE

    if strip_tags(value) != value:
        return HTML_MARKUP_MESSAGE

    return None


def find_free_text_violation(value: Any, _depth: int = 0) -> str | None:
    """Return an error message when *value* is not acceptable free text.

    Strings are checked directly. Lists/tuples and mappings are scanned
    *recursively* (keys included — a JSON object key is user-authored too), so
    a payload hidden one level down in a ``JSONField`` such as
    ``synonyms: ["<img src=x onerror=alert(1)>"]`` is caught rather than
    skipped. Before this recursion the guard returned ``None`` for anything
    that was not a ``str``, which is how those list items reached the database
    byte-identically.

    Returns ``None`` for acceptable values and for scalar non-string input
    (type errors are the caller's job, not this guard's).
    """
    if isinstance(value, str):
        return _find_scalar_violation(value)

    if _depth >= MAX_SCAN_DEPTH:
        return None

    if isinstance(value, Mapping):
        # ``chain`` over keys and values: both halves are attacker-controlled.
        candidates: Iterable[Any] = chain(value.keys(), value.values())
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = value
    else:
        return None

    for item in candidates:
        violation = find_free_text_violation(item, _depth + 1)
        if violation is not None:
            return violation

    return None
