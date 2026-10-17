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

