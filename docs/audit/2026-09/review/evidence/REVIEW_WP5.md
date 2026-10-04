---
type: REVIEW
scope: WP-5 (Traceability) — adversarial second review
status: final
date: 2026-10-01
author_agent: validator
branch: chore/audit-review-2026-09
method: read-only static verification at HEAD 10dc620f; all numbers re-derived from docs/se/**, backend tests and CI config; audit's own AUDIT_EVIDENCE/* not used as proof
targets: [AUD-2026-09-345, -346, -191, -192, -193, -195, -196, -201, -330, -331, -333, -334, -339, -340, -342, -343, -344, -347, -348, -349, -350, -194, -197, -198, -199, -200, -202, -203, -204, -332, -335, -205]
---

# REVIEW_WP5 — adversariale Zweitprüfung der WP-5-Traceability-/SE-Nachweis-Findings

**Scope.** Unabhängiger, read-only Falsifikationsversuch der WP-5-Beiträge aus
`docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5 (Volltext in `AUDIT_TRACEABILITY.md`).
Ziel-IDs: Critical `345`, `346`; High `191`, `192`, `193`, `195`, `196`, `201`,
`330`, `331`, `333`, `334`, `339`, `340`, `342`, `343`, `344`, `347`, `348`,
`349`, `350`; Medium-Stichprobe `194`, `197`, `198`, `199`, `200`, `202`, `203`,
`204`, `332`, `335`; Low `205` — **32/32 Ziele geprüft, alle Critical + High
vollständig, Medium 10/10, Low 1/1**.

**Methodik.** Alles aus echten Produktartefakten am HEAD `10dc620f` neu
abgeleitet. Das audit-eigene `AUDIT_EVIDENCE/*` wurde **nicht als Beweis**
verwendet; es diente nur zur Identifikation der zu prüfenden Behauptung.
Zählungen wurden mit `ripgrep 15.2.0` bzw. `.NET Regex` in PowerShell
nachgerechnet. Wo eine Zahl nur durch Ausführung (`pytest --collect-only`,
`vitest run`) reproduzierbar wäre und diese hier nicht ausgeführt wurde, ist das
explizit als **offener Prüfschritt** markiert. `.kimi-code/` und
`AUDIT_EVIDENCE/stack-seeds.md` wurden nicht angefasst; es wurde kein
Produktcode geändert. Der Audit-Basis-Commit `abd61aed`/`75beb750` ist Vorfahre
des Prüf-HEAD; die geprüften Artefakte sind gegenüber dem Audit-Stand
unverändert (Stichprobe der zitierten Zeilen stimmt exakt).

**Wichtige Vorab-Korrektur zur Auftragsnotiz.** Die Auftragsangabe „57 % der
REQs ohne Testbezug (192 nennt 42,9 %)" ist **kein Widerspruch**: es sind die
zwei Seiten derselben Messung (358 mit = 42,9 %, 477 ohne = 57,1 %). Die
Auftragsangabe „316/324 fehlende REQ-IDs" ließ sich nicht bestätigen — die
gemessene und belegte Zahl ist **324**; eine `316` existiert im WP-5-Kontext
nicht (316 ist eine WP-3b-Finding-ID). Siehe §6.

---

## 1. Scope / Methodik

| Messung | Verfahren | Ergebnis |
|---|---|---|
| REQ-Quellinventar | `rg -o 'REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}' docs/se/L0 docs/se/L1 \| sort -u` | **835** |
| Matrix-Inventar | dasselbe über `docs/se/traceability-matrix.md` | **511** |
| Drift | Mengendifferenz Quell- minus Matrix-IDs | **324 fehlend, 0 Phantom** |
| Test-Bezug | Schnitt Quell-× IDs in Testdateien (`test_*.py`,`*_test.py`,`*.test.*`,`*.spec.ts`) | **358/835 = 42,9 %** |
| `open_adrs` | `rg -l 'open_adrs' docs backend frontend/src` | nur Audit-eigene Dokumente |
| CI-Testlücke | 658 Testdateien gegen die 20 CI-Pfade, `^\s*def test_` gezählt | **443 ungedeckt / 7 684 gedeckt = 8 127** |

Das audit-eigene Zitat-Konvention „`datei:zeile` + Zitat" wird in §2 für jedes
Verdikt eingehalten. Zitierte Zeilen wurden einzeln gelesen.

---

## 2. Gegenbeweis-Tabelle

| ID | Behauptung (Kern) | Mein Gegenbeweis (`pfad:zeile` + Zitat) | Verdikt |
|---|---|---|---|
| **345** | `matrix:331` REQ-L1-046 `Implemented`, Restore nie im Image (`Dockerfile:154`) | `traceability-matrix.md:144` `\| REQ-L1-046 … \| Implemented …`; `:331` `\| REQ-L2-BL-011 … \| Not Implemented \| Missing \|`; `backend/Dockerfile:154` `COPY . .`; Build-Context `./backend` (`docker-publish.yml:35` `context: ./backend`); `scripts/restore.sh` (8 337 B) liegt außerhalb → `rg 'restore' backend/Dockerfile deploy/docker-compose.yml` → 0 Treffer | **TEILWEISE** — Fakten bestätigt, aber **Duplikat des Critical AUD-123** (`scripts/restore.sh:183,186,198-213`) |
| **346** | `providers.py:1080` Default-Modell abgeschaltet, REQ-L1-013 `Implemented/Covered` | `backend/llm_adapter/providers.py:1080` `MODEL_NAME = "claude-3-opus-20240229"` — identische Zeile wie **AUD-052** (`AUDIT_FINDINGS.md:192`) | **TEILWEISE** — Fakten bestätigt, aber **Duplikat des Critical AUD-052**, kein eigenständiger WP-5-Fund |
| **191** | stdio-Handler existiert, Transport nicht exponiert | `protocol_handler.py:345` `"""stdio transport — reads newline-delimited JSON from stdin."""`; `views.py:425` `"stdio" is deliberately absent` | **BESTAETIGT** |
| **192** | 42,9 % der REQ-IDs mit Test-Bezug (3,6 % der Tests) | 358/835 = 42,9 % exakt; aber `366` ist die Zahl **eindeutiger REQ-IDs in Testdateien** (backend+FE+E2E), nicht „Backend-Testdefinitionen": Testfunktionen in REQ-haltigen Backend-Dateien = **3 207/10 052 = 31,9 %**; Backend-Testdateien mit `REQ-L` = **179** (nicht 256) | **TEILWEISE** — Headline korrekt, Sub-Zahl „3,6 %" ist eine Etiketten-Verwechslung |
| **193** | 511 von 10 052 Definitionen in keinem CI-Job | Kanonisch ist laut Synthese **443**; 443 exakt reproduziert (§6). `ci.yml:44-55` deckt 20 App-Pfade ab | **TEILWEISE** — CI-Lücke bestätigt, **Zahl 511 durch 443 ersetzt**; Registerzeile `AUDIT_FINDINGS.md:255` trägt noch 511 |
| **195** | „Regression-Suite vollständig grün" bei 511 nie ausgeführten Tests + 4 Errors | `RELEASE_v1.8.0-beta.17.md:12-13` Zitat wörtlich vorhanden; `:171` `10015 passed, 13 skipped, 1 xfailed sowie 4 Errors` — Selbstwiderspruch real. Zahl „511" überholt (→443) | **TEILWEISE** |
| **196** | „W1–W4 … getestet", W4-Tests rot (65 FE-Fehler) | `RELEASE_v1.8.0-beta.17.md:17` Zitat wörtlich vorhanden; `useNotificationFeed.test.ts:57` `localStorage.clear();` (Bare-Global) statisch bestätigt. „65 rot" nur durch `vitest run` unter Node ≥ 22.4 reproduzierbar — hier nicht ausgeführt | **TEILWEISE** (65 siehe §6) |
| **201** | L0-031 existiert nirgends, Matrix springt 030→032 | `SN_Stakeholder_Needs.md:763` REQ-L0-030, `:793` REQ-L0-032 (kein 031); `traceability-matrix.md:59` 030, `:60` 032 | **BESTAETIGT** |
| **330** | 324 Quell-REQ-IDs fehlen in Matrix (24 L2, 300 L3) | Reproduziert: 324 = 24 (L2) + 300 (L3), 0 L0/L1 | **BESTAETIGT** |
| **331** | Matrix publiziert 0 von 354 L3-Zeilen; behauptete 369 | `rg -c '^\| REQ-L3-'` → kein Treffer; `traceability-matrix.md:701` `\| **Gesamt** \| **290** \| **116** \| **369** …` | **BESTAETIGT** (Zitat „649-655" trifft die Tabelle bei 649-656/701, unwesentlich) |
| **333** | `open_adrs` repo-weit 0/835 | `rg -l 'open_adrs' docs backend frontend/src` → **nur** `docs/audit/2026-09/**` (der Audit selbst); in `docs/se/**` 0 Treffer | **BESTAETIGT** |
| **334** | 14/15 `arch_impact:true`-REQ-L1 ohne ADR; kein akzeptiertes ADR deckt L1/L2 | `L1_Gesamtsystem_Requirements.md` enthält 16 `arch_impact`-Zeilen (15× `true`, 1× `false` bei `:1427`); nur REQ-L1-100 → ADR-DS-02 | **BESTAETIGT** (Stichprobe) |
| **339** | `arch_impact` bei L2-Ableitung true→false | `L1_clarifications_iter-1.md:40,89,106` `arch_impact: true`; `L2_ReqIFServiceSystem_Requirements.md:41,69`, `L2_CommentServiceSystem_Requirements.md:42,70,98`, `L2_VectorSearchServiceSystem_Requirements.md:52,80,108` je `**arch_impact:** false` | **BESTAETIGT** |
| **340** | 17 `Implemented`-REQ-L1 mit nicht-impl. Kind (3 vollständig) | `matrix:103` REQ-L1-005 `Implemented`, 8/12 Kinder ohne Marker (MC-001…006, MC-009, MC-011); `:310-312` REQ-L1-039 2/3; `:331` REQ-L1-046 1/1 | **BESTAETIGT** (Stichprobe der 3 „vollständigen") |
| **342** | `semantic_search` als `Implemented/Covered`, existiert nicht | `L2_McpServerSystem_Requirements.md` (Pfad `docs/se/L1/Gesamtsystem/L2/McpServerSystem/`) Block REQ-L2-MC-014: `Implemented`, Review Findings `… exportiert das Tool semantic_search standardkonform.`, `Covered`; `rg 'semantic_search' backend frontend/src e2e` → **1 Treffer, ein Testmethodenname**; `tools/search.py` existiert nicht (30 Tool-Module) | **BESTAETIGT** |
| **343** | 7/29 Stichproben-REQs stale (Code+Tests existieren) | `matrix:231` AS-005 `Not Implemented`; `:311` AT-018 `Not Implemented`; `:390` LA-009; `:433` PL-007; `:483` RF-015; `:512/:513` RQ-001/002; `cm` — Code+Tests vorhanden (`reqif_import_service.py`, `comment_service.py`, `item_permission.py`, `effective_permission_service.py` alle `Test-Path=True`) | **BESTAETIGT** |
| **344** | 3 REQ-L1 `Not Implemented` mit vollständig implementierten Kindern | `matrix:131` REQ-L1-033 `Not Implemented`, `:304-309` alle 6 Kinder `Implemented/Covered`; `:120` REQ-L1-022 + `:241` Kind Implemented; `:134` REQ-L1-036 + `:257` AS-031 Implemented, aber MC-013 „kein Marker" (1/2) | **TEILWEISE** — Wort „vollständig" stimmt nur für 022/033; 036 ist 1/2 |
| **347** | Azure implementiert, nicht wählbar | `frontend/src/api/llm-settings.ts:22` `export type LlmProvider = "anthropic" \| "openai" \| "ollama" \| "opencode_go" \| "mock";` — `azure` fehlt | **BESTAETIGT** |
| **348** | i18n `Implemented/Covered`, 112 Keys fehlen, Lint wirkungslos | `matrix:114` REQ-L1-016 `Implemented`; Zahl im WP-5-Text **112**, der Ratchet führt aber `i18n-parity.test.ts:186 const MISSING_KEY_BASELINE = 116;` — **112 vs. 116 widersprüchlich** | **TEILWEISE** (Zahl siehe §6) |
| **349** | CSV-Import meldet Spaltenverlust als `success: true` | `import_service.py:226-234` unbekannte Spalten nur in `warnings`; `:317 success=True` im Erfolgspfad; `:149 success: bool` — bestätigt | **BESTAETIGT** (Link auf AUD-070 ist allerdings stale, da WIDERLEGT) |
| **350** | Asynchronie `Covered`, jede Celery-Task läuft 4× | Reiner Cross-Ref auf `AUD-120` (Critical, unabhängig bestätigt); kein eigener WP-5-Beleg. `matrix:521` REQ-L2-RO-001 `Implemented/Covered` | **BESTAETIGT** (als Cross-Ref) |
| **194** | Zweites CI führt kein `pytest` | `.woodpecker.yml` Trigger `push: main`; einziger Backend-Schritt `:61 python manage.py check`; `rg 'pytest'` → 0 Treffer | **BESTAETIGT** |
| **197** | 0 REQ-IDs in 11 Abnahmeberichten; **keine Checkboxen** | 7 RELEASE + 4 TESTPLAN = 11 Dateien; REQ-IDs in den exakt 11 Dateien = **0** ✔. Aber: `TESTPLAN_v1.8.0-beta.15/.16` je 3 und `beta.17` **10** Checkboxen (`rg -c '\- \[[ x]\]'`) — Behauptung „keine Checkboxen" **falsch** | **TEILWEISE** |
| **198** | SSE-Live-Redis-Pfad in jedem CI-Lauf übersprungen | `test_e2e_sse_transport.py:349` `skipif(bool(os.environ.get("CI") …))`, `:353` `skipif(not _REDIS_REACHABLE)` | **BESTAETIGT** |
| **199** | Bare-Global `localStorage` in 4 FE-Dateien → 65 Fehlschläge | `useNotificationFeed.test.ts:57` `localStorage.clear();`; 4 Dateien mit Bare-Global bestätigt. „65" nur durch `vitest run` reproduzierbar — hier nicht ausgeführt | **TEILWEISE** (65 siehe §6) |
| **200** | Test fixiert abgeschaltetes Modell als Erwartungswert | `backend/rest_api/tests/test_llm_settings.py:248` `"model_name": "claude-3-opus-20240229"` und `:255 assert body[…]==…` | **BESTAETIGT** |
| **202** | 104/121 Requirement-Dokumente ohne YAML-Frontmatter | 121 `*Requirements*.md`, davon 17 mit Frontmatter (`Get-Content -TotalCount 1 -eq '---'`) → **104 ohne** | **BESTAETIGT** |
| **203** | 20 doppelt vergebene REQ-IDs; „letzter gewinnt" positionsabhängig | `traceability-matrix.md:724` zählt selbst **20** IDs; `:728` erklärt „Marker: letzter gesetzter Wert gewinnt" | **BESTAETIGT** (Matrix-Selbstauskunft) |
| **204** | „Parallelbefund ‚Archivierung nie registriert' nicht reproduzierbar" | Master-Zeile `AUDIT_FINDINGS.md:366` behauptet weiter „nicht reproduzierbar", obwohl `AUDIT_TRACEABILITY.md:148-161` die Aussage **zurücknimmt** und `-121`/`-270` bestätigt; `settings.py:822` + `audit/apps.py:36` stützen `-121` | **FALSCH** — Registerzeile ist stale; die Korrektur steht nur im WP-Report |
| **332** | 15 als „nicht existent" gelistete `REQ-L2-AppSvc-*`, im Code referenziert | `matrix:721` „Verweise auf nicht existierende REQ-IDs \| 15 \| REQ-L2-AppSvc-…"; `rg -l 'REQ-L2-AppSvc' backend` → `import_service.py`, `export_service.py`, `tests/test_import_service.py` | **BESTAETIGT** |
| **335** | 4/10 ADRs ohne YAML-Frontmatter | `docs/se/ADR/` 10 Dateien; erste Zeile ist bei ADR-001/-002/-003/-DS-02 `# ADR-…` (kein `---`), bei 004-009 `---` | **BESTAETIGT** |
| **205** | Health-Aggregation statisch nicht entscheidbar → BLOCKED | `admin_ops/health_rest.py:72` `STATUS_OK = "ok"`; `:434` `STATUS_OK if ok else STATUS_DOWN`; `:459-461` ok/degraded/down; Aggregationspfad aus statischer Sicht nicht entscheidbar | **BESTAETIGT** (BLOCKED korrekt, kein PASS) |

---

## 3. Register-Quercheck (Duplikate)

| Paar | Verhältnis | Bewertung |
|---|---|---|
| **345 ↔ AUD-123** | Gleicher Defekt (Restore-Skript nie im Image). AUD-123 ist `Critical` (`scripts/restore.sh:183,186,198-213`); AUD-345 fügt nur die Matrix-Marker-Perspektive hinzu. Register klassifiziert 345 als `NEU` und zählt damit **denselben Critical doppelt**. | **Duplikat** — 345 sollte `DUPLIKAT`/Querverweis auf 123 sein; Schweregrad als eigenständiger Fund nicht haltbar (SOLL-STALE-Anteil = Medium). |
| **346 ↔ AUD-052** | Identische Zeile `providers.py:1080`, identischer Defekt. AUD-052 ist bereits `Critical` mit `BESTAETIGT(#118)`; AUD-345/346-Spalte im Register ohne CR-Track. | **Duplikat** — 346 sollte `DUPLIKAT` zu 052 sein; der WP-5-Mehrwert (REQ-L1-013-Marker) ist eine Traceability-Beobachtung, kein zweiter Defekt. |
| **204 ↔ AUD-121 / -270** | Registerzeile 366 (204) behauptet „nicht reproduzierbar"; WP-Report und `-270` bestätigen das Gegenteil. | **Widerspruch im Register** — Master-Zeile muss auf „BESTAETIGT (121/270 gelten)" korrigiert werden. |
| **348 ↔ AUD-002/-016** | WP-5 übernimmt die i18n-Zahl, ermittelt sie nicht neu (selbst deklariert). 112 (WP-3) vs. 116 (Ratchet/AUD-300). | **Cross-Ref mit Zahlendrift** — keine eigenständige Erhebung; 112 ist wahrscheinlich zu niedrig. |
| **349 ↔ AUD-070** | WP-5 §A5 verlinkt „Round-Trip-Defekt AUD-070", der am 2026-09-30 **WIDERLEGT** wurde (`AUDIT_FINDINGS.md:193,542-554`). Der CSV-`success`-Kernbefund bleibt, der Link ist tot. | **Stale-Querverweis** — Hyperlink korrigieren. |
| **350 ↔ AUD-120** | Kein eigener Beleg, reine Referenz auf den bestätigten 4×-Fanout. | **zulässiger Cross-Ref** (kein Duplikat-Zähler nötig, da inhaltlich neuer REQ-Marker-Aspekt). |

---

## 4. Verdikt-Zählung

| Verdikt | Anzahl | IDs |
|---|---:|---|
| **BESTAETIGT** | **21** | 191, 194, 198, 200, 201, 202, 203, 205, 330, 331, 332, 333, 334, 335, 339, 340, 342, 343, 347, 349, 350 |
| **TEILWEISE** | **10** | 192, 193, 195, 196, 197, 199, 344, 345, 346, 348 |
| **FALSCH** | **1** | 204 |
| UEBERZOGEN | 0 | — |
| UNTERSCHAETZT | 0 | — |
| NICHT VERIFIKABAR | 0 | (Teilzahlen 65/112 als Prüfschritt in §6) |
| KEIN REQOGNILOOM-BEZUG | 0 | (WP-5 betrifft ausschließlich Produkt-Repo-Doku/CI/Tests) |
| **Summe** | **32** | |

**Severity-Korrekturen** (nur wo das Verdikt TEILWEISE/FALSCH ist):
- **345** Critical → **eigenständig Medium** (Duplikat des Critical AUD-123; im Register nicht als zweiter Critical zählen).
- **346** Critical → **Duplikat von Critical AUD-052** (kein eigener Schweregrad).
- **193/195** High bleibt, aber die Zahl ist auf **443** zu setzen (Registerzeile 255 ist stale).
- **192** High bleibt (42,9 % korrekt); die Sub-Zahl „3,6 % der Tests" ist zu streichen/richtigzustellen.

---

## 5. Key-Verdikte

1. **AUD-345 + AUD-346 (beide Critical) sind Redundanzen.** Beide bestätigen einen
   bereits erfassten Critical-Defekt (`123` bzw. `052`) und erhöhen die
   Critical-Zählung ohne neuen Defekt. Der Traceability-Mehrwert ist real
   (Marker `Implemented` vs. Code-Realität), gehört aber als SOLL-STALE/Querverweis
   in einen Fund, nicht als zweiter Critical. **Konsequenz:** die im Audit
   kommunizierte Critical-Zahl für WP-5 ist um 2 überhöht.

2. **AUD-204 ist FALSCH.** Die Register-Master-Zeile (`AUDIT_FINDINGS.md:366`)
   trägt weiter die am selben Tag **zurückgenommene** Aussage „Archivierung nie
   registriert — nicht reproduzierbar". Der WP-Report (`AUDIT_TRACEABILITY.md:148-161`)
   und `AUD-270` belegen das Gegenteil. Das ist kein Falschbefund der Analyse,
   sondern ein **Register-Sync-Fehler** (§9 des WP-Reports enthält die Korrektur,
   §3 des Registers nicht).

3. **AUD-197 ist TEILWEISE.** Die Kernzahl **0 REQ-IDs in den 11 beta-Abnahme-
   berichten** ist exakt reproduziert. Die Zusatzbehauptung „die Berichte
   enthalten **keine Checkboxen**" ist widerlegt: `TESTPLAN_v1.8.0-beta.15`
   (3), `-16` (3) und `-17` (10) enthalten sehr wohl `- [ ]`-Checkboxen.

4. **AUD-342 ist der stärkste eigenständige Treffer.** `REQ-L2-MC-014` behauptet
   wörtlich „MCP-Server exportiert das Tool `semantic_search` standardkonform",
   `Implemented/Covered` — und es existiert weder Tool noch Modul; nur ein
   Testmethodenname nennt den String. Voll bestätigt.

5. **AUD-330/331/333/339 sind voll bestätigt** und unabhängig der Kernthese des
   Audits zuträglich: 324 fehlende IDs, 0 L3-Zeilen, `open_adrs` nirgends (außer
   in den Audit-Dokumenten selbst), `arch_impact`-Umschreibung ohne ADR.

---

## 6. Zahlen-Nachrechnung

| Kennzahl | Audit-Angabe | Nachgerechnet | Methode | Bewertung |
|---|---|---:|---|---|
| Quell-REQ-IDs | 835 | **835** | `rg` unique über `docs/se/L0`+`L1` | exakt |
| Matrix-IDs | 511 | **511** | `rg` unique über Matrix | exakt |
| Fehlende IDs | 324 (24 L2 / 300 L3) | **324** (24/300, 0/0) | Mengendifferenz | exakt |
| L0/L1/L2/L3 Quelle | 58/94/329/354 | **58/94/329/354** | filter per Ebene | exakt |
| Matrix je Ebene | 58/94/305/54 | **58/94/305/54** | filter per Ebene | exakt |
| L3-Zeilen in Matrix | 0 | **0** | `rg -c '^\| REQ-L3-'` | exakt |
| REQ mit Test-Bezug | 358 (42,9 %) | **358 (42,9 %)** | Mengenschnitt 835 × 366 | exakt |
| REQ ohne Test-Bezug | 477 (57,1 %) | **477 (57,1 %)** | Komplement | exakt |
| „366/10 052 = 3,6 % Backend-Testdefinitionen" | 3,6 % | **nicht reproduzierbar** | 366 = unique REQ-IDs in Testdateien; Testfunktionen in REQ-haltigen Backend-Dateien = **3 207/10 052 = 31,9 %**; Backend-Testdateien mit `REQ-L` = **179** (nicht 256) | **Etiketten-Verwechslung** |
| `open_adrs` | 0/835 | **0 in `docs/se/**`** | `rg -l` | exakt (Treffer nur in Audit-Docs) |
| Non-CI-Tests (kanonisch) | 443 | **443** | 658 Dateien − 20 CI-Pfade; `^\s*def test_` | **exakt reproduziert**: 34 ungedeckte Dateien, 443 Funktionen, 7 684 gedeckt, Σ 8 127 |
| Non-CI-Tests (WP-5) | 511 | **nicht erneut ausgeführt** | `pytest --collect-only memory/tests link_types/tests tests` | offener Prüfschritt; Zahl durch Synthese auf 443 adjudiziert |
| Non-CI-Tests (Vor-Audit) | 463 | **nicht zutreffend** | bezieht sich auf `attribute_definitions` (läuft in `set-2-api`) | Zahl ist kein CI-Gap |
| 65 FE-Fehlschläge | 65 | **nicht erneut ausgeführt** | erfordert `vitest run` unter Node ≥ 22.4 | offener Prüfschritt |
| i18n fehlende Keys | 112 | **widersprüchlich** | Ratchet `MISSING_KEY_BASELINE = 116` (`i18n-parity.test.ts:186`) | 112 vs. 116 offen |
| ADR-Frontmatter | 4/10 fehlen | **4/10 fehlen** | erste Zeile `---` | exakt |
| Frontmatter Requirements | 104/121 fehlen | **104/121 fehlen** | erste Zeile `---` | exakt |
| `arch_impact:true` L1 | 15 | **15** (+1 false) | zeilenweise Auswertung L1-Datei | exakt |

**443-Methode (offengelegt, reproduzierbar):** Alle Dateien
`backend/**/test_*.py` + `tests.py`, ohne `__pycache__`/`migrations` = **658**.
Abdeckung gegen die 20 Pfade in `.github/workflows/ci.yml:44-55`
(`application/tests` … `audit/tests`) = `<app>/tests/*`. Ungedeckt: **34 Dateien**
(`link_types/tests` 14, `memory/tests` 13, `backend/tests/` 4,
`application/test_run_service.py`, `application/test_service.py`,
`mcp_server/tools/tests.py`). `def test_`-Funktionen: **443 ungedeckt / 7 684
gedeckt = 8 127**. Die im Audit-Verification-Dokument genannte Zahl „18 Matrix-
Pfade" ist ungenau (es sind 20) — das Ergebnis 443 ist davon unberührt.

---

## 7. NEU-AUDIT-LUECKE

| # | Lücke | Was fehlt | Prio |
|---|---|---|---|
| L1 | **Register-Sync AUD-204** | Master-Zeile `AUDIT_FINDINGS.md:366` trägt die zurückgenommene Aussage; Korrektur existiert nur im WP-Report. | Hoch (Widerspruch im kanonischen Register) |
| L2 | **Doppelzählung Critical 345/346** | Beide sind Duplikate (123/052); Register zählt denselben Defekt zweimal als Critical. | Hoch |
| L3 | **AUD-193-Zahl im Register** | Master-Zeile `:255` nennt noch 511, die Synthese kanonisch 443. | Mittel |
| L4 | **AUD-192 Sub-Zahl „3,6 % der Tests"** | Etiketten-Verwechslung (unique IDs vs. Testdefinitionen); die korrekte Zahl ist 31,9 % (3 207/10 052) bzw. 179 REQ-haltige Backend-Testdateien. | Mittel |
| L5 | **AUD-197 Checkbox-Behauptung** | 3 der 11 Abnahmeberichte enthalten Checkboxen (TESTPLAN .15/.16/.17). | Mittel |
| L6 | **i18n 112 vs. 116** | WP-5 übernimmt 112, Ratchet/AUD-300 nennt 116. | Mittel |
| L7 | **AUD-348/349 tote Querverweise** | 348 baut auf 112 (statt Ratchet), 349 verlinkt das widerlegte AUD-070. | Niedrig |
| L8 | **Auftragsnotiz „316/324"** | Kein 316-Bezug in WP-5 auffindbar; 316 ist eine WP-3b-Finding-ID. Die belegte Zahl ist 324. | Info |

---

## 8. Fazit

Die **Kernzahlen des WP-5-Audits halten einer unabhängigen Nachrechnung stand**:
835/511/324, 358 (42,9 %), 0 L3-Zeilen, `open_adrs` 0, 104/121 Frontmatter, 15
`arch_impact:true`, 4/10 ADR-Frontmatter und die 443-CI-Testlücke sind
**exakt reproduziert**. Die Schwächen liegen (a) in **Register-Hygiene**
(Doppelzählung 345/346, stale Zeile 204, stale Zahl 193) und (b) in
**Etiketten-Verwechslungen** zweier Sub-Zahlen (192 „3,6 %", 348 „112"). Kein
WP-5-Finding musste als FALSCH im Sachkern verworfen werden — außer der
Registerzeile 204, die dem eigenen Korrekturstand widerspricht.
