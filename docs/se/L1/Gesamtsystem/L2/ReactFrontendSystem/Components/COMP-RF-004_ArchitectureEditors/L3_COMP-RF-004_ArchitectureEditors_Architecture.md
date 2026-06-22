---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:55:00Z"
schema_version: "1.0.0"
---
# L3 ArchitectureEditors Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RF-004_ArchitectureEditors
> **Parent:** L2_ReactFrontendSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die ArchitectureEditors-Komponente implementiert CRUD-Operationen für ArchitectureElements (Create, Read, Update, Delete). Sie ermöglicht Element-Typ-Auswahl (Component, Interface, Subsystem, Layer, Module), Markdown-Description-Editing mit Toggle, und zeigt verknüpfte Requirements in einer Seitenleiste. Löschoperationen erfordern Bestätigung.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Komponenten und Module

- **`ArchitectureEditors` (React.FC):** Main Editor-Komponente.
- **`ArchitectureElementForm` (React.FC):** Formular für Create/Edit.
- **`ElementTypeSelector` (React.FC):** Dropdown für Element-Typ-Auswahl.
- **`MarkdownDescriptionEditor` (React.FC):** Markdown Edit/Preview Toggle.
- **`RequirementsPanel` (React.FC):** Seitenleiste mit TraceLink-Requirements.
- **`DeleteConfirmationDialog` (React.FC):** Bestätigungsdialog vor Löschung.
- **`ArchitectureDataLoader` (Hook):** `useArchitectureElement()` — lädt Element + TraceLinks.

### 2.2 Datenstrukturen

**ArchitectureEditor-State:**
```typescript
interface ArchitectureEditorState {
  elementId?: UUID;  // undefined für Create-Modus
  element?: ArchitectureElement;
  formData: {
    name: string;
    elementType: "component" | "interface" | "subsystem" | "layer" | "module";
    description: string;  // Markdown
  };
  isDirty: boolean;
  isSaving: boolean;
  linkedRequirements: Requirement[];
  error?: Error;
  showDeleteConfirmation: boolean;
}

interface ArchitectureElement {
  id: UUID;
  name: string;
  elementType: string;
  description: string;  // Markdown
  createdAt: DateTime;
  modifiedAt: DateTime;
  parentId?: UUID;  // Hierarchie-Support
}
```

**Element-Type Definitions:**
```typescript
const ELEMENT_TYPES = [
  { value: "component", label: "Component" },
  { value: "interface", label: "Interface" },
  { value: "subsystem", label: "Subsystem" },
  { value: "layer", label: "Layer" },
  { value: "module", label: "Module" },
];
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RF004-001 (CRUD-Operationen) | Create: Form mit ElementTypeSelector füllen, POST. Read: `useArchitectureElement()` lädt. Update: Inline-Edit oder Form, PATCH. Delete: Dialog-Bestätigung vor DELETE. |
| REQ-L3-RF004-002 (Markdown-Description-Editing) | MarkdownDescriptionEditor mit Toggle. Edit-Modus: Textarea. Preview-Modus: gerenderte Markdown. PATCH speichert Änderungen. |
| REQ-L3-RF004-003 (Verknüpfte Requirements in Seitenleiste) | RequirementsPanel zeigt alle via TraceLinks verbundenen Requirements. Klick navigiert zu RequirementEditors. Leer-Zustand wenn keine Links. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RF-INT-001:** NavigationShell aktiviert ArchitectureEditors.
- **IF-RF-INT-003:** NavigationShell übergibt `{artifact_id, artifact_type}` als Props.
- **IF-RF-INT-002:** I18nService liefert Labels/Translations.

**Ausgänge (Outbound):**
- **IF-RF-EXT-OUT-001:** REST API:
  - `POST /api/v1/architecture-elements` — Create
  - `GET /api/v1/architecture-elements/{id}` — Read
  - `PATCH /api/v1/architecture-elements/{id}` — Update
  - `DELETE /api/v1/architecture-elements/{id}` — Delete
  - `GET /api/v1/architecture-elements/{id}/trace-links` — Linked Requirements

---

## 5. Architectural Rationale

**ADR-L3-RF-007 — Element-Typ-Auswahl als Dropdown statt Free-Text**

*Entscheidung:* ElementTypeSelector ist ein eingeschränktes Dropdown mit 5 vordefinierten Typen.

*Alternative (abgelehnt):* Free-Text-Input für Element-Typ. Grund: Keine Konsistenz, Backend-Validierung komplizierter.

*Rationale:* REQ-L3-RF004-001 fordert Type-Auswahl. Dropdown erzwingt Konsistenz.

---

**ADR-L3-RF-008 — Delete-Bestätigung via Dialog**

*Entscheidung:* `DeleteConfirmationDialog` wird vor DELETE angezeigt. Nutzer muss aktiv bestätigen.

*Alternative (abgelehnt):* Direkter DELETE ohne Dialog. Grund: Zu riskant, Nutzer-Fehler.

*Rationale:* REQ-L3-RF004-001 fordert explizit „DELETE-Request erst nach Bestätigung".

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
