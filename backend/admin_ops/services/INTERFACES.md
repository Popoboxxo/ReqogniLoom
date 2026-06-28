# admin_ops — Pre-Implementation Interface Analysis

**leaf_id:** `admin_ops.DisasterRecoveryFoundation`
**req_id:**   `REQ-L1-046` (Disaster Recovery — foundation phase)
**status:**    Pre-implementation (must exist BEFORE the first code artifact)

This document freezes the public API and the design decisions for the
Disaster Recovery foundation. It is the contract handed to
`se-architect` and `se-critic` for approval; no code below this line in
the implementation phase may deviate from it without re-running the
interface review.

---

## 1. Context and Scope

`admin_ops` is a new Django app introduced by REQ-L1-046. It owns the
Disaster Recovery (DR) foundation for the whole system:

* a persistent record of system-wide backup operations (`BackupMetadata`)
* the public service surface used to **create, list, get, delete** backups
* a public service surface used to **restore** a previously created backup
  (admin-only, with a mandatory typed-confirmation captcha)

The foundation does **not** expose REST views or MCP tools (those arrive
in a later wave). The app is consumed by other components (admin tooling,
on-call runbooks) via the service classes.

`BackupMetadata` is **instance-level**, not tenant-scoped: it is the
system's bookkeeping of *what was backed up at the platform level*, not a
piece of tenant data. A backup row therefore has no `tenant` FK and
queries against the table must NOT apply a tenant filter.

---

## 2. Public API

### 2.1 `admin_ops.services.backup_service.BackupService`

All methods are **admin-only**. They raise
`application.base.PermissionDeniedError` if the caller's `AuthContext`
does not include the `admin` role.

| Method | Signature | Returns | Raises |
|--------|-----------|---------|--------|
| `create_backup` | `(ctx: AuthContext, *, backup_type: str = "full", metadata: dict | None = None) -> BackupMetadata` | The newly created `BackupMetadata` (status set after the row is committed; see §6). | `PermissionDeniedError`, `ValueError` (unknown `backup_type`), `OSError`/`RuntimeError` on I/O failure. |
| `list_backups` | `(ctx: AuthContext, *, limit: int = 100, offset: int = 0) -> list[BackupMetadata]` | Backups ordered by `-created_at`. | `PermissionDeniedError` |
| `get_backup`   | `(ctx: AuthContext, backup_id: UUID) -> BackupMetadata` | The single row. | `PermissionDeniedError`, `BackupNotFoundError` |
| `delete_backup`| `(ctx: AuthContext, backup_id: UUID) -> bool` | `True` if a row was removed, `False` if it did not exist. | `PermissionDeniedError` |

`BackupService` is **stateless** and safe to instantiate per request.

### 2.2 `admin_ops.services.admin_restore_service.AdminRestoreService`

| Method | Signature | Returns | Raises |
|--------|-----------|---------|--------|
| `restore` | `(ctx: AuthContext, *, backup_id: UUID, confirmation_text: str) -> RestoreResult` | A `RestoreResult` with `backup_id`, `started_at`, `completed_at`, `restored_tables`, `rows_per_table`. | `PermissionDeniedError`, `ValidationError` (captcha mismatch), `BackupNotFoundError` (when `backup_id` is unknown or in a non-restorable state) |

`AdminRestoreService` is **stateless** and safe to instantiate per request.

#### 2.2.1 Captcha contract

`restore()` is the most dangerous operation in the system. To prevent
accidental or malicious invocation the method requires a typed
confirmation:

```python
if confirmation_text != "RESTORE":  # case-sensitive
    raise ValidationError("Captcha mismatch")
```

The literal string `RESTORE` is the captcha value. Comparison is
**exact and case-sensitive** — `"restore"`, `" RESTORE"`, `"RESTORE!"` all
fail. The only message surfaced to the caller is the constant
`"Captcha mismatch"` (tested in `test_admin_restore_service.py`).

### 2.3 Shared DTOs

```python
@dataclass(frozen=True)
class RestoreResult:
    backup_id: UUID
    started_at: datetime
    completed_at: datetime
    restored_tables: list[str]      # app_label.ModelName per row touched
    rows_per_table: dict[str, int]  # table -> row count restored
```

`BackupNotFoundError(LookupError)` is defined in
`admin_ops.services.exceptions` and re-exported by
`admin_ops.services`.

### 2.4 Re-exports

`admin_ops.services.__init__` exports:

* `BackupService`
* `AdminRestoreService`
* `RestoreResult`
* `BackupNotFoundError`

---

## 3. Backup format strategy

Three options were evaluated:

* **(a) `dumpdata` to `MEDIA_ROOT/backups/<uuid>.json`** — Django's
  built-in serializer handles FKs, M2M, multi-table inheritance, and
  produces a human-readable JSON file that can be diffed and audited.
* **(b) Reference-only** — `BackupMetadata` is just a pointer to an
  externally managed file (e.g. S3 URI). Pros: scalable. Cons: leaves
  the actual file format out of our control; restore needs an external
  downloader; hard to test.
* **(c) Hybrid** — metadata row + file path, but the file is also
  `dumpdata`-JSON.

**Choice: (a).** Rationale: in scope for the foundation we want
deterministic, self-contained artifacts that the system can produce and
consume without external dependencies. (a) gives us exactly that, the
JSON file is the audit-evidence of *what* was in the database at the
moment of the backup, and `loaddata` already understands the format on
restore. (b) is deferred to a later wave if S3-style off-host storage
becomes a requirement.

The `metadata` JSONField on `BackupMetadata` carries a summary snapshot
(`{"tenant_count": N, "artifact_count": M, "app_counts": {...}}`) so
that the operator can decide whether a backup is worth restoring
without opening the file.

---

## 4. Restore safety mechanisms

Three guards, applied in this order at the start of `AdminRestoreService.restore`:

1. **Admin role gate** — `ServiceBase._assert_permission(ctx, "admin")`.
2. **Captcha gate** — `confirmation_text == "RESTORE"` (exact, case-sensitive).
3. **Backup-state gate** — refuse to restore from a backup whose `status`
   is not `completed` (i.e. we never restore from a `pending`,
   `in_progress`, or `failed` row).

The restore body then runs inside a single
`django.db.transaction.atomic()` block. Any exception raised inside
that block rolls back the entire restore — partial restores are not
possible. The audit log entries for `restore.start` and
`restore.complete` / `restore.fail` are written *inside* the same
transaction so a rolled-back restore also removes its start audit row;
the failure audit is written in a *separate* small atomic block after
the rollback so that operators can still see *why* it failed.

**Dry-run mode** is *not* included in v1 (foundation phase). A future
wave can add a `dry_run: bool` parameter that runs the same plumbing
but skips the `loaddata` write. Documented here so that the interface
gap is visible to the critic.

---

## 5. Audit log integration

AuditLog writes go through `ServiceBase._audit`, which delegates to
`audit.services.log_write`. Because `AuditEntry` is a `TenantScopedModel`
the writer needs an active `TenantContext`; we set it to the **admin's
own tenant** via `ServiceBase._set_tenant_context(ctx)`. This matches
the pattern in `ItemPermissionService` — the audit row is owned by the
admin's tenant, not by any of the tenants whose data the backup
contains.

| Operation | `operation` | `entity_type` | `entity_id` | `details.operation_kind` |
|-----------|-------------|---------------|-------------|--------------------------|
| `create_backup`     | `create` | `BackupMetadata` | new id | `backup.create` |
| `delete_backup`     | `delete` | `BackupMetadata` | existing id | `backup.delete` |
| `restore.start`     | `create` | `BackupRestore` | new uuid | `restore.start` |
| `restore.complete`  | `update` | `BackupRestore` | same uuid | `restore.complete` |
| `restore.fail`      | `update` | `BackupRestore` | same uuid | `restore.fail` |

`BackupRestore` is a *virtual* entity id (a `uuid4()` generated at
`restore.start`) so that all three restore events form a coherent
audit trail under the same id. The id is not persisted on
`BackupMetadata` — it lives only in the audit log.

---

## 6. Permission model

A single gate per public method:

```python
ServiceBase._assert_permission(ctx, "admin")
```

There is **no** `admin_ops/services/admin_guard.py`. The decision
mirrors `auth_tenancy.services.item_permission.ItemPermissionService`,
which puts the gate inline in each method rather than in a separate
module. Tests assert the gate for `editor` / `viewer` / empty-roles
contexts and confirm that the failure happens *before* any DB write.

Tenant context is still propagated (`ServiceBase._set_tenant_context`)
so the audit log can resolve the admin's tenant.

---

## 7. Failure scenarios

| Scenario | Behaviour |
|----------|-----------|
| `create_backup` I/O failure (e.g. disk full) | `transaction.atomic()` rolls back; a *second* small atomic block marks the `pending` row as `failed` with `error_message`. If the second block also fails the row is left `pending` and an exception is re-raised. |
| `create_backup` writes the row successfully but `dumpdata` itself raises | Same path: the row is marked `failed` with the captured error. |
| `delete_backup` for a non-existent id | Returns `False`; no audit row written. |
| `restore` captcha mismatch | Raises `ValidationError("Captcha mismatch")` *before* any DB read; no audit row. |
| `restore` against a `pending` / `in_progress` / `failed` backup | Raises `BackupNotFoundError` with reason `non-restorable status`; no audit row. |
| `restore` fails mid-`loaddata` | The outer `transaction.atomic()` rolls back. A separate atomic block writes a `restore.fail` audit row so the operator sees what happened. The backup's own `metadata.last_restore_status` is updated to `failed` with the captured error. |
| `restore` fails inside the failure-audit block | Logged at ERROR; the original exception is re-raised. The failure-audit row may be lost; an operator must check the application log. |

`last_restore_status` is a small JSON sub-dict stored on
`BackupMetadata.metadata` (e.g. `{"last_restore_status": "failed",
"last_restore_error": "..."}`). It is best-effort bookkeeping, not
authoritative.

---

## 8. Migration impact

Hand-authored `0001_initial.py` (matches the pattern in
`auth_tenancy/migrations/0003_item_permission.py`).

* **Dependencies:**
  * `("auth_tenancy", "0003_item_permission")` — the foundation row
    needs the `User` and `Tenant` tables that the auth app already
    created.
  * `("persistence", "0009_workspace_lifecycle_fields")` — the latest
    pre-RLS persistence migration, so we run before the
    `0010_rls_item_permission` sweep (this table is instance-level and
    does not need RLS).
* **New table:** `admin_ops_backup_metadata`
* **Fields (in addition to `AuditableModel`):**
  * `status` — `CharField(16)`, `choices=BackupStatus.choices`, default `pending`
  * `backup_type` — `CharField(16)`, `choices=BackupType.choices`, default `full`
  * `file_path` — `CharField(512)`, nullable
  * `file_size_bytes` — `BigIntegerField`, nullable
  * `checksum_sha256` — `CharField(64)`, nullable
  * `error_message` — `TextField`, blank, default `""`
  * `completed_at` — `DateTimeField`, nullable
  * `metadata` — `JSONField`, default `dict`, blank
* **Indexes:**
  * `idx_adminops_backup_status_created` on `(status, created_at)` — for
    the admin list view.
* **No FKs** (instance-level). `created_by` / `modified_by` come from
  `AuditableModel` and FK to `persistence.user`.
* **No constraints** beyond Django defaults.

---

## 9. Out of scope (deferred to later waves)

* REST views for `/api/v1/admin/backups/...`
* MCP tools for the same surface
* Dry-run restore
* S3 / off-host backup storage (option (b) above)
* Asynchronous / Celery-driven backup (currently synchronous)
* Backup rotation / retention policy
* Restore with PITR (point-in-time recovery)

The foundation is intentionally narrow so that the next wave can
iterate on the public API without re-doing the schema.
