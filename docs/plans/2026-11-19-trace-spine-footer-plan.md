---
type: PLAN
title: "TraceSpine-Footer & Baumbreite — Analyse + Umsetzungsplan (Revision 2)"
status: proposed
date: 2026-11-19
author_agent: planner
language: de
branch_basis: "origin/main 37e3ee40 (Worktree .tmp/wt-plan, nach S3.4-Merge)"
review_iteration: 2
review_state: open
---

# TraceSpine-Footer & Baumbreite — Analyse + Umsetzungsplan (Revision 2)

**Goal:** Die Ableitungskette (`● Need → ○ Req → ◍ Arch → ○ TC`) aus der vertikalen Schiene in einen systematischen **horizontalen Footer über die volle Inhaltsbreite** (außer Systemmenü/Navigation) überführen; Baumbreite pro Modul user-adjustable mit gespeichertem Drag; `/traceability`-Impact-Spalte als On-Demand-Drawer.

**Architecture:** React-19-SPA, `<SplitView>` mit dediziertem `spine`-Slot, `<TraceSpineFooter>` besitzt `useDerivationChain` (RPC nur bei Footer an), User-Präferenzen via Q1-Registry (`user > global > registry`) bzw. gerätelokaler Layout-Key. Vier Schnitte, je Gate → Review → CI → Merge. Kein Eingriff in Django-Domain-Layer.

**Tech Stack:** TypeScript 5.5+ / React 19 / CSS Modules + `tokens.css`, Vitest 4, Playwright (4 Shards), Django 6.1+ / DRF, Q1-Settings-Registry, i18n DE/EN.

**Spec:** `docs/UI_KONZEPT.md` (Kap. 5, 6, 12.10) — maßgeblich. Abhängigkeit (kein Scope): `docs/superpowers/specs/2026-11-10-inspector-redesign-design.md` / Implementierung M8.

> **Hinweis zu `pipeline_stages` (Review-Fundament):** Dieser Plan wird vom `orchestrator` als 4-Schnitt-Plan dispatched (je Gate → Review → CI → Merge), **nicht** von einer `plan-driven`-Pipeline. Deshalb bewusst **kein** `pipeline_stages`-Frontmatter — ein gesetztes Feld ohne passende `### Task N`-Zuordnung würde zur Laufzeit in den `fallback_agent` fallen und die Stage-Zuordnung verlieren. Die Tasks unten sind dennoch als `### Task N` gegliedert und einzeln dispatchbar.

## 0. Verständniskorrektur (beibehalten, geschärft)

Die erste Analyse lief falsch: „verknüpfte Artefakte" wurde als CRUD-Tabelle (`TraceLinkPanel` / `ReqTraceLinkPanel` mit Incoming/Outgoing, Anlegen/Löschen) interpretiert. Gemeint ist die **Trace-Artefakt-Verfolgungs-Pfeil-Funktion**, die `<TraceSpine>`: die vom Graphen abgeleitete Kette mit Glyphen (● ○ ◍), Richtungspfeilen, Verifikations-Badges und Sprungzahlen.

**Ziel:** Diese Kette systematisch **horizontal in einer Fußzeile** darstellen, statt als schmale vertikale Schiene. Ausklappen erst ab 5 Stationen; die aktive Station bleibt beim Einklappen immer sichtbar.

Die CRUD-Tabelle bleibt wo sie ist — eigenes Finding, **nicht** Teil dieses Schnitts (siehe §7).

## 1. Verifizierte Ist-Analyse (Korrekturen der abgelehnten Fassung eingearbeitet)

| Thema | Verifizierter Stand (Head 37e3ee40) | Konsequenz für den Plan |
|---|---|---|
| Spine-Slot | `SplitView.tsx:20-25,48-50,174-199`: `<SplitView>` hat **nur noch den Concept-Vertrag** `list/detail/spine/ratio/minWidths`. `spine` ist ein eigener, unabhängig scrollbarer Slot mit `data-testid="splitview-spine"`, **nicht** in `detailScroll`. Legacy-Vertrag + Drag-Persistence wurden in **S3.2 / UI-001** entfernt; Kommentar: „Drag-persistence is intentionally gone — the concept uses a fixed ratio". `reqflow_splitview_*` hat **null** Code-Treffer (nur Docs). **Kein** `initialLeftWidth`. | Footer wird als **Geschwister des SplitView** gemountet, nicht in die Schiene gezwängt. Schnitt 3 ist eine **Neue Funktion**, die die UI-001-Entscheidung explizit zurückdreht (ADR/Critic-Gate, s. Task 7). |
| Mounts | **Exakt 8 echte JSX-Mounts**: `NeedsEditors.tsx:528`, `RiskEditors.tsx:292`, `RequirementEditors.tsx:789`, `ArchitectureEditors.tsx:828`, `AdrEditors.tsx:365`, `IssueEditors.tsx:294`, `TestCaseEditors.tsx:457`, `Goals/GoalsPage.tsx:513`. Der „9." ist ein Doc-Kommentar in `SplitView.tsx:9`. **`GoalDetail:127` existiert nicht.** | Migration betrifft 8 Hosts, nicht 9. `GoalDetail.tsx` ist **kein** Host. |
| Horizontal-Variante | Bereits vorhanden: `TraceSpine.module.css:220-251` (`@media max-width: --bp-lg`), `SplitView.tsx` `spineIsHorizontal` / `NARROW_RATIO` (:136-137,174-205), `tokens.css:918-935` (`--bp-lg` für **Spine und Inspector R4**) + `breakpoint-token-gate.test.ts`. **Drei** Mechanismen greifen ineinander. | Schnitt 2c räumt alle drei auf; `--bp-lg` bleibt nur für den Inspector. |
| `hideTraceLinks` | **Null** Code-Treffer — durch Inspector-Redesign **M8** entfernt (`docs/superpowers/plans/2026-11-12-inspector-redesign-implementation.md:517,553`). Sein Zweck war genau die Unterdrückung doppelter Link-Views. Heute besitzt `InspectorShell` die Trace-Leseansicht, `TracePanel` hat „Show in spine". `focusSpine`/`onShowInSpine` existieren in 6+ Hosts (NeedsEditors:277,520; RequirementEditors:337,672; IssueEditors:148,286; GoalsPage:197,463), inkl. Skip-Link/Fokus-Regeln (z. B. `RiskEditors.module.css:57-80`). | „Beide an = beide zeigen Links" ist **Status quo**, kein neues Risiko. D2b wird explizit als erwartetes Verhalten getestet, nicht „repariert". |
| Station-Panel | `TraceSpine.tsx:81-83,268-316` öffnet bei Stations-Klick ein `<aside class="panel">` mit scrollbarer Linkliste; `.panel{flex:1 1 auto}` setzt Side-by-Side-Layout voraus. Ein 64–96 px Footer hat dafür keinen Platz. | Panel wird **Popover über der Station** (s. §3.4), nicht Side-by-Side. `isOpenable` bleibt erhalten. |
| `isOpenable` | `useDerivationChain.ts:54-61`: `false` für **drei** Fälle (`resolved:false`, Resolve in Flight, Resolve fehlgeschlagen). `:94-107`: die aktive Station wird **immer** geliefert. | Drei Fälle bleiben deaktiviert (keine toten Links); aktive Station ist auch bei 1-Element-Kette vorhanden → „Artefakt ohne Kette" ist die 1-Station-Variante. |
| Empty State | Hosts mounten `<TraceSpine>` nur bei Auswahl (z. B. `NeedsEditors:526-536`). | „Keine Auswahl" = Footer fehlt, **kein reservierter Platz**. „Artefakt ohne Kette" = einzeiliger Platzhalter. Zweigetrennte Tests. |
| Preferences | `display_preference_service.py:56`: **Flate Allowlist** `("show_readable_ids","visible_metrics")`. Punktierte Keys laufen über Q1-Registry (`:59` `ui.ids.show_readable`; `resolve_for(tenant_id, workspace_id=None, user_id, key)` :114-120 = user > global > registry). Serializer-Declared-Fields spiegeln die Allowlist; das `openapi_contract_snapshot.json` pinnt **keine** Felder (nur Operationen/Schema-Namen/securitySchemes) und bleibt deshalb unverändert — neuer Fail-First-Test ist der Serializer/View-Test. `grep display_preference backend/mcp_server` → **keine Treffer**. | Zwei neue User-Toggles via **Q1-Registry** (`ui.trace_footer.enabled`, `ui.inspector.enabled`), konsistent zu `show_readable_ids`. **MCP-Tool bewusst nicht ergänzt** (s. §7) — Drift-Gate `test_tool_manifest_drift.py` bleibt unberührt. |
| `/traceability` | `TraceabilityView.tsx:919-939` nutzt `window.location.assign("/impact")`; `ImpactDetailPanel` sitzt im `detailPanel`-Slot (`~:772,1074`). Ein Drawer ist **kein** Rebuild, aber auch nicht trivial. | Task 10 spezifiziert Drawer mit ESC/Fokus-Rückgabe/`aria-modal`, ersetzt die Navigation, kein `|| true`. |
| Settings-Ort | „Appearance" ist ein **Tab in WorkspaceSettings** (`WorkspaceSettings.test.tsx:255`), D1 fordert aber **User**-Setting; vorhandener Display-Toggle liegt in `UserProfileSettings/IdentifiersSection.tsx`. | **Auflösung:** Die beiden Switches kommen in **UserProfileSettings** (neue Sektion „Darstellung"), **nicht** in den WorkspaceSettings-Appearance-Tab. Workspace-Level bleibt außen vor (Q1 `workspace_id=None`). |
| Ratchets / Snapshots | `ui-ratchet.test.ts`, `design-system-ratchet.test.ts` + `.baseline.json`, `dialog-consistency-ratchet.test.ts` zählen Inline-Styles/Raw-Colors; ~14 Visual-Baselines betroffener Views. | „Ratchet unverändert" ist bei neuen Komponenten **nicht glaubwürdig** — §5/§6 benennen konkrete erlaubte Deltas, nie Anhebung bestehender Baselines. Snapshot-Churn bekommt Owner (Task 11). |
| Mobile | Footer in Bottom-Sheet + `InspectorShell` bereits Sheet/Overlay (`RiskEditors.module.css:51`) → **zwei** überlagernde Sheets. | §3.5 definiert z-index/Back-Button/Fokus-Konflikt-Auflösung. |

### 1.1 Visuelle Belege (Ausgangslage)

14 Snapshots (1280×720) aus `e2e/tests/visual-regression.spec.ts-snapshots/`: Needs/ADRs/Risks/Goals (Nav 220 px, Baum 377 px, Detail 679 px), Requirements/Architecture/ICDs (Baum 535 px, Detail 520 px), `/traceability` (dauerhaft leere Impact-Spalte ~40 %). Dialoge folgen Header (fix) / Body (scroll) / Footer (fix) — der neue Spine-Footer wird zweite Leiste direkt über dem Aktions-Footer.

## 2. User-Entscheidungen (beibehalten + Präzisierungen)

| # | Entscheidung | Präzisierung / Review-Auflösung |
|---|---|---|
| D1 | Footer-Schalter ist **User-Setting** | Q1-Key, `workspace_id=None`; UI in **UserProfileSettings**, nicht WorkspaceSettings (s. §1). |
| D2 | **Zwei unabhängige Schalter**: Footer ein/aus **und** Inspector ein/aus | Zwei getrennte Q1-Keys, zwei getrennte Hooks, zwei Switches. Kein Schalter beeinflusst den anderen. |
| D2b | Bei **beiden an**: beide zeigen Links | Status quo (M8), **keine** neue Unterdrückungslogik; als erwartetes Verhalten testen. |
| D3 | Baumbreite **pro Modul**, Default + Drag gespeichert | **Kein** Reaktivieren des gelöschten Legacy-Kontrakts. Neue Fähigkeit, die UI-001 explizit zurückdreht → ADR + Critic-Gate (Task 7). Persistenz: **neuer** gerätelokaler Key `reqflow.splitview.treeWidth.v2.<moduleType>` (nicht `reqflow_splitview_*` lesen), Default optimal je Modul. `ratio`/`minWidths`-Semantik ändern sich (s. §3.6). |
| D5 | `/traceability` Impact-Spalte: **On-Demand-Drawer** | Im selben Schnitt (Task 10), nicht als Follow-up. |
| D7 | Nur die **Pfeil-Kette** in den Footer — Version/History/Properties bleiben im Inspector | Kein Umzug dieser Panels; kein Eingriff in `InspectorShell`-Inhalte. |
| D8 | **Ab 5 Stationen** ausklappen; aktive Station immer sichtbar | ≤4 = eine Zeile; ≥5 = eingeklappt mit `[+N weitere]`; aktive Station reserviert sich einen Slot (s. §3.3). |

## 3. Zielbild — Wireframes & Zustandsmatrix

### 3.1 Footer — Vollseiten-Editor (Hauptfall, Desktop)

```
┌──────────┬──────────────┬──────────────────────────────────┐
│ NAV 220  │ Baum         │ Artefaktkopf (sticky)            │
│          │ (scrollt)    ├──────────────────────────────────┤
│ ReqLo    │ ▾ L1 System  │ Formular (scrollt)               │
│ …        │  ▸ L2 …      │  Identification …                │
│ System   │  ▸ L2 …      │  Content …                       │
│ Req      │              │                                  │
│          ├──────────────┴──────────────────────────────────┤
│          │ ● Need ─ ○ Req ─ ◍ Arch ─ ○ TC   [+2]      [▲] │ ← TRACE-FOOTER
│          │ (horizontal, ==== Pfeile, Badges, Ausklappen)    │   ~64/96px
└──────────┴──────────────┴──────────────────────────────────┘
     Navigation endet hier ┘  Footer spannt Baum + Detail
```

Der Footer ist **Geschwister des `<SplitView>`**, nicht mehr Kind von `detailScroll` und nicht mehr im `spine`-Slot. Er spannt exakt `Inhaltsbreite − 220 px Navigation`. Der `spine`-Slot bleibt in der API erhalten (kein Breaking Change an Drittnutzern), wird aber von keinem Host mehr mit `<TraceSpine>` gefüttert → 2c prüft per grep, ob er entfernt werden kann.

### 3.2 Footer — Modal-Dialog

```
┌──────────┬─────────────────────────────────────────┐
│ NAV 220  │  New Requirement                  [×]   │ Header
│          ├─────────────────────────────────────────┤
│ ReqLo    │  Identification  title * [___________]  │
│ …        │  Content  Description …                │ Body (scroll)
│ System   ├─────────────────────────────────────────┤
│ Req      │  ● Need ─ ○ Req ─ ◍ Arch ─ ○ TC   [▲]  │ TRACE-FOOTER (56px)
│          ├─────────────────────────────────────────┤
│          │                       [Cancel] [Save]   │ Aktions-Footer
└──────────┴─────────────────────────────────────────┘
```

Im Modal ist der Inspector keine Seitenspalte; wird er dort eingeschaltet, öffnet er denselben Overlay-Drawer wie in §3.4/§4 (Task 10). Der Footer liegt im Stacking-Kontext des Modals (z-index = Modal + 1).

### 3.3 Ausklappen ab 5 Stationen — aktive Station immer sichtbar

```
≤4 Stationen:  ● Need ─ ○ Req ─ ◍ Arch ─ ○ TC
≥5 eingeklappt (aktive Station = TC, Position 4):
               ● Need ─ ○ Req ─ ◍ Arch ─ ● TC ─ [+3 weitere] [▲ expand]
≥5 eingeklappt (aktive Station = Position 6):
               ● Need ─ ○ Req ─ ◍ Arch ─ ● Goal ─ [+2 weitere] [▲ expand]
≥5 ausgeklappt:● Need ─ ○ Req ─ ◍ Arch ─ ○ TC ─ ○ Goal ─ ◍ ADR ─ ○ Risk
               (horizontaler Overflow, Order bleibt lesbar — wie heute --bp-lg)
```

Algorithmus (testbar): Länge ≤ 4 → alle Stationen. Länge ≥ 5 → erste 3 Stationen + aktive Station (falls nicht bereits darin; war sie es, 4 erste Stationen) + `[+N weitere]`. Die aktive Station trägt `aria-current="step"` und `data-active="true"`, wird beim Einklappen **nie** ausgeblendet.

### 3.4 Stations-Panel → Popover (Auflösung von `TraceSpine.tsx:268-316`)

Stations-Klick öffnet eine schwebende Karte **über** der Station (`role="dialog"`, nicht-modal, `max-height: 320px`, eigener Scroll, `data-testid="trace-station-popover"`). ESC schließt, Fokus kehrt zur auslösenden Chip zurück. Bei `isOpenable === false` (alle drei Fälle aus §1) ist die Chip `disabled` und öffnet **kein** Popover. Auf Mobil wird daraus die in §3.5 definierte Sheet-Variante. Damit entfällt die Side-by-Side-Annahme `.panel{flex:1 1 auto}` für den Footer.

### 3.5 Vier-Zustands-Wahrheitstabelle (span / höhe / z-index)

Systemmenü/Navigation (links, 220 px) ist **vom Footer ausgenommen**. Es gibt **keine** feste rechte Icon-Bar — die in frühen Snapshots sichtbaren runden Buttons sind das Chat-Widget, kein App-Rail. Toggle-Rückweg bei ausgeblendetem Panel: ausschließlich `UserProfileSettings` (D1); ein Quick-Toggle im Header ist optionaler Follow-up, nicht Teil dieses Plans.

| Footer | Inspector | Detailbreite | Footer (span / höhe / z) | Inspector (span / höhe / z) |
|---|---|---|---|---|
| an | an | −320 px | `220…W` / 64 px (96 px expand) / **10** | rechte Spalte 320 px / `H−Footer` / **5** |
| an | aus | voll | `220…W` / 64 (96) / **10** | — |
| aus | an | −320 px | **kein Element, 0 px reserviert** | 320 px / `H` / **5** |
| aus | aus | voll | — | — |

**Modal-Tab-Reihenfolge (explizit):** Formularfelder → Trace-Footer (Disclosure + Station-Chips + `[+N]`) → Aktions-Footer (`Cancel`/`Save`). Der Trace-Footer erzeugt **keine** eigene Fokus-Falle; Tab/Shift-Tab verlassen ihn in die Aktionsbuttons. Assertion in Task 11 Step 1 (Mobile-Specs, Modal-Fall): `document.activeElement` nach dem letzten Footer-Tab = `dialog-...-cancel`.

**Modal:** Footer span = Modal-Body-Breite, 56 px, z = Modal+1; Inspector = Overlay-Drawer 320 px, z = Modal+2, nur wenn eingeschaltet. **Mobil (< --bp-lg):** Footer = Bottom-Sheet 56 px (expand 50vh), z 1200; Inspector = bestehendes Sheet/Overlay, z 1300. Beide Präferenzen dürfen an sein (D2b), aber **nur ein Sheet ist gleichzeitig expandiert**: das Öffnen des einen kollabiert das andere; die **eine** Back-Taste schließt das oberste Sheet; Fokus wandert in das geöffnete Sheet, `aria-modal` nur dort; die kollabierte Footer-Leiste bleibt als Tap-Target sichtbar. Damit sind z-index-, Back-Button- und Fokus-Konflikt aufgelöst.

### 3.6 Baumbreite — pro Modul, Drag, neue Semantik

```
NARROW (optimaler Default je Modul, z. B. 350 px ADR / 424 px Requirements):
┌──────────┬──────────────┬────────────────────────────────┐
│ NAV 220  │ TREE 350     │ DETAIL ~…                      │
│          │ ▾ L1         │  ● Need ─ ○ Req ─ ◍ Arch       │
│          │  ▸ L2        │  (Footer über voller Breite)   │
└──────────┴──────────────┴┴────────────────────────────────┘
                          └ Divider: role="separator", 24px Target
```

Divider: `role="separator"`, `aria-valuenow/min/max`, `tabindex=0`; `←/→` ±16 px, `Shift` ±64 px, `Home/End` = min/max, `Enter`/Doppelklick = Modul-Default. Clamp 200 px … 70 % der Inhaltsbreite. **Semantik-Änderung (Review-Punkt):** Der Concept-Vertrag `ratio={[40,60]}` / `minWidths={[380,520]}` beschreibt derzeit ein **fixes** Verhältnis. Mit freiem Drag wird die tatsächliche linke Breite zur **autoritativen** Größe; `ratio` wird zum **Initialwert**, `minWidths` zum **Clamp**. Das ist eine bewusste Umdeutung und wird in Task 7 (ADR) festgehalten.

## 4. Global Constraints

- **Nur Planung** — dieses Dokument implementiert nichts.
- Jeder Task mappt auf **genau eine** existierende Rolle; jeder Schritt hat ein messbares Akzeptanzkriterium.
- Keine Inline-Styles, keine Raw-Colors in neuen Komponenten — alles über `tokens.css`-Custom-Properties. Neue Tokens: `--trace-footer-h`, `--trace-footer-h-expanded`, `--trace-footer-h-modal`, `--inspector-drawer-w`. **Bestehende Ratchet-Baselines werden nie angehoben**; nur die in §5 gelisteten Deltas sind erlaubt.
- Byte-identische E2E-Testids: `splitview-list`, `splitview-detail`, `splitview-back`, `splitview-spine`, `trace-spine`; neue: `trace-footer`, `trace-station-popover`, `impact-drawer`, `tree-width-separator`.
- APG-Tree-Tastatur, Skip-Links und `focusSpine`/`onShowInSpine`-Verträge bleiben unangetastet.
- i18n DE/EN für **alle** neuen Strings (`de.json`, `en.json`), keine hardcodierten Labels.
- Vier Schnitte strikt sequenziell (Gate → Review → CI → Merge); Within-Slice-Parallelität nur wo dateidisjunkt markiert.
- Kein `|| true`, kein Rebuild von `window.location.assign`, kein Eingriff in M8-Inspector-Inhalte.

## 5. File Structure (dispatchable Liste — Modify/Create + Tests)

**Slice 1 — Settings:**
- M `backend/application/display_preference_service.py` — 2 neue Q1-Keys + `resolve_for`, Allowlist/Serializer-Sync.
- M `backend/.../DisplayPreferenceUpdateSerializer` (declared fields) — 2 bool-Felder.
- M Q1-Registry-Modul — `ui.trace_footer.enabled`, `ui.inspector.enabled` (Default `true`, `workspace_id=None`).
- `openapi_contract_snapshot.json` bleibt **unverändert** (pinnt keine Felder). **(Kein** MCP-Tool, kein Manifest-Drift.)
- M `frontend/src/api/display-preferences.ts`, `frontend/src/api/index.ts` — Wrapper + Re-Exporte.
- C `frontend/src/hooks/useTraceFooterVisible.ts`, `useInspectorVisible.ts` (+ `.test.ts` je) — unabhängige Hook-Paare nach `useReadableIdsVisible`-Muster.
- M `frontend/src/components/PreferencesHydrator.tsx` (+ `.test.tsx`) — hydratisiert beide neuen Hooks.
- M `frontend/src/components/UserProfileSettings/IdentifiersSection.tsx` (+ `.test.tsx`) oder neue Sektion `AppearanceSection.tsx` — zwei Switches.
- M `frontend/src/i18n/locales/de.json`, `en.json`.

**Slice 2 — Footer:**
- C `frontend/src/components/shared/TraceSpine/TraceSpineFooter.tsx`, `TraceSpineFooter.module.css`, `TraceSpineFooter.test.tsx`.
- M `TraceSpine.tsx`, `TraceSpine.module.css`, `useDerivationChain.ts` — Stations-/Panel-API unverändert, Popover-Modus ergänzt.
- M 8 Hosts + zugehörige `.test`-Suites: `NeedsEditors`, `RiskEditors`, `RequirementEditors`, `ArchitectureEditors`, `AdrEditors`, `IssueEditors`, `TestCaseEditors`, `Goals/GoalsPage`.
- M `frontend/src/components/SplitView/SplitView.tsx`, `SplitView.module.scss`, `useSplitViewMobileState.ts`, `SplitView.test.tsx`, `SplitView.a11y.test.tsx`.
- M `frontend/src/test/breakpoint-token-gate.test.ts`, `frontend/src/styles/tokens.css`.

**Slice 3 — Baumbreite:**
- C ADR `SE/ADR/ADR-NNN_kurztitel.md` (falls SE-Kaskade aktiv, sonst `docs/plans/2026-11-19-tree-width-reversal-adr.md`) — Rückdrehung UI-001.
- C `frontend/src/hooks/useTreeWidth.ts` (+ `.test.ts`) — neuer Key, Clamp, Defaults.
- M `SplitView.tsx`, `SplitView.module.scss`, `useSplitViewMobileState.ts`, `SplitView.test.tsx`.
- M 8 Hosts (nur `treeWidth`-Prop/_default), `e2e/tests/requirement-editor.spec.ts`.

**Slice 4 — Drawer + Politur:**
- M `frontend/src/components/TraceabilityView/TraceabilityView.tsx`, `TraceabilityView.module.css`, `TraceabilityView.smoke.test.tsx`.
- C `frontend/src/components/TraceabilityView/ImpactDrawer.tsx` (+ `.test.tsx`).
- M `frontend/src/components/ImpactView/impact-preset.ts`.
- M `frontend/src/test/interactive-hit-targets.test.ts`, `ui-ratchet.test.ts`, `design-system-ratchet.baseline.json`, `dialog-consistency-ratchet.test.ts` (nur gelistete Deltas).
- M `e2e/helpers/mobile.ts`, `e2e/tests/mobile-smoke.spec.ts`, `mobile-list-detail.spec.ts`, `visual-regression.spec.ts` + ~14 Snapshots (Owner: `e2e-tester`).
- M `docs/UI_KONZEPT.md` (+ `docs/plans/index.md` bleibt unverändert — Dateiname identisch, Index-Freshness bleibt grün).

## 6. Umsetzungsplan — 4 Schnitte, je Gate → Review → CI → Merge

### Task 1 (Schnitt 1a): Backend-Präferenz-Keys + Q1-Registry
**Agent:** `senior-developer` · **Depends on:** — · **Parallel zu:** Task 2 (dateidisjunkt)
**Files:** `display_preference_service.py`, Serializer, Q1-Registry, View-Tests
**Interfaces:** Q1 keys `ui.trace_footer.enabled` + `ui.inspector.enabled` (bool, default `true`, `levels=frozenset({PREFERENCE_SCOPE_USER})` — pure user setting, no tenant-global default). **HTTP field names (pin für Task 2): `trace_footer_enabled` / `inspector_enabled`** in both request and response serializers. Consumes Q1 `resolve_for`.
- [ ] Step 1 (fail): `backend/application/tests/test_preference_service.py` (`TestDisplayPreferenceFacadeOnQ1`, :774-805) — `resolve_for(workspace_id=None, key=<each>)` → `(True,"default")` ohne Row, `(False,"user")` nach `set_level`; `ALL_DISPLAY_PREFERENCES` enthält beide Keys; `get_display_preferences()` liefert beide `True`. `backend/rest_api/tests/test_display_preference_views.py` — GET ohne Row 200 + beide `True`; PATCH eines Feldes → 200 + Row `scope="user"`, **anderes Feld unverändert** (Unabhängigkeit); Non-Bool → 400; camelCase-Feld → 400 (`UnknownFieldRejectionMixin`); beide in einem PATCH → beide persistiert, anderer User sieht Defaults. **Registry zuerst registrieren** (`auth_tenancy/apps.py`), sonst GET 500 durch `ValidationError`. Beide Serializer (`DisplayPreferenceUpdateSerializer` :83 + `DisplayPreferenceResponseSerializer` :62) deklarieren die Felder. `openapi_contract_snapshot.json` bleibt **unverändert** (pinnt keine Felder); `backend/mcp_server` hat weiterhin **keinen dedizierten** Display-Preference-Tool-Treffer.
- [ ] Step 2: Registry-Einträge **zuerst** in `auth_tenancy/apps.py::_register_q1_preference_keys()` (`value_type="bool"`, `default=True`, `levels=frozenset({PREFERENCE_SCOPE_USER})`, `mode="override"`), dann Allowlist + Service-Resolution + **beide** Serializer ergänzen.
- [ ] Step 3 (pass): obige Assertions grün; `test_openapi_contract_snapshot.py`, `test_tool_manifest_drift.py`, `test_preference_tool_group.py`, `test_display_preference_views.py` (a)-(n) unverändert grün.
- [ ] Step 4: Commit `feat: add independent trace footer and inspector preferences` (nach Secret-Scan). **Gate-Findings F1–F6 eingearbeitet** (Key-Rename, API-Felder, Response-Serializer, Registry-Reihenfolge, User-Scope, Threat-Model-Wortlaut).
**DoD:** Messbar wie oben; kein neues Datenmodell, keine neue Tabelle; kein MCP-Tool.

### Task 2 (Schnitt 1b): Frontend-Hooks, Hydrator, Settings-UI
**Agent:** `frontend-component-engineer` · **Depends on:** — · **Parallel zu:** Task 1 (dateidisjunkt: Frontend-Hooks/Settings-UI vs. Backend-Service/Serializer)
**Files:** `api/display-preferences.ts`, `api/index.ts`, 2 neue Hooks + Tests, `PreferencesHydrator.tsx`, `UserProfileSettings/*`, i18n
**Interfaces:** Consumes die 2 Keys; Produces `useTraceFooterVisible()`, `useInspectorVisible()`.
- [ ] Step 1 (fail): Hook-Tests — zwei Hooks sind **unabhängig** (Toggle von A ändert B nicht); `display-preferences.test.ts` Roundtrip; `PreferencesHydrator.test.tsx` hydratisiert beide; Settings-Test: genau 2 `role="switch"` mit korrektem `aria-checked`, **nicht** im WorkspaceSettings-Appearance-Tab.
- [ ] Step 2: Wrapper, Hooks, Hydrator-Erweiterung, `AppearanceSection` in UserProfileSettings, DE/EN-Strings.
- [ ] Step 3 (pass): alle obigen Tests grün; `useReadableIdsVisible.test.ts` bleibt grün (Muster nicht gebrochen).
- [ ] Step 4: Commit `feat: add user toggles for trace footer and inspector`.
**DoD:** 2 unabhängige Switches, Persistenz über Reload, i18n-Parität DE/EN.

### Task 3 (Schnitt 1-Gate): Review + CI + Merge
**Agent:** `code-reviewer` (Review), danach Merge durch Orchestrator. **DoD:** Frontend-Review grün, Backend-Review grün, CI (pytest + vitest) grün; kein Ratchet-Hit durch neue Styles.

### Task 4 (Schnitt 2a): TraceSpineFooter-Komponente + isolierte Tests
**Agent:** `frontend-component-engineer` · **Depends on:** Task 3
**Files:** `TraceSpineFooter.tsx`, `TraceSpineFooter.module.css`, `TraceSpineFooter.test.tsx`, i18n
**Interfaces:** Der Hook `useDerivationChain(artifact)` zieht **in die Footer-Komponente** (nicht mehr in die 8 Hosts) — damit feuern `impact()`/`resolve` nur bei gemountetem Footer. Produces `data-testid="trace-footer"`, `trace-station-popover`. Hosts übergeben nur `artifact` + `onOpenArtifact`/`isOpenable`-Callbacks.
- [ ] Step 1 (fail): `TraceSpineFooter.test.tsx` — (a) 4 Stationen → 4 Chips, kein `[+N]`; (b) 5 Stationen → `[+1 weitere]`; (c) 6 Stationen → `[+2 weitere]`; (d) aktive Station bei Position 4 **und** Position 6 sichtbar mit `aria-current="step"`; (e) `isOpenable=false` für `resolved:false` / in-flight / error → Chip `disabled`, kein Popover; (f) Popover ESC + Fokus-Rückgabe; (g) 1-Station-Kette → einzeiliger Platzhalter, kein „leer"-Crash; (h) keine Auswahl → Komponente nicht gemountet, kein reservierter Platz.
- [ ] Step 2: Komponente mit Chips, Pfeilen, Badges, `[+N]`, Expand, horizontalem Overflow, Popover.
- [ ] Step 3 (pass): alle 8 Assertions grün; keine Inline-Styles/Raw-Colors (`ui-ratchet.test.ts` bleibt grün).
- [ ] Step 4: Commit `feat: add horizontal TraceSpineFooter component`.
**DoD:** exakt die 8 Assertions; `TraceSpine.levels.test.tsx` / `.badge.test.tsx` bleiben grün.

### Task 5 (Schnitt 2b): Host-Migration (8 Hosts) + Slot-Entzug + Testids
**Agent:** `developer` · **Depends on:** Task 4
**Files:** 8 Hosts + `.test`-Suites, `SplitView.tsx` (nur Slot-Aufruf entfernen)
**Interfaces:** Consumes Footer-Komponente + 2 Hooks; Produces gemounteten Footer je Host.
- [ ] Step 1 (fail): Footer-Unit-Test (Hook inside) + Host-Tests — in allen 8 Suites: genau 1 `trace-footer` als **Geschwister** des SplitView, `spine`-Slot leer (`splitview-spine` nicht mehr von TraceSpine belegt); Footer aus = `trace-footer` **nicht** im DOM **und** `tracelinksApi`/`traceabilityApi` → 0 Calls (Hook wird nicht gemountet, keine RPC); Footer an + Inspector an = beide Link-Ansichten sichtbar (D2b, kein `hideTraceLinks`).
- [ ] Step 2: 8 Hosts umstellen; `spine={…}`-Prop entfernen; `focusSpine`/`onShowInSpine`-Verträge und Skip-Links unangetastet lassen.
- [ ] Step 3 (pass): 8 Suites grün; `RequirementEditors.test.tsx` „ArtifactInspector exactly once" weiterhin grün.
- [ ] Step 4: Commit `feat: migrate 8 editors to trace footer sibling`.
**DoD:** 8/8 Hosts, 0 Spine-Slot-Consumer, 0 Chain-RPC bei Footer aus.

### Task 6 (Schnitt 2c): Breakpoint-Aufräumung (drei Mechanismen)
**Agent:** `senior-developer` · **Depends on:** Task 5
**Files:** `TraceSpine.module.css`, `SplitView.tsx`, `SplitView.module.scss`, `useSplitViewMobileState.ts`, `tokens.css`, `breakpoint-token-gate.test.ts`
**Interfaces:** Consumes Ergebnis von Task 5; Produces single-source Breakpoint.
- [ ] Step 1 (fail): `breakpoint-token-gate.test.ts` — Assert: `TraceSpine.module.css` hat keine horizontale Footer-Media-Query mehr; `SplitView.tsx` hat kein `spineIsHorizontal`/`NARROW_RATIO` mehr (falls `grep spine` 0 Treffer → Slot entfernen); `--bp-lg` bleibt für **Inspector R4** erhalten.
- [ ] Step 2: Obsolete Media-Query/Narrow-Logik entfernen; `--bp-lg`-Kommentar in `tokens.css:918-935` auf Inspector reduzieren; Test anpassen (nie Baselines anheben).
- [ ] Step 3 (pass): Gate-Test + `SplitView.mobile.test.tsx` grün.
- [ ] Step 4: Commit `refactor: remove obsolete spine breakpoint logic`.
**DoD:** eine Breakpoint-Quelle für den Inspector; kein toter Spine-Code.

### Task 7 (Schnitt 2-Gate + Schnitt 3-Voraussetzung): ADR/Critic-Gate zur UI-001-Umkehr
**Agent:** `concept-reviewer` (Critic) · **Depends on:** Task 6
**Files:** ADR (s. §5), `docs/UI_KONZEPT.md` (Kap. 6.1/12.6)
**Interfaces:** Produces freigegebene Entscheidung + aktualisierte Ratio/MinWidths-Semantik.
- [ ] Step 1: ADR (MADR-Minimal: Kontext / ≥2 Alternativen inkl. rejected / Entscheidung / Konsequenzen) mit `affected_reqs` und `deciders` anlegen; Begründung: generische fixe Ratio reicht fürbaumlastige Module nicht, user-adjustable Breite ist messbar bessere Usability; rejected: globale Ratio, Automation ohne Persistenz.
- [ ] Step 2: `concept-reviewer`-Critic gegen Architekturgesetze + UI-001; Status `proposed → review → accepted` pro AGENTS.md (nur `se-architect` setzt Status — hier als Gate vermerkt, nicht selbst vollzogen).
- [ ] Step 3: `docs/UI_KONZEPT.md` Semantik: `ratio` = Initialwert, `minWidths` = Clamp, Drag autoritativ.
**DoD:** ADR existiert mit Pflichtfeldern; Critic hat kein Finding der Kategorie „unbegründete Entscheidungsumkehr"; Doku konsistent. **Ohne dieses Gate kein Task 8.**

### Task 8 (Schnitt 3a): SplitView Divider + per-Modul Width
**Agent:** `frontend-component-engineer` · **Depends on:** Task 7
**Files:** `SplitView.tsx`, `SplitView.module.scss`, `useSplitViewMobileState.ts`, `SplitView.test.tsx`, `SplitView.a11y.test.tsx`
**Interfaces:** Consumes `moduleType`, Default-Map; Produces `tree-width-separator`, `treeWidth` State.
- [ ] Step 1 (fail): `SplitView.test.tsx`/`.a11y.test.tsx` — Divider hat `role="separator"`, `aria-valuenow/min/max`, `tabindex=0`; Pfeil ±16 px, Shift ±64 px, `Home/End` = 200 px / 70 %, `Enter`/Doppelklick = Default; 24 px Trefferfläche; `prefers-reduced-motion` respektiert; APG-Tree-Tastatur + `splitview-*`-Testids unverändert.
- [ ] Step 2: Divider + `treeWidth`-State + Clamp implementieren; `ratio`/`minWidths`-Semantik gemäß ADR umdeuten.
- [ ] Step 3 (pass): alle Assertions + `SplitView.a11y.test.tsx` grün.
- [ ] Step 4: Commit `feat: add accessible per-module tree width divider`.
**DoD:** messbar wie oben; kein Eingriff in Mobile-State-Machine außer Breiten-Prop.

### Task 9 (Schnitt 3b): Persistenz-Rebuild + Defaults
**Agent:** `developer` · **Depends on:** Task 8
**Files:** `useTreeWidth.ts` (+ `.test.ts`), 8 Hosts (nur Default/Prop), `e2e/tests/requirement-editor.spec.ts`
**Interfaces:** Consumes `treeWidth`; Produces persisted Width.
- [ ] Step 1 (fail): `useTreeWidth.test.ts` — neuer Key `reqflow.splitview.treeWidth.v2.<moduleType>` wird gelesen/geschrieben; der **gelöschte** `reqflow_splitview_*` wird ignoriert (kein Stale-Import); Default je Modul (ADR 350, Requirements 424, …); Clamp 200 px…70 %; Module sind unabhängig; E2E: Drag → Reload → identische Breite.
- [ ] Step 2: Hook + Host-Wiring + Defaults.
- [ ] Step 3 (pass): Unit + E2E grün; Visual-Baselines für betroffene Views aktualisiert (Owner: `e2e-tester`, Task 11).
- [ ] Step 4: Commit `feat: persist per-module tree width with new key`.
**DoD:** Reload-Persistenz nachweisbar, 0 Treffer auf alten Key, keine Q1-/Serializer-Änderung in diesem Task (bewusst lokal).

### Task 10 (Schnitt 4a): `/traceability` Impact-On-Demand-Drawer
**Agent:** `frontend-component-engineer` · **Depends on:** Task 9
**Files:** `TraceabilityView.tsx`, `ImpactDrawer.tsx` (+ Test), `TraceabilityView.module.css`, `TraceabilityView.smoke.test.tsx`, `impact-preset.ts`
**Interfaces:** Consumes Impact-Daten aus bestehendem `detailPanel`-Pfad; Produces `impact-drawer`.
- [ ] Step 1 (fail): `ImpactDrawer.test.tsx` + Smoke — `window.location.assign("/impact")` hat **0** Treffer; Drawer öffnet nur auf Klick; ESC schließt; Fokus kehrt zum Trigger zurück; `aria-modal="true"`; Fokus-Trap; kein `|| true`; Impact-Spalte im Grid entfällt.
- [ ] Step 2: `ImpactDetailPanel` in Drawer überführen, Preset beibehalten, Grid-Breite anpassen.
- [ ] Step 3 (pass): alle Assertions + `traceability-view.spec.ts` grün.
- [ ] Step 4: Commit `feat: replace traceability impact column with on-demand drawer`.
**DoD:** messbar wie oben; kein Rebuild, kein Full-Page-Reload.

### Task 11 (Schnitt 4b): Mobile-Sheet-Konflikt + Ratchet + Visual Regression
**Agent:** `e2e-tester` · **Depends on:** Task 10
**Files:** `interactive-hit-targets.test.ts`, `ui-ratchet.test.ts`, `design-system-ratchet.baseline.json`, `dialog-consistency-ratchet.test.ts`, `e2e/helpers/mobile.ts`, `mobile-*.spec.ts`, `visual-regression.spec.ts` + ~14 Snapshots
**Interfaces:** Consumes §3.5-Zustandsmatrix; Produces grüne CI-Gates.
- [ ] Step 1 (fail): Mobile-Specs — genau 1 expandiertes Sheet; Back-Taste schließt oberstes Sheet; Fokus im geöffneten Sheet; `aria-modal` nur dort; Tap-Ziele ≥ 44 px (`interactive-hit-targets.test.ts`); 400 % Zoom; 5 Themes; axe-Sweep grün.
- [ ] Step 2: Sheet-Logik + Helpers + Testid-Stabilität; Snapshots für 8 Hosts + Modal + Mobile neu aufnehmen.
- [ ] Step 3 (pass): Ratchets grün mit **nur** den erlaubten Deltas aus §5 (neue Tokens, keine Inline-Styles, keine Raw-Colors, keine Anhebung bestehender Baselines); Snapshots haben benannten Owner (`e2e-tester`) und Churn-Umfang ist gelistet.
- [ ] Step 4: Commit `test: update mobile, ratchet and visual baselines for trace footer`.
**DoD:** alle Assertions + axe + 400 %-Zoom + 5 Themes + Snapshot-Owner benannt.

### Task 12 (Schnitt 4-Gate): Doku + Review + CI + Merge
**Agent:** `documenter` (Doku), `ui-reviewer` + `accessibility-specialist` (Review) · **Depends on:** Task 11
**Files:** `docs/UI_KONZEPT.md`, Review-Status dieses Plans
**DoD:** Doku bildet Footer + Zustandsmatrix + ADR ab; `test_doc_index_freshness.py` und `test_internal_doc_language.py` grün; UI-/A11y-Review ohne Major-Finding; CI grün; Merge durch Orchestrator.

## 7. Abgrenzung — NOT covered (explizit)

- **CRUD `TraceLinkPanel` / `ReqTraceLinkPanel`** (Incoming/Outgoing, Anlegen/Löschen, inkl. Link-Edit-Dialoge) — eigenes Finding, bleibt unangetastet.
- **Version / History / Properties** im Inspector — bleiben dort (D7); kein Umzug, kein Eingriff in `InspectorShell`-Inhalte.
- **Interview-Dialoge** — nicht Teil dieses Schnitts.
- **MCP-Tool für Display Preferences** — bewusst **nicht** ergänzt: rein interne UI-Präferenz, kein **dedizierter** Agent-/API-Konsument (Keys erscheinen über generische `preference.registry`/`preference.set`-Tools; kein Manifest-Drift, da das Gate Tools nicht Keys pinnt); `grep display_preference backend/mcp_server` = 0; `tool-manifest.json` (301 Tools) und `test_tool_manifest_drift.py` bleiben unberührt. Falls später ein Agent die Präferenz lesen muss, separater Schnitt mit Manifest-Drift-Gate.
- **Cross-Device-Sync der Baumbreite** — bewusst deferred: gerätelokaler Key (Task 9) statt Q1 (8 statische Registry-Einträge wären nötig). Revisit bei konkretem Bedarf.
- **Abhängigkeit:** Inspector-Redesign **M8** (`docs/superpowers/plans/2026-11-12-inspector-redesign-implementation.md:517,553`) hat `hideTraceLinks` entfernt. Dieser Plan setzt genau diesen Stand voraus; ein Revert von M8 würde D2b und Task 5 obsolet machen.

## 8. Threat Model (2 Zeilen, interne App)

1. **Was / schiefgehen?** Reine UI-Layout-/Anzeige-Präferenzen im Tenant-/User-Scope, keine neuen Datenfelder und keine neuen Rechte; schlimmstenfalls eine falsch gespeicherte Breite/Footer-Sichtbarkeit **für den eigenen User**.
2. **Was dagegen / Konsequenz?** Q1 `resolve_for(tenant_id, user_id, workspace_id=None)` bzw. gerätelokaler Key ohne Tenant-Daten, Clamp gegen extreme Widths, kein Zugriff auf fremde Präferenzen; Konsequenz rein kosmetisch — kein Datenleck, kein Rechte-Bypass.

## 9. Risiken (beibehalten + geschärft)

- **Doppelte Anzeige bewusst erlaubt** (D2b / M8-Status-quo) — in Task 5 als erwartetes Verhalten getestet, damit kein Reviewer es als Bug meldet.
- `isOpenable` (Artifact-ID vs. Entity-ID, 3 Kollaps-Fälle) darf durch Footer/Popover **nicht** verloren gehen — keine toten Links, keine RPC-Fehler-Kaskade; Chain-RPC nur bei Footer an (Task 5).
- Aktive Station muss bei ≥5 Stationen **immer** sichtbar sein (Task 4d) — Kernzweck des Spine laut `TraceSpine.tsx:5-6,177-190`.
- Testids byte-identisch (§4); neue Testids stabil für E2E.
- Ratchet-Deltas sind explizit und begrenzt (§5) — nie Anheben bestehender Baselines; Snapshot-Churn hat Owner.
- Mobile: zwei Sheets → eine expandiert, ein Back-Button, ein Fokus (§3.5) — sonst Accessibility-Regression.
- Drei Breakpoint-Mechanismen → eine Quelle (Task 6), sonst --bp-lg-Drift zwischen Spine und Inspector R4.

## 10. Aufwand

Gesamtaufwand wird vom **`effort-estimator`** geschätzt (Text-Referenz gemäß Rollenkonvention, kein Tool-Call, keine eigene Bezifferung in diesem Plan). Der Plan liefert die Grundlage: 4 Schnitte, 12 dispatchbare Tasks, Backend-Fundament + 8 Host-Migrationen + Drawer + E2E-/Visual-Churn. Schätzung ist vor User-Freigabe nachzuziehen.

## 11. Review-Status

- [x] **Review 1 — `planner` P-01…P-13** (Blocker P-01/P-02/P-03, Major P-04…P-12, Minor P-13) → **Plan abgelehnt**.
- [x] **Review 2 — `concept-reviewer` CR-01 (critical = P-01), MJ-02…MJ-09, MN-10…MN-12, INFO-13** → **Plan abgelehnt**.
- [x] **Revision 2 (dieses Dokument)** adressiert sämtliche Findings (Zuordnung in §12) — `review_iteration: 2`, `review_state: open`.
- [x] **Re-Review 3 (`planner` + `concept-reviewer`)** — Ursprungsfindings alle RESOLVED; neue Findings lokal behoben: **N-01** Icon-Bar (entfernt, Span `W−220`), **N-02** Snapshot-Assertion (durch Serializer/View-Test ersetzt), **N-03** Chain-RPC (`useDerivationChain` in Footer-Komponente gezogen), **N-04** Task-1/2-Abhängigkeit (parallel, dateidisjunkt), **NEW-01** Icon-Bar (identisch N-01), **MJ-08** Modal-Tab-Order explizit.
- [x] **Finaler Kurz-Re-Review 4 (`planner` + `concept-reviewer`)** — **beide APPROVE**, keine Blocker, 0 critical/major/minor. `review_iteration: 4`, `review_state: approved`. Plan ist reif zur User-Freigabe.
- [ ] **User-Freigabe** — ausstehend. Kein automatisches Triggern der `feature-lifecycle`-Pipeline; Orchestrator entscheidet über Ausführung und übergibt `plan_ref`.

**Auflösungsnachweis (Finding → Abschnitt):**

| Finding | Auflösung |
|---|---|
| P-01 / CR-01 (kritisch): falsche Mount-/Vertragsannahmen | §1 (8 Mounts, Concept-Vertrag, kein `initialLeftWidth`, kein GoalDetail:127) |
| P-02: S2 zu monolithisch | Task 4/5/6 (2a/2b/2c) |
| P-03: Legacy-Drag fälschlich als vorhanden | §1 + §2 D3 + Task 7/9 (neue Fähigkeit, neuer Key) |
| P-04: `hideTraceLinks`-Status quo nicht erkannt | §1 + Task 5 (D2b-Test) |
| P-05: 4-Zustands-Matrix fehlt | §3.5 (inkl. Modal, Mobil, z-index) |
| P-06: Stations-Panel im Footer ungeklärt | §3.4 (Popover) |
| P-07: `isOpenable`-3-Fälle / aktive Station | §1 + Task 4d/4e |
| P-08: Empty-State vermischt | §1 + Task 4g/4h |
| P-09: Settings-Ort Workspace vs. User | §1 + §2 D1 + Task 2 |
| P-10: Ratchet „unverändert" nicht glaubwürdig | §4 + §5 + Task 11 (konkrete Deltas) |
| P-11: Visual-Snapshot-Churn ohne Owner | §5 + Task 11 (Owner `e2e-tester`) |
| P-12: Zwei Mobile-Sheets / Fokus-Konflikt | §3.5 + Task 11 |
| P-13: Frontmatter/Template | Kein `pipeline_stages` (Begründung oben); `### Task N` vorhanden; Review-Status hier |
| MJ-02…MJ-09: Q1-Flat-Liste, MCP-Abwesenheit, `/traceability`-Drawer, Drawer-A11y, Persistence-Rebuild, Ratio-Semantik, Test-DD | §1, §2 D3/D5, Task 1/7/9/10 (je mit Assertions) |
| MN-10…MN-12: NOT-covered, Threat Model, Spec-Pfad | §7, §8, Kopfzeile `**Spec:**` |
| INFO-13: effort-estimator nur als Text-Referenz | §10 |

## 12. Re-Planung & Annahmen

Nach jedem Major Milestone (Schnitt-Gate) prüfen: Gelten die Annahmen noch? Ist die Reihenfolge korrekt? Plan aktualisieren, nicht als frozen behandeln.

- **A1:** Q1 unterstützt 2 neue statische Bool-Keys mit Default `true` und `workspace_id=None`. *Falsch → Task 1 ändert sich (neuer Endpunkt nötig).*
- **A2:** Die 8 Hosts bleiben die einzigen `<TraceSpine>`-Mounts. *Falsch → Task 5-Mountzählung und 2c-grep anpassen.*
- **A3:** SE-Kaskade aktiv → ADR nach `SE/ADR/ADR-NNN_…`; sonst Architektur-Notiz in `docs/plans/`. *Falsch → Task 7-Pfad anpassen (Gate bleibt).*
- **A4:** Drawer-Primitive ist in Modal und Mobile wiederverwendbar. *Falsch → Task 10/11 brauchen getrennte Implementierung.*
- **A5:** Snapshot-Owner (`e2e-tester`) ist für Task 11 verfügbar. *Falsch → Schnitt 4-CI blockiert; vorher eskalieren.*

## 13. Self-Review

- Jeder Task mappt auf genau eine Rolle; jedes Akzeptanzkriterium ist messbar (Zahlen, Testids, 0-Treffer, DOM-Zustände). ✓
- `Files:`/`Interfaces:` pro Task vollständig; Task 1/2 laufen parallel (dateidisjunkt: Backend vs. Frontend); keine Überlappung innerhalb einer Parallelgruppe. ✓
- Kein `pipeline_stages`-Frontmatter, da kein `plan-driven`-Pipeline-Plan — Fallback-Agent-Falle vermieden; `### Task N` dennoch dispatchbar. ✓
- `**Spec:**`, `## Global Constraints`, `## File Structure`, TDD-Schritte (fail → implement → pass → commit), `Review-Status`, `NOT covered`, Threat Model vorhanden. ✓
- Alle Review-Findings P-01…P-13, CR-01, MJ-02…MJ-09, MN-10…MN-12, INFO-13 sind in §11 adressiert. ✓
