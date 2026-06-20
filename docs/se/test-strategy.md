# ReqFlow — Teststrategie & Testmodelle

> **Status:** KONSOLIDIERT | **Datum:** 2026-06-20
> **Scope:** 12 L2-Subsysteme, 55 Komponenten, 136 REQ-L2, 95 Schnittstellen
>
> **Quellen (autoritativ):**
> - 12 L2-Architekturen: `docs/se/L1/Gesamtsystem/L2/*/L2_*_Architecture.md`
> - 2 L3-Architekturen: `docs/se/L1/Gesamtsystem/L2/{ApplicationServiceSystem,McpServerSystem}/L3/`
> - Interface-Registry: `docs/se/interface-registry.md`
> - Traceability-Matrix: `docs/se/traceability-matrix.md`
> - Integration-Strategy: `docs/se/integration-strategy.md`

---

## 1. Testphilosophie

### 1.1 Grundsätze

Die ReqFlow-Teststrategie folgt dem **rechten V-Modus-Flügel** mit MBSE-Prinzipien (Model-Based Systems Engineering). Jedes Testszenario tracebar zu mindestens einer Architekturanforderung. Tests sind ausgelegt auf **Determinismus**, **Unabhängigkeit** und **Minimalität**.

### 1.2 Risikobasierte Priorisierung

Tests werden nach Risiko priorisiert. Höchste Priorität haben Sicherheit und Datenkonsistenz.

| Priorität | Risikobereich | Begründung |
|-----------|---------------|------------|
| **P0 — Kritisch** | Tenant-Isolation, Datenkonsistenz (ACID), Audit-Trail-Vollständigkeit | Sicherheitskritisch; Datenleck = Systemkompromittierung |
| **P1 — Hoch** | Workflow-State-Machines, Baseline-Immutabilität, Traceability-Graph-Integrität | Kern-Domänenlogik; Fehler = funktionale Defekte |
| **P2 — Mittel** | Preset-abhängiges Verhalten, Performance-SLAs, API-Validierung | Benutzererfahrung; Fehler = degraded UX |
| **P3 — Standard** | UI-Rendering, i18n, Export-Formate | Präsentationschicht; Fehler = kosmetisch |

### 1.3 Testebenen

| Ebene | Scope | Granularität | Ausführung |
|-------|-------|--------------|------------|
| **L0 — Unit-Test** | Einzelne L3-Units (für Continue-Systeme) oder L2-Komponenten (für Leaf-Systeme) | Einzelne Funktion/Klasse | pytest (Backend), Jest (Frontend) |
| **L1 — Komponenten-Integration** | Inter-Komponenten-Schnittstellen innerhalb eines L2-Systems | L2-interne Schnittstellen (IF-*-INT-*) | pytest mit Stubs/Drivers |
| **L2 — System-Integration** | Inter-System-Schnittstellen über L2-Systemgrenzen | L1-Schnittstellen (IF-L1-*) | Django Test Client, MCP Test Harness |
| **L3 — End-to-End** | Vollständige User-Journeys über alle Systeme | Externe Schnittstellen (IF-EXT-*) | Docker Compose + Playwright |

---

## 2. Testmodelle — Leaf-Systeme (10 Systeme)

### 2.1 PersistenceLayerSystem (ARCH-L1-010) — 9 REQ-L2, 5 Komponenten

**Integrationsstrategie:** Schritt 1 (Foundation — keine Abhängigkeiten)
**Risiko:** HOCH — alle nachfolgenden Schritte dependieren davon

#### Komponententests

| TC-ID | Komponente | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------------|----------|--------------|----------|-------------------|-----------|
| TC-Persist-001 | COMP-PL-001 EntitySchemaManager | Alle 13 Entity-Schemas korrekt definiert | Leere Test-DB | `makemigrations --check` | Keine pending Migrations; alle Models haben Audit-Felder | REQ-L2-Persist-004, 005 |
| TC-Persist-002 | COMP-PL-001 EntitySchemaManager | Referentielle Integrität | DB mit Entities | Entity mit FK-Referenzen löschen | IntegrityError; CASCADE-Regeln respektiert | REQ-L2-Persist-009 |
| TC-Persist-003 | COMP-PL-002 TenantIsolationManager | **Automatischer Tenant-Filter** | Zwei Tenants mit Daten | Query ohne expliziten Tenant-Filter | Nur Daten des aktuellen Tenants zurückgegeben | REQ-L2-Persist-001 |
| TC-Persist-004 | COMP-PL-002 TenantIsolationManager | **TenantContextNotSetError** | Kein Tenant-Context gesetzt | ORM-Query ausführen | TenantContextNotSetError | REQ-L2-Persist-001 |
| TC-Persist-005 | COMP-PL-002 TenantIsolationManager | **Raw-SQL-Bypass-Prävention** | Tenant-Context gesetzt | Raw SQL ohne Manager ausführen | Raw SQL blockiert oder Tenant-Filter erzwungen | REQ-L2-Persist-001 |
| TC-Persist-006 | COMP-PL-003 TransactionCoordinator | **Atomarer Rollback** | Gültiger DB-Zustand | Multi-Entity-Operation die mitten scheitert | Alle Änderungen zurückgerollt | REQ-L2-Persist-002 |
| TC-Persist-007 | COMP-PL-003 TransactionCoordinator | **Atomarer Commit** | Gültiger DB-Zustand | Multi-Entity-Operation erfolgreich | Alle Änderungen atomar committet | REQ-L2-Persist-002 |
| TC-Persist-008 | COMP-PL-004 SchemaMigrationEngine | Forward-Migration von leerer DB | Leeres PostgreSQL | `migrate` ausführen | Alle Tabellen erstellt; Schema entspricht Models | REQ-L2-Persist-003 |
| TC-Persist-009 | COMP-PL-004 SchemaMigrationEngine | Migrations-Idempotenz | Bereits migrierte DB | `migrate` erneut ausführen | Keine Änderungen; keine Fehler | REQ-L2-Persist-003 |
| TC-Persist-010 | COMP-PL-005 PerformanceOptimizationLayer | Index-Existenz | Migrierte DB | DB-Indizes inspizieren | BTree/GIN/tsvector-Indizes auf konfigurierten Feldern | REQ-L2-Persist-006 |
| TC-Persist-011 | COMP-PL-005 PerformanceOptimizationLayer | **Query-Latenz-SLA** | 10.000 Items geladen | Full-Text-Search-Query | Response < 500ms (p95) | REQ-L2-Persist-007 |
| TC-Persist-012 | COMP-PL-005 PerformanceOptimizationLayer | Connection-Pooling | Aktive Verbindungen | Parallele Queries | Pool recycelt Connections; keine Erschöpfung | REQ-L2-Persist-008 |
| TC-Persist-013 | COMP-PL-001 EntitySchemaManager | **Audit-Felder bei Erstellung** | Leere Test-DB | Entity erstellen | `created_by`, `created_at`, `modified_by`, `modified_at` gesetzt; `version` == 1 | REQ-L2-Persist-005 |
| TC-Persist-014 | COMP-PL-001 EntitySchemaManager | **Audit-Felder bei Update** | Existierendes Entity | Entity aktualisieren | `modified_at` und `modified_by` geändert; `created_at` unverändert; `version` inkrementiert | REQ-L2-Persist-005 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-Persist-01 | PL-001 + PL-002 | IF-PL-INT-001 | Driver: Test-Queries | TenantQuerySet filtert alle Entity-Queries korrekt |
| IT-Persist-02 | PL-003 + PL-001 | IF-PL-INT-002 | Driver: Multi-Entity-Write | transaction.atomic() umschließt ORM-Operationen; Rollback bei Fehler |
| IT-Persist-03 | PL-004 + PL-001 | IF-PL-INT-003 | None | Migrations aus models.py generiert; Operations-Liste korrekt |
| IT-Persist-04 | PL-004 + PL-005 | IF-PL-INT-004 | None | Migrations enthalten AddIndex-Operationen |
| IT-Persist-05 | PL-005 + PL-001 | IF-PL-INT-005 | None | Meta.indexes und tsvector-Felder in Model-Definitionen |

---

### 2.2 AuthAndTenancySystem (ARCH-L1-011) — 10 REQ-L2, 8 Komponenten

**Integrationsstrategie:** Schritt 2 (abhängig von PersistenceLayer)
**Risiko:** HOCH — Tenant-Isolation ist sicherheitskritisch

#### Komponententests

| TC-ID | Komponente | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------------|----------|--------------|----------|-------------------|-----------|
| TC-Auth-001 | COMP-AT-001 AuthMiddleware | Request-Interception | Laufender Server | Request an geschützten Endpunkt ohne Auth | 401; standardisiertes Fehlerformat | REQ-L2-Auth-007 |
| TC-Auth-002 | COMP-AT-001 AuthMiddleware | Health-Endpoint-Bypass | Laufender Server | Request an /health ohne Auth | 200; keine Auth erforderlich | REQ-L2-Auth-007 |
| TC-Auth-003 | COMP-AT-002 BearerTokenValidator | **Gültiges JWT akzeptiert** | Gültiges JWT in DB | Gültiges JWT übergeben | IdentityClaims mit user_id, roles | REQ-L2-Auth-001 |
| TC-Auth-004 | COMP-AT-002 BearerTokenValidator | **Abgelaufenes JWT abgelehnt** | Abgelaufenes JWT | Abgelaufenes JWT übergeben | 401 "token_expired" | REQ-L2-Auth-001 |
| TC-Auth-005 | COMP-AT-002 BearerTokenValidator | **Ungültige Signatur abgelehnt** | Manipuliertes JWT | JWT mit falscher Signatur | 401 "invalid_signature" | REQ-L2-Auth-001 |
| TC-Auth-006 | COMP-AT-003 ApiKeyValidator | **Gültiger API-Key akzeptiert** | Gültiger gehashter API-Key in DB | Gültiger API-Key | IdentityClaims mit user_id, tenant_id | REQ-L2-Auth-002 |
| TC-Auth-007 | COMP-AT-003 ApiKeyValidator | **Widerrufener API-Key abgelehnt** | Widerrufener API-Key | Widerrufener API-Key | 401 "api_key_revoked" | REQ-L2-Auth-002 |
| TC-Auth-008 | COMP-AT-003 ApiKeyValidator | **Constant-Time-Vergleich** | Gültiger API-Key | Timing-Attacke mit variierenden Key-Längen | Keine Timing-Side-Channel; konstante Ausführungszeit | REQ-L2-Auth-002 |
| TC-Auth-009 | COMP-AT-004 TenantResolver | Tenant-Extraktion aus Claims | Gültige Identity-Claims | Tenant resolvieren | TenantContext mit korrekter tenant_id | REQ-L2-Auth-003 |
| TC-Auth-010 | COMP-AT-004 TenantResolver | **Fehlender Tenant abgelehnt** | Claims ohne Tenant | Tenant resolvieren | 500; Request abgelehnt | REQ-L2-Auth-003 |
| TC-Auth-011 | COMP-AT-005 AccessControlEngine | **RBAC-Allow für autorisierte Rolle** | User mit 'editor'-Rolle | Permission-Check für 'edit_requirement' | PermissionDecision: ALLOW | REQ-L2-Auth-004 |
| TC-Auth-012 | COMP-AT-005 AccessControlEngine | **RBAC-Deny für nicht-autorisierte Rolle** | User mit 'viewer'-Rolle | Permission-Check für 'edit_requirement' | PermissionDecision: DENY | REQ-L2-Auth-004 |
| TC-Auth-013 | COMP-AT-005 AccessControlEngine | **Preset-aware Approver-Rolle** | Standard-Preset-Workspace | Permission-Check für 'approve_requirement' | DENY (Approver nur in Extended) | REQ-L2-Auth-005 |
| TC-Auth-014 | COMP-AT-006 RoleStore | Rollen-Definitionen geladen | DB mit Rollen | Alle Rollen abfragen | Vollständige Rollenliste | REQ-L2-Auth-006 |
| TC-Auth-015 | COMP-AT-007 TenantContextManager | Tenant-Context-Propagation | Gültiger Tenant-Context | Tenant-Context setzen; Query ausführen | tenant_id automatisch angewendet | REQ-L2-Auth-008 |
| TC-Auth-016 | COMP-AT-008 AuthContextBuilder | **Vollständiger AuthContext** | Gültige Identity + Tenant | Context bauen | AuthContext mit identity, tenant, roles, permissions | REQ-L2-Auth-009 |
| TC-Auth-017 | COMP-AT-008 AuthContextBuilder | **Immutabler Context** |gebauter AuthContext | Context modifizieren | ImmutableError oder keine Wirkung | REQ-L2-Auth-010 |
| TC-Auth-018 | COMP-AT-001 AuthMiddleware | **Standardisiertes 401-Response** | Kein Auth-Token | Geschützten Endpunkt aufrufen | 401 mit JSON: {error_code, message, details} | REQ-L2-Auth-010 |
| TC-Auth-019 | COMP-AT-003 ApiKeyValidator | **API-Key-Erstellung** | Gültiger Auth-Context | API-Key erstellen | Plaintext im Response; SHA-256-Hash in DB | REQ-L2-Auth-009 |
| TC-Auth-020 | COMP-AT-003 ApiKeyValidator | **API-Key-Liste** | Mehrere API-Keys | API-Keys auflisten | Keine Plaintext-Keys exponiert | REQ-L2-Auth-009 |
| TC-Auth-021 | COMP-AT-003 ApiKeyValidator | **API-Key-Limit** | 10 API-Keys existieren | 11. API-Key erstellen | Abgelehnt (max 10) | REQ-L2-Auth-009 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-Auth-01 | AT-001 + AT-002 | INT-L2-A-001 | Driver: HTTP-Request mit JWT | BearerTokenValidator validiert korrekt und liefert Claims |
| IT-Auth-02 | AT-001 + AT-003 | INT-L2-A-002 | Driver: HTTP-Request mit API-Key | ApiKeyValidator validiert korrekt und liefert Claims |
| IT-Auth-03 | AT-001 + AT-004 | INT-L2-A-003 | Stub: IdentityClaims | TenantResolver extrahiert Tenant aus Claims |
| IT-Auth-04 | AT-001 + AT-005 | INT-L2-A-004 | Stub: AuthContext | AccessControlEngine liefert korrekte Permission-Decision |
| IT-Auth-05 | AT-001 + AT-008 | INT-L2-A-005 | Stub: identity, tenant | AuthContextBuilder baut vollständigen immutablen Context |

---

### 2.3 PresetConfigEngineSystem (ARCH-L1-008) — 14 REQ-L2, 1 Komponente (Terminal)

**Integrationsstrategie:** Schritt 3 (abhängig von PersistenceLayer)
**Risiko:** MITTEL — einzelne Komponente, klar definierter Kontrakt

#### Komponententests (Black-Box — Single Component)

| TC-ID | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|----------|--------------|----------|-------------------|-----------|
| TC-Preset-001 | get_preset liefert korrekte Config | Workspace mit 'standard'-Preset | `get_preset(workspace_id)` | PresetConfig mit korrekten mandatory_fields, features | REQ-L2-Preset-001 |
| TC-Preset-002 | is_feature_enabled für Baselines in Minimal | Minimal-Preset-Workspace | `is_feature_enabled("baselines", workspace_id)` | false | REQ-L2-Preset-002 |
| TC-Preset-003 | is_feature_enabled für Baselines in Standard | Standard-Preset-Workspace | `is_feature_enabled("baselines", workspace_id)` | true | REQ-L2-Preset-002 |
| TC-Preset-004 | is_feature_enabled für Global-Baselines in Extended | Extended-Preset-Workspace | `is_feature_enabled("global_baselines", workspace_id)` | true | REQ-L2-Preset-003 |
| TC-Preset-005 | **validate_downgrade blockiert bei existierenden Baselines** | Workspace mit Baselines | `validate_downgrade(ws_id, "minimal")` | CompatibilityResult: INCOMPATIBLE mit Begründung | REQ-L2-Preset-004 |
| TC-Preset-006 | validate_downgrade erlaubt bei keinen inkompatiblen Items | Sauberer Workspace | `validate_downgrade(ws_id, "minimal")` | CompatibilityResult: COMPATIBLE | REQ-L2-Preset-004 |
| TC-Preset-007 | mandatory_fields pro Preset | Jeder Preset-Typ | `get_preset(ws_id).mandatory_fields` | Korrekte Feld-Sets pro Entity-Typ | REQ-L2-Preset-005 |
| TC-Preset-008 | get_terminology_profile für Dev-Modus | Dev-Modus-Workspace | `get_terminology_profile(ws_id)` | TerminologyMapping: Requirement→Story, etc. | REQ-L2-Preset-009 |
| TC-Preset-009 | get_terminology_profile für SE-Modus | SE-Modus-Workspace | `get_terminology_profile(ws_id)` | TerminologyMapping: Requirement→Requirement, etc. | REQ-L2-Preset-009 |
| TC-Preset-010 | Workflow-Konfigurierbarkeit pro Preset | Jeder Preset | Workflow-Regeln abfragen | Minimal: fix; Standard/Extended: konfigurierbar | REQ-L2-Preset-006 |
| TC-Preset-011 | change_reason-Policy pro Preset | Jeder Preset | change_reason-Regeln abfragen | Minimal/Standard: optional; Extended: obligatorisch | REQ-L2-Preset-007 |
| TC-Preset-012 | is_scope_allowed für Document-Scope | Standard-Preset | `is_scope_allowed(ws_id, "document")` | true | REQ-L2-Preset-005 |
| TC-Preset-013 | is_scope_allowed für Global-Scope in Standard | Standard-Preset | `is_scope_allowed(ws_id, "global")` | false | REQ-L2-Preset-005 |
| TC-Preset-014 | Preset-Wechsel triggert Feature-Neuberechnung | Workspace-Preset geändert | Preset wechseln; Features abfragen | Aktualisiertes Feature-Set | REQ-L2-Preset-011 |
| TC-Preset-015 | **Preset-Wechsel ohne Datenmigration** | Workspace mit Daten in Standard | Wechsel zu Minimal | PresetConfig aktualisiert; Daten unverändert; keine Migration | REQ-L2-Preset-008 |
| TC-Preset-016 | **Terminologie-Wechsel ohne Datenmigration** | Workspace mit SE-Terminologie | Wechsel zu Dev-Terminologie | TerminologyMapping aktualisiert; DB-Labels unverändert | REQ-L2-Preset-010 |
| TC-Preset-017 | **Default-Preset ist immutable** | System-Default-Preset-Config | Default-Preset-Definition modifizieren | Operation rejected; ImmutablePresetError | REQ-L2-Preset-012 |

---

### 2.4 AuditLogSystem (ARCH-L1-012) — 7 REQ-L2, 1 Komponente (Terminal)

**Integrationsstrategie:** Schritt 4 (abhängig von PersistenceLayer)
**Risiko:** NIEDRIG — einfaches Append-Only-Pattern

#### Komponententests (Black-Box — Single Component)

| TC-ID | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|----------|--------------|----------|-------------------|-----------|
| TC-Audit-001 | **Append-Only-Log-Write** | Gültiger Auth-Context | `log_write(actor, op, entity_type, entity_id, ...)` | AuditLogEntry erstellt; immutable | REQ-L2-AuditLog-001 |
| TC-Audit-002 | **UPDATE-Rejektion** | Existierender Entry | UPDATE auf Entry versuchen | DB-Constraint-Verletzung; Operation rejected | REQ-L2-AuditLog-002 |
| TC-Audit-003 | **DELETE-Rejektion** | Existierender Entry | DELETE auf Entry versuchen | DB-Constraint-Verletzung; Operation rejected | REQ-L2-AuditLog-002 |
| TC-Audit-004 | **MCP-spezifische Anreicherung** | MCP-Schreiboperation | `log_write(source="mcp", client_name="Claude", api_key_hash="abc")` | Entry enthält source, client_name, api_key_hash | REQ-L2-AuditLog-003 |
| TC-Audit-005 | **Atomare Konsistenz mit Geschäftsoperation** | In-Transaction-Context | Schreiboperation + Audit-Log in gleicher Transaktion | Beide committet oder beide zurückgerollt | REQ-L2-AuditLog-004 |
| TC-Audit-006 | Paginierte Query mit Filtern | 100+ Audit-Entries | `query(entity_id=X, page=1, page_size=10)` | 10 Ergebnisse; total_count korrekt; Pagination-Info | REQ-L2-AuditLog-005 |
| TC-Audit-007 | **Tenant-Isolation in Queries** | Zwei Tenants mit Entries | Query als Tenant A | Nur Tenant-A-Entries zurückgegeben | REQ-L2-AuditLog-006 |
| TC-Audit-008 | **Query-Performance-SLA** | 100.000 Audit-Entries | Gefilterte Query ausführen | Response < 200ms (p95) | REQ-L2-AuditLog-007 |

---

### 2.5 LlmAdapterSystem (ARCH-L1-009) — 7 REQ-L2, 4 Komponenten

**Integrationsstrategie:** Schritt 5 (abhängig von AuditLog)
**Risiko:** MITTEL — externe Abhängigkeit via MockLlmProvider abstrahiert

#### Komponententests

| TC-ID | Komponente | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------------|----------|--------------|----------|-------------------|-----------|
| TC-Llm-001 | COMP-LA-001 CapabilityInterface | Interface-Kontrakt | Provider implementiert | `validate_artifact()` aufrufen | LlmResult mit strukturierter Antwort | REQ-L2-Llm-001 |
| TC-Llm-002 | COMP-LA-001 CapabilityInterface | Standardisiertes Ergebnisformat | Beliebiger Capability-Call | Capability ausführen | LlmResult/LlmDecompositionResult/LlmConsistencyResult | REQ-L2-Llm-004 |
| TC-Llm-003 | COMP-LA-002 ProviderPool | Anthropic-Provider via MockLlmProvider | MockLlmProvider als Anthropic konfiguriert | Call via AnthropicProvider | Valides LlmResult vom Mock; kein Live-API-Call | REQ-L2-Llm-005 |
| TC-Llm-004 | COMP-LA-002 ProviderPool | OpenAI-Provider via MockLlmProvider | MockLlmProvider als OpenAI konfiguriert | Call via OpenAiProvider | Valides LlmResult vom Mock; kein Live-API-Call | REQ-L2-Llm-005 |
| TC-Llm-005 | COMP-LA-002 ProviderPool | Ollama-Provider via MockLlmProvider | MockLlmProvider als Ollama konfiguriert | Call via OllamaProvider | Valides LlmResult vom Mock; kein Live-API-Call | REQ-L2-Llm-005 |
| TC-Llm-006 | COMP-LA-002 ProviderPool | **Provider-Timeout** | MockLlmProvider mit Delay > Timeout | Call mit timeout=5s; Mock delayt 10s | TimeoutError nach konfigurierter Dauer | REQ-L2-Llm-005 |
| TC-Llm-006b | COMP-LA-002 ProviderPool | **Provider-Error-Response** | MockLlmProvider gibt Fehler zurück | Capability aufrufen; Mock gibt Fehler | LlmError propagiert; Graceful Degradation | REQ-L2-Llm-005 |
| TC-Llm-006c | COMP-LA-002 ProviderPool | Token-Usage aus Mock-Response | MockLlmProvider gibt Usage-Dict zurück | Capability aufrufen; Usage extrahieren | prompt_tokens, completion_tokens korrekt geparst | REQ-L2-Llm-007 |
| TC-Llm-007 | COMP-LA-003 CapabilityRegistry | **Graceful Degradation ohne Config** | Keine LLM-Config (.env leer) | Beliebige Capability aufrufen | Strukturierter Fehler: "LLM not configured" | REQ-L2-Llm-002 |
| TC-Llm-008 | COMP-LA-003 CapabilityRegistry | **Selektive Capability-Aktivierung** | Nur 'validate' aktiviert | 'decompose' aufrufen | Fehler: capability not enabled | REQ-L2-Llm-003 |
| TC-Llm-009 | COMP-LA-003 CapabilityRegistry | Provider-Selektion aus Config | Provider konfiguriert | Capability aufrufen | Korrekte Provider-Instanz verwendet | REQ-L2-Llm-002 |
| TC-Llm-010 | COMP-LA-004 LlmAuditLogger | **Audit-Entry nach LLM-Call** | Erfolgreicher LLM-Call | Capability ausführen | AuditLog-Entry mit provider, capability, token_usage | REQ-L2-Llm-006 |
| TC-Llm-011 | COMP-LA-004 LlmAuditLogger | **Audit-Entry bei Fehler** | Fehlgeschlagener LLM-Call | Capability die fehlschlägt ausführen | AuditLog-Entry mit error details, source="llm_adapter" | REQ-L2-Llm-006 |
| TC-Llm-012 | COMP-LA-004 LlmAuditLogger | Token-Usage-Extraktion | Provider-Response mit Usage | Token-Usage extrahieren | Dict mit prompt_tokens, completion_tokens | REQ-L2-Llm-007 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-Llm-01 | LA-003 → LA-001 | IF-LA-INT-001 | Stub: Provider | CapabilityRegistry delegiert an korrekte Interface-Methode |
| IT-Llm-02 | LA-003 → LA-002 | IF-LA-INT-002 | Stub: Config | Korrekte Provider-Instanz basierend auf Config zurückgegeben |
| IT-Llm-03 | LA-002 → LA-001 | IF-LA-INT-003 | None | Alle Provider implementieren LlmCapabilityInterface |
| IT-Llm-04 | LA-004 → LA-003 | IF-LA-INT-004 | Stub: AuditLog | Audit-Hook nach Capability-Ausführung getriggert |
| IT-Llm-05 | LA-004 → LA-002 | — | Stub: Provider-Response | Token-Usage korrekt aus Provider-spezifischem Format extrahiert |

---

### 2.6 TraceabilityEngineSystem (ARCH-L1-007) — 12 REQ-L2, 4 Module (Terminal)

**Integrationsstrategie:** Schritt 6 (abhängig von PersistenceLayer)
**Risiko:** MITTEL — Graph-Query-Performance kritisch

#### Komponententests

| TC-ID | Modul | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|-------|----------|--------------|----------|-------------------|-----------|
| TC-Trace-001 | TraceLink-CRUD | TraceLink-Erstellung | Gültige Source + Target-Entities | `create(source_id, target_id, link_type)` | TraceLink persistiert; Audit-Entry erstellt | REQ-L2-Trace-001 |
| TC-Trace-002 | TraceLink-CRUD | **Source/Target-Validierung** | Nicht-existente Source | `create(invalid_source, target, type)` | ValidationError | REQ-L2-Trace-002 |
| TC-Trace-003 | TraceLink-CRUD | **Workspace-Konsistenz-Check** | Source in WS A, Target in WS B | `create(source_a, target_b, type)` | WorkspaceConsistencyError | REQ-L2-Trace-002 |
| TC-Trace-004 | TraceLink-CRUD | Link-Type-Validierung | Ungültiger Link-Typ | `create(source, target, "invalid_type")` | ValidationError mit erlaubten Typen | REQ-L2-Trace-001 |
| TC-Trace-005 | TraceLink-CRUD | TraceLink-Löschung | Existierender TraceLink | `delete(tracelink_id)` | TraceLink entfernt; Cascade behandelt | REQ-L2-Trace-009 |
| TC-Trace-006 | Graph-Query | Upstream-Query | Entity mit Upstream-Links | `query(entity_id, "upstream")` | Alle Upstream-Entities zurückgegeben | REQ-L2-Trace-004 |
| TC-Trace-007 | Graph-Query | Downstream-Query | Entity mit Downstream-Links | `query(entity_id, "downstream")` | Alle Downstream-Entities zurückgegeben | REQ-L2-Trace-004 |
| TC-Trace-008 | Graph-Query | **Query-Performance** | 10.000 Items, 50.000 Links | Graph-Query ausführen | Response < 200ms (p95) | REQ-L2-Trace-005 |
| TC-Trace-009 | Coverage-Engine | Coverage-Berechnung | Requirements mit/ohne Test-Links | `coverage(workspace_id)` | Prozentsatz mit Breakdown nach Typ | REQ-L2-Trace-006 |
| TC-Trace-010 | Coverage-Engine | Coverage-Filter nach Typ | Gemischte Entity-Typen | `coverage(ws_id, types=["requirement"])` | Nur Requirement-Coverage | REQ-L2-Trace-007 |
| TC-Trace-011 | Snapshot-Collector | Trace-Graph-Collection | Workspace mit verknüpften Items | `collect_trace_graph(workspace_id)` | Vollständige item_ids, Versionen, trace_links | REQ-L2-Trace-008 |
| TC-Trace-012 | Snapshot-Collector | **Collection-Performance** | Großer Workspace (10k Items) | `collect_trace_graph(ws_id)` | Vollständige Collection < 500ms | REQ-L2-Trace-008 |
| TC-Trace-013 | TraceLink-CRUD | **Batch-Erstellung** | Gültige Source/Target-Paare (50+) | `batch_create([(s1,t1,type), ...])` | Alle TraceLinks atomar persistiert | REQ-L2-Trace-003 |
| TC-Trace-014 | TraceLink-CRUD | **Batch-Partial-Failure-Rollback** | 50 Paare, ein ungültiges Target | `batch_create([...invalid...])` | Gesamter Batch zurückgerollt; ValidationError | REQ-L2-Trace-003 |
| TC-Trace-015 | Graph-Query | **Transitive-Closure-Berechnung** | Kette: A→B→C→D | `transitive_closure(entity_id=A, depth=3)` | Alle erreichbaren Entities {B, C, D} mit Tiefen-Info | REQ-L2-Trace-005 |
| TC-Trace-016 | Graph-Query | **Transitive-Closure mit Cycle-Schutz** | Graph mit potenziellem Cycle | `transitive_closure(entity_id=X)` | Terminiert; kein Infinite-Loop | REQ-L2-Trace-005 |
| TC-Trace-017 | TraceLink-CRUD | **Audit-Metadaten** | Gültige TraceLink-Operationen | Create, dann Delete TraceLink | Jede Operation produziert Audit-Entry | REQ-L2-Trace-010 |
| TC-Trace-018 | TraceLink-CRUD | **Audit-Metadaten-Immutabilität** | Existierende Audit-Entries | Audit-Entry-Felder modifizieren | Operation rejected | REQ-L2-Trace-010 |
| TC-Trace-019 | TraceLink-CRUD | **Tenant-Isolation** | Tenant A und B mit Links | Query als Tenant A | Nur Tenant-A-Links sichtbar | REQ-L2-Trace-011 |
| TC-Trace-020 | TraceLink-CRUD | **Cross-Tenant-Erstellung blockiert** | Tenant-A-Source, Tenant-B-Target | `create(source_a, target_b, type)` | TenantViolationError | REQ-L2-Trace-011 |
| TC-TE-Cycle-001 | Graph-Query | **Zyklenerkennung — Directed Cycle** | Graph: A→B→C→A | `detect_cycle(A)` | CycleDetectedException | REQ-L2-TE-002 |
| TC-TE-Cycle-002 | Graph-Query | **Zyklenerkennung — Kein False-Positive** | Azyklischer Graph: A→B, C→D | `detect_cycle(D)` | Kein Cycle; liefert false | REQ-L2-TE-002 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-Trace-01 | TraceLink-CRUD → PersistenceLayer | IF-TE-INT-001 | Driver: Batch-Create | TraceLink-CRUD persistiert korrekt via ORM; Tenant-Filter angewendet |
| IT-Trace-02 | Graph-Query → PersistenceLayer | IF-TE-INT-002 | Driver: Graph-Query | Graph-Queries nutzen optimiertes SQL (Recursive CTE) |
| IT-Trace-03 | Coverage-Engine → Graph-Query | IF-TE-INT-003 | Stub: Linked Workspace | Coverage-Berechnung nutzt Graph-Query-Ergebnisse |
| IT-Trace-04 | Snapshot-Collector → CRUD + Query | IF-TE-INT-001, 002 | Stub: Linked Workspace | Snapshot sammelt vollständigen Graph |
| IT-Trace-05 | TraceLink-CRUD → AuditLog | IF-L1-016 | Stub: AuditLog | Jede CRUD-Operation triggert Audit-Log-Entry |

---

### 2.7 WorkflowEngineSystem (ARCH-L1-005) — 8 REQ-L2, 3 Module

**Integrationsstrategie:** Schritt 7 (abhängig von PresetConfigEngine, AuthAndTenancy)
**Risiko:** MITTEL — Preset-abhängiges Verhalten adds Komplexität

#### Komponententests

| TC-ID | Modul | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|-------|----------|--------------|----------|-------------------|-----------|
| TC-WF-001 | COMP-WE-001 WorkflowDefinitionManager | Default-Definition-Generierung | Neuer Workspace, Minimal-Preset | Erster Zugriff auf Workflow-Definitionen | Default-Minimal-Definition erstellt | REQ-L2-Workflow-002 |
| TC-WF-002 | COMP-WE-001 WorkflowDefinitionManager | Custom-Definition-Validierung | Existierender Workspace | Custom-Definition ohne Initial-State | ValidationError: "initial state missing" | REQ-L2-Workflow-002 |
| TC-WF-003 | COMP-WE-001 WorkflowDefinitionManager | **Orphan-Prävention** | Items in existierenden States | State mit Items entfernen | Blockiert: "would orphan N items" | REQ-L2-Workflow-004 |
| TC-WF-004 | COMP-WE-001 WorkflowDefinitionManager | **Preset-Downgrade-Block** | Workspace mit Baselines | Definition inkompatibel mit Preset ändern | Blockiert mit beschreibendem Fehler | REQ-L2-Workflow-007 |
| TC-WF-005 | COMP-WE-002 TransitionEngine | **Gültige Transition** | Gültige Definition, gültiger State | `transition(item, "draft→review", ctx)` | ValidationResult: valid=true | REQ-L2-Workflow-001 |
| TC-WF-006 | COMP-WE-002 TransitionEngine | **Nicht-existente Transition** | Gültige Definition | `transition(item, "draft→approved", ctx)` (nicht definiert) | valid=false, error="transition_not_found" | REQ-L2-Workflow-001 |
| TC-WF-007 | COMP-WE-002 TransitionEngine | **Rollen-Check** | User ohne 'approver'-Rolle | `transition(item, "review→approved", ctx)` | valid=false, error="role_not_authorized" | REQ-L2-Workflow-001 |
| TC-WF-008 | COMP-WE-002 TransitionEngine | **change_reason-Check** | Extended-Preset, requires_change_reason=true | `transition(item, target, ctx)` ohne Reason | valid=false, error="change_reason_required" | REQ-L2-Workflow-001 |
| TC-WF-009 | COMP-WE-002 TransitionEngine | **Fail-Fast-Regelreihenfolge** | Mehrere Regeln verletzt | `transition(...)` mit falscher Rolle UND fehlendem Reason | Erste verletzte Regel gemeldet (Rolle) | REQ-L2-Workflow-008 |
| TC-WF-010 | COMP-WE-002 TransitionEngine | **Performance-Budget** | Geladene Definition | 1000 Validierungen ausführen | Alle < 10ms jeweils | REQ-L2-Workflow-008 |
| TC-WF-011 | COMP-WE-003 StateLifecycleManager | **Initial-State-Initialisierung** | Neues Item | `initialize(item_ids, item_type, ws_id)` | WorkflowState auf initial_state gesetzt | REQ-L2-Workflow-005 |
| TC-WF-012 | COMP-WE-003 StateLifecycleManager | **Atomare State-Mutation** | Validierte Transition | `mutate(item_id, new_state)` | State aktualisiert; History-Entry angehängt; Optimistic Lock | REQ-L2-Workflow-003 |
| TC-WF-013 | COMP-WE-003 StateLifecycleManager | History-Entry-Format | Nach Transition | History abfragen | Entry enthält from_state, to_state, transitioned_by, transitioned_at, change_reason | REQ-L2-Workflow-003 |
| TC-WF-014 | COMP-WE-003 StateLifecycleManager | **Tenant-Isolation** | Zwei Tenants | Query/Mutate als Tenant A | Nur Tenant-A-Daten zugreifbar | REQ-L2-Workflow-006 |
| TC-WF-015 | COMP-WE-003 StateLifecycleManager | **Konkurrente Transitionen** | Gültiger State; zwei parallele Requests | Zwei gleichzeitige Transitionen auf selben State | Genau eine erfolgreich (200); andere 409 Conflict | REQ-L2-Workflow-003, REQ-L2-Workflow-005 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-WF-01 | WE-001 → WE-002 | IF-WE-INT-001 | Driver: Transition-Request | WorkflowDefinition korrekt an TransitionEngine übergeben |
| IT-WF-02 | WE-002 → WE-003 | IF-WE-INT-002 | Stub: Gültige Definition | ValidationResult korrekt propagiert; Mutation nur bei valid=true |
| IT-WF-03 | WE-003 → WE-001 | IF-WE-INT-003 | Stub: Existierende Definitionen | StateQuery liefert korrekten initial_state |

---

### 2.8 BaselineServiceSystem (ARCH-L1-006) — 8 REQ-L2, 4 Komponenten

**Integrationsstrategie:** Schritt 8 (abhängig von TraceabilityEngine, PresetConfigEngine)
**Risiko:** MITTEL — Scope-Resolution-Komplexität und Performance bei Scale

#### Komponententests

| TC-ID | Komponente | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------------|----------|--------------|----------|-------------------|-----------|
| TC-BS-001 | COMP-BL-001 ScopeResolver | Document-Scope-Resolution | Artifact mit Descendants | `resolve_scope("document", artifact_id, ws_id)` | Alle Descendant-Items + Related-Items | REQ-L2-Baseline-001 |
| TC-BS-002 | COMP-BL-001 ScopeResolver | Project-Scope-Resolution | Workspace mit Items | `resolve_scope("project", null, ws_id)` | Alle Workspace-Items | REQ-L2-Baseline-001 |
| TC-BS-003 | COMP-BL-001 ScopeResolver | Global-Scope-Resolution | Tenant mit mehreren Workspaces | `resolve_scope("global", null, ws_id)` | Alle Tenant-Items | REQ-L2-Baseline-001 |
| TC-BS-004 | COMP-BL-002 SnapshotBuilder | **Atomare Baseline-Erstellung** | Gültiger Scope, Preset erlaubt | `build(scope, ws_id, name, desc, ctx)` | Baseline atomar persistiert; Metadaten korrekt | REQ-L2-Baseline-001, 005, 007 |
| TC-BS-005 | COMP-BL-002 SnapshotBuilder | **Immutability-Enforcement** | Existierende Baseline | Baseline updaten | Rejected: "baselines are immutable" | REQ-L2-Baseline-002 |
| TC-BS-006 | COMP-BL-002 SnapshotBuilder | **Duplicate-Name-Rejektion** | Baseline "v1.0" existiert | Baseline "v1.0" in gleichem Workspace | Rejected: "duplicate name" | REQ-L2-Baseline-005 |
| TC-BS-007 | COMP-BL-002 SnapshotBuilder | Retrieval und Listing | Mehrere Baselines | `get(id)` und `list(ws_id, scope)` | Korrekte Baseline(s) zurückgegeben | REQ-L2-Baseline-006 |
| TC-BS-008 | COMP-BL-003 BaselineDiffEngine | **Diff-Berechnung** | Zwei Baselines mit Unterschieden | `diff(baseline_a, baseline_b)` | added/changed/removed Items mit Versions-Deltas | REQ-L2-Baseline-003 |
| TC-BS-009 | COMP-BL-003 BaselineDiffEngine | Inkompatible-Scope-Rejektion | Baselines unterschiedlicher Scopes | `diff(a, b)` mit mismatched scopes | Fehler: "incompatible scopes" | REQ-L2-Baseline-003 |
| TC-BS-010 | COMP-BL-004 PresetGate | Scope erlaubt in Standard | Standard-Preset | `require_scope_allowed(ws_id, "document")` | Kein Fehler (erlaubt) | REQ-L2-Baseline-004 |
| TC-BS-011 | COMP-BL-004 PresetGate | **Scope blockiert in Minimal** | Minimal-Preset | `require_scope_allowed(ws_id, "document")` | ScopeNotAllowedError | REQ-L2-Baseline-004 |
| TC-BS-012 | COMP-BL-004 PresetGate | **Global-Scope nur in Extended** | Standard-Preset | `require_scope_allowed(ws_id, "global")` | ScopeNotAllowedError | REQ-L2-Baseline-004 |
| TC-BS-013 | COMP-BL-002 SnapshotBuilder | **Baseline-Performance unter Last** | 10.000 Items im Scope | `build(scope, ws_id, name, desc, ctx)` | Baseline atomar innerhalb 5s; Memory < 512MB | REQ-L2-Baseline-008 |
| TC-BS-014 | COMP-BL-003 BaselineDiffEngine | **Diff-Performance** | Zwei Baselines mit je 10.000 Items | `diff(baseline_a, baseline_b)` | Diff < 3s; added/changed/removed korrekt | REQ-L2-Baseline-008 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-BS-01 | BL-002 → BL-004 | IF-BL-INT-001 | Stub: PresetConfigEngine | PresetGate validiert Scope vor Snapshot korrekt |
| IT-BS-02 | BL-002 → BL-001 | IF-BL-INT-002 | Stub: TraceabilityEngine, PersistenceLayer | ScopeResolver liefert vollständige Item-Liste |
| IT-BS-03 | BL-003 → BL-002 | IF-BL-INT-003 | Stub: PersistenceLayer | BaselineDiffEngine lädt Snapshots korrekt |

---

### 2.9 ReactFrontendSystem (ARCH-L1-001) — 12 REQ-L2, 8 Sub-Komponenten

**Integrationsstrategie:** Schritt 12 (abhängig von RestApiAdapter)
**Risiko:** MITTEL — UI-Testing erfordert Browser-Automatisierung

#### Komponententests

| TC-ID | Komponente | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------------|----------|--------------|----------|-------------------|-----------|
| TC-React-001 | COMP-RF-001 NavigationShell | Initiales Rendering | Gebaute App | Navigiere zu / | Dashboard innerhalb 2s gerendert | REQ-L2-React-009 |
| TC-React-002 | COMP-RF-001 NavigationShell | **401-Redirect** | Keine gültige Session | Geschützte Route aufrufen | Redirect zu /login | REQ-L2-React-010 |
| TC-React-003 | COMP-RF-002 DashboardView | Workspace-Übersicht | Workspace mit Requirements | Login und Dashboard ansehen | Requirement-Counter, offene Items, Terminologie-Profil | REQ-L2-React-002 |
| TC-React-004 | COMP-RF-003 RequirementEditor | Requirement-Editing | Existierendes Requirement | Titel bearbeiten, speichern | Aktualisierter Titel persistiert; Optimistic Update | REQ-L2-React-003 |
| TC-React-005 | COMP-RF-004 ArchitectureEditor | Architecture-Element-Editing | Existierendes Element | Element-Properties bearbeiten | Änderungen gespeichert; Version inkrementiert | REQ-L2-React-004 |
| TC-React-006 | COMP-RF-005 ArtifactTreeView | **Artifact-Tree-Rendering** | Hierarchische Artefakte | Baum navigieren | Baum expandiert; Selektion propagiert zum Editor | REQ-L2-React-005 |
| TC-React-007 | COMP-RF-006 WorkspaceConfig | **Preset-Wechsel** | Standard-Preset-Workspace | Wechsel zu Extended | Neue Features in UI sichtbar | REQ-L2-React-006 |
| TC-React-008 | COMP-RF-007 I18nService | **Sprachwechsel** | DE-Locale aktiv | Wechsel zu EN | Alle Labels auf Englisch | REQ-L2-React-007 |
| TC-React-009 | COMP-RF-007 I18nService | **Terminologie-Profil-Labels** | Dev-Modus-Workspace | Requirement-Liste ansehen | "Story"-Label statt "Requirement" | REQ-L2-React-008 |
| TC-React-010 | COMP-RF-008 ApiService | **Error-Handling** | Backend gibt 500 | API-Call auslösen | User-freundliche Fehlermeldung | REQ-L2-React-011 |
| TC-React-011 | COMP-RF-008 ApiService | **Optimistic Update** | Existierendes Requirement | Requirement updaten | UI zeigt sofort neuen Wert; reconciliert bei Server-Response | REQ-L2-React-012 |
| TC-React-012 | COMP-RF-008 ApiService | **Cache-Invalidation** | Staler Cache | Server-seitige Änderung via MCP | Cache invalidiert; frische Daten beim nächsten Read | REQ-L2-React-012 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-React-01 | RF-001 → RF-002..005 | IF-RF-INT-001 | None | Routing-Events aktivieren/deaktivieren Module korrekt |
| IT-React-02 | RF-005 → RF-003 | IF-RF-INT-003 | None | Artefakt-Selektion propagiert von Navigation zum Editor |
| IT-React-03 | RF-008 → RF-002..005 | — | Stub: REST API | Daten-Responses korrekt an Module verteilt |
| IT-React-04 | RF-007 → RF-001..005 | IF-RF-INT-002 | None | Translation-Keys aufgelöst; Locale-Change propagiert |
| IT-React-05 | RF-003 → RF-008 | — | Stub: REST API | Optimistic Update gesendet; Server-Response reconciliert |

---

### 2.10 RestApiAdapterSystem (ARCH-L1-002) — 12 REQ-L2, 5 Module

**Integrationsstrategie:** Schritt 10 (abhängig von ApplicationService, AuthAndTenancy, PresetConfigEngine)
**Risiko:** MITTEL — gut definiertes Adapter-Pattern

#### Komponententests

| TC-ID | Modul | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|-------|----------|--------------|----------|-------------------|-----------|
| TC-Rest-001 | COMP-RA-001 HttpEndpointController | **Endpoint-Routing** | Laufender Server | `GET /api/v1/requirements/` | 200; JSON-Liste | REQ-L2-Rest-001 |
| TC-Rest-002 | COMP-RA-001 HttpEndpointController | **OpenAPI-Schema-Endpunkt** | Laufender Server | `GET /api/v1/schema/` | OpenAPI 3.0 Spec zurückgegeben | REQ-L2-Rest-002 |
| TC-Rest-003 | COMP-RA-001 HttpEndpointController | **Swagger-UI** | Laufender Server | `GET /api/v1/schema/swagger-ui/` | HTML Swagger-UI gerendert | REQ-L2-Rest-002 |
| TC-Rest-004 | COMP-RA-002 DataSerializer | **Request-Validierung** | Ungültiger JSON-Body | `POST /api/v1/requirements/` mit fehlendem Titel | 400; Validierungsfehler mit Feld-Details | REQ-L2-Rest-003 |
| TC-Rest-005 | COMP-RA-002 DataSerializer | **Response-Serialisierung** | Gültige Daten | `GET /api/v1/requirements/{id}` | JSON-Response entspricht Serializer-Schema | REQ-L2-Rest-003 |
| TC-Rest-006 | COMP-RA-003 AuthEnforcer | **Auth-Enforcement** | Kein Token | Geschützten Endpunkt aufrufen | 401 | REQ-L2-Rest-004 |
| TC-Rest-007 | COMP-RA-003 AuthEnforcer | **Auth-Context-Propagation** | Gültiges Token | Endpunkt aufrufen | AuthContext an ApplicationService übergeben | REQ-L2-Rest-004 |
| TC-Rest-008 | COMP-RA-004 PresetGuard | **Field-Filtering für Minimal** | Minimal-Preset | `POST /requirements/` mit SE-only Feldern | SE-only Felder rejected/ignoriert | REQ-L2-Rest-005 |
| TC-Rest-009 | COMP-RA-004 PresetGuard | **Feature-Gating** | Minimal-Preset | `POST /baselines/` | 403: feature not available in preset | REQ-L2-Rest-005 |
| TC-Rest-010 | COMP-RA-005 OpenApiGenerator | **Auto-generierte Schema** | Alle Endpunkte registriert | OpenAPI-Spec inspizieren | Alle Endpunkte dokumentiert; korrekte Schemas | REQ-L2-Rest-006 |
| TC-Rest-011 | COMP-RA-001 HttpEndpointController | **Error-Response-Format** | Verschiedene Fehlerbedingungen | 400, 401, 403, 404, 500 triggern | Standardisiertes JSON-Error-Format | REQ-L2-Rest-007 |
| TC-Rest-012 | COMP-RA-001 HttpEndpointController | **Pagination** | 100+ Items | `GET /requirements/?page=2&page_size=10` | Paginierte Response mit Meta | REQ-L2-Rest-008 |

#### Integrationstests

| IT-ID | Komponenten | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------------|---------------|---------------|----------------|
| IT-Rest-01 | RA-001 → RA-003 | IF-RA-INT-001 | Driver: HTTP-Request | AuthEnforcer validiert bevor Controller verarbeitet |
| IT-Rest-02 | RA-001 → RA-004 | IF-RA-INT-002 | Stub: PresetConfigEngine | PresetGuard filtert Felder vor Serialisierung |
| IT-Rest-03 | RA-001 → RA-002 | IF-RA-INT-003 | None | DataSerializer validiert Input und serialisiert Output |
| IT-Rest-04 | RA-004 → RA-002 | IF-RA-INT-004 | Stub: Preset-Regeln | PresetGuard übergibt Feld-Constraints an Serializer |
| IT-Rest-05 | RA-005 → RA-001 | IF-RA-INT-005 | None | OpenApiGenerator registriert alle Routes korrekt |
| IT-Rest-06 | RA-005 → RA-002 | IF-RA-INT-006 | None | OpenApiGenerator stellt Serializer-Schemas für OpenAPI bereit |

---

## 3. Testmodelle — Continue-Systeme (L3-Ebene)

### 3.1 ApplicationServiceSystem (ARCH-L1-004) — 25 REQ-L2, 12 L2-Komponenten, 13 L3-Units

**Integrationsstrategie:** Schritt 9 (zentraler Orchestrator) + L3-Unit-Tests parallel
**Risiko:** KRITISCH — 10 ausgehende L1-Schnittstellen; Failure blockiert Steps 10 und 11

#### 3.1.1 L3-Unit-Tests

| TC-ID | Unit | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------|----------|--------------|----------|-------------------|-----------|
| TC-AS-001 | UNIT-AS-01 CycleDetector | **Cycle-Detection** | Artifact-Tree: A→B→C | `detect_cycle(C, A)` (A als Parent von C vorschlagen) | CycleDetectedException | UNIT-REQ-001 |
| TC-AS-002 | UNIT-AS-01 CycleDetector | Kein False-Positive | Artifact-Tree: A→B, C→D | `detect_cycle(D, B)` | Kein Cycle; liefert false | UNIT-REQ-001 |

> **Hinweis:** Zyklenerkennung wird primär in der TraceabilityEngine (COMP-TE-001 TraceLinkManager) implementiert und dort getestet (TC-TE-Cycle-001/002). UNIT-AS-01 konsumiert das Ergebnis.

| TC-AS-003 | UNIT-AS-02 ArtifactService | **Artifact-CRUD** | Gültiger Workspace | Artifact erstellen, lesen, updaten, löschen | Alle Operationen erfolgreich; Audit-Entries | UNIT-REQ-002 |
| TC-AS-004 | UNIT-AS-02 ArtifactService | **Tree-Query** | Hierarchische Artefakte | `get_tree()` | Korrekte Baumstruktur mit Nesting | UNIT-REQ-003 |
| TC-AS-005 | UNIT-AS-03 ArtifactTreeNode | Node-Struktur | Artifact mit Children | Baum bauen | Korrekte Parent-Child-Beziehungen | UNIT-REQ-004 |
| TC-AS-006 | UNIT-AS-04 RequirementService | **Requirement-CRUD + Workflow** | Gültiger Workspace | Requirement erstellen | Requirement erstellt; Workflow initialisiert | UNIT-REQ-005 |
| TC-AS-007 | UNIT-AS-04 RequirementService | **Decomposition-Orchestrierung** | Existierendes Requirement | `decompose(req_id)` | Child-Requirements + Trace-Links erstellt | UNIT-REQ-006 |
| TC-AS-008 | UNIT-AS-04 RequirementService | **LLM-Validation-Orchestrierung** | LLM konfiguriert | `validate(req_id)` | LLM-Validation-Ergebnis zurückgegeben | UNIT-REQ-007 |
| TC-AS-009 | UNIT-AS-05 ArchitectureService | **ArchitectureElement-CRUD** | Gültiger Workspace | Element erstellen, lesen, updaten, löschen | Alle Operationen erfolgreich; Version inkrementiert | UNIT-REQ-008 |
| TC-AS-010 | UNIT-AS-05 ArchitectureService | **Optimistic Locking** | Parallele Updates | Zwei simultane Updates | Eines erfolgreich; anderes ConflictError | UNIT-REQ-009 |
| TC-AS-011 | UNIT-AS-05 ArchitectureService | **Cascade-Delete** | Element mit Trace-Links | Element löschen | Element + Trace-Links gelöscht | UNIT-REQ-010 |
| TC-AS-012 | UNIT-AS-06 TestService | **TestCase-CRUD** | Gültiger Workspace | TestCase erstellen, lesen, updaten, löschen | Alle Operationen erfolgreich | UNIT-REQ-011 |
| TC-AS-013 | UNIT-AS-06 TestService | **Coverage-Berechnung** | Tests mit Requirements verknüpft | `calculate_coverage(ws_id)` | Korrekter Prozentsatz | UNIT-REQ-012 |
| TC-AS-014 | UNIT-AS-06 TestService | Execution-Status-Management | Existierender TestCase | Execution-Status updaten | Status aktualisiert; Audit geloggt | UNIT-REQ-013 |
| TC-AS-015 | UNIT-AS-07 ExportService | **JSON-Export** | Workspace mit Items | `export(format="json")` | Valides JSON mit allen Items + Terminologie-Metadaten | UNIT-REQ-014 |
| TC-AS-016 | UNIT-AS-07 ExportService | **CSV-Export** | Workspace mit Items | `export(format="csv")` | Valides CSV mit Headers + Terminologie-Metadaten | UNIT-REQ-015 |
| TC-AS-017 | UNIT-AS-07 ExportService | **Export-Performance** | 1.000 Items | `export(format="json")` | Completion < 5 Sekunden | UNIT-REQ-016 |
| TC-AS-018 | UNIT-AS-08 SearchService | **Full-Text-Search** | Indizierte Items | `search("query")` | Relevanz-sortierte Ergebnisse < 500ms | UNIT-REQ-017 |
| TC-AS-019 | UNIT-AS-08 SearchService | **Type-Filter** | Gemischte Entity-Typen | `search("query", types=["requirement"])` | Nur Requirements in Ergebnissen | UNIT-REQ-019 |
| TC-AS-020 | UNIT-AS-08 SearchService | **Workspace-Filter** | Mehrere Workspaces | `search("query", workspace_id=X)` | Nur Workspace-X-Ergebnisse | UNIT-REQ-020 |
| TC-AS-021 | UNIT-AS-09 SearchResult | Ergebnis-Struktur | Search ausgeführt | Ergebnisse inspizieren | Jedes Ergebnis hat id, type, title, snippet, score | UNIT-REQ-018 |
| TC-AS-022 | UNIT-AS-10 TraceLinkService | **Link-Erstellung mit Validierung** | Gültige Source + Target | `create_link(source, target, type)` | Link erstellt; validiert | UNIT-REQ-021 |
| TC-AS-023 | UNIT-AS-10 TraceLinkService | **Link-Query** | Existierende Links | `query(entity_id, direction)` | Korrekte Upstream/Downstream-Links | UNIT-REQ-022 |
| TC-AS-024 | UNIT-AS-11 BaselineFacade | **Baseline-Lifecycle-Orchestrierung** | Preset erlaubt Scope | `create_baseline(...)` | PresetPolicyService konsultiert; BaselineService delegiert; AuditLog geschrieben | UNIT-REQ-023 |
| TC-AS-025 | UNIT-AS-12 WorkflowFacade | **Transition-Orchestrierung** | Gültige Transition | `transition(item_id, target_state, ctx)` | WorkflowEngine delegiert; AuditLog geschrieben | UNIT-REQ-024 |
| TC-AS-026 | UNIT-AS-13 PresetPolicyService | **Scope-Permission-Check** | Standard-Preset | `is_scope_allowed(ws_id, "document")` | true | UNIT-REQ-025 |
| TC-AS-027 | UNIT-AS-13 PresetPolicyService | **change_reason-Requirement-Check** | Extended-Preset | `is_change_reason_required(ws_id)` | true | UNIT-REQ-025 |
| TC-AS-028 | UNIT-AS-13 PresetPolicyService | **Downgrade-Validierung** | Workspace mit Baselines | `validate_downgrade(ws_id, "minimal")` | INCOMPATIBLE | UNIT-REQ-025 |
| TC-AS-029 | UNIT-AS-07 ExportService / ImportService | **CSV-Bulk-Import** | Valides CSV mit 1.000 Requirement-Zeilen | `import_csv(file, ws_id, ctx)` | Alle 1.000 erstellt; Audit-Entries; atomar; Duplicate-Detection | REQ-L2-AppSvc-014 |
| TC-AS-030 | UNIT-AS-07 ExportService / ImportService | **CSV-Import mit Invalid Rows** | CSV mit 100 Zeilen, 5 invalid | `import_csv(file, ws_id, ctx)` | Valide Zeilen importiert; invalide mit Zeilennummern berichtet | REQ-L2-AppSvc-014 |

#### 3.1.2 L3-Integrationstests (Unit ↔ Unit)

| IT-ID | Units | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------|---------------|---------------|----------------|
| IT-AS-01 | UNIT-AS-02 → UNIT-AS-01 | IF-L3-AS-01 | Driver: Artifact-Create mit Cycle | CycleDetector erkennt Zyklen korrekt |
| IT-AS-02 | UNIT-AS-02 → UNIT-AS-03 | IF-L3-AS-02 | None | ArtifactTreeNode repräsentiert Baum korrekt |
| IT-AS-03 | UNIT-AS-08 → UNIT-AS-09 | IF-L3-AS-03 | Stub: DB | SearchService liefert Liste von SearchResult |
| IT-AS-04 | UNIT-AS-11 → UNIT-AS-10 | IF-L3-AS-04 | Stub: BaselineService | BaselineFacade triggert Trace-Link-Cleanup |
| IT-AS-05 | UNIT-AS-12 → UNIT-AS-10 | IF-L3-AS-05 | Stub: WorkflowEngine | WorkflowFacade triggert Trace-Link-Cleanup |

#### 3.1.3 L2-System-Integrationstests

| IT-ID | Komponenten integriert | Schnittstellen | Stubs/Drivers | Pass-Kriterium |
|-------|----------------------|----------------|---------------|----------------|
| IT-AppSvc-L2-01 | AppService + WorkflowEngine | IF-L1-010 | Stub: PresetConfigEngine | Workflow-Transitions korrekt orchestriert |
| IT-AppSvc-L2-02 | AppService + BaselineService | IF-L1-011 | Stub: PresetConfigEngine, TraceabilityEngine | Baseline-Lifecycle korrekt orchestriert |
| IT-AppSvc-L2-03 | AppService + TraceabilityEngine | IF-L1-012 | None | TraceLink-CRUD und Queries funktionieren E2E |
| IT-AppSvc-L2-04 | AppService + PresetConfigEngine | IF-L1-013 | None | Preset-Policies korrekt durchgesetzt |
| IT-AppSvc-L2-05 | AppService + LlmAdapter | IF-L1-014 | Stub: LLM-Provider | LLM-Capabilities korrekt orchestriert |
| IT-AppSvc-L2-06 | AppService + AuditLog | IF-L1-016 | None | Alle Schreiboperationen produzieren Audit-Entries |
| IT-AppSvc-L2-07 | AppService + AuthAndTenancy | IF-L1-015, IF-L1-027 | None | RBAC korrekt pro Operation durchgesetzt |
| IT-AppSvc-L2-08 | AppService + PersistenceLayer | IF-L1-022 (via alle) | None | Alle DB-Operationen tenant-isoliert |

---

### 3.2 McpServerSystem (ARCH-L1-003) — 12 REQ-L2, 6 L2-Komponenten, 22 L3-Units

**Integrationsstrategie:** Schritt 11 + L3-Unit-Tests parallel (Sandwich)
**Risiko:** HOCH — 22 L3-Units, duale Transport-Protokolle, komplexes RBAC

#### 3.2.1 L3-Unit-Tests

| TC-ID | Unit | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion | Traces To |
|-------|------|----------|--------------|----------|-------------------|-----------|
| TC-MCP-001 | UNIT-MCP-01 McpDispatcher | **JSON-RPC-Dispatch** | Gültiger MCP-Frame | `requirement.get` dispatchen | Korrekter Tool-Handler aufgerufen | UNIT-REQ-026 |
| TC-MCP-002 | UNIT-MCP-01 McpDispatcher | **Unknown-Tool-Rejektion** | Gültiger MCP-Frame | `unknown.tool` dispatchen | McpError: "tool_not_found" | UNIT-REQ-026 |
| TC-MCP-003 | UNIT-MCP-02 ToolRegistry | Tool-Registrierung | Alle 20 Tools registriert | `get_handler("requirement.get")` | Korrekter Handler-Callable | UNIT-REQ-027 |
| TC-MCP-004 | UNIT-MCP-02 ToolRegistry | **Preset-basiertes Filtering** | Minimal-Preset | `list_tools(preset="minimal")` | Nur erlaubte Tools gelistet | UNIT-REQ-027 |
| TC-MCP-005 | UNIT-MCP-03 RequirementGetTool | Single-Requirement-Retrieval | Existierendes Requirement | `execute({id: "req-1"})` | Requirement-JSON | UNIT-REQ-028 |
| TC-MCP-006 | UNIT-MCP-04 RequirementQueryTool | Requirement-Query | Mehrere Requirements | `execute({filter: {...}})` | Gefilterte Liste | UNIT-REQ-029 |
| TC-MCP-007 | UNIT-MCP-05 RequirementCreateTool | **Requirement-Creation** | Gültige Params | `execute({title: "New", ...})` | Requirement erstellt; Audit-Entry | UNIT-REQ-030 |
| TC-MCP-008 | UNIT-MCP-06 RequirementUpdateTool | **Requirement-Update** | Existierendes Requirement | `execute({id: "req-1", title: "Updated"})` | Requirement aktualisiert; Audit-Entry | UNIT-REQ-031 |
| TC-MCP-009 | UNIT-MCP-07 RequirementDecomposeTool | **Decomposition mit LLM** | LLM konfiguriert | `execute({id: "req-1"})` | Decomposition-Ergebnis | UNIT-REQ-032 |
| TC-MCP-010 | UNIT-MCP-07 RequirementDecomposeTool | **Decomposition ohne LLM** | Kein LLM konfiguriert | `execute({id: "req-1"})` | Fehler: "LLM not configured" | UNIT-REQ-032 |
| TC-MCP-011 | UNIT-MCP-08 RequirementValidateTool | Validation mit LLM | LLM konfiguriert | `execute({id: "req-1"})` | Validation-Ergebnis | UNIT-REQ-033 |
| TC-MCP-012 | UNIT-MCP-09 ArchitectureGetTool | Element-Retrieval | Existierendes Element | `execute({id: "ae-1"})` | Element-JSON | UNIT-REQ-034 |
| TC-MCP-013 | UNIT-MCP-10 ArchitectureQueryTool | Element-Query | Mehrere Elemente | `execute({filter: {...}})` | Gefilterte Liste | UNIT-REQ-035 |
| TC-MCP-014 | UNIT-MCP-11 ArchitectureCreateTool | **Element-Creation** | Gültige Params | `execute({title: "New AE", ...})` | Element erstellt; Audit-Entry | UNIT-REQ-036 |
| TC-MCP-015 | UNIT-MCP-12 ArchitectureUpdateTool | **Element-Update** | Existierendes Element | `execute({id: "ae-1", ...})` | Element aktualisiert; Version inkrementiert | UNIT-REQ-037 |
| TC-MCP-016 | UNIT-MCP-13 ArchitectureLinkTool | **Link-Creation** | Gültige Source + Target | `execute({source, target, type})` | TraceLink erstellt; Audit-Entry | UNIT-REQ-038 |
| TC-MCP-017 | UNIT-MCP-14 TestGetTool | Test-Retrieval | Existierender Test | `execute({id: "test-1"})` | Test-JSON | UNIT-REQ-039 |
| TC-MCP-018 | UNIT-MCP-15 TestQueryTool | Test-Query | Mehrere Tests | `execute({filter: {...}})` | Gefilterte Liste | UNIT-REQ-040 |
| TC-MCP-019 | UNIT-MCP-16 TestCreateTool | **Test-Creation** | Gültige Params | `execute({title: "New Test", ...})` | Test erstellt; Audit-Entry | UNIT-REQ-041 |
| TC-MCP-020 | UNIT-MCP-17 TestUpdateTool | **Test-Update** | Existierender Test | `execute({id: "test-1", status: "passed"})` | Test aktualisiert; Audit-Entry | UNIT-REQ-042 |
| TC-MCP-021 | UNIT-MCP-18 TestLinkTool | **Test-Requirement-Link** | Gültiger Test + Requirement | `execute({test_id, req_id})` | TraceLink (verifies) erstellt | UNIT-REQ-043 |
| TC-MCP-022 | UNIT-MCP-19 TraceabilityQueryTool | **Trace-Graph-Query** | Verknüpfte Artefakte | `execute({artifact_id, direction})` | Trace-Graph | UNIT-REQ-044 |
| TC-MCP-023 | UNIT-MCP-20 ArtifactSearchTool | **Artifact-Search** | Indizierte Artefakte | `execute({query: "search term"})` | Suchergebnisse | UNIT-REQ-045 |
| TC-MCP-024 | UNIT-MCP-21 ArtifactGetTreeTool | **Tree-Retrieval** | Hierarchische Artefakte | `execute({root_id})` | Baumstruktur | UNIT-REQ-046 |
| TC-MCP-025 | UNIT-MCP-22 WorkspaceGetContextTool | **Context-Aggregation** | Workspace mit Daten | `execute({workspace_id})` | Vollständiger Context: Requirements, Tests, Coverage, Preset, Terminologie, Workflows | UNIT-REQ-047 |
| TC-MCP-026 | UNIT-MCP-01 McpTransport | **stdio-Transport** | stdio konfiguriert | JSON-RPC-Frame via stdin senden | Frame korrekt geparst; Response auf stdout | REQ-L2-Mcp-005 |
| TC-MCP-027 | UNIT-MCP-01 McpTransport | **HTTP+SSE-Transport** | HTTP+SSE konfiguriert | HTTP POST mit JSON-RPC-Body | 200 Response; SSE-Stream für Notifications | REQ-L2-Mcp-005 |
| TC-MCP-028 | UNIT-MCP-01 McpTransport | **API-Key-Authentifizierung** | API-Key konfiguriert | Request mit gültigem X-API-Key-Header | Request authentifiziert; IdentityClaims befüllt | REQ-L2-Mcp-006 |
| TC-MCP-029 | UNIT-MCP-01 McpTransport | **API-Key-Rejektion** | API-Key konfiguriert | Request mit ungültigem/fehlendem API-Key | 401 JSON-RPC-Error; keine Tool-Ausführung | REQ-L2-Mcp-006 |
| TC-MCP-030 | UNIT-MCP-02 ToolRegistry | **RBAC für MCP-Tool-Zugriff** | User mit 'viewer'-Rolle | `requirement.create` aufrufen | McpError: "permission_denied" | REQ-L2-Mcp-007 |
| TC-MCP-031 | UNIT-MCP-02 ToolRegistry | **RBAC erlaubt autorisierten Zugriff** | User mit 'editor'-Rolle | `requirement.create` mit gültigen Params | Tool ausgeführt; Requirement erstellt | REQ-L2-Mcp-007 |
| TC-MCP-032 | UNIT-MCP-03..22 | **Direkter ApplicationService-Call** | StubApplicationService | Tool-Handler direkt aufrufen (Transport bypass) | ApplicationService-Methode mit korrekten Params aufgerufen | REQ-L2-Mcp-009 |
| TC-MCP-033 | UNIT-MCP-03..22 | **ApplicationService-Error-Propagation** | StubApplicationService raised Error | Tool-Handler aufrufen; Stub raised DomainError | McpError mit korrektem Error-Code | REQ-L2-Mcp-009 |
| TC-MCP-034 | UNIT-MCP-01 McpTransport | **MCP-Performance unter Last** | 50 parallele MCP-Clients | 50 parallele JSON-RPC-Requests | Alle Responses < 2s (p95); kein Request-Verlust | REQ-L2-Mcp-010 |
| TC-MCP-035 | UNIT-MCP-01 McpTransport | **MCP-Throughput** | Sustained Load | 100 Requests/Sekunde für 60s | Null Fehler; p99 < 3s; kein Memory-Leak | REQ-L2-Mcp-010 |

#### 3.2.2 L3-Integrationstests (Unit ↔ Unit)

| IT-ID | Units | Schnittstelle | Stubs/Drivers | Pass-Kriterium |
|-------|-------|---------------|---------------|----------------|
| IT-MCP-01 | UNIT-MCP-01 → UNIT-MCP-02 | IF-MC-INT-001 | Driver: MCP-Frame | McpDispatcher löst Tool via ToolRegistry korrekt auf |
| IT-MCP-02 | UNIT-MCP-02 → UNIT-MCP-03..22 | IF-MC-INT-002..005 | Stub: ApplicationService | ToolRegistry dispatched an korrekten Tool-Handler |

#### 3.2.3 L2-System-Integrationstests

| IT-ID | Komponenten integriert | Schnittstellen | Stubs/Drivers | Pass-Kriterium |
|-------|----------------------|----------------|---------------|----------------|
| IT-Mcp-L2-01 | McpTransport + RequirementTools | IF-MC-INT-002 | Driver: MCP-Client | Transport dispatched korrekt an Requirement-Tools |
| IT-Mcp-L2-02 | McpTransport + ArchitectureTools | IF-MC-INT-003 | Driver: MCP-Client | Transport dispatched korrekt an Architecture-Tools |
| IT-Mcp-L2-03 | McpTransport + TestTools | IF-MC-INT-004 | Driver: MCP-Client | Transport dispatched korrekt an Test-Tools |
| IT-Mcp-L2-04 | McpTransport + CrossCuttingTools | IF-MC-INT-005 | Driver: MCP-Client | Transport dispatched korrekt an Cross-Cutting-Tools |
| IT-Mcp-L2-05 | Alle Tool-Subsysteme → Transport | IF-MC-INT-006 | Stub: ApplicationService | ToolResults korrekt durch Transport zurückgegeben |
| IT-Mcp-L2-06 | McpServer + ApplicationService | IF-L1-006 | None | Alle 20 Tools rufen ApplicationService-Methoden korrekt auf |
| IT-Mcp-L2-07 | McpServer + AuthAndTenancy | IF-L1-007 | None | API-Key-Validierung für alle Tool-Calls |
| IT-Mcp-L2-08 | McpServer + PresetConfigEngine | IF-L1-008 | None | Tool-Visibility korrekt nach Preset gefiltert |
| IT-Mcp-L2-09 | McpServer + AuditLog | IF-L1-021 | None | Alle Schreiboperationen produzieren MCP-spezifische Audit-Entries |

---

## 4. Test-Interface-Spezifikationen

### 4.1 Testmethoden pro Interface-Klasse

| Interface-Klasse | Testmethode | Beobachtbare Effekte | Fault-Injection-Punkte |
|-----------------|-------------|---------------------|----------------------|
| **IF-EXT-*** (Extern) | Browser-Automatisierung (Playwright), HTTP-Client (curl/requests), MCP-Client | UI-Rendering, HTTP-Responses, MCP-JSON-RPC-Responses | Network-Timeout, Fehleingabe, fehlende Auth |
| **IF-L1-*** (Inter-System) | Django-Test-Client, In-Process-Python-Calls | Rückgabewerte, DB-Zustandsänderungen, Audit-Log-Entries | Ungültiger Auth-Context, fehlender Tenant, falsches Preset |
| **IF-L2-*** (Intra-System) | Direkte Python-Methodenaufrufe mit pytest-Fixtures | Rückgabewerte, interne Zustandsänderungen | Ungültige Parameter, Null-Referenzen, paralleler Zugriff |
| **IF-L3-*** (Unit ↔ Unit) | Unit-Test-Harness mit Mocks/Stubs | Rückgabewerte, Mock-Call-Verifikation | Exception-Propagation, Timeout-Simulation |

### 4.2 Kritische Interface-Test-Spezifikationen

| Interface-ID | Quelle | Ziel | Testmethode | Beobachtbare Effekte | Fault-Injection |
|-------------|--------|------|-------------|---------------------|----------------|
| IF-L1-006 | McpServer | ApplicationService | In-Process Python | Use-Case-Methode Rückgabewert | Ungültige Params, fehlender Auth-Context |
| IF-L1-010 | ApplicationService | WorkflowEngine | In-Process Python | ValidationResult, State-Mutation | Ungültige Transition, fehlende Rollen |
| IF-L1-011 | ApplicationService | BaselineService | In-Process Python | Baseline-Entity erstellt | Scope nicht erlaubt, Duplicate-Name |
| IF-L1-012 | ApplicationService | TraceabilityEngine | In-Process Python | TraceLink-CRUD-Ergebnisse | Cross-Workspace-Links, ungültige Typen |
| IF-L1-013 | ApplicationService | PresetConfigEngine | In-Process Python | PresetConfig, CompatibilityResult | Ungültige workspace_id |
| IF-L1-014 | ApplicationService | LlmAdapter | In-Process Python | LlmResult oder Fehler | Provider-Timeout, keine Config |
| IF-L1-016 | ApplicationService | AuditLog | In-Process Python | AuditLogEntry persistiert | Fehlender Akteur, ungültiger entity_type |
| IF-L1-022 | * (alle) | PersistenceLayer | Django ORM | Entity persistiert mit tenant_id | Fehlende tenant_id, FK-Verletzung |

---

## 5. Testdaten- & Fixture-Definitionen

### 5.1 Standard-Test-Fixtures

| Fixture | Scope | Inhalt | Teardown |
|---------|-------|--------|----------|
| `empty_db` | Unit | Leere PostgreSQL-Test-Datenbank | Datenbank droppen |
| `single_tenant` | Unit/Integration | Ein Tenant, ein User, ein Workspace (Standard-Preset) | Datenbank droppen |
| `multi_tenant` | Integration | Zwei Tenants, jeweils mit Workspace und Items | Datenbank droppen |
| `hierarchy_500` | Integration | 500 Artefakte in 5-level Hierarchie | Datenbank droppen |
| `linked_workspace` | Integration | 100 Requirements, 50 Arch-Elemente, 30 Tests, 200 Trace-Links | Datenbank droppen |
| `baseline_pair` | Integration | Zwei Baselines gleichen Scopes mit bekannten Unterschieden | Datenbank droppen |
| `full_preset_matrix` | Integration | Drei Workspaces: Minimal, Standard, Extended | Datenbank droppen |
| `performance_scale` | Performance | 10.000 Items, 50.000 Trace-Links, 100.000 Audit-Entries | Datenbank droppen |

### 5.2 Mock/Stub-Definitionen

| Mock/Stub | Ersetzt | Verhalten |
|-----------|---------|-----------|
| `MockLlmProvider` | LLM-Provider (Anthropic/OpenAI/Ollama) | Liefert vordefiniertes LlmResult; konfigurierbarer Delay/Fehler |
| `MockWebhookReceiver` | Externe Webhook-URL | Zeichnet empfangene POST-Payloads auf; liefert 200/500 konfigurierbar |
| `StubPersistenceLayer` | PostgreSQL-Datenbank | In-Memory-Datenspeicher mit Django-ORM-Subset |
| `StubAuthContext` | AuthAndTenancy-System | Liefert vordefinierten AuthContext mit konfigurierbaren Rollen/Tenant |
| `StubPresetConfig` | PresetConfigEngine | Liefert konfigurierbare PresetConfig pro Workspace |
| `StubApplicationService` | ApplicationService (für MCP-Testing) | Zeichnet Methodenaufrufe auf; liefert vordefinierte Ergebnisse |

### 5.3 Boundary- & Invalid-Testdaten

| Kategorie | Testdaten | Zweck |
|-----------|-----------|-------|
| **Gültige Boundaries** | Empty-String-Titel, Max-Length-Titel (1000 Zeichen), UUID-Edge-Cases | Boundary-Value-Analyse |
| **Ungültige Typen** | Nicht-numerische IDs, Null-Pflichtfelder, falsche Typ-Enums | Typ-Validierung |
| **Cross-Tenant** | Entity-IDs von Tenant A accessed by Tenant B | Tenant-Isolation |
| **Cross-Workspace** | TraceLinks zwischen Workspaces | Workspace-Konsistenz |
| **Parallel** | Simultane Updates auf gleiche Entity | Optimistic Locking |
| **Performance** | 10.000 Items, 50.000 Trace-Links, 100.000 Audit-Entries | SLA-Verifikation |

### 5.4 Boundary-Value-Analyse (BVA) — Systematisch

| TC-ID | Kategorie | Szenario | Testdaten | Erwartete Reaktion | Gilt für |
|-------|-----------|----------|-----------|-------------------|----------|
| TC-BVA-001 | Pagination | page_size=0 Rejektion | `page=1, page_size=0` | 400: "page_size must be ≥ 1" | REST API, AuditLog, TraceLink-Queries |
| TC-BVA-002 | Pagination | page_size=1 Minimum | `page=1, page_size=1` | Genau 1 Ergebnis | Alle Listen-Endpunkte |
| TC-BVA-003 | Pagination | Max page_size | `page_size=10000` | 400 oder gecappt bei 100 | Alle Listen-Endpunkte |
| TC-BVA-004 | Pagination | page=0 Rejektion | `page=0` | 400: "page must be ≥ 1" | Alle Listen-Endpunkte |
| TC-BVA-005 | Pagination | Page jenseits Datenbereich | `page=9999` (nur 50 Items) | Leere Ergebnisliste; kein Fehler | Alle Listen-Endpunkte |
| TC-BVA-006 | String-Länge | Empty-String-Titel | `title=""` | 400: "title must not be empty" | Requirement, TestCase, Baseline-Erstellung |
| TC-BVA-007 | String-Länge | Max-Length-Titel | `title="x"*1000` | Akzeptiert; vollständig gespeichert | Requirement, TestCase-Erstellung |
| TC-BVA-008 | String-Länge | Over-Max-Titel | `title="x"*1001` | 400: "title exceeds maximum length" | Requirement, TestCase-Erstellung |
| TC-BVA-009 | String-Länge | Description-Max-Boundary | `description="x"*10000` | Akzeptiert; vollständig gespeichert | Alle Entities mit Description-Feld |
| TC-BVA-010 | String-Länge | Over-Max-Description | `description="x"*10001` | 400: "description exceeds maximum length" | Alle Entities mit Description-Feld |
| TC-BVA-011 | Numerisch | Negative-ID-Rejektion | `id=-1` | 400 oder 404; kein Datenleck | Alle Get-by-ID-Endpunkte |
| TC-BVA-012 | Numerisch | Zero-ID-Rejektion | `id=0` | 400 oder 404; kein Datenleck | Alle Get-by-ID-Endpunkte |
| TC-BVA-013 | Numerisch | Max-Integer-ID | `id=2147483647` (INT_MAX) | 404 (not found); kein Overflow | Alle Get-by-ID-Endpunkte |
| TC-BVA-014 | Numerisch | Overflow-ID | `id=2147483648` (INT_MAX+1) | 400: invalid ID format | Alle Get-by-ID-Endpunkte |
| TC-BVA-015 | Array | Leeres Array in Batch | `ids=[]` | 400: "at least one ID required" | Batch-Create/Delete |
| TC-BVA-016 | Array | Single-Element-Array | `ids=["uuid-1"]` | Genau ein Item verarbeitet | Batch-Operationen |
| TC-BVA-017 | Array | Max-Batch-Size | `ids=[...100 UUIDs]` | Alle 100 verarbeitet | Batch-Operationen |
| TC-BVA-018 | Array | Over-Max-Batch | `ids=[...101 UUIDs]` | 400: "batch size exceeds maximum (100)" | Batch-Operationen |
| TC-BVA-019 | Array | Duplicate-IDs | `ids=["uuid-1", "uuid-1"]` | Dedupliziert oder 400: "duplicate IDs" | Batch-Operationen |

### 5.5 Edge-Case- & Resilience-Tests

| TC-ID | Kategorie | Szenario | Vorbedingung | Stimulus | Erwartete Reaktion |
|-------|-----------|----------|--------------|----------|-------------------|
| TC-EDGE-001 | DB-Resilience | **DB-Connection-Drop-Recovery** | Aktive DB-Connection | PostgreSQL-Connection mid-query killen | Operation failt gracefully; Retry erfolgreich innerhalb 5s |
| TC-EDGE-002 | DB-Resilience | **Connection-Pool-Erschöpfung** | Pool bei Max-Capacity (20) | 21. parallele Connection anfordern | Wait/Timeout mit klarem Fehler; kein Crash |
| TC-EDGE-003 | DB-Resilience | **Deadlock-Detection** | Zwei parallele Transaktionen mit Lock-Ordering-Konflikt | Konfliktparallele Transaktionen | Eine Transaktion zurückgerollt; andere erfolgreich |
| TC-EDGE-004 | Netzwerk | **Netzwerk-Partition** | McpServer mit ApplicationService verbunden | Netzwerk zwischen Containern trennen | Pending-Requests timeout; Reconnect erfolgreich |
| TC-EDGE-005 | Payload | **Max-Payload-Handling** | API konfiguriert für 10MB max | 10MB-JSON-Payload senden | Akzeptiert und innerhalb SLA verarbeitet |
| TC-EDGE-006 | Payload | **Over-Max-Payload-Rejektion** | API konfiguriert für 10MB max | 11MB-JSON-Payload senden | 413 Payload Too Large; Connection erhalten |
| TC-EDGE-007 | Input | **Unicode-Injection** | Normale Input-Felder | `\u0000\uFFFF` und Mixed Scripts senden | Input sanitisiert; kein Crash |
| TC-EDGE-008 | Input | **SQL-Injection in Search** | Search-Endpunkt | `'; DROP TABLE requirements; --` senden | Parametrisierte Query; keine SQL-Injection |
| TC-EDGE-009 | Concurrency | **Optimistic-Lock unter Contention** | 10 parallele Updates auf gleiche Entity | 10 parallele PATCH-Requests | Genau eines erfolgreich; andere 409 Conflict |
| TC-EDGE-010 | Memory | **Large-Export-Memory-Management** | 50.000 Items im Workspace | `export(format="json")` | Streaming-Response; Memory < 1GB; kein OOM |
| TC-EDGE-011 | Zeit | **Timezone-Edge-Cases** | DST-Transition-Periode | Items während DST-Spring-Forward erstellen | Timestamps in UTC gespeichert; korrekt lokal angezeigt. *Clock-Mocking via `freezegun` erforderlich* |
| TC-EDGE-012 | Auth | **Token-Expiry während Request** | JWT expireert mid-request (30s Operation) | Operation starten; Token während Ausführung ablaufen lassen | Operation abgeschlossen wenn bereits autorisiert. *Clock-Mocking via `freezegun` erforderlich* |

### 5.6 Clock-Mocking Strategy

Zeitbasierte Tests erfordern deterministische Clock-Steuerung um Flakiness zu vermeiden.

| Ansatz | Tool | Verwendung |
|--------|------|------------|
| **Freeze-Time** | `freezegun` | Standard für alle zeitabhängigen Tests (Audit, Workflow, Token-Expiry) |
| **Tick-Mode** | `freezegun.tick()` | Für Tests mit expliziter Zeitfortschritt (z.B. Token-Ablauf, Timeout) |
| **UTC-Enforcement** | `pytz.UTC` | Alle Timestamps in UTC persistieren; Locale-Conversion nur in Presentation Layer |

**Regel:** Kein zeitabhängiger Test ohne Clock-Mocking. Zeit wird nie aus dem System-OS gelesen.

### 5.7 Äquivalenzklassen-Definitionen

| Parameter | Gültige Klassen | Ungültige Klassen | Test-IDs |
|-----------|----------------|-------------------|----------|
| **entity_id (UUID)** | EC-1: Gültige UUID v4 im korrekten Tenant | EC-2: UUID von anderem Tenant; EC-3: Non-UUID-String; EC-4: Null/empty; EC-5: UUID falschen Entity-Typs | TC-BVA-011..014, TC-Persist-003 |
| **page (integer)** | EC-6: 1 ≤ page ≤ max_page | EC-7: page ≤ 0; EC-8: page > max_page; EC-9: Non-integer | TC-BVA-004, TC-BVA-005 |
| **page_size (integer)** | EC-10: 1 ≤ page_size ≤ 100 | EC-11: page_size ≤ 0; EC-12: page_size > 100; EC-13: Non-integer | TC-BVA-001..003 |
| **title (string)** | EC-14: 1 ≤ len ≤ 1000, printable chars | EC-15: Empty string; EC-16: len > 1000; EC-17: Null bytes; EC-18: Pure whitespace | TC-BVA-006..008, TC-EDGE-007 |
| **description (string)** | EC-19: 0 ≤ len ≤ 10000 | EC-20: len > 10000; EC-21: Contains control chars | TC-BVA-009, TC-BVA-010 |
| **preset_type (enum)** | EC-22: "minimal"; EC-23: "standard"; EC-24: "extended" | EC-25: Unknown string; EC-26: Null; EC-27: Case variant ("Standard") | TC-Preset-001..003 |
| **scope (enum)** | EC-28: "document"; EC-29: "project"; EC-30: "global" | EC-31: Unknown string; EC-32: Null | TC-BS-001..003, TC-Preset-012..013 |
| **link_type (enum)** | EC-33: "parent-child"; EC-34: "derives-from"; EC-35: "satisfies"; EC-36: "verifies"; EC-37: "implements"; EC-38: "refines" | EC-39: Unknown string; EC-40: Null; EC-41: Empty string | TC-Trace-002, TC-Trace-004 |
| **api_key (string)** | EC-42: Gültiger 64-char hex key | EC-43: Too short; EC-44: Too long; EC-45: Non-hex chars; EC-46: Expired/revoked | TC-Auth-006, TC-Auth-007, TC-MCP-028, TC-MCP-029 |
| **role (string)** | EC-47: "admin"; EC-48: "editor"; EC-49: "viewer" | EC-50: Unknown role; EC-51: Null; EC-52: Empty string | TC-Auth-011..013, TC-MCP-030 |
| **batch_ids (array)** | EC-53: 1-100 gültige UUIDs | EC-54: Empty array; EC-55: > 100 UUIDs; EC-56: Contains invalid UUIDs; EC-57: Contains duplicates | TC-BVA-015..019, TC-Trace-013, TC-Trace-014 |
| **mcp_payload (JSON)** | EC-58: Gültiger JSON-RPC 2.0 Frame | EC-59: Malformed JSON; EC-60: Missing "method"; EC-61: Extra unknown fields | TC-MCP-001, TC-EDGE-005, TC-EDGE-006 |

---

## 6. Security-Testszenarien

### 6.1 Tenant-Isolation

| TC-ID | Szenario | Angriff | Erwartete Reaktion |
|-------|----------|---------|-------------------|
| TC-SEC-001 | **Cross-Tenant-Datenzugriff** | Tenant A versucht Entity von Tenant B zu lesen | 404 (Entity nicht gefunden im eigenen Tenant) |
| TC-SEC-002 | **Cross-Tenant-Schreibzugriff** | Tenant A versucht Entity von Tenant B zu updaten | 404 oder 403 |
| TC-SEC-003 | **Cross-Tenant-TraceLink** | Tenant A versucht TraceLink zu Tenant-B-Entity | TenantViolationError |
| TC-SEC-004 | **Tenant-Context-Manipulation** | Manipuliertes JWT mit fremder tenant_id | Auth-Rejektion; Token als ungültig behandelt |
| TC-SEC-005 | **Raw-SQL-Tenant-Bypass** | SQL-Injection-Versuch um Tenant-Filter zu umgehen | Parametrisierte Queries; Injection wirkungslos |

### 6.2 RBAC-Enforcement

| TC-ID | Szenario | Angriff | Erwartete Reaktion |
|-------|----------|---------|-------------------|
| TC-SEC-006 | **Viewer versucht Schreibzugriff** | Viewer-Rolle versucht Requirement zu erstellen | 403: permission denied |
| TC-SEC-007 | **Editor versucht Approval** | Editor-Rolle (ohne Approver) versucht approve | 403: role_not_authorized |
| TC-SEC-008 | **Approver in Minimal-Preset** | Approver-Rolle in Minimal-Workspace | Approver-Rolle nicht aktiv; 403 |
| TC-SEC-009 | **MCP-Tool-RBAC** | Viewer versucht requirement.create via MCP | McpError: permission_denied |

### 6.3 API-Key-Validierung

| TC-ID | Szenario | Angriff | Erwartete Reaktion |
|-------|----------|---------|-------------------|
| TC-SEC-010 | **Abgelaufener API-Key** | Abgelaufener API-Key bei MCP-Call | 401: api_key_expired |
| TC-SEC-011 | **Widerrufener API-Key** | Widerrufener API-Key | 401: api_key_revoked |
| TC-SEC-012 | **Timing-Attacke** | Variierende Key-Längen für Timing-Analyse | Constant-Time-Vergleich; ≥1000 Wiederholungen, Perzentil-Vergleich (p99 < threshold) |
| TC-SEC-013 | **Brute-Force-Schutz** | 100 fehlgeschlagene API-Key-Versuche in 60s | Rate-Limiting; temporäre Sperre |

### 6.4 Audit-Trail-Vollständigkeit

| TC-ID | Szenario | Erwartete Reaktion |
|-------|----------|-------------------|
| TC-SEC-014 | **REST-Schreiboperation ohne Audit** | Jeder REST-Write erzeugt AuditLogEntry |
| TC-SEC-015 | **MCP-Schreiboperation ohne Audit** | Jeder MCP-Write erzeugt AuditLogEntry mit source="mcp", client_name, api_key_hash |
| TC-SEC-016 | **Audit-Entry-Manipulation** | AuditLogEntry nicht modifizierbar (append-only) |
| TC-SEC-017 | **Audit-Query-Tenant-Isolation** | Audit-Query zeigt nur Entries des eigenen Tenants |

---

## 7. Performance-Testszenarien

| TC-ID | Szenario | Ziel | Last | Messgröße |
|-------|----------|------|------|-----------|
| TC-PERF-BVA-001 | **BVA — 0 Items** | < 10ms | Leere DB | Query-Response-Zeit |
| TC-PERF-BVA-002 | **BVA — 1 Item** | < 50ms | 1 Item | Query-Response-Zeit |
| TC-PERF-BVA-003 | **BVA — 10.001 Items** | Pagination aktiviert | 10.001 Items | Page-Size-Verifikation; Response-Zeit |
| TC-PERF-001 | **REST-Standard-Query** | < 200ms p95 | 10.000 Items, 50 simultan | API-Response-Zeit |
| TC-PERF-002 | **Full-Text-Search** | < 500ms p95 | 10.000 Items | Search-Response-Zeit |
| TC-PERF-003 | **Traceability-Query** | < 200ms | 10.000 Items, 50.000 Links | Graph-Query-Zeit |
| TC-PERF-004 | **Baseline-Erstellung (Projekt-Scope)** | < 5s | 1.000 Items | Baseline-Creation-Zeit |
| TC-PERF-005 | **Baseline-Diff** | < 3s | 10.000 Items pro Baseline | Diff-Berechnungszeit |
| TC-PERF-006 | **Workflow-Transition-Validierung** | < 10ms | Geladene Definition | Einzelne Validierung |
| TC-PERF-007 | **Audit-Log-Query** | < 200ms p95 | 100.000 Audit-Entries | Query-Response-Zeit |
| TC-PERF-008 | **MCP-Concurrent-Load** | < 2s p95 | 50 simultane MCP-Clients | MCP-Response-Zeit |
| TC-PERF-009 | **MCP-Throughput** | 100 req/s | Sustained Load 60s | Fehlerrate, p99-Latenz |
| TC-PERF-010 | **CSV-Bulk-Import** | < 30s | 10.000 Zeilen | Import-Zeit |
| TC-PERF-011 | **JSON-Export** | < 5s | 1.000 Items | Export-Zeit |
| TC-PERF-012 | **Large-Export-Streaming** | < 1GB Memory | 50.000 Items | Memory-Peak |

---

## 8. Coverage-Summary & Traceability

### 8.1 Anforderungs-Coverage-Matrix

| L2-System | REQ-L2 | Test-Szenarien | Coverage |
|-----------|--------|---------------|----------|
| PersistenceLayerSystem | 9 | 14 Komp. + 5 Int. | 9/9 (100%) |
| AuthAndTenancySystem | 10 | 21 Komp. + 5 Int. | 10/10 (100%) |
| PresetConfigEngineSystem | 14 | 17 Komp. | 14/14 (100%) |
| AuditLogSystem | 7 | 8 Komp. | 7/7 (100%) |
| LlmAdapterSystem | 7 | 14 Komp. + 5 Int. | 7/7 (100%) |
| TraceabilityEngineSystem | 12 | 22 Komp. + 5 Int. | 12/12 (100%) |
| WorkflowEngineSystem | 8 | 15 Komp. + 3 Int. | 8/8 (100%) |
| BaselineServiceSystem | 8 | 14 Komp. + 3 Int. | 8/8 (100%) |
| ReactFrontendSystem | 12 | 12 Komp. + 5 Int. | 12/12 (100%) |
| RestApiAdapterSystem | 12 | 12 Komp. + 6 Int. | 12/12 (100%) |
| ApplicationServiceSystem | 25 | 30 L3-Unit + 5 L3-Int + 8 L2-Int | 25/25 (100%) |
| McpServerSystem | 12 | 35 L3-Unit + 2 L3-Int + 9 L2-Int | 12/12 (100%) |
| **Cross-Cutting** | — | 19 BVA + 12 Edge/Resilience + 17 Security + 15 Performance | — |
| **GESAMT** | **136** | **214 Komp./Unit + 61 Int. + 63 Cross-Cutting** | **136/136 (100%)** |

### 8.2 Interface-Coverage-Matrix

| Interface-Klasse | Gesamt | Getestet | Coverage |
|-----------------|--------|----------|----------|
| IF-EXT (External) | 6 | 6 (via E2E) | 6/6 (100%) |
| IF-L1 (Inter-System) | 31 | 31 (via System-Integration) | 31/31 (100%) |
| IF-L2-internal (Intra-System) | 60 | 60 | 60/60 (100%) |
| IF-L3 (Unit ↔ Unit) | 7 | 7 | 7/7 (100%) |
| **GESAMT** | **104** | **104** | **104/104 (100%)** |

### 8.3 Integrationsschritte-Summary

| Schritt | System | Testanzahl | Abhängigkeiten |
|---------|--------|-----------|----------------|
| 1 | PersistenceLayer | 19 | Keine (Foundation) |
| 2 | + AuthAndTenancy | 26 | PersistenceLayer |
| 3 | + PresetConfigEngine | 17 | PersistenceLayer |
| 4 | + AuditLog | 8 | PersistenceLayer |
| 5 | + LlmAdapter | 19 | AuditLog |
| 6 | + TraceabilityEngine | 27 | PersistenceLayer |
| 7 | + WorkflowEngine | 18 | PresetConfigEngine, AuthAndTenancy |
| 8 | + BaselineService | 17 | TraceabilityEngine, PresetConfigEngine |
| 9 | + ApplicationService | 43 | Alle Domain-Services |
| 10 | + RestApiAdapter | 18 | ApplicationService, AuthAndTenancy, PresetConfigEngine |
| 11 | + McpServer | 46 | ApplicationService, AuthAndTenancy, PresetConfigEngine, AuditLog |
| 12 | + ReactFrontend | 17 | RestApiAdapter |
| — | Cross-Cutting | 63 | Alle Systeme |

---

## 9. Testausführungsprioritäten

### 9.1 Prioritätsklassifikation

| Priorität | Kriterien | Systeme |
|-----------|-----------|---------|
| **P0 — Kritisch** | Core-Datenpfad; blockiert alle anderen Tests; Sicherheit | PersistenceLayer, AuthAndTenancy |
| **P1 — Hoch** | Core-Domänenlogik; zentrale Orchestrierung | ApplicationService, WorkflowEngine, BaselineService, TraceabilityEngine |
| **P2 — Mittel** | Interface-Adapter; Präsentation | RestApiAdapter, McpServer, ReactFrontend |
| **P3 — Standard** | Unterstützende Services | PresetConfigEngine, AuditLog, LlmAdapter |

### 9.2 Ausführungsreihenfolge

```
Phase 1 (P0): PersistenceLayer → AuthAndTenancy → PresetConfigEngine → AuditLog
Phase 2 (P1): LlmAdapter → TraceabilityEngine → WorkflowEngine → BaselineService → ApplicationService
Phase 3 (P2): RestApiAdapter → McpServer → ReactFrontend
Phase 4 (Cross-Cutting): Security + Performance + BVA + Edge/Resilience
Phase 5 (E2E): Vollständige User-Journeys (REST + MCP + UI)
```

---

## 10. Quality-Gates

### 10.1 Entry-Kriterien für Integration-Testing

| Gate | Kriterium |
|------|-----------|
| **Unit → Integration** | Alle Unit-Tests grün; Code-Coverage ≥ 80% pro Komponente |
| **Integration → System** | Alle Integrationstests grün; Interface-Coverage 100% |
| **System → Acceptance** | Alle Systemtests grün; Performance-SLAs erfüllt |

### 10.2 Exit-Kriterien für Test-Phase

| Kriterium | Ziel |
|-----------|------|
| Anforderungs-Coverage | 100% (jedes REQ-L2 hat ≥ 1 Testszenario) |
| Interface-Coverage | 100% (jede interne Schnittstelle ≥ 1x getestet) |
| Integrationsschritte | Alle 12 Schritte ausgeführt und bestanden |
| Performance-SLAs | Alle Latenz/Throughput-Anforderungen verifiziert |
| Security-Tests | Alle Tenant-Isolation-, RBAC-, Audit-Tests bestanden |
| Fault-Injection | Alle Fault-Injection-Punkte getestet |

---

*Erstellt durch se-test-engineer-Agent | ReqFlow SE-Kaskade V&V | 2026-06-20*
*Branch: refactor/se-structure*
*Handoff: HOFF-20260620-006*
*Bereit für se-testreviewer Quality-Gate-Audit*
