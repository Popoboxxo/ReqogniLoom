"""Memory permission policy — the single matrix shared by REST and MCP.

RFC #1002 PR B implements the matrix from RFC §3.1 exactly once, here, so the
REST adapter (``memory.memory_rest``) and the MCP tool group
(``mcp_server.tools.memory``) cannot drift apart:

======================  ====================  ====================  ====================
action                  ``scope="user"``      ``scope="workspace"``  ``scope="artifact"``
======================  ====================  ====================  ====================
read / search           only own ``user_id``  any active workspace  any active role in the
                                              role                  artifact's workspace
write                   any authenticated     Editor+               Editor+
                        user (writes own)
delete                  Owner                 Workspace-Admin       Workspace-Admin of the
                                                                    artifact's workspace
purge / export          System-Admin          System-Admin          System-Admin
======================  ====================  ====================  ====================

Role resolution deliberately reuses
``auth_tenancy.services.authorization.AuthorizationService`` — the same service
``mcp_server.tools.memory`` already called before this PR — rather than
inventing a second role lookup. "Editor+" means any role the shared RBAC matrix
grants ``Operation.WRITE`` (editor/approver/admin); "Workspace-Admin" means the
literal ``"admin"`` workspace role; "System-Admin" means a tenant-wide
``TenantRole(admin)`` (``AuthorizationService.is_tenant_admin``), matching
``MemoryAdminService._assert_system_admin`` and
``memory_rest._is_system_admin``.

Tenant context: every role lookup reads the RLS-gated ``UserRole``/``TenantRole``
tables and every artifact lookup reads the RLS-gated ``Artifact`` table, so the
caller MUST have an active tenant context. Both production callers do — a
request has it armed by ``AuthTenancyAuthentication``, and the MCP group wraps
its calls in ``memory.backends._tenant_context`` — and
``application.memory_entry_service`` additionally re-arms it around each policy
call so a Celery-style caller cannot silently read an empty role set.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple
from uuid import UUID

from memory.models import MemoryEntry
from persistence.errors import PermissionDeniedError
from persistence.models import Artifact


class MemoryPermissionDenied(PermissionDeniedError):
    """Raised when the memory policy matrix refuses an action.

    Subclasses ``persistence.errors.PermissionDeniedError`` (re-exported as
    ``application.base.PermissionDeniedError``), so every existing
    ``except PermissionDeniedError`` in the REST/MCP layers keeps working and
    the REST error mapper still answers HTTP 403 — while callers that want the
    memory-specific type can still catch it.
    """


#: Workspace roles that grant ``Operation.WRITE`` in the shared RBAC matrix
#: (``AuthorizationService._RBAC_MATRIX``): Editor, Approver and Admin.
WRITE_ROLES = frozenset({"editor", "approver", "admin"})

#: Workspace role that may delete team-owned (workspace/artifact) memory.
ADMIN_ROLES = frozenset({"admin"})


def _owner_of(entry: Any) -> Tuple[str, Optional[UUID], Optional[UUID], Optional[UUID]]:
    """Return ``(scope, user_id, workspace_id, artifact_id)`` for *entry*.

    Accepts a ``MemoryEntry`` instance or a mapping with the same keys, so the
    same policy check serves both the ORM-resolved entry (get/forget) and a
    backend-agnostic ref/dict (list/search results).
    """
    if isinstance(entry, dict):
        return (
            entry.get("scope"),
            _as_uuid(entry.get("user_id")),
            _as_uuid(entry.get("workspace_id")),
            _as_uuid(entry.get("artifact_id")),
        )
    return (
        getattr(entry, "scope", None),
        _as_uuid(getattr(entry, "user_id", None)),
        _as_uuid(getattr(entry, "workspace_id", None)),
        _as_uuid(getattr(entry, "artifact_id", None)),
    )


def _as_uuid(value: Any) -> Optional[UUID]:
    """Return *value* as a ``UUID``, or ``None`` when it already is/absent."""
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def resolve_artifact_workspace_id(artifact_id: Any) -> Optional[UUID]:
    """Return the workspace id owning *artifact_id*, or ``None``.

    Requires an active tenant context (``Artifact`` is ``TenantScopedModel``);
    a malformed id, an unknown row or a lookup error all resolve to ``None``,
    which every caller treats as "not permitted" (fail-closed).
    """
    artifact_uuid = _as_uuid(artifact_id)
    if artifact_uuid is None:
        return None
    try:
        return (
            Artifact.objects.filter(id=artifact_uuid)
            .values_list("workspace_id", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 - a lookup failure must never grant access
        return None


def _roles_for(user_id: Any, workspace_id: Any) -> Tuple[str, ...]:
    """Active workspace roles for ``user_id`` in ``workspace_id``.

    Imported lazily (see ``application.base.ServiceBase._assert_write_permission``):
    ``auth_tenancy.services.__init__`` imports ``item_permission``, which imports
    ``application.base`` — a module-level import here would create a circular
    import at package-init time.
    """
    if user_id is None or workspace_id is None:
        return ()
    from auth_tenancy.services.authorization import AuthorizationService

    return AuthorizationService().active_roles_for(
        user_id=user_id, workspace_id=workspace_id
    )


class MemoryPolicy:
    """Stateless policy object — the one implementation of the RFC §3.1 matrix."""

    # -- read -----------------------------------------------------------

    @staticmethod
    def can_read(ctx: Any, entry: Any) -> bool:
        """Whether *ctx* may read the memory entry *entry*."""
        scope, user_id, workspace_id, artifact_id = _owner_of(entry)
        return MemoryPolicy.can_read_scope(
            ctx,
            scope=scope,
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )

    @staticmethod
    def can_read_scope(
        ctx: Any,
        *,
        scope: str,
        user_id: Any = None,
        workspace_id: Any = None,
        artifact_id: Any = None,
    ) -> bool:
        """Scope-level read check used when only owner ids are known (list/search).

        ``user``: only one's own entries. ``workspace``: any active role in the
        workspace. ``artifact``: any active role in the artifact's workspace.
        """
        if scope == MemoryEntry.SCOPE_USER:
            return user_id is not None and user_id == ctx.user_id
        if scope == MemoryEntry.SCOPE_WORKSPACE:
            return bool(_roles_for(ctx.user_id, workspace_id))
        if scope == MemoryEntry.SCOPE_ARTIFACT:
            owning_workspace_id = resolve_artifact_workspace_id(artifact_id)
            if owning_workspace_id is None:
                return False
            return bool(_roles_for(ctx.user_id, owning_workspace_id))
        return False

    # -- write ----------------------------------------------------------

    @staticmethod
    def can_write(
        ctx: Any,
        *,
        scope: str,
        workspace_id: Any = None,
        artifact_id: Any = None,
    ) -> bool:
        """Whether *ctx* may create a new entry for ``scope``.

        ``user``: any authenticated caller (the entry is written for
        ``ctx.user_id``). ``workspace``/``artifact``: Editor+ in the owning
        workspace (for ``artifact`` the workspace is derived from the artifact).
        """
        if scope == MemoryEntry.SCOPE_USER:
            return bool(ctx.user_id)
        if scope == MemoryEntry.SCOPE_WORKSPACE:
            return bool(WRITE_ROLES.intersection(_roles_for(ctx.user_id, workspace_id)))
        if scope == MemoryEntry.SCOPE_ARTIFACT:
            owning_workspace_id = resolve_artifact_workspace_id(artifact_id)
            if owning_workspace_id is None:
                return False
            return bool(
                WRITE_ROLES.intersection(_roles_for(ctx.user_id, owning_workspace_id))
            )
        return False

    # -- delete ---------------------------------------------------------

    @staticmethod
    def can_delete(ctx: Any, entry: Any) -> bool:
        """Whether *ctx* may delete the single memory entry *entry*.

        ``user``: Owner. ``workspace``/``artifact``: Workspace-Admin of the
        owning workspace (for ``artifact`` derived from the artifact).
        """
        scope, user_id, workspace_id, artifact_id = _owner_of(entry)
        return MemoryPolicy.can_delete_scope(
            ctx,
            scope=scope,
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )

    @staticmethod
    def can_delete_scope(
        ctx: Any,
        *,
        scope: str,
        user_id: Any = None,
        workspace_id: Any = None,
        artifact_id: Any = None,
    ) -> bool:
        """Scope-level delete check (single entry, or a whole scope purge)."""
        if scope == MemoryEntry.SCOPE_USER:
            return user_id is not None and user_id == ctx.user_id
        if scope == MemoryEntry.SCOPE_WORKSPACE:
            return bool(ADMIN_ROLES.intersection(_roles_for(ctx.user_id, workspace_id)))
        if scope == MemoryEntry.SCOPE_ARTIFACT:
            owning_workspace_id = resolve_artifact_workspace_id(artifact_id)
            if owning_workspace_id is None:
                return False
            return bool(
                ADMIN_ROLES.intersection(_roles_for(ctx.user_id, owning_workspace_id))
            )
        return False

    # -- purge / export (admin surface) ---------------------------------

    @staticmethod
    def can_purge(ctx: Any) -> bool:
        """Whether *ctx* may purge/export memory across scopes (System-Admin).

        Mirrors ``MemoryAdminService._assert_system_admin`` and
        ``memory_rest._is_system_admin``: a tenant-wide ``TenantRole(admin)``,
        never a merely workspace-scoped admin.
        """
        from auth_tenancy.services.authorization import AuthorizationService

        return AuthorizationService().is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )

    # -- assertion helpers (raise the dedicated exception) ---------------

    @staticmethod
    def assert_can_write(
        ctx: Any,
        *,
        scope: str,
        workspace_id: Any = None,
        artifact_id: Any = None,
    ) -> None:
        if not MemoryPolicy.can_write(
            ctx, scope=scope, workspace_id=workspace_id, artifact_id=artifact_id
        ):
            raise MemoryPermissionDenied(
                f"Permission denied: cannot write {scope!r}-scoped memory"
            )

    @staticmethod
    def assert_can_delete(ctx: Any, entry: Any) -> None:
        if not MemoryPolicy.can_delete(ctx, entry):
            raise MemoryPermissionDenied(
                f"Permission denied: cannot delete {_owner_of(entry)[0]!r}-scoped memory"
            )

    @staticmethod
    def assert_can_read(ctx: Any, entry: Any) -> None:
        if not MemoryPolicy.can_read(ctx, entry):
            raise MemoryPermissionDenied(
                f"Permission denied: cannot read {_owner_of(entry)[0]!r}-scoped memory"
            )

    @staticmethod
    def assert_can_purge(ctx: Any) -> None:
        if not MemoryPolicy.can_purge(ctx):
            raise MemoryPermissionDenied("System-Admin role required")


__all__ = [
    "MemoryPolicy",
    "MemoryPermissionDenied",
    "WRITE_ROLES",
    "ADMIN_ROLES",
    "resolve_artifact_workspace_id",
]
