"""drf-spectacular schema policy for the ReqogniLoom REST surface (#1388).

The published OpenAPI document used to describe *nothing* for every view that
does not declare a DRF serializer. ``AutoSchema._get_serializer()`` answered
``None`` with the blunt ``unable to guess serializer … Ignoring view for now``
error, and the generator then rendered the operation with
``responses: {200: {description: "No response body"}}`` and no request body at
all. The path survived, but the contract was empty — a generated client could
not tell a status endpoint from a 204-only operation, and a POST body could
only be guessed.

Trade-off — a permissive schema is honest, a missing path is a lie
------------------------------------------------------------------
A view that genuinely has no serializer is *not* an error worth dropping: its
path, method, parameters, security and error responses are real and must be
published. This module therefore replaces the silent ``None`` with an explicit,
permissive fallback that is marked ``x-reqlo-untyped: true`` and still carries
the operation's real metadata. The fallback says only what is true — "any JSON
object" — instead of inventing a shape or pretending there is no body.

The fallback is *not* a licence to skip serializers. Every REST view now
declares its shape, so a real generation run reaches the fallback for no view at
all: :data:`UNTYPED_VIEW_ALLOWLIST` is empty and must stay empty. A view that
reaches the fallback is a regression and is reported by the paired gate
(``rest_api.tests.test_schema_completeness_1388``) and the ratchet
(``rest_api.tests.test_schema_burndown_1388``). The fallback machinery itself is
kept on purpose — it is the detector that makes such a regression visible
instead of silently emptying the operation again.

Where the base class raised its "guess" error, this subclass resolves nothing
and does not emit the error; everywhere it *can* resolve a serializer it
returns exactly what ``AutoSchema`` would have returned. No view is dropped and
no view's real schema changes.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

import uritemplate
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import (
    build_serializer_context,
    get_view_model,
    resolve_django_path_parameter,
    resolve_regex_path_parameter,
)
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

# Importing the module registers the ``AuthTenancyAuthentication`` extension
# (drf-spectacular discovers extensions via their metaclass). It is imported
# here — next to ``DEFAULT_SCHEMA_CLASS`` — so the extension is guaranteed to
# exist before the first ``get_auth()`` call, without touching app startup.
from auth_tenancy import schema as _auth_tenancy_schema  # noqa: F401

__all__ = [
    "ReqLoAutoSchema",
    "UNTYPED_VIEW_ALLOWLIST",
    "reset_untyped_view_usage",
    "untyped_operation_count",
    "untyped_operations_used",
    "untyped_views_used",
]


#: Views that legitimately reach the permissive fallback, mapped to the reason
#: their shape is not statically described.
#:
#: **This mapping is empty and must stay empty.** Every REST view was typed during
#: the #1388 burndown, so a real generation run records no fallback use at all:
#: ``untyped_views_used()`` is an empty frozenset and
#: ``untyped_operation_count()`` is ``0``. An entry here is therefore a
#: *regression* — a view lost its serializer — not a configuration knob.
#:
#: A non-empty entry is admissible only together with a documented justification
#: for that specific view (why its shape genuinely cannot be stated statically),
#: and it is treated as a regression for as long as ENT-E1 = A ("burn down to
#: zero, no permanent allowlist") holds. The paired gate
#: (``rest_api.tests.test_schema_completeness_1388``) and the ratchet
#: (``rest_api.tests.test_schema_burndown_1388``) fail as soon as an entry
#: appears or as soon as a view uses the fallback without one.
#:
#: Keys are **fully qualified** (``<module>.<qualname>``), never bare class
#: names: two modules may legitimately define a ``VersionView``-like class, and a
#: bare key would let the unrelated class satisfy the entry (review finding m6 on
#: #1388). ``untyped_views_used()`` records the same form, so the gate compares
#: like with like.
#:
#: The fallback machinery is deliberately *not* removed along with the entries:
#: :func:`untyped_views_used`, :func:`untyped_operation_count` and the
#: ``x-reqlo-untyped`` marker are the detector that turns a silent contract
#: regression into a failing build.
UNTYPED_VIEW_ALLOWLIST: dict[str, str] = {}


#: Operations that actually used the fallback during a generation, keyed by
#: the **fully qualified** view class (``<module>.<qualname>``) and mapped to
#: the ``(METHOD, path)`` pairs that reached it.
#:
#: The record is **per generation**, not process-global (review finding m6 on
#: #1388): drf-spectacular runs ``PREPROCESSING_HOOKS`` and the view inspection
#: synchronously on the requesting thread, so a thread-keyed bucket isolates
#: two concurrent ``/api/v1/schema/`` requests from each other. Before this, the
#: single module-level set was cleared by whichever request started last, so
#: one call's ``unable to guess`` diagnostics could be wiped by another's — and
#: the gate's "exactly this document" claim was only true single-threaded.
#:
#: A bucket starts empty in :func:`reset_untyped_view_usage`; a record without
#: a preceding reset (a generator invoked directly) transparently creates one.
_usage_by_thread: dict[int, dict[str, set[tuple[str, str]]]] = {}
_usage_lock = threading.Lock()


def _view_key(view: Any) -> str:
    """Return the module-qualified key used by the allowlist (finding m6)."""
    cls = view.__class__
    return f"{cls.__module__}.{cls.__qualname__}"


def _empty_view_operations() -> dict[str, set[tuple[str, str]]]:
    """A fresh per-view operation record."""
    return {}


def reset_untyped_view_usage(endpoints: Any, **kwargs: Any) -> Any:
    """``PREPROCESSING_HOOKS`` entry point: start a fresh per-build record.

    drf-spectacular calls preprocessing hooks once per generation with the
    endpoint list, before any view is inspected. Returning the endpoints
    unchanged keeps the hook side-effect-free for discovery.
    """
    with _usage_lock:
        _usage_by_thread[threading.get_ident()] = _empty_view_operations()
    return endpoints


def _read_view_operations() -> dict[str, set[tuple[str, str]]]:
    """Snapshot of the current thread's record, or of every record merged.

    The merge only applies when the calling thread never generated a document
    itself (a diagnostic read from another thread); the gate reads on the
    thread that generated the document and therefore always sees exactly one
    generation.
    """
    with _usage_lock:
        own = _usage_by_thread.get(threading.get_ident())
        if own is not None:
            return {view: set(operations) for view, operations in own.items()}
        merged: dict[str, set[tuple[str, str]]] = {}
        for bucket in _usage_by_thread.values():
            for view, operations in bucket.items():
                merged.setdefault(view, set()).update(operations)
        return merged


def untyped_views_used() -> frozenset[str]:
    """The module-qualified view keys that used the fallback in this build."""
    return frozenset(_read_view_operations())


def untyped_operations_used() -> dict[str, frozenset[str]]:
    """Snapshot of the fallback usage per view, for diagnostics and the gate.

    Each value is a set of ``"<METHOD> <path>"`` strings in the same form the
    document publishes (``/api/v1/...``), so a diagnostic can be compared with
    ``paths`` directly.
    """
    return {
        view: frozenset(f"{method.upper()} {path}" for method, path in operations)
        for view, operations in _read_view_operations().items()
    }


def untyped_operation_count() -> int:
    """Number of distinct operations that used the fallback in this build."""
    return sum(len(operations) for operations in _read_view_operations().values())


def _fallback_schema() -> dict[str, Any]:
    """A fresh permissive object schema for a view without a serializer."""
    return {
        "type": "object",
        "additionalProperties": True,
        "description": (
            "Permissive fallback schema (#1388): this view declares no DRF "
            "serializer, so its concrete fields are not described. Any JSON "
            "object is accepted and returned. Reaching this schema is a "
            "regression — rest_api.schema.UNTYPED_VIEW_ALLOWLIST is held empty "
            "— so a generated client must not treat the absence of properties "
            "as an empty body."
        ),
        "x-reqlo-untyped": True,
    }


class ReqLoAutoSchema(AutoSchema):
    """``AutoSchema`` that publishes untyped views instead of emptying them.

    Two behaviours change relative to the base class, both additive:

    1. A view for which no serializer can be resolved returns a marked
       permissive object schema (request: media-type map; response: a
       status-keyed map of ``OpenApiResponse``) instead of ``None`` + an
       ``unable to guess serializer`` error. An untyped write publishes every
       success status the view may answer (``POST``: 200 and 201, ``DELETE``:
       200 and 204) rather than one guess derived from the view's class shape.
    2. Path parameters whose type cannot be derived (no converter, no model —
       e.g. a plain ``ViewSet`` without ``queryset``) are declared explicitly
       as strings. This silences ``could not derive type of path parameter``
       without weakening any typed route: an existing converter or a resolvable
       model field always wins.
    """

    # -- serializer resolution ------------------------------------------------

    def _resolve_serializer(self) -> Optional[Any]:
        """Mirror ``AutoSchema._get_serializer`` without emitting an error.

        Returns the serializer/instance the base class would have returned, or
        ``None`` when it would have failed. The base class' private helper is
        not called because it emits the very error this schema exists to
        replace; the resolution rules below are copied verbatim from
        drf-spectacular 0.30 (``GenericAPIView`` → ``APIView`` leniency).
        """
        view = self.view
        context = build_serializer_context(view)
        try:
            if isinstance(view, GenericAPIView):
                # Same shortcut the base class takes: only call get_serializer()
                # when the view overrides it, otherwise get_serializer_class().
                if view.__class__.get_serializer == GenericAPIView.get_serializer:
                    serializer_class = view.get_serializer_class()
                    if serializer_class is None:
                        return None
                    return serializer_class(context=context)
                return view.get_serializer(context=context)
            if isinstance(view, APIView):
                get_serializer = getattr(view, "get_serializer", None)
                if callable(get_serializer):
                    return get_serializer(context=context)
                get_serializer_class = getattr(view, "get_serializer_class", None)
                if callable(get_serializer_class):
                    serializer_class = get_serializer_class()
                    if serializer_class is None:
                        return None
                    return serializer_class(context=context)
                return getattr(view, "serializer_class", None)
        except Exception:  # noqa: BLE001 - the base class swallows this too
            # A serializer whose get_queryset()/get_serializer_class() needs a
            # real request is not statically describable; fall back instead of
            # turning schema generation into a 500.
            return None
        return None

    def _serializer(self) -> Optional[Any]:
        """Resolve once per operation (request and response share the result)."""
        if not hasattr(self, "_reqlo_resolved_serializer"):
            self._reqlo_resolved_serializer = self._resolve_serializer()
        return self._reqlo_resolved_serializer

    def _record_untyped(self) -> None:
        view_key = _view_key(self.view)
        operation = (self.method.lower(), self.path)
        with _usage_lock:
            bucket = _usage_by_thread.setdefault(
                threading.get_ident(), _empty_view_operations()
            )
            bucket.setdefault(view_key, set()).add(operation)

    def get_auth(self) -> list[Any]:
        """Deduplicate security requirements emitted for one operation.

        Registering an ``OpenApiAuthenticationExtension`` for the project's
        authenticator (#1388) makes each operation declare ``BearerAuth`` from
        the authenticator *and* from the global ``SECURITY`` setting, which
        drf-spectacular appends unconditionally. Publishing the same
        requirement twice adds noise to every generated client, so exact
        duplicates are collapsed while the original order is preserved.
        """
        requirements = super().get_auth()
        seen: set[tuple[Any, ...]] = set()
        deduped: list[Any] = []
        for requirement in requirements:
            if isinstance(requirement, dict):
                key = tuple(
                    sorted(
                        (name, tuple(scopes or []))
                        for name, scopes in requirement.items()
                    )
                )
            else:  # pragma: no cover - defensive, requirements are mappings
                key = (str(requirement),)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(requirement)
        return deduped

    # -- request / response fallback -----------------------------------------

    def get_request_serializer(self) -> Any:
        """Return the resolved serializer or a marked permissive request body."""
        serializer = self._serializer()
        if serializer is not None:
            return serializer
        self._record_untyped()
        # A ``dict`` returned here is read by ``_get_request_body`` as a
        # media-type map, so wrap the raw schema accordingly.
        return {"application/json": _fallback_schema()}

    def get_response_serializers(self) -> Any:
        """Return the resolved serializer or the marked permissive status set."""
        serializer = self._serializer()
        if serializer is not None:
            return serializer
        self._record_untyped()
        return self._fallback_responses()

    #: Success statuses an *untyped* operation may answer. The base class picks
    #: exactly one (200, 201 for a create, 204 for DELETE) from the view's
    #: class shape, which is wrong for a plain hand-written ``APIView``: a
    #: ``POST`` that answers 201 was published as 200-only, so a generated
    #: client rejected the real response (review finding F4 on #1388).
    #:
    #: Publishing both statuses is the honest statement — the concrete code is
    #: decided by the view body, which the schema cannot see. It replaces a
    #: single possibly-wrong claim with the actual set of documented outcomes;
    #: no body is invented, and both entries point at the same permissive
    #: schema rather than a fabricated shape.
    _FALLBACK_SUCCESS_STATUSES: dict[str, tuple[int, ...]] = {
        "POST": (200, 201),
        "DELETE": (200, 204),
    }

    def _fallback_responses(self) -> dict[int, OpenApiResponse]:
        """Status-keyed fallback responses for one untyped operation."""
        statuses = self._FALLBACK_SUCCESS_STATUSES.get(self.method.upper(), (200,))
        allowed = "/".join(str(status) for status in statuses)
        responses: dict[int, OpenApiResponse] = {}
        for code in statuses:
            if code == 204:
                responses[code] = OpenApiResponse(
                    response=None,
                    description=(
                        "No response body. This untyped operation may answer "
                        f"{allowed}; the concrete success status is view-defined "
                        "(#1388)."
                    ),
                )
                continue
            responses[code] = OpenApiResponse(
                response=_fallback_schema(),
                description=(
                    "Permissive fallback response (#1388): the view declares no "
                    "DRF serializer, so the concrete body is not described. This "
                    f"untyped operation may answer {allowed}; the concrete "
                    "success status is view-defined."
                ),
            )
        return responses

    # -- path parameter types -------------------------------------------------

    def get_override_parameters(self) -> list[Any]:
        """Declare string path parameters the generator cannot type (#1388).

        ``_resolve_path_parameters`` warns for every path variable that has no
        Django converter and whose view exposes no model. Those variables are
        already published as ``string``; declaring them through the override
        seam records the same schema without the warning and makes the type
        explicit. A converter or a resolvable model field is never overridden.
        """
        parameters: list[Any] = list(super().get_override_parameters())
        try:
            model = get_view_model(self.view, emit_warnings=False)
        except Exception:  # noqa: BLE001 - no model is exactly the case we fill
            model = None
        if model is not None:
            return parameters

        for variable in uritemplate.variables(self.path):
            if resolve_django_path_parameter(
                self.path_regex, variable, self.map_renderers("format")
            ):
                continue
            if resolve_regex_path_parameter(self.path_regex, variable):
                continue
            parameters.append(
                OpenApiParameter(
                    variable,
                    type=str,
                    location=OpenApiParameter.PATH,
                    description=(
                        "Resource identifier. The route carries no converter "
                        "and the view exposes no model, so the type is declared "
                        "here as a string (#1388)."
                    ),
                )
            )
        return parameters
