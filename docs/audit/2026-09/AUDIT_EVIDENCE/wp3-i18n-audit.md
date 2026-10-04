---
type: REVIEW
scope: wp-3-i18n-audit
status: complete
date: 2026-09-29
author_agent: e2e-tester
method: Browser DE<->EN Umschaltung (lang-switch) + statische Key-Nutzungsanalyse
---

# WP-3 — i18n-Befunde (DE/EN)

## A. Strukturelle Parität

| Kennzahl | Wert |
|---|---|
| Keys in `de.json` | 2 120 |
| Keys in `en.json` | 2 120 |
| In DE fehlend | 0 |
| In EN fehlend | 0 |
| **Daraus folgender Fehlschluss** | Die Paritätsprüfung ist grün, obwohl 112 sichtbare Strings unübersetzbar sind |

## B. Befund B1 — 112 `t()`-Keys fehlen in BEIDEN Locales (AUD-2026-09-002)

Messmethode: alle `t("a.b.c", "Fallback")`-Aufrufe in `frontend/src/**/*.ts{,x}`
(ohne Tests) gegen die aufgelösten Key-Pfade in beiden Locales geprüft.
**Ergebnis: 112 Aufrufe, deren Key in keiner der beiden Dateien existiert.**

### B1.1 Verteilung

| Bereich | Datei | Anzahl | Fallback-Sprache |
|---|---|---|---|
| Canvas-Editor-Toolbar | `canvas/CanvasEditor.tsx` | 20 | EN |
| Berechtigungs-Matrix | `WorkspaceSettings/PermissionsSection.tsx` | 18 | EN |
| Baseline-Compare/Diff | `BaselinesView/BaselinesPanels.tsx` (12) + `BaselinesView.tsx` (2) | 14 | EN |
| Profil | `UserProfileSettings/ProfileSection.tsx` (9) + `ApiKeysSection.tsx` (1) + `UserProfileSettings.tsx` (2) | 12 | **DE** |
| LLM-Einstellungen | `WorkspaceSettings/LlmSettingsSection.tsx` | 9 | EN |
| Memory | `Memory/MemoryPage.tsx` (3) + `SystemSettings/MemoryManagementSection.tsx` (3) + `MemorySystemSettingsSection.tsx` (1) + `MemoryVisualizationSection.tsx` (1) | 8 | **DE** |
| Workflow-/Berechtigungskonfig | `WorkspaceSettings/WorkflowPermissionsSection.tsx` | 7 | EN |
| ICD-Ähnlichkeit | `IcdView/SimilarIcdsPanel.tsx` (5) + `IcdDetailPane.tsx` (1) | 6 | EN |
| CSV-Export | `CsvImport/CsvImport.tsx` | 4 | EN |
| Workspace-Grundlabels | `WorkspaceSettings/WorkspaceSettings.tsx` | 9 | EN (5) + DE (4) |
| Prompt-Vorlagen-Hinweis | `WorkspaceSettings/AiPromptsSection.tsx` | 1 | EN |
| Admin-Dialoge | `AdminDialog/SystemHealthDialog.tsx` (1) + `TriLabelOverviewDialog.tsx` (1) — beide `common.close` | 2 | EN |
| Sidebar / TraceLink / TestRuns | `SidebarNavigation.tsx` (2) + `shared/TraceLinkPanel.tsx` (2) + `TestRuns/TestRunsList.tsx` (1) | 5 | DE (2) / EN (3) |

### B1.2 Fehlende Einzelkeys (Auswahl, vollständig in Anhang A der Fundliste)

```
export.entityType        → "Entity Type"        (fehlt: Section "export" hat nur
                                                 download / downloadReqif / downloading)
export.title             → "CSV Export"
export.errorGeneric      → "Export failed"      (2×)
export.reqifHint         → "Exports the whole workspace …"
settings.workspaceName   → "Workspace Name"
settings.llm.title       → "LLM Provider"       (2×)
settings.llm.description → "Configure the LLM provider …"
settings.llm.provider / baseUrl / apiKey / apiKeyNotSet / modelName
settings.workflowConfig / workflowConfigHint / openInEditor
settings.permissionConfig / permissionConfigHint / overrideMatrix
settings.noGlobalSourceHint
settings.adminOnly        → "You must be an admin to view or edit Workspace Settings. …"
permissions.title / hint / user / artifact / level / grant / load / empty
permissions.noMembers / selectUser / workspaceWide / workspaceWideShort / filterSelect
permissions.userRequired
profile.nameHeading / saved / noName / edit / firstName / lastName
profile.saving / save / cancel
settings.visibility / visibilityFromPreset / promptTemplates.interviewDescription
apiKeys.createNew
systemSettings.adminOnly
systemSettings.memory.degraded / statusDegraded / statusOk / memorySettings.usingDefault
systemSettings.memory.viz.prev / pageInfo / next
canvas.defaultText / defaultLabel
canvas.toolbar.rect / ellipse / text / connector / lineStyle / fill / noFill
canvas.toolbar.snap / zoomOut / zoomIn / zoomFit
canvas.status.hint
baselines.capturedItems / noCapturedItems / legacyEntry
baselines.compareA / compareB / comparing / added / removed / changed
baselines.compareNoChanges / field / before / after
baselines.compareSelectBoth / compareSameBaseline
icds.similarInterfaces / similar.heading / similar.findButton
icds.similar.noEmbedding / unavailable / empty
nav.showOptionalArtifacts / hideOptionalArtifacts
actions.newLink / showAll
common.close
editor.name
```

## C. Befund C1 — Rohe Keys als sichtbare Überschrift (AUD-2026-09-004)

`/settings` → Tab „LLM & Prompts" (deutsches UI), als **Titel** der Prompt-Sektion gerendert:

| Gerenderter Titel | Kontext |
|---|---|
| `architecture_decompose_tree` | Prompt „Analyse the architecture element '{element_title}' …" |
| `bundle_compression` | Prompt „You are compressing a structured export …" |
| `interview.grounding_rank` | Prompt „You are ranking candidate existing artifacts …" |

Die übrigen 9 Sektionen tragen sprechende Titel („Stakeholder Need → Systemanforderungen",
„Anforderung → Testfälle", „Interview: Adr", …). Der Titel stammt aus einem
Key→Label-Mapping, das diese drei Schlüssel nicht enthält.

## D. Befund D1 — Deutsche Lecks im EN-Modus (AUD-2026-09-002, Gegenrichtung)

`/profile`, Sprache auf EN umgestellt:

| Sichtbar | Sollte (EN) | Quelldatei |
|---|---|---|
| Button `Bearbeiten` | `Edit` | `ProfileSection.tsx:117` (`profile.edit`, Fallback „Bearbeiten") |
| Überschrift `Sichtbarkeit (Workspace: e2e-isolated-…5v1h7w)` | `Visibility (…)` | `UserProfileSettings.tsx:106` |
| 6× Checkbox `ADR (Architecture Decision Records)(aus Preset)`, `Risks(aus Preset)`, `Issues(aus Preset)`, `Diagrams(aus Preset)`, `ICDs (…)(aus Preset)`, `Metrics(aus Preset)` | `(from preset)` | `UserProfileSettings.tsx:155` |

Weitere deutsche Fallback-Keys, die im EN-Modus sichtbar werden:
`nav.showOptionalArtifacts`/`hideOptionalArtifacts`, `systemSettings.memory.viz.prev/next/pageInfo`,
`systemSettings.memory.degraded`/`statusDegraded`/`statusOk`, `systemSettings.memorySettings.usingDefault`,
`profile.*` (8), `settings.visibility*`.

## E. Befund E1 — Englische Lecks im DE-Modus (AUD-2026-09-002)

| Screen | Sichtbar | Quelldatei |
|---|---|---|
| `/settings` Allgemein | `Workspace Name` | `WorkspaceSettings.tsx:314` |
| `/settings` LLM | `LLM Provider`, `Provider`, `API Key`, `Model Name`, `Save` | `LlmSettingsSection.tsx:114,122,124,131,179,194,205,211` |
| `/settings` LLM | `Configure the LLM provider used for AI-assisted derivation. …` | `LlmSettingsSection.tsx:124` |
| `/settings` LLM | `Interview prompt placeholders differ by slot. …` | `AiPromptsSection.tsx:253` |
| `/import` Export | `Entity Type` (Import-Karte korrekt: `Entitätstyp`) | `CsvImport.tsx:789` |
| `/import` Export | `Exports the whole workspace (Needs, Requirements, TraceLinks) as ReqIF 1.2 …` | `CsvImport.tsx:831` |
| `/system-settings` | `Sandbox Name`, `Create Sandbox` | `SystemSettings.tsx` |
| `/workflows` | `Export` | `WorkflowEditor` |
| `/settings` Workflows-Tab | `Workflow Configuration`, `Permission Configuration`, `Override matrix…`, `Open in Workflow Editor` | `WorkflowPermissionsSection.tsx:234,237,276,304,351` |

## F. Befund F1 — Denglish in deutschen Werten (AUD-2026-09-013)

| Zeile in `de.json` | Wert | Anzeigeort |
|---|---|---|
| 952 | `"{{count}} User in diesem Tenant"` | `/user-management`: „12 **User** in diesem Tenant" |
| 968 | „Tenant-Admin-Rechte von „{{username}}" entziehen? Der **User** verliert damit sofort den erweiterten Zugriff." | Tenant-Admin-Widerruf |
| 2110 | `"memory.colUserEntries": "User-Einträge (Tenant-weit)"` | `/system-settings` Memory-Tab |
| 2120 | `… {{userCount}} User-Einträge (tenant-weites Memory …)` | Memory-Löschen-Bestätigung |

## G. Befund G1 — Defekter deutscher Wert (AUD-2026-09-012)

`de.json:752`
```
"emptyDescription": "Probleme erfassen Defekte, Verbesserungen und offene Fragen für diesen Workspace."
```
Gerendert auf `/issues`. Fehlender Doppelpunkt nach „erfassen". Der EN-Wert
(`"Issues track defects, improvements and open questions for this workspace."`) ist
grammatisch korrekt ⇒ Copy-Paste-Fehler aus dem EN-String.

## H. Befund H1 — Unmaskiertes Status-Enum (AUD-2026-09-011)

`/test-runs` (deutsches UI), Listenzeile:
```
WK-Abnahme-Lauf-001   Failed   CI: wk-ci-job-001
```
Der Filter derselben Seite bietet `In Bearbeitung / Bestanden / Fehlgeschlagen / Teilweise /
Abgeschlossen`. ⇒ mind. eine Rendering-Stelle ohne `t()`.

## I. Positivbefunde

| Aspekt | Ergebnis |
|---|---|
| Sprachumschaltung | ✅ wirkt sofort, ohne Reload, über `nav-lang-switch`; DE→EN auf `/settings` vollständig korrekt (H1, 6 Tabs, Banner, Preset-Optionen, Terminologie) |
| Schlüsselparität | ✅ 2 120 = 2 120, 0 fehlend |
| `common.*`-Basisstrings | ✅ vorhanden und korrekt übersetzt |
| Pluralisierung | ✅ `_one`/`_other`-Varianten vorhanden (z. B. `"{{count}} Probleme"` / `_one` / `_other`) |
| E2E-Abdeckung der i18n | ❌ **1 von 54 Specs** referenziert `lang-switch` ⇒ die Defekte B/C/D/E/F/G/H sind für die Suite unsichtbar |
