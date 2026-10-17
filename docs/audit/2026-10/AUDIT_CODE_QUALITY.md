# Audit Code Quality — 2026-10-15

Scope: backend `backend/**/*.py` (Ruff 0.17.0), frontend `frontend/src/**/*.{ts,tsx}` (ESLint) + `tsc --noEmit`. Commands:
- `ruff check backend --output-format json`
- `cd frontend && npx eslint src --format json`
- `cd frontend && npx tsc --noEmit -p tsconfig.json`

## Summary
- Backend Python: 7292 findings / 1096 files
- Frontend TypeScript: 298 findings / 708 files
- TypeScript typecheck: 0 errors (clean)
- Notable: backend findings are dominated by automated modernization (`UP*`, `I001`, `RUF*`), not functional defects.

## Backend top rules (Ruff)
| Rule | Count | Meaning |
|---|---:|---|
| UP006 | 1862 | legacy typing aliases (`List`, `Dict`, etc.) |
| UP045 | 1290 | `Optional[X]` -> `X \| None` |
| RUF012 | 832 | mutable class attributes |
| I001 | 575 | import sorting |
| UP035 | 452 | deprecated typing imports |
| RUF059 | 372 | unused unpacked variables |
| SIM117 | 315 | nested `with` statements |
| F401 | 253 | unused imports |
| BLE001 | 241 | broad exception catches |
| RUF100 | 235 | unused noqa directives |
| UP037 | 207 | quoted type annotations |
| RUF022 | 152 | `__all__` sorting |
| UP017 | 112 | datetime UTC alias |
| C408 | 70 | dict literal vs constructor |
| F841 | 59 | unused locals |
| RUF013 | 38 | implicit Optional |
| F811 | 37 | redefinition of unused name |
| ISC004 | 33 | implicit string concat |
| S110 | 27 | `try/except/pass` |
| UP007 | 18 | union type modernization |

## Backend hotspots (most findings)
1. backend/rest_api/views.py — 134
2. backend/llm_adapter/providers.py — 126
3. backend/application/management/commands/migrate_se_docs.py — 121
4. backend/application/import_service.py — 102
5. backend/traceability/audit/hierarchy.py — 85
6. backend/mcp_server/tool_registry.py — 73
7. backend/application/reqif_export_service.py — 66
8. backend/persistence/models.py — 64
9. backend/mcp_server/tools/cross_cutting.py — 63
10. backend/mcp_server/protocol_handler.py — 62
11. backend/application/ai_derivation_service.py — 59
12. backend/application/search_service.py — 57
13. backend/mcp_server/tests/ratchet_framework.py — 57
14. backend/application/baseline_facade.py — 56
15. backend/application/requirement_service.py — 56

## Frontend top rules (ESLint)
| Rule | Count |
|---|---:|
| @typescript-eslint/no-explicit-any | 275 |
| react-hooks/exhaustive-deps | 7 |
| jsx-a11y/no-static-element-interactions | 7 |
| jsx-a11y/label-has-associated-control | 5 |
| jsx-a11y/click-events-have-key-events | 3 |
| jsx-a11y/role-has-required-aria-props | 1 |

Frontend files with findings: 708. `tsc --noEmit`: 0 errors.

## Frontend hotspots (most findings)
1. frontend/src/test/ArchitectureEditors.test.tsx — 32
2. frontend/src/test/RequirementEditors.test.tsx — 26
3. frontend/src/components/Reviews/ReviewsView.test.tsx — 24
4. frontend/src/components/TestRuns/TestRunsList.test.tsx — 19
5. frontend/src/components/ArtifactDiff/ArtifactDiff.smoke.test.tsx — 18
6. frontend/src/components/TraceabilityView/TraceabilityView.smoke.test.tsx — 18
7. frontend/src/components/IcdView/IcdView.smoke.test.tsx — 11
8. frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.test.tsx — 11
9. frontend/src/test/useBundleCompressionStatus.test.ts — 10
10. frontend/src/components/AdrEditors/useAdrData.test.tsx — 9

## Assessment
- High volume, low semantic risk: majority are modernization/style issues addressable via autofix (`ruff check --fix`, `ruff format`).
- Real quality risks to address deliberately:
  - 241 broad exception catches (`BLE001`) in backend, especially in I/O/service paths.
  - 253 unused imports / 59 unused locals indicating possible dead paths or failed refactors.
  - 37 duplicate redefinitions (`F811`) can hide real bugs.
  - 27 `try/except/pass` (`S110`) silently swallowing errors.
  - Frontend: 275 explicit `any` reduce type safety, plus 7 hook dependency warnings that can cause stale closures.
  - A11y interaction issues concentrated in UI components and tests (16 total).

## Recommended next slices
1. Python autofix modernization (`UP*`, `I001`, `UP035`, `RUF022`) in separate PR; avoid hand edits.
2. Manually review `BLE001`, `S110`, and `F811` hotspots, prioritizing `rest_api`, `application`, and `mcp_server`.
3. Frontend: replace `any` incrementally (start hotspots/tests), fix hook dependency warnings.
4. Re-run after autofix to establish lowered baseline and ratchet.

## Post-autofix baseline (W17 Slice 1) — frozen 2026-10-17

Measured on branch `fix/w17-autofix-modernization` (base `origin/main @ 12cce237`),
Ruff 0.17.0 (autofix run; re-measured with 0.17.1 — identical counts), scope
`backend/**/*.py`, safe fixes only (`ruff --fix`, no `--unsafe-fixes`):

| Command (in `backend/`) | Before | After (frozen) |
|---|---:|---:|
| `ruff check . --select UP,I001,RUF022` | 4686 | **34** |
| `ruff check . --select F401` | 253 | **243** |
| `ruff check .` (project default rule set) | 7294 | **2632** |

Per-rule before → after of the autofix selector set (residuals have no *safe* fix):

| Rule | Before | After | Residual reason |
|---|---:|---:|---|
| UP006 | 1862 | 0 | — |
| UP045 | 1291 | 1 | fix only unsafe (comment inside annotation) |
| UP035 | 452 | 0 | — |
| UP037 | 208 | 0 | — |
| UP017 | 112 | 0 | — |
| UP007 | 18 | 2 | fix only unsafe (comment inside annotation) |
| UP042 | 8 | 8 | no stable fix (`str`-Enum → `StrEnum`, behavior-relevant) |
| UP031 | 7 | 7 | no stable fix (percent-format) |
| UP028 | 1 | 1 | no stable fix (`yield from`) |
| I001 | 575 | 0 | — |
| RUF022 | 152 | 15 | fix only unsafe (`__all__` entries carrying comments) |

**F401 note:** the UP006/UP017/UP035 rewrites orphaned 586 imports
(`typing.*` names, `datetime.timezone`, `collections.abc.*`); they were removed in the
same change set, plus 5 pre-existing dead `typing` imports — hence 253 → 243. The 243
remaining F401 findings are pre-existing and intentionally untouched (re-export risk,
hand-review slice). Observed non-selected-rule deltas under `--select ALL`: TC003
+121 (typing-only stdlib imports; rule not enabled by the project config), E501 −10,
PLC0415 +3 (isort split/merge of local imports, same symbols).

Ratchet intent: the "After" numbers are ceilings (analogous to the i18n baselines) —
they may be lowered freely; raising one requires a documented justification. No CI
wiring in this slice.

## Post-hand-review baseline (W17 Slice 2) — frozen 2026-10-17

Measured on branch `fix/w17-manual-rules` (base `origin/main @ 378a094d`, i.e.
including the Slice-1 autofix), Ruff 0.17.1, scope `backend/**/*.py`:

| Command (repo root) | Before | After (frozen) |
|---|---:|---:|
| `ruff check backend/ --select BLE001` | 241 | **0** |
| `ruff check backend/ --select S110` | 27 | **0** |
| `ruff check backend/ --select F811` | 37 | **0** |
| `ruff check backend/ --select F821,F822` | 0 | **0** (re-checked on all touched files) |

Composition of the three rule sets (no finding was removed by a blanket
file-level ignore; every suppression is a per-site `# noqa` with an English
reason):

| Rule | Narrowed to specific exception types | Replaced by assertion | Log-and-continue (broad kept, logged) | Fixed by adding `logger.exception` | Justified `# noqa` |
|---|---:|---:|---:|---:|---:|
| BLE001 | 40 | 1 | 8 | 5 | **187** |
| S110 | 8 | 1 | 7 | — | **11** (carry `BLE001, S110`) |
| F811 | 37 fixed structurally (see below) | | | | 0 |

Each row sums to the observed baseline (241 / 27 / 37). The net
`# noqa`-line delta for `BLE001` is 186 because one pre-existing
`# noqa: BLE001` (in `auth_tenancy/admin_lockout.py`) was deleted when that
handler was narrowed — the finding it used to hide was S110-only, so it never
appears in the 241.

"Log-and-continue" here means the broad catch was kept and the handler now
logs with `exc_info=True` — ruff exempts such handlers from `BLE001`/`S110`,
so no suppression is needed (version reconstruction probes, ADR-title
fallback, preset-gate fail-open, PDF terminology fallback).

F811 detail (all findings were test-fixture/import artefacts, none masked a
production bug): 11 sites resolved with the PEP 484 explicit re-export idiom
(`from x import fixture as fixture`, silences the parameter-shadowing
redefinition) in `admin_ops/tests/conftest.py` + 3 admin_ops test modules;
19 redundant fixture/import re-declarations removed (`mcp_server/tests/
test_e2e_performance.py` 17 — fixtures are auto-discovered from the sibling
`conftest.py`; `application/tests/test_requirement_service.py` 2 — genuinely
unused `unittest.mock.call` import); 7 auto-fixable redundant local imports
removed via `ruff check --select F811 --fix` (`baseline`,
`se_metrics` tests).

BLE001/S110 justification patterns (the reasoning behind the larger `# noqa`
set, all one-line English reasons in the code):

- **REST error boundary** (106 in `rest_api/views.py` + 14 in
  `rest_api/icd_views.py` + 2 in the workflow-transitions mixin + 1 in
  `rest_api/openapi.py`): the catch-all exists to map *unknown* errors to the
  structured 500 contract; the shared helpers (`_service_error_response`,
  `_internal_error`, `_edit_error_response`) log the real cause and mask the
  client-facing message (CWE-209, fix #108). Narrowing per site is impossible
  by design; logging twice (`logger.exception` + helper) was rejected.
- **Auth-context probes** (31 sites narrowed instead: 10 in `rest_api`
  config/metrics views, 8 in `admin_ops/theme_rest.py`, 13 in
  `memory/memory_rest.py`): `get_auth_context()` raises exactly
  `rest_framework.exceptions.NotAuthenticated`; narrowed to that type, auth
  failures still answer 401 and real errors now surface.
- **Fail-open/closed probes and degrade paths** (memory settings/health cache,
  preset gates, RBAC role resolution, embedding adapters, webhook delivery,
  metrics counters): breadth is contractual ("total function", documented
  fail-open for preset/auth-is-the-hard-gate, ADR-016 fail-closed recording,
  best-effort caches); each site keeps its defined direction (fail-open stays
  fail-open, fail-closed stays fail-closed) and logs.
- **`_remap_*_exc` re-raise sites** (`baseline_facade`, `workflow_facade`):
  the handler always re-raises a remapped domain exception — ruff cannot prove
  that across functions, hence the reasoned noqa.
- **Noqa-typo fix:** `application/requirement_service.py` carried
  `# noqa: BLE0001` (invalid code — suppression never applied); corrected to
  `BLE001` with a reason.

Notable non-`noqa` improvements made on the way (no behavior intended beyond
exception/logging semantics):

- 5 silent static-500 handlers (`rest_api/audit_views.py` ×2,
  `rest_api/architecture_decompose_views.py` ×2,
  `rest_api/traceability_suggest_views.py` ×1) now log via `logger.exception`
  before answering the masked 500 — they previously dropped the cause entirely
  (`audit_views` already had the same fix documented for a sibling handler).
- `application/tests/test_event_bus.py` retry-bookkeeping test absorbed the
  expected dispatch exception with `try/except/pass` (could pass vacuously);
  now asserts it via `pytest.raises`.
- `rest_api/api_key_views.py` revoke mapped *any* error to `404 Key not
  found`; narrowed to the service's typed `AuthenticationFailed` (404 contract
  preserved, real failures now surface). The stale test was updated with it:
  the 404 test now mocks `AuthenticationFailed("invalid_api_key")`, and a new
  test pins that an unexpected error propagates instead of being masked.
- Version reconstruction probes (`baseline/version_reconstructor.py`) and
  preset-gate fail-open (`baseline/delta_index_builder.py`) now log their
  degradation at debug/warning instead of staying silent; the ADR-title
  fallbacks (`application/artifact_service.py`,
  `context_graph/generators/glossary.py`, `traceability/service.py`) log at
  debug with `exc_info` analogously.

No real product bug was found behind any of the 305 findings (F811: test
artefacts only; S110/BLE001: deliberate boundaries and documented degrade
paths). The fixes above are observability/test-rigour corrections.

Tests (docker overlay `deploy/docker-compose.yml` +
`testing/docker-compose.test.yml`, `LLM_PROVIDER=mock`; `MEMORY_BACKEND=pgvector`
where the dev default `honcho` is not DNS-resolvable from the test container):
~3.9k backend tests green across the touched modules and broad slices —
`admin_ops`, `application` (43 targeted files incl. all touched services),
`rest_api` (26 targeted files), `mcp_server` (21 targeted files incl. the slow
perf suite), `memory`, `presets`, `audit`, `context_graph`, `resilience`,
`llm_adapter`, `baseline`, `workflow` (signature/force-transition),
`auth_tenancy` (lockout/auth), `traceability` (service/pdf/rule-engine),
`persistence` slices. One pre-existing, environment-dependent failure:
`application/tests/test_interview_service.py::...test_prompt_includes_memory_
context_when_memory_exists` fails on the dev-default honcho backend (DNS) and
passes with `MEMORY_BACKEND=pgvector`; unrelated to this slice (comment-only
changes in the path). `python manage.py check`: no errors (1 pre-existing
`application.W001` config warning).

Ratchet intent (unchanged): the "After" numbers are ceilings; lowering is free,
raising requires a documented justification. No CI wiring in this slice.

