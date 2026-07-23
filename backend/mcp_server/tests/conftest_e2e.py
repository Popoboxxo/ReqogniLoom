"""
End-to-end test fixtures for the MCP server (covers all 40+ MCP tools).

This conftest builds a fully wired test environment:

* An isolated ``Tenant`` with a unique name.
* Three ``User`` rows (admin / member / viewer) belonging to the tenant.
* A single ``Workspace`` in that tenant, in the ``extended`` preset tier
  (so every feature flag is enabled and no MCP tool is blocked by the
  preset filter).
* A ``UserRole`` row per (user, workspace) granting the corresponding
  RBAC role.
* An ``ApiKey`` row per user, returning the raw plaintext key (the
  one-time value the test client uses in the ``X-API-Key`` header).
* A pre-wired ``django.test.Client`` per role, plus an invalid-key
  client for negative tests.

Important — TenantContext activation is intentionally NOT autouse-set
here. The tool_registry fix in
``mcp_server.tool_registry.dispatch_request`` activates the context
internally after a successful API-key validation. Setting it from the
test side would mask a regression of that fix.

We DO use ``set_request_tenant`` inside the fixture bodies to build the
seed data (Workspace, UserRole, ApiKey are tenant-scoped and require an
active context for ``objects.create``). This is fixture setup, not a
test-time workaround — we explicitly clear it before yielding the
fixture to the test, so no context leaks into the test itself.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from django.test import Client

from auth_tenancy.models import (
    ApiKey,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
    UserRole,
)
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from presets.models import WorkspacePresetConfig


# ---------------------------------------------------------------------------
# Autouse: reset module-level singletons between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _e2e_reset_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset ``mcp_server.views`` singletons between tests.

    The view module keeps a lazy-initialised ``ToolRegistry`` and
    ``ProtocolHandler`` for the lifetime of the process. Without this
    reset, a cached registry from a prior test would leak its
    ``PresetCache`` (and any DB-backed singletons) into the next test.
    """
    monkeypatch.setattr("mcp_server.views._tool_registry", None)
    monkeypatch.setattr("mcp_server.views._protocol_handler", None)
    yield
    # monkeypatch auto-restores the original values; explicit reset for
    # robustness in case other fixtures touched the module globals.
    monkeypatch.setattr("mcp_server.views._tool_registry", None)
    monkeypatch.setattr("mcp_server.views._protocol_handler", None)


@pytest.fixture(autouse=True)
def _e2e_clear_preset_cache() -> Iterator[None]:
    """Reset the ``PresetCache`` singleton's internal dict.

    Defensive: if the module exposes a class-level ``_preset_cache``
    singleton, clear its internal ``_cache`` mapping so cached
    feature-flag decisions from a previous test do not leak. If the
    attribute does not exist (the current code uses per-instance
    caches), the fixture is a no-op.
    """
    from mcp_server import tool_registry

    def _clear_once() -> None:
        cache = getattr(tool_registry, "_preset_cache", None)
        if cache is not None and hasattr(cache, "_cache"):
            cache._cache = {}

    _clear_once()
    yield
    _clear_once()


# ---------------------------------------------------------------------------
# Preset fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_preset() -> Dict[str, Any]:
    """A preset descriptor enabling all features.

    The preset config is held in memory (``presets.registry``); the DB
    side is a ``WorkspacePresetConfig`` row pointing at the ``extended``
    tier, which is the built-in tier with every feature flag set to
    ``True``. We return the JSONField value that goes on
    ``Workspace.preset``; the ``WorkspacePresetConfig`` row is created
    by :func:`e2e_workspace`.

    Returns:
        Dict with ``name="e2e_preset"`` and a synthetic ``features``
        mapping set to all ``True`` for documentation purposes; the
        runtime feature decision is read from ``WorkspacePresetConfig``
        via ``get_preset()``.
    """
    return {
        "name": "e2e_preset",
        "active_tier": "extended",
        "features": {key: True for key in (
            "baselines",
            "global_baselines",
            "approval_workflows",
            "custom_workflows",
            "change_reason_mandatory",
        )},
    }


# ---------------------------------------------------------------------------
# Tenant fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_tenant(db: None) -> Tenant:
    """A single test tenant with a UUID-suffixed name for isolation."""
    suffix = uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"E2E Tenant {suffix}",
        slug=f"e2e-tenant-{suffix}",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# User fixtures (admin / member / viewer)
# ---------------------------------------------------------------------------


def _make_user(tenant: Tenant, role_label: str) -> User:
    """Create a single test user in *tenant* with a unique username."""
    suffix = uuid4().hex[:8]
    return User.objects.create(
        username=f"e2e_{role_label}_user_{suffix}",
        email=f"e2e_{role_label}_{suffix}@e2e.test",
        tenant=tenant,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )


@pytest.fixture
def e2e_user_admin(e2e_tenant: Tenant) -> User:
    """An active admin user belonging to the E2E tenant."""
    return _make_user(e2e_tenant, "admin")


@pytest.fixture
def e2e_user_member(e2e_tenant: Tenant) -> User:
    """An active editor/member user belonging to the E2E tenant."""
    return _make_user(e2e_tenant, "member")


@pytest.fixture
def e2e_user_viewer(e2e_tenant: Tenant) -> User:
    """An active viewer user belonging to the E2E tenant."""
    return _make_user(e2e_tenant, "viewer")


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_workspace(
    db: None,
    e2e_tenant: Tenant,
    e2e_preset: Dict[str, Any],
) -> Workspace:
    """A workspace in *e2e_tenant* with the extended preset tier.

    The ``WorkspacePresetConfig`` row is created via the unscoped manager
    so it survives the absence of a tenant context during seed
    construction. The workspace itself is created inside an active
    tenant context (set via ``set_request_tenant``) because
    ``Workspace`` is tenant-scoped.

    The *e2e_preset* fixture supplies the JSONField value for
    ``Workspace.preset``. The runtime tier decision is read from the
    ``WorkspacePresetConfig`` row below — the JSONField is kept in sync
    for forward-compat (e.g. seed scripts that derive the initial tier
    from the JSONField before ``WorkspacePresetConfig`` is materialised).
    """
    set_request_tenant(e2e_tenant.id)
    try:
        ws = Workspace.objects.create(
            tenant=e2e_tenant,
            name="E2E Test Workspace",
            is_active=True,
            preset=e2e_preset,
        )
    finally:
        clear_request_tenant()

    # WorkspacePresetConfig must also live in the tenant — use unscoped
    # to avoid re-entering the (now-cleared) tenant context just for
    # this row. The active tier is always "extended" so every feature
    # flag is enabled and no MCP tool is blocked by the preset filter.
    WorkspacePresetConfig.unscoped.create(
        tenant=e2e_tenant,
        workspace=ws,
        active_tier="extended",
        terminology_profile="dev_mode",
        downgrade_policy="allow",
    )
    return ws


# ---------------------------------------------------------------------------
# UserRole fixtures
# ---------------------------------------------------------------------------


def _make_user_role(
    user: User, workspace: Workspace, role: str
) -> UserRole:
    """Create a single active UserRole row.

    Uses the ``unscoped`` manager so the create call does not depend on
    an active tenant context — the tenant context is cleared by the
    workspace fixture before the test runs.
    """
    return UserRole.unscoped.create(
        tenant=workspace.tenant,
        user=user,
        workspace=workspace,
        role=role,
        suspended_at=None,
    )


@pytest.fixture
def e2e_userrole_admin(
    e2e_user_admin: User, e2e_workspace: Workspace
) -> UserRole:
    """Admin role for the admin user in the E2E workspace."""
    return _make_user_role(e2e_user_admin, e2e_workspace, ROLE_ADMIN)


@pytest.fixture
def e2e_userrole_member(
    e2e_user_member: User, e2e_workspace: Workspace
) -> UserRole:
    """Editor role for the member user in the E2E workspace."""
    return _make_user_role(e2e_user_member, e2e_workspace, ROLE_EDITOR)


@pytest.fixture
def e2e_userrole_viewer(
    e2e_user_viewer: User, e2e_workspace: Workspace
) -> UserRole:
    """Viewer role for the viewer user in the E2E workspace."""
    return _make_user_role(e2e_user_viewer, e2e_workspace, ROLE_VIEWER)


# ---------------------------------------------------------------------------
# API key fixtures
# ---------------------------------------------------------------------------


def _make_api_key(user: User, tenant: Tenant) -> str:
    """Create an active ApiKey row for *user* and return its plaintext.

    The plaintext is generated via the project's canonical
    ``generate_api_key_plaintext()`` (format ``reqlo_<40 chars>``). The
    ApiKey row is created with the ``unscoped`` manager because
    authentication-time lookups use it.
    """
    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=f"e2e-key-{user.username}",
        key_hash=hash_api_key(plaintext),
        revoked_at=None,
    )
    return plaintext


@pytest.fixture
def e2e_api_key_admin(e2e_user_admin: User, e2e_tenant: Tenant) -> str:
    """Raw plaintext API key for the admin user."""
    return _make_api_key(e2e_user_admin, e2e_tenant)


@pytest.fixture
def e2e_api_key_member(e2e_user_member: User, e2e_tenant: Tenant) -> str:
    """Raw plaintext API key for the member user."""
    return _make_api_key(e2e_user_member, e2e_tenant)


@pytest.fixture
def e2e_api_key_viewer(e2e_user_viewer: User, e2e_tenant: Tenant) -> str:
    """Raw plaintext API key for the viewer user."""
    return _make_api_key(e2e_user_viewer, e2e_tenant)


@pytest.fixture
def e2e_api_key_invalid() -> str:
    """A plain string for negative-auth tests (no DB row exists)."""
    return "rf_e2e_invalid_xxx"


# ---------------------------------------------------------------------------
# Pre-wired Django test clients
# ---------------------------------------------------------------------------


def _make_client(api_key: str) -> Client:
    """Return a fresh ``django.test.Client`` with the API key pre-set.

    The test client carries no per-request state, but we re-instantiate
    per fixture to keep fixtures independent.
    """
    client = Client()
    client.defaults = dict(client.defaults or {})
    client.defaults["HTTP_X_API_KEY"] = api_key
    return client


@pytest.fixture
def admin_client(e2e_api_key_admin: str) -> Client:
    """``Client`` authenticated as the admin user."""
    return _make_client(e2e_api_key_admin)


@pytest.fixture
def member_client(e2e_api_key_member: str) -> Client:
    """``Client`` authenticated as the member/editor user."""
    return _make_client(e2e_api_key_member)


@pytest.fixture
def viewer_client(e2e_api_key_viewer: str) -> Client:
    """``Client`` authenticated as the viewer user."""
    return _make_client(e2e_api_key_viewer)


@pytest.fixture
def invalid_client(e2e_api_key_invalid: str) -> Client:
    """``Client`` carrying a syntactically-valid but unknown API key."""
    return _make_client(e2e_api_key_invalid)


# ---------------------------------------------------------------------------
# Optional service-mock fixtures (not autouse; tests opt in)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the LLM availability check so LLM-gated tools are reachable.

    ``mcp_server.tools.requirements._check_llm_configured`` reads env
    vars at call time. We patch it directly to keep the fixture
    hermetic — no environment mutation, no risk of leaking into
    sibling tests.
    """
    monkeypatch.setattr(
        "mcp_server.tools.requirements._check_llm_configured",
        lambda: True,
    )


@pytest.fixture
def mock_backup_filesystem(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mock filesystem-touching backup services.

    ``BackupService.create_backup`` and ``AdminRestoreService.restore``
    reach into the filesystem and call ``dumpdata``/``loaddata``. Both
    are stubbed with ``MagicMock`` so tests do not require a writable
    media directory.
    """
    monkeypatch.setattr(
        "admin_ops.services.BackupService.create_backup",
        MagicMock(return_value={"id": "mocked", "file_path": str(tmp_path)}),
    )
    monkeypatch.setattr(
        "admin_ops.services.AdminRestoreService.restore",
        MagicMock(return_value={"restored": True}),
    )


# ---------------------------------------------------------------------------
# Convenience: env-tweak fixture for LLM-dependent tests
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set ``LLM_PROVIDER`` so the env-based LLM check passes.

    Prefer :func:`mock_llm_configured` for unit-style tests; this
    fixture is for tests that exercise the real env-reading code path.
    """
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
