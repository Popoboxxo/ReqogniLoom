# ItemPermissionStore — Pre-Implementation Interface Analysis

**leaf_id:** COMP-AT-005_ItemPermissionStore
**req_id:** REQ-L1-039 (Item-Level RBAC)
**spec_doc:** `docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-005_ItemPermissionStore/COMP-AT-005_ItemPermissionStore.md`
**author:** se-senior-developer
**date:** 2026-06-28
**scope:** Wave B (Welle B) — model + service + cache foundation.
**deferred:** REST adapter (IF-AT-EXT-IN-001) and MCP tools (Wave C). RLS policy registration (Wave C — `persistence/migrations/0003_rls_policies.py` is intentionally NOT extended here).

---

## 1. Public API of `ItemPermissionService`

All public methods are instance methods on the stateless `ItemPermissionService` class. The service is a thin orchestrator over the `ItemPermission` model + `PermissionCache`. It reuses the cross-cutting helpers from `application.base.ServiceBase` (`_assert_permission`, `_set_tenant_context`, `_audit`).

### 1.1 `grant_permission(ctx, *, user_id, workspace_id, artifact_id, level, granted_by_user_id) -> ItemPermission`

Create or update a permission rule. Upsert semantics: if a row already exists for `(user, workspace, artifact)`, update the level in place; otherwise create.

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `ctx` | `AuthContext` | yes | Caller's auth context; `_assert_permission(ctx, "admin")` gates this. |
| `user_id` | `UUID` | yes | Subject user. |
| `workspace_id` | `UUID` | yes | Workspace scope. |
| `artifact_id` | `UUID \| None` | yes | Target artifact. `None` = workspace-wide default rule for `(user, workspace)`. |
| `level` | `str` | yes | One of `"read"`, `"write"`, `"none"`. |
| `granted_by_user_id` | `UUID` | yes | Admin user id (audit trail → `granted_by` column). |

**Returns:** the upserted `ItemPermission` instance.

**Raises:**
- `PermissionDeniedError` (from `ServiceBase._assert_permission`) if `ctx` lacks the `admin` role.
- `ValueError` if `level` is not one of the allowed choices.
- `TenantContextNotSetError` (from `TenantManager`) if no tenant context is active.

**Side effects:**
- INSERT or UPDATE on `at_item_permission` inside `transaction.atomic()`.
- AuditLog write via `ServiceBase._audit` (`op="create"` or `"update"`, `entity_type="ItemPermission"`, `entity_id=permission.id`).
- `PermissionCache.invalidate(...)` for the affected `(user_id, workspace_id, artifact_id_or_none)` triple.

### 1.2 `revoke_permission(ctx, *, user_id, workspace_id, artifact_id) -> bool`

Delete the matching permission rule if present.

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `ctx` | `AuthContext` | yes | `_assert_permission(ctx, "admin")` gate. |
| `user_id` | `UUID` | yes | Subject user. |
| `workspace_id` | `UUID` | yes | Workspace scope. |
| `artifact_id` | `UUID \| None` | yes | Target artifact. `None` = workspace-wide rule. |

**Returns:** `True` if a row was deleted, `False` if no matching row existed.

**Raises:** `PermissionDeniedError`.

**Side effects:**
- DELETE on `at_item_permission`.
- AuditLog write (`op="delete"`) on the deleted row's id, if it existed.
- `PermissionCache.invalidate(...)` for the affected key.

### 1.3 `list_permissions(ctx, *, user_id, workspace_id) -> list[ItemPermission]`

List all permission rules for `(user, workspace)` — both artifact-scoped and workspace-wide.

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `ctx` | `AuthContext` | yes | `_assert_permission(ctx, "admin")` gate. |
| `user_id` | `UUID` | yes | Subject user. |
| `workspace_id` | `UUID` | yes | Workspace scope. |

**Returns:** list of `ItemPermission` instances (may be empty). Read-only — no audit, no cache touch.

**Raises:** `PermissionDeniedError`.

### 1.4 `check_permission(user_id, workspace_id, artifact_id) -> PermissionDecision`

Evaluate the effective permission level for `(user, workspace, artifact)`. The result of every call is **cached** in `PermissionCache` for 60 seconds and **invalidated** on the next `grant_permission` / `revoke_permission` for the same triple.

This is a **read** operation; no RBAC gate, no tenant-context assertion beyond what the ORM manager requires, and no audit. The caller (e.g. RestApiAdapter / McpServer) is expected to have already cleared RBAC via `AuthorizationService.decide_access()`; both checks must pass.

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `user_id` | `UUID` | yes | Subject user. |
| `workspace_id` | `UUID` | yes | Workspace scope. |
| `artifact_id` | `UUID \| None` | yes | `None` = workspace-wide check. |

**Returns:** `PermissionDecision` (frozen dataclass): `level: str` (`"read"` | `"write"` | `"none"` | `"deny"`) and `reason: str` (the evaluation path that produced the answer).

**Raises:** `TenantContextNotSetError` (lazy: only on cache miss when the DB is hit).

---

## 2. Cache key strategy

`PermissionCache` is a thread-local TTL dict (see `permission_cache.py`). The cache key is the **frozen tuple**:

```
cache_key = (user_id_uuid, workspace_id_uuid, artifact_id_uuid_or_None)
```

The `None` artifact case is encoded as the literal `None` inside the tuple (so a workspace-wide rule and an artifact-scoped rule with the same artifact uuid do not collide — they cannot, because `None != <UUID>`). The tuple is used as a dict key (Python's tuple hash + equality are content-based and handle `None` correctly).

A separate `(user_id, workspace_id, "list")` key is **not** used: `list_permissions` does not touch the cache (it is admin-only, low-frequency, and returns model instances, not primitive decisions).

A tenant id is **not** part of the key because the cache lives on the thread-local context of a single request, and the active tenant is set for the entire request lifetime. Cross-tenant bleed cannot occur on a single thread.

## 3. Cache invalidation triggers

The cache is **fully** invalidated on any write to the model, because the resolution algorithm needs to consider the full rule set for `(user, workspace)`. Per-key invalidation is unsafe (a single workspace contains many `(user, artifact)` triples; knowing one was touched is not enough — a related workspace-wide default may have been added/removed).

| Trigger | Cache action |
|---------|--------------|
| `grant_permission(...)` | `PermissionCache.invalidate_all()` |
| `revoke_permission(...)` | `PermissionCache.invalidate_all()` |
| Test teardown | `PermissionCache.clear_thread()` (autouse fixture in `conftest.py`) |

Rationale: keeping it simple and correct. A future per-user cache is possible but out of scope for the MVP (60 s TTL, single-tenant per request).

## 4. Permission resolution algorithm

Given `check_permission(user_id, workspace_id, artifact_id)`, the algorithm evaluates, in this strict order:

1. **Cache hit** → return the cached `PermissionDecision` (no DB hit).
2. **Explicit artifact rule exists** (`ItemPermission` row with `artifact_id == artifact_id` and `level != "none"`) → return that level.
3. **Explicit artifact deny** (`ItemPermission` row with `artifact_id == artifact_id` and `level == "none"`) → return `level="deny"` (explicit deny override; beats the workspace default).
4. **Workspace-wide rule exists** (`ItemPermission` row with `artifact_id is None` and `level != "none"`) → return that level.
5. **Workspace-wide deny** (`ItemPermission` row with `artifact_id is None` and `level == "none"`) → return `level="deny"`.
6. **Default** → no rule applies → return `level="deny"` (closed-world: no rule means no access at the item layer; RBAC may still grant access through `AuthorizationService`).

The order of (2) vs (3) and (4) vs (5) is collapsed by the model: a `level` of `"none"` always means deny, regardless of whether the row is artifact-scoped or workspace-wide. The distinct ordering above is documented for future readers, but the implementation simplifies to:

```
effective_level = (
    explicit_artifact_level
    or workspace_default_level
    or "deny"
)
```

where `explicit_artifact_level` is `None` when no artifact-scoped row exists, and `workspace_default_level` is `None` when no workspace-wide row exists.

The resulting decision is **cached** under `(user_id, workspace_id, artifact_id)` for 60 seconds, then on cache miss the algorithm re-evaluates from scratch.

## 5. Interaction with RBAC (`AuthorizationService`)

`ItemPermissionStore` is a **separate layer** from `AuthorizationService`. Both must pass for a request to be allowed. They are evaluated in this order at the call site (RestApiAdapter / McpServer / domain facade):

1. `AuthorizationService.decide_access(roles, operation)` — coarse, role-based, **no item context**. Answers: "does this role allow this operation *type*?"
2. `ItemPermissionService.check_permission(user_id, workspace_id, artifact_id)` — fine, item-based, **no role context**. Answers: "does this user have a rule for this specific item?"

ItemPermission **does not** call or extend `AuthorizationService`. The `Operation` enum and the RBAC matrix stay untouched. ItemPermission is a defense-in-depth layer that can only further restrict, never broaden, what RBAC already permits:

| RBAC outcome | ItemPermission outcome | Final |
|--------------|-----------------------|-------|
| allow | allow (read/write) | **allow** |
| allow | deny / no rule | **deny** |
| deny | allow (read/write) | **deny** (RBAC already blocks) |
| deny | deny | **deny** |

This contract is implemented at the call site (RestApiAdapter / McpServer / domain facade), not in either service. The two services stay orthogonal.

## 6. Migration impact

**New table:** `at_item_permission` (one).

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | `UUID PK` | `default=uuid.uuid4` (inherited from `AuditableModel`) |
| `tenant_id` | `UUID FK → pl_tenant` | `ON DELETE PROTECT` (inherited from `TenantScopedModel`), indexed |
| `user_id` | `UUID FK → pl_user` | `ON DELETE CASCADE`, `related_name="item_permissions"` |
| `workspace_id` | `UUID FK → pl_workspace` | `ON DELETE CASCADE`, `related_name="item_permissions"` |
| `artifact_id` | `UUID FK → pl_artifact` | `ON DELETE CASCADE`, `null=True`, `related_name="item_permissions"` |
| `permission_level` | `VARCHAR(16)` | `choices=("read", "write", "none")` |
| `granted_by_id` | `UUID FK → pl_user` | `ON DELETE SET NULL`, `null=True`, `related_name="+"` |
| `created_at` | `TIMESTAMP` | `auto_now_add` (inherited) |
| `created_by_id` | `UUID FK → pl_user` | `SET_NULL`, `null=True` (inherited) |
| `modified_at` | `TIMESTAMP` | `auto_now` (inherited) |
| `modified_by_id` | `UUID FK → pl_user` | `SET_NULL`, `null=True` (inherited) |
| `version` | `INTEGER` | `default=1` (inherited) |

**New indexes (declared on the model, emitted by the migration):**

- `idx_itempermission_user_workspace` on `(user_id, workspace_id)` — backs `list_permissions` and cache lookups.
- `idx_itempermission_workspace_artifact` on `(workspace_id, artifact_id)` — backs resolution-order evaluation and `revoke_permission`.

**New unique constraint:**

- `uq_itempermission_user_ws_artifact` on `(tenant_id, user_id, workspace_id, artifact_id)` — prevents duplicate rules for the same triple. Nullable `artifact_id` participates in the constraint (NULL is treated as a distinct value in a unique index on PostgreSQL — but the upsert path uses `update_or_create` with the same triple, so the constraint acts as the last-line safety net).

**RLS implications (deferred to Wave C):**

- The `at_item_permission` table is tenant-scoped and therefore **must** be added to the `_TENANT_TABLES` list in `persistence/migrations/0003_rls_policies.py`. **This change is explicitly out of scope for Wave B** (constraint `no_rls_update` in the task).
- A second RLS policy for row-level "is this user allowed to see this row" is **not** required for the MVP; the application layer (`TenantManager`) and the cache are the enforcement points. RLS for ItemPermission is a Wave C item.

**Migration file:** `backend/auth_tenancy/migrations/0003_item_permission.py`, hand-authored, depends on:

- `("auth_tenancy", "0002_alter_apikey_managers_alter_userrole_managers")`
- `("persistence", "0009_workspace_lifecycle_fields")` — the latest persistence migration (Welle A baseline).

---

## Summary

- **Public API**: 4 methods, all on `ItemPermissionService` (stateless). `grant_permission` / `revoke_permission` / `list_permissions` are admin-gated; `check_permission` is read-only and uncoupled from RBAC.
- **Cache**: thread-local TTL dict, 60 s TTL, key = `(user_id, workspace_id, artifact_id)`. Invalidated fully on every write.
- **Resolution**: explicit artifact rule → workspace-wide default → deny (closed-world). `level="none"` always means deny.
- **RBAC interaction**: orthogonal. Both must pass at the call site; ItemPermission is the finer, second gate.
- **Migration**: one new table (`at_item_permission`), two indexes, one unique constraint. RLS registration deferred to Wave C.
- **Boundary check**: no level crossing (ItemPermission lives entirely within AuthAndTenancySystem, leaf node has no child L3 components). The interaction with `AuthorizationService` is **deliberately** non-extending — both layers call into the same `AuthContext` shape but stay separate.
- **No interface changes**: the existing `AuthContext`, `TenantContext`, `AuthorizationService`, `ServiceBase`, `audit.services.log_write` interfaces are consumed as-is. No unilateral changes.
