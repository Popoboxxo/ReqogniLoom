---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:40:00Z"
schema_version: "1.0.0"
---
# L3 NavigationShell Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RF-001_NavigationShell
> **Parent:** L2_ReactFrontendSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die NavigationShell ist der Haupteinstiegspunkt und das äußere Layout der React-Anwendung. Sie verwaltet das Routing zwischen Funktionsmodulen, implementiert Authentifizierungs-Gates, Top-Level Error Boundaries, Workspace-Selektion, und steuert die Sichtbarkeit von Modulen basierend auf dem Workspace-Preset. Sie koordiniert mit allen Kind-Modulen (DashboardViews, RequirementEditors, ArchitectureEditors).

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Komponenten und Module

- **`NavigationShell` (React.FC):** Root-Komponente mit Layout-Grid (Sidebar, Main Area).
- **`AuthGate` (HOC):** Higher-Order-Component für Token-Validierung.
- **`ErrorBoundary` (React Error Boundary):** Top-Level Exception-Handler.
- **`SidebarNavigation` (React.FC):** Artifact-Tree-Anzeige mit Vorschau/Eingabe.
- **`RouteVisibilityManager` (Utility):** Stellt Routes basierend auf Preset-Features ein.
- **`TokenManager` (Singleton):** Verwaltet Bearer-Token, Refresh, Expiration.
- **`I18nContext` (React Context):** Globales Translations- und Terminologie-Profil.

### 2.2 Datenstrukturen

**NavigationState (React State):**
```typescript
interface NavigationState {
  isAuthenticated: boolean;
  currentUser?: User;
  activeWorkspace?: Workspace;
  selectedArtifactId?: UUID;
  selectedArtifactType?: "requirement" | "architecture_element";
  visibleRoutes: Set<string>;  // basierend auf Preset
  activeTab: "dashboard" | "requirements" | "architecture" | "baselines" | "workflow";
  sidebarOpen: boolean;
  lastError?: ApplicationError;
}
```

**Routing-Konfiguration:**
```typescript
const ROUTES: Route[] = [
  { path: "/", component: DashboardViews, presetRequired: "none" },
  { path: "/requirements", component: RequirementEditors, presetRequired: "standard" },
  { path: "/architecture", component: ArchitectureEditors, presetRequired: "standard" },
  { path: "/baselines", component: BaselinesView, presetRequired: "standard" },
  { path: "/global-baselines", component: GlobalBaselinesView, presetRequired: "extended" },
  { path: "/workflows", component: WorkflowConfig, presetRequired: "extended" },
  { path: "/login", component: LoginPage, public: true },
];
```

**ErrorBoundary State:**
```typescript
interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
  errorInfo?: React.ErrorInfo;
  recoveryActions: Array<{ label: string; action: () => void }>;
}
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RF001-001 (Authentifizierungs-Gate) | `AuthGate` HOC prüft Bearer-Token bevor Route renderiert. 401-Response triggt Auto-Redirect zu `/login`. Unauthenticated-Access → `/login`. |
| REQ-L3-RF001-002 (Preset-gesteuertes Modul-Routing) | `RouteVisibilityManager` stellt Routes basierend auf `workspace.preset` ein. Verborgene Routes zeigen 403/Fehlermeldung bei direktem URL-Zugriff. |
| REQ-L3-RF001-003 (Top-Level Error Boundary) | `ErrorBoundary` fängt unbehandelte Fehler in Kind-Komponenten ab. Zeigt übersetzte Fehlermeldung + Recovery-Optionen (Reload, Zurück). Logged zu Console. |
| REQ-L3-RF001-004 (Artefakt-Selektion und Editor-Aktivierung) | Click auf Tree-Item setzt `selectedArtifactId` und `selectedArtifactType`. Triggt Route-Wechsel zu RequirementEditors oder ArchitectureEditors. Props-Übergabe via Context oder Props. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RF-EXT-IN-001:** Browser-Nutzer interagiert via Mouse/Keyboard mit UI.
- **IF-RF-INT-002:** COMP-RF-006 (I18nService) liefert Translations und Terminologie-Labels.

**Ausgänge (Outbound):**
- **IF-RF-EXT-OUT-001:** REST-API-Aufrufe via axios/fetch (Auth-Endpoints, Workspace-Settings).
- **IF-RF-EXT-OUT-002:** Gerenderte Shell-UI (HTML/CSS/React Virtual DOM).
- **IF-RF-INT-001:** Routing-Events und View-Activation zu Kind-Komponenten.
- **IF-RF-INT-003:** Artefakt-Selektion `{artifact_id, artifact_type}` zu RequirementEditors/ArchitectureEditors.

---

## 5. Architectural Rationale

**ADR-L3-RF-001 — Authentifizierung via HOC statt Middleware**

*Entscheidung:* `AuthGate` HOC wraps protected Routes. Token wird in `TokenManager` (Singleton) gespeichert und bei jedem API-Request im Authorization-Header mitgesendet.

*Alternative (abgelehnt):* Route-Level Guards via React Router Canactivate. Grund: Weniger elegant, schwerer zu debuggen.

*Rationale:* REQ-L3-RF001-001 fordert einfache Token-Validierung. HOC ist idiomatic React für Cross-Cutting Concerns.

---

**ADR-L3-RF-002 — Preset-basierte Route-Sichtbarkeit via Manager-Klasse**

*Entscheidung:* `RouteVisibilityManager` prüft bei jeder Route-Aktivierung, ob `workspace.preset` die Route erlaubt. Verborgene Routes sind nicht erreichbar (404/403).

*Alternative (abgelehnt):* Conditional Rendering in jeder Komponente. Grund: Redundanz, Fehleranfälligkeit.

*Rationale:* REQ-L3-RF001-002 fordert konsistente Enforcement. Zentrale Manager-Klasse ist wartbar.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
