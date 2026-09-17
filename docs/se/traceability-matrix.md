# ReqogniLoom Traceability Matrix

> **AUTOGENERIERT — NICHT MANUELL EDITIEREN.**
> Generiert von `scripts/generate_traceability_matrix.py` am 2026-08-28T12:51:08+00:00 aus 120 Requirement-Dokumenten und 18 Architektur-Dokumenten.
> Neu erzeugen: `python3 scripts/generate_traceability_matrix.py` — Aenderungen gehoeren in die
> Quelldokumente unter `docs/se/L0/` und `docs/se/L1/`, nicht in diese Datei.
>
> Traceability-Kette der SE-Kaskade:
> **REQ-L0 → REQ-L1 → REQ-L2 → Component → REQ-L3**
>
> Quellen:
> - `docs/se/L0/SN_Stakeholder_Needs.md` (REQ-L0 / Stakeholder Needs)
> - `docs/se/L1/**/L1_*_Requirements.md` (REQ-L1)
> - `docs/se/L1/**/L2_*_Requirements.md` (REQ-L2)
> - `docs/se/L1/**/L3_*_Requirements.md` (REQ-L3)
> - `docs/se/L1/**/L2_*_Architecture.md` (COMP-* und REQ-L2 → Component)
>
> **Notation:** `—` = im Quelldokument nicht verknuepft / nicht zutreffend.
> Alle Status-Marker sind unveraendert aus den Quelldokumenten uebernommen.

---

## 1. REQ-L0 → REQ-L1 (Stakeholder Need → System-Anforderung)

> Quelle: `docs/se/L0/SN_Stakeholder_Needs.md` (REQ-L0-Bestand) und die `**Traceability:**`-Felder
> der REQ-L1-Bloecke (Rueckwaerts-Aufloesung).

| REQ-L0 | SN | Titel | Impl. State | REQ-L1 IDs |
|--------|----|-------|-------------|------------|
| REQ-L0-001 | SN-01 | Maschinenlesbarer Anforderungskontext für AI-Agenten | Implemented | REQ-L1-005, REQ-L1-006, REQ-L1-020 |
| REQ-L0-002 | SN-02 | Skalierbare SE-Tiefe ohne Produktwechsel | Not Implemented | REQ-L1-001, REQ-L1-002, REQ-L1-007, REQ-L1-025, REQ-L1-026 |
| REQ-L0-003 | SN-03 | Vollständige Traceability zwischen Requirements, Architektur und Tests | Teilweise Implementiert | REQ-L1-001, REQ-L1-003, REQ-L1-004, REQ-L1-012, REQ-L1-058, REQ-L1-060, REQ-L1-061, REQ-L1-062, REQ-L1-063, REQ-L1-092 |
| REQ-L0-004 | SN-04 | Unveränderliche, benannte Anforderungs-Baselines auf mehreren Ebenen | Not Implemented | REQ-L1-008, REQ-L1-090 |
| REQ-L0-005 | SN-05 | Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates | Teilweise Implementiert | REQ-L1-002, REQ-L1-009, REQ-L1-010 |
| REQ-L0-006 | SN-06 | Self-Hosted Deployment ohne Vendor-Lock-in | Not Implemented | REQ-L1-018 |
| REQ-L0-007 | SN-07 | LLM-gestützte Qualitätssicherung als optionale Capability | Not Implemented | REQ-L1-013 |
| REQ-L0-008 | SN-08 | Mandantenfähige Isolation für spätere SaaS-Erweiterung | Not Implemented | REQ-L1-015 |
| REQ-L0-009 | SN-09 | Zweisprachige Benutzeroberfläche (Deutsch und Englisch) | Not Implemented | REQ-L1-016, REQ-L1-089, REQ-L1-093, REQ-L1-094 |
| REQ-L0-010 | SN-10 | Terminologie-Flexibilität für zwei Zielgruppen ohne Datenverlust | Not Implemented | REQ-L1-014 |
| REQ-L0-011 | SN-11 | Vollständiger Audit-Trail für agentengesteuerte und manuelle Änderungen | Implemented | REQ-L1-011 |
| REQ-L0-012 | SN-12 | REST API und MCP Server als gleichrangige, vollständige Schnittstellen | Implemented | REQ-L1-005, REQ-L1-006, REQ-L1-017, REQ-L1-019, REQ-L1-024 |
| REQ-L0-013 | SN-13 | Effiziente Übernahme bestehender Anforderungsdaten | Implemented | REQ-L1-021 |
| REQ-L0-014 | SN-14 | Integration mit Entwicklungstools und Issue-Trackern | Not Implemented | REQ-L1-022, REQ-L1-024 |
| REQ-L0-015 | SN-15 | Audit-dokumentierbare Anforderungsberichte und Traceability-Matrizen | Implemented | REQ-L1-023 |
| REQ-L0-016 | SN-16 | Interaktive Diagramme und Grafiken direkt im Tool | Implemented | REQ-L1-027, REQ-L1-100, REQ-L1-101 |
| REQ-L0-017 | SN-17 | Verwaltung einer rekursiven Architektur-Hierarchie mit versionierten ICDs | Implemented | REQ-L1-028, REQ-L1-058, REQ-L1-059, REQ-L1-062, REQ-L1-089, REQ-L1-090, REQ-L1-091, REQ-L1-095 |
| REQ-L0-018 | SN-18 | Verwaltung von Architekturentscheidungen (ADRs), Risiken und Issues | Not Implemented | REQ-L1-029, REQ-L1-089, REQ-L1-095 |
| REQ-L0-019 | SN-19 | Projektübergreifende Traceability für rekursive SE-Zerlegung | Not Implemented | REQ-L1-030 |
| REQ-L0-020 | SN-20 | Metrikbasiertes Steuern des SE-Prozesses | Implemented | REQ-L1-031 |
| REQ-L0-021 | SN-21 | Asynchrone, resiliente Systemkommunikation zwischen Komponenten | Not Implemented | REQ-L1-032 |
| REQ-L0-022 | SN-22 | Credential-basierter User-Login (Benutzername/Passwort) | Not Implemented | REQ-L1-033 |
| REQ-L0-023 | SN-23 | ReqIF-Support für MBSE-Datenaustausch | Not Implemented | REQ-L1-034 |
| REQ-L0-024 | SN-24 | Test-Ausführungs-Management (Test Runs) | Not Implemented | REQ-L1-035, REQ-L1-036 |
| REQ-L0-025 | SN-25 | Kollaboration und In-App-Diskussion | Not Implemented | REQ-L1-037 |
| REQ-L0-026 | SN-26 | Semantische Suche (RAG) und KI-Assistenz | Not Implemented | REQ-L1-038 |
| REQ-L0-027 | SN-27 | Granulare Zugriffssteuerung (Item-Level Access) | Not Implemented | REQ-L1-039 |
| REQ-L0-028 | SN-28 | Visuelles Diffing von Artefakten und Baselines | Not Implemented | REQ-L1-040, REQ-L1-041, REQ-L1-091 |
| REQ-L0-029 | SN-29 | Workspace-Lifecycle-Management für Administratoren | Not Implemented | REQ-L1-042 |
| REQ-L0-030 | SN-30 | Suspect-Link-Propagierung bei Anforderungsänderungen | Not Implemented | REQ-L1-043, REQ-L1-092 |
| REQ-L0-032 | SN-32 | Semantisches Projekt-Glossar (Data Dictionary) | Not Implemented | REQ-L1-044 |
| REQ-L0-033 | SN-33 | Isolierte Requirement-Sandboxes (Branch & Merge) | Not Implemented | REQ-L1-045 |
| REQ-L0-034 | SN-34 | Instanz-Backup, Disaster Recovery & Baseline-Vergleich | Not Implemented | REQ-L1-046 |
| REQ-L0-035 | SN-35 | Direkte Traceability-Verknüpfungen über mehrere Ebenen (Cross-Level-Links) | Not Implemented | REQ-L1-047, REQ-L1-092 |
| REQ-L0-036 | SN-36 | Diagramme als freies Canvas-Zeichnen (Free-Hand Drawing) | Not Implemented | REQ-L1-056 |
| REQ-L0-037 | SN-37 | Mermaid-Code mit Live-Rendering (Live Preview) | Not Implemented | REQ-L1-057 |
| REQ-L0-038 | SN-38 | Skalierbarkeit & Übersicht bei großen Datenmengen | Not Implemented | REQ-L1-064, REQ-L1-066 |
| REQ-L0-039 | SN-39 | Systemebenen-Orientierung durch Hierarchie-Darstellung | Not Implemented | REQ-L1-067 |
| REQ-L0-040 | SN-40 | UI-Performance durch Lazy Loading | Not Implemented | REQ-L1-065 |
| REQ-L0-041 | SN-41 | Adaptive Ontologie (Skalierung der SE-Strenge) | Not Implemented | REQ-L1-068, REQ-L1-075 |
| REQ-L0-042 | SN-42 | Ontologie-Vielfalt (StReq, SyReq, ArchE, CoReq, IF, ADR, Risk, TC) | Not Implemented | REQ-L1-071, REQ-L1-095 |
| REQ-L0-043 | SN-43 | Erweiterte UI-Ansichten (TRM, Node Graph, Split-Screen) | Not Implemented | REQ-L1-070 |
| REQ-L0-044 | SN-44 | Versionierte Kanten (Dynamic vs. Static Traces) | Not Implemented | REQ-L1-072 |
| REQ-L0-045 | SN-45 | Anti-Pattern Erkennung (Orphans, Barren Nodes) | Not Implemented | REQ-L1-073 |
| REQ-L0-046 | SN-46 | Proaktive KI-Agenten (Semantic Healing, Interfaces, Decomposition) | Not Implemented | REQ-L1-069, REQ-L1-074, REQ-L1-080 |
| REQ-L0-047 | SN-47 | Präzises, domänenspezifisches Datenmodell | Not Implemented | REQ-L1-076, REQ-L1-077 |
| REQ-L0-048 | SN-48 | Industriestandard Workflow-Status | Not Implemented | REQ-L1-078 |
| REQ-L0-049 | SN-49 | Stage-Gating & Guardrails (Strenge SE-Regeln) | Not Implemented | REQ-L1-079, REQ-L1-080 |
| REQ-L0-050 | SN-50 | Personal Access Tokens (PAT) via UI | Sonstige (Freitext) | — |
| REQ-L0-051 | SN-51 | System Broadcast Banner | Not Implemented | — |
| REQ-L0-052 | SN-52 | Visuelle Baum-Struktur für Artefakt-Hierarchien | Not Implemented | — |
| REQ-L0-053 | SN-53 | Konsistentes Split-View Layout | Not Implemented | — |
| REQ-L0-054 | SN-54 | Effiziente Listen-Navigation | Not Implemented | — |
| REQ-L0-055 | SN-55 | Glossar-Referenzen im Freitext (@-Mentions) | Not Implemented | REQ-L1-086 |
| REQ-L0-056 | SN-56 | Konfigurierbare KI-Ableitungs-Prompts | Not Implemented | REQ-L1-088 |
| REQ-L0-060 | SN-60 | Konsistentes UI/UX Design und Universelles Versioning | Not Implemented | REQ-L1-085, REQ-L1-086 |
| REQ-L0-061 | SN-61 | Interaktive und versionierte Architektur-Diagramme | Not Implemented | REQ-L1-087 |
| REQ-L0-062 | SN-62 | Unified Artifact Inspector Sidebar (Right Sidebar) | Not Implemented | REQ-L1-089, REQ-L1-090, REQ-L1-091, REQ-L1-092, REQ-L1-093, REQ-L1-094, REQ-L1-095, REQ-L1-099 |

---

## 2. REQ-L1 → REQ-L2 (System → Subsystem)

> Rueckwaerts aufgeloest aus den `**Traceability:**`-Feldern der REQ-L2-Bloecke.
> `primaer` = REQ-L2 ohne `(mitwirkend)`-Annotation; mitwirkende Links sind nur
> gezaehlt, nicht ausgeschrieben.

| REQ-L1 | Titel | Impl. State | Primaere L2-Systeme | REQ-L2 (primaer) | mitw. |
|--------|-------|-------------|---------------------|------------------|-------|
| REQ-L1-001 | Artefakt-Hierarchie mit beliebiger Tiefe | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, TraceabilityEngineSystem | REQ-L2-AS-001, REQ-L2-AS-002, REQ-L2-AS-039, REQ-L2-PL-004, REQ-L2-TE-002 | 3 |
| REQ-L1-002 | Requirements CRUD mit konfigurierbarem Status-Workflow | Implemented | ApplicationServiceSystem, PersistenceLayerSystem | REQ-L2-AS-003, REQ-L2-AS-024, REQ-L2-PL-004 | 10 |
| REQ-L1-003 | Traceability-Engine mit bidirektionalen Links | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, TraceabilityEngineSystem | REQ-L2-AS-010, REQ-L2-PL-004, REQ-L2-TE-001, REQ-L2-TE-003, REQ-L2-TE-004, REQ-L2-TE-005, REQ-L2-TE-009, REQ-L2-TE-013, REQ-L2-TE-019, REQ-L2-TE-020 | 12 |
| REQ-L1-004 | ArchitectureElement als eigenständiger, schreibbarer Artefakttyp | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, TraceabilityEngineSystem | REQ-L2-AS-004, REQ-L2-PL-004, REQ-L2-TE-007 | 6 |
| REQ-L1-005 | MCP Server mit vollständigem Read/Write-Zugriff auf alle Artefakttypen | Implemented | AuthAndTenancySystem, McpServerSystem, PersistenceLayerSystem | REQ-L2-AT-002, REQ-L2-AT-007, REQ-L2-AT-009, REQ-L2-MC-001, REQ-L2-MC-002, REQ-L2-MC-003, REQ-L2-MC-004, REQ-L2-MC-005, REQ-L2-MC-006, REQ-L2-MC-009, REQ-L2-MC-011, REQ-L2-PL-004 | 5 |
| REQ-L1-006 | Synchrone maschinenlesbare API mit Spezifikation für alle Entitäten | Implemented | AuthAndTenancySystem, PersistenceLayerSystem, RestApiAdapterSystem | REQ-L2-AT-001, REQ-L2-AT-007, REQ-L2-AT-010, REQ-L2-PL-004, REQ-L2-RA-001, REQ-L2-RA-002, REQ-L2-RA-005, REQ-L2-RA-009, REQ-L2-RA-010, REQ-L2-RA-012 | 6 |
| REQ-L1-007 | Configurable-Rigor-Presets (Minimal / Standard / Extended) | Implemented | ApplicationServiceSystem, McpServerSystem, PersistenceLayerSystem, PresetConfigEngineSystem, ReactFrontendSystem, RestApiAdapterSystem, WorkflowEngineSystem | REQ-L2-AS-020, REQ-L2-MC-008, REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-003, REQ-L2-PC-004, REQ-L2-PC-005, REQ-L2-PC-006, REQ-L2-PC-007, REQ-L2-PC-008, REQ-L2-PC-011, REQ-L2-PC-012, REQ-L2-PC-014, REQ-L2-PL-004, REQ-L2-RA-008, REQ-L2-RF-007, REQ-L2-WE-007 | 8 |
| REQ-L1-008 | Multi-Level-Baselines (Dokument / Projekt / Global) | Implemented | ApplicationServiceSystem, BaselineServiceSystem, PersistenceLayerSystem, TraceabilityEngineSystem | REQ-L2-AS-011, REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-003, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-006, REQ-L2-BL-007, REQ-L2-BL-008, REQ-L2-BL-009, REQ-L2-BL-012, REQ-L2-PL-004, REQ-L2-TE-008 | 4 |
| REQ-L1-009 | Konfigurierbarer Item-Level-Workflow mit Audit-Trail | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, WorkflowEngineSystem | REQ-L2-AS-012, REQ-L2-PL-004, REQ-L2-WE-001, REQ-L2-WE-002, REQ-L2-WE-003, REQ-L2-WE-004, REQ-L2-WE-005, REQ-L2-WE-009 | 9 |
| REQ-L1-010 | Rollenbasierte Zugriffskontrolle (Admin, Editor, Viewer, Approver) | Implemented | ApplicationServiceSystem, AuthAndTenancySystem, McpServerSystem, PersistenceLayerSystem, RestApiAdapterSystem | REQ-L2-AS-021, REQ-L2-AT-001, REQ-L2-AT-002, REQ-L2-AT-003, REQ-L2-AT-004, REQ-L2-AT-005, REQ-L2-AT-006, REQ-L2-AT-007, REQ-L2-AT-009, REQ-L2-MC-007, REQ-L2-PL-004, REQ-L2-RA-006 | 6 |
| REQ-L1-011 | Vollständiger Audit-Trail für alle Änderungen | Implemented | ApplicationServiceSystem, AuditLogSystem, LlmAdapterSystem, McpServerSystem, PersistenceLayerSystem, RestApiAdapterSystem, TraceabilityEngineSystem | REQ-L2-AL-001, REQ-L2-AL-002, REQ-L2-AL-003, REQ-L2-AL-005, REQ-L2-AL-009, REQ-L2-AS-019, REQ-L2-AS-029, REQ-L2-LA-006, REQ-L2-MC-012, REQ-L2-PL-004, REQ-L2-PL-005, REQ-L2-RA-007, REQ-L2-TE-010 | 15 |
| REQ-L1-012 | Testmanagement mit Coverage-Tracking | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, TraceabilityEngineSystem | REQ-L2-AS-005, REQ-L2-AS-025, REQ-L2-PL-004, REQ-L2-TE-006 | 7 |
| REQ-L1-013 | LLM-Capabilities als konfigurierbare, optionale Features | Implemented | ApplicationServiceSystem, LlmAdapterSystem, PersistenceLayerSystem | REQ-L2-AS-013, REQ-L2-AS-024, REQ-L2-LA-001, REQ-L2-LA-002, REQ-L2-LA-003, REQ-L2-LA-004, REQ-L2-LA-005, REQ-L2-LA-007, REQ-L2-LA-008, REQ-L2-LA-009, REQ-L2-LA-010, REQ-L2-PL-004 | 3 |
| REQ-L1-014 | Konfigurierbare Terminologie-Profile (Dev-Modus / SE-Modus) | Implemented | ApplicationServiceSystem, PersistenceLayerSystem, PresetConfigEngineSystem, ReactFrontendSystem | REQ-L2-AS-007, REQ-L2-PC-009, REQ-L2-PC-010, REQ-L2-PL-004, REQ-L2-RF-008 | 3 |
| REQ-L1-015 | Mandantenfähigkeit ohne spätere Datenmigration | Implemented | ApplicationServiceSystem, AuditLogSystem, AuthAndTenancySystem, PersistenceLayerSystem, RestApiAdapterSystem, TraceabilityEngineSystem, WorkflowEngineSystem | REQ-L2-AL-006, REQ-L2-AS-022, REQ-L2-AT-008, REQ-L2-PL-001, REQ-L2-PL-004, REQ-L2-PL-010, REQ-L2-RA-011, REQ-L2-TE-011, REQ-L2-WE-006 | 4 |
| REQ-L1-016 | Zweisprachige Benutzeroberfläche (Deutsch und Englisch) | Implemented | ReactFrontendSystem, RestApiAdapterSystem | REQ-L2-RA-004, REQ-L2-RF-001, REQ-L2-RF-011 | 2 |
| REQ-L1-017 | Grafische Benutzeroberfläche (GUI) für manuelle Workflows | Implemented | ReactFrontendSystem | REQ-L2-RF-002, REQ-L2-RF-003, REQ-L2-RF-004, REQ-L2-RF-005, REQ-L2-RF-006, REQ-L2-RF-010, REQ-L2-RF-011, REQ-L2-RF-012 | — |
| REQ-L1-018 | Eigenständiges Deployment für Self-Hosted-Betrieb | Implemented | PersistenceLayerSystem | REQ-L2-PL-006 | 1 |
| REQ-L1-019 | Export in JSON und CSV für alle Entitäten | Implemented | ApplicationServiceSystem | REQ-L2-AS-006, REQ-L2-AS-007 | — |
| REQ-L1-020 | Volltextsuche über alle Artefakttypen | Implemented | ApplicationServiceSystem | REQ-L2-AS-008, REQ-L2-AS-009 | 3 |
| REQ-L1-021 | CSV-Bulk-Import für Requirements und Artefakte | Implemented | ApplicationServiceSystem | REQ-L2-AS-014 | — |
| REQ-L1-022 | GitHub-Integration für Requirement-Issue/PR-Verknüpfung | Not Implemented | ApplicationServiceSystem | REQ-L2-AS-015 | — |
| REQ-L1-023 | PDF-Report-Export für Anforderungsdokumente und Traceability-Matrizen | Implemented | ApplicationServiceSystem | REQ-L2-AS-016 | — |
| REQ-L1-024 | Webhook-Support für Anforderungsänderungen | Implemented | ApplicationServiceSystem | REQ-L2-AS-017 | — |
| REQ-L1-025 | Transaktionale Konsistenz (ACID) | Implemented | ApplicationServiceSystem, AuditLogSystem, PersistenceLayerSystem | REQ-L2-AL-004, REQ-L2-AS-018, REQ-L2-PL-002, REQ-L2-PL-009 | 6 |
| REQ-L1-026 | Übergreifende Performance-Anforderung | Implemented | ApplicationServiceSystem, AuditLogSystem, BaselineServiceSystem, McpServerSystem, PersistenceLayerSystem, PresetConfigEngineSystem, ReactFrontendSystem, RestApiAdapterSystem, SeMetricsSystem, TraceabilityEngineSystem, WorkflowEngineSystem | REQ-L2-AL-007, REQ-L2-AL-008, REQ-L2-AS-023, REQ-L2-AS-029, REQ-L2-BL-008, REQ-L2-MC-010, REQ-L2-PC-013, REQ-L2-PL-003, REQ-L2-PL-007, REQ-L2-PL-008, REQ-L2-RA-003, REQ-L2-RA-013, REQ-L2-RF-009, REQ-L2-SM-013, REQ-L2-TE-012, REQ-L2-WE-008 | 11 |
| REQ-L1-027 | Integrierte Diagramm- und Grafik-Verwaltung | Implemented | DiagramServiceSystem | REQ-L2-DS-001, REQ-L2-DS-002, REQ-L2-DS-003, REQ-L2-DS-004, REQ-L2-DS-005 | — |
| REQ-L1-028 | ICD-Verwaltung mit Versionierung und Design-by-Contract | Implemented | IcdManagementSystem | REQ-L2-ICD-001, REQ-L2-ICD-002, REQ-L2-ICD-003, REQ-L2-ICD-004, REQ-L2-ICD-005, REQ-L2-ICD-006 | — |
| REQ-L1-029 | ADR-, Risiko- und Issue-Verwaltung mit Artefakt-Verknüpfung | Implemented | ApplicationServiceSystem | REQ-L2-AS-026, REQ-L2-AS-027, REQ-L2-AS-028 | 1 |
| REQ-L1-030 | Projektübergreifende Traceability (Cross-Projekt-Links) | Implemented | TraceabilityEngineSystem | REQ-L2-TE-014, REQ-L2-TE-015 | — |
| REQ-L1-031 | SE-Prozess-Metrikmodul | Implemented | SeMetricsSystem | REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-003, REQ-L2-SM-004, REQ-L2-SM-005, REQ-L2-SM-006, REQ-L2-SM-007, REQ-L2-SM-008, REQ-L2-SM-009, REQ-L2-SM-010, REQ-L2-SM-011, REQ-L2-SM-012 | 1 |
| REQ-L1-032 | Resilienz-Anforderung — Fehlertoleranz und Graceful Degradation | Implemented | ResilienceOrchestratorSystem | REQ-L2-RO-001, REQ-L2-RO-002, REQ-L2-RO-003, REQ-L2-RO-004, REQ-L2-RO-005, REQ-L2-RO-006 | — |
| REQ-L1-033 | Credential-basierte Authentifizierung mit Token-Ausgabe | Not Implemented | AuthAndTenancySystem | REQ-L2-AT-011, REQ-L2-AT-012, REQ-L2-AT-013, REQ-L2-AT-014, REQ-L2-AT-015, REQ-L2-AT-016 | — |
| REQ-L1-034 | ReqIF-Import und -Export für MBSE-Datenaustausch | Not Implemented | ReqIFServiceSystem | REQ-L2-RQ-001, REQ-L2-RQ-002 | — |
| REQ-L1-035 | Test-Run-Protokollierung mit Ausführungsstatus | Implemented | ApplicationServiceSystem | REQ-L2-AS-030 | — |
| REQ-L1-036 | Automatisierte Test-Ergebnis-Einspeisung via API und MCP | Not Implemented | ApplicationServiceSystem, McpServerSystem | REQ-L2-AS-031, REQ-L2-MC-013 | — |
| REQ-L1-037 | Kontextbezogene Kommentar-Threads mit Mention-Benachrichtigung | Not Implemented | CommentServiceSystem | REQ-L2-CM-001, REQ-L2-CM-002, REQ-L2-CM-003 | — |
| REQ-L1-038 | Semantische Vektorsuche über alle Artefakttypen (RAG) | Not Implemented | VectorSearchServiceSystem | REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003, REQ-L2-VS-004 | — |
| REQ-L1-039 | Granulare Item-Level-Zugriffskontrolle | Implemented | AuthAndTenancySystem | REQ-L2-AT-017, REQ-L2-AT-018, REQ-L2-AT-019 | — |
| REQ-L1-040 | Visuelles Artefakt-Diff zwischen Versionen | Implemented | ApplicationServiceSystem, ReactFrontendSystem | REQ-L2-AS-032, REQ-L2-RF-014 | — |
| REQ-L1-041 | Visuelles Baseline-Diff zwischen zwei Baselines | Not Implemented | ReactFrontendSystem | REQ-L2-RF-015 | — |
| REQ-L1-042 | Workspace-Lifecycle-Operationen mit RBAC | Implemented | — | — | — |
| REQ-L1-043 | Suspect-Link-Engine (Automatische Änderungsmarkierung) | Not Implemented | TraceabilityEngineSystem | REQ-L2-TE-016 | — |
| REQ-L1-044 | Semantisches Projekt-Glossar (Data Dictionary) | Not Implemented | — | — | — |
| REQ-L1-045 | Artefakt-Branching & Merging (Isolierte Sandboxes) | Not Implemented | BaselineServiceSystem | REQ-L2-BL-010 | — |
| REQ-L1-046 | Instanz-Backup, Disaster Recovery & Baseline-Restore | Implemented | BaselineServiceSystem | REQ-L2-BL-011 | — |
| REQ-L1-047 | Cross-Level-TraceLink-Konzept (Kontrollierte Ebenensprünge) | Not Implemented | TraceabilityEngineSystem | REQ-L2-TE-017 | — |
| REQ-L1-048 | Flache und Ebenenbasierte Artefaktansicht (Multi-View) | Not Implemented | — | — | — |
| REQ-L1-056 | Free-Hand Canvas Drawing | Implemented | DiagramServiceSystem | REQ-L2-DS-006, REQ-L2-DS-008, REQ-L2-DS-009, REQ-L2-DS-010, REQ-L2-DS-011, REQ-L2-DS-012 | — |
| REQ-L1-057 | Mermaid Live Preview | Implemented | ApplicationServiceSystem, DiagramServiceSystem | REQ-L2-AS-033, REQ-L2-DS-007 | — |
| REQ-L1-058 | SE Masks Unification (13 Entity Types) | Backlog | — | — | — |
| REQ-L1-059 | ArchitectureElement parent_id + Level-Derivation | Backlog | ApplicationServiceSystem | REQ-L2-AS-034 | — |
| REQ-L1-060 | TraceLink allocated-to + Allocation-Coverage Reporter | Backlog | TraceabilityEngineSystem | REQ-L2-TE-018 | — |
| REQ-L1-061 | RequirementService.decompose() Extension mit target_elements | Backlog | ApplicationServiceSystem | REQ-L2-AS-035 | — |
| REQ-L1-062 | Invarianten-Validator (I1-I4) rigor-gated | Backlog | ApplicationServiceSystem | REQ-L2-AS-036 | — |
| REQ-L1-063 | Frontend Level-View (Requirements Hierarchy) | Backlog | — | — | — |
| REQ-L1-064 | Einheitliche, skalierbare Listen-Komponente (UI) | Backlog | — | — | — |
| REQ-L1-065 | Lazy Loading / Server-Side Pagination | Backlog | — | — | — |
| REQ-L1-066 | Serverseitige Such-, Filter- und Sortierfunktionen | Backlog | — | — | — |
| REQ-L1-067 | Hierarchische Darstellung in Primärlisten | Backlog | — | — | — |
| REQ-L1-068 | Graph-Datenbank als Backend-Kern | Deferred | — | — | — |
| REQ-L1-069 | AI Orchestration Layer & Semantic Router | Backlog | — | — | — |
| REQ-L1-070 | WebGL / Canvas Graph Rendering | Backlog | — | — | — |
| REQ-L1-071 | Spezifische Traceability-Ontologie | Backlog | — | — | — |
| REQ-L1-072 | Statische vs. Dynamische TraceLinks | Backlog | — | — | — |
| REQ-L1-073 | Rules Engine für Anti-Patterns | Backlog | — | — | — |
| REQ-L1-074 | Semantic Trace Healing Engine | Backlog | — | — | — |
| REQ-L1-075 | GraphQL & REST Parität | Deferred | — | — | — |
| REQ-L1-076 | Global Entity Metadata | Backlog | — | — | — |
| REQ-L1-077 | Artifact-Specific Schema | Backlog | — | — | — |
| REQ-L1-078 | State Machine & Workflow | Backlog | — | — | — |
| REQ-L1-079 | Stage-Gating Engine (Guardrails) | Backlog | — | — | — |
| REQ-L1-080 | Event-Driven AI Automation | Backlog | — | — | — |
| REQ-L1-081 | Personal Access Token (PAT) Management | Sonstige (Freitext) | — | — | — |
| REQ-L1-082 | Global System Announcement | Not Implemented | — | — | — |
| REQ-L1-083 | Navigation in hierarchischer Baumstruktur | Not Implemented | — | — | — |
| REQ-L1-084 | Konsistente Split-View-Maskenarchitektur | Not Implemented | — | — | — |
| REQ-L1-085 | Erweiterte Listenoperationen | Not Implemented | — | — | — |
| REQ-L1-086 | Glossary Mentions & Persistence | Backlog | ApplicationServiceSystem | REQ-L2-AS-037 | — |
| REQ-L1-087 | Strikte Trennung von Workspace Administration und User Preferences | In Progress | — | — | — |
| REQ-L1-088 | Konfigurierbare KI-Ableitungs-Prompts | Backlog | ApplicationServiceSystem | REQ-L2-AS-038 | — |
| REQ-L1-089 | Unified ArtifactInspector (RightSidebar) Shell | Not Implemented | ReactFrontendSystem | REQ-L2-RF-034 | — |
| REQ-L1-090 | VersionPanel inside ArtifactInspector | Not Implemented | ReactFrontendSystem | REQ-L2-RF-035 | — |
| REQ-L1-091 | DiffPanel inside ArtifactInspector (field-level diff) | Not Implemented | ReactFrontendSystem | REQ-L2-RF-036 | — |
| REQ-L1-092 | TracePanel inside ArtifactInspector (inbound/outbound links, type filter) | Not Implemented | ReactFrontendSystem | REQ-L2-RF-037 | — |
| REQ-L1-093 | Accessibility baseline for ArtifactInspector | Not Implemented | ReactFrontendSystem | REQ-L2-RF-034, REQ-L2-RF-036 | — |
| REQ-L1-094 | i18n key naming convention for ArtifactInspector (DE/EN) | Not Implemented | ReactFrontendSystem | REQ-L2-RF-034, REQ-L2-RF-035, REQ-L2-RF-036, REQ-L2-RF-037 | — |
| REQ-L1-095 | Adoption of ArtifactInspector on all 10 artifact types | Not Implemented | — | — | — |
| REQ-L1-096 | API Security & Secret Management | Planned | — | — | — |
| REQ-L1-097 | Transactional Integrity & Concurrency | Planned | — | — | — |
| REQ-L1-098 | Data Integrity & Tenant Isolation | Planned | — | — | — |
| REQ-L1-099 | System Performance & Constraints | Planned | — | — | — |
| REQ-L1-100 | Node Graph Diagram Payload Format | Implemented | — | — | — |
| REQ-L1-101 | DIAGRAM_REF Trace Link Type for Reconciler-Owned Diagram-Artifact References | Implemented | — | — | — |

---

## 3. REQ-L2 → Component (Subsystem → Komponente)

> Je L2-System: alle REQ-L2 des Systems mit der in `L2_*_Architecture.md`
> (§ *Zugeordnete REQ-L2*) deklarierten Komponente sowie den im Requirement-
> Dokument gesetzten Status-Markern.
>
> `(via L3)` = im Architektur-Dokument nicht zugeordnet, sondern aus dem
> L3-Komponenten-Dokument abgeleitet (§ *Zugeordnete L2-Anforderungen* bzw.
> REQ-L3-Parent-Links).

### 3.1 AiOrchestrationSystem (8 REQ-L2 → 4 Komponenten, 11 REQ-L3)

*Komponenten:* COMP-AI-001 (AiQualityGateAgent), COMP-AI-002 (AiDecompositionAgent), COMP-AI-003 (AiVerificationAgent), COMP-AI-004 (AiDerivationService)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-AI-001 | Semantic Router (Hybrid AI) | COMP-AI-004 | Not Implemented | Missing |
| REQ-L2-AI-002 | Semantic Trace Healing Agent | COMP-AI-004 | Not Implemented | Missing |
| REQ-L2-AI-003 | Interface Consistency Agent | COMP-AI-001 | Not Implemented | Missing |
| REQ-L2-AI-004 | AI Quality Gate bei Status-Übergang | COMP-AI-001 | Not Implemented | Missing |
| REQ-L2-AI-005 | AI Decomposition & AI Test-Generation | COMP-AI-002, COMP-AI-003 | Not Implemented | Missing |
| REQ-L2-AI-006 | Workspace-spezifische KI-Prompts anwenden | COMP-AI-001, COMP-AI-002, COMP-AI-003, COMP-AI-004 | Not Implemented | Missing |
| REQ-L2-AI-007 | AI Derivation Service — Draft/Accept-Infrastruktur | COMP-AI-004 | Not Implemented | (kein Marker) |
| REQ-L2-AI-008 | AI Derivation Flows — Konkrete Ableitungsschritte | COMP-AI-004 | Not Implemented | (kein Marker) |

### 3.2 ApplicationServiceSystem (44 REQ-L2 → 19 Komponenten, 115 REQ-L3)

*Komponenten:* COMP-AS-001 (ArtifactService), COMP-AS-002 (RequirementService), COMP-AS-003 (ArchitectureService), COMP-AS-004 (TestService), COMP-AS-005 (TraceLinkService), COMP-AS-006 (BaselineFacade), COMP-AS-007 (WorkflowFacade), COMP-AS-008 (ExportService), COMP-AS-009 (ImportService), COMP-AS-010 (SearchService), COMP-AS-011 (WebhookDispatcher), COMP-AS-012 (PresetPolicyService), COMP-AS-013 (AdrService), COMP-AS-014 (RiskService), COMP-AS-015 (IssueService), COMP-AS-016 (DomainEventBus), COMP-AS-017 (TestRunService) ⚠ nur Verzeichnis, COMP-AS-018 (TestResultIngestion) ⚠ nur Verzeichnis, COMP-AS-019 (ArtifactDiffService) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-AS-001 | Artifact-Hierarchy Cycle Detection | COMP-AS-001 | Implemented | Covered |
| REQ-L2-AS-002 | Artifact Tree Query mit beliebiger Tiefe | COMP-AS-001 | Implemented | Covered |
| REQ-L2-AS-003 | Requirement CRUD with Workflow Integration | COMP-AS-002 | Implemented | Covered |
| REQ-L2-AS-004 | ArchitectureElement CRUD with Versioning | COMP-AS-003 | Implemented | Covered |
| REQ-L2-AS-005 | TestCase CRUD with Test Status Management | COMP-AS-004 | Not Implemented | Covered |
| REQ-L2-AS-006 | Export in JSON and CSV | COMP-AS-008 | Implemented | Covered |
| REQ-L2-AS-007 | Export with Terminology Profile Metadata | COMP-AS-008 | Implemented | Missing |
| REQ-L2-AS-008 | Full-Text Search across Artifact Types | COMP-AS-010 | Not Implemented | Missing |
| REQ-L2-AS-009 | Search Type-Filter and Workspace-Filter | COMP-AS-010 | Implemented | Covered |
| REQ-L2-AS-010 | TraceLink Orchestration | COMP-AS-005 | Implemented | Covered |
| REQ-L2-AS-011 | Baseline Lifecycle Orchestration | COMP-AS-006 | Not Implemented | Missing |
| REQ-L2-AS-012 | Workflow Transition Orchestration | COMP-AS-007 | Not Implemented | Missing |
| REQ-L2-AS-013 | LLM Capability Orchestration | COMP-AS-002 | Implemented | Covered |
| REQ-L2-AS-014 | CSV Bulk Import | COMP-AS-009 | Implemented | Covered |
| REQ-L2-AS-015 | GitHub Integration | COMP-AS-002 | Implemented | Missing |
| REQ-L2-AS-016 | PDF Report Export | COMP-AS-008 | Implemented | Covered |
| REQ-L2-AS-017 | Webhook Dispatch | COMP-AS-011 | Implemented | Covered |
| REQ-L2-AS-018 | Transactional Consistency (ACID) | — | Implemented | Covered |
| REQ-L2-AS-019 | Audit Log Writing | — | Implemented | Covered |
| REQ-L2-AS-020 | Preset Policy Enforcement | COMP-AS-012 | Implemented | Covered |
| REQ-L2-AS-021 | Auth Context Propagation | — | Implemented | Missing |
| REQ-L2-AS-022 | Tenant Context Propagation | — | Implemented | Covered |
| REQ-L2-AS-023 | Performance Contribution | — | Implemented | Missing |
| REQ-L2-AS-024 | Requirement Decomposition Orchestration | COMP-AS-002 | Implemented | Covered |
| REQ-L2-AS-025 | Coverage Calculation | COMP-AS-004 | Implemented | Covered |
| REQ-L2-AS-026 | ADR CRUD | COMP-AS-016 | Implemented | Missing |
| REQ-L2-AS-027 | Risiko CRUD | — | Not Implemented | Missing |
| REQ-L2-AS-028 | Issue CRUD | — | Not Implemented | Missing |
| REQ-L2-AS-029 | Asynchroner Entkopplungsmechanismus | — | Implemented | Covered |
| REQ-L2-AS-030 | Test-Run-Protokollierung | — | Implemented | Covered |
| REQ-L2-AS-031 | Automatisierte Test-Ergebnis-Einspeisung | — | Implemented | Covered |
| REQ-L2-AS-032 | Artefakt Field-Level Diff | — | Implemented | Covered |
| REQ-L2-AS-033 | Semantisches Projekt-Glossar (GlossaryTerm CRUD) | — | Not Implemented | Missing |
| REQ-L2-AS-034 | ArchitectureElement parent_id + Level-Derivation | — | Backlog | Missing |
| REQ-L2-AS-035 | RequirementService.decompose() Extension mit target_elements | — | Backlog | Missing |
| REQ-L2-AS-036 | Invarianten-Validator (I1-I4) rigor-gated | — | Backlog | Missing |
| REQ-L2-AS-037 | Glossary Persistence on Workspace Deletion | — | Backlog | Missing |
| REQ-L2-AS-038 | Workspace-spezifische KI-Prompts (AIPrompt CRUD) | — | Backlog | Missing |
| REQ-L2-AS-039 | Dynamische Custom-Attribute (JSONB) pro Artefakttyp | COMP-AS-001 | Not Implemented | Missing |
| REQ-L2-AS-040 | Atomare Event-Bus Claims & DLQ-Moves | — | Planned | Untested |
| REQ-L2-AS-041 | Service-Level Autorisierung (RBAC & Tenant) | — | Planned | Untested |
| REQ-L2-AS-042 | Konsistente Fachlogik & Bugfixes | — | Planned | Untested |
| REQ-L2-AS-043 | Resilienz bei Drittsystemen (LLM & Webhooks) | — | Planned | Untested |
| REQ-L2-AS-044 | Exporte und Datenkonsistenz | — | Planned | Untested |

### 3.3 AuditLogSystem (9 REQ-L2 → 3 Komponenten, 12 REQ-L3)

*Komponenten:* COMP-AL-001 (AuditLogWriter), COMP-AL-002 (AuditLogQuery), COMP-AL-003 (ArchiveLifecycleManager)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-AL-001 | Vollständige Audit-Einträge für alle Schreiboperationen | COMP-AL-001 | Implemented | Covered |
| REQ-L2-AL-002 | MCP-Audit-Anreicherung mit Agent-Identität und API-Key-Hash | COMP-AL-001 | Implemented | Covered |
| REQ-L2-AL-003 | Unveränderlichkeit des Audit-Logs (Append-Only) | COMP-AL-001 | Implemented | Covered |
| REQ-L2-AL-004 | Atomare Konsistenz mit auslösender Operation | COMP-AL-001 | Implemented | Covered |
| REQ-L2-AL-005 | Query- und Retrieval-Fähigkeit | COMP-AL-002 | Implemented | Untested |
| REQ-L2-AL-006 | Tenant-Isolation für Audit-Einträge | COMP-AL-001, COMP-AL-002 | Implemented | Covered |
| REQ-L2-AL-007 | Performance-Anforderungen | COMP-AL-002 | Implemented | Untested |
| REQ-L2-AL-008 | Table-Partitionierung der Audit-Tabelle | COMP-AL-001 | Implemented | Untested |
| REQ-L2-AL-009 | Cold-Storage-Archivierung (Datenlebenszyklus) | COMP-AL-003 | Implemented | Untested |

### 3.4 AuthAndTenancySystem (20 REQ-L2 → 6 Komponenten, 15 REQ-L3)

*Komponenten:* COMP-AT-001 (AuthenticationService), COMP-AT-002 (AuthorizationService), COMP-AT-003 (TenantContextService), COMP-AT-004 (CredentialAuthenticationService), COMP-AT-005 (ItemPermissionStore) ⚠ nur Verzeichnis, COMP-AT-006 (TokenService) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-AT-001 | Bearer Token Authentication | COMP-AT-001 | Implemented | Covered |
| REQ-L2-AT-002 | API Key Authentication | COMP-AT-001 | Implemented | Missing |
| REQ-L2-AT-003 | Role-Based Permission Enforcement | COMP-AT-002 | Implemented | Missing |
| REQ-L2-AT-004 | Approver Role Preset Restriction | COMP-AT-002 | Implemented | Missing |
| REQ-L2-AT-005 | Authentication Context Propagation | COMP-AT-003 | Implemented | Missing |
| REQ-L2-AT-006 | Role Assignment Management | COMP-AT-002 | Implemented | Missing |
| REQ-L2-AT-007 | Auth Middleware Interception | COMP-AT-001 | Implemented | Missing |
| REQ-L2-AT-008 | Tenant Extraction and Propagation | COMP-AT-003 | Implemented | Covered |
| REQ-L2-AT-009 | API Key Lifecycle Management | COMP-AT-001 | Implemented | Missing |
| REQ-L2-AT-010 | Authentication Failure Response Standardization | COMP-AT-001 | Implemented | Covered |
| REQ-L2-AT-011 | Credential Verification (Constant-Time) | COMP-AT-004 | Implemented | Covered |
| REQ-L2-AT-012 | Token Issuance — BearerTokenAuthentication-Kompatibilität | COMP-AT-004 | Implemented | Covered |
| REQ-L2-AT-013 | Public Login Endpoint Exemption | COMP-AT-004 | Implemented | Covered |
| REQ-L2-AT-014 | Password Hash Storage Contract | COMP-AT-004 | Implemented | Covered |
| REQ-L2-AT-015 | Self-Identity Endpoint (Session Bootstrap) | COMP-AT-001, COMP-AT-003 | Implemented | Covered |
| REQ-L2-AT-016 | No Account Enumeration | COMP-AT-004 | Implemented | Covered |
| REQ-L2-AT-017 | Item-Level-RBAC Regelverwaltung | — | Implemented | Covered |
| REQ-L2-AT-018 | Item-Level Permission Enforcement | — | Not Implemented | Missing |
| REQ-L2-AT-019 | (NEU): Item-Level-Berechtigungs-UI (Admin-Oberfläche) | — | Not Implemented | Missing |
| REQ-L2-AT-020 | Persistierung und Validierung von PATs | COMP-AT-006 (via L3) | Not Implemented | Missing |

### 3.5 BaselineServiceSystem (12 REQ-L2 → 4 Komponenten, 15 REQ-L3)

*Komponenten:* COMP-BL-001 (DeltaIndexBuilder), COMP-BL-002 (DiffEngine), COMP-BL-003 (BaselineStore), COMP-BL-004 (VersionReconstructor)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-BL-001 | Baseline Scope Resolution and Delta Storage | COMP-BL-001 | Implemented | Covered |
| REQ-L2-BL-002 | Baseline Immutability | COMP-BL-003 | Implemented | Covered |
| REQ-L2-BL-003 | Baseline Diff (Vergleich) | COMP-BL-002 | Implemented | Covered |
| REQ-L2-BL-004 | Preset Gate — Scope Availability | COMP-BL-001 | Implemented | Covered |
| REQ-L2-BL-005 | Baseline Naming and Metadata | COMP-BL-001 | Implemented | Covered |
| REQ-L2-BL-006 | Baseline Retrieval and Listing | COMP-BL-003 | Implemented | Covered |
| REQ-L2-BL-007 | Atomic Creation with Transactional Guarantees | COMP-BL-003 | Implemented | Covered |
| REQ-L2-BL-008 | Baseline Creation Performance | COMP-BL-001, COMP-BL-002, COMP-BL-003 | Not Implemented | Missing |
| REQ-L2-BL-009 | Baseline-Rekonstruktion aus Versionshistorie | COMP-BL-004 | Implemented | Covered |
| REQ-L2-BL-010 | Artefakt-Branching & Merging (Sandbox-Zweige) | — | Not Implemented | Missing |
| REQ-L2-BL-011 | Instanz-Backup, Full Restore & Baseline-Soft-Restore | — | Not Implemented | Missing |
| REQ-L2-BL-012 | Baseline Full-State-Snapshot in BaselineDeltaIndexEntry | COMP-BL-001 | Not Implemented | Missing |

### 3.6 CommentServiceSystem (3 REQ-L2 → 3 Komponenten, 0 REQ-L3)

*Komponenten:* COMP-CM-001 (CommentManager) ⚠ nur Verzeichnis, COMP-CM-002 (MentionResolver) ⚠ nur Verzeichnis, COMP-CM-003 (NotificationDispatcher) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-CM-001 | Kommentar-CRUD mit Thread-Struktur | — | Not Implemented | Missing |
| REQ-L2-CM-002 | @Mention-Auflösung | — | Not Implemented | Missing |
| REQ-L2-CM-003 | In-App-Notification-Dispatch | — | Not Implemented | Missing |

### 3.7 DiagramServiceSystem (12 REQ-L2 → 7 Komponenten, 13 REQ-L3)

*Komponenten:* COMP-DS-001 (DiagramManager), COMP-DS-002 (DiagramValidator), COMP-DS-003 (DiagramRenderer), COMP-DS-004 (TraceabilityConnector), COMP-DS-005 (McpArtifactProvider), COMP-DS-006 (CanvasEditor), COMP-DS-007 (MermaidLiveRenderer)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-DS-001 | Diagramm CRUD und Versionierung | COMP-DS-001 | Implemented | Covered |
| REQ-L2-DS-002 | Strukturierte Payload-Validierung | COMP-DS-002 | Implemented | Covered |
| REQ-L2-DS-003 | Renderbare Repräsentation | COMP-DS-003 | Implemented | Covered |
| REQ-L2-DS-004 | Traceability-Verknüpfung (Typ: documents) | COMP-DS-004 | Implemented | Covered |
| REQ-L2-DS-005 | MCP-Tool Integration | COMP-DS-005 | Implemented | Covered |
| REQ-L2-DS-006 | Free-Hand Canvas Drawing | COMP-DS-006 | Implemented | Covered |
| REQ-L2-DS-007 | Mermaid Live Preview | COMP-DS-007 | Implemented | Covered |
| REQ-L2-DS-008 | Canvas — Rechteck-Werkzeug | COMP-DS-006 | Implemented | (kein Marker) |
| REQ-L2-DS-009 | Canvas — Ellipsen-Werkzeug | COMP-DS-006 | Implemented | (kein Marker) |
| REQ-L2-DS-010 | Canvas — Text-Label-Werkzeug | COMP-DS-006 | Implemented | (kein Marker) |
| REQ-L2-DS-011 | Canvas — Verbindungslinien (Pfeile) zwischen Objekten | COMP-DS-006 | Implemented | (kein Marker) |
| REQ-L2-DS-012 | Canvas — Persistenz-Migration auf fabric.js-Canvas-JSON | COMP-DS-006 | Implemented | (kein Marker) |

### 3.8 IcdManagementSystem (6 REQ-L2 → 4 Komponenten, 8 REQ-L3)

*Komponenten:* COMP-ICD-001 (IcdManager), COMP-ICD-002 (ContractValidator), COMP-ICD-003 (TraceabilityConnector), COMP-ICD-004 (AuditLogger)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-ICD-001 | ICD CRUD und Versionierung | COMP-ICD-001 | Implemented | Covered |
| REQ-L2-ICD-002 | Design-by-Contract Modellierung | COMP-ICD-002 | Implemented | Covered |
| REQ-L2-ICD-003 | Breaking-Change Erkennung | COMP-ICD-002 | Implemented | Covered |
| REQ-L2-ICD-004 | Traceability-Verknüpfung (Typ: realizes) | COMP-ICD-003 | Implemented | Covered |
| REQ-L2-ICD-005 | Baseline-Integration | COMP-ICD-001 | Implemented | Covered |
| REQ-L2-ICD-006 | Audit-Logging für Breaking Changes | COMP-ICD-004 | Implemented | Covered |

### 3.9 LlmAdapterSystem (10 REQ-L2 → 5 Komponenten, 19 REQ-L3)

*Komponenten:* COMP-LA-001 (CapabilityInterface), COMP-LA-002 (ProviderRegistry), COMP-LA-003 (CapabilityRouter), COMP-LA-004 (LlmAuditLogger), COMP-LA-005 (AsyncTaskDispatcher)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-LA-001 | LLM-Capability-Interface mit Provider-Abstraktion | COMP-LA-001, COMP-LA-002 | Implemented | Covered |
| REQ-L2-LA-002 | Graceful Degradation bei fehlender LLM-Konfiguration | COMP-LA-003 | Implemented | Covered |
| REQ-L2-LA-003 | Selektive Capability-Aktivierung | COMP-LA-003 | Implemented | Covered |
| REQ-L2-LA-004 | Standardisiertes LLM-Ergebnisformat | COMP-LA-001 | Implemented | Covered |
| REQ-L2-LA-005 | Provider-Fehlerbehandlung und Timeout | COMP-LA-002, COMP-LA-003 | Implemented | Covered |
| REQ-L2-LA-006 | LLM-Audit-Logging | COMP-LA-004 | Implemented | Covered |
| REQ-L2-LA-007 | Azure-OpenAI Provider-Unterstützung | COMP-LA-002 | Implemented | Missing |
| REQ-L2-LA-008 | Asynchrone LLM-Task-Ausführung via Celery | COMP-LA-005 | Implemented | Covered |
| REQ-L2-LA-009 | LlmSettings — Mandanten-konfigurierbarer LLM-Provider | COMP-LA-002, COMP-LA-003 | Not Implemented | (kein Marker) |
| REQ-L2-LA-010 | PromptTemplate — Admin-editierbare Prompt-Slots | COMP-LA-001, COMP-LA-003 | Not Implemented | (kein Marker) |

### 3.10 McpServerSystem (21 REQ-L2 → 7 Komponenten, 24 REQ-L3)

*Komponenten:* COMP-MC-001 (ProtocolHandler), COMP-MC-002 (ToolRegistry), COMP-MC-003 (RequirementsToolGroup), COMP-MC-004 (ArchitectureToolGroup), COMP-MC-005 (TestToolGroup), COMP-MC-006 (CrossCuttingToolGroup), COMP-MC-007 (GenericCrudToolGroup)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-MC-001 | (kein `###`-Block im Quelldokument) | COMP-MC-003 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-002 | (kein `###`-Block im Quelldokument) | COMP-MC-004 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-003 | (kein `###`-Block im Quelldokument) | COMP-MC-005 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-004 | (kein `###`-Block im Quelldokument) | COMP-MC-006 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-005 | (kein `###`-Block im Quelldokument) | COMP-MC-001 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-006 | (kein `###`-Block im Quelldokument) | COMP-MC-001, COMP-MC-002 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-007 | (kein `###`-Block im Quelldokument) | COMP-MC-002 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-008 | (kein `###`-Block im Quelldokument) | COMP-MC-002 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-009 | (kein `###`-Block im Quelldokument) | COMP-MC-003 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-010 | (kein `###`-Block im Quelldokument) | COMP-MC-001 (via L3) | (kein Marker) | (kein Marker) |
| REQ-L2-MC-011 | (kein `###`-Block im Quelldokument) | COMP-MC-001, COMP-MC-002 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-012 | (kein `###`-Block im Quelldokument) | COMP-MC-003 | (kein Marker) | (kein Marker) |
| REQ-L2-MC-013 | (kein `###`-Block im Quelldokument) | — | (kein Marker) | (kein Marker) |
| REQ-L2-MC-014 | MCP-Tool `semantic_search` (Semantische Suche für AI-Agenten) | — | Implemented | Covered |
| REQ-L2-MC-015 | MCP-Tool `record_test_result` (Testergebnis-Einspeisung) | — | Implemented | Covered |
| REQ-L2-MC-016 | System Info Tool (Announcement) | COMP-MC-006 (via L3) | Implemented | Covered |
| REQ-L2-MC-017 | MCP Security & Secret Management | — | Planned | Untested |
| REQ-L2-MC-018 | MCP RBAC & Rate-Limiting | — | Planned | Untested |
| REQ-L2-MC-019 | MCP Protocol Compliance & Schemas | — | Planned | Untested |
| REQ-L2-MC-020 | MCP Performance & Concurrency | — | Planned | Untested |
| REQ-L2-MC-021 | MCP Audit Logging für Needs | — | Planned | Untested |

### 3.11 PersistenceLayerSystem (15 REQ-L2 → 6 Komponenten, 20 REQ-L3)

*Komponenten:* COMP-PL-001 (EntitySchemaManager), COMP-PL-002 (TenantIsolationManager), COMP-PL-003 (TransactionCoordinator), COMP-PL-004 (SchemaMigrationEngine), COMP-PL-005 (PerformanceOptimizationLayer), COMP-PL-006 (RLSPolicyEnforcer)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-PL-001 | Tenant-Isolation via Custom Django Manager | COMP-PL-002 | Implemented | Covered |
| REQ-L2-PL-002 | Transaktionale Konsistenz (ACID) | COMP-PL-003 | Implemented | Covered |
| REQ-L2-PL-003 | Performance-Indizes | COMP-PL-005 | Implemented | Covered |
| REQ-L2-PL-004 | Vollständigkeit des Entity-Schemas | COMP-PL-001 | Implemented | Covered |
| REQ-L2-PL-005 | Audit-Felder auf allen schreibbaren Entitäten | COMP-PL-001 | Implemented | Covered |
| REQ-L2-PL-006 | Idempotente Datenbank-Migrationen | COMP-PL-004 | Implemented | Covered |
| REQ-L2-PL-007 | Datenbankverbindungs-Pooling | COMP-PL-005 | Not Implemented | Missing |
| REQ-L2-PL-008 | Performance-Latenzziele | COMP-PL-005 | Implemented | Missing |
| REQ-L2-PL-009 | Referentielle Integrität | COMP-PL-001 | Implemented | Covered |
| REQ-L2-PL-010 | PostgreSQL Row-Level Security (RLS) | COMP-PL-006 | Implemented | Covered |
| REQ-L2-PL-011 | Datenbankverbindungs-Pooling (Connection-Pool-Konfiguration) | — | Not Implemented | Missing |
| REQ-L2-PL-012 | Vollständige Tenant-Isolation | — | Planned | Untested |
| REQ-L2-PL-013 | Datenbank-Migrationen & Konsistenz | — | Planned | Untested |
| REQ-L2-PL-014 | Datenbank-Performance & Indizes | — | Planned | Untested |
| REQ-L2-PL-015 | Modell-Konsolidierung & Typisierung | — | Planned | Untested |

### 3.12 PresetConfigEngineSystem (14 REQ-L2 → 3 Komponenten, 11 REQ-L3)

*Komponenten:* COMP-PC-001 (PresetRegistry), COMP-PC-002 (TerminologyProfileService), COMP-PC-003 (FeatureGateService)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-PC-001 | Preset-Verwaltung (Minimal / Standard / Extended) | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-002 | Feature-Query-Interface | COMP-PC-003 | Implemented | Covered |
| REQ-L2-PC-003 | Preset-Query-Interface | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-004 | Pflichtfeld-Regeln pro Preset | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-005 | Baseline-Scope-Verfügbarkeit pro Preset | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-006 | Workflow-Konfigurierbarkeits-Regeln pro Preset | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-007 | Change-Reason-Pflicht-Regeln pro Preset | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-008 | Preset-Wechsel aufsteigend ohne Datenmigration | COMP-PC-003 | Implemented | Covered |
| REQ-L2-PC-009 | Terminologie-Profil-Verwaltung (Dev-Modus / SE-Modus) | COMP-PC-002 | Implemented | Covered |
| REQ-L2-PC-010 | Terminologie-Profil-Wechsel ohne Datenmigration | COMP-PC-002 | Implemented | Covered |
| REQ-L2-PC-011 | Preset-Downgrade-Validierung | COMP-PC-003 | Implemented | Covered |
| REQ-L2-PC-012 | Default-Preset-Immutabilität | COMP-PC-001 | Implemented | Covered |
| REQ-L2-PC-013 | Preset-Query-Performance | COMP-PC-003 | Implemented | Covered |
| REQ-L2-PC-014 | Benutzerdefinierte Presets (Extended-Modus) | COMP-PC-001 | Implemented | Covered |

### 3.13 ReactFrontendSystem (35 REQ-L2 → 10 Komponenten, 24 REQ-L3)

*Komponenten:* COMP-RF-001 (NavigationShell), COMP-RF-002 (DashboardViews), COMP-RF-003 (RequirementEditors), COMP-RF-004 (ArchitectureEditors), COMP-RF-005 (TraceabilityViews), COMP-RF-006 (I18nService), COMP-RF-007 (SystemAnnouncementBanner) ⚠ nur Verzeichnis, COMP-RF-008 (HierarchyTreeView) ⚠ nur Verzeichnis, COMP-RF-009 (SplitViewLayout) ⚠ nur Verzeichnis, COMP-RF-010 (ListToolbar) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-RF-001 | Frontend-i18n mit react-i18next (DE/EN) | COMP-RF-006 | Implemented | Missing |
| REQ-L2-RF-002 | Dashboard mit Projektübersicht und Offenen Punkten | COMP-RF-002 | Implemented | Covered |
| REQ-L2-RF-003 | Requirements-Editor mit Inline-Editing und Markdown | COMP-RF-003 | Implemented | Covered |
| REQ-L2-RF-004 | Architecture-Editor | COMP-RF-004 | Implemented | Covered |
| REQ-L2-RF-005 | Artefakt-Navigation als Baumstruktur | COMP-RF-001 | Implemented | Covered |
| REQ-L2-RF-006 | Traceability-Anzeige | COMP-RF-005 | Implemented | Covered |
| REQ-L2-RF-007 | Preset-basierte UI-Sichtbarkeit | COMP-RF-001 | Implemented | Covered |
| REQ-L2-RF-008 | Terminologie-Profil-Rendering (Dev-Modus / SE-Modus) | COMP-RF-006 | Implemented | Covered |
| REQ-L2-RF-009 | UI-Performance | COMP-RF-001 | Implemented | Missing |
| REQ-L2-RF-010 | REST-API-Kommunikation mit Bearer-Token-Authentifizierung | COMP-RF-001 | Implemented | Covered |
| REQ-L2-RF-011 | Fehleranzeige und Backend-Error-Rendering | COMP-RF-001 | Implemented | Missing |
| REQ-L2-RF-012 | Workspace-Konfigurations-UI | COMP-RF-001 | Implemented | Covered |
| REQ-L2-RF-014 | Visuelles Artefakt-Diff | — | Implemented | Covered |
| REQ-L2-RF-015 | Visuelles Baseline-Diff | — | Not Implemented | Missing |
| REQ-L2-RF-016 | Flat View & Level View (Multi-View-Artefaktansicht) | — | Implemented | Covered |
| REQ-L2-RF-017 | Sandbox-Diff-UI & Baseline-Vergleich | — | Not Implemented | Missing |
| REQ-L2-RF-018 | Frontend Level-View (Requirements Hierarchy) | — | Backlog | Missing |
| REQ-L2-RF-019 | Pagination und API-State in Listen-Komponenten | — | Backlog | Missing |
| REQ-L2-RF-020 | Wiederverwendbare ListToolbar (Search, Filter, Sort) | — | Backlog | Missing |
| REQ-L2-RF-021 | Hierarchische Darstellung (Tree-View-Modus) | — | Backlog | Missing |
| REQ-L2-RF-022 | WebGL-basierter Interaktiver Node-Graph | — | Backlog | Missing |
| REQ-L2-RF-023 | Traceability Matrix (TRM) Ansicht | — | Backlog | Missing |
| REQ-L2-RF-024 | Split-Screen Context Panel & KI-Chat | — | Backlog | Missing |
| REQ-L2-RF-025 | Dynamische UI-Masken für Artefakt-Typen | COMP-RF-003, COMP-RF-004 (via L3) | Backlog | Missing |
| REQ-L2-RF-026 | UI-Feedback für Guardrail-Fehler (Stage-Gating) | COMP-RF-005 (via L3) | Backlog | Missing |
| REQ-L2-RF-028 | Globales System Announcement Banner | COMP-RF-007 (via L3) | Not Implemented | Missing |
| REQ-L2-RF-029 | Hierarchy Tree-View Component | COMP-RF-008 (via L3) | Not Implemented | Missing |
| REQ-L2-RF-030 | Split-View Layout Component | COMP-RF-009 (via L3) | Not Implemented | Missing |
| REQ-L2-RF-031 | Reusable List-Toolbar | COMP-RF-010 (via L3) | Not Implemented | Missing |
| REQ-L2-RF-032 | Markdown Glossary Tooltips | COMP-RF-003 (via L3) | Not Implemented | Missing |
| REQ-L2-RF-033 | Workspace-spezifische KI-Prompts Konfigurations-UI | — | Not Implemented | Missing |
| REQ-L2-RF-034 | RightSidebar Shell Component (ArtifactInspector) | — | Not Implemented | Missing |
| REQ-L2-RF-035 | VersionPanel Component | — | Not Implemented | Missing |
| REQ-L2-RF-036 | DiffPanel Component (field-level diff) | — | Not Implemented | Missing |
| REQ-L2-RF-037 | TracePanel Component (inbound/outbound links, type filter) | — | Not Implemented | Missing |

### 3.14 ReqIFServiceSystem (2 REQ-L2 → 2 Komponenten, 0 REQ-L3)

*Komponenten:* COMP-RQ-001 (ReqIFParser) ⚠ nur Verzeichnis, COMP-RQ-002 (ReqIFSerializer) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-RQ-001 | ReqIF-Import | — | Not Implemented | Missing |
| REQ-L2-RQ-002 | ReqIF-Export | — | Not Implemented | Missing |

### 3.15 ResilienceOrchestratorSystem (6 REQ-L2 → 5 Komponenten, 16 REQ-L3)

*Komponenten:* COMP-RO-001 (AsyncDispatcher), COMP-RO-002 (PolicyEngine), COMP-RO-003 (CircuitBreaker), COMP-RO-004 (DegradationManager), COMP-RO-005 (ResilienceAuditLogger)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-RO-001 | Asynchrone Entkopplung | COMP-RO-001 | Implemented | Covered |
| REQ-L2-RO-002 | Konfigurierbare Timeouts | COMP-RO-002 | Implemented | Covered |
| REQ-L2-RO-003 | Retry-Logik mit Exponential Backoff | COMP-RO-002 | Implemented | Covered |
| REQ-L2-RO-004 | Circuit-Breaker-Logik | COMP-RO-003 | Implemented | Covered |
| REQ-L2-RO-005 | Graceful Degradation und Kernverfügbarkeit | COMP-RO-004 | Implemented | Covered |
| REQ-L2-RO-006 | Audit-Logging für Resilienz-Events | COMP-RO-005 | Implemented | Covered |

### 3.16 RestApiAdapterSystem (27 REQ-L2 → 8 Komponenten, 27 REQ-L3)

*Komponenten:* COMP-RA-001 (HttpEndpointController), COMP-RA-002 (DataSerializer), COMP-RA-003 (AuthEnforcer), COMP-RA-004 (PresetGuard), COMP-RA-005 (OpenApiGenerator), COMP-RA-006 (QuerysetOptimizer), COMP-RA-007 (TokenEndpoints) ⚠ nur Verzeichnis, COMP-RA-008 (SystemSettingsEndpoints) ⚠ nur Verzeichnis

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-RA-001 | REST-CRUD-Endpunkte für alle Entitäten | COMP-RA-001, COMP-RA-002 | Implemented | Covered |
| REQ-L2-RA-002 | Auto-generierte OpenAPI-Spezifikation | COMP-RA-005 | Implemented | Covered |
| REQ-L2-RA-003 | API-Response-Performance unter 200ms | COMP-RA-001, COMP-RA-002 | Implemented | Untested |
| REQ-L2-RA-004 | Backend-Fehlermeldungen i18n (DE/EN) | COMP-RA-002 | Implemented | Covered |
| REQ-L2-RA-005 | Bearer-Token-Authentifizierung für alle Endpunkte | COMP-RA-003 | Implemented | Covered |
| REQ-L2-RA-006 | RBAC-Enforcement auf API-Ebene | COMP-RA-003 | Implemented | Covered |
| REQ-L2-RA-007 | Audit-Log-Auslösung bei Schreiboperationen | COMP-RA-001 | Implemented | Untested |
| REQ-L2-RA-008 | Preset-basierte Endpunkt- und Feldsichtbarkeit | COMP-RA-002, COMP-RA-004 | Implemented | Covered |
| REQ-L2-RA-009 | Standardisierte HTTP-Fehlercodes und Response-Format | COMP-RA-001, COMP-RA-002 | Implemented | Covered |
| REQ-L2-RA-010 | Pagination, Filtering, Sorting für Listen-Endpunkte | COMP-RA-002 | Implemented | Covered |
| REQ-L2-RA-011 | Tenant-Kontext-Propagation | COMP-RA-003 | Implemented | Covered |
| REQ-L2-RA-012 | Keine Geschäftslogik in der Adapter-Schicht | COMP-RA-001, COMP-RA-002 | Implemented | Untested |
| REQ-L2-RA-013 | N+1-Query-Vermeidung bei verschachtelten Responses | COMP-RA-006 | Implemented | Covered |
| REQ-L2-RA-014 | REST-Endpunkte für Semantisches Projekt-Glossar | — | Not Implemented | Missing |
| REQ-L2-RA-015 | REST-Endpunkte für Semantische Suche und Hybrid-Suche | — | Not Implemented | Missing |
| REQ-L2-RA-016 | REST-Endpunkte mit serverseitiger Paginierung | — | Not Implemented | Missing |
| REQ-L2-RA-017 | REST-Endpunkte mit serverseitigem Filter & Sort | — | Not Implemented | Missing |
| REQ-L2-RA-018 | GraphQL Endpoint für Traceability-Queries | — | Deferred | Missing |
| REQ-L2-RA-019 | REST-Schema-Validierung für domänenspezifische Felder | COMP-RA-002 (via L3) | Not Implemented | Missing |
| REQ-L2-RA-020 | API State Machine & Guardrails Enforcer | COMP-RA-006 (via L3) | Not Implemented | Missing |
| REQ-L2-RA-022 | System Announcement API | COMP-RA-008 (via L3) | Not Implemented | Missing |
| REQ-L2-RA-023 | Global Glossary API | — | Not Implemented | Missing |
| REQ-L2-RA-024 | REST API Security & Ownership Checks | — | Planned | Untested |
| REQ-L2-RA-025 | REST API Data Integrity (No DDL in Handlers) | — | Planned | Untested |
| REQ-L2-RA-026 | REST API Query Performance | — | Planned | Untested |
| REQ-L2-RA-027 | OpenAPI Spec & Error Consistency | — | Planned | Untested |
| REQ-L2-RA-028 | API Filter & Search Fields Declaration | — | Planned | Untested |

### 3.17 SeMetricsSystem (13 REQ-L2 → 9 Komponenten, 13 REQ-L3)

*Komponenten:* COMP-SM-001 (MetricsQueryController), COMP-SM-002 (MetricsAggregator), COMP-SM-003 (VolatilityCalculator), COMP-SM-004 (CoverageCalculator), COMP-SM-005 (WorkflowGapDetector), COMP-SM-006 (RiskClassifier), COMP-SM-007 (ThresholdEvaluator), COMP-SM-008 (MetricsCacheManager), COMP-SM-009 (CeleryMetricsBeatWorker)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-SM-001 | REST-Endpunkt GET /metrics/workspace/{id} | COMP-SM-001, COMP-SM-002 | Implemented | Covered |
| REQ-L2-SM-002 | Zeitraum- und Scope-Filter | COMP-SM-001 | Implemented | Covered |
| REQ-L2-SM-003 | Requirements-Volatility-Berechnung | COMP-SM-003 | Implemented | Covered |
| REQ-L2-SM-004 | Traceability-Coverage-Berechnung | COMP-SM-004 | Implemented | Covered |
| REQ-L2-SM-005 | Workflow-Lücken-Erkennung | COMP-SM-005 | Implemented | Covered |
| REQ-L2-SM-006 | Offene Risiken nach Schweregrad | COMP-SM-006 | Implemented | Covered |
| REQ-L2-SM-007 | Konfigurierbare Schwellwert-Warnungen | COMP-SM-007, COMP-SM-008 | Implemented | Covered |
| REQ-L2-SM-008 | Read-Modell ohne Seiteneffekte | COMP-SM-002, COMP-SM-003, COMP-SM-004, COMP-SM-005, COMP-SM-006 | Implemented | Covered |
| REQ-L2-SM-009 | Optionale Metric-Cache-Persistenz mit proaktiver Vorberechnung | COMP-SM-008, COMP-SM-009 | Implemented | Covered |
| REQ-L2-SM-010 | Tenant-Isolation für alle Metrik-Abfragen | COMP-SM-001 | Implemented | Covered |
| REQ-L2-SM-011 | Metrik-Antwort-Performance-SLA | COMP-SM-002, COMP-SM-008 | Implemented | Covered |
| REQ-L2-SM-012 | Strukturiertes JSON-Antwortformat | COMP-SM-001 | Implemented | Covered |
| REQ-L2-SM-013 | Thundering-Herd-Prevention bei Cache-Miss | COMP-SM-008, COMP-SM-009 | Implemented | Covered |

### 3.18 TraceabilityEngineSystem (20 REQ-L2 → 4 Komponenten, 13 REQ-L3)

*Komponenten:* COMP-TE-001 (TraceLinkManager), COMP-TE-002 (QueryEngine), COMP-TE-003 (CoverageCalculator), COMP-TE-004 (VCRMReportGenerator)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-TE-001 | TraceLink-Verwaltung mit 6 Link-Typen | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-002 | Zyklenprävention für alle transitiven Link-Typen | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-003 | Atomare Batch-Operationen für TraceLinks mit globaler Zyklenprüfung | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-004 | Upstream/Downstream-Graph-Query | COMP-TE-002 | Implemented | Covered |
| REQ-L2-TE-005 | Transitive Hüllen-Query (Impact-Analyse) | COMP-TE-002 | Implemented | Covered |
| REQ-L2-TE-006 | Coverage-Berechnung (Requirement → Test-Abdeckung) | COMP-TE-003 | Implemented | Covered |
| REQ-L2-TE-007 | Coverage-Filterung nach Artefakttyp und Link-Typ | COMP-TE-003 | Implemented | Covered |
| REQ-L2-TE-008 | Trace-Graph-Sammlung für Baseline-Snapshot | COMP-TE-002 | Implemented | Covered |
| REQ-L2-TE-009 | Referentielle Integrität bei Artefakt-Löschung | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-010 | TraceLink-Audit-Metadaten | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-011 | Tenant-Isolation für alle TraceLink-Operationen | COMP-TE-001 | Implemented | Covered |
| REQ-L2-TE-012 | TraceLink-Query-Performance-SLA | COMP-TE-001, COMP-TE-002, COMP-TE-003 | Implemented | Covered |
| REQ-L2-TE-013 | Verification Cross Reference Matrix (VCRM) Report-Generator | COMP-TE-004 | Implemented | Covered |
| REQ-L2-TE-014 | Cross-Projekt-Link-CRUD | — | Not Implemented | Missing |
| REQ-L2-TE-015 | Cross-Projekt-Graph-Query | — | Implemented | Untested |
| REQ-L2-TE-016 | Suspect-Link-Propagation Engine | COMP-TE-001 | Not Implemented | Missing |
| REQ-L2-TE-017 | Cross-Level-TraceLink-Typ mit Begründungspflicht | COMP-TE-001 | Not Implemented | Missing |
| REQ-L2-TE-018 | TraceLink allocated-to + Allocation-Coverage Reporter | COMP-TE-001, COMP-TE-003 | Backlog | Missing |
| REQ-L2-TE-019 | TraceLink Read-Model mit rekursiven CTE-Abfragen | COMP-TE-002 | Not Implemented | Missing |
| REQ-L2-TE-020 | ADR ↔ ArchitectureElement TraceLink | COMP-TE-001 | Not Implemented | (kein Marker) |

### 3.19 VectorSearchServiceSystem (4 REQ-L2 → 3 Komponenten, 0 REQ-L3)

*Komponenten:* COMP-VS-001 (VectorSearchEngine), COMP-VS-002 (EmbeddingPipeline), COMP-VS-003 (HybridQueryRouter)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-VS-001 | Semantische Vektorsuche | COMP-VS-001 | Not Implemented | Missing |
| REQ-L2-VS-002 | Embedding-Pipeline | COMP-VS-002 | Not Implemented | Missing |
| REQ-L2-VS-003 | Hybrid-Suche (Vektor + Volltext) | COMP-VS-003 | Not Implemented | Missing |
| REQ-L2-VS-004 | pgvector-Extension und Embedding-Datenmodell | COMP-VS-001, COMP-VS-002 | Not Implemented | Missing |

### 3.20 WorkflowEngineSystem (9 REQ-L2 → 4 Komponenten, 13 REQ-L3)

*Komponenten:* COMP-WE-001 (WorkflowDefinitionStore), COMP-WE-002 (TransitionValidator), COMP-WE-003 (StateLifecycleManager), COMP-WE-004 (SignatureGateVerifier)

| REQ-L2 | Titel | Komponente(n) | Impl. State | Test Status |
|--------|-------|---------------|-------------|-------------|
| REQ-L2-WE-001 | Transition Validation | COMP-WE-002 | Implemented | Covered |
| REQ-L2-WE-002 | WorkflowDefinition Management | COMP-WE-001 | Implemented | Covered |
| REQ-L2-WE-003 | WorkflowState History (Audit-Trail) | COMP-WE-003 | Implemented | Covered |
| REQ-L2-WE-004 | Workflow Migration on Definition Change | COMP-WE-001 | Implemented | Covered |
| REQ-L2-WE-005 | Workflow State Initialization | COMP-WE-003 | Implemented | Covered |
| REQ-L2-WE-006 | Tenant-Scoped Workflow Data Isolation | COMP-WE-003 | Implemented | Covered |
| REQ-L2-WE-007 | Preset-Downgrade Behavior | COMP-WE-001 | Implemented | Covered |
| REQ-L2-WE-008 | Transition Performance | COMP-WE-002 | Implemented | Covered |
| REQ-L2-WE-009 | SignatureGate — Credential-Verifizierung | COMP-WE-004 | Implemented | Covered |

---

## 4. Coverage Summary

> *Zerlegt* = mindestens ein Kind-Requirement der naechsten Ebene verweist per
> `**Traceability:**` zurueck. *Parent-Link* = das Requirement deklariert selbst
> mindestens einen Parent. Beides misst die **Dokumentations**-Traceability, nicht
> die Implementierung.
>
> Der niedrige Zerlegungsgrad auf REQ-L2 ist erwartbar: die meisten L2-Systeme
> sind als Leaf-AE deklariert (*keine L3-Zerlegung*), REQ-L3 existiert nur fuer
> die tatsaechlich weiter zerlegten Komponenten.

| Ebene | Gesamt | mit Parent-Link | zerlegt (Kind-Links) | Zerlegungsgrad |
|-------|--------|-----------------|----------------------|----------------|
| REQ-L0 (Stakeholder Needs) | 58 | — | 53 | 91% |
| REQ-L1 (System) | 94 | 86 | 59 | 63% |
| REQ-L2 (Subsystem) | 290 | 232 | 34 | 12% |
| REQ-L3 (Komponente) | 369 | 116 | — | — |
| Components (COMP-*) | 116 | 106 | — | 91% |

### 4.1 Implementation State (aus den Quelldokumenten uebernommen)

| Ebene | Implemented | Not Implemented | Planned | Backlog | In Progress | Teilweise Implementiert | Deferred | Sonstige (Freitext) | (kein Marker) | Summe |
|---|---|---|---|---|---|---|---|---|---|---|
| REQ-L0 (Stakeholder Needs) | 8 | 47 | 0 | 0 | 0 | 2 | 0 | 1 | 0 | 58 |
| REQ-L1 (System) | 40 | 23 | 4 | 23 | 1 | 0 | 2 | 1 | 0 | 94 |
| REQ-L2 (Subsystem) | 181 | 61 | 19 | 15 | 0 | 0 | 1 | 0 | 13 | 290 |
| REQ-L3 (Komponente) | 221 | 114 | 22 | 0 | 0 | 0 | 0 | 2 | 10 | 369 |

> Die Marker werden **unveraendert** aus den Requirement-Dokumenten uebernommen. Ob ein Marker den tatsaechlichen Code-Stand trifft, prueft dieses Skript nicht.

### 4.2 Test Status (aus den Quelldokumenten uebernommen)

| Ebene | Covered | Missing | Untested | Sonstige (Freitext) | (kein Marker) | Summe |
|---|---|---|---|---|---|---|
| REQ-L0 (Stakeholder Needs) | 4 | 52 | 0 | 2 | 0 | 58 |
| REQ-L1 (System) | 30 | 60 | 4 | 0 | 0 | 94 |
| REQ-L2 (Subsystem) | 152 | 88 | 27 | 0 | 23 | 290 |
| REQ-L3 (Komponente) | 146 | 168 | 22 | 0 | 33 | 369 |

### 4.3 System-Zusammenfassung

| System | REQ-L2 | Komponenten | REQ-L3 | REQ-L2 Implemented | REQ-L2 Test Covered |
|--------|--------|-------------|--------|---|---|
| AiOrchestrationSystem | 8 | 4 | 11 | 0 | 0 |
| ApplicationServiceSystem | 44 | 19 | 115 | 26 | 22 |
| AuditLogSystem | 9 | 3 | 12 | 9 | 5 |
| AuthAndTenancySystem | 20 | 6 | 15 | 17 | 10 |
| BaselineServiceSystem | 12 | 4 | 15 | 8 | 8 |
| CommentServiceSystem | 3 | 3 | 0 | 0 | 0 |
| DiagramServiceSystem | 12 | 7 | 13 | 12 | 7 |
| IcdManagementSystem | 6 | 4 | 8 | 6 | 6 |
| LlmAdapterSystem | 10 | 5 | 19 | 8 | 7 |
| McpServerSystem | 21 | 7 | 24 | 3 | 3 |
| PersistenceLayerSystem | 15 | 6 | 20 | 9 | 8 |
| PresetConfigEngineSystem | 14 | 3 | 11 | 14 | 14 |
| ReactFrontendSystem | 35 | 10 | 24 | 14 | 11 |
| ReqIFServiceSystem | 2 | 2 | 0 | 0 | 0 |
| ResilienceOrchestratorSystem | 6 | 5 | 16 | 6 | 6 |
| RestApiAdapterSystem | 27 | 8 | 27 | 13 | 10 |
| SeMetricsSystem | 13 | 9 | 13 | 13 | 13 |
| TraceabilityEngineSystem | 20 | 4 | 13 | 14 | 13 |
| VectorSearchServiceSystem | 4 | 3 | 0 | 0 | 0 |
| WorkflowEngineSystem | 9 | 4 | 13 | 9 | 9 |
| **Gesamt** | **290** | **116** | **369** | **181** | **152** |

---

## 5. Luecken und Auffaelligkeiten

> Maschinell erkannt. Kein Qualitaetsurteil — nur Stellen, an denen die
> Dokumenten-Kette bricht.

| Befund | Anzahl | IDs |
|--------|--------|-----|
| REQ-L0 ohne REQ-L1-Zerlegung | 5 | REQ-L0-050, REQ-L0-051, REQ-L0-052, REQ-L0-053, REQ-L0-054 |
| REQ-L1 ohne REQ-L0-Parent | 8 | REQ-L1-048, REQ-L1-081, REQ-L1-082, REQ-L1-083, REQ-L1-084, REQ-L1-096, REQ-L1-097, REQ-L1-098 |
| REQ-L1 ohne REQ-L2-Zerlegung | 35 | REQ-L1-042, REQ-L1-044, REQ-L1-048, REQ-L1-058, REQ-L1-063, REQ-L1-064, REQ-L1-065, REQ-L1-066, REQ-L1-067, REQ-L1-068, REQ-L1-069, REQ-L1-070, REQ-L1-071, REQ-L1-072, REQ-L1-073, REQ-L1-074, REQ-L1-075, REQ-L1-076, REQ-L1-077, REQ-L1-078, REQ-L1-079, REQ-L1-080, REQ-L1-081, REQ-L1-082, REQ-L1-083, REQ-L1-084, REQ-L1-085, REQ-L1-087, REQ-L1-095, REQ-L1-096, REQ-L1-097, REQ-L1-098, REQ-L1-099, REQ-L1-100, REQ-L1-101 |
| REQ-L2 ohne REQ-L1-Parent | 58 | REQ-L2-AI-001, REQ-L2-AI-002, REQ-L2-AI-003, REQ-L2-AI-004, REQ-L2-AI-005, REQ-L2-AI-006, REQ-L2-AI-007, REQ-L2-AI-008, REQ-L2-AS-040, REQ-L2-AS-041, REQ-L2-AS-042, REQ-L2-AS-043, REQ-L2-AS-044, REQ-L2-AT-020, REQ-L2-MC-014, REQ-L2-MC-015, REQ-L2-MC-016, REQ-L2-MC-017, REQ-L2-MC-018, REQ-L2-MC-019, REQ-L2-MC-020, REQ-L2-MC-021, REQ-L2-PL-011, REQ-L2-PL-012, REQ-L2-PL-013, REQ-L2-PL-014, REQ-L2-PL-015, REQ-L2-RA-014, REQ-L2-RA-015, REQ-L2-RA-016, REQ-L2-RA-017, REQ-L2-RA-018, REQ-L2-RA-019, REQ-L2-RA-020, REQ-L2-RA-022, REQ-L2-RA-023, REQ-L2-RA-024, REQ-L2-RA-025, REQ-L2-RA-026, REQ-L2-RA-027, … (+18) |
| REQ-L2 ohne Zuordnung im Architektur-Dokument | 87 | REQ-L2-AS-018, REQ-L2-AS-019, REQ-L2-AS-021, REQ-L2-AS-022, REQ-L2-AS-023, REQ-L2-AS-027, REQ-L2-AS-028, REQ-L2-AS-029, REQ-L2-AS-030, REQ-L2-AS-031, REQ-L2-AS-032, REQ-L2-AS-033, REQ-L2-AS-034, REQ-L2-AS-035, REQ-L2-AS-036, REQ-L2-AS-037, REQ-L2-AS-038, REQ-L2-AS-040, REQ-L2-AS-041, REQ-L2-AS-042, REQ-L2-AS-043, REQ-L2-AS-044, REQ-L2-AT-017, REQ-L2-AT-018, REQ-L2-AT-019, REQ-L2-AT-020, REQ-L2-BL-010, REQ-L2-BL-011, REQ-L2-CM-001, REQ-L2-CM-002, REQ-L2-CM-003, REQ-L2-MC-010, REQ-L2-MC-013, REQ-L2-MC-014, REQ-L2-MC-015, REQ-L2-MC-016, REQ-L2-MC-017, REQ-L2-MC-018, REQ-L2-MC-019, REQ-L2-MC-020, … (+47) |
| REQ-L2 ohne Komponente (auch nach L3-Ableitung) | 74 | REQ-L2-AS-018, REQ-L2-AS-019, REQ-L2-AS-021, REQ-L2-AS-022, REQ-L2-AS-023, REQ-L2-AS-027, REQ-L2-AS-028, REQ-L2-AS-029, REQ-L2-AS-030, REQ-L2-AS-031, REQ-L2-AS-032, REQ-L2-AS-033, REQ-L2-AS-034, REQ-L2-AS-035, REQ-L2-AS-036, REQ-L2-AS-037, REQ-L2-AS-038, REQ-L2-AS-040, REQ-L2-AS-041, REQ-L2-AS-042, REQ-L2-AS-043, REQ-L2-AS-044, REQ-L2-AT-017, REQ-L2-AT-018, REQ-L2-AT-019, REQ-L2-BL-010, REQ-L2-BL-011, REQ-L2-CM-001, REQ-L2-CM-002, REQ-L2-CM-003, REQ-L2-MC-013, REQ-L2-MC-014, REQ-L2-MC-015, REQ-L2-MC-017, REQ-L2-MC-018, REQ-L2-MC-019, REQ-L2-MC-020, REQ-L2-MC-021, REQ-L2-PL-011, REQ-L2-PL-012, … (+34) |
| Komponenten ohne REQ-L2-Zuordnung | 10 | COMP-AS-017, COMP-AS-018, COMP-AS-019, COMP-AT-005, COMP-CM-001, COMP-CM-002, COMP-CM-003, COMP-MC-007, COMP-RQ-001, COMP-RQ-002 |
| Komponenten ohne Zeile im Architektur-Dokument | 16 | COMP-AS-017, COMP-AS-018, COMP-AS-019, COMP-AT-005, COMP-AT-006, COMP-CM-001, COMP-CM-002, COMP-CM-003, COMP-RA-007, COMP-RA-008, COMP-RF-007, COMP-RF-008, COMP-RF-009, COMP-RF-010, COMP-RQ-001, COMP-RQ-002 |
| Zugeordnete, aber voellig unbekannte Komponenten | 0 | — |
| Verweise auf nicht existierende REQ-IDs | 15 | REQ-L2-AppSvc-006, REQ-L2-AppSvc-007, REQ-L2-AppSvc-008, REQ-L2-AppSvc-009, REQ-L2-AppSvc-011, REQ-L2-AppSvc-012, REQ-L2-AppSvc-014, REQ-L2-AppSvc-016, REQ-L2-AppSvc-017, REQ-L2-AppSvc-018, REQ-L2-AppSvc-019, REQ-L2-AppSvc-020, REQ-L2-AppSvc-022, REQ-L2-AppSvc-023, REQ-L2-AppSvc-026 |
| REQ-L2 nur in Tabellen, ohne `###`-Block | 13 | REQ-L2-MC-001, REQ-L2-MC-002, REQ-L2-MC-003, REQ-L2-MC-004, REQ-L2-MC-005, REQ-L2-MC-006, REQ-L2-MC-007, REQ-L2-MC-008, REQ-L2-MC-009, REQ-L2-MC-010, REQ-L2-MC-011, REQ-L2-MC-012, REQ-L2-MC-013 |
| L2-Systeme ohne Architektur-Dokument | 2 | CommentServiceSystem, ReqIFServiceSystem |
| Doppelt vergebene REQ-IDs (gleiche Datei) | 20 | REQ-L1-085, REQ-L1-086, REQ-L1-087, REQ-L2-AT-017, REQ-L2-AT-018, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-006, REQ-L2-BL-007, REQ-L2-BL-008, REQ-L2-BL-009, REQ-L2-CM-001, REQ-L2-CM-002, REQ-L2-CM-003, REQ-L2-RQ-001, REQ-L2-RQ-002, REQ-L2-VS-001, REQ-L2-VS-002, REQ-L2-VS-003, REQ-L3-AS002-004 |

**Nicht existierende Parent-IDs im Detail:** `REQ-L2-AppSvc-006` (referenziert von REQ-L3-EXP-001, REQ-L3-EXP-002, REQ-L3-EXP-003, REQ-L3-EXP-005, REQ-L3-EXP-008); `REQ-L2-AppSvc-007` (referenziert von REQ-L3-EXP-001, REQ-L3-EXP-002); `REQ-L2-AppSvc-008` (referenziert von REQ-L3-SEARCH-001, REQ-L3-SEARCH-002, REQ-L3-SEARCH-003, REQ-L3-SEARCH-006, REQ-L3-SEARCH-007, REQ-L3-SEARCH-008, … (+1)); `REQ-L2-AppSvc-009` (referenziert von REQ-L3-SEARCH-004, REQ-L3-SEARCH-005); `REQ-L2-AppSvc-011` (referenziert von REQ-L3-EXP-006); `REQ-L2-AppSvc-012` (referenziert von REQ-L3-WF-001, REQ-L3-WF-002, REQ-L3-WF-005); `REQ-L2-AppSvc-014` (referenziert von REQ-L3-IMP-001, REQ-L3-IMP-002, REQ-L3-IMP-003, REQ-L3-IMP-004, REQ-L3-IMP-005); `REQ-L2-AppSvc-016` (referenziert von REQ-L3-EXP-004); `REQ-L2-AppSvc-017` (referenziert von REQ-L3-WHOOK-001, REQ-L3-WHOOK-002, REQ-L3-WHOOK-003, REQ-L3-WHOOK-004, REQ-L3-WHOOK-005, REQ-L3-WHOOK-006, … (+2)); `REQ-L2-AppSvc-018` (referenziert von REQ-L3-IMP-002, REQ-L3-WF-006); `REQ-L2-AppSvc-019` (referenziert von REQ-L3-IMP-006, REQ-L3-WF-003); `REQ-L2-AppSvc-020` (referenziert von REQ-L3-PPL-001, REQ-L3-PPL-002, REQ-L3-PPL-003, REQ-L3-PPL-004, REQ-L3-PPL-006, REQ-L3-PPL-007, … (+2)); `REQ-L2-AppSvc-022` (referenziert von REQ-L3-ADR-006, REQ-L3-DEB-009, REQ-L3-IMP-007, REQ-L3-ISSUE-009, REQ-L3-RISK-008, REQ-L3-SEARCH-005, … (+1)); `REQ-L2-AppSvc-023` (referenziert von REQ-L3-EXP-007, REQ-L3-IMP-008, REQ-L3-PPL-005, REQ-L3-SEARCH-008, REQ-L3-WF-007); `REQ-L2-AppSvc-026` (referenziert von REQ-L3-ADR-007, REQ-L3-DEB-001, REQ-L3-DEB-002, REQ-L3-DEB-003, REQ-L3-DEB-004, REQ-L3-DEB-005, … (+7))

**Doppelte REQ-IDs:** dieselbe ID taucht mehrfach als `###`-Ueberschrift im selben Dokument auf (meist durch nachtraeglich angehaengte *Erweiterung*-Abschnitte). Diese Matrix zaehlt solche IDs **einmal** und fuehrt die Bloecke zusammen (Marker: letzter gesetzter Wert gewinnt; Parent-Links: Vereinigung). Betroffene Dokumente: `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-002_RequirementService/L3_COMP-AS-002_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/L2_AuthAndTenancySystem_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/BaselineServiceSystem/L2_BaselineServiceSystem_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/CommentServiceSystem/L2_CommentServiceSystem_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/ReqIFServiceSystem/L2_ReqIFServiceSystem_Requirements.md`, `docs/se/L1/Gesamtsystem/L2/VectorSearchServiceSystem/L2_VectorSearchServiceSystem_Requirements.md`.
