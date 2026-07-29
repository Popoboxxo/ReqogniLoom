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

**Implementation State:** Implemented
**Reviewbefunde:** MCP Server wurde vollständig standardkonform implementiert inkl. dynamischer `tools/list` Schemagenerierung.
**Test Status:** Covered
**Remarks:** Der Zugriff erfolgt über stdio, HTTP POST oder asynchron via SSE Streaming.

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

**Implementation State:** Teilweise Implementiert
**Reviewbefunde:** Kern-Traceability-Engine implementiert und verifiziert
(`backend/traceability/trace_link_manager.py` — Zyklen-Prüfung via SCC,
`backend/application/trace_link_service.py` — CRUD/Cascade-Delete/Allocation-Invariant,
`backend/traceability/query_engine.py` — Upstream/Downstream/Transitive Queries,
`backend/traceability/coverage_calculator.py` — Coverage-Berechnung). Siehe REQ-L1-001,
REQ-L1-003, REQ-L1-012 (alle Implemented). Offen bleibt der Stage-Gating-Guardrails-Teil
(Orphan-Protection + Approval-Gate-Enforcement beim Statuswechsel) — siehe REQ-L0-005.
**Test Status:** Teilweise (Backend-Traceability-Kern verifiziert; Guardrails fehlen)
**Remarks:** Frühere Markierung "Not Implemented" war veraltet — Dokument war nicht mit
dem tatsächlichen Implementierungsstand von L1/L2 synchron (Korrektur 2026-07-04).

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

**Implementation State:** Teilweise Implementiert
**Reviewbefunde:** Workflow-Engine mit rollenbasierten Übergängen implementiert
(`backend/workflow/services.py` — `transition()`-Orchestrierung,
`backend/workflow/transition_validator.py` — vierstufiges sequentielles Gateway:
Transition-Existenz, Rollen-Prüfung, Change-Reason-Pflicht, SignatureGate).
**Lücke (bestätigt, nicht dokumentationsbedingt):** Keine der vier Gateway-Regeln prüft
den Traceability-Graphen — Top-Down-Approval-Enforcement (Status "Approved" nur wenn alle
referenzierten Vorgänger ebenfalls "Approved") und No-Orphan-Rule fehlen vollständig.
Siehe REQ-L1-079 / REQ-L2-RA-020 / REQ-L3-RA006-002 (Stage-Gating Guardrails,
HTTP 409 + `guardrail_errors`) — dort korrekt als "Backlog"/"Not Implemented" geführt.
**Test Status:** Teilweise (Workflow-Kern verifiziert; Guardrail-Regeln fehlen)
**Remarks:** Frühere Markierung "Not Implemented" war veraltet für den Workflow-Kern;
der verbleibende Guardrails-Teil ist echt fehlend, nicht nur ein Dokumentations-Rückstand
(Korrektur 2026-07-04).

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

**Implementation State:** Implemented
**Reviewbefunde:** GenericCrudToolGroup implementiert vollständige UI-Parität für CRUD-Operationen aller Artefakte.
**Test Status:** Covered
**Remarks:** Alle Endpunkte (ADR, Risk, Issue, Glossary, etc.) sind via REST und als MCP Tools via `tools/call` verfügbar.

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

## Stakeholder-Needs (Erweiterung v7 — REQ-L0-050)

> **Datum:** 2026-07-03 | **Quelle:** User-Request "PAT via UI"

### REQ-L0-050 — SN-50: Personal Access Tokens (PAT) via UI

**Implementation State:** Erfüllt durch bestehende Komponenten (siehe REQ-L1-081)
**Review Findings:** Erfüllt durch das bestehende `ApiKey`-System, herausgelöst in eine eigene, workspace-unabhängige `/profile`-Seite.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [x] User kann sich über die UI selbstständig Tokens für externe Zugriffe (z.B. MCP Server) generieren. → `/profile`, kein aktiver Workspace erforderlich.
- [x] Der Token wird nach Generierung nur ein einziges Mal im Klartext angezeigt.
- [x] User kann aktive Tokens in einer Liste einsehen (Name, Erstelldatum) und einzeln löschen (Revoke).

**Rationale:** Für eine sichere Integration von AI-Agenten via MCP oder externen Skripten wird eine Möglichkeit zur Authentifizierung benötigt. Passwörter sind dafür zu unsicher, PATs lassen sich gezielt widerrufen.
**Abgeleitet von:** User-Request

## Stakeholder-Needs (Erweiterung v8 — REQ-L0-051)

> **Datum:** 2026-07-04 | **Quelle:** User-Request "System Banner"

### REQ-L0-051 — SN-51: System Broadcast Banner

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Administratoren können zur Laufzeit eine textuelle Nachricht aktivieren und deaktivieren.
- [ ] Wenn aktiviert, wird die Nachricht global als Banner (Sticky) an alle Benutzer in der UI ausgeliefert.
- [ ] KI-Agenten und Skripte können den Banner-Inhalt via API und MCP-Server abrufen.

**Rationale:** Wichtig, um Nutzer und integrierte Agenten auf anstehende Wartungsarbeiten, System-Downtimes oder geänderte Arbeitsanweisungen hinzuweisen.
**Abgeleitet von:** User-Request

## Stakeholder-Needs (Erweiterung v9 — REQ-L0-052 bis 054)

> **Datum:** 2026-07-04 | **Quelle:** Migration der Alt-Anforderungen (REQUIREMENTS.md)

### REQ-L0-052 — SN-52: Visuelle Baum-Struktur für Artefakt-Hierarchien

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-001.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nutzer können die Systemhierarchie visuell als Baum (Tree-View) aufklappen und durchnavigieren.
- [ ] Einzelne Äste lassen sich expandieren und kollabieren.

**Rationale:** Um komplexe Systemstrukturen (L0→L1→L2) erfassen zu können, ist eine reine Listen-Darstellung unzureichend.
**Abgeleitet von:** REQUIREMENTS.md (REQ-001)

---

### REQ-L0-053 — SN-53: Konsistentes Split-View Layout

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-002.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Alle wesentlichen Ansichten (Requirements, Architecture, Risks, etc.) verwenden ein einheitliches Zweispalten-Layout (Split-View).
- [ ] Der Divider zwischen den Spalten ist durch den Nutzer verschiebbar (resizable).

**Rationale:** Eine einheitliche User Experience (UX) verringert die kognitive Last beim Wechsel zwischen verschiedenen Domänen (z.B. von Requirements zu Tests).
**Abgeleitet von:** REQUIREMENTS.md (REQ-002)

---

### REQ-L0-054 — SN-54: Effiziente Listen-Navigation

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-003.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] In allen Artefakt-Listen (linke Spalte des Split-Views) gibt es Freitextsuche, Filter und Sortierung.
- [ ] Hunderte Artefakte bleiben durch diese Werkzeuge nutzbar.

**Rationale:** In großen Projekten mit tausenden Artefakten ist schnelles Finden überwachstumskritisch.
**Abgeleitet von:** REQUIREMENTS.md (REQ-003)

---

*Erstellt durch se-requirements-Agent (L0) | ReqFlow SE-Kaskade | 2026-07-04*
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

## Stakeholder-Needs (Aus dem Backlog übernommen — REQ-L0-023 bis REQ-L0-028)

> **Quelle:** docs/se/L0/SN_Stakeholder_Needs_Backlog.md
> **Datum:** 2026-07-01
> **Erstellt durch:** documenter Agent | Backlog-Übernahme

---

### REQ-L0-023 — SN-23: ReqIF-Support für MBSE-Datenaustausch

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Systems Engineers müssen Anforderungsstrukturen verlustfrei über den Industriestandard ReqIF (Requirements Interchange Format) importieren und exportieren können, um nahtlos mit externen Zulieferern und klassischen SE-Tools (wie DOORS oder Polarion) zusammenzuarbeiten.

**Rationale:** CSV-Exporte/Importe (SN-13) reichen für komplexe, hierarchische MBSE-Datenstrukturen mit Trace-Links nicht aus. ReqIF ist in regulierten Industrien zwingend erforderlich.

---

### REQ-L0-024 — SN-24: Test-Ausführungs-Management (Test Runs)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

QA-Ingenieure und CI/CD-Pipelines müssen Testläufe (Test Runs) protokollieren und den Ausführungsstatus von Testfällen dokumentieren können. Automatisierte Pipelines müssen Testergebnisse direkt über die API oder den MCP-Server als Testlauf-Ergebnis an das System zurückmelden können.

**Rationale:** SN-03 definiert Testfälle, aber ohne die Dokumentation der eigentlichen Testausführung fehlt der Nachweis auf der rechten Seite des V-Modells (Verification & Validation).

---

### REQ-L0-025 — SN-25: Kollaboration und In-App-Diskussion

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Entwickler, Systems Engineers und AI-Agenten müssen direkt an einzelnen Artefakten (Requirements, Architektur-Elementen) kontextbezogen diskutieren können, inkl. @Mentions und Kommentar-Threads.

**Rationale:** Ohne integrierte Kommunikation finden Abstimmungen in externen Tools statt, wodurch der Kontext für AI-Agenten und zukünftige Reviews verloren geht.

---

### REQ-L0-026 — SN-26: Semantische Suche (RAG) und KI-Assistenz

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Nutzer und AI-Agenten müssen das System über semantische (vektorbasierte) Suchen abfragen können, um Duplikate zu identifizieren, Impact-Analysen intelligent zu unterstützen und fehlende Verknüpfungen vorzuschlagen.

**Rationale:** Eine rein textbasierte Suche skaliert bei tausenden Anforderungen nicht. Ein AI-natives Tool profitiert maßgeblich von integrierten Embeddings/Vektordatenbanken (RAG).

---

### REQ-L0-027 — SN-27: Granulare Zugriffssteuerung (Item-Level Access)

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Projekt-Admins müssen die Sichtbarkeit und Bearbeitungsrechte auf Subsystem- oder sogar Artefakt-Ebene einschränken können (z.B. Lesezugriff für Zulieferer A nur auf Komponenten des Subsystems X).

**Rationale:** Mandantenfähigkeit (SN-08) trennt Kunden komplett. In großen Projekten müssen jedoch externe Partner am selben Projekt arbeiten, ohne den gesamten Systemkontext sehen zu dürfen.

---

### REQ-L0-028 — SN-28: Visuelles Diffing von Artefakten und Baselines

**Implementation State:** Not Implemented
**Reviewbefunde:** Keine direkte Implementierung im Code referenziert.
**Test Status:** Missing
**Remarks:** REQ-ID taucht im Codebase nicht auf.

Reviewer müssen Änderungen an Artefakten oder Unterschiede zwischen zwei Projekt-Baselines visuell als "Diff" vergleichen können, um Freigabe-Entscheidungen (Approvals) fundiert treffen zu können.

**Rationale:** Das Audit-Log (SN-11) speichert Änderungen, ist aber für Menschen schwer lesbar. Ein visueller Text-Diff ist für formale Reviews unerlässlich.

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

---

## Stakeholder-Needs (Erweiterung v5 — REQ-L0-030 bis REQ-L0-035)

> **Quelle:** User-Feedback zu `docs/se/reqflow_ontology_analysis.md` (Gap-Analyse Abschnitt 4)
> **Datum:** 2026-06-28
> **Erstellt durch:** se-requirements-Agent | 2026-06-28
> **Status:** formalisiert

---

### REQ-L0-030 — SN-30: Suspect-Link-Propagierung bei Anforderungsänderungen

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need aus Gap-Analyse; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Abgeleitet aus reqflow_ontology_analysis.md Gap 1. User-Feedback: „JA BITTE AUFNEHMEN!"

Wenn sich eine übergeordnete Anforderung ändert, müssen alle direkt und transitiv abhängigen
Artefakte (abgeleitete Anforderungen, Testfälle, Architektur-Elemente) automatisch als
„suspect" (prüfbedürftig) markiert werden. Die Markierung bleibt bestehen, bis ein
autorisierter Reviewer die Konsistenz explizit bestätigt.

**Rationale:** Traceability zeigt bislang nur die *Existenz* einer Kante, nicht die
*Konsistenz* der Inhalte an beiden Enden. Ohne Suspect-Marking verletzt das System den
Grundsatz der Change-Impact-Transparenz, der insbesondere in sicherheitskritischen
Projekten (Automotive, Aerospace) zwingend ist.

**Akzeptanzkriterien:**
- AC1: Jede Änderung an einem Requirement (Inhalt, Status, Titel) löst eine automatische Propagierung aus, die alle `derives-from`- und `parent-child`-Nachfolger als `suspect` markiert
- AC2: Verknüpfte TestCases werden ebenfalls als `suspect` markiert
- AC3: Suspect-Status ist in der UI sichtbar (z. B. Warnsymbol) und über die API abfragbar
- AC4: Ein autorisierter Reviewer kann `suspect` auf `reviewed` zurücksetzen, mit Zeitstempel und Nutzerkennung im Audit-Log
- AC5: Der TraceLink-Graph kann nach `suspect`-Status gefiltert werden (Impact-Analyse)
- AC6: Die Propagierung erfolgt transitiv über beliebig viele Ebenen

**Abgeleitet von:** reqflow_ontology_analysis.md Gap 1 | User-Feedback 2026-06-28
**Ableitet L1:** neue L1-Anforderung REQ-L1-043 erforderlich (Suspect-Link-Engine)

---

### REQ-L0-032 — SN-32: Semantisches Projekt-Glossar (Data Dictionary)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need aus Gap-Analyse; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Abgeleitet aus reqflow_ontology_analysis.md Gap 3. User-Feedback: „JA BITTE AUFNEHMEN!" — Kritisch für AI-Agenten-Validierung gegen definierte Begriffe.

Jedes Projekt muss ein zentrales, maschinenlesbares Glossar mit domänenspezifischen
Begriffsdefinitionen pflegen können. AI-Agenten, Reviewer und Werkzeuge müssen gegen
dieses Glossar prüfen, um Halluzinationen, Mehrdeutigkeiten und Begriffsinkonsistenz
in Anforderungen zu erkennen.

**Rationale:** AI-Agenten validieren Anforderungen semantisch, benötigen dazu aber ein
hart definiertes Vokabular. Ohne Glossar können Agenten Begriffe unterschiedlich
interpretieren, was zu inkonsistenten Reviews führt (reqflow_ontology_analysis.md Gap 3).

**Akzeptanzkriterien:**
- AC1: Pro Projekt kann ein Glossar mit Term, Definition, Synonym-Liste und Abkürzung gepflegt werden
- AC2: Glossar-Einträge sind versioniert und in Baselines enthalten
- AC3: Die API stellt einen Endpunkt bereit, über den AI-Agenten das Glossar maschinenlesbar abrufen können (JSON/YAML)
- AC4: Beim Erstellen/Bearbeiten einer Anforderung warnt das System bei Verwendung unbekannter Begriffe (nicht im Glossar) oder bei Begriffen, die dem Glossar widersprechen
- AC5: Glossar-Begriffe sind bidirektional mit Requirements verknüpfbar (TraceLink-Typ `uses-term`)
- AC6: Glossar ist durchsuchbar (Volltext und semantisch)

**Abgeleitet von:** reqflow_ontology_analysis.md Gap 3 | User-Feedback 2026-06-28
**Ableitet L1:** neue L1-Anforderung REQ-L1-044 erforderlich (Semantisches Projekt-Glossar)

---

### REQ-L0-033 — SN-33: Isolierte Requirement-Sandboxes (Branch & Merge)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need aus Gap-Analyse; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Abgeleitet aus reqflow_ontology_analysis.md Gap 4. User-Feedback: „JA BITTE AUFNEHMEN! ggf. Git-Mechanismus prüfen."

Systems Engineers müssen Teile des Anforderungsbaums oder einer Architekturdekomposition
„auschecken", isoliert bearbeiten (Sandbox) und kontrolliert mit dem Haupt-Zweig
zusammenführen können. Änderungen im Sandbox-Zweig dürfen den freigegebenen Hauptstand
erst nach einem expliziten Merge-Schritt mit Konfliktauflösung beeinflussen.

**Rationale:** Baselines sichern vergangene Stände (Snapshot), erlauben aber keine
parallele Entwicklung. Ohne Branching-Konzept für Artefakte können Teams nicht
gleichzeitig an alternativen Lösungsansätzen arbeiten, ohne den freigegebenen Hauptstand
zu gefährden (reqflow_ontology_analysis.md Gap 4).

> **Lösungsneutralität:** Diese Anforderung beschreibt das *Was* (isolierte, parallele
> Arbeitskopie mit kontrolliertem Merge), nicht das *Wie*. Die Implementierung darf
> keinen bestimmten Mechanismus vorschreiben.
>
> **Implementation Hint (informativ, nicht normativ):** Als möglicher Ansatz wurde
> ein datenbankinterner Git-ähnlicher Branching-Mechanismus identifiziert. Weitere
> mögliche Ansätze umfassen Event-Sourcing-basierte Parallelzweige oder Copy-on-Write-
> Snapshots mit Merge-Logik. Die endgültige Technologieentscheidung obliegt der
> Architekturphase (ADR erforderlich).

**Akzeptanzkriterien:**
- AC1: Nutzer kann einen neuen Sandbox-Zweig aus dem aktuellen Hauptstand erstellen (expliziter Scope: Workspace, Subsystem oder einzelne Artefakt-Unterstruktur)
- AC2: Änderungen im Sandbox-Zweig sind für andere Nutzer unsichtbar, bis ein Merge erfolgt
- AC3: Merge-Vorgang zeigt einen visuellen Diff zwischen Sandbox und Hauptstand
- AC4: Konflikte (gleichzeitige Änderung desselben Artefakts) werden erkannt und müssen manuell aufgelöst werden
- AC5: Jeder Merge wird im Audit-Log protokolliert (Ersteller, Zeitstempel, Scope, Konflikte)
- AC6: Ein Sandbox-Zweig kann ohne Merge verworfen werden (Discard)
- AC7: Bestehende Baselines bleiben von Sandbox-Aktivitäten unberührt

**Abgeleitet von:** reqflow_ontology_analysis.md Gap 4 | User-Feedback 2026-06-28
**Ableitet L1:** neue L1-Anforderung REQ-L1-045 erforderlich (Artefakt-Branching & Merging)

---

### REQ-L0-034 — SN-34: Instanz-Backup, Disaster Recovery & Baseline-Vergleich

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need aus Gap-Analyse; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Abgeleitet aus reqflow_ontology_analysis.md Gap 5. User-Feedback: „JA BITTE AUFNEHMEN! Inkl. Versionsvergleich von Elementen, Elemententypen und ganzen Baseline vergleichen. Und Möglichkeit Baseline zurückzuspielen."

Administratoren müssen automatisierbare Wege haben, um vollständige Instanz-Snapshots
(inkl. Audit-Trails, Nutzer, Konfigurationen und alle Projektdaten) zu erstellen und
wiederherzustellen. Zusätzlich müssen Reviewer zwei beliebige Baselines oder
Artefakt-Versionen visuell als Diff vergleichen und einen früheren Zustand
(Baseline-Restore) gezielt wiederherstellen können.

**Rationale:** Projekt-Exporte (CSV/JSON/ReqIF) sichern nur Nutzdaten, nicht den
Systemzustand. Für regulierte Domänen ist ein vollständiges DR-Konzept (inkl.
Nachweis der Wiederherstellbarkeit) Pflicht. Baseline-Vergleiche und Restore
ermöglichen fundierte Freigabe-Entscheidungen und Fehleranalysen.

**Akzeptanzkriterien:**
- AC1: Admin kann einen vollständigen Instanz-Snapshot (Backup) manuell oder zeitgesteuert auslösen
- AC2: Backup umfasst: alle Projekte, Requirements, Architecture, TestCases, TraceLinks, Baselines, AuditLog, Nutzer (ohne Passwort-Klartexte), Konfigurationen
- AC3: Backup kann vollständig auf einer leeren Instanz wiederhergestellt werden (Restore)
- AC4: Reviewer können zwei Baselines (oder zwei Versionen eines Artefakts) als visuellen Diff vergleichen — auf Feld-Ebene (Changed/Added/Removed)
- AC5: Eine Baseline kann in einen Sandbox-Zweig (SN-33) zurückgespielt werden, ohne den aktiven Hauptstand zu überschreiben
- AC6: Hard-Restore auf den Hauptstand erfordert Admin-Berechtigung + Captcha-Bestätigung
- AC7: Alle Backup- und Restore-Operationen werden im Audit-Log protokolliert

**Abgeleitet von:** reqflow_ontology_analysis.md Gap 5 | User-Feedback 2026-06-28
**Ableitet L1:** neue L1-Anforderung REQ-L1-046 erforderlich (Backup, DR & Baseline-Restore)

---

### REQ-L0-035 — SN-35: Direkte Traceability-Verknüpfungen über mehrere Ebenen (Cross-Level-Links)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need — aus User-Feedback zur strikten L0→L1→L2-Traceability-Regel.
**Test Status:** Missing
**Remarks:** Gegenpart zu der Regel „kein Ebenensprung". Das System muss Sprünge technisch erlauben, aber klar als solche kennzeichnen und validierbar machen.

Nutzer und AI-Agenten müssen in der Lage sein, einen TraceLink direkt von einem
Stakeholder-Need (L0) zu einer Komponenten-Anforderung (L2/L3) zu setzen, wenn
eine Zwischenebene (L1) nachweislich keinen zusätzlichen Erkenntnisgewinn bietet —
zum Beispiel bei rein technischen Nicht-Funktions-Anforderungen. Solche Cross-Level-Links
müssen als abweichend von der Kaskaden-Norm explizit markiert, begründet und separat
auditierbar sein.

**Rationale:** Strikte Ebenen-Traceability erzwingt artifizielle Zwischenschritte für
einfache Sachverhalte. Gleichzeitig dürfen unkontrollierte Ebenensprünge die
Nachvollziehbarkeit nicht untergraben. Das System braucht daher ein kontrolliertes,
begründungspflichtiges Cross-Level-Link-Konzept.

**Akzeptanzkriterien:**
- AC1: Ein TraceLink kann mit dem Typ `cross-level` über beliebig viele Ebenen gesetzt werden
- AC2: Cross-Level-Links erfordern eine Pflichtbegründung (Freitext, min. 20 Zeichen)
- AC3: Cross-Level-Links sind in der Traceability-Matrix und im TraceLink-Graph visuell distinkt markiert (z. B. gestrichelte Linie, separates Icon)
- AC4: Ein Report „Cross-Level-Links ohne Begründung" kann generiert werden
- AC5: AI-Agenten können Cross-Level-Links in ihrer Traceability-Analyse gesondert ausweisen
- AC6: Die Standardregel (keine Ebenensprünge) bleibt der empfohlene Pfad; Cross-Level-Links sind eine dokumentierte Ausnahme

**Abgeleitet von:** User-Feedback 2026-06-28 (Kommentar zu Implementierungsplan)
**Ableitet L1:** neue L1-Anforderung REQ-L1-047 erforderlich (Cross-Level-TraceLink-Konzept)

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 | User-Feedback Gap-Analyse reqflow_ontology_analysis.md*

---

## Stakeholder-Needs (Erweiterung v6 — REQ-L0-036 und REQ-L0-037)

> **Quelle:** User-Request: Canvas-Freehand-Drawing + Mermaid-Live-Preview
> **Datum:** 2026-06-30
> **Erstellt durch:** se-requirements-Agent | 2026-06-30
> **Status:** formalisiert

---

### REQ-L0-036 — SN-36: Diagramme als freies Canvas-Zeichnen (Free-Hand Drawing)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Neues Interaktionsparadigma — ergänzt die bestehenden strukturierten Diagramm-Typen aus REQ-L0-016 um freies Zeichnen.

Teams müssen Diagramme innerhalb von ReqFlow **frei auf einer Zeichenfläche (Canvas)** erstellen können, ohne auf externe Zeichenprogramme ausweichen zu müssen. Die Zeichenfläche muss folgende Werkzeuge bereitstellen:
- Pen/Stift-Tool für Freihandzeichnungen
- Geometrische Grundformen (Rechteck, Kreis, Linie, Polygon)
- Text-Notizen und Beschriftungen
- Pfeile und Verbinder zwischen Formen (auch nachträglich verschiebbar)
- Auswahl-, Verschiebe- und Löschfunktion für gezeichnete Elemente

Gezeichnete Diagramme werden als Artefakte persistiert (z. B. SVG oder JSON-Stroke-Daten) und sind versioniert, über TraceLinks mit Requirements und Tests verknüpfbar und via MCP abrufbar.

**Rationale:** Strukturierte Diagramm-Typen (Block, Flow, Context — REQ-L0-016) decken formale Modellierung ab, aber nicht das schnelle, informelle Skizzieren von Ideen. Free-Hand Canvas-Zeichnen ist der niedrigschwelligste Einstieg für visuelle Kommunikation und schließt die Lücke zwischen „Whiteboard-Skizze" und „formalem Diagramm". Ohne diese Capability müssen Teams weiterhin zu externen Tools (Excalidraw, Draw.io) greifen, was Medienbrüche verursacht.

**Akzeptanzkriterien:**
- AC1: Eine leere Zeichenfläche (Canvas) kann innerhalb eines Workspace geöffnet werden und unterstützt mindestens: Pen/Stift, Rechteck, Kreis/Kreisbogen, Linie, Text-Notiz, Pfeil/Verbinder.
- AC2: Gezeichnete Elemente können nachträglich ausgewählt, verschoben, skaliert und gelöscht werden.
- AC3: Verbinder bleiben mit verbundenen Formen assoziiert (bewegt sich die Form, folgt der Verbinder).
- AC4: Das gezeichnete Diagramm wird als Artefakt mit Struktur-Payload persistiert: JSON-Stroke-Daten als Primärformat (versioniert, diff-bar) + SVG als abgeleitetes Export-Format.
- AC5: Das gezeichnete Diagramm kann mit Requirements, ArchitectureElements und TestCases via TraceLink (Typ `documents`) verknüpft werden.
- AC6: Canvas-Diagramme sind via MCP (artifact.get) als strukturierter Payload abrufbar.
- AC7: Die Canvas-Zeichnung kann als SVG/PNG exportiert werden.
- AC8: Bei Browser-Crash oder Verbindungsabbruch während der Zeichnung gehen höchstens die letzten 5 Sekunden an Eingaben verloren (Auto-Save mit konfigurierbarem Intervall, max. 5s). Das System persistiert Stroke-Daten transaktional bei jeder Save-Operation; partielle Zeichnungen werden nicht korrupt.
- AC9: Das Canvas rendert flüssig (≥30fps) bei bis zu 500 Stroke-Elementen und 100 Formen. Bei Überschreitung wird die Framerate dokumentiert degradiert, der Editor bleibt bedienbar.

**Abgrenzung:**
- Ersetzt nicht REQ-L0-016 (strukturierte Diagramm-Typen) — Canvas ist eine **neue, ergänzende** Interaktionsform.
- Kein Vektor-Editing auf Illustrator-Niveau; Fokus auf schnelles Skizzieren.
- SVG-Export dient der Weiternutzung und Einbettung; das Primärformat sind die Stroke-Daten für Versionierung und Differenz-Anzeige.

**Abgeleitet von:** REQ-L0-016 (Erweiterung um freies Zeichnen) | User-Request Need-1
**Ableitet L1:** Erweiterung von REQ-L1-027 erforderlich (neue Canvas-Diagramm-Typen, Stroke-Payload-Format) — neue L1-Anforderung REQ-L1-056 empfohlen

---

### REQ-L0-037 — SN-37: Mermaid-Code mit Live-Rendering (Live Preview)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need; kein Code-Äquivalent vorhanden.
**Test Status:** Missing
**Remarks:** Neues Interaktionsparadigma — Code-basierte Diagrammeingabe mit Echtzeit-Vorschau. Ergänzt die bestehenden Diagramm-Typen aus REQ-L0-016 um den Mermaid-Ökosystem-Zugang.

Teams müssen **Mermaid-Diagrammcode** direkt in ReqFlow eingeben und das gerenderte Diagramm grafisch im Browser sehen können — mit Live-Preview während der Eingabe. Unterstützt werden MÜSSEN mindestens die folgenden Mermaid-Syntax-Typen:
- flowchart (Flussdiagramm)
- sequenceDiagram (Sequenzdiagramm)
- classDiagram (Klassendiagramm)
- stateDiagram (Zustandsdiagramm)
- erDiagram (Entity-Relationship-Diagramm)

Der eingegebene Mermaid-Code wird als Quelle gespeichert; die gerenderte grafische Darstellung wird als abgeleitetes Artefakt (Bitmap/SVG-Vorschaubild) bereitgestellt. Das gerenderte Diagramm muss interaktiv sein: zoombar (Mausrad/Pinch) und exportierbar als PNG oder SVG.

**Rationale:** Mermaid ist ein De-facto-Standard für Code-basierte Diagramme in der Software-Entwicklung und wird von GitHub, GitLab und vielen Markdown-Prozessoren nativ unterstützt. Der Kern-Need ist die Live-Preview-UX — nicht die Mermaid-Unterstützung an sich (die bereits in REQ-L0-016/REQ-L1-027 als Payload-Option angelegt ist). Entscheidend ist die Echtzeit-Rückkopplung zwischen Code-Eingabe und grafischer Darstellung im selben Werkzeug. Teams, die bereits in Mermaid modellieren, müssen diesen Code in ReqFlow wiederverwenden können — statt ihn manuell in ein strukturiertes Diagramm-Format zu übersetzen. Die Live-Preview senkt die kognitive Last beim Editieren erheblich.

**Akzeptanzkriterien:**
- AC1: Der Nutzer kann Mermaid-Code in einen Texteditor eingeben; während der Eingabe wird das gerenderte Diagramm im selben Bildschirmbereich als Vorschau angezeigt (Live-Preview, Aktualisierung bei Tastatur-Eingabe mit 500ms Debounce).
- AC2: Der Mermaid-Quellcode wird als Diagramm-Quelltext-Payload persistiert (immutable Versionen bei Änderung).
- AC3: Mindestens 5 Mermaid-Typen werden unterstützt: flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram.
- AC4: Das gerenderte Diagramm ist zoombar (Mausrad, Pinch-Geste, Zoom-Buttons).
- AC5: Das gerenderte Diagramm kann als PNG und als SVG exportiert werden.
- AC6: Der Mermaid-Quellcode ist via TraceLink mit Requirements, ArchitectureElements und TestCases verknüpfbar (Typ `documents`).
- AC7: Bei Syntaxfehlern im Mermaid-Code wird eine aussagekräftige Fehlermeldung im UI angezeigt (mit Zeilennummer und Fehlerkategorie). Die zuletzt erfolgreich gerenderte grafische Darstellung bleibt als Fossil sichtbar, bis der Code wieder syntaktisch valide ist.
- AC8: Das Mermaid-Diagramm ist via MCP (artifact.get) als strukturierter Payload (Quellcode + Render-Hinweise) abrufbar.
- AC9: Fällt der Mermaid-Renderer aus (Library-Ladefehler, Timeout, CORS-Problem), zeigt das System eine Fehlermeldung und den rohen Quellcode lesbar als Fallback an. Der Quellcode bleibt editierbar und speicherbar — unabhängig vom Rendering-Status.
- AC10: Das Live-Rendering schließt in <2s für Diagramme mit bis zu 100 Knoten/Kanten ab. Bei Überschreitung wird eine Ladeanzeige gezeigt, der Editor bleibt responsiv.

**Abgrenzung:**
- Ersetzt nicht REQ-L0-016 (strukturierte Diagramm-Typen) — Mermaid ist eine **neue, code-basierte** Eingabeform für dieselben und zusätzliche Diagramm-Typen.
- Mermaid-Rendering kann serverseitig (Backend wandelt Mermaid in SVG/PNG um) oder clientseitig (mermaid.js im Browser) erfolgen — die Entscheidung obliegt der Architekturphase.
- Versionierung erfolgt auf dem Quellcode (diff-bar), nicht auf dem gerenderten Bild.

**Abgeleitet von:** REQ-L0-016 (Erweiterung um Mermaid-Unterstützung) | User-Request Need-2
**Ableitet L1:** Erweiterung von REQ-L1-027 erforderlich (Mermaid-Code-Payload, Live-Rendering) — neue L1-Anforderung REQ-L1-057 empfohlen

---

*Erweiterung durch se-requirements-Agent | 2026-06-30 | User-Request Need-1 (Canvas Free-Hand Drawing) + Need-2 (Mermaid Live Preview)*

---

## Stakeholder-Needs (Erweiterung v7 — REQ-L0-038 bis REQ-L0-040)

> **Quelle:** User-Feedback (Befund - SE-Mode / Requirements-Management-Fähigkeit der UI)
> **Datum:** 2026-07-03
> **Erstellt durch:** se-requirements-Agent | 2026-07-03
> **Status:** formalisiert

---

### REQ-L0-038 — SN-38: Skalierbarkeit & Übersicht bei großen Datenmengen

**Implementation State:** Not Implemented
**Review Findings:** UI-Befund ergab unpaginierte, unstrukturierte Liste
**Test Status:** Missing
**Remarks:** Essentiell für den produktiven Einsatz bei Projekten mit > 100 Requirements.

Als SysEng-Nutzer muss ich auch bei Hunderten von Requirements, Architecture-Elementen und anderen Artefakten die Übersicht behalten, ohne dass die Liste unendlich lang, unsortiert und unübersichtlich wird. Das System muss Mechanismen zur Filterung und Sortierung bereitstellen.

**Rationale:** Aktuell werden alle Requirements in einer flachen `<ul>`-Liste ohne Filter- oder Suchfunktion dargestellt. Bei realistischen Projektgrößen ist diese Ansicht nicht handhabbar.
**Akzeptanzkriterien:**
- AC1: Artefakt-Listen bieten eine Suchleiste.
- AC2: Artefakt-Listen bieten Filter nach Status und Kategorie.
- AC3: Artefakt-Listen können nach verschiedenen Attributen sortiert werden.

**Ableitet L1:** neue L1-Anforderungen REQ-L1-058 (Wiederverwendbarkeit) und REQ-L1-060 (Search, Filter, Sort)

---

### REQ-L0-039 — SN-39: Systemebenen-Orientierung durch Hierarchie-Darstellung

**Implementation State:** Not Implemented
**Review Findings:** Parent-Child-Struktur nur als Trace-Link sichtbar, nicht als Struktur
**Test Status:** Missing

Als SysEng-Nutzer muss ich die hierarchische Struktur (Parent-Child / Systemebenen) meiner Systemelemente sofort in der primären Listenansicht erkennen können, um den Kontext nicht zu verlieren.

**Rationale:** Die flache Darstellung verdeckt die Dekompositionsebene der Requirements.
**Akzeptanzkriterien:**
- AC1: Die UI bietet eine Tree-View-Ansicht oder Einrückungen basierend auf Parent-Child-Beziehungen.
- AC2: Untergeordnete Elemente können in der Liste ein- und ausgeklappt werden.

**Ableitet L1:** neue L1-Anforderung REQ-L1-061 (Hierarchie-Darstellung)

---

### REQ-L0-040 — SN-40: UI-Performance durch Lazy Loading

**Implementation State:** Not Implemented
**Review Findings:** listAll() ruft alle Daten synchron ab
**Test Status:** Missing

Als Nutzer erwarte ich eine performante Applikation, die auch bei großen Projekten flüssig lädt, ohne unnötig alle Datensätze auf einmal vom Server zu ziehen.

**Rationale:** Die aktuelle Implementierung ruft alle Requirements in einer Schleife (bis zu 100 Seiten) ab, was den Browser bei großen Projekten blockiert und API-Limits erschöpft.
**Akzeptanzkriterien:**
- AC1: Listen-Views rufen Daten paginiert (Lazy-Loading) vom Backend ab.
- AC2: Paginierung wird serverseitig unterstützt.

**Ableitet L1:** neue L1-Anforderung REQ-L1-059 (Lazy Loading / Pagination)

---

---

## Stakeholder-Needs (Erweiterung v8 — REQ-L0-041 bis REQ-L0-046)

> **Quelle:** User-Request: Adaptive AI-Native Systems Engineering Plattform
> **Datum:** 2026-07-03
> **Erstellt durch:** se-requirements-Agent | 2026-07-03
> **Status:** formalisiert

---

### REQ-L0-041 — SN-41: Adaptive Ontologie (Skalierung der SE-Strenge)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need (Architektur-Erweiterung).
**Test Status:** Missing

Als SysEng-Nutzer muss ich das System flexibel skalieren können — von einem leichten "Kleinprojekt" (Kanban-Stil) bis hin zu einem strengen, ISO-15288-konformen SE-Prozess (Hardcore SE) — ohne das Tool wechseln zu müssen.

**Rationale:** Vermeidung von Tool-Bruch zwischen frühen agilen Phasen und späten regulierten Phasen.
**Akzeptanzkriterien:**
- AC1: Das System unterstützt "Modi" (Presets), die die Komplexität der Ontologie anpassen.
- AC2: In leichten Modi sind komplexe Entitäten transparent ausgeblendet.

**Ableitet L1:** Architekturvorgabe Preset-Engine, Traceability-Ontologie

---

### REQ-L0-042 — SN-42: Ontologie-Vielfalt (StReq, SyReq, ArchE, CoReq, IF, ADR, Risk, TC)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need (Architektur-Erweiterung).
**Test Status:** Missing

Das System muss spezifische SE-Entitäten (Stakeholder Requirement, System Requirement, Architecture Element, Component Requirement, Interface, ADR, Risk, TestCase) klar unterscheiden und deren Verbindungsregeln (z.B. *refines*, *allocated to*, *mitigated by*) erzwingen.

**Rationale:** Ohne strikte Typisierung der Entitäten und Kanten ist kein semantisches Routing oder automatisiertes Anti-Pattern-Detection möglich.
**Akzeptanzkriterien:**
- AC1: Entitätstypen sind im Datenmodell tief verankert.
- AC2: Kanten (Traces) haben eine feste Semantik.

**Ableitet L1:** REQ-L1-071 (Spezifische Traceability-Ontologie)

---

### REQ-L0-043 — SN-43: Erweiterte UI-Ansichten (TRM, Node Graph, Split-Screen)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need.
**Test Status:** Missing

Nutzer benötigen neben klassischen Listen und Bäumen auch eine Traceability Matrix (Kreuztabelle), interaktive Netzwerk-Graphen für Impact-Analysen und einen Split-Screen für tiefen Kontext + KI-Chat.

**Rationale:** Komplexe Systeme lassen sich nur visuell über TRM und Netzwerk-Graphen überschauen.
**Akzeptanzkriterien:**
- AC1: Ansicht für interaktive Node-Graphen.
- AC2: Ansicht für Traceability Matrix (TRM).
- AC3: Split-Screen Layout mit Kontext-Panel & KI-Chat.

**Ableitet L1:** REQ-L1-070 (WebGL / Canvas Graph Rendering)

---

### REQ-L0-044 — SN-44: Versionierte Kanten (Dynamic vs. Static Traces)

**Implementation State:** Not Implemented
**Review Findings:** Bisher nur dynamische Verweise auf `latest`.
**Test Status:** Missing

In späten/strengen Projektphasen müssen Trace-Links statisch ("Pinned") auf eine spezifische Objektversion zeigen können, während sie in frühen Phasen dynamisch auf den "Latest"-Stand zeigen.

**Rationale:** Notwendig für Compliance, formale Releases und Baselines (Product Baseline).
**Akzeptanzkriterien:**
- AC1: TraceLinks können ein Attribut `pin_version` haben.
- AC2: Wenn gesetzt, zeigt der Link auf einen Snapshot.

**Ableitet L1:** REQ-L1-072 (Statische vs. Dynamische TraceLinks)

---

### REQ-L0-045 — SN-45: Anti-Pattern Erkennung (Orphans, Barren Nodes)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need.
**Test Status:** Missing

Das System muss Fehler in der Architektur (Orphans ohne Upstream, Barren Nodes ohne Downstream, Zirkelbezüge) aktiv erkennen und markieren.

**Rationale:** Qualitätssicherung bei komplexen Traceability-Bäumen.
**Akzeptanzkriterien:**
- AC1: Das System flaggt Orphans (Gold Plating).
- AC2: Das System flaggt Barren Nodes (Unfertige Spezifikation).
- AC3: Zyklen im DAG werden verhindert oder markiert.

**Ableitet L1:** REQ-L1-073 (Rules Engine für Anti-Patterns)

---

### REQ-L0-046 — SN-46: Proaktive KI-Agenten (Semantic Healing, Interfaces, Decomposition)

**Implementation State:** Not Implemented
**Review Findings:** KI-Agenten bisher meist reaktiv/chat-basiert.
**Test Status:** Missing

KI-Agenten dürfen nicht nur auf Anfrage reagieren, sondern müssen proaktiv Suspect-Links analysieren (Semantic Trace Healing), Schnittstellenkonsistenz einfordern und über RAG Architekturentwürfe generieren.

**Rationale:** Echter AI-Native Ansatz — KI arbeitet als kontinuierlicher System-Ingenieur im Hintergrund.
**Akzeptanzkriterien:**
- AC1: Semantic Trace Healing schlägt Updates für Downstream-Elemente vor.
- AC2: Interface-Consistency wird proaktiv überwacht.
- AC3: KI bricht Anforderungen vertikal herunter (AI Decomposition).

**Ableitet L1:** REQ-L1-074 (Semantic Trace Healing Engine), REQ-L1-069 (AI Orchestration Layer)

---
---

## Stakeholder-Needs (Erweiterung v9 — REQ-L0-047 bis REQ-L0-049)

> **Quelle:** User-Request: Striktes Datenmodell & Stage-Gating
> **Datum:** 2026-07-03
> **Erstellt durch:** se-requirements-Agent | 2026-07-03
> **Status:** formalisiert

---

### REQ-L0-047 — SN-47: Präzises, domänenspezifisches Datenmodell

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need.
**Test Status:** Missing

Das System muss über ein rigides Datenmodell verfügen. Jedes Artefakt benötigt zwingend globale Metadaten (UID als Auto-String z.B. REQ-1042, Float/SemVer Versionierung, Created By/Date, Last Modified By/Date, Tags). Zudem müssen artefaktspezifische Attribute vorhanden sein (z.B. Priority nach MoSCoW für StReq, Complexity/Points nach Fibonacci für SyReq, Criticality/ASIL für ArchE).

**Rationale:** Ein schwammiges Schema verhindert tiefgreifende Auswertungen und normkonformes Systems Engineering (wie ISO 26262, ASPICE).
**Akzeptanzkriterien:**
- AC1: Globale Metadaten (UID, Version, Audit-Trail) sind unveränderlich und systemgemanagt.
- AC2: Artefaktspezifische UI-Masken und Backend-Validierungen existieren (z.B. MoSCoW-Dropdown).

**Ableitet L1:** REQ-L1-076 (Global Metadata), REQ-L1-077 (Artifact-Specific Schema)

---

### REQ-L0-048 — SN-48: Industriestandard Workflow-Status

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need.
**Test Status:** Missing

Jedes Hauptartefakt (StReq, SyReq, ArchE, TC) muss einen strengen Lifecycle durchlaufen. Die erlaubten Status sind: Draft (Entwurf), In Review (In Prüfung), Approved (Freigegeben), In Implementation (Nur ArchE), Verified (Verifiziert), Rejected (Abgelehnt) und Obsolete (Veraltet).

**Rationale:** Vermeidung von Chaos; klare Definition des Reifegrads (Maturity) eines Artefakts.
**Akzeptanzkriterien:**
- AC1: Artefakte starten immer im Status "Draft".
- AC2: Übergänge sind nur nach einer definierten State Machine erlaubt.

**Ableitet L1:** REQ-L1-078 (State Machine & Workflow)

---

### REQ-L0-049 — SN-49: Stage-Gating & Guardrails (Strenge SE-Regeln)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifizierter Need.
**Test Status:** Missing

Im "Hardcore SE-Modus" muss das System Statusübergänge aktiv blockieren (Guardrails), wenn semantische SE-Regeln verletzt sind.
Spezifisch:
- Top-Down Restriktion: SyReq darf nur "Approved" werden, wenn Parent-StReq "Approved" ist.
- No-Orphan Rule: SyReq darf nicht "In Review" gehen, ohne Upstream-Trace.
- Allocation Gate: ArchE muss mind. "Draft" sein für Allocation; ArchE darf erst "Approved" werden, wenn alle zugewiesenen SyReqs "Approved" sind.
- Baseline Lock: Baseline-Erstellung erfordert 100% "Approved" Artefakte und 0 "Suspect" Links.

**Rationale:** Die Software muss den Ingenieur zwingen, sauber zu arbeiten, statt ihm nur eine Dokumentationsfläche zu bieten.
**Akzeptanzkriterien:**
- AC1: Das Backend lehnt ungültige State-Transitions mit einem Fehler ab.
- AC2: Die UI zeigt dem Nutzer klare Meldungen an, warum ein Statuswechsel blockiert wird.

**Ableitet L1:** REQ-L1-079 (Stage-Gating Engine)

---


## Stakeholder-Needs (Erweiterung v10 — REQ-L0-055)

### REQ-L0-055 — SN-55: Glossar-Referenzen im Freitext (@-Mentions)

**Implementation State:** Not Implemented
**Reviewbefunde:** Neu angelegt.
**Test Status:** Missing

Die Anwendung muss es ermöglichen, definierte Glossar-Einträge direkt im Freitext (Beschreibungen von Anforderungen, Testfällen etc.) über eine `@Begriff`-Syntax zu referenzieren.
Glossar-Begriffe müssen auch über die API abrufbar sein, um programmgesteuert kontextbezogene Erklärungen zu liefern.
Beim Löschen eines Workspaces dürfen Glossar-Begriffe nicht gelöscht werden (kein CASCADE Delete), sondern bleiben mit `null`-Workspace global oder verwaist erhalten, damit die Definitionen über Projekte hinweg nutzbar oder zumindest historisch gesichert bleiben.

**Rationale:** Fachtexte enthalten oft domänenspezifische Begriffe. Durch eine einfache `@`-Erwähnung und Auto-Erkennung im Text können Nutzer sofort beim Lesen Tooltips mit den Definitionen abrufen, was Missverständnisse reduziert. Die Persistenz über Workspace-Grenzen hinweg sichert mühsam erarbeitete Begriffsklärungen.
**Akzeptanzkriterien:**
- AC1: Die Markdown-Vorschau erkennt `@Begriff` und macht daraus ein UI-Element (z.B. Link oder Tooltip).
- AC2: Tooltips zeigen die Definition des Begriffs.
- AC3: Das Löschen eines Workspaces löscht nicht das Glossar, sondern setzt die Workspace-ID auf `null` (`on_delete=SET_NULL`).
- AC4: REST-API unterstützt den Abruf von Glossarbegriffen.

**Ableitet L1:** REQ-L1-080 (Glossary Mentions & Persistence)

---


## Zusammenfassung: Neue Stakeholder-Needs

| REQ-ID | Titel | Priorität | Abgeleitet von | L1-Ableitung |
|--------|-------|-----------|----------------|--------------|
| REQ-L0-036 | Free-Hand Canvas Drawing | desired | REQ-L0-016, User Need-1 | Erweiterung REQ-L1-027 / NEU REQ-L1-056 |
| REQ-L0-037 | Mermaid Live Preview | desired | REQ-L0-016, User Need-2 | Erweiterung REQ-L1-027 / NEU REQ-L1-057 |
| REQ-L0-038 | Skalierbarkeit & Übersicht | mandatory | UI-Befund | NEU REQ-L1-058, REQ-L1-060 |
| REQ-L0-039 | Systemebenen-Orientierung | mandatory | UI-Befund | NEU REQ-L1-061 |
| REQ-L0-040 | UI-Performance | mandatory | UI-Befund | NEU REQ-L1-059 |
| REQ-L0-041 | Adaptive Ontologie | mandatory | User-Request | Architekturvorgabe Preset-Engine |
| REQ-L0-042 | Ontologie-Vielfalt | mandatory | User-Request | REQ-L1-071 |
| REQ-L0-043 | Erweiterte UI-Ansichten | mandatory | User-Request | REQ-L1-070 |
| REQ-L0-044 | Versionierte Kanten | mandatory | User-Request | REQ-L1-072 |
| REQ-L0-045 | Anti-Pattern Erkennung | mandatory | User-Request | REQ-L1-073 |
| REQ-L0-046 | Proaktive KI-Agenten | mandatory | User-Request | REQ-L1-069, REQ-L1-074 |
| REQ-L0-047 | Präzises Datenmodell | mandatory | User-Request | REQ-L1-076, REQ-L1-077 |
| REQ-L0-048 | Workflow-Status | mandatory | User-Request | REQ-L1-078 |
| REQ-L0-049 | Stage-Gating & Guardrails | mandatory | User-Request | REQ-L1-079 |
| REQ-L0-055 | Glossar-Referenzen im Freitext (@-Mentions) | mandatory | User-Request | REQ-L1-080 |
| REQ-L0-056 | Konfigurierbare KI-Ableitungs-Prompts | desired | User-Request | REQ-L1-088 |
| REQ-L0-062 | Unified Artifact Inspector Sidebar | mandatory | User-Request 2026-07-06 | NEU REQ-L1-089..095 |

**Nächster Schritt:** L1-System-Anforderungen in `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md` erweitern.

---

## Stakeholder-Needs (Erweiterung v11 — REQ-L0-056)

### REQ-L0-056 — SN-56: Konfigurierbare KI-Ableitungs-Prompts

**Implementation State:** Not Implemented
**Reviewbefunde:** Neu angelegt.
**Test Status:** Missing

System- und Projektadministratoren müssen die System-Prompts, die von KI-Agenten zur automatischen Ableitung von Anforderungen (z.B. L1 zu L2) oder zur Testfall-Generierung verwendet werden, projekt- oder workspacespezifisch konfigurieren können. 

**Rationale:** Jedes Projekt hat individuelle Domänen-Richtlinien und Dokumentationsstandards. Hardcodierte Prompts generieren oft Ergebnisse, die nicht den spezifischen Projektvorgaben entsprechen. Eine Konfigurierbarkeit stellt sicher, dass die KI-Agenten qualitativ hochwertige und passgenaue Ergebnisse liefern.
**Akzeptanzkriterien:**
- AC1: Die UI bietet Administratoren eine Möglichkeit, KI-Prompts für verschiedene Ableitungs-Aufgaben (Requirements, Architecture, Tests) einzusehen und zu bearbeiten.
- AC2: Konfigurierte Prompts sind an den aktiven Workspace gebunden (Tenant-Isolation).
- AC3: KI-Agenten nutzen bei der Ausführung immer den aktuell im Workspace hinterlegten Prompt für die jeweilige Aufgabe.
- AC4: Änderungen an den Prompts werden im Audit-Log protokolliert.

**Ableitet L1:** REQ-L1-088 (Configurable AI Prompts)

### REQ-L0-060 � SN-60: Konsistentes UI/UX Design und Universelles Versioning
**Implementation State:** Not Implemented
**Reviewbefunde:** N/A
**Test Status:** Missing

Benutzer ben�tigen ein durchgehend konsistentes Look-and-Feel �ber alle Entit�tstypen (Requirements, Needs, ADRs) hinweg. TraceLinks, Versionierungen und Filter m�ssen in allen Ansichten einheitlich verf�gbar und bedienbar sein.
**Rationale:** Steigert die Effizienz und Usability massiv.

### REQ-L0-061 � SN-61: Interaktive und versionierte Architektur-Diagramme
**Implementation State:** Not Implemented
**Reviewbefunde:** N/A
**Test Status:** Missing

Benutzer m�ssen Architektur-Diagramme direkt im System zeichnen k�nnen (Canvas) und diese l�ckenlos �ber TraceLinks mit den Architekturelementen verkn�pfen k�nnen. Diagramme m�ssen ebenfalls versionierbar sein.
**Rationale:** Diagramme sind integrale Bestandteile von Architektur-Entscheidungen.

---

## Stakeholder-Needs (Erweiterung v12 — REQ-L0-062)

> **Quelle:** User-Request "UI Unification of the Right Sidebar (ArtifactInspector)"
> **Datum:** 2026-07-06 | **Erstellt durch:** requirements-Agent

---

### REQ-L0-062 — SN-62: Unified Artifact Inspector Sidebar (Right Sidebar)

**Implementation State:** Not Implemented
**Review Findings:** Newly identified. The existing `bidirektionale Traceability-Seitenleiste` (REQ-L3-RF003-003) and `verknuepfte Requirements in Seitenleiste` (REQ-L3-RF004-003) are inline, page-specific widgets. They will be replaced/superseded by the unified ArtifactInspector pattern.
**Test Status:** Missing
**Priority:** mandatory

Users must encounter a single, consistent right-sidebar (the **ArtifactInspector**) on every artifact detail page (ICD, Diagram, ADR, Risk, Issue, Glossary, Stakeholder Need, Requirement, Architecture, TestCase). The ArtifactInspector MUST always expose the same set of panel slots in the same order:

1. **VersionPanel** — list of versions of the current artifact, the ability to switch the displayed version, and a baseline indicator (whether the displayed version is part of an active baseline).
2. **DiffPanel** — field-level diff between any two selectable versions of the current artifact.
3. **TracePanel** — inbound and outbound TraceLinks of the current artifact, filterable by TraceLink type.

The sidebar shell MUST support collapse (hide all panels) and pin (keep the sidebar open while the user navigates between artifacts). The pattern REPLACES existing inline sidebars on the Requirement and Architecture editor pages and is ADDED to all other artifact detail pages that do not yet have a sidebar.

**Rationale:** Today the right sidebar exists only on a subset of artifact detail pages (Requirement editor, Architecture editor) and uses page-specific widgets. When users move between artifact types (e.g. from a Requirement to a Risk, an ADR or an ICD) the right-hand area either disappears or shows an inconsistent widget. This breaks the user's mental model, hides cross-cutting capabilities (versioning, diffing, traceability) on most artifact types, and forces context-switches. A unified, predictable ArtifactInspector reduces cognitive load, makes version/diff/trace capabilities discoverable on every artifact type, and gives AI-Agents a stable UI contract to drive via MCP-driven actions.

**Acceptance Criteria:**
- AC1: Every artifact detail page of the 10 supported artifact types renders the ArtifactInspector in the right column of the split-view.
- AC2: The ArtifactInspector exposes VersionPanel, DiffPanel, and TracePanel in this fixed order.
- AC3: The user can collapse the entire sidebar and pin it open; both states are persisted per user session.
- AC4: The TracePanel shows inbound and outbound TraceLinks grouped by link type, and supports a type filter (multi-select).
- AC5: The VersionPanel lists all available versions of the artifact, allows switching the displayed version, and shows a baseline indicator (e.g. "In Baseline: v1.2.0 (Project, 2026-07-01)").
- AC6: The DiffPanel accepts any two selectable versions as inputs and renders a field-level diff (added / changed / removed).
- AC7: The ArtifactInspector is keyboard-navigable (Tab order: sidebar → panel headers → panel content; focus visible), exposes ARIA roles (`complementary`, `region`, `tab`/`tabpanel` per panel), and supports screen readers in both German and English.
- AC8: All user-visible strings of the ArtifactInspector follow the i18n key naming convention `sidebar.inspector.*`, `sidebar.version.*`, `sidebar.diff.*`, `sidebar.trace.*` and are translated for both `de` and `en`.
- AC9: The unified sidebar supersedes the existing inline `Traceability-Seitenleiste` of the Requirement editor and the `verknuepfte Requirements in Seitenleiste` of the Architecture editor — those inline widgets are removed.

**Derived from:** User-Request "UI Unification of the Right Sidebar (ArtifactInspector)" 2026-07-06
**Derived L1:** new L1-requirements REQ-L1-089 (Unified Right Sidebar Shell) through REQ-L1-095 (Adoption on 10 artifact types)
**Cross-references:** REQ-L0-009 (DE/EN i18n), REQ-L0-003 (Traceability), REQ-L0-028 (Visual Diffing), REQ-L0-004 (Baselines), REQ-L0-017 (ICDs), REQ-L0-018 (ADRs/Risks/Issues), REQ-L0-042 (Ontology variety)


### REQ-L0-063 — SN-63: i18n-Leak beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-004.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Rohe Translation-Keys dürfen nicht in der UI angezeigt werden. Bestätigte Fälle: editor.status (ADRs, Risiken, Testfälle), workspace.create.submit (Neuer-Workspace-Button). Alle vergleichbaren Fälle beheben.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-004)

---

### REQ-L0-064 — SN-64: Link-Erstellen-Dialog vereinheitlichen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-005.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein gemeinsamer CreateTraceLinkDialog wird in Architektur, Impact-Analyse (TraceabilityView) und ADRs verwendet. Enthält Suchfeld, Elementtyp-Filter und zeigt Titel (nicht nur IDs). Öffnet als Modal (kein Layout-Shift).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-005)

---

### REQ-L0-065 — SN-65: Soft-Delete-Statusmodell

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-006.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Architektur-Elemente, ADRs und Glossar-Einträge können nicht mehr von normalen Nutzern physisch gelöscht werden. Stattdessen: Status outdated/deprecated/deleted (lifecycle_status bei ArchitectureElement/GlossaryTerm; Adr.Status.DELETED). Gelöschte Elemente werden in Normalansicht ausgeblendet (?include_deleted=true für Admin-Zugriff). Hartes Löschen nur via Django Admin. TODO: Requirements/StakeholderNeeds haben unvalidiertes status-Feld — Soft-Delete dort in separatem Ticket nachziehen.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-006)

---

### REQ-L0-066 — SN-66: Splitter-Fix und Badge-Kürzel

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-007.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Splitter-Hitbox auf min. 8px verbreitern (Anforderungen, Diagramme). Element-Typ-Badges auf Kürzel reduzieren (SysRec→SR, Component→C etc.) in Baum-Ansichten.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-007)

---

### REQ-L0-067 — SN-67: KI-Ableitungs-Button

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-008.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] KI-Ableitungs-Button in Bedarfe muss Ergebnis anzeigen (kein stilles Versagen): Fehler rot mit role="alert", Erfolg in normaler Textfarbe. Anforderungen-View erhält den gleichen AI-Derivation-Button wie Bedarfe (✨ Ableiten via decompose-next-level).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-008)

---

### REQ-L0-068 — SN-68: Validation-Fehlermeldungen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-009.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Beim Speichern in Anforderungen werden alle Validierungsfehler mit Feldname und Beschreibung angezeigt, nicht nur "validation failed".

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-009)

---

### REQ-L0-069 — SN-69: Tags-Implementierung (Probleme)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-010.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Tags in der Probleme-Ansicht müssen funktionsfähig sein: hinzufügen (Enter/Komma), entfernen (X-Klick), speichern und nach Reload anzeigen.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-010)

---

### REQ-L0-070 — SN-70: Testlauf abschließen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-012.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Der "Confirm/Abschließen"-Button in Testläufen muss den Testlauf sichtbar abschließen: TestRuns ohne Testergebnisse müssen einen terminalen Status ("closed") erhalten statt bei "in_progress" zu verharren; nach dem Abschließen zeigt die Detailansicht eine Erfolgsmeldung statt kommentarlos zu schließen; Fehler werden sichtbar angezeigt.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-012)

---

### REQ-L0-071 — SN-71: Lifecycle-Status für Requirements und Stakeholder-Needs

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-013.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Requirements und StakeholderNeeds erhalten lifecycle_status-Feld (active/deprecated/archived). Soft-Delete statt physisches Löschen implementieren — gelöschte Elemente in UI ausgeblendet, nur für Admin sichtbar via ?include_deleted=true.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-013)

---

### REQ-L0-072 — SN-72: Item-Permissions User-Picker

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-014.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Must — Ein neuer GET-Endpoint (z.B. /api/v1/workspaces/{id}/members/) liefert die Workspace-Mitgliederliste mit mind. user_id, Anzeigename und E-Mail-Adresse. PermissionsSection.tsx ersetzt das fehleranfällige UUID-Freitext-Eingabefeld durch ein Dropdown oder Autocomplete-Feld, das Workspace-Mitglieder nach Name oder E-Mail durchsuchbar macht und die user_id automatisch befüllt. Akzeptanzkriterien: 1. Der neue Endpoint ist nur für authentifizierte Workspace-Mitglieder erreichbar. 2. Das bestehende ItemPermission-Datenmodell (permission_level: read/write/none) sowie das RBAC-Rollenmodell (admin/editor/viewer/approver) bleiben semantisch unverändert. 3. Vorhandene Item-Permissions funktionieren nach dem Update weiterhin korrekt. 4. Das Workflows-Redesign (WorkflowsSection.tsx) ist explizit nicht Teil dieser Anforderung.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-014)

---

### REQ-L0-073 — SN-73: Workspace-Einstellungen Redesign

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-015.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Workspace-Einstellungen-Ansicht wird von einer vertikalen Liste inkonsistenter Karten zu einer klaren Sektions-/Tab-Struktur umgebaut. Einheitliches Karten-/Formular-Layout (gemeinsamer Card-Style analog ApiKeysSection) über alle Panels; Gruppierung der Einstellungen in Tabs (Allgemein, Traceability, Sichtbarkeit, LLM & Prompts, Workflows & Berechtigungen, Administration). Bestehende Funktionalität und Feature-Flags (Baselines/Backup-Restore) bleiben erhalten. Reines Frontend-Redesign ohne funktionale Änderungen an den Subkomponenten.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-015)

---

### REQ-L0-074 — SN-74: Custom Fields workspace-weit

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-016.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Workspace-Administratoren können für einen Workspace benutzerdefinierte Felder (Custom Fields) mit Name, Typ (Text, Zahl oder Dropdown mit vordefinierten Optionen) und Pflichtfeld-Kennzeichen definieren. Die Felddefinitionen gelten workspace-weit und stehen an allen Artefakten (Requirements, Architecture Elements, Testfälle etc.) als zusätzliche Eingabefelder zur Verfügung. Eingetragene Werte werden je Artefakt-Instanz persistiert und sind nach Reload abrufbar. Die Verwaltung der Felddefinitionen erfolgt über die Workspace-Einstellungen.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-016)

---

### REQ-L0-075 — SN-75: API-Key-Klartext-Logging entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-017.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] API-Keys dürfen nicht im Klartext in Logs protokolliert werden. Debug-Log-Zeilen in mcp_server/views.py:59-62 entfernen; nur maskierte Präfixe (rfk_…xxxx) auf DEBUG-Level erlaubt. (SYSTEM_AUDIT P-01)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-017)

---

### REQ-L0-076 — SN-76: API-Key aus SSE-Endpoint-URL entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-018.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] API-Key darf nicht als Query-Parameter in SSE-Endpoint-URLs übergeben werden. Session-Binding erfolgt serverseitig via Session-Token statt Key in URL (mcp_server/views.py:219). (SYSTEM_AUDIT P-02)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-018)

---

### REQ-L0-077 — SN-77: IDOR-Fix ApiKeyViewSet.destroy

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-019.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] ApiKeyViewSet.destroy muss Ownership-Check durchführen. Fremde API-Keys werden mit HTTP 404 abgelehnt, nicht 403 (backend/rest_api/api_key_views.py). (SYSTEM_AUDIT A-01)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-019)

---

### REQ-L0-078 — SN-78: Event-Bus Race-Condition: atomare Claims

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-020.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] DomainEventBus.poll_and_dispatch() nutzt atomare Row-Locks (select_for_update(skip_locked=True) in transaction.atomic()) um Race-Conditions und Event-Doppelverarbeitung bei mehreren Celery-Workern auszuschließen. (SYSTEM_AUDIT S-01)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-020)

---

### REQ-L0-079 — SN-79: DLQ-Move atomar durchführen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-021.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] DomainEventBus DLQ-Move erfolgt atomar: DLQ-Insert und Outbox-Update in einer transaction.atomic()-Klammer, um Datenverlust/Doppelverarbeitung bei Ausfällen auszuschließen. (SYSTEM_AUDIT S-02)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-021)

---

### REQ-L0-080 — SN-80: StakeholderNeedService RBAC-Gate

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-022.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] StakeholderNeedService.create() implementiert RBAC-Gate: Permission-Check (Rolle + Workspace-Berechtigung) am Service-Eingang vor Erzeugung (backend/application/stakeholder_need_service.py). (SYSTEM_AUDIT S-03)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-022)

---

### REQ-L0-081 — SN-81: WorkspaceService.clone_workspace() Hierarchie-Fix

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-023.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] WorkspaceService.clone_workspace() nutzt old_id→new_instance-Map zur korrekten Parent-Child-Hierarchie in geklonten Workspaces. Regressionstest mit ≥2 Ebenen Tiefe erforderlich. (SYSTEM_AUDIT S-04)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-023)

---

### REQ-L0-082 — SN-82: Frontend Prod-Build reparieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-024.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Frontend Dockerfile kopiert package-lock.json nicht (Zeile 8) und nutzt `npm ci --only=production` (Zeile 24) — Build-Toolchain (tsc/vite) fehlt im Image, Prod-Build schlägt hart fehl. Fix: package-lock.json COPY ergänzen, --only=production entfernen. Zusätzlich VITE_* als Build-Args durchreichen (docker-compose.yml:150-153). Referenz: DEEP_SYSTEM_ANALYSIS.md FE-1/INF-1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-024)

---

### REQ-L0-083 — SN-83: eslint-plugin-react-hooks aktivieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-025.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] eslint-plugin-react-hooks ist nicht installiert — keinerlei Hook-Prüfung (rules-of-hooks, exhaustive-deps) im Projekt. Plugin in package.json ergänzen und in eslint.config.js aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-025)

---

### REQ-L0-084 — SN-84: CI-Pipeline für pytest, Vitest und Lint

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-026.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Einziger CI-Workflow ist playwright.yml (E2E). Kein CI für die 1042 Backend-pytest-Tests, kein Vitest, kein ESLint/mypy. GitHub Actions Workflow anlegen: backend-pytest-Job, frontend-vitest-Job, lint-Job. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-026)

---

### REQ-L0-085 — SN-85: Backend runserver durch gunicorn/uvicorn ersetzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-027.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/Dockerfile:32 und docker-compose.yml:100-102 nutzen Django-Dev-Server (runserver) als Prod-Kommando — single-threaded, nicht produktionsgeeignet. Ersetzen durch gunicorn oder uvicorn, collectstatic aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-027)

---

### REQ-L0-086 — SN-86: Source-Bind-Mounts aus Production-Compose entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-028.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:91-92 und :128-129 mounten ./backend:/app und ./frontend:/app als Volumes in die als "Production-Ready" bezeichnete Compose — Source-Code-Mounts gehören in docker-compose.override.yml. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-4

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-028)

---

### REQ-L0-087 — SN-87: Postgres/Redis Host-Ports nicht publishen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-029.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:39-40 (Postgres 5432) und :54-55 (Redis 6379) publishen Ports auf den Host — widerspricht dem eigenen Security-Kommentar in Zeile 24. Ports aus der Production-Compose entfernen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-5

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-029)

---

### REQ-L0-088 — SN-88: Celery-Beat-Service in docker-compose ergänzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-030.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml enthält keinen celery-beat-Service — periodische Tasks (inkl. Outbox-Consumer BE-1) können nie feuern. Dedizierter beat-Service mit korrektem Command und depends_on ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-6

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-030)

---

### REQ-L0-089 — SN-89: nginx SPA-Routing (History-API-Fallback)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-031.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/Dockerfile:35-36 hat TODO für nginx.conf — Deep-Links in der React-SPA liefern 404, da nginx keine try_files-Regel für index.html hat. nginx.conf mit SPA-Fallback ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-7

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-031)

---

### REQ-L0-090 — SN-90: Outbox-Consumer als Celery-Beat-Task registrieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-032.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/application/event_bus.py:242 definiert poll_and_dispatch(), wird aber von keinem Celery-Task, keinem Beat-Schedule und keinem Management-Command aufgerufen — Outbox füllt sich, Events werden nie dispatcht. Als periodischen Beat-Task registrieren (z.B. alle 5 s). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-032)

---

### REQ-L0-091 — SN-91: Django CACHES auf Redis konfigurieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-033.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/reqflow/settings.py enthält keine CACHES-Konfiguration — Django fällt auf LocMemCache (pro-Prozess, unsynchronisiert) zurück. Root-Cause für alle 4 In-Process-Caches. Redis-Cache-Backend konfigurieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-033)

---

### REQ-L0-092 — SN-92: _paginate auf QuerySet-Slicing umstellen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-034.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] BaseEntityViewSet._paginate (backend/rest_api/views.py:160) materialisiert vollständige Listen vor der Paginierung — alle 16 ViewSet-List-Endpoints sind O(N) in Speicher und Zeit. Auf DRF-Paginator mit QuerySet-Slicing umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-034)

---

### REQ-L0-093 — SN-93: SSE-PubSub Redis-Connection-Pool

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-035.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/sse_pubsub.py:31-49 öffnet pro Publish-Call eine neue Redis-Connection statt einen Connection-Pool zu verwenden. Auf redis.ConnectionPool umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-4

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-035)

---

### REQ-L0-094 — SN-94: API-Key in Redis mit Django-Signing absichern

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-036.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/sse_pubsub.py:33 speichert den Roh-API-Key als Redis-Value — schwächt den REQ-018-Fix. Reversible Verschlüsselung (Django-Signing) statt Klartext speichern und Vergleich entsprechend anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-5

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-036)

---

### REQ-L0-095 — SN-95: pytest auf dedizierte Test-Settings umstellen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-037.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/pyproject.toml konfiguriert pytest gegen Prod-Settings — Tests erben Prod-Cache-, Celery- und LLM-Einstellungen. Dedizierte backend/reqflow/settings_test.py anlegen und in pyproject.toml referenzieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-6

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-037)

---

### REQ-L0-096 — SN-96: Cache-Invalidierungsstrategie implementieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-038.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die 4 In-Process-Caches haben keine Invalidierungsstrategie — Schreiboperationen eines Workers sind für andere unsichtbar. Nach BE-2/REQ-033: Signal-basierte Invalidierung (post_save/post_delete) oder TTL-Strategie für alle django.core.cache-Nutzungen definieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-7

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-038)

---

### REQ-L0-097 — SN-97: Composite-Indexes für dominante Filterkombinationen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-039.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/persistence/models.py fehlen Composite-Indexes für die häufigsten Filterkombinationen (tenant_id+workspace+type, tenant_id+status) — Row-Level-Security filtert immer auf tenant_id, ListEndpoints zusätzlich auf workspace/type/status. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-8

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-039)

---

### REQ-L0-098 — SN-98: Multi-Worker-Konsistenz Deployment-Constraint dokumentieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-040.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Bis BE-2/REQ-033 und BE-7/REQ-038 vollständig umgesetzt sind, machen In-Process-Caches + fehlende Invalidierung jedes Deployment mit >1 Worker inkonsistent. Constraint explizit in settings.py und Deployment-Docs dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-9

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-040)

---

### REQ-L0-099 — SN-99: derive_requirements in Anthropic/Ollama/Azure implementieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-041.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] llm_adapter/interface.py:136 deklariert derive_requirements als @abstractmethod. Nur MockLlmProvider und OpenAiProvider implementieren es — Anthropic (providers.py:366), Ollama (providers.py:640) und Azure (providers.py:736) werfen beim Instanziieren TypeError. Alle drei Provider implementieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F2.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-041)

---

### REQ-L0-100 — SN-100: Async-LLM-Pfad reparieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-042.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] dispatcher.py:66-97 instanziiert ad-hoc eine neue Celery-App im Web-Prozess und sendet llm_adapter.run_capability — ein Task-Name, den der Worker (reqflow/celery.py) nie registriert hat. Broker nimmt Message an, Worker verwirft sie, Status bleibt ewig PENDING. Task korrekt im Worker registrieren und Dispatcher anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-042)

---

### REQ-L0-101 — SN-101: RBAC-Bypass: fehlende MCP-Tool-Prefixes ergänzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-043.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] mcp_server/tool_registry.py:52-77 klassifiziert Schreib-Tools per Prefix-Liste — needs.*, adr.*, risk.*, issue.*, glossary.*, prompt_template.* fehlen. Ein API-Key mit Viewer-Rolle kann darüber Daten schreiben; prompt_template.*-Write ermöglicht persistente Prompt-Injection. Alle fehlenden Prefixes in _WRITE_TOOL_PREFIXES aufnehmen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-043)

---

### REQ-L0-102 — SN-102: SSE-GET-Crash und Handshake-Auth beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-044.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] mcp_server/views.py:62-78 kombiniert synchrones CorsMixin.dispatch mit async def get → TypeError bei jedem GET /mcp/sse/. Zusätzlich fehlt API-Key-Check beim Handshake (DoS-Vektor). Sync/Async-Konflikt auflösen und Auth beim Handshake ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-044)

---

### REQ-L0-103 — SN-103: requirement.validate TypeError beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-045.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] mcp_server/tools/requirements.py:425 ruft validate_artifact(str(req_id), ctx=auth_context) auf — die Facade akzeptiert nur artifact_id (kein ctx-Parameter). Jeder Aufruf endet im TypeError. Signatur-Mismatch korrigieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F1.2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-045)

---

### REQ-L0-104 — SN-104: Artefakt-Inhalt in LLM-Provider-Prompts aufnehmen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-046.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Provider-Prompt-Builder (providers.py:431,541,621,717,810) interpolieren nur Artefakt-UUIDs, nie den Artefakt-Inhalt. LLM halluziniert bei decompose/validate/check_consistency zwangsläufig. Artefakt-Inhalt aus dem Repository laden und in Prompt einbetten. Referenz: DEEP_SYSTEM_ANALYSIS.md F3.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-046)

---

### REQ-L0-105 — SN-105: JSON-RPC-Error-Format auf Spec bringen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-047.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] mcp_server/protocol_handler.py:154-165 gibt Fehler als {"error_code": "...", "message": "..."} zurück statt {"code": <int>, "message": <str>} gemäß JSON-RPC 2.0 Spec — Standard-MCP-Clients sind inkompatibel. Format korrigieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-047)

---

### REQ-L0-106 — SN-106: LLM-Interface-Vertrag vervollständigen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-048.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] complete() existiert auf Providern aber nicht im Interface (kein statischer Vertrag). OpenAI-derive_requirements greift auf nicht existentes self._model zu, verletzt Layer-Grenzen durch direkten Persistence-Zugriff und nutzt print statt logger. Interface vervollständigen und OpenAI-Implementierung bereinigen. Referenz: DEEP_SYSTEM_ANALYSIS.md F2.2/F2.3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-048)

---

### REQ-L0-107 — SN-107: React-Query-Migration (State Management)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-049.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Handgerollte use*Data-Hooks (useAdrData, useRiskData, useIssueData, useNeedData, useArchitectureData) auf @tanstack/react-query migrieren — behebt gleichzeitig fehlendes AbortController-Cleanup (FE-6), klebenden Error-State (FE-7) und Fünffach-Duplikation (FE-4). React Query ist bereits installiert und in 4 Dateien genutzt. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-3/FE-4/FE-6/FE-7

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-049)

---

### REQ-L0-108 — SN-108: Monster-Komponenten zerlegen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-050.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] 5 Komponenten >= 1000 Zeilen (CanvasEditor.tsx 1605, IcdView.tsx 1483, BaselinesView.tsx 1461, DiagramView.tsx 1036, TestRunsList.tsx 1000) mischen Datenladen, UI-State, Formular-Logik und Rendering. Container/Presenter-Trennung + Fetch-Logik in Query-Hooks auslagern. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-5

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-050)

---

### REQ-L0-109 — SN-109: 401/403-Unterscheidung im API-Client

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-051.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/src/api/client.ts:64-74 behandelt 401 und 403 identisch — 403 (Berechtigungsfehler) loggt den User aus statt "keine Berechtigung" anzuzeigen. Separate Handler für 401 (Logout) und 403 (Fehlermeldung ohne Logout). Referenz: DEEP_SYSTEM_ANALYSIS.md FE-8

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-051)

---

### REQ-L0-110 — SN-110: Auth-Token aus sessionStorage entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-052.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/src/context/AuthContext.tsx:93,149 speichert Auth-Token in sessionStorage — XSS-lesbar. Auf httpOnly-Cookie (bevorzugt) oder In-Memory-Storage + Refresh-Token-Rotation umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-9. Umgesetzt: httpOnly-Cookie `reqflow_access` (SameSite=Lax, Secure außer DEBUG), Dual-Read (Header+Cookie), CSRF-Enforcement für Cookie-Pfad, POST /auth/logout/, /auth/me/-Bootstrap; sessionStorage-Token/-User entfernt.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-052)

---

### REQ-L0-111 — SN-111: Frontend-Testabdeckung große Views

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-053.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die 5 größten, ungetesteten Views (IcdView, DiagramView, BaselinesView, ArtifactDiff, TraceabilityView) sowie alle use*Data-Hooks sind nicht getestet. Tests ergänzen — mindestens Smoke-Tests für Render und Hauptinteraktionen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-10

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-053)

---

### REQ-L0-112 — SN-112: Code-Splitting via React.lazy

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-054.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] mermaid (~2 MB) und fabric landen im monolithischen Haupt-Bundle. React.lazy + Suspense für DiagramView.tsx und CanvasEditor.tsx einführen. frontend/src/App.tsx anpassen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-11

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-054)

---

### REQ-L0-113 — SN-113: i18n konsequent ausrollen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-055.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] i18next/react-i18next ist in 71 Frontend-Dateien aktiv genutzt (useTranslation); die ursprüngliche Analyse-Prämisse "nur 3 Dateien" war falsch. Die Dependency soll bleiben. Offene Aufgaben: fehlende Übersetzungsschlüssel vervollständigen (DE/EN), alle raw-string-Literals in noch nicht migrierten Komponenten durch t()-Aufrufe ersetzen, Translation-Files auf Vollständigkeit prüfen und ggf. Namespacing einführen.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-055)

---

### REQ-L0-114 — SN-114: Accessibility-Basisabsicherung

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-056.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Nur 20 aria-/role-Treffer in 10 von 117 Komponenten. eslint-plugin-jsx-a11y in frontend/eslint.config.js ergänzen + aktivieren. Offensichtliche A11y-Fehler in häufig genutzten Komponenten beheben. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-13

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-056)

---

### REQ-L0-115 — SN-115: Redis absichern

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-057.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:51-61 konfiguriert Redis ohne Passwort, ohne maxmemory-Policy und ohne Persistenz. requirepass setzen, maxmemory + maxmemory-policy volatile-lru konfigurieren, AOF-Persistenz für Broker-Zuverlässigkeit aktivieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-8

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-057)

---

### REQ-L0-116 — SN-116: Unsichere DB-Password-Defaults entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-058.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:36,78,119 nutzt DB_PASSWORD:-reqflow als stillen Trivial-Passwort-Default. Fail-Fast-Verhalten: Fehler wenn DB_PASSWORD nicht gesetzt, kein Default. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-9

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-058)

---

### REQ-L0-117 — SN-117: USER-Direktive in Dockerfiles

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-059.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/Dockerfile und frontend/Dockerfile laufen Container als root — kein USER definiert. Dedizierten Non-Root-User anlegen und als USER setzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-10

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-059)

---

### REQ-L0-118 — SN-118: Healthchecks für Backend und Celery

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-060.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:66-102,142-157 hat keine Healthchecks für backend- und celery-Service. depends_on ohne condition wartet nicht auf Backend-Readiness. Healthcheck-Direktiven für beide Services ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-11

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-060)

---

### REQ-L0-119 — SN-119: Backend-Dockerfile Multi-Stage

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-061.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/Dockerfile ist Single-Stage: gcc/libpq-dev (~150 MB Build-Dependencies) verbleiben im Runtime-Image. Multi-Stage-Build: Builder-Stage mit Dev-Dependencies, Runtime-Stage nur mit installierten Packages. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-12

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-061)

---

### REQ-L0-120 — SN-120: Secrets nicht als Compose-Env-Variables

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-062.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:73,115 gibt Secrets direkt als environment-Werte an Container (via docker inspect lesbar). Auf env_file mit .env-Datei oder Docker Secrets umstellen. Trennung von Infra-Config und Secrets dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-13

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-062)

---

### REQ-L0-121 — SN-121: Observability-Grundausstattung

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-063.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Keinerlei Metriken-, Tracing- oder Log-Aggregations-Infrastruktur vorhanden. Mindest-Maßnahmen: strukturierte JSON-Logs (django-structlog oder python-json-logger), /metrics-Endpoint (django-prometheus), Celery-Task-Metriken, Outbox-Backlog-Gauge. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-14

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-063)

---

### REQ-L0-122 — SN-122: Migration aus Container-Startkommando lösen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-064.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:100-102 führt migrate im Startkommando aus — Race-Condition bei mehreren Replicas. Dedizierter Init-Container oder Startup-Job für Migrationen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-15

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-064)

---

### REQ-L0-123 — SN-123: CI loaddata Fixture-Fehler sichtbar machen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-065.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] .github/workflows/playwright.yml:65 nutzt loaddata initial_data

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-065)

---

### REQ-L0-124 — SN-124: Service-Layer-Grenzen schärfen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-066.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Option B (Django-idiomatisch): kein direkter ORM-Zugriff in rest_api/ (Views), ORM gekapselt in Application-/Domain-Services; wiederverwendete/komplexe Queries in Custom Manager/QuerySets. Phase 1 (Writes aus Views, 34de8ab–d85ba5d), Phase 2 (Reads: ArtifactService.list_child_summaries/resolve_artifact_titles/collect_artifact_names, Commit b50ed5c) und Phase 3 (BE-10-Hotspot allocation_coverage → TraceLinkService.get_requirement_allocations, Latent-Bug get_with_level gefixt, Commit b013d0c) vollständig abgeschlossen. views.py ist jetzt vollständig ORM-frei (Guardrail-Ratchet auf 0). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-10

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-066)

---

### REQ-L0-125 — SN-125: factory-boy-Entscheidung

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-067.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] factory-boy ist in backend/requirements.txt deklariert, wird aber nirgends genutzt (alle Fixtures manuell). Entscheidung: entweder key-Fixtures auf factory-boy migrieren oder Dependency aus requirements.txt streichen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-11

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-067)

---

### REQ-L0-126 — SN-126: conftest.py-Fossil bereinigen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-068.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/conftest.py enthält tote Fixtures/Konfiguration. Aufräumen: tote Fixtures entfernen, aktive Fixtures kommentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-12

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-068)

---

### REQ-L0-127 — SN-127: Outbox-Monitoring: Backlog-Gauge

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-069.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/application/event_bus.py exponiert weder Backlog-Größe noch DLQ-Umfang als Metrik oder Log. Nach poll_and_dispatch() Backlog-Größe und DLQ-Count loggen (INFO-Level) damit stilles Liegenbleiben erkennbar wird. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-13

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-069)

---

### REQ-L0-128 — SN-128: N+1-Audit für alle 16 ViewSets

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-070.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/rest_api/views.py und serializers.py haben in mehreren ViewSets fehlende select_related/prefetch_related-Aufrufe. Alle 16 ViewSets auditieren, N+1-Stellen mit select_related/prefetch_related beheben. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-14

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-070)

---

### REQ-L0-129 — SN-129: API-Fehlerformat-Konsistenz (REST vs. MCP)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-071.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] DRF-Endpoints und MCP-Server (backend/mcp_server/protocol_handler.py) geben unterschiedliche Fehlerformate zurück. Gemeinsames Error-Envelope definieren und beide Seiten darauf vereinheitlichen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-15

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-071)

---

### REQ-L0-130 — SN-130: Celery-Task-Idempotenz für Outbox-Dispatch

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-072.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Outbox-Dispatch braucht at-least-once-taugliche, idempotente Handler. Jeder Handler muss bei Wiederholung dasselbe Ergebnis liefern (Idempotenz-Key oder Datenbank-Constraint). Referenz: DEEP_SYSTEM_ANALYSIS.md BE-16

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-072)

---

### REQ-L0-131 — SN-131: Transaktionsgrenzen dokumentieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-073.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Unklar welche Service-Methoden in atomic() laufen und wann Domain-Events relativ zum Commit gefeuert werden. Transaktionsgrenzen in backend/application/** durch Inline-Kommentare und/oder eine Tabelle im ARCHITECTURE.md dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-17

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-073)

---

### REQ-L0-132 — SN-132: DB-Query-Logging in Dev aktivieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-074.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/reqflow/settings.py hat kein LOGGING-Setup für SQL-Queries in Dev. django-silk oder LOGGING['django.db.backends'] auf DEBUG in Test-/Dev-Settings aktivieren um O(N)- und N+1-Regressionen sichtbar zu machen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-18

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-074)

---

### REQ-L0-133 — SN-133: Test-Pyramide rebalancieren + Wiring-Tests

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-075.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] 1042 grüne Tests haben toten Async-Pfad, crashendes SSE und nicht instanziierbare Provider nicht erkannt. Wiring-Tests ergänzen: jeder Celery-Task registriert, jeder Beat-Eintrag vorhanden, jede URL antwortet mit korrekter Server-Klasse. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-19

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-075)

---

### REQ-L0-134 — SN-134: Paginierungs-Verträge in OpenAPI dokumentieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-076.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Paginierungsverhalten (Cursor vs. Offset, Seitengröße, Gesamtzahl) ist nicht explizit definiert. In OpenAPI-Schema via drf-spectacular verankern; Paginierungsparameter als standardisierte Query-Params dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-20

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-076)

---

### REQ-L0-135 — SN-135: Celery-Routing/Queues definieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-077.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/reqflow/celery.py nutzt Single-Queue für alle Tasks. Separate Queues für LLM-Tasks (llm), Events (events) und Standard-Tasks (default) definieren — Voraussetzung für getrennte Skalierung. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-21

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-077)

---

### REQ-L0-136 — SN-136: Stiller Mock-Fallback markieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-078.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/application/ai_derivation_service.py:342-345 fällt bei jedem LLM-Fehler still auf MockProvider zurück — Nutzer erhält unmarkierten Fake-Content. Fallback-Ergebnisse als provider: "mock-fallback" kennzeichnen und im Response-Body ausweisen; besser: Fehler propagieren statt still faken. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-078)

---

### REQ-L0-137 — SN-137: Echte Input-Schemas für 11 MCP-Tool-Gruppen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-079.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/tools/base.py:125-146 fällt für 11 von 14 Tool-Gruppen auf {"kwargs": {"type": "object"}} zurück — MCP-Clients sehen keine Parameternamen oder -typen. Jede Tool-Gruppe bekommt ein konkretes JSON-Schema mit expliziten Parameter-Definitionen. Referenz: DEEP_SYSTEM_ANALYSIS.md F1.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-079)

---

### REQ-L0-138 — SN-138: Prompt-Injection-Oberfläche reduzieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-080.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/llm_adapter/providers.py (alle Prompt-Builder) interpolieren User-Content ungefiltert ohne Delimiter oder Escaping in Prompts. Delimiter-basiertes Escaping oder Instruction-Hierarchie (System/User-Trennung) einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-080)

---

### REQ-L0-139 — SN-139: Klartext-Secrets in Persistenz beseitigen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-081.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] API-Key als Klartext in Redis (sse_pubsub.py:33, schwächt REQ-036-Fix), Provider-api_key im Klartext in Postgres (persistence/models.py:1217), CORS * mit Credentials-Flag. Alle Stellen auf sichere Speicherung umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md F6.4

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-081)

---

### REQ-L0-140 — SN-140: Retry/Circuit-Breaker für LLM-Calls

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-082.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/resilience/-Modul existiert, wird aber nicht genutzt. LLM-Provider-Aufrufe in providers.py durch Retry-Wrapper (exponential backoff, max 3 Versuche) und Circuit-Breaker aus dem vorhandenen resilience/-Modul schützen. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-082)

---

### REQ-L0-141 — SN-141: Tenant-LLM-Settings in Celery-Worker propagieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-083.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/llm_adapter/dispatcher.py übergibt per-Tenant-Provider-Konfiguration nicht an den Worker — wirkt nur im Sync-Pfad. Worker-Task muss Tenant-ID erhalten und Settings zur Laufzeit laden. Referenz: DEEP_SYSTEM_ANALYSIS.md F4.4

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-083)

---

### REQ-L0-142 — SN-142: Sync-LLM-Call auf Async-Pfad umlenken

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-084.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Nach REQ-042-Fix (Async-Pfad repariert): Sync-LLM-Calls in backend/llm_adapter/ blockieren den Request-Thread bis 30 s (Gunicorn-Worker-Erschöpfung). Auf den reparierten Async-Pfad umlenken oder zumindest Timeout setzen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-084)

---

### REQ-L0-143 — SN-143: Contract-Tests Provider + SSE-E2E-Tests

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-085.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Keine Contract-Tests die Provider gegen Interface-Vertrag prüfen (hätte F2.1 sofort gefangen). SSE-E2E-Tests testen tote API-Form (POST statt GET). Contract-Tests für alle 5 Provider + echte SSE-GET-E2E-Tests schreiben. Referenz: DEEP_SYSTEM_ANALYSIS.md F7.1/F7.2

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-085)

---

### REQ-L0-144 — SN-144: MCP-Tool-Fehler als isError-Result + Thread-Pool

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-086.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/protocol_handler.py meldet Tool-Fehler als JSON-RPC-Error statt als isError:true Tool-Result (MCP-Spec-Abweichung). Pro Message wird unbegrenzt Thread gestartet (OOM-Risiko). Thread-Pool einführen, Tool-Fehler als isError-Result formatieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.2/F8.4

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-086)

---

### REQ-L0-145 — SN-145: REQ-036 Beschreibung redaktionell anpassen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-087.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docs/REQUIREMENTS.md REQ-036-Eintrag beschreibt "SHA-256-Hash" — tatsächliche Implementierung nutzt Django-Signing (reversible Verschlüsselung für Downstream-Kompatibilität). Beschreibungstext auf "reversible Verschlüsselung (Django-Signing)" korrigieren. Kein Code-Change.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-087)

---

### REQ-L0-146 — SN-146: Service-Layer O(N) in list()-Aufrufen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-088.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Service-Methoden in backend/application/** geben teils list(queryset) zurück statt QuerySets zu delegieren — O(N)-Materialisierung auch außerhalb der View-Paginierung. Alle list(qs)-Aufrufe in Service-Methoden durch QuerySet-Delegation ersetzen. Follow-up aus REQ-034-Partial-Fix.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-088)

---

### REQ-L0-147 — SN-147: check_consistency-Verdrahtung und validate-MCP-Caller

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-089.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Nach REQ-046 (Artefakt-Inhalt in Prompts): kein Service-Aufrufer ruft check_consistency auf (Funktion nie erreichbar); requirement.validate MCP-Tool übergibt noch id-only. Service-Aufruf für check_consistency verdrahten, MCP-Tool-Caller auf inhaltstragende Signatur umstellen.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-089)

---

### REQ-L0-148 — SN-148: 9 vorbestehende E2E-Test-Failures in test_e2e_mcp.py

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-090.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] test_e2e_mcp.py hat 9 Failures die nicht durch P1-Wave verursacht wurden. Root-Cause analysieren, Failures beheben oder Tests als expected-failure markieren mit Issue-Referenz.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-090)

---

### REQ-L0-149 — SN-149: Listen-Virtualisierung für große Artefakt-Listen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-091.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] RequirementList.tsx:259 und NeedList.tsx:270 rendern vollständige Listen ohne Virtualisierung — kombiniert mit O(N)-Backend-Paginierung (REQ-034) skaliert das doppelt schlecht. react-window oder react-virtual einführen für lange Listen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-14

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-091)

---

### REQ-L0-150 — SN-150: Memoization in Hot-Paths ergänzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-092.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] React.memo/useMemo nur in 15 von 117 Komponenten-Dateien; in den größten Render-Bäumen (BaselinesView, IcdView) fehlt sie weitgehend. Gezielte Memoization in identifizierten Hot-Paths ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-15

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-092)

---

### REQ-L0-151 — SN-151: Typ-Löcher in API-Client schließen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-093.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/src/api/client.ts:47,93 enthält `undefined as unknown as T` bei 204-Responses und `as Record<string, string>`-Header-Cast — Null-Fehler werden zur Laufzeit verschoben. Typsichere Alternativen einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-16

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-093)

---

### REQ-L0-152 — SN-152: ESLint-Versions-Inkonsistenz beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-094.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/eslint.config.js behauptet "ESLint 9 flat config", frontend/package.json pinnt eslint ^8.57.0, globals ^17.7.0 setzt neuere Node-Umgebung voraus — widersprüchliche Versionsangaben bereinigen. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-17

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-094)

---

### REQ-L0-153 — SN-153: Prettier einführen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-095.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Keinerlei Formatter-Konfiguration im Frontend-Projekt. .prettierrc ergänzen, npm-Script für format/format:check, CI-Hook. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-18

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-095)

---

### REQ-L0-154 — SN-154: Test-Layout vereinheitlichen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-096.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Frontend-Tests liegen teils co-located (components/**/**.test.tsx), teils zentral (src/test/), teils als api/*.test.ts — einheitliche Konvention festlegen und dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-19

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-096)

---

### REQ-L0-155 — SN-155: fabric-Mock Contract-Test ergänzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-097.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] fabric-Mock-Alias nur in Vitest-Config (vite.config.ts:34-38) — Prod-Typprüfung und Test-Realität divergieren. Contract-Test gegen echtes fabric-Interface ergänzen um sicherzustellen dass der Mock die echte API abbildet. Referenz: DEEP_SYSTEM_ANALYSIS.md FE-20

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-097)

---

### REQ-L0-156 — SN-156: Node-Versionsdrift beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-098.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/Dockerfile baut mit node:22, CI-Workflow (.github/workflows/playwright.yml:86) testet mit node 20 — gleiche Version in Docker und CI verwenden. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-17

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-098)

---

### REQ-L0-157 — SN-157: Docker-Image-Versionen härten

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-099.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/Dockerfile:4,31 nutzt nginx:alpine und node:22-slim ohne Digest-/Minor-Pin — Image-Versionen mit vollständigem Tag oder Digest pinnen um reproduzierbare Builds zu gewährleisten. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-18

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-099)

---

### REQ-L0-158 — SN-158: E2E-CI gegen Prod-Build ausführen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-100.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] .github/workflows/playwright.yml:94-98 führt E2E-Tests gegen Vite-Dev-Server aus — Prod-Regressionen (wie der defekte Prod-Build) bleiben unsichtbar. E2E-Pipeline auf Docker-Prod-Build umstellen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-19

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-100)

---

### REQ-L0-159 — SN-159: Dependabot für Python- und npm-Dependencies aktivieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-101.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Kein automatisches Dependency-Update konfiguriert. .github/dependabot.yml mit Konfiguration für pip (backend) und npm (frontend) anlegen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-20

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-101)

---

### REQ-L0-160 — SN-160: Backup-Strategie für postgres_data-Volume

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-102.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] postgres_data-Volume (docker-compose.yml:159-160) hat keine Backup-Strategie. pg_dump-Script oder Sidecar-Service mit Cron-Scheduling einführen und in docker-compose.backup.yml dokumentieren. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-21

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-102)

---

### REQ-L0-161 — SN-161: Log-Rotation-Limit für Docker-Container

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-103.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] docker-compose.yml:32,53,70 setzt restart: unless-stopped ohne Log-Rotation — Log-Volumes wachsen unbegrenzt. logging.options.max-size und max-file für alle Services ergänzen. Referenz: DEEP_SYSTEM_ANALYSIS.md INF-22

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-103)

---

### REQ-L0-162 — SN-162: Read-Model für Traceability-Matrix

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-104.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/application/ berechnet die Traceability-Matrix durch Live-Graph-Traversierung — bei Extended-Rigor-Projekten mit tausenden Trace-Links skaliert das schlecht. Materialisierte Sicht oder Cache-Layer einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md BE-22

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-104)

---

### REQ-L0-163 — SN-163: Response-Caching für LLM-Derivation-Anfragen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-105.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/application/ai_derivation_service.py führt identische LLM-Anfragen wiederholt aus ohne Caching. Prompt-Hash-basiertes Caching (Django-Cache-Backend) für Derivation-Ergebnisse einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.1

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-105)

---

### REQ-L0-164 — SN-164: Token-Usage pro Tenant aggregieren und limitieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-106.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/llm_adapter/ loggt Token-Usage, speichert sie aber nicht auswertbar. Token-Verbrauch pro Tenant in der DB aggregieren, Query-API bereitstellen und konfigurierbares Limit mit 429-Response einführen. Referenz: DEEP_SYSTEM_ANALYSIS.md F5.3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-106)

---

### REQ-L0-165 — SN-165: SSE Event-IDs und Last-Event-ID-Replay

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-107.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/sse_pubsub.py liefert SSE-Events ohne Event-ID — bei Verbindungsabbruch gehen Events verloren (at-most-once). Event-IDs ergänzen und Last-Event-ID-Header für Replay-Unterstützung implementieren. Referenz: DEEP_SYSTEM_ANALYSIS.md F8.3

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-107)

---

### REQ-L0-166 — SN-166: MCP-Protokoll-Kleinigkeiten beheben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-108.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/protocol_handler.py und tool_registry.py: (1) Response auf notifications/initialized obwohl Notifications keine Antwort erwarten, (2) hartkodierte protocolVersion, (3) unbounded PresetCache ohne Größenlimit, (4) list_tools ignoriert RBAC (Viewer sieht Schreib-Tools). Referenz: DEEP_SYSTEM_ANALYSIS.md F8.5

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-108)

---

### REQ-L0-167 — SN-167: pgvector Python-Dependency ergänzen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-109.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Celery-Container crasht beim Start wegen fehlendem pgvector-Modul (ImportError). pgvector in backend/requirements.txt ergänzen und Dockerfile-Build sicherstellen. Neues Finding aus P2-Implementierungsbericht.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-109)

---

### REQ-L0-168 — SN-168: python-json-logger Dependency im Container sicherstellen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-110.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] python-json-logger fehlt im laufenden Container-Image (aus REQ-063, JSON-Logging-Feature). Dependency in backend/requirements.txt ergänzen und im Backend-Dockerfile sicherstellen dass der Package-Build korrekt erfolgt. Neues Finding aus P2-Implementierungsbericht.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-110)

---

### REQ-L0-169 — SN-169: Symmetrische Rollen-Auflösung für Bearer-Tokens

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-126.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Bearer-Token-Pfad verwendet JWT-Claims als einzige Rollen-Quelle. Wenn Rollen im JWT leer sind (neuer User / Rolle nach Login zugewiesen), erhalten Users 403 auf Schreib-Endpoints. Fix: DB-Fallback identisch dem API_KEY-Pfad wenn `claims.roles` leer ist (`auth_tenancy/rest.py`).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-126)

---

### REQ-L0-170 — SN-170: Decomposition backend/rest_api/views.py (P1 Architektur)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-111.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] views.py: 4524 Zeilen, 30+ ViewSets + 100+ Action-Methoden in einer Datei. Decompose in Domain-Submodule (views_artifacts.py, views_requirements.py, views_architecture.py, views_test_management.py etc.). Jedes Submodul enthält verwandte ViewSet-Gruppen (ein Domain pro Datei), reduziert Komplexität und Änderungsradius bei Fehlerbehebung. Blocking für skalable Architektur. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-111)

---

### REQ-L0-171 — SN-171: Decomposition backend/rest_api/serializers.py (P1 Architektur)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-112.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] serializers.py: 1110 Zeilen, 31 Serializer-Klassen in einer Datei. Analog views.py-Decomposition: serializers_artifacts.py, serializers_requirements.py etc. Ein Serializer-Set pro Domain. Bessere Übersicht und reduzierte Merge-Konflikte. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-112)

---

### REQ-L0-172 — SN-172: Decomposition CanvasEditor.tsx (P1 Frontend-Architektur)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-113.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] CanvasEditor.tsx: 1364 Zeilen, monolithische Canvas+Toolbar+Fabric.js-Lifecycle, 28 Hooks entangled (ToolbarState, GeometryState, SelectionState, etc.). Extract: ToolbarPresenter-Komponente, useCanvasState Hook (centralisiertes Canvas-State-Management), pure Geometry-Utility-Funktionen (Transformer-Kalkulationen, Path-Simplifizierung). Reduziert Complexity auf <500 Zeilen Pro-Subkomponente. Blocking für Bug-Fixes in Canvas. Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-113)

---

### REQ-L0-173 — SN-173: Decomposition SidebarNavigation.tsx (P1 Frontend-Architektur)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-114.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] SidebarNavigation.tsx: 821 Zeilen, Route-Registrierung + Preset-Gating, single Point of Failure (alle Route-Änderungen erfordern Edit dieser Datei). Extract: useRouteRegistry Hook (Zentrale Route-Deklaration + Visibility-Logic), usePresetVisibility Hook (Preset-basiertes Gating), RoutePresetPresenter Komponente. Ermöglicht dezentralisierte Route-Registrierung (Feature-Modules können eigene Routes anmelden). Status: Backlog (P1-Priorisierung nächste Phase).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-114)

---

### REQ-L0-174 — SN-174: Hardcoded Default-Secrets in settings.py (P2 Security)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-115.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/reqflow/settings.py Zeile 32 (SECRET_KEY = "CHANGE-ME-IN-PRODUCTION") und Zeile 267 (AUTH_JWT_SECRET = "CHANGE-ME-IN-PRODUCTION") sind Production-Deployment-Blocker. Fix: Secrets NICHT hardcoden, stattdessen zwingend aus ENV-Variablen laden. .env.example bereitstellen mit Secrets-Checklist und Kommentaren zu generierten Werten (Django-generierten SECRET_KEY, JWT-Secret-Generierung). Deployment-Docs: Fail-Fast-Verhalten wenn Secrets nicht gesetzt. Status: Backlog.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-115)

---

### REQ-L0-175 — SN-175: API-Contract-Drift TypeScript vs DRF (P2 API)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-116.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/src/types/index.ts vs backend/rest_api/serializers.py sind nur manuell synchronisiert. Empfehlung: OpenAPI Codegen-Integration einführen (drf-spectacular im Backend → OpenAPI-Schema-Export, TypeScript-Codegen in Frontend). Alternativ: TypeScript-Definitionenfile als Single Source of Truth mit Codegen in beide Richtungen (Backend-Validator, Frontend-Types). Reduziert Typ-Drift-Bugs um ~90%. Status: Backlog.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-116)

---

### REQ-L0-176 — SN-176: N+1 Queries in MCP-Server (P2 Performance)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-117.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/mcp_server/tools/requirements.py:58-71 (_requirement_to_dict) lädt Requirement→Artifact→Workspace ohne select_related/prefetch_related — pro Item min. 3 zusätzliche DB-Queries. Fix: n-Queries vor der Serialisierung mit select_related('artifact__workspace') laden, oder auf GraphQL-artige Feld-Selektion migrieren. Status: Backlog.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-117)

---

### REQ-L0-177 — SN-177: Multi-Worker Cache-Invalidierung unvollständig (P2 Non-Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-118.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] REQ-038 referenziert diesen Punkt: aktuell nur Single-Worker-Deployment sicher. backend/reqflow/settings.py:333-340 hat Cache-Konfiguration aber KEINE Invalidierungsstrategie nach Writes. Mehrere Worker sehen alte Werte. Fix: Signal-basierte Invalidierung (post_save/post_delete auf Domain-Models) oder TTL-Strategie für alle Cache-Keys. Test: ≥2 Worker, Write in Worker-1, Read in Worker-2 muss neue Wert sehen. Status: Backlog.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-118)

---

### REQ-L0-178 — SN-178: React-Query-Migration zu 92% fertig (P2 Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-119.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] REQ-049 (React-Query-Migration) zu 92% implementiert. Offene Aufgaben: 2 verbleibende Hooks (useTestCaseData.ts und useDashboardData.ts) noch mit useState+useEffect+fetch statt TanStack Query implementiert. Migriere diese 2 Hooks zu @tanstack/react-query QueryClient, align Error/Loading-States mit bestehenden Patterns (useAdrData, useRiskData, etc.). Status: Backlog (sollte vor RC-Release done sein).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-119)

---

### REQ-L0-179 — SN-179: Container/Presenter zu 90% fertig (P2 Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-120.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] REQ-050 (Monster-Komponenten-Zerlegung) zu 90% implementiert. Offenes TODO in TestRunDetailEditor.tsx:12-13: testRunsApi.listResults() ruft noch direktes API auf statt über useTestRunsData Hook zu gehen. Extract useTestRunsData Hook (oder nutze bestehenden entsprechenden Hook), migiere TestRunDetailEditor zu Container/Presenter-Pattern (Daten-Container in Container-Komponente, UI-Rendering in Presenter). Status: Backlog (sollte vor RC-Release done sein).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-120)

---

### REQ-L0-180 — SN-180: DEFAULT_TENANT_ID hardcoded (P3 Non-Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-121.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] backend/reqflow/settings.py:358 — DEFAULT_TENANT_ID ist hardcoded zu '1'. Für echte Multi-Tenancy vorsehen: ENV-Var DJANGO_DEFAULT_TENANT_ID mit Fallback oder ganz aus Code entfernen (Multi-Tenancy sollte request-aware sein, nicht global). Status: Backlog (P3 Optimierung).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-121)

---

### REQ-L0-181 — SN-181: Frontend-Monolithen-Kandidaten (P3 Non-Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-122.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] DecompositionTree.tsx (835 Zeilen) und TraceabilityView.tsx (802 Zeilen) sind nächste Zerlegungs-Kandidaten nach REQ-050. Baum-Algorithmen/Such-Logik entangled mit UI-Rendering. Extract: Utility-Module mit Pure-Funktionen (Baum-Traverse, Filter-Logik, Path-Suche), useTreeState Hook für State-Management, TreePresenter Komponente. Status: Backlog (P3).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-122)

---

### REQ-L0-182 — SN-182: TypeScript-Typing: any statt unknown (P3 Non-Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-123.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] CanvasEditor.tsx:110-113 (type AnyObj = Record<string, any>), AdrForm.tsx:35 (handleChange value: any) und weitere Stellen nutzen `any` statt `unknown` + Type-Guards. any schwächt TypeScript-Sicherheit, `unknown` erzwingt Type-Checks. Ersetze `any` durch `unknown` + Discriminator-Patterns oder konkrete Typen. Status: Backlog (P3).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-123)

---

### REQ-L0-183 — SN-183: Accessibility: Error-State A11y (P3 Accessibility)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-124.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] frontend/src/components/.../ArtifactDiff.tsx:441-450 — Error-State-Div fehlt role="alert" und aria-live="assertive". Liveregion-Markup ergänzen um sicherzustellen dass Screen-Reader Fehler aussprechen. Weitere Stellen mit Error/Toast-Komponenten auditieren. Status: Backlog (P3).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-124)

---

### REQ-L0-184 — SN-184: Unused/Overlapping Component (P3 Functional)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-125.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] AiPromptsSection.tsx überlappt konzeptuell mit PromptTemplateSection.tsx (ähnliche Funktionalität, unterschiedliche Naming). Entscheidung erforderlich: Komponente löschen oder zusammenführen + Naming vereinheitlichen (UX-Entscheidung mit Team). Status: Backlog (Entscheidung nötig vor Cleanup).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-125)

---

### REQ-L0-185 — SN-185: MCP API-Key Rollen-Propagation

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-127.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] MCP API-Key-Authentifizierung muss Workspace-Rollen des Users laden und in den MCP-Dispatch-Kontext propagieren. Ohne workspace_id in Tool-Call-Parametern bleibt active_roles leer und blockiert alle Schreib-Operationen für API-Key-authentifizierte User. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-127)

---

### REQ-L0-186 — SN-186: URL-Routing StakeholderNeedViewSet — derive-requirements

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-128.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] GET /api/v1/needs/derive-requirements/ darf nicht 500 zurückgeben. Der DRF-Router interpretiert "derive-requirements" als UUID-pk. Fix: lookup_value_regex in StakeholderNeedViewSet auf UUID-Muster einschränken, damit Custom Actions nicht als pk aufgelöst werden. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-128)

---

### REQ-L0-187 — SN-187: MCP tools/list — doppelte Einträge entfernen

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-129.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] MCP tools/list-Response muss eindeutige Tool-Einträge zurückgeben. Aktuell erscheinen 7 Tools doppelt, verursacht durch shared object references und mehrere CrossCuttingToolGroup-Instanzen. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-129)

---

### REQ-L0-188 — SN-188: MCP Typed inputSchemas für alle Tool-Gruppen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-130.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Alle MCP-Tool-Gruppen müssen typisierte inputSchema-Parameter exponieren statt generischem {"kwargs": {"type": "object"}}. Aktuell haben nur requirement.*, prompt_template.get und ai_derivation.* typisierte Schemas — betrifft 15+ Tool-Gruppen. Priorität: Backlog (außerhalb des aktuellen Sprints — zu groß).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-130)

---

### REQ-L0-189 — SN-189: MCP Capability Declaration — nur implementierte Transports

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-131.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] MCP Capability-Declaration darf nur implementierte Transports ausweisen. "sse" aus der Transports-Liste entfernen, da SSE-Transport nicht implementiert ist. Die aktuelle Deklaration führt MCP-Clients in die Irre. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-131)

---

### REQ-L0-190 — SN-190: Ollama base_url Validierungsfehler

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-132.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Wenn LLM-Provider "ollama" ist und base_url leer ist, muss das Backend einen klaren Validierungsfehler zurückgeben statt still auf localhost:11434 zurückzufallen. Zusätzlich OLLAMA_BASE_URL in der Dokumentation ergänzen. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-132)

---

### REQ-L0-191 — SN-191: Workspace language-Feld in Datenbank persistieren

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-133.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Workspace-Spracheinstellung muss in der Datenbank gespeichert werden. Das Workspace-Model hat keine language-Spalte; der Serializer gibt immer den Default "en" zurück. language-Feld zum Workspace-Model hinzufügen inkl. Migration. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-133)

---

### REQ-L0-192 — SN-192: API-Key Retrieve-Endpoint

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-134.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] GET /api/v1/api-keys/{id}/ muss 200 mit den Key-Details zurückgeben. Aktuell sind nur list (GET /api-keys/) und create (POST) implementiert. retrieve-Action zu ApiKeyViewSet hinzufügen. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-134)

---

### REQ-L0-193 — SN-193: change_reason Validierungsfehler mit Kontext

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-135.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] change_reason-Validierungsfehler muss Workspace-Name und Preset in der Fehlermeldung enthalten. Aktuelle Meldung "change_reason required" gibt keinen Kontext darüber, welcher Workspace die Angabe erfordert oder warum. Priorität: Could.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-135)

---

### REQ-L0-194 — SN-194: Attribut-Visibility-Config leere Antwort fehlerfrei behandeln

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-136.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das Frontend muss eine leere []-Antwort von /api/v1/attribute-visibility-configs/ ohne console.error verarbeiten. Die aktuelle Implementierung ruft console.error bei leerem Array auf; AdminDialog zeigt bei jedem API-Fehler eine nutzerseitige Fehlermeldung. Priorität: Could.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-136)

---

### REQ-L0-195 — SN-195: Preferences GET-Endpoint muss 200 mit leeren Defaults zurückgeben

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-137.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] GET /api/v1/users/me/preferences/?workspace_id=<uuid> MUSS HTTP 200 mit einer neu angelegten (leeren) Preference-Row zurückgeben, wenn für das gegebene User/Workspace-Paar noch kein Eintrag existiert — statt HTTP 404. Entspricht der get_or_create-Semantik des PATCH-Endpoints und verhindert console.error-Fluten im Frontend (WorkspaceContext). Fix: GET-Handler in UserPreferenceView auf PreferenceService.get_or_create_preference() umstellen statt get_preference(). Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-137)

---

### REQ-L0-196 — SN-196: CSRF Trusted Origins für Browser-SPA konfiguriert

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-138.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das Backend MUSS in CSRF_TRUSTED_ORIGINS alle erlaubten SPA-Origins (mindestens http://localhost:5173 für den Vite-Dev-Server und die produktive Frontend-URL) eintragen, sodass state-ändernde REST-Anfragen (POST, PATCH, PUT, DELETE) der Browser-SPA nicht mit HTTP 403 abgelehnt werden. Hintergrund: Der Cookie-basierte Session-Auth-Pfad erzwingt die Django-CSRF-Origin-Prüfung; fehlt der Origin in CSRF_TRUSTED_ORIGINS, scheitern alle Schreibzugriffe der SPA. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-138)

---

### REQ-L0-197 — SN-197: Automatisierter CSRF-Regressionstest (Cross-Origin Enforcement)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-139.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Es MUSS ein automatisierter Test existieren, der das Cross-Origin-CSRF-Enforcement des Django-Backends prüft. Der Test verwendet `django.test.Client` mit `enforce_csrf_checks=True` und sendet POST/PATCH/DELETE-Anfragen sowohl mit korrektem als auch mit fehlendem/falschem Origin-Header gegen mindestens einen schreibenden REST-Endpoint. Ein korrekter Origin MUSS HTTP 2xx zurückgeben; ein fehlender oder nicht-erlaubter Origin MUSS HTTP 403 zurückgeben. Ziel: Regressionen wie REQ-138 (fehlende CSRF_TRUSTED_ORIGINS) werden automatisch erkannt. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-139)

---

### REQ-L0-198 — SN-198: npm install ohne --legacy-peer-deps: fabric.js/jsdom-Kompatibilität

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-140.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] `npm install` im Frontend-Verzeichnis MUSS ohne `--legacy-peer-deps`-Flag erfolgreich durchlaufen. Die fabric.js-Abhängigkeit MUSS mit dem jsdom@^25-devDependency (oder einer kompatiblen jsdom-Version) peer-kompatibel sein. Existiert keine kompatibel veröffentlichte Version von fabric.js, MUSS die Inkompatibilität in der Codebase dokumentiert und mit technischer Begründung gerechtfertigt sein. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-140)

---

### REQ-L0-199 — SN-199: TracePanel im ArtifactInspector an echte TraceLink-API anbinden

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-141.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das TracePanel im ArtifactInspector MUSS echte Trace-Links über `/api/v1/tracelinks/` laden statt des `mockFetchTraceLinks`-Stubs (liefert immer `[]`). Loading-, Error- und Empty-State MÜSSEN unterschieden werden; „keine Links" darf erst nach erfolgreichem Fetch angezeigt werden. `resolveArtifactRef` MUSS verdrahtet sein, sodass Link-Endpunkte mit Titel/UID angezeigt werden. Priorität: Must. (AP-07)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-141)

---

### REQ-L0-200 — SN-200: Versions- und Diff-Endpoints für Diagramm & Glossar

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-142.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Für Diagramme und Glossar-Einträge MÜSSEN `GET …/{pk}/versions/` und `GET …/{pk}/diff/?from_version=&to_version=` analog zu den Requirement-Endpoints existieren (Versionstabellen `DiagramVersion`/`GlossaryTermVersion` sind vorhanden). Die Frontend-Stubs in `api/glossary.ts`/`api/diagrams.ts` („Not Implemented") sowie die Mock-Fallbacks in VersionPanel/DiffPanel MÜSSEN durch echte Aufrufe ersetzt werden. Priorität: Should. (AP-08)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-142)

---

### REQ-L0-201 — SN-201: Status-Modell konsolidieren: Workflow-Engine als Quelle der Wahrheit

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-143.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Es DARF nur einen Schreibpfad für Statuswechsel geben: die Workflow-Engine (`workflow`-App). Das freie `status`-CharField auf Requirement/Need wird zum denormalisierten, read-only Spiegel, gesetzt ausschließlich durch Workflow-Transitions. Direkte Status-Writes via REST/MCP MÜSSEN abgelehnt oder ignoriert werden. Datenmigration mappt Bestandswerte auf gültige Workflow-States; Mapping wird als ADR dokumentiert. Priorität: Must. (AP-09)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-143)

---

### REQ-L0-202 — SN-202: Review-/Approval-UI auf Basis der Workflow-Engine

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-144.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Es MUSS eine Review-Ansicht (`/reviews`) geben: Liste aller Items im Zustand `in_review`, Detailansicht mit Diff zur letzten approved-Version, Aktionen Approve/Reject. Approve MUSS das vorhandene Signature-Gate nutzen (Credential-Dialog Passwort/TOTP, HMAC-Seal, approver-Rolle). Workflow-Historie inkl. Seal-Status MUSS am Item sichtbar sein. Ein Playwright-E2E-Szenario deckt draft→in_review→approved ab. Priorität: Must. (AP-10)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-144)

---

### REQ-L0-203 — SN-203: PDF-Export-Stubs fertigstellen (VCRM-PDF, Export-PDF)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-145.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Der VCRM-Report-Generator und der Export-Service DÜRFEN für PDF kein `NotImplemented` mehr werfen. VCRM-PDF (Matrix-Tabelle) und Export-PDF werden mit reportlab vervollständigt (Vorbild: `traceability/pdf_report_generator.py`). Tests prüfen, dass ein nicht-leeres PDF mit Stichproben-Inhalten erzeugt wird. Priorität: Should. (AP-11)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-145)

---

### REQ-L0-204 — SN-204: ReqIF-Export

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-146.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Requirements, Stakeholder Needs und TraceLinks eines Workspace MÜSSEN als ReqIF 1.2 exportierbar sein (`GET /api/v1/workspaces/{pk}/export/reqif/`): Artefakte als SPEC-OBJECT mit typespezifischen Attributen, Hierarchie als SPECIFICATION/SPEC-HIERARCHY, TraceLinks als SPEC-RELATION, stabile IDENTIFIER aus Artifact-UUID (Re-Export ändert IDs nicht). Die exportierte Datei MUSS gegen das ReqIF-Schema validieren und von einem Referenz-Parser lesbar sein. Priorität: Must. (AP-12)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-146)

---

### REQ-L0-205 — SN-205: ReqIF-Import

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-147.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] ReqIF-Dateien MÜSSEN importierbar sein (`POST /api/v1/workspaces/{pk}/import/reqif/`): atomar, Upsert per IDENTIFIER-Matching gegen vorhandene UIDs (Re-Import aktualisiert statt dupliziert), unbekannte Attribute → custom_fields, Dry-Run-Modus (`?dry_run=true`) liefert Bericht ohne Persistenz. Roundtrip Export→Import MUSS idempotent sein. Priorität: Must. (AP-13)

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-147)

---

### REQ-L0-206 — SN-206: Issue-Status Normalisierung (Case-Insensitive)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-148.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] IssueSerializer MUSS case-insensitive Status-Eingaben akzeptieren und normalisieren (z.B. 'open', 'IN PROGRESS', 'wONtFiX' → Title-Case). Implementierung via NormalizedChoiceField mit .title()-Transformation. Tests decken lowercase, uppercase und mixed-case Inputs ab. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-148)

---

### REQ-L0-207 — SN-207: Workspace-Kontext: neutraler Placeholder während Load

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-149.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] WorkspaceContext.DEFAULT_WORKSPACE.name MUSS während der initialen Workspace-Loading-Phase auf leeren String gesetzt sein statt auf 'Default Workspace', um Verwirrung zu vermeiden. Nutzer sehen keinen irreführenden Text wenn der echte Workspace 'Demo Workspace' oder anderes heißt. Loading-State ist already vorhanden; UI-Konsumenten prüfen isLoadingWorkspace vor Rendering. Priorität: Could.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-149)

---

### REQ-L0-208 — SN-208: ADR-Supersedes-Link bei Statusübergang

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-150.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Wenn ein ADR in den Status 'Superseded' übergeht, MUSS AdrService.transition_status() einen optionalen Parameter `superseded_by_id` (UUID des Nachfolger-ADRs) akzeptieren und bei Angabe einen TraceLink vom neuen (Nachfolger-)ADR zum alten (abgelösten) ADR anlegen, damit der TraceLink-Graph die Ablösung dokumentiert. 'supersedes' ist kein Mitglied von VALID_LINK_TYPES; 'decides' (bereits für ADR-Entscheidungs-Links verwendet, REQ-L2-TE-020) ist die semantisch nächstliegende Alternative. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-150)

---

### REQ-L0-209 — SN-209: Extended-Preset: implemented/verified-States (V-Modell rechte Seite)

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-151.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das Extended-Workflow-Preset (workflow/definition_store.py PRESET_SCHEMAS) endet aktuell bei approved/deprecated und kann die rechte Seite des V-Modells (Implementierung, Verifikation) nicht abbilden. Ergänzung um States `implemented` (nach `approved`) und `verified` (nach `implemented`) mit Transitions approved→implemented und implemented→verified. Rollenmapping nutzt die vorhandenen RBAC-Rollen (admin/editor/viewer/approver aus auth_tenancy/models.py) — "editor" für die Implementierungs-Transition, "approver" für die Verifikations-Transition, da "developer"/"reviewer"/"verifier" keine im System definierten Rollen sind. Bestandsanforderungen in approved/deprecated bleiben gültig (Backward-Compatibility). Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-151)

---

### REQ-L0-210 — SN-210: Hierarchie-Konsolidierung: Artifact.parent zugunsten von TraceLinks deprecaten

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-152.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Artifact.parent (Self-FK, persistence/models.py) und 'derives-from'-TraceLinks bilden zwei parallele Hierarchie-Mechanismen. Domain-Services (RequirementService, StakeholderNeedService, AdrService, ...) befüllen Artifact.parent nicht und nutzen ausschließlich TraceLinks; die generische ArtifactService (COMP-AS-001) sowie einzelne Baseline-/ReqIF-/Workspace-Duplizierungs-Codepfade lesen/schreiben das Feld weiterhin. Das Feld wird mit Deprecation-Kommentar versehen (single source of truth: 'derives-from'-TraceLink), ohne Migration/Verhaltensänderung; betroffene Lesestellen erhalten TODO-Kommentare zur schrittweisen Migration. Priorität: Could.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-152)

---

### REQ-L0-211 — SN-211: Requirement-Hierarchie-Level (L0-L4) als explizites Feld

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-153.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Requirement besitzt kein `level`-Feld — die V-Modell-Hierarchie (L0 System, L1 Subsystem, L2 Component, L3 Part, L4 Material) existiert bisher nur als Namenskonvention. Ein nullable `level`-Feld (PositiveSmallIntegerField, choices 0-4) MUSS die Ebene explizit und abfragbar machen. Additiv/backward-compatible: Bestandszeilen bleiben `NULL` (kein Backfill; die Ebene wird bewusst zugewiesen). Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-153)

---

### REQ-L0-212 — SN-212: TestCase-Testtyp als First-Class-Feld + Verification-Method Demonstration

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-154.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] TestCase kodiert den Testtyp bisher als String-Präfix im `artifact_type` (z.B. "TestCase:System"). Ein nullable `test_type`-Feld (CharField, choices system/integration/unit/inspection/analysis/demonstration) MUSS den Typ als eigenständiges Feld führen; eine Datenmigration backfilled aus dem Legacy-Präfix. Zusätzlich wird `Demonstration` zu VerificationMethod ergänzt (V-Modell-Vollständigkeit). Additiv/backward-compatible. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-154)

---

### REQ-L0-213 — SN-213: Functional/Physical Architecture Separation

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-155.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] The artifact model must distinguish between functional architecture elements (functions, logical blocks, behavioral decomposition) and physical architecture elements (components, hardware items, physical topology). Currently both are stored as generic Artifact records without semantic differentiation. Future implementation should: (a) add an `architecture_domain` field (functional/physical) to Architecture-type Artifacts, (b) add a dedicated `allocates` TraceLink type from functional to physical elements, (c) update MBSE views to render functional and physical hierarchies separately. Priority: Follow-up / Post-v1.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-155)

---

### REQ-L0-214 — SN-214: TestRun Baseline Support

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-156.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] TestRun/TestRunResult entities must be includeable in Baseline snapshots to enable reproducible verification evidence at each project milestone. The `ScopeResolver` MUST include `pl_test_run` and `pl_test_run_result` rows (by `workspace_id`/`tenant_id`) when building project- and global-scoped baselines. Each entity is stored as a `BaselineDeltaIndexEntry` with `entity_type="test_run"` or `entity_type="test_run_result"`. Full state (name, status, timestamps, ci_job_id, results) is captured via `state_capture.py`. No schema migration required — `BaselineDeltaIndexEntry.entity_type` is a free-form `CharField`. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-156)

---

### REQ-L0-215 — SN-215: Change Request Management — CCB Approval Workflow

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-157.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Users must be able to create, submit, review, approve/reject, and implement Change Requests (CR) through a formal CCB (Configuration Control Board) approval workflow powered by the existing WorkflowEngine. The CR lifecycle MUSS follow the states: draft → submitted → under_review → approved

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-157)

---

### REQ-L0-216 — SN-216: Bug: Build-Version zeigt "unknown"

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-158.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] `version.py` behandelt den Default-String (z.B. `"unknown"`) als validen Git-SHA, wodurch der Git-Fallback-Pfad nie erreicht wird und die Build-Version in der UI dauerhaft als "unknown" angezeigt wird. `version.py` MUSS den Default-String von einem echten Git-SHA unterscheiden: Ist kein valider SHA verfügbar (Wert leer, gleich `"unknown"` oder ein bekannter Placeholder), MUSS der Git-Fallback-Pfad ausgeführt werden. Akzeptanzkriterium: Ein Prod-Build zeigt in der UI eine echte Commit-SHA oder einen definierten Fallback-String (z.B. `"dev"`) statt `"unknown"`. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-158)

---

### REQ-L0-217 — SN-217: Bug: AuthContext-Attributfehler in StakeholderNeedService

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-159.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] `stakeholder_need_service.py` Zeile 207 greift via `ctx.user` auf ein nicht vorhandenes Attribut des `AuthContext` zu — `AuthContext` exponiert `user_id`, nicht `user`. Der Aufruf wirft `AttributeError` und blockiert alle StakeholderNeed-Operationen, die diesen Pfad durchlaufen. Die betroffene Stelle MUSS `ctx.user_id` statt `ctx.user` verwenden. Akzeptanzkriterium: StakeholderNeed-Operationen (Create, Update, Derive) schlagen nicht mehr mit `AttributeError: 'AuthContext' object has no attribute 'user'` fehl. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-159)

---

### REQ-L0-218 — SN-218: Bug: Artefakt-Formulare umgehen WorkflowFacade — leere Transitions-Liste

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-160.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Alle Artefakt-Formulare außer `RequirementForm` (d.h. `AdrForm`, `TestCaseForm`, `NeedForm`, `RiskForm`, `IssueForm`, `ChangeRequestForm`) führen Status-Writes direkt per REST durch und umgehen die `WorkflowFacade`. Bei fehlendem `WorkflowItemState`-Eintrag liefert die Transitions-API eine leere Liste, Status-Änderungen über die UI sind vollständig blockiert. Alle betroffenen Formulare MÜSSEN Status-Transitions ausschließlich über `WorkflowFacade.transition_status()` auslösen. Ein fehlender `WorkflowItemState`-Eintrag MUSS serverseitig automatisch auf den definierten Initial-State initialisiert werden statt eine leere Transitions-Liste zurückzugeben. Akzeptanzkriterium: Status-Transitionen für alle sieben Artefakt-Typen sind in der UI ausführbar; ein Artefakt ohne `WorkflowItemState`-Eintrag erhält automatisch den Initial-State und zeigt erlaubte Transitionen. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-160)

---

### REQ-L0-219 — SN-219: Redesign: Unified Workflow Status Editor (wiederverwendbare Komponente)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-161.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Eine wiederverwendbare React-Komponente `WorkflowStatusEditor` MUSS für alle Artefakt-Typen (Requirements, ADR, TestCase, StakeholderNeed, Risk, Issue, ChangeRequest) bereitgestellt werden. Die Komponente zeigt den aktuellen Workflow-Status und die erlaubten Transitionen über die `WorkflowFacade`-API an, löst Transition-Aktionen aus und behandelt Fehlerzustände (leere Transitions-Liste, fehlender State, Netzwerkfehler) einheitlich mit sichtbarem Feedback. Hardcoded Status-Select-Dropdowns in Artefakt-Formularen werden durch `WorkflowStatusEditor` ersetzt. Akzeptanzkriterium: Kein Artefakt-Formular enthält ein eigenständiges Status-Dropdown mehr; alle Status-Änderungen laufen über dieselbe Komponente und die `WorkflowFacade`-API. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-161)

---

### REQ-L0-220 — SN-220: Bug: NeedForm fehlt change_reason-Feld für Extended-Preset

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-162.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] `NeedForm.tsx` besitzt keinen `change_reason`-State, kein Eingabefeld und keinen API-Payload-Eintrag für das Feld `change_reason`. Der Backend-Service `stakeholder_need_service.py` (Zeilen 177–180, 239–242) erzwingt `change_reason` als Pflichtfeld bei Update- und Delete-Operationen, wenn der Workspace das Extended-Rigor-Preset nutzt — die fehlende Feldübergabe führt zu HTTP-400-Fehlern ("change_reason is required by preset policy"). `NeedForm.tsx` MUSS ein `change_reason`-Textarea-Feld erhalten, das ausschließlich bei aktivem Extended-Preset sichtbar ist, bei Update- und Delete-Requests im API-Payload mitgesendet wird und analog zur bestehenden Implementierung in `RequirementForm.tsx` (Zeilen 86, 110–111, 435–451) und `ArchitectureForm.tsx` aufgebaut ist. Akzeptanzkriterium: Im Extended-Preset sind Update- und Delete-Operationen auf StakeholderNeeds ohne HTTP-400-Fehler ausführbar; im Minimal- und Standard-Preset wird das Feld nicht angezeigt. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-162)

---

### REQ-L0-221 — SN-221: LLM-Fähigkeiten standardmäßig nicht aktiviert

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-163.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Das Backend liest `LLM_CAPABILITIES` aus einer Umgebungsvariable (`backend/llm_adapter/router.py:110`). Fehlt die Variable oder ist sie leer, sind alle vier LLM-Fähigkeiten (`validate_artifact`, `decompose_requirement`, `check_consistency`, `derive_requirements`) deaktiviert — ohne Fehlermeldung. Die `.env`- und `.env.example`-Dateien enthalten diese Variable nicht. `LLM_CAPABILITIES=validate_artifact,decompose_requirement,check_consistency,derive_requirements` MUSS in `.env` und `.env.example` ergänzt und dokumentiert werden. Akzeptanzkriterium: Ein frisch ausgechecktes Projekt mit `docker-compose up` aktiviert alle vier LLM-Fähigkeiten, da die Variable in `.env.example` vorbelegt ist. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-163)

---

### REQ-L0-222 — SN-222: Fehlende requests-Dependency im Backend

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-164.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Python-Bibliothek `requests` wird im Backend (LLM-Adapter-Provider) verwendet, ist aber nicht in `backend/requirements.txt` deklariert — führt zu `ImportError` zur Laufzeit, wenn das Paket nicht zufällig transitiv installiert ist. `requests>=2.31.0` MUSS explizit in `backend/requirements.txt` ergänzt werden. Akzeptanzkriterium: `pip install -r backend/requirements.txt` in einer sauberen virtualenv-Umgebung endet ohne ImportError; LLM-Adapter-Provider sind instanziierbar. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-164)

---

### REQ-L0-223 — SN-223: Universelle Workflow-Engine für alle primären Entitätstypen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-165.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die `WorkflowEngine` (eingeführt mit REQ-160/161) deckt aktuell nur `Requirement` vollständig und `StakeholderNeed` teilweise ab. Alle primären Entitätstypen — `Requirement`, `StakeholderNeed`, `Adr` (Architecture Decision Record), `TestCase`, `Risk`, `Issue` — MÜSSEN einen einheitlichen Workflow-Status besitzen, der ausschließlich durch die `WorkflowEngine` verwaltet wird. Der `WorkflowStatusEditor` MUSS in allen zugehörigen Frontend-Formularen sichtbar und funktionsfähig sein. Kein Entitätstyp darf Status-Writes mehr direkt via REST durchführen. Akzeptanzkriterium: Status-Transitionen sind für alle sechs Entitätstypen über die `WorkflowFacade`-API auslösbar; kein Formular enthält ein eigenständiges Status-Dropdown. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-165)

---

### REQ-L0-224 — SN-224: Entitätstyp-spezifisch konfigurierbare Workflow-Presets

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-166.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Jeder Entitätstyp MUSS eine eigene, unabhängig konfigurierbare Workflow-Zustandsmaschine besitzen — kein einziges globales Preset für alle Typen. Standard-Presets MÜSSEN dem RM/SE-Standard-Lifecycle folgen: Draft → In Review → Approved → Released/Deprecated/Rejected. Die Preset-Konfiguration MUSS in der Datenbank (z.B. `WorkflowEngineDefinition`) gespeichert werden, nicht hartkodiert. Ein Konfigurationsinterface (UI oder Admin-Einstellungen) MUSS pro Entitätstyp vorhanden sein, über das Zustände und erlaubte Übergänge angepasst werden können. Akzeptanzkriterium: Für zwei Entitätstypen können unterschiedliche Zustandsmaschinen aktiv sein; Änderungen über das Konfigurationsinterface wirken ohne Deployment. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-166)

---

### REQ-L0-225 — SN-225: Workflow-Approval/Release-Dialog-Integration für alle Entitätstypen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-167.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Workflow-Zustandsübergänge, die Genehmigungs- oder Freigabeschritte darstellen (z.B. → Approved, → Released), MÜSSEN mit den bestehenden `SignatureDialog`- und `ReviewsView`-Komponenten integriert werden. Die aktuelle Verdrahtung des Signature-Gate-Mechanismus gilt ausschließlich für `Requirement`; alle weiteren Entitätstypen (`StakeholderNeed`, `Adr`, `TestCase`, `Risk`, `Issue`) MÜSSEN denselben Mechanismus nutzen. Akzeptanzkriterium: Ein Approve-Übergang für einen ADR oder ein TestCase öffnet denselben Signature-Dialog wie bei Anforderungen; die Signature-Gate-Prüfung ist für alle Entitätstypen einheitlich. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-167)

---

### REQ-L0-226 — SN-226: Bug: change_reason-Enforcement-Inkonsistenz in Workflow-Transitionen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-169.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Der `WorkflowFacade` erzwingt `change_reason` bei Extended-Preset auf Workspace-Ebene für ALLE Transitionen; der `GET /transitions/`-Endpoint gibt jedoch pro-Transitions-Flags `requires_change_reason` (oft `false`) zurück, anhand derer das Frontend das Eingabefeld einblendet. Betroffen: `NeedForm` (draft→in_review), `RiskForm` (Accepted→Closed), `TestCaseForm` (Draft→Ready). Der `GET /transitions/`-Endpoint MUSS das effektive `requires_change_reason` zurückgeben, das Workspace-Preset und per-Transitions-Flag kombiniert. Akzeptanzkriterium: Im Extended-Preset wird das `change_reason`-Eingabefeld immer angezeigt, wenn das Backend es als Pflichtfeld behandelt; im Minimal/Standard-Preset nur wenn die Transition es explizit erfordert. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-169)

---

### REQ-L0-227 — SN-227: Bug: Requirement-Workflow für Bestandsworkspaces nicht initialisiert

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-170.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Migration `0004_backfill_entity_workflow_definitions` übersprang den Entitätstyp `"Requirement"` unter der falschen Annahme, dass `workspace_service` diesen bei Workspace-Erstellung anlegt. Workspaces, die vor dem entsprechenden Fix erstellt wurden, besitzen keinen `WorkflowEngineDefinition`-Eintrag für `"Requirement"`. Der Lazy-Init-Pfad in `lifecycle_manager.py` greift nur, wenn eine Definition bereits vorhanden ist, und kann den fehlenden Eintrag nicht nachholen. Es MUSS eine neue Django-Migration erstellt werden, die fehlende `Requirement`-Definitionen für alle betroffenen Workspaces nachträglich anlegt (Backfill). Akzeptanzkriterium: Alle Workspaces (einschließlich vor dem Fix erstellter) besitzen nach Ausführung der Migration einen `WorkflowEngineDefinition`-Eintrag für `"Requirement"`. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-170)

---

### REQ-L0-228 — SN-228: Bug: ArchitectureForm ohne WorkflowStatusEditor-Integration

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-171.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] `ArchitectureForm.tsx` enthält keine `WorkflowStatusEditor`-Komponente, obwohl alle anderen Entitätsformulare (`AdrForm`, `IssueForm`, `RiskForm`, `NeedForm`, `TestCaseForm`, `RequirementForm`) diese Integration erhalten haben. Zusätzlich fehlt der Wert `"architecture"` in `WorkflowArtifactType` (`frontend/src/api/workflow-transitions.ts`). `ArchitectureForm.tsx` MUSS `WorkflowStatusEditor` integrieren; `WorkflowArtifactType` MUSS `"architecture"` als gültigen Typ enthalten. Akzeptanzkriterium: Architektur-Elemente zeigen Workflow-Status und erlaubte Transitionen in der UI; kein hardkodiertes Status-Dropdown in `ArchitectureForm`. Priorität: Must.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-171)

---

### REQ-L0-229 — SN-229: Konfigurierbare per-Transition-change_reason-Anforderung

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-172.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die `change_reason`-Pflichtfeld-Logik MUSS pro Transition und pro Entitätstyp konfigurierbar sein — nicht global auf Workspace-Preset-Ebene erzwungen. Das State-Machine-Schema (`WorkflowEngineDefinition` / `definition_store`) MUSS je Transition eine Eigenschaft `requires_change_reason` unterstützen, die festlegt ob `change_reason` für diese spezifische Transition erforderlich ist. Das Workspace-Preset `extended` SOLL nur den Standardwert setzen; individuelle Transitionen können diesen Standard überschreiben. Die globale `_check_change_reason()`-Logik wird durch die per-Transition-Konfiguration ersetzt. Ergänzend: globale Standard-Workflow-Definitionen pro Entitätstyp, Workspace-Level-Override dieser Defaults und eine Reset-to-Default-Funktion (UI: Formular mit Standardwerten, Override und Reset-Button). Akzeptanzkriterium: Zwei Transitionen desselben Entitätstyps können unterschiedliche `requires_change_reason`-Werte haben; Workspace-Preset-Override und Zurücksetzen auf Default sind möglich. Priorität: Should. Abhängigkeit: REQ-166.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-172)

---

### REQ-L0-230 — SN-230: Workflow-Engine-Erweiterung auf nicht unterstützte Entitätstypen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-173.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Workflow-Engine (`WorkflowTransitionsMixin`, `WorkflowStatusEditor`, `WorkflowArtifactType`) MUSS auf die aktuell nicht unterstützten Entitätstypen `TestRun`, `Baseline`, `ICD`, `Diagram` und `Glossary` erweitert werden. Jeder Entitätstyp MUSS erhalten: einen Backend-ViewSet-Mixin (`WorkflowTransitionsMixin`), eine Workflow-Definition im `definition_store` und eine Frontend-`WorkflowStatusEditor`-Integration im jeweiligen Formular-Component. Akzeptanzkriterium: Alle fünf neuen Entitätstypen zeigen Workflow-Status und erlaubte Transitionen in der UI; Transitionen sind über die `WorkflowFacade`-API auslösbar und in der Datenbank protokolliert. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-173)

---

### REQ-L0-231 — SN-231: Workflow-Settings-UI-Redesign (Umsetzung REQ-166)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-174.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die bestehende `WorkflowsSection` in den Workspace-Einstellungen ist ein primitives Admin-Tool (rohe UUIDs, Freitexteingabe für State-Namen) und erfüllt REQ-166 nicht. Eine vollwertige Workflow-Settings-UI MUSS bereitstellen: (1) Übersicht der aktuellen Workflow-Konfiguration pro Entitätstyp, (2) Bearbeitung globaler Standardwerte, (3) Anwendung von Workspace-Level-Overrides, (4) Zurücksetzen von Overrides auf globale Defaults (Reset-Button). Rohe UUIDs und Freitexteingaben für State-Namen werden durch strukturierte Formular-Elemente ersetzt. Akzeptanzkriterium: Ein Workspace-Administrator kann für jeden Entitätstyp den aktiven Workflow-Preset einsehen und überschreiben; geänderte Konfigurationen wirken ohne Deployment. Priorität: Should. Abhängigkeit: REQ-172.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-174)

---

### REQ-L0-232 — SN-232: Visueller Workflow-Editor (Phase 1, read-only)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-176.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein grafischer State-Machine-Editor (`WorkflowEditorPage`, Route `/workflows/:entityType`) MUSS die vollständige Workflow-Definition je Entitätstyp read-only visualisieren: alle States (typ-klassifiziert: initial/active/terminal/error) und Transitionen (mit Rollen-, change_reason- und Signatur-Metadaten) als interaktiver Graph (React Flow) mit Auto-Layout, Inspector-Panel und Mermaid-Export. Datenquelle: `GET /api/v1/workflows/definition/?workspace_id&item_type`. Akzeptanzkriterium: Für jeden der 7 Entitätstypen wird die komplette State-Machine korrekt gerendert; States/Transitionen sind selektier- und inspizierbar. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-176)

---

### REQ-L0-233 — SN-233: Visueller Workflow-Editor (Phase 2, Edit Mode)

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-177.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Der Workflow-Editor (REQ-176) MUSS einen admin-gegateten Edit-Modus erhalten, der die Workflow-Definition mutiert: States hinzufügen/umbenennen/löschen und Transitionen hinzufügen/bearbeiten/löschen (Backend-Mutations-Endpunkte unter `/api/v1/workflows/definition/states

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-177)

---

### REQ-L0-234 — SN-234: Globales, PRO-PRESET Workflow-Definitions-Modell als Source-of-Truth

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-178.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Workflow-Definitionen (`WorkflowDefinition`, `backend/workflow/models.py`) existieren aktuell ausschließlich pro Workspace (`workspace_id`-Feld, keine tenant-weite Default-Ebene) — Provisionierung (`provision_workflow_definitions`-Command, Presets minimal/standard/full) seedet direkt in jeden Workspace, ohne gemeinsame Quelle. Es MUSS je Rigor-Preset (Minimal/Standard/Extended) eine EIGENE tenant-weite globale Workflow-Definition je Entitätstyp als Source-of-Truth existieren — KEIN einzelner, presetübergreifend geteilter globaler Default. Ein neu angelegter Workspace MUSS beim Erstellen automatisch die aktuell gültige globale Workflow-Definition SEINES Presets je Entitätstyp erben (Persistenzform — Kopie oder Referenz — ist Aufgabe des Datenmodell-Designs, nicht dieser Anforderung). Der on-default/customized-Zustand eines Workspace (REQ-180) MUSS gegen den globalen Default DES EIGENEN Presets des Workspace berechnet werden, nicht gegen einen presetübergreifenden Durchschnitts- oder Mehrheitswert — dies vereinheitlicht zugleich das Backfill- und Change-Handling über alle drei Presets hinweg. Akzeptanzkriterium: Für einen frisch erstellten Workspace ist ohne manuelle Konfiguration für jeden Entitätstyp eine funktionsfähige, aus dem globalen Default SEINES Presets abgeleitete Workflow-Definition vorhanden; zwei Workspaces mit unterschiedlichem Preset erben nachweislich unterschiedliche globale Defaults, auch wenn beide "on-default" sind. Priorität: Must. Abhängigkeit: REQ-166, REQ-172.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-178)

---

### REQ-L0-235 — SN-235: Workspace-Workflow-Override bleibt vollständig editierbar

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-179.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein Workspace MUSS seine geerbte Workflow-Definition weiterhin vollständig anpassen können (States/Transitionen hinzufügen, ändern, entfernen) — die bestehende Editier-Fähigkeit des Workflow-Editors (REQ-177, `WorkflowEditorPage.tsx`, Mutations-Endpunkte unter `/api/v1/workflows/definition/...`) DARF durch die Einführung globaler Defaults (REQ-178) nicht eingeschränkt, verändert oder entfernt werden (Regressionsschutz). Eine workspace-eigene Anpassung wird als Override der globalen Definition geführt und bleibt unabhängig vom globalen Default persistiert, bis ein Reset (REQ-180) erfolgt. Akzeptanzkriterium: Alle bisher via REQ-177 unterstützten Bearbeitungsoperationen (State/Transition hinzufügen/umbenennen/löschen, Validierungsregeln) funktionieren nach Einführung des globalen Default-Modells unverändert für einen Workspace mit Override. Priorität: Must. Abhängigkeit: REQ-176, REQ-177, REQ-178.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-179)

---

### REQ-L0-236 — SN-236: Workflow Reset-to-Default

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-180.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein Workspace, dessen Workflow-Definition vom globalen Default abweicht (Override, REQ-179), MUSS jederzeit auf den aktuell gültigen globalen Default zurückgesetzt werden können. Das System MUSS erkennbar unterscheiden, ob eine Workspace-Workflow-Definition aktuell dem globalen Default entspricht ("on-default") oder davon abweicht ("customized") — sichtbar für Nutzer und Administratoren. Der Reset verwirft workspace-spezifische Anpassungen vollständig und übernimmt den globalen Default. Akzeptanzkriterium: Für einen Workspace im "customized"-Zustand ist eine Reset-Aktion verfügbar, die nach Ausführung den "on-default"-Zustand herstellt; der Zustand ("on-default"/"customized") ist vor und nach dem Reset für den Nutzer erkennbar. Priorität: Must. Abhängigkeit: REQ-178, REQ-179.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-180)

---

### REQ-L0-237 — SN-237: Globales Permissions-Default-Modell als Source-of-Truth

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-181.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Berechtigungen (RBAC-Rollenmodell admin/editor/viewer/approver, `ItemPermission`-Datenmodell, `auth_tenancy`) existieren aktuell ausschließlich pro Workspace — analog zum bisherigen Workflow-Modell (REQ-178, vor dessen Fix). Es MUSS — symmetrisch zu REQ-178 — eine tenant-weite globale Permissions-Default-Definition existieren. Ein neu angelegter Workspace MUSS beim Erstellen automatisch die aktuell gültige globale Permissions-Default-Definition erben. Diese Anforderung beschreibt ausschließlich das Datenmodell (Global-Default + Vererbung); ob und wie dieses Modell die bestehende hartkodierte `UserRole`/`ItemPermission`-Durchsetzung als autoritative Zugriffskontrolle ablöst, regelt REQ-186. Akzeptanzkriterium: Für einen frisch erstellten Workspace ist ohne manuelle Konfiguration ein aus dem globalen Default abgeleitetes, funktionsfähiges Berechtigungsschema vorhanden. Priorität: Must. Abhängigkeit: REQ-014, REQ-178.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-181)

---

### REQ-L0-238 — SN-238: Workspace-Permissions-Override bleibt vollständig editierbar

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-182.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein Workspace MUSS seine geerbte Permissions-Konfiguration weiterhin vollständig anpassen können (z.B. abweichende Rollenzuordnungen, Item-Permissions). Eine workspace-eigene Anpassung wird als Override der globalen Permissions-Default-Definition geführt und bleibt unabhängig davon persistiert, bis ein Reset (REQ-183) erfolgt. Regressionsschutz bezieht sich auf die für Nutzer sichtbare Bearbeitungsfähigkeit (bestehende Bedienelemente/Operationen aus REQ-014 und Item-Permission-Verwaltung MÜSSEN funktional erhalten bleiben) — NICHT auf den Fortbestand der bisherigen hartkodierten `UserRole`/`ItemPermission`-Durchsetzungslogik selbst, deren Ablösung als autoritative Zugriffskontrolle explizit Ziel von REQ-186 ist. Akzeptanzkriterium: Alle bisher unterstützten Berechtigungs-Bearbeitungsoperationen funktionieren nach Einführung des globalen Default-Modells unverändert für einen Workspace mit Override — unabhängig davon, ob im Hintergrund bereits das neue autoritative Modell (REQ-186) oder noch die Legacy-Durchsetzung entscheidet. Priorität: Must. Abhängigkeit: REQ-181.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-182)

---

### REQ-L0-239 — SN-239: Permissions Reset-to-Default

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-183.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein Workspace, dessen Permissions-Konfiguration vom globalen Default abweicht (Override, REQ-182), MUSS jederzeit auf den aktuell gültigen globalen Default zurückgesetzt werden können. Das System MUSS — analog zu REQ-180 — erkennbar unterscheiden, ob die Workspace-Permissions-Konfiguration aktuell dem globalen Default entspricht ("on-default") oder davon abweicht ("customized"). Akzeptanzkriterium: Für einen Workspace im "customized"-Zustand ist eine Reset-Aktion verfügbar, die nach Ausführung den "on-default"-Zustand herstellt; der Zustand ist vor und nach dem Reset für den Nutzer erkennbar. Priorität: Must. Abhängigkeit: REQ-181, REQ-182.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-183)

---

### REQ-L0-240 — SN-240: Settings-IA-Split: System Settings als eigener Navigationsbereich

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-184.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Workspace-Einstellungen und System-Einstellungen sind aktuell in einer einzigen Komponente/Route zusammengefasst (`WorkspaceSettings.tsx`, Tabs general/traceability/visibility/llm/governance/admin). Es MUSS ein eigenständiger Top-Level-Navigationseintrag "System Settings" mit eigener Route entstehen. Workspace-bezogene Einstellungen (Allgemein, Traceability, Sichtbarkeit, LLM) VERBLEIBEN unter der bestehenden workspace-gebundenen Settings-Route. System-weite Einstellungen (Administration, System-Health, Lifecycle sowie neu: globale Workflow-Defaults REQ-178 und globale Permissions-Defaults REQ-181) ZIEHEN in den neuen System-Settings-Bereich um. Bestehendes Karten-/Tab-Styling bleibt visuell unverändert — reiner IA-Split, kein Redesign. Akzeptanzkriterium: System-weite Einstellungen sind über einen eigenen Top-Level-Navigationseintrag erreichbar und nicht mehr Teil der workspace-gebundenen Settings-Ansicht; Workspace-bezogene Einstellungen bleiben an ihrem bisherigen Ort erreichbar. Priorität: Should.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-184)

---

### REQ-L0-241 — SN-241: Governance-Tab "Workflows & Berechtigungen" auf Global/Override/Reset-Modell umstellen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-185.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Der bestehende Governance-Tab (`WorkspaceSettings.tsx:295`, `WorkflowsSection.tsx`, `PermissionsSection`) bildet ausschließlich workspace-lokale Konfiguration ab und wird durch die Einführung globaler Defaults (REQ-178, REQ-181) fachlich obsolet — er MUSS dismantled und auf das neue Modell umgebaut werden: globaler Default (Verwaltung im System-Settings-Bereich, REQ-184), Workspace-Override-Status ("on-default"/"customized") und Zugriff auf die Reset-Aktion (REQ-180, REQ-183) für Workflows und Berechtigungen. Das konkrete visuelle/interaktive Design dieser Umstellung ist NICHT Teil dieser Anforderung, sondern eines nachgelagerten Design-Schritts (ui-ux-designer). Akzeptanzkriterium: Der bestehende Governance-Tab (bzw. sein Nachfolger) zeigt für Workflows und Berechtigungen erkennbar den Override-Status je Workspace und bietet Zugriff auf Reset und (im System-Settings-Bereich) auf die globalen Defaults. Priorität: Should. Abhängigkeit: REQ-178, REQ-180, REQ-181, REQ-183, REQ-184.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-185)

---

### REQ-L0-242 — SN-242: Globales Permission-Modell wird alleinige autoritative Durchsetzungsinstanz

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-186.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die tatsächliche Zugriffskontrolle läuft heute ausschließlich über hartkodierte `UserRole`/`ItemPermission`-Prüfungen (COMP-AT-002 AuthorizationService, `backend/auth_tenancy`) — unabhängig vom Global-Default/Override/Reset-Permissions-Modell aus REQ-181–183, das ursprünglich als zusätzliche Governance-/Anzeige-Schicht NEBEN dieser Durchsetzung konzipiert war. Der Nutzer hat entschieden, dass diese additive Einordnung nicht ausreicht: Das Global-Default/Override/Reset-Permission-Modell MUSS die reale, alleinige autoritative Durchsetzungsinstanz für Zugriffsentscheidungen in der gesamten Anwendung werden und die hartkodierten `UserRole`/`ItemPermission`-Prüfungen vollständig ablösen (nicht nur ergänzen). Akzeptanzkriterium: Nach vollständiger Umsetzung entscheiden ausschließlich das globale Permission-Default-Modell und seine Workspace-Overrides (REQ-181–183) über Zugriffsberechtigungen für alle Artefakttypen und Operationen; keine Zugriffsentscheidung im System stützt sich mehr auf die alte hartkodierte `UserRole`/`ItemPermission`-Prüfung als primäre Quelle. Priorität: Must. Abhängigkeit: REQ-181, REQ-182, REQ-183.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-186)

---

### REQ-L0-243 — SN-243: Sicherer Migrationspfad mit sichtbarem Regressionsrisiko für Permission-Ablösung

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-187.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Ablösung der hartkodierten `UserRole`/`ItemPermission`-Durchsetzung durch das neue autoritative Permission-Modell (REQ-186) betrifft die live Zugriffskontrolle der gesamten Anwendung und hat damit einen erheblichen Blast-Radius. Die Umstellung DARF NICHT als stiller Hard-Cutover erfolgen. Es MUSS ein sicherer Rollout-Pfad existieren, der Regressionsrisiken vor der endgültigen Abschaltung der Legacy-Prüfung sichtbar macht, statt sie zu verbergen (konkreter Mechanismus — z.B. Parallelbetrieb/Verifikation alt vs. neu, schrittweise Aktivierung — ist Aufgabe von database-engineer/senior-developer und NICHT Teil dieser Anforderung). Akzeptanzkriterium: Vor der endgültigen Abschaltung der `UserRole`/`ItemPermission`-Hardcoding-Prüfung liegt ein Nachweis vor, dass zwischen alter und neuer Zugriffsentscheidung keine unbeabsichtigten Abweichungen bestehen, oder etwaige Abweichungen sind explizit dokumentiert und bewusst akzeptiert; ein negativer bzw. fehlender Nachweis blockiert den Cutover. Priorität: Must. Abhängigkeit: REQ-186.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-187)

---

### REQ-L0-244 — SN-244: Selbstständige Erstinitialisierung der Applikation ohne separate Bootstrap-/Provisioning-Mechanismen

**Implementation State:** Not Implemented
**Review Findings:** Migration aus REQ-188.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Die Erstinitialisierung eines frischen Deployments erfolgt aktuell über zwei getrennte, fehleranfällige Mechanismen: (1) einen dedizierten `bootstrap`-Service in `docker-compose.yml` (`command: python manage.py bootstrap_admin`), der ausschließlich den Admin-Account anlegt, und (2) das separate Management-Command `provision_workflow_definitions` für Workflow-Definitionen pro Workspace, das NICHT automatisch aufgerufen wird. Der Bootstrap-Service ruft das Workflow-Seeding nicht mit auf — Folge: Nach jedem `docker-compose up` mit frischem Volume steht der Demo-/Erst-Workspace ohne Workflow-Definitionen da. Die Applikation MUSS ihren Erstinitialisierungs-Zustand (Admin-Account UND Default-Workflow-Definitionen pro neuem Workspace) beim ersten Start SELBST herstellen — OHNE dediziertes Bootstrap-Container-/Service-Pattern und OHNE separat manuell aufzurufendes Provisioning-Command. Denkbare Zielarchitektur (nicht bindend vorgeschrieben): Self-Initializing beim Anwendungsstart, z.B. via Django `AppConfig.ready()`, Signal, Lazy-Check beim ersten Request oder direkt im `create_workspace`-Aufruf. Diese Anforderung ergänzt REQ-178 (regelt das Datenmodell des globalen, presetweiten Workflow-Defaults) um den Trigger-/Provisionierungs-Mechanismus (WIE/WANN die Erstinitialisierung ausgelöst wird) — sie ersetzt REQ-178 nicht. Akzeptanzkriterium: Ein frisches `docker-compose up` (leeres Volume) führt ohne manuellen Zusatzschritt zu einem vollständig initialisierten Demo-/Erst-Workspace (Admin-Account UND Workflow-Definitionen vorhanden) — ohne dedizierten Bootstrap-Container und ohne manuellen Aufruf eines Provisioning-Commands. Priorität: Should. Abhängigkeit: REQ-178.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-188)

---

### REQ-L0-245 — SN-245: ReviewPolicy-Modell und Workspace-Konfiguration

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-189.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Ein neues `ReviewPolicy`-Modell mit Feldern `workspace`, `mode` (auto/review_changes/review_all/review_high_risk), und `min_confidence` (Dezimalzahl, Schwellwert für high_risk-Modus) wird in die Persistenz-Schicht eingefügt. `SettingsService` erhält zwei neue Methoden: `get_effective_review_policy(workspace_id)` (liefert Workspace-Policy oder Tenant-Default) und `update_review_policy(workspace_id, mode, min_confidence)` (speichert Workspace-Override). Die Konfiguration ist pro-Workspace editierbar und wirkt auf alle AI-Derivation- und Approval-Workflow-Übergänge. Priorität: Must. Abhängigkeit: Phase 0 (outdate-Mechanismus, WorkflowItemState).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-189)

---

### REQ-L0-246 — SN-246: MCP-Tool-Gruppe `review.*` für Approval-Workflows

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-190.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Neue MCP-Tool-Group `review` mit vier Tools: `review.list_pending` (Artefakte in `in_review`-State), `review.approve` (Transition zu `approved`), `review.reject` (Transition zu einem `rejected`/`draft`-State), `review.request_changes` (Requester-Notification ohne State-Änderung). Jedes Tool ist Thin Wrapper über `WorkflowFacade`-Transitionen und erzeugt `WorkflowHistoryEntry`-Audit-Einträge. RBAC-Gating: nur `approver`-Rolle und höher darf diese Tools nutzen. Tools werden in `backend/mcp_server/tool_registry.py` registriert. Priorität: Must. Abhängigkeit: REQ-190-Test (Approval-Workflows aus Phase 0).

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-190)

---

### REQ-L0-247 — SN-247: REST-Endpunkt für ReviewPolicy-Verwaltung

**Implementation State:** Implemented
**Review Findings:** Migration aus REQ-191.
**Test Status:** Missing
**Priority:** desired
**Acceptance Criteria:**
- [ ] Neuer REST-Endpoint `GET/PUT /api/v1/workspaces/{workspace_id}/review-policy/` (admin-only) mit DRF-Serializer für `ReviewPolicy`. Der GET-Endpoint liefert die effektive Policy (Workspace-Override oder Tenant-Default). Der PUT-Endpoint aktualisiert die Workspace-Policy via `SettingsService.update_review_policy()` und validiert die Eingaben (mode muss gültig sein, min_confidence ≥ 0.0 und ≤ 1.0). Fehlerhafte Eingaben werden mit HTTP 400 abgelehnt, fehlende Admin-Berechtigung mit HTTP 403. Priorität: Must. Abhängigkeit: REQ-189.

**Rationale:** Übernommen aus REQUIREMENTS.md
**Abgeleitet von:** REQUIREMENTS.md (REQ-191)

