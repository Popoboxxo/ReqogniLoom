# W1 Integration Report

**Date:** 2026-10-02 · **Scope:** 2026-09 audit review, workstream W1
**Branch:** `chore/w1-integration` (LOCAL ONLY — no push, no tag)
**Base:** `chore/audit-review-2026-09` @ `510d75e2b772bcd595892dfdbd7a2b760d10c248`
**Integration head at report time:** 91a9da5239bc60926a629d6563bf4e6a48242651

## 1. Merged branches
| Order | Branch | Head | Merge commit |
|---|---|---|---|
| 1 | fix/authz-workspace-fence (SEC-02/03) | e4fd72d6 | 270c0a29 |
| 2 | fix/redis-throttle-health (RES-01/02) | 593de64c | 1a656ee0 |
| 3 | fix/health-contract-live-ready (RES-03/04/05) | 3d040834 | 3fab6b99 |
| 4 | fix/data-recovery-integrity (DATA-01..04) | 9b046814 | ea75f10f |
| 5 | fix/reqif-import-success (INT-01 + ADR-014) | 01aec396 | 4114ae1a |

## 2. Merge result
All five merges used `git merge --no-ff` and auto-merged cleanly (ort strategy; hunks are disjoint). No textual conflicts occurred. Content preservation was verified explicitly for the hotspots instead of trusting the auto-merge:
- `backend/reqogniloom/settings.py` — all four additive flag blocks coexist (SEC `AUTHZ_*`; RES1 `CACHE_SOCKET_*`/`CACHE_DNS_TIMEOUT`/`CACHE_UNHEALTHY_COOLDOWN` + CACHES options; RES2 `HEALTH_STRICT_READINESS`/`HEALTH_ALIAS_SUNSET`; INT `IMPORT_CONTRACT_V2`/`IMPORT_IDEMPOTENCY_*` + cleanup task).
- `backend/rest_api/views.py` — INT `ReqifImportView` v2 AND DATA `expected_version`/If-Match in Adr/Goal/MainGoal/ChangeRequest ViewSets.
- `backend/application/reqif_import_service.py` — DATA CAS writer `_apply_imported_workflow_state` (AUD-167/168) AND INT contract-v2 semantics + idempotency.
- `backend/application/tests/test_reqif_import_service.py` — INT contract-v2 tests AND DATA `version == 2` + history assertion.
- `deploy/docker-compose.yml` — RES2 celery-beat healthcheck/`memory: 768M` AND DATA backup offhost block; `.env.example` — RES1 cache vars AND DATA backup vars.
- `docs/audit/2026-09/review/plan/SECURITY_TRACK_EXECUTION.md` — identical on all branches. `backend/reqogniloom/celery.py` is not touched by any branch.
- `python -m py_compile` over all 67 changed `.py` files: 0 failures.
- Post-merge test-only commits (no production code changed): `db0a06a6`, `70e5c1c4`, `1b64f291` (cross-branch integration tests), `91a9da52` (3 targeted E2E specs).

## 3. Full suite on the merged head
### Backend `pytest -q` (docker overlay `deploy/docker-compose.yml` + `testing/docker-compose.test.yml`, service `backend-test`)
`10184 passed, 0 failed, 4 errors, 13 skipped, 1 xfailed` — total 10202, duration ~42:32 (pytest-reported 2552.53s).
- The 4 errors are the known pre-existing environmental SetupErrors in `mcp_server/tests/test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation` (missing demo-workspace seed) — unchanged, not W1-related.
- Reference: per-branch SEC run reported 10062 passed → +122, consistent with the merged integration head adding tests. No new failures.

### Frontend `npm test` (vitest run)
`2324 passed / 68 failed / 2392 total` (9 failing test files). INT-01 targeted files: 19/19 passed.
- Baseline on base `510d75e2`: `2319 passed / 66 failed` (8 files).
- → 66 of the 68 failures are PRE-EXISTING environmental failures (`localStorage` undefined in the jsdom/node test env; 6 files).
- The 2 extra failures on the integration head are in `src/test/ArtifactFormSaveShortcut.test.tsx` and were classified as a FLAKY jsdom microtask race, not a W1 regression: the file, its dependencies and config are byte-identical to base, and it passes 13/13 in isolation. No test was weakened.
- W1 introduced NO frontend regression.

### E2E (Playwright / Chromium, live stack)
`9 passed, 2 skipped, 0 failed`:
- `e2e/tests/csv-import.spec.ts` (existing) — 4 passed
- `e2e/tests/health-contract.spec.ts` (new) — 3 passed
- `e2e/tests/w1-authz-workspace-fence.spec.ts` (new) — 1 passed
- `e2e/tests/w1-import-outcome.spec.ts` (new) — 1 passed / 2 skipped. Reason: `IMPORT_CONTRACT_V2` defaults to `False` (ADR-014 §5 Phase 1) and is not set in the repo/compose env, so the v2 envelope + replay badge are not reachable from the browser; the skips state the remedy (set `IMPORT_CONTRACT_V2=True`, recreate backend).

## 4. Cross-branch interaction verification
1. **SEC-02/03 workspace fence × INT-01 REST ReqIF import** — covered by dedicated tests; live: a fence-scoped agent API key gets **403 PERMISSION_DENIED** importing into a foreign workspace (no write) and **200** in its own workspace.
2. **RES-03 health contract × Celery × Redis** — gap closed: prior tests stubbed `_check_redis`; 2 new tests exercise the real Redis probe. Live `GET /health/ready` → 200 with all five checks `ok` incl. `cache` and `celery_beat`; `manage.py check_celery_beat` → heartbeat ok.
3. **DATA-03 CAS (`expected_version`) × INT-01 savepoint/idempotency** — gap closed: stale `expected_version` during import → **409** with rollback (no mutation); idempotent replay returns `idempotent_replay: true` with identical counts and no revision/history re-bump.
No genuine regression was found in any combination; no production source change was required.

## 5. Residues filed as issues (GitHub `Popoboxxo/ReqogniLoom`)
- #1128 INT-01 hardening (HMAC→SHA-256, Deprecation/Sunset headers, hard tenant cap, guarded randomUUID)
- #1129 MCP goal-transition expected_version parity
- #1130 RES-01 TLS/`rediss://` + frozen-read gap
- #1131 SEC-02 intra-tenant 403-vs-404 oracle
- #1132 celery beat embedding preload (~407 MiB)
- #1133 test-stack demo-workspace seed (4 pre-existing SetupErrors)

## 6. Deviations, observations, open points
- Base tip deviation: the integration branch was created from the actual tip `510d75e2` (not `d5f0da36`, which is only the merge-base) so the 510d75e2 content is not re-introduced as a phantom conflict.
- 66 pre-existing frontend environmental failures + 1 flaky file are outside W1 scope; they are not fixed here and no test was weakened.
- `IMPORT_CONTRACT_V2=False` by default → new import-UI paths are not live-exercised.
- `gitleaks` was not on the default PATH for some tool environments; the verified pinned v8.30.1 binary was prepended to PATH for the e2e/report commits (hook ran and passed — no bypass). Durable fix: install gitleaks on PATH.
- `.kimi-code/` and `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` intentionally remain untracked.
- No push / no tag; all work is local.

## 7. Verdict
Integration head is merge-ready for the W1 scope: all five branches integrate cleanly, the backend suite is green apart from the known environmental seed errors, cross-branch combinations verified (unit + live), and E2E green. Open (non-blocking) items are the filed residues #1128–#1133 plus the pre-existing frontend test-environment failures. Release-readiness for W1 = YES (local branch `chore/w1-integration`).

---
FINAL REPORT COMMIT: 037479959214f35575fd69e31f6eae7c7e70cd49
