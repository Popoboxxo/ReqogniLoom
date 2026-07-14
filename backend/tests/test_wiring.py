"""
Wiring tests: verify system-level integration points are correctly registered.

[REQ-075] The test suite previously validated only function-level behaviour;
it did not verify that components are wired together correctly. These tests
close that gap by checking:

  1. The outbox consumer is registered in the Celery Beat schedule.
  2. The async LLM capability task is discoverable by the worker.
  3. MCP HTTP and messages URL endpoints exist in the URL configuration.
  4. The SSE GET handler is declared async (required for ASGI — a sync handler
     causes a TypeError at runtime).

No database access required; these tests run against the Django settings and
the Celery app registry alone.
"""
from __future__ import annotations

import inspect

import pytest


def test_outbox_poll_task_in_beat_schedule():
    """[REQ-075] Beat schedule contains the outbox dispatch task.

    Before this fix (DEEP_SYSTEM_ANALYSIS.md BE-1) the Beat schedule was
    missing, so domain events accumulated in the outbox forever.
    """
    from django.conf import settings

    beat_schedule = settings.CELERY_BEAT_SCHEDULE
    task_names = [entry["task"] for entry in beat_schedule.values()]
    assert any(
        "dispatch" in t or "outbox" in t or "poll" in t for t in task_names
    ), f"No outbox dispatch task found in CELERY_BEAT_SCHEDULE: {task_names}"


def test_outbox_task_targets_correct_module():
    """[REQ-075] Beat schedule task name points to application.dispatch_outbox_events."""
    from django.conf import settings

    beat_schedule = settings.CELERY_BEAT_SCHEDULE
    task_names = [entry["task"] for entry in beat_schedule.values()]
    assert "application.dispatch_outbox_events" in task_names, (
        f"Expected 'application.dispatch_outbox_events' in Beat schedule, "
        f"got: {task_names}"
    )


def test_llm_capability_task_registered():
    """[REQ-075] LLM run_capability is importable as a Celery shared task.

    Before the fix (DEEP_SYSTEM_ANALYSIS.md BE-3) the dispatcher created a
    throw-away Celery app per call that was never wired to the worker, so
    every async dispatch stayed PENDING forever. The fix registers
    run_capability as a @shared_task so the real worker picks it up.
    """
    from celery import Task

    from llm_adapter.tasks import run_capability

    assert isinstance(run_capability, Task), (
        "run_capability must be a Celery Task instance (decorated with @shared_task)"
    )


def test_llm_task_has_correct_name():
    """[REQ-075] run_capability task uses the expected registered task name.

    The name 'llm_adapter.run_capability' must match the route configured in
    reqflow/celery.py task_routes so the message is delivered to the 'llm'
    queue and not silently dropped on the default queue.
    """
    from llm_adapter.tasks import run_capability

    assert run_capability.name == "llm_adapter.run_capability", (
        f"Task name mismatch: expected 'llm_adapter.run_capability', "
        f"got {run_capability.name!r}. "
        "The name must match the route in reqflow/celery.py task_routes."
    )


def test_mcp_http_endpoint_exists():
    """[REQ-075] MCP HTTP endpoint is registered in URL configuration."""
    from django.urls import reverse

    url = reverse("mcp-http")
    assert url.endswith("/"), f"Expected a path ending in '/', got {url!r}"
    assert "mcp" in url, f"Expected 'mcp' in URL path, got {url!r}"


def test_mcp_messages_endpoint_exists():
    """[REQ-075] MCP messages endpoint (SSE session relay) is in URL configuration.

    This endpoint receives JSON-RPC POST bodies for an active SSE session and
    forwards responses over the SSE stream via Redis pub/sub.
    """
    from django.urls import reverse

    url = reverse("mcp-messages")
    assert "messages" in url, f"Expected 'messages' in URL path, got {url!r}"


def test_mcp_sse_endpoint_exists():
    """[REQ-075] MCP SSE endpoint is registered in URL configuration."""
    from django.urls import reverse

    url = reverse("mcp-sse")
    assert "sse" in url, f"Expected 'sse' in URL path, got {url!r}"


def test_sse_view_is_async():
    """[REQ-075] SSE GET handler is a coroutine function.

    A synchronous GET handler on McpSseTransportView raises TypeError at
    runtime when served under ASGI (REQ-044 / DEEP_SYSTEM_ANALYSIS.md BE-20).
    """
    from mcp_server.views import McpSseTransportView

    view = McpSseTransportView()
    assert inspect.iscoroutinefunction(view.get), (
        "McpSseTransportView.get must be 'async def'. "
        "A sync handler causes TypeError under ASGI (Django channels / uvicorn)."
    )


def test_sse_options_handler_is_async():
    """[REQ-075] SSE OPTIONS handler is also async (CORS preflight must be async)."""
    from mcp_server.views import McpSseTransportView

    view = McpSseTransportView()
    assert inspect.iscoroutinefunction(view.options), (
        "McpSseTransportView.options must be 'async def' for ASGI compatibility."
    )
