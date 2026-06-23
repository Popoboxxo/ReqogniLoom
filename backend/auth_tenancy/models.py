"""
ARCH-L1-011 AuthAndTenancy — Models.

TODO(COMP-AT-001): Implement Token model for Bearer Token and API Key authentication.
TODO(COMP-AT-002): Implement Role enum and UserRole assignment model.
  Roles: Admin, Editor, Viewer, Approver (Approver only active in Extended preset).
TODO(COMP-AT-003): Implement TenantMiddleware — reads tenant_id from token,
  stores in thread-local/request context so PersistenceLayer.CustomManager can
  filter all queries. See ADR-03.

Reference: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/L2_AuthAndTenancySystem_Architecture.md
"""
from django.db import models  # noqa: F401
