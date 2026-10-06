"""Issue #1165 — architecture.decompose maps expected LLM failures to 503/504.

Before the fix a provider timeout (or any other exhausted transport failure)
was wrapped by the service in a generic ``LlmResponseError`` and the view's
bare ``except Exception`` answered HTTP 500 ``INTERNAL_SERVER_ERROR`` — a
retry-able upstream hiccup looked like a server bug.

This module pins the boundary contract for
``POST /api/v1/workspaces/<workspace_id>/architecture/decompose/``:

* a provider timeout            -> 504 ``LLM_TIMEOUT``
* a non-timeout transport error -> 503 ``LLM_UNAVAILABLE``

Both carry a localized, retry-able message (``detect_lang`` /
``build_error_response``). It also pins the second half of the issue: the
``arch_decompose_tree`` purpose must actually run under the workspace-wide
(long-running) timeout, not merely be listed in
``llm_adapter.timeouts.WORKSPACE_WIDE_PURPOSES``.
"""
from __future__ import annotations

from typing import Any

import pytest

from llm_adapter.resilient_transport import LlmTransportError

pytestmark = pytest.mark.django_db

_DECOMPOSE_URL = "/api/v1/workspaces/{workspace_id}/architecture/decompose/"

#: Mirrors ``settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS`` (default 180); the
#: test pins it explicitly below so the assertion cannot drift with deployment
#: config.
_LONG_TIMEOUT = 180.0


class _FailingProvider:
    """Provider double whose ``complete()`` fails like a real transport error.

    Records the per-call timeout it was handed so the workspace-wide timeout
    wiring can be asserted from the same seam that fails the call.
    """

    PROVIDER_NAME = "capture"

    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        prompt: str,
        *,
        purpose: str = "",
        context: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> str:
        self.calls.append({"purpose": purpose, "timeout": timeout})
        raise self._error


def _patch_provider(monkeypatch, provider: _FailingProvider) -> None:
    """Route the service's ``get_provider()`` to *provider*.

    Mirrors the seam used by
    ``application/tests/test_llm_long_running_timeout.py``.
    """
    monkeypatch.setattr(
        "llm_adapter.providers.get_provider", lambda *a, **k: provider
    )


def _timing_out_provider() -> _FailingProvider:
    return _FailingProvider(
        LlmTransportError(
            "LLM provider 'capture' call failed (timeout): TimeoutError: "
            f"operation on 'llm:capture' exceeded {_LONG_TIMEOUT:.0f}s timeout"
        )
    )


def _unavailable_provider() -> _FailingProvider:
    return _FailingProvider(
        LlmTransportError(
            "LLM provider 'capture' call failed (transient): Connection error"
        )
    )


def _post_decompose(authed_client, workspace, element, **extra):
    return authed_client.post(
        _DECOMPOSE_URL.format(workspace_id=workspace.id),
        {"element_id": str(element.id)},
        format="json",
        **extra,
    )


class TestTimeoutMapsTo504:
    def test_provider_timeout_returns_llm_timeout(
        self,
        authed_client,
        workspace,
        architecture_element,
        requirement_allocated_to,
        monkeypatch,
    ):
        requirement_allocated_to(architecture_element)
        _patch_provider(monkeypatch, _timing_out_provider())

        resp = _post_decompose(authed_client, workspace, architecture_element)

        assert resp.status_code == 504
        error = resp.json()["error"]
        assert error["code"] == "LLM_TIMEOUT"
        assert "retry later" in error["message"].lower()

    def test_timeout_message_is_localized_to_german(
        self,
        authed_client,
        workspace,
        architecture_element,
        requirement_allocated_to,
        monkeypatch,
    ):
        requirement_allocated_to(architecture_element)
        _patch_provider(monkeypatch, _timing_out_provider())

        resp = _post_decompose(
            authed_client,
            workspace,
            architecture_element,
            HTTP_ACCEPT_LANGUAGE="de-DE,de;q=0.9",
        )

        assert resp.status_code == 504
        error = resp.json()["error"]
        assert error["code"] == "LLM_TIMEOUT"
        assert "später" in error["message"]

    def test_calls_run_under_the_workspace_wide_timeout(
        self,
        authed_client,
        workspace,
        architecture_element,
        requirement_allocated_to,
        monkeypatch,
        settings,
    ):
        """The listed purpose is only effective if the service applies it."""
        settings.LLM_SYNC_TIMEOUT_SECONDS = 25
        settings.LLM_LONG_RUNNING_TIMEOUT_SECONDS = int(_LONG_TIMEOUT)
        requirement_allocated_to(architecture_element)
        provider = _timing_out_provider()
        _patch_provider(monkeypatch, provider)

        _post_decompose(authed_client, workspace, architecture_element)

        assert provider.calls, "the flow must have called the provider"
        assert provider.calls[0]["purpose"] == "arch_decompose_tree"
        assert provider.calls[0]["timeout"] == _LONG_TIMEOUT


class TestUnavailableMapsTo503:
    def test_transport_failure_returns_llm_unavailable(
        self,
        authed_client,
        workspace,
        architecture_element,
        requirement_allocated_to,
        monkeypatch,
    ):
        requirement_allocated_to(architecture_element)
        _patch_provider(monkeypatch, _unavailable_provider())

        resp = _post_decompose(authed_client, workspace, architecture_element)

        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["code"] == "LLM_UNAVAILABLE"
        assert "retry later" in error["message"].lower()
