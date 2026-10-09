# R-3 — Inventory of `.unscoped` readers of `ApiKey` / `UserRole`

- **Issue:** #1184 (spec residual R-3 of #1136)
- **Spec:** [`docs/audit/2026-10/1136-rls-coverage-spec.md`](./1136-rls-coverage-spec.md)
  — risk entry **R-3** (line 668) and the addendum note at lines 830-833.
- **Static guard:**
  [`backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py`](../../../backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py)
- **Status:** documentation + static guard. No policy change and no flag flip.
  The single dangerous reader identified below has been **fixed** (guarded, like
  the `inventory_api_keys` canon), so the R-3 blocker on the pre-flip checklist
  is closed; the flag itself stays off until the remaining checklist items are
  verified against a live database.

## Purpose

`RLS_PREAUTH_ENFORCED` (`backend/reqogniloom/settings.py:350-351`) gates the
permissive staged policy on `at_api_key` / `at_user_role`
(`auth_tenancy/0017_preauth_staged_rls.py`, see `RLS_STAGED_TABLES` in
`backend/persistence/tests/test_rls_coverage.py`). While the flag is **off** the
policy predicate is fully permissive and every reader is unaffected. When the
flag is **on**, any reader of those tables that is *not* covered by the
`SECURITY DEFINER` functions (`public.auth_api_key_lookup`,
`public.auth_resolve_roles`) is subjected to the tenant predicate and — if no
tenant context is armed — would be silently emptied.

R-3 requires the full grep inventory of `ApiKey.unscoped` / `UserRole.unscoped`
readers to be written down *before* the flag is flipped, and each finding to be
verified: an **unverified** reader that would go silently empty is a **blocker**
for the flip. This document is that inventory. The static guard keeps it from
drifting independently of the code.

## Inventory (production code only)

Scope: every `.unscoped` usage of the tracked models in production Python files
under `backend/` (tests, migrations, `conftest.py` and `__pycache__` excluded).
`UserRole.unscoped` occurrences that remain in tests and in docstrings are not
production readers and are out of scope.

| Model | file:line | enclosing symbol | operation | tenant context armed? | risk under `RLS_PREAUTH_ENFORCED=on` |
|---|---|---|---|---|---|
| `ApiKey` | `backend/auth_tenancy/services/authentication.py:732` | `AuthenticationService.create_api_key` | READ — active-key count (`filter(...).count()`) | yes — REST `POST /api/v1/api-keys/`, armed by `AuthTenancyAuthentication` | **safe** |
| `ApiKey` | `backend/auth_tenancy/services/authentication.py:744` | `AuthenticationService.create_api_key` | CREATE (`ApiKey.unscoped.create`) | yes — same request as above | **safe** |
| `ApiKey` | `backend/auth_tenancy/services/authentication.py:761` | `AuthenticationService.list_api_keys` | READ (`filter(user_id=...)`) | yes — REST `GET /api/v1/api-keys/`, armed | **safe** |
| `ApiKey` | `backend/auth_tenancy/services/authentication.py:790` | `AuthenticationService.revoke_api_key` | READ (`filter(id=...).first()`) | yes from REST (`DELETE /api/v1/api-keys/<pk>/`); **no** when called from the `revoke_api_key` management command | **safe** from REST; **loud-fail** on the CLI branch (unarmed read returns `None` → `AuthenticationFailed("invalid_api_key")`, and the CLI caller is already stopped by `Command._resolve_key`) |
| `ApiKey` | `backend/auth_tenancy/management/commands/revoke_api_key.py:115,121` | `Command._resolve_key` | READ (`filter(...)`) | **no** — privileged cross-tenant CLI, no tenant context | **loud-fail** — an empty result raises `CommandError("No API key matches --key-id ...")`; it never silently reports success |
| `ApiKey` | `backend/auth_tenancy/management/commands/inventory_api_keys.py:357` | `collect_inventory` | READ (`ApiKey.unscoped.all()`, cross-tenant) | **no**, but explicitly guarded by `SET LOCAL row_security = off` (`:362`) | **loud-fail** — on the least-privilege app role the read raises rather than reporting "0 keys", which is exactly the intent of the guard |
| `ApiKey` | `backend/auth_tenancy/management/commands/cleanup_revoked_api_keys.py:91` | `Command.handle` | READ (`filter(revoked_at__isnull=False, revoked_at__lt=cutoff)`) then DELETE (`stale.delete()`) | **no** — cross-tenant maintenance, no tenant context; explicitly guarded by `SET LOCAL row_security = off` (`:104`) | **loud-fail** — on the least-privilege app role the read raises instead of reporting "0 ... would be deleted" / "Deleted 0", which is exactly the intent of the guard (see below) |
| `UserRole` | *(none)* | — | — | — | **n/a** |

## `UserRole` — zero production readers

Production code contains **zero** `UserRole.unscoped` readers. The sole
production role read is the raw-SQL call to the `SECURITY DEFINER` function:

```
SELECT role FROM public.auth_resolve_roles(%s)
```

in `PasswordAuthenticationService.resolve_roles`
(`backend/auth_tenancy/services/password_authentication.py:173-178`, issue #1136
IC-1b). That function is the reviewed replacement for the former
`UserRole.unscoped` read and is the reason the `at_user_role` staged policy can
be enabled without emptying role resolution. The only remaining textual
`UserRole.unscoped` mentions are in test fixtures and in explanatory docstrings
(e.g. `password_authentication.py:158,170`); they are documentation, not
readers.

The guard test encodes this directly: because no `UserRole` entry exists in its
allowlist, any newly introduced production `UserRole.unscoped` usage is reported
as an unexpected reader and fails the test.

## The former dangerous path: `cleanup_revoked_api_keys.py:91`

`Command.handle` used to be the single R-3 reader that would fail **silently**
under `RLS_PREAUTH_ENFORCED=on`:

- it runs from the CLI with **no tenant context** armed, and
- unlike `inventory_api_keys.collect_inventory`, it had **no**
  `SET LOCAL row_security = off` guard.

With the flag on, the staged policy predicate on `at_api_key` reduced the
cross-tenant queryset to zero rows. Consequently:

- `stale.count()` returned `0` (dry run printed "0 revoked API key(s) … would be
  deleted"), and
- `stale.delete()` returned `0` (with `--apply` it printed "Deleted 0 revoked API
  key(s)") —

both without any error or warning: the command reported success while doing
nothing. That concrete silent-empty consequence is what R-3 warns about.

### Fix (issue #1184)

The read and the delete now run inside `transaction.atomic()` with
`SET LOCAL row_security = off` (`cleanup_revoked_api_keys.py:96-110`, the `SET`
itself at `:104`), the same guard `inventory_api_keys.collect_inventory`
established. The two branches of the guard match the canon, and both were proven
live against PostgreSQL by
`backend/auth_tenancy/tests/test_cleanup_revoked_api_keys_rls_1184.py`:

- on an operator/owner (owner or superuser) connection no policy is ever applied,
  so the guard is a no-op and the delete really happens;
- on the least-privilege app role (`reqogniloom_app`) `SET row_security = off` is
  accepted but the *read* is not: Postgres raises `query would be affected by
  row-level security policy`, so the command aborts with the data untouched
  instead of printing "Deleted 0". The same armed session reading the plain
  unguarded `ApiKey.unscoped.filter(revoked_at__isnull=False)` queryset still
  returns 0 rows — that unguarded read is the mechanism the guard exists to
  break, and the test pins it so the fix cannot silently regress to a no-op.

Command behaviour is otherwise unchanged: dry-run by default, `--apply` to
delete, `--older-than-days` as the threshold, identical output strings. This is
the single cross-tenant maintenance path in production for `at_api_key`, and it
is now the guarded one rather than the dangerous one.

## Pre-flip checklist

Before setting `RLS_PREAUTH_ENFORCED=on`, confirm each item:

1. The guard
   (`backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py`) is green,
   i.e. the production `.unscoped` reader set still matches this reviewed
   allowlist exactly.
2. `cleanup_revoked_api_keys.py:91` is fixed: the cross-tenant read and delete are
   guarded by `SET LOCAL row_security = off`, like `inventory_api_keys`, and the
   loud-fail behaviour on the app role is proven by
   `backend/auth_tenancy/tests/test_cleanup_revoked_api_keys_rls_1184.py`.
   **Closed.** Still re-verify once against the live database before the flip, as
   item 3 requires.
3. `revoke_api_key.py:115,121` and `inventory_api_keys.py:357` are re-verified as
   loud-fail under a live `RLS_PREAUTH_ENFORCED=on` database (not just by
   inspection).
4. `AuthenticationService.create_api_key` / `list_api_keys` /
   `revoke_api_key` are re-verified as tenant-armed on every production call
   site.
5. The `UserRole` reader count is still zero (no new `UserRole.unscoped`).
6. R-7, R-8 and R-9 each have a tracking issue + owner + review date (AC-26).

Until items 1-5 hold and R-7/R-8/R-9 are scheduled, `RLS_PREAUTH_ENFORCED` stays
**off**. R-3 itself is no longer a flip blocker: the inventory above is complete
and the one reader that would have failed silently is guarded. What remains for
the flip are the verification items (3-5) and the scheduling of R-7/R-8/R-9, not
the reader inventory.
