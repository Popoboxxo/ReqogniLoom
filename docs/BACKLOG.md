# ReqFlow — Offene Anforderungen & Blocker

> Generiert: 2026-06-30 | Branch: `feat/se-implementation`

## Top-Priorität (Bugs)

| REQ-ID | Titel | Status | Nächste Aktion | Blocker |
|--------|-------|--------|----------------|---------|
| `REQ-L3-AS005-004` | TraceLink 404 Resolution | Phase 0 done (REQ-Swap + History-Rewrite), Phase 1-7 pending | SE-Kaskade: se-requirements → ... → se-testreviewer | Docker |
| `REQ-L1-028` | ICD expected_version 500 | Offen (Commit `c76d90f`) | SE-Kaskade starten | Docker |
| `REQ-L1-007` | Baseline-Preset 404 | Offen (Commit `d90d905`) | SE-Kaskade starten | Docker |

**Hierarchie-Notiz:** `REQ-L3-AS005-004` ist L3-Bugfix unter `COMP-AS-005` (TraceLinkService), abgeleitet von `REQ-L2-AS-010`. `REQ-L1-031` (Metrikmodul) ist eine separate, gültige L1-Anforderung — nicht verwechseln.

## Infrastruktur

- [ ] **Docker Desktop starten** → Test-Gate re-runnen (pytest Backend + npm test Frontend + Playwright E2E `waterkettle-scenario.spec.ts`)
- [ ] **Phase 8-9 (se-validator + se-verifier)** für alle 3 Bugs nach grünem Test-Gate
- [ ] **Push auf Remote** `feat/se-implementation` (Push-Gate: erst nach SE-Implementation + Tests grün)

## UI/UX — SE-Masken

- [ ] **REQ-L1-040**: SE-Entity-Masken Vereinheitlichung (Konsistenz über 13 Entitätstypen hinweg)

## Optional / Non-urgent

- Optionale Korrektur `af149c8`: refactor-Bundle in 4 separate `feat(REQ-L2-RF-019..022)` Commits aufsplitten — User hat akzeptiert, nicht akut
