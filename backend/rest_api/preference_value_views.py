"""REST surface for the Q1 three-level preference values (Plan C, T-C2-3).

Endpoints (all under ``/api/v1/``, envelope from ``build_error_response``):

  GET         preference-values/registry/
  GET         users/me/preference-values/effective/[?keys=a,b]
  GET         workspaces/<uuid:workspace_id>/preference-values/effective/[?keys=a,b]
  GET/PATCH   users/me/preference-values/
  GET/PATCH   workspaces/<uuid:workspace_id>/preference-values/
  GET/PATCH   system/preference-values/

The registry names every preference key this build knows (type, default, allowed
levels, combination mode, optional choices and the generic editor hint). The
``effective`` reads answer the *resolved* value plus which level supplied it
(``user`` / ``workspace`` / ``global`` / ``default`` / ``merged``); the level
routes answer one level's stored values, so "absent" means "inherit", never
"empty". ``PATCH`` takes ``{"values": {<key>: <value> | null}}``; ``null`` resets
that key at that level.

Authorization (ENT-C2 = A, ENT-C3 = B):

* personal — ``ctx.user_id`` is the whole boundary (self-service, same shape as
  the sibling ``/users/me/*`` routes),
* workspace — read: any member with READ on the workspace; write:
  :attr:`Operation.WORKSPACE_CONFIG` (ADMIN tier), declared per method through
  ``required_operation``,
* global — read: any authenticated member; write: the ``admin`` role (re-asserted
  by the service) plus the ADMIN-tier API-key capability via
  :class:`AdminScopeRequiredMixin`.

A workspace that is not in the caller's tenant answers 404 ``NOT_FOUND`` — the
store itself is tenant-filtered rather than workspace-validating, so without the
explicit lookup a foreign workspace would read as "no values set".

Deliberately named ``preference_value_views``: ``rest_api/preference_views.py``
already owns the unrelated ``UserPreferenceView`` (``UserWorkspacePreference``,
REQ-L1-027). One module per concept keeps the two resolution models apart.

Layer 3 only: every read and write goes through ``PreferenceService`` (ADR-01),
workspace existence through ``WorkspaceService``; this module contains no ORM
access — the ratchet in ``rest_api/tests/test_architecture.py`` enforces that.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.preference_registry import (
    all_preference_keys,
    get_preference_key,
    validate_preference_value,
)
from application.preference_service import (
    LEVEL_GLOBAL,
    LEVEL_USER,
    LEVEL_WORKSPACE,
    PreferenceService,
)
from application.workspace_service import WorkspaceService
from auth_tenancy.rest import HasOperationPermission
from auth_tenancy.services import Operation
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from rest_api.auth_enforcer import AdminScopeRequiredMixin, get_auth_context
from rest_api.serializers import (
    UnknownFieldRejectionMixin,
    build_error_response,
    detect_lang,
)

#: OpenAPI tag shared by the six routes below.
_TAG = "preferences"

#: The ``?keys=a,b`` filter, described once for both ``effective`` reads.
_KEYS_PARAMETER = OpenApiParameter(
    name="keys",
    type=str,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Comma-separated preference keys to answer. Omit for every registered "
        "key. An unregistered key is a 400 VALIDATION_ERROR."
    ),
)


# ---------------------------------------------------------------------------
# Response serializers (also the OpenAPI schema, per §f.5 / KA-ALL-04)
# ---------------------------------------------------------------------------


class PreferenceEffectiveValueSerializer(serializers.Serializer):
    """One resolved key: its effective value and the level that supplied it."""

    value = serializers.JSONField()
    source = serializers.CharField()


class PreferenceEffectiveSerializer(serializers.Serializer):
    """Body of both ``effective`` reads."""

    workspace_id = serializers.CharField(allow_null=True)
    values = serializers.DictField(child=PreferenceEffectiveValueSerializer())


class PreferenceLevelSerializer(serializers.Serializer):
    """Body of the three level routes: only the keys actually set there."""

    scope = serializers.CharField()
    workspace_id = serializers.CharField(allow_null=True)
    values = serializers.DictField(child=serializers.JSONField())


class PreferenceRegistryEntrySerializer(serializers.Serializer):
    """One registered preference key."""

    key = serializers.CharField()
    type = serializers.CharField()
    choices = serializers.ListField(child=serializers.CharField(), allow_null=True)
    default = serializers.JSONField()
    levels = serializers.ListField(child=serializers.CharField())
    mode = serializers.CharField()
    ui_editor = serializers.CharField(allow_null=True)


class PreferenceRegistrySerializer(serializers.Serializer):
    """Body of ``GET preference-values/registry/``."""

    keys = PreferenceRegistryEntrySerializer(many=True)


class PreferenceLevelWriteSerializer(
    UnknownFieldRejectionMixin, serializers.Serializer
):
    """``{"values": {<key>: <value> | null}}``.

    ``values`` is required but may carry ``null`` per key (reset = inherit).
    Validation of the keys themselves belongs to the registry/service — they are
    the single source of truth — so this serializer only pins the envelope.
    ``UnknownFieldRejectionMixin`` (#851) turns an undeclared top-level key into a
    400 instead of the DRF default of silently dropping it.
    """

    values = serializers.JSONField()

    def validate_values(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Must be a JSON object mapping preference keys to values."
            )
        return value


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _validation_error(
    lang: str, message: str | None = None, details: Any = None
) -> Response:
    return Response(
        build_error_response(
            "VALIDATION_ERROR", lang, message=message, details=details
        ),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _not_found(lang: str, message: str) -> Response:
    return Response(
        build_error_response("NOT_FOUND", lang, message=message),
        status=status.HTTP_404_NOT_FOUND,
    )


def _permission_denied(lang: str, message: str) -> Response:
    return Response(
        build_error_response("PERMISSION_DENIED", lang, message=message),
        status=status.HTTP_403_FORBIDDEN,
    )


def _serializer_details(errors: Any) -> list[dict[str, Any]]:
    """Flatten ``serializer.errors`` into the ``{field, errors}`` envelope list."""
    details: list[dict[str, Any]] = []
    for field, messages in errors.items():
        if not isinstance(messages, list):
            messages = [messages]
        details.append({"field": field, "errors": [str(message) for message in messages]})
    return details


def _value_error_details(scope: str, values: dict[str, Any]) -> list[dict[str, Any]]:
    """Name the offending ``values.<key>`` entries of a rejected payload.

    Only called on the error path, after ``PreferenceService.set_level`` refused
    the payload: the service stays the authority (it validates and writes
    atomically — this pass cannot and must not write anything). Its error is one
    message, while the contract asks for one ``{field, errors}`` entry per bad
    entry, so the offending keys are re-derived here from the registry's public
    API — the same two functions the service validates with.
    """
    if not isinstance(values, dict):  # pragma: no cover - serializer guards this
        return [{"field": "values", "errors": ["Must be a JSON object."]}]
    details: list[dict[str, Any]] = []
    for key, value in values.items():
        if not isinstance(key, str):
            details.append(
                {
                    "field": "values",
                    "errors": [
                        f"Preference keys must be strings, got {type(key).__name__}"
                    ],
                }
            )
            continue
        try:
            spec = get_preference_key(key)
        except ValidationError as exc:
            details.append({"field": f"values.{key}", "errors": [str(exc)]})
            continue
        if scope not in spec.levels:
            # Same wording as ``PreferenceService._validated_writes`` so the
            # envelope's message and this detail never describe the rule
            # differently.
            details.append(
                {
                    "field": f"values.{key}",
                    "errors": [
                        f"Preference key {key!r} cannot be set at level "
                        f"{scope!r}; allowed levels: {sorted(spec.levels)}"
                    ],
                }
            )
            continue
        if value is None:
            continue  # reset, nothing to validate
        try:
            validate_preference_value(spec, value)
        except ValidationError as exc:
            details.append({"field": f"values.{key}", "errors": [str(exc)]})
    return details


def _parse_keys(request: Request) -> list[str] | None:
    """Return the ``?keys=a,b`` filter, or ``None`` for "every registered key"."""
    raw = request.query_params.get("keys")
    if raw is None:
        return None
    keys = [key.strip() for key in raw.split(",") if key.strip()]
    return keys or None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PreferenceRegistryView(APIView):
    """``GET /api/v1/preference-values/registry/`` — the key catalogue.

    Metadata only: every authenticated member may read it (the generic settings
    section needs it to render a level's editors). ``keys`` is sorted by key so
    the payload is deterministic (KA-ALL-10).
    """

    permission_classes = [HasOperationPermission]
    serializer_class = PreferenceRegistrySerializer

    @extend_schema(tags=[_TAG], responses=PreferenceRegistrySerializer)
    def get(self, request: Request, **kwargs: Any) -> Response:
        entries = [
            {
                "key": spec.key,
                "type": spec.value_type,
                "choices": list(spec.choices) if spec.choices is not None else None,
                "default": spec.default,
                "levels": sorted(spec.levels),
                "mode": spec.mode,
                "ui_editor": spec.ui_editor,
            }
            for spec in all_preference_keys()
        ]
        return Response(PreferenceRegistrySerializer({"keys": entries}).data)


# ---------------------------------------------------------------------------
# Effective reads
# ---------------------------------------------------------------------------


class _WorkspaceLookupMixin:
    """Shared plumbing for the routes whose URL may name a workspace.

    The store is tenant-filtered rather than workspace-validating, so a workspace
    id that exists in another tenant (or not at all) would silently read as "no
    values set". Resolving it through ``WorkspaceService`` — which raises
    ``NotFoundError`` — turns that into the contract's 404.
    """

    @staticmethod
    def _workspace_id(kwargs: dict[str, Any]) -> UUID | None:
        workspace_id = kwargs.get("workspace_id")
        return workspace_id if isinstance(workspace_id, UUID) else None

    @staticmethod
    def _assert_workspace(ctx: Any, workspace_id: UUID | None) -> None:
        if workspace_id is not None:
            WorkspaceService().get_workspace(workspace_id, ctx)


class _EffectivePreferenceBaseView(_WorkspaceLookupMixin, APIView):
    """Shared plumbing for the two ``…/preference-values/effective/`` reads."""

    permission_classes = [HasOperationPermission]
    serializer_class = PreferenceEffectiveSerializer

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id = self._workspace_id(kwargs)
        try:
            self._assert_workspace(ctx, workspace_id)
            payload = PreferenceService().effective(
                ctx, workspace_id=workspace_id, keys=_parse_keys(request)
            )
        except NotFoundError as exc:
            return _not_found(lang, str(exc))
        except ValidationError as exc:
            return _validation_error(
                lang, message=str(exc), details=[{"field": "keys", "errors": [str(exc)]}]
            )
        return Response(PreferenceEffectiveSerializer(payload).data)


class UserEffectivePreferenceView(_EffectivePreferenceBaseView):
    """``/api/v1/users/me/preference-values/effective/`` — user + global levels.

    ``workspace_id`` is ``null`` on purpose: this is the account-wide view, so no
    workspace level participates. The Frontend hydrator reads it at app start.
    """

    @extend_schema(
        tags=[_TAG], parameters=[_KEYS_PARAMETER], responses=PreferenceEffectiveSerializer
    )
    def get(self, request: Request, **kwargs: Any) -> Response:
        return super().get(request, **kwargs)


class WorkspaceEffectivePreferenceView(_EffectivePreferenceBaseView):
    """``/api/v1/workspaces/<uuid>/preference-values/effective/``.

    Same shape as the personal read, with the workspace level included; the
    workspace comes from the URL, so the auth layer scopes ``active_roles`` to
    it and ``Operation.READ`` keeps the read to members.
    """

    required_operation = Operation.READ

    @extend_schema(
        tags=[_TAG], parameters=[_KEYS_PARAMETER], responses=PreferenceEffectiveSerializer
    )
    def get(self, request: Request, **kwargs: Any) -> Response:
        return super().get(request, **kwargs)


# ---------------------------------------------------------------------------
# Level reads/writes
# ---------------------------------------------------------------------------


class _PreferenceLevelBaseView(_WorkspaceLookupMixin, APIView):
    """Shared read/write plumbing for the three level routes."""

    permission_classes = [HasOperationPermission]
    serializer_class = PreferenceLevelSerializer
    #: The level this view stores into — overridden by each subclass.
    scope: str = LEVEL_USER

    def get(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        workspace_id = self._workspace_id(kwargs)
        try:
            self._assert_workspace(ctx, workspace_id)
            payload = PreferenceService().get_level(
                ctx, scope=self.scope, workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return _not_found(lang, str(exc))
        except ValidationError as exc:
            return _validation_error(lang, message=str(exc))
        return Response(PreferenceLevelSerializer(payload).data)

    def patch(self, request: Request, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        serializer = PreferenceLevelWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(lang, details=_serializer_details(serializer.errors))

        values = serializer.validated_data["values"]
        workspace_id = self._workspace_id(kwargs)
        try:
            self._assert_workspace(ctx, workspace_id)
            payload = PreferenceService().set_level(
                ctx, scope=self.scope, values=values, workspace_id=workspace_id
            )
        except NotFoundError as exc:
            return _not_found(lang, str(exc))
        except PermissionDeniedError as exc:
            return _permission_denied(lang, str(exc))
        except ValidationError as exc:
            return _validation_error(
                lang,
                message=str(exc),
                details=_value_error_details(self.scope, values)
                or [{"field": "values", "errors": [str(exc)]}],
            )
        return Response(PreferenceLevelSerializer(payload).data)


class UserPreferenceLevelView(_PreferenceLevelBaseView):
    """``/api/v1/users/me/preference-values/`` — the caller's own values.

    Self-service, so ``required_operation`` is deliberately unset: the API-key
    scope gate must keep deriving WRITE from the HTTP method, otherwise a
    read-scoped key could write here. ``ctx.user_id`` is the boundary — the view
    takes no user parameter.
    """

    scope = LEVEL_USER

    @extend_schema(tags=[_TAG], responses=PreferenceLevelSerializer)
    def get(self, request: Request, **kwargs: Any) -> Response:
        return super().get(request, **kwargs)

    @extend_schema(
        tags=[_TAG],
        request=PreferenceLevelWriteSerializer,
        responses=PreferenceLevelSerializer,
    )
    def patch(self, request: Request, **kwargs: Any) -> Response:
        return super().patch(request, **kwargs)


class WorkspacePreferenceLevelView(_PreferenceLevelBaseView):
    """``/api/v1/workspaces/<uuid>/preference-values/`` — the workspace default.

    ENT-C3 = B: a workspace-wide default is governance configuration, so a write
    requires :attr:`Operation.WORKSPACE_CONFIG` (ADMIN tier) while a read stays
    ``Operation.READ``. Declared per method because one APIView serves both.
    """

    scope = LEVEL_WORKSPACE

    @property
    def required_operation(self) -> Operation:
        """``READ`` for a read, ``WORKSPACE_CONFIG`` for a mutation.

        Read through ``getattr(self, "request", None)`` because the permission
        class looks this up during schema generation too, where no request is
        bound yet.
        """
        request = getattr(self, "request", None)
        if request is not None and request.method == "PATCH":
            return Operation.WORKSPACE_CONFIG
        return Operation.READ

    @extend_schema(tags=[_TAG], responses=PreferenceLevelSerializer)
    def get(self, request: Request, **kwargs: Any) -> Response:
        return super().get(request, **kwargs)

    @extend_schema(
        tags=[_TAG],
        request=PreferenceLevelWriteSerializer,
        responses=PreferenceLevelSerializer,
    )
    def patch(self, request: Request, **kwargs: Any) -> Response:
        return super().patch(request, **kwargs)


class GlobalPreferenceLevelView(AdminScopeRequiredMixin, _PreferenceLevelBaseView):
    """``/api/v1/system/preference-values/`` — the tenant-wide default.

    Reads are open to any authenticated member (a settings page resolves the
    inherited value through this endpoint); a mutation requires the ``admin``
    role (re-asserted by the service) plus the ADMIN-tier API-key capability.
    """

    scope = LEVEL_GLOBAL

    @property
    def required_operation(self) -> Operation:
        """``READ`` for a read, ``WORKSPACE_CONFIG`` for a mutation."""
        request = getattr(self, "request", None)
        if request is not None and request.method == "PATCH":
            return Operation.WORKSPACE_CONFIG
        return Operation.READ

    @extend_schema(tags=[_TAG], responses=PreferenceLevelSerializer)
    def get(self, request: Request, **kwargs: Any) -> Response:
        return super().get(request, **kwargs)

    @extend_schema(
        tags=[_TAG],
        request=PreferenceLevelWriteSerializer,
        responses=PreferenceLevelSerializer,
    )
    def patch(self, request: Request, **kwargs: Any) -> Response:
        return super().patch(request, **kwargs)


__all__ = [
    "GlobalPreferenceLevelView",
    "PreferenceEffectiveSerializer",
    "PreferenceEffectiveValueSerializer",
    "PreferenceLevelSerializer",
    "PreferenceLevelWriteSerializer",
    "PreferenceRegistryEntrySerializer",
    "PreferenceRegistrySerializer",
    "PreferenceRegistryView",
    "UserEffectivePreferenceView",
    "UserPreferenceLevelView",
    "WorkspaceEffectivePreferenceView",
    "WorkspacePreferenceLevelView",
]
