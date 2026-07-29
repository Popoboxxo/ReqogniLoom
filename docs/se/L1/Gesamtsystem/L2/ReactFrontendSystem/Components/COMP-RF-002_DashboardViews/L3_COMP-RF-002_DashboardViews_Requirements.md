---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:45:00Z"
schema_version: "1.0.0"
---
# L3 DashboardViews Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RF-002_DashboardViews
> **Parent:** L2_ReactFrontendSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die DashboardViews präsentieren eine Workspace-Übersicht mit Projekt-Karten. Jede Karte zeigt Requirements-Zähler, Anzahl offener Punkte, und das aktive Terminologie-Profil. Die Komponente lädt Daten vom Backend und rendert die Kartenliste innerhalb von 2 Sekunden. Profilwechsel wirken ohne Seiten-Reload.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Komponenten und Module

- **`DashboardViews` (React.FC):** Main Component, orchestriert Data-Fetching und Card-Rendering.
- **`WorkspaceCard` (React.FC):** Einzelne Projekt-Karte mit Metadaten.
- **`DashboardDataLoader` (Hook):** `useDashboardData()` — lädt Workspace-Liste + Metriken.
- **`TerminologyContext` (React Context):** Globaler Zugriff auf aktives Profil.
- **`MetricsCalculator` (Utility):** Berechnet offene Punkte, Requirements-Zähler.

### 2.2 Datenstrukturen

**Dashboard-State (React State):**
```typescript
interface DashboardState {
  workspaces: WorkspaceWithMetrics[];
  isLoading: boolean;
  error?: Error;
  lastFetchTime: number;
}

interface WorkspaceWithMetrics {
  id: UUID;
  name: string;
  requirementCount: number;
  openItemCount: number;  // Requirements ohne TraceLink
  activeTerminologyProfile: "dev_mode" | "se_mode";
  preset: "minimal" | "standard" | "extended";
}
```

**WorkspaceCard Props:**
```typescript
interface WorkspaceCardProps {
  workspace: WorkspaceWithMetrics;
  onSelect: (workspace: Workspace) => void;
  terminologyProfile: TerminologyProfile;
}
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken) | `useDashboardData()` lädt alle Workspaces + Metriken (requirementCount, openItemCount, activeProfile). WorkspaceCard rendert Metriken. Render < 2 Sekunden. |
| REQ-L3-RF002-002 (Terminologie-Profil-Label-Rendering) | WorkspaceCard benutzt `TerminologyContext` um Labels zu übersetzen (z.B. "Stories" im Dev-Modus, "Requirements" im SE-Modus). Profilwechsel triggert Context-Update → Rerender. |
| REQ-L3-RF002-003 (Navigation von Dashboard zu Workspace-Detail) | Klick auf Karte ruft `onSelect()` auf → NavigationShell wechselt zur Artifact-Tree-Route. Workspace-ID in Router-State. Browser-Back-Button funktioniert. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RF-INT-001:** NavigationShell aktiviert DashboardViews als View und setzt Routing-Events.
- **IF-RF-INT-002:** I18nService liefert `TerminologyProfile` via Context.

**Ausgänge (Outbound):**
- **IF-RF-EXT-OUT-001:** REST API: `GET /api/v1/workspaces` mit Metriken.

---

## 5. Architectural Rationale

**ADR-L3-RF-003 — Metriken aus Backend statt Berechnung im Frontend**

*Entscheidung:* `requirementCount` und `openItemCount` werden vom Backend als Teil der Workspace-Liste geliefert, nicht im Frontend berechnet.

*Alternative (abgelehnt):* Frontend lädt alle Requirements und berechnet lokal. Grund: Netzwerk-Overhead, langsamer.

*Rationale:* REQ-L3-RF002-001 fordert < 2 Sekunden Render-Zeit. Backend-Aggregation ist schneller.

---

**ADR-L3-RF-004 — Terminologie-Labels über Context, nicht Props-Drilling**

*Entscheidung:* `TerminologyContext` wird am Top-Level (NavigationShell) gesetzt. WorkspaceCard liest Labels direkt aus Context.

*Alternative (abgelehnt):* Labels als Props durch Komponenten-Hierarchie weiterleiten. Grund: Mehr Boilerplate, Props-Drilling.

*Rationale:* REQ-L3-RF002-002 erfordert Profilwechsel ohne Rerender-Cascade. Context ist ideal für Global-State.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
