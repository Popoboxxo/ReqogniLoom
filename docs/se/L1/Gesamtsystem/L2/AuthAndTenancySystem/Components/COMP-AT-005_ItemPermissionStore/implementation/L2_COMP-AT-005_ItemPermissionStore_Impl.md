---
step: implementation
agent: se-senior-developer
status: done
timestamp: "2026-06-28T16:10:00Z"
schema_version: "1.0.0"
req_id: REQ-L1-039
leaf_id: COMP-AT-005_ItemPermissionStore
---

# COMP-AT-005 ItemPermissionStore — Implementation (Welle B)

**req_id:** REQ-L1-039 (Item-Level RBAC)
**leaf_id:** COMP-AT-005_ItemPermissionStore
**agent:** se-senior-developer
**branch:** feat/se-implementation
**date:** 2026-06-28

## INTERFACE_ANALYSIS

leaf_id: COMP-AT-005_ItemPermissionStore
interface_count: 0 (leaf consumes existing framework interfaces; no new internal/external IFs created in this wave)
inherited_external: 0 — component relies on `AuthContext`, `TenantContext`, `AuthorizationService`, `ServiceBase`, `audit.services.log_write` — all consumed as-is
new_internal_incoming: 0 — no REST or MCP surface in this wave
new_internal_outgoing: 0 — no new outgoing calls; uses framework-provided ORM + audit
completeness: ok — every consumed interface exists in the registry (REUSE, no changes)
consistency: ok — no contradictions between consumed contracts and the new code
boundary_crossed: no — leaf is fully self-contained in `auth_tenancy/`
decision: proceed

**Algorithm summary** (full analysis in
`backend/auth_tenancy/services/item_permission_INTERFACES.md`):

1. `check_permission(user, workspace, artifact)` evaluates, in order:
   explicit artifact rule (wins) -> workspace-wide default (fallback) -> deny
   (closed-world). `level="none"` always produces `deny` (explicit-deny
   override).
2. Cache key: `(user_id, workspace_id, artifact_id_or_None)` in a thread-local
   TTL dict; TTL 60s; wiped fully on any grant/revoke write.
3. `check_permission` is read-only and uncoupled from RBAC. RBAC and
   ItemPermission are orthogonal layers, both must pass at the call site.
4. Audit uses `audit.services.log_write` with `op` in
   `{create, update, delete}` (the only values accepted by
   `AuditEntry.OP_CHOICES`); the `details.operation_kind` field carries the
   semantic name (`item_permission.grant` / `item_permission.revoke`).

## DECISION

context: The audit `op` field accepts only the closed enum
`{create, update, delete, transition}`, but the task brief asked for
`item_permission.grant|revoke|check` as the operation label.
choice: Map the three semantic operations onto the existing audit choices
(`grant` -> `create` or `update` depending on upsert outcome; `revoke` ->
`delete`; `check` is not audited because it is a read). Carry the semantic
name in `details.operation_kind` for traceability.
alternatives: (a) extend `AuditEntry.OP_CHOICES` with a new value -> rejected,
violates "no unilateral interface changes" rule and would change the
`audit.services` interface contract. (b) Skip audit entirely on grant/revoke
-> rejected, REQ-L2-AL-001 mandates an entry for every write.
consequences: Audit query filters can still be built on the existing op
enum; consumers that need the granular label can filter on
`details.operation_kind`.
interface_impact: none — only `details` payload was added, no schema change.

## Artifacts

| Path | Type | Purpose |
|------|------|---------|
| `backend/auth_tenancy/services/item_permission_INTERFACES.md` | new | Pre-implementation interface analysis (6 sections) |
| `backend/auth_tenancy/models.py` | modified | Added `ItemPermission` model + `ITEM_PERMISSION_*` constants |
| `backend/auth_tenancy/services/permission_cache.py` | new | Thread-local TTL cache (60s), 4-method API |
| `backend/auth_tenancy/services/item_permission.py` | new | `ItemPermissionService` (grant/revoke/list/check) + `PermissionDecision` |
| `backend/auth_tenancy/services/__init__.py` | modified | Re-exports for the new service + cache |
| `backend/auth_tenancy/migrations/0003_item_permission.py` | new | Hand-authored `CreateModel` + `AddConstraint` |
| `backend/auth_tenancy/tests/test_item_permission.py` | new | 5 unit + 16 integration tests = 21 total |

## Test coverage

| Surface | Test | Type |
|---------|------|------|
| PermissionCache | `test_permission_cache_get_returns_none_when_empty` | unit |
| PermissionCache | `test_permission_cache_set_then_get_returns_decision` | unit |
| PermissionCache | `test_permission_cache_ttl_expiry` | unit |
| PermissionCache | `test_permission_cache_invalidate_all_clears_everything` | unit |
| PermissionCache | `test_permission_cache_thread_isolation` | unit |
| RBAC gate | `test_grant_permission_requires_admin_role` | unit (gate only) |
| RBAC gate | `test_revoke_permission_requires_admin_role` | unit (gate only) |
| RBAC gate | `test_list_permissions_requires_admin_role` | unit (gate only) |
| Validation | `test_grant_permission_rejects_invalid_level` | unit |
| Grant | `test_grant_then_check_returns_granted_level` | integration |
| Grant | `test_grant_is_upsert` | integration |
| Revoke | `test_revoke_removes_rule_and_returns_true` | integration |
| Revoke | `test_revoke_nonexistent_rule_returns_false` | integration |
| Check | `test_check_permission_no_rule_returns_deny` | integration |
| Check | `test_check_permission_artifact_rule_overrides_workspace_default` | integration |
| Check | `test_check_permission_workspace_default_fallback` | integration |
| Check | `test_check_permission_explicit_deny` | integration |
| List | `test_list_permissions_returns_all_rules_for_user_workspace` | integration |
| Cache | `test_grant_invalidates_check_cache` | integration |
| Model | `test_itempermission_model_properties` | integration |
| Schema | `test_unique_constraint_blocks_duplicate_triple` | integration |

## Verification commands run

| Command | Result |
|---------|--------|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --dry-run --check` | `No changes detected` |
| `pytest backend/auth_tenancy -v` | `78 passed in 6.21s` (57 existing + 21 new) |
| `pytest backend/mcp_server -v` | `108 passed, 3 warnings in 0.32s` (regression check, green) |
| `pytest backend/{auth_tenancy,persistence,mcp_server,application}` | `561 passed, 4 pre-existing failures unrelated to this change` |
| `git status` | only the listed artifacts + 3 pre-existing files untouched |

The 4 pre-existing failures (`test_admin_login.py` x3, `test_export_service.py` x1) were verified to fail on the baseline (commit c13b64c) as well — they are not regressions.

## Boundary check

- No level boundary crossed: implementation lives entirely inside the L2
  `AuthAndTenancySystem`.
- `AuthorizationService` consumed as-is, NOT extended. The ItemPermission
  decision is computed independently of the RBAC matrix; both layers must
  pass at the call site.
- `ServiceBase` and `audit.services.log_write` consumed as-is. No
  interface changes.
- No additions to `_TENANT_TABLES` in `persistence/migrations/0003_rls_policies.py` (deferred to Welle C per task constraint `no_rls_update`).
- No REST views, no MCP tools (deferred to Welle C per task constraints `no_rest` / `no_mcp`).
- The 3 pre-existing modified files (`.meta-config/project.yaml`, `CLAUDE.md`,
  `docs/conclusions/conclusions-2026-06-25.md`) were not touched.

## De-escalation hint

Not applicable. The leaf stayed at the senior-developer tier: it touches
multiple concerns (model, service, cache, migration, audit) and has
high-risk security/performance characteristics (item-level access control,
60s cache with proper invalidation, cross-tenant isolation). All findings
were self-resolvable; no escalation to `se-interface-mgr` or `se-architect`
was needed.
