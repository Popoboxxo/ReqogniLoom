# VWZ-Vergleich: fachliche Lücken und Verbesserungsvorschläge für ReqogniLoom

> **Status:** Entwurf zur Review (2026-11-16). Keine Umsetzung, keine Issues angelegt.
> **Art:** Spezifikation von Verbesserungsvorschlägen. Kein Task-Plan. Aufgaben entstehen erst nach Freigabe.
> **Basis:** `origin/main` `fe34e583`, ReqogniLoom 1.9.0-beta.2. VWZ-Stand: Webseite `<Webseite>` und **Quellcode** `<Quellrepo>` HEAD `ebade476` (2026-10-28, Go, GPL-3.0, Version v0.1.x-alpha), gelesen am 2026-11-16.
> **Fokus:** nur die **fachlichen Konzepte**. Der Ansatz ist verschieden (VWZ: Markdown in Git, CLI, kein Server. ReqogniLoom: Mehrmandanten-Plattform mit Datenbank, Workflow, MCP). Wir vergleichen nicht den Ansatz, sondern was VWZ fachlich **strenger, einfacher oder besser prüfbar** macht.
> **Namensregel:** Das Vergleichswerkzeug wird auf Wunsch von Daniel nirgends beim Namen genannt. Es heißt hier **VWZ**. Bezeichner des Werkzeugs sind entsprechend umbenannt (`x-vwz`, `vwz-suppress`, `vwz-code`, …). `<Webseite>`, `<Quellrepo>` und `<Fremdrepo>` stehen für die Originalquellen. Der Quellenindex liegt bewusst außerhalb des Repos.

## 0. Vorgeschichte und Abgrenzung

Es gibt bereits `docs/superpowers/plans/2026-08-08-vwz-interop-and-inspiration-concept.md` (1241 Zeilen). Es bewertet VWZ aus dem **README** und schlägt eine Import/Export-Brücke plus sieben Konzepte vor. Es steht in `docs/superpowers/plans/index.md` als *Deferred*.

Diese Spec ersetzt es nicht, sondern **aktualisiert und erweitert** es:

| Punkt | Konzept vom 2026-08-08 | Stand heute (verifiziert) |
|---|---|---|
| Waiver / Unterdrückung (§8.6) | fehlt | **gebaut** (#569, #821: `backend/baseline/waivers.py`, MCP `audit.waive_finding`) |
| Baseline-Diff nach Inhalt (§8.5) | fehlerhaft (#398) | **gebaut** (`backend/baseline/diff_engine.py`: erfasste Feldwerte entscheiden `changed`) |
| CTRF-Import, ergebnisgetriebene Abdeckung (§8.1) | fehlt | **fehlt weiter** (kein `ctrf`/`junit`/`xunit` im Backend, geprüft) |
| Versions-gepinnte Links (§8.2) | fehlt | **fehlt weiter** (nur Boolean `suspect`, kein `target_version`/`repin`, geprüft) |
| `disposition` (§8.7a) | fehlt | **fehlt weiter** (geprüft, Treffer sind HTTP-`Content-Disposition` und Workflow-Kommentare) |
| Quelle über VWZ | README | **Webseite (fast vollständig) und Quellcode**: neu sind Verdict-Rollup, manuelle Verifikation, Disjunktheits-Check, `repin`, Varianten per Filter, `vwz-code`, `vwz-import`, Agenten-Skills. Der Code zeigt die exakte Semantik (Abschnitt 2b) |

Die Brücke (ReqogniLoom ⇄ VWZ-Verzeichnisbaum) ist **nicht** Gegenstand dieser Spec. Sie bleibt vertagt (siehe Entscheidung E8).

## 1. Kurzfazit

VWZ ist an vier Stellen fachlich **strenger**, an zwei Stellen **einfacher bedienbar** als ReqogniLoom. In allen Fällen liegt die Stärke in der **Prüfbarkeit durch Automatik**, nicht in mehr Funktionen.

**Strenger:**
1. **Abdeckung heißt Nachweis.** VWZ rechnet ein Testergebnis in einen Befund um (`failing-verdict`, `missing-verdict`). ReqogniLoom zählt ein Requirement als abgedeckt, sobald ein `verifies`-Link auf einen Test zeigt, auch wenn der Test nie lief oder rot ist.
2. **Links merken sich den Stand.** `trace: [SYS-001~3]` bindet an Version 3. Ändert sich SYS-001, wird der Pin veraltet gemeldet und per `repin` bewusst nachgezogen. ReqogniLoom kennt nur ein Boolean `suspect`.
3. **Abdeckung ist ein Vertrag.** `requires-trace-from` legt je Ebene fest, wer das Requirement abdecken muss, und nur *freigegebene* Anbieter zählen.
4. **Schema je Ordner.** Pflichtfelder, erlaubte Werte, Präfix und Verbot unbekannter Attribute gelten pro Dokumenttyp.

**Einfacher:**
5. **Ein Befehl, ein Ergebnis.** `VWZ check` prüft alles in einem Lauf mit Exit-Code. Das ist CI-tauglich ohne Zusatzarbeit.
6. **Standardformat statt interner IDs.** Testergebnisse kommen als CTRF-JSON, das viele Test-Runner ohnehin erzeugen.

**Unsere Vorteile** (Abschnitt 6): Mehrmandantenfähigkeit, Freigabe-Workflow mit CCB, Audit-Trail, MCP, KI-Ableitung, Interviews, Risiken, ADRs, Diagramme. VWZ verzichtet darauf ausdrücklich. Wir übernehmen davon **nichts** zurück.

## 2. Vorgehen und Belegstand

- VWZ-Aussagen: Webseite (Startseite, Cheat Sheet, FAQ, Compare, About, AI, Import, Benchmarks, Use-Cases, Quickstart 0–15, die drei Agent-Skills über `/ai/`) plus **Quellcode** (drei getrennte Tiefenanalysen: Check-Engine, Datenmodell/Parser/Filter/Baseline, Import/Code/Exporte/CI). **Nicht gelesen:** die letzten ~70.000 Zeichen von `llms-full.txt`, `site/` und Diskussionen im Repo. `/skills/` liefert 404. Der Code wurde **nicht ausgeführt**, Test-Aussagen beruhen auf Funktionsnamen und Greps. Leistungszahlen (720.000 Requirements in ~7 s) sind Herstellerangaben.
- **Widerspruch in VWZ, durch den Code geklärt:** Startseite sagt „Broken references warn", die FAQ-Passage „How does the trace check work?" sagt Fehler mit Exit-Code 1. Der **Code** meldet eine kaputte Referenz als **WARNING** (`internal/graph/graph.go:345,358`), README und Skill `vwz-usage` stimmen zu. Die FAQ-Stelle (`site/content/faq.md:95`) ist falsch. Zyklen, mehrdeutige Referenzen und doppelte IDs sind **ERROR**.
- ReqogniLoom-Aussagen: gegen den Code geprüft. **Selbst nachgeprüft:** keine CTRF/JUnit-Treffer, keine Pin-Felder, keine `disposition`, `coverage_calculator.py:60-68`, `diff_engine.py:30-40`, `models.py:2380-2396` (Suspect-Felder), `models.py:1895` (`verification_method`), `TestRunResult.status`. **Aus Agenten-Befund, per Stichprobe plausibel, nicht einzeln nachgeprüft:** alle weiteren Dateistellen in Abschnitt 3 (als „Agent" markiert). Vor jeder Umsetzung muss die jeweilige Task-Planung den Beleg frisch prüfen (`scripts/check_plan_refs.py`).
- Frontend-Funktionen (Ansichten, Coverage-UI) wurden nur oberflächlich geprüft.

## 2b. Was der VWZ-Quellcode über die Doku hinaus zeigt

Belege: `internal/graph/graph.go` (G), `internal/verify/` (V), `internal/schema/`, `internal/parser/`, `internal/filter/`, `internal/repin/`, `internal/cli/`. Aussagen mit „(Inf.)" sind Schlüsse aus dem Code, nicht getestet.

### Reife und Risiko

- 115 Go-Dateien, ~17.200 Zeilen ohne Tests, 483 Testfunktionen, 50 Commits (2026-07-30 bis 2026-10-28) von praktisch **einem Autor**, Version alpha.
- **Die CI führt kein `go test`, kein `go vet` und kein Lint aus.** Es laufen nur Site-Build, Release und PyPI-Publish. Die `.golangci.yml` ist vorhanden, wird aber nicht aufgerufen.
- `spec/` ist ein Beispielprojekt (V-Modell-Dogfood mit 293 handgeschriebenen Requirements), **keine formale Spezifikation**. Konformitätstests dagegen fehlen.
- Lizenz GPL-3.0. Für uns gilt: **Konzepte übernehmen, keinen Code** (E11).

### Exakte Semantik der Kernprüfungen

| Thema | Verhalten im Code |
|---|---|
| Schwere | kaputte Referenz WARNING. Mehrdeutige Referenz, doppelte ID, Zyklus, fehlender Parent ERROR. Exit 2 bei Parse- oder Schema-Fehler, 1 bei mindestens einem ERROR, sonst 0. WARNING und INFO ändern den Exit-Code nie (`reporter.go:81-107`) |
| Zyklen | rekursive DFS über Trace- und Parent-Kanten, O(V+E). Gemeldet wird nur die Rückkante, nicht die Kette. Der Filter wird nicht angewendet (G:549-588) |
| ID-Auflösung | qualifiziert `document-id/ID` zuerst als Dokument-ID, dann als Verzeichnispfad. Unqualifiziert global. Existiert die ID in mehreren Dokumenten, ERROR „ambiguous" und **keine Kante** (G:325-369) |
| Version | `version` ist ein **von Hand gepflegtes Integer-Attribut**, kein automatischer Zähler. Pins `~N` werden nur geprüft, wenn das Ziel `version > 0` hat und nicht `external` ist (G:889) |
| Pin-Befunde | Pin < Version: *outdated*, ERROR (mit `--relaxed-versions` WARNING). Pin > Version: *predated*, immer ERROR, wird von `repin` nie korrigiert. *unpinned* ist kein Befund, nur mit `repin --promote-unpinned` nachziehbar |
| `repin` | schreibt byte-genau **nur innerhalb von `attr`-Blöcken**, Ganz-Ref-Match mit Grenzprüfung, Präfix `doc-id/` bleibt, Pfade bleiben im Root (`os.Root`). Trockenlauf ist Standard |
| Coverage-Anbieter | nur `status == approved`. **Fehlt `status`, gilt Default `approved`.** Jeder zusätzliche Status-Wert aus `additional-status-values` zählt **nicht** als Anbieter (G:1654). `ignore-status` macht alles zum Anbieter |
| Coverage-Erwartung | `requires-trace-from` am Requirement gewinnt vor dem Dokument-Default. `[]` schaltet ab. Tokens lösen zuerst als Dokument-ID, dann als Level-Name auf. Unbekannter Token: WARNING |
| Coverage ohne Konfiguration | **Fallback aus der Struktur:** „untraced" (nichts zeigt darauf) und „no upstream reference". Wurzel und Blatt werden aus `upstream.sources` abgeleitet, `external` zählt als Wurzel (G:449, 725-760) |
| Gefilterte Coverage | Der Graph wird immer aus dem **vollen Baum** gebaut, damit Referenzen auflösen. Geprüft und gezählt wird nur in der Sicht. Ein ausgefilterter Anbieter deckt nicht ab (G:641) |
| Verdict-Schlüssel | `(Ziel ohne Pin, Case)`. Neuestes `verified-at` gewinnt, bei Gleichstand die lexikalisch kleinere Quelle. Manuelle Daten nur als `YYYY-MM-DD` (V:95-100, 365) |
| Rollup | Reihenfolge `none < pass < skipped < inconclusive < fail`, das Maximum gewinnt (G:1100). **Beweismenge = eigene Ergebnisse plus die aller freigegebenen Inbound-Items, rekursiv** (G:1195-1250) |
| `missing-verdict` | läuft **nur, wenn Ergebnisse übergeben wurden** (`--results`). Bedingung („measureGate"): `verify`-Attribut, approved, nicht deferred/rejected. **`skipped` zählt als Beweis**, es gibt dann kein Missing (G:967-1020) |
| CTRF | passed→pass, failed→fail, skipped→skipped, **flaky→inconclusive** (unabhängig vom Endstatus), alles andere→inconclusive. Ohne Bindung (`id` oder `verifies`) entsteht die Warnung `unbound-result` |
| Disposition | `mandatory-disposition` fehlt: ERROR. Begründung fehlt bei `deferred`/`rejected`: WARNING. Deferred und rejected nehmen das Requirement aus `missing-` und `failing-verdict` |
| Disjunktheit | je ausgehender Kante (auch Eltern-Kante) ohne gemeinsamen Wert ERROR. **Leer oder fehlend = „gilt für alle", also ausgenommen** (G:1717) |
| Schema | **ein Schema pro Verzeichnis, keine Vererbung**, JSON Schema 2020-12. Eingebaute Attribute werden eingefügt, Neudefinition wird abgelehnt |
| Filter | `expr-lang`. Unbekannte Attribute sind ein Compile-Fehler, `status` ist im Filter `nil`, wenn nicht gesetzt (der Default `approved` gilt nur im Graph) |
| Baseline-Diff | vergleicht **nur Attribute** (Identität = Dokumentpfad + ID). **Body, Titel und Begründung werden nicht verglichen.** Deshalb muss der Autor `version` von Hand erhöhen. Schemas und Submodul-Pins werden ausgewiesen |
| Code-Import | stabile ID = `Name-` + 7 Hex aus FNV-1a über (Package, Name bzw. `Receiver.Name`), ohne Zeile und Dateipfad. **Keine Rename-Erkennung, keine Erkennung generierten Codes.** Kollisionen (28 Bit) werden mit Warnung übersprungen |
| `aspice`-Preset | **dünn**: ein Schema mit `asil`-Pflicht (QM/A/B/C/D), `safety-goal`, `owner`, `additionalProperties: false`. Keine Ebenenhierarchie, keine Coverage-Regeln. Das ist eine ISO-26262-Anmutung, kein ASPICE-Prozessmodell |
| HTML-Export | eingebettet per `go:embed`, ohne CDN. Dokumentansicht serverseitig, Tabelle/Trace/Coverage clientseitig aus einem eingebetteten JSON-Modell |

### Fallstricke und Fehler in VWZ (wir kopieren sie nicht)

1. **Stiller Verlust:** ungültiges `x-vwz` (z. B. `level`, `upstream`) ergibt `nil` ohne Fehlermeldung. Unbekannte Namen in `vwz-suppress` werden nirgends gemeldet. Frontmatter-Fehler in großen Dateien werden verworfen.
2. **Doppelte IDs:** der erste gewinnt, die Trace-Kanten des verworfenen Duplikats landen am ersten Knoten (Inf., kein Test). Der Befund ist nicht unterdrückbar.
3. **ID-Präfix-Kollision** wird je Datei, nicht je Verzeichnis geprüft. Die Doku sagt „zwei Verzeichnisse". Das Ergebnis hängt von der Map-Reihenfolge ab (Inf.).
4. **Nicht deterministische Befund-Reihenfolge** an mehreren Stellen (Map-Iteration). Ob der Reporter nachsortiert, ist ungeklärt.
5. **Inkonsistenz:** `MeasureOutcome` liefert das erste Ergebnis statt des Rollups. `ResolveTraceRef` hält eine mehrdeutige Referenz für aufgelöst.
6. **Der Baseline-Diff sieht reine Textänderungen nicht**, solange niemand `version` erhöht. Das ist die Lücke, die bei uns der inhaltliche Diff (#398) schon schließt.
7. **Testlücken** (nach Funktionsnamen): kein Test für mehrdeutige Referenzen, `--relaxed-versions`, `skipped`/`inconclusive` im Rollup, den Tie-Break, Suppression von `broken-ref` und `circular`, CRLF.
8. **`vwz-code` extrahiert auch Testdateien und generierten Code** und nimmt nur Top-Level-Symbole. Veraltete `.md`-Dateien werden nie gelöscht (Inf.).
9. **Keine CI-Tests** für ein Werkzeug, dessen Zweck Prüfsicherheit ist.

**Folgerung für uns:** VWZs Konzepte sind gut, die Umsetzung ist ein alpha-Einzelprojekt. Wo wir übernehmen, müssen die Randfälle (Duplikat, Mehrdeutigkeit, Suppress-Typos, Determinismus) **von Anfang an mit Tests** abgedeckt sein.

## 3. Fähigkeitsvergleich

Legende: **Ja** vorhanden, **Teil** teilweise, **Nein** fehlt. „Beleg" nennt Datei oder Quelle.

| # | VWZ-Fähigkeit | ReqogniLoom | Beleg ReqogniLoom |
|---|---|---|---|
| F1 | Verdict-Rollup (fail > inconclusive > skipped > pass, neuester Lauf gewinnt) | **Nein** | Run-Status passed/failed/blocked/not_run, kein Rollup (`models.py` `TestRunResult.status`) |
| F2 | Befunde `missing-verdict` / `failing-verdict` | **Nein** | VERIF-P8 prüft nur Link-Existenz (Agent: `rules/coverage_consistency.py:299`) |
| F3 | Import von Testergebnissen im Standardformat (CTRF) | **Nein** | nur interne `test_case_id` (UUID) (Agent: `test_run_service.py:263`) |
| F4 | Manuelle Verifikation (Review, Inspection, Analysis, Demonstration) mit Verifier, Evidenz, Datum | **Teil** | `verification_method` als Feld (`models.py:1895`), keine strukturierten Ergebnisse |
| F5 | Versions-Pins auf Links, `repin` | **Nein** | nur `suspect` Boolean, `suspect_flagged_at` (`models.py:2380-2396`) |
| F6 | `requires-trace-from` je Ebene oder Typ | **Nein** | Coverage zählt nur `verifies`-Links (`coverage_calculator.py:60`) |
| F7 | Nur freigegebene Anbieter zählen | **Teil** | KI-erzeugte, ungeprüfte Tests zählen nicht (`coverage_calculator.py:68`), Gate nur im Extended-Tier (Agent: `precondition_rules.py:671`) |
| F8 | Schema je Dokumentordner (Pflicht, Enum, kein Zusatzattribut, ID-Präfix) | **Teil** | Attributdefinitionen je Item-Typ und Rigor-Tier (Agent: `attribute_definitions/schema.py`), nicht je Dokument oder Ebene |
| F9 | `disposition` (implemented/deferred/rejected) mit Begründung | **Nein** | nur Workflow-Zustände und `change_reason` |
| F10 | Disjunktheits-Check über Trace-Kanten (z. B. `variant`) | **Nein** | nur `ASILLevel`-Enum, keine Mengenprüfung (Agent: `models.py:412`) |
| F11 | Filter-Ausdruck als Sicht, Coverage/Export/Baseline innerhalb der Sicht | **Teil** | typisiertes JSON-Filter-DSL und `SavedView` für Tabellen (Agent: `rest_api/table_views.py`), nicht als Scope für Coverage, Export, Baseline |
| F12 | Baseline-Diff inhaltlich, Schema-Änderungen, zwei Teilmengen im selben Stand | **Teil** | inhaltlicher Feld-Diff **ja** (`diff_engine.py`), Schema-Diff und Teilmengen-Vergleich **nein** |
| F13 | Ein Prüflauf über alles, Exit-Code 0/1/2, `--json` | **Teil** | SE-Auditor mit Findings und Severity per REST/MCP (Agent: `audit/rule_engine.py`), kein CI-Exit-Code, kein CLI |
| F14 | Einzelne Prüfung je Requirement unterdrücken | **Ja** | auditierte Waiver (`baseline/waivers.py`), strenger als VWZ (Ablauf, Begründungspflicht) |
| F15 | Zyklen im Trace-Graph | **Ja, anders** | Prüfung beim Schreiben (Agent: `trace_link_manager.py:112,136`), nicht als Audit-Lauf |
| F16 | Standalone-HTML-Report (Dokument, Tabelle, Trace, Coverage) | **Nein** | nur PDF/CSV/ReqIF/JSON/VCRM (Agent: `export_service.py`, `vcrm_report_generator.py`) |
| F17 | NDJSON-Export für Data Warehouse (deterministisch) | **Nein** | `export_json` ohne NDJSON (Agent) |
| F18 | Code-Symbole als Requirements importieren (`vwz-code`, stabile IDs) | **Nein** | nur CSV und ReqIF-Import |
| F19 | Projektvorlagen (`init`: generic, ASPICE, results) | **Teil** | Rigor-Presets und Attribut-Bootstrap, keine Prozessvorlage |
| F20 | Agenten-Zugang: Skills, `AGENTS.md`, `llms.txt`, CLI mit `--json` | **Teil** | 8 Skills in `dist/agent-skills/`, MCP. Kein `llms.txt`, kein CLI |
| F21 | Git als Wahrheitsquelle, PR-Review als Freigabe | **Nein, bewusst** | Plattform nutzt Datenbank, Workflow, CCB. Dokument-Projektion (#1374) ist der Berührungspunkt |

## 4. Verbesserungsvorschläge

Jeder Vorschlag nennt Ziel, Vorgehen, prüfbare Akzeptanzkriterien (A), Abgrenzung, Aufwand (grob, in Tasks), Abhängigkeit. Aufwand ist Schätzung, nicht Zusage.

### K1 Konzeptbedarf: Ausführungsstatus am Trace (offen, Daniel 2026-11-16)

**Anforderung (Antwort zu E1, sinngemäß):** Der Trace bleibt. Zusätzlich muss sinnvoll erkennbar sein, ob der verknüpfte Test ausgeführt wurde, nicht ausgeführt wurde, grün oder rot ist oder einen anderen Zustand hat. Die Entscheidung über das **Wie** ist **zurückgestellt**. Das Konzept fehlt und ist wichtig.

Diese Spec entscheidet das nicht. Sie ordnet die Entwurfsfragen, damit das Konzept gezielt entschieden werden kann. Die Reihenfolge der Fragen ist ein Vorschlag, jede wird einzeln mit Daniel geklärt.

| ID | Entwurfsfrage | Optionen (Auswahl) | Hinweis aus VWZ-Code und Bestand |
|---|---|---|---|
| K1.a | **Wo hängt der Status?** (**entschieden: gespeichertes Feld am Link**) | (1) abgeleitet aus Testläufen, nichts Neues gespeichert. (2) als abgeleiteter Zustand an der `verifies`-Kante. (3) als abgeleiteter Zustand am Requirement. (4) gespeichertes Feld | VWZ speichert nichts, es berechnet je Lauf. Bei uns existieren `TestRun` und `TestRunResult` schon. Abgeleitet vermeidet Widersprüche zwischen zwei Quellen |
| K1.b | **Zustandsmodell** (**zurückgestellt, Richtung: konfigurierbar als Workflow-Erweiterung**) | `kein Test`, `nicht ausgeführt`, `bestanden`, `fehlgeschlagen`, `blockiert/unklar`, `übersprungen`, `veraltet` | VWZ kennt vier Ergebnisse (pass, fail, skipped, inconclusive). „Nicht ausgeführt" und „kein Test" sind dort Befunde, keine Zustände. **„Veraltet"** (Requirement oder Test hat sich nach dem Lauf geändert) kennt VWZ nur über Pins am Ergebnis (Test `TestVersionPin_StaleResultPin`, Inf.). Das hängt mit V4 zusammen |
| K1.c | **Rollup-Regel** | strikt wie VWZ (`fail` schlägt `inconclusive` schlägt `skipped` schlägt `pass`), oder konfigurierbar je Rigor-Tier | `skipped` zählt in VWZ als Beweis, also kein „fehlt". Ob das für uns gelten soll, ist offen |
| K1.d | **Beweismenge** | nur direkte Tests, oder auch Tests der Kind-Anforderungen (rekursiv) | VWZ zählt freigegebene Inbound-Items rekursiv mit (G:1195-1250). Für unsere V-Modell-Ebenen L0–L3 entscheidet das, ob ein L3-Test das L1-Requirement „beweist" |
| K1.e | **Wie lange gilt ein Ergebnis?** | immer das neueste, Ablauf nach Zeit, Ablauf bei Änderung des Requirements/Tests | VWZ: neuestes `verified-at` je (Ziel, Case) |
| K1.f | **Quellen der Ergebnisse** | CI (CTRF/JUnit), manuell (Review/Inspektion/Analyse/Demonstration), KI-erzeugt (zählt bei uns heute nicht, #424) | siehe V2, V3 |
| K1.g | **Darstellung** | eine Kennzahl, zwei Kennzahlen (`covered`, `verified`), oder eine Matrix Trace-Abdeckung × Nachweisstatus; Trace-Ansicht färbt Kanten | VWZ zeigt in der Coverage-Ansicht Coverage- und Verdict-Zustand getrennt (`CoverageStates`, `VerificationStates`) |
| K1.h | **Wirkung auf Freigabe und Baseline** | nur Anzeige, Warnung, Blocker je Rigor-Tier | bestehendes Gate `require_verification_on_approval` gilt heute nur im Extended-Tier |

**Entschieden (Daniel, 2026-11-16):**

- **K1.a: gespeichertes Feld am Link** (`verifies`-Kante), nach der Richtung „Unter-Workflow" im Abschnitt K1-Ansatz als `WorkflowItemState` der Kante ausgestaltet (Bestätigung offen). Bewusst gegen die Empfehlung „abgeleitet", Begründung liegt bei Daniel. Folgen, die das Konzept beantworten muss:
  - Das Feld ist ein **Cache**, die Quelle der Wahrheit bleiben `TestRun`/`TestRunResult`. Es braucht eine **Abgleich-Funktion** (Neuaufbau aus den Läufen), damit Abweichungen heilbar sind (K1.a1).
  - Schreibpfade: Abschluss eines Laufs und `test.run_report_results`. Das Schreiben des Feldes darf **weder `suspect` noch den Concurrency-Zähler auslösen** und braucht eine eigene Audit-Regel (K1.a2).
  - Inhalt des Feldes mindestens: Zustand, Lauf-Referenz, Zeitpunkt, und der Inhaltsstand von Requirement und Test zum Zeitpunkt des Laufs (Grundlage für „veraltet", hängt an V4-S0) (K1.a3).
  - **Backfill** für Bestandskanten aus dem jeweils letzten Ergebnis, mit Migration nach der Roadmap-Regel (nacheinander mergen, renummerieren).
  - **Baselines** müssen den Feldwert miterfassen oder bewusst ausschließen (K1.a4).
  - Row-Level-Security und Mandantentrennung wie bei jedem Link-Feld.

- **K1.b: zurückgestellt, Richtung gesetzt.** Das Zustandsmodell soll **konfigurierbar** sein, als eine Art **Workflow-Erweiterung oder -Anpassung**, und wird später tiefer analysiert. Anknüpfungspunkt: konfigurierbare State-Machines je Workspace (ADR-06, `backend/workflow/`). Bei der Analyse zu klären:
  - Ob die Workflow-Engine Kanten (Links) als Gegenstand unterstützt, oder bisher nur Artefakte. **Nicht geprüft.**
  - Welche Zustände und Übergänge je Workspace und Rigor-Tier frei konfigurierbar sind und welche Mindestzustände fest bleiben.
  - Ob Übergänge **automatisch aus Testläufen** entstehen (ereignisgetrieben), manuell, oder beides, und ob das Mapping „Lauf-Ergebnis → Zustand" konfigurierbar ist.
  - **Hinweis (Vorschlag, nicht entschieden):** Jeder konfigurierte Zustand erhält eine feste **Ergebnisklasse** (bestanden / negativ / unklar / übersprungen / offen). Rollup, Befunde und Freigabe-Gates arbeiten auf der Klasse, nicht auf dem frei benannten Zustand. So bleiben die Prüfungen unabhängig von der Konfiguration berechenbar.
  - Zusammenspiel mit dem Zustand „veraltet" (K1.b ursprünglich) und mit V4.

### K1-Ansatz: Teststand als konfigurierbarer Unter-Workflow der Verifikationskante

**Richtung (Daniel, 2026-11-16, sinngemäß):** Der Testzustand zwischen Requirement und Testfall soll ein **konfigurierbarer Unter-Workflow** sein. Möglicherweise lässt sich das mit dem vorhandenen Workflow-System schon abbilden. Das Befüllen ist **eine systemeigene Auswertung**. Das gehört in die Spec. Dies ist eine Richtung, die Bestätigung der Ausgestaltung steht noch aus.

**Entschieden (Daniel, 2026-11-16):** Der technische Weg bleibt **offen**. Das K1-Konzeptdokument vergleicht beide Wege gegeneinander: (A) neuer Workflow-Item-Typ an der Kante (Entwurf unten) und (B) lose Spalte am Link mit eigener, konfigurierbarer Zustandsliste außerhalb der Workflow-Engine. Der Vergleich nennt je Weg Aufwand, Risiko, Datenmenge, Konfigurationsmodell und Folgen für Verlauf, Sperre und Mandantentrennung. Danach entscheidet Daniel.

**Befund am Code** (Stand `origin/main` `c27d172a`, selbst geprüft):

| # | Befund | Beleg |
|---|---|---|
| 1 | Die Engine führt Zustände **je Item**: `WorkflowItemState` mit `item_id` (UUID, beliebiger Typ), `item_type`, `definition`, `current_state`, Optimistic-Lock-`version`. Definitionen sind je Workspace konfigurierbar, mit Verlauf | `workflow/models.py:201-241`, `workflow/definition_store.py` |
| 2 | Welche Typen die Engine führt, steht in **einer** Registry: 14 Typen, u. a. `TestCase`, `Document`. Neue Typen werden dort eingetragen, ein Konsistenztest zieht die übrigen Kopien nach | `workflow/item_types.py:30-47`, `workflow/tests/test_item_type_registries_consistent.py` |
| 3 | Ein **Trace-Link ist heute ausdrücklich kein workflow-geführtes Item** („no WorkflowItemState per link"). KI-Vorschläge werden über `proposed_by`/`proposed_at` markiert, nicht über einen Zustand | `persistence/models.py:2341-2343` |
| 4 | `TestCase` hat schon einen Workflow (`testcase_default`). Das ist der **Lebenszyklus des Testfalls**, nicht sein Ausführungsstand. Beide dürfen nicht vermischt werden | `workflow/item_types.py:36` |
| 5 | Eine Übergangsdefinition kennt nur `from_state`, `to_state`, `allowed_roles`, `requires_change_reason`, `signature_gate`. **Es gibt kein Merkmal „löst das System aus"** | `workflow/definition_store.py:41-60` |
| 6 | Systemübergänge laufen heute über `force_transition(..., allow_system=True)`, laut Docstring ein Notausgang, der von **jedem** Zustand in **jeden** führen kann und die konfigurierte Übergangsstruktur umgeht | `workflow/lifecycle_manager.py:439-478` |

**Antwort auf „schon abbildbar?":** **Teilweise.** Zustände, Verlauf, Konfiguration je Workspace, Sperre gegen gleichzeitiges Schreiben und Mandantentrennung sind als neuer Item-Typ ohne neue Technik nutzbar. **Nicht abbildbar ohne Erweiterung:** (a) die Kante als Gegenstand des Workflows (Befund 3), (b) systemgetriebene Übergänge als Teil der Definition statt als Notausgang (Befund 5 und 6).

**Entwurf (Vorschlag, nicht entschieden):**

1. **Neuer Workflow-Item-Typ** für die Verifikationskante (Arbeitsname `Verification`). Gegenstand ist der `verifies`-Link, `item_id` ist die Link-ID, Preset `verification_default`. Eintrag in `WORKFLOW_ITEM_TYPES`. Der Zustand liegt damit im `WorkflowItemState` der Kante und ersetzt die lose Spalte aus K1.a. Eine denormalisierte Spiegelspalte für schnelle Abfragen ist nach dem Muster `STATUS_MIRROR_ITEM_TYPES` möglich.
2. **Default-Zustände:** nicht ausgeführt, bestanden, fehlgeschlagen, blockiert, übersprungen. Je Workspace und Rigor-Tier konfigurierbar (K1.b).
3. **Ergebnisklasse je Zustand** (fest: offen, bestanden, negativ, unklar, übersprungen). Rollup, Befunde und Gates rechnen mit der Klasse. So bleiben sie unabhängig davon, wie ein Workspace seine Zustände nennt.
4. **Auslöser als Teil der Definition:** `trigger: manuell | system`. Ein Systemübergang darf nur vom Evaluator und nur entlang deklarierter Kanten laufen. Das ersetzt `force_transition` für diesen Zweck. Erweiterung von `TransitionDefinitionDTO` und der Definitionsspeicherung.
5. **Evaluator (die systemeigene Auswertung):** Dienst in Layer 2, ausgelöst bei Abschluss eines Testlaufs und bei `test.run_report_results`. Je betroffener Kante bestimmt er den Zielzustand aus dem neuesten Ergebnis (Zuordnung Lauf-Ergebnis → Zustand konfigurierbar, Default 1:1) und führt den deklarierten Systemübergang aus. Idempotent. Ein **Abgleich-Befehl** baut alle Zustände aus den Läufen neu auf (Heilung und Backfill, löst K1.a1).
6. **Manuelle Zustände nur, wo die Definition es erlaubt**, etwa für manuelle Verifikation (V3: Review, Inspektion mit Verifier und Evidenz). Standard: niemand setzt „bestanden" von Hand.
7. **Anzeige:** Zustand und Klasse an der Kante in Trace-Ansicht, VCRM und Coverage. Rollup am Requirement aus den Klassen (K1.c, K1.d).
8. **„Veraltet"** wird kein eigener Zustand, sondern eine Auswertung des Evaluators bei Inhaltsänderung (Hash-Wechsel, V4-S0). Welcher Zustand dann gilt, ist offen.
9. Werkzeuge: Evaluator und Anzeige erweitern bestehende Tools, Delta 0 beim Tool-Zähler.

**Offene Punkte dieses Ansatzes:**

| ID | Frage |
|---|---|
| Q-a | **Datenmenge:** je `verifies`-Kante ein Zustand plus Verlauf. Größenordnung am Bestand prüfen, Indizes und Aufbewahrung festlegen |
| Q-b | **Baseline:** Zustand der Kante miterfassen oder ausschließen (K1.a4) |
| Q-c | **Suspect:** ein Zustandswechsel darf weder `suspect` noch den Concurrency-Zähler des Links auslösen |
| Q-d | **Audit:** Verlauf der Engine reicht, oder zusätzlich Audit-Eintrag je Systemübergang |
| Q-e | **Backfill:** Startzustand der Bestandskanten aus dem jeweils letzten Ergebnis, Migration nach Roadmap-Regel |
| Q-f | **`validates`-Kanten** (TestCase → StakeholderNeed) gleich behandeln oder zunächst nur `verifies` |
| Q-g | **Löschen und Umhängen** einer Kante: Zustand und Verlauf mitführen oder verwerfen |
| Q-h | **Abwärtskompatibilität:** bestehende Workspaces ohne Definition erhalten den Default beim Provisionieren (wie bei anderen Typen) |

**Grober Aufwand (Schätzung, nicht Zusage):** Definitionserweiterung (`trigger`) ~4 Tasks, Item-Typ mit Provisionierung und Migration ~4, Evaluator mit Abgleich-Befehl ~5, Anzeige ~4. Zusammen ~17 Tasks, größter Block der Welle 1.

**Rahmen, der feststeht:** Der Trace bleibt wie er ist. `covered` ändert sich bis zur Entscheidung nicht. Nichts davon wird vor Abschluss von K1 gebaut. Die Vorschläge V1–V3 sind **Bausteine** von K1 und werden erst nach K1 geplant.

### V1 Ergebnisgetriebene Verifikation (F1, F2, F7) — Baustein von K1

**Problem.** Die Kernzahl „Abdeckung" ist ein Versprechen ohne Nachweis. Ein roter oder nie gelaufener Test zählt als abgedeckt. Das ist die **gewichtigste Lücke** im Vergleich und deckt sich mit der Bewertung vom 2026-08-08.

**Vorschlag (vorläufig, Form hängt von K1 ab).** Der Nachweis wird neben dem Trace sichtbar. Ob als zweite Kennzahl `verified`, als Zustand an der Kante oder am Requirement, entscheidet K1.a und K1.g. Bis dahin bleibt `covered` unverändert.
- Rollup je (Requirement, TestCase): neuester Lauf gewinnt (K1.e). Je Requirement nach dem VWZ-Vorbild strikt: ein `failed` ergibt `failed`, sonst `blocked`/`not_run` ergibt `inconclusive`, sonst nur `skipped` ergibt `skipped`, sonst `passed`. Mapping auf unsere Status und die Frage, ob `skipped` als Beweis zählt, sind K1.b und K1.c.
- Neue Auditor-Regeln: `VERIF-P8b missing-verdict` (freigegebenes Requirement mit Testlink, aber ohne Ergebnis) und `failing-verdict`. Draft, outdated und zurückgestellte Items werden übersprungen.
- Kennzahl `verified` in `traceability.coverage` und VCRM (neue Spalte).

**A (vorläufig, vorbehaltlich K1).** (1) Requirement mit Testlink und rotem neuestem Lauf erscheint in `verified` nicht und löst `failing-verdict` aus. (2) Ohne Lauf löst es `missing-verdict` aus. (3) `covered` ändert sich für keinen bestehenden Datensatz. (4) Zweiter, grüner Lauf hebt den Befund auf. (5) KI-erzeugte, ungeprüfte Tests zählen weiter nicht (Regel #424 bleibt).

**Aufwand** ~6 Tasks. **Abhängigkeit** keine. **Tools** Erweiterung bestehender Tools (Delta 0 laut Roadmap-Regel).

### V2 Standardformat-Import für Testergebnisse (F3)

**Problem.** CI muss ReqogniLooms interne UUIDs kennen, um Ergebnisse zu melden. VWZ liest CTRF ohne Integrationscode.

**Vorschlag.** Endpunkt und Tool-Erweiterung: CTRF-JSON einlesen, Ergebnisse über einen **stabilen, vom Nutzer vergebenen Schlüssel** (`uid`) an Testfälle binden, nicht über die UUID. Ergebnisse ohne Bindung werden als Finding `unbound-result` gemeldet, nicht verworfen. Optional JUnit-XML als zweiter Leser (E3).

**A.** (1) CTRF-Datei mit drei Fällen erzeugt einen Lauf mit drei Ergebnissen. (2) Unbekannte `uid` erzeugt `unbound-result`, der Rest wird trotzdem übernommen. (3) Zweimal derselbe Import ist idempotent. (4) Statusabbildung passed/failed/skipped/pending/other ist dokumentiert und getestet.

**Voraussetzung.** `TestCase.uid` muss je Workspace eindeutig sein. Das Konzept vom 2026-08-08 (§9.6) nennt: kein Constraint für `TestCase`/`ArchitectureElement`. **Vor Planung neu prüfen**, ggf. Datenbereinigung vor Migration.
**Aufwand** ~5 Tasks plus ggf. 1–2 für `uid`-Eindeutigkeit. **Abhängigkeit** V1 (Rollup nutzt die Ergebnisse).

### V3 Strukturierte manuelle Verifikation (F4)

**Problem.** Nicht alles wird getestet. Review, Inspektion, Analyse und Demonstration sind laut Verifikationsmethode gleichwertig, haben bei uns aber keinen strukturierten Nachweis.

**Vorschlag.** Ergebnis-Datensatz mit `outcome` (pass/fail/skipped/inconclusive), `verifier` (Benutzer), `evidence` (Text oder Link), `verified_at`. Fließt in denselben Rollup wie V1. Bindung über das bestehende Feld `verification_method`.

**A.** (1) Requirement mit `verification_method=Inspection` kann ohne TestCase `verified` werden, wenn ein Ergebnis `pass` mit Verifier und Evidenz vorliegt. (2) Ohne Evidenz wird das Ergebnis abgelehnt. (3) Ergebnis ist auditiert.
**Aufwand** ~4 Tasks. **Abhängigkeit** V1.

### V4 Inhaltsrevision, versionsgepinnte Links, `repin` (F5)

**Problem.** `suspect` ist ein Boolean, feuert bei jeder Speicherung und wird nie automatisch zurückgesetzt. Ein Link weiß nicht, gegen welchen Stand er geprüft wurde. `AuditableModel.version` ist nur ein Concurrency-Zähler, keine Inhaltsrevision (`models.py:305-322`).

**Einordnung gegen VWZ.** VWZs `version` ist ein **von Hand erhöhtes Integer-Attribut**. Vergisst der Autor den Bump, sieht weder der Pin-Check noch der Baseline-Diff (Attribute-only) die Änderung. Eine **automatische Inhaltsrevision** (S0) wäre VWZs Konzept also überlegen, nicht nur gleichwertig. Die Pin-Semantik selbst (outdated ERROR, predated immer ERROR und nie automatisch korrigiert, `repin` nur in `attr`-Blöcken mit Trockenlauf) ist übernehmenswert. **Ergebnis-Pins** (ein Testergebnis merkt sich den Stand des Requirements, gegen den es lief) sind die Grundlage für den Zustand „veraltet" aus K1.b.

**Vorschlag, in Stufen** (die Stufen sind einzeln auslieferbar):
- **S0 Inhaltsrevision:** Inhalts-Hash zuerst (billiger, reversibel). Ergebnis: „hat sich der Inhalt geändert?" ist exakt beantwortbar. Sofortnutzen: `suspect` feuert nur noch bei echter Inhaltsänderung.
- **S1 Pin:** Link trägt optional `target_revision`. Neue Links pinnen standardmäßig auf den aktuellen Stand.
- **S2 Veraltet-Befund und `repin`:** Auditor-Regel „Pin veraltet". Aktion `repin` mit **Trockenlauf als Standard**, idempotent, Pins über dem Upstream-Stand werden nur gemeldet, nicht verändert. Einzeln und gesammelt.
- **S3** `suspect` wird davon abgeleitet, nicht mehr gespeichert (nach Migrationsphase).

**A (S0).** Speichern ohne Inhaltsänderung setzt kein `suspect`. **A (S2).** `repin` ohne Bestätigung ändert nichts und liefert die Liste. Zweiter Lauf nach Bestätigung ist leer.

**Berührungspunkte.** Allokation-Release und Inhalt einfrieren (#1669/#1670, D10/D12) betreffen ebenfalls „Stand eines Elements". **Revisionsmodell mit diesen Entwürfen abstimmen, bevor S0 gebaut wird**, sonst entstehen zwei Versionsbegriffe.
**Aufwand** S0 ~4, S1 ~4, S2 ~6, S3 ~3 Tasks. Größte Einzelinvestition. **Abhängigkeit** E2.

### V5 Abdeckung als Vertrag (F6, F7)

**Problem.** Welche Ebene durch welche abgedeckt sein muss, steckt im Code der Regeln, nicht in Konfiguration.

**Vorschlag.** Pro Ebene oder Item-Typ konfigurierbar: „wird abgedeckt durch Typ/Ebene X". Als Parametrisierung der **bestehenden** Auditor-Regeln, nicht als zweites System. Nur freigegebene Anbieter zählen (Status je Rigor-Tier). Coverage-Berechnung nimmt optional einen Scope (siehe V7). Ausschalten je Ebene möglich (VWZ: leere Liste).

**A.** (1) Konfiguration „L1 wird durch L2 abgedeckt" erzeugt Befunde für L1 ohne L2-Anbieter. (2) Ein Anbieter im Zustand Entwurf zählt nicht. (3) Ohne Konfiguration verhält sich alles wie heute.
**Aufwand** ~6 Tasks, zusammen mit V6 ~10. **Abhängigkeit** V6 teilweise.

### V6 Schema je Ebene, Typ und Dokument (F8)

**Problem.** Attributdefinitionen gelten je Item-Typ und Rigor-Tier, nicht je Ebene oder Dokument. Es gibt kein „keine unbekannten Attribute" und keinen konfigurierbaren ID-Präfix je Ebene (nur `UidSequence`, Agent: `models.py:4305`).

**Vorschlag.** Konfigurationsschlüssel um **Ebene** und **Typ** erweitern (Adapt, kein JSON-Schema-Import). Stufenweise Pflicht gibt es schon (Freigabe, Baseline). Neu: Strict-Modus „unbekannte Attribute verboten" und ID-Präfix je Ebene.
**A.** Zwei Ebenen mit unterschiedlichen Pflichtfeldern validieren getrennt. **Aufwand** ~6 Tasks. **Hinweis** reines JSON-Schema (2020-12) als Austauschformat ist optional (E5), nicht Ziel.

### V7 Sichten als Scope (F11, F12)

**Problem.** Sichten gibt es für Tabellen. Coverage, Export und Baseline-Vergleich kennen sie nicht. VWZ bildet damit **Varianten** ohne eigenes Feature ab.

**Vorschlag.** Eine gespeicherte Sicht (`SavedView`) ist ein Scope für Coverage, Export und `baseline.compare`. **Kein neuer Ausdruckskern:** das Filter-DSL aus dem Tabellenansicht-Plan (`2026-11-04-tabellenansicht-neu.md`, Slice 1) wird wiederverwendet. Eine freie Ausdruckssprache ist nur zu bauen, wenn das DSL nicht reicht (E6).
**A.** Coverage mit Sicht „variant enthält X" zählt nur Items der Sicht. **Aufwand** ~5 Tasks. **Abhängigkeit** Tabellenansicht Slice 1 und 3.

### V8 Disposition (F9)

**Problem.** „Wird nicht umgesetzt" und „später" sind nicht von „offen" zu unterscheiden. Offene Items verfälschen Coverage-Berichte.

**Vorschlag.** Optionales Attribut `disposition` (implemented | deferred | rejected) mit Pflicht-Begründung bei deferred/rejected. Pflicht der Disposition je Rigor-Tier konfigurierbar (Standard: nur Extended). Zurückgestellte und abgelehnte Items entfallen aus Coverage-Befunden. Nutzt bestehende Attributdefinitionen.
**A.** Deferred ohne Begründung wird abgelehnt. Deferred-Requirement erzeugt kein `missing-verdict`. **Aufwand** ~3 Tasks. **Abhängigkeit** V1 (Berührung), V6.

### V9 Disjunktheits-Check über Trace-Kanten (F10)

**Vorschlag.** Auditor-Regel: für konfigurierbare Mengen-Attribute (z. B. `variant`, Sicherheitsstufe) müssen die Werte über jede Trace-Kante eine **nicht-leere Schnittmenge** haben. Erwartet ein Mengen-Attribut (Multi-Enum) und V7 als Scope.
**A.** Kind mit Variante {B}, Eltern mit {A} erzeugt Befund. **Aufwand** ~3 Tasks. **Priorität niedrig** (nur wenn Varianten ein echtes Thema sind, E7).

### V10 Ein Prüflauf mit CI-Exit-Code (F13, F15)

**Problem.** Der SE-Auditor kann alles, ist aber per REST/MCP schwer in eine Pipeline zu hängen.

**Vorschlag.** Dünne Hülle über dem bestehenden Auditor-Endpunkt: ein Aufruf liefert Findings als JSON und einen Exit-Code (0 gültig, 1 Befunde ab Schwelle, 2 Aufruf-/Zugriffsfehler). Schwelle und Scope (Baseline, Sicht) wählbar. **Kein neues MCP-Tool** (Delta 0), Ablage in `dist/` neben den vorhandenen Clients. Zyklen werden als Befund im selben Lauf gemeldet (heute nur beim Schreiben).
**A.** Pipeline-Schritt scheitert bei Befund ab Schwelle, Waiver werden berücksichtigt. **Aufwand** ~4 Tasks. **Abhängigkeit** keine, nutzt V1 sobald vorhanden.

### V11 Baseline-Diff ergänzen (F12)

**Vorschlag.** (a) Schema-/Attributdefinitions-Änderungen im Diff ausweisen. (b) Vergleich zweier Sichten im selben Stand (V7). (c) Diff als Datei exportierbar. Der Inhalts-Diff selbst ist fertig und bleibt.
**Aufwand** ~4 Tasks. **Priorität niedrig bis mittel.**

### V12 Exporte (F16, F17)

**Vorschlag.** (a) **Standalone-HTML-Report** ohne externe Skripte: Dokument-, Tabellen-, Trace- und Coverage-Ansicht, geeignet für Auditoren ohne Zugang. (b) **NDJSON-Export** (Requirements, Links, Ergebnisse, Findings), deterministisch sortiert. Graph-DB-Export wird nicht übernommen (cgo-Abhängigkeit, kein Bedarf belegt).
**A.** HTML-Datei öffnet offline, enthält keine externen Ressourcen. NDJSON zweimal erzeugt ist byte-gleich. **Aufwand** HTML ~6, NDJSON ~3 Tasks.

### V13 Prozessvorlage (F19)

**Einordnung.** VWZs `aspice`-Preset ist **dünn**: ein Schema mit `asil`-Pflicht, `safety-goal`, `owner` und `additionalProperties: false`, ohne Ebenen und ohne Coverage-Regeln. Es gibt dort **kein** ASPICE-Prozessmodell, das wir nachbauen könnten. Der echte V-Modell-Aufbau liegt nur im Beispielprojekt `spec/`.

**Vorschlag.** Eigene Workspace-Vorlage (Ebenen L0–L3, Link-Typen, Pflichtattribute, Rigor-Preset) in einem Schritt anlegen. Nutzt den vorhandenen Bootstrap. Inhalt der Vorlage ist **unsere** Fachentscheidung, nicht von VWZ abgeleitet. **Aufwand** ~4 Tasks. **Wert** Onboarding, geringes Risiko.

### V14 Agenten-Zugang (F20)

**Vorschlag.** `llms.txt` für die Doku-Seite, `AGENTS.md`-Vorlage für Anwender-Repos (verweist auf MCP und Skills). Das CLI aus V10 deckt `--json` ab. **Aufwand** ~2 Tasks. Kleiner Gewinn, sehr günstig.

## 5. Nicht übernommen

| VWZ-Merkmal | Grund |
|---|---|
| Git als Wahrheitsquelle, kein Server | Gegenteil unseres Modells: Mehrmandanten, Workflow, Audit |
| Freigabe nur per PR-Review | wir haben CCB und Workflow |
| Graph-DB-Export (LadybugDB) | nur mit cgo-Build-Tag, kein Bedarf belegt |
| `vwz-code` (Symbole als Requirements) | Requirements entstehen aus Bedürfnissen, nicht aus Code. Zurückgestellt (E9) |
| Rein lesende Weboberfläche | wir haben Bearbeitung. Der HTML-Report (V12) deckt den Lesefall ab |
| Dokumentformat Markdown + `attr`-Block | Round-Trip-Fragen und Free-Text-Guard (`<…>`) sprechen dagegen. Nur relevant für die vertagte Brücke |

## 6. Unsere Vorteile (zur Einordnung, nicht zur Änderung)

1. Mehrmandanten mit Postgres-RLS (`persistence/migrations/0003_rls_policies.py`).
2. Freigabe-Workflow, CCB, Baseline-Gate mit Waivern (`workflow/`, `baseline/waivers.py`).
3. Audit-Trail (`audit/`).
4. MCP-Server mit API-Key-Policy (301 Tools laut `CLAUDE.md` auf `origin/main`. Die Roadmap nennt 290, der Zähler ist key-abhängig, vor jeder Zähler-Aussage `tool-manifest.json` prüfen).
5. KI-Ableitung und Link-Vorschläge (`ai_derivation.*`, `traceability.suggest_links`).
6. Interviews (`interview.*`).
7. Risiken, ADRs, Diagramme, ICD als eigene Artefakttypen.
8. SE-Auditor mit Rigor-Tiers, Remediation-Vorschlägen und KI-Review.

9. **Baseline-Diff nach Inhalt:** VWZ vergleicht nur Attribute, Text- und Titeländerungen bleiben ohne manuellen `version`-Bump unsichtbar. Unser Diff nutzt erfasste Feldwerte.
10. **Waiver mit Ablauf und Auditspur** statt einer Liste von Unterdrückungsnamen im `attr`-Block ohne Begründung und ohne Prüfung von Tippfehlern.
11. **Testgestützte Qualität:** VWZ hat keine CI-Tests (Abschnitt 2b). Das ist unser Vorsprung, solange wir ihn halten.

VWZ räumt die Prozess-Lücken in „What VWZ is not" selbst ein. Eine „Gleichziehen"-Strategie ist deshalb **nicht** das Ziel.

## 7. Priorisierung und Einordnung in die Roadmap

Ziel der Reihenfolge: erst die Zahl absichern, der man vertraut, dann Verträge, dann die großen Umbauten.

| Welle | Inhalt | Begründung |
|---|---|---|
| 0 | **K1 Konzept Ausführungsstatus** (Entwurfsrunde, kein Code) | Daniel hat E1 zurückgestellt. V1–V3 und V8 hängen davon ab. Ergebnis ist ein eigenes Konzeptdokument und danach ein Freigabe-Gate |
| 1 | V1, V2, V3, V8 (nach K1) | Nachweis statt Versprechen. Größter fachlicher Hebel, baut auf vorhandenem `TestRun` auf. V8 ist klein und entlastet V1 |
| 2 | V5, V6, V7, V10 | Abdeckungsvertrag, Schema je Ebene, Sicht als Scope, CI-Lauf |
| 3 | V4 (S0 sofort, S1–S3 nach Abstimmung mit #1669/#1670) | größte Investition. S0 ist billig und bringt den Sofortnutzen |
| 4 | V9, V11, V12, V13, V14 | Ergänzungen mit geringem Risiko |
| zurück | Brücke, `vwz-code` | bewusst vertagt |

**Verhältnis zu `backlog-roadmap.md`.** Die Roadmap kennt diese Themen nicht. Berührungen: Phase F (Testqualität, #587) wegen V1/V2, Phase E (Allokation/Release, #1669/#1670) wegen V4, Tabellenansicht-Plan wegen V7. Vorschlag: **neue Phase I „Verifikation und Abdeckungsverträge"** mit Welle 1 und 2, Absprache mit F nötig, damit Test-Ergebnismodell nicht doppelt angefasst wird.
**Querschnittsregeln der Roadmap gelten:** Migrationen nacheinander mergen und renummerieren, Tool-Zähler (290) nur durch Phase G ändern, Frische-Check vor Ausführung.

## 8. Offene Entscheidungen (einzeln zu klären, vor Planung)

| ID | Frage | Empfehlung |
|---|---|---|
| E1 | Darf sich die Definition von „Abdeckung" ändern? | **Zurückgestellt (Daniel, 2026-11-16).** Der Trace bleibt, der Ausführungsstatus muss sinnvoll dazu. Das Konzept K1 fehlt und wird zuerst geklärt (Fragen K1.a–K1.h). `covered` bleibt bis dahin unverändert |
| E2 | Inhaltsrevision: Hash oder eigene Versionstabelle? | **Hash zuerst.** Billiger, reversibel. Vorher mit #1669/#1670 abstimmen |
| E3 | Testergebnis-Import: nur CTRF oder auch JUnit-XML? | CTRF zuerst, JUnit als zweiter Leser, wenn Bedarf belegt |
| E4 | Schwere von kaputten Referenzen und Zyklen im Prüflauf? | je Rigor-Tier konfigurierbar. VWZ (Code): kaputte Referenz WARNING, Mehrdeutigkeit, Duplikat und Zyklus ERROR. Als Ausgangswert brauchbar |
| E5 | Schema-Austauschformat JSON-Schema 2020-12? | **Nein**, eigene Konfiguration erweitern |
| E6 | Freie Ausdruckssprache für Sichten? | **Nein** vorerst, Filter-DSL wiederverwenden |
| E7 | Sind Varianten ein echtes Thema? | offen. Davon hängt V9 ab |
| E8 | Brücke ReqogniLoom ⇄ VWZ gewollt? Gibt es ein konkretes Projekt? | offen, vertagt. Aus Konzept 2026-08 §9.1 |
| E9 | Code-Symbole importieren? | **Nein**, zurückgestellt |
| E10 | Neue Phase I in die Roadmap oder getrennt führen? | Phase I, Absprache mit F |
| E11 | VWZ ist GPL-3.0. Nur Konzepte übernehmen, keinen Code? | **Ja.** Keine Kopie, keine Einbettung, kein Linking. Eigene Umsetzung nach eigener Spec. Keine Rechtsberatung, bei Zweifel klären lassen |

## 9. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| V1 ändert wahrgenommene Zahlen | `covered` unverändert, `verified` additiv (E1), Ankündigung im Changelog |
| V4 erzeugt zweiten Versionsbegriff neben Release/Freeze | Abstimmung mit #1669/#1670 vor S0 |
| `uid`-Duplikate blockieren V2 | Datenbereinigung vor Constraint, Migrationsreihenfolge beachten |
| Befund-Flut nach V1/V5 (`missing-verdict` auf Altbestand) | Standard `warning` je Tier, Waiver nutzbar, Rollout je Rigor-Tier |
| PARTIAL-Urteile beruhen teils auf Docstrings, nicht Laufzeittests | Frische-Check und Beleg je Task, siehe Abschnitt 2 |
| VWZ-Aussagen unvollständig belegt | Lücken in Abschnitt 2 benannt, GitHub-Repo bei Bedarf nachlesen |

## 10. Quellen

- VWZ Webseite: `<Webseite>/`, `/cheat-sheet/`, `/faq/`, Compare, About, `/ai/` (mit den drei Skills), Import, Benchmarks, Use-Cases, Quickstart 0–15, `llms.txt`, `llms-full.txt` (teilweise). Abruf 2026-11-16.
- VWZ Quellcode: `<Quellrepo>`, HEAD `ebade4760f10064aa58b4fb807024a2e0e872bfd`, lokale Kopie `.tmp/vwz-src` (flach, nicht Teil des Repos). Das README dieses Repos verweist auf `<Webseite>`, das Feld `homepageUrl` ist leer, die Zuordnung beruht daher auf dem README. Drei weitere Repos mit ähnlichem Namen (`<Fremdrepo>`, drei Stück) verweisen nicht auf `<Webseite>`.
- Intern: `docs/superpowers/plans/2026-08-08-vwz-interop-and-inspiration-concept.md`, `docs/superpowers/plans/index.md`, `docs/superpowers/plans/2026-11-10-backlog-roadmap.md`, `docs/superpowers/plans/2026-11-04-tabellenansicht-neu.md`, `docs/superpowers/specs/2026-11-10-allokation-objekt-release-design.md`.
- Code-Belege siehe Abschnitt 3.
