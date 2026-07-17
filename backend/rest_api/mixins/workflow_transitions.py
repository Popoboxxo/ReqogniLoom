"""WorkflowTransitionsMixin — shared workflow REST actions (REQ-165 / REQ-167).

Adds the two workflow endpoints that every workflow-backed entity ViewSet needs:

    GET  /api/v1/<entity>/{pk}/transitions/       → current state + allowed moves
    POST /api/v1/<entity>/{pk}/transitions/       → perform a gated transition
    GET  /api/v1/<entity>/{pk}/workflow-history/   → append-only audit trail

The WorkflowEngine (via ``WorkflowFacade``) is the single authority for the
transition: role gates, change_reason and signature gates are enforced there and
their errors propagate unchanged to the HTTP layer. This mixin only translates
between HTTP and the facade — no business logic (REQ-L3-RA001-004).

Extracted from the original inline ``RequirementViewSet`` actions so all entity
types (Requirement, StakeholderNeed, Adr, Risk, Issue, ChangeRequest, TestCase)
share one implementation and one response contract.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from application.preset_policy_service import get_preset_policy_service
from application.services import (
    NotFoundError,
    PermissionDeniedError,
    WorkflowFacade,
)
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


class WorkflowTransitionsMixin:
    """Adds GET/POST ``transitions/`` and GET ``workflow-history/`` actions.

    Subclasses must declare::

        workflow_item_type: str   # e.g. "Adr", "Risk", "Requirement", ...

    and implement::

        _resolve_workflow_target(self, pk, ctx) -> tuple[UUID, UUID]
            # returns (item_id, workspace_id); raises NotFoundError /
            # PermissionDeniedError on not-found or permission denied, and
            # ValueError on a malformed pk.

    Subclasses may override ``_serialize_after_transition`` to embed the refreshed
    entity in the transition POST response.
    """

    workflow_item_type: str = ""

    def _resolve_workflow_target(self, pk: str, ctx: Any) -> tuple[UUID, UUID]:
        """Return ``(item_id, workspace_id)`` for the entity identified by *pk*.

        Must raise ``NotFoundError`` / ``PermissionDeniedError`` when the entity
        is missing or inaccessible, and ``ValueError`` on a malformed pk.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _resolve_workflow_target"
        )

    def _serialize_after_transition(self, item_id: UUID, ctx: Any) -> dict | None:
        """Override to embed refreshed entity data in the transition POST response.

        Returning ``None`` (the default) yields the bare state envelope
        ``{id, previous_state, new_state}``.
        """
        return None

    @action(detail=True, methods=["get", "post"], url_path="transitions")
    def transitions(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """Workflow transitions for a workflow-backed entity (REQ-143).

        GET  → ``{current_state, states, allowed_transitions[]}`` — the moves
               allowed from the current state. Drives a transition-aware UI.

        POST → body ``{target_state, change_reason?, credential?}``; performs the
               transition through the WorkflowEngine (role / change_reason /
               signature gates enforced) and returns the new state envelope,
               optionally with the refreshed entity embedded.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item_id, workspace_id = self._resolve_workflow_target(pk, ctx)
        except NotFoundError as exc:
            return self._error(exc, lang)
        except PermissionDeniedError as exc:
            return self._error(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        facade = WorkflowFacade()

        if request.method.upper() == "GET":
            avail = facade.get_available_transitions(
                item_id=item_id,
                ctx=ctx,
                item_type=self.workflow_item_type,
                workspace_id=workspace_id,
            )
            # REQ-169: surface the EFFECTIVE change_reason requirement. When the
            # workspace preset mandates a change_reason (Extended rigor), the
            # facade's global gate (WorkflowFacade._check_change_reason) rejects
            # every empty-reason transition regardless of the per-transition flag.
            # If the GET response only reported the per-transition flag, the UI
            # would hide the textarea for those transitions and POST an empty
            # reason that the facade then blocks. Report the OR of both so the UI
            # always collects a reason when it will actually be required.
            preset_requires = get_preset_policy_service().is_change_reason_required(
                str(workspace_id)
            )
            return Response(
                {
                    "current_state": avail.current_state,
                    "states": list(avail.states),
                    "allowed_transitions": [
                        {
                            "target_state": t.to_state,
                            "requires_change_reason": (
                                t.requires_change_reason or preset_requires
                            ),
                            "signature_gate": t.signature_gate,
                        }
                        for t in avail.transitions
                    ],
                }
            )

        # POST → perform the transition.
        target_state = request.data.get("target_state")
        if not target_state:
            return Response(
                build_error_response(
                    "VALIDATION_ERROR", lang, message="target_state is required"
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        change_reason = request.data.get("change_reason", "") or ""
        credential = request.data.get("credential", "") or ""
        try:
            result = facade.transition(
                item_id=item_id,
                target_state=target_state,
                change_reason=change_reason,
                ctx=ctx,
                credential=credential,
                item_type=self.workflow_item_type,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return self._error(exc, lang)

        body: dict[str, Any] = {
            "id": pk,
            "previous_state": result.previous_state,
            "new_state": result.new_state,
        }
        embedded = self._serialize_after_transition(item_id, ctx)
        if embedded is not None:
            body.update(embedded)
        return Response(body)

    @action(detail=True, methods=["get"], url_path="workflow-history")
    def workflow_history(self, request: Request, pk: str, **kwargs: Any) -> Response:
        """GET ``workflow-history/`` — transition audit trail (REQ-144).

        Returns the append-only WorkflowHistoryEntry list for this entity,
        oldest first: actor, from/to state, change_reason, timestamp, and whether
        the transition was signature-sealed. The seal value itself is never
        exposed — only a ``sealed`` boolean.
        """
        lang = detect_lang(request)
        try:
            ctx = get_auth_context(request)
            item_id, workspace_id = self._resolve_workflow_target(pk, ctx)
        except NotFoundError as exc:
            return self._error(exc, lang)
        except PermissionDeniedError as exc:
            return self._error(exc, lang)
        except ValueError:
            return Response(
                build_error_response("NOT_FOUND", lang),
                status=status.HTTP_404_NOT_FOUND,
            )

        facade = WorkflowFacade()
        entries = facade.get_history(
            item_id=item_id,
            ctx=ctx,
            item_type=self.workflow_item_type,
            workspace_id=workspace_id,
        )
        return Response(
            [
                {
                    "id": str(entry.id),
                    "from_state": entry.from_state,
                    "to_state": entry.to_state,
                    "actor": entry.transitioned_by,
                    "change_reason": entry.change_reason,
                    "transitioned_at": entry.transitioned_at.isoformat(),
                    "sealed": bool(entry.signature_seal),
                }
                for entry in entries
            ]
        )

    @staticmethod
    def _error(exc: Exception, lang: str) -> Response:
        """Translate a service exception into the standard error Response.

        Delegates to ``rest_api.views._service_error_response`` (single source of
        truth for the exception→HTTP mapping). Imported lazily to avoid a circular
        import: ``rest_api.views`` imports this mixin at module load time.
        """
        from rest_api.views import _service_error_response

        return _service_error_response(exc, lang)
