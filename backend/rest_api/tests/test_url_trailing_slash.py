"""Regression tests for CR-03: POST without a trailing slash must never 500.

Root cause: Django's default ``APPEND_SLASH=True`` makes
``django.middleware.common.CommonMiddleware`` try to redirect unmatched
non-slash URLs to their slash-terminated counterpart. For unsafe methods
(POST/PUT/PATCH) this either raised a bare ``RuntimeError`` (surfaced as a
settings-leaking HTTP 500 debug page when ``DEBUG=True``) or silently
dropped the POST body via a 301 redirect (when ``DEBUG=False``).

Fix: ``APPEND_SLASH = False`` in ``reqogniloom/settings.py`` — every route in
this project is already registered with a trailing slash, so a non-slash
URL now returns a plain, immediate 404 instead of attempting a lossy
redirect, in every rigor preset and regardless of ``DEBUG``.
"""
from __future__ import annotations

from django.test import override_settings
from rest_framework.test import APIClient


def _post_without_trailing_slash():
    """POST /api/v1/requirements (no trailing slash), no auth."""
    return APIClient().post(
        "/api/v1/requirements", data={}, format="json"
    )


def test_post_without_trailing_slash_returns_404_not_500() -> None:
    """The missing-slash POST must 404 cleanly, never 500 (CR-03)."""
    response = _post_without_trailing_slash()
    assert response.status_code == 404


def test_post_without_trailing_slash_does_not_redirect() -> None:
    """No 301/308 redirect attempt (which would drop the POST body)."""
    response = _post_without_trailing_slash()
    assert response.status_code not in (301, 302, 307, 308)
    assert "Location" not in response


@override_settings(DEBUG=True, ALLOWED_HOSTS=["testserver"])
def test_post_without_trailing_slash_leaks_nothing_even_in_debug_mode() -> None:
    """Defense in depth: even with DEBUG=True, no settings/secrets leak (CR-03).

    Before the fix this path raised a raw ``RuntimeError`` from
    ``CommonMiddleware.get_full_path_with_slash``, rendered as Django's
    technical 500 page (full settings/traceback disclosure). It must now
    stay a 404 and the body must not contain any sensitive configuration.
    """
    response = _post_without_trailing_slash()
    assert response.status_code == 404

    body = response.content.decode(errors="replace")
    assert "RuntimeError" not in body
    for leaked in ("SECRET_KEY", "FIELD_ENCRYPTION_KEY", "DATABASES", "PASSWORD"):
        assert leaked not in body


def test_post_with_trailing_slash_still_reaches_the_view() -> None:
    """Sanity/no-regression: the well-formed URL is unaffected by the fix."""
    response = APIClient().post("/api/v1/requirements/", data={}, format="json")
    # Unauthenticated -> 403, but it must reach the view (not 404/500).
    assert response.status_code == 403
