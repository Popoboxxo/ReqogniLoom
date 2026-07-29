---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---

# L3 StateLifecycleManager Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-WE-003_StateLifecycleManager
> **Parent:** L2_WorkflowEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der StateLifecycleManager verwaltet den gesamten Lebenszyklus von Workflow-States: atomare Initialisierung mit dem Initial-State pro Item, atomare State-Mutation mit Optimistic Locking nach erfolgter Validierung, append-only History-Einträge mit Audit-Trail (from_state, to_state, transitioned_by, transitioned_at, change_reason, signature_seal), und strikte Tenant-Isolation aller Datenbankoperationen. Alle Operationen sind transaktional.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`StateLifecycleManager` (Klasse):** Orchestriert Initialisierung, State-Mutation und History-Management.
- **`WorkflowState` (Entity-Klasse):** Repräsentation des aktuellen States eines Items.
- **`WorkflowStateHistory` (Entity-Klasse):** Append-only History-Log.
- **`TransactionContext` (Klasse):** Verwaltung von Datenbanktransaktionen mit Tenant-Kontext.
- **`OptimisticLockChecker` (Klasse):** Version-basierte Concurrency-Control.

### 2.2 Datenstrukturen

- **WorkflowState-Entity:**
  - `id`: UUID (Primary Key)
  - `item_id`: UUID (Foreign Key)
  - `workspace_id`: UUID
  - `item_type`: String
  - `current_state`: String
  - `version`: Integer (für Optimistic Locking)
  - `updated_at`: DateTime (UTC)
  - `tenant_id`: UUID (Tenant-Isolation)

- **WorkflowStateHistory-Entity:**
  - `id`: UUID (Primary Key)
  - `item_id`: UUID (Foreign Key)
  - `from_state`: String
  - `to_state`: String
  - `transitioned_by`: String (User-ID oder Agent-Client-ID)
  - `transitioned_at`: DateTime (UTC, Millisekunden-Präzision)
  - `change_reason`: String (optional)
  - `signature_seal`: String (optional, HMAC-SHA256 hex, non-null nur wenn SignatureGate durchlaufen)
  - `workspace_id`: UUID
  - `tenant_id`: UUID (Tenant-Isolation)
  - `created_at`: DateTime (immutable, Append-Only-Marker)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WE003-001 (Atomare State-Initialisierung) | Methode `initialize(item_ids[], item_type, workspace_id, ctx)`: (1) Leeres Array → kein Error, kein DB-Write. (2) Query IF-WE-INT-003 an COMP-WE-001 für `initial_state`. (3) Alle item_ids in einer einzigen DB-Transaktion mit neuem WorkflowState-Record (current_state=initial_state) erzeugen. Bei Fehler: gesamte Transaktion rollback. Alle Records share transaction.commit_timestamp. |
| REQ-L3-WE003-002 (State-Mutation mit Optimistic Locking + Append-only History) | Methode `transition(item_id, from_state, to_state, transitioned_by, change_reason?, seal?, ctx)`: (1) Optimistic Lock check via `version` auf aktuelles WorkflowState. (2) Update `current_state` und inkrementiere `version`. (3) Append neuen History-Entry mit allen Feldern in **gleicher** Transaktion. Bei History-Fehler: rollback State-Update. Alte History-Entries DÜRFEN NICHT modifiziert werden (append-only Garantie via DB-Constraints). |
| REQ-L3-WE003-003 (Tenant-Isolation) | Alle read/write Queries mit `WHERE tenant_id = <active_tenant>` filtern. Missing tenant_id im Kontext → Error "Missing tenant context". Keine Exposure von Daten außerhalb aktiven Tenants. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-WE-EXT-IN-002:** ApplicationService-Methode `initialize(item_ids[], item_type, workspace_id, ctx)`.
  - **IF-WE-INT-002 (eingehend):** `ValidationResult {valid, seal?}` von TransitionValidator.
  - **IF-WE-INT-005 (eingehend):** `VerificationResult {valid, seal?}` von SignatureGateVerifier (optional, wenn Transition signature_gate hat).

- **Ausgänge (Outbound):**
  - **IF-WE-INT-003 (ausgehend):** Query an COMP-WE-001 für `initial_state` (nur während Initialisierung).
  - **IF-WE-EXT-OUT-001:** ORM-Aufrufe an PersistenceLayer (Django ORM) für WorkflowState und History-Tabellen. Alle mit Tenant-Filter.

---

## 5. Architectural Rationale

**ADR-L3-WE003-01 — Atomare Transaktion für State + History**
*Entscheidung:* State-Update und History-Append erfolgen in einer einzigen DB-Transaktion; bei History-Fehler rollback alles.
*Rationale:* Erfüllt REQ-L3-WE003-002 strikt. Verhindert inkonsistente Zustände (State geändert, aber kein History-Eintrag). Audit-Trail ist vollständig oder nichts.
*Alternative (abgelehnt):* Separate Transaktionen mit Retry-Logik — Risiko, dass History-Append fehlschlägt nach State-Update; Audit-Trail wird lückenhaft.

**ADR-L3-WE003-02 — Optimistic Locking mit Version-Counter**
*Entscheidung:* State-Mutation nutzt `version`-Feld zum Concurrency-Control statt pessimistischem Lock.
*Rationale:* Erfüllt REQ-L3-WE003-002 strikt. Bessere Performance unter hoher Concurrency. Konflikt-Erkennung erfolgt im `UPDATE`-Statement.
*Alternative (abgelehnt):* Pessimistic Row Locks — Deadlock-Risiko, niedrigerer Throughput, unnötige Contention.

**ADR-L3-WE003-03 — Append-Only History mit DB-Constraints**
*Entscheidung:* History-Tabelle hat `created_at` als Non-Nullable Immutable Field; kein UPDATE/DELETE erlaubt (nur INSERT). Logik achtet `created_at` nie zu ändern.
*Rationale:* Erfüllt REQ-L3-WE003-002 strikt. Verhindert versehentliche oder böswillige Änderung von Audit-Trail. Datenbankintegrität erzwingt Append-Only-Semantik.
*Alternative (abgelehnt):* Nur Code-Logik verhindert Updates — zu fragil, DB-Constraints sind stärker.

**ADR-L3-WE003-04 — Tenant-Filter in jedem Query**
*Entscheidung:* Jede read/write Operation explizit mit `WHERE tenant_id = <active_tenant>` filtern; Missing tenant_id → Error.
*Rationale:* Erfüllt REQ-L3-WE003-003 strikt. Verhindert Data Leakage bei Programmierfehlern. Defense-in-Depth: Kontext + Query-Filter.
*Alternative (abgelehnt):* Row-Level Security (RLS) nur — nicht ausreichend dokumentierbar für Audit, Code ist weniger explizit.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
