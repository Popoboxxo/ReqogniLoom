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

### 4.2 Backend-Dependencies

`pip audit` ist im Stack nicht installiert. Empfehlung: `pip-audit` in die CI aufnehmen (analog npm audit). Bekannte Risiken: openai/anthropic SDKs, honcho-ai, sentence-transformers (torch) — sollten auf CVEs geprueft werden.

### 4.3 Betriebs-Funde aus dem Live-Lauf

- `LLM_API_KEY` ist in `.env` leer; `LLM_OPENCODE_SESSION` steht auf dem `.env.example`-Platzhalter — der Preflight blockiert damit jeden echten KI-Start. Dokumentation/Deployment-Check ergaenzen.
- Honcho ohne Embedding-Provider: Write 500 (behoben: #1823), Readiness 503 (behoben: #1824) — aber Embeddings bleiben unverfuegbar, Honcho ist damit funktional eingeschraenkt.
- `page_size`-Kleinkram (#1761) behoben.

## 5. P3 — Code-Qualitaet und Wartung

### 5.1 Lint

- **Backend:** 59 x `F841` (unused locals) — kosmetisch, keine F821/F822 (undefinierte Namen). Ruff-Gate prueft nur F821/F822, daher gruen. Aufraeumen in einem `chore`-Commit.
- **Frontend:** ESLint 0 Errors, 71 Warnings (vorbestehend: `no-explicit-any` in Test-Mocks). Neue Dateien aus #1763/#1564 haben keine neuen Warnings.

### 5.2 Architektur (graphify)

- 57.000 Nodes, 128.387 Edges, 2.262 Communities
- Keine Edge-Collapse-Risiken, 2 Self-Loops (minor)
- God-Nodes (hochgradige Knoten) sollten geprueft werden auf zu starke Kopplung
- Der Graph ist lokal unter `graphify-out/` und gitignored

### 5.3 Offene technische Schulden

- `variant="panel"`-Zweig der vier Panels (Trace/Diff/Version/Comment) ist toter Produktionspfad nach M5–M8; Tests decken ihn noch ab. Aufräumen als `refactor`.
- `released_tier_key` ist read-only im Serializer, aber fehlt in ChangeRequest-DTO (`artifact_id`-Paritaetsluecke, analog #1763).
- `AttributeDefinition`-Bootstrap introspektiert neue Modellfelder automatisch; bei neuen Feldern muessen Labels und Read-only-Klassifikation nachgezogen werden (Gates fangen das, aber es ist manuelle Arbeit).
- `ui-ratchet`-Baseline: 74 hartcodierte Farb-Literale in 14 Dateien (dokumentiert, Abbau bei Gelegenheit).

## 6. P4 — Testabdeckung und CI

- **Backend:** 4 CI-Sets, ~11.000 Tests; letzter Lauf 3.758 + 323 + 442 + 603 + 941 = alle gruen
- **Frontend:** 3.615 Tests (Vitest 5), 0 Failures
- **E2E:** 417/418 Playwright (67 Specs, 4 Shards); 1 bekannter Failure (waterkettle 17/18, behoben in #1830, aber noch nicht live verifiziert)
- **Gates:** Manifest-Drift (293 Tools), Doc-Surface-Consistency, Meta-Tool-Count, Schema-Completeness, RLS-Coverage — alle gruen

### Empfohlene naechste Schritte

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
EOF