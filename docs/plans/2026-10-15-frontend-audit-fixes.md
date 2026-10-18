---
type: Plan
title: "Frontend-Audit-Fixes — Umsetzungsplan"
scope: "frontend/src (React 19, TS 5.5+, Vite 8, Vitest)"
status: in Umsetzung
date: 2026-10-15
status_updated: 2026-10-18
progress_base: "origin/main = 6d87b172"
base_head: b6159d6b
target_branch: fix/audit-frontend-findings
author_agent: planner
language: de
---

# Frontend-Audit-Fixes — Umsetzungsplan

> **Reiner Umsetzungsplan. Kein Code, keine Migration, keine Config-Änderung.**
> Dieses Dokument ist **eigenständig lesbar**: die Befunde der vorausgegangenen
> Frontend-/System-Audits sind als Evidenz- und Findings-Abschnitte (§1, §2, §3)
> vollständig eingearbeitet. Es entscheidet **keine** neuen Produktpunkte; die vier
> bestätigten Entscheidungen sind in „Entscheidungen (bestätigt)" festgehalten.
> Jede `datei:zeile`-Angabe wurde gegen den Arbeitsbaum bei Basis-HEAD `b6159d6b`
> verifiziert; überholte Alt-Annahmen sind in §2 dokumentiert.

| Feld | Wert |
|---|---|
| **Status** | **In Umsetzung** — Phasen 0–4 gemergt, Phase 5 (5a/5b) als PR offen; Phasen 5c/6–8 offen. Vier Entscheidungen bestätigt (siehe „Entscheidungen (bestätigt)"). Fortschreibung siehe „Umsetzungsstand" oben. |
| **Datum** | 2026-10-15 (Stand aktualisiert: 2026-10-18) |
| **Bezug** | System-Audit `frontend/src` 2026-10-15 · Frontend-Fach-Audit (16 Findings, Score 57) · UI-Audit (Score 68) · Code-Qualitäts-Audit (C+ 7.0/10) · Accessibility-Audit (78/100) · `frontend/src/test/design-system-ratchet.baseline.json` (#954, #797, #1091, #1093, #1092) · #1193 |
| **Grundlage** | Verifizierter Arbeitsbaum-Stand bei Basis-HEAD `b6159d6b`; graphify-Wissensgraph `graphify-out/graph.json` (bei `b6159d6b` gebaut; 50.289 Nodes, 4.035 Nodes unter `frontend/src/`); read-only Code-/A11y-/Ratchet-Evidenz-Inventare |
| **Geltung / Scope** | Ausschließlich `frontend/src` (plus `frontend/src/test` und `e2e/`). Reuse-Refactors, Storage-DRY, Timer-Cleanups, God-Component-Zerlegung, A11y-Rest, Design-System-Ratchet-Abbau |
| **Nicht-Teil** | Kein Backend, keine API-/Contract-Änderung, kein neues Feature; keine Erhöhung irgendeines Ratchet-Ceilings; keine Migration; kein Commit/Push auf `main` |

---

## Umsetzungsstand (fortgeschrieben 2026-10-18)

> **Persistenter Projektstand** — fortlaufend gepflegt, damit die Bearbeitung an
> beliebiger Stelle fortgesetzt werden kann. Ursprünglicher Plan-Text ab §0 ist
> unverändert; dieser Abschnitt ist der **einzige lebende Status-Teil**.
>
> Lokaler (gitignorierter) Session-Checkpoint als Zusatz: `.meta-viz/checkpoint-20261017-frontend-audit.json`.

- **Basis (`origin/main` zum Fortschreibungszeitpunkt):** `6d87b172`
- **Branch-Konvention (Abweichung vom Plan):** je Phase ein eigener Branch `fix/audit-frontend-phaseN` statt eines Sammel-Branches `fix/audit-frontend-findings`. Jede Phase wird als eigener PR gemergt.
- **Verifikations-Baseline (Phase 0):** `npm run lint` 0 errors / **231** warnings · `tsc` exit 0 · `vitest` 296 Files / 2808 pass + 1 env-Flake `mermaidSanitizeRoundtrip` (isoliert grün) · Ratchet-Ceilings **278 / 26 / 3** (27 Exemptions). Baseline post-hoc gemessen.
- **Regel für Folgephasen:** nur **neue** Fails blockieren (Delta gegen Baseline); Ratchet-Ceilings dürfen **nie** erhöht werden; Lint-Warnungen liegen exakt bei 231/231 → **kein Puffer** für neue Warnungen.

### Status je Phase

| Phase | Status | Branch | PR → Merge | Commits | Kern-Verifikation |
|---|---|---|---|---|---|
| 0 Baseline | ✅ done | — | — | — | 0 Err/231 Warn; tsc 0; Ratchets 278/26/3 |
| 1 Timer + premature Memos | ✅ gemergt | `fix/audit-frontend-phase1` | #1426 → `c1a989ad` | `bc456857` (FE-04), `6eb1d688` (FE-07) | Timer-Clear je Site; vitest grün |
| 2 safeStorage (DRY) | ✅ gemergt | `fix/audit-frontend-phase2` | #1427 → `3a4e9d99` | `0f87c96e`, `8842b464` (FE-05) | 14 Sites migriert; validate-on-read |
| 3a `useArtifactList` | ✅ gemergt | `fix/audit-frontend-phase3a` | #1428 → `e99020d6` | `df670f46`, `ac23f549` (F-13) | 9 Listen migriert |
| 3b `useInitialFormValues` + `EditorPageShell` | ✅ gemergt | `fix/audit-frontend-phase3b` | #1429 → `2079e35e` | `d25e6c10` (F-14, F-15) | vitest 299/2837/0 |
| 4 Type-Barrel-Split | ✅ gemergt | `fix/audit-frontend-phase4` | #1430 → `6d87b172` | 12 × `1f2cd9f3`..`15417b24` (F-16) | tsc 0 je Commit; Barrel 1162 → 21 LOC; Exporte 96 = 96 |
| 5a WorkspaceContext | ✅ (PR offen) | `fix/audit-frontend-phase5` | #1431 (offen) | `0ff7f7d4`, `079e7c85` (FE-01, F-03) | 581 → 319 LOC; API 1:1 |
| 5b ArtifactForm | ✅ (PR offen) | `fix/audit-frontend-phase5` | #1431 (offen) | `d3ec31fe`, `b202967e`, `8493b068` (FE-01, F-01) | 1359 → 226 LOC; Props/8 Renderstellen unverändert |
| 5c WorkspaceTree | ⬜ offen — **gebündelt mit Phase 6** | `fix/audit-frontend-phase6` (geplant) | — | — | H-1 Keyboard-Reparenting |
| 6 Accessibility | ⬜ offen | `fix/audit-frontend-phase6` (geplant) | — | — | Skip-Link, Drawer-Modal, `useMediaQuery`, Sections, M-2/M-4/L-2, axe-Gate |
| 7 Ratchet-Abbau | ⬜ offen | `fix/audit-frontend-phase7` (geplant) | — | — | Ceilings < 278/26/3 senken |
| 8 Final-Verifikation & DoD | ⬜ offen | `fix/audit-frontend-phase8` (geplant) | — | — | lint/build/vitest/e2e/axe |

**Phase 5 (5a+5b) Verifikationsdetails:** `tsc` exit 0 je Commit · `vitest` **301 Files / 2853 pass / 0 fail** (Delta +2 Files/+16 Tests, 0 neue Fails) · lint 0 Err/231 Warn · 4 Ratchets grün, Ceilings 278/26/3 unverändert.

### Wiederaufnahme (nächster Schritt)

1. **PR #1431 mergen** (`fix/audit-frontend-phase5` → `main`). Erst danach Phase 6 starten.
2. **Phase 6** auf neuem Branch `fix/audit-frontend-phase6` (Basis = aktueller `origin/main`), **inklusive 5c** (WorkspaceTree-Zerlegung + H-1 Keyboard-Reparenting, da beides dasselbe Modul schneidet).
3. Danach Phase 7 (Ratchet-Abbau) und Phase 8 (Final-DoD) wie im Plan-Text ab §Phase 6/7/8.

### Abweichungen / Erkenntnisse (fortgeschrieben)

- **Phase 1:** FE-07 ohne Teständerung; Phase-0-Baseline post-hoc.
- **Phase 3a:** `usePersistedListFilter` **geskippt** — nur 1 Persistenz-Consumer (statt geplant für alle Listen); dokumentiert.
- **Phase 3b:** `EditorPageShell` ist der **create-dialog-Scaffold** (komponiert `useSaveShortcut`, dupliziert es nicht). Die im Plan genannten „Dirty-Wrapper / Workflow-Status / ConfirmDialog" sind **kein** gemeinsames Page-Glue (Dirty = per-Page-Sibling-Logik, Workflow-Status liegt im `ArtifactForm`, `ConfirmDialog` page-spezifisch) → bewusst minimal gehalten. Die 8. Direkt-Renderstelle (`RequirementEditors.tsx` Create-Dialog) ist **nicht anwendbar** (statische `initialValues`, Shortcut liegt im `ArtifactForm`). `dialog-consistency-ratchet` angepasst: `EditorPageShell` als 13. Host gepinnt (geschärft, nicht geschwächt).
- **Phase 4:** Domänen-Zuschnitt aus den echten Exporten abgeleitet — `metrics` **verworfen** (nicht gerechtfertigt); `diagram` fasst Diagram/Graph/Canvas/Mermaid zusammen; `common` = geteilte Primitives + generische API-Envelopes. Kein Zyklus (kein Modul importiert `./index` oder ein Geschwister).
- **Phase 5:** RMZ-Matrix (`widgets/RiskMatrixRpz`) und Status-Editor (`WorkflowStatusEditor`) **waren bereits** eigenständig → keine redundante Extraktion. `design-system-ratchet.baseline.json` **decken-neutral re-recorded** (Section-Toggle-Button wanderte `ArtifactForm.tsx` → `ArtifactSections.tsx`; Datei:Zeile steckt im Key). Plan-LOC „588" vs. gemessen „581" (Plan gegen ältere Revision).

### Unveränderte Randbedingungen (für alle Folgephasen)

- **Kein** `main`/`master`-Commit; Push/Tag/Branch/PR ausschließlich über die `git`-Rolle; kein Force-Push, kein Branch-Löschen.
- Keine API-/Contract-/Props-/Context-API-Änderung; kein neues Feature; **keine Erhöhung** irgendeines Ratchet-Ceilings.
- `SystemSettings` / **#1258 aussparen**.
- Conventional Commits (Beschreibung Englisch, erste Zeile ≤ 72 Zeichen — die vorgegebenen Plan-Messages liegen selbst bei ~79–80 Zeichen; ohne Commitlint ist das advisory).
- Secret-Scan (gitleaks) vor jedem Commit.
- **Fremde Dirty-/Untracked-Dateien nie anfassen/stagen:** `.serena/project.yml`, `$null`, `docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md`, `knowledge/wiki/plans/`, `knowledge/wiki/specs/`.

---

## 0. Ziel & Scope / Nicht-Ziele

**Ziel:** Die verifizierten Frontend-Audit-Befunde (God-Components, Timer-Leaks, echte
premature Memos, DRY-/Reuse-Duplikate, fehlende A11y-Grundlagen, Design-System-Ratchet-
Rückstand) in kleinen, risiko-geordneten, einzeln revertierbaren Schritten abbauen —
**ohne Verhaltensänderung** außer dort, wo der Befund genau das ist.

**Arbeitsweise:** branch-basiert (`fix/audit-frontend-findings`), ein Commit pro Phase bzw.
pro Batch, Conventional Commits (Beschreibung Englisch), Referenz auf Audit-ID / Issue.
**Risiko-Reihenfolge:** risikoarme mechanische Fixes zuerst, der 206-Consumer-Barrel-Split
und die God-Component-Refactors zuletzt.

**Nicht-Ziele:**

- Keine neuen Features, kein API-Change, keine Erhöhung irgendeines Ratchet-Ceilings.
- Kein Umbau der vier server-backed Hooks in eine Storage-Factory (siehe §2).
- Kein `main`/`master`-Commit (Branch-Guard); Push/Tag/Branch bleiben Aufgabe der `git`-Rolle.

---

## 1. Audit-Befundlage (eingearbeitet)

### 1.1 System-Audit `frontend/src` — Domänen-Scores (2026-10-15)

| Domäne | Score | Kernbefund |
|---|---|---|
| Frontend-Code & Reuse | **57 / 100** | 16 Findings; 6+ Editor-Listen duplizieren Scaffolding |
| UI/UX-Konsistenz | **68 / 100** | tokenisiert; 278 eingefrorene unstyled Buttons; 26 Emoji-Glyphen |
| Allgemeine Code-Qualität | **C+ (7.0 / 10)** | drei 1k+-LOC-Komponenten; monolithisches Type-Barrel |
| Accessibility (WCAG 2.x) | **78 / 100** | 0 CRITICAL, 2 HIGH, 4 MEDIUM, 3 LOW |

**Verifikations-Baseline des Audits (read-only):** `npm run lint` → 0 errors, 298 warnings
(überwiegend `@typescript-eslint/no-explicit-any` und Style, v. a. Tests/Baseline);
`tsc --noEmit -p tsconfig.build.json` → exit 0. **Unit-Test-Läufe wurden im Audit NICHT
ausgeführt** (read-only) — das ist das größte Plan-Risiko und Grund für die Baseline-Phase 0.

### 1.2 Cross-cutting-Blocker (empfohlene Fix-Reihenfolge)

1. **God-Components / Reuse-Root:** `shared/ArtifactForm/ArtifactForm.tsx` (1359 LOC) und
   `shared/WorkspaceTree/workspace-tree.tsx` (1370 LOC). Orchestrierung vs. Rendering trennen;
   ergibt extrahierbare `EditorPageShell` / `useArtifactList`.
2. **State-Drift-Risiko:** `context/WorkspaceContext.tsx` — manuelle Ref-Twins + separates
   `overriddenKeys`-Set. Aus einer einzigen Quelle ableiten.
3. **Async-Leaks:** fire-and-forget-Timeouts in `CanvasEditor`, `MermaidEditor`,
   `MemoryVisualizationSection` — `clearTimeout` beim Unmount ergänzen.
4. **Monolithisches Barrel:** `types/index.ts` (1162 LOC) — je Domäne splitten, Barrel-Reexports
   erhalten.
5. **Still geschluckte Fehler:** `shared/ArtifactInspector/CommentPanel.tsx` (vier leere `catch {}`
   — **bereits erledigt**, siehe §2).
6. **Accessibility-Highs:** WorkspaceTree pointer-only-Reparenting (SC 2.1.1/2.5.7);
   ArtifactForm-Sections ohne accessible name/Heading (SC 1.3.1/2.4.6); mobiler Sidebar-Drawer
   ohne Modal-Focus-Handling; kein Skip-Link (SC 2.4.1).
7. **Reuse-Backlog:** sechs Editor-Listen duplizieren Filter/Map/Map-Scaffolding; vier
   Inspector-Panel-Kopien; wiederholte `initialValues`-Boilerplate über sechs `*ArtifactForm`.
8. **WCAG-Oberfläche:** 278 button-chrome-freie Controls (eingefroren), 26 Emoji-Glyphen,
   3 mehrdeutige Blanko-Verb-Labels.
9. **Premature `useMemo`:** triviale Operationen memoised (Multiplikation, `Set` aus Primitiven).

### 1.3 Frontend-Fach-Audit — 16 Findings (Score 57)

Deduktionen (Kurz): FE-01 God-Components −10 · FE-02 doppelter State −8 · FE-04 Timer-/
Listener-Leaks −9 · FE-05 Perf −2 · FE-07 premature Memos −6 · REUSE-Duplikation −8
(FE-06 Bundle-Secrets: 0; keine `sk-`/Token-Literale, env nicht inlined).

- **FE-01 God-Components:** `ArtifactForm.tsx` (1359 LOC, F-01), `CanvasEditor.tsx` (1426) +
  `audit-dashboard.tsx` (1445) (F-02), `WorkspaceContext.tsx` (588, F-03).
- **FE-02 doppelter State:** `WorkspaceContext.tsx:195-197,470-492` Ref-Twins (F-04);
  `overriddenKeys`-Set neben `userOverrides`-Map (F-05).
- **FE-04 Timer/Listener:** `CanvasEditor.tsx:454` ungetrackter `setTimeout` (F-06);
  `MermaidEditor.tsx:364` idle-Timer nicht vom Cleanup gedeckt (F-07);
  `MemoryVisualizationSection.tsx:233` Debounce ohne Unmount-Cleanup (F-08).
- **FE-05 Perf:** `InterviewWidget.tsx:65-82` defensive `localStorage`-Re-Reads im Render-Pfad (F-09).
- **FE-07 premature Memos:** `ArchitectureDecomposePanel.tsx:235` (`nodeCount * 3`, F-10);
  `workspace-tree.tsx:432` (`new Set(displayFields)`, F-11); `ArtifactForm.tsx:513,539` (F-12) —
  **Letzteres ist widerlegt** (siehe §2: keine premature Memos).
- **REUSE:** sechs Editor-Listen mit identischem Scaffolding (F-13); `initialValues`-Boilerplate
  in jedem `*ArtifactForm` (F-14); Page-Level-Glue statt `EditorPageShell` (F-15);
  wiederholte Tree-Display-/Filter-Persistenz (F-16).

### 1.4 UI-Audit (Score 68)

- **UI-01 Token-Konformanz:** `styles/tokens.css` ist kanonisch; verbleibende Roh-`rgba`-Werte nur
  in CSS-Modul-Shadows/Glows (z. B. `DiagramGraphEditor.module.css:46,322,396`) — Spiegel
  numerischer Opacity-Fallbacks.
- **UI-02 Layout:** Breakpoints in Tokens (`--bp-md:768px`, `--bp-lg:1024px`, `--bp-xl:1600px`);
  keine neue Drift.
- **UI-03 Interaction-states:** `<Dialog>`, `<EmptyState>`, `<Spinner>`, `<ConfirmDialog>`
  konsistent; Rest-Problem sind Icon-only-Controls (UI-05).
- **UI-04 i18n:** überwiegend `react-i18next` `t(...)`; kleinere Fallback-Literale in
  `Dialog.tsx:204-205` (`aria-label`/`title`) sind Locale-Fallbacks, keine Primärstrings.
- **UI-05 WCAG-Basics:** Emoji-Glyphen als UI (z. B. `MismatchReviewTable.tsx:179-181` `⚠`;
  `SidebarNavigation` ✓/✕; `TraceabilityView` ⚠; `InspectorPanel` 🔒; `RightSidebar` 📌/🔗).
- **UI-06 Identifikation:** 3 eingefrorene Blanko-Verb-Labels (`attribute-editor-export`,
  `attribute-editor-import`, `workflow-export-button`).
- **UI-07 Semantik:** Shared `<Dialog>` korrekt (`role="dialog"` + `aria-modal` +
  `aria-labelledby`); Hauptlücke = 278 `button`-Elemente ohne `btn-*`-Klasse (eingefroren),
  inkl. Shared-Primitives (`Dialog.tsx:199` `className={styles.close}`, `EmptyState`-Buttons).

**Living-Baseline (Ratchet-Tests):** `design-system-ratchet.test.ts` → `button-missing-design-system-class` 278,
`emoji-as-ui-glyph` 26, `ambiguous-button-label` 3 (alle eingefroren, keine neuen Regressionen).

### 1.5 Code-Qualitäts-Audit (C+ 7.0/10)

**Stärken:** zentrale API-Fehler-Extraktion, timeout-garantierter Fetch (`client.ts`),
External-Store-Pattern für High-Frequency-Reads, konsistente Badge-Geometrie.
**Schwächen:** monolithisches Type-Barrel, übergroße Form-/Tree-Komponenten, wiederholte
modulare Store-Boilerplate, still geschluckte Fehler in Shared-Inspektor-Panels.

**Top-Dateien nach LOC (>800, non-test):**
`audit-dashboard.tsx` 1445 · `CanvasEditor.tsx` 1426 · `workspace-tree.tsx` 1370 ·
`ArtifactForm.tsx` 1359 · `ReviewsView.tsx` 1233 · `CsvImport.tsx` 1163 · `types/index.ts` 1162 ·
`AttributeEditorPage.tsx` 1132 · `TraceabilityView.tsx` 1073 · `ArchitectureEditors.tsx` 947 ·
`SplitView.tsx` 836 · `MemoryPage.tsx` 830 · `api/client.ts` 616.

**Blocker:** (1) `types/index.ts` 1162-LOC-Barrel; (2) `workspace-tree.tsx` (D&D + Virtualisierung
+ Display-Fields in einem Tree); (3) `ArtifactForm.tsx` (universelle Form-Engine, 7 Editoren);
(4) `api/client.ts:440-616` mischt Fetch/Auth/Pagination/Errors; (5) `usePersistedListState.ts:45`
`JSON.parse(raw) as T` ungeprüft; (6) `useReadableIdsVisible` + `useTreeDisplayFields` doppelte
External-Store-Scaffolds; (7) four silent `catch` in `CommentPanel.tsx` (**erledigt**, §2);
(8) flache `STATUS_VARIANT_MAP` in `statusBadge.ts` (akzeptabler Classifier, Guard-Test empfohlen).

### 1.6 Accessibility-Audit (78/100)

**Verteilung:** 0 CRITICAL · 2 HIGH · 4 MEDIUM · 3 LOW.

- **H-1 (HIGH):** WorkspaceTree D&D-Reparenting ohne Keyboard-/Single-Pointer-Alternative
  (`workspace-tree.tsx:1201`; nur HTML5-D&D; `handleTreeKeyDown` deckt kein Reparent ab) —
  SC 2.1.1 (A), SC 2.5.7 (AA).
- **H-2 (HIGH):** ArtifactForm-`<section>` ohne accessible name/Heading-Semantik
  (`ArtifactForm.tsx:926-932`) — SC 1.3.1 (A), SC 2.4.6 (AA).
- **M-1 (MED):** Mobiler Sidebar-Drawer nicht modalsemantisch — kein Initial-Focus, kein
  Focus-Trap, kein Focus-Return (`SidebarNavigation.tsx:474-495`) — SC 2.1.1/2.4.3/4.1.2.
- **M-2 (MED):** Audit `RuleInfoPopover` nutzt `role="dialog"` ohne Modal-Semantik/`aria-labelledby`/
  Focus/Escape (`audit-dashboard.tsx:1170-1200`).
- **M-3 (MED):** Kein Skip-Link/Bypass-Block vor der Primärnavigation
  (`NavigationShell.tsx:122-127`; `rg skip-link/main-content` → 0 Treffer) — SC 2.4.1 (A).
- **M-4 (MED):** `CreateTraceLinkDialog` Typ-Tabs/Element-Liste ohne Selected-State-Semantik
  (kein `aria-pressed`/`aria-selected`) — SC 4.1.2.
- **L-1 (LOW):** Dialog-Close-Button bewusst aus Tab-Order (`Dialog.tsx:199-213`, `tabIndex={-1}`).
- **L-2 (LOW):** `WorkspaceCard` clickable `role="button"`-Div ohne `aria-label`
  (`WorkspaceCard.tsx:63-84`).
- **L-3 (LOW):** Statusanzeigen teils Farbe+Dot (`SystemHealthDialog.tsx:228-231`) — Text-Status
  vorhanden, funktional.

**Positives (nicht regressieren):** `Dialog.tsx` (`role="dialog"` + `aria-modal` + `aria-labelledby`
+ Portal + Focus-Trap + Escape + Focus-Restore); `ArtifactForm.tsx` (`role="alert"` +
`aria-live="assertive"`); `global.css:63` globaler `:focus-visible`-Ring; `global.css:14-22`
`prefers-reduced-motion`; WorkspaceTree vollständiges ARIA-Treeview-Keyboard-Modell.
**Tooling-Lücke:** kein **automatisiertes** Runtime-A11y-Gate — statisch, ohne Kontrast-Ratios.
**Evidenz-Fußnote (Tooling-Realität):** `e2e/a11y-followup.js` nutzt axe-core manuell (nicht in
`playwright test`, kein CI-Gate). Entscheidung 2 bleibt gültig, weil ein automatisiertes Gate
fehlt — nicht weil axe völlig fehlt.

---

## 2. Korrektur-Status (verifizière Korrekturen)

Diese Punkte wurden am Arbeitsbaum geprüft. Sie sind **verifiziert** und in der Umsetzung
entsprechend einzuordnen:

| Alt-Befund | Verifizierter Status | Beleg |
|---|---|---|
| Silent-Catches `CommentPanel.tsx` (40/57/70/88) | **ERLEDIGT** — alle vier `catch` setzen i18n-`error`-State | `CommentPanel.tsx:41,58,71,89` |
| Leere `catch {}` `ReviewsView.tsx` | **ERLEDIGT** (#1193) — `onError`/`setActionError` + Anzeige | `ReviewsView.tsx:174-197,193` |
| `MemoryVisualizationSection` `filterDebounceRef` fehlt | **ERLEDIGT** — Ref existiert + `clearTimeout` | `MemoryVisualizationSection.tsx:111,232` |
| `MermaidEditor` Timer-Cleanup fehlt | **TEILWEISE** — `previewTimerRef`/`saveTimerRef` + Cleanup vorhanden; **nur** idle-`setTimeout` (L364) offen | `MermaidEditor.tsx:382-383` |
| Premature `useMemo` `ArtifactForm.tsx:513,539` | **FALSCH** — echte Deps von `groupedSections`/`sectionEntries` (Set/Map-Aufbau) | `ArtifactForm.tsx:513,539,553-596` |
| `usePersistedListFilter` „existiert bereits" | **FALSCH** — existiert nicht (0 Treffer) | `rg` |
| `useReadableIdsVisible`/`useTreeDisplayFields` in generische Storage-Factory zwingen | **FALSCH** — beide **server-backed**; `useTreeDisplayFields` nutzt gar kein `localStorage` | Docstrings (Issues #1096 / #1257) |
| Silent-Errors-Phase als eigener Block | **ENTFÄLLT** — bereits erledigt | — |
| Storage „26 Dateien mit direktem Zugriff" | **KORRIGIERT** — **26 Dateien mit String-Nennung** (gepinnter Scope §3.4), aber nur **14 echte Zugriffs-Sites** (12 nur Kommentar/Key-Konstante) | `rg -l` (Scope §3.4) + Einzelprüfung |
| Timer: „3 Leaks" | **KORRIGIERT** — **2 harte fire-and-forget-Leaks** (`CanvasEditor:454`, `MermaidEditor:364`) + **2 Debounce-Cleanup-Lücken** (`MemoryPage:217`, `MemoryVisualizationSection:233`) | Inventar §3.1 |

**Konsequenz:** Es bleiben die **2 echten** Timer-Leaks, die **2** Debounce-Cleanup-Lücken,
die **2 echten** premature Memos und die DRY-/A11y-/Ratchet-Arbeit.

---

## 3. Blast-Radius & Detail-Evidenz (graphify + Arbeitsbaum)

### 3.1 Blast-Radius-Matrix (graphify-Rückwärts-Importkanten, Basis-HEAD `b6159d6b`)

| Zielsymbol | importierende FE-Dateien | LOC (gesamt) | Risiko | Phase |
|---|---:|---:|---|---|
| `types/index.ts` (Barrel) | **206** | 1162 | **hoch** | 4 |
| `context/WorkspaceContext.tsx` | **104** | 588 (558 nicht-leer) | **sehr hoch** | 5 |
| `shared/ArtifactForm/ArtifactForm.tsx` | **14** (7 Editor-Forms + `RequirementEditors.tsx` Direct-Render + `index.ts`/`payload.ts` + 4 Tests) | 1359 | **hoch** | 3c / 5b |
| `shared/WorkspaceTree/workspace-tree.tsx` | **3** (extern) | 1370 | **hoch** | 5c / 6 |
| `hooks/useReadableIdsVisible.ts` | 5 | — | niedrig | 2 (nur intern) |
| `hooks/useTreeDisplayFields.ts` | 5 | — | niedrig | **nicht anfassen** (server-backed) |
| `hooks/usePersistedListState.ts` | 2 | — | niedrig | 2 / 3a |

Methode: exakter Rückwärts-Kanten-Scan (`imports`/`imports_from`/`re_exports`/`dynamic_import`)
über `graphify-out/graph.json` — die Ad-hoc-`graphify query` ist heuristischer BFS und für
Fan-in-Zahlen ungeeignet (bei ~2000 Tokens trunkierend).

### 3.2 Timer-Inventar (`setTimeout` ohne zugehöriges `clearTimeout`)

Scan-Basis: `rg -n "setTimeout" frontend/src` → 60 Treffer (inkl. Tests); davon 22 Nicht-Test-Aufrufe,
**20 korrekt abgesichert**, **2 ohne jedes Clear**, zusätzlich **2 Debounce-Timer ohne Unmount-Cleanup**.

| # | Datei:Zeile | Clear? | Verdikt |
|---|---|---|---|
| 1 | `components/canvas/CanvasEditor.tsx:454` | **nein** | **LEAK** (fire-and-forget in `handleAutoSave`) |
| 2 | `components/mermaid/MermaidEditor.tsx:364` | **nein** | **LEAK** (idle-Reset; von `previewTimerRef`/`saveTimerRef` nicht gedeckt) |
| 3 | `components/SystemSettings/MemoryVisualizationSection.tsx:233` | ja (L232) | harmlos (Debounce), **kein Unmount-Cleanup** |
| 4 | `components/Memory/MemoryPage.tsx:217` | ja (L216) | harmlos (Debounce), **kein Unmount-Cleanup** |

Ausdrücklich harmlos (mit Cleanup, kein Eingriff): `WorkflowEditorPage.tsx:112` (`toastTimerRef` +
Unmount-Cleanup L120), `shared/Toast/useToast.ts:60` (`timerRef` + Cleanup L69),
`DiagramGraphEditor/useGraphAutosave.ts:177,224` (Cleanup L335-339),
`bluepencil/loader.ts:171,211,243` (Handle-Timer sauber gecleart).

### 3.3 Premature `useMemo` (bestätigt vs. widerlegt)

- **Echt (trivial):** `ArchitectureDecomposePanel.tsx:234-235` (`useMemo(() => nodeCount * 3, [nodeCount])`);
  `workspace-tree.tsx:431-432` (`useMemo(() => new Set(displayFields), [displayFields])`).
- **NICHT premature:** `ArtifactForm.tsx:513` (`widgetOwned`, Dep von `groupedSections` L553-556)
  und `:539` (`sectionMeta`, konsumiert von `sectionEntries` L567-596) — stabile Memo-Deps anderer
  Memos, nicht-triviale Set/Map-Aufbauten. **Keine Änderung.**

### 3.4 Storage-Zugriff

`src/utils/safeStorage.ts` existiert **nicht**; `createExternalStore` existiert **nicht**.

**Evidenz-Kommando (26 — reproduzierbar):**
```
rg -l "localStorage|sessionStorage" frontend -g "!*.test.*" -g "!**/test/**"
```
→ **26 Dateien mit String-Nennung**: 25 unter `frontend/src` + 1 vendored Bundled-Artefakt
`frontend/public/bluepencil/latest/bluepencil.element.min.js`. Davon **14 mit echtem
GET/SET/REMOVE** (Zugriffs-Sites, siehe Tabelle unten); die übrigen **12** nur Kommentar/
Key-Konstante/Re-Export.

**Kategorien-Trennung (26 ≠ 14):** **26** = Dateien mit einer String-Nennung (kein Vorkommen-,
kein Zugriffs-Zähler); **14** = echte Zugriffs-Sites. Der gepinnte Scope ist bewusst `frontend`
**ohne** `*.test.*` / `**/test/**` — ein `rg -l` über `frontend/` **plus `e2e/`** ohne
Test-Ausschluss liefert 53 Dateien und passt **nicht** zu diesen Zahlen.

**Die 14 echten Zugriffs-Sites:**

| # | Datei | Storage | Beispiel-Key |
|---|---|---|---|
| 1 | `hooks/useReadableIdsVisible.ts:57,65` | localStorage | `reqflow-display-readable-ids` (nur First-Render-Fallback, §3.5) |
| 2 | `hooks/usePersistedListState.ts:43,89` | sessionStorage | caller-supplied (`reqlo:list-state:…`) |
| 3 | `context/ThemeContext.tsx:109,117` | localStorage | `reqflow-theme-palette`, `reqflow-theme-mode` |
| 4 | `context/WorkspaceContext.tsx:128,220,240,247` | sessionStorage | `reqflow_workspace_id` |
| 5 | `components/NavigationShell/BannerStack.tsx:27,42` | sessionStorage | `banner-dismissed-*` |
| 6 | `components/NavigationShell/LoginPage.tsx:47,170` | sessionStorage | `banner-dismissed-global-login-*` |
| 7 | `components/SplitView/SplitView.tsx:396,453` | localStorage | `reqflow_splitview_<moduleType>` |
| 8 | `components/InterviewWidget/InterviewWidget.tsx:75,82` | localStorage (lokaler Wrapper L65) | `reqflow-interview-widget-open` |
| 9 | `components/ImpactView/ImpactView.tsx:356,358` | sessionStorage | `reqlo-impact-preset` |
| 10 | `components/TraceabilityView/TraceabilityView.tsx:875` | sessionStorage | `reqlo-impact-preset` |
| 11 | `components/AttributeEditor/AttributeEditorPage.tsx:116,206` | localStorage | `attributeEditor.viewMode` |
| 12 | `components/shared/ArtifactInspector/RightSidebar.tsx:94,112,124,133,146` | localStorage | `reqflow_inspector_*` |
| 13 | `components/WorkflowEditor/InspectorPanel.tsx:52,92` | localStorage | `reqflow_workflow_inspector_width` |
| 14 | `components/WorkflowEditor/layout-store.ts:31,48` | localStorage | `reqflow_workflow_positions_*` |

### 3.5 Server-backed Hooks (nicht in eine Storage-Factory zwingen)

- `useReadableIdsVisible.ts:4-20` — Issue #1096: **server-backed** via
  `GET/PATCH /api/v1/users/me/display-preferences/`; `localStorage` ist First-Render-Fallback,
  Rollback bei fehlgeschlagenem PATCH. External Store L150-156.
- `useTreeDisplayFields.ts` — Issue #1257: **server-backed** via
  `GET …/tree-display-config/?resolve=effective`; **kein `localStorage`** (Modul-Store
  `selections` L62 + In-Flight-Dedup `inFlight` L65 + `loadedKeys` L67).

### 3.6 Editor-Listen-Scaffolding (6 bestätigt)

| Liste | `visible` | `treeNodes` | `byId` | Spanne |
|---|---|---|---|---|
| `RequirementEditors/RequirementList.tsx` (Beleg) | 230-241 | 243-254 | `reqById` 258-262 | 230-262 |
| `RiskEditors/RiskList.tsx` | 76-84 | 86 | `riskById` 90-94 | 76-94 |
| `IssueEditors/IssueList.tsx` | 76-84 | 86 | `issueById` 90-94 | 76-94 |
| `TestCaseEditors/TestCaseList.tsx` | 78-86 | 88 | `testCaseById` 92-96 | 78-96 |
| `AdrEditors/AdrList.tsx` | 77-85 | 87 | `adrById` 91-95 | 77-95 |
| `NeedsEditors/NeedList.tsx` | 156-170 | 172-175 | — (kein `byId`) | 156-175 |

**Nuancen (nicht blind migrieren):** RequirementList filtert zusätzlich `category` + id; NeedList
`title` + `uid`; die übrigen nur `title` + `status`. NeedList hat **keine** `byId`-Map →
`useArtifactList`-API muss `byId` **optional** halten. Zusatz-Kandidaten mit gleichem
`visible = filter→sortItems`-Muster: `IcdView/IcdList.tsx:52-55`, `DiagramView/DiagramList.tsx:109-116`,
`InterviewEditors/InterviewList.tsx:66-84` (letzterer inkl. `treeNodes` + Map).

### 3.7 `*ArtifactForm`-Wrapper & Save-Shortcut

Alle sieben rendern genau ein `<ArtifactForm>`: `AdrArtifactForm.tsx:72`,
`ArchitectureArtifactForm.tsx:98`, `IssueArtifactForm.tsx:92`, `NeedArtifactForm.tsx:160`,
`RequirementArtifactForm.tsx:153`, `RiskArtifactForm.tsx:96`, `TestCaseArtifactForm.tsx:242`.
**8. Renderstelle:** `RequirementEditors.tsx:550` rendert `<ArtifactForm>` direkt (kein Wrapper) —
beim Shell-Entwurf mitdenken.
`hooks/useSaveShortcut.ts` (**259 LOC**) existiert zentral (Document-Level-`keydown`,
Topmost-Arbitration, `containerRef`-Gate) mit 10 Aufrufern — **kein Duplikat**.
`EditorPageShell` existiert **nicht** — es wird neu angelegt und **konsumiert** `useSaveShortcut`,
dupliziert es nicht.

### 3.8 A11y-/Hook-Evidenz (verifiziert)

- **Skip-Link fehlt:** `NavigationShell.tsx:127` `<main className={styles.main} role="main">` —
  kein `id="main-content"`, kein Skip-Link; `rg skip-link|main-content` → 0 Treffer.
- **Sidebar-Drawer:** Burger `SidebarNavigation.tsx:474-483` (`aria-expanded`), Backdrop
  `:484-495` (bewusst ohne `role`/`tabIndex`), Drawer `<nav>` `:496-498` — **kein** `role="dialog"`,
  **kein** `aria-modal`, kein Focus-Trap/Initial-Focus/Focus-Return; Escape `:453-460` vorhanden.
- **WorkspaceTree D&D:** `handleTreeKeyDown` `:700-788` deckt nur Arrow/Home/End/Enter/`*`/Letter-Jump;
  Zeilen-D&D `:1201-1226` pointer-only, kein Tastatur-Reparent.
- **Focus-Trap vorhanden** unter `components/shared/Dialog/use-focus-trap.ts` (`useFocusTrap` `:111`;
  Re-Export `shared/Dialog/index.ts:7-8`) — **nicht** unter `hooks/`.
- **`useMediaQuery` fehlt** — nur rohes `matchMedia` in `ThemeContext.tsx:60`; kein wiederverwendbarer
  Hook unter `frontend/src/hooks/`.

### 3.9 Design-System-Ratchet-Baseline (`frontend/src/test/design-system-ratchet.baseline.json`)

| Check | Ceiling (`maxViolations`) | `known`-Einträge | Issue |
|---|---:|---:|---|
| `button-missing-design-system-class` | **278** | 278 | #954, #797, #1091, #1093 |
| `emoji-as-ui-glyph` | **26** | 26 | #1092 |
| `ambiguous-button-label` | **3** | 3 | #1093 |

- **27 Exemptions** (alle `button-missing-design-system-class`), jeweils mit `reason` + `#NNN`
  (überwiegend #1099, eine #1262) — **nicht antasten**; neue Exemptions nur mit Begründung.
- **Chrome-Klassen** (`CHROME_CLASSES`): `btn-primary|btn-secondary|btn-danger|btn-ghost|btn-tab|btn-icon`.
- **Gate/Regeln** (`ratchet-framework.ts`, Spiegel von
  `backend/mcp_server/tests/ratchet_framework.py`, #1103 / REQ-193): `unexempted.length <= maxViolations`;
  Identitäts-Test auf neue Keys (nennt Datei:Zeile:Element); Staleness-Tests (gefixte-aber-nicht-
  rebaselinete Violations **und** veraltete Exemptions schlagen fehl); **Monotonie-Guard**
  `assertCeilingNotRaised` (Re-Baseline darf halten/senken, **niemals erhöhen**; nur der
  Bootstrap-Lauf ohne Baseline-Datei darf erhöhen — sonst bricht ein Dump vor dem Schreiben ab).
- **Re-Baseline-Kommando:** `DESIGN_SYSTEM_REBASELINE=1 npx vitest run src/test/design-system-ratchet.test.ts`.

---

## Entscheidungen (bestätigt)

Alle vier folgenden Punkte sind **bestätigt** und in der Umsetzung verbindlich:

1. **Sidebar-Drawer → modaler Mobile-Drawer.** `role="dialog"` + `aria-modal="true"`, Focus-Trap
   über das **vorhandene** `frontend/src/components/shared/Dialog/use-focus-trap.ts` (kein Neu-Bau),
   Initial-Focus ins Drawer, Focus-Return auf den Burger. Der **Desktop-Rail bleibt non-modal**
   (persistente Navigation, keine Focus-Bindung). Zusätzlich ist ein neuer **`useMediaQuery`-Hook**
   einzuplanen (existiert nicht), um Mobil/Desktop sauber zu unterscheiden. Wirksam in Phase 6.4,
   abgesichert durch `dialog-consistency-ratchet` + `dialog-focus-owner.test.ts`.
2. **`@axe-core/playwright` einführen** (Dev-Dependency in `frontend/` bzw. `e2e/`) und als
   **automatisiertes A11y-Gate** in **Phase 6 und Phase 8** verankern. *Tooling-Realität:*
   `e2e/a11y-followup.js` nutzt axe-core manuell (nicht in `playwright test`, kein CI-Gate).
   Entscheidung 2 bleibt gültig, weil ein automatisiertes Gate fehlt — nicht weil axe völlig fehlt.
3. **Phase 4 (Type-Barrel-Split, 206 Consumer) wird durchgeführt** — je Domäne **ein Commit**,
   Barrel-Reexports (`export * from "./<domain>"`) erhalten, `tsc --noEmit` nach **jedem** Commit.
4. **Zusatz-Listen `IcdList`, `DiagramList`, `InterviewList`** werden in den `useArtifactList`-Refactor
   aufgenommen — **nur nach Vorprüfung** des exakt identischen Scaffoldings (**bedingte Migration**);
   ohne bestandene Vorprüfung bleiben sie ausgenommen.

---

## Phase 0 — Baseline & Branching

### 0.1 Branch

1. `git checkout -b fix/audit-frontend-findings` (Basis `b6159d6b`).
2. Ab hier: ein Commit pro Phase/Batch; keine Sammel-Commits.

### 0.2 Baseline einfrieren (Pflicht)

Der Fach-Audit hat **keine Tests ausgeführt** — das ist das größte Plan-Risiko. Vor der ersten
Änderung wird der Ist-Stand reproduzierbar festgehalten und **in der PR-/CI-Beschreibung**
(dauerhaft, ohne Scratch-Dateien) notiert:

```bash
cd frontend
npm run lint                                   # erwartet: 0 errors, ~298 warnings
npx tsc --noEmit -p tsconfig.build.json        # erwartet: exit 0
npx vitest run                                 # Counts pass/fail/skip + bekannte Fails
npx vitest run src/test/ui-ratchet.test.ts \
             src/test/design-system-ratchet.test.ts \
             src/test/dialog-consistency-ratchet.test.ts \
             src/test/i18n-parity.test.ts
```

Zusätzlich die drei Ratchet-Ceilings (278 / 26 / 3) als Text festhalten — sie sind der Abnahmemaßstab.

### 0.3 Akzeptanz

Lint-/tsc-/Test-Counts und die drei Ratchet-Ceilings sind reproduzierbar dokumentiert.

---

## Phase 1 — Timer-Leaks & echte premature Memos

- **Ziel:** Die 2 fire-and-forget-`setTimeout`-Leaks und die 2 Debounce-Timer ohne Unmount-Cleanup
  schließen; die 2 echten premature Memos entfernen. Kein sonstiges Verhalten ändern.
- **Files (Modify):** `components/canvas/CanvasEditor.tsx`, `components/mermaid/MermaidEditor.tsx`,
  `components/Memory/MemoryPage.tsx`, `components/SystemSettings/MemoryVisualizationSection.tsx`,
  `components/ArchitectureDecompose/ArchitectureDecomposePanel.tsx`,
  `components/shared/WorkspaceTree/workspace-tree.tsx`.
- **Evidenz:** §3.2, §3.3.
- **Schritte:**
  1. `CanvasEditor.tsx:454`: Timer in `useRef` legen, im vorhandenen Unmount-Effect clearen.
  2. `MermaidEditor.tsx:364`: neuen `idleTimerRef` einführen und in den Cleanup (L382-383) aufnehmen;
     `previewTimerRef`/`saveTimerRef` unverändert.
  3. `MemoryPage.tsx` + `MemoryVisualizationSection.tsx`: je `useEffect(() => () =>
     clearTimeout(filterDebounceRef.current), [])` ergänzen.
  4. `ArchitectureDecomposePanel.tsx:234-235`: `useMemo` entfernen, `nodeCount * 3` inline.
  5. `workspace-tree.tsx:431-432`: `useMemo` entfernen bzw. `new Set(displayFields)` inline.
  6. **Nicht anfassen:** `ArtifactForm.tsx:513,539` (§2/§3.3).
- **Risiko/Mitigation:** niedrig (rein mechanisch). Falle: `MermaidEditor` nicht doppelt belegen —
  je Datei eigener kleiner Commit; Prettier/ESLint als Gate.
- **Akzeptanz:** Timer-Clear-Pfad je Site nachweisbar; keine neue Lint-Warnung (Trend ≤ Baseline);
  `npx vitest run` grün (keine neuen Fails gegenüber Baseline).
- **Commit:** `fix(frontend): clear untracked timeouts on unmount (FE-04)` ·
  `refactor(frontend): drop trivial useMemo on primitive values (FE-07)`

---

## Phase 2 — `safeStorage.ts` (DRY-Konsolidierung Storage-Zugriff)

- **Ziel:** Defensiven `localStorage`/`sessionStorage`-Zugriff (try/catch + Default) zentralisieren
  und die 14 tatsächlichen Zugriffs-Sites migrieren.
- **Files:**
  - Create: `src/utils/safeStorage.ts` + `src/utils/safeStorage.test.ts`
  - Modify (batchweise): die 14 Sites (§3.4); `InterviewWidget.tsx` verliert seinen lokalen Wrapper.
- **Evidenz:** §3.4, §3.5.
- **Schritte:**
  1. `safeStorage.ts`: `safeLocalStorage`/`safeSessionStorage` mit `get`/`set`/`remove`
     (try/catch → Default, SSR-Guard); API-Muster aus dem lokalen Wrapper in `InterviewWidget.tsx`.
  2. Optionaler Lese-Validator `get<T>(key, fallback, validate?)`.
  3. `usePersistedListState.ts`: migrieren **und** beim Lesen validieren (statt `JSON.parse(raw) as T`)
     → bei ungültiger Form `initialValue` liefern.
  4. `InterviewWidget.tsx` migrieren (lokalen Wrapper löschen).
  5. Weitere Sites nach Risiko, je eigener Commit: `ThemeContext`, `BannerStack`, `LoginPage`,
     `SplitView`, `RightSidebar`, `WorkspaceContext`-Storage-Teile, `ImpactView`, `TraceabilityView`,
     `AttributeEditorPage`, `InspectorPanel`, `layout-store`.
  6. `useReadableIdsVisible.ts`: **rein mechanisch** intern auf `safeLocalStorage` umstellen —
     server-backed-Semantik (First-Render-Fallback, PATCH-Rollback) bleibt unverändert.
- **Nicht tun:** `useReadableIdsVisible`/`useTreeDisplayFields` in eine generische Store-Factory
  zwingen (§3.5).
- **Risiko/Mitigation:** niedrig-mittel. `usePersistedListState` (Blast 2) muss tab-scoped stabil
  bleiben; `WorkspaceContext`-Storage nur den Zugriff berühren, keine Context-API ändern.
- **Akzeptanz:** `rg -n "localStorage|sessionStorage" frontend/src` findet Direkt-Zugriff nur noch
  in `utils/safeStorage.ts` (Key-Konstanten/Kommentare ausgenommen); `usePersistedListState.test.ts`,
  `RequirementList.filterPersistence.test.tsx`, Workspace-/SplitView-Tests grün; kein Verhaltensunterschied.
- **Commit:** `refactor(frontend): centralize safe web-storage access (FE-05)` ·
  `fix(frontend): validate persisted list state on read`

---

## Phase 3 — Reuse: Editor-Listen & Form-Scaffolding

- **Ziel:** Das identische `filter → sort → Map → toNode`-Scaffolding der Editor-Listen und die
  `initialValues`-/Dirty-/Save-Shortcut-Boilerplate der Editor-Forms in geteilte Bausteine ziehen.
- **Files:**
  - Create: `src/hooks/useArtifactList.ts` (+ Test), `src/hooks/usePersistedListFilter.ts` (+ Test),
    `src/hooks/useInitialFormValues.ts` (+ Test), `src/components/shared/EditorPageShell.tsx` (+ Test)
  - Modify: die 6 Editor-Listen (+ bedingt `IcdList`/`DiagramList`/`InterviewList`) und die
    7 `*ArtifactForm`-Wrapper + `RequirementEditors.tsx:550`
- **Evidenz:** §3.6, §3.7.
- **Schritte:**
  1. **`useArtifactList<T>({ items, filter, sort, toNode, keyFn })`** →
     `{ visible: T[], byId?: Map<string,T>, treeNodes: WorkspaceTreeNode[] }` (`byId` **optional**,
     weil NeedList keins hat) — genau das Scaffolding aus `RequirementList.tsx:230-262`.
  2. **`usePersistedListFilter`** (neu, existiert nicht): kapselt das persistierte Filter-/Sortier-
     Tripel pro Liste auf Basis `usePersistedListState`; Key-Muster aus `RequirementList.tsx:221-228`.
  3. **Vorprüfung je Liste:** `visible`/`byId`/`treeNodes`-Triade konkret bestätigen (Nuancen §3.6) —
     nicht blind migrieren.
  4. Listen migrieren, je Cluster ein Commit. **Zusatz-Listen `IcdList`, `DiagramList`, `InterviewList`**
     aufnehmen **nur nach bestandener Vorprüfung** des exakt identischen Scaffoldings (Entscheidung 4).
  5. **`useInitialFormValues<TIn,TOut>(artifact, toValues)`** (neu) extrahieren.
  6. **`EditorPageShell.tsx`** (neu): komponiert das **vorhandene** `useSaveShortcut` (259 LOC),
     Dirty-Wrapper, Workflow-Status, `ConfirmDialog`.
  7. Die 7 Wrapper + die Direkt-Renderstelle `RequirementEditors.tsx:550` auf `useInitialFormValues`
     + `EditorPageShell` migrieren.
- **Regressionsnetz (zentral in `src/test/`, nicht co-located):** `ArtifactForm.test.tsx` (1660 LOC),
  `ArtifactFormFields.test.tsx`, `ArtifactFormWidgets.test.tsx`, `ArtifactFormCreateForm.test.tsx`,
  `ArtifactFormSaveShortcut.test.tsx`, `hooks/useSaveShortcut.test.ts`, `AdrEditors.save-shortcut.test.tsx`.
- **Risiko/Mitigation:** mittel-hoch (ArtifactForm-Blast 14, 8 Renderstellen). Extern sichtbare
  Props-/Hook-APIs unverändert; ein Commit je Extraktion; nach jedem Commit `npx vitest run ArtifactForm`
  + betroffene Listen-Tests.
- **Akzeptanz:** die vier neuen Bausteine existieren und sind getestet; `npx vitest run` (inkl.
  ArtifactForm-Suite) grün; `ui-ratchet.test.ts` unverändert; kein Wrapper erzeugt eigenes
  Save-Shortcut-Handling.
- **Commit:** `refactor(frontend): shared useArtifactList + usePersistedListFilter for editor lists (F-13)` ·
  `refactor(frontend): extract EditorPageShell + useInitialFormValues (F-14, F-15)`

---

## Phase 4 — Type-Barrel-Split (206 Consumer; bestätigt durchzuführen)

- **Ziel:** `types/index.ts` (1162 LOC, **206 importierende FE-Dateien**) in Domänen-Module zerlegen,
  Barrel-Importstabilität erhalten.
- **Files:**
  - Modify: `src/types/index.ts` (Barrel schrumpft auf ≤ ~50 LOC)
  - Create: `src/types/{auth,workspace,requirement,architecture,testing,traceability,diff,graph,glossary,metrics,common}.ts`
- **Evidenz:** §3.1 (206 Importeure → hohes Diff-Churn-Risiko; läuft daher spät).
- **Schritte (Entscheidung 3):**
  1. Domänen-Gruppen aus Barrel-Exporten ableiten.
  2. **Je Domäne ein Commit:** Definitionen **unverändert** verschieben; Barrel behält
     `export * from "./<domain>"`.
  3. Nach **jedem** Domänen-Commit: `npx tsc --noEmit -p tsconfig.build.json`.
  4. Keine Umbenennungen (kein API-Change).
- **Risiko/Mitigation:** hoch (206 Consumer). Rein mechanische Verschiebung; ein Commit je Domäne →
  einzeln revertierbar; tsc nach jedem Commit.
- **Akzeptanz:** `tsc --noEmit` + `npx vitest run` grün nach **jedem** Domänen-Commit; Barrel ≤ ~50 LOC;
  keine umbenannten Symbole.
- **Commit:** `refactor(frontend): split types barrel by domain (F-16)`

---

## Phase 5 — God-Components (höchstes Risiko, zuletzt)

- **Ziel:** `WorkspaceContext`, `ArtifactForm` und `WorkspaceTree` hinter **unveränderter Außen-API**
  in Orchestrierung + Extraktionen trennen.

| Komponente | LOC | Consumer | Extraktionsziele |
|---|---:|---:|---|
| `context/WorkspaceContext.tsx` | 588 (558 nicht-leer) | **104** | `useWorkspaceLanguage`, `useWorkspacePreferences` |
| `shared/ArtifactForm/ArtifactForm.tsx` | 1359 | 14 (8 Renderstellen) | `useArtifactFormState`, Section-Renderer (via `layout-flow.ts`), RMZ-Matrix + Status-Editor |
| `shared/WorkspaceTree/workspace-tree.tsx` | 1370 | 3 (extern) | `tree-drag`, `tree-virtualization`, `tree-display-fields` |

- **Files:**
  - Modify: `context/WorkspaceContext.tsx`; `shared/ArtifactForm/ArtifactForm.tsx`;
    `shared/WorkspaceTree/workspace-tree.tsx`
  - Create: `hooks/useWorkspaceLanguage.ts`, `hooks/useWorkspacePreferences.ts`,
    `shared/ArtifactForm/useArtifactFormState.ts`, `shared/WorkspaceTree/tree-drag.ts`,
    `shared/WorkspaceTree/tree-virtualization.tsx`, `shared/WorkspaceTree/tree-display-fields.ts`
- **Schritte:**
  1. **5a WorkspaceContext (104 Consumer):** Ref-Twins `userOverridesRef`/`hideAllOptionalRef`/
     `overriddenKeysRef` (L195-197) → abgeleitete `useMemo(userOverrides + preset)` **nur dann**, wenn
     die 104 Consumer **keinen** Ref-Zugriff benötigen. `overriddenKeys` aus `userOverrides +
     activeWorkspace.preset` ableiten. Provider komponiert Hooks; **public Context-API 1:1 halten**.
  2. **5b ArtifactForm (1359 LOC, 14 Consumer):** `useArtifactFormState` herausziehen; Section-Rendering
     über das **vorhandene** `layout-flow.ts`; RMZ-Matrix + Status-Editor als eigene Komponenten;
     Ziel: Thin-Orchestrator (~200-300 LOC); Props-API der 8 Renderstellen unverändert;
     `ArtifactForm.tsx:513/539` **unverändert** lassen.
  3. **5c WorkspaceTree (1370 LOC, 3 externe Consumer):** `tree-drag` (D&D-Reparenting, opt-in
     `onReparent`), `tree-virtualization`, `tree-display-fields` herausziehen; Typ-Badge als
     `Record<WorkspaceTreeNodeType,string>` statt `Record<string,string>`. **Zusammen mit Phase 6
     (Keyboard-Reparenting) schneiden** — das ändert dieses Modul ohnehin.
  4. Je Extraktion **ein** Commit; nach jedem `npx vitest run` + Tree-Tests
     (`workspace-tree.test.tsx`, `*.virtualize.test.tsx`). Bei Rot sofort revertieren.
- **Regressionsnetz:** Charakterisierungs-Test des Context-Values und des Tree-Verhaltens **vor** dem
  Refactor (kein Unit-Test für den Context gefunden); danach Manual-Smoke/Playwright.
- **Risiko/Mitigation:** sehr hoch (104 / 14 / interne 1370-LOC-Oberfläche). Unveränderte Props-/Context-
  API; ein Commit je Extraktion.
- **Akzeptanz:** Context-Value und ArtifactForm-Props identisch (Charakterisierungs-Test grün);
  `npx vitest run` + Tree-Tests grün nach jeder Extraktion; keine Änderung der extern sichtbaren API.
- **Commit:** `refactor(frontend): decompose WorkspaceContext into focused hooks (FE-01, F-03)` ·
  `refactor(frontend): extract ArtifactForm state + section renderers (FE-01, F-01)` ·
  `refactor(frontend): extract WorkspaceTree drag/virtualization modules (FE-01)`

---

## Phase 6 — Accessibility (WCAG 2.1/2.2 AA) — verifizierter Rest

- **Ziel:** Den verifizierten A11y-Rest schließen (0 CRITICAL, 2 HIGH, 4 MEDIUM, 3 LOW).
- **Files:**
  - Modify: `components/NavigationShell/NavigationShell.tsx`, `components/shared/WorkspaceTree/workspace-tree.tsx`,
    `components/shared/ArtifactForm/ArtifactForm.tsx`, `components/NavigationShell/SidebarNavigation.tsx`,
    `components/Audit/audit-dashboard.tsx`, `components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx`,
    `components/DashboardViews/WorkspaceCard.tsx`
  - Create: `src/hooks/useMediaQuery.ts` (fehlt)
  - Modify: `frontend/package.json` / `e2e/package.json` (`@axe-core/playwright`, Entscheidung 2)
- **Evidenz:** §1.6, §3.8.
- **Schritte:**
  1. **Skip-Link (M-3, SC 2.4.1):** erstes tabbares Element im Shell vor der Navigation; zielt auf
     `<main id="main-content" tabIndex={-1}>`; Fokus-Move bei Aktivierung.
  2. **Keyboard-Reparenting WorkspaceTree (H-1, SC 2.1.1/2.5.7):** sichtbarer „Move…"-Button/Shortcut
     mit `aria-haspopup="dialog"`; Ergebnis-Ankündigung via bestehendem `role="status"`/`aria-live`;
     D&D bleibt Shortcut. **Mit Phase 5c bündeln.**
  3. **ArtifactForm-Sections (H-2, SC 1.3.1/2.4.6):** `aria-labelledby={sectionToggleId}` am `<section>`;
     Toggle mit `id` + `aria-controls`; Header als echtes Heading, wo Dichte erlaubt.
  4. **Sidebar-Drawer (M-1) — Entscheidung 1:** modaler Mobile-Drawer: `role="dialog"` +
     `aria-modal="true"`, Focus-Trap über vorhandenes `shared/Dialog/use-focus-trap.ts`, Initial-Focus,
     Focus-Return auf den Burger; Overlay keyboard-erreichbar. **Desktop-Rail non-modal** belassen.
     Neuen `useMediaQuery`-Hook ergänzen (mit eigenem Test, ohne Verhaltensänderung außerhalb des Drawers).
  5. **RuleInfoPopover (M-2, SC 4.1.2):** korrekte Non-Modal-Tooltip-Semantik (`role="tooltip"`/
     `aria-describedby` + Escape) **oder** Wechsel auf Shared `<Dialog>`.
  6. **CreateTraceLinkDialog (M-4, SC 4.1.2):** verbleibendes `aria-pressed`/`aria-selected` auf Typ-/
     Element-Buttons ergänzen; Loading/Empty in `role="status"`/`aria-live` (Listbox-`aria-selected`
     L468 vorhanden).
  7. **WorkspaceCard (L-2, SC 4.1.2):** echtes `<button>` **oder** `aria-labelledby` auf den Titel;
     `data-testid=workspace-card-clickable-region` unverändert.
  8. **`@axe-core/playwright` (Entscheidung 2):** als Dev-Dependency einführen und einen Smoke-Test an
     Navigation/Dialog/ArtifactForm hängen — automatisiertes A11y-Gate für Phase 6 und 8.
- **Risiko/Mitigation:** mittel. Focus-Trap im Shell-Chrome kann Keyboard-Tests brechen →
  `dialog-consistency-ratchet.test.ts` + `dialog-focus-owner.test.ts` als Gate.
- **Akzeptanz:** Skip-Link vorhanden/erstes tabbares Element; `<main id="main-content">`; Drawer mit
  `role="dialog"`/`aria-modal="true"` + Focus-Trap + Focus-Return; Escape und Backdrop keyboard-erreichbar;
  `dialog-consistency-ratchet` + `dialog-focus-owner.test.ts` grün; keine neue jsx-a11y-Lint-Warnung;
  axe-Smoke-Test grün.
- **Commit:** `fix(a11y): add skip link and main-content landmark (M-3)` ·
  `fix(a11y): keyboard-accessible tree reparenting (H-1)` ·
  `fix(a11y): make mobile sidebar drawer a modal dialog (M-1)` ·
  `fix(a11y): name artifact form sections (H-2)` ·
  `fix(a11y): correct rule-popover and trace-link-dialog semantics (M-2, M-4)` ·
  `test(a11y): add @axe-core/playwright automated gate`

---

## Phase 7 — Design-System-Ratchet-Abbau (278 / 26 / 3)

- **Ziel:** Die drei gefrorenen Ratchet-Ceilings durch echte Fixes **inkrementell senken** —
  Ceilings werden nie erhöht (§3.9).
- **Files:**
  - Modify (batchweise): Komponenten aus den `known`-Listen (z. B. `AttributeEditor/*`,
    `Audit/audit-dashboard.tsx`, `CsvImport/CsvImport.tsx`, `Memory/*`, `SystemSettings/*`,
    `WorkflowEditor/*`, `shared/Dialog/Dialog.tsx`, `shared/EmptyState/*`)
  - Modify (nur am Ende): `src/test/design-system-ratchet.baseline.json`
- **Schritte:**
  1. **`button-missing-design-system-class` (278):** batchweise pro Verzeichnis Controls auf die
     passende `btn-*`-Klasse migrieren und ad-hoc-Fills entfernen. Nach jedem Batch
     `DESIGN_SYSTEM_REBASELINE=1 npx vitest run src/test/design-system-ratchet.test.ts` →
     `maxViolations` **auf den neuen, kleineren Ist-Wert senken** (nie erhöhen).
  2. **`emoji-as-ui-glyph` (26):** Emoji-Glyphen durch monochrome `currentColor`-Icons ersetzen
     (z. B. `SidebarNavigation` ✓/✕, `RightSidebar` 📌/🔗, `TraceabilityView`/`MismatchReviewTable` ⚠/✓).
  3. **`ambiguous-button-label` (3):** `attribute-editor-export`/`attribute-editor-import` und
     `workflow-export-button` über qualifizierte i18n-Keys (`actions.export`/`actions.import`) in
     **beiden** Locales benennen.
  4. Exemptions (27) unverändert lassen; keine neue Exemption ohne Begründung. Ceilings erst im
     abschließenden Re-Baseline-Lauf senken.
- **Risiko/Mitigation:** niedrig (isolierte Einzelstellen). Hauptrisiko ist eine versehentliche
  Erhöhung — der Monotonie-Guard blockt, dennoch vermeiden. Ein Batch = ein Commit; Staleness-Tests
  erzwingen, dass gefixte Einträge tatsächlich entfernt/rebaselined werden.
- **Akzeptanz:** `design-system-ratchet.test.ts` grün; jeder Batch senkt exakt die betroffenen
  Ceilings; **kein** Ceiling erhöht; Exemption-Zahl bleibt 27 (oder sinkt mit Begründung); nach
  Phase 7 liegen alle drei Ceilings < Ausgangswert (278/26/3).
- **Commit:** `refactor(ui): migrate <area> buttons to design-system chrome (#954, #797, #1091)` ·
  `refactor(ui): replace emoji UI glyphs with monochrome icons (#1092)` ·
  `fix(ui): qualify ambiguous export/import button labels (#1093)`

---

## Phase 8 — Final-Verifikation & DoD

- **Ziel:** Gesamtabnahme gegen die Baseline aus Phase 0 und die Definition of Done.
- **Files:** Keine neuen Produktionsdateien; referenziert `src/test/design-system-ratchet.baseline.json`
  (Re-Baseline, nur gesenkt) und die Baseline-Dokumentation aus Phase 0.
- **Schritte:**
  1. `cd frontend && npm run lint` — 0 errors; Warntrend ≤ 298.
  2. `npm run build` (tsc + vite) — grün.
  3. `npx vitest run` — vollständig grün (inkl. aller vier Ratchets).
  4. `npx playwright test` (E2E-Shards: Navigation/Dialog/ArtifactForm/WorkspaceTree).
  5. **`@axe-core/playwright`-Gate** (Entscheidung 2) — A11y-Smoke grün.
  6. Ratchet-Endstand: die drei Ceilings < 278/26/3; `design-system-ratchet.baseline.json` neu
     committet (nur gesenkt).
  7. Baseline aus Phase 0 gegen Endstand stellen; Delta dokumentieren.
  8. PR gegen `main` mit Referenz auf die eingearbeitete Audit-Befundlage (§1) und diesen Plan;
     DoD-/Traceability-Audit durch `validator`.
- **Risiko/Mitigation:** niedrig. Einzige Falle: Abnahme gegen eine Baseline mit bekannten Alt-Fails
  (Audit lief ohne Test-Lauf) → strikte Delta-Betrachtung Baseline vs. Endstand; nur **neue** Fails
  blockieren.
- **Akzeptanz (DoD):** Lint 0 errors, Build grün, alle Vitest-Suites grün, E2E-Shards grün, axe-Gate grün;
  kein Ratchet-Ceiling erhöht, alle drei gesenkt; Conventional Commits eingehalten; PR referenziert
  Audit + Plan; Feature-Branch `fix/audit-frontend-findings` — kein Direkt-Commit auf `main`.
- **Commit:** `chore(frontend): finalize audit-fix verification`

---

## Verifikationsmatrix

| Phase | Primär-Verifikation | Ergänzend |
|---|---|---|
| 0 | `lint`/`tsc`/`vitest`-Baseline | drei Ratchet-Ceilings dokumentiert |
| 1 Timer/Memos | Timer-Clear je Site; `vitest run` | Unmount-Smoke; lint unverändert |
| 2 Storage | `usePersistedListState.test.ts`, `RequirementList.filterPersistence.test.tsx` | Workspace-/SplitView-Tests; `rg`-Gate |
| 3 Reuse | `ArtifactForm*.test.tsx`, `useSaveShortcut.test.ts` | `ui-ratchet.test.ts` unverändert |
| 4 Types | `tsc --noEmit` nach jedem Domänen-Commit | Consumer-grep (`import … from "../types"`) |
| 5 God-Comps | Charakterisierungs-Test Context + Tree | `workspace-tree.test.tsx`, `*.virtualize.test.tsx` |
| 6 A11y | `dialog-consistency-ratchet` + `dialog-focus-owner.test.ts` | axe-Smoke, Playwright |
| 7 Ratchet | `design-system-ratchet.test.ts` sinkt (nie steigt) | visuelle Sichtprüfung |
| 8 Final | `lint` + `build` + `vitest` + `playwright` + axe | Baseline vs. Endstand |

---

## Rollback

- **Granularität:** ein Commit pro Phase/Batch → jede Phase einzeln per `git revert <sha>` rückbaubar.
- **Refactors** laufen durchgehend hinter **unveränderten** Props-/Hook-/Context-APIs → kein extern
  sichtbarer API-Bruch; bei Rot in Tests sofort revertieren statt nachbessern.
- **Ratchet-Baseline:** da Ceilings nur gesenkt werden, ist ein Revert des Baseline-Commits zusammen
  mit dem Fix möglich; ein isolierter Baseline-Commit ohne den zugehörigen Fix ist zu vermeiden.
- **Kein** Force-Push, kein `main`-Commit (Branch-Guard).

---

## Tooling-Lücken

- **Automatisiertes A11y-Testing** wird gemäß Entscheidung 2 nachgerüstet: `@axe-core/playwright`
  als Dev-Dependency in `frontend/` bzw. `e2e/`, verankert in Phase 6 und 8. Vorher: **kein
  automatisiertes axe-Gate** — axe-core existiert nur manuell (`e2e/a11y-followup.js`, nicht in
  `playwright test`); ergänzend `eslint-plugin-jsx-a11y`-Lint + `@playwright/test`.
- **Ad-hoc-Graph-Abfragen** (`graphify query`) sind heuristisch/trunkierend und liefern für Fan-in
  keine exakten Zahlen; die Blast-Radius-Werte stammen aus dem exakten Rückwärts-Kantenscan über
  `graphify-out/graph.json` (Basis-HEAD `b6159d6b`).
- **Kein Test-Lauf im Audit:** alle Test-/Lint-Baselines entstehen erst in Phase 0 — bis dahin ist
  jeder Zustand „unverifiziert grün".

---

## Anhang — Evidenz & Quellen (eingearbeitet)

- **System-Audit:** Domänen-Scores und Cross-cutting-Blocker in §1.1/§1.2; Verifikations-Baseline
  (Lint/tsc/kein Testlauf) §1.1.
- **Frontend-Fach-Audit (16 Findings, 57):** §1.3 (FE-01…FE-07, F-01…F-16, Deduktionen).
- **UI-Audit (68):** §1.4 (UI-01…UI-07, Living-Baseline-Ratchets).
- **Code-Qualitäts-Audit (C+ 7.0/10):** §1.5 (Top-LOC-Dateien, 8 Blocker).
- **Accessibility-Audit (78/100):** §1.6 (H-1/H-2, M-1…M-4, L-1…L-3, Positives).
- **Code-Evidenz-Inventar:** §2 (Korrektur-Status), §3.2 (Timer), §3.3 (Memos), §3.4/§3.5 (Storage),
  §3.6 (Listen-Scaffolding), §3.7 (Form-Wrapper/Save-Shortcut).
- **A11y-/graphify-Evidenz:** §3.1 (Blast-Radius, LOC), §3.8 (Skip-Link, Drawer, Tree-D&D, Focus-Trap,
  `useMediaQuery` fehlt), §3.9 (Ratchet-Baseline, Monotonie-Guard).
- **Ratchet:** `frontend/src/test/design-system-ratchet.baseline.json` (278/26/3, 27 Exemptions),
  `design-system-ratchet.test.ts`, `ratchet-framework.ts` (Spiegel von
  `backend/mcp_server/tests/ratchet_framework.py`, #1103 / REQ-193).
- **Abhängigkeitsgraph:** Rückwärts-Importkanten über `graphify-out/graph.json`, Stand Basis-HEAD
  `b6159d6b` — Grundlage der Blast-Radius-Matrix.
- **Aufwandsabschätzung:** über die Rolle `effort-estimator` einzuholen (hier keine eigene
  Zahlenberechnung) — Referenz nur textlich, nicht als Tool-Call.

---

*Erstellt am 2026-10-15 als eigenständiger, repo-konformer Umsetzungsplan zu den
Frontend-Audit-Fixes. Kein Produktcode, keine Migration, kein Commit. Umsetzung erst nach
Freigabe durch User/Orchestrator; Branch `fix/audit-frontend-findings`, kein `main`-Commit.*
