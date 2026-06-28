# L3 MetricsAggregator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-SM-002 — MetricsAggregator
> **Parent-System:** SeMetricsSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Kern-Orchestrator: ruft die vier Quell-Interfaces (IF-L1-044..047) parallel ab, delegiert Berechnungen an VolatilityCalculator, CoverageCalculator, WorkflowGapDetector und RiskClassifier, sammelt deren Ergebnisse, delegiert Schwellwert-Prüfung an ThresholdEvaluator, baut das vollständige MetricsResult-Objekt zusammen.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-SM-001 | REST-Endpunkt GET /metrics/workspace/{id} mit vollständigem JSON-Metrikbericht |
| REQ-L2-SM-008 | Read-Modell ohne Seiteneffekte auf Quellsystemen |
| REQ-L2-SM-011 | Metrik-Antwort-Performance-SLA ≤ 500ms (p95) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-SM-INT-001 | eingehend | COMP-SM-001 MetricsQueryController | `compute(workspace_id, timeframe, scope_filter, tenant_ctx) -> MetricsResult` |
| IF-SM-INT-002 | ausgehend | COMP-SM-003 VolatilityCalculator | `calculate(audit_entries: list[AuditEntry], timeframe) -> VolatilityResult` |
| IF-SM-INT-003 | ausgehend | COMP-SM-004 CoverageCalculator | `calculate(coverage_data: CoverageData) -> CoverageResult` |
| IF-SM-INT-004 | ausgehend | COMP-SM-005 WorkflowGapDetector | `detect(incomplete_states: list[IncompleteState]) -> WorkflowGapResult` |
| IF-SM-INT-005 | ausgehend | COMP-SM-006 RiskClassifier | `classify(risk_artifacts: list[RiskArtifact]) -> RiskResult` |
| IF-SM-INT-006 | ausgehend | COMP-SM-007 ThresholdEvaluator | `evaluate(metrics_result: MetricsResult, workspace_id) -> list[Warning]` |
| IF-SM-INT-009 | eingehend | COMP-SM-009 CeleryMetricsBeatWorker | `compute(workspace_id, timeframe, scope_filter=None, tenant_ctx=SystemCtx) -> MetricsResult` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-L1-044 | ausgehend | AuditLog | `query_changes(workspace_id, timeframe)` — Quelldaten für Volatility |
| IF-L1-045 | ausgehend | TraceabilityEngine | `coverage(workspace_id)` — Coverage-Daten |
| IF-L1-046 | ausgehend | WorkflowEngine | `find_incomplete_states(workspace_id)` — Lücken-Daten |
| IF-L1-047 | ausgehend | ApplicationService | `query_risks_by_severity(workspace_id)` — Risiko-Artefakte |

---

## L3 Komponenten-Anforderungen

### REQ-L3-SM002-001: Parallele Abfrage aller vier Quell-Interfaces


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsAggregator SHALL die vier Quell-Abfragen (IF-L1-044, IF-L1-045, IF-L1-046, IF-L1-047) parallel und nicht sequenziell ausführen. Erst nach Vorliegen aller vier Ergebnisse SHALL die Delegation an die Calculator-Schicht (COMP-SM-003..006) erfolgen. Ein Fehler einer einzelnen Quell-Abfrage SHALL mit einer partiellen Antwort behandelt werden, nicht mit einem HTTP 5xx, sofern mindestens drei der vier Quellen erfolgreich antworten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Four source queries issued concurrently (verifiable by timing: total time ≈ max(individual times), not sum)
- [ ] All four results available before calculator delegation begins
- [ ] Single source failure with three successful → partial MetricsResult returned, failed category marked as `null` with error indicator
- [ ] All four sources fail → HTTP 503 returned

---

### REQ-L3-SM002-002: Zusammenstellung des MetricsResult-Objekts


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsAggregator SHALL nach Vorliegen aller Calculator-Ergebnisse (von COMP-SM-003..006) und der Warnings-Liste (von COMP-SM-007) ein vollständiges `MetricsResult`-Objekt zusammenstellen, das alle vier Metrik-Kategorien sowie die `warnings`-Liste enthält. Das Objekt SHALL den Zeitstempel `computed_at` (UTC) und den angewendeten `timeframe` enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] MetricsResult contains volatility, traceability_coverage, workflow_gaps, open_risks, warnings, computed_at, timeframe
- [ ] `computed_at` is set to UTC timestamp at time of aggregation completion
- [ ] `timeframe` reflects the window passed via IF-SM-INT-001
- [ ] warnings list is appended from ThresholdEvaluator result (may be empty list)

---

### REQ-L3-SM002-003: Strikte Read-Only-Nutzung aller Quell-Interfaces


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsAggregator SHALL ausschließlich lesende Operationen auf den vier Quell-Interfaces (IF-L1-044..047) ausführen. Er darf keine schreibenden Operationen auf Requirements, TraceLinks, WorkflowStates oder AuditLog-Einträgen der Quellsysteme auslösen. Dies ist strukturell durch die Signatur der Quell-Interfaces erzwungen; eine Verletzung gilt als kritischer Architekturverstoß.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Before and after `compute()` call: requirement count, trace link count, workflow state count, audit log entry count unchanged in source systems
- [ ] No write methods on source interfaces called (verifiable by interface contract enforcement)
- [ ] Integration tests confirm zero mutations on core entities per MetricsAggregator invocation

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
