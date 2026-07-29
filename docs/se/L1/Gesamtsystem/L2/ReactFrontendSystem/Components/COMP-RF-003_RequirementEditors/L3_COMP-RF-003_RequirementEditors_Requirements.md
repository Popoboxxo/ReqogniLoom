---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:50:00Z"
schema_version: "1.0.0"
---
# L3 RequirementEditors Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RF-003_RequirementEditors
> **Parent:** L2_ReactFrontendSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die RequirementEditors-Komponente ermöglicht Inline-Editing von Requirement-Feldern (Title, Description, Category), zeigt und verwaltet Workflow-States mit Transitionen, und präsentiert bidirektionale TraceLink-Seitenbars. Editor-Wechsel erfolgt in < 500ms. Alle Änderungen werden per PATCH an das Backend synchronisiert.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Komponenten und Module

- **`RequirementEditors` (React.FC):** Main Editor-Komponente mit Tabs/Sections.
- **`RequirementDetailEditor` (React.FC):** Inline-Editor für Title, Description, Category.
- **`MarkdownPreview` (React.FC):** Toggle zwischen Edit/Preview für Description.
- **`WorkflowStateTransition` (React.FC):** Dropdown für State-Übergänge.
- **`TraceabilityPanel` (React.FC):** Seitenleiste mit Upstream/Downstream Links.
- **`RequirementDataLoader` (Hook):** `useRequirementData()` — lädt Requirement + TraceLinks.

### 2.2 Datenstrukturen

**RequirementEditor-State:**
```typescript
interface RequirementEditorState {
  requirementId: UUID;
  requirement: Requirement;
  isEditing: boolean;
  pendingChanges: Partial<Requirement>;
  workflowState: WorkflowState;
  availableTransitions: string[];
  traceLinks: {
    upstream: TraceLink[];
    downstream: TraceLink[];
  };
  isSaving: boolean;
  lastSaveTime?: number;
  error?: Error;
}

interface Requirement {
  id: UUID;
  title: string;
  description: string;  // Markdown
  category?: string;
  status: string;
  createdAt: DateTime;
  modifiedAt: DateTime;
}
```

**Markdown-Editor-State:**
```typescript
interface MarkdownEditorState {
  content: string;
  isPreviewMode: boolean;
  isDirty: boolean;
}
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RF003-001 (Inline-Editing) | Click auf Title/Description aktiviert contentEditable oder Input-Feld. Blur oder Save-Button triggt PATCH-Request. Response aktualisiert Editor-State. |
| REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition) | WorkflowStateTransition zeigt Current-State als Badge. Dropdown listet Backend-valide nächste States. Klick triggt PATCH /api/v1/requirements/{id}/workflow-state. |
| REQ-L3-RF003-003 (TraceabilityPanel) | TraceabilityPanel zeigt Upstream/Downstream Links gruppiert. Klick auf Link triggt Navigation zu verknüpftem Artefakt. |
| REQ-L3-RF003-004 (Editor-Performance < 500ms) | `useRequirementData()` prefetcht. Editor-Switch ist Komponenten-Re-Mount oder State-Update, kein Page-Reload. p95 < 500ms unter Last. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RF-INT-001:** NavigationShell aktiviert RequirementEditors.
- **IF-RF-INT-003:** NavigationShell übergibt `{artifact_id, artifact_type}` als Props.
- **IF-RF-INT-002:** I18nService liefert Labels/Translations.

**Ausgänge (Outbound):**
- **IF-RF-EXT-OUT-001:** REST API:
  - `GET /api/v1/requirements/{id}` — Laden
  - `PATCH /api/v1/requirements/{id}` — Update Fields
  - `PATCH /api/v1/requirements/{id}/workflow-state` — State-Transition
  - `GET /api/v1/requirements/{id}/trace-links` — TraceLinks

---

## 5. Architectural Rationale

**ADR-L3-RF-005 — Inline-Editing statt Modal-Dialog**

*Entscheidung:* Bearbeitbare Felder sind direkt im Detailview sichtbar (contentEditable oder Input-Felder), kein separater Modal.

*Alternative (abgelehnt):* Modal-Dialog für jeden Edit. Grund: Höhere Komplexität, UI-Klicks, weniger fluid.

*Rationale:* REQ-L3-RF003-001 fordert Inline-Editing. Bessere UX, schneller.

---

**ADR-L3-RF-006 — Workflow-State-Validierung vom Backend**

*Entscheidung:* Verfügbare nächste States kommen vom Backend (abhängig von Current-State + Workspace-Regeln), nicht hardcoded im Frontend.

*Alternative (abgelehnt):* Frontend enthält Workflow-Definition. Grund: Fehleranfälligkeit, Synchronisierungsprobleme.

*Rationale:* REQ-L3-RF003-002 fordert „nur valide Transitionen". Backend ist Quelle der Wahrheit.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
