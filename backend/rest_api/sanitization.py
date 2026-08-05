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
:class:`~rest_api.serializers.SanitizedCharField` (or ``SanitizedJSONField``
for list/object-shaped prose such as ``GlossaryTerm.synonyms``) on the
serializer — no per-ViewSet copy-paste. Both carry
:class:`FreeTextFieldMarker`, which is what enrolment actually keys on.

The two rule families (HTML markup, script-capable URI schemes) and the
recursive scan live in :mod:`persistence.free_text`, which carries no DRF
dependency so that non-REST write paths can apply exactly the same rules —
notably ``persistence.custom_fields.validate_custom_fields``, which guards
``Artifact.custom_fields`` for REST, MCP and ReqIF import alike. This module is
the REST-facing wrapper and re-exports those symbols, so
``from rest_api.sanitization import find_free_text_violation`` keeps working.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from rest_framework import serializers

from persistence.free_text import (
    DANGEROUS_URI_MESSAGE,
    HTML_MARKUP_MESSAGE,
    find_free_text_violation,
)

__all__ = [
    "DANGEROUS_URI_MESSAGE",
    "HTML_MARKUP_MESSAGE",
    "FreeTextFieldMarker",
    "collect_free_text_field_names",
    "collect_free_text_violations",
    "find_free_text_violation",
    "validate_free_text",
]


class FreeTextFieldMarker:
    """Mixin that declares a serializer field as guarded free text.

    Enrolment used to be "is a ``SanitizedCharField``", which silently excluded
    any free-text field that is not character-shaped — notably
    ``GlossaryTerm.synonyms``, a ``JSONField`` holding a *list of strings*. The
    marker decouples "this value is user-authored prose" from "this value is a
    ``str``", so ``SanitizedJSONField`` enrols on exactly the same terms.

    Defined here rather than in ``rest_api.serializers`` so
    :func:`collect_free_text_field_names` can do its ``isinstance`` check
    without importing that module (which imports this one).
    """


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

    A field counts as free text when it carries :class:`FreeTextFieldMarker`
    (``SanitizedCharField`` and ``SanitizedJSONField`` both do). Resolved from
    ``_declared_fields`` (a class attribute) so no serializer is instantiated —
    this runs on every write request.

    .. note:: ``CustomFieldsSerializerMixin`` used to be a plain class whose
       declarations never reached ``_declared_fields``. #290 gave it
       ``SerializerMetaclass``, so its ``custom_fields`` JSON map became a
       *live* — and initially unguarded — stored-XSS surface. It is now
       declared as a ``SanitizedJSONField`` and therefore appears here, which
       is what produces a field-scoped ``custom_fields`` error even on the
       ViewSets that never run their serializer. The authoritative check for
       that field additionally sits in
       ``persistence.custom_fields.validate_custom_fields``, so non-REST write
       paths (MCP, services, ReqIF import) are covered too.
    """
    if serializer_cls is None:
        return frozenset()

    declared: Mapping[str, Any] = getattr(serializer_cls, "_declared_fields", {})
    return frozenset(
        name
        for name, field in declared.items()
        if isinstance(field, FreeTextFieldMarker)
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
