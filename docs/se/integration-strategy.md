# ReqFlow — Integrationsstrategie

> **Status:** KONSOLIDIERT | **Datum:** 2026-06-20
> **Scope:** 12 L2-Subsysteme, 55 Komponenten, 95 Schnittstellen
>
> **Quellen (autoritativ):**
> - L1-Architektur: `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architektur.md`
> - 12 L2-Architekturen: `docs/se/L1/Gesamtsystem/L2/*/L2_*_Architecture.md`
> - Interface-Registry: `docs/se/interface-registry.md`
> - Test-Strategie: `docs/se/test-strategy.md` (338 Szenarien)
> - Traceability-Matrix: `docs/se/traceability-matrix.md`

---

## 1. Integrationsstrategie — Überblick

### 1.1 Strategie-Selektion: Bottom-Up mit Sandwich-Elementen

**Primärstrategie: Bottom-Up** — begründet durch die geschichtete Architektur und den Abhängigkeitsgraphen.

**Entscheidungskriterien:**

| Kriterium | Bewertung | Favorisiert |
|-----------|-----------|-------------|
| Anzahl Leaf-Systeme | 10 von 12 Systemen sind Leaf (terminal at L2) | Bottom-Up |
| Abhängigkeitstiefe | 5 Schichten (Layer 0–4) mit klarer Schichtung | Bottom-Up |
| Foundation-Dependency | 10 von 12 Systemen dependieren von PersistenceLayer | Bottom-Up |
| Continue-Systeme | 2 Systeme (ApplicationService, McpServer) haben aktive L3 | Sandwich |
| Interface-Kritikalität | 31 L1-Inter-System-Schnittstellen; 60 L2-interne Schnittstellen | Interface-First |
| Risiko-Konzentration | ApplicationService ist zentraler Orchestrator (10 ausgehende L1-IFs) | Sandwich für AppSvc |

**Rationale:** Die geschichtete Architektur bildet sich natürlich auf eine Bottom-Up-Integrationssequenz ab. PersistenceLayer ist die universelle Foundation (10/12 Systeme dependieren davon). Domain-Services (Layer 1) können unabhängig verifiziert werden bevor ApplicationService (Layer 2) sie integriert. Interface-Adapter (Layer 3) werden gegen den bereits verifizierten Domain-Core getestet. ReactFrontend (Layer 4) ist der finale Integrationspunkt.

Die zwei Continue-Systeme (ApplicationService mit 13 L3-Units, McpServer mit 22 L3-Units) nutzen einen **Sandwich-Ansatz**: L3-Unit-Tests laufen Bottom-Up (einzelne Handler), während L2-System-Integrationstests Top-Down (Dispatcher → Handler → ApplicationService) laufen.

### 1.2 Integrations-Architektur

```
Layer 4: ReactFrontend ──────────────────────── Schritt 12 (final)
Layer 3: RestApiAdapter, McpServer ──────────── Schritte 10–11
Layer 2: ApplicationService ─────────────────── Schritt 9 (zentraler Orchestrator)
Layer 1: WorkflowEngine, BaselineService, ───── Schritte 5–8
          TraceabilityEngine, LlmAdapter
Layer 0: PersistenceLayer, AuthAndTenancy, ──── Schritte 1–4
          PresetConfigEngine, AuditLog
```

### 1.3 System-Klassifikation

| Kategorie | Systeme | Anzahl | Integrationsansatz |
|-----------|---------|--------|-------------------|
| **Infrastruktur** (Layer 0) | PersistenceLayer, AuthAndTenancy, PresetConfigEngine, AuditLog | 4 | Bottom-Up, sequentiell |
| **Domain-Services** (Layer 1) | LlmAdapter, TraceabilityEngine, WorkflowEngine, BaselineService | 4 | Bottom-Up, teilweise parallel |
| **Orchestrierung** (Layer 2) | ApplicationService | 1 | Sandwich (L3 Bottom-Up + L2 Top-Down) |
| **Interface-Adapter** (Layer 3) | RestApiAdapter, McpServer | 2 | Top-Down gegen verifizierten Domain-Core |
| **Präsentation** (Layer 4) | ReactFrontend | 1 | Top-Down gegen verifizierten REST-Adapter |

---

## 2. Abhängigkeitsgraph

### 2.1 System-Dependency-Matrix

> Zeile = System; Spalten = Abhängigkeiten (System ruft auf). ✓ = direkte Abhängigkeit via L1-Schnittstelle.

| System (ARCH-L1) | Persist (010) | Auth (011) | Preset (008) | Audit (012) | Llm (009) | Trace (007) | WF (005) | BS (006) | AppSvc (004) | REST (002) | MCP (003) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **PersistenceLayer (010)** | — | | | | | | | | | | |
| **AuthAndTenancy (011)** | ✓ | — | | | | | | | | | |
| **PresetConfigEngine (008)** | ✓ | | — | | | | | | | | |
| **AuditLog (012)** | ✓ | | | — | | | | | | | |
| **LlmAdapter (009)** | | | | ✓ | — | | | | | | |
| **TraceabilityEngine (007)** | ✓ | | | | | — | | | | | |
| **WorkflowEngine (005)** | ✓ | ✓ | ✓ | | | | — | | | | |
| **BaselineService (006)** | ✓ | | ✓ | | | ✓ | | — | | | |
| **ApplicationService (004)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | | |
| **RestApiAdapter (002)** | | ✓ | ✓ | | | | | | ✓ | — | |
| **McpServer (003)** | | ✓ | ✓ | ✓ | | ✓ | ✓ | | ✓ | | — |
| **ReactFrontend (001)** | | | | | | | | | | ✓ | — |

### 2.2 Dependency-Tiefe (Topologische Ordnung)

```
Tiefe 0: PersistenceLayer          (keine Abhängigkeiten)
Tiefe 1: AuthAndTenancy            (abhängig von: Persist)
         PresetConfigEngine        (abhängig von: Persist)
         AuditLog                  (abhängig von: Persist)
Tiefe 2: LlmAdapter                (abhängig von: Audit)
         TraceabilityEngine        (abhängig von: Persist)
Tiefe 3: WorkflowEngine            (abhängig von: Persist, Auth, Preset)
         BaselineService           (abhängig von: Persist, Trace, Preset)
Tiefe 4: ApplicationService        (abhängig von: ALLEN Domain-Services)
Tiefe 5: RestApiAdapter            (abhängig von: AppSvc, Auth, Preset)
         McpServer                 (abhängig von: AppSvc, Auth, Preset, Audit, WF, Trace)
Tiefe 6: ReactFrontend             (abhängig von: REST)
```

### 2.3 Kritischer Pfad

```
PersistenceLayer → AuthAndTenancy → WorkflowEngine → ApplicationService → McpServer
     (Schritt 1)      (Schritt 2)       (Schritt 7)        (Schritt 9)         (Schritt 11)

PersistenceLayer → ApplicationService → RestApiAdapter → ReactFrontend
     (Schritt 1)          (Schritt 9)       (Schritt 10)      (Schritt 12)
```

**Kritischer Pfad Länge:** 5 Schritte (Persist → Auth → WF → AppSvc → McpServer)
**Totale Integrationsschritte:** 12 sequentiell + Cross-Cutting E2E

---

## 3. Integrationsphasen & -reihenfolge

### 3.1 Phasen-Überblick

| Phase | Name | Schritte | Systeme | Priorität | Testanzahl |
|-------|------|----------|---------|-----------|-----------|
| **Phase 1** | Infrastructure Foundation | 1–4 | PersistenceLayer, AuthAndTenancy, PresetConfigEngine, AuditLog | P0 — Kritisch | 70 |
| **Phase 2** | Domain Service Assembly | 5–8 | LlmAdapter, TraceabilityEngine, WorkflowEngine, BaselineService | P1 — Hoch | 81 |
| **Phase 3** | Orchestration Integration | 9 | ApplicationService | P1 — Hoch | 43 |
| **Phase 4** | Interface Adapter Integration | 10–11 | RestApiAdapter, McpServer | P2 — Mittel | 64 |
| **Phase 5** | Presentation Integration | 12 | ReactFrontend | P2 — Mittel | 17 |
| **Phase 6** | Cross-Cutting & E2E | — | Alle Systeme | P0 — Kritisch | 70 |
| | **Gesamt** | **12** | **12 Systeme** | | **338** |

### 3.2 Detaillierte Integrationsschritte

---

#### Phase 1 — Infrastructure Foundation (P0)

##### Schritt 1: PersistenceLayer (ARCH-L1-010) — Foundation

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (alleinstehend) |
| **Abhängigkeiten** | Keine — Foundation-Layer |
| **L3-Status** | Terminal at L2 (5 Komponenten) |
| **Verifizierte Interfaces** | IF-PL-INT-001..005 (5 intern) |
| **Testanzahl** | 14 Komp. + 5 Int. = **19** |
| **Entry-Kriterien** | PostgreSQL-Test-Container läuft; Django ORM konfiguriert |
| **Exit-Kriterien** | Alle 19 Tests grün; Tenant-Isolation verifiziert; Migrations-Idempotenz bestätigt; Performance-SLA < 500ms verifiziert; Audit-Felder-Verhalten (created_at/modified_at/version) bestätigt |
| **Risiko** | HOCH — alle nachfolgenden Schritte dependieren davon. Failure blockiert gesamte Integration. |
| **Mitigation** | DB-Schema vor Weitergang verifizieren; volles Migration-Suite ausführen; Connection-Pooling unter Last validieren |
| **Gate** | G1: Foundation Verified |

##### Schritt 2: AuthAndTenancy + PersistenceLayer (ARCH-L1-011)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritt 1) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅) |
| **L3-Status** | Terminal at L2 (8 Komponenten) |
| **Verifizierte Interfaces** | INT-L2-A-001..005 (5 intern); IF-L1-022 (Persist via ORM) |
| **Testanzahl** | 21 Komp. + 5 Int. = **26** |
| **Entry-Kriterien** | Schritt 1 bestanden; User/Role/Tenant-Seed-Daten verfügbar |
| **Exit-Kriterien** | Bearer-Token + API-Key-Validierung funktional; RBAC Allow/Deny verifiziert; Tenant-Context-Propagation bestätigt; immutabler AuthContext verifiziert; API-Key-Lifecycle (Erstellung, Liste, Limit) verifiziert |
| **Risiko** | HOCH — Tenant-Isolation ist sicherheitskritisch. Alle nachfolgenden Systeme benötigen AuthContext. |
| **Mitigation** | Cross-Tenant-Access-Tests obligatorisch; Constant-Time-Vergleich für API-Keys verifiziert |
| **Gate** | G2: Auth Verified |

##### Schritt 3: PresetConfigEngine + PersistenceLayer (ARCH-L1-008)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritt 1) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅) |
| **L3-Status** | Terminal at L2 (1 Komponente — Black-Box) |
| **Verifizierte Interfaces** | IF-L1-022 (Persist via ORM) |
| **Testanzahl** | 17 Komp. = **17** |
| **Entry-Kriterien** | Schritt 1 bestanden; Workspace-Entities mit Preset-Typen geseedet |
| **Exit-Kriterien** | Alle 3 Presets liefern korrekte Config; Feature-Flags korrekt; Terminologie-Profile verifiziert; Preset-Immutabilität bestätigt; Downgrade-Validierung funktional |
| **Risiko** | MITTEL — einzelne Komponente, klar definierter Kontrakt. |
| **Parallelism** | Kann parallel mit Schritt 2 laufen (beide dependieren nur von Schritt 1) |
| **Gate** | G3: Preset Verified |

##### Schritt 4: AuditLog + PersistenceLayer (ARCH-L1-012)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritt 1) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅) |
| **L3-Status** | Terminal at L2 (1 Komponente — Append-Only) |
| **Verifizierte Interfaces** | IF-L1-022 (Persist via ORM) |
| **Testanzahl** | 8 Komp. = **8** |
| **Entry-Kriterien** | Schritt 1 bestanden; Auth-Context verfügbar für Audit-Actor |
| **Exit-Kriterien** | Append-Only-Semantik verifiziert (UPDATE/DELETE rejected); MCP-Anreicherung funktional; atomare Konsistenz mit Business-Ops bestätigt; Pagination < 200ms bei 100k Entries |
| **Risiko** | NIEDRIG — einfaches Append-Only-Pattern. |
| **Parallelism** | Kann parallel mit Schritten 2 und 3 laufen |
| **Gate** | G4: Audit Verified |

**Phase 1 Abschluss:** Alle 4 Infrastruktur-Systeme verifiziert. 70 Tests bestanden. Foundation für Domain-Services etabliert.

---

#### Phase 2 — Domain Service Assembly (P1)

##### Schritt 5: LlmAdapter + AuditLog (ARCH-L1-009)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritten 1, 4) |
| **Abhängigkeiten** | AuditLog (Schritt 4 ✅); PersistenceLayer (Schritt 1 ✅, implizit) |
| **L3-Status** | Terminal at L2 (4 Komponenten) |
| **Verifizierte Interfaces** | 5 L2-intern; IF-L1-021 (→ AuditLog); IF-L1-023 (→ External LLM) |
| **Testanzahl** | 14 Komp. + 5 Int. = **19** |
| **Entry-Kriterien** | Schritte 1, 4 bestanden; MockLlmProvider konfiguriert |
| **Exit-Kriterien** | Alle 3 Provider (Anthropic, OpenAI, Ollama) via MockLlmProvider; Capability-Registry erzwingt selektive Aktivierung; Graceful Degradation ohne Config; Token-Usage-Extraktion korrekt; Audit-Logging für jeden LLM-Call |
| **Risiko** | MITTEL — externe Abhängigkeit (LLM) via MockLlmProvider abstrahiert. |
| **Parallelism** | Kann parallel mit Schritt 6 laufen (unabhängige Abhängigkeiten) |
| **Gate** | G5: LLM Adapter Verified |

##### Schritt 6: TraceabilityEngine + PersistenceLayer (ARCH-L1-007)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritt 1) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅) |
| **L3-Status** | Terminal at L2 (4 Module) |
| **Verifizierte Interfaces** | IF-TE-INT-001..003 (3 intern); IF-L1-022 (Persist) |
| **Testanzahl** | 22 Komp. + 5 Int. = **27** |
| **Entry-Kriterien** | Schritt 1 bestanden; Entity-Fixtures mit Trace-Links |
| **Exit-Kriterien** | TraceLink-CRUD mit Validierung; Graph-Queries (upstream/downstream/transitive closure) < 200ms bei 10k Items; Coverage-Berechnung korrekt; Batch-Operationen atomar; Tenant-Isolation erzwungen; Audit-Metadaten immutable; Zyklenerkennung in TraceabilityEngine verifiziert |
| **Risiko** | MITTEL — Graph-Query-Performance kritisch. |
| **Parallelism** | Kann parallel mit Schritt 5 laufen |
| **Gate** | G6: Traceability Verified |

##### Schritt 7: WorkflowEngine + PresetConfigEngine + AuthAndTenancy (ARCH-L1-005)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritten 1, 2, 3) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅), AuthAndTenancy (Schritt 2 ✅), PresetConfigEngine (Schritt 3 ✅) |
| **L3-Status** | Terminal at L2 (3 Module) |
| **Verifizierte Interfaces** | IF-WE-INT-001..003 (3 intern); IF-L1-017 (→ Preset); IF-L1-018 (→ Auth); IF-L1-022 (Persist) |
| **Testanzahl** | 15 Komp. + 3 Int. = **18** |
| **Entry-Kriterien** | Schritte 1, 2, 3 bestanden; Workflow-Definitions geseedet pro Preset |
| **Exit-Kriterien** | Gültige/ungültige Transitions verifiziert; Rollen-Checks erzwungen; change_reason obligatorisch in Extended; Fail-Fast-Regelreihenfolge; Performance-Budget < 10ms pro Validierung; Tenant-Isolation; atomare State-Mutation mit Optimistic Locking; konkurrente Transitionen auf selben State erzeugen 409 Conflict |
| **Risiko** | MITTEL — Preset-abhängiges Verhalten adds Komplexität. |
| **Gate** | G7: Workflow Verified |

##### Schritt 8: BaselineService + TraceabilityEngine + PresetConfigEngine (ARCH-L1-006)

| Attribut | Wert |
|----------|------|
| **Strategie** | Bottom-Up (abhängig von Schritten 1, 3, 6) |
| **Abhängigkeiten** | PersistenceLayer (Schritt 1 ✅), PresetConfigEngine (Schritt 3 ✅), TraceabilityEngine (Schritt 6 ✅) |
| **L3-Status** | Terminal at L2 (4 Komponenten) |
| **Verifizierte Interfaces** | IF-BL-INT-001..003 (3 intern); IF-L1-019 (→ Trace); IF-L1-020 (→ Preset); IF-L1-022 (Persist) |
| **Testanzahl** | 14 Komp. + 3 Int. = **17** |
| **Entry-Kriterien** | Schritte 1, 3, 6 bestanden; Workspace mit Items und Trace-Links |
| **Exit-Kriterien** | Alle 3 Scopes (document/project/global) lösen korrekt auf; Baseline-Immutabilität erzwungen; Duplicate-Name-Rejektion; Diff-Berechnung korrekt; Preset-Scope-Gating (Minimal blockt document, Standard erlaubt document, Extended erlaubt global); Performance: Baseline-Erstellung < 5s bei 10k Items, Diff < 3s bei 10k Items |
| **Risiko** | MITTEL — Scope-Resolution-Komplexität und Performance bei Scale. |
| **Gate** | G8: Baseline Verified |

**Phase 2 Abschluss:** Alle 4 Domain-Services verifiziert. 81 Tests bestanden. Domain-Core bereit für Orchestrierung.

---

#### Phase 3 — Orchestration Integration (P1)

##### Schritt 9: ApplicationService + ALLE Domain-Services (ARCH-L1-004)

| Attribut | Wert |
|----------|------|
| **Strategie** | **Sandwich** — L3 Bottom-Up (Unit → Unit-Integration) + L2 Top-Down (System → Domain-Services) |
| **Abhängigkeiten** | ALLE Domain-Services (Schritte 1–8 ✅) |
| **L3-Status** | **L3 aktiv** — 13 Units (UNIT-AS-01..13) |
| **Verifizierte Interfaces** | 12 L2-intern (IF-AS-INT-001..012); 5 L3-intern; 8 L2-System-Integration; IF-L1-010..016, IF-L1-027 |
| **Testanzahl** | 30 L3-Unit + 5 L3-Int + 8 L2-Int = **43** |
| **Entry-Kriterien** | Schritte 1–8 bestanden; alle Domain-Services grün |

**Sandwich-Ansatz für ApplicationService:**

1. **Bottom-Up (L3):** Individuelle Unit-Tests zuerst (30 Tests), dann L3-Integration (5 Tests)
   - CycleDetector, ArtifactService, ArtifactTreeNode
   - RequirementService, ArchitectureService, TestService
   - ExportService, SearchService, SearchResult
   - TraceLinkService, BaselineFacade, WorkflowFacade, PresetPolicyService

2. **Top-Down (L2):** System-Integration gegen verifizierte Domain-Services (8 Tests)
   - AppSvc + WorkflowEngine (IF-L1-010)
   - AppSvc + BaselineService (IF-L1-011)
   - AppSvc + TraceabilityEngine (IF-L1-012)
   - AppSvc + PresetConfigEngine (IF-L1-013)
   - AppSvc + LlmAdapter (IF-L1-014)
   - AppSvc + AuditLog (IF-L1-016)
   - AppSvc + AuthAndTenancy (IF-L1-015, IF-L1-027)
   - AppSvc + PersistenceLayer (IF-L1-022, Tenant-Isolation)

| Exit-Kriterien | Alle 43 Tests grün; alle Use-Case-Methoden orchestrieren korrekt; Cycle-Detection funktioniert; Optimistic Locking verifiziert; CSV-Import behandelt 1000 Zeilen atomar; Audit-Entries für alle Schreib-Ops |
|---|---|
| **Risiko** | **KRITISCH** — ApplicationService ist der zentrale Orchestrator. 10 ausgehende L1-Schnittstellen. Failure blockiert Schritte 10 und 11. |
| **Mitigation** | StubApplicationService verfügbar für Downstream-Testing; L3-Unit-Tests isolieren individuelle Units; L2-Integrations-Tests verifizieren jede Schnittstelle unabhängig |
| **Gate** | G9: ApplicationService Verified — **MAJOR MILESTONE** |

**Phase 3 Abschluss:** Zentraler Orchestrator verifiziert. 43 Tests bestanden. Domain-Core vollständig assembliert.

---

#### Phase 4 — Interface Adapter Integration (P2)

##### Schritt 10: RestApiAdapter + ApplicationService + AuthAndTenancy + PresetConfigEngine (ARCH-L1-002)

| Attribut | Wert |
|----------|------|
| **Strategie** | Top-Down (abhängig von verifiziertem Domain-Core) |
| **Abhängigkeiten** | ApplicationService (Schritt 9 ✅), AuthAndTenancy (Schritt 2 ✅), PresetConfigEngine (Schritt 3 ✅) |
| **L3-Status** | Terminal at L2 (5 Module) |
| **Verifizierte Interfaces** | IF-RA-INT-001..006 (6 intern); IF-L1-003 (→ AppSvc); IF-L1-004 (→ Auth); IF-L1-005 (→ Preset); IF-L1-024 (→ Auth); IF-L1-029..031 (→ external) |
| **Testanzahl** | 12 Komp. + 6 Int. = **18** |
| **Entry-Kriterien** | Schritt 9 bestanden; Django REST Framework konfiguriert |
| **Exit-Kriterien** | Alle Endpunkte routbar; OpenAPI-Schema generiert; Request-Validierung funktional; Auth-Enforcement verifiziert; Preset-aware Field-Filtering korrekt; Error-Response-Format standardisiert; Pagination funktional |
| **Risiko** | MITTEL — gut definiertes Adapter-Pattern. |
| **Parallelism** | Kann parallel mit Schritt 11 laufen (beide dependieren von Schritt 9) |
| **Gate** | G10: REST Adapter Verified |

##### Schritt 11: McpServer + ApplicationService + AuthAndTenancy + PresetConfigEngine + AuditLog (ARCH-L1-003)

| Attribut | Wert |
|----------|------|
| **Strategie** | **Sandwich** — L3 Bottom-Up (Tool-Handler) + L2 Top-Down (Transport → Tools → AppSvc) |
| **Abhängigkeiten** | ApplicationService (Schritt 9 ✅), AuthAndTenancy (Schritt 2 ✅), PresetConfigEngine (Schritt 3 ✅), AuditLog (Schritt 4 ✅), WorkflowEngine (Schritt 7 ✅), TraceabilityEngine (Schritt 6 ✅) |
| **L3-Status** | **L3 aktiv** — 22 Units (UNIT-MCP-01..22) |
| **Verifizierte Interfaces** | IF-MC-INT-001..006 (6 intern); 2 L3-intern; 9 L2-System-Integration; IF-L1-006..008, IF-L1-021, IF-L1-025..026 |
| **Testanzahl** | 35 L3-Unit + 2 L3-Int + 9 L2-Int = **46** |
| **Entry-Kriterien** | Schritte 2, 3, 4, 6, 7, 9 bestanden |

**Sandwich-Ansatz für McpServer:**

1. **Bottom-Up (L3):** Individuelle Tool-Handler-Tests (35 Tests), dann L3-Integration (2 Tests)
   - Transport: stdio, HTTP+SSE, API-Key-Auth, Concurrent-Load
   - Dispatcher + ToolRegistry: JSON-RPC-Dispatch, RBAC-Filtering
   - 20 Tool-Handler: requirement.*, architecture.*, test.*, cross-cutting.*

2. **Top-Down (L2):** System-Integration (9 Tests)
   - Transport → RequirementTools (IF-MC-INT-002)
   - Transport → ArchitectureTools (IF-MC-INT-003)
   - Transport → TestTools (IF-MC-INT-004)
   - Transport → CrossCuttingTools (IF-MC-INT-005)
   - Alle Tools → Transport (IF-MC-INT-006)
   - McpServer + ApplicationService (IF-L1-006)
   - McpServer + AuthAndTenancy (IF-L1-007)
   - McpServer + PresetConfigEngine (IF-L1-008)
   - McpServer + AuditLog (IF-L1-021)

| Exit-Kriterien | Alle 46 Tests grün; alle 20 Tools dispatchen korrekt; stdio und HTTP+SSE Transports funktional; API-Key-Auth erzwungen; RBAC pro Tool verifiziert; Preset-basiertes Tool-Filtering korrekt; MCP-spezifische Audit-Entries erstellt; Concurrent-Load < 2s p95 bei 50 Clients |
|---|---|
| **Risiko** | HOCH — 22 L3-Units, duale Transport-Protokolle, komplexes RBAC. |
| **Parallelism** | Kann parallel mit Schritt 10 laufen |
| **Gate** | G11: MCP Server Verified |

**Phase 4 Abschluss:** Beide Interface-Adapter verifiziert. 64 Tests bestanden. System via REST und MCP zugreifbar.

---

#### Phase 5 — Presentation Integration (P2)

##### Schritt 12: ReactFrontend + RestApiAdapter (ARCH-L1-001)

| Attribut | Wert |
|----------|------|
| **Strategie** | Top-Down (abhängig von verifiziertem REST-Adapter) |
| **Abhängigkeiten** | RestApiAdapter (Schritt 10 ✅) |
| **L3-Status** | Terminal at L2 (8 Sub-Komponenten) |
| **Verifizierte Interfaces** | IF-RF-INT-001..003 (3 intern); IF-L1-001 (→ REST); IF-EXT-001 (→ Browser) |
| **Testanzahl** | 12 Komp. + 5 Int. = **17** |
| **Entry-Kriterien** | Schritt 10 bestanden; React-Build-Pipeline konfiguriert |
| **Exit-Kriterien** | Initiales Rendering < 2s; 401-Redirect funktional; Dashboard zeigt korrekte Daten; Editor-CRUD funktional; Artifact-Tree-Navigation funktional; Preset-Wechsel in UI reflektiert; i18n DE/EN-Switch; Terminologie-Profil-Labels korrekt; Optimistic Updates reconcilieren; Cache-Invalidation bei Server-seitigen Änderungen |
| **Risiko** | MITTEL — UI-Testing erfordert Browser-Automatisierung. |
| **Mitigation** | Playwright für E2E; Komponententests via Jest/React Testing Library; Mock-REST-API für isolierte UI-Tests |
| **Gate** | G12: Frontend Verified |

**Phase 5 Abschluss:** Vollständiges System assembliert. 17 Tests bestanden. Alle 12 Systeme integriert.

---

#### Phase 6 — Cross-Cutting & End-to-End

##### Phase 6a — Performance Tests

| Kategorie | Testanzahl | Scope | Entry-Kriterien |
|-----------|-----------|-------|----------------|
| Performance Tests | 15 | Alle Performance-SLAs inkl. BVA (0/1/10.001 Items) | Schritte 1–12 bestanden |

##### Phase 6b — Boundary Value Analysis (BVA)

| Kategorie | Testanzahl | Scope | Entry-Kriterien |
|-----------|-----------|-------|----------------|
| Boundary Value Analysis (BVA) | 19 | Alle Input-akzeptierenden Endpunkte (REST + MCP) | Schritte 1–12 bestanden |

##### Phase 6c — Security Tests

| Kategorie | Testanzahl | Scope | Entry-Kriterien |
|-----------|-----------|-------|----------------|
| Security Tests | 17 | Tenant-Isolation, RBAC, API-Key, Audit | Schritte 1–12 bestanden |

##### Phase 6d — Resilience & Edge Cases

| Kategorie | Testanzahl | Scope | Entry-Kriterien |
|-----------|-----------|-------|----------------|
| Edge Case & Resilience | 12 | Alle Systeme unter Fehlerbedingungen | Schritte 1–12 bestanden |

##### Cross-Cutting Gesamt

| Kategorie | Testanzahl |
|-----------|-----------|
| Performance | 15 |
| BVA | 19 |
| Security | 17 |
| Resilience | 12 |
| **Gesamt** | **63** |

##### End-to-End User Journeys (L3 System-Level)

| Journey-ID | User Journey | Systeme | Priorität |
|-----------|-------------|---------|-----------|
| E2E-01 | Engineer erstellt Requirement via REST | REST → Auth → AppSvc → WF → Persist → Audit | P0 |
| E2E-02 | AI-Agent decomposiert Requirement via MCP | MCP → Auth → AppSvc → LLM → Persist → WF → Audit | P0 |
| E2E-03 | Engineer erstellt Baseline via UI | UI → REST → Auth → AppSvc → Baseline → Trace → Persist → Audit | P1 |
| E2E-04 | Engineer transitiert Workflow via UI | UI → REST → Auth → AppSvc → WF → Persist → Audit | P1 |
| E2E-05 | AI-Agent queried Traceability via MCP | MCP → Auth → AppSvc → Trace → Persist | P1 |
| E2E-06 | Engineer sucht und exportiert via UI | UI → REST → Auth → AppSvc → Search/Export → Persist | P2 |
| E2E-07 | Preset-Wechsel: Standard → Minimal | UI → REST → AppSvc → Preset → Persist | P2 |

**E2E-Umgebung:** Docker Compose (3 Container: Backend, Frontend, PostgreSQL) + Playwright Browser-Automatisierung.

---

## 4. Testumgebungs-Strategie

### 4.1 Umgebungen pro Phase

| Umgebung | Phase | Infrastruktur | Teardown |
|----------|-------|---------------|----------|
| **Unit** | Alle Phasen | pytest-Fixtures, Mocks, In-Memory-DB | Pro-Test-Teardown |
| **Integration** | Phase 1–4 | PostgreSQL-Test-Container, Django-Test-Client | Pro-Suite-Teardown |
| **System** | Phase 3–5 | Docker Compose (3 Container) | Pro-Phase-Teardown |
| **Acceptance** | Phase 6 | Docker Compose + Playwright Browser | Pro-Journey-Teardown |
| **Performance** | Phase 2, 6 | PostgreSQL mit 10k+ Items geladen | Pro-Test-Teardown |
| **Resilience** | Phase 6 | Chaos Engineering (DB-Kill, Network-Partition) | Pro-Test-Teardown |

### 4.2 Mock/Stub-Strategie für externe Abhängigkeiten

| Externe Abhängigkeit | Mock/Stub | Konfiguration | Verhalten |
|---------------------|-----------|---------------|-----------|
| **LLM-Provider** (Anthropic/OpenAI/Ollama) | `MockLlmProvider` | `.env`: `LLM_PROVIDER=mock` | Vordefinierte LlmResult; konfigurierbarer Delay (0–30s); konfigurierbare Fehlerrate (0–100%); Token-Usage-Simulation |
| **GitHub API** (v1 Should-Have) | `MockGitHubApi` | `.env`: `GITHUB_MOCK=true` | Issue/PR-Erstellung simuliert; Webhook-Events generiert; Rate-Limiting simulierbar |
| **Webhook-Ziel-URLs** | `MockWebhookReceiver` | Test-Fixture | Empfängt POST-Payloads; liefert konfigurierbaren Status (200/500/Timeout); zeichnet alle Received-Payloads auf |
| **SMTP-Server** (Benachrichtigungen) | `MockSmtpServer` | Test-Fixture | E-Mails werden aufgezeichnet statt gesendet; Abrufbar über Test-API |

### 4.3 Datenbank-Test-Fixtures

| Fixture | Beschreibung | Entity-Anzahl | Verwendung |
|---------|-------------|---------------|------------|
| `empty_db` | Leere PostgreSQL-Test-DB | 0 | Unit-Tests, Migration-Tests |
| `single_tenant` | 1 Tenant, 1 User, 1 Workspace (Standard) | ~10 | Komponententests |
| `multi_tenant` | 2 Tenants, je 1 Workspace mit Items | ~50 | Tenant-Isolation-Tests |
| `preset_matrix` | 3 Workspaces: Minimal, Standard, Extended | ~30 | Preset-Verhaltens-Tests |
| `hierarchy_deep` | 500 Artefakte in 10-level Hierarchie | 500 | Cycle-Detection, Tree-Query |
| `linked_workspace` | 100 Req, 50 Arch, 30 Test, 200 TraceLinks | ~380 | Traceability-Tests |
| `baseline_pair` | 2 Baselines gleichen Scopes mit Diff | ~200 | Baseline-Diff-Tests |
| `performance_scale` | 10.000 Items, 50.000 Links, 100.000 Audit | ~160.000 | Performance-Tests |

### 4.4 Test-Isolation — Tenant-Separation in Tests

**Prinzip:** Jeder Integrationstest der Tenant-Isolation testet, verwendet die `multi_tenant`-Fixture mit mindestens zwei Tenants.

**Muster:**
```python
@pytest.fixture
def multi_tenant(db):
    tenant_a = Tenant.objects.create(name="Tenant A")
    tenant_b = Tenant.objects.create(name="Tenant B")
    # ... Items für beide Tenants erstellen
    return tenant_a, tenant_b

def test_cross_tenant_access_blocked(multi_tenant):
    tenant_a, tenant_b = multi_tenant
    entity_b = create_entity(tenant=tenant_b)
    
    # Als Tenant A authentifizieren
    set_tenant_context(tenant_a)
    
    # Entity von Tenant B ist nicht sichtbar
    assert Entity.objects.filter(id=entity_b.id).count() == 0
```

**Invariant:** Kein Test darf jemals Daten von Tenant B sehen wenn Context auf Tenant A gesetzt ist.

---

## 5. V&V-Plan

### 5.1 V&V-Meilensteine

| Meilenstein | Name | Gate | Kriterium | Entscheidungs-Autorität |
|-------------|------|------|-----------|------------------------|
| **M1** | Infrastructure Foundation | G1–G4 | 70 Tests grün; Tenant-Isolation 100%; Preset-Matrix vollständig | se-verifier |
| **M2** | Domain Core Assembly | G5–G8 | 81 Tests grün; Graph-Queries < 200ms; Workflow-Preset-Matrix grün | se-verifier |
| **M3** | Orchestrator Verified | G9 | 43 Tests grün; alle 10 ausgehenden L1-IFs verifiziert | se-verifier |
| **M4** | Interface Adapters Green | G10–G11 | 64 Tests grün; OpenAPI-Spec vollständig; alle 20 MCP-Tools funktional | se-verifier |
| **M5** | Full System Assembled | G12 | 17 Tests grün; UI rendert korrekt; i18n funktional | se-verifier |
| **M6** | Cross-Cutting Complete | — | 63 Tests grün; alle Security/Performance/BVA/Edge-Szenarien grün | se-verifier |
| **M7** | E2E Validation | — | 7 User Journeys grün; Performance-SLAs erfüllt | se-validator |
| **M8** | V&V Sign-Off | — | V&V Gesamtbericht approved; alle 345 Tests grün | se-integration-and-test-manager |

### 5.2 Entry/Exit-Kriterien pro Phase

| Phase | Entry-Kriterien | Exit-Kriterien |
|-------|----------------|----------------|
| **Phase 1** (Infrastructure) | PostgreSQL-Test-Container verfügbar; Django-Test-Framework konfiguriert | 70/70 Tests grün; Tenant-Isolation 100%; Migrations-Idempotenz bestätigt |
| **Phase 2** (Domain) | Phase 1 Gates G1–G4 bestanden; Domain-Service-Fixtures bereit | 81/81 Tests grün; Performance-SLAs erfüllt (Trace < 200ms, WF < 10ms) |
| **Phase 3** (Orchestration) | Phase 2 Gates G5–G8 bestanden; alle Domain-Services verfügbar | 43/43 Tests grün; alle 10 ausgehenden L1-IFs verifiziert |
| **Phase 4** (Adapters) | Phase 3 Gate G9 bestanden; DRF + MCP-Framework konfiguriert | 64/64 Tests grün; OpenAPI-Spec valide; alle 20 MCP-Tools dispatchen korrekt |
| **Phase 5** (Presentation) | Phase 4 Gates G10–G11 bestanden; React-Build-Pipeline bereit | 17/17 Tests grün; UI rendert in < 2s; i18n DE/EN verifiziert |
| **Phase 6** (Cross-Cutting) | Alle 12 Systeme integriert (Gates G1–G12 bestanden) | 63/63 Cross-Cutting Tests grün; keine Datenkorruption unter Fehlerbedingungen |
| **Phase 7** (E2E) | Docker Compose Umgebung läuft; Playwright konfiguriert | 7/7 User Journeys grün; Performance-SLAs E2E erfüllt |

### 5.3 Quality-Gates — Eskalationsprotokoll

```
Test-Fehler bei Schritt N:
├── Komponenten/Unit-Test-Fehler → Fix in Komponente; Schritt N erneut ausführen
├── Integrationstest-Fehler → Interface-Contract-Verletzung
│   ├── Root-Cause in Caller → Fix Caller; Schritt N erneut ausführen
│   └── Root-Cause in Callee → Fix Callee; Callee-Schritt + Schritt N erneut
├── Performance-SLA-Fehler → Architektur-Review
│   ├── Query-Optimierung nötig → Delegate an se-architect
│   └── Index/Schema-Problem → Fix in PersistenceLayer; Schritt 1 + Schritt N erneut
├── Security-Test-Fehler → KRITISCH
│   ├── Tenant-Isolation-Leak → Sofortiger Stopp; Fix erforderlich; alle abhängigen Steps erneut
│   └── RBAC-Bypass → Sofortiger Stopp; Fix erforderlich
└── Blocker (nicht in Phase fixbar) → Eskalation an orchestrator
```

**Keine Silent Failures:** Ein blockierter Integrationsschritt stoppt die Kette. Kein Schritt darf übersprungen werden.

### 5.4 Risiko-Bewertung

| Risiko-ID | Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|-----------|--------|-------------------|------------|------------|
| R-01 | PersistenceLayer-Schema-Migration fehlschlägt | Niedrig | **Kritisch** — blockiert alle | Frühes Migration-Testing; Rollback-Prozedur; separate Migration-Test-Suite |
| R-02 | Tenant-Isolation-Leak in AuthAndTenancy | Mittel | **Kritisch** — Sicherheitslücke | Cross-Tenant-Tests obligatorisch; DB-Constraint-Verifikation; Code-Review-Fokus |
| R-03 | ApplicationService-Orchestrierungskomplexität | Hoch | **Hoch** — blockiert Schritte 10, 11 | Sandwich-Ansatz; StubApplicationService für Downstream; L3-Unit-Isolation |
| R-04 | MCP-Dual-Transport-Protokoll-Probleme | Mittel | **Hoch** — blockiert MCP-Interface | Separate Transport-Tests; Loopback-Testing; Protokoll-Conformance-Suite |
| R-05 | TraceabilityEngine-Graph-Query-Performance | Mittel | **Mittel** — SLA-Verletzung | Frühes Performance-Testing bei 10k Items; Recursive-CTE-Optimierung |
| R-06 | Preset × Feature-Interaktions-Matrix-Explosion | Niedrig | **Mittel** — unvollständige Coverage | Systematische Matrix-Test-Generierung; Äquivalenzklassen-Reduktion |
| R-07 | ReactFrontend-Optimistic-Update-Race-Conditions | Mittel | **Mittel** — UI-Inkonsistenz | Concurrent-Update-Tests; Cache-Invalidation-Verifikation |
| R-08 | LLM-Provider-Timeout-kaskadierende Fehler | Mittel | **Mittel** — degradierte UX | MockLlmProvider mit konfigurierbarem Delay; Graceful-Degradation-Tests |

---

## 6. Parallelität & Scheduling

### 6.1 Parallele Ausführungsmöglichkeiten

```
Timeline (konzeptionell):

Schritt 1: PersistenceLayer ─────────────────────────────────────────
           │
           ├── Schritt 2: AuthAndTenancy ─────────────────────────────
           ├── Schritt 3: PresetConfigEngine ─────────────────────────
           └── Schritt 4: AuditLog ───────────────────────────────────
                    │              │              │
                    │              │              ├── Schritt 5: LlmAdapter ──
                    │              │              │
                    │              └── Schritt 6: TraceabilityEngine ──
                    │                            │
                    └── Schritt 7: WorkflowEngine ┘
                              │
                              ├── Schritt 8: BaselineService (braucht Schritt 6) ──
                              │
                              └── Schritt 9: ApplicationService ──────────────────
                                          │
                                          ├── Schritt 10: RestApiAdapter ─────────
                                          └── Schritt 11: McpServer ──────────────
                                                        │
                                                        └── Schritt 12: ReactFrontend
                                                                      │
                                                        Cross-Cutting + E2E
```

### 6.2 Maximale Parallelität

| Welle | Schritte | Parallelisierbar | Blockiert durch |
|-------|----------|-----------------|----------------|
| **Welle 1** | Schritt 1 | 1 Schritt | — |
| **Welle 2** | Schritte 2, 3, 4 | 3 Schritte parallel | Schritt 1 |
| **Welle 3** | Schritte 5, 6, 7 | 3 Schritte parallel | Schritte 1–4 |
| **Welle 4** | Schritt 8 | 1 Schritt | Schritt 6 |
| **Welle 5** | Schritt 9 | 1 Schritt | Schritte 1–8 |
| **Welle 6** | Schritte 10, 11 | 2 Schritte parallel | Schritt 9 |
| **Welle 7** | Schritt 12 | 1 Schritt | Schritt 10 |
| **Welle 8** | Cross-Cutting + E2E | 1 Welle | Schritte 1–12 |

**Minimale sequentielle Tiefe:** 8 Wellen
**Maximale parallele Schritte pro Welle:** 3 (Wellen 2 und 3)

---

## 7. Delegation-Protokoll

### 7.1 Agent-Zuordnung pro Phase

| Phase | Verantwortlicher Agent | Aktion | Input | Erwarteter Output |
|-------|----------------------|--------|-------|------------------|
| Phase 1 (Schritte 1–4) | se-verifier | Jedes Infrastruktur-System verifizieren | L2-Architektur, Test-Cases | Verifikationsbericht pro System |
| Phase 2 (Schritte 5–8) | se-verifier | Jeden Domain-Service verifizieren | L2-Architektur, Test-Cases | Verifikationsbericht pro System |
| Phase 3 (Schritt 9) | se-verifier | ApplicationService verifizieren | L2+L3-Architektur, Test-Cases | Verifikationsbericht (L3 + L2) |
| Phase 4 (Schritte 10–11) | se-verifier | Interface-Adapter verifizieren | L2+L3-Architektur, Test-Cases | Verifikationsbericht pro Adapter |
| Phase 5 (Schritt 12) | se-verifier | ReactFrontend verifizieren | L2-Architektur, Test-Cases | Verifikationsbericht |
| Phase 6 (Cross-Cutting) | se-verifier | Cross-Cutting Concerns verifizieren | BVA/Edge/Security/Perf-Test-Definitionen | Cross-Cutting-Verifikationsbericht |
| Phase 7 (E2E) | se-validator | User Journeys validieren | L1-Spec, Stakeholder-Needs | Validierungsbericht |
| Gesamt | se-integration-and-test-manager | Alle Phasen orchestrieren | Dieses Dokument | V&V Gesamtbericht |

### 7.2 Eskalationspfade

| Situation | Eskalationsziel | Aktion |
|-----------|----------------|--------|
| Test-Fehler in Komponente | se-verifier → developer | Komponente fixen; neu verifizieren |
| Interface-Contract-Verletzung | se-verifier → se-architect | Interface-Contract reviewen |
| Performance-SLA-Fehler | se-verifier → se-architect | Architektur-Optimierung |
| Security-Fehler (Tenant-Leak) | se-verifier → orchestrator | Sofortiger Stopp; alle abhängigen Steps blockiert |
| Integrationsschritt blockiert | se-integration-and-test-manager → orchestrator | Koordinationsentscheidung |
| Unklare Stakeholder-Need nach Validierungs-Fehler | se-validator → se-requirements | Anforderungsklärung |
| Test-Definitions-Lücke | se-integration-and-test-manager → se-test-engineer | Fehlende Tests definieren |

---

## 8. Traceability — Integration zu Test-Strategie

### 8.1 Integrationsschritt → Test-Strategie-Mapping

| Integrationsschritt | Test-Strategie-Abschnitt | Test-IDs | Anzahl |
|--------------------|------------------------|---------|--------|
| Schritt 1: PersistenceLayer | §2.1 | TC-Persist-001..014, IT-Persist-01..05 | 19 |
| Schritt 2: AuthAndTenancy | §2.2 | TC-Auth-001..021, IT-Auth-01..05 | 26 |
| Schritt 3: PresetConfigEngine | §2.3 | TC-Preset-001..017 | 17 |
| Schritt 4: AuditLog | §2.4 | TC-Audit-001..008 | 8 |
| Schritt 5: LlmAdapter | §2.5 | TC-Llm-001..012, IT-Llm-01..05 | 19 |
| Schritt 6: TraceabilityEngine | §2.6 | TC-Trace-001..020, TC-TE-Cycle-001/002, IT-Trace-01..05 | 27 |
| Schritt 7: WorkflowEngine | §2.7 | TC-WF-001..015, IT-WF-01..03 | 18 |
| Schritt 8: BaselineService | §2.8 | TC-BS-001..014, IT-BS-01..03 | 17 |
| Schritt 9: ApplicationService | §3.1 | TC-AS-001..030, IT-AS-01..05, IT-AppSvc-L2-01..08 | 43 |
| Schritt 10: RestApiAdapter | §2.10 | TC-Rest-001..012, IT-Rest-01..06 | 18 |
| Schritt 11: McpServer | §3.2 | TC-MCP-001..035, IT-MCP-01..02, IT-Mcp-L2-01..09 | 46 |
| Schritt 12: ReactFrontend | §2.9 | TC-React-001..012, IT-React-01..05 | 17 |
| Cross-Cutting | §5.4, §5.5, §5.7, §6, §7 | TC-BVA-001..019, TC-EDGE-001..012, TC-SEC-001..017, TC-PERF-BVA-001..003, TC-PERF-001..012 | 63 |
| **Gesamt** | | | **338** |

### 8.2 Interface-Coverage pro Integrationsschritt

| Schritt | L1-IFs verifiziert | L2-IFs verifiziert | L3-IFs verifiziert |
|---------|-------------------|-------------------|-------------------|
| 1 | IF-L1-022 (partiell) | IF-PL-INT-001..005 | — |
| 2 | IF-L1-022, IF-L1-027 (partiell) | INT-L2-A-001..005 | — |
| 3 | IF-L1-022 (partiell) | — | — |
| 4 | IF-L1-022 (partiell) | — | — |
| 5 | IF-L1-021 | 5 L2-intern | — |
| 6 | IF-L1-022 | IF-TE-INT-001..003 | — |
| 7 | IF-L1-017, IF-L1-018, IF-L1-022 | IF-WE-INT-001..003 | — |
| 8 | IF-L1-019, IF-L1-020, IF-L1-022 | IF-BL-INT-001..003 | — |
| 9 | IF-L1-010..016, IF-L1-027 | IF-AS-INT-001..012 | 5 L3-intern |
| 10 | IF-L1-003..005, IF-L1-024, IF-L1-029..031 | IF-RA-INT-001..006 | — |
| 11 | IF-L1-006..008, IF-L1-021, IF-L1-025..026 | IF-MC-INT-001..006 | 2 L3-intern |
| 12 | IF-L1-001 | IF-RF-INT-001..003 | — |
| **Gesamt** | **31/31 (100%)** | **60/60 (100%)** | **7/7 (100%)** |

---

## 9. Integrationsplan — JSON-Repräsentation

```json
{
  "integration_plan_id": "INT-001",
  "strategy": "Bottom-Up with Sandwich Elements",
  "strategy_rationale": "12 L2-Systeme mit klarer 5-Layer-Architektur. 10 Leaf-Systeme integrieren natürlich Bottom-Up. 2 Continue-Systeme (ApplicationService L3, McpServer L3) nutzen Sandwich-Ansatz. PersistenceLayer ist universelle Foundation (10/12 Systeme dependieren davon). Kritischer Pfad: Persist → Auth → WF → AppSvc → McpServer.",
  "integration_levels": [
    {
      "level": 1,
      "name": "Infrastructure Foundation",
      "phase": "Phase 1",
      "steps": [
        {"step": 1, "system": "PersistenceLayerSystem", "arch_id": "ARCH-L1-010", "test_count": 19, "gate": "G1", "risk": "HIGH"},
        {"step": 2, "system": "AuthAndTenancySystem", "arch_id": "ARCH-L1-011", "test_count": 26, "gate": "G2", "risk": "HIGH"},
        {"step": 3, "system": "PresetConfigEngineSystem", "arch_id": "ARCH-L1-008", "test_count": 17, "gate": "G3", "risk": "MEDIUM", "parallel_with": "Step 2"},
        {"step": 4, "system": "AuditLogSystem", "arch_id": "ARCH-L1-012", "test_count": 8, "gate": "G4", "risk": "LOW", "parallel_with": "Steps 2,3"}
      ]
    },
    {
      "level": 2,
      "name": "Domain Service Assembly",
      "phase": "Phase 2",
      "steps": [
        {"step": 5, "system": "LlmAdapterSystem", "arch_id": "ARCH-L1-009", "test_count": 19, "gate": "G5", "risk": "MEDIUM"},
        {"step": 6, "system": "TraceabilityEngineSystem", "arch_id": "ARCH-L1-007", "test_count": 27, "gate": "G6", "risk": "MEDIUM", "parallel_with": "Step 5"},
        {"step": 7, "system": "WorkflowEngineSystem", "arch_id": "ARCH-L1-005", "test_count": 18, "gate": "G7", "risk": "MEDIUM"},
        {"step": 8, "system": "BaselineServiceSystem", "arch_id": "ARCH-L1-006", "test_count": 17, "gate": "G8", "risk": "MEDIUM"}
      ]
    },
    {
      "level": 3,
      "name": "Orchestration Integration",
      "phase": "Phase 3",
      "steps": [
        {"step": 9, "system": "ApplicationServiceSystem", "arch_id": "ARCH-L1-004", "strategy": "Sandwich", "test_count": 43, "gate": "G9", "risk": "CRITICAL", "milestone": "M3"}
      ]
    },
    {
      "level": 4,
      "name": "Interface Adapter Integration",
      "phase": "Phase 4",
      "steps": [
        {"step": 10, "system": "RestApiAdapterSystem", "arch_id": "ARCH-L1-002", "test_count": 18, "gate": "G10", "risk": "MEDIUM", "parallel_with": "Step 11"},
        {"step": 11, "system": "McpServerSystem", "arch_id": "ARCH-L1-003", "strategy": "Sandwich", "test_count": 46, "gate": "G11", "risk": "HIGH"}
      ]
    },
    {
      "level": 5,
      "name": "Presentation Integration",
      "phase": "Phase 5",
      "steps": [
        {"step": 12, "system": "ReactFrontendSystem", "arch_id": "ARCH-L1-001", "test_count": 17, "gate": "G12", "risk": "MEDIUM"}
      ]
    },
    {
      "level": 6,
      "name": "Cross-Cutting & E2E Validation",
      "phase": "Phase 6-7",
      "steps": [
        {"step": "CC-1", "test_type": "Performance Tests", "test_count": 15},
        {"step": "CC-2", "test_type": "Boundary Value Analysis", "test_count": 19},
        {"step": "CC-3", "test_type": "Security Tests", "test_count": 17},
        {"step": "CC-4", "test_type": "Edge Case & Resilience", "test_count": 12},
        {"step": "E2E", "test_type": "End-to-End User Journeys", "test_count": 7}
      ]
    }
  ],
  "critical_path": ["Step 1", "Step 2", "Step 7", "Step 9", "Step 11"],
  "total_test_count": {
    "component_unit": 214,
    "integration": 61,
    "cross_cutting": 63,
    "e2e": 7,
    "grand_total": 345
  }
}
```

---

## 10. V&V Gesamtbericht — Template

Nach Abschluss aller V&V-Aktivitäten folgt der Abschlussbericht dieser Struktur:

```markdown
# V&V Gesamtbericht — [Datum]

## Integrationsstrategie
Bottom-Up mit Sandwich-Elementen. 12 Schritte über 7 Phasen.
Kritischer Pfad: Persist → Auth → WF → AppSvc → McpServer.

## Durchlaufene Integrations-Level
| Level | Phase | Status | Systeme | Verifikationsrate |
|-------|-------|--------|---------|------------------|
| Infrastructure (L0) | Phase 1 | ✅/❌ | 4/4 | X/65 |
| Domain Services (L1) | Phase 2 | ✅/❌ | 4/4 | X/79 |
| Orchestration (L2) | Phase 3 | ✅/❌ | 1/1 | X/43 |
| Interface Adapters (L3) | Phase 4 | ✅/❌ | 2/2 | X/64 |
| Presentation (L4) | Phase 5 | ✅/❌ | 1/1 | X/17 |
| Cross-Cutting | Phase 6 | ✅/❌ | Alle | X/63 |
| E2E Validation | Phase 7 | ✅/❌ | Alle | X/7 |

## Offene Issues
| ID | Phase | Beschreibung | Schwere | Status |
|----|-------|-------------|---------|--------|

## Fazit
[Gesamtbewertung, Empfehlungen für nächste Iteration]
```

---

*Erstellt durch se-test-engineer-Agent | ReqFlow SE-Kaskade V&V | 2026-06-20*
*Branch: refactor/se-structure*
*Handoff: HOFF-20260620-006*
*Bereit für Integrationsausführung — Phase 1 kann starten*
