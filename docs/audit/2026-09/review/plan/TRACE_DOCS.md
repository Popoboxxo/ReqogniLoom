---
type: PLAN
scope: audit-review-2026-09-trace-docs
status: final
date: 2026-10-01
author_agent: planner
epic: DOC — Traceability / Doku-Hygiene / i18n / CI / UI
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic DOC — Traceability, Doku-Hygiene, i18n, CI-Wahrheit, UI

> `204` ist FALSCH (stale Registerzeile) → nur Registerkorrektur, kein Produkt-Fix.
> Teil-FALSCH `006/016/021/088/153/234` → nur präzisieren.

## DOC-01 — Traceability-Matrix / ADR-Frontmatter / `refines` (P1, W2)

- **Findings:** 201, 325, 326, 328, 330–334, 339–344, 347–350
- **Ort:** `docs/se/traceability-matrix.md` (Zeilen u. a. `:59-60,103,114,120,131,231,257,304-312,331,390,433,483,512-513,521,701,721,724,728`);
  ADRs `docs/se/ADR/` (kein `open_adrs` in `docs/se`); `traceability/audit/hierarchy.py:172-186`
  (`refines` fehlt, Docstring `:34-38` veraltet); `baseline/services.py:430`,
  `delta_index_builder.py:288`, `frontend/src/utils/traceEndpoints.ts:72-75`
- **Zielverhalten:** Matrix-Zahlen/IDs sind kanonisch (`443` statt `511`, `116` statt `112`,
  `031` ergänzt, `REQ-L3`-Lücke und doppelte IDs dokumentiert); ADR-Frontmatter-
  Pflichtfelder ergänzt und Lifecycle-Status konsistent; `refines` als Built-in in den
  Hierarchie-Definitionen und im Docstring berücksichtigt (oder bewusst ausgeschlossen und
  dokumentiert); toter Verweis `349→070` entfernt.
- **Akzeptanz:** Matrix-`rg`-Stichproben liefern die kanonischen Werte; ADVs parsebar;
  `rg refines`-Status konsistent zu Kandidat (vi).
- **Test:** `validator`-Stichprobe + `rg`-Repro je Zahl.
- **Aufwand:** M · **Risiko/Rollback:** Doku-only. · **Deps:** ADR iii/v/vi (Matrix-Zusagen),
  DATA-01 (`REQ-L2-BL-011`-Status) · **ADR:** vi (teil)

## DOC-02 — i18n-Ratchet & Key-Vertrag (P1, W3)

- **Findings:** 300, 301, 002, 016, 303, 304, 302, 348
- **Ort:** `frontend/src/i18n-parity.test.ts:186,202-222` (`MISSING_KEY_BASELINE = 116`);
  Locale-Dateien; `NeedsEditors.tsx:264`
- **Zielverhalten:** **ADR (viii) entscheidet** Inline-Default/dynamische Keys; danach
  Ratchet auf 0 oder monoton sinkend; Locale-Ceiling = kanonische 116; tote Keys (536)
  abgebaut oder begründet; Matrix-Zusage ehrlich.
- **Akzeptanz:** Ratchet-Wert sinkt monoton in CI; ein neuer fehlender Key lässt den Test rot
  werden. · **Test:** Vitest (`i18n-parity`). · **Aufwand:** M · **Risiko/Rollback:**
  disruptive Default-Entfernung → Migrationsfenster. · **Deps:** ADR viii · **ADR:** viii

## DOC-03 — Test-/CI-Wahrheit (P1, W2)

- **Findings:** 193, 194, 195, 196, 198, 199, 200
- **Ort:** `ci.yml:44-55` (443 reproduziert); `.woodpecker.yml:61` (kein pytest);
  `test_e2e_sse_transport.py:349,353` (`skipif CI`); `test_llm_settings.py:248,255` (fixiert Modell);
  `useNotificationFeed.test.ts:57`
- **Zielverfahren:** Zahlen (`443`, `65` FE-Fehlschläge) werden **gemessen**, nicht behauptet;
  `pytest` in Woodpecker; CI-skip der SSE-Transporttests begründet/behoben; Modell-Fixierung
  entkoppelt.
- **Akzeptanz:** `pytest --collect-only` liefert 443 (oder korrigierte kanonische Zahl);
  `vitest run`-Ergebnis dokumentiert; CI führt pytest. · **Test:** CI-Lauf + Sammel-Lauf.
- **Aufwand:** M · **Risiko/Rollback:** CI-Erweiterung → reversibel. · **Deps:** — · **ADR:** —

## DOC-04 — UI/a11y-Highs (P2, W3)

- **Findings:** 003, 001, 005, 006, 008
- **Ort:** `NavigationShell.tsx:122-127` (kein Skip-Link); `useDashboardData.ts:47-53` (N+1);
  `ThemeManagementSection.tsx:275-295` (combobox ohne Name);
  `ApiKeysSection.tsx:224` (Widerruf-ConfirmDialog existiert — `006` Teil-FALSCH);
  `SidebarNavigation.tsx:570-576` (kein `scrollIntoView`)
- **Zielverhalten:** Skip-Link, accessible names, Fokus-Scroll, N+1 reduziert.
- **Akzeptanz:** Playwright-a11y-Smoke + Vitest; `006` nur als Registerpräzisierung.
- **Test:** e2e (gezielt) + Vitest. · **Aufwand:** M · **Risiko/Rollback:** gering ·
  **Deps:** — · **ADR:** —

## DOC-05 — Doc-Drift-Zahlen vereinheitlichen (P2, W3)

- **Findings:** 037, N5, 085, 086, 188
- **Ort:** `AGENTS.md:8,30,58` (215/31) vs. `README.md:77,1191` (35/25) vs. Manifest (219)
  vs. `.meta-config/project.yaml` (218); `pdf_report_generator.py:220`;
  `urls.py:51-52,59`
- **Zielverhalten:** Eine kanonische Tool-/Gruppen-Zahl (219/35) und arithmetisch korrekte
  Mirror-Doku; Modulpfad korrigiert.
- **Akzeptanz:** `rg` findet nur die kanonische Zahl in Produkt-Doku. · **Test:** Drift-Gate
  (`test_tool_manifest_drift.py`). · **Aufwand:** S · **Risiko/Rollback:** Doku-only ·
  **Deps:** DOC-01 · **ADR:** —

## DOC-06 — Register-Hygiene & Teil-FALSCH-Präzisierung (P2, W2)

- **Findings:** 204, 345/346, 088, 153, 234, 006, 016, 021, 071-§5, 129
- **Ort:** `AUDIT_FINDINGS.md` §3/§5; `REVIEW_*`-Evidenz
- **Zielverhalten:** Registerzeilen korrigiert: `204` FALSCH, `345`=Duplikat `123`,
  `346`=Duplikat `052`, `129` als „warnings⇒200, degraded⇒503, Cache/Worker/Beat fehlen",
  `071`-§5-Überschrift auf Savepoint-Ursache, `088`-Klammer, `153/234/006/016/021`
  präzisiert. **Kein Code-Fix** für widerlegte Findings.
- **Akzeptanz:** Keine widersprüchliche Registerzeile mehr; Critical-Zählung = 8 eigenständige.
- **Test:** Konsistenz-Lauf (`grep`/Review). · **Aufwand:** S · **Risiko/Rollback:** Doku-only ·
  **Deps:** — · **ADR:** —
