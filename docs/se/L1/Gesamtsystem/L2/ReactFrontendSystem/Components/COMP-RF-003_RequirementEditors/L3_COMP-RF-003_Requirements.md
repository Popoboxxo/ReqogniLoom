# L3 RequirementEditors Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-003 — RequirementEditors
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Inline-Editing fuer Requirements, Markdown-Rendering, Workflow-State-Anzeige und -Transitionen, bidirektionale Traceability-Anzeige.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-003 | Requirements-Editor mit Inline-Editing und Markdown |
| REQ-L2-RF-006 | Traceability-Anzeige (mitwirkend) |
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
| IF-RF-EXT-OUT-001 | ausgehend | RestApiAdapter | data | PATCH /api/v1/requirements/{id} — Feld-Updates |
| IF-RF-EXT-OUT-001 | eingehend | RestApiAdapter | data | GET /api/v1/requirements/{id} — Requirement-Daten und TraceLinks |

## L3 Komponenten-Anforderungen

### REQ-L3-RF003-001: Inline-Editing fuer Requirements-Felder


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die RequirementEditors-Komponente MUSS das Inline-Editing der Felder Title, Description und Category eines Requirements direkt in der Detailansicht ermöglichen, ohne einen separaten Bearbeitungsdialog zu öffnen. Aenderungen MÜSSEN per PATCH-Request an das Backend gespeichert werden. Das Description-Feld MUSS zwischen Edit-Modus und Markdown-Vorschau umschaltbar sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Click on title/description → field becomes editable inline (no modal dialog)
- [ ] Markdown preview toggleable via toggle button within the description field
- [ ] PATCH request fired on save/blur; response updates editor state
- [ ] Unit test: Render RequirementEditors with mock requirement → all fields visible and editable

---

### REQ-L3-RF003-002: Workflow-State-Anzeige und Transition


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die RequirementEditors-Komponente MUSS den aktuellen WorkflowState des Requirements prominent anzeigen und State-Übergänge über ein Dropdown ermöglichen. Nur valide Transitionen (gemaess Backend-WorkflowEngine) DÜRFEN im Dropdown angeboten werden. Nach einer Transition MUSS der angezeigte State sofort aktualisiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Current WorkflowState displayed visually (badge or label) in editor header
- [ ] Dropdown shows only valid next states as returned by the backend
- [ ] State transition triggers PATCH request; editor reflects new state on success
- [ ] Invalid transition attempt → error message displayed inline

---

### REQ-L3-RF003-003: Bidirektionale Traceability-Seitenleiste


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Die RequirementEditors-Komponente MUSS eine Seitenleiste bereitstellen, die alle verknuepften TraceLinks (Upstream und Downstream) des aktiven Requirements anzeigt, gruppiert nach Link-Typ. Ein Klick auf ein verknuepftes Artefakt MUSS die NavigationShell veranlassen, zur Detailansicht des verlinkten Artefakts zu navigieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Sidebar shows upstream and downstream links visually distinguished
- [ ] Links grouped by type (parent-child, derives-from, satisfies, verifies, implements, refines)
- [ ] Click on linked artifact → navigation to that artifact's detail view
- [ ] Integration test: Create TraceLink → link appears in both affected artifacts' sidebars

---

### REQ-L3-RF003-004: Editor-Performance bei grossem Requirement-Bestand


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Die RequirementEditors-Komponente MUSS einen Editor-Wechsel zwischen zwei Requirements innerhalb von 500 ms abschliessen — unter der Bedingung eines Workspaces mit bis zu 10.000 Requirements und einer stabilen Netzwerkverbindung.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Editor switch (artifact selection change) → new requirement rendered within 500 ms
- [ ] No full page reload on editor switch
- [ ] Performance measured at 95th percentile under 50 concurrent users

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
