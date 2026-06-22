---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 RequirementService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-002_RequirementService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der RequirementService ist die zentrale Service-Komponente für Anforderungs-CRUD und Decomposition-Orchestrierung. Er ist verantwortlich für:
- Vollständiges CRUD für Requirements mit Workflow-Integration
- Change-Reason-Validierung gegen PresetPolicy
- Atomare Decomposition mit Kind-Erstellung und TraceLink-Anlage
- LLM-gestützte Validierung und Konsistenzprüfung
- GitHub-Integration für Issue-Verlinkung

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`RequirementService` (Hauptklasse):** Orchestriert CRUD (`create`, `update`, `delete`), `decompose()`, `validate_requirement()`, `check_consistency()`, `link_github_issue()`.
- **`DecompositionOrchestrator` (Module):** Verwaltet Kinder-Erstellung, TraceLink-Anlage, Transaktionskontext.
- **`PresetPolicyValidator` (Module):** Konsultiert PresetPolicyService für `change_reason`-Pflicht.
- **`LlmValidator` (Module):** Delegiert an LlmAdapter, validiert Struktur.
- **`GitHubIntegration` (Module):** GitHub-API-Aufrufe (optional, kann bei fehlender Konfiguration offline gehen).
- **`RequirementDTO` / `DecompositionResultDTO`:** Datenstrukturen.

### 2.2 Datenstrukturen

- **Requirement-Entity:**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Tenant)
  - `title`: String
  - `description`: Text
  - `status`: String (workflow state)
  - `created_at`: DateTime
  - `updated_at`: DateTime

- **DecompositionResult:**
  ```json
  {
    "parent_id": "uuid",
    "children": [
      {"id": "uuid", "title": "string", "description": "string"}
    ],
    "trace_links": [
      {"source_id": "uuid", "target_id": "uuid", "type": "parent-child"}
    ]
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS002-001 (CRUD mit change_reason-Validierung) | `create()`: initialer WorkflowState via WorkflowFacade. `update(id, data, change_reason)`: PresetPolicyService konsultieren. `delete()`: TraceLinkService cascade aufrufen. Alle ops atomar. |
| REQ-L3-AS002-002 (Decomposition-Orchestrierung) | `decompose(req_id, children=[...], ctx)`: mit Kind-Definitionen → Validierung + Persistierung + TraceLinks + WorkflowState-Init im selben TX. Ohne Kinder → LlmAdapter + Strukturvalidierung. |
| REQ-L3-AS002-003 (LLM-Validierung) | `validate_requirement(id, ctx)`: LlmAdapter.validate() + Strukturprüfung. Fehlende LLM-Config → klar dokumentierter ConfigurationError. |
| REQ-L3-AS002-004 (GitHub-Verknüpfung) | `link_github_issue(req_id, issue_url, ctx)`: bidirektionale Speicherung. Fehler bei ungültiger URL oder fehlendem Token. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **REST API / ApplicationService:** CRUD, Decomposition, Validierungs-Aufrufe
  - **Python Function Call:** Direkte Methodenaufrufe

- **Ausgänge (Outbound):**
  - **IF-AS-INT-002:** `COMP-AS-005` (TraceLinkService) — `create_trace_link(source_id, target_id, link_type)`
  - **IF-AS-INT-003:** `COMP-AS-007` (WorkflowFacade) — `transition(item_id, target_state, change_reason, ctx)`
  - **IF-AS-INT-008:** `COMP-AS-012` (PresetPolicyService) — `is_change_reason_required(workspace_id)`
  - **IF-AS-INT-009:** `COMP-AS-013` (DomainEventBus) — Publikation `RequirementCreated / Updated / Deleted` (Outbox)
  - **IF-AS-EXT-OUT-005:** `LlmAdapter` — `validate()`, `decompose()`, `check_consistency()`
  - **IF-AS-EXT-OUT-007:** Django ORM — Requirement-Entity mit Tenant-Isolation

---

## 5. Architectural Rationale

**ADR-L3-AS002-01 — Transaktionale Decomposition als atomare Multi-Entity-Operation**

*Entscheidung:* `decompose()` erzeugt Kinder, TraceLinks und WorkflowStates in einer einzigen Datenbank-Transaktion. Fehler bei irgendeinem Child führt zu Rollback aller bisherigen.

*Rationale:*
- **Annahme:** REQ-L3-AS002-002 fordert atomare Konsistenz.
- **Gewählter Ansatz:** Django `transaction.atomic()` mit nested savepoints pro Child.
- **Abgelehnte Alternative:** Einzelne TXs pro Child → Datenlecks bei Fehler, schwer zu rückgängig machen.
- **Erfüllt REQ-L3-AS002-002:** Atomarität garantiert, Partialzustände nicht möglich.

---

**ADR-L3-AS002-02 — Explizite change_reason-Validierung via PresetPolicy**

*Entscheidung:* Vor jedem Update wird `PresetPolicyService.is_change_reason_required(workspace_id)` konsultiert. Im Extended-Preset ist `change_reason` pflicht.

*Rationale:*
- **Annahme:** Verschiedene Workspaces haben unterschiedliche Governance-Anforderungen.
- **Gewählter Ansatz:** Delegation an spezialisierte PolicyService, nicht im RequirementService hardcodiert.
- **Abgelehnte Alternative:** Hardcoded Rule im Service → nicht konfigurierbar, Änderungen erfordern Code-Deploy.
- **Erfüllt REQ-L3-AS002-001:** Validierung ist flexible und policy-konform.

---

**ADR-L3-AS002-03 — LLM-Fehlerbehandlung mit expliziter Konfigurationsprüfung**

*Entscheidung:* Wenn LLM nicht konfiguriert, wirft `validate_requirement()` einen **expliziten** `ConfigurationError` ("LLM not configured"), nicht einen stillen Fallback.

*Rationale:*
- **Annahme:** Nutzer sollen wissen, warum LLM-Features nicht verfügbar sind.
- **Gewählter Ansatz:** Frühe Konfigurationsprüfung mit klarer Fehlermeldung.
- **Abgelehnte Alternative:** Fallback auf "No validation result" → Nutzer vertraut falsches Feature.
- **Erfüllt REQ-L3-AS002-003:** Transparenz statt stillem Fallback.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
