# Phase B2 — Inspector-Neukonzept Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein reviewtes Konzept (Spec) für einen deutlich besseren Artefakt-Inspector, getragen von Ist-Analyse, Best-Practice-Recherche und Usability-Prüfung. Am Ende dieses Plans steht eine Spec und ein Freigabe-Gate, noch kein Produktivcode.

**Architecture:** Der Inspector existiert bereits: `shared/ArtifactInspector/RightSidebar.tsx` (Version, Diff, Trace, Kommentare; einklappbar, 280–520 px skalierbar, `aside role="complementary"`) ist in 10 Artefakttypen eingebunden (REQ-L1-095). Die `TraceSpine` (`shared/TraceSpine/`) ist in 7 Routen im Einsatz. #801 ("nur Requirements haben einen Inspector") ist damit überholt. Das Vorhaben ist nun Neukonzeption der bestehenden Lösung: erst messen und recherchieren, dann entwerfen, dann Daniel reviewt, erst danach Umsetzungsplan.

**Tech Stack:** React 19, TypeScript, CSS Custom Properties (`styles/tokens.css`), Playwright (nur über den `e2e-tester`-Agenten mit erlaubten Tools), Agenten `ui-ux-designer`, `design-system-architect`, `accessibility-specialist`.

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` Phase B, Entscheidung 4 (bestätigt am 2026-11-10: "bestehenden Inspector tiefgehend analysieren und neu konzipieren"), `docs/UI_KONZEPT.md` §3.4, §5, §6.

## Befund (origin/main 4f8aa29f, beta.29)

- `RightSidebar.tsx` (466 Zeilen) und vier Panels: `VersionPanel` (410), `DiffPanel`, `TracePanel` (465), `CommentPanel`. Insgesamt 2919 Zeilen mit Tests.
- Eingebunden in Needs, Risk, ADR, TestCase, Issue, Architecture, Requirements (SplitView), Glossary, ICD, Diagram, Goals.
- `hideTraceLinks` blendet das TracePanel aus, wo eine `TraceSpine` die Links schon zeigt. Glossary und ICD haben noch keine Spine und behalten das TracePanel. Die Aufteilung "Spine am Rand, Panel rechts" ist selbst ein Konzeptpunkt.
- `DIFF_SUPPORTED_KINDS` (`types.ts:128`): nicht jeder Typ hat Diff.
- Offene Messwerte aus dem Audit vom 2026-10-13: 19 Button-Höhen, 7 Radien (im Inspector zu prüfen).

## Global Constraints

- Keine Zeile Produktivcode in diesem Plan. Ergebnisse sind Analysen, eine Spec, Mockups.
- Dokumente unter `docs/analysis/` und `docs/superpowers/specs/`. Interne Doku auf Deutsch, Quellen mit URL und Abrufdatum.
- Recherche nur aus belegbaren Quellen. Kein Fakt aus dem Gedächtnis ohne Quelle in die Spec.
- Barrierefreiheit: WCAG 2.2 AA als Untergrenze (ARIA `complementary`, Fokusreihenfolge, Tastaturbedienung, Kontrast per Token).
- Alle Texte i18n DE/EN, keine hartcodierten Farben/Größen (`styles/tokens.css`).
- Playwright nur mit den erlaubten MCP-Tools (`browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_click`, …). Verboten: `browser_evaluate`, `browser_run_code_unsafe`, `browser_file_upload`, `browser_handle_dialog`.
- Git-Mutationen nur über den `git`-Agenten. Volle Testläufe sequentiell.

## Review Focus

- Konzept löst ein Scheinproblem: Der Neuentwurf verbessert, was Nutzer nie stört. Test: Task 3 formuliert fünf konkrete Nutzeraufgaben und misst den Ist-Aufwand. Ein Entwurf wird nur akzeptiert, wenn er mindestens eine messbar verbessert.
- Typ-Unterschiede gehen verloren: Ein einheitlicher Entwurf bricht Typen ohne Diff oder ohne Spine (Glossary, ICD). Test: Task 5 enthält eine Typ-Matrix mit Verhalten je Typ.
- Schmale Fenster: Inspector verdrängt den Inhalt. Test: Task 5 beschreibt das Verhalten bei 768 und 1024 px Breite, Task 2 liefert Screenshots als Ist-Beleg.
- Tastatur und Screenreader: neuer Aufbau ohne definierte Fokusreihenfolge. Test: Task 5 legt Tabreihenfolge und Live-Region-Texte fest, Task 6 lässt `accessibility-specialist` prüfen.
- Doppelte Darstellung: Trace-Links erscheinen in Spine und Panel. Test: Task 5 legt je Information genau einen Ort fest.

---

### Task 1: Tracking-Issue anlegen, #801 schließen

**Files:** keine.

**Interfaces:** Produces: neues Issue "Inspector neu konzipieren" (Nummer N), #801 geschlossen. Zähler: −1 (#801) +1 (N).

- [ ] **Step 1: Freigabe von Daniel einholen, dann Issue anlegen**

```bash
gh issue create --title "[DESIGN][frontend] Artefakt-Inspector neu konzipieren: Analyse, Best Practice, Spec (inkl. Trace-Spine)" --label enhancement --label ui/ux --label frontend --label design --body "Nachfolger von #801. Der Inspector (shared/ArtifactInspector, RightSidebar) ist inzwischen in 10 Artefakttypen eingebunden, die Trace-Spine in 7 Routen. Ziel ist eine tiefgehende Neukonzeption für deutlich bessere Usability und Design. Vorgehen: Ist-Analyse, Best-Practice-Recherche, Usability-Prüfung, Spec, Review durch Daniel, dann Umsetzungsplan. Plan: docs/superpowers/plans/2026-11-10-phase-b2-inspector-concept.md. Bezug: docs/UI_KONZEPT.md §3.4, §5, §6; Audit-Restwerte aus #186 (19 Button-Höhen, 7 Radien)."
```

- [ ] **Step 2: #801 schließen**

```bash
gh issue close 801 --reason completed --comment "Die Anbindung ist erledigt: RightSidebar (Version, Diff, Trace, Kommentare) ist in 10 Artefakttypen eingebunden (REQ-L1-095). Das Neukonzept läuft in #<N>."
```

- [ ] **Step 3: Verifizieren**

Run: `gh issue view 801 --json state --jq .state`
Expected: `CLOSED`.

---

### Task 2: Ist-Analyse (Inventar)

**Files:**
- Read: `frontend/src/components/shared/ArtifactInspector/*.tsx`, `frontend/src/components/shared/TraceSpine/*.tsx`, die 11 Konsumenten (Liste im Befund)
- Create: `docs/analysis/2026-11-inspector-ist.md`
- Create: `docs/analysis/2026-11-inspector-screenshots/` (Screenshots, nur wenn ein Stack läuft)

**Interfaces:** Produces: Matrix Typ × Merkmal, Screenshot-Satz, Liste von Inkonsistenzen mit Datei:Zeile. Task 3 und 5 lesen sie.

- [ ] **Step 1: Inventar-Matrix aus dem Code**

Je Konsument (Requirements/SplitView, Needs, Risk, ADR, TestCase, Issue, Architecture, Glossary, ICD, Diagram, Goals): eingebundene Panels, `hideTraceLinks`, `DIFF_SUPPORTED_KINDS`, Standard-Breite, Zustand einklappen/anheften (`localStorage`-Schlüssel je `kind`), Spine vorhanden, Leerzustand, `data-testid`. Als Tabelle in `docs/analysis/2026-11-inspector-ist.md`.
Run (Hilfe): `cd frontend/src && grep -rn "<RightSidebar" components --include=*.tsx | grep -v test`
Expected: je Konsument eine Fundstelle mit den Props.

- [ ] **Step 2: Inkonsistenzen markieren**

Alles, was je Typ abweicht und keine fachliche Ursache hat (Reihenfolge der Panels, Standardzustand, Leerzustandstext, Breite). Je Fund Datei:Zeile.

- [ ] **Step 3: Screenshots (optional, wenn ein Stack erreichbar ist)**

Der `e2e-tester`-Agent erzeugt je Typ zwei Screenshots (1440 und 768 px Breite, Inspector offen und eingeklappt) mit `browser_navigate`, `browser_resize`, `browser_take_screenshot`. Ohne laufenden Stack entfällt der Schritt und das steht im Dokument.

- [ ] **Step 4: Commit** (über `git`-Agent): `docs(frontend): add inspector as-is analysis`

---

### Task 3: Usability-Prüfung an fünf Aufgaben

**Files:**
- Create: `docs/analysis/2026-11-inspector-usability.md`

**Interfaces:** Consumes: Inventar aus Task 2. Produces: Aufwandsmessung (Klicks, Wechsel, Wartezeit) je Aufgabe, Probleme nach Schwere (Nielsen-Skala 0–4).

- [ ] **Step 1: Fünf Aufgaben festlegen**

1. "Was realisiert oder testet diese Anforderung?" (Trace-Sicht)
2. "Was hat sich seit Baseline X an diesem Artefakt geändert?" (Version/Diff)
3. "Wer hat wann was kommentiert, und was ist offen?" (Kommentare)
4. "Wo sitzt dieses Artefakt in der Ableitungskette?" (Spine)
5. "Springe zum verknüpften Artefakt und zurück." (Navigation)

- [ ] **Step 2: Heuristische Evaluation**

Je Aufgabe und Typ den Pfad durchgehen, Klickzahl und Kontextverlust notieren, Verstöße gegen die zehn Heuristiken von Nielsen benennen, Schwere vergeben. Ergebnis als Tabelle.

- [ ] **Step 3: Ranking**

Die drei schwersten Probleme mit Beleg (Datei:Zeile oder Screenshot). Sie sind die Messlatte, an der der Entwurf in Task 5 gemessen wird.

- [ ] **Step 4: Commit** (über `git`-Agent): `docs(frontend): add inspector usability evaluation`

---

### Task 4: Best-Practice-Recherche

**Files:**
- Create: `docs/analysis/2026-11-inspector-best-practice.md`

**Interfaces:** Produces: Quellenliste mit URL und Abrufdatum, je Quelle Kernaussage und Übertragbarkeit, Muster-Katalog. Task 5 verweist per Quellennummer.

- [ ] **Step 1: Quellen sammeln (Agent mit WebSearch/WebFetch)**

Themen und mindestens je zwei belegte Quellen: (a) Detail- und Seitenpanel-Muster und Progressive Disclosure (Design-Systeme wie Material, Carbon, Atlassian; Nielsen Norman Group), (b) Nachverfolgbarkeits- und Verlaufsdarstellung in Requirements-Werkzeugen (öffentliche Doku von z. B. Jama, Polarion, DOORS Next, Jira), (c) Diff-Darstellung und Versionshistorie (z. B. GitHub, Confluence), (d) barrierefreie Seitenpanels und Splitter (WAI-ARIA Authoring Practices: complementary landmark, window splitter, disclosure), (e) responsive Verhalten von Seitenpanels.
Jede Quelle: Titel, URL, Abrufdatum, Kernaussage in zwei Sätzen, Übertragbarkeit auf ReqogniLoom (ja/teilweise/nein, mit Grund).

- [ ] **Step 2: Muster-Katalog**

Aus den Quellen drei bis sechs Muster mit Name, Problem, Lösung und Quelle. Nur Muster aus belegten Quellen.

- [ ] **Step 3: Commit** (über `git`-Agent): `docs(frontend): add inspector best-practice research`

---

### Task 5: Konzept und Design (Spec)

**Files:**
- Create: `docs/superpowers/specs/2026-11-10-inspector-redesign-design.md`
- Create: `docs/superpowers/specs/inspector-redesign-mockups/` (Mockups, vom `ui-ux-designer`)

**Interfaces:**
- Consumes: Tasks 2, 3, 4; `docs/UI_KONZEPT.md` §3.4 ("Eine Fläche, eine Aufgabe"), §5 (Trace-Spine), §6 (Layout).
- Produces: Spec mit den Abschnitten unten. Sie ist Eingabe für den Umsetzungsplan.

- [ ] **Step 1: Skill brainstorming für den Entwurf**

Einstieg mit `superpowers:brainstorming`. Offene Gestaltungsfragen werden Daniel einzeln gestellt (AskUserQuestion, je Frage ein Aufruf), nicht gesammelt.

- [ ] **Step 2: Spec schreiben**

Pflichtabschnitte:
1. Ziel und Messlatte (die drei schwersten Probleme aus Task 3, jeweils mit Zielwert).
2. Informationsarchitektur: genau ein Ort je Information (Version, Diff, Trace-Links, Kommentare, Status, IDs). Verhältnis Spine ↔ Panel, damit nichts doppelt erscheint.
3. Typ-Matrix: Verhalten je Artefakttyp (Diff ja/nein, Spine ja/nein, Standardtab).
4. Layout und Responsives Verhalten bei ≥1440, 1024 und 768 px.
5. Interaktion und Tastatur: Fokusreihenfolge, Kürzel, Live-Region-Texte.
6. Token-/Varianten-Vertrag (vom `design-system-architect`): Höhen, Radien, Abstände, Zustände. Adressiert die 19 Button-Höhen und 7 Radien.
7. Barrierefreiheit gegen WCAG 2.2 AA.
8. Migration: Reihenfolge der Typen, Rückfallpfad, Ratchet-Auswirkung (`ui-ratchet.test.ts`).
9. Nicht-Ziele.
10. Quellenverweise auf Task 4.

- [ ] **Step 3: Mockups**

Der `ui-ux-designer` liefert Mockups für Requirement (voller Funktionsumfang), Glossary (ohne Spine) und eine Schmalansicht.

- [ ] **Step 4: Commit** (über `git`-Agent): `docs(frontend): add inspector redesign spec`

---

### Task 6: Prüfung und Freigabe-Gate

**Files:** keine neuen.

**Interfaces:** Produces: Freigabe oder Änderungsliste. Ohne Freigabe entsteht kein Umsetzungsplan.

- [ ] **Step 1: Fachliche Prüfung**

`accessibility-specialist` prüft die Spec (Fokus, Landmarks, Live-Regionen, Kontrast), `ui-reviewer` prüft Token-Konformität und Zustände. Befunde werden in die Spec eingearbeitet.

- [ ] **Step 2: Daniel reviewt die Spec**

Zusammenfassung in fünf Zeilen plus Link auf die Spec. Warten auf Freigabe oder Änderungen.

- [ ] **Step 3: Nach Freigabe: Umsetzungsplan**

`superpowers:writing-plans` auf Basis der freigegebenen Spec, neues Dokument `docs/superpowers/plans/<datum>-inspector-redesign-implementation.md`. Es enthält Code-Tasks mit Tests, aufgeteilt nach der Migrationsreihenfolge aus Spec Abschnitt 8.

- [ ] **Step 4: Issue #N aktualisieren**

Kommentar mit Spec-Link und Ergebnis der Prüfung. Das Issue bleibt offen, bis die Umsetzung gemergt ist.

---

## Self-Review

- **Abdeckung:** Daniels Vorgabe "tiefgehende Analyse, Best Practice, besseres Konzept, Usability und Design" ist durch Tasks 2 bis 5 gedeckt. Trace-Spine-Integration (Entscheidung zu #186) steckt in Task 5, Abschnitt 2.
- **Bewusste Lücke:** Dieser Plan endet an einem Freigabe-Gate. Code-Tasks entstehen erst aus der freigegebenen Spec. Das ist gewollt, weil die Lösung davon abhängt.
- **Abhängigkeit zu B1:** `audit-dashboard.tsx` und der Inspector berühren sich nicht. B1 und B2 sind parallel lauffähig.
- **Offen:** Ob ein laufender Stack für Screenshots (Task 2 Step 3) erreichbar ist, wurde nicht geprüft.
