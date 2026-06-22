---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---

# L3 WorkflowDefinitionStore Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-WE-001_WorkflowDefinitionStore
> **Parent:** L2_WorkflowEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der WorkflowDefinitionStore ist das zentrale Verwaltungs- und Speicher-System für WorkflowDefinitions. Er stellt Preset-spezifische Default-Workflows bereit, validiert und persistiert Custom-Definitions (nur Extended-Preset), führt Orphaned-State-Checks durch bevor Definitionen geändert werden, blockiert Preset-Downgrades, wenn Items in Zielpreset-inkompatiblen States existieren, und verwaltet das `signature_gate`-Attribut pro Transition-Definition. Alle Operationen sind Tenant-scoped.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`WorkflowDefinitionStore` (Klasse):** Orchestriert CRUD-Operationen, Validierung, Orphaned-State-Checks und Downgrade-Logik.
- **`WorkflowDefinitionDTO` / `TransitionDefinitionDTO`:** Data Transfer Objects zur Übergabe innerhalb des Systems und an externe Schnittstellen.
- **`PresetManager` (Klasse):** Verwaltung von Preset-Schemas und Default-Workflows.
- **`OrphanedStateChecker` (Klasse):** Hilfsmethode zur Orphaned-State-Prüfung vor Definition-Änderungen.
- **`PresetDowngradeValidator` (Klasse):** Prüfung auf State-Inkompatibilität bei Preset-Downgrade.

### 2.2 Datenstrukturen

- **WorkflowDefinition-Entity:**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Foreign Key)
  - `item_type`: String (z.B. "Requirement", "Document")
  - `preset`: Enum (`minimal`, `standard`, `extended`)
  - `states`: JSON Array (z.B. `["draft", "approved", "deprecated"]`)
  - `transitions`: JSON Array (Transition-Definitionen mit `from`, `to`, `allowed_roles`, `requires_change_reason`, `signature_gate?`)
  - `is_custom`: Boolean (True wenn Custom-Definition, False wenn Preset-Default)
  - `created_at`: DateTime
  - `updated_at`: DateTime
  - `tenant_id`: UUID (Tenant-Kontext)

- **Transition-Definition (JSON-Struktur):**
  - `from_state`: String
  - `to_state`: String
  - `allowed_roles`: List[String]
  - `requires_change_reason`: Boolean
  - `signature_gate`: Boolean (optional, default: False)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WE001-001 (Preset-Default-Workflow-Bereitstellung) | Methode `create_workspace_default_workflow(workspace_id, preset)`: Lädt Preset-Schema, erstellt entsprechende WorkflowDefinition-Entity (is_custom=False), persistiert diese via PersistenceLayer. Für Minimal-Preset wird zusätzliche `locked=True`-Flag gesetzt, die `update`-Methode wirft Fehler bei Änderungsversuch. |
| REQ-L3-WE001-002 (Custom-WorkflowDefinition-Validierung) | Methode `validate_and_persist_custom(definition, workspace_id, item_type)`: Prüft `preset == extended`, mindestens 2 States und 1 Transition, alle Transitions referenzieren vorhandene States. Speichert `signature_gate`-Attribute unverändert. Gibt vollständige Definition an TransitionValidator weiter via IF-WE-INT-001. |
| REQ-L3-WE001-003 (Orphaned-State-Prüfung) | Methode `update_definition(id, new_definition)`: Ruft `OrphanedStateChecker.check_items_in_removed_states()` auf. Falls Items in verwaisten States existieren, blockiert Update, gibt Fehlermeldung mit State-Name, Count und bis zu 100 Item-IDs zurück. |
| REQ-L3-WE001-004 (Preset-Downgrade-Blockade) | Methode `downgrade_preset(workspace_id, target_preset)`: Ruft `PresetDowngradeValidator.check_compatibility()` auf. Falls Items in Zielpreset-inkompatiblen States existieren, blockiert Downgrade. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-WE-EXT-IN-003:** REST API oder ApplicationService-Methoden (`create_workflow`, `update_workflow`, `get_workflow`).
  - **IF-WE-INT-003 (ausgehend):** Query-Anfrage an StateLifecycleManager zur `initial_state`-Bestimmung.

- **Ausgänge (Outbound):**
  - **IF-WE-INT-001 (ausgehend):** Lieferung der kompletten `WorkflowDefinition {states, transitions, allowed_roles, requires_change_reason, signature_gate?}` an TransitionValidator.
  - **IF-WE-EXT-OUT-001:** ORM-Aufrufe an den PersistenceLayer (Django ORM) für CRUD auf WorkflowDefinition-Tabelle, Tenant-gefiltert.

---

## 5. Architectural Rationale

**ADR-L3-WE001-01 — Preset-Defaults als vordefinierte Schemas**
*Entscheidung:* Preset-Workflows werden als vordefinierte Schemas in Code/Config verwaltet, nicht dynamisch erstellt.
*Rationale:* Erfüllt REQ-L3-WE001-001 strikt. Garantiert Konsistenz über alle Workspaces mit gleichem Preset. Minimales-Preset wird unveränderbar, Standard und Extended sind änderbar (nur Custom im Extended-Preset).
*Alternative (abgelehnt):* Dynamische Template-Verwaltung — zu komplex, höheres Fehler-Risiko, keine Konsistenz-Garantie.

**ADR-L3-WE001-02 — Append-Only Historisierung mit Orphaned-State-Check**
*Entscheidung:* Jede Definition-Änderung wird nur erlaubt, wenn kein Item in einem zu-entfernenden State existiert. Blockierte Änderungen hinterlassen keine Spur.
*Rationale:* Erfüllt REQ-L3-WE001-003 strikt. Verhindert inkonsistente Zustände (Items im Non-existent-State). Audit-Trail bleibt sauber.
*Alternative (abgelehnt):* Automatische Item-Migration bei Definition-Änderung — unvorhersehbare Seiteneffekte, Audit-Trail komplexer.

**ADR-L3-WE001-03 — Preset-Downgrade-Blockade statt Auto-Migration**
*Entscheidung:* Downgrade blockiert bei State-Inkompatibilität; erfordert manuelle Remediation oder State-Migration.
*Rationale:* Erfüllt REQ-L3-WE001-004 strikt. Vermeidet stille Datenverluste. Explizitheit vor Implizitheit.
*Alternative (abgelehnt):* Auto-Migration auf kompatible State — unklar, welcher State gewählt werden sollte, Nutzer könnte nicht erwarten.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
