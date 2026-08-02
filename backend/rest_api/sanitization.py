"""Free-text input guard for user-authored narrative fields (GitHub #269).

Historical behaviour (SEC-03/B006) was *silent sanitization*: ``strip_tags``
removed markup from a handful of fields and the stripped value was persisted
without telling the caller. That has two defects, both reported in #269:

* **Silent data loss.** ``{"title": "<img src=x onerror=alert(1)>"}`` returned
  ``201`` with ``title == ""``. The caller believes the value was stored. This
  is the same failure class as #263 (silently ignored PATCH fields).
* **Inconsistent coverage.** Sanitization lived in ``SanitizedCharField`` and
  therefore only applied on write paths that actually run the serializer.
  Several ViewSets (``GlossaryTermViewSet``, ``TestRunViewSet``,
  ``WorkspaceViewSet``, ...) read ``request.data`` directly, so their free-text
  fields were persisted verbatim — stored XSS for every non-React consumer
  (MCP responses, ReqIF/PDF export, CSV).

This module replaces "strip quietly" with "reject loudly" and provides a single
reusable seam so a *new* free-text field is protected by declaring it as
:class:`~rest_api.serializers.SanitizedCharField` on the serializer — no
per-ViewSet copy-paste.

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
is now a ``400`` instead of being silently mangled. Rejecting is the safer and
more honest of the two — the caller keeps its data and gets an actionable
message, whereas the previous behaviour destroyed it.
"""
from __future__ import annotations

import html
import re
from typing import Any, Iterable, Mapping

from django.utils.html import strip_tags
from rest_framework import serializers

__all__ = [
    "DANGEROUS_URI_MESSAGE",
    "HTML_MARKUP_MESSAGE",
    "collect_free_text_field_names",
    "collect_free_text_violations",
    "find_free_text_violation",
    "validate_free_text",
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


def _normalize_for_scheme_check(value: str) -> str:
    """Return *value* in the form a browser would resolve a URI from.

    HTML entities are decoded (twice, to catch ``&amp;#106;``) and the
    obfuscation characters above are removed, so ``&#106;avascript&#58;`` and
    ``java\\tscript:`` both normalise to ``javascript:``.
    """
    unescaped = html.unescape(html.unescape(value))
    return _OBFUSCATION_CHARS_RE.sub("", unescaped).lower()


def find_free_text_violation(value: Any) -> str | None:
    """Return an error message when *value* is not acceptable free text.

    Returns ``None`` for acceptable values and for non-string input (type
    errors are the serializer's job, not this guard's).
    """
    if not isinstance(value, str) or not value:
        return None

    normalized = _normalize_for_scheme_check(value)
    if any(scheme in normalized for scheme in _DANGEROUS_SCHEMES):
        return DANGEROUS_URI_MESSAGE

    if strip_tags(value) != value:
        return HTML_MARKUP_MESSAGE

    return None


def validate_free_text(value: Any, field_name: str | None = None) -> Any:
    """Return *value* unchanged, or raise ``ValidationError`` if it is unsafe.

    ``field_name`` scopes the raised error to that key so the response body
    reads like any other DRF field error (``{"title": ["..."]}``).
    """
    violation = find_free_text_violation(value)
    if violation is None:
        return value
    if field_name:
        raise serializers.ValidationError({field_name: [violation]})
    raise serializers.ValidationError(violation)


def collect_free_text_field_names(serializer_cls: type | None) -> frozenset[str]:
    """Names of the fields *serializer_cls* declares as free text.

    A field counts as free text when it is a ``SanitizedCharField`` instance.
    Resolved from ``_declared_fields`` (a class attribute) so no serializer is
    instantiated — this runs on every write request.

    .. note:: ``CustomFieldsSerializerMixin`` is a plain class without the DRF
       metaclass, so anything it declares never reaches ``_declared_fields``.
       That is a known, separate defect (see #263 notes); nothing declared
       there is free text today.
    """
    if serializer_cls is None:
        return frozenset()

    # Imported lazily: serializers.py imports this module.
    from rest_api.serializers import SanitizedCharField

    declared: Mapping[str, Any] = getattr(serializer_cls, "_declared_fields", {})
    return frozenset(
        name
        for name, field in declared.items()
        if isinstance(field, SanitizedCharField)
    )


def collect_free_text_violations(
    data: Any,
    serializer_cls: type | None,
    *,
    extra_fields: Iterable[str] = (),
) -> dict[str, list[str]]:
    """Map offending field name -> messages for a raw request body.

    Used by the ViewSet-level seam so write paths that bypass the serializer
    (``request.data.get(...)`` straight into a service call) get the same
    guarantee as serializer-driven ones. Unknown keys are ignored here —
    rejecting them is ``_validate_patch_payload``'s job (#263).

    Reports *every* offending field rather than the first, so a caller fixes
    them in one round-trip. Returns a plain dict (no exception) to keep this
    module free of the REST error-envelope helpers, which live in
    ``rest_api.serializers`` and import this module.
    """
    if not isinstance(data, Mapping):
        return {}

    guarded = collect_free_text_field_names(serializer_cls) | frozenset(extra_fields)
    violations: dict[str, list[str]] = {}
    for name in sorted(guarded):
        if name not in data:
            continue
        violation = find_free_text_violation(data[name])
        if violation is not None:
            violations[name] = [violation]

    return violations
