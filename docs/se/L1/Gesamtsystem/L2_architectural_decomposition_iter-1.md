---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-27T21:00:00Z"
schema_version: "1.0.0"
---
# L2 Architectural Decomposition — Iteration 1

> **Agent:** se-architect
> **Scope:** 9 REQs (REQ-L1-023, REQ-L1-034..041)
> **Datum:** 2026-06-27
> **Status:** done — bereit für se-critic Review
> **Input:** Phase 1 (se-requirements), Phase 2 (se-critic APPROVED_WITH_FIXES)

---

## 1. Decomposition Table

| L1 REQ | Titel | L2 System | L2 REQ-ID(s) | Component(s) | Aktion |
|--------|-------|-----------|--------------|--------------|--------|
| REQ-L1-023 | PDF-Report-Export | ApplicationServiceSystem + TraceabilityEngineSystem | REQ-L2-AS-016 (bestehend), REQ-L2-TE-013 (bestehend) | COMP-AS-008 (ExportService), COMP-TE-004 (VCRMReportGenerator) | **Keine Änderung** — bestehende Zerlegung verifiziert |
| REQ-L1-034 | ReqIF-Import/-Export | **ReqIFServiceSystem (NEU)** | REQ-L2-RQ-001, REQ-L2-RQ-002 | COMP-RQ-001 (ReqIFParser), COMP-RQ-002 (ReqIFSerializer) | **Neues L2-System** + 2 REQs + 2 COMP |
| REQ-L1-035 | Test-Run-Protokollierung | ApplicationServiceSystem | REQ-L2-AS-030 | COMP-AS-017 (TestRunService) | **Neue L2-REQ** + 1 COMP |
| REQ-L1-036 | Test-Ergebnis-Einspeisung | ApplicationServiceSystem + McpServerSystem | REQ-L2-AS-031, REQ-L2-MC-013 | COMP-AS-018 (TestResultIngestion), COMP-MC-005 (erweitert) | **2 neue L2-REQs** + 1 COMP + 1 COMP-Erweiterung |
| REQ-L1-037 | Kommentar-Threads @Mention | **CommentServiceSystem (NEU)** | REQ-L2-CM-001, REQ-L2-CM-002, REQ-L2-CM-003 | COMP-CM-001 (CommentManager), COMP-CM-002 (MentionResolver), COMP-CM-003 (NotificationDispatcher) | **Neues L2-System** + 3 REQs + 3 COMP |
| REQ-L1-038 | Semantische Vektorsuche RAG | **VectorSearchServiceSystem (NEU)** | REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003 | COMP-VS-001 (VectorSearchEngine), COMP-VS-002 (EmbeddingPipeline), COMP-VS-003 (HybridQueryRouter) | **Neues L2-System** + 3 REQs + 3 COMP |
| REQ-L1-039 | Item-Level-RBAC | AuthAndTenancySystem | REQ-L2-AT-017, REQ-L2-AT-018 | COMP-AT-005 (ItemPermissionStore) | **2 neue L2-REQs** + 1 COMP |
| REQ-L1-040 | Visuelles Artefakt-Diff | ApplicationServiceSystem + ReactFrontendSystem | REQ-L2-AS-032, REQ-L2-RF-014 | COMP-AS-019 (ArtifactDiffService), COMP-RF-005 (erweitert) | **2 neue L2-REQs** + 1 COMP + 1 COMP-Erweiterung |
| REQ-L1-041 | Visuelles Baseline-Diff | ReactFrontendSystem | REQ-L2-RF-015 | COMP-RF-006 (erweitert) | **1 neue L2-REQ** + 1 COMP-Erweiterung |

---

## 2. Platzhalter-Auflösung (Phase-2 WARN-4)

**REQ-L1-040:** Der Placeholder `REQ-L2-AS-?` wird aufgelöst zu **REQ-L2-AS-032** (ApplicationServiceSystem). Die visuelle Darstellung wird als REQ-L2-RF-014 im ReactFrontendSystem abgebildet.

---

## 3. Entscheidungen für Phase-2 Warnings

### WARN-1: REQ-L1-023 Component-IDs validieren

**Entscheidung:** Die bestehende Aufteilung wird bestätigt:
- **COMP-AS-008 (ExportService):** PDF-Export für Requirement-Dokumente (REQ-L3-EXP-004, bereits vorhanden)
- **COMP-TE-004 (VCRMReportGenerator):** PDF-Export für VCRM-Traceability-Matrix (REQ-L3-TE004-003, bereits vorhanden)

**Rationale:** Die Trennung folgt dem Orthogonalitätsprinzip — der ExportService rendert Dokument-Strukturen, der VCRMReportGenerator rendert Matrix-Strukturen. Beide nutzen eine gemeinsame PDF-Rendering-Bibliothek, aber die Template-Logik ist domänenspezifisch.

**Abgelehnte Alternative:** Zentrales PDF-Rendering-Subsystem — abgelehnt, da dies eine zusätzliche Abhängigkeit zwischen ApplicationService und TraceabilityEngine erzeugen würde, die den bestehenden Architekturmuster widerspricht.

### WARN-2: REQ-L1-038 Self-Hosted-Kompatibilität

**Entscheidung:** Die Vektorsuche wird auf **embedded pgvector** (PostgreSQL-Extension) implementiert. Kein externer Vektordatenbank-Service (Qdrant/Milvus).

**Rationale:** REQ-L1-018 (Self-Hosted Deployment) erfordert, dass alle Komponenten innerhalb eines einzelnen Deployment-Units laufen. pgvector ist eine PostgreSQL-Extension, die keine zusätzliche Infrastruktur benötigt. Die Performance-Anforderung (≤ 2s bei 10.000 Artefakten) ist mit pgvector und HNSW-Index erfüllbar.

**Abgelehnte Alternative:** Externer Qdrant-Service — abgelehnt, da dies die Deployment-Topologie verkompliziert und Self-Hosted-Betrieb erschwert.

### WARN-3: REQ-L1-039 Architektur-Pattern

**Entscheidung:** Implementierung als **PostgreSQL Row-Level Security (RLS) Policies** + Permission-Cache in der Authorization-Komponente.

**Rationale:** RLS-Policies enforce Berechtigungen auf Datenbankebene — unabhängig von Query-Pfad. Dies verhindert, dass neue API-Endpunkte versehentlich Item-Level-Regeln umgehen. Der Permission-Cache (TTL: 60s) reduziert die Evaluierungs-Latenz auf < 10% Overhead.

**Abgelehnte Alternative:** Middleware-Filter auf API-Ebene — abgelehnt, da dies jeden API-Endpunkt einzeln absichert und neue Endpunkte vergessen werden könnten. Query-Filtering im ApplicationService — abgelehnt, da dies die Geschäftslogik mit Sicherheitslogik vermischt.

### WARN-4: REQ-L1-040 Placeholder

**Entscheidung:** `REQ-L2-AS-?` → **REQ-L2-AS-032** (Artifact Field-Level Diff). Siehe Decomposition Table.

---

## 4. Neue L2-Subsysteme

### 4.1 ReqIFServiceSystem (Prefix: RQ)

**Verantwortlichkeit:** Bidirektionale Konvertierung zwischen ReqIF-XML und dem internen Datenmodell. Eigenständiges L2-System, da ReqIF-Parsing/Serialisierung eine domänenspezifische Expertise erfordert und die Testbarkeit der Roundtrip-Treue isoliert werden muss.

**Komponenten:**
- COMP-RQ-001 (ReqIFParser): Import — XML-Parsing, Schema-Validierung, Mapping auf internes Modell
- COMP-RQ-002 (ReqIFSerializer): Export — internes Modell auf ReqIF-XML serialisieren

**Schnittstellen:**
- Incoming: IF-RQ-EXT-IN-001 — Import/Export-Request vom ApplicationService
- Outgoing: IF-RQ-EXT-OUT-001 — Persistenz an PersistenceLayer
- Outgoing: IF-RQ-EXT-OUT-002 — TraceLink-CRUD an TraceabilityEngine

### 4.2 CommentServiceSystem (Prefix: CM)

**Verantwortlichkeit:** Kommentar-Threads mit @Mention-Auflösung und In-App-Notification. Eigenständiges L2-System, da Kommentar-Datenmodell, Thread-Struktur und Notification-Dispatch eine kohärente Funktionseinheit bilden, die orthogonal zu bestehenden Systemen ist.

**Komponenten:**
- COMP-CM-001 (CommentManager): CRUD für Kommentare und Thread-Struktur
- COMP-CM-002 (MentionResolver): @Mention-Parsing und Nutzer-Auflösung
- COMP-CM-003 (NotificationDispatcher): In-App-Benachrichtigungen

**Schnittstellen:**
- Incoming: IF-CM-EXT-IN-001 — Kommentar-CRUD vom ApplicationService
- Outgoing: IF-CM-EXT-OUT-001 — Audit-Log an AuditLogSystem
- Outgoing: IF-CM-EXT-OUT-002 — Nutzer-Lookup an AuthAndTenancySystem
- Outgoing: IF-CM-EXT-OUT-003 — Persistenz an PersistenceLayer

### 4.3 VectorSearchServiceSystem (Prefix: VS)

**Verantwortlichkeit:** Semantische Vektorsuche mit Embedding-Pipeline und Hybrid-Suche. Eigenständiges L2-System, da Vektordatenbank, Embedding-Generierung und Such-Orchestrierung eine spezialisierte Infrastruktur bilden.

**Komponenten:**
- COMP-VS-001 (VectorSearchEngine): pgvector-basierte Vektorsuche
- COMP-VS-002 (EmbeddingPipeline): Asynchrone Embedding-Generierung bei Artefakt-Mutation
- COMP-VS-003 (HybridQueryRouter): Kombination Vektor + Volltext mit Ranking-Fusion

**Schnittstellen:**
- Incoming: IF-VS-EXT-IN-001 — Suchanfrage vom ApplicationService
- Incoming: IF-VS-EXT-IN-002 — Domain-Event (Artefakt-Mutation) vom ApplicationService
- Outgoing: IF-VS-EXT-OUT-001 — Embedding-Generierung an LlmAdapterSystem
- Outgoing: IF-VS-EXT-OUT-002 — Persistenz an PersistenceLayer (pgvector)

---

## 5. Cross-System Interfaces (für se-interface-mgr)

| # | Source | Target | Typ | Beschreibung | Betroffene REQs |
|---|--------|--------|-----|--------------|-----------------|
| 1 | ApplicationService (Domain-Event) | VectorSearchServiceSystem | data (async) | `ArtifactCreated`/`ArtifactUpdated` Events → Embedding-Trigger | REQ-L1-038 |
| 2 | CommentServiceSystem | AuditLogSystem | data | `log_write()` für Kommentar-CRUD und @Mention-Ereignisse | REQ-L1-037 |
| 3 | AuthAndTenancySystem (ItemPermissionStore) | PersistenceLayer | control | RLS-Policy-Enforcement für Item-Level-Filterung auf Query-Ebene | REQ-L1-039 |
| 4 | ApplicationService | ReqIFServiceSystem | data | Import/Export-Request mit ReqIF-Datei / internes Modell | REQ-L1-034 |
| 5 | ApplicationService | CommentServiceSystem | data | Kommentar-CRUD-Delegation (create/list/update) | REQ-L1-037 |

**Top 3 für se-interface-mgr (Priorität nach Kopplungsgrad):**
1. **CSI-001:** ApplicationService → VectorSearchServiceSystem (Domain-Event-basierte Embedding-Triggerung)
2. **CSI-003:** AuthAndTenancySystem → PersistenceLayer (RLS-Policy-Enforcement)
3. **CSI-002:** CommentServiceSystem → AuditLogSystem (Audit-Log-Pflicht für alle Kommentar-Operationen)

---

## 6. Re-use bestehender Komponenten

| L1 REQ | Bestehende Komponente | Wiederverwendung |
|--------|----------------------|------------------|
| REQ-L1-023 | COMP-AS-008 (ExportService), COMP-TE-004 (VCRMReportGenerator) | Vollständig — REQ-L3-EXP-004 und REQ-L3-TE004-003 decken PDF-Export ab |
| REQ-L1-035 | COMP-AS-004 (TestService) | Komp-AS-004 wird um TestRun-CRUD erweitert (neuer COMP-AS-017 TestRunService) |
| REQ-L1-036 | COMP-AS-004 (TestService), COMP-MC-005 (TestToolGroup) | COMP-MC-005 wird um `test.record_result` erweitert |
| REQ-L1-040 | COMP-BL-002 (DiffEngine) | Komp-BL-002 wird NICHT erweitert — Artefakt-Diff ist ein anderes Konzept als Baseline-Diff |
| REQ-L1-041 | COMP-BL-002 (DiffEngine) | Vollständig — REQ-L3-BL002-001 liefert bereits kategorisiertes Diff |

---

## 7. Zusammenfassung

| Metrik | Wert |
|--------|------|
| **L2-REQs hinzugefügt** | 15 |
| **Komponenten erstellt** | 11 |
| **Neue L2-Subsysteme** | 3 (ReqIFServiceSystem, CommentServiceSystem, VectorSearchServiceSystem) |
| **Bestehende L2-Systeme erweitert** | 4 (ApplicationService, McpServer, AuthAndTenancy, ReactFrontend) |
| **Unverändert (verifiziert)** | 1 (REQ-L1-023 — PDF-Export) |
| **Phase-2 Warnings adressiert** | 4/4 |

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
*Nächster Schritt: se-critic Review (iteration 1)*
