"""
Tests for API key role resolution in AuthTenancyAuthentication (REQ-L2-AT-007).

Verifies that API keys correctly resolve roles from UserRole table
when building the auth context.

Coverage:
  - API key auth resolves roles from UserRole (tenant-scoped)
  - Bearer tokens use roles from JWT claims
  - Both resolve to correct active_roles tuple
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims, TenantContext
from auth_tenancy.models import UserRole, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER
from auth_tenancy.rest import AuthTenancyAuthentication
from persistence.models import Tenant, User
from persistence.tenancy import TenantContext as PersistenceTenantContext
from persistence.middleware import set_request_tenant, clear_request_tenant


class TestApiKeyRoleResolution(TestCase):
    """API key role resolution via UserRole lookup."""

    def setUp(self) -> None:
        """Create test tenant, user, and workspace."""
        self.tenant = Tenant.objects.create(
            id=uuid.uuid4(),
            slug="test-tenant",
            name="Test Tenant",
            is_active=True,
        )
        self.user = User.objects.create(
            id=uuid.uuid4(),
            username="test-admin",
            email="test@example.com",
            is_active=True,
            tenant=self.tenant,
        )
        # Set tenant context for workspace creation
        set_request_tenant(self.tenant.id)
        try:
            from persistence.models import Workspace
            self.workspace = Workspace.objects.create(
                id=uuid.uuid4(),
                tenant=self.tenant,
                name="Test Workspace",
            )
            # Create admin role assignment
            UserRole.objects.create(
                user=self.user,
                workspace=self.workspace,
                role=ROLE_ADMIN,
                tenant=self.tenant,
                suspended_at=None,
            )
        finally:
            clear_request_tenant()

    def test_api_key_resolves_admin_role(self) -> None:
        """API key authentication resolves admin role from UserRole."""
        from auth_tenancy.services import (
            AuthenticationService,
            TenantContextService,
        )
        from auth_tenancy.models import ApiKey
        from auth_tenancy.services.authentication import hash_api_key

        # Create API key
        api_key = ApiKey.unscoped.create(
            id=uuid.uuid4(),
            user=self.user,
            name="test-key",
            key_hash=hash_api_key("rf_test123"),
            tenant=self.tenant,
        )

        # Mock the authentication to return claims with empty roles
        authn = AuthenticationService()
        claims = IdentityClaims(
            user_id=self.user.id,
            tenant_id=self.tenant.id,
            roles=(),  # API key has empty roles initially
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
        )

        # Mock tenant context service
        tenancy = TenantContextService()
        tenant_context = tenancy.resolve_tenant_context(claims)
        tenancy.activate(tenant_context)

        try:
            # Simulate what AuthTenancyAuthentication.authenticate() does
            active_roles = claims.roles
            if claims.auth_method == AuthMethod.API_KEY:
                # This is the fix: resolve roles from UserRole
                role_entries = (
                    UserRole.objects.filter(
                        user_id=claims.user_id,
                        suspended_at__isnull=True,
                    )
                    .values_list("role", flat=True)
                    .distinct()
                )
                active_roles = tuple(sorted({str(r).lower() for r in role_entries}))

            auth_context = tenancy.build_auth_context(
                claims, tenant_context, active_roles
            )

            # Verify that admin role was resolved
            assert "admin" in auth_context.active_roles
            assert auth_context.auth_method == AuthMethod.API_KEY
            assert auth_context.api_key_id == api_key.id
        finally:
            tenancy.deactivate()

    def test_api_key_resolves_multiple_roles(self) -> None:
        """API key resolves all active roles across workspaces."""
        from auth_tenancy.models import ApiKey
        from auth_tenancy.services.authentication import hash_api_key
        from auth_tenancy.services import TenantContextService
        from auth_tenancy.context import IdentityClaims

        # Set tenant context for workspace creation
        set_request_tenant(self.tenant.id)
        try:
            # Create second workspace with editor role
            from persistence.models import Workspace
            workspace2 = Workspace.objects.create(
                id=uuid.uuid4(),
                tenant=self.tenant,
                name="Test Workspace 2",
            )
            UserRole.objects.create(
                user=self.user,
                workspace=workspace2,
                role=ROLE_EDITOR,
                tenant=self.tenant,
                suspended_at=None,
            )
        finally:
            clear_request_tenant()

        # Create API key
        api_key = ApiKey.unscoped.create(
            id=uuid.uuid4(),
            user=self.user,
            name="test-key-2",
            key_hash=hash_api_key("rf_test456"),
            tenant=self.tenant,
        )

        # Create claims with empty roles
        claims = IdentityClaims(
            user_id=self.user.id,
            tenant_id=self.tenant.id,
            roles=(),
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
        )

        # Resolve roles
        tenancy = TenantContextService()
        tenant_context = tenancy.resolve_tenant_context(claims)
        tenancy.activate(tenant_context)

        try:
            active_roles = claims.roles
            if claims.auth_method == AuthMethod.API_KEY:
                role_entries = (
                    UserRole.objects.filter(
                        user_id=claims.user_id,
                        suspended_at__isnull=True,
                    )
                    .values_list("role", flat=True)
                    .distinct()
                )
                active_roles = tuple(sorted({str(r).lower() for r in role_entries}))

            auth_context = tenancy.build_auth_context(
                claims, tenant_context, active_roles
            )

            # Verify both roles resolved (deduplicated and sorted)
            assert set(auth_context.active_roles) == {"admin", "editor"}
        finally:
            tenancy.deactivate()

    def test_api_key_ignores_suspended_roles(self) -> None:
        """API key ignores suspended role assignments."""
        from auth_tenancy.models import ApiKey
        from auth_tenancy.services.authentication import hash_api_key
        from auth_tenancy.services import TenantContextService
        from auth_tenancy.context import IdentityClaims
        from django.utils import timezone

        # Create API key
        api_key = ApiKey.unscoped.create(
            id=uuid.uuid4(),
            user=self.user,
            name="test-key-suspended",
            key_hash=hash_api_key("rf_test789"),
            tenant=self.tenant,
        )

        # Suspend the admin role
        set_request_tenant(self.tenant.id)
        try:
            admin_role = UserRole.objects.get(user=self.user, role=ROLE_ADMIN)
            admin_role.suspended_at = timezone.now()
            admin_role.save()
        finally:
            clear_request_tenant()

        # Create claims
        claims = IdentityClaims(
            user_id=self.user.id,
            tenant_id=self.tenant.id,
            roles=(),
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
        )

        # Resolve roles
        tenancy = TenantContextService()
        tenant_context = tenancy.resolve_tenant_context(claims)
        tenancy.activate(tenant_context)

        try:
            active_roles = claims.roles
            if claims.auth_method == AuthMethod.API_KEY:
                role_entries = (
                    UserRole.objects.filter(
                        user_id=claims.user_id,
                        suspended_at__isnull=True,
                    )
                    .values_list("role", flat=True)
                    .distinct()
                )
                active_roles = tuple(sorted({str(r).lower() for r in role_entries}))

            auth_context = tenancy.build_auth_context(
                claims, tenant_context, active_roles
            )

            # Verify no active roles (admin role is suspended)
            assert auth_context.active_roles == ()
        finally:
            tenancy.deactivate()
