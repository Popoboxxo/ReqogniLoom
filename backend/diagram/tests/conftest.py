"""
Shared fixtures for DiagramService tests (ARCH-L1-013).

leaf_id: COMP-DS-001 through COMP-DS-005
req_id: REQ-L1-027, REQ-L2-DS-001 through REQ-L2-DS-005

Provides tenants, workspaces, and diagram factory helpers for all
DiagramService test modules.
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Iterator

import pytest

from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext


# ---------------------------------------------------------------------------
# Tenant context helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def active_tenant(tenant: Tenant) -> Iterator[None]:
    """Activate a tenant context for the duration of the block."""
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> Iterator[None]:
    """Ensure tenant context is clean between tests."""
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Tenant / Workspace fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant_a(db: None) -> Tenant:
    return Tenant.objects.create(name="Diagram Test Tenant A", slug="ds-tenant-a")


@pytest.fixture
def tenant_b(db: None) -> Tenant:
    return Tenant.objects.create(name="Diagram Test Tenant B", slug="ds-tenant-b")


@pytest.fixture
def workspace_a(tenant_a: Tenant) -> Workspace:
    with active_tenant(tenant_a):
        return Workspace.objects.create(tenant=tenant_a, name="DS-WS-A")


@pytest.fixture
def workspace_b(tenant_b: Tenant) -> Workspace:
    with active_tenant(tenant_b):
        return Workspace.objects.create(tenant=tenant_b, name="DS-WS-B")


# ---------------------------------------------------------------------------
# Artifact helpers (for TraceabilityConnector tests)
# ---------------------------------------------------------------------------

def make_artifact(
    tenant: Tenant,
    workspace: Workspace,
    artifact_type: str = "requirement",
) -> Artifact:
    """Create an Artifact directly (bypasses manager — for test setup only)."""
    return Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type=artifact_type,
    )


# ---------------------------------------------------------------------------
# Valid diagram payloads for each combination
# ---------------------------------------------------------------------------

VALID_MERMAID_BLOCK = "block-beta\n  A[Block A]\n  B[Block B]"
VALID_MERMAID_FLOW = "flowchart TD\n  A --> B"
VALID_MERMAID_CONTEXT = "flowchart LR\n  User --> System"

VALID_PLANTUML_BLOCK = "@startuml\nrectangle A\n@enduml"
VALID_PLANTUML_FLOW = "@startuml\nA --> B\n@enduml"
VALID_PLANTUML_CONTEXT = "@startuml\nrectangle System\n@enduml"

VALID_JSON_BLOCK = '{"nodes": [{"id": "A", "label": "Block A"}]}'
VALID_JSON_FLOW = '{"nodes": [{"id": "A"}], "edges": [{"from": "A", "to": "B"}]}'
VALID_JSON_CONTEXT = '{"nodes": [{"id": "System"}]}'

# ---------------------------------------------------------------------------
# Valid canvas stroke data — COMP-DS-006, REQ-L2-DS-006
# ---------------------------------------------------------------------------

VALID_CANVAS_STROKES = {
    "strokes": [
        {
            "id": "stroke-1",
            "type": "pen",
            "points": [{"x": 10, "y": 20}, {"x": 30, "y": 40}, {"x": 50, "y": 60}],
            "color": "#000000",
            "width": 2,
        },
        {
            "id": "rect-1",
            "type": "rect",
            "x": 100,
            "y": 100,
            "width": 200,
            "height": 150,
            "color": "#333333",
            "fill": "#eeeeee",
        },
        {
            "id": "text-1",
            "type": "text",
            "x": 150,
            "y": 175,
            "content": "Hello Canvas",
            "font_size": 16,
        },
    ],
    "width": 800,
    "height": 600,
}

VALID_CANVAS_CONNECTORS = {
    "strokes": [
        {
            "id": "shape-a",
            "type": "rect",
            "x": 10,
            "y": 10,
            "width": 100,
            "height": 50,
        },
        {
            "id": "shape-b",
            "type": "rect",
            "x": 200,
            "y": 10,
            "width": 100,
            "height": 50,
        },
        {
            "id": "conn-1",
            "type": "connector",
            "source_id": "shape-a",
            "target_id": "shape-b",
            "x1": 110,
            "y1": 35,
            "x2": 200,
            "y2": 35,
        },
    ],
    "width": 800,
    "height": 600,
}
