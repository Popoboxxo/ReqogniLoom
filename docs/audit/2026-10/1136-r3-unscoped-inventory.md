# R-3 — Inventory of `.unscoped` readers of `ApiKey` / `UserRole`

- **Issue:** #1184 (spec residual R-3 of #1136)
- **Spec:** [`docs/audit/2026-10/1136-rls-coverage-spec.md`](./1136-rls-coverage-spec.md)
  — risk entry **R-3** (line 668) and the addendum note at lines 830-833.
- **Static guard:**
  [`backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py`](../../../backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py)
- **Status:** documentation + static guard only. No policy change, no production
  behaviour change, no flag flip.

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
| `ApiKey` | `backend/auth_tenancy/management/commands/cleanup_revoked_api_keys.py:57` | `Command.handle` | READ (`filter(revoked_at__isnull=False, revoked_at__lt=cutoff)`) then DELETE (`stale.delete()`) | **no** — cross-tenant maintenance, no tenant context and no `row_security` guard | **SILENT-EMPTY — the one dangerous reader** (see below) |
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

## The dangerous path: `cleanup_revoked_api_keys.py:57`

`Command.handle` is the single R-3 reader that would fail **silently** under
`RLS_PREAUTH_ENFORCED=on`:

- it runs from the CLI with **no tenant context** armed, and
- unlike `inventory_api_keys.collect_inventory`, it has **no**
  `SET LOCAL row_security = off` guard.

With the flag on, the staged policy predicate on `at_api_key` reduces the
cross-tenant queryset to zero rows. Consequently:

- `stale.count()` returns `0` (dry run prints "0 revoked API key(s) … would be
  deleted"), and
- `stale.delete()` returns `0` (with `--apply` it prints "Deleted 0 revoked API
  key(s)") —

both without any error or warning. The command reports success while doing
nothing. This is the concrete silent-empty consequence R-3 warns about, and it
must be resolved (or the read reworked to escape the policy the same way
`inventory_api_keys` does) before the flag is flipped.

## Pre-flip checklist

Before setting `RLS_PREAUTH_ENFORCED=on`, confirm each item:

1. The guard
   (`backend/auth_tenancy/tests/test_unscoped_readers_guard_1184.py`) is green,
   i.e. the production `.unscoped` reader set still matches this reviewed
   allowlist exactly.
2. `cleanup_revoked_api_keys.py:57` is either fixed (tenant-scoped /
   `SET LOCAL row_security = off` guarded, like `inventory_api_keys`) or
   explicitly reclassified with a loud-fail behaviour. **This is the remaining
   blocker.**
3. `revoke_api_key.py:115,121` and `inventory_api_keys.py:357` are re-verified as
   loud-fail under a live `RLS_PREAUTH_ENFORCED=on` database (not just by
   inspection).
4. `AuthenticationService.create_api_key` / `list_api_keys` /
   `revoke_api_key` are re-verified as tenant-armed on every production call
   site.
5. The `UserRole` reader count is still zero (no new `UserRole.unscoped`).
6. R-7, R-8 and R-9 each have a tracking issue + owner + review date (AC-26).

Until items 1-5 hold and R-7/R-8/R-9 are scheduled, `RLS_PREAUTH_ENFORCED` stays
**off** — R-3 stays a documented, tracked pre-flip task.
