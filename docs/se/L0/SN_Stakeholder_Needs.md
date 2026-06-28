# L0 Stakeholder Needs

> **Level:** L0 (Stakeholder Needs)
> **System:** ReqFlow
> **Quelle:** docs/KONZEPT.md (final, Runden 1–4), docs/VISION.md
> **Datum:** 2026-06-18
> **Status:** formalisiert

---

## Übersicht

Dieses Dokument enthält die Stakeholder-Needs (REQ-L0-001..015) für ReqFlow v1.
Stakeholder-Needs beschreiben das "Was" und "Warum" aus Nutzerperspektive — ohne Architektur- oder Implementierungsdetails.

Die abgeleiteten L1-System-Anforderungen befinden sich in:
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md`

---

## Stakeholder-Needs (SN)

### REQ-L0-001 — SN-01: Maschinenlesbarer Anforderungskontext für AI-Agenten

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

AI-Agenten (Coding-Agenten, Orchestratoren, CI/CD-Pipelines) benötigen strukturierten,
maschinenlesbaren Zugriff auf Anforderungen, Architektur und Tests — ohne Text-Parsing
oder Webhook-Wrapper — damit Code-Generierung und -Review mit vollständigem fachlichem
Kontext erfolgen können.

**Rationale:** Ohne strukturierte Schnittstelle geht AI-generierter Code oft am fachlichen
Kontext vorbei, weil das "Warum" hinter dem Code nicht maschinenlesbar vorliegt (KONZEPT.md, Abschnitt 1).

---

### REQ-L0-002 — SN-02: Skalierbare SE-Tiefe ohne Produktwechsel

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams unterschiedlicher Reife (von Startups bis zu Automotive-Zulieferern) müssen
dieselbe Plattform mit unterschiedlicher Prozessstrenge nutzen können — von einfachem
Anforderungs-CRUD bis zu vollständigem Systems Engineering mit Baselines,
Approval-Workflows und Audit-Trails — ohne das Tool zu wechseln oder die Infrastruktur
umzubauen.

**Rationale:** Der Markt bietet keinen Mittelpunkt zwischen zu leichtgewichtigen Agile-Tools
und zu schweren Enterprise-Systemen (KONZEPT.md, Abschnitt 1, 2).

---

### REQ-L0-003 — SN-03: Vollständige Traceability zwischen Requirements, Architektur und Tests

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Systems Engineers und AI-first Teams benötigen bidirektionale Verknüpfungen zwischen
Anforderungen, Architektur-Elementen und Testfällen, um Impact-Analysen, Coverage-Reports
und Konsistenz-Prüfungen durchzuführen — sowohl manuell als auch durch Agenten automatisiert.

**Rationale:** Ohne Traceability sind Blast-Radius-Analysen bei Anforderungsänderungen
nicht möglich; dies ist ein Kernbedarf beider Zielgruppen (KONZEPT.md, Abschnitt 3.4, 4.1).

---

### REQ-L0-004 — SN-04: Unveränderliche, benannte Anforderungs-Baselines auf mehreren Ebenen

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams in regulierten oder sicherheitskritischen Umgebungen müssen zu jedem Zeitpunkt
auf einen exakten, unveränderlichen Stand aller Anforderungen zurückgreifen können —
auf Dokumentebene, Projektebene und instanzweit — um Übergaben, Reviews und spätere
Compliance-Nachweise zu ermöglichen.

**Rationale:** Baselines sind ein Must-Have für die SE-Zielgruppe; ohne sie ist
ReqFlow für Systems Engineers nicht ernsthaft nutzbar (KONZEPT.md, Abschnitt 4.1, 7.3).

---

### REQ-L0-005 — SN-05: Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Projektteams müssen den Lifecycle-Workflow für Requirements, Architektur-Elemente und
Testfälle an ihre Domäne und Compliance-Anforderungen anpassen können — inklusive
rollengebundener Approval-Gates — ohne Code-Änderungen am System.

**Rationale:** Ein hartcodierter Status-Enum (Draft/Approved/Deprecated) ist zu starr
für domänenspezifische Prozesse und formale Compliance-Anforderungen
(KONZEPT.md, Abschnitt 7a).

---

### REQ-L0-006 — SN-06: Self-Hosted Deployment ohne Vendor-Lock-in

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Datenschutz-sensible Organisationen und Teams mit eigener Infrastruktur müssen
ReqFlow vollständig on-premise betreiben können — ohne Cloud-Zwang, ohne Lizenzkosten,
mit voller Datenkontrolle.

**Rationale:** Open Source (Apache 2.0) + Docker Compose ist die bewusste Entscheidung
gegen Vendor-Lock-in; SaaS erst ab v2 (KONZEPT.md, Abschnitt 1, 9.1, Anhang A).

---

### REQ-L0-007 — SN-07: LLM-gestützte Qualitätssicherung als optionale Capability

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams, die LLM-Zugang haben, müssen AI-gestützte Funktionen (Validierung,
Zerlegungsvorschläge, Konsistenz-Checks) nutzen können — ohne dass das System bei
fehlendem LLM-Zugang nicht funktioniert.

**Rationale:** LLM als pluggable Capability ist eine der zwei AI-nativen Dimensionen;
Self-Hosted-Nutzer ohne LLM-Zugang dürfen keine Kernfunktionalität verlieren
(KONZEPT.md, Abschnitt 1, 9.3).

---

### REQ-L0-008 — SN-08: Mandantenfähige Isolation für spätere SaaS-Erweiterung

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Das Datenmodell muss bereits in v1 so angelegt sein, dass eine spätere Aktivierung
echter Multi-Tenancy (mehrere Kunden auf einer Instanz) keine Datenmigration erfordert.

**Rationale:** Row-Level-Isolation mit tenant_id ist die Voraussetzung für den v2-SaaS-Betrieb
ohne Schema-Umbau (KONZEPT.md, Abschnitt 5.4, Anhang A).

---

### REQ-L0-009 — SN-09: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams in deutschsprachigen Märkten und international gemischte Teams müssen die
Oberfläche in ihrer Arbeitssprache nutzen können, ohne Funktionseinschränkungen.

**Rationale:** Duale Marktausrichtung DE/EN ist eine v1-Entscheidung; nachträgliche
String-Extraktion ist aufwändiger als proaktive i18n-Integration
(KONZEPT.md, Abschnitt 9.3, Anhang A).

---

### REQ-L0-010 — SN-10: Terminologie-Flexibilität für zwei Zielgruppen ohne Datenverlust

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Software-Teams (Epics, Stories, Acceptance Criteria) und Systems Engineers
(System Requirements, Functions, Verification Criteria) müssen auf demselben
Datenmodell arbeiten, ohne dass ein Profilwechsel Datenverluste oder Migrationen verursacht.

**Rationale:** Gemeinsames generisches Artefakt-Datenmodell mit konfigurierbaren
Terminologie-Layern ist das Fundament der Dual-Zielgruppen-Strategie
(KONZEPT.md, Abschnitt 3.2, 3.3).

---

### REQ-L0-011 — SN-11: Vollständiger Audit-Trail für agentengesteuerte und manuelle Änderungen

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 2 Datei(en) gefunden (u.a. views.py).
**Test Status:** Covered
**Remarks:** Test-Referenz in test_views.py vorhanden.

Compliance-orientierte Teams müssen zu jeder Anforderung, jedem Architektur-Element
und jedem Testfall nachvollziehen können: wer hat was wann geändert — einschließlich
AI-Agenten, die via MCP schreiben.

**Rationale:** Vollständige Auditierbarkeit aller Änderungen ist eine explizite
Non-Functional-Anforderung; MCP-Schreibzugriff ohne Audit-Log wäre ein Sicherheitsrisiko
(KONZEPT.md, Abschnitt 4.2, 6.1, 8.1).

---

### REQ-L0-012 — SN-12: REST API und MCP Server als gleichrangige, vollständige Schnittstellen

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Entwickler und AI-Agenten müssen alle CRUD-Operationen auf allen Artefakttypen
sowohl über REST als auch über MCP vollständig durchführen können — keine
Zweit-Klassen-Schnittstelle.

**Rationale:** Der MCP Server ist kein Anhängsel, sondern greift direkt auf die
Django-Service-Schicht zu; REST ist für direkte Integration, MCP für AI-Agenten
(KONZEPT.md, Abschnitt 6.1, 9.3).

---

### REQ-L0-013 — SN-13: Effiziente Übernahme bestehender Anforderungsdaten

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 5 Datei(en) gefunden (u.a. import.ts).
**Test Status:** Covered
**Remarks:** Test-Referenz in test_csv_import.py vorhanden.

Organisationen, die auf ReqFlow migrieren, müssen Anforderungsdaten aus bestehenden Quellen
(CSV-Dateien, andere Tools) via Bulk-Import übernehmen können — ohne manuelle Neueingabe
jedes einzelnen Items — damit der Produktiveinsatz ohne Datenverlust und ohne übermäßigen
Migrationsaufwand beginnen kann.

**Rationale:** CSV-Bulk-Import ist ein explizites Must-Have in KONZEPT.md §4.6; ohne Import-
Capability ist die Migrationshürde für bestehende Teams zu hoch.

**Akzeptanzkriterien:**
- CSV-Dateien mit Requirements, Architektur-Elementen und Testfällen können importiert werden
- Das System validiert die importierten Daten gegen das Datenmodell und meldet Fehler
- Importierte Items erhalten reguläre UUIDs und sind voll integrierter Bestandteil des Systems

---

### REQ-L0-014 — SN-14: Integration mit Entwicklungstools und Issue-Trackern

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams müssen Anforderungen mit ihren Entwicklungswerkzeugen verknüpfen können — insbesondere
GitHub Issues und Pull Requests — damit die Rückverfolgbarkeit von der Anforderung bis zum
Code-Change ohne Medienbrüche möglich ist.

**Rationale:** GitHub-Integration ist ein explizites Should-Have in KONZEPT.md §4.6; die
Zielgruppe (Developer-affine Teams) erwartet native Integration in ihren bestehenden Workflow.

**Akzeptanzkriterien:**
- Requirements können mit GitHub Issues und Pull Requests verknüpft werden
- Die Verknüpfung ist bidirektional abrufbar (aus ReqFlow und via GitHub)
- Die Verknüpfung ist via UI und API (REST/MCP) herstellbar und abfragbar

---

### REQ-L0-015 — SN-15: Audit-dokumentierbare Anforderungsberichte und Traceability-Matrizen

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 1 Datei(en) gefunden (u.a. pdf_report_generator.py).
**Test Status:** Missing
**Remarks:** Fehlende Traceability in den Tests.

Teams in regulierten Umgebungen müssen Anforderungsdokumente und Traceability-Matrizen als
formalisierte, exportierbare Berichte (PDF) erzeugen können — für interne Audits, Reviews
und Compliance-Nachweise — ohne die Daten manuell aus dem System zusammenstellen zu müssen.

**Rationale:** PDF-Reports sind ein Should-Have in KONZEPT.md §4.6; die SE-Zielgruppe
benötigt dokumentierbare Übergaben für Reviews und Compliance (KONZEPT.md §8.1).

**Akzeptanzkriterien:**
- Anforderungsdokumente können als PDF exportiert werden (inkl. Metadaten, Version, Baseline-Referenz)
- Traceability-Matrizen (Requirement → Test, Requirement → Architektur) können als PDF exportiert werden
- Der Bericht enthält alle für ein Audit relevanten Informationen (Status, Workflow-History, Baseline-Zuordnung)

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade | 2026-06-18*
*Nächster Schritt: L1 System-Anforderungen in docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md*

---

## Stakeholder-Needs (Erweiterung v2 — REQ-L0-016..021)

> **Quelle:** SE-Manifest (Punkte 1–6) + Feature-Wünsche FW-1..FW-3
> **Datum:** 2026-06-21
> **Erstellt durch:** se-requirements-Agent | HOFF-20260621-002

---

### REQ-L0-016 — SN-16: Interaktive Diagramme und Grafiken direkt im Tool

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 3 Datei(en) gefunden (u.a. diagrams.ts).
**Test Status:** Missing
**Remarks:** Fehlende Traceability in den Tests.

Teams müssen Diagramme und grafische Darstellungen (z.B. Systemkontextdiagramme,
Blockdiagramme, Flussdiagramme) direkt innerhalb von ReqFlow erstellen, bearbeiten
und mit Anforderungen oder Architekturelementen verknüpfen können — ohne Medienbruch
zu externen Zeichenprogrammen. Einmal erstellte Diagramme bleiben Teil des versionierten
Artefakts und sind via MCP abrufbar.

**Rationale:** Grafische Darstellungen sind in jedem SE-Prozess unverzichtbar. Ohne
integrierte Diagramm-Capability entstehen Medienbrüche (Visio, Draw.io, PowerPoint),
die Traceability unterbrechen und Diagramme von Requirements entkoppeln.

**Akzeptanzkriterien:**
- AC1: Ein Diagramm kann innerhalb einer Anforderung oder eines Architekturelements erstellt und gespeichert werden.
- AC2: Das Diagramm ist versioniert (Version N bei Änderung inkrementiert) und mit dem übergeordneten Artefakt tracelinked.
- AC3: Diagramme sind via MCP (artifact.get, artifact.get_tree) als strukturierter Payload abrufbar.
- AC4: Mindestens 3 Diagramm-Typen werden unterstützt (z.B. Blockdiagramm, Flussdiagramm, Kontextdiagramm).

**Abgeleitet von:** Feature-Wunsch FW-1
**Ableitet L1:** neue L1-Anforderung REQ-L1-027 erforderlich (Diagramm-Verwaltung)

---

### REQ-L0-017 — SN-17: Verwaltung einer rekursiven Architektur-Hierarchie mit versionierten ICDs

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 2 Datei(en) gefunden (u.a. icds.ts).
**Test Status:** Missing
**Remarks:** Fehlende Traceability in den Tests.

Systems Engineers müssen die Systemarchitektur als mehrstufige Hierarchie
(Gesamtsystem → Subsysteme → Komponenten) strukturieren, Schnittstellen zwischen
Elementen als versionierte Verträge (ICDs — Interface Control Documents) definieren
und sowohl syntaktische als auch semantische Schnittstellenbeschreibungen hinterlegen
können. Jede ICD-Version muss unveränderlich baseline-fähig sein; Rückwärtskompatibilitäts-
Prüfung muss unterstützt werden.

**Rationale:** ICDs sind in der SE-Praxis rechtlich bindende Verträge zwischen Subsystemen.
Ohne versionierte, semantisch beschriebene Schnittstellen fehlt die Grundlage für
Design-by-Contract und inkrementelle Integration. (SE-Manifest Punkt 4, 5)

**Akzeptanzkriterien:**
- AC1: Architekturelemente können in einer beliebig tiefen Hierarchie (mindestens 4 Ebenen) organisiert werden.
- AC2: Schnittstellen zwischen Elementen können als ICD-Einträge mit Typ, Richtung, semantischer Beschreibung, Vorbedingung, Nachbedingung und Invariante angelegt werden.
- AC3: Jede ICD-Änderung erzeugt eine neue ICD-Version; ältere Versionen bleiben unveränderlich lesbar.
- AC4: Das System erkennt und meldet Kompatibilitätskonflikte, wenn eine ICD-Änderung auf inkompatible Verbraucher trifft (breaking-change-Warnung).

**Abgeleitet von:** Feature-Wunsch FW-2; SE-Manifest Punkt 4 (Interface-Definitionen)
**Ableitet L1:** neue L1-Anforderung REQ-L1-028 erforderlich (ICD-Verwaltung und Versionierung)

---

### REQ-L0-018 — SN-18: Verwaltung von Architekturentscheidungen (ADRs), Risiken und Issues

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams müssen Architekturentscheidungen (ADRs — Architecture Decision Records), Risiken und
Probleme/Issues als eigenständige, strukturierte Artefakte erfassen und mit Anforderungen,
Architekturelementen und Testfällen verknüpfen können. Status-Workflows (z.B.
ADR: Proposed → Accepted → Deprecated) müssen konfigurierbar sein; Risiken benötigen
Wahrscheinlichkeit, Auswirkung und Mitigationsmaßnahmen.

**Rationale:** ADRs, Risiken und Issues sind integrale Bestandteile des SE-Prozesses.
Ohne Verknüpfung mit Anforderungen und Architektur fehlen Kontext und Rückverfolgbarkeit
für spätere Entscheidungsrevisionen und Compliance-Nachweise. (SE-Manifest Punkt 6, Feature FW-3)

**Akzeptanzkriterien:**
- AC1: ADRs können mit Titel, Kontext, Entscheidung, Konsequenzen und Status (Proposed/Accepted/Deprecated) erfasst und mit Anforderungen oder Architekturelementen verlinkt werden.
- AC2: Risiken können mit Wahrscheinlichkeit (1–5), Auswirkung (1–5) und Mitigationsmaßnahmen erfasst und mit beliebigen Artefakten verlinkt werden.
- AC3: Issues können mit Priorität, Typ (Bug/Constraint/TBD) und Verknüpfung zu ADRs oder Risiken erfasst werden.
- AC4: Alle drei Artefakttypen (ADR, Risiko, Issue) sind via REST und MCP vollständig CRUD-fähig.

**Abgeleitet von:** Feature-Wunsch FW-3; SE-Manifest Punkt 6 (SSOT, Metrikenbasiertes Steuern)
**Ableitet L1:** neue L1-Anforderung REQ-L1-029 erforderlich (ADR/Risiko/Issue-Verwaltung)

---

### REQ-L0-019 — SN-19: Projektübergreifende Traceability für rekursive SE-Zerlegung

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Teams, die mehrere ReqFlow-Projekte für unterschiedliche Systemebenen führen
(z.B. L1-Gesamtsystem in Projekt A, L2-Subsystem in Projekt B), müssen
Trace-Links zwischen Artefakten unterschiedlicher Projekte innerhalb derselben
ReqFlow-Instanz anlegen können. Impact-Analysen müssen projektübergreifend auflösbar
sein, damit systemische Zerlegung über Projektgrenzen hinweg nachvollziehbar bleibt.

**Rationale:** Rekursive SE-Zerlegung erfordert Cross-Projekt-Traceability.
Ohne sie endet Traceability an der Projektgrenze und die Systemzerlegungskette
wird unvollständig — kritisch für Safety-Cases und Compliance-Audits.
(SE-Manifest Punkt 1, 2)

**Akzeptanzkriterien:**
- AC1: Ein TraceLink kann eine Anforderung in Projekt A mit einer Anforderung in Projekt B als Quelle/Ziel referenzieren.
- AC2: Upstream/Downstream-Queries lösen Cross-Projekt-Links auf und liefern eine vollständige Kette.
- AC3: Cross-Projekt-Trace-Links sind in der Traceability-Matrix und in Impact-Analysen sichtbar.
- AC4: Das System verhindert Cross-Projekt-Links über Tenant-Grenzen hinweg (Isolation bleibt gewahrt).

**Abgeleitet von:** SE-Manifest Punkt 1 (System-Rekursion); SE-Manifest Punkt 2 (lückenlose Traceability)
**Ableitet L1:** Erweiterung von REQ-L1-003 (Traceability-Engine) erforderlich; neue L1-Anforderung REQ-L1-030 empfohlen

---

### REQ-L0-020 — SN-20: Metrikbasiertes Steuern des SE-Prozesses

**Implementation State:** Implemented
**Reviewbefunde:** Code-Referenz in 2 Datei(en) gefunden (u.a. MetricsDashboard.tsx).
**Test Status:** Missing
**Remarks:** Fehlende Traceability in den Tests.

SE-Verantwortliche müssen den Zustand des SE-Prozesses anhand messbarer Metriken
überwachen können — mindestens: Requirements Volatility (Änderungsrate pro Zeitraum),
Traceability Coverage (Anteil verknüpfter Items), Workflow-Lücken (Items ohne
vollständige Workflow-Historie) und offene Risiken nach Schweregrad. Diese Metriken
müssen als Dashboard und via API abrufbar sein.

**Rationale:** "Metrikenbasiertes Steuern" ist ein explizites Prinzip des SE-Manifests.
Ohne Metriken ist keine fundierte Prozesssteuerung möglich; Teams handeln reaktiv
statt proaktiv. (SE-Manifest Punkt 6)

**Akzeptanzkriterien:**
- AC1: Das System berechnet und zeigt Requirements Volatility (Anzahl Änderungen je Anforderung in einem konfigurierbaren Zeitraum) für den aktiven Workspace.
- AC2: Das System zeigt Traceability Coverage als Prozentwert (verknüpfte Requirements / Gesamt-Requirements) und identifiziert nicht verknüpfte Items.
- AC3: Metriken sind via REST-API-Endpunkt (z.B. /metrics/workspace/{id}) abrufbar und maschinenlesbar.
- AC4: Ein konfigurierbarer Schwellwert für Traceability Coverage kann gesetzt werden; Unterschreitung erzeugt eine Warnung.

**Abgeleitet von:** SE-Manifest Punkt 6 (Metrikenbasiertes Steuern)
**Ableitet L1:** neue L1-Anforderung REQ-L1-031 erforderlich (SE-Prozess-Metrikmodul)

---

### REQ-L0-021 — SN-21: Asynchrone, resiliente Systemkommunikation zwischen Komponenten

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Das System muss intern so aufgebaut sein, dass Kommunikation zwischen entkoppelten
Subsystemen bevorzugt asynchron und stateless erfolgt — mit definierten Timeout-,
Retry- und Graceful-Degradation-Mechanismen — sodass der Ausfall einer Komponente
(z.B. LLM-Adapter, Webhook-Dispatcher) keine kaskadierenden Ausfälle anderer
Komponenten verursacht.

**Rationale:** Resilienz ist eine übergreifende Systemqualität. Ohne zeitliche Entkopplung
und Graceful Degradation verlieren synchron-koppelte Systeme bei jedem Teilausfall
vollständig ihre Verfügbarkeit. (SE-Manifest Punkt 3)

**Akzeptanzkriterien:**
- AC1: Alle nicht-kritischen Subsystem-Aufrufe (LLM, Webhooks, GitHub-Integration) laufen über einen Mechanismus mit konfigurierbarem Timeout und mindestens einem Retry.
- AC2: Bei wiederholtem Fehler eines nicht-kritischen Subsystems bleibt der Kern (CRUD, Traceability, Baselines) vollständig verfügbar (Graceful Degradation messbar: Uptime-Kern > 99,5 % unabhängig von LLM-Verfügbarkeit).
- AC3: Stateless-Design wird durch eine Architektur-Richtlinie erzwungen: kein Subsystem hält Session-Zustand im Arbeitsspeicher.
- AC4: Ausfall und Recovery optionaler Subsysteme werden im Audit-Log erfasst.

**Abgeleitet von:** SE-Manifest Punkt 3 (Systemkommunikation & SW-Auswirkungen)
**Ableitet L1:** Erweiterung von REQ-L1-026 (Performance/Resilienz) und REQ-L1-018 (Deployment) erforderlich; neue L1-Anforderung REQ-L1-032 empfohlen

---

*Erweiterung durch se-requirements-Agent | HOFF-20260621-002 | 2026-06-21*

---

## Stakeholder-Needs (Erweiterung v3 — REQ-L0-022)

> **Quelle:** Bewusste Scope-Erweiterung — Feature bereits implementiert; Formalisierung nachgezogen
> **Datum:** 2026-06-25
> **Erstellt durch:** se-requirements-Agent | 2026-06-25

---

### REQ-L0-022 — SN-22: Credential-basierter User-Login (Benutzername/Passwort)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Engineers und Admins müssen sich mit einem Benutzernamen und Passwort am System
authentifizieren können, um einen Zugriffstoken zu erhalten — ohne ein Token
vorab manuell erzeugen oder verwalten zu müssen. Das System übernimmt dabei die
sichere Verifikation der Anmeldedaten und die Token-Ausgabe.

**Rationale:** Bearer-Token und API Keys (STRATEGY.md §3) setzen voraus, dass ein
Token existiert. Ohne einen Credential-basierten Login-Mechanismus gibt es keinen
niedrigschwelligen Einstiegspunkt für interaktive Nutzer (Frontend) und keine
automatisierte Token-Beschaffung für Skripte und Agenten. SSO (SAML/OIDC) ist
bewusst auf v2 verschoben (STRATEGY.md §6 Out-of-Scope); SN-22 schließt die
Lücke für v1 mit dem einfachsten vollständigen Credential-Flow.

**Akzeptanzkriterien:**
- AC1: Ein Nutzer mit gültigem Benutzernamen und Passwort erhält nach Anmeldung einen gültigen Bearer-Token, der für alle geschützten API-Endpunkte verwendbar ist.
- AC2: Ein Nutzer mit falschem Passwort oder unbekanntem Benutzernamen erhält einen Fehler (keine Zugriffsberechtigung); keine Information über die Existenz des Kontos wird preisgegeben.
- AC3: Ein inaktives oder gesperrtes Konto kann sich nicht anmelden und erhält einen Fehler.
- AC4: Passwörter werden ausschließlich gehasht gespeichert; Klartext-Passwörter erscheinen nie in Logs, API-Responses oder Audit-Einträgen.
- AC5: Das System stellt einen Endpunkt bereit, über den ein angemeldeter Nutzer seine eigene Identität (Benutzername, Rollen, Tenant) abrufen kann.

**Abgrenzung:**
- SSO (SAML/OIDC) ist explizit NOT in Scope für v1 (STRATEGY.md §6 Out-of-Scope, v2-Roadmap).
- Passwort-Reset und E-Mail-Verifikation sind ebenfalls nicht Teil dieses Needs.

**Abgeleitet von:** Bewusste Scope-Erweiterung (implementiert); verknüpft mit REQ-L0-005 (Rollen/RBAC), REQ-L0-008 (Mandantenfähigkeit)
**Ableitet L1:** neue L1-Anforderung REQ-L1-033 erforderlich (Credential-basierte Authentifizierung mit Token-Ausgabe)

---

*Erweiterung durch se-requirements-Agent | 2026-06-25*

---

## Stakeholder-Needs (Erweiterung v4 — REQ-L0-029)

> **Quelle:** Gap-Analyse `docs/se/reports/req-gap-workspace-lifecycle-2026-06-27.md`
> **Datum:** 2026-06-27
> **Erstellt durch:** se-requirements-Agent | 2026-06-27

---

### REQ-L0-029 — SN-29: Workspace-Lifecycle-Management für Administratoren

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Administratoren müssen Workspaces explizit schließen, archivieren, reaktivieren oder
(nach Bestätigung) endgültig löschen können. Ein geschlossener Workspace bleibt für
Read-Only-Zugriffe (Audit, Compliance) erhalten, ist aber nicht mehr aktiv editierbar.
Gelöschte Workspaces werden mit allen abhängigen Daten (Requirements, Architecture,
TestCases, TraceLinks, Baselines, AuditLog-Einträge) vollständig entfernt — vor dem
endgültigen Löschen ist eine explizite Bestätigung mit Eingabe des Workspace-Namens
erforderlich.

**Rationale:** Ohne expliziten Lifecycle können Workspaces nur über direkten
Datenbankzugriff entfernt werden — fehleranfällig, inkompatibel mit
Multi-Tenancy-Isolation und blockiert jede Form von Compliance-Archivierung.
RBAC (REQ-L0-008) und Configurable-Rigor (REQ-L0-002) benötigen einen definierten
Workspace-Lebenszyklus.

**Akzeptanzkriterien:**
- AC1: Admin kann Workspace auf Status `closed` setzen → `is_active=false`, aber Daten bleiben erhalten
- AC2: Admin kann geschlossenen Workspace auf `active` reaktivieren (sofern noch nicht gelöscht)
- AC3: Admin kann Workspace löschen mit Bestätigungsdialog (Eingabe Workspace-Name als Captcha)
- AC4: Delete ist kaskadierend: alle Requirements, Architecture, TestCases, TraceLinks, Baselines, Audit-Logs werden mit gelöscht (in dieser Reihenfolge, transaktional)
- AC5: Soft-Delete (`closed`) ist die Standardoption; Hard-Delete erfordert explizite Captcha-Bestätigung
- AC6: Audit-Log-Eintrag wird sowohl bei `close` als auch bei `delete` geschrieben
- AC7: Nicht-Admin-Nutzer sehen weder Close- noch Delete-Buttons

**Abgeleitet von:** Gap-Analyse (Workspace-Lifecycle vollständig fehlend)
**Ableitet L1:** neue L1-Anforderung REQ-L1-042 erforderlich (Workspace-Lifecycle-Operationen mit RBAC)

---

*Erweiterung durch se-requirements-Agent | 2026-06-27 | Gap-Analyse Workspace-Lifecycle*
