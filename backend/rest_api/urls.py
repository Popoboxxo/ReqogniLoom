"""
ARCH-L1-002 RestApiAdapter — URL routing.

TODO(COMP-RA-001): Register DRF routers for all artifact ViewSets once
  implemented. Example:
    router = DefaultRouter()
    router.register(r'requirements', RequirementViewSet)
    router.register(r'artifacts', ArtifactViewSet)
    ...
    urlpatterns = [path('', include(router.urls))]

Reference: docs/se/L1/Gesamtsystem/L2/RestApiAdapterSystem/L2_RestApiAdapterSystem_Architecture.md
"""
from django.urls import path

urlpatterns: list = []
