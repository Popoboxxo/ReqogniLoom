# ReqFlow — Strategy

> Status: KONSOLIDIERT + VERBESSERT | Erstellt: 2026-06-17 | Letzte Aktualisierung: 2026-06-21
>
> Konsolidierte Strategie-Sicht für die SE-Kaskade. Destilliert aus `docs/VISION.md` und `docs/KONZEPT.md`.
> Dieses Dokument erfindet keine neuen Inhalte — es bündelt die strategischen Aussagen, die für die
> SE-Decomposition (L0 → L1 → L2 → L3) relevant sind, an einer Stelle.
>
> Quellen (autoritativ):
> - `docs/VISION.md` (Produktvision, Feature-Set, offene Fragen)
> - `docs/KONZEPT.md` (Konsolidierte Konzeptentscheidungen, Runden 1–4)

---

## 1. System-Ziel

ReqFlow ist das erste Requirements-Management-Tool, das **AI-Agenten als native
Prozess-Teilnehmer** behandelt — nicht als Texthelfer oder nachträgliches Add-on, sondern
als vollständige, strukturierte Schnittstelle für den gesamten Anforderungslebenszyklus.

ReqFlow schließt die Lücke zwischen zu leichten Agile-Tools (Jira, Linear) und zu schweren
Enterprise-ALM-Systemen (DOORS, Polarion, Codebeamer) durch drei strategische
Entscheidungen:

1. **Nativer MCP Server** als gleichrangige Schnittstelle neben der REST API — AI-Agenten
   können Anforderungen, Architektur-Elemente und Tests direkt und strukturiert abrufen,
   anlegen, verändern und in Beziehung setzen.
2. **Gemeinsames generisches Artefakt-Datenmodell** mit konfigurierbarer Tiefe
   (Configurable Rigor): Vom schlanken Requirements-Management bis zu vollwertigen
   Systems-Engineering-Strukturen — ohne Datenmodell-Duplizierung.
3. **Open Source + Self-Hosted First**: Apache 2.0, Docker-Compose-Deployment, kein
   Vendor-Lock-in, maximale Datenkontrolle.

Quelle: KONZEPT.md §1, VISION.md §1.

---

## 2. Zielgruppen

ReqFlow bedient in v1 **zwei gleichwertige Primärzielgruppen**. Beide teilen dasselbe
Kernproblem (strukturierter Anforderungskontext fehlt) und profitieren vom selben
Lösungsansatz; die Unterschiede in Terminologie und Prozesstiefe werden durch
Configurable Rigor aufgelöst.

| Zielgruppe | Beschreibung | Quelle |
|---|---|---|
| **A — AI-first Software Teams** | Teams mit AI-Agenten (Claude Code, Cursor, GitHub Copilot) im Entwicklungsprozess; benötigen strukturierten, maschinenlesbaren Anforderungskontext. Denken in Epics, Stories, Acceptance Criteria. Agile, schlankes Tool ohne Prozess-Overhead. | VISION.md §2.1, KONZEPT.md §3.1 |
| **B — Systems Engineers (Embedded / Safety-Critical Mid-Market)** | Engineers in regulierten/sicherheitskritischen Domänen (Medizintechnik-Startups, Automotive-Zulieferer 2. Reihe, Industrieautomation-KMU). Benötigen formale Artefakt-Hierarchien, Baselines, Approval-Workflows. Stecken zwischen Agile-Tools und Enterprise-ALM. | VISION.md §2.1, KONZEPT.md §3.1 |
| **C — Systems Engineers mit AI-Affinität** (Bridge-Gruppe) | Engineers, die SE-Methodik mit modernen AI-Werkzeugen kombinieren wollen. | VISION.md §2.1 |

### Nicht für ReqFlow v1 (Out-of-Scope)

- Teams ohne jegliche Requirements-Disziplin (Issue-Tracking-only) → Jira/Linear
- Hochregulierte Programme mit Zertifizierungspflicht (DO-178C Level A, ISO 26262 ASIL-D)
  → Polarion/Codebeamer (mögliches v2+-Ziel)
- Primäres Dokument-Management → Confluence/SharePoint

Quelle: VISION.md §2.2, KONZEPT.md §3.1.

---

## 3. Architektur-Constraints (ADR-Kurzform)

Die folgenden Constraints sind in der L1-Architektur als Architecture Decision Records
verbindlich verankert (siehe `L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` §6):

| ADR | Constraint | Quelle |
|---|---|---|
| **ADR-01** | MCP Server greift **direkt** auf ApplicationService zu (nicht über REST). Beide Adapter sind gleichrangig über demselben Domain-Service. | KONZEPT.md §9.3, SN-12 |
| **ADR-02** | LLM-Provider über schmale Adapter-Schicht abstrahieren (`LlmCapabilityInterface`). Kein Vendor-Lock-in. Graceful Degradation bei fehlender Konfiguration. | KONZEPT.md §1 (Dimension 1), §9.3, SN-07 |
| **ADR-03** | Tenant-Isolation via Row-Level + Custom Django Manager (kein Schema-per-Tenant). | KONZEPT.md §5.4, §9.3, SN-08 |
| **ADR-04** | Configurable Rigor als Querschnitts-Service (`PresetConfigEngine`) — Single Source of Truth für Preset-Regeln. | KONZEPT.md §2, §7, SN-02 |
| **ADR-05** | Generisches Artefakt-Datenmodell + Terminologie-Profile statt zielgruppen-spezifischer Code-Pfade. | KONZEPT.md §3.2, §3.3, SN-10 |
| **ADR-06** | Item-Lifecycle als konfigurierbare WorkflowEngine (statt hartcodiertem Status-Enum). | KONZEPT.md §7a, SN-05 |
| **ADR-07** | Baselines auf drei Scopes (Dokument / Projekt / Global) in einer Entität mit `scope`-Enum. | KONZEPT.md §5.2, SN-04 |
| **ADR-08** | Self-Hosted via Docker Compose (kein Kubernetes in v1). | KONZEPT.md §9.1, §9.3, SN-06 |
| **ADR-09** | Volltextsuche via PostgreSQL Full-Text (keine separate Search-Engine in v1). | KONZEPT.md §10.2, SYS-REQ-20 |
| **ADR-10** | AuditLog Operation-Level in v1, Feld-Level in v2. | KONZEPT.md §11.2, SYS-REQ-11 |

### Übergreifende Technologie-Constraints

- **Backend:** Python 3.x / Django + Django REST Framework
- **Frontend:** React + TypeScript, i18n via react-i18next (DE/EN)
- **Persistenz:** PostgreSQL via Django ORM, Tenant-Isolation auf ORM-Ebene
- **Deployment:** Docker Compose (drei Container: Backend, Frontend, PostgreSQL)
- **API-Authentifizierung:** Bearer Token / API Keys
- **OpenAPI:** Auto-generiert (`drf-spectacular` o.ä.)

Quelle: KONZEPT.md §9 (Tech-Stack), `CLAUDE.md` (Tech-Stack-Sektion).

---

## 4. Configurable Rigor — Strategisches Designprinzip

Configurable Rigor ist das zentrale Differenzierungsmerkmal von ReqFlow. Die **Strenge
des Prozesses** (SE-Tiefe, Audit-Anforderungen, Workflow-Stufen) ist keine globale, fest
verdrahtete Eigenschaft, sondern **pro Workspace** über Presets einstellbar:

| Preset | Charakteristik | Zielgruppe |
|---|---|---|
| **Minimal** | Schlankes Modell, wenig Pflichtfelder, kein Approval-Workflow, keine Baselines | Startups, AI-first Software Teams |
| **Standard** | Erweiterte Pflichtfelder, Document- und Project-Baselines, einfacher Approval-Workflow | Mid-Market Software Teams, einfache SE-Projekte |
| **Extended** | Vollständiger Audit-Trail, alle Baseline-Scopes (Document / Project / Global), strikter Approval-Workflow mit Approver-Rolle, `change_reason` als Pflichtfeld | Systems Engineering, regulierte Umgebungen (ohne Zertifizierungspflicht) |

Das Datenmodell ist **immer vollständig** — Felder für Audit, Compliance und erweiterte
Workflows sind von Beginn an vorhanden. Was sich pro Preset ändert, ist ob und wie diese
Felder erzwungen, sichtbar und schreibbar sind.

Quelle: KONZEPT.md §2, §7 (Presets).

---

## 5. AI-nativ — Zwei Dimensionen

"AI-nativ" ist bei ReqFlow kein Marketing-Begriff, sondern beschreibt zwei konkrete,
architektonische Dimensionen:

### Dimension 1 — LLM als pluggable Capability quer über alle Artefakttypen

LLM-Unterstützung ist nicht auf ein einzelnes Tool beschränkt. LLMs werden als
konfigurierbare, optionale Capability quer über Requirements, Architektur-Elemente und
Tests eingebunden. Die Architektur (`LlmAdapter` mit `LlmCapabilityInterface`) sieht
vier Capabilities als pluggable vor:

- **Generierung** (Vorschläge für Requirement-Formulierungen, Testfall-Ableitung, Architektur-Beschreibungen)
- **Validierung** (Qualitätsprüfung auf Vollständigkeit, Eindeutigkeit, Testbarkeit)
- **Decomposition** (automatische Zerlegungsvorschläge für komplexe Anforderungen)
- **Konsistenz-Checks** (LLM-gestützte Prüfung auf Widersprüche)

Provider-Implementierungen (Anthropic, OpenAI, Ollama) sind austauschbar. Self-Hosted-Nutzer
ohne LLM-Zugang verlieren AI-Features, aber keine Kernfunktionalität.

### Dimension 2 — MCP als vollwertige externe Schnittstelle für ALLE Artefakttypen

Der MCP Server bietet nicht nur Zugriff auf Requirements, sondern auf alle drei zentralen
Artefakttypen — Requirements, Architektur und Tests — vollständig les- und schreibbar.
Architektur-Elemente sind damit ein eigener, schreibbarer Artefakttyp im Datenmodell und
in der MCP-Tool-Liste (20 Tools in 4 Gruppen).

Quelle: KONZEPT.md §1 (zwei Dimensionen), §6 (MCP-Tools).

---

## 6. Nicht-Ziele / Out-of-Scope

Die folgenden Aspekte sind **bewusst kein Bestandteil von ReqFlow v1** und werden in der
Architektur nicht adressiert:

| Out-of-Scope (v1) | Begründung | Mögliche v2+-Roadmap |
|---|---|---|
| Compliance-Zertifizierung (DO-178C Level A, ISO 26262 ASIL-D) | v1 ist „audit-ready, nicht zertifiziert" — Aufwand übersteigt v1-Scope | v2+, ggf. mit dediziertem Compliance-Preset |
| Schema-per-Tenant-Isolation (django-tenants) | Row-Level genügt für v1 + niedrigen 4-stelligen Tenant-Bereich (ADR-03) | Nicht geplant — Row-Level skaliert ausreichend |
| Kubernetes-Deployment / Helm-Chart | Docker Compose deckt Self-Hosted-Footprint ab (ADR-08) | v2 |
| SaaS-Hosting (Managed Hosting) | Self-Hosted First (KONZEPT.md §1, §9.3) | v2 |
| Echtzeit-Kollaboration (CRDT / OT) | Hohe Komplexität, geringer v1-Mehrwert | Could-Have / v2 |
| ReqIF-Import/Export | Standard-Format, aber v1-Footprint hat anderen Fokus | v2+ |
| Bidirektionale Jira-Synchronisation | v1 hat GitHub-Integration als Should-Have | v2+ |
| SSO (SAML/OIDC) | Bearer Token / API Keys reichen für v1 | v2 |
| Vektor-DB / Semantische Suche | PostgreSQL Full-Text deckt v1-Performance-Ziel (< 500 ms / 10k Items) ab (ADR-09) | v2+ |
| AuditLog auf Feld-Diff-Ebene | Operation-Level genügt für v1 (ADR-10) | v2 |
| Elektronische Signaturen, Baseline-Freeze für Zertifizierung | SignatureGate (QES) als DESIRED-Anforderung in v1 spezifiziert (REQ-L2-WE-009), Vollimplementierung v2+ | v2+ |
| Horizontale Skalierung auf 100.000+ Requirements | v1-Skalenziel sind 10.000 Requirements | v2+ |
| Workflow-Migration bei Definition-Wechsel (Auto-Mapping) | v1: Block-Wechsel solange Items im verwaisten State (OP-03) | v2 |
| Multi-Tenancy aktiv (mehrere Tenants gleichzeitig nutzbar) | v1: ein Default-Tenant; Datenmodell ist bereits Tenant-aware | v2 (ohne Schema-Migration) |

Quelle: VISION.md §6.x (MoSCoW: Could-Have / nicht v1), KONZEPT.md §10.2, §11.2.

---

## 7. SE-Kaskade Status

> Stand: 2026-06-21

### L2-Cascade: ABGESCHLOSSEN + ARCHITEKTURVERBESSERUNGEN EINGEARBEITET

Die vollständige SE-Kaskade von L0 → L1 → L2 ist für alle 13 Subsysteme abgeschlossen. Alle Handlungsempfehlungen aus der Architektur-Analyse (`docs/se/reports/handlungsempfehlungen.md`) wurden in die betroffenen L2-Dokumente eingearbeitet.

**Kennzahlen:**

| Metrik | Wert |
|--------|------|
| REQ-L0 (Stakeholder Needs) | 15 |
| REQ-L1 (System Requirements) | 26 |
| REQ-L2 (Subsystem Requirements) | 158 |
| L2-Komponenten | 73 |
| Interne Schnittstellen (L2) | ~117 |
| Test Cases (Acceptance Criteria) | 550+ |
| Subsysteme | 13 |

**Termination-Entscheidung:** Alle 13 Systeme sind **LEAF** — keine L3-Zerlegung.

| System | Komponenten | REQ-L2 | Status |
|--------|------------|--------|--------|
| ApplicationServiceSystem | 13 | 26 | LEAF |
| WorkflowEngineSystem | 4 | 9 | LEAF |
| McpServerSystem | 6 | 12 | LEAF |
| TraceabilityEngineSystem | 4 | 13 | LEAF |
| LlmAdapterSystem | 5 | 8 | LEAF |
| RestApiAdapterSystem | 6 | 13 | LEAF |
| BaselineServiceSystem | 4 | 9 | LEAF |
| ReactFrontendSystem | 6 | 12 | LEAF |
| AuthAndTenancySystem | 3 | 10 | LEAF |
| PresetConfigEngineSystem | 3 | 14 | LEAF |
| AuditLogSystem | 3 | 9 | LEAF |
| PersistenceLayerSystem | 6 | 10 | LEAF |
| SeMetricsSystem | 9 | 13 | LEAF |

### Naechster Schritt

**Implementation-Handoff + Architectural Improvements addressed** — Alle 13 L2-Systeme sind mit vollständigen Anforderungen, Architektur-Dokumenten und Test-Cases ausgestattet. Die 9 Handlungsempfehlungen aus der Architektur-Analyse wurden eingearbeitet (RLS, Event-Bus, Delta-Storage, N+1-Optimierung, AuditLog-Archivierung, SignatureGate, VCRM, Zyklen-Verhinderung, Celery-Async). Die Traceability-Matrix (`docs/se/traceability-matrix.md`) ermöglicht lückenlose Rückverfolgbarkeit von Stakeholder Need bis zum Test Case.

---

## 8. Verweise

| Dokument | Zweck |
|---|---|
| `docs/VISION.md` | Produktvision, Pain Points, Wettbewerbsabgrenzung, MoSCoW-Feature-Set, offene Fragen |
| `docs/KONZEPT.md` | Konsolidierte Konzeptentscheidungen aus Ideation-Runden 1–4, finalisiert |
| `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` | L1-System-Architektur (Kontext, Whitebox, ADRs) |
| `docs/se/L1/Gesamtsystem/L2/<System>System/L2_<System>System_Architecture.md` | L2-Subsystem-Architekturen (12 Systeme) |
| `docs/se/L1/Gesamtsystem/L2/<System>System/L3/<System>Component/L3_<System>Component_Architecture.md` | L3-Detail-Architekturen (5 Systeme: ApplicationService, McpServer, WorkflowEngine, BaselineService, LlmAdapter) |
| `docs/se/traceability-matrix.md` | Lückenlose Traceability SN → SYS-REQ → COMP-REQ → UNIT-REQ → AE |
| `docs/se/interface-registry.md` | Zentrale Interface-Registry aller externen und internen Schnittstellen |
| `docs/se/reports/l3-audit-report.md` | se-critic Quality-Gate-Audit für L3 |
| `docs/se/reports/l3-termination-report.md` | se-termination Termination-Report für L3 |

---

*Konsolidiert durch se-architect-Agent | Quellen: VISION.md, KONZEPT.md | 2026-06-18*
