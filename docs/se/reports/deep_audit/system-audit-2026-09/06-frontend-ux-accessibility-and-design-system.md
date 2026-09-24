---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: accessibility-specialist
revision: 66e21f56f36b10e9280e10fed75ee709e5bd7d50
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — Frontend, UX, Accessibility und Design-System

## 1. Management-Summary

Dieser Audit untersucht die React-Frontend-Oberfläche von ReqogniLoom entlang der Kernflüsse Navigation, Requirement-/Need-/TestCase-Bearbeitung, TestRuns, Traceability, Settings/Themes, Interviews, Diff/Inspector und ICD-Ähnlichkeitssuche. Geprüft wurden Informationsarchitektur, Tastatur- und Screenreader-Nutzung, ARIA, Fokus, Formular- und Dirty-State-Verhalten, Loading-/Empty-/Error-/Partial-/Unauthorized-Zustände, responsive Darstellung, i18n, berechnete Kontraste und die Konsistenz des Design-Systems.

Der Audit dokumentiert **0 P0, 7 P1, 8 P2 und 1 P3**. Nach höchster betroffener Konformitätsstufe verteilen sich die Befunde auf **7 × Level A, 9 × Level AA und 0 × Level AAA**.

Die wichtigsten belegten Barrieren sind:

1. **Kein Bypass-Mechanismus für die wiederholte Navigation:** Auf jeder authentifizierten Route stehen Suche, bis zu 24 Navigationslinks und weitere Sidebar-Aktionen vor dem Hauptinhalt; ein Skip-Link fehlt.
2. **Kein anwendungsweiter Dirty-Guard:** Requirement-, Need-, Architecture- und TestCase-Editoren schützen nur den Wechsel innerhalb desselben Artefaktbaums; Sidebar-/Browser-Navigation bleibt ungeschützt. TestRun-Ergebnisentwürfe können beim Wechsel oder Back vollständig verloren gehen.
3. **Legacy-SplitView liefert auf Mobilgeräten keinen funktionierenden Detailzustand:** „Detail“ beendet nur den mobilen Collapsed-Zustand und rendert anschließend wieder beide Panels nebeneinander.
4. **Die ausgelieferten Themes enthalten berechnete WCAG-AA-Verstöße:** Statusfarben als Text, Link-Hover, Fokusringe und hart auf `white` gesetzte Textfarben fallen je nach Theme unter 4,5:1 beziehungsweise 3:1.
5. **Traceability behandelt fehlgeschlagene Teildaten als gültige Leerheit:** Fehlgeschlagene Enrichment- oder Zyklusabfragen werden zu leeren Arrays; die UI kann damit eine nicht geprüfte Hierarchie als sauber darstellen.
6. **Die Dokument-Sprache ist nicht zuverlässig synchronisiert:** `index.html` startet mit `lang="en"`; die deutsche i18next-Sprache kann aktiv sein, ohne dass `document.documentElement.lang` aktualisiert wird.

**Gesamtbewertung:** Das Frontend besitzt bereits starke Grundlagen — insbesondere den gemeinsamen Dialog mit Fokusfalle, native Formularelemente, `prefers-reduced-motion`, Rollen- und Statusmeldungen in vielen Flows sowie Theme- und Token-Ratchets. Die aktuelle AA-Nachweiskette ist dennoch nicht vollständig: zentrale Navigations-, Dirty-State-, Responsive-, Kontrast- und Semantiklücken müssen vor einer belastbaren WCAG-2.2-AA-Erklärung geschlossen oder mit Restrisiko akzeptiert werden.

## 2. Scope, Revision und Methodik

### 2.1 Revision und Abgrenzung

- **Repository:** `C:\Repositories\ai-native-reqflow-POC`
- **Branch:** `feat/1031-bluepencil-host-bridge`
- **Revision:** `66e21f56f36b10e9280e10fed75ee709e5bd7d50`
- **Branch-Guard:** erfüllt; der Branch ist kein `main`/`master`.
- **Änderungsgrenze:** ausschließlich dieser Auditbericht; keine Anwendungsdatei geändert.
- **Prüfbereich:** `frontend/src`, relevante REST-Theme-Validierung, vorhandene Unit-/Integrations-/E2E-Tests und das aktuelle Design-Token-System.
- **Nicht behauptet:** Eine formale WCAG-Zertifizierung oder vollständige manuelle Prüfung mit NVDA, JAWS, VoiceOver, TalkBack, Browser-Zoom und echter Hardware.

### 2.2 Vorgehen

1. Route-, Shell-, Provider- und Navigationsstruktur gelesen und die sichtbaren Kernflüsse verfolgt.
2. Shared Primitives und Formulare auf native HTML-Semantik, ARIA, Fokus, Tastatur und Statusmeldungen geprüft.
3. Dirty-State- und Fehlerpfade für Requirement, Need, Architecture, TestCase, TestRun, Traceability, Settings, Interview und Diff nachverfolgt.
4. Theme-Mappings, reale Farbverwendungen, serverseitige Palette-Validierung und vorhandene Kontrasttests abgeglichen.
5. Alle im Bericht genannten Kontraste nach der WCAG-2.x-Formel für relative Luminanz und Kontrastverhältnis berechnet; keine Schätzwerte.
6. Gezielte Vitest-Suiten für die untersuchten Bereiche ausgeführt.
7. `npm run lint` ausgeführt und nur die belastbaren Produktionswarnungen bewertet; triviale Linter-Hinweise oder gleichwertige native Alternativen wurden nicht automatisch zu WCAG-Verstößen erklärt.
8. Vorhandene E2E-Abdeckung inventarisiert. Wegen eines nicht laufenden Docker-Stacks wurde kein Browser-/Screenreader-Live-Test behauptet.

### 2.3 Tatsache, Hypothese und Confidence

- **Tatsache:** direkt aus aktuellem Quelltext, CSS, Test, Token-Mapping oder berechnetem Kontrast belegt.
- **Hypothese/Auswirkung:** aus der Tatsache abgeleitete mögliche Nutzerfolge; nicht als bereits eingetretener Schaden behauptet.
- **Confidence:** Vertrauen in die Kausalkette, nicht in die Schwere.
- **P0/P1:** nur mit belegtem Standardpfad, realer Nutzerreichweite und fehlender oder unzureichender Gegenmaßahme.

### 2.4 Schweregrade

- **P0:** aktueller, systemweiter Ausfall oder unmittelbarer schwerwiegender Schaden mit belegtem Produktionspfad.
- **P1:** wesentliche Barriere oder Datenverlustrisiko auf einem aktiven Standardpfad.
- **P2:** materielle, aber begrenzte oder indirekte Barriere.
- **P3:** kleines, lokales Risiko mit geringer aktueller Reichweite.

## 3. Informationsarchitektur und Systemgrenzen

### 3.1 Authentifizierte Shell

`NavigationShell.tsx:119-228` bildet jede authentifizierte Route als folgende Struktur:

```text
AuthGate
└── AppShell
    ├── BannerStack
    ├── SidebarNavigation
    │   ├── globale Suche
    │   ├── 24 potenzielle Top-Level-Navigationseinträge
    │   ├── optionale Artefakte
    │   └── Workspace-/Theme-/Sprachaktionen
    ├── main
    └── InterviewWidget (FAB/Overlay)
```

- Die Sidebar wird vor `<main>` gerendert (`frontend/src/components/NavigationShell/NavigationShell.tsx:123-128`).
- Die globale Suche steht vor den Links (`SidebarNavigation.tsx:510-555`).
- `NAV_ITEMS` enthält 24 Einträge, die abhängig von Preset, Rolle und Workspace sichtbar sind (`SidebarNavigation.tsx:75-139`).
- Ein sichtbarer/fokussierbarer Skip-Link existiert im gesamten `frontend/src` nicht.

### 3.2 List/Detail-System

`SplitView.tsx` enthält zwei Verträge:

- **Legacy:** `leftPanel`/`rightPanel` mit Drag-Divider; 16 Produktionsaufrufer.
- **Concept:** `list`/`detail`/`spine`; mobil wird ein offenes Detail als exklusiver Full-Width-Inhalt dargestellt (`SplitView.tsx:718-823`).

Alle 16 aktuellen Produktionsaufrufer verwenden noch den Legacy-Vertrag. Die vorhandenen Concept-Tests schützen den neuen Vertrag, nicht den mobilen Legacy-Pfad (`SplitView.test.tsx:17-210`).

### 3.3 Design-System und Themes

- Primitive und semantische Tokens sind getrennt (`tokens.css:1-24,26-380`).
- Fünf registrierte Themes existieren: `dark`, `light`, `bauhaus`, `nordic`, `sepia` (`ThemeContext.tsx:42-47`).
- `theme-contrast.test.ts` prüft eine begrenzte Positivmatrix (`theme-contrast.test.ts:52-107`).
- DB-Paletten für die Light-Modi der drei benannten Themes werden inline angewendet (`ThemeContext.tsx:91-105`).
- Der Importpfad prüft nur die Vollständigkeit des Token-Schlüsselsatzes (`backend/admin_ops/theme_rest.py:62-79`), nicht Farbformat oder Kontrast.

## 4. Flow-Matrix

| Flow | Vorhandene Zustände und Guards | Belegte Lücke |
|---|---|---|
| Navigation/Routing | `nav`, `main`, Rollen-/Preset-Filter, Route-Suspense-Status, ErrorBoundary | Kein Skip-Link; Suche verschluckt Fehler; mobile Drawer-Fokus bleibt im Hintergrund |
| Requirement/Need/Architecture/TestCase | Initial Loading/Error mit Retry, Empty/No-match, Create-Dialog, Same-Artifact-Dirty-Dialog | Sidebar-/Browser-Navigation nicht geschützt; globaler Router kennt Dirty-State nicht |
| TestRun | Listen-Loading/Error/Retry, Create-Dialog, Ergebnisgrid, Status-/Fehlermeldungen, immutable Close-Bestätigung | Ergebnisentwürfe ohne Route-/Unmount-Guard; UI-Flow nicht durch die vorhandene API-E2E-Suite abgesichert |
| Traceability | Gesamt-Loading, Error-Alert, Empty/No-match, Coverage, Cycle-Alert, Diff-Range-Live-Region | Teildatenfehler werden als Leerheit dargestellt; Error-State ohne Retry; Exportfehler nur Console |
| Workspace-/System-Settings | Rollen-Gate, Tablist/Keyboard, Fehler-Alert, Preset-Downgrade-Bestätigung | Erfolgsstatus nicht als Statusmeldung; Theme-Persistenzfehler verschluckt; Theme-Default-Selects ohne Label-Bindung |
| Interview | Startdialog mit Fehler, Chat-Live-Region, Multi-Proposal mit Busy/Error/Double-Submit-Guard | Transcript ohne Sprecherkennzeichnung; Single-Formalize ohne Busy-/Error-Guard |
| Diff/Inspector | Version-Loading, Error, Initial-State-Hinweis, Range-Live-Region, Inspector-Resize-Keyboard | „Close“ und „Pin“ entsprechen nicht ihrer Bezeichnung; Trace-Chips mit ungültiger Switch-Semantik |
| ICD | Versionierung, Similarity-Loading/-Error/-Empty, Read-only Terminalzustand | Ähnliche Interfaces nur per Maus erreichbar; zugängliche native Button-Variante existiert parallel, wird aber nicht verwendet |

## 5. Berechnete Kontrastmatrix

### 5.1 Rechnung

Die Werte wurden mit der WCAG-Formel berechnet:

```text
L = 0,2126 R + 0,7152 G + 0,0722 B
C = (L_heller + 0,05) / (L_dunkler + 0,05)
```

Die Berechnung erfolgte reproduzierbar über die im Repository festgelegten sRGB-Hexwerte. Für normale kleine Textfarben gilt 4,5:1; für Fokus-/Bedienungsindikatoren giltWCAG 1.4.11 mit 3:1.

### 5.2 Semantische Tokens auf Hauptsurface

| Paar | dark | light | bauhaus | nordic | sepia | Mindestwert |
|---|---:|---:|---:|---:|---:|---:|
| `primary / surface` | **2,84** | 6,01 | **1,69** | **3,01** | 5,06 | 4,5 |
| `success / surface` | 7,04 | **3,60** | **4,31** | 7,68 | **4,29** | 4,5 |
| `warning / surface` | 8,31 | 4,80 | **2,66** | 5,50 | **2,86** | 4,5 |
| `danger / surface` | 4,74 | 4,62 | 4,59 | **3,83** | 5,89 | 4,5 |
| `link-hover / surface` | 5,98 | **2,85** | **2,71** | 5,25 | **2,65** | 4,5 |
| `focus / surface` | 5,98 | 6,01 | **2,47** | 6,02 | 7,13 | 3,0 |
| `white / primary` | 6,29 | 6,29 | **1,87** | 5,19 | 5,70 | 4,5 |
| `white / danger` | **3,76** | 4,83 | 5,06 | **4,09** | 6,63 | 4,5 |

### 5.3 DB-Light-Paletten der benannten Themes

| Paar | bauhaus light | nordic light | sepia light | Mindestwert |
|---|---:|---:|---:|---:|
| `success / surface` | **3,49** | **3,27** | **3,63** | 4,5 |
| `warning / surface` | **4,42** | 4,74 | 4,72 | 4,5 |
| `link-hover / surface` | **3,83** | **3,66** | **3,87** | 4,5 |

Die hervorgehobenen Werte unterschreiten die jeweilige WCAG-2.1-AA-Schwelle. Sie sind keine Schätzung und wurden gegen die aktuellen Zuordnungen in `tokens.css` beziehungsweise `backend/admin_ops/fixtures/themePalettes.light.json` berechnet.

## 6. Detailbefunde

### FEA-001 — Kein Bypass für die wiederholte Sidebar-Navigation

**WCAG criterion:** 2.4.1 Bypass Blocks  
**Conformance level:** A  
**Severity:** major (P1)  
**Location:** `frontend/src/components/NavigationShell/NavigationShell.tsx:119-128`; `frontend/src/components/NavigationShell/SidebarNavigation.tsx:75-139,510-555,465-780`; `frontend/src/components/NavigationShell/AppShell.module.css:10-23`  
**Problem:** Auf jeder authentifizierten Route steht die vollständige Sidebar vor dem Hauptinhalt. Im Extended-Preset umfasst sie Suche, 24 Links, Workspace-/Theme-/Sprachaktionen und weitere Buttons. Im gesamten Frontend existiert kein Skip-Link zum Hauptinhalt.

**Assistive tech:** Tastatur; Screenreader-Browse-Mode und Screenreader-Navigation über Landmarken.

**Fakt:** Die Sidebar wird vor `<main>` gerendert; ein Mechanismus wie `href="#main-content"` fehlt in `frontend/src`.

**Evidenz:**
- `NavigationShell.tsx:123-128` — `SidebarNavigation` steht vor `main`.
- `SidebarNavigation.tsx:75-139` — bis zu 24 Navigationseinträge.
- `SidebarNavigation.tsx:510-555` — globale Suche als erster fokussierbarer Sidebar-Inhalt.
- Kein Treffer für Skip-Link/`main-content` in `frontend/src`.

**Auswirkung:** Tastatur- und Switch-Benutzer müssen auf jeder Route denselben langen Navigationsblock durchlaufen, bevor sie den auftragsbezogenen Inhalt erreichen. Landmarken helfen Screenreadern, ersetzen aber keinen direkten Tastatur-Bypass.

**Root Cause:** Die Shell priorisiert die visuelle Navigation, ohne einen separaten Bypass- und Fokusübergabepfad zu modellieren.

**Gegenmaßnahme:**
- Als erstes fokussierbares Element einen nativen `<a href="#main-content">Zum Hauptinhalt springen</a>` rendern.
- `id="main-content"` am bestehenden `<main>` setzen und es bei Aktivierung programmatisch fokussierbar machen.
- Den Skip-Link nur bei `:focus` sichtbar machen, ohne ihn aus dem Tab-Fokus zu entfernen.
- Mit `aria-label`/sichtbarem Text beide Sprachrichtungen abdecken.

**Aufwand:** S — ein fokussierter Shell- und E2E-Test.

**Alternativen:**
- Nur ein Landmark-Rotor: für Tastaturbenutzer nicht ausreichend.
- Sidebar-Einträge alphabetisch oder kompakter umsortieren: reduziert nur die Wiederholung, beseitigt den Bypass nicht.

**Confidence:** Hoch.

**Validierung/Messplan:** Mit ausschließlich `Tab` und `Shift+Tab` von einem kalten App-Load prüfen, dass der erste Stop der Skip-Link ist und die Aktivierung den Fokus in `<main>` setzt. NVDA, JAWS und VoiceOver müssen den Sprung und den neuen Kontextansatz melden.

### FEA-002 — Dirty-State schützt nur lokale Entitätswechsel, nicht Anwendungsnavigation

**WCAG criterion:** 3.3.4 Error Prevention (Data), angewandt auf persistente Artefakt- und Testresultatentwürfe  
**Conformance level:** AA  
**Severity:** major (P1)  
**Location:** `frontend/src/components/RequirementEditors/RequirementEditors.tsx:84-119,248-276,797-805`; `frontend/src/components/NeedsEditors/NeedsEditors.tsx:70-102,310-339,383-391`; `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx:115-120,285-309,713-721`; `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx:73-101,169-198,248-256`; `frontend/src/components/TestRuns/TestRunResultEntryGrid.tsx:118-146,203-251,400-510`; `frontend/src/components/NavigationShell/SidebarNavigation.tsx:465-580`; `frontend/src/components/NavigationShell/NavigationShell.tsx:135-219`  
**Problem:** Die vier Artefakt-Editoren bestätigen einen drohenden Verlust nur beim Wechsel innerhalb desselben Artefaktbaums. Ein Klick in die globale Sidebar, ein Router-Navigationspfad oder ein Browser-Reload umgeht diesen Guard. TestRun-Ergebnisentwürfe besitzen überhaupt keinen Route-/Unmount-Guard.

**Assistive tech:** Tastatur; Screenreader-Fokusmodus; alle Nutzergruppen sind durch den Datenverlust betroffen.

**Fakt:**
- `pendingSelectId` wird ausschließlich von den lokalen `select*`-Callbacks gesetzt.
- `NavigationShell` rendert die Sidebar unabhängig vom lokalen Editor-Guard.
- `TestRunResultEntryGrid` speichert Entwürfe nur in lokalem State und verwirft sie beim Result-Reset bzw. Unmount.
- `PermissionMatrixEditor.tsx:65-83` zeigt, dass das Projekt bereits einen selektiven `beforeunload`-Guard für eigenständige Settings-Editoren etabliert hat.

**Evidenz:**
- Requirement: `selectRequirement()` schützt nur `id !== selectedId` (`RequirementEditors.tsx:254-276`).
- Need: `selectNeed()` schützt nur den lokalen Baumwechsel (`NeedsEditors.tsx:318-339`).
- Architecture: `selectElement()` schützt nur den lokalen Baumwechsel (`ArchitectureEditors.tsx:292-309`).
- TestCase: `selectTestCase()` schützt nur den lokalen Baumwechsel (`TestCaseEditors.tsx:177-198`).
- TestRun: `drafts` leben nur in `useState`; `results` resetten den State (`TestRunResultEntryGrid.tsx:118-136`).

**Auswirkung:** Bearbeitete Anforderungen, Needs, Architekturelemente, Testfälle oder Testresultate können beim Wechsel zu einer anderen Route oder beim Schließen/Neuladen ohne Rückfrage verloren gehen. Besonders betroffen sind lange Testlauf-Notizen und ungespeicherte Custom-Field-Entwürfe.

**Root Cause:** Dirty-State ist eine lokale Komponentenentscheidung statt eines Anwendungsvertrags. Der Router kennt nicht, welche Entitäten oder Formulare gerade schutzbedürftig sind.

**Gegenmaßnahme:**
- Einen zentralen `UnsavedChangesProvider`/Dirty-Registry-Vertrag einführen.
- Editoren registrieren Dirty-State und eine menschenlesbare Bezeichnung; verschachtelte Editoren werden referenzzählt.
- React-Router-Navigation über `useBlocker` und Browser-Unload über `beforeunload` gemeinsam absichern.
- Einen fokussierten Shared-ConfirmDialog verwenden: standardmäßig „Speichern“, „Verwerfen“, „Abbrechen“; bei read-only oder laufender Mutation wird die Entscheidung angepasst.
- TestRun-Ergebnisentwürfe in denselben Vertrag einbeziehen; die vorhandenen Row-/Save-All-Guards bleiben bestehen.

**Aufwand:** L — zentraler Provider, Integrationspunkte und mehrere Tests.

**Alternativen:**
- In jedem Editor `beforeunload` ergänzen: schützt Reload, aber keine SPA-Navigation und führt zu Logikduplikaten.
- Autosave erzwingen: verändert fachliche Semantik und darf ohne Produktentscheidung nicht eingeführt werden.

**Confidence:** Hoch für die Codepfade; keine Häufigkeitsmessung.

**Validierung/Messplan:** Für jeden geschützten Editor einen dirty Draft anlegen und nacheinander (a) lokalen Artefaktwechsel, (b) Sidebar-Navigation, (c) Browser Back, (d) Reload, (e) Tabwechsel innerhalb Settings testen. Erwartung: Abbrechen erhält den Draft; Verwerfen navigiert erst nach expliziter Bestätigung.

### FEA-003 — Legacy-SplitView rendert mobil keinen isolierten Detailzustand

**WCAG criterion:** 1.4.10 Reflow; 4.1.2 Name, Role, Value; 3.1.2 Language of Parts  
**Conformance level:** AA  
**Severity:** major (P1)  
**Location:** `frontend/src/components/SplitView/SplitView.tsx:525-569,718-823`; 16 Produktionsaufrufer, unter anderem `RequirementEditors.tsx:830-838`, `TestRunsList.tsx:195-504`, `TraceabilityView.tsx:836-842`, `BaselinesView.tsx:351`  
**Problem:** Unterhalb 768 px ist zunächst nur die Liste sichtbar. „Detail“ setzt `isResponsiveCollapsed` lediglich auf `false`; dadurch endet der mobile Zweig und die Desktop-Zweispaltenansicht rendert beide Panels. Ein „Zurück/List“-Zustand existiert danach nicht.

**Assistive tech:** Tastatur; Screenreader; Reflow bei Zoom und kleinen Viewports.

**Fakt:** Die beiden Buttons sind hartcodiert „List“ und „Detail“, tragen keinen programmatischen Auswahlzustand und sind nicht übersetzt.

**Evidenz:**
- Mobil: `SplitView.tsx:541-569`.
- Klick „Detail“: nur `setIsResponsiveCollapsed(false)` (`SplitView.tsx:556-561`).
- Danach rendert der Desktop-Zweig Liste und Detail gleichzeitig (`SplitView.tsx:572-631`).
- Der bereits vorhandene Concept-Vertrag liefert den korrekten Mobile-Replace (`SplitView.tsx:718-823`).
- 16 Produktionsdateien rufen den Legacy-Vertrag auf.

**Auswirkung:** Auf schmalen Viewports kann die gewählte Detailseite zweigeteilt, horizontal gequetscht oder außerhalb des sichtbaren Bereichs dargestellt werden. Rücknavigation zur Liste und eindeutige Ansichtsauswahl fehlen.

**Root Cause:** Ein boolescher Wert `isResponsiveCollapsed` bildet drei Konzepte gleichzeitig ab: Zone, aktive Seite und Auf-/Zuklappen.

**Gegenmaßnahme:**
- Primär die 16 Aufrufer auf `list`/`detail` migrieren.
- Falls der Legacy-Vertrag kurzfristig bleiben muss: expliziten `view: list|detail`-State, vollständig austauschbare Panels, einen sichtbaren Rück-Button und i18n-Prosa einführen.
- Keine ARIA-Tabs ergänzen, wenn es sich nicht wirklich um Tabs handelt; ein einfacher nativer Button ist robuster.

**Aufwand:** L für die Migration, S für einen lokalen Legacy-Fix.

**Alternativen:**
- Nur die Labels lokalisieren: behebt WCAG 3.1.2, nicht den Funktionsverlust.
- Auf Desktop-Verhalten verzichten: verschlechtert Tablet-/Zoom-Nutzung.

**Confidence:** Hoch.

**Validierung/Messplan:** Bei 320, 375, 767, 768, 1023 und 1024 px sowie 200 % Zoom für mindestens Requirement, TestRun und Traceability prüfen: kein horizontales Two-Pane-Scrolling, genau eine sichtbare Seite, Detail rückt zur vollständigen Liste zurück, Fokus bleibt auf einer sichtbaren Aktion.

### FEA-004 — Theme-Kontrastvertrag ist unvollständig; Custom-Paletten werden nicht kontrasvalidiert

**WCAG criterion:** 1.4.3 Contrast (Minimum); 1.4.11 Non-text Contrast  
**Conformance level:** AA  
**Severity:** major (P1)  
**Location:** `frontend/src/styles/tokens.css:885-1055,1067-1232,1241-1393,1402-1559`; `frontend/src/styles/global.css:42-50,59-67`; `frontend/src/components/ArtifactDiff/ArtifactDiff.module.css:146-173,238-260`; `frontend/src/components/NavigationShell/SidebarNavigation.module.css:351-364,453-466,664-666`; `frontend/src/components/WorkspaceSettings/WorkspaceSettings.module.css:17-23,168-177`; `frontend/src/components/shared/ArtifactInspector/TracePanel.module.css:51-65,166-192`; `frontend/src/test/theme-contrast.test.ts:52-107`; `backend/admin_ops/theme_rest.py:62-79`  
**Problem:** Mehrere semantische Tokens werden als normale kleine Texte auf Hauptsurfaces verwendet, obwohl ihre berechneten Werte in ausgelieferten Themes unter 4,5:1 liegen. Der Bauhaus-Fokusring liegt zusätzlich unter 3:1. Mehrere Komponenten setzen statt `--color-on-primary`/`--color-on-danger` hart `white`. Der Palette-Import akzeptiert jede nichtleere Token-Map mit vollständigen Schlüsseln, ohne Werte oder Kontraste zu prüfen.

**Assistive tech:** Nutzer mit Sehbeeinträchtigung, Kontrastverlust und High-Contrast-/Zoom-Nutzung; Screenreader bei fehlender Textalternative für Status und Fokus.

**Fakt:** Die berechnete Matrix in Abschnitt 5 zeigt aktuelle Verstöße. Beispiele:

- Diff-Erfolgstext: `success/surface` in light **3,60**, bauhaus **4,31**, sepia **4,29** (`ArtifactDiff.module.css:163-165,238-240`).
- Link-Hover: `link-hover/surface` in light **2,85**, bauhaus **2,71**, sepia **2,65** (`global.css:48-50`).
- Workspace-Erfolg: `success/surface` in light **3,60** (`WorkspaceSettings.module.css:175-177`).
- Fokus: bauhaus **2,47** auf Surface und **2,72** auf Raised (`tokens.css:1148`, `global.css:63-67`).
- Create-Workspace-Button: weiß auf bauhaus-Primary **1,87** (`SidebarNavigation.module.css:453-465`).
- Trace-Fehlerbanner: weiß auf danger **3,76** in dark und **4,09** in nordic (`TracePanel.module.css:166-184`).
- Sidebar-Sprachfehler: `danger/nav-bg` liegt in allen fünf Theme-Hintergründen unter 4,5:1; tatsächlich 4,36/3,40/3,25/4,01/2,48 (`SidebarNavigation.module.css:664-666`).
- DB-Light-Paletten haben zusätzliche `success/surface`-Werte von 3,27–3,63.

**Evidenz:** Der vorhandene Kontrasttest nennt seine Paare absichtlich „not an exhaustive sweep“ und enthält weder `primary/surface`, `success/surface`, `warning/surface`, `danger/surface`, `link-hover/surface` noch Fokus gegen Raised (`theme-contrast.test.ts:52-107`).

**Auswirkung:** Links, Statusmeldungen, Diff-Werte, Warnhinweise und Fokusindikatoren können für Nutzer mit Sehbeeinträchtigung unlesbar oder nicht erkennbar sein. Ein absichtlich importiertes Custom Theme kann dieselben Verstöße tenantweit aktivieren.

**Root Cause:** Das Design-System trennt Fill- und Textrollen nicht konsequent. `--color-primary` und Statusfarben müssen sowohl als Fläche als auch als Text funktionieren, während nur ein Kontrastvertrag getestet wird. Der Server prüft Schlüssel, nicht das Verhalten der Farbrolle.

**Gegenmaßnahme:**
- Rollenspezifische Tokens einführen, etwa `--color-link`, `--color-success-text`, `--color-warning-text`, `--color-danger-text` und gegebenenfalls `--color-primary-text`.
- Auf jeder soliden Fläche ausschließlich `--color-on-primary`, `--color-on-success`, `--color-on-warning`, `--color-on-danger` verwenden.
- Theme-Mappings so ändern, dass alle reellen Nutzungspaare 4,5:1 beziehungsweise Fokus/UI 3:1 erreichen.
- Import serveseitig gegen CSS-Farbsyntax und eine explizite Rollenmatrix validieren; semantisch nicht erlaubte Werte für `--color-primary-rgb` usw. zurückweisen.
- Den Kontrasttest um eine usage-basierte Positivliste erweitern und translucent `color-mix()`-Hintergründe im Browser testen.

**Aufwand:** L — Token-Neubelegung, visuelle Regression und Importvertrag.

**Alternativen:**
- Nur Testgrenzen verschärfen: lässt die aktuellen Verstöße bestehen.
- Alle fehlerhaften Verwendungen auf `--color-text` umstellen: entfernt Statussemantik und erhöht nicht automatisch die Nicht-Text-Kontraste.

**Confidence:** Hoch; Werte sind reproduzierbar berechnet.

**Validierung/Messplan:** Automatisierter Token-Test über alle 5 CSS-Themes und 3 DB-Light-Paletten; je Usage-Paar mindestens 4,5:1 beziehungsweise 3:1. Zusätzlich Axe/Color Contrast im Browser für Default, Link-Hover, Diff-Success, Settings-Saved, Sidebar-Fehler, Fokus und Inspector-Status.

### FEA-005 — Dokument-Sprache und gemischtsprachige UI-Teile sind nicht zuverlässig synchron

**WCAG criterion:** 3.1.1 Language of Page; 3.1.2 Language of Parts  
**Conformance level:** AA  
**Severity:** major (P1)  
**Location:** `frontend/index.html:2`; `frontend/src/i18n/index.ts:15-27`; `frontend/src/context/WorkspaceContext.tsx:330-347`; `frontend/src/components/NavigationShell/SidebarNavigation.tsx:363-410`; `frontend/src/components/RequirementEditors/MarkdownPreview.tsx:80-83`; `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx:149-153,418-547`; `frontend/src/components/SplitView/SplitView.tsx:548-561`; `frontend/src/components/InterviewWidget/InterviewArtifactPane.tsx:30-52`; `frontend/src/test/i18n-parity.test.ts:62-203`  
**Problem:** Das Dokument startet mit `lang="en"`. `i18n.init()` wählt DE/EN, synchronisiert `<html lang>` aber nicht. Die Workspace-Wiederherstellung setzt das Attribut nur, wenn `i18next.language` bereits von der Workspace-Sprache abweicht; bei gleicher Sprache bleibt das initiale Englisch stehen. Zahlreiche sichtbare Texte sind unabhängig von der Oberflächensprache hartcodiert.

**Assistive tech:** Screenreader-Spracherkennung und Braille-Ausgabe; Sprachlernende.

**Fakt:** Auf einem deutschen Browser/Workspace kann i18next bereits `de` sein, während `document.documentElement.lang` weiterhin `en` ist. Der Sprachwechsel im Sidebar setzt das Attribut manuell; es gibt keinen zentralen `languageChanged`-Vertrag.

**Evidenz:**
- `index.html:2` — `lang="en"`.
- `i18n/index.ts:22` — wählt nur die i18next-Sprache.
- `WorkspaceContext.tsx:341-346` — `html.lang` wird nur im Change-Zweig aktualisiert.
- `SplitView.tsx:554,560` — „List“/„Detail“.
- `ArtifactDiff.tsx:431,441,461,495,501,529-542` — „Close“, „From“, „To“, „Loading diff...“, „Error“, „Raw JSON“.
- `i18n-parity.test.ts:186-203` — erlaubt bis zu 116 im Source referenzierte, in beiden Bundles fehlende Schlüssel.
- `InterviewArtifactPane.tsx:33-51` — englische Labels/Resultatprosa.

**Auswirkung:** Screenreader verwenden die falsche Aussprache und Braille-Sprache; gemischtsprachige Parts sind für Sprachlern und Nutzer mit Sprachbarrieren schwer verständlich. Fehlende Schlüssel können je nach Default zwischen DE und EN springen.

**Root Cause:** Dokument-Sprache und i18next-Sprache werden an mehreren Stellen manuell synchronisiert; i18n-Parität wird als monotoner Ratchet statt als vollständiger Release-Vertrag geführt.

**Gegenmaßnahme:**
- Nach `i18n.init()` und bei jedem `languageChanged`-Event zentral `document.documentElement.lang = i18n.resolvedLanguage` setzen.
- Manuelle Zuweisungen in Sidebar/Workspace/Settings entfernen.
- Hartcodierte sichtbare Strings in DE/EN-Bundles überführen.
- Fehlende Keys bis null reduzieren; insbesondere die konkreten Diff-/SplitView-/Interview-Defaults priorisieren.
- Für bewusst fremdsprachige Dokumentinhalte `lang` am konkreten Element setzen, nicht die Dokumentsprache umschreiben.

**Aufwand:** M.

**Alternativen:**
- Nur `index.html` auf `lang="de"` ändern: verschiebt die Fehlermeldung ins Englische und bricht englische Workspaces.
- Nur `i18next.language` beobachten: die Eigenschaft kann Regionalvarianten enthalten; `resolvedLanguage` ist hier die robustere Quelle.

**Confidence:** Hoch.

**Validierung/Messplan:** Tests für Browser-DE, Workspace-DE, Workspace-EN und nachträglichen Sprachwechsel. Nach jedem Zustand muss `html.lang` der sichtbaren Sprache entsprechen. NVDA/JAWS mit deutscher und englischer Voice prüfen; NVDA/JAWS müssen keine Mischsprache im Transcript und Diff vorlesen.

### FEA-006 — Interview-Transcript gibt Sprecherrollen nicht programmatisch aus

**WCAG criterion:** 1.3.1 Info and Relationships  
**Conformance level:** A  
**Severity:** major (P1)  
**Location:** `frontend/src/components/InterviewWidget/InterviewChatPane.tsx:121-151`; `frontend/src/api/interviews.ts:28-37,241-247`  
**Problem:** Das Transkript erhält `role="log"`, rendert aber nur den Nachrichtentext. Die visuell unterschiedlichen CSS-Klassen für User und Assistant sind programmatisch nicht als Sprecherbeziehung ausgezeichnet. Die Rolle steckt zwar im Datenmodell, wird aber nicht in Text oder zugänglichem Namen ausgegeben.

**Assistive tech:** Screenreader-Browse-Mode und VoiceOver-Rotor; NVDA/JAWS-Browse-Mode.

**Fakt:** `msg.role` steuert ausschließlich `styles.userMessage` oder `styles.assistantMessage`; im Accessibility-Baum sind beide Nachrichten nur neutrale `<p>`-Elemente.

**Evidenz:**
- Rollen im API-Modell: `interviews.ts:29-37`.
- Rendering ohne Speaker: `InterviewChatPane.tsx:143-150`.
- `role="log"` allein kennzeichnet den Container, nicht die einzelnen Sprecher.

**Auswirkung:** Screenreader-Nutzer hören eine Folge gleichartiger Absätze und verlieren die zentrale semantische Information, wer die Aussage gemacht hat. NVDA/JAWS können im Browse-Modus den visuellen CSS-Unterschied nicht zuverlässig vorlesen; VoiceOver verhält sich beim Rotor für Log-Inhalte abweichend.

**Root Cause:** Visuelle Klassen wurden als ausreichende Rollenabbildung betrachtet; semantische Transkriptdaten werden nicht in zugängliche Struktur überführt.

**Gegenmaßnahme:**
- Pro Nachricht einen semantischen Artikel oder Container mit sichtbarem beziehungsweise nur für AT bestimmtem Sprecherlabel rendern, zum Beispiel „Sie: …“ und „Assistent: …“.
- `role="log"`/`aria-live="polite"` für die Aktualisierung beibehalten.
- Keine redundanten Rollen wie `role="message"` ohne vollständigen Browser-/AT-Vertrag ergänzen.
- Die `role`- Werte am Backend auf eine geschlossene Menge `user|assistant|system|tool` begrenzen und lokalisiert ausgeben.

**Aufwand:** S.

**Alternativen:** Nur unterschiedliche `aria-label` am `<p>`: funktioniert, ist aber bei deaktiviertem Labeling und virtualisierten Logs schwerer zu prüfen; sichtbare Labels sind robuster.

**Confidence:** Hoch.

**Validierung/Messplan:** NVDA- und JAWS-Browse-Mode sowie VoiceOver-Rotor auf mindestens fünf Rollenwechseln prüfen. Jede neue Nachricht muss Sprecher und Text in der richtigen Reihenfolge ansagen, ohne dass der Fokus springt.

### FEA-007 — Traceability verbirgt fehlgeschlagene Teildaten als gültige Leerheit

**WCAG criterion:** 4.1.3 Status Messages; 1.3.1 Info and Relationships  
**Conformance level:** AA  
**Severity:** major (P1)  
**Location:** `frontend/src/components/TraceabilityView/TraceabilityView.tsx:290-426,461-481,522-531,642-662`  
**Problem:** Mehrere optionale Requests werden bei Fehlern auf leere Listen gesetzt; die Zyklusprüfung wird bei Fehler auf `cycles: []` gesetzt. Dadurch kann die UI fehlende Daten nicht von einer echten Nullmenge unterscheiden. Insbesondere kann ein fehlgeschlagener Cycle-Check als „keine Zyklen“ erscheinen.

**Assistive tech:** Screenreader-Statusansagen; visuelle Nutzer mit unterschiedlichen Ansagen von „leer“ und „nicht verfügbar“.

**Fakt:** `Promise.all` verwendet pro Endpoint `.catch(() => emptyList)` beziehungsweise `.catch(() => emptyCycles)`. Diese Teilausfall-Zustände werden nicht in State oder UI modelliert.

**Evidenz:**
- Risk/Issue/ADR/Need/ICD/Cycle-Fallbacks: `TraceabilityView.tsx:308-337`.
- Zustand wird anschließend als normaler Erfolg gesetzt: `TraceabilityView.tsx:396-406`.
- Cycle-Warnung erscheint nur bei `state.cycles.length > 0`: `TraceabilityView.tsx:642-662`.
- Der Gesamt-Error-State hat keinen Retry-Button: `TraceabilityView.tsx:522-531`.

**Auswirkung:** Nutzer können eine unvollständige Trace-Matrix, fehlende Endpoint-Titel oder eine ungeprüfte Hierarchie als gültiges Analyseergebnis interpretieren. Das ist besonders kritisch, wenn die Ansicht für Review-, Impact- oder Baseline-Entscheidungen verwendet wird.

**Root Cause:** Fehlertoleranz wurde durch lokale Catch-zu-leer-Defaults implementiert statt als expliziter Degraded-State.

**Gegenmaßnahme:**
- `Promise.allSettled` verwenden und je Datenquelle `ready|empty|unavailable` modellieren.
- Cycle-Fehler als sichtbare, programmatisch ankündbare Warnung „Prüfung nicht verfügbar“ rendern; niemals als leere Zyklenliste.
- Coverage und Endpoint-Titel nur als vollständig berechnen, wenn alle benötigten Quellen erfolgreich waren.
- Im Gesamt-Error-State einen Retry mit demselben `reloadKey` anbieten.
- Fehlgeschlagene Enrichment-Quellen visuell als eingeschränkt kennzeichnen, auch wenn ein UUID-Fallback nutzbar bleibt.

**Aufwand:** M.

**Alternativen:** Fehler wiederholt automatisch versuchen, ohne sichtbaren Degraded-State: reduziert nur temporäre Fehler, verbirgt aber weiterhin dauerhafte Verfügbarkeitsprobleme.

**Confidence:** Hoch.

**Validierung/Messplan:** Pro optionalem Endpoint einen 503/Timeout erzwingen und mit `aria-live`/`role="alert"` prüfen, dass genau die betroffene Aussage als nicht verfügbar markiert wird. Zusätzlich sicherstellen, dass die Coverage-Zahl bei unvollständiger Datenbasis nicht als gesamtvertrauenswürdig erscheint.

### FEA-008 — Globale Suche verwendet eine unvollständige Listbox-/Combobox-Semantik

**WCAG criterion:** 2.1.1 Keyboard; 4.1.2 Name, Role, Value  
**Conformance level:** A  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/NavigationShell/SidebarNavigation.tsx:182-188,243-307,510-555`  
**Problem:** Das Suchfeld ist ein natives `input type="search"`, die Trefferliste erhält `role="listbox"`, die Treffer native Buttons mit `role="option"`. Es fehlen `role="combobox"`, `aria-autocomplete`, `aria-expanded`, `aria-controls`, `aria-activedescendant` und die erwartete Pfeiltasten-/Enter-Navigation. Suchfehler werden verworfen.

**Assistive tech:** Tastatur; NVDA/JAWS; VoiceOver-Rotor und VoiceControl.

**Fakt:** Enter startet nur die Suche erneut. Nach der Antwort bleiben die Tastaturoptionen nicht mit dem Eingabefeld verknüpft; VoiceOver kann die Liste je nach Rotor als statische Liste behandeln.

**Evidenz:** `SidebarNavigation.tsx:512-529` — Input/Listbox; `:535-551` — Buttons als Optionen; `:297-307` — nur Enter/Escape; `:267-275` — Fehler werden still verworfen.

**Auswirkung:** Screenreader- und Tastaturbenutzer erhalten kein zuverlässiges Search-Combobox-Verhalten. NVDA/JAWS können den Fokus/aktiven Treeitem unterschiedlich ankündigen; VoiceOver kann die Liste nur über Rotor oder Tabfindings erreichen.

**Root Cause:** Die visuelle Suggestion-Liste wurde als ARIA-Listbox etikettiert, ohne das editoriale Combobox-Modell vollständig zu implementieren.

**Gegenmaßnahme:**
- Bevorzugt die Rollen entfernen und eine semantische Region mit nativen Buttons anbieten, die per Tab erreichbar sind.
- Falls ein echtes Editable Combobox gewünscht ist, das APG-Modell vollständig implementieren: `combobox`, `aria-autocomplete=list`, `aria-expanded`, `aria-controls`, `aria-activedescendant`, Arrow/Home/End/Enter/Escape, unsichtbarer Fallback für fehlende `aria-activedescendant`-Unterstützung.
- Suchfehler sichtbar als `role="alert"` melden und Retry anbieten.

**Aufwand:** M.

**Alternativen:** Die Listbox-Rollen trotz unvollständiger Tastatur beibehalten: schwächt die heutige Nachvollziehbarkeit und verlagert die Reparatur in Screenreader-Sonderfälle.

**Confidence:** Hoch für die Markup-/Keyboard-Lücke, mittel für die konkrete Screenreader-Ausgabe.

**Validierung/Messplan:** NVDA mit Firefox, JAWS mit Chrome und VoiceOver mit Safari; Suchen, Pfeiltasten, Enter, Escape, Tab und Fehlerfall prüfen. Kein Screenreader darf eine Listbox ohne verknüpften aktiven Wert ankündigen.

### FEA-009 — Asynchrone Erfolgs- und Fehlerstatus sind in Settings, Theme und Export inkonsistent

**WCAG criterion:** 4.1.3 Status Messages  
**Conformance level:** AA  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:638-648`; `frontend/src/context/ThemeContext.tsx:190-197`; `frontend/src/components/SystemSettings/ThemeManagementSection.tsx:32-57,83-112,196-230`; `frontend/src/components/TraceabilityView/TraceabilityView.tsx:461-481,826-833`  
**Problem:** Mehrere sichtbare Erfolgszustände sind nur statische Spans; serverseitige Persistenz- oder Exportfehler werden nicht als Statusmeldung ausgegeben. ThemeContext verschluckt den Persistenzfehler vollständig, ThemeManagement verschluckt Default-Reload-/Delete-Fehler, Traceability loggt PDF-Exportfehler nur in die Konsole.

**Assistive tech:** Screenreader-Statusregionen und Live-Regionen.

**Fakt:** `WorkspaceSettings.savedOk` und `tenantDefaultSaved` rendern Text ohne `role="status"`/`aria-live`. ThemeContext kommentiert das Schweigen ausdrücklich. Der Export-Button zeigt nur während des laufenden Exports „Exporting…“, aber keinen Fehlerstatus.

**Evidenz:** Siehe Locations; `ThemeManagementSection.tsx:151-155` besitzt zwar einen sichtbaren Fehlerbereich, der für die verschluckten Teilpfade aber nicht gesetzt wird.

**Auswirkung:** Nutzer von Screenreadern erhalten nach erfolgreichen Auto-Saves oder fehlgeschlagener Theme-/PDF-Persistenz keine zuverlässige Rückmeldung. Der UI-Zustand kann von einem serverseitig nicht gespeicherten Zustand abweichen.

**Root Cause:** Asynchrone Statusverträge sind pro Komponente ad hoc statt als gemeinsamer, rollenbasierter Vertrag implementiert.

**Gegenmaßnahme:**
- Einen kleinen `AsyncStatus`-Primitive mit `status|alert`, `aria-busy` und Retry-Aktion einführen.
- Theme-Lokalzustand und Serverpersistenz getrennt behandeln: bei Fehler „lokal aktiv, nicht gespeichert“ melden und Retry anbieten.
- ThemeManagement-Fehler pro Aktion sichtbar machen; Delete erst nach erfolgreichem Server-OK schließen.
- Export-Fehler als `role="alert"` ausgeben; Erfolg nach Datei-Download als `role="status"`.
- Die beiden Theme-Default-Selects mit echten `<label>`-Assoziationen versehen.

**Aufwand:** M.

**Alternativen:** Nur sichtbare Farbe/Text ohne ARIA: erfüllt WCAG 4.1.3 nicht zuverlässig.

**Confidence:** Hoch.

**Validierung/Messplan:** Fehler und Erfolg je Async-Aktion in Unit- und Browser-Tests mit `getByRole("status"/"alert")` prüfen; Screenreader-Test muss die Nachricht einmal ansagen, ohne Fokus zu stehlen.

### FEA-010 — Trace-Filterchips kombinieren `switch` mit `aria-pressed`

**WCAG criterion:** 4.1.2 Name, Role, Value  
**Conformance level:** A  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/shared/ArtifactInspector/TracePanel.tsx:289-327`; `frontend/src/components/shared/ArtifactInspector/TracePanel.module.css:30-65`  
**Problem:** Jeder Filterchip erhält `role="switch"`, aber `aria-checked` fehlt; stattdessen wird `aria-pressed` gesetzt. Ein Switch muss seinen Zustand über `aria-checked` exponieren. Der aktuelle ESLint-Lauf bestätigt den Required-ARIA-Prop-Fehler.

**Assistive tech:** Screenreader-Rollen-/Zustandsansage; NVDA, JAWS und VoiceOver.

**Fakt:** `role="switch"` und `aria-pressed` sind zwei verschiedene Rollenverträge. NVDA, JAWS und VoiceOver interpretieren den fehlenden Checked-State nicht einheitlich.

**Evidenz:** `TracePanel.tsx:301-312`; ESLint: `jsx-a11y/role-has-required-aria-props` bei `TracePanel.tsx:304`.

**Auswirkung:** Nutzer erkennen, dass ein Filter optisch aktiv ist, können seinen On-/Off-Status aber nicht zuverlässig aus dem Screenreader-Baum ableiten.

**Root Cause:** Ein Toggle-Chip wurde als Switch etikettiert, die ARIA-Properties aber aus einer Press-Button-Implementierung übernommen.

**Gegenmaßnahme:** Bevorzugt native Checkboxen in einer beschrifteten `fieldset`/`legend`- oder native Button-Toggle-Gruppe verwenden. Falls die Chips als Switch bleiben: `aria-checked={active}` setzen und `aria-pressed` entfernen.

**Aufwand:** S.

**Alternativen:** `role="button"` plus `aria-pressed` beibehalten: zulässig, wenn die Chips als Drucktasten statt als Switches modelliert werden.

**Confidence:** Hoch.

**Validierung/Messplan:** Accessibility-Tree und Rollenname/-Zustand mit NVDA, JAWS und VoiceOver prüfen; der aktive Zustand muss als `checked` beziehungsweise `pressed` eindeutig angekündigt werden.

### FEA-011 — `MultiEnum`-Gruppe ist nicht programmatisch mit ihrem Feldlabel verbunden

**WCAG criterion:** 1.3.1 Info and Relationships; 3.3.2 Labels or Instructions  
**Conformance level:** A  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/shared/ArtifactForm/fields/MultiEnum.tsx:17-53`; `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx:56-97`; `frontend/src/test/ArtifactFormFields.test.tsx:209-239`  
**Problem:** `FieldShell` rendert ein `<label htmlFor={testId}>`; `MultiEnum` setzt die entsprechende ID auf ein `div[role="group"]`, nicht auf ein labelierbares Steuerelement. Die Gruppe referenziert weder Label noch Help-/Fehlertexte mit `aria-labelledby`/`aria-describedby`.

**Assistive tech:** Screenreader-Formularnavigation und Gruppenansage.

**Fakt:** Native `label.htmlFor` kann die `div`-Gruppe nicht beschriften. Die Option-Buttons sind zwar fokussierbar, die Gruppenbedeutung und der erforderliche Zustand werden aber nicht zuverlässig aus dem Feldkontext abgeleitet.

**Evidenz:** `FieldShell.tsx:68-94`; `MultiEnum.tsx:23-30,34-48`.

**Auswirkung:** Screenreader können die Optionen als unbenannte Gruppe bzw. als Buttons ohne Feldkontext melden. Die Fehler- und Help-Beziehung des wiederverwendbaren Formularfelds fehlt.

**Root Cause:** Das gemeinsame Label-Contract nimmt an, jedes Child sei ein einzelnes native Control; MultiEnum rendert mehrere Controls in einer Gruppe.

**Gegenmaßnahme:** Native Checkboxen in einem `<fieldset>` mit `<legend>` rendern und Help/Fehler über `aria-describedby` an die Gruppe oder jedes Control binden. Alternativ die bestehende Buttongruppe behalten und `aria-labelledby={`${testId}-label`}`, `aria-describedby` und `aria-required` vollständig setzen.

**Aufwand:** S–M.

**Alternativen:** Nur `aria-label` am Feldnamen: verliert Help-/Fehlerbeziehung und dupliziert den Labeltext.

**Confidence:** Hoch.

**Validierung/Messplan:** Formular mit Required-MultiEnum, Help und Serverfehler in NVDA/JAWS/VoiceOver prüfen; Gruppenname, Optionen, Required-State und Fehler müssen in einem Durchlauf verständlich sein.

### FEA-012 — Klickbare ArtifactRow exponiert Selection auf einer Buttonrolle über `aria-selected`

**WCAG criterion:** 4.1.2 Name, Role, Value  
**Conformance level:** A  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx:102-145,168-175`; `frontend/src/components/shared/ArtifactRow/ArtifactRow.test.tsx:106-117`; aktuelle Direktaufrufer `frontend/src/components/IcdView/IcdList.tsx:106-119` und `frontend/src/components/DiagramView/DiagramList.tsx:188-201`  
**Problem:** Wenn `ArtifactRow` anklickbar ist, erhält die `div` `role="button"` und `aria-selected`. `aria-selected` ist auf der Buttonrolle nicht der zulässige Zustand; der vorhandene Test fixiert diese falsche Zuordnung.

**Assistive tech:** Screenreader-Buttonsemantik und Zustandsansage.

**Fakt:** Die Komponente behandelt den Selection-Zustand als Rolle „button“ statt als `aria-pressed` oder `aria-current`. Die Tree-Aufrufer ohne eigenes `onClick` bleiben vom Problem unberührt, weil `WorkspaceTree` den Treeitem-Kontext besitzt.

**Evidenz:** `ArtifactRow.tsx:129-145`; `ArtifactRow.test.tsx:106-117`; Direktnutzung in ICD/Diagram.

**Auswirkung:** NVDA/JAWS können „button“ ohne verlässbaren Selected-State melden; VoiceOver kann die Auswahl nur visuell bzw. aus dem Layout ableiten.

**Root Cause:** Das Shared Row-Primitive vereinheitlicht Layout und Interaktion, kennt aber nicht sauber den Unterschied zwischen Tree-Auswahl, Aktivierungsbutton und Navigation.

**Gegenmaßnahme:** Für klickbare Rows eine native `<button>`- oder, wenn Navigation, eine native `<a href>`-Struktur verwenden und `aria-pressed` beziehungsweise `aria-current` setzen. Wegen des eingebetteten Copy-Controls `ArtifactId` nicht als verschachtelte Aktion in einem Button behalten; Copy-Button als sibling außerhalb der Row platzieren oder `readOnly` aktivieren und die gewünschte Aktion separat anbieten.

**Aufwand:** M.

**Alternativen:** `role="option"`/`aria-selected` in einer `listbox`: verlangt Listbox-Keyboardnavigation und ist hier nicht nötig.

**Confidence:** Hoch.

**Validierung/Messplan:** ICD- und Diagram-Liste mit Tastatur und Screenreader testen; Auswahl muss als pressed/current verständlich sein, und Copy/Delete dürfen nicht versehentlich die Row-Navigation auslösen.

### FEA-013 — Single-Interview-Formalize hat weder Statusmeldung noch Double-Submit-Schutz

**WCAG criterion:** 4.1.3 Status Messages  
**Conformance level:** AA  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/InterviewWidget/InterviewArtifactPane.tsx:15-53`; Vergleich `frontend/src/components/InterviewWidget/InterviewChatPane.tsx:54-58,100-118,152-165`  
**Problem:** `formalize()` setzt weder Lade- noch Fehlerstatus und deaktiviert den Button nicht. Ein Fehler wird als unbehandelte Promise-Rejection behandelt; der Nutzer erhält keine sichtbare oder programmatische Rückmeldung. Die Multi-Variante im ChatPane besitzt bereits `creating`, `aria-busy`, Spinner und Alert.

**Assistive tech:** Screenreader-Busy-/Fehleransage; visuelle Statuswahrnehmung.

**Fakt:** `InterviewArtifactPane.formalize()` ruft direkt `await interviewsApi.formalize()` auf; es gibt keinen `try/catch`, keinen `creating`-State und kein `disabled={creating}`.

**Evidenz:** `InterviewArtifactPane.tsx:22-28,39-51`; der bestehende Positivpfad `InterviewChatPane.tsx:100-118,156-164`.

**Auswirkung:** Ein Formalize-Fehler erscheint für Screenreader und Sehende Nutzer nicht zuverlässig; wiederholte Klicks können mehrfach schreiben, bevor der erste Request abgeschlossen ist.

**Root Cause:** Single- und Multi-Mode haben denselben Backend-Vertrag, aber zwei unterschiedliche UI-State-Verträge.

**Gegenmaßnahme:** Den Multi-Mode-State als shared Formalize-Controller extrahieren oder zumindest dieselben Zustände in Single-Mode übernehmen: `creating`, `error`, `aria-busy`, Spinner, disabled Button und Retry.

**Aufwand:** S–M.

**Alternativen:** Nur einen globalen Toast verwenden: Toast ist keine zuverlässige Statusmeldung, wenn er zeitlich aus dem Fokus- und Dialogkontext verschwindet.

**Confidence:** Hoch.

**Validierung/Messplan:** Mock-Request 1 Sekunde hängen lassen, dann ablehnen; Erwartung: genau ein Request, Button disabled/busy, `role="alert"` sichtbar und nach Retry erfolgreich eine Statusmeldung.

### FEA-014 — Mobiler Sidebar-Drawer lässt Fokus hinter die sichtbare Overlay-Fläche wandern

**WCAG criterion:** 2.4.11 Focus Not Obscured (Minimum)  
**Conformance level:** AA  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/NavigationShell/SidebarNavigation.tsx:177-180,439-456,470-495`; `frontend/src/components/NavigationShell/SidebarNavigation.module.css:41-69`  
**Problem:** Escape und `aria-expanded` sind vorhanden. Beim Öffnen wird der Fokus aber nicht in den Drawer gesetzt, der Hintergrund erhält kein `inert`, und der Drawer verwendet keine Fokusfalle. Nach dem Tab durch die Sidebar kann der Fokus auf Controls im visuell verdeckten Hauptinhalt landen.

**Assistive tech:** Tastaturfokus; Screenreader-Fokusmodus; VoiceOver Touch Exploration.

**Fakt:** Das Overlay ist visuell modal, der Code kommentiert es aber ausdrücklich als nicht fokussierbare, nicht modale Fläche. Der Hintergrund bleibt interaktiv und sichtbar verdeckt.

**Evidenz:** `SidebarNavigation.tsx:445-456` — Escape; `:470-490` — Burger/Backdrop; `:492-495` — offene Nav ohne Fokusübernahme; `SidebarNavigation.module.css:45-69` — Drawer plus Backdrop.

**Auswirkung:** Tastatur- und Screenreaderbenutzer können den sichtbaren Kontext verlassen, ohne den Hintergrund bewusst zu aktivieren. NVDA/JAWS melden den Fokussprung, VoiceOver kann beim Touch Exploration den verdeckten Hintergrund trotzdem erreichen.

**Root Cause:** Visuelles Modalverhalten und DOM-/Fokusverhalten wurden als getrennte Entscheidungen modelliert.

**Gegenmaßnahme:** Unterhalb 1024 px einen echten modalen Drawervertrag herstellen: erster sinnvoller Nav-Fokus beim Öffnen, Fokusfalle, `inert`/`aria-hidden` am restlichen Shell-Inhalt, Escape schließt, Fokus zurück auf den Burger. Alternativ das Backdrop entfernen und den Drawer tatsächlich nicht modal machen.

**Aufwand:** M.

**Alternativen:** Nur Escape beibehalten: löst den Fokussprung nicht.

**Confidence:** Hoch für die DOM-/Fokuslücke, mittel für die genaue Screenreader-Ausgabe.

**Validierung/Messplan:** Mobile Viewport öffnen, mit Tab/Shift+Tab alle Fokuspositionen protokollieren; kein Fokuspunkt darf vollständig vom Backdrop verdeckt sein. Escape und Fokus-Rückgabe testen.

### FEA-015 — ICD-Ähnlichkeitsliste ist nicht per Tastatur bedienbar

**WCAG criterion:** 2.1.1 Keyboard  
**Conformance level:** A  
**Severity:** minor (P2)  
**Location:** `frontend/src/components/IcdView/IcdDetailPane.tsx:425-487,455-483`; zugängliche Parallelvariante `frontend/src/components/IcdView/SimilarIcdsPanel.tsx:125-149`  
**Problem:** Die tatsächlich verwendete lokale Similar-Icds-Funktion rendert jedes Ergebnis als `<li onClick>`. Sie ist weder fokussierbar noch hat sie Rolle, Tabindex oder Keyboard-Handler. ESLint meldet den Required-Keyboard-Listener.

**Assistive tech:** Tastatur; Screenreader-Navigation zu den Ergebnissen.

**Fakt:** `IcdDetailPane` verwendet die lokale Funktion; die native Button-Variante in `SimilarIcdsPanel.tsx` ist zwar barriereärmer, wird aber nicht importiert.

**Evidenz:** `IcdDetailPane.tsx:465-481` — klickbares `li`; `SimilarIcdsPanel.tsx:130-147` — native Buttons mit derselben fachlichen Aktion.

**Auswirkung:** Tastaturbenutzer können die Ähnlichkeitsnavigation nicht bedienen; die Funktion bleibt für diese Nutzergruppe unentdeckbar.

**Root Cause:** Eine zugängliche neue Panel-Variante wurde eingeführt, während die bestehende lokale Variante im Detail-Paneer weiter gerendert wird.

**Gegenmaßnahme:** Die native `SimilarIcdsPanel`-Variante importieren oder die lokale Liste auf native Buttons umstellen. Zusätzlich die Similarity-Überschrift als echte Abschnittsüberschrift und Treffer als echte Buttons mit verständlichem Accessible Name erhalten.

**Aufwand:** S.

**Alternativen:** `tabIndex=0` und `onKeyDown` am `li`: behebt nur die Tastatur, nicht die erste Regel der zugänglichen nativen HTML-Struktur.

**Confidence:** Hoch.

**Validierung/Messplan:** ICD-Detail mit mindestens zwei Similarity-Treffern öffnen, ausschließlich per Tab/Enter navigieren; Screenreader muss Name, Similarity-Score und auslösende Aktion melden.

### FEA-016 — TestRun-Create-Dialog konkurriert mit zwei Fokussierungsmechanismen

**WCAG criterion:** 2.4.3 Focus Order; 2.4.7 Focus Visible  
**Conformance level:** AA  
**Severity:** minor (P3)  
**Location:** `frontend/src/components/TestRuns/TestRunsList.tsx:229-260`; shared `frontend/src/components/shared/Dialog/Dialog.tsx:120-162`; Vergleich `frontend/src/components/RequirementEditors/RequirementEditors.tsx:228-240`  
**Problem:** Das Create-Dialog erhält sowohl `initialFocusRef={nameInputRef}` als auch `autoFocus` am Input. Der Shared Dialog setzt Fokus über seine Fokusfalle; der native Autofocus-Mechanismus läuft als separater Browserschritt und kann die Reihenfolge oder den sichtbaren Fokusring variieren.

**Assistive tech:** Tastatur und Screenreader-Fokus; sichtbarer Fokusring für Nutzer mit Sehbeeinträchtigung.

**Fakt:** Andere Create-Dialoge im Projekt haben den doppelten Mechanismus bereits entfernt und dokumentieren genau diese Race-Bedingung.

**Evidenz:** `TestRunsList.tsx:233-260`; `RequirementEditors.tsx:228-240` erklärt die bereits etablierte Korrektur.

**Auswirkung:** In einzelnen Browsern kann der Fokus nach Dialogöffnung oder nach einem Refetch auf dem falsigen Feld landen. Der Effekt ist begrenzt und vom restlichen Dialog-Fallback abhängig.

**Root Cause:** Die TestRun-Komponente hat den bestehenden Fokusvertrag nicht vollständig übernommen.

**Gegenmaßnahme:** `autoFocus` entfernen und ausschließlich `initialFocusRef` des Shared Dialogs verwenden; Test mit Tab/Shift+Tab und sichtbarem Fokus ergänzen.

**Aufwand:** S.

**Alternativen:** Den Shared Dialog global um native Autofocus-Unterstützung erweitern: der zentrale Vertrag sollte weiterhin eine Quelle für Fokus besitzen.

**Confidence:** Hoch.

**Validierung/Messplan:** Dialog in Chromium, Firefox und Safari öffnen; nach dem Öffnen muss der Fokus im sichtbaren Namensfeld liegen und der Fokusring weder am Body noch am Dialog-Close hängen bleiben.

## 7. Nicht als eigenständige WCAG-Verstöße gewertete Beobachtungen

- `frontend/src/queries/queryClient.ts:5-25` behauptet, 401/403 nicht zu retryen, erkennt aber nur `AUTHENTICATION_REQUIRED`; `ForbiddenError.status === 403` wird daher bis zu dreimal erneut versucht. Das ist ein deterministischer Effizienz-/Unauthorized-Feedback-Bug, aber kein eigener WCAG-Nachweis; die Fehleridentifikation kann nach Abschluss der Retries erfolgen. Technisch sollte `ForbiddenError.status` oder ein stabiler 403-Code zusätzlich geprüft werden.
- `ArtifactRow.tsx:170` und einige DnD-Container werden von ESLint als non-native Interaktion gemeldet. Nicht jeder Linter-Hinweis ist ein WCAG-Fehler; die konkreten Barrieren wurden nur für ArtifactRow, TracePanel und die ICD-Liste als Befunde aufgenommen.
- `Dialog.tsx:148-152` erhält einen Linter-Hinweis für den Backdrop. Backdrop-Klick ist eine zusätzliche Zeigerfunktion; Dialog, Escape, Fokusfalle und Fokus-Rückgabe sind separat getestet.
- `AttributeCatalogDialog.tsx:212-246`, `UserProfileSettings.tsx:128-151` und `WorkspaceSettings.tsx:343-369` enthalten Linter-Hinweise zu Labels, obwohl Inputs verschachtelt beziehungsweise über `htmlFor` verbunden sind. Diese Hinweise wurden nicht als Barrieren behauptet.
- Der mobile Drawer besitzt bereits Escape-Dismissal; der Befund betrifft Fokus- und Overlay-Semantik, nicht fehlende Tastaturbedienung.

## 8. Maßnahmenreihenfolge

### Priorität 1 — Standardpfade vor AA-Sign-off

1. **FEA-002:** zentralen Dirty-Contract und Router-/Unload-Guard einführen.
2. **FEA-004:** Theme-Farben und Importvalidierung korrigieren; keine zentrale Nutzeroberfläche ohne dokumentierte Kontrastmatrix freigeben.
3. **FEA-003:** 16 Legacy-SplitView-Aufrufer auf den Concept-Vertrag migrieren.
4. **FEA-005:** `html.lang` zentral synchronisieren und konkrete Mixed-Language-Defaults bereinigen.
5. **FEA-001:** Skip-Link und Fokusübergabe im AppShell ergänzen.
6. **FEA-006 und FEA-007:** Transcript-Sprecherbeziehungen und Traceability-Degraded-State korrigieren.

### Priorität 2 — Wiederverwendbare Semantik und Statusverträge

1. Trace-Chips auf native Checkboxen umstellen oder korrekt `aria-checked` verwenden.
2. MultiEnum als native Feld-/Checkboxgruppe mit Label, Help und Fehlerbezug modellieren.
3. ArtifactRow für Direktinteraktion auf native Button/Link-Struktur migrieren.
4. Interview-Formalize, Settings-, Theme- und Exportstatus vereinheitlichen.
5. Globale Suche entweder auf native Buttons vereinfachen oder vollständig als Combobox implementieren.
6. Mobile Drawer und ICD-Ähnlichkeitsnavigation an die vorhandenen positiven Primitive angleichen.

## 9. Empfohlene Abnahmekriterien

- Ein Tastaturstart erreicht den Skip-Link als ersten Fokuspunkt; die Aktivierung setzt den Fokus in den sichtbaren Hauptinhalt.
- Dirty-Drafts in allen vier Artefakt-Editoren und im TestRun-Grid überleben Sidebar-Navigation, Router-Back, Tabwechsel und Reload oder werden vor dem Verlust bestätigt.
- Bei 320 px und 200 % Zoom ist in jedem Legacy-SplitView-Flow genau Liste oder Detail sichtbar; Detail und Liste lassen sich per Tastatur in beide Richtungen wechseln.
- Alle real verwendeten Theme-Paare erreichen 4,5:1 für Text beziehungsweise 3:1 für Fokus/UI; Custom-Import mit absichtlich schlechtem Kontrast wird serverseitig abgewiesen.
- `document.documentElement.lang` entspricht nach Init, Workspace-Restore und jedem Sprachwechsel der sichtbaren Sprache.
- NVDA, JAWS und VoiceOver geben Interview-Sprecher, Suchstatus, Theme-Status, Formularfehler und Filterzustände ohne Fokusverlust aus.
- Traceability zeigt bei jedem fehlgeschlagenen Teilservice einen sichtbaren und programmatisch erkennbaren Degraded-State; eine nicht geprüfte Zyklusprüfung wird nie als leer dargestellt.
- `npm run lint` enthält keine produktive Warnung mit `jsx-a11y/role-has-required-aria-props` oder `click-events-have-key-events` an einem realen interaktiven Element.
- Ein gezielter Browser-Accessibility-Lauf (Axe plus manuelle Tastaturprüfung) wird für die geänderten Flows als Evidenz archiviert; ein einzelner Screenreader-Lauf ersetzt die NVDA/JAWS/VoiceOver-Matrix nicht.

## 10. Screenreader- und Browser-Testleitfaden

### 10.1 NVDA/JAWS unter Windows

1. **Browse-Mode:** Landmarken, Heading-Level, Transcript-Sprecher, Tabellenzeilen und Formulargruppen prüfen. NVDA und JAWS können `aria-selected` beziehungsweise `aria-pressed` bei falscher Rollenkombination unterschiedlich interpretieren; deshalb darf kein Test nur die DOM-Attribute prüfen.
2. **Focus-Mode:** Alle interaktiven Elemente mit Tab/Shift+Tab erreichen. Bei Dirty- und Confirm-Dialogs prüfen, dass der Fokus im Dialog bleibt und nach Abbruch zurück auf dem auslösenden Control landet.
3. **NVDA/JAWS-Unterschied:** NVDA meldet virtualisierte Tree-Rows und `aria-activedescendant` nicht in jedem Browser gleich; JAWS reagiert auf nicht standardkonforme Listbox-Eigentümer besonders streng. Die globalen Such- und Tree-Pfade deshalb in beiden Readern testen.
4. **Status:** `role="status"` und `role="alert"` müssen einmal und ohne doppelte Vorlesung erkannt werden; kein sichtbarer Erfolg darf ausschließlich farblich erkennbar sein.

### 10.2 VoiceOver unter macOS/iOS

1. **Rotor:** Überschriften, Landmarken, Tabellen, Formulare und Transcript prüfen. VoiceOver kann eine defekte Listbox als statische Liste behandeln, während NVDA/JAWS den fehlenden aktiven Wert anders darstellen.
2. **Touch Exploration:** Mobile Drawer öffnen und prüfen, dass verdeckte Hintergrundcontrols nicht fokussiert werden; der Drawer muss entweder echtes Modalverhalten oder sichtbar nicht-modales Verhalten besitzen.
3. **Voice Control:** Labels wie „Zum Hauptinhalt springen“, „Kopie löschen“ und „Interviewchat“ müssen eindeutig ansprechbar sein; rein visuelle Symbole wie „✕“, „📌“ und „☰“ benötigen im Zielzustand zusätzliche Namen.

### 10.3 Divergenzen, die nicht als eine Referenz behandelt werden dürfen

- NVDA/JAWS können Screenreader-Navigation und `aria-activedescendant` in Firefox/Chrome unterschiedlich behandeln.
- VoiceOver interpretiert `role="switch"` ohne `aria-checked` nicht zuverlässig als fehlerhaften Zustand; manche Clients geben stattdessen nur den Accessible Name aus.
- Browser-Screenreader-Paare und Tastatur-only-Prüfung sind getrennte Testdimensionen: „mit Maus erreichbar“ beweist weder 2.1.1 noch 1.4.10.
- Zoom/Reflow, High-Contrast/Windows High Contrast und `prefers-reduced-motion` sind eigene Prüfungen; sie dürfen nicht aus dem Desktop-Default-Test abgeleitet werden.

## 11. Verifikationsstatus und Grenzen

- **Statische Prüfung:** Quelltext, CSS, Locale-Dateien, Theme-Fixtures, Tests und relevante Backend-Theme-Regeln wurden repo-relativ geprüft.
- **Kontrastprüfung:** Werte in Abschnitt 5 wurden reproduzierbar aus den aktuellen Theme-Hexwerten berechnet; keine geschätzten WCAG-Werte.
- **Gezielte Vitest-Läufe:** 24 relevante Testdateien mit 277 Tests gestartet; 272 Tests bestanden. 5 Tests in `RightSidebar.test.tsx` schlugen in der lokalen Node-26.7.0-Umgebung fehl, weil `window.localStorage` dort nicht verfügbar ist (`Cannot read properties of undefined (reading 'clear')`). Das ist eine Testumgebungs-/Fixture-Infrastrukturabweichung, kein grüner Lauf und kein Produktbefund.
- **Lint:** `npm run lint` endete mit 0 Fehlern und 290 Warnungen. Die konkrete ARIA-Warnung für `TracePanel.tsx:304` wurde übernommen; triviale oder gleichwertig native Linter-Hinweise wurden nicht automatisch als WCAG-Verstöße klassifiziert.
- **Docker:** `rtk docker compose -f deploy/docker-compose.yml ps --format json` lieferte am 2026-09-24 keine laufenden Dienste. Deshalb wurden keine Live-UI-, Axe-, Browser- oder Screenreader-Ergebnisse behauptet.
- **Nicht ausgeführt:** vollständige Frontend-Suite, vollständige Playwright-Suite, NVDA/JAWS/VoiceOver-Sitzung und manueller Reflow-Test. Diese bleiben nach dem Fix erforderlich.
- **Arbeitsbaum:** Vor Berichtserstellung bestanden bereits untracked `.serena/memories/*` und die Berichte 02–04; diese wurden nicht verändert.

## 12. Zusammenfassung nach WCAG-Stufe

| Höchste betroffene Stufe | Befunde | Schwereverteilung |
|---|---:|---|
| Level A | 7 | 2 P1, 5 P2 |
| Level AA | 9 | 5 P1, 3 P2, 1 P3 |
| Level AAA | 0 | 0 |
| **Gesamt** | **16** | **0 P0, 7 P1, 8 P2, 1 P3** |

**Höchste Schwere:** major/P1, wegen standardpfadweiter Navigation-, Datenverlust-, Responsive-, Kontrast-, Sprach- und Datenintegritätslücken.  
**Top-Barrieren:** Tastatur-Bypass, Dirty-State über Route/Unload, mobile List/Detail-Navigation, berechnete Theme-AA-Verstöße, fehlerhafte Dokument-Sprache, Transcript-Sprecherbeziehungen und als leer getarnte Traceability-Teilausfälle.

## 13. Abschlussstatus

```text
STATUS: done
RESULT: Frontend-, UX- und Accessibility-Audit abgeschlossen; 16 WCAG-gebundene Befunde (0 P0, 7 P1, 8 P2, 1 P3) mit Code-, Test- und berechneten Kontrastbelegen dokumentiert. Anwendungsdateien wurden nicht verändert; Live- und Screenreader-Nachweise bleiben nach Behebung erforderlich.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/06-frontend-ux-accessibility-and-design-system.md
NEXT: [Review, Developer fix, targeted tests, browser accessibility run]
```

## 14. Quellenverzeichnis

### Navigation und Shell
- `frontend/src/components/NavigationShell/NavigationShell.tsx:35-228`
- `frontend/src/components/NavigationShell/SidebarNavigation.tsx:41-789`
- `frontend/src/components/NavigationShell/SidebarNavigation.module.css:14-666`
- `frontend/src/components/NavigationShell/AppShell.module.css:1-23`
- `frontend/index.html:1-13`

### Editoren und Dirty-State
- `frontend/src/hooks/use-form-dirty.ts:1-38`
- `frontend/src/components/RequirementEditors/RequirementEditors.tsx:70-842`
- `frontend/src/components/NeedsEditors/NeedsEditors.tsx:60-563`
- `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx:100-874`
- `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx:60-462`
- `frontend/src/components/PermissionMatrix/PermissionMatrixEditor.tsx:45-171`

### Responsive und Inspector
- `frontend/src/components/SplitView/SplitView.tsx:1-829`
- `frontend/src/components/SplitView/SplitView.test.tsx:1-211`
- `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx:1-482`
- `frontend/src/components/shared/ArtifactInspector/TracePanel.tsx:1-438`
- `frontend/src/components/shared/ArtifactInspector/DiffPanel.tsx:1-211`
- `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx:1-553`
- `frontend/src/components/ArtifactDiff/ArtifactDiff.module.css:130-283`
- `e2e/tests/artifact-diff.spec.ts:1-204`

### TestRuns und Traceability
- `frontend/src/components/TestRuns/TestRunsList.tsx:1-508`
- `frontend/src/components/TestRuns/TestRunResultEntryGrid.tsx:1-517`
- `frontend/src/components/TestRuns/TestRunDetailEditor.tsx:1-403`
- `e2e/tests/test-runs.spec.ts:1-150`
- `frontend/src/components/TraceabilityView/TraceabilityView.tsx:250-856`
- `frontend/src/components/TraceabilityView/TraceabilityView.smoke.test.tsx:1-400`

### Settings und Themes
- `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:1-669`
- `frontend/src/components/WorkspaceSettings/WorkspaceSettings.module.css:1-178`
- `frontend/src/components/SystemSettings/SystemSettings.tsx:1-176`
- `frontend/src/components/SystemSettings/ThemeManagementSection.tsx:1-247`
- `frontend/src/context/ThemeContext.tsx:1-211`
- `backend/admin_ops/theme_rest.py:62-204`
- `backend/admin_ops/models.py:146-192`
- `backend/admin_ops/fixtures/themePalettes.light.json:1-239`
- `frontend/src/styles/tokens.css:1-1559`
- `frontend/src/styles/global.css:1-255`
- `frontend/src/test/theme-contrast.test.ts:1-498`

### Formulare und i18n
- `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx:1-115`
- `frontend/src/components/shared/ArtifactForm/fields/MultiEnum.tsx:1-56`
- `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx:1-202`
- `frontend/src/components/shared/ArtifactId.tsx:1-70`
- `frontend/src/i18n/index.ts:1-29`
- `frontend/src/context/WorkspaceContext.tsx:296-347`
- `frontend/src/test/i18n-parity.test.ts:1-205`
- `frontend/src/components/InterviewWidget/InterviewChatPane.tsx:1-210`
- `frontend/src/components/InterviewWidget/InterviewArtifactPane.tsx:1-55`
- `frontend/src/components/InterviewEditors/InterviewEditors.tsx:1-183`

### Screenreader- und Testreferenzen
- `frontend/src/components/shared/Dialog/Dialog.tsx:1-214`
- `frontend/src/components/shared/Dialog/Dialog.test.tsx:1-677`
- `frontend/src/components/shared/CreateTraceLinkDialog/link-type-listbox.tsx:1-478`
- `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx:810-1272`
- `e2e/tests/overlay-dismissal.spec.ts:1-94`
- `e2e/tests/ui-konzept-gates.spec.ts:130-163`
- `docs/se/reports/TESTPLAN_v1.8.0-beta.15.md:301-345`
