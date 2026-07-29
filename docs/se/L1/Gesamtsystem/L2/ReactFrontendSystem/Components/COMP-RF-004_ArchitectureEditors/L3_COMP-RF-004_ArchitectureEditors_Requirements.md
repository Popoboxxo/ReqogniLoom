decomposition_status: terminal

# L3 ArchitectureEditors Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-004 — ArchitectureEditors
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

CRUD-Operationen fuer ArchitectureElements, Element-Typ-Auswahl, Markdown-Description, verknuepfte TraceLinks.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-004 | Architecture-Editor mit CRUD und Typ-Auswahl |
| REQ-L2-RF-009 | UI-Performance |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RF-INT-001 | eingehend | COMP-RF-001 | View-Activation, Modul-Aktivierung |
| IF-RF-INT-003 | eingehend | COMP-RF-001 | Artefakt-Selektion `{artifact_id, artifact_type}` |
| IF-RF-INT-002 | eingehend | COMP-RF-006 | Translation-Keys, Terminologie-Profil-Labels |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-RF-EXT-OUT-001 | ausgehend | RestApiAdapter | data | CRUD-Operationen auf /api/v1/architecture-elements/ |
| IF-RF-EXT-OUT-001 | eingehend | RestApiAdapter | data | ArchitectureElement-Daten und verknuepfte TraceLinks |

## L3 Komponenten-Anforderungen

### REQ-L3-RF004-001: CRUD-Operationen fuer ArchitectureElements


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die ArchitectureEditors-Komponente MUSS das Anlegen, Lesen, Bearbeiten und Loeschen von ArchitectureElements ermöglichen. Das Anlegen MUSS die Auswahl eines Element-Typs (Component, Interface, Subsystem, Layer, Module) ueber ein Dropdown erfordern. Eine Loeschoperation MUSS eine Bestaetigung vom Nutzer verlangen, bevor der DELETE-Request ausgeloest wird.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] User can create a new ArchitectureElement by selecting element type from dropdown
- [ ] User can edit name and description of an existing ArchitectureElement inline
- [ ] Delete action requires confirmation dialog before firing DELETE request
- [ ] Unit test: Render ArchitectureEditor with mock ArchitectureElement → all fields visible and editable

---

### REQ-L3-RF004-002: Markdown-Description-Editing


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die ArchitectureEditors-Komponente MUSS das Description-Feld eines ArchitectureElements als Markdown-faehiges Textfeld bereitstellen. Das Feld MUSS zwischen Edit-Modus und gerenderter Markdown-Vorschau umschaltbar sein. Aenderungen MÜSSEN per PATCH-Request an das Backend gespeichert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Description field renders Markdown preview when toggle is active
- [ ] Toggle switches between edit mode and preview without data loss
- [ ] PATCH request fired on save; response reflects updated description
- [ ] Markdown rendering supports headings, lists, code blocks, and bold/italic

---

### REQ-L3-RF004-003: Verknuepfte Requirements in Seitenleiste


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die ArchitectureEditors-Komponente MUSS in einer Seitenleiste alle mit dem aktiven ArchitectureElement verknuepften Requirements (via TraceLinks) anzeigen. Ein Klick auf ein verlinktes Requirement MUSS die NavigationShell veranlassen, zur Detailansicht des betreffenden Requirements zu navigieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Sidebar displays all TraceLink-connected requirements for the active ArchitectureElement
- [ ] Each linked requirement shows at minimum: ID and title
- [ ] Click on linked requirement → navigation to RequirementEditors for that requirement
- [ ] Empty sidebar shown when no TraceLinks exist (no error state)

---

---

## Erweiterung v2 — REQ-L3-RF004-004 (Dynamische Masken für AI-Native SE)

> **Datum:** 2026-07-03 | **Quelle:** User-Request "Deep Dive" (REQ-L2-RF-025)

---

### REQ-L3-RF004-004: Dynamische UI-Masken für Architecture Elements

Die ArchitectureEditors-Komponente MUSS das Eingabeformular um domänenspezifische Felder erweitern:
- Ein Dropdown für das `ASIL` Level (QM, A, B, C, D).
- Ein Dropdown für `Make or Buy` (Make, Buy, Reuse).

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] ASIL und Make-or-Buy Dropdowns sind sichtbar und editierbar.
- [ ] Die Felder `UID` und `Version` sind prominent im Header platziert und read-only.

**Traceability:** Abgeleitet von REQ-L2-RF-025

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-RF004-004 | Abgeleitet von REQ-L2-RF-025 |


---

### REQ-L3-RF004-005: L3 Context Generators Implementation

Derives from REQ-L2-REA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RF004-006: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-REA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
