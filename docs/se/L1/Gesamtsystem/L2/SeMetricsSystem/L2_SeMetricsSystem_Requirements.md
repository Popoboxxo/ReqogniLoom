# L2 SeMetrics Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** SeMetricsSystem (ARCH-L1-015)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-031 (primär), REQ-L1-003 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Systemzweck

Das SeMetricsSystem ist ein reines Read-Modell zur Berechnung und Exposition von SE-Prozessmetriken. Es aggregiert Daten aus vier Quellsystemen — AuditLog (ARCH-L1-012), TraceabilityEngine (ARCH-L1-007), WorkflowEngine (ARCH-L1-005) und ApplicationService (ARCH-L1-004) — und stellt das Ergebnis als strukturierten JSON-Metrikbericht bereit. Das System führt keine Schreiboperationen durch und erzeugt keine Seiteneffekte auf den Quelldaten.

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-042 | input | control | `compute_metrics(workspace_id, timeframe, scope_filter)` vom RestApiAdapter (ARCH-L1-002) via `GET /metrics/workspace/{id}` |
| IF-L1-043 | input | control | Dashboard-Datenabruf vom ReactFrontend (ARCH-L1-001) via RestApiAdapter (A002 → A015) |
| IF-L1-044 | output | data | `query_changes(workspace_id, timeframe)` an AuditLog (ARCH-L1-012) — Quelldaten für Volatility-Berechnung |
| IF-L1-045 | output | data | `coverage(workspace_id)` an TraceabilityEngine (ARCH-L1-007) — Traceability-Coverage-Daten |
| IF-L1-046 | output | data | `find_incomplete_states(workspace_id)` an WorkflowEngine (ARCH-L1-005) — Workflow-Lücken-Daten |
| IF-L1-047 | output | data | `query_risks_by_severity(workspace_id)` an ApplicationService (ARCH-L1-004) — Risiko-Artefakte nach Schweregrad |
| IF-L1-048 | output | data | Metric-Cache-Entity Lesen/Schreiben an PersistenceLayer (ARCH-L1-010) — optional materialisierte Aggregationen |

---

## L2 Subsystem-Anforderungen

### REQ-L2-SM-001: REST-Endpunkt GET /metrics/workspace/{id}

Das SeMetricsSystem SHALL den Endpunkt `GET /metrics/workspace/{id}` bereitstellen, der einen vollständigen strukturierten JSON-Metrikbericht für den angegebenen Workspace zurückgibt. Die Antwort SHALL mindestens die vier Metrik-Kategorien Volatility, TraceabilityCoverage, WorkflowLuecken und OffeneRisiken enthalten. Anfragen ohne gültigen Bearer Token oder API-Key MÜSSEN mit HTTP 401 abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `GET /metrics/workspace/{id}` mit gültigem Token → HTTP 200 + JSON mit allen vier Metrik-Kategorien
- [ ] Unbekannte `workspace_id` → HTTP 404
- [ ] Kein oder ungültiger Token → HTTP 401
- [ ] Antwortzeit ≤ 500ms (p95) bei bis zu 10.000 Requirements im Workspace

**Interfaces:**
- Incoming: IF-L1-042, IF-L1-043
- Outgoing: IF-L1-044, IF-L1-045, IF-L1-046, IF-L1-047

**Traceability:** REQ-L1-031
**Rationale:** Der REST-Endpunkt ist die primäre Schnittstelle für Dashboard und API-Clients.

---

### REQ-L2-SM-002: Zeitraum- und Scope-Filter

Das SeMetricsSystem SHALL optionale Query-Parameter `timeframe` (ISO-8601-Zeitraum, z.B. `P30D`) und `scope_filter` (Artefakttyp-Liste) am Metrik-Endpunkt auswerten. Fehlt `timeframe`, SHALL ein konfigurierter Standardwert (Default: 30 Tage) verwendet werden. Ungültige Parameter-Werte MÜSSEN mit HTTP 400 und beschreibender Fehlermeldung abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `?timeframe=P7D` → Metrik-Berechnungen beschränkt auf letzten 7 Tage
- [ ] `?timeframe=P90D` → letzten 90 Tage
- [ ] Kein `timeframe` → Default 30 Tage
- [ ] `?timeframe=INVALID` → HTTP 400 `"Invalid timeframe format"`
- [ ] `?scope_filter=Requirement,ArchitectureElement` → Metriken nur für diese Typen

**Interfaces:**
- Incoming: IF-L1-042

**Traceability:** REQ-L1-031
**Rationale:** REQ-L1-031 fordert konfigurierbare Zeiträume für die Volatility-Berechnung.

---

### REQ-L2-SM-003: Requirements-Volatility-Berechnung

Das SeMetricsSystem SHALL Requirements Volatility berechnen als: Anzahl Änderungsereignisse je Requirement im konfigurierbaren Zeitraum, aggregiert als Gesamt-Änderungsrate (Total-Changes / Total-Requirements) und als geordnete Liste der Top-10-volatilsten Requirements mit Änderungszahl. Quelldaten: AuditLog (IF-L1-044) nach Entitäts-Typ `Requirement` und Operation `update`/`workflow_transition`.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 100 Requirements, 50 Änderungen in 30 Tagen → `{total_changes: 50, avg_changes_per_req: 0.5, top10_volatile: [...]}`
- [ ] Kein Änderungsereignis im Zeitraum → `{total_changes: 0, avg_changes_per_req: 0.0, top10_volatile: []}`
- [ ] Top-10-Liste absteigend nach Änderungszahl sortiert
- [ ] Nur Ereignisse innerhalb `timeframe` gezählt

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-044

**Traceability:** REQ-L1-031, REQ-L1-011 (mitwirkend)
**Rationale:** Volatility ist die erste Kernmetrik aus REQ-L1-031 für Prozesssteuerung und Änderungsmanagement.

---

### REQ-L2-SM-004: Traceability-Coverage-Berechnung

Das SeMetricsSystem SHALL Traceability Coverage berechnen als: Anteil der Requirements mit mindestens einem ausgehenden TraceLink (beliebiger Typ), ausgedrückt in Prozent. Quelldaten: TraceabilityEngine `coverage(workspace_id)` (IF-L1-045). Die Antwort SHALL Gesamtanzahl, abgedeckte Anzahl, Prozentwert und Liste der unabgedeckten Requirement-IDs enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 20 Requirements, 15 mit TraceLinks → `{total: 20, covered: 15, coverage_percent: 75.0, uncovered_ids: [...]}`
- [ ] 0 Requirements → `{total: 0, covered: 0, coverage_percent: 0.0, uncovered_ids: []}`
- [ ] `coverage_percent` auf eine Nachkommastelle gerundet
- [ ] `uncovered_ids` enthält ausschließlich IDs ohne jeglichen ausgehenden TraceLink

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-045

**Traceability:** REQ-L1-031, REQ-L1-003 (mitwirkend)
**Rationale:** Traceability Coverage ist die zweite Kernmetrik aus REQ-L1-031; misst Vollständigkeit der Anforderungsverknüpfung.

---

### REQ-L2-SM-005: Workflow-Lücken-Erkennung

Das SeMetricsSystem SHALL Workflow-Lücken identifizieren als: Items ohne vollständige Workflow-Historie, d.h. Items, die einen oder mehrere obligatorische Zustände der aktiven WorkflowDefinition nie durchlaufen haben. Quelldaten: WorkflowEngine `find_incomplete_states(workspace_id)` (IF-L1-046). Die Antwort SHALL Gesamtanzahl betroffener Items und eine Liste mit Item-ID, Item-Typ und fehlendem Zustand enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Item hat aktive WorkflowDefinition mit Pflicht-State `reviewed`, aber keine `reviewed`-History → in Lückenliste enthalten
- [ ] Item hat vollständige History → nicht in Lückenliste
- [ ] Workspace ohne konfigurierte WorkflowDefinition → `{total_incomplete: 0, items: []}`
- [ ] Antwort enthält `{item_id, item_type, missing_state}` je Eintrag

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-046

**Traceability:** REQ-L1-031, REQ-L1-009 (mitwirkend)
**Rationale:** Workflow-Lücken sind die dritte Kernmetrik aus REQ-L1-031; zeigt prozessuale Compliance-Lücken.

---

### REQ-L2-SM-006: Offene Risiken nach Schweregrad

Das SeMetricsSystem SHALL offene Risiken nach Schweregrad aggregieren. Quelldaten: ApplicationService `query_risks_by_severity(workspace_id)` (IF-L1-047), gefiltert auf Risiko-Artefakte mit WorkflowState != geschlossen/mitigation-abgeschlossen. Die Antwort SHALL Gesamtanzahl sowie Aufschlüsselung nach Schweregrad-Kategorie (critical, high, medium, low) enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace mit 2 critical, 5 high, 3 medium Risiken → `{total: 10, by_severity: {critical: 2, high: 5, medium: 3, low: 0}}`
- [ ] Risiko mit WorkflowState = geschlossen → nicht gezählt
- [ ] Kein Risiko-Artefakt im Workspace → `{total: 0, by_severity: {critical: 0, high: 0, medium: 0, low: 0}}`

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-047

**Traceability:** REQ-L1-031, REQ-L1-029 (mitwirkend)
**Rationale:** Offene Risiken nach Schweregrad sind die vierte Kernmetrik aus REQ-L1-031 für Risikomanagement.

---

### REQ-L2-SM-007: Konfigurierbare Schwellwert-Warnungen

Das SeMetricsSystem SHALL pro Workspace konfigurierbare Schwellwert-Warnungen für alle vier Metrik-Kategorien unterstützen. Überschreitet ein Metrikwert den konfigurierten Schwellwert, SHALL die Antwort ein `warnings`-Objekt mit Metrik-Name, Ist-Wert, Schwellwert und Beschreibung enthalten. Schwellwerte für Metriken SHALL über eine dedizierte konfigurierbare Schnittstelle verwaltbar sein (CRUD).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Konfiguriere `traceability_coverage_min: 80` → Coverage = 65% → `warnings: [{metric: "traceability_coverage", actual: 65.0, threshold: 80, description: "..."}]`
- [ ] Coverage = 90% mit `min: 80` → kein `warnings`-Eintrag für diese Metrik
- [ ] `PUT /metrics/workspace/{id}/thresholds` mit gültiger Konfiguration → HTTP 200
- [ ] Kein Schwellwert konfiguriert → `warnings: []`
- [ ] Ungültiger Schwellwert-Typ → HTTP 400

**Interfaces:**
- Incoming: IF-L1-042, IF-L1-043
- Outgoing: IF-L1-048

Die Schwellwert-Konfiguration wird via IF-L1-048 (PersistenceLayer) persistiert; dies ist die einzige Schreiboperation des SeMetricsSystems außer der optionalen Metric-Cache-Persistenz.

**Traceability:** REQ-L1-031
**Rationale:** REQ-L1-031 fordert konfigurierbare Schwellwert-Warnungen explizit.

---

### REQ-L2-SM-008: Read-Modell ohne Seiteneffekte

Das SeMetricsSystem SHALL ausschließlich lesende Operationen auf allen Quellsystemen durchführen. Es darf keine schreibenden Operationen auf Requirements, ArchitectureElements, TestCases, TraceLinks, WorkflowStates oder AuditLog-Einträgen ausführen. Der einzig erlaubte Schreibzugriff ist die optionale Persistenz von Metric-Cache-Einträgen (IF-L1-048) sowie die Persistenz von Schwellwert-Konfigurationen (IF-L1-048).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Vor und nach einem `GET /metrics/workspace/{id}`-Aufruf: Anzahl Requirements, TraceLinks, WorkflowState-Einträge und AuditLog-Einträge unverändert
- [ ] Keine schreibenden Operationen auf Kern-Entitäten (Requirements, TraceLinks, WorkflowStates, AuditLog-Einträge) durch das SeMetricsSystem nachweisbar — prüfbar durch Integrationstests, die Zustand der Kern-Entitäten vor und nach einem GET /metrics/workspace/{id}-Aufruf vergleichen.
- [ ] Erlaubte Schreib-Ausnahmen via IF-L1-048: (a) Metric-Cache-Persistenz (optional, REQ-L2-SM-009) und (b) Schwellwert-Konfiguration (REQ-L2-SM-007) — beide nachweislich auf IF-L1-048 beschränkt, keine Schreibzugriffe auf Kern-Entitäten.

**Interfaces:**
- Outgoing: IF-L1-044, IF-L1-045, IF-L1-046, IF-L1-047, IF-L1-048

**Traceability:** REQ-L1-031
**Rationale:** Read-Modell-Charakter verhindert zirkuläre Abhängigkeiten und unbeabsichtigte Mutations-Seiteneffekte auf transaktionale Pfade.

---

### REQ-L2-SM-009: Optionale Metric-Cache-Persistenz mit proaktiver Vorberechnung

Das SeMetricsSystem SOLLTE berechnete Aggregationsergebnisse optional in einer Metric-Cache-Entity (IF-L1-048) materialisieren, um wiederholte Berechnungen für denselben Workspace und Zeitraum zu vermeiden. Cache-Invalidierung SHALL bei Empfang eines Änderungsereignisses aus dem AuditLog für den betroffenen Workspace erfolgen oder nach einer konfigurierbaren TTL. Zusätzlich SHALL ein Celery-Beat-Job Metriken für aktive Workspaces in konfigurierbaren Intervallen (Default: alle 15 Minuten) proaktiv vorberechnen und Ergebnisse in den Cache schreiben, bevor ein Cache-Miss durch einen eingehenden Request ausgelöst wird.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Zweiter identischer `GET /metrics/workspace/{id}?timeframe=P30D`-Aufruf innerhalb TTL → Antwortzeit ≤ 100ms (p95)
- [ ] Nach einer Requirement-Änderung im Workspace → Cache ungültig; nächster Aufruf berechnet neu
- [ ] TTL konfigurierbar (Default: 5 Minuten)
- [ ] Cache-Fehler → Fallback auf Live-Berechnung, kein HTTP 5xx
- [ ] Celery-Beat-Job läuft alle 15 Minuten (konfigurierbar) und befüllt Cache für alle aktiven Workspaces proaktiv; nach einem erfolgreichen Beat-Lauf ist der Cache für alle aktiven Workspaces warm, bevor der nächste Request eintrifft

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-048

**Traceability:** REQ-L1-031, REQ-L1-026 (mitwirkend)
**Rationale:** Materialisierter Cache reduziert Last auf Quellsysteme bei häufigen Dashboard-Refreshes. Proaktive Vorberechnung per Celery-Beat verhindert, dass WSGI-Worker bei großen Workspaces durch schwere Aggregationen blockiert werden (Handlungsempfehlung 1.3).

---

### REQ-L2-SM-010: Tenant-Isolation für alle Metrik-Abfragen

Das SeMetricsSystem SHALL sicherstellen, dass alle Quelldaten-Abfragen (IF-L1-044 bis IF-L1-047) ausschließlich Daten des aktiven Tenants liefern. Workspace-ID-Validierung gegen den Tenant-Kontext des Aufrufers SHALL vor jeder Berechnung erfolgen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant-1 ruft `GET /metrics/workspace/{id-von-tenant-2}` → HTTP 403 (Workspace existiert, aber Tenant-Kontext des Aufrufers schließt Zugriff aus — 403 Forbidden, nicht 404, um Ressourcen-Existenz nicht zu verschleiern in SE-Prozess-Kontext.)
- [ ] Volatility-Berechnung enthält ausschließlich AuditLog-Einträge des eigenen Tenants
- [ ] Coverage-Berechnung enthält ausschließlich TraceLinks des eigenen Tenants

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-044, IF-L1-045, IF-L1-046, IF-L1-047

**Traceability:** REQ-L1-031, REQ-L1-015 (mitwirkend)
**Rationale:** Row-Level-Isolation muss konsistent durch alle Schichten gelten, auch für Read-Modelle.

---

### REQ-L2-SM-011: Metrik-Antwort-Performance-SLA

Das SeMetricsSystem SHALL die folgenden Performance-SLAs einhalten: ≤ 500ms (p95) für eine vollständige Metrik-Berechnung ohne Cache bei bis zu 10.000 Requirements und 50.000 TraceLinks im Workspace. Überschreitungen von 2.000ms (p99) gelten als Verletzung.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Vollständige Berechnung aller vier Metrik-Kategorien für 10.000 Requirements → ≤ 500ms (p95) in Lasttests
- [ ] p99 ≤ 2.000ms unter Lastbedingungen (50 gleichzeitige Metrik-Anfragen)
- [ ] Dashboard-Refresh-Szenario (repeated GET alle 30s) → kein Performance-Abbau über 10-Minuten-Fenster

**Interfaces:**
- Incoming: IF-L1-042, IF-L1-043

**Traceability:** REQ-L1-031, REQ-L1-026 (mitwirkend)
**Rationale:** REQ-L1-026 fordert ≤ 200ms für Standard-Queries; Metrik-Aggregation aus vier Subsystemen erhält relaxierten SLA von 500ms.

---

### REQ-L2-SM-012: Strukturiertes JSON-Antwortformat

Das SeMetricsSystem SHALL ein stabiles, versioniertes JSON-Antwortformat für den Metrik-Endpunkt bereitstellen. Das Format SHALL mindestens die Felder `workspace_id`, `computed_at`, `timeframe`, `volatility`, `traceability_coverage`, `workflow_gaps`, `open_risks` und `warnings` enthalten. Feldnamen und -typen dürfen in v1 nicht ohne API-Versionierung geändert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Antwort enthält alle acht Pflicht-Felder
- [ ] `computed_at` ist ISO-8601-Zeitstempel
- [ ] `timeframe` spiegelt den angewendeten Berechnungszeitraum wider (auch wenn Default verwendet)
- [ ] Fehlende optionale Werte werden als `null` oder leere Objekte serialisiert, nicht weggelassen
- [ ] OpenAPI-Schema für den Endpunkt in der auto-generierten Spezifikation (REQ-L1-006) vorhanden

**Interfaces:**
- Incoming: IF-L1-042, IF-L1-043

**Traceability:** REQ-L1-031, REQ-L1-006 (mitwirkend)
**Rationale:** Stabiles Format verhindert Breaking Changes im Dashboard und bei API-Clients.

---

### REQ-L2-SM-013: Thundering-Herd-Prevention bei Cache-Miss

Das SeMetricsSystem MUSS sicherstellen, dass bei einem Cache-Miss für einen Workspace/Zeitraum-Schlüssel genau EINE Celery-Task zur Neuberechnung ausgelöst wird. Alle parallel eingehenden Anfragen für denselben Workspace/Zeitraum-Schlüssel MÜSSEN auf das Ergebnis dieser Task warten, anstatt eigenständig weitere Berechnungen anzustoßen. Die Implementierung MUSS einen distributed Lock-Mechanismus (z.B. Redis-Lock) verwenden, der für die Dauer der Berechnung exklusiv gehalten wird.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] 50 gleichzeitige Anfragen für denselben Workspace/Zeitraum bei leerem Cache → genau 1 Celery-Task wird ausgelöst, 49 Anfragen warten auf das Ergebnis dieser Task (nachweisbar per Task-Zähler im Lasttest)
- [ ] Redis-Lock wird vor Auslösung der Berechnung gesetzt und nach Schreiben des Cache-Eintrags freigegeben
- [ ] Lock-Timeout konfigurierbar (Default: 30 Sekunden); nach Ablauf wird Lock freigegeben und nächste Anfrage darf neue Berechnung starten
- [ ] Wartende Anfragen erhalten dasselbe Ergebnis wie die berechnende Task (kein doppeltes Lesen aus Quellsystemen)
- [ ] Lock-Fehler (z.B. Redis nicht erreichbar) → Fallback auf direkte Live-Berechnung ohne Lock; kein HTTP 5xx

**Interfaces:**
- Incoming: IF-L1-042
- Outgoing: IF-L1-048

**Traceability:** REQ-L1-026 (primär), REQ-L1-031 (mitwirkend)
**Rationale:** Ohne Thundering-Herd-Prevention können bei einem Cache-Miss gleichzeitige Requests alle eine schwere Aggregation starten, was WSGI-Worker blockiert und die Quellsysteme unter Last setzt. Ein distributed Lock stellt sicher, dass die teure Berechnung exakt einmal erfolgt (Handlungsempfehlung 1.3).

---

## Traceability-Matrix: REQ-L2-SM → REQ-L1

| REQ-L2-SM | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-SM-001 | REQ-L1-031 | — |
| REQ-L2-SM-002 | REQ-L1-031 | — |
| REQ-L2-SM-003 | REQ-L1-031 | REQ-L1-011 |
| REQ-L2-SM-004 | REQ-L1-031 | REQ-L1-003 |
| REQ-L2-SM-005 | REQ-L1-031 | REQ-L1-009 |
| REQ-L2-SM-006 | REQ-L1-031 | REQ-L1-029 |
| REQ-L2-SM-007 | REQ-L1-031 | — |
| REQ-L2-SM-008 | REQ-L1-031 | — |
| REQ-L2-SM-009 | REQ-L1-031 | REQ-L1-026 |
| REQ-L2-SM-010 | REQ-L1-031 | REQ-L1-015 |
| REQ-L2-SM-011 | REQ-L1-031 | REQ-L1-026 |
| REQ-L2-SM-012 | REQ-L1-031 | REQ-L1-006 |
| REQ-L2-SM-013 | REQ-L1-026 | REQ-L1-031 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-SM | 13 |
| Mandatory | 12 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 1 (REQ-L1-031) |
| Abgedeckte REQ-L1 (mitwirkend) | 6 |
| Referenzierte Interfaces | IF-L1-042..IF-L1-048 (alle 7) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Handoff: HOFF-20260621-002 | Parent: REQ-L1-031 | Architektur-Referenz: ARCH-L1-015*
*Designation: component (terminal) — decomposition_status: terminal*
