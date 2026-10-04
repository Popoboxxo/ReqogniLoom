"""Tenant-scoped Django-admin plumbing (SEC-04, ADR-011).

The Django admin is a maintenance surface. Historically it was a *cross-tenant*
one: every ``TenantScopedModel`` admin overrode ``get_queryset`` with
``unscoped()`` so that a staff user of tenant A could list and edit tenant B's
rows. ADR-011 makes the tenant the non-negotiable isolation shell, so the admin
must honour it as well.

:class:`TenantScopedAdminMixin` is the single enforcement point. It derives the
operator's tenant from ``request.user.tenant_id`` — never from a request body,
URL kwarg or query parameter — and narrows both the list/change queryset and the
per-object permission checks to it. A user without a tenant sees nothing
(fail-closed); there is deliberately no implicit "show everything" fallback.

Usage::

    class MyAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
        ...          # default: matches ``tenant_id``

    class WebhookAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
        tenant_lookup = None
        workspace_lookup = "workspace_id"   # no tenant column on the model

The mixin is intentionally scoped to the admin surface: REST/MCP correctness is
owned by ``RbacPermission``/``AuthTenancyAuthentication`` (ADR-011 §3), not by
this module.
"""
from __future__ import annotations

from typing import Any, Optional

from persistence.models import Workspace


class TenantScopedAdminMixin:
    """Narrow a ``ModelAdmin`` to the requesting operator's tenant.

    Class attributes:
        tenant_lookup: Model field matched against the operator's tenant id.
            Defaults to ``"tenant_id"`` (the ``TenantScopedModel`` FK). Use
            ``"id"`` for the root ``Tenant`` model.
        workspace_lookup: Fallback for models that carry no tenant column but a
            field path to a ``Workspace`` FK (``"workspace_id"`` or
            ``"subscription__workspace_id"``). Only used when ``tenant_lookup``
            is ``None``.
    """

    tenant_lookup: Optional[str] = "tenant_id"
    workspace_lookup: Optional[str] = None

    # -- queryset ---------------------------------------------------------

    def _base_queryset(self) -> Any:
        """Return the unfiltered manager queryset for the model.

        ``unscoped()`` is used where available so the mixin's own tenant filter
        is the one that applies; the ``TenantManager`` default would raise
        ``TenantContextNotSetError`` outside a request context.
        """
        model = self.model
        if hasattr(model, "unscoped"):
            return model.unscoped.all()
        return model._default_manager.all()

    def tenant_scoped_queryset(self, request: Any) -> Any:
        """Return ``self.model``'s rows visible to the requesting operator.

        Fail-closed: an operator without a tenant sees no rows. A resolved
        tenant is matched either directly (``tenant_lookup``) or through the
        workspaces that belong to it (``workspace_lookup``).
        """
        base = self._base_queryset()
        tenant_id = self._operator_tenant_id(request)
        if tenant_id is None:
            return base.none()
        if self.tenant_lookup:
            return base.filter(**{self.tenant_lookup: tenant_id})
        if self.workspace_lookup:
            workspace_ids = Workspace.unscoped.filter(
                tenant_id=tenant_id
            ).values("id")
            return base.filter(**{f"{self.workspace_lookup}__in": workspace_ids})
        return base.none()

    def get_queryset(self, request: Any) -> Any:
        """Admin list/change queryset, narrowed to the operator's tenant."""
        return self.tenant_scoped_queryset(request)

    @staticmethod
    def _operator_tenant_id(request: Any):
        user = getattr(request, "user", None)
        return getattr(user, "tenant_id", None)

    # -- per-object permission checks ------------------------------------

    def _is_tenant_row(self, request: Any, obj: Any) -> bool:
        """Return whether *obj* is inside the operator's tenant (fail-closed)."""
        if obj is None:
            return True
        return self.tenant_scoped_queryset(request).filter(pk=obj.pk).exists()

    def has_view_permission(self, request: Any, obj: Any = None) -> bool:
        return super().has_view_permission(request, obj) and self._is_tenant_row(
            request, obj
        )

    def has_change_permission(self, request: Any, obj: Any = None) -> bool:
        return super().has_change_permission(request, obj) and self._is_tenant_row(
            request, obj
        )

    def has_delete_permission(self, request: Any, obj: Any = None) -> bool:
        return super().has_delete_permission(request, obj) and self._is_tenant_row(
            request, obj
        )


__all__ = ["TenantScopedAdminMixin"]
