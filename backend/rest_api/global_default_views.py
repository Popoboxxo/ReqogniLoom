"""REST endpoints for the Workflow & Permission global-default model.

Implements the contract in
``docs/api/workflow-permissions-global-default.openapi.yaml`` (REQ-178..187):

* Global workflow definitions (tenant-wide, per item_type+preset) — list,
  retrieve, initialize, state/transition CRUD (admin-only).
* Global permission definition (tenant singleton) + guarded enforcement flip.
* Workspace permission definition override + reset-to-default.
* Permission-decision mismatch review log (read-only).

All endpoints reuse the project error envelope (``build_error_response``) and the
same admin gate pattern as :class:`LlmSettingsView` (``ctx.has_role(ROLE_ADMIN)``
resolved tenant-wide).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import unquote
from uuid import UUID

from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.workflow_facade import WorkflowFacade
from auth_tenancy.models import GlobalPermissionDefinition, ROLE_ADMIN
from auth_tenancy.services.permission_definition import (
    DEFAULT_MISMATCH_WINDOW_DAYS,
    MismatchCountStaleError,
    NoGlobalSourceError,
    PermissionDefinitionService,
)
from auth_tenancy.services.permission_matrix import MatrixValidationError
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _require_admin(request: Request):
    """Return ``(ctx, lang)`` or a 403 Response when the caller is not admin."""
    lang = detect_lang(request)
    ctx = get_auth_context(request)
    if not ctx.has_role(ROLE_ADMIN):
        return Response(
            build_error_response(
                "PERMISSION_DENIED",
                lang,
                message="Admin role required.",
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return ctx, lang


def _validation(lang: str, message: str, *, code: str = "VALIDATION_ERROR") -> Response:
    return Response(
        build_error_response(code, lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _map_workflow_error(exc: Exception, lang: str) -> Response:
    """Map a workflow-definition error to a precise HTTP status."""
    from workflow.services import (
        StateReferencedError,
        WorkflowDefinitionError,
    )

    if isinstance(exc, StateReferencedError):
        return Response(
            build_error_response("CONFLICT", lang, message=str(exc)),
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, WorkflowDefinitionError):
        msg = str(exc)
        # "already initialized" is a conflict, not a validation error.
        if "already initialized" in msg:
            return Response(
                build_error_response("CONFLICT", lang, message=msg),
                status=status.HTTP_409_CONFLICT,
            )
        return _validation(lang, msg)
    return Response(
        build_error_response("INTERNAL_ERROR", lang, message=str(exc)),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _serialize_global_graph(
    obj: Any,
    *,
    tenant_id: str,
    item_type: str,
    preset: str,
    propagated: int | None = None,
) -> dict[str, Any]:
    """Serialize a GlobalWorkflowDefinition (or empty graph) — WorkflowGraphGlobal."""
    if obj is None:
        data: dict[str, Any] = {
            "scope": "global",
            "tenant_id": str(tenant_id),
            "item_type": item_type,
            "preset": preset,
            "initialized": False,
            "initial_state": None,
            "states": [],
            "transitions": [],
            "updated_at": None,
        }
    else:
        wf = obj.workflow_json or {}
        states = list(wf.get("states", []))
        data = {
            "scope": "global",
            "tenant_id": str(obj.tenant_id),
            "item_type": obj.item_type,
            "preset": obj.preset,
            "initialized": True,
            "initial_state": states[0] if states else None,
            "states": states,
            "transitions": [
                {
                    "from_state": t.get("from_state"),
                    "to_state": t.get("to_state"),
                    "allowed_roles": list(t.get("allowed_roles", [])),
                    "requires_change_reason": bool(
                        t.get("requires_change_reason", False)
                    ),
                    "signature_gate": bool(t.get("signature_gate", False)),
                }
                for t in wf.get("transitions", [])
            ],
            "updated_at": obj.modified_at,
        }
    if propagated is not None:
        # Additive field the UI spec surfaces as a toast; the frontend reads it
        # as optional (documented tolerance in api/workflow-defaults.ts).
        data["propagated_workspace_count"] = propagated
    return data


# ---------------------------------------------------------------------------
# 1. Global workflow definitions (REQ-178)
# ---------------------------------------------------------------------------


class GlobalWorkflowDefinitionListView(APIView):
    """GET /workflow-defaults/ — list tenant global workflow definitions."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        item_type = request.query_params.get("item_type")
        preset = request.query_params.get("preset")
        rows = WorkflowFacade().list_global_definitions(
            ctx, item_type=item_type, preset=preset
        )
        return Response(
            {
                "workflow_defaults": [
                    _serialize_global_graph(
                        row,
                        tenant_id=row.tenant_id,
                        item_type=row.item_type,
                        preset=row.preset,
                    )
                    for row in rows
                ]
            }
        )


class GlobalWorkflowDefinitionDetailView(APIView):
    """GET /workflow-defaults/{item_type}/{preset}/ — one definition or empty."""

    def get(
        self, request: Request, item_type: str, preset: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        obj = WorkflowFacade().get_global_definition(
            ctx, item_type=item_type, preset=preset
        )
        return Response(
            _serialize_global_graph(
                obj, tenant_id=ctx.tenant_id, item_type=item_type, preset=preset
            )
        )


class GlobalWorkflowInitializeView(APIView):
    """POST /workflow-defaults/{item_type}/{preset}/initialize/."""

    def post(
        self, request: Request, item_type: str, preset: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            obj = WorkflowFacade().initialize_global_definition(
                ctx, item_type=item_type, preset=preset
            )
        except Exception as exc:  # noqa: BLE001 — mapped precisely
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj, tenant_id=ctx.tenant_id, item_type=item_type, preset=preset
            ),
            status=status.HTTP_201_CREATED,
        )


class GlobalWorkflowStatesView(APIView):
    """POST /workflow-defaults/{item_type}/{preset}/states/."""

    def post(
        self, request: Request, item_type: str, preset: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        name = (request.data.get("name") or "").strip()
        if not name:
            return _validation(lang, "name is required")
        try:
            obj, count = WorkflowFacade().add_global_state(
                ctx, item_type=item_type, preset=preset, name=name
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            ),
            status=status.HTTP_201_CREATED,
        )


class GlobalWorkflowStateDetailView(APIView):
    """PATCH/DELETE /workflow-defaults/{item_type}/{preset}/states/{state_id}/."""

    def patch(
        self,
        request: Request,
        item_type: str,
        preset: str,
        state_id: str,
        **kwargs: Any,
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        new_name = (request.data.get("name") or "").strip()
        if not new_name:
            return _validation(lang, "name is required")
        try:
            obj, count = WorkflowFacade().rename_global_state(
                ctx,
                item_type=item_type,
                preset=preset,
                old_name=unquote(state_id),
                new_name=new_name,
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            )
        )

    def delete(
        self,
        request: Request,
        item_type: str,
        preset: str,
        state_id: str,
        **kwargs: Any,
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            obj, count = WorkflowFacade().delete_global_state(
                ctx, item_type=item_type, preset=preset, name=unquote(state_id)
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            )
        )


class GlobalWorkflowTransitionsView(APIView):
    """POST /workflow-defaults/{item_type}/{preset}/transitions/."""

    def post(
        self, request: Request, item_type: str, preset: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        from_state = request.data.get("from_state")
        to_state = request.data.get("to_state")
        if not from_state or not to_state:
            return _validation(lang, "from_state and to_state are required")
        try:
            obj, count = WorkflowFacade().add_global_transition(
                ctx,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
                allowed_roles=request.data.get("allowed_roles"),
                requires_change_reason=bool(
                    request.data.get("requires_change_reason", False)
                ),
                signature_gate=bool(request.data.get("signature_gate", False)),
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            ),
            status=status.HTTP_201_CREATED,
        )


class GlobalWorkflowTransitionDetailView(APIView):
    """PATCH/DELETE .../transitions/{transition_id}/ ('<from>__<to>')."""

    @staticmethod
    def _split(transition_id: str, lang: str):
        decoded = unquote(transition_id)
        parts = decoded.split("__")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return _validation(lang, "transition id must be '<from>__<to>'")
        return parts[0], parts[1]

    def patch(
        self,
        request: Request,
        item_type: str,
        preset: str,
        transition_id: str,
        **kwargs: Any,
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        parsed = self._split(transition_id, lang)
        if isinstance(parsed, Response):
            return parsed
        from_state, to_state = parsed
        try:
            obj, count = WorkflowFacade().update_global_transition(
                ctx,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
                allowed_roles=request.data.get("allowed_roles"),
                requires_change_reason=request.data.get("requires_change_reason"),
                signature_gate=request.data.get("signature_gate"),
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            )
        )

    def delete(
        self,
        request: Request,
        item_type: str,
        preset: str,
        transition_id: str,
        **kwargs: Any,
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        parsed = self._split(transition_id, lang)
        if isinstance(parsed, Response):
            return parsed
        from_state, to_state = parsed
        try:
            obj, count = WorkflowFacade().delete_global_transition(
                ctx,
                item_type=item_type,
                preset=preset,
                from_state=from_state,
                to_state=to_state,
            )
        except Exception as exc:  # noqa: BLE001
            return _map_workflow_error(exc, lang)
        return Response(
            _serialize_global_graph(
                obj,
                tenant_id=ctx.tenant_id,
                item_type=item_type,
                preset=preset,
                propagated=count,
            )
        )


# ---------------------------------------------------------------------------
# 3. Global permission definition (REQ-181/186/187)
# ---------------------------------------------------------------------------


def _serialize_global_permission(obj: Any) -> dict[str, Any]:
    return {
        "tenant_id": str(obj.tenant_id),
        "permission_json": obj.permission_json,
        "enforcement_mode": obj.enforcement_mode,
        "updated_at": obj.modified_at,
    }


class GlobalPermissionDefinitionView(APIView):
    """GET/PUT/PATCH /permission-defaults/ (tenant singleton, admin-only)."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        obj = PermissionDefinitionService().get_or_create_global(ctx.tenant_id)
        return Response(_serialize_global_permission(obj))

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._write(request, partial=False)

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._write(request, partial=True)

    def _write(self, request: Request, *, partial: bool) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        # enforcement_mode is NOT editable via this endpoint — a routine matrix
        # edit must never cut over enforcement (guarded flip endpoint only).
        if "enforcement_mode" in body:
            return _validation(
                lang,
                "enforcement_mode is not editable here; use "
                "/permission-defaults/enforcement/flip/.",
                code="ENFORCEMENT_MODE_NOT_EDITABLE_HERE",
            )
        if "permission_json" not in body:
            return _validation(lang, "permission_json is required")
        matrix = body["permission_json"]
        svc = PermissionDefinitionService()
        try:
            if partial:
                obj, propagated = svc.patch_global(ctx, matrix)
            else:
                obj, propagated = svc.replace_global(ctx, matrix)
        except MatrixValidationError as exc:
            return _validation(lang, str(exc))
        data = _serialize_global_permission(obj)
        data["propagated_workspace_count"] = propagated
        return Response(data)


class EnforcementStatusView(APIView):
    """GET /permission-defaults/enforcement/ — phase + shadow readiness."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            window_days = int(
                request.query_params.get("window_days", DEFAULT_MISMATCH_WINDOW_DAYS)
            )
        except (TypeError, ValueError):
            return _validation(lang, "window_days must be an integer")
        window_days = max(1, min(window_days, 365))

        svc = PermissionDefinitionService()
        obj = svc.get_or_create_global(ctx.tenant_id)
        count, last = svc.pending_mismatch_count(
            ctx.tenant_id, window_days=window_days
        )
        ready = count == 0
        note = (
            "No unreviewed mismatches in the window — safe to flip."
            if ready
            else (
                f"{count} unreviewed mismatch(es) in the last {window_days} days. "
                f"Review via GET /permission-mismatches/ before flipping."
            )
        )
        return Response(
            {
                "enforcement_mode": obj.enforcement_mode,
                "pending_mismatch_count": count,
                "mismatch_window_days": window_days,
                "last_mismatch_at": last,
                "ready_for_authoritative": ready,
                "advisory_note": note,
            }
        )


class EnforcementFlipView(APIView):
    """POST /permission-defaults/enforcement/flip/ — guarded phase transition."""

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        target_mode = body.get("enforcement_mode")
        valid = {
            GlobalPermissionDefinition.ENFORCEMENT_SHADOW,
            GlobalPermissionDefinition.ENFORCEMENT_AUTHORITATIVE,
        }
        if target_mode not in valid:
            return _validation(
                lang, f"enforcement_mode must be one of {sorted(valid)}"
            )
        confirm = body.get("confirm_pending_mismatch_count")
        if confirm is not None:
            try:
                confirm = int(confirm)
            except (TypeError, ValueError):
                return _validation(
                    lang, "confirm_pending_mismatch_count must be an integer"
                )
        try:
            obj = PermissionDefinitionService().flip_enforcement(
                ctx,
                target_mode=target_mode,
                confirm_pending_mismatch_count=confirm,
            )
        except MismatchCountStaleError as exc:
            return Response(
                build_error_response(
                    "MISMATCH_COUNT_STALE",
                    lang,
                    message=(
                        f"Confirmed count does not match the current pending "
                        f"mismatch count ({exc.current_count}). Re-fetch and "
                        f"re-confirm."
                    ),
                    details=[
                        {
                            "field": "confirm_pending_mismatch_count",
                            "current_count": exc.current_count,
                        }
                    ],
                ),
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_global_permission(obj))


# ---------------------------------------------------------------------------
# 4. Workspace permission definition (REQ-182/183)
# ---------------------------------------------------------------------------


def _serialize_workspace_permission(obj: Any) -> dict[str, Any]:
    return {
        "workspace_id": str(obj.workspace_id),
        "permission_json": obj.permission_json,
        "is_customized": obj.is_customized,
        "source_global_id": (
            str(obj.source_global_id) if obj.source_global_id else None
        ),
        "updated_at": obj.modified_at,
    }


class WorkspacePermissionDefinitionView(APIView):
    """GET/PUT/PATCH /workspaces/{workspace_id}/permission-definition/."""

    def get(
        self, request: Request, workspace_id: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        obj = PermissionDefinitionService().get_or_create_workspace(
            ctx.tenant_id, workspace_id
        )
        return Response(_serialize_workspace_permission(obj))

    def put(
        self, request: Request, workspace_id: str, **kwargs: Any
    ) -> Response:
        return self._write(request, workspace_id, partial=False)

    def patch(
        self, request: Request, workspace_id: str, **kwargs: Any
    ) -> Response:
        return self._write(request, workspace_id, partial=True)

    def _write(
        self, request: Request, workspace_id: str, *, partial: bool
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        body = request.data if isinstance(request.data, dict) else {}
        if "permission_json" not in body:
            return _validation(lang, "permission_json is required")
        matrix = body["permission_json"]
        svc = PermissionDefinitionService()
        try:
            if partial:
                obj = svc.patch_workspace(ctx, workspace_id, matrix)
            else:
                obj = svc.replace_workspace(ctx, workspace_id, matrix)
        except MatrixValidationError as exc:
            return _validation(lang, str(exc))
        return Response(_serialize_workspace_permission(obj))


class WorkspacePermissionResetView(APIView):
    """POST /workspaces/{workspace_id}/permission-definition/reset/."""

    def post(
        self, request: Request, workspace_id: str, **kwargs: Any
    ) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            obj = PermissionDefinitionService().reset_workspace(ctx, workspace_id)
        except NoGlobalSourceError as exc:
            return Response(
                build_error_response("NO_GLOBAL_SOURCE", lang, message=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_serialize_workspace_permission(obj))


# ---------------------------------------------------------------------------
# 5. Permission-decision mismatch log (REQ-187, read-only)
# ---------------------------------------------------------------------------


def _subject_type(subject_identifier: str) -> str | None:
    if ":" in subject_identifier:
        return subject_identifier.split(":", 1)[0]
    return None


def _serialize_mismatch(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "subject_identifier": row.subject_identifier,
        "subject_type": _subject_type(row.subject_identifier),
        "capability": row.capability,
        "artifact_id": str(row.artifact_id) if row.artifact_id else None,
        "legacy_decision": row.legacy_decision,
        "new_decision": row.new_decision,
        "context_json": row.context_json,
        "created_at": row.created_at,
    }


class PermissionMismatchListView(APIView):
    """GET /permission-mismatches/ — paginated shadow-phase mismatch log."""

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        params = request.query_params

        try:
            page = int(params.get("page", 1))
            page_size = int(params.get("page_size", 25))
        except (TypeError, ValueError):
            return _validation(lang, "page and page_size must be integers")

        since = parse_datetime(params.get("since")) if params.get("since") else None
        until = parse_datetime(params.get("until")) if params.get("until") else None

        total, rows = PermissionDefinitionService().list_mismatches(
            ctx.tenant_id,
            workspace_id=params.get("workspace_id"),
            capability=params.get("capability"),
            subject_type=params.get("subject_type"),
            subject_identifier=params.get("subject_identifier"),
            since=since,
            until=until,
            page=page,
            page_size=page_size,
        )
        return Response(
            {
                "count": total,
                "next": None,
                "previous": None,
                "results": [_serialize_mismatch(r) for r in rows],
            }
        )


__all__ = [
    "GlobalWorkflowDefinitionListView",
    "GlobalWorkflowDefinitionDetailView",
    "GlobalWorkflowInitializeView",
    "GlobalWorkflowStatesView",
    "GlobalWorkflowStateDetailView",
    "GlobalWorkflowTransitionsView",
    "GlobalWorkflowTransitionDetailView",
    "GlobalPermissionDefinitionView",
    "EnforcementStatusView",
    "EnforcementFlipView",
    "WorkspacePermissionDefinitionView",
    "WorkspacePermissionResetView",
    "PermissionMismatchListView",
]
