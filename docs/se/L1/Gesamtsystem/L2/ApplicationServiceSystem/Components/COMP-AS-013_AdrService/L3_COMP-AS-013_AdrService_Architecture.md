---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 AdrService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-013_AdrService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der AdrService (Architectural Decision Record Service) verwaltet den vollständigen Lifecycle von ADR-Entitäten im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowFacade, verwaltet TraceLinks via TraceLinkService und publikziert Domain-Events via DomainEventBus. ADRs sind zentrale Artefakte zur Dokumentation von Architektur-Entscheidungen und deren Rationale. Der Service implementiert Versionierung (Append-Only) und garantiert Tenant-Isolation.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AdrService` (Klasse):** Orchestrator für ADR-Operationen:
  - `create_adr(title, description, context, consequences, status, workspace_id, auth_context) → ADR`
  - `update_adr(adr_id, updates) → ADR`
  - `get_adr(adr_id) → ADR`
  - `list_adr(workspace_id, page, limit) → [ADR]`
  - `delete_adr(adr_id)`
  - `transition_status(adr_id, target_status, change_reason, auth_context) → ADR`
  - `create_tracelink(adr_id, target_id, link_type) → TraceLink`

- **`AdrEntity` (Model):** Datenbank-Modell für ADRs mit Versionierung.

- **`AdrValidator` (Klasse):** Validiert ADR-Payloads gegen Schema (title 3-200 Zeichen, description max 10.000 Zeichen, status enum, etc.).

- **`AdrDTO` (DTO):** Data Transfer Object für ADR-Responses.

### 2.2 Datenstrukturen

- **ADR-Entity:**
  - `id`: UUID (PK)
  - `workspace_id`: UUID (FK)
  - `tenant_id`: UUID (FK)
  - `title`: String (3-200 Zeichen)
  - `description`: String (max 10.000 Zeichen)
  - `context`: String (optional, max 5.000 Zeichen)
  - `consequences`: String (optional, max 5.000 Zeichen)
  - `status`: enum (Draft, In Review, Approved, Rejected, Superseded)
  - `version`: Integer (Append-Only-Versionierung)
  - `created_at`: DateTime
  - `updated_at`: DateTime
  - `created_by`: String (User/Agent-ID)

- **ADRVersion-Entity:** Historische Versionen mit copy of allen ADR-Feldern + version_number.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-ADR-001 (ADR-Erstellung mit Workflow) | Methode `create_adr(payload)`: (1) Validiere payload (AdrValidator), (2) Erstelle ADR-Entity mit UUID, (3) Hole WorkflowDefinition der Workspace, (4) Initialisiere WorkflowState (status=Draft), (5) Persistiere atomare Transaktion. Rückgabe: ADR-UUID. |
| REQ-L3-ADR-002 (Update mit Versionierung) | Methode `update_adr(adr_id, updates)`: (1) Lade aktuelle Version, (2) Erstelle neue Version mit version+1, (3) Kopiere alte Version zu AdrVersion-Table, (4) Aktualisiere aktuelle Version. Timestamp und Actor erfasst. Optimistic Locking verhindert Race-Conditions. |
| REQ-L3-ADR-003 (Deletion mit Cascade-Cleanup) | Methode `delete_adr(adr_id)` in `transaction.atomic()`: (1) Lade TraceLinks (via TraceLinkService), (2) Lösche TraceLinks, (3) Lösche WorkflowState-History, (4) Lösche ADR. Bei Fehler: Rollback. |
| REQ-L3-ADR-004 (Status-Transitions) | Methode `transition_status(adr_id, target_status, change_reason)`: Delegiere an WorkflowFacade.transition(). Erlaubte Status: Draft → In Review → Approved (oder Rejected). Rejected → Draft (optional). Approved → Superseded. change_reason wird erfasst (wenn erforderlich). |
| REQ-L3-ADR-005 (TraceLink-Verwaltung) | Methode `create_tracelink(adr_id, target_id, link_type)`: Unterstützte Link-Typen: addresses, supersedes, related-to. Rufe TraceLinkService.create_trace_link() auf. Validiere link_type gegen Whitelist. Bidirektionale Querybarkeit. Link-Erstellung ist optional (keine Pflicht). |
| REQ-L3-ADR-006 (Tenant-Isolation) | Alle CRUD-Operationen: Tenant wird aus Auth-Context extrahiert. ADR wird mit tenant_id gekennzeichnet. Queries filtern nach tenant_id (Custom Manager). Keine Cross-Tenant-ADRs. Keine Cross-Tenant-TraceLinks. |
| REQ-L3-ADR-007 (Domain-Event-Publikation) | Nach erfolgreicher Mutation: Publiziere Event via DomainEventBus.publish() (post_commit Hook). Events: AdrCreated (mit UUID + Snapshot), AdrUpdated (mit Änderungen), AdrDeleted (mit UUID). Fire-and-Forget (nicht-blockierend). |
| REQ-L3-ADR-008 (Abfragen und Listing) | Methoden: get_by_id(), list_by_workspace(workspace_id, page, limit), list_by_status(status), search(query_text). Alle Queries tenant-isoliert. FTS in title/description. Pagination unterstützt. Queries performant (≤500ms für 1000 ADRs). |
| REQ-L3-ADR-009 (Schema-Validierung) | AdrValidator.validate(payload): Prüfe title (3-200 Zeichen), description (max 10.000 Zeichen), status (enum), context (optional, max 5.000), consequences (optional, max 5.000). Rückgabefehler mit Feldname und Grund. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoints für ADR CRUD (POST /adr, PUT /adr/:id, GET /adr/:id, GET /adr, DELETE /adr/:id).

- **Ausgänge (Outbound):**
  - **IF-AS-INT-002:** Aufruf TraceLinkService (`create_trace_link()`, `delete_trace_links()`) — Python Function Call.
  - **IF-AS-INT-003:** Aufruf WorkflowFacade (`transition()`) — Python Function Call.
  - **IF-AS-INT-015 (Domain-Event):** Publikation AdrCreated/Updated/Deleted Events via DomainEventBus.
  - **IF-AS-EXT-OUT-007:** ORM-Aufrufe an PersistenceLayer (INSERT/UPDATE/DELETE/SELECT).

---

## 5. Architectural Rationale

**ADR-L3-ADR-01 — Append-Only Versionierung statt In-Place Updates**

*Entscheidung:* ADR-Updates erzeugen neue Versionen (AdrVersion-Tabelle), alte Versionen bleiben unverändert.

*Rationale:* Ermöglicht vollständiges Audit-Trail und Rollback-Möglichkeiten. Architektur-Entscheidungen sind kritisch; alle Änderungen müssen nachvollziehbar sein. Alternative: In-Place-Update (überschreibe alte Werte) → Verlust von Entscheidungs-Geschichte. **Abgelehnt**: Compliance und Nachvollziehbarkeit erfordern Versionierung.

*Erfüllt Trigger:* REQ-L3-ADR-002 (Update mit Versionierung).

---

**ADR-L3-ADR-02 — TraceLinks für ADR-Relationen statt Embedded Arrays**

*Entscheidung:* ADR-Relationen (addresses, supersedes, related-to) werden als separate TraceLink-Entities modelliert, nicht als embedded Arrays.

*Rationale:* Ermöglicht flexibles Linking zwischen ADRs und anderen Artefakten (Requirements, ArchitectureElements). Separate TraceLinks sind querybar und können bidirektional durchsucht werden. Alternative: Embedded Arrays in ADR-Entity → weniger flexibel, schwerer zu querien, weniger normalisiert. **Abgelehnt**: TraceLink-Model ist universell und besser wartbar.

*Erfüllt Trigger:* REQ-L3-ADR-005 (TraceLink-Verwaltung).

---

**ADR-L3-ADR-03 — Atomare Transaktionen für Konsistenz**

*Entscheidung:* ADR-Erstellung, -Update und -Deletion erfolgen in `transaction.atomic()`. Bei Fehler: Rollback.

*Rationale:* Verhindert Partial-States (z.B. ADR erstellt, aber WorkflowState nicht initialisiert). Alternative: Keine Transaktionen → Risiko von inkonsistenten States. **Abgelehnt**: Datenintegrität ist kritisch.

*Erfüllt Trigger:* REQ-L3-ADR-001, REQ-L3-ADR-003 (Konsistenz).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
