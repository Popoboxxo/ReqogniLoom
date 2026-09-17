"""
Middleware for ReqogniLoom request handling.

SA-46: Request ID correlation middleware for structured logging and tracing.
M4: RequestIdFilter for injecting request_id into every log record.
"""
import contextvars
import logging
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

# Thread-local context variable for the current request ID.
# Available to logging formatters and other request-scoped code via
# get_request_id() or context["request_id"].get()
# N4: Type annotation must allow None (default=None); fixed from ContextVar[str] to ContextVar[str | None]
_request_id_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_request_id() -> str | None:
    """Return the current request ID from the context, or None if not set."""
    return _request_id_context.get()


class RequestIdFilter(logging.Filter):
    """
    M4: Logging filter that injects the current request ID into every log record.

    Allows structured logging formatters to include %(request_id)s in their
    output, connecting logs across the entire request lifecycle for distributed tracing.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject request_id into the LogRecord."""
        record.request_id = get_request_id() or "N/A"
        return True


class RequestIdMiddleware:
    """
    Injects a unique request ID (UUID) into every HTTP request for correlation.

    - Generates a UUID per request if not present in X-Request-ID header.
    - Stores it in the ContextVar so logging formatters can access it.
    - Adds it to the response X-Request-ID header for client round-tripping.

    Usage in logging formatters:
        from reqogniloom.middleware import get_request_id
        request_id = get_request_id() or "N/A"
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Check if the request already has an X-Request-ID (e.g., from a proxy).
        # M5: Validate it as a UUID; if invalid or missing, generate a new one.
        # This prevents client-supplied garbage from polluting logs/traces.
        client_request_id = request.META.get("HTTP_X_REQUEST_ID", "").strip()
        if client_request_id:
            try:
                uuid.UUID(client_request_id)  # Validate format
                request_id = client_request_id
            except (ValueError, TypeError):
                # Invalid UUID format — discard and generate a new one.
                request_id = str(uuid.uuid4())
        else:
            request_id = str(uuid.uuid4())

        # Store in context so logging and other code can access it.
        # N4: Use reset() in finally to prevent context pollution on thread reuse (WSGI).
        token = _request_id_context.set(request_id)

        # Attach to the request object for convenience.
        request.request_id = request_id

        try:
            # Get the response from the view.
            response = self.get_response(request)

            # Add the request ID to the response header for the client.
            response["X-Request-ID"] = request_id

            return response
        finally:
            # N4: Reset context to prevent stale request_id from leaking to the next request
            # on thread-reused WSGI workers.
            _request_id_context.reset(token)
