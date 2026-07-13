---
step: implementation
agent: se-senior-developer
status: done
timestamp: "2026-06-24T00:00:00Z"
schema_version: "1.0.0"
---

# L2 PersistenceLayerSystem — Implementation Summary

System: ARCH-L1-010 PersistenceLayerSystem
Context boundary: `backend/persistence/`

## INTERFACE_ANALYSIS

```
leaf_id: ARCH-L1-010 / COMP-PL-001..006
interface_count: 9 external (IF-PL-EXT-IN-001..009 + OUT-001) + 6 internal (IF-PL-INT-001..006)
inherited_external: 9 — IF-PL-EXT-IN-001..009, IF-PL-EXT-OUT-001
new_internal_incoming: 0 (terminal subsystem, no new exposed contracts beyond ORM)
new_internal_outgoing: 6 — IF-PL-INT-001..006
completeness: ok
consistency: ok
boundary_crossed: no
decision: proceed
```

Note: IF-PL-EXT-IN-008 (tenant context) and IF-PL-EXT-IN-006 (User/Role/Tenant
ORM) are partially owned by AuthAndTenancy (ARCH-L1-011). The seam is provided
here (`persistence.middleware.BaseTenantMiddleware`, `TenantContext`) but the
resolution of tenant-from-credentials is deliberately left to ARCH-L1-011.

## DECISION

```
context: L3 arch references requirements_app/models.py; task mandates backend/persistence/.
choice: implement in backend/persistence/ (task is authoritative; app already in INSTALLED_APPS).
alternatives: requirements_app/ — rejected, not in INSTALLED_APPS, contradicts task scope.
consequences: other apps import from `persistence`, not `requirements_app`.
interface_impact: none (module location, not an interface contract)
```

```
context: L2 arch defines 6 components (COMP-PL-006 RLS added); task brief listed 5.
choice: implemented all 6 — RLS (COMP-PL-006) is required by REQ-L2-PL-010 (mandatory).
alternatives: skip RLS — rejected, would leave a mandatory requirement unmet.
consequences: migration 0003 ships CREATE POLICY + FORCE RLS on 11 tenant tables.
interface_impact: none (matches IF-PL-INT-006 already in the registered arch).
```

```
context: TenantManager must scope every query without infinite recursion.
choice: single enforcement point in TenantManager.get_queryset; TenantQuerySet does
        not override filter/exclude (they inherit the WHERE via Django clone).
        base_manager_name="unscoped" so Django internals (cascade, FK validation)
        are not tenant-filtered.
alternatives: override every queryset method — rejected, recurses infinitely and is fragile.
consequences: safe-by-default objects manager; explicit `unscoped` escape hatch.
interface_impact: none
```

## Artifacts

| File | Component | Requirements |
|------|-----------|--------------|
| `backend/persistence/tenancy.py` | COMP-PL-002 | REQ-L2-PL-001, REQ-L3-PL002-001..003 |
| `backend/persistence/models.py` | COMP-PL-001 / COMP-PL-005 | REQ-L2-PL-004/005/009/003 |
| `backend/persistence/transactions.py` | COMP-PL-003 | REQ-L2-PL-002, REQ-L3-PL003-001..003 |
| `backend/persistence/middleware.py` | COMP-PL-002 / COMP-PL-006 | IF-PL-EXT-IN-008 |
| `backend/persistence/services.py` | foundation surface | — |
| `backend/persistence/migrations/0001_initial.py` | COMP-PL-004 | REQ-L2-PL-006 |
| `backend/persistence/migrations/0002_fulltext_indexes.py` | COMP-PL-005 | REQ-L2-PL-003/008 |
| `backend/persistence/migrations/0003_rls_policies.py` | COMP-PL-006 | REQ-L2-PL-010 |
| `backend/persistence/tests/*` | all | acceptance criteria |

## Foundation import surface (for other apps)

```python
from persistence.models import TenantScopedModel, AuditableModel
from persistence.tenancy import TenantContext, TenantContextNotSetError
from persistence.transactions import atomic_transaction, TransactionContextManager
# or the aggregated facade:
from persistence.services import TenantScopedModel, TenantContext, atomic_transaction
```

## Open escalations

1. RLS uses FORCE ROW LEVEL SECURITY; the app DB role is currently the table owner.
   A dedicated least-privilege application role is recommended for production so
   the owner bypass cannot be abused. Owner: devops / AuthAndTenancy.
2. IF-PL-EXT-IN-008 tenant resolution from credentials is a stub
   (`BaseTenantMiddleware.resolve_tenant_id` returns None) — to be completed by
   ARCH-L1-011 AuthAndTenancy.
3. Connection pooling (REQ-L2-PL-007, desired) not wired into settings DATABASES
   to avoid changing shared DB config beyond scope; CONN_MAX_AGE/DB_POOL_SIZE
   hooks documented in COMP-PL-005 arch for a follow-up.
