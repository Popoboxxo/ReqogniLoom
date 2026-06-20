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

AI-Agenten (Coding-Agenten, Orchestratoren, CI/CD-Pipelines) benötigen strukturierten,
maschinenlesbaren Zugriff auf Anforderungen, Architektur und Tests — ohne Text-Parsing
oder Webhook-Wrapper — damit Code-Generierung und -Review mit vollständigem fachlichem
Kontext erfolgen können.

**Rationale:** Ohne strukturierte Schnittstelle geht AI-generierter Code oft am fachlichen
Kontext vorbei, weil das "Warum" hinter dem Code nicht maschinenlesbar vorliegt (KONZEPT.md, Abschnitt 1).

---

### REQ-L0-002 — SN-02: Skalierbare SE-Tiefe ohne Produktwechsel

Teams unterschiedlicher Reife (von Startups bis zu Automotive-Zulieferern) müssen
dieselbe Plattform mit unterschiedlicher Prozessstrenge nutzen können — von einfachem
Anforderungs-CRUD bis zu vollständigem Systems Engineering mit Baselines,
Approval-Workflows und Audit-Trails — ohne das Tool zu wechseln oder die Infrastruktur
umzubauen.

**Rationale:** Der Markt bietet keinen Mittelpunkt zwischen zu leichtgewichtigen Agile-Tools
und zu schweren Enterprise-Systemen (KONZEPT.md, Abschnitt 1, 2).

---

### REQ-L0-003 — SN-03: Vollständige Traceability zwischen Requirements, Architektur und Tests

Systems Engineers und AI-first Teams benötigen bidirektionale Verknüpfungen zwischen
Anforderungen, Architektur-Elementen und Testfällen, um Impact-Analysen, Coverage-Reports
und Konsistenz-Prüfungen durchzuführen — sowohl manuell als auch durch Agenten automatisiert.

**Rationale:** Ohne Traceability sind Blast-Radius-Analysen bei Anforderungsänderungen
nicht möglich; dies ist ein Kernbedarf beider Zielgruppen (KONZEPT.md, Abschnitt 3.4, 4.1).

---

### REQ-L0-004 — SN-04: Unveränderliche, benannte Anforderungs-Baselines auf mehreren Ebenen

Teams in regulierten oder sicherheitskritischen Umgebungen müssen zu jedem Zeitpunkt
auf einen exakten, unveränderlichen Stand aller Anforderungen zurückgreifen können —
auf Dokumentebene, Projektebene und instanzweit — um Übergaben, Reviews und spätere
Compliance-Nachweise zu ermöglichen.

**Rationale:** Baselines sind ein Must-Have für die SE-Zielgruppe; ohne sie ist
ReqFlow für Systems Engineers nicht ernsthaft nutzbar (KONZEPT.md, Abschnitt 4.1, 7.3).

---

### REQ-L0-005 — SN-05: Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates

Projektteams müssen den Lifecycle-Workflow für Requirements, Architektur-Elemente und
Testfälle an ihre Domäne und Compliance-Anforderungen anpassen können — inklusive
rollengebundener Approval-Gates — ohne Code-Änderungen am System.

**Rationale:** Ein hartcodierter Status-Enum (Draft/Approved/Deprecated) ist zu starr
für domänenspezifische Prozesse und formale Compliance-Anforderungen
(KONZEPT.md, Abschnitt 7a).

---

### REQ-L0-006 — SN-06: Self-Hosted Deployment ohne Vendor-Lock-in

Datenschutz-sensible Organisationen und Teams mit eigener Infrastruktur müssen
ReqFlow vollständig on-premise betreiben können — ohne Cloud-Zwang, ohne Lizenzkosten,
mit voller Datenkontrolle.

**Rationale:** Open Source (Apache 2.0) + Docker Compose ist die bewusste Entscheidung
gegen Vendor-Lock-in; SaaS erst ab v2 (KONZEPT.md, Abschnitt 1, 9.1, Anhang A).

---

### REQ-L0-007 — SN-07: LLM-gestützte Qualitätssicherung als optionale Capability

Teams, die LLM-Zugang haben, müssen AI-gestützte Funktionen (Validierung,
Zerlegungsvorschläge, Konsistenz-Checks) nutzen können — ohne dass das System bei
fehlendem LLM-Zugang nicht funktioniert.

**Rationale:** LLM als pluggable Capability ist eine der zwei AI-nativen Dimensionen;
Self-Hosted-Nutzer ohne LLM-Zugang dürfen keine Kernfunktionalität verlieren
(KONZEPT.md, Abschnitt 1, 9.3).

---

### REQ-L0-008 — SN-08: Mandantenfähige Isolation für spätere SaaS-Erweiterung

Das Datenmodell muss bereits in v1 so angelegt sein, dass eine spätere Aktivierung
echter Multi-Tenancy (mehrere Kunden auf einer Instanz) keine Datenmigration erfordert.

**Rationale:** Row-Level-Isolation mit tenant_id ist die Voraussetzung für den v2-SaaS-Betrieb
ohne Schema-Umbau (KONZEPT.md, Abschnitt 5.4, Anhang A).

---

### REQ-L0-009 — SN-09: Zweisprachige Benutzeroberfläche (Deutsch und Englisch)

Teams in deutschsprachigen Märkten und international gemischte Teams müssen die
Oberfläche in ihrer Arbeitssprache nutzen können, ohne Funktionseinschränkungen.

**Rationale:** Duale Marktausrichtung DE/EN ist eine v1-Entscheidung; nachträgliche
String-Extraktion ist aufwändiger als proaktive i18n-Integration
(KONZEPT.md, Abschnitt 9.3, Anhang A).

---

### REQ-L0-010 — SN-10: Terminologie-Flexibilität für zwei Zielgruppen ohne Datenverlust

Software-Teams (Epics, Stories, Acceptance Criteria) und Systems Engineers
(System Requirements, Functions, Verification Criteria) müssen auf demselben
Datenmodell arbeiten, ohne dass ein Profilwechsel Datenverluste oder Migrationen verursacht.

**Rationale:** Gemeinsames generisches Artefakt-Datenmodell mit konfigurierbaren
Terminologie-Layern ist das Fundament der Dual-Zielgruppen-Strategie
(KONZEPT.md, Abschnitt 3.2, 3.3).

---

### REQ-L0-011 — SN-11: Vollständiger Audit-Trail für agentengesteuerte und manuelle Änderungen

Compliance-orientierte Teams müssen zu jeder Anforderung, jedem Architektur-Element
und jedem Testfall nachvollziehen können: wer hat was wann geändert — einschließlich
AI-Agenten, die via MCP schreiben.

**Rationale:** Vollständige Auditierbarkeit aller Änderungen ist eine explizite
Non-Functional-Anforderung; MCP-Schreibzugriff ohne Audit-Log wäre ein Sicherheitsrisiko
(KONZEPT.md, Abschnitt 4.2, 6.1, 8.1).

---

### REQ-L0-012 — SN-12: REST API und MCP Server als gleichrangige, vollständige Schnittstellen

Entwickler und AI-Agenten müssen alle CRUD-Operationen auf allen Artefakttypen
sowohl über REST als auch über MCP vollständig durchführen können — keine
Zweit-Klassen-Schnittstelle.

**Rationale:** Der MCP Server ist kein Anhängsel, sondern greift direkt auf die
Django-Service-Schicht zu; REST ist für direkte Integration, MCP für AI-Agenten
(KONZEPT.md, Abschnitt 6.1, 9.3).

---

### REQ-L0-013 — SN-13: Effiziente Übernahme bestehender Anforderungsdaten

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
