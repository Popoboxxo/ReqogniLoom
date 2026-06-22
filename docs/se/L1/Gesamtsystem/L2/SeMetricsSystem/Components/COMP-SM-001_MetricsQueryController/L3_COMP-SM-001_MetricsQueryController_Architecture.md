---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:25:00Z"
schema_version: "1.0.0"
---

# L3 MetricsQueryController Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-SM-001_MetricsQueryController
> **Parent:** L2_SeMetricsSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der MetricsQueryController ist der REST-API-Adapter für Metriken-Abfragen. Er empfängt GET-Requests auf `/metrics/workspace/{id}`, validiert authentifizierte Nutzer-Identität, prüft Workspace-Existenz und Tenant-Isolation, parst und validiert Query-Parameter (timeframe, scope_filter), konsultiert einen Metriken-Cache, delegiert bei Cache-Miss an MetricsAggregator und serialisiert die MetricsResult-Antwort nach stabilem JSON-Format.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`MetricsQueryController` (Klasse):** Hauptklasse mit Methode `get_metrics(workspace_id, query_params, auth_context) -> JSON_Response`.
- **`TimeframeParser` (Klasse):** Parst ISO-8601-Durationstrings (P7D, P30D, P90D). Default: P30D. Fehler → HTTP 400.
- **`ScopeFilterParser` (Klasse):** Parst kommaseparierte Artefakttyp-Liste. Validiert gegen zulässige Typen.
- **`MetricsResponseSerializer` (Klasse):** Serialisiert MetricsResult in stabiles JSON-Format.

### 2.2 Datenstrukturen

- **`MetricsQueryRequest` (Pydantic Model):** {workspace_id, timeframe, scope_filter?, auth_context}.
- **`MetricsJsonResponse` (Pydantic Model):** {workspace_id, computed_at (ISO-8601), timeframe, volatility, traceability_coverage, workflow_gaps, open_risks, warnings}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SM001-001 (HTTP Auth & Workspace Access) | Sequenzielle Checks: (1) Bearer Token vorhanden? → 401. (2) Workspace existiert? → 404. (3) Tenant-Kontext passt? → 403. Nur nach allen drei Checks: Delegation. |
| REQ-L3-SM001-002 (Parameter-Parsing) | TimeframeParser liest `?timeframe=P7D`. Default: P30D. Ungültig → HTTP 400. ScopeFilterParser liest `?scope_filter=Requirement,ArchitectureElement`. Ungültig → HTTP 400. |
| REQ-L3-SM001-003 (JSON-Serialisierung) | MetricsResponseSerializer schreibt 8 obligatorische Felder (workspace_id, computed_at, timeframe, volatility, traceability_coverage, workflow_gaps, open_risks, warnings). Fehlende optional → null oder {}. HTTP 200 bei Erfolg. |
| REQ-L3-SM001-004 (Cache-Lookup) | Vor MetricsAggregator-Aufruf: Cache-Query via IF-SM-INT-008. Hit → direktes Return. Miss → Aggregator-Aufruf, dann Cache-Schreib. Cache-Fehler blockieren nicht die Response (Fallback zu Aggregator). |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-L1-042:** GET `/metrics/workspace/{id}` von API-Clients/RestApiAdapter.
- **IF-L1-043:** GET `/metrics/workspace/{id}` von React-Frontend.

**Ausgänge (Outbound):**
- **IF-SM-INT-001:** Zu COMP-SM-002 (MetricsAggregator): `compute(workspace_id, timeframe, scope_filter, tenant_ctx) -> MetricsResult`.
- **IF-SM-INT-008:** Zu COMP-SM-008 (MetricsCacheManager): `get_cached(workspace_id, timeframe) -> MetricsResult | None` und `put_cached(workspace_id, timeframe, result)`.

---

## 5. Architectural Rationale

**ADR-L3-SM1-01 — Sequenzielle Auth-Checks vor Delegation**

*Entscheidung:* Auth/Workspace/Tenant-Checks erfolgen sequenziell und blockierend. Nur nach allen drei erfolgreich: Delegation an MetricsAggregator.

*Rationale:* Erfüllt REQ-L3-SM001-001 ("HTTP 401 ... HTTP 404 ... HTTP 403 ... only after successful prüfung"). Verhindert Informationslecks durch Reihenfolge-Abhängigkeiten. Alternative: Parallele Checks → würde Timing-Unterschiede erlauben, die Existenz einer Resource verraten.

---

**ADR-L3-SM1-02 — Timeframe-Validierung mit Default-Fallback**

*Entscheidung:* Fehlender Timeframe → Default P30D. Ungültiges Format → HTTP 400 (kein Fallback).

*Rationale:* Erfüllt REQ-L3-SM001-002 ("No timeframe parameter → default P30D applied"). Default erleichtert Client-Nutzung. Ungültiges Format ist aber nicht zu verzeihen. Alternative: Immer erforderlich → würde Client-Komplexität erhöhen.

---

**ADR-L3-SM1-03 — Cache mit Graceful-Fallback bei Fehler**

*Entscheidung:* Cache-Fehler beim Lookup oder Schreib blockieren nicht die Response. Bei Fehler: Fallback zu Aggregator-Aufruf ohne Cache-Optimierung.

*Rationale:* Erfüllt REQ-L3-SM001-004 ("Cache read error → request proceeds to MetricsAggregator (no HTTP 5xx)"). Macht Metriken-Endpunkt robust gegen Cache-Ausfälle. Alternative: Cache-Fehler → HTTP 503 → würde Verfügbarkeit gefährden.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
