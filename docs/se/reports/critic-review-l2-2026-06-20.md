# SE-Critic L2 Audit Report

> Datum: 2026-06-20
> Scope: 12 L2 subsystems, 136 REQ-L2, 55 components
> Quellen: L1 Requirements, L1 Architecture, Interface Registry, 12 L2 Requirements, 12 L2 Architectures

---

## Summary

| Dimension | Status | Issues |
|-----------|--------|--------|
| REQ-L1 Coverage | **PASS** | 0 |
| Interface Compatibility | **FAIL** | 4 |
| Cross-System Consistency | **FAIL** | 3 |
| Naming Conventions | **FAIL** | 2 |
| Component Quality | **FAIL** | 2 |
| Arch-Req Alignment | **FAIL** | 4 |

**Gesamt: 1 PASS, 5 FAIL — 15 Issues (3 Critical, 10 Major, 2 Minor)**

---

## Issues Found

### CRITICAL (must fix)

#### C-01: McpServer-AuditLog-Pfad widerspricht L1-Architektur (Dual-Path-Bug)
- **Beschreibung:** REQ-L2-MC-012 und die McpServer-Architektur modellieren einen direkten Aufruf `McpServer → AuditLog` (IF-MC-EXT-OUT-005 / IF-L1-09). Die L1-Architektur (ADR-01, Sequenzdiagramm §4.1) definiert jedoch eindeutig, dass MCP-Schreiboperationen durch den `ApplicationService` orchestriert werden und dieser zentral den AuditLog befüllt (`AppService → AuditLog`). Es entstehen zwei parallele Audit-Pfade, die die Einheitlichkeit des Audit-Trails gefährden und die Konsistenzgarantie von ADR-01 untergraben.
- **Betroffene Systeme:** McpServerSystem, ApplicationServiceSystem, AuditLogSystem, L1-Architektur
- **Empfohlene Lösung:** McpServer DARF NICHT direkt AuditLog aufrufen. MCP-spezifische Audit-Felder (`client_name`, `api_key_hash`) müssen über den Auth-Kontext (von `AuthAndTenancy` an `ApplicationService`) propagiert und von `ApplicationService` in den `log_write()`-Aufruf eingebettet werden. REQ-L2-MC-012 und McpServer-Architektur §2/§3 sind entsprechend zu korrigieren; IF-L1-09 ist aus der Interface-Registry zu entfernen.

#### C-02: Interface-Registry unterdrückt L2-interne Schnittstellen dreier Systeme
- **Beschreibung:** Die Interface-Registry §3.10 behauptet fälschlicherweise, dass `TraceabilityEngine`, `PresetConfigEngine` und `AuditLog` **keine** L2-internen Schnittstellen besitzen (`0` pro System). Tatsächlich definieren deren Architekturen: TraceabilityEngine `IF-TE-INT-001..003`, PresetConfigEngine `IF-PC-INT-001..002`, AuditLog `IF-AL-INT-001`. Die Registry ist damit als zentrale Konsistenzquelle unbrauchbar.
- **Betroffene Systeme:** TraceabilityEngineSystem, PresetConfigEngineSystem, AuditLogSystem, Interface Registry
- **Empfohlene Lösung:** Interface-Registry §3.10 korrigieren und die drei fehlenden Schnittstellengruppen gemäß Architektur-Dokumenten einfügen. Gesamtzahl L2-interner Schnittstellen korrekt auf **60** hochsetzen (statt 57).

#### C-03: ApplicationService-Anforderungen referenzieren nicht-existierende Schnittstelle `IF-AS-IN-04`
- **Beschreibung:** In den Externen Schnittstellen von `ApplicationService` sind nur `IF-AS-IN-01..03` definiert. REQ-L2-AS-007 („Export with Terminology Profile Metadata“) und REQ-L2-AS-020 („Preset Policy Enforcement“) listen jedoch fälschlicherweise `Incoming: IF-AS-IN-04` auf. Zudem ist die Richtung falsch: Beide Anforderungen konsultieren die `PresetConfigEngine`, was eine **ausgehende** Schnittstelle (`IF-AS-OUT-04`) ist, nicht eingehend.
- **Betroffene Systeme:** ApplicationServiceSystem
- **Empfohlene Lösung:** In REQ-L2-AS-007 und REQ-L2-AS-020: `IF-AS-IN-04` durch `IF-AS-OUT-04` ersetzen und Richtung auf `Outgoing` korrigieren.

#### C-04: L3-Artefakte existieren trotz LEAF-Terminierung (Phase 3)
- **Beschreibung:** Phase 3 hat alle 12 Systeme als `LEAF` deklariert. Dennoch existieren physische L3-Dateien für zwei Systeme: `ApplicationServiceSystem/L3/ApplicationServiceComponent/` und `McpServerSystem/L3/McpServerComponent/`. Diese veralteten Artefakte erzeugen Verwirrung über den aktuellen Zerlegungsstand und widersprechen der `decomposition_status: terminal`-Entscheidung.
- **Betroffene Systeme:** ApplicationServiceSystem, McpServerSystem
- **Empfohlene Lösung:** L3-Verzeichnisse und alle darin enthaltenen `_Requirements.md`- und `_Architecture.md`-Dateien löschen. Designation-Header in L2-Requirements anpassen (siehe M-05).

### MAJOR (should fix)

#### M-01: Systematische Interface-ID-Inkonsistenz zwischen L2-Requirements und L2-Architektur
- **Beschreibung:** Alle 12 Systeme verwenden in den Requirements 2-stellige IDs ohne Richtungs-Marker (z.B. `IF-AS-IN-01`), während die Architekturen 3-stellige IDs mit `EXT`-Präfix verwenden (z.B. `IF-AS-EXT-IN-001`). Diese systematische Divergenz erschwert die automatisierte Traceability zwischen Requirements und Architektur erheblich.
- **Betroffene Systeme:** Alle 12 Systeme
- **Empfohlene Lösung:** Vereinheitlichung auf das Architektur-Schema (`IF-<SYS>-EXT-IN-NNN` / `IF-<SYS>-EXT-OUT-NNN` / `IF-<SYS>-INT-NNN`). L2-Requirements sind anzupassen.

#### M-02: `ReactFrontend → PresetConfigEngine` (IF-L1-02) fälschlich als direkte L1-Schnittstelle modelliert
- **Beschreibung:** `ReactFrontend` ist ein Browser-Client und kann ausschließlich via HTTP mit dem Backend kommunizieren. Ein direkter L1-System-zu-System-Kanal `ReactFrontend → PresetConfigEngine` existiert nicht; die Kommunikation läuft über `ReactFrontend → RestApiAdapter → PresetConfigEngine`. Die Interface-Registry modelliert dies dennoch als direkte Schnittstelle `IF-L1-02` mit dem widersprüchlichen Typ `In-Process (via REST)`.
- **Betroffene Systeme:** ReactFrontendSystem, RestApiAdapterSystem, PresetConfigEngineSystem, Interface Registry
- **Empfohlene Lösung:** IF-L1-02 entweder als indirekte Schnittstelle markieren (z.B. `ReactFrontend → RestApiAdapter → PresetConfigEngine`) oder aus der L1-Inter-System-Schnittstellen-Tabelle entfernen und stattdessen unter den REST-Endpunkt-Kategorien aufführen.

#### M-03: ApplicationService-Architektur fehlt `TraceLink-CRUD`-Verbindung zur TraceabilityEngine
- **Beschreibung:** REQ-L2-AS-010 fordert: „TraceLink-Erstellung, -Query und -Löschung als Orchestrierung über die TraceabilityEngine“. Die TraceabilityEngine-Architektur erwartet entsprechend `IF-TE-EXT-IN-003` (TraceLink-CRUD von ApplicationService). Die ApplicationService-Architektur zeigt jedoch `COMP-AS-005 TraceLinkService` ausschließlich mit Direktverbindung zur `PersistenceLayer` (`IF-AS-EXT-OUT-007`), nicht zur `TraceabilityEngine`. Die Interface-Registry listet zudem `TraceLink-CRUD` unter `IF-L1-12` (AppService → TraceabilityEngine), was die Architektur widerspricht.
- **Betroffene Systeme:** ApplicationServiceSystem, TraceabilityEngineSystem
- **Empfohlene Lösung:** ApplicationService-Architektur §3 um externe Schnittstelle `COMP-AS-005 → TraceabilityEngine` (z.B. `IF-AS-EXT-OUT-008`) ergänzen. Interne Logik von `TraceLinkService` muss `TraceabilityEngine` orchestrieren statt direkt auf die Datenbank zuzugreifen.

#### M-04: Designation-Inkonsistenzen in L2-Requirements-Headern
- **Beschreibung:** Die L2-Requirements verwenden uneinheitliche Designations: `subsystem (Leaf-AE)`, `system (Leaf-AE)`, `component (terminal)`, `subsystem (L3-zerlegt — 13 Units)`, `system (intermediate — L3-Zerlegung möglich)`. Besonders `ApplicationService`, `BaselineService` und `McpServer` behaupten noch L3-Zerlegung, obwohl Phase 3 terminal entschieden hat.
- **Betroffene Systeme:** Alle 12 Systeme (primär AS, BL, MC)
- **Empfohlene Lösung:** Alle 12 L2-Requirements-Header auf einheitliche Designation `component (terminal — keine L3-Zerlegung)` oder `subsystem (LEAF — keine L3-Zerlegung)` standardisieren.

#### M-05: WorkflowEngine-Architektur referenziert nicht-existierende REQ-L2-WE-012
- **Beschreibung:** ADR-WE-02 in der WorkflowEngine-Architektur zitiert REQ-L2-WE-012 („definiert den Adapter als 'pure translation layer'“). Das WorkflowEngine-Requirements-Dokument enthält jedoch nur REQ-L2-WE-001..008. Die Referenz ist vermutlich eine Kopie aus der RestApiAdapter-Architektur (wo REQ-L2-RA-012 existiert).
- **Betroffene Systeme:** WorkflowEngineSystem
- **Empfohlene Lösung:** ADR-WE-02 korrigieren: REQ-L2-WE-012 entfernen; stattdessen auf REQ-L2-WE-001 (Transition Validation) oder REQ-L2-WE-003 (WorkflowState History) verweisen, die die L2-Terminierung begründen.

#### M-06: BaselineService-Architektur-Diagramm fehlt Rückflüsse zu ApplicationService
- **Beschreibung:** Das Mermaid-Diagramm in der BaselineService-Architektur zeigt `ApplicationService → SnapshotBuilder` und `ApplicationService → DiffEngine`, aber keine Pfeile für die Rückgabe von Baseline-Entitäten oder Diff-Ergebnissen. Die Requirements definieren dafür explizit `IF-BL-OUT-01` und `IF-BL-OUT-02`.
- **Betroffene Systeme:** BaselineServiceSystem
- **Empfohlene Lösung:** Diagramm um Rückflüsse `SnapshotBuilder → ApplicationService` und `DiffEngine → ApplicationService` ergänzen.

#### M-07: AuthAndTenancy-Architektur-Diagramm fehlt WorkflowEngine-Verbindung
- **Beschreibung:** Die externe Schnittstelle `IF-AT-EXT-OUT-002` (Rollen-Check-Ergebnis an WorkflowEngine) ist in der Architektur-Tabelle definiert, erscheint jedoch nicht im Mermaid-Diagramm.
- **Betroffene Systeme:** AuthAndTenancySystem
- **Empfohlene Lösung:** Mermaid-Diagramm um Pfeil `C002 → WorkflowEngine` ergänzen.

#### M-08: L1-Architektur §5 fehlt `TraceLink-CRUD` für AppService → TraceabilityEngine
- **Beschreibung:** Die Schnittstellen-Übersicht in L1-Architektur §5 listet für `ApplicationService → TraceabilityEngine` nur `query()` und `coverage()`. Die Interface-Registry und die TE-Anforderungen verlangen jedoch zusätzlich `TraceLink-CRUD` auf dieser Schnittstelle (`IF-L1-12`).
- **Betroffene Systeme:** L1-Architektur, ApplicationServiceSystem, TraceabilityEngineSystem
- **Empfohlene Lösung:** L1-Architektur §5 um `TraceLink-CRUD` in der `ApplicationService → TraceabilityEngine`-Zeile ergänzen.

#### M-09: McpServer- und RestApiAdapter-Requirements unterdokumentieren interne Schnittstellen
- **Beschreibung:** McpServer-Requirements listen 4 interne Schnittstellen (`IF-MC-INT-01..04`), die Architektur definiert jedoch 6 (`IF-MC-INT-001..006`). RestApiAdapter-Requirements listen 3 (`IF-RA-INT-01..03`), die Architektur definiert 6 (`IF-RA-INT-001..006`).
- **Betroffene Systeme:** McpServerSystem, RestApiAdapterSystem
- **Empfohlene Lösung:** L2-Requirements um die fehlenden internen Schnittstellen ergänzen oder zumindest einen Verweis auf die Architektur-Dokumentation einfügen.

#### M-10: ApplicationService-Architektur fehlt explizite Webhook-Ausgangsschnittstelle
- **Beschreibung:** Das Architektur-Diagramm zeigt `WebhookDispatcher → HTTPS POST → Externe Webhook-URLs`, aber die externe Schnittstellen-Tabelle in §2 dokumentiert keinen Ausgang zu externen Systemen. REQ-L2-AS-017 definiert Webhook-Dispatch ohne ausgehende Interface-ID.
- **Betroffene Systeme:** ApplicationServiceSystem
- **Empfohlene Lösung:** Externe Schnittstelle `IF-AS-EXT-OUT-008` (oder ähnlich) für `WebhookDispatcher → Externe Webhook-URLs` in §2-Tabelle und Interface-Registry §1 (als `IF-EXT-07`?) einfügen.

### MINOR (nice to fix)

#### N-01: AuditLog-Entitätsnamen inkonsistent zwischen L1-Architektur und PersistenceLayer
- **Beschreibung:** L1-Architektur und Interface-Registry verwenden durchgehend „AuditLog", während PersistenceLayer-Architektur und -Requirements die konkrete Entität als „AuditLogEntry“ bezeichnen.
- **Betroffene Systeme:** PersistenceLayerSystem, L1-Architektur
- **Empfohlene Lösung:** In L1-Architektur §3.1 und Interface-Registry konsistent „AuditLogEntry“ verwenden, da es sich um die tatsächliche Modell-Entität handelt.

#### N-02: Interface-Registry L3-Abschnitt veraltet (AS + MC als „aktiv" gelistet)
- **Beschreibung:** §4 der Interface-Registry listet ApplicationService und McpServer unter „Nicht terminiert (L3 aktiv)“. Dieser Status ist durch Phase-3-Entscheidung überholt.
- **Betroffene Systeme:** Interface Registry
- **Empfohlene Lösung:** L3-Abschnitt §4 aktualisieren: ApplicationService und McpServer als `deprecated/terminated` markieren. L3-Schnittstellen (§4.1–4.4) als historisch kennzeichnen.

---

## Recommendations (Priorisiert)

1. **Sofort (vor nächster Phase):** C-01 beheben — McpServer-AuditLog-Pfad korrigieren, um Dual-Path zu vermeiden und ADR-01-Einheitlichkeit wiederherzustellen.
2. **Sofort:** C-03 beheben — `IF-AS-IN-04` in ApplicationService-Requirements korrigieren.
3. **Sofort:** C-04 beheben — L3-Verzeichnisse für AS und MC löschen.
4. **Vor Interface-Manager-Handoff:** C-02 beheben — Interface-Registry §3.10 korrigieren und fehlende L2-interne Schnittstellen ergänzen.
5. **Vor Architektur-Approval:** M-03 beheben — ApplicationService-Architektur um TraceabilityEngine-Verbindung für TraceLink-CRUD ergänzen.
6. **Vor Architektur-Approval:** M-08 beheben — L1-Architektur §5 um TraceLink-CRUD ergänzen.
7. **Parallel:** M-01 beheben — Interface-ID-Namenskonventionen zwischen Requirements und Architektur vereinheitlichen.
8. **Parallel:** M-04 beheben — Alle L2-Requirements-Designations auf `LEAF/terminal` standardisieren.
9. **Parallel:** M-02 beheben — IF-L1-02 korrekt als indirekte Schnittstelle modellieren.
10. **Nachfolgend:** M-05, M-06, M-07, M-09, M-10, N-01, N-02 als Korrektur-Iteration abarbeiten.

---

## Anhang: REQ-L1-Abdeckungsmatrix (Konsolidiert)

| REQ-L1 | Titel | Primär abgedeckt durch | Mitwirkende REQ-L2 | Status |
|--------|-------|------------------------|---------------------|--------|
| REQ-L1-001 | Artefakt-Hierarchie | AS-001, AS-002, TE-002 | RF-005, PL-004 | ✓ |
| REQ-L1-002 | Requirements CRUD + Workflow | AS-003, WE-001 | PC-004, MC-001, AL-001 | ✓ |
| REQ-L1-003 | Traceability-Engine | AS-010, TE-001..005 | TE-008, MC-002..004 | ✓ |
| REQ-L1-004 | ArchitectureElement | AS-004, RF-004 | LA-001, WE-001 | ✓ |
| REQ-L1-005 | MCP Server | MC-001..012 | AT-002 | ✓ |
| REQ-L1-006 | REST API + OpenAPI | RA-001..012 | AT-001, AT-007 | ✓ |
| REQ-L1-007 | Configurable-Rigor-Presets | AS-020, PC-001..008 | WE-002, MC-008, RF-007 | ✓ |
| REQ-L1-008 | Multi-Level-Baselines | AS-011, BL-001..007 | — | ✓ |
| REQ-L1-009 | Item-Level-Workflow | AS-012, WE-001..005 | AL-001 | ✓ |
| REQ-L1-010 | RBAC | AT-001..007 | RA-005..006, MC-006..007 | ✓ |
| REQ-L1-011 | Audit-Trail | AS-019, AL-001..007 | LA-006, WE-003 | ✓ |
| REQ-L1-012 | Testmanagement + Coverage | AS-005, AS-025, TE-006 | MC-003 | ✓ |
| REQ-L1-013 | LLM-Capabilities | AS-013, LA-001..007 | MC-001 | ✓ |
| REQ-L1-014 | Terminologie-Profile | PC-009..010, RF-008 | AS-007 | ✓ |
| REQ-L1-015 | Multi-Tenancy-Vorbereitung | AS-022, AT-008, PL-001 | TE-011, WE-006 | ✓ |
| REQ-L1-016 | i18n DE/EN | RF-001, RA-004 | RF-011 | ✓ |
| REQ-L1-017 | React-UI | RF-002..006, RF-010..012 | — | ✓ |
| REQ-L1-018 | Docker Compose | — | PL-006 | ⚠ (nur mitwirkend) |
| REQ-L1-019 | Export JSON/CSV | AS-006..007 | — | ✓ |
| REQ-L1-020 | Volltextsuche | AS-008..009 | — | ✓ |
| REQ-L1-021 | CSV-Bulk-Import | AS-014 | — | ✓ |
| REQ-L1-022 | GitHub-Integration | AS-015 | — | ✓ |
| REQ-L1-023 | PDF-Report-Export | AS-016 | — | ✓ |
| REQ-L1-024 | Webhook-Support | AS-017 | — | ✓ |
| REQ-L1-025 | Transaktionale Konsistenz | AS-018, PL-002 | BL-007, TE-003, WE-003, AL-004 | ✓ |
| REQ-L1-026 | Übergreifende Performance | AS-023, PL-008 | TE-012, WE-008, MC-010, RF-009, RA-003 | ✓ |

**Hinweis zu REQ-L1-018:** Kein REQ-L2 hat REQ-L1-018 als primäre Traceability. Die Abdeckung erfolgt ausschließlich mitwirkend durch PL-006 (Idempotente Migrationen für Docker-Compose-Deployment). Für eine vollständige primäre Abdeckung wäre ein dediziertes Deployment-/DevOps-REQ-L2 erforderlich (außerhalb des aktuellen L2-Scopes).

---

*Erstellt durch se-critic-Agent | ReqFlow SE-Kaskade | HOFF-20260620-004*
*Iteration: 1 / 3*
