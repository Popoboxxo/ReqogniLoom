"""Shared fixtures for context_graph tests.

Mirrors the real-DB seeding pattern from
``application/tests/test_search_service.py::_seed_workspace`` /
``_seed_requirement`` — a real Tenant/Workspace/AuthContext and real
artifact-backed rows, not mocks. Task 1 of the implementation plan
specifically requires an unmocked, real-transaction proof for the
subscriber-registration path; the rest of this app's tests follow the same
convention for consistency.
"""
from __future__ import annotations

import uuid


def seed_workspace(name: str):
    """Create Tenant + User + Workspace and a matching AuthContext.

    Sets :class:`persistence.tenancy.TenantContext` for the new tenant —
    callers must clear it (``TenantContext.clear_tenant()``) when done,
    same convention as every other real-DB test in this codebase.
    """
    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"{name}-{unique}", slug=f"{name}-{unique}")
    user = User.objects.create(
        username=f"{name}-{unique}-user", email=f"{name}-{unique}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-{unique}-ws")
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def seed_requirement(tenant, workspace, *, title: str, uid: str, description: str = ""):
    """Create a real Artifact-backed Requirement (no service layer — pure fixture)."""
    from persistence.models import Artifact, Requirement

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title=title,
        description=description,
        uid=uid,
    )


def seed_glossary_term(tenant, workspace, *, term: str, synonyms: list | None = None):
    from persistence.models import GlossaryTerm

    return GlossaryTerm.objects.create(
        tenant=tenant,
        workspace=workspace,
        term=term,
        definition=f"Definition of {term}",
        synonyms=synonyms or [],
    )


def seed_context_settings(tenant, workspace, *, enabled=True, enabled_generators=None):
    from context_graph.models import WorkspaceContextSettings

    return WorkspaceContextSettings.objects.create(
        tenant=tenant,
        workspace=workspace,
        enabled=enabled,
        enabled_generators=enabled_generators if enabled_generators is not None else ["glossary"],
    )
