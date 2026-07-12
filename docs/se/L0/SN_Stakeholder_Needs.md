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

