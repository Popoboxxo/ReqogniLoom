"""ViewSet-level free-text guard (GitHub #269, findings 3 + 4).

``SanitizedCharField`` only fires on write paths that actually run the
serializer. An audit of ``rest_api/views.py`` found nine ``create``/
``partial_update`` implementations that read ``request.data`` directly and hand
the raw value to the service layer — ``GlossaryTermViewSet.create`` among them,
which is how ``{"definition": "<img src=x onerror=alert(1)>"}`` reached the
database byte-identically (#269 finding 4).

Rather than patching those nine call sites (and hoping the tenth is
remembered), the guard is hoisted into :meth:`initial`, DRF's pre-handler hook.
Every write request through a ViewSet that mixes this in is checked against the
free-text fields its ``serializer_class`` declares, regardless of whether the
handler bothers to use that serializer. Adding a new
``SanitizedCharField`` to a serializer is therefore sufficient to protect it
everywhere; no ViewSet change is needed.

Placed on ``BaseEntityViewSet``, so it covers all entity CRUD endpoints *and*
their ``@action`` sub-routes (transitions, approve, ...) uniformly.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers as drf_serializers
from rest_framework.request import Request

from rest_api.sanitization import collect_free_text_violations

__all__ = ["FreeTextSanitizationMixin"]


class FreeTextSanitizationMixin:
    """Reject HTML markup / script URIs in free-text keys of a write body."""

    #: Free-text keys a ViewSet accepts that its ``serializer_class`` does not
    #: declare (e.g. ``change_reason`` on serializers that omit it). Names
    #: listed here are guarded in addition to the declared ones.
    free_text_extra_fields: tuple[str, ...] = ()

    #: Methods whose body is inspected. Safe methods carry no body.
    _GUARDED_METHODS = frozenset({"POST", "PUT", "PATCH"})

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        """Run the standard DRF pre-checks, then guard the request body.

        Runs *after* ``super().initial`` so authentication, RBAC and throttling
        still decide first — an unauthenticated caller must not be able to
        probe field names through the validation error.
        """
        super().initial(request, *args, **kwargs)  # type: ignore[misc]

        if request.method not in self._GUARDED_METHODS:
            return

        violations = collect_free_text_violations(
            request.data,
            getattr(self, "serializer_class", None),
            extra_fields=self.free_text_extra_fields,
        )
        if not violations:
            return

        # Imported here: rest_api.serializers imports rest_api.sanitization,
        # so a module-level import would be a cycle for this package.
        from rest_api.serializers import build_error_response, detect_lang

        # Raised (not returned) because ``initial`` has no response channel.
        # The detail is already the project's REQ-L2-RA-009 envelope, which
        # ``reqogniloom_exception_handler`` passes through untouched — so a
        # free-text rejection is shaped exactly like every other validation
        # error the API emits, and the SPA's ``extractErrorMessage`` (which
        # reads ``error.details[0].errors[0]``) can surface it.
        raise drf_serializers.ValidationError(
            build_error_response(
                "VALIDATION_ERROR",
                detect_lang(request),
                details=[
                    {"field": field, "errors": messages}
                    for field, messages in violations.items()
                ],
            )
        )
