"""REST surface for the ADR-028 release cascade.

Three additive routes; the workflow transition itself remains the only lock:

* ``GET  /api/v1/architecture/<id>/release-impact/``
* ``POST /api/v1/architecture/<id>/release/``
* ``POST /api/v1/requirements/<id>/release/``

A release from a non-releasable state answers **409** with the allowed source
states and an executable change-request reference, never a generic 400. A
missing release configuration (no ``freeze_on_enter`` state in the workspace)
is a **400**: the request cannot succeed until an admin configures the
workflow.
"""

from __future__ import annotations

from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import (
    PermissionDeniedError,
    ReleaseStateError,
    ValidationError,
)
from application.release_service import ReleaseService
from rest_api.auth_enforcer import get_auth_context
from rest_api.release_serializers import (
    ReleaseErrorSerializer,
    ReleaseImpactSerializer,
    ReleaseRequestSerializer,
    ReleaseResultSerializer,
    RequirementReleaseResultSerializer,
)
from rest_api.serializers import build_error_response, detect_lang
from rest_api.views import _service_error_response

_RELEASE_ERROR_RESPONSES = {
    400: OpenApiResponse(
        description=(
            "Malformed request body, or the workspace configures no release "
            "state (state_meta.freeze_on_enter) for this item type."
        )
    ),
    403: OpenApiResponse(description="The caller lacks the approver/admin role."),
    409: ReleaseErrorSerializer,
}


def _change_request_details(
    element_id: UUID | None, requirement_id: UUID | None, reason: str
) -> list[dict]:
    query = (
        f"?scope=allocation&element_id={element_id}"
        if element_id is not None
        else f"?scope=allocation&requirement_id={requirement_id}"
    )
    return [
        {
            "field": "element_id" if element_id is not None else "requirement_id",
            "required_action": "create_change_request",
            "change_request_url": f"/api/v1/change-requests/{query}",
            # The service text names the current state and the allowed source
            # states; the envelope message above stays localised.
            "reason": reason,
        }
    ]


class _ReleaseBase(APIView):
    def _lang(self, request: Request) -> str:
        return detect_lang(request)

    def _invalid_request(self, request: Request, errors: dict) -> Response:
        return Response(
            build_error_response(
                "VALIDATION_ERROR",
                self._lang(request),
                details=[
                    {"field": field, "errors": [str(e) for e in errs]}
                    for field, errs in errors.items()
                ],
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _release_state_conflict(
        self,
        request: Request,
        exc: ReleaseStateError,
        *,
        element_id: UUID | None = None,
        requirement_id: UUID | None = None,
    ) -> Response:
        return Response(
            build_error_response(
                "RELEASE_NOT_ALLOWED",
                self._lang(request),
                details=_change_request_details(element_id, requirement_id, str(exc)),
            ),
            status=status.HTTP_409_CONFLICT,
        )


class ElementReleaseImpactView(_ReleaseBase):
    @extend_schema(
        summary="Preview the impact of releasing an architecture element",
        description=(
            "Read-only preview of the cascade: the workspace release state, the "
            "allowed source states, the descendant elements and every requirement "
            "allocated to them. Nothing is changed."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=str,
                location=OpenApiParameter.PATH,
                description="ArchitectureElement id (the entity id, not the Artifact id).",
            )
        ],
        responses={
            200: ReleaseImpactSerializer,
            400: OpenApiResponse(
                description="Element not found or no release state configured."
            ),
            403: OpenApiResponse(description="No access to the element's workspace."),
        },
    )
    def get(self, request: Request, element_id: UUID) -> Response:
        try:
            impact = ReleaseService().impact(
                element_id=element_id, ctx=get_auth_context(request)
            )
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, self._lang(request))
        return Response(impact.to_dict())


class ElementReleaseView(_ReleaseBase):
    @extend_schema(
        summary="Release an architecture element, its descendants and their requirements",
        description=(
            "Transitions the element, every descendant and every allocated "
            "requirement into the workspace's release state (the state carrying "
            "state_meta.freeze_on_enter). All affected items are validated before "
            "the first transition, so a rejected request changes nothing."
        ),
        request=ReleaseRequestSerializer,
        responses={
            200: ReleaseResultSerializer,
            **_RELEASE_ERROR_RESPONSES,
        },
    )
    def post(self, request: Request, element_id: UUID) -> Response:
        serializer = ReleaseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_request(request, serializer.errors)

        try:
            result = ReleaseService().release_element(
                element_id=element_id,
                ctx=get_auth_context(request),
                change_reason=serializer.validated_data["change_reason"],
            )
        except ReleaseStateError as exc:
            return self._release_state_conflict(request, exc, element_id=element_id)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, self._lang(request))
        return Response(result, status=status.HTTP_200_OK)


class RequirementReleaseView(_ReleaseBase):
    @extend_schema(
        summary="Release a single requirement (the element release's special case)",
        description=(
            "Releases one requirement without touching its element. Releasing an "
            "already released requirement is a no-op success (released=false)."
        ),
        request=ReleaseRequestSerializer,
        responses={
            200: RequirementReleaseResultSerializer,
            **_RELEASE_ERROR_RESPONSES,
        },
    )
    def post(self, request: Request, requirement_id: UUID) -> Response:
        serializer = ReleaseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_request(request, serializer.errors)

        try:
            result = ReleaseService().release_requirement(
                requirement_id=requirement_id,
                ctx=get_auth_context(request),
                change_reason=serializer.validated_data["change_reason"],
            )
        except ReleaseStateError as exc:
            return self._release_state_conflict(
                request, exc, requirement_id=requirement_id
            )
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, self._lang(request))
        return Response(result, status=status.HTTP_200_OK)
