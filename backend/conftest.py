"""
Pytest configuration and shared fixtures for ReqFlow backend tests.

TODO(ARCH-L1-011): Add tenant fixture once auth_tenancy is implemented.
TODO(ARCH-L1-010): Add database factory fixtures once persistence models are defined.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def db_access(db: None) -> None:
    """Alias fixture to ensure database access is explicit in tests.

    TODO(ARCH-L1-010): Replace with transactional_db where needed for
    tests that verify ACID behaviour (REQ-L1-025).
    """
    pass


@pytest.fixture
def single_tenant(db: None) -> dict[str, int]:
    """Provide the default tenant context for v1 (single-tenant mode).

    In v1, only one default tenant exists (see ADR-03 and settings.DEFAULT_TENANT_ID).
    v2-activation of multi-tenancy requires no data migration.

    TODO(ARCH-L1-011): Once Tenant model is implemented in auth_tenancy, replace
    this fixture with an actual Tenant object from the database.

    Returns:
        dict with 'tenant_id' key matching settings.DEFAULT_TENANT_ID.
    """
    from django.conf import settings

    return {"tenant_id": settings.DEFAULT_TENANT_ID}


@pytest.fixture
def api_client():
    """DRF test client with default configuration.

    TODO(ARCH-L1-011): Extend with Bearer-Token authentication helper once
    auth_tenancy is implemented (REQ-L1-010 RBAC).
    """
    from rest_framework.test import APIClient

    return APIClient()
