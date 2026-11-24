---
type: PLAN
title: "Masterplan: Exhaustives UI-E2E-Testing"
status: proposed
date: 2026-11-24
author_agent: main_chat
language: de
branch_basis: "origin/main 5659c1ad (v1.9.0-beta.5)"
---

# Masterplan: Exhaustives UI-E2E-Testing (ReqogniLoom)

Stand: 2026-11-24 · Autor: main_chat · Status: Entwurf zur Freigabe

## 1. Ziel und Realitätscheck

Ziel: **jeden Dialog, jeden Button, jede Einstellung, jeden Klick, jede visuelle Anordnung, jedes Preset, jedes Artefakt und jede Statuskombination im Browser testen.**

Realitätscheck: Das ist ein kombinatorischer Raum, kein Testfall:

| Dimension | Groessenordnung |
|---|---|
| TSX-Komponenten | 518 |
| Dialog-Komponenten | 31 |
| Artefakt-Typen | ~18 (Requirement, Need, ArchitectureElement, TestCase, ADR, Risk, Issue, Goal, Document, GlossaryTerm, Milestone, Baseline, ICD, Diagram, WorkItem, ChangeRequest …) |
| Rigor-Presets | 3 (minimal / standard / extended) |
| Workflow-States | ~9 (draft, proposed, review, approved, released, outdated, Entwurf, Freigegeben, Archiviert …) |
| Rollen / Key-Tiers | viewer, editor, approver, admin × bearer / reqlo_-Key (reader/author/admin) |
| Link-Typen | 20 built-in + tenant-extensibel |
| Bestehende E2E-Specs | 75, 4 CI-Shards + Mobile |

Eine vollständige kartesische Abdeckung wäre praktisch unendlich. Der Plan nutzt deshalb **Model-Based Testing + Combinatorial Testing + Risikogewichtung**, sodass jede *relevante* Interaktion und jede *kritische* Kombination nachweislich abgedeckt ist — mit dokumentierter, messbarer Abdeckung statt dem Versuch, alle Tuple zu fahren.

## 2. Grundsatz: „Alles getriggert im Browser"

- **Interaktion und Assertion:** ausschliesslich über Browser-Aktionen (Klick, Tastatur, Formular, Scroll, Fokus, Dialog, Navigation). Kein direkten State-Injektion, kein `page.evaluate`, kein API-Call als Ersatz für einen UI-Klick.
- **Setup (erlaubt, klar getrennt):** Seed/Fixtures per `manage.py seed_demo`, `seed_toothbrush`, `bootstrap_attribute_definitions` und selektiv REST-Seed fuer Daten, die die UI nicht erzeugen kann. Alles, was die UI selbst erzeugen kann, wird von der UI erzeugt.
- **Harte Tool-Grenzen:** `browser_run_code_unsafe`, `browser_evaluate`, `browser_file_upload`, `browser_handle_dialog` sind gesperrt. Datei-Upload wird ueber den nativen Input (`setInputFiles` in einer Playwright-Spec) oder manuell geloest, nicht ueber `browser_file_upload`.
- **Test-Beweis:** jeder Testfall hinterlaesst ein Artefakt (Screenshot, Trace, Accessibility-Snapshot, Netzwerk-Log), das die Browser-Aktion belegt.

## 3. Schichtenmodell

| Schicht | Zweck | Technik | Umfang |
|---|---|---|---|
| L0 | Reine Logik/Validierung | Vitest | alle Validator/Formatter/State-Mapper |
| L1 | Komponenten-Interaktion | Vitest + React Testing Library | alle 31 Dialoge, Buttons, Formulare, Tastatur, Error-States |
| L2 | Model-Based E2E | Playwright, Browser-Aktionen | Zustandsautomaten je Artefakt, ueber 12 Kernrouten |
| L3 | Visuelle Regression | Playwright Screenshot + Diff | jede Seite × State × Preset × Theme × Breakpoint |
| L4 | Barrierefreiheit | axe-core + Keyboard-Walk | jeder State, WCAG A/AA |
| L5 | Exploratorischer Random-Walk | Playwright, deterministischer Seed | unerwartete Klickpfade, 5–10 Min pro Lauf |

## 4. Der zentrale State-Space (Source of Truth)

Ein maschinenlesbarer Katalog (`e2e/models/ui-state-catalog.ts`) wird aus **Code** generiert, nicht von Hand gepflegt:

- **Routes:** aus `SidebarNavigation.tsx` (_scope_ aller NAV-Einträge).
- **Artefakt-Typen:** aus `frontend/src/types` + Backend-Modellen.
- **Workflow-States:** aus den Preset-Workflows (`backend/presets`, `workflow`); Transitionen als Graph.
- **Rollen/Key-Tiers:** aus RBAC-Matrix + API-Key-Scopes.
- **Presets:** minimal / standard / extended.
- **Dialoge/Buttons:** aus `data-testid`-Attributen (Repo-Pflicht fuer interaktive Elemente) + Komponenten-Scan.

Jeder Testfall wird als Tupel `(route, artifact, state, preset, role, keyTier, viewport, theme, language, dialog?, action)` registriert. Daraus entsteht eine **Abdeckungsmatrix**, dieCU in CI als Gate ausgewertet wird.

## 5. Kombinatorische Reduktion (statt kartesischem Produkt)

- **Pairwise / All-Pairs** fuer unkritische Dimensionen (Theme × Sprache × Viewport × Preset): 6–12 Kombinationen decken alle Paare ab.
- **Vollfaktor** nur fuer kritische Triple: `(Artefakt × Workflow-State × Rolle)` und `(Dialog × Aktion × Fehlerfall)`.
- **AEP-Test** (All-Element-Pairwise) fuer Buttons/Dialoge: jeder Button mindestens einmal in jedem relevanten State.
- **Risikogewichtung:**admin + extended + released + destruktive Aktion (delete/outdate/transition) immer voll; viewer + minimal + readonly pairwise.
- **Äquivalenzklassen:** gleiche Dialog-Komponente mit anderer Entität wird nur einmal voll getestet, danach Paritätstest (Test bestätigt identische Render-Struktur).

Dashboard der Matrix: `e2e/reports/coverage-matrix.html`, mit Ampel fuer jede Zelle und Link zum Beweis-Artefakt.

## 6. Test-Inhalte pro Ebene

### 6.1 Jeder Dialog (31)
Interaktionsvertrag, der fuer jeden Dialog getestet wird:
1. Oeffnen (Trigger-Button, Tastatur, Deep-Link falls vorhanden)
2. Pflichtfelder validieren (leer, ungültig, gültig)
3. Speichern → Erfolg + UI-Reflektion
4. Abbrechen → keine Mutation, Fokus zurueck
5. ESC / Escape → identisch zu Abbrechen
6. Fehlerfall (Server 4xx/5xx) → Fehlermeldung, kein Crash, Retry moeglich
7. Fokusfalle + Fokus-Rueckfuehrung + ARIA-Rollen
8. Screenshot Baseline (offen, gefuellt, Fehler)

### 6.2 Jeder Button
- existiert mit eindeutigem `data-testid`, korrektes Label (DE/EN), `aria-label` falls Icon-only
- Klick loest genau eine dokumentierte Aktion aus (Netzwerk-Log als Beweis)
- Disabled-/Loading-/Error-State
- Tastatur (Tab/Enter/Space)
- Doppelklick-Schutz bei destruktiven Aktionen

### 6.3 Jede Einstellung
- Toggle setzen → persistiert nach Reload
- DE/EN-i18n korrekt
- Konflikt mit Preset (z. B. Feature in minimal nicht sichtbar)
- Rolle/KTier-Gate (viewer darf nicht, approver darf nicht, admin darf)
- Ruecksetzen auf Default

### 6.4 Jedes Artefakt (alle Typen)
CRUD + V-Modell-Kaskade:
- Create (Dialog, Validierung, Default-Werte je Preset)
- Read (Detailansicht, Versionen, Custom Fields, Acceptance Criteria)
- Update (inkl. Feld-Freeze nach Freigabe → FIELD_FROZEN in UI sichtbar)
- Derive / Decompose / Allocate / Link / Trace-Link-Typen
- Outdate / Reactivate (Soft-Delete-Semantik sichtbar)
- Baseline / Diff / Rollback-Preview
- Alle Workflow-States und erlaubte Transitionen (Graph-Test)
- Screenshot je State

### 6.5 Jeder Preset
- Feature-Flags sichtbar/unsichtbar
- Pflichtfelder permissiv vs. stringent
- Approval-Gates (Rollen, Change-Reason, Signatur)
- Tool-Count/Manifest-Drift (302 Tools, 49 Praefixe)

### 6.6 Visuelle Anordnung
- Screenshot-Diff pro Route × State × Preset × Theme × Breakpoint (Desktop/Tablet/Mobile)
- Dynamische Werte maskieren (UUIDs, Zeitstempel, Zaehler, Chat-Texte)
- Layout-Assertions: keine Ueberlappung, kein horizontaler Overflow, Touch-Target >= 24/44 px, Kontrast (axe)
- Dark/Light, DE/EN, 100 %/150 % Zoom

## 7. Prompt-/Trigger-System

Um „alles getriggert" zu realisieren, wird jeder Testfall ueber einen **Action-Dispatcher** im Browser ausgeloest:

- `navigate(route)` → `openDialog(testid)` → `fill(field, value)` → `click(button)` → `assertState(...)`.
- Kein direkter Aufruf von Services oder REST im Testkoerper.
- Jede Aktion schreibt einen Eintrag ins `action-log.jsonl` mit `actor=UI`, `selector`, `timestamp`, `screenshotRef`.
- Bei Fehler: Trace + Video + Network-Harness automatisch an den Report haengen.

## 8. Organisation & Ausfuehrung

- **Spec-Struktur:** `e2e/tests/generated/<route>/<artifact>.spec.ts` (generiert aus Katalog) + `e2e/tests/handwritten/` fuer Spezialfaelle.
- **Fixtures:** global-setup (preconditions), workspace-factory (pro Spec eigener Workspace, Isolation), role-fixtures.
- **Sharding:** bestehende 4 CI-Shards + Mobile + neuer `ui-matrix`-Shard; `workers: 1` ( bewusst, wegen Shared DB-State).
- ** CI-Budget:** Matrix-Specs in 4 Teilmengen aufteilen, maximale Laufzeit pro Shard ~20 min (Erfahrung: 17m24s beim langsamsten Set).
- **Flakes:** Quarantaene-Datei, automatischer Re-Run (max. 2), kein stilles Ignorieren; `check:unexpected-skips` bleibt aktiv.

## 9. Reporting und Abnahme

- HTML-Report mit: Matrix-Abdeckung %, Screenshot-Diffs, axe-Verletzungen, Network-Statuscodes, Action-Log.
- **Exit-Kriterium:** 100 % der als `critical` markierten Matrix-Zellen grün, 0 axe serious/critical, 0 unmaskierte visuelle Diffs, `gh pr checks` grün.
- Jeder Befund bekommt einen Stable-ID (`UI-<route>-<artefakt>-<zustand>`), damit Regressionen referenzierbar sind.
- Monatlicher Review: Katalog gegen Code-Drift abgleichen (neue Dialoge/Buttons ohne Test → rote Zelle).

## 10. Phasen & Aufwand (Schätzung)

| Phase | Inhalt | Aufwand (ca.) |
|---|---|---|
| P0 | Katalog-Generator + Abdeckungsmatrix + Action-Dispatcher | 2–3 Tage |
| P1 | L1: alle 31 Dialoge + Button-Vertraege (Vitest) | 3–5 Tage |
| P2 | L2: Artefakt-Zustandsmaschinen + Rollen/Presets (E2E) | 5–8 Tage |
| P3 | L3/L4: visuelle Baselines + axe auf alle States | 3–5 Tage |
| P4 | L5 Random-Walk + CI-Shards + Reporting/Dashboard | 2–3 Tage |
| P5 | Drift-Gate im CI (neue UI ohne Test blockt PR) | 1–2 Tage |

Gesamt: **ca. 16–26 Arbeitstage**, aufteilbar in mehrere PRs.empfehlung: P0 + P1 als ersten PR (groesster Hebel: Dialoge/Buttons), danach P2.

## 11. Risiken / Grenzen

- 518 Komponenten und 75 Specs bedeuten: ohne Generierung aus Code veraltet der Katalog sofort → Generator ist Pflicht, nicht optional.
- Screenshot-Diffs sind bei aktivem Chat-/Hilfe-Widget und dynamischen Zaehlern flaky → Maskierung zwingend.
- MFA: E2E-Helper unterstuetzt derzeit kein TOTP; User hat MFA im Dev-Stack deaktiviert. Fuer CI ist das kein Thema (eigene Seeds), fuer lokale Laeufe ist es dokumentiert.
- Browser-Tool-Verbote verhindern `browser_evaluate`; deshalb L2 ueber Playwright-Specs (nicht ueber MCP-Browser) fahren.

## 12. Nächster Schritt

Freigabe einholen, ob **P0+P1** als naechster PR umgesetzt werden soll. Der aktuelle Fix-PR (`fix/workspace-null-uuid-requests`) laeuft parallel und bleibt davon unberuehrt.
