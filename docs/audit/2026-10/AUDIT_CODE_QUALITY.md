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
