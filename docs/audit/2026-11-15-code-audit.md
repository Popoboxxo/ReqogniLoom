# Code-Audit ReqogniLoom — 2026-11-15

Stand: main = 0d8bdbc4, nach Abschluss der Roadmap-Phasen A–H und der Release-/Inspector-/Honcho-Folgearbeiten. Audit über ruff, npm audit, graphify diagnose multigraph, pytest (Backend/Frontend/E2E-Shards) und die vorhandene Gate-Suite. Keine Code-Änderung in diesem Dokument.

## 1. Zusammenfassung

| Bereich | Befund | Schwere |
|---|---|---|
| Lint Backend | 59 x F841 (unused locals), 0 x F821/F822 | P3 |
| Lint Frontend | 0 Errors, 71 Warnings (vorbestehend: no-explicit-any in Tests) | P3 |
| Security npm | 15 Advisories: 1 critical (dompurify), 2 high (undici, zod) | P2 |
| Security pip | pip audit nicht verfuegbar | P2 |
| Architektur | 57.000 Nodes, 128.387 Edges, 2.262 Communities; keine Collapse-Risiken, 2 Self-Loops | P3 |
| Tests | Backend 4 CI-Sets gruen, Frontend 3.615, E2E 417/418 | P0 (gruen) |
| Offene Issues | 5 (#1230, #1247, #1762, #1792, #1793) + 3 Live-Issues (#1823-1825, davon 2 behoben) | — |
| Vorschlaege | V1, V8 offen; V2 geratcht; V4/V6 triagiert; V3/V5/V7/V9 erledigt/entfaellt | P3 |

> **Abarbeitungsstand:** Die Befunde in Abschnitt 1, 4 und 5 sind zum Teil bereits geschlossen. Status je Befund mit Beleg: siehe **§8 Abarbeitung**.

## 2. P0 — Funktionalitaet (gruen)

- Roadmap A–H vollstaendig: #1670, #587, #879, #1564, #1578, #1374, #1701 geschlossen; Release-Kaskade (ADR-028) mit Async-Pfad (#1804), REL-P1 (#1805), Inspector M1–M8 (#1762 implementiert)
- Honcho-Degradation (#1823/#1824) behoben: Write 500 -> 503, Readiness dreiwertig
- Inspector-Kommentare (#1763): Entity-ID vs. Artifact-UUID korrigiert, incl. Backend-DTO-Ergaenzung
- Live-Lauf 2026-11-14: 417/418 E2E gruen, Honcho healthy, interne KI beam-free bewiesen

## 3. P1 — Funktional und UX (offen)

| # | Befund | Empfehlung |
|---|---|---|
| 1 | DoD-10-Visuelle Pruefung (1440/1024/768/320 px) fuer Inspector M1–M8 nicht durchgefuehrt (kein Stack) | Live-Stack starten, Pruefung + Baseline-Refresh |
| 2 | Inspector-UX bei 1280 px: Sheet legt das Formular `inert` (spec-konform, aber ungluecklich) | Sheet default zu oder inert nur auf den verdeckten Bereich |
| 3 | #1825 waterkettle Phase 1b: 17 statt 18 Requirements | Trace auswerten, robuste Wartebedingung |
| 4 | V6-Luecke: `?level=`-Filter fehlt in der UI (Backend vorhanden) | Issue + kleiner Frontend-Slice |
| 5 | V1: einheitliche Fehler-/Leerzustaeende je Liste | Mechanischer Frontend-Slice |
| 6 | V8: Gherkin-Parser + Schritt-Ergebnisse im TestRun | baut auf #1564 |

## 4. P2 — Security und Betrieb

### 4.1 Frontend-Dependencies (npm audit)

15 Advisories, davon 3 high/critical:

- **dompurify** (critical) — XSS-Sanitizer, used for Markdown rendering
- **undici** (high) — HTTP client, DoS via EventSource parser
- **zod** (high) — Schema validation

Alle sind transitive Abhaengigkeiten (vitest, katex, @typescript-eslint). `npm audit fix` ist verfuegbar, `--force` fuer minimatch-Kette.

> **Status:** abgearbeitet — `npm audit` = 0 (PR #1860). Siehe §8.

### 4.2 Backend-Dependencies

`pip audit` ist im Stack nicht installiert. Empfehlung: `pip-audit` in die CI aufnehmen (analog npm audit). Bekannte Risiken: openai/anthropic SDKs, honcho-ai, sentence-transformers (torch) — sollten auf CVEs geprueft werden.

> **Status:** teilweise — CI-Gate existiert als PR #1865, noch nicht gemergt. Siehe §8.

### 4.3 Betriebs-Funde aus dem Live-Lauf

- `LLM_API_KEY` ist in `.env` leer; `LLM_OPENCODE_SESSION` steht auf dem `.env.example`-Platzhalter — der Preflight blockiert damit jeden echten KI-Start. Dokumentation/Deployment-Check ergaenzen.
- Honcho ohne Embedding-Provider: Write 500 (behoben: #1823), Readiness 503 (behoben: #1824) — aber Embeddings bleiben unverfuegbar, Honcho ist damit funktional eingeschraenkt.
- `page_size`-Kleinkram (#1761) behoben.

## 5. P3 — Code-Qualitaet und Wartung

### 5.1 Lint

- **Backend:** 59 x `F841` (unused locals) — kosmetisch, keine F821/F822 (undefinierte Namen). Ruff-Gate prueft nur F821/F822, daher gruen. Aufraeumen in einem `chore`-Commit.

  > **Status:** abgearbeitet — 0 Funde (PR #1862). Siehe §8.
- **Frontend:** ESLint 0 Errors, 71 Warnings (vorbestehend: `no-explicit-any` in Test-Mocks). Neue Dateien aus #1763/#1564 haben keine neuen Warnings.

### 5.2 Architektur (graphify)

- 57.000 Nodes, 128.387 Edges, 2.262 Communities
- Keine Edge-Collapse-Risiken, 2 Self-Loops (minor)
- God-Nodes (hochgradige Knoten) sollten geprueft werden auf zu starke Kopplung
- Der Graph ist lokal unter `graphify-out/` und gitignored

### 5.3 Offene technische Schulden

- `variant="panel"`-Zweig der vier Panels (Trace/Diff/Version/Comment) ist toter Produktionspfad nach M5–M8; Tests decken ihn noch ab. Aufräumen als `refactor`.
- `released_tier_key` ist read-only im Serializer, aber fehlt in ChangeRequest-DTO (`artifact_id`-Paritaetsluecke, analog #1763).

  > **Status:** `artifact_id` geschlossen (PR #1864); `baseline_id` bleibt offen. Siehe §8.
- `AttributeDefinition`-Bootstrap introspektiert neue Modellfelder automatisch; bei neuen Feldern muessen Labels und Read-only-Klassifikation nachgezogen werden (Gates fangen das, aber es ist manuelle Arbeit).
- `ui-ratchet`-Baseline: 74 hartcodierte Farb-Literale in 14 Dateien (dokumentiert, Abbau bei Gelegenheit).

  > **Status:** 43 Literale in 9 Dateien (PR #1863); weitere Reduktion in PR #1866 offen. Siehe §8.

## 6. P4 — Testabdeckung und CI

- **Backend:** 4 CI-Sets, ~11.000 Tests; letzter Lauf 3.758 + 323 + 442 + 603 + 941 = alle gruen
- **Frontend:** 3.615 Tests (Vitest 5), 0 Failures
- **E2E:** 417/418 Playwright (67 Specs, 4 Shards); 1 bekannter Failure (waterkettle 17/18, behoben in #1830, aber noch nicht live verifiziert)
- **Gates:** Manifest-Drift (293 Tools), Doc-Surface-Consistency, Meta-Tool-Count, Schema-Completeness, RLS-Coverage — alle gruen

### Empfohlene naechste Schritte

> **Status 2026-11-15/16:** Nr. 1, 3 und 4 abgearbeitet (#1860/#1862/#1864 — Nr. 3 zusaetzlich teilweise via #1863); Nr. 2 offen, CI-Gate liegt als nicht gemergter PR #1865 vor; Nr. 5–6 unveraendert offen. Siehe §8.

1. **npm audit fix** (dompurify, undici, zod) — pruefen auf Breaking Changes
2. **pip-audit in CI aufnehmen** — Backend-Dependencies sind aktuell ungeprueft
3. **Ruff F841 bereinigen** — `chore`-Commit, 59 Funde
4. **#1763-Backend-Luecke fuer ChangeRequest** schliessen (artifact_id im DTO)
5. **DoD-10 visuelle Pruefung** mit Live-Stack (1440/1024/768/320 px)
6. **waterkettle 17/18** live verifizieren (Fix ist analytisch, aber nicht live getestet)

## 7. Nicht geprueft

- **Performance:** kein Profiling durchgefuehrt; Big-O-Bottlenecks nicht geprueft
- **Accessibility (WCAG):** keine ARIA-/Keyboard-/Screen-Reader-Pruefung ueber die automatisierten Ratchet-Tests hinaus
- **Datenbank-Performance:** keine Query-Analyse (N+1, fehlende Indizes)
- **E2E vollstaendig:** nur 417/418, der waterkettle-Fall ist offen
- **Security-Pentest:** statische Analyse (OWASP) wurde nicht separat ausgefuehrt
- **Honcho-Write-Pfad:** nach Fix (#1823) nicht live getestet

## 8. Abarbeitung (Stand 2026-11-15/16)

Dieser Abschnitt ist ein **Nachtrag** und aendert die Befunde oben nicht: die Abschnitte 1–7 dokumentieren unveraendert den Audit-Stand vom 2026-11-15. Hier steht, was davon inzwischen erledigt ist, mit welchem Beleg — und was bewusst offen bleibt.

Bezugsstand der Gegenpruefung: `origin/main` = `582cc08` (Merge von #1864). Geprueft wurden die betroffenen Dateien selbst (`frontend/package.json`, `frontend/src/test/hardcoded-styles.test.ts`, `backend/application/change_request_service.py`, `.woodpecker.yml`) sowie die PR-Beschreibungen; `ruff`/`npm audit` wurden **nicht** lokal ausgefuehrt, die Zahlen stammen aus den PR-Verifikationen plus der genannten Dateipruefung.

| Befund (Abschnitt) | Status | Beleg |
|---|---|---|
| `npm audit`: 15 Advisories, 1 critical (dompurify), 2 high (undici, zod) (§1, §4.1) | **abgearbeitet** — `npm audit` = 0 | **#1860** (gemergt, `c6374e2`): dompurify 3.4.17, undici 8.12.3 und zod 4.6.7 waren auf main bereits gepatcht, die Audit-Notiz war an dieser Stelle veraltet; offen war nur die `minimatch`-Kette (moderate, dev-only). `npm audit fix` (eslint 10.14 -> 10.15, `@eslint/config-array` 0.23.5 -> 0.23.6) plus verschachtelter Override `@typescript-eslint/typescript-estree -> minimatch ^11.0.8` in `frontend/package.json`; kein `--force`, kein `--legacy-peer-deps`. Gegengeprueft in `frontend/package.json` (dompurify `^3.4.17`, undici-Override `^8.12.3`, minimatch-Override vorhanden). |
| 59 x Ruff `F841` (§1, §5.1) | **abgearbeitet** — 0 Funde | **#1862** (gemergt, `389972b`): 9 Produktions- und 50 Test-Bindings entfernt; in Produktion bleibt der Aufruf stehen, wo er Guard/Seiteneffekt ist, in Tests bleiben Factories/Service-Calls. Kein `noqa`, keine `per-file-ignores`, keine ausgenommene Datei. `ruff check --select F841` = 0, F821/F822-Gate unveraendert gruen. |
| 74 hartkodierte Farb-Literale in 14 Dateien (§5.3) | **teilweise abgearbeitet** — 43 Literale in 9 Dateien | **#1863** (gemergt, `d739d46`): 31 Literale auf Design-Tokens umgestellt, 4 neue Layer-1-Alpha-Tokens (`--palette-indigo-500-a20/-a25`, `--palette-red-500-a10/-a40`), 5 tote `var(--token, #hex)`-Fallbacks entfernt; Baseline in `frontend/src/test/hardcoded-styles.test.ts` entsprechend gesenkt. Gegengeprueft: Summe der `BASELINE`-Eintraege = 15 + 1 + 2 + 1 + 18 + 1 + 1 + 3 + 1 = **43** ueber **9** Dateien. Die 43 sind dokumentierte Ausnahmen: Fabric.js-Canvas (19: `CanvasEditor.tsx` 15, `use-canvas-tool-settings.ts` 2, `canvas-geometry.ts` 1, `CanvasEditor.module.css` 1), ASIL-Skala (18: `utils/asilUtils.ts`), uebrige Single-Site-Alphas (5: `WorkflowEditor.module.css` 3, `DiagramGraphEditor.module.css` 1, `Dialog.module.css` 1), Containment-Farbe (1: `GraphEdge.tsx`). Der PR-Text nennt die Canvas-Gruppe mit 18 und die Single-Site-Alphas mit 6 — der Canvas-Frame-Schatten in `CanvasEditor.module.css` ist je nach Zaehlweise Canvas- oder Single-Site-Fall; die Gesamtsumme 43 ist in beiden Zaehlweisen identisch. |
| ASIL-Totcode `getAsilColor()` / `getAsilBadgeStyle()` (Nebenbefund zu #1863) | **offen** — PR nicht gemergt | **#1866** (offen, Branch `chore/remove-asil-colour-helpers`): entfernt beide Funktionen samt Baseline-Eintrag. Auf `main` gilt daher **weiterhin 43** (der Eintrag `utils/asilUtils.ts` mit `count: 18` steht noch in `hardcoded-styles.test.ts`); nach einem Merge waeren es **25 Literale in 8 Dateien**. |
| `ChangeRequest.artifact_id` fehlt im DTO (§5.3) | **geschlossen** | **#1864** (gemergt, `582cc08` = aktueller main-HEAD): Ursache war nicht nur der Serializer, sondern der gemeinsame Response-Builder `_cr_to_dict()`, den alle CR-Pfade nutzen. Das Feld ist jetzt im Serializer (read_only, allow_null), im DTO-Builder, im Service-`ChangeRequestDTO` und im Frontend-Typ; MCP lieferte es bisher nur zufaellig und ist jetzt gepinnt. Bewusst read-only, weil das Artefakt serverseitig per `ensure_artifact` entsteht. Regressionstests fuer POST/detail/list (REST), Service-DTO und MCP read/query; keine Migration, Tool-Zahl unveraendert, Manifest-Drift-Gate gruen. Gegengeprueft in `backend/application/change_request_service.py` (`artifact_id: UUID \| None = None` im DTO, inkl. `from_orm`). |
| `pip audit` nicht verfuegbar / fehlendes Dependency-Gate (§4.2, §6 Nr. 2) | **offen** — CI-Job existiert als PR, nicht gemergt | **#1865** (offen, Branch `ci/dependency-audit-gates`): ein Job „Dependency Audit (npm + pip-audit)“ — Frontend `npm audit --audit-level=high --json` (critical/high blockieren, moderate/low nur in der Job-Summary, bewusst ohne `--omit=dev`), Backend `pip-audit -r requirements.txt --strict` in einer Wegwerf-venv, Version gepinnt (2.10.1); `--strict` = fail-closed, wenn eine Abhaengigkeit nicht aufloesbar ist. Baseline: **145 Backend-Pakete / 676 Frontend-Pakete, 0 Findings**; beide JSON-Reports als Artefakt; die alten Ad-hoc-Scans in `frontend-test`/`backend-test` entfallen. Auf `main` laufen bis zum Merge weiter die alten Scans (`ci.yml`: `pip install pip-audit` ungepinnt, `npm audit` im Frontend-Job). |

### 8.1 Weiterhin offen

- **DoD-10-Sichtpruefung** (1440/1024/768/320 px, §3 Nr. 1): braucht einen laufenden Stack und ist damit nicht dokumentierbar geworden — unveraendert offen.
- **`.woodpecker.yml`-Scan:** `security-scan-backend` installiert `safety` weiterhin ungepinnt (`pip install -q safety`, `.woodpecker.yml:127`) und laeuft zusaetzlich zu den GitHub-Scans; in #1865 als eigener Slice vermerkt.
- **`ChangeRequestDTO.baseline_id`** fehlt weiterhin im REST-/MCP-Payload — in #1864 bewusst nicht mit abgedeckt (andere Parity-Luecke als `artifact_id`).
- **`minimatch`-Override** ist eine Bruecke bis `@typescript-eslint` ≥ 8.72.3 stabil `minimatch@^11` pinnt (Follow-up aus #1860); danach muss der Override fallen.
- **#1865 als Required Check** in den Repo-Settings eintragen (Follow-up aus #1865) — ohne das blockiert der Job keinen Merge.

EOF