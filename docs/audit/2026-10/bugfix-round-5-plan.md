---
title: Bugfix- & Feature-Runde 5 — Umsetzungsplan (beta.21-QA-Batch, Client-/Release-Kette, Code-Quality-Ratchet)
date: 2026-10-16
branch_base: origin/main @ f637ac16
author_agent: orchestrator
status: proposed
scope: beta.21-QA-Batch (#1342–#1368) + Residuen (#1239/#1247/#1153/#1258/#1279/#1287) + Memory-/Vektor-Potenzial (#1314–#1317/#1334/#1336/#1337/#1339, Entscheidungsspur) in 6 Wellen (W12–W17) + Housekeeping
---

# Bugfix- & Feature-Runde 5 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert nichts. Er beschreibt Paket,
> Reihenfolge, Wellen und Akzeptanzkriterien.
>
> **Faktenbasis:** Eigene Gegenprüfung im Repo am 2026-10-16 gegen `origin/main @ f637ac16`
> (Arbeits-Branch `chore/audit-code-quality-2026-10-15` = `f637ac16` + Audit-Commit `448e87e2`).
> Angaben aus Issues sind als „laut Issue" markiert, eigene Prüfung als „**verifiziert**".
> Drei Issues tragen eine **korrigierte Ursachenangabe** (§0.2, Nr. 5/6/8).
>
> **Abgrenzung zur Runde 4** (`bugfix-round-4-plan.md`): Runde 4 ist **vollständig gemergt**
> (W7 #1309, W8 #1310, W9 #1311, W10 #1312, Plan #1306, Housekeeping #1307, W11 #1313/#1331/
> #1332/#1333/#1335, #1104 #1338, Frontend-Plan-Doc #1340). Dieser Plan arbeitet den **danach
> gemeldeten** beta.21-QA-Batch (#1342–#1368) plus Residuen ab.

---

## 0. Ausgangslage

### 0.1 Basen & bereits Erledigtes

| Aspekt | Wert |
|---|---|
| `origin/main` | `f637ac16` |
| `v1.8.0-beta.21` | `78b50ec` = `f637ac16` + 1 Release-Commit (`chore/release-1.8.0-beta.21`; `rev-list` main↔Release = `0 1` → main ist strikt enthalten) — **alle QA-Befunde gelten 1:1 am main-Stand** |
| Runde 4 | vollständig gemergt (PRs #1306–#1340, siehe oben) |
| Residuum D4 | **erledigt** — „+ 74 APIViews"-Klausel nicht mehr in `.meta-config/project.yaml` (**verifiziert**) |
| Neuer Batch | #1342–#1368 (25 Issues, 2026-10-15); **#1364–#1367 bereits als Duplikate geschlossen** (#1364→#1357, #1365→#1361, #1366→#1359, #1367→#1363) |
| Backend-Potenzial-Batch | #1314/#1315/#1316/#1317/#1334/#1336/#1337/#1339 (beta.20-Analyse) + #1308 (2FA-Roadmap) |
| Offene Residuen | #1239, #1247/#1153, #1258, #1279, #1287, #1094 |
| Separater Strang A | **Code-Quality-Audit** `docs/audit/2026-10/AUDIT_CODE_QUALITY.md` (Branch dieses Dokuments) → W17 |
| Separater Strang B | **Frontend-Audit-Plan** `docs/plans/2026-10-15-frontend-audit-fixes.md` (Status „geplant", per #1340 nur als Dokument gemergt) → eigener Zyklus, nicht Teil von R5 |

### 0.2 Verifizierte Befunde (eigene Prüfung) und Ursachenkorrekturen

1. **#1279 (Sidebar 1366×768) ist behoben** — `SidebarNavigation.module.css:88-114` dokumentiert die
   Re-Verifikation (`.scrollContent` mit `overflow-y:auto` + persistentem Scrollbar; Höhenkette
   AppShell→…→`.scrollContent`), Commit `6bfa0fd7`. → **Schließen**, nicht implementieren.
2. **#1239 (CRITICAL „Save persistiert nichts") ist laut Gegenmessung nicht reproduzierbar** —
   Kommentar vom 2026-10-13 (PATCH 200 in `standard` und `extended`, Trace `issue-1239-save-trace.spec.ts`).
   → 1× E2E-Repro auf aktuellem Stand, dann **schließen**.
3. **#1350 verifiziert:** `git ls-files -s` → `install.sh`/`verify.sh` beide `100644`; zusätzlich ist
   lokal `core.fileMode=false` → Fix **muss** `git update-index --chmod=+x` nutzen (nicht `chmod`);
   dazu defensiv `exec bash verify.sh` (Zeile 307 ruft die Skripte direkt auf).
4. **#1351 verifiziert:** `copy_if_absent` (`install.sh:84-87`) überschreibt nie — der als Update-Weg
   dokumentierte „Re-run" ist ein No-Op.
5. **#1349 verifiziert, mit Präzisierung:** Kein Workflow referenziert `check_plugin_packages.py`;
   **aber:** auf main sind `VERSION` und alle Carrier konsistent (`1.8.0-beta.20`) — der Fehlschlag
   existiert nur am Release-Tag. Fix = **Pipeline-Verdrahtung + Release-Bump** erweitert die Carrier;
   **kein** Bump auf main.
6. **#1353 verifiziert, Ursachenangabe des Issues korrigiert:** `render.py` liest `VERSION` sehr wohl
   (`load_version()`, Zeile 158) — die generierte Doku wurde im Release nur **nicht neu gerendert**
   (Tag `v1.8.0-beta.21`: `VERSION=1.8.0-beta.21`, `docs/clients/hermes.md` = `beta.20`).
   `client-artifacts-check.yml` (`render.py --check`) läuft nur auf PR/`push main` mit Pfadfilter —
   **nicht** auf dem Release-Branch/Tag. Fix = Release-Prozess rendert neu + Gate greift am Tag.
7. **#1358 verifiziert, mit Präzisierung:** MCP `ai_derivation.*` kennt `mode="preview"|"write"`
   (`tools/ai_derivation.py:95`); Write-Helfer existieren (`_write_glossary_term_draft:1904`,
   `_write_adr_draft:1999`, `_write_derived_entity:1489`). Fehlend sind **REST-Parität + UI-Einstieg +
   ehrlicher Preview-Contract** — nicht der Persistenzmechanismus.
8. **#1359 verifiziert, mit Präzisierung:** Die 3 „schlafenden" Kinds sind **ADR-019-Design** und
   werfen sauber `SUGGESTION_KIND_NOT_ENABLED` (`suggestion_adapters.py:56-64, 393-409`).
   Der reale Defekt ist die Provenance-Priorität: `SuggestionsInbox.tsx:54-56` nimmt
   `proposed_by` (UUID) vor `producer` (z. B. „QA-Agent").
9. **#1363 verifiziert, mit Präzisierung:** Der Guard existiert — `i18n-parity.test.ts` hat
   `MISSING_KEY_BASELINE = 73` (nach #1277) und den Inline-Default-Ratchet (`INLINE_DEFAULT_BASELINE
   = 1283`, Muster Zeile 128). Die 54 gemeldeten Keys liegen **im Budget** → „blind" = Allowance,
   nicht fehlender Scan. Stichprobe (node): `baselines.added`, `icds.similar.findButton`,
   `systemSettings.adminOnly`, `nav.showOptionalArtifacts` in **de+en `undefined`**;
   `traceSpine.close` DE `Schliessen` / EN `Close` (Schreibinkonsistenz bestätigt).
10. **#1361 verifiziert:** `interview.py:341-364` lässt `artifact_type` optional, Default
    `session_kind="single"` verlangt es aber → Vertragsentscheidung (Default multi **oder**
    Schema-Pflicht explizit).
11. **#1356 verifiziert:** Fehlerstelle `review.py:388-392` (`available.current_state`); das
    Requirement ist `draft`, die Facade-Auflösung liefert im MCP-Pfad `None` → Wurzel im
    Zustands-/Transition-Auflösungspfad, mit Repro zu fixen.
12. **#1354 verifiziert:** `deploy/README.md` kennt kein Teardown mit vollständigem Profilsatz
    (nur `down` ohne `-v`-Hinweis, Z. 186-187).
13. **#1315 verifiziert:** Honcho hängt an `latest` + Digest (`deploy/docker-compose.yml`, Z. 1222).
14. **E2E #1342–#1348:** laut Issue Testkollisionen (1347/1348), Timeouts (1343/1344/1345),
    Visual-Baseline (1346), 0-Zeilen-Import (1342) — Klassifikation in W16, nicht blind fixen.

---

## 1. Inventar der offenen Issues

| # | Sev | Track | Kurz | Welle |
|---|---|---|---|---|
| 1356 | HIGH | MCP | `review.approve` löst Status nicht auf („from 'None'") | W13a |
| 1368 | HIGH | AI/UI | Requirement-`decompose-next-level`: Drafts verworfen, falsche Erfolgsmeldung | W12b |
| 1360 | HIGH | FEATURE | Einheitlicher KI-Freigabe-Dialog (Bestätigen/Verwerfen/„Review später") | W12c |
| 1349 | HIGH | CI/Release | Plugin-Ratchet in keinem Workflow; beta.21-Tag: 4 Carrier auf beta.20 | W15a |
| 1350 | HIGH | DX | Installer/Verifier Mode 100644 → Exit 126 | W15b |
| 1357 | MED | MCP | Workspace-restriktiver Key + irreführende Fehlermeldung | W13b |
| 1358 | MED | AI | Glossar-/ADR-/Risiko-Ableitung: Drafts ohne Persistenz/Preview-Wahrheit | W12a |
| 1361 | MED | MCP | `interview.start` verlangt undok. `artifact_type`; Frontend-API tot | W13c |
| 1362 | MED | MCP | Contract-Drift: Parameter, Rollen-Gates, ID-Semantik, Pfad-Asymmetrien | W13d |
| 1363 | MED | i18n | 54 Fallback-Keys (43× EN in DE-UI); Ratchet 73 → senken | W14 |
| 1351 | MED | DX | `copy_if_absent` = No-Op für Updates | W15b |
| 1352 | MED | DOCS | Hermes-Dashboard-Plugin ohne Install-/Update-Pfad | W15c |
| 1353 | MED | DOCS | Client-Doku-Version stale; Gate greift am Tag nicht | W15c |
| 1359 | LOW | AI/UI | Provenance als rohe UUID; dormante Kinds kennzeichnen | W12d |
| 1354 | LOW | OPS | Kein Teardown profilierter Services | W15d |
| 1342 | LOW | E2E | csv-import: 0 Zeilen importiert | W16 |
| 1343–1348 | LOW | E2E | 6 Flakes/Timeouts/Kollisionen/Visual | W16 |
| 1315 | MED | OPS | Honcho `latest` ohne stabilen Tag | W15d |
| 1314/#1334/#1316 | MED/HIGH | MEM/VEC | Qdrant-Konfig/Auslastung, Artefakt-Indexer, Hybrid-Suche | Entscheidung D5 |
| 1336/#1337 | HIGH/MED | HONCHO | Dream nie ausgeführt; 6 Fähigkeiten ohne Aufrufer | Entscheidung D6 |
| 1339 | — | MEMORY | Injektion je KI-Aktivität/Workspace/User schaltbar | Entscheidung D7 |
| 1317 | LOW | DOCS | 3 Memory-Ablagen, doppelte Embedding-Config | Entscheidung D7 |
| 1247/#1153 | HIGH | HONCHO | `memory.ask` degraded (Dialektik-LLM-Call ohne Header; upstream) | D6 (Doku/Upstream) |
| 1279 | MED | UI | Sidebar 1366×768 | Housekeeping (schließen) |
| 1239 | CRIT | UI | Edit/Save persistiert nichts | Housekeeping (re-verify, schließen) |
| 1258 | MED | UI | Button-Streuung (19 Höhen/7 Radien) | Haushalt → Frontend-Plan |
| 1287 | LOW | UI | Markdown-Formatierungszeile nicht ausblendbar | Runde-6-Kandidat |
| 1308 | — | SECURITY | 2FA für Staff (ADR-021 O5 akzeptiert) | Roadmap, außerhalb |

---

## 2. Wellen

Jede Welle ist unabhängig shippbar, eigener `fix/*`-Branch off `origin/main`, kein Commit auf
`main`. Bündelung nach **geteilter Komponente**.

### W12 — KI-Ableitungs- & Freigabe-Lifecycle (Kern des Batches)

| Teil | Inhalt | Ziel |
|---|---|---|
| **W12a — #1358 Wahrheit & Contract** | Preview-Antworten als ephemer kennzeichnen (Feld/Doku), `mode="write"`-Pfad als kanonischen Persistenzweg dokumentieren; Entscheidung REST-Parität (additiv) vs. MCP-only + Doku; Tests | Drafts sind entweder persistent **oder** ehrlich als flüchtig ausgewiesen |
| **W12b — #1368 Requirement-Draft-Flow** | `decompose-next-level`-Drafts rendern (Panel analog `DeriveRequirementsPanel`) mit Bestätigen/Verwerfen über den `proposed`-Seam; Erfolgsmeldung ohne Freigabe-Zusage bei reiner Vorschau | Kein bezahlter Entwurf verpufft; Erfolgsmeldung deckt sich mit dem, was passiert |
| **W12c — #1360 Einheitlicher Freigabe-Dialog** (Feature) | Dialog mit **Bestätigen / Verwerfen / Review später** für die 8 Ableitungen; „Review später" persistiert als `proposed` → sichtbar in `/reviews` → „Vorschläge" (`review_queue_service` union, verifiziert konzeptionell); für Glossar/ADR/Risiko prüfen, ob deren `proposed`-Status in der Inbox erscheint | Ein Muster statt acht Einzellösungen; keine Persistenz ohne sichtbare Bestätigung |
| **W12d — #1359 Provenance** | `producer`/`agent_label` vor `proposed_by`-UUID; UUID als Tooltip; dormante Kinds im UI als „nicht verfügbar" kennzeichnen | Lesbare Herkunft; keine falsche Erwartung an schlafende Kinds |

**Reihenfolge:** W12a → W12b → W12c; W12d parallel (disjunkte Dateien).
**Risiko:** W12c ist UI-weit und LLM-kostenrelevant. Gegenmaßnahme: auf bestehendem
`preview|write`-Seam aufsetzen (keine neuen Endpunkte, wo nicht nötig), kein Auto-Schreiben,
Freigabe immer explizit.

### W13 — MCP-Contract & Zustandsauflösung

| Teil | Inhalt | Ziel |
|---|---|---|
| **W13a — #1356** | Repro (Requirement `draft`), Wurzel der `None`-Auflösung im Workflow-/Facade-Pfad fixen; zustandsrichtige Fehlermeldung; Test | `review.approve` arbeitet auf dem echten Zustand |
| **W13b — #1357** | Scope-Prüfung gegen den Ziel-Workspace des **Artefakts** auflösen; Parameter-/Validierungsfehler mit eigenem Code (`-32602`) statt Scope-Text | Fail-closed bleibt, aber Diagnose stimmt; Security-Review nötig |
| **W13c — #1361** | Vertrag entscheiden: `artifact_type` optional (Default multi) **oder** Schema-Pflicht explizit; tote Frontend-API (`grounding`/`answer`) entfernen oder verdrahten | Kein undokumentierter Zwang; kein totes API |
| **W13d — #1362** | (a) `workspace_id` in OpenAPI für `reviews/pending`; (b) Rollen-Gates in Tool-Beschreibungen; (c) ID-Semantik `context.*` (artifact_id) vs. Entity-`id` + PascalCase-`entity_type`; (d) REST-Asymmetrien (`check_consistency`/`validate`) — Pendant oder dokumentieren | Contract = Realität; Agenten debuggen nicht mehr in die falsche Richtung |

**Risiko:** W13b ist sicherheitsrelevant (Workspace-Fence) → eine PR, dedizierte Tests für
abgelehnte Fremd-Workspace-Zugriffe; W13a berührt Workflow-Semantik → keine Preset-Lockerung.
**Contract-Pflege:** Tool-Schemas ändern sich → kanonisches Manifest
(`docs/agent-templates/tool-manifest.json`) und Drift-Test im selben PR prüfen.

### W14 — i18n-Fallbacks als Ratchet (#1363)

- 54 fehlende Keys in **de.json + en.json** ergänzen, Fallback-Literale an den Call-Sites
  entfernen (43 EN / 17 DE), `traceSpine.close` DE auf `Schließen` korrigieren.
- `MISSING_KEY_BASELINE` messen und **senken** (aktuell 73; nach Übersetzung der 54 Keys ~19);
  Inline-Default-Ratchet mitziehen, wenn Call-Sites bereinigt werden.
- Kein Guard-Umbau nötig — der Ratchet existiert; Issue-Formulierung „blind" im PR korrigieren
  (Budget, nicht fehlender Scan).

**Risiko:** Übersetzungsqualität + Baseline muss exakt zur Messung passen → Messwert im Commit
dokumentieren (Konvention der bestehenden Kommentarkette im Test).

### W15 — Client-, Release- & Deploy-Kette (DX)

| Teil | Inhalt | Ziel |
|---|---|---|
| **W15a — #1349** | `check_plugin_packages.py` in den Tag-Release-Pfad verdrahten (`docker-publish.yml` @ `v*.*.*` oder dedizierter Tag-Workflow); Release-Bump-Schritt erweitert die 4 Hermes-Carrier; auf main **nichts** bumpen | Drift schlägt am Tag fehl, nicht beim Nutzer |
| **W15b — #1350/#1351** | `git update-index --chmod=+x` (core.fileMode=false lokal beachten) + defensives `exec bash verify.sh`; Mode-Gate in CI; `--force`/`--refresh` mit `.bak-<ts>`; `docs/clients/*.md` §8 korrigieren | One-Command-Install und dokumentierter Update-Weg funktionieren |
| **W15c — #1352/#1353** | Hermes-Dashboard-/Agent-Plugin: Install/Update-Abschnitt in `registry.yaml` (→ render.py) + optional `--with-dashboard`; Release rendert `docs/clients/**` neu; `render.py --check` im Tag-Pfad; Versionsregeln je Artefakt (ADR-017) benennen | Installierbar dokumentiert; Doku-Version folgt `VERSION` |
| **W15d — #1354/#1315** | Teardown-Abschnitt mit vollständigem Profilsatz (+ `COMPOSE_PROFILES`-Hinweis) in `deploy/README.md`; Honcho auf stabilen Tag + Digest pinnen | Reproduzierbare Stacks über Version-Upgrades |

**Bezug:** W15a/W15c teilen das Thema „generierte Artefakte + Release-Gates" → ein Strang,
`client-artifacts-check.yml` ggf. um Tag-Trigger erweitern.

### W16 — E2E-Härtung (#1342–#1348)

Triage jeder der 7 Meldungen mit einer von drei Ausgängen:
1. **Test-Isolation** (1347/1348: eindeutige Workspace-Namen/Cleanup) — Test-Fix.
2. **Echte Produktlatenz/-robustheit** (1343/1344/1345: derive-requirements im E2E; „missing Ollama
   graceful" muss schnell & sauber antworten) — prüfen, ob Backend-Bug; Timeout nicht blind erhöhen.
3. **Format/Baseline** (1342: csv-import 0 Zeilen — Importer-Edge-Case möglich; 1346: Visual-Baseline
   mit Begründung neu setzen oder Umgebungsdrift fixen).
**Ziel:** E2E-Suite grün mit dokumentierter Ursache je Issue (Kommentar + close oder Fix-Referenz).

### W17 — Code-Quality-Ratchet (separater Strang, **nachgelagert**)

Aus `AUDIT_CODE_QUALITY.md`, in 3 Slice-PRs (Merge-Konflikt-Risiko → zuletzt):
1. **Autofix-Modernisierung** (UP*/I001/UP035/RUF022 …; ~5.000+ mechanische Findings) in einem
   separaten PR; danach Lint-Zählung als Baseline einfrieren (Ratchet analog i18n).
2. **Manuelle Hochrisiko-Regeln:** `BLE001` (241), `S110` (27), `F811` (37) — Hotspots
   `rest_api`, `application`, `mcp_server` sichten (können echte Bugs verbergen).
3. **Frontend:** `no-explicit-any` (275) + `exhaustive-deps` (7) + jsx-a11y-Rest (16) —
   inkrementell; Berührungspunkte mit dem Frontend-Audit-Plan (§0.1 Strang B) abstimmen.

### Entscheidungs- & Housekeeping-Spur (keine Produktwellen)

| # / Punkt | Schritt |
|---|---|
| **D5 — Qdrant/Memory-Richtung** (#1314/#1334/#1316) | ADR nötig: Option A (Qdrant abkündigen, pgvector trägt) vs. Option B (voll betreiben inkl. Artefakt-Indexer + Hybrid). **Blockiert** #1334/#1314-Umsetzung; ohne Entscheidung kein Code. |
| **D6 — Honcho-Produktpfad** (#1336/#1337/#1247/#1153) | Upstream-Befund (Dialektik-LLM-Call ohne `x-opencode-session`) dokumentieren, Honcho-Version pinnen (W15d), Upstream-Issue; Dream/Fähigkeiten erst nach D5-analoger Richtungsentscheidung. |
| **D7 — Memory-Injektion & Ablagen** (#1339/#1317) | Konzept (`MEMORY_INJEKTION_KONZEPT.md`, laut Issue) liegt vor → ADR-light + Umsetzungsschnitt; #1317 als Doku-Teil desselben Schnitts. |
| **#1279** | Schließen mit Evidenz (CSS-Kommentar + `6bfa0fd7`). |
| **#1239** | 1× `issue-1239-save-trace.spec.ts` gegen main laufen lassen, dann schließen (Gegenmessung). |
| **#1258** | Mit Frontend-Audit-Plan bündeln (Design-System-Ratchet-Absenkung statt Einzel-Fix); nicht in R5. |
| **#1287/#1094/Roadmap** (#1308, #186, #934/#941, #801, #1171) | Runde-6-Kandidaten bzw. laufende Epics — unverändert. |
| **#1364–#1367** | Bereits als Duplikate geschlossen — keine Aktion. |

---

## 3. Priorisierter Vorschlag („schneller Nutzen zuerst")

1. **W14** (i18n, budgetierter Ratchet) und **W13a/W13b** (#1356/#1357) — sichtbare MCP-Bugs,
   kleine Änderungen, hohe Wirkung.
2. **W12** (KI-Ableitungs-Lifecycle) — größter funktionaler Hebel des Batches; #1360 als Feature
   erst nach #1358/#1368.
3. **W15** (Release-/DX-Kette) — verhindert Wiederholung von #1349/#1350/#1353 bei jedem Release.
4. **W16** (E2E-Härtung) — Triage, keine blinden Timeout-Erhöhungen.
5. **W17** (Ratchet) und **D5–D7** (Gedächtnis-Epic) — nachgelagert, eigene Zyklen.

---

## 4. Reihenfolge & Parallelisierung

- **W12a–c** teilen `ai_derivation_service.py` + REST/MCP + UI → **ein** Strang, sequenziell.
- **W13** berührt `mcp_server/tools/{review,interview,…}.py`, Workflow-Facade und API-Key-Prüfung;
  W13a und W13d überlappen in `review.py` → bündeln; W13b (Auth) separat; W13c klein.
- **W12 ↔ W13**: beide ändern MCP-Tool-Schemas → Manifest/Drift-Test in der **zuerst gemergten**
  Welle aktualisieren, die zweite rebased.
- **W14** (Locales + wenige Komponenten) und **W15** (Skripte/Workflows/Docs) und **W16** (e2e/)
  sind disjunkt → parallel möglich.
- **W17** zuletzt (höchster Konflikt-Radius: `backend/**`, `frontend/**`).

---

## 5. DoD

Wie Runde 3/4: pro Welle ein eigener `fix/*`-Branch, Conventional Commits, Tests im selben Commit,
`make test-backend`/`make test-frontend` ohne neue Fehler, Ruff `--select=F821,F822` sauber,
`npm run lint`/`npm run build`, Secret-Scan vor jedem Commit. Zusätzliche Ratchets, wo vorgesehen:

- **W14:** `MISSING_KEY_BASELINE` sinkt exakt auf den gemessenen Wert (Kommentar im Test).
- **W15a/W15c:** Ratchet + `render.py --check` im Tag-Pfad; Nachweis per Trockenlauf.
- **W13:** MCP-Contract-Tests + Manifest-Drift-Test grün; #1357 mit Fail-closed-Tests.
- **W12:** Preview-Antworten enthalten das Ephemeral-Kennzeichen; „Review später" hat einen
  sichtbaren Inbox-Eintrag (E2E-nah testbar).
- **W16:** E2E-Suite ohne die 7 gemeldeten Fehlschläge; je Issue dokumentierter Ausgang.

---

## 6. Risiken & offene Entscheidungen

| Risiko / Entscheidung | Issue(s) | Handling |
|---|---|---|
| Scope-Prüfung ändern (Fail-closed!) | #1357 | Security-Review, Tests für Fremd-Workspace-Ablehnung; kein Fail-open |
| `interview.start`-Default ändern = Verhaltensänderung für Agenten | #1361 | Vertrag zuerst festschreiben (Schema), dann umsetzen; abwärtskompatibel |
| REST-Parität für Glossar/ADR/Risiko: bauen oder dokumentieren? | #1358 | **Entscheidung** in W12a (User/`se-architect`); bei „bauen" additive Endpunkte über den `write`-Seam |
| „Review später" für Artefakttypen ohne `proposed`-Status | #1360 | Vor Umsetzung prüfen (Review-Queue-Union); notfalls Typ-Liste eingrenzen und Rest dokumentieren |
| Release-Workflow-Verdrahtung + Carrier-Bump | #1349/#1353 | Auf main nichts bumpen (verifiziert konsistent); Release-Prozess + Gate ändern |
| Exec-Bit unter Windows (core.fileMode=false) | #1350 | `git update-index --chmod=+x` + CI-Mode-Gate als Nachweis |
| E2E-Triage: Timeout vs. echter Backend-Bug | #1343–#1345 | Erst Ursache (Log/Netzwerk), dann Fix-Entscheidung; kein pauschales Timeout-Hochsetzen |
| Upstream-Abhängigkeit Honcho-Dialektik | #1247/#1153 | Nicht In-Repo heilbar → Pin + Upstream-Issue + degraded-Pfad dokumentieren (D6) |
| Autofix-Blast-Radius (~5.000 Findings) | W17 | Eigener PR, keine Verhaltensänderung, volle Testläufe, Ratchet danach |

---

## 7. Self-Review

- **Vollständigkeit:** Alle offenen Issues mit Bezug zu R4/R5 erfasst: beta.21-Batch #1342–#1368
  (4 Duplikate als geschlossen vermerkt), Residuen #1239/#1247/#1153/#1258/#1279/#1287,
  Backend-Potenzial #1314–#1317/#1334/#1336/#1337/#1339 (+#1308, #1315) in der Entscheidungsspur.
- **Fakten vs. Annahmen:** 14 Kernbefunde im Repo gegengeprüft (§0.2); Korrekturen an drei
  Issue-Ursachen (#1353, #1358, #1359) und eine Präzisierung an #1349/#1363. Restliche Angaben
  sind „laut Issue" und in der jeweiligen Welle zu verifizieren.
- **Holistik:** Bündelung nach geteilter Komponente (AI-Derivation-Service/UI, MCP-Tools/Manifest,
  Locales, scripts/clients+Workflows, e2e) statt nach Issue-Nummer.
- **Nicht implementiert:** dieser Plan ändert nichts; Housekeeping-Schließungen erst mit Evidenz.
- **Offen (bewusst):** D5–D7 brauchen Richtungsentscheidungen; der Frontend-Audit-Plan bleibt ein
  eigener Zyklus.

---

*Erstellt am 2026-10-16. Basis `origin/main @ f637ac16` (= beta.21 minus Release-Commit);
25 beta.21-QA-Issues + 8 Potenzial-Issues + 6 Residuen in 6 Wellen (W12–W17) +
Entscheidungs-/Housekeeping-Spur.*
