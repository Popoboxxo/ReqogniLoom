---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:30:00Z"
schema_version: "1.0.0"
---

# L3 MetricsAggregator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-SM-002_MetricsAggregator
> **Parent:** L2_SeMetricsSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der MetricsAggregator ist der zentrale Orchestrator für Metriken-Berechnung. Er ruft vier Quell-Interfaces parallel ab (AuditLog, TraceabilityEngine, WorkflowEngine, ApplicationService), delegiert Berechnungen an vier spezialisierte Calculator-Module, aggregiert deren Ergebnisse, delegiert Schwellwert-Evaluierung, und assembliert ein vollständiges MetricsResult-Objekt mit allen Kategorien und Timestamps.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`MetricsAggregator` (Klasse):** Hauptklasse mit Methode `compute(workspace_id, timeframe, scope_filter, tenant_ctx) -> MetricsResult`. Orchestriert den Ablauf sequenziell.
- **`ParallelSourceFetcher` (Klasse):** Async/Concurrent-Wrapper für die vier Quell-Abfragen. Nutzt asyncio.gather() oder Executor.
- **`MetricsResultBuilder` (Klasse):** Assembliert MetricsResult aus Calculator-Ergebnissen und Warnings.

### 2.2 Datenstrukturen

- **`MetricsSourceData` (Dataclass):** {audit_entries, coverage_data, incomplete_states, risk_artifacts}.
- **`MetricsResult` (Pydantic Model):** {workspace_id, computed_at (UTC), timeframe, volatility, traceability_coverage, workflow_gaps, open_risks, warnings}.
- **`PartialMetricsResult` (Dataclass):** Bei einzelnem Source-Fehler: {failed_category: "volatility"|"coverage"|..., error_message, partial_metrics}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SM002-001 (Parallele Quell-Abfragen) | ParallelSourceFetcher startet 4 Abfragen konkurrent via asyncio.gather() oder ThreadPoolExecutor. Blockiert bis alle 4 zurück oder Timeout. Bei 3 von 4 erfolgreich: Partial MetricsResult. Bei < 3: HTTP 503. |
| REQ-L3-SM002-002 (MetricsResult-Assemblierung) | MetricsResultBuilder baut {volatility, traceability_coverage, workflow_gaps, open_risks, warnings, computed_at (UTC), timeframe}. Alle 4 Kategorien befüllt von Calculators oder null bei Fehler. |
| REQ-L3-SM002-003 (Strikte Read-Only) | Keine Write-Operationen auf IF-L1-044..047. Integration-Tests bestätigen: vor/nach Aggregator-Aufruf keine Datenbank-Mutationen. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-SM-INT-001:** Von COMP-SM-001 (MetricsQueryController): `compute(workspace_id, timeframe, scope_filter, tenant_ctx) -> MetricsResult`.
- **IF-SM-INT-009:** Von COMP-SM-009 (CeleryMetricsBeatWorker): `compute(workspace_id, timeframe, scope_filter=None, tenant_ctx=SystemCtx) -> MetricsResult` (Async-Anruf).

**Ausgänge (Outbound):**
- **IF-L1-044:** Zu AuditLog: `query_changes(workspace_id, timeframe)`.
- **IF-L1-045:** Zu TraceabilityEngine: `coverage(workspace_id)`.
- **IF-L1-046:** Zu WorkflowEngine: `find_incomplete_states(workspace_id)`.
- **IF-L1-047:** Zu ApplicationService: `query_risks_by_severity(workspace_id)`.
- **IF-SM-INT-002:** Zu COMP-SM-003 (VolatilityCalculator): `calculate(audit_entries, timeframe) -> VolatilityResult`.
- **IF-SM-INT-003:** Zu COMP-SM-004 (CoverageCalculator): `calculate(coverage_data) -> CoverageResult`.
- **IF-SM-INT-004:** Zu COMP-SM-005 (WorkflowGapDetector): `detect(incomplete_states) -> WorkflowGapResult`.
- **IF-SM-INT-005:** Zu COMP-SM-006 (RiskClassifier): `classify(risk_artifacts) -> RiskResult`.
- **IF-SM-INT-006:** Zu COMP-SM-007 (ThresholdEvaluator): `evaluate(metrics_result, workspace_id) -> list[Warning]`.

---

## 5. Architectural Rationale

**ADR-L3-SM2-01 — Parallele Quell-Abfragen mit Graceful Degradation**

*Entscheidung:* ParallelSourceFetcher startet alle 4 Abfragen gleichzeitig (asyncio.gather()). Bei 3/4 Erfolg: Partial MetricsResult. Bei < 3: HTTP 503.

*Rationale:* Erfüllt REQ-L3-SM002-001 ("Single source failure with three successful → partial MetricsResult"). Verhindert Cascading-Fehler. Timeouts sind konfigurierbar. Alternative: Sequenzielle Abfragen → würde 4x länger dauern (violiert Performance-SLA ≤ 500ms).

---

**ADR-L3-SM2-02 — Calculator-Delegation, nicht In-Line-Berechnung**

*Entscheidung:* Berechnungen (Volatility, Coverage, etc.) sind in separaten Komponenten (COMP-SM-003..006), nicht inline in Aggregator.

*Rationale:* Erfüllt Single-Responsibility-Prinzip. Ermöglicht Unit-Tests und Wiederverwendung. Alternative: Alle Logik in Aggregator → würde Komponente zu komplexe machen.

---

**ADR-L3-SM2-03 — Strict Read-Only auf Source-Interfaces**

*Entscheidung:* Signatur aller Source-Interfaces (IF-L1-044..047) nur Read-Operationen. Keine Write-Methoden verfügbar.

*Rationale:* Erfüllt REQ-L3-SM002-003 ("Before and after compute() call: requirement count, trace link count, workflow state count ... unchanged"). Strukturell erzwungen durch Interface-Design, nicht per Honor-System.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
