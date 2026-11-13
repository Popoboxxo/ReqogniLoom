"""REST surface for the ADR-028 release cascade.

Four additive routes; the workflow transition itself remains the only lock:

* ``GET  /api/v1/architecture/<id>/release-impact/``
* ``POST /api/v1/architecture/<id>/release/``
* ``GET  /api/v1/architecture/<id>/release-status/<task_id>/``
* ``POST /api/v1/requirements/<id>/release/``

A release from a non-releasable state answers **409** with the allowed source
states and an executable change-request reference, never a generic 400. A
missing release configuration (no ``freeze_on_enter`` state in the workspace)
is a **400**: the request cannot succeed until an admin configures the
workflow.

A cascade above ``MAX_SYNC_RELEASE_ITEMS`` is not an error any more (GH-1804):
the same route answers **202 Accepted** with a ``task_id`` and queues
``application.tasks.release_element_async``; the status route reports its
Celery state.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.cache import cache
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import (
    PermissionDeniedError,
    ReleaseStateError,
    ReleaseTooLargeError,
    ValidationError,
)
from application.release_service import ReleaseService
from rest_api.auth_enforcer import get_auth_context
from rest_api.release_serializers import (
    ReleaseErrorSerializer,
    ReleaseImpactSerializer,
    ReleaseQueuedSerializer,
    ReleaseRequestSerializer,
    ReleaseResultSerializer,
    ReleaseStatusSerializer,
    RequirementReleaseResultSerializer,
)
from rest_api.serializers import build_error_response, detect_lang
from rest_api.views import _service_error_response

#: Cache namespace of the ``task_id`` → ``{element_id, tenant_id}`` ownership
#: record. Celery's result backend is tenant-blind (ADR-03), so a bare task id
#: would let any authenticated user in any tenant poll another tenant's
#: release result by guessing a UUID. The record is written at dispatch time and
#: enforced on every poll; a foreign and an unknown id are indistinguishable
#: (both 404) so a probe cannot even learn that a task exists.
RELEASE_TASK_META_CACHE_PREFIX = "release:task"

#: 24 h — far beyond any realistic cascade runtime, short enough that the
#: ownership records do not accumulate forever. After expiry the poll answers
#: 404 rather than serving a result nobody can attribute to a tenant.
RELEASE_TASK_META_TTL_SECONDS = 24 * 60 * 60

_RELEASE_ERROR_RESPONSES = {
    400: OpenApiResponse(
        description=(
            "Malformed request body, or the workspace configures no release "
            "state (state_meta.freeze_on_enter) for this item type. Also "
            "carries RELEASE_TOO_LARGE when the cascade cannot be queued."
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

    def _not_found(self, request: Request) -> Response:
        return Response(
            build_error_response("NOT_FOUND", self._lang(request)),
            status=status.HTTP_404_NOT_FOUND,
        )

    def _queue_release(
        self,
        request: Request,
        exc: ReleaseTooLargeError,
        *,
        element_id: UUID,
        change_reason: str,
    ) -> Response:
        """Answer **202** and queue the oversized cascade (GH-1804).

        The service refused only because the cascade is too large for a
        request thread, so the same work moves to a worker. Everything the
        worker must not re-derive from the payload is recorded beside the task
        id: the owning tenant and the target element, which is what makes the
        poll route safe against a foreign task id.

        Fallback: without ``workspace_id`` the worker could not resolve the
        caller's roles, so queueing would only produce a doomed job. The
        request then keeps the plain ``RELEASE_TOO_LARGE`` (400).
        """
        from application.tasks import release_element_async

        if exc.workspace_id is None:
            return _service_error_response(exc, self._lang(request))

        ctx = get_auth_context(request)
        task = release_element_async.delay(
            str(ctx.tenant_id),
            str(exc.workspace_id),
            str(element_id),
            str(ctx.user_id),
            change_reason,
            auth_method=getattr(ctx.auth_method, "value", ctx.auth_method),
        )
        task_id = str(task.id)
        cache.set(
            f"{RELEASE_TASK_META_CACHE_PREFIX}:{task_id}",
            {"element_id": str(element_id), "tenant_id": str(ctx.tenant_id)},
            RELEASE_TASK_META_TTL_SECONDS,
        )
        status_url = (
            f"/api/v1/architecture/{element_id}/release-status/{task_id}/"
        )
        return Response(
            {"task_id": task_id, "status": "queued", "status_url": status_url},
            status=status.HTTP_202_ACCEPTED,
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
            "the first transition, so a rejected request changes nothing. "
            "A cascade above the synchronous ceiling answers 202 with a task_id "
            "instead of running on the request thread."
        ),
        request=ReleaseRequestSerializer,
        responses={
            200: ReleaseResultSerializer,
            202: ReleaseQueuedSerializer,
            **_RELEASE_ERROR_RESPONSES,
        },
    )
    def post(self, request: Request, element_id: UUID) -> Response:
        serializer = ReleaseRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return self._invalid_request(request, serializer.errors)

        change_reason = serializer.validated_data["change_reason"]
        try:
            result = ReleaseService().release_element(
                element_id=element_id,
                ctx=get_auth_context(request),
                change_reason=change_reason,
            )
        except ReleaseTooLargeError as exc:
            # Well-formed, just too large for a request thread: run the same
            # cascade in a worker and answer 202 (GH-1804).
            return self._queue_release(
                request, exc, element_id=element_id, change_reason=change_reason
            )
        except ReleaseStateError as exc:
            return self._release_state_conflict(request, exc, element_id=element_id)
        except (ValidationError, PermissionDeniedError) as exc:
            return _service_error_response(exc, self._lang(request))
        return Response(result, status=status.HTTP_200_OK)


class ElementReleaseStatusView(_ReleaseBase):
    """GET /api/v1/architecture/<id>/release-status/<task_id>/

    Polls the Celery task queued by an oversized release (GH-1804). Follows the
    established ``BundleCompressionStatusView``/``ConsistencyStatusView``
    bare-``APIView`` polling pattern.

    Response shape::

        {"task_id": str,
         "state": "PENDING"|"STARTED"|"SUCCESS"|"FAILURE",
         "result": dict,      # present once state == "SUCCESS"
         "error": str}        # present once state == "FAILURE"

    ADR-03: Celery's result backend is tenant-blind, so the ownership record
    written at dispatch time is checked **before** the backend is touched. A
    foreign tenant's task id, another element's task id and an unknown id are
    deliberately indistinguishable — all **404** — so a probe cannot learn that
    a task exists.
    """

    @extend_schema(
        summary="Poll a queued (202) release cascade",
        description=(
            "Reports the Celery state of the release cascade queued for this "
            "element. The task id must have been issued for this element and "
            "the caller's tenant; anything else is a 404."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=str,
                location=OpenApiParameter.PATH,
                description="ArchitectureElement id the task was queued for.",
            ),
            OpenApiParameter(
                name="task_id",
                type=str,
                location=OpenApiParameter.PATH,
                description="Task id from the 202 answer.",
            ),
        ],
        responses={
            200: ReleaseStatusSerializer,
            404: OpenApiResponse(
                description="Unknown task id, or one queued for another "
                "element/tenant."
            ),
        },
    )
    def get(self, request: Request, element_id: UUID, task_id: str) -> Response:
        ctx = get_auth_context(request)
        meta = cache.get(f"{RELEASE_TASK_META_CACHE_PREFIX}:{task_id}")
        if (
            not isinstance(meta, dict)
            or meta.get("element_id") != str(element_id)
            or meta.get("tenant_id") != str(ctx.tenant_id)
        ):
            return self._not_found(request)

        state, result, error = task_state(task_id)
        body: dict[str, Any] = {"task_id": task_id, "state": state}
        if state == "SUCCESS":
            body["result"] = result
        elif state == "FAILURE":
            body["error"] = error
        return Response(body)


def task_state(task_id: str) -> tuple[str, Any, str | None]:
    """Return ``(state, result, error)`` for a Celery task id.

    ``state`` is normalised to the published enum: ``PENDING``,
    ``STARTED``, ``SUCCESS`` or ``FAILURE``. ``RETRY`` reports ``STARTED``
    (the job is alive), and any state the result backend invents beyond that
    (``REVOKED``, an expired id) reports ``PENDING`` — the task never ran under
    this deployment's knowledge, which is exactly what ``PENDING`` means to a
    polling client.

    Module-level on purpose: the status route's own tests patch this seam
    instead of standing up a broker and a result backend.
    """
    from celery.result import AsyncResult

    from reqogniloom.celery import app as celery_app

    async_result = AsyncResult(task_id, app=celery_app)
    state = async_result.state
    if state == "SUCCESS":
        return "SUCCESS", async_result.result, None
    if state == "FAILURE":
        exc = async_result.result
        return "FAILURE", None, str(exc) if exc is not None else "Unknown error"
    if state in ("STARTED", "RETRY"):
        return "STARTED", None, None
    return "PENDING", None, None


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
