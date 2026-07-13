# L3 MetricsQueryController Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-SM-001 — MetricsQueryController
> **Parent-System:** SeMetricsSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

REST-Endpunkt-Adapter: empfängt `GET /metrics/workspace/{id}`, validiert Bearer Token (401), prüft workspace_id-Existenz (404), führt Tenant-Isolation-Check durch (403), parst und validiert `timeframe`- und `scope_filter`-Parameter (400), koordiniert MetricsAggregator und serialisiert die JSON-Antwort nach stabilem Format.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-SM-001 | REST-Endpunkt GET /metrics/workspace/{id} mit vollständigem JSON-Metrikbericht |
| REQ-L2-SM-002 | Zeitraum- und Scope-Filter (timeframe, scope_filter) |
| REQ-L2-SM-010 | Tenant-Isolation für alle Metrik-Abfragen |
| REQ-L2-SM-012 | Strukturiertes stabiles JSON-Antwortformat |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-SM-INT-001 | ausgehend | COMP-SM-002 MetricsAggregator | `compute(workspace_id, timeframe, scope_filter, tenant_ctx) -> MetricsResult` |
| IF-SM-INT-008 | ausgehend | COMP-SM-008 MetricsCacheManager | `get_cached(workspace_id, timeframe) -> MetricsResult \| None` und `put_cached(workspace_id, timeframe, result)` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-L1-042 | eingehend | RestApiAdapter | `GET /metrics/workspace/{id}` — Haupt-Request-Eingang |
| IF-L1-043 | eingehend | ReactFrontend (via RestApiAdapter) | Dashboard-Datenabruf — identischer Endpunkt, unterschiedlicher Aufrufer |

---

## L3 Komponenten-Anforderungen

### REQ-L3-SM001-001: HTTP-Authentifizierung und Workspace-Zugriffskontrolle


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsQueryController SHALL jeden eingehenden Request auf `GET /metrics/workspace/{id}` vor jeder Verarbeitung auf Authentizität und Autorisierung prüfen: (1) Fehlendes oder ungültiges Bearer Token → HTTP 401, (2) Gültiger Token, aber `workspace_id` nicht existent → HTTP 404, (3) Gültiger Token und Workspace existent, aber Tenant-Kontext des Aufrufers schließt Zugriff aus → HTTP 403. Erst nach erfolgreicher Prüfung aller drei Bedingungen SHALL die Anfrage an COMP-SM-002 delegiert werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Request without Authorization header → HTTP 401, no backend call triggered
- [ ] Request with invalid token → HTTP 401, no backend call triggered
- [ ] Valid token, non-existent workspace_id → HTTP 404
- [ ] Valid token, workspace exists, requester belongs to different tenant → HTTP 403
- [ ] Valid token, workspace exists, correct tenant → request delegated to MetricsAggregator

---

### REQ-L3-SM001-002: Parameter-Parsing und Validierung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsQueryController SHALL die Query-Parameter `timeframe` (ISO-8601-Zeitraum) und `scope_filter` (kommaseparierte Artefakttyp-Liste) parsen und validieren. Fehlt `timeframe`, SHALL der konfigurierte Standardwert (Default: P30D) verwendet werden. Ungültige Parameter-Werte SHALL mit HTTP 400 und maschinenlesbarer Fehlermeldung abgelehnt werden, bevor eine Delegation an COMP-SM-002 erfolgt.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `?timeframe=P7D` → parsed as 7-day window, passed to MetricsAggregator
- [ ] `?timeframe=P90D` → parsed as 90-day window
- [ ] No `timeframe` parameter → default P30D applied
- [ ] `?timeframe=INVALID` → HTTP 400, `{"error": "Invalid timeframe format", "field": "timeframe"}`
- [ ] `?scope_filter=Requirement,ArchitectureElement` → list forwarded to MetricsAggregator
- [ ] No backend call on invalid parameters

---

### REQ-L3-SM001-003: JSON-Antwort-Serialisierung nach stabilem Format


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsQueryController SHALL das von COMP-SM-002 zurückgegebene `MetricsResult`-Objekt in ein stabiles JSON-Antwortformat serialisieren, das die Pflichtfelder `workspace_id`, `computed_at`, `timeframe`, `volatility`, `traceability_coverage`, `workflow_gaps`, `open_risks` und `warnings` enthält. Fehlende optionale Werte SHALL als `null` oder leere Objekte serialisiert werden. Der HTTP-Statuscode SHALL bei Erfolg immer 200 sein.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Successful response contains all eight mandatory fields
- [ ] `computed_at` is ISO-8601 timestamp
- [ ] `timeframe` reflects the applied window (including default)
- [ ] Missing optional fields serialized as `null` or `{}`, never omitted
- [ ] HTTP 200 on successful computation

---

### REQ-L3-SM001-004: Cache-Lookup vor Aggregator-Delegation


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der MetricsQueryController SHALL vor jeder Delegation an COMP-SM-002 einen Cache-Lookup via IF-SM-INT-008 (COMP-SM-008) durchführen. Bei Cache-Treffer SHALL das gecachte Ergebnis direkt serialisiert und zurückgegeben werden, ohne COMP-SM-002 aufzurufen. Bei Cache-Miss SHALL COMP-SM-002 aufgerufen und das Ergebnis nach Rückgabe via IF-SM-INT-008 in den Cache geschrieben werden. Cache-Fehler beim Lookup oder Schreiben dürfen die Antwort nicht mit HTTP 5xx abbrechen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Cache hit → response returned without calling MetricsAggregator (verifiable by mock/spy)
- [ ] Cache miss → MetricsAggregator called, result written to cache after computation
- [ ] Cache read error → request proceeds to MetricsAggregator (no HTTP 5xx)
- [ ] Cache write error → response still returned successfully (no HTTP 5xx)

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
