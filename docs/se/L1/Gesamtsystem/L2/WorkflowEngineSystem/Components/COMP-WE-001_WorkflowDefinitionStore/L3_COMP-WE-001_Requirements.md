# L3 WorkflowDefinitionStore Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-WE-001 — WorkflowDefinitionStore
> **Parent-System:** WorkflowEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

CRUD fuer WorkflowDefinitions pro Item-Typ und Workspace, Default-Templates pro Preset, Custom-Definition-Validierung, Migrations-Sicherheit (Orphaned-State-Check), Preset-Downgrade-Blockade; verwaltet `signature_gate`-Attribut pro Transition-Definition.

---

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-WE-002 | WorkflowDefinition Management — CRUD, Default-Workflows pro Preset, Custom-Definition |
| REQ-L2-WE-004 | Workflow Migration on Definition Change — Orphaned-State-Check bei Aenderungen |
| REQ-L2-WE-007 | Preset-Downgrade Behavior — Downgrade-Blockade bei inkompatiblen Item-States |

---

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-INT-001 | ausgehend | COMP-WE-002 (TransitionValidator) | `WorkflowDefinition {states, transitions, allowed_roles, requires_change_reason, signature_gate?}` |
| IF-WE-INT-003 | eingehend | COMP-WE-003 (StateLifecycleManager) | `StateQuery {workspace_id, item_type, query_type: "initial_state"}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-EXT-IN-003 | eingehend | PresetConfigEngine | Preset-Regeln (Workflow-Konfigurierbarkeit) |
| IF-WE-EXT-OUT-001 | ausgehend | PersistenceLayer | WorkflowDefinition lesen/schreiben (Django ORM) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-WE001-001: Preset-Default-Workflow-Bereitstellung

Der WorkflowDefinitionStore SHALL fuer jeden neuen Workspace automatisch einen vordefinierten Default-Workflow gemaess dem Workspace-Preset bereitstellen: Minimal (`[draft, done]`, alle Transitionen fuer `editor`), Standard (`[draft, approved, deprecated]`, rollenbasiert), Extended (`[draft, in_review, approved, deprecated]`, `in_review → approved` nur fuer `approver`, `change_reason` Pflicht). Im Minimal-Preset SHALL der Default-Workflow unveraenderbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] New workspace with preset "minimal" → WorkflowDefinition contains exactly states `[draft, done]`
- [ ] New workspace with preset "extended" → WorkflowDefinition contains states `[draft, in_review, approved, deprecated]`
- [ ] Attempt to overwrite workflow definition in minimal preset → rejected with error `"Workflow not configurable in minimal preset"`
- [ ] New workspace with preset "standard" → role-based transitions present, `editor` cannot approve

---

### REQ-L3-WE001-002: Custom-WorkflowDefinition-Validierung und -Persistenz

Der WorkflowDefinitionStore SHALL Custom-WorkflowDefinitions ausschliesslich im Extended-Preset akzeptieren, auf Vollstaendigkeit pruefen (mindestens 2 States, mindestens 1 Transition, jede Transition referenziert vorhandene States) und persistieren. Jede Transition-Definition KANN optional ein `signature_gate: true`-Attribut tragen; dieses SHALL unveraendert gespeichert und ueber IF-WE-INT-001 an den TransitionValidator uebergeben werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Valid custom definition in extended preset → persisted, retrievable via IF-WE-INT-001
- [ ] Custom definition with transition referencing non-existent state → rejected with `"Invalid transition: unknown state"`
- [ ] Custom definition with `signature_gate: true` on a transition → attribute stored and passed through IF-WE-INT-001
- [ ] Custom definition submitted for standard preset → rejected with `"Custom workflows only allowed in extended preset"`

---

### REQ-L3-WE001-003: Orphaned-State-Pruefung bei Definitionsaenderung

Der WorkflowDefinitionStore SHALL vor jeder Aenderung einer aktiven WorkflowDefinition pruefen, ob Items in States existieren, die nach der Aenderung nicht mehr in der Definition vorhanden waeren (verwaiste States). Existieren solche Items, SHALL die Aenderung blockiert werden mit einer Fehlermeldung, die State-Name, Anzahl betroffener Items und bis zu 100 Item-IDs enthaelt.

**Priority:** desired
**Acceptance Criteria:**
- [ ] Definition change removes state `in_progress` with 5 items → blocked, error contains `"in_progress"`, count `5`, all 5 IDs
- [ ] 500 items in orphaned state → error contains count `500` and first 100 IDs only
- [ ] Definition change with no items in affected states → applied successfully
- [ ] Blocked change leaves existing WorkflowDefinition unchanged in persistence

---

### REQ-L3-WE001-004: Preset-Downgrade-Blockade

Der WorkflowDefinitionStore SHALL bei einem Preset-Downgrade (z.B. Extended → Standard, Standard → Minimal) pruefen, ob Items in States existieren, die im Zielpreset nicht vorhanden sind. Existieren solche Items, SHALL der Downgrade blockiert werden.

**Priority:** desired
**Acceptance Criteria:**
- [ ] 3 items in state `in_review`, downgrade extended → standard → blocked
- [ ] All items migrated to `draft`, retry downgrade extended → standard → successful
- [ ] All items in `draft`, downgrade standard → minimal → successful
- [ ] Downgrade blocked → active WorkflowDefinition and preset unchanged

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
