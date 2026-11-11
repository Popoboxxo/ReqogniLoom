# Ist-Analyse Artefakt-Inspector — 2026-11

**Auftrag:** Task 2 aus `docs/superpowers/plans/2026-11-10-phase-b2-inspector-concept.md` (Ist-Analyse/Inventar).
**Zweck:** Belegte Bestandsaufnahme des Artefakt-Inspectors (`shared/ArtifactInspector`, Shell `RightSidebar`) und der `TraceSpine` über alle Konsumenten, damit Task 3 (Usability) und Task 5 (Spec) darauf aufsetzen können.
**Stand:** Worktree `fix/phase-b1-frontend-hygiene`, Basis `origin/main` @ `f8c07842`.
**Sprache:** Deutsch (interne Doku). Code-/Datei-Belege in Originalschreibweise.

**Belegkonvention:** Jeder Befund trägt mindestens einen Beleg `datei:zeile`. Pfade sind relativ zur Repo-Wurzel. Mehrfachbelege stehen in einer Zelle durch `·` getrennt.

**Methode:** Reine Code-Lesung (kein Produktivcode, keine Laufzeit-Instrumentierung). Klickzahlen und Wartezeiten in Task 3 sind aus dem Code-Pfad abgeleitet (siehe `docs/analysis/2026-11-inspector-usability.md`, Abschnitt 2).

---

## 0. Laufender Stack / Screenshots — NICHT verfügbar

Task 2 Step 3 (Screenshots) ist **entfallen**. Belegte Prüfung am 2026-11-11:

| Prüfung | Ergebnis |
|---|---|
| `curl http://localhost:5173/` | keine Verbindung (`000`) |
| `curl http://localhost:8001/health/` | keine Verbindung (`000`) |
| `docker ps` | kein ReqogniLoom-Container (nur fremde Projekte: bluepencil-hub, qa-dashboard, portainer, …) |

Es wurde **kein** Docker-Stack gestartet (Vorgabe). Damit existiert kein Ist-Screenshot je Typ und auch kein Verzeichnis `docs/analysis/2026-11-inspector-screenshots/`. Alle Aussagen in diesem Dokument stammen aus dem Quellcode, nicht aus gerenderten Screens. Für Task 5 heißt das: Aussagen zu 768/1024 px Breite sind aus CSS/JS abgeleitet und müssen vor der Umsetzung visuell nachgeprüft werden.

---

## 1. Shell-Aufbau (das, was alle Konsumenten teilen)

`frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx` (466 Zeilen):

| Merkmal | Wert | Beleg |
|---|---|---|
| Element | `<aside role="complementary" aria-label="Inspector for {{kind}}">` | `RightSidebar.tsx:429-437` |
| Testids | `artifact-inspector`, `data-artifact-kind`, `-collapsed`, `-expand`, `-pin`, `-collapse`, `-resize` | `RightSidebar.tsx:316,323,392,402,424,435-436` |
| Breite | Default 360 px, Min 280 px, Max 520 px, eingeklappt 40 px | `RightSidebar.tsx:63-66` |
| Effektive Breite | `min(max(280px, 45%), 100%)` des **Elterncontainers** als `max-width`, `flex: 0 0 <width>px` | `RightSidebar.tsx:72,269-271,305-307` |
| Einklappen | Default **eingeklappt** unter 1600 px Viewport, sofern keine gespeicherte Präferenz | `RightSidebar.tsx:87,110-118` |
| Persistenz (je `kind`) | `reqflow_inspector_collapsed_<kind>`, `reqflow_inspector_pinned_<kind>`, `reqflow_inspector_width_<kind>` | `RightSidebar.tsx:74-76,152-161` |
| Anheften | `pinned` wird nur in `useState`, `useEffect` und `aria-pressed` benutzt — **keine Verhaltenswirkung** | `RightSidebar.tsx:153,160,381-395` (einzige Vorkommen) |
| Resize | Maus-Drag + Tastatur (`role="separator"`, Pfeile/Home/End, 20-px-Schritte) | `RightSidebar.tsx:207-258,411-427` |
| Panel-Reihenfolge | Provenienz-Badge → Version → Diff → Trace (optional) → Kommentare | `RightSidebar.tsx:443-460` |
| Scrollmodell | **eine** Scrollbox für alle Panels (`.panels: overflow-y: auto`) | `RightSidebar.module.css:76-86` |
| Tabs/Anker | existieren nicht; im Code als bewusste Lücke dokumentiert | `RightSidebar.tsx:327-336` · `CommentPanel.tsx:4-7` |
| `hideTraceLinks` | blendet **nur** das TracePanel aus; Default `false` | `RightSidebar.tsx:49-57,144,458` |

**Vier Panels, ein Shell:**

| Panel | Region/Landmark | Testid | Leerzustand | Beleg |
|---|---|---|---|---|
| `VersionPanel` | `<section role="region" aria-labelledby="inspector-version-label">` | `inspector-version-panel`, `version-empty`, `version-error` | „No version history for this artifact." | `VersionPanel.tsx:397-405,230-233` |
| `DiffPanel` | `<section role="region" aria-labelledby="inspector-diff-label">` | `inspector-diff-panel`, `diff-unsupported` | „Diff is not yet available for {{kind}} …" | `DiffPanel.tsx:152-166,172-178` |
| `TracePanel` | `<section role="region" aria-labelledby="inspector-trace-label">` | `inspector-trace-panel`, `trace-empty` | „No trace links." | `TracePanel.tsx:431-446` |
| `CommentPanel` | `<section aria-label>` — **ohne** `role="region"`, ohne `aria-labelledby` | `comment-panel`, `comment-panel-empty` | „No comments yet." | `CommentPanel.tsx:97-114` |
| `InterviewProvenanceBadge` | kein Panel; rendert `null` ohne Provenienz | `interview-provenance-badge` | — | `InterviewProvenanceBadge.tsx:44-60` |

Die drei statischen `aria-labelledby`-IDs sind global eindeutig nur, solange genau ein Inspector gleichzeitig montiert ist. `CommentPanel` fällt als einziges Panel aus dem Muster (kein `inspector-`-Präfix, keine Region).

---

## 2. Inventar-Matrix Teil A — Einbindung je Konsument

11 Einbindungen, 12 `ArtifactKind`-Werte (`types.ts:21-33`). `I` = `InterviewProvenanceBadge` (immer montiert, rendert ohne Provenienz nichts).

| # | Konsument | `kind` | Panels | `hideTraceLinks` | Spine | Inspector-Mount | Beleg |
|---|---|---|---|---|---|---|---|
| 1 | Requirements / SplitView | `requirement` | I, V, D, C | **true** | ja | `currentVersion &&` (praktisch immer) | `RequirementEditors.tsx:889-894`; Spine `:784`; Gate `:888` |
| 2 | Needs | `stakeholderNeed` | I, V, D, C | **true** | ja | `need &&` | `NeedsEditors.tsx:644-649`; Spine `:537` |
| 3 | Risk | `risk` | I, V, D, C | **true** | ja | `item &&` | `RiskEditors.tsx:235`; Spine `:200` |
| 4 | ADR | `adr` | I, V, D, C | **true** | ja | `item &&` | `AdrEditors.tsx:376`; Spine `:332` |
| 5 | Issue | `issue` | I, V, D, C | **true** | ja | `item &&` | `IssueEditors.tsx:237`; Spine `:200` |
| 6 | TestCase | `testCase` | I, V, D, C | **true** | ja | `item &&` | `TestCaseEditors.tsx:400`; Spine `:327` |
| 7 | Architecture | `architecture` | I, V, D, C | **true** | ja | `element &&` | `ArchitectureEditors.tsx:952-956`; Spine `:858` |
| 8 | Goals | `goal` / `mainGoal` | I, V, D, C | **true** | nur `goal` | Auswahl-abhängig | `GoalsPage.tsx:379-384` (Kinds `:332,344`); Spine `GoalDetail.tsx:127` |
| 9 | Glossary | `glossary` | I, V, D, **T**, C | **false (Default)** | **nein** | immer (Term gewählt) | `GlossaryDetailPanel.tsx:83-95` |
| 10 | ICD | `icd` | I, V, D, **T**, C | **false (Default)** | **nein** | immer | `IcdDetailPane.tsx:249-253` |
| 11 | Diagram | `diagram` | I, V, D, **T**, C | **false (Default)** | **nein** | immer | `DiagramDetailView.tsx:537-541` |

Damit: **8 von 12 Kinds haben eine Spine**, **4 nicht** (Glossary, ICD, Diagram, MainGoal). Der Plan nennt „7 Routen" — aktuell sind es 8 Einbindungen (Goal kam hinzu). **9 von 12 Kinds blenden das TracePanel aus** (in 8 Einbindungen), **3 von 12 zeigen es** (Glossary, ICD, Diagram).

---

## 3. Inventar-Matrix Teil B — Merkmal × Typ

| `kind` | Spine | TracePanel | `/versions/`-Fetch | Diff | `baselines`-Prop | `currentVersion`-Quelle | Persistenz-Slots | Kontext (SplitView-Pane) |
|---|---|---|---|---|---|---|---|---|
| `requirement` | ja | nein | ja | ja | **nein** | synthetisch, `updated_at` | 3 Keys | Legacy-SplitView, `initialLeftWidth` nicht gesetzt |
| `stakeholderNeed` | ja | nein | ja | ja | **nein** | synthetisch, `createdAt: null` | 3 Keys | Legacy, `350` |
| `risk` | ja | nein | ja | ja | **nein** | synthetisch, `createdAt: null` | 3 Keys | Legacy, `350` |
| `adr` | ja | nein | ja | ja | **nein** | synthetisch, `createdAt: null` | 3 Keys | Legacy, `350` |
| `issue` | ja | nein | ja | ja | **nein** | synthetisch, `createdAt: null` | 3 Keys | Legacy, `350` |
| `testCase` | ja | nein | ja | ja | **nein** | synthetisch, `createdAt: null` | 3 Keys | Legacy, `350` |
| `architecture` | ja | nein | ja | ja | **nein** | synthetisch, `updated_at` | 3 Keys | Legacy, `leftMinWidth 250` |
| `goal` | ja | nein | ja | ja | **nein** | synthetisch, `created_at` | 3 Keys | Legacy, `350` |
| `mainGoal` | nein | nein | ja | ja | **nein** | synthetisch, `created_at` | 3 Keys | Legacy, `350` |
| `glossary` | nein | ja | ja | ja | **nein** | synthetisch, `updated_at` | 3 Keys | Legacy, **`380`** |
| `icd` | nein | ja | ja | ja | **nein** | synthetisch, `created_at` | 3 Keys | Legacy, Pane-Grid `2fr 1fr` |
| `diagram` | nein | ja | ja | ja | **nein** | synthetisch, `created_at` | 3 Keys | Legacy, Pane-Flex |

Quellen: `types.ts:128-144` (`DIFF_SUPPORTED_KINDS` = alle 12), `VersionPanel.tsx:66-94` (`VERSION_SUPPORTED_KINDS` = dieselbe Menge plus `goal`/`mainGoal`), `VersionPanel.tsx:112-120` (`baselines?` optional), `RightSidebar.tsx:445-451` (kein `baselines` übergeben), `GlossaryView.tsx:634` (`initialLeftWidth={380}`), `IcdDetailPane.module.css:112-116` (`.mainGrid { grid-template-columns: 2fr 1fr }`), `DiagramDetailView.module.css:30-34` (`.layout { display:flex }`).

**Standard-Breite ist für alle Typen identisch** (360 px Default, `RightSidebar.tsx:63`). Die *wirksame* Breite unterscheidet sich trotzdem, weil `max-width` relativ zum Elterncontainer rechnet (`RightSidebar.tsx:305-307`) und dieser Container typabhängig ein Flex-Pane (SplitView), ein Grid-Track (ICD) oder eine Inline-Sektion (Glossary) ist.

**Versions-/Diff-Coverage:** `DIFF_SUPPORTED_KINDS` enthält alle 12 `ArtifactKind`-Werte (`types.ts:128-144`), `VERSION_SUPPORTED_KINDS` ist dieselbe Menge (`VersionPanel.tsx:66-94`). Der Typ-Unterschied „Diff ja/nein" existiert damit im Frontend nicht mehr — obwohl der Plan ihn als offenen Punkt führt (`types.ts:118-126` nennt ihn „now unreachable in practice"). Der Code-Kommentar dort nennt Backend-Coverage für alle Kinds (`types.ts:122-125`).

### 3.1 `data-testid`-Inventar

| Ebene | Testids |
|---|---|
| Shell | `artifact-inspector`, `artifact-inspector-collapsed`, `artifact-inspector-expand`, `artifact-inspector-pin`, `artifact-inspector-collapse`, `artifact-inspector-resize` |
| Version | `inspector-version-panel`, `version-empty`, `version-error`, `version-retry`, `version-row-<n>`, `version-baseline-<n>`, `version-overflow-<n>`, `version-switch-<n>`, `version-compare-<n>` |
| Diff | `inspector-diff-panel`, `diff-unsupported` |
| Trace | `inspector-trace-panel`, `trace-empty`, `trace-error`, `trace-retry`, `trace-filter-chip-<type>`, `trace-filter-toggle-all`, `trace-row-<id>`, `trace-row-open-<id>` |
| Kommentare | `comment-panel`, `comment-panel-empty`, `comment-panel-error`, `comment-panel-list`, `comment-panel-item-<id>`, `comment-panel-resolve-<id>`, `comment-panel-delete-<id>`, `comment-panel-input`, `comment-panel-submit` |
| **Lücken** | Die drei Sektions-Icons des eingeklappten Streifens haben **keine** `data-testid` (`RightSidebar.tsx:337-365`); `CommentPanel` nutzt kein `inspector-`-Präfix. |

### 3.2 Zustände (loading/empty/error/partial)

- **Loading:** Version und Trace haben Skeletons (`VersionPanel.tsx:218-227`, `TracePanel.tsx:394-405`); Diff zeigt einen leeren Live-Bereich bis zur ersten Antwort (`DiffPanel.tsx:190-206`); Kommentare haben **keinen** Ladezustand (`CommentPanel.tsx:30-47`).
- **Empty:** je Panel ein eigener Satz, aber identisch über alle Typen (keine typabhängige Copy). `VersionPanel` faltet „kein Verlauf" und „Endpoint fehlt" in denselben Satz (`VersionPanel.tsx:155-167`).
- **Error:** Version und Trace: Banner + „Reload"-Button; Kommentare: Banner **ohne** Retry, Composer bleibt aktiv (`CommentPanel.tsx:105-109,157-175`); Diff: kein eigener Error-Zustand (delegiert an `ArtifactDiff`).
- **Partial:** `contentAvailable === false` disables „Switch/Compare" je Zeile (Issue #213) — betrifft Einzelzeilen-Typen (`types.ts:57-64`).

---

## 4. Markierte Inkonsistenzen

Bewertungsspalte „fachlich?" = gibt es eine fachliche Ursache für die Abweichung.
`Schwere` nach Nielsen 0–4 (0 = kein Problem, 1 = kosmetisch, 2 = gering, 3 = schwer, 4 = Blockade).

| ID | Befund | Beleg | fachlich? | Schwere |
|---|---|---|---|---|
| **I-01** | **Glossary rendert die Shell inline**, als Block unter der Überschrift „Verwendungen" innerhalb der scrollenden Detailspalte — nicht als rechte Spalte wie alle anderen 10 Einbindungen. | `GlossaryDetailPanel.tsx:71-102` · `GlossaryView.module.css:211-215,248-250` | nein | 3 |
| **I-02** | **ICD legt die Shell in ein CSS-Grid (`2fr 1fr`)**. Die Shell setzt `width`/`flex-basis` und einen Resize-Handle; in einem Grid-Track ändert das nur die Breite *innerhalb* der 1fr-Spalte → sichtbare Lücke statt Spaltenbreite, Resize wirkt nicht wie erwartet. | `IcdDetailPane.module.css:112-116` · `RightSidebar.tsx:269-271,305-307` | nein | 2 |
| **I-03** | **Trace-Links doppelt** bei ICD: `IcdLinkedElements` (incoming+outgoing) **und** `TracePanel` im Inspector zeigen dieselben Links. | `IcdDetailPane.tsx:231-235,249-253` · `IcdLinkedElements.tsx:1-20` | nein | 3 |
| **I-04** | **`hideTraceLinks` ist ein Routen-Schalter, kein Typ-Merkmal.** 8 Typen blenden das TracePanel aus; von diesen haben aber nur Requirement- und Architecture-Stationen ein Verifikations-Badge (`V·n`). Für Risk/ADR/Issue/TestCase/Need/Goal bleibt damit als einzige Link-Ansicht das CRUD-Panel `TraceLinkPanel` unter dem Formular (gruppiert nach Richtung, ohne Typfilter) — eine Read-Ansicht „welcher Test verifiziert das?" fehlt. | `RightSidebar.tsx:49-57,458` · `TraceSpine.tsx:225-255` · `TraceLinkPanel.tsx:277-323` | nein | 3 |
| **I-05** | **`baselines`-Prop wird von keinem Aufrufer übergeben** → Baseline-Chips (`sidebar.version.baselineChip`) und `VersionRef.baselineIds` sind toter Pfad. Der Inspector kann „welche Version pinnt Baseline X?" nicht beantworten. | `VersionPanel.tsx:112-120,137,200-202,271` · `RightSidebar.tsx:445-451` · `types.ts:110-115` | nein | 3 |
| **I-06** | **Id-Space-Bruch:** `CommentPanel` dokumentiert „The generic Artifact id (not the business-entity id)" und ruft `/artifacts/<id>/comments/`; alle 11 Aufrufer übergeben die **Entity**-ID. Das Backend löst bewusst **nicht** auf und antwortet 404 (Issue #983). | `CommentPanel.tsx:20-25` · `api/comments.ts:56-62` · Aufrufer z. B. `RequirementEditors.tsx:891`, `RiskEditors.tsx:235` · `backend/application/comment_service.py:100-112` · `backend/rest_api/collaboration_views.py:53-62` | nein | 4 |
| **I-07** | Derselbe Id-Space-Bruch ist **im Inspector inkonsistent gelöst**: `TracePanel` funktioniert mit Entity-IDs (Backend löst auf), `VersionPanel`/`DiffPanel` brauchen Entity-IDs, `CommentPanel` braucht Artifact-PK, `InterviewProvenanceBadge` akzeptiert beides. Eine Shell, drei ID-Verträge, nirgends dokumentiert. | `TracePanel.tsx:163-167` · `backend/rest_api/views.py:4840-4875` (`list_links_for_entity`) · `InterviewProvenanceBadge.tsx:6-13` · `CommentPanel.tsx:24` | nein | 3 |
| **I-08** | **Anheften ohne Wirkung**: `pinned` beeinflusst nur `aria-pressed` und die Button-Farbe, keine Layout-/Scroll-/Mount-Entscheidung. Ein Bedienelement verspricht eine Funktion, die es nicht gibt. | `RightSidebar.tsx:153,160,381-395` | nein | 2 |
| **I-09** | **Einklapp-Default 1600 px für alle Typen**: auf 1440 px und 1280 px startet der Inspector eingeklappt, unabhängig davon, wie viel Platz die Route hat. | `RightSidebar.tsx:87,110-118` | teilweise (#419: Editor-Kollaps) | 3 |
| **I-10** | **Kein Tab-/Anker-Konzept**: feste Reihenfolge, keine Direktnavigation zu „Kommentare" oder „Diff"; `sidebar.inspector.refresh` und `sidebar.inspector.skeletonLoading` sind definiert, aber in keiner Komponente verwendet. | `RightSidebar.tsx:327-336,443-460` · `i18n/locales/en.json:2235-2236` (Keys ohne Nutzung) | nein | 2 |
| **I-11** | **`aria-label` mit rohem `kind`**: „Inspector for stakeholderNeed" statt lokalisierter Typbezeichnung. | `RightSidebar.tsx:434` · `en.json:2230` · `de.json:2230` | nein | 2 |
| **I-12** | **Landmark/ID-Inkonsistenz**: drei Panels `role="region"` + statisches `aria-labelledby`, Kommentare ohne Region; drei globale IDs (`inspector-version-label`, `-diff-label`, `-trace-label`). | `VersionPanel.tsx:397-401` · `DiffPanel.tsx:172-178` · `TracePanel.tsx:431-436` · `CommentPanel.tsx:97-102` | nein | 2 |
| **I-13** | **Spine-Slot ungenutzt**: `SplitView` bietet einen dedizierten `spine`-Slot (Konzept-Vertrag), kein Konsument nutzt ihn; die Spine liegt stattdessen bei 8 Routen **im scrollenden Detailbereich** und scrollt mit dem Formular weg. | `SplitView.tsx:109-111,332` · `RequirementEditors.tsx:778-790` · `NeedsEditors.tsx:534-545` | nein | 3 |
| **I-14** | **Zwei Kinds auf einer Route (Goals)**: `goal` und `mainGoal` haben getrennte Persistenz-Slots → Einklapp-/Breitenzustand springt beim Wechsel zwischen Hauptziel und Einzelziel. | `GoalsPage.tsx:332-352,379-384` · `RightSidebar.tsx:74-76` | nein | 1 |
| **I-15** | **`diff-unsupported` ist unerreichbar**: `DIFF_SUPPORTED_KINDS` enthält alle 12 Kinds, `mapKindToDiffEntityType` kann nie `null` liefern, der Zweig ist toter Code (im Code selbst als „unreachable in practice" vermerkt). | `types.ts:128-144` · `DiffPanel.tsx:115-119,152-166` | nein (Altlast) | 1 |
| **I-16** | **Token-Drift in den Inspector-CSS**: elfmal literales `white` für Text, Rahmen und Outline, obwohl `--color-on-primary` existiert und **je Theme variiert** (im Bauhaus-Theme navy) → in diesem Theme Kontrastfehler. | `RightSidebar.module.css:67,163` · `VersionPanel.module.css:236,245-246,255` · `TracePanel.module.css:54,175,184-185,194` · `styles/tokens.css:425,1123` | nein | 2 |
| **I-17** | **Geometrie gemischt**: Header-Buttons quadratisch `var(--btn-h-sm)`, Streifen-Buttons `width: 32px` + `height: var(--btn-h-sm)`, Resize-Hitbox 24 px, Chip-Höhen 22/44 px, vier verschiedene Radius-Tokens in einer Komponentenfamilie. | `RightSidebar.module.css:43-49,144-149,174-177` · `TracePanel.module.css:143,208-209,223` · Radius-Inventar: `--radius-md` ×10, `--radius-btn` ×9, `--radius-full` ×6, `--radius-sm` ×3 | nein | 2 |
| **I-18** | **Stale Kommentar**: ICD behauptet „`/versions/` endpoint is not exposed yet" — `VERSIONS_FETCHERS` enthält `icd`, die Doku in `VersionPanel` sagt „all 10 kinds". | `IcdDetailPane.tsx:78-82` vs. `VersionPanel.tsx:64-79` | nein | 1 |
| **I-19** | **DE-Locale mit ASCII-Umlauten in Nutzertexten**: „Verknuepfte Testfaelle anzeigen", „{{count}} Testfaelle". | `i18n/locales/de.json:2707-2708` · Fallback `TraceSpine.tsx:240` | nein | 1 |
| **I-20** | **Eingeklappter Streifen**: nur der Expand-Button trägt ein Testid; die drei Sektions-Icons sind alle `onClick={() => setCollapsed(false)}` (dokumentierter Minimal-Fix) und nutzen Glyphen `⏱`/`≅` neben einem Lucide-Icon. | `RightSidebar.tsx:337-365` | teilweise (`UI-27`) | 2 |
| **I-21** | **Bewusst abweichend, fachlich begründet**: `mainGoal` hat `hideTraceLinks` **und** keine Spine → gar keine Trace-Ansicht. Grund ist dokumentiert (MainGoal hat keinen artifact-level Trace-Graph). | `GoalsPage.tsx:26-32,383` | **ja** | 1 |

**Zählung:** 20 markierte Inkonsistenzen ohne fachliche Ursache (I-01 … I-20, davon I-09/I-20 teilweise begründet), 1 bewusst abweichender Fall (I-21).

### 4.1 Fehlende Standardisierung, die im Plan als Messwert steht

Der Audit-Restwert „19 Button-Höhen, 7 Radien" (Plan, Befund) ist im Inspector teilweise sichtbar, aber nicht als 19 verschiedene Höhen: im Inspector-CSS existieren **vier Radius-Tokens** und **drei Höhen-Tokens** (32/36/44 px) **plus vier zusätzliche Literale** (22, 24, 32, 44 px). Das ist weniger dramatisch als der globale Audit-Wert, aber dieselbe Ursache: Literale neben Tokens (Belege in I-17).

---

## 5. Was der Inspector heute leistet (Kurzfassung für Task 5)

1. **Version + Diff + Kommentare sind überall vorhanden** (12/12 Kinds), **Trace-Links bei 3/12 im Panel**, bei **8/12 über die Spine**; `mainGoal` hat keine der beiden Ansichten.
2. **Ein Ort je Information existiert nicht**: Trace-Links erscheinen je nach Route in Spine, TracePanel und/oder `TraceLinkPanel` (CRUD) — bei ICD zusätzlich in `IcdLinkedElements`, bei Glossary unter „Verwendungen".
3. **Die Shell hat keine Informationsarchitektur** (keine Tabs, keine Anker, eine Scrollbox, feste Reihenfolge) — Navigation zu „Kommentare" ist immer Scrollen.
4. **Zwei der vier Panels sind derzeit funktional eingeschränkt**: Kommentare (Id-Space, I-06) und Version ohne Baseline-Bezug (I-05).
5. **Die Einbindung ist typabhängig divergiert**, nicht typabhängig entworfen: Position (Spalte/Inline/Grid), Trace-Ersatz (Spine/Panel/keins) und Container (Flex/Grid/Flow) unterscheiden sich ohne fachlichen Grund.

---

## 6. Grenzen dieser Analyse

- Keine Laufzeitmessung, keine Screenshots (kein Stack, Abschnitt 0).
- Keine Aussage über tatsächliche Latenz der Requests; nur über deren Anzahl (Task 3).
- Die Id-Space-Folge (I-06) ist aus Frontend-Aufruf + Backend-Vertrag abgeleitet, nicht im Browser reproduziert. Vor Task 5 sollte ein Lauf mit einem echten Artefakt das Fehlerbanner bestätigen.
- `backend/` wurde nur gelesen, um die Frontend-Verträge zu prüfen (Kommentar- und Trace-Link-Service); es wurden keine Backend-Tests ausgeführt.
