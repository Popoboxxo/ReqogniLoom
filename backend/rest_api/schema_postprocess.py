"""Drf-spectacular post-processing hooks (schema-only corrections).

Like the ``extend_schema`` decorators, these describe the wire contract; they
never change runtime behaviour. A hook is used where a decorator on the shared
mixin would import DRF serializers at settings-load time and close an import
cycle (``rest_api.serializers`` -> ``DEFAULT_PAGINATION_CLASS``).
"""
from __future__ import annotations

from typing import Any

TRANSITION_REQUEST_REF = "#/components/schemas/WorkflowTransitionRequestRequest"


def patch_workflow_transition_request_bodies(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Point every ``POST …/transitions/`` at the transition request schema.

    The generic ``WorkflowTransitionsMixin`` serves GET and POST from one
    action; without a scoped schema drf-spectacular infers the ViewSet's entity
    serializer (``DocumentRequest`` etc.), which has no ``target_state`` and
    documents a body the server rejects (#2078/#2089). The component is already
    generated (the Diagram surface declares it), so referencing it is safe.
    """
    del generator, request, public  # hook signature; unused here
    for path, path_item in result.get("paths", {}).items():
        if not path.endswith("/transitions/"):
            continue
        operation = path_item.get("post")
        if not isinstance(operation, dict):
            continue
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": TRANSITION_REQUEST_REF}}
            },
        }
    return result
