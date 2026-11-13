# Triage: V4 (Memory-Statusseite) und V6 (Allokations-/Level-Filter)

**Datum:** 2026-11-14 · **Bezug:** Vorschlagsliste „Plan-Leftovers" (Stand 2026-11-10)
**Art:** reine Befundaufnahme — keine Umsetzung, keine Issues.

Belege beziehen sich auf `origin/main` (`0d8bdbc4`); Zeilennummern können driften,
die genannten Symbole/Funktionen sind der stabilere Anker.

---

## V4 — Gibt es eine Admin-Statusseite „Memory"?

**Befund: vorhanden — der Vorschlag ist erledigt und kann geschlossen werden.**

Es gibt drei ergänzende Oberflächen:

| Oberfläche | Ort | Beleg |
|---|---|---|
| Dedizierte Memory-Seite (Workspace-Sicht, alle Scopes) | Route `/memory` | `frontend/src/components/NavigationShell/NavigationShell.tsx:117-118,200`; Menüeintrag `frontend/src/components/NavigationShell/SidebarNavigation.tsx:103` (`nav.memory`, Gruppe „overview"); Komponente `frontend/src/components/Memory/MemoryPage.tsx` |
| Admin-Tab „Memory" in den Systemeinstellungen (Konfiguration + Bestandsverwaltung + Visualisierung) | `SystemSettings` → Tab `memory` | `frontend/src/components/SystemSettings/SystemSettings.tsx:91,179-183`; `MemorySystemSettingsSection.tsx` (Embedding-Provider/Memory-Backend inkl. Honcho-Knobs), `MemoryManagementSection.tsx` (Workspace-Übersicht + Löschen), `MemoryVisualizationSection.tsx` (List/Cluster/Scatter) |
| Admin-Statusanzeige (Health) | System-Health-Dialog | `frontend/src/components/AdminDialog/SystemHealthDialog.tsx:221-245` rendert **alle** Komponenten des Snapshots generisch; das Backend liefert `memory_embedding` und `memory_backend` als eigene Statuszeilen (`backend/admin_ops/health_rest.py:341-424` bzw. `:427`ff.) |

Damit sind sowohl Konfiguration/Bestand als auch ein echter *Status* (ok/degraded/down,
Embedding-Provider + Backend-Health) für System-Admins sichtbar.

**Offener Rest (nicht Teil von V4):** `MemorySystemSettingsSection.tsx:11-18`
dokumentiert eine bekannte Lücke — einige Honcho-Felder werden vom
Backend-Serializer (`SystemMemorySettingsWriteSerializer`) noch nicht
angenommen/ausgegeben, ein Speichern dieser Felder ist serverseitig ein No-op.

---

## V6 — Sind `?allocated=` / `?level=` und die Ebene in Requirement-Liste und Trace-Matrix nutzbar?

**Befund: teils. `allocated` ja (Liste vollständig, Matrix nur „nicht allokiert"),
`level` nein (nur Backend, keine UI-Filterung), Ebenen-Anzeige nur in der Liste.**

### Backend (Referenz)

`GET /api/v1/requirements/` wertet beide Parameter aus:
`backend/rest_api/views.py:1930-1947` — `allocated` über `parse_bool_param`
(tri-state), `level` über `parse_int_param(..., minimum=1, maximum=4)`, beide
werden an `RequirementService.list_requirements(...)` durchgereicht
(`views.py:1948-1956`).

### Requirement-Liste (UI)

- **`?allocated=` — nutzbar, dreistufig (alle / allokiert / nicht allokiert):**
  `frontend/src/api/requirements.ts:73-87` (`RequirementListOptions.allocated`),
  `frontend/src/queries/requirements.ts:38-49` (`useRequirementsList`),
  `frontend/src/components/RequirementEditors/useRequirementData.ts:42-75`
  (Mapping `all|allocated|unallocated` → `undefined|true|false`,
  sessionStorage-Key je Workspace `:77-88`), Toolbar-Filter
  `frontend/src/components/RequirementEditors/RequirementList.tsx:462-476`,
  Zustand im Container `RequirementEditors.tsx:90-97`.
- **`?level=` — nicht nutzbar (Lücke):** In der Toolbar existieren nur die
  Filter `category`, `status`, `allocation`
  (`RequirementList.tsx:438-476`); `RequirementListOptions` kennt kein `level`
  (`api/requirements.ts:73-87`), ebenso wenig `useRequirementsList`
  (`queries/requirements.ts:38-49`). Das Backend-Feature ist damit über die UI
  unerreichbar.
- **Ebenen-Anzeige in der Liste — vorhanden:** Die Zeile zeigt die abgeleitete
  Ebene als Badge-Präfix (`reqTierPrefix`, `RequirementList.tsx:93-110`) und als
  Attribut „Level" inkl. Provenienz (`tier_name`, `level_source`,
  `RequirementList.tsx:657-670`).

### Trace-Matrix (UI)

Zwei Flächen sind zu unterscheiden:

1. `frontend/src/components/TraceabilityView/*` (Link-Liste + Verifikations-Coverage):
   Filter sind Suche, Link-Typ und „nur nicht abgedeckte"
   (`use-traceability-filters.ts:22-30`). **Weder `allocated` noch `level` werden
   hier gefiltert oder angezeigt** (kein `level`-Vorkommen in
   `TraceabilityView.tsx`).
2. `frontend/src/components/ConnectionView/*` (Allokations-Matrix
   `MatrixRenderer.tsx`, Baum/Zwei-Spalten-Ansichten):
   - **`allocated` — nutzbar, aber nur als Negativ-Filter:** `ConnectionFilters.allocated`
     ist serverseitig (`useAllocationView.ts:53-55,96,125-126`), die UI bietet
     ausschließlich den Quick-Filter „Nicht allokiert"
     (`FilterBar.tsx:82-91`, `data-testid="quick-unallocated"`). Ein Filter
     „nur allokierte" existiert nicht.
   - **`level` — nicht nutzbar:** `ConnectionFilters`
     (`useAllocationView.ts:53-78`) hat `tier`, `type`, `category`, `state`,
     `elementSubtree`, `q` — kein `level`. Das Payload-Feld `AllocationRow.level`
     (`api/allocation-view.ts:50`) wird in den Renderern nicht dargestellt; die
     Matrix zeigt Zeilentitel + Lock-Icon, die Spalten sind Architektur-Elemente
     ohne Ebenen-Spalte (`MatrixRenderer.tsx:88-124`).

### Ergebnis in einem Satz

`allocated` ist in der Requirement-Liste vollständig und in der Allokations-Matrix
als „nicht allokiert"-Chip nutzbar; `level` ist im Backend implementiert, in der UI
aber weder filterbar noch in der Matrix sichtbar — die Ebene erscheint nur als
Anzeige-Attribut in der Requirement-Liste. Eine Level-Filterung (Liste **und**
Matrix) wäre damit ein Kandidat für ein eigenes, kleines Feature-Issue.
