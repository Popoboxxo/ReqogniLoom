# ReqFlow — Anforderungsregister

*(Alle Anforderungen wurden erfolgreich in die entsprechenden L1- und L2-Dokumente migriert.)*

---

## L1 — System Requirements (SE-Cascade Foundations)

### REQ-L1-040: SE Masks Unification (13 Entity Types)

**Category:** UI/UX, Data

**Status:** In Progress

**Description:**
Standardisiere SE-Masken für alle 13 Entitätstypen (ArchitectureElement, Requirement, TraceLink, etc.) zur Gewährleistung konsistenter Level-Ableitung, Parent-ID-Handling und Allocation-Tracking. Ziel: Einheitliches Datenmodell für hierarchische Ebenen (L0-Ln), mit Level als abgeleitetes (nicht manuell gesetztes) Feld über Recursive CTE. Umfasst Backend-Invarianten (I1-I4), Frontend Level-View und Allocation-Coverage-Reporting. Baseline: arch-concept-proposal-20260702.md, Punkt 2.

Bezug: `.claude/artifacts/arch-concept-proposal-20260702.md`, §2 (Modell & Ableitung).

**Acceptance Criteria:**
1. SE-Masken für 13 Entitätstypen standardisiert (parent_id nullable FK, level read-only, status enum)
2. Parent-ID-Ableitung via Recursive CTE auf Query-Zeit implementiert
3. Allocation-Tracking via TraceLink.allocated-to eingeführt
4. Invarianten-Validator (I1-I4) rigor-gated implementiert
5. Frontend Level-View zeigt Requirements gruppiert nach Ebene mit Owner-Links
6. Decompose-Extension mit target_elements für Sub-Req-Allocation
7. Coverage-Report zeigt Allocation-Status pro Level
8. Integration-Tests bestätigen End-to-End Workflow

**Interfaces:**
- Input: API für Requirement/Architecture CRUD mit parent_id-Support
- Output: Level-View UI, Allocation-Coverage Report, API-Responses mit Level-Feld

**Complexity:** High (13 Entity Types, Recursive Queries, Multi-Tier Validation)
**Tier:** senior-developer (cross-cutting coordination)
**Traceability:** REQ-L1-001 (parent: Requirements Management Architecture)
**DoD:** req-traceability=true, tests=true, entity-coverage=13/13, ui-responsive=verified

---

### REQ-L1-041: ArchitectureElement parent_id + Level-Derivation

**Category:** Data, Backend

**Status:** Backlog

**Description:**
Implementiere parent_id-Feld (self-referencing FK, nullable) auf ArchitectureElement-Modell zur Abbildung der Hierarchie aller Ebenen (L1 System → L2 Subsystems → L3 Components → Ln). Level wird nicht manuell gesetzt, sondern über Recursive CTE aus Baumtiefe abgeleitet (Rekursive Query: parent=null → level=1, parent.level=n → level=n+1). Serializer exponiert level als read-only Feld. Service nutzt Recursive CTE für Level-Ableitung auf Query-Zeit oder optional gecacht in denormalisertem level-Feld (Decision: Query-Zeit vs. Denormalisierung nach Performance-Messung).

Bezug: `.claude/artifacts/arch-concept-proposal-20260702.md`, §2.2 (Entitäten und Zuordnung), §2.3 (Ableitung).

**Acceptance Criteria:**
1. ArchitectureElement.parent_id existiert (FK zu ArchitectureElement, nullable, self-referencing)
2. DB-Migration ohne Datenverlust (nur Schema-Änderung, no data transformation)
3. Recursive CTE-Query liefert level-Ableitung: root level=1, jedes Kind level=parent.level+1
4. Serializer: read-only level-Feld, von Recursive CTE abgeleitet
5. ArchitectureService.get_architecture_element() — level im Response
6. Unit-Tests: 3-Level-Baum (System → Subsystem → Component), Levels korrekt abgeleitet
7. Integration-Tests: Persistent Query Performance OK (ggf. Index auf parent_id)

**Interfaces:**
- Input: ArchitectureService.create_architecture_element() (parent_id optional)
- Output: ArchitectureService.get_architecture_element(), API GET /architecture/{id}

**Complexity:** High (DB-Migration, Recursive Query, Serializer-Änderung)
**Tier:** senior-developer
**Traceability:** REQ-L1-040 (parent: SE Masks Unification), REQ-L1-001, REQ-L1-003, REQ-L1-004
**DoD:** req-traceability=true, tests=true, migration=tested

---

### REQ-L1-042: TraceLink allocated-to + Allocation-Coverage Reporter

**Category:** Traceability, Backend

**Status:** Backlog

**Description:**
Führe neuen TraceLink-Typ `allocated-to` ein (Requirement → ArchitectureElement, 1:1 Kardinalität). Ein Requirement gehört zur Spezifikation genau eines ArchEl (Owner), das seine Ebene bestimmt. Stakeholder Needs (category=stakeholder_need) haben keinen Owner (live in L0). TraceLink.link_type enumeration erweitern (CharField mit neuen Validator). AllocationCoverageValidator: Requirement mit arch_impact=true MUSS genau 1 incoming allocated-to Link haben (außer Stakeholder Needs). API GET /requirements/{id}/allocation zeigt Owner-ArchitectureElement. Coverage-Report zeigt Allocation-Status pro Level. Bei Verletzung: Warning (rigor=Standard) oder Error (rigor=Extended).

Bezug: arch-concept-proposal-20260702.md, §2.2 (Requirement-Ownership), §2.4 (Invarianten I1).

**Acceptance Criteria:**
1. TraceLink.link_type = 'allocated-to' in Enum + Validator
2. AllocationCoverageValidator prüft: Requirement arch_impact=true → ≥1 allocated-to Input, oder category=stakeholder_need
3. API GET /requirements/{id}/allocation → {owner_architecture_id, owner_title, owner_level}
4. Allocation-Coverage Report: Metrics pro Level (covered, uncovered, warnings)
5. Serializer: TraceLink exponiert link_type='allocated-to' korrekt
6. Unit-Tests: 3 Cases — (1) Requirement with owner, (2) Requirement without owner (warning), (3) Stakeholder Need (ok ohne owner)
7. Integration-Tests: Allocation-Abfrage + Coverage-Report-Generierung

**Interfaces:**
- Input: TraceLink CRUD, Requirement Validation
- Output: API GET /requirements/{id}/allocation, Allocation-Coverage Report (JSON + CSV)

**Complexity:** Medium (Link-Type Extension, Validator, API-Endpoint, Reporting)
**Tier:** developer oder senior-developer (Validator-Komplexität)
**Traceability:** REQ-L1-040 (parent: SE Masks Unification), REQ-L1-001, REQ-L1-004, REQ-L1-048
**DoD:** req-traceability=true, tests=true, api-contract=defined, report-export=implemented

---

### REQ-L1-043: RequirementService.decompose() Extension mit target_elements

**Category:** Functional, Backend

**Status:** Backlog

**Description:**
Erweitere decompose(requirement_id, sub_requirements: [], target_elements: []) um optionalen target_elements-Parameter. Neue Semantik: (1) Decompose Requirement in Sub-Requirements (bestehend), (2) Optional: Erstelle allocated-to Links von Sub-Reqs zu angegebenen ArchEl (target_elements). Atomare Transaktion: Bei Fehler in Sub-Req-Erstellung → Rollback aller Allocations. Wenn target_elements leeres Array oder nicht angegeben → kein Allocation-Create (backward compatible). Bestehend: decompose() wirft bei duplicate sub_req-Titles oder zirkulären Parent-Child-Links Exception.

Bezug: arch-concept-proposal-20260702.md, §2.3 (Ableitung via decompose), Konzept-Proposal line 56.

**Acceptance Criteria:**
1. decompose(req_id, subs, target_elements=[]) Signatur
2. Transaktion: Sub-Req-Create + Allocation-Create (ggf. Rollback)
3. Allocation-Create: für jedes Sub-Req ein allocated-to Link zu entsprechendem ArchEl (Mapping-Strategie: index-based oder Map<req_title→arch_id>)
4. Backward-Compat: target_elements=[] oder nicht angegeben → nur Sub-Req-Erstellung
5. Validation: target_elements.length == sub_requirements.length (bei non-empty)
6. Unit-Tests: (1) mit target_elements, (2) ohne target_elements, (3) Allocation-Fehler → Rollback
7. Integration-Tests: Decomposition mit Allocation-Coverage-Report

**Interfaces:**
- Input: RequirementService.decompose(req_id, subs, target_elements)
- Output: Sub-Reqs + allocated-to Links (JSON Response mit Status per Link)

**Complexity:** Medium (Service-Logik-Erweiterung, Transaktion)
**Tier:** developer
**Traceability:** REQ-L1-040 (parent: SE Masks Unification), REQ-L1-042 (uses allocated-to), REQ-L1-001
**DoD:** req-traceability=true, tests=true, transaction-consistency=verified

---

### REQ-L1-044: Invarianten-Validator (I1-I4) rigor-gated

**Category:** Non-Functional, Validation, Backend

**Status:** Backlog

**Description:**
Implementiere 4 Invarianten zur Sicherung der Ebenen-Konsistenz. Validator läuft nach Allocation-Create, nach decompose(), nach Level-Änderungen. Rigor-abhängig: Minimal=skip, Standard=Warnings (Log), Extended=Hard Errors (Exception). 

**Invarianten:**
- **I1:** Requirement.level == Owner-ArchEl.level + 1 (oder flexibel n vs. n+1 nach Designentscheidung)
- **I2:** Allocated Requirement kann nicht zu höherer Ebene als Parent-Requirement allociert sein (hierarchische Konsistenz)
- **I3:** Zirkuläre Allocations verboten: Req1 → Arch1 → decomposed-Req2 → Arch2 → Req1 (Cycle-Detection via DFS/BFS)
- **I4:** Wenn Requirement decomposed (hat Sub-Reqs), dann müssen alle Sub-Reqs allocated sein (Completeness unter Extended-Rigor)

Bezug: arch-concept-proposal-20260702.md, §2.4 (Invarianten I1-I4).

**Acceptance Criteria:**
1. InvariantValidator.check_invariant_i1(req_id, owner_arch_id) → bool
2. InvariantValidator.check_invariant_i2(req_id, owner_arch_id, parent_req_id) → bool
3. InvariantValidator.check_invariant_i3(req_id, owner_arch_id) → bool (cycle detection)
4. InvariantValidator.check_invariant_i4(req_id) → bool
5. Alle 4 sind rigor-gated (Minimal=skip, Standard/Extended=enabled, Extended=throw on I1-I3, warn on I4)
6. Unit-Tests: 1 Test pro Invariant, Minimal/Standard/Extended Modes
7. Integration-Tests: Decomposition + Allocation Workflow, alle 4 Invarianten prüfen
8. Invariant-Verletzung auf Extended → Exception mit Hinweis auf betroffene REQ-ID

**Interfaces:**
- Input: Allocation-Create, decompose(), Requirement-Update
- Output: Validation Result (bool oder Exception), Audit-Log-Eintrag

**Complexity:** High (4 Invarianten, Recursive Checks für I2/I3, Rigor-Integration)
**Tier:** senior-developer
**Traceability:** REQ-L1-040 (parent: SE Masks Unification), REQ-L1-041, REQ-L1-042, REQ-L1-043
**DoD:** req-traceability=true, tests=true, rigor-preset-compliance=verified

---

### REQ-L1-045: Frontend Level-View (Requirements Hierarchy)

**Category:** UI/UX, Frontend

**Status:** Backlog

**Description:**
Implementiere neue Route/Tab `/levels` oder Integration in RequirementEditor zeigt Requirements gruppiert nach ihrer abgeleiteten Ebene (L0 Stakeholder Needs → L1 Requirements → L2 Architekturen → L2 Derived Requirements → L3 Components → ...). Layout: Tree-View (erweiterbar/kollapsierbar) oder Tabellen-View (spaltenweise Ebenen). Jede Zeile: Requirement, level, allocated-to-Owner (ArchElement-Name + Link), status, workflow-state. Klick auf Requirement → RequirementEditor-Detail. Klick auf ArchElement → ArchitectureEditor-Detail. Daten via API GET /requirements?level={n} oder GETall + Frontend-Filter. Level wird vom Backend bereitgestellt (REQ-L1-041).

Bezug: REQ-L1-048 (bereits als Anforderung erfasst), arch-concept-proposal-20260702.md, §2.5 (Frontend).

**Acceptance Criteria:**
1. Route `/levels` oder Tab in RequirementEditor existiert
2. Tree/Table rendert alle Requirements gruppiert by level
3. Spalten: title, level (read-only), allocated-to-owner (mit Link), status, workflow-state
4. Level-Wert vom Backend (Recursive CTE aus REQ-L1-041)
5. Klick-Navigation: Req → RequirementEditor, ArchEl → ArchitectureEditor
6. API Integration: GET /requirements/{id} enthält level-Feld + allocated-to-owner info
7. Responsive UI (mobile-friendly): Tree collapsible, Tabelle scrollbar
8. Unit-Tests: Component Rendering, Navigation Links
9. Integration-Tests: Fetch Requirements with levels, Render Tree, Click Navigation

**Interfaces:**
- Input: GET /requirements (+ filter by level optional), GET /architecture/{id}
- Output: React Component mit Tree/Table, Navigation-Links

**Complexity:** Medium (UI + API-Integration, Navigation)
**Tier:** developer
**Traceability:** REQ-L1-040 (parent: SE Masks Unification), REQ-L1-048 (related: Requirements UI), REQ-L1-041 (uses level-derivation)
**DoD:** req-traceability=true, tests=true, ui-responsive=verified, a11y-compliant=checked

---

## L3 — Cross-Cutting Architecture (Ebenen-Modell Infrastructure)

### REQ-L3-EM-001: ArchitectureElement parent_id + level-Ableitung via Recursive CTE

**Category:** Data, Backend

**Description:**
Implementiere parent_id-Feld (self-referencing FK, nullable) auf ArchitectureElement-Modell zur Abbildung der Hierarchie aller Ebenen (L1 System → L2 Subsystems → L3 Components → Ln). Level wird nicht manuell gesetzt, sondern über Recursive CTE aus Baumtiefe abgeleitet (Rekursive Query: parent=null → level=1, parent.level=n → level=n+1). Serializer exponiert level als read-only Feld. Service nutzt Recursive CTE für Level-Ableitung auf Query-Zeit oder optional gecacht in denormalisertem level-Feld (Decision: Query-Zeit vs. Denormalisierung nach Performance-Messung).

Bezug: `.claude/artifacts/arch-concept-proposal-20260702.md`, §2.2 (Entitäten und Zuordnung), §2.3 (Ableitung).

**Acceptance Criteria:**
1. ArchitectureElement.parent_id existiert (FK zu ArchitectureElement, nullable, self-referencing)
2. DB-Migration ohne Datenverlust (nur Schema-Änderung, no data transformation)
3. Recursive CTE-Query liefert level-Ableitung: root level=1, jedes Kind level=parent.level+1
4. Serializer: read-only level-Feld, von Recursive CTE abgeleitet
5. ArchitectureService.get_architecture_element() — level im Response
6. Unit-Tests: 3-Level-Baum (System → Subsystem → Component), Levels korrekt abgeleitet
7. Integration-Tests: Persistent Query Performance OK (ggf. Index auf parent_id)

**Interfaces:**
- Input: ArchitectureService.create_architecture_element() (parent_id optional)
- Output: ArchitectureService.get_architecture_element(), API GET /architecture/{id}

**Complexity:** High (DB-Migration, Recursive Query, Serializer-Änderung)
**Tier:** senior-developer
**Traceability:** REQ-L1-001, REQ-L1-003, REQ-L1-004 (parent: Architecture Design Foundations)
**DoD:** req-traceability=true, tests=true, migration=tested

---

### REQ-L3-EM-002: TraceLink allocated-to + Allocation-Coverage Validator

**Category:** Traceability, Backend

**Description:**
Führe neuen TraceLink-Typ `allocated-to` ein (Requirement → ArchitectureElement, 1:1 Kardinalität). Ein Requirement gehört zur Spezifikation genau eines ArchEl (Owner), das seine Ebene bestimmt. Stakeholder Needs (category=stakeholder_need) haben keinen Owner (live in L0). TraceLink.link_type enumeration erweitern (CharField mit neuen Validator). AllocationCoverageValidator: Requirement mit arch_impact=true MUSS genau 1 incoming allocated-to Link haben (außer Stakeholder Needs). API GET /requirements/{id}/allocation zeigt Owner-ArchitectureElement. Bei Verletzung: Warning (rigor=Standard) oder Error (rigor=Extended).

Bezug: arch-concept-proposal-20260702.md, §2.2 (Requirement-Ownership), §2.4 (Invarianten I1).

**Acceptance Criteria:**
1. TraceLink.link_type = 'allocated-to' in Enum + Validator
2. AllocationCoverageValidator prüft: Requirement arch_impact=true → ≥1 allocated-to Input, oder category=stakeholder_need
3. API GET /requirements/{id}/allocation → {owner_architecture_id, owner_title, owner_level}
4. Serializer: TraceLink exponiert link_type='allocated-to' korrekt
5. Unit-Tests: 3 Cases — (1) Requirement with owner, (2) Requirement without owner (warning), (3) Stakeholder Need (ok ohne owner)
6. Integration-Tests: Allocation-Abfrage + Coverage-Report

**Interfaces:**
- Input: TraceLink CRUD, Requirement Validation
- Output: API GET /requirements/{id}/allocation, Allocation-Coverage Report

**Complexity:** Medium (Link-Type Extension, Validator, API-Endpoint)
**Tier:** developer oder senior-developer (Validator-Komplexität)
**Traceability:** REQ-L1-001, REQ-L1-004, REQ-L1-048 (parent: Traceability & Architecture Binding)
**DoD:** req-traceability=true, tests=true, api-contract=defined

---

### REQ-L3-EM-003: RequirementService.decompose() Extension mit target_elements

**Category:** Functional, Backend

**Description:**
Erweitere decompose(requirement_id, sub_requirements: [], target_elements: []) um optionalen target_elements-Parameter. Neue Semantik: (1) Decompose Requirement in Sub-Requirements (bestehend), (2) Optional: Erstelle allocated-to Links von Sub-Reqs zu angegebenen ArchEl (target_elements). Atomare Transaktion: Bei Fehler in Sub-Req-Erstellung → Rollback aller Allocations. Wenn target_elements leeres Array oder nicht angegeben → kein Allocation-Create (backward compatible). Bestehend: decompose() wirft bei duplicate sub_req-Titles oder zirkulären Parent-Child-Links Exception.

Bezug: arch-concept-proposal-20260702.md, §2.3 (Ableitung via decompose), Konzept-Proposal line 56.

**Acceptance Criteria:**
1. decompose(req_id, subs, target_elements=[]) Signatur
2. Transaktion: Sub-Req-Create + Allocation-Create (ggf. Rollback)
3. Allocation-Create: für jedes Sub-Req ein allocated-to Link zu entsprechendem ArchEl (Mapping-Strategie: index-based oder Map<req_title→arch_id>)
4. Backward-Compat: target_elements=[] oder nicht angegeben → nur Sub-Req-Erstellung
5. Validation: target_elements.length == sub_requirements.length (bei non-empty)
6. Unit-Tests: (1) mit target_elements, (2) ohne target_elements, (3) Allocation-Fehler → Rollback
7. Integration-Tests: Decomposition mit Allocation-Coverage-Report

**Interfaces:**
- Input: RequirementService.decompose(req_id, subs, target_elements)
- Output: Sub-Reqs + allocated-to Links

**Complexity:** Medium (Service-Logik-Erweiterung, Transaktion)
**Tier:** developer
**Traceability:** REQ-L3-EM-002 (parent: uses allocated-to), REQ-L1-001 (parent: Requirements Management)
**DoD:** req-traceability=true, tests=true, transaction-consistency=verified

---

### REQ-L3-EM-004: Invarianten-Validator (I1-I4) rigor-gated

**Category:** Non-Functional, Validation, Backend

**Description:**
Implementiere 4 Invarianten zur Sicherung der Ebenen-Konsistenz. Validator läuft nach Allocation-Create, nach decompose(), nach Level-Änderungen. Rigor-abhängig: Minimal=skip, Standard=Warnings (Log), Extended=Hard Errors (Exception). 

**Invarianten:**
- **I1:** Requirement.level == Owner-ArchEl.level + 1 (oder flexibel n vs. n+1 nach Designentscheidung)
- **I2:** Allocated Requirement kann nicht zu höherer Ebene als Parent-Requirement allociert sein (hierarchische Konsistenz)
- **I3:** Zirkuläre Allocations verboten: Req1 → Arch1 → decomposed-Req2 → Arch2 → Req1 (Cycle-Detection via DFS/BFS)
- **I4:** Wenn Requirement decomposed (hat Sub-Reqs), dann müssen alle Sub-Reqs allocated sein (Completeness unter Extended-Rigor)

Bezug: arch-concept-proposal-20260702.md, §2.4 (Invarianten I1-I4).

**Acceptance Criteria:**
1. InvariantValidator.check_invariant_i1(req_id, owner_arch_id) → bool
2. InvariantValidator.check_invariant_i2(req_id, owner_arch_id, parent_req_id) → bool
3. InvariantValidator.check_invariant_i3(req_id, owner_arch_id) → bool (cycle detection)
4. InvariantValidator.check_invariant_i4(req_id) → bool
5. Alle 4 sind rigor-gated (Minimal=skip, Standard/Extended=enabled, Extended=throw on I1-I3, warn on I4)
6. Unit-Tests: 1 Test pro Invariant, Minimal/Standard/Extended Modes
7. Integration-Tests: Decomposition + Allocation Workflow, alle 4 Invarianten prüfen
8. Invariant-Verletzung auf Extended → Exception mit Hinweis auf betroffene REQ-ID

**Interfaces:**
- Input: Allocation-Create, decompose(), Requirement-Update
- Output: Validation Result (bool oder Exception), Audit-Log-Eintrag

**Complexity:** High (4 Invarianten, Recursive Checks für I2/I3, Rigor-Integration)
**Tier:** senior-developer
**Traceability:** REQ-L3-EM-001, REQ-L3-EM-002, REQ-L3-EM-003 (parent: Level-Model Consistency)
**DoD:** req-traceability=true, tests=true, rigor-preset-compliance=verified

---

### REQ-L3-EM-005: Frontend Level-View (Ebenen-Baum für Requirements)

**Category:** UI/UX, Frontend

**Description:**
Implementiere neue Route/Tab `/levels` oder Integrationin RequirementEditor zeigt Requirements gruppiert nach ihrer abgeleiteten Ebene (L0 Stakeholder Needs → L1 Requirements → L2 Architekturen → L2 Derived Requirements → L3 Components → ...). Layout: Tree-View (erweiterbar/kollapsierbar) oder Tabellen-View (spaltenweise Ebenen). Jede Zeile: Requirement, level, allocated-to-Owner (ArchElement-Name + Link), status, workflow-state. Klick auf Requirement → RequirementEditor-Detail. Klick auf ArchElement → ArchitectureEditor-Detail. Daten via API GET /requirements?level={n} oder GETall + Frontend-Filter. Level wird vom Backend bereitgestellt (REQ-L3-EM-001).

Bezug: REQ-L1-048 (bereits als Anforderung erfasst), arch-concept-proposal-20260702.md, §2.5 (Frontend).

**Acceptance Criteria:**
1. Route `/levels` oder Tab in RequirementEditor existiert
2. Tree/Table rendert alle Requirements gruppiert by level
3. Spalten: title, level (read-only), allocated-to-owner (mit Link), status, workflow-state
4. Level-Wert vom Backend (Recursive CTE aus REQ-L3-EM-001)
5. Klick-Navigation: Req → RequirementEditor, ArchEl → ArchitectureEditor
6. API Integration: GET /requirements/{id} enthält level-Feld + allocated-to-owner info
7. Responsive UI (mobile-friendly): Tree collapsible, Tabelle scrollbar
8. Unit-Tests: Component Rendering, Navigation Links
9. Integration-Tests: Fetch Requirements with levels, Render Tree, Click Navigation

**Interfaces:**
- Input: GET /requirements (+ filter by level optional), GET /architecture/{id}
- Output: React Component mit Tree/Table, Navigation-Links

**Complexity:** Medium (UI + API-Integration, Navigation)
**Tier:** developer
**Traceability:** REQ-L1-048 (parent: Requirements UI), REQ-L3-EM-001 (parent: uses level-derivation)
**DoD:** req-traceability=true, tests=true, ui-responsive=verified, a11y-compliant=checked

---
