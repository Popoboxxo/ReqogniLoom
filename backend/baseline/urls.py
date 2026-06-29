"""
ARCH-L1-006 BaselineService — URL routing for the scope-preview endpoint.

leaf_id: COMP-BL-005
req_id:  REQ-L1-049

This module exposes the URL patterns that are included by the project-level
URL configuration in :mod:`rest_api.urls`. The mount point is
``/api/v1/baselines/`` (see rest_api.urls).

Wiring required in ``backend/rest_api/urls.py``::

    from baseline.urls import urlpatterns as baseline_urlpatterns
    # ... and add either:
    #   path("baselines/", include(baseline_urlpatterns)),
    # or merge the individual patterns next to the existing baseline routes.

Because the existing ``BaselineViewSet`` already lives at
``/api/v1/baselines/`` and is registered on the DRF router, the cleanest
option is to expose the preview action at a sub-path that does not collide
with the router's ``/baselines/<pk>/`` pattern. The current path
``baselines/scope-preview/`` is therefore safe and matches the spec.
"""
from __future__ import annotations

from django.urls import path

from baseline.views import scope_preview

app_name = "baseline"

urlpatterns = [
    # REQ-L1-049: read-only preview of items a Baseline of the given scope
    # would include.
    path(
        "scope-preview/",
        scope_preview,
        name="baseline-scope-preview",
    ),
]

__all__ = ["urlpatterns"]
