"""#2086: the outdate agent guard must answer 403, not an internal 500."""
from __future__ import annotations

import pytest

from rest_api.views_common import _service_error_response
from workflow.services import WorkflowTransitionError
from workflow.transition_validator import EC_AGENT_SELF_CONFIRM


@pytest.mark.parametrize("lang", ["en", "de"])
def test_agent_self_confirm_maps_to_403(lang: str) -> None:
    exc = WorkflowTransitionError(
        EC_AGENT_SELF_CONFIRM,
        "An AI agent may not discard a proposal.",
    )

    response = _service_error_response(exc, lang)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"
