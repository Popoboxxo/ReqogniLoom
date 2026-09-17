"""
Content-Security-Policy middleware (SEC-008, GitHub #75).

Django 4.2 ships no built-in CSP support (that only landed as
``django.middleware.csp`` in Django 5.1) and the project does not depend on
the third-party ``django-csp`` package, so this is a small, dependency-free
middleware that adds a single, restrictive ``Content-Security-Policy``
header to every response.

The policy intentionally starts conservative (``default-src 'self'``) since
this is an API backend, not a page-rendering app: no inline scripts, no
third-party origins are expected. Adjust ``CSP_POLICY`` in settings if a
future frontend integration needs additional origins (e.g. a CDN).
"""
from __future__ import annotations

from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class ContentSecurityPolicyMiddleware:
    """Add a ``Content-Security-Policy`` header to every response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.policy: str = getattr(
            settings,
            "CSP_POLICY",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'",
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.policy)
        return response
