---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 BaselineFacade Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-006_BaselineFacade
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Die BaselineFacade ist eine Orchestrierungs-Komponente für Baseline-Lebenszyklen. Sie ist verantwortlich für:
- Preset-basierte Scope-Validierung vor Baseline-Erstellung
- Delegierung der Baseline-Erstellung an den BaselineService
- Domain-Event-Publikation nach erfolgreicher Erstellung
- Baseline-Diff-Operationen

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`BaselineFacade` (Hauptklasse):** Orchestriert `create_baseline()`, `diff_baseline()`.
- **`ScopeValidator` (Module):** Konsultiert PresetPolicyService für Scope-Erlaubnis.
- **`BaselineOrchestrator` (Module):** Delegiert Build an BaselineService, fängt Fehler, triggert Events.
- **`BaselineDTO` / `BaselineDiffResult`:** API-Datenstrukturen.

### 2.2 Datenstrukturen

- **Baseline-Metadaten (Entity):**
  - `id`: UUID (Primary Key)
  - `workspace_id`: UUID (Tenant)
  - `scope`: String (minimal|project|global)
  - `created_at`: DateTime
  - `immutable_flag`: Boolean (true nach Erstellung, keine Updates erlaubt)

- **BaselineDiffResult:**
  ```json
  {
    "baseline_a_id": "uuid",
    "baseline_b_id": "uuid",
    "added": [{"id": "uuid", "name": "string"}],
    "removed": [{"id": "uuid", "name": "string"}],
    "changed": [{"id": "uuid", "old": "...", "new": "..."}]
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AS006-001 (Preset-gesteuerter Scope-Check) | `create_baseline(scope, workspace_id, ctx)`: ScopeValidator konsultiert PresetPolicyService.is_scope_allowed(). Bei Nein: PolicyError werfen. Bei Ja: BaselineService.build() aufrufen. |
| REQ-L3-AS006-002 (Baseline-Erstellung und Event) | Nach BaselineService.build(): `BaselineCreated`-Event im Outbox publizieren. Immutable-Flag setzen. Rollback bei Fehler. |
| REQ-L3-AS006-003 (Diff-Operation) | `diff_baseline(baseline_id_a, baseline_id_b, ctx)`: Beide laden, Workspace-Konsistenz prüfen, an BaselineService.diff(a, b) delegieren. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **REST API / ApplicationService:** `create_baseline()`, `diff_baseline()`
  - **Python Function Call:** Direkte Methodenaufrufe

- **Ausgänge (Outbound):**
  - **IF-AS-INT-006:** `COMP-AS-012` (PresetPolicyService) — `is_scope_allowed(workspace_id, scope)`
  - **IF-AS-INT-012:** `COMP-AS-013` (DomainEventBus) — Publikation `BaselineCreated` (Outbox)
  - **IF-AS-EXT-OUT-002:** `BaselineService` — `build(scope, workspace_id, ctx)`, `diff(a, b)`
  - **IF-AS-EXT-OUT-007:** Django ORM — Baseline-Metadaten mit Tenant-Isolation

---

## 5. Architectural Rationale

**ADR-L3-AS006-01 — Preset-Konsultation vor Delegation an BaselineService**

*Entscheidung:* Die BaselineFacade prüft die Scope-Erlaubnis mittels PresetPolicyService, bevor der BaselineService aufgerufen wird.

*Rationale:*
- **Annahme:** Verschiedene Presets (Minimal, Standard, Extended) haben unterschiedliche Scope-Beschränkungen. Diese sind Policy-Entscheidungen, nicht technische.
- **Gewählter Ansatz:** Facade pattern mit expliziter Policy-Prüfung als Gatekeeper.
- **Abgelehnte Alternative:** BaselineService führt Prüfung selbst durch → Coupling zwischen BaselineService und Policy-Engine.
- **Erfüllt REQ-L3-AS006-001:** Governance ist deklarativ und zentralisiert.

---

**ADR-L3-AS006-02 — Immutable-Flag und Event-Publikation in derselben TX**

*Entscheidung:* Nach erfolgreicher BaselineService.build() wird immutable_flag gesetzt UND `BaselineCreated`-Event im Outbox publiziert — beide in der gleichen DB-TX.

*Rationale:*
- **Annahme:** REQ-L3-AS006-002 fordert Unveränderlichkeit NACH Erstellung; Events müssen veröffentlicht werden.
- **Gewählter Ansatz:** Atomare TX mit beiden Operationen.
- **Abgelehnte Alternative:** Immutable-Flag in BaselineService, Event async elsewhere → Datenlecks möglich.
- **Erfüllt REQ-L3-AS006-002:** Atomarität ist garantiert, keine Partial-States.

---

**ADR-L3-AS006-03 — Diff-Validierung vor BaselineService-Delegation**

*Entscheidung:* `diff_baseline()` prüft, dass beide Baselines zum gleichen Workspace gehören, bevor BaselineService.diff() aufgerufen wird.

*Rationale:*
- **Annahme:** Cross-Workspace-Diffs würden Tenant-Isolation brechen.
- **Gewählter Ansatz:** Validierung in der Facade, bevor Delegation.
- **Abgelehnte Alternative:** BaselineService validiert selbst → nicht klar, in welcher Schicht die Validierung stattfindet.
- **Erfüllt REQ-L3-AS006-003:** Sicherheit ist an der Facade durchgesetzt.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
