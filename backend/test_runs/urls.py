"""
backend.test_runs.urls — URL routing placeholder (A.6, REQ-L1-035).

The actual GET endpoint exposed in A.6 is part of the existing
:class:`rest_api.views.TestRunViewSet` (``results`` action now accepts
both ``GET`` and ``POST``). That ViewSet is already wired into the
``/api/v1/test-runs/`` URL prefix by ``rest_api.urls.DefaultRouter`` —
see ``backend/rest_api/urls.py``.

Per the A.6 task brief, this file is owned by the test_runs scope and
is intentionally kept as a placeholder until test_runs graduates into a
fully separate Django app. At that point the ``results`` action can be
moved to a ``TestRunViewSet`` defined here and this ``urlpatterns`` list
will be the wire-in point for ``reqogniloom.urls`` / ``rest_api.urls``.

Until then, **no URL wiring change is required**: the existing route
``GET/POST /api/v1/test-runs/{id}/results/`` continues to be served by
the rest_api TestRunViewSet.
"""
from __future__ import annotations

# Intentionally empty — see module docstring.
urlpatterns: list = []

__all__ = ["urlpatterns"]
