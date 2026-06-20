# L2 WorkflowEngine Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** WorkflowEngineSystem (ARCH-L1-005)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** subsystem (Leaf-AE — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-009 (primär), REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-007 (mitwirkend), REQ-L1-010 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-015 (mitwirkend), REQ-L1-025 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-WE-EXT-IN-001 | input | data | `transition(item_id, target_state, change_reason, ctx)` von ApplicationService |
| IF-WE-EXT-IN-002 | input | data | `initialize(item_ids[], item_type, workspace_id, ctx)` von ApplicationService |
| IF-WE-EXT-IN-003 | input | data | Preset-Regeln von PresetConfigEngine (ARCH-L1-008) |
| IF-WE-EXT-IN-004 | input | data | Rollen-Kontext von AuthAndTenancy (ARCH-L1-011) |
| IF-WE-EXT-OUT-001 | output | data | WorkflowDefinition, WorkflowState an PersistenceLayer (ARCH-L1-010) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-WE-001: Transition Validation

Die WorkflowEngine SHALL jede Workflow-State-Transition (`from_state → to_state`) gegen die aktive WorkflowDefinition validieren. Die Validierung SHALL drei Regeln durchsetzen:
1. Die Transition existiert in der aktiven WorkflowDefinition für den Item-Typ und Workspace.
2. Die Rolle des anfragenden Nutzers ist in den `allowed_roles` der Transition enthalten.
3. Falls `requires_change_reason = true`, MUSS ein nicht-leerer `change_reason` vorhanden sein.

Bei Regelverletzung SHALL die Transition mit spezifischer Fehlermeldung abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nutzer mit Rolle `editor` versucht `draft → approved` (nur `approver` erlaubt) → Fehler `"Role not allowed"`
- [ ] Nutzer mit `approver` versucht Transition ohne `change_reason` (Pflicht) → Fehler `"change_reason required"`
- [ ] Nicht-definierte Transition `draft → deprecated` → Fehler `"Transition not allowed"`
- [ ] Gültige Transition mit allen Bedingungen → WorkflowState aktualisiert, History-Eintrag

**Interfaces:**
- Incoming: IF-WE-EXT-IN-001, IF-WE-EXT-IN-003, IF-WE-EXT-IN-004
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-009, REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-010 (mitwirkend), REQ-L1-012 (mitwirkend)
**Rationale:** Transition-Validierung ist der Kern-Sicherheitsmechanismus der WorkflowEngine.

---

### REQ-L2-WE-002: WorkflowDefinition Management

Die WorkflowEngine SHALL WorkflowDefinitions pro Item-Typ und Workspace verwalten. Vordefinierte Default-Workflows für alle drei Presets:
- **Minimal:** States `[draft, done]`, alle Transitionen für `editor`.
- **Standard:** States `[draft, approved, deprecated]`, rollenbasiert.
- **Extended:** States `[draft, in_review, approved, deprecated]`, `in_review → approved` nur für `approver`, `change_reason` Pflicht.

Custom WorkflowDefinitions SOLLTEN im Extended-Preset erlaubt sein. Im Minimal-Preset SHALL der Default-Workflow nicht konfigurierbar sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Neuer Workspace Minimal → Default-Workflow: `[draft, done]`
- [ ] Neuer Workspace Extended → Default-Workflow: `[draft, in_review, approved, deprecated]`
- [ ] Custom Workflow im Minimal-Preset → abgelehnt
- [ ] Custom Workflow im Extended-Preset → persistiert

**Interfaces:**
- Incoming: IF-WE-EXT-IN-003
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-009, REQ-L1-007 (mitwirkend)
**Rationale:** WorkflowDefinitions sind das strukturelle Fundament von Configurable Rigor auf Item-Ebene.

---

### REQ-L2-WE-003: WorkflowState History (Audit-Trail)

Die WorkflowEngine SHALL für jede erfolgreiche Transition einen append-only History-Eintrag schreiben mit: `from_state`, `to_state`, `transitioned_by`, `transitioned_at` (UTC, ms-Präzision), `change_reason` (optional). History-Einträge DÜRFEN NICHT modifiziert oder gelöscht werden. Transition und History-Eintrag MÜSSEN atomar persistiert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 3 aufeinanderfolgende Transitionen → 3 History-Einträge in chronologischer Reihenfolge
- [ ] Versuch History-Eintrag zu modifizieren → Exception `"History is append-only"`
- [ ] History-Write-Fehler → State-Transition zurückgerollt
- [ ] MCP-Transition → `transitioned_by` enthält Agent-Client-Identität

**Interfaces:**
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-009, REQ-L1-011 (mitwirkend), REQ-L1-025 (mitwirkend)
**Rationale:** Append-only History ist die Grundlage des Audit-Trails für Workflow-Transitionen.

---

### REQ-L2-WE-004: Workflow Migration on Definition Change

Die WorkflowEngine SHALL bei WorkflowDefinition-Änderungen prüfen, ob Items in nicht mehr vorhandenen States existieren (verwaiste States). Falls ja, SHALL die Änderung blockiert werden mit Fehlermeldung (State-Name, betroffene Item-Anzahl, Item-IDs bis Limit 100).

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Definition entfernt State `in_progress` mit 5 Items darin → Fehler `"Workflow change blocked: 5 items in orphaned state 'in_progress'"`
- [ ] Nach Migration aller Items → Änderung erfolgreich
- [ ] 500 Items in verwaistem State → Count (500) + erste 100 IDs gelistet

**Interfaces:**
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-009, REQ-L1-007 (mitwirkend)
**Rationale:** Verhindert stille Datenkorruption durch unkontrollierte Definitionsänderungen. Adressiert OP-03.

---

### REQ-L2-WE-005: Workflow State Initialization

Die WorkflowEngine SHALL die Operation `initialize_workflow_state(item_ids[], item_type, workspace_id, ctx)` bereitstellen, die für jedes Item einen initialen WorkflowState erstellt (initial_state, typischerweise `draft`). Alle States MÜSSEN atomar persistiert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `initialize([id1, id2, id3], "Requirement", W, ctx)` → 3 WorkflowState-Records mit `current_state = "draft"`
- [ ] Alle Records in einer atomaren Transaktion
- [ ] Keine WorkflowDefinition vorhanden → Fehler `"No WorkflowDefinition found"`
- [ ] Leeres item_ids-Array → erfolgreich ohne Records

**Interfaces:**
- Incoming: IF-WE-EXT-IN-002
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-009, REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-025 (mitwirkend)
**Rationale:** Initialisierung ist erforderlich bei jeder Item-Erstellung (REST, MCP, CSV-Import).

---

### REQ-L2-WE-006: Tenant-Scoped Workflow Data Isolation

Die WorkflowEngine SHALL alle WorkflowDefinition- und WorkflowState-Queries auf den aktiven Tenant beschränken. Jede Operation SHALL den `tenant_id` aus dem Auth-Kontext als Filter verwenden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant A query → nur Tenant-A-WorkflowDefinitions
- [ ] Transition mit Tenant-B-Kontext für Tenant-A-Item → abgelehnt
- [ ] SQL enthält immer `WHERE tenant_id = <active_tenant>`

**Interfaces:**
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-015, REQ-L1-009 (mitwirkend)
**Rationale:** Tenant-Isolation ist Querschnittsanforderung für alle Subsysteme.

---

### REQ-L2-WE-007: Preset-Downgrade Behavior

Die WorkflowEngine SHALL bei Preset-Downgrades prüfen, ob Items in States existieren, die im Zielpreset nicht gültig sind. Falls ja, SHALL der Downgrade blockiert werden.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 3 Items in `in_review`, Downgrade Extended → Standard → Blockiert
- [ ] Nach Transition aller Items nach `draft` → Downgrade erfolgreich
- [ ] Alle Items in `draft`, Downgrade Standard → Minimal → erfolgreich

**Interfaces:**
- Incoming: IF-WE-EXT-IN-003
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-007, REQ-L1-009 (mitwirkend)
**Rationale:** Verhindert Items in States ohne gültige Transitionen. Adressiert OP-02.

---

### REQ-L2-WE-008: Transition Performance

Die WorkflowEngine SHALL eine einzelne Transition (Validierung + State-Update + History-Write) innerhalb von 50ms abschließen — unter Normal-Last (50 gleichzeitige Nutzer, 10.000 Items).

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 10.000 Items, 50 gleichzeitige Transitionen → 95% < 50ms
- [ ] Validierungsschritt allein < 10ms

**Interfaces:**
- Incoming: IF-WE-EXT-IN-001
- Outgoing: IF-WE-EXT-OUT-001

**Traceability:** REQ-L1-026, REQ-L1-009 (mitwirkend)
**Rationale:** 50ms-Budget stellt sicher, dass die WorkflowEngine nicht zum Flaschenhals wird.

---

## Traceability-Matrix: REQ-L2-WE → REQ-L1

| REQ-L2-WE | REQ-L1 (primär) | REQ-L1 (mitwirkend) |
|-----------|-----------------|---------------------|
| REQ-L2-WE-001 | REQ-L1-009 | REQ-L1-002, -004, -010, -012 |
| REQ-L2-WE-002 | REQ-L1-009 | REQ-L1-007 |
| REQ-L2-WE-003 | REQ-L1-009 | REQ-L1-011, -025 |
| REQ-L2-WE-004 | REQ-L1-009 | REQ-L1-007 |
| REQ-L2-WE-005 | REQ-L1-009 | REQ-L1-002, -004, -012, -025 |
| REQ-L2-WE-006 | REQ-L1-015 | REQ-L1-009 |
| REQ-L2-WE-007 | REQ-L1-007 | REQ-L1-009 |
| REQ-L2-WE-008 | REQ-L1-026 | REQ-L1-009 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-WE | 8 |
| Mandatory | 5 |
| Desired | 3 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-009, REQ-L1-015 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, -004, -007, -010, -011, -012, -025, -026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Workflow → REQ-L2-WE, Template-Standardisierung*
*Designation: subsystem (Leaf-AE) — decomposition_status: terminal*
