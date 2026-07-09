# Deep Audit: Test Coverage für SeMetricsSystem

Dieses Dokument ist ein detaillierter Audit der Testabdeckung für das `SeMetricsSystem` im Projekt ReqFlow. Es vergleicht die Implementierung in `backend/se_metrics/tests/` Zeile für Zeile mit den Anforderungen aus `L2_SeMetricsSystem_Requirements.md`.

## Allgemeine Erkenntnisse (General Findings)
Das Test-Setup leidet unter einem systematischen **Shallow-Testing-Anti-Pattern**. Die Geschäftslogik, Caching-Ebenen und HTTP-Schnittstellen sind vollständig durch Mocks (`@patch`, `MagicMock`) und Fake-Dataclasses isoliert. Es gibt keine echten Integrationstests, welche die tatsächliche Datenbankinteraktion oder das reelle JSON-Rendering des REST-Endpunkts mit echten Kern-Entitäten überprüfen.

Außerdem fehlen Tests für wichtige nicht-funktionale Akzeptanzkriterien völlig:
- **Fehlende E2E-Integration:** Niemals wird ein HTTP-Request (`GET /metrics/workspace/{id}`) auf echte DB-Daten (Requirements, TraceLinks) angewandt.
- **Seiteneffektfreiheit (REQ-L2-SM-008):** Das Kriterium verlangt explizit einen Integrationstest, der den Zustand der Kern-Entitäten vor und nach dem API-Call vergleicht. Dieser existiert nicht.
- **Celery-Beat Job (REQ-L2-SM-009):** Der geforderte proaktive Caching-Job (alle 15 Minuten) wird nicht getestet.
- **Performance SLA (REQ-L2-SM-011):** Es fehlt ein Lasttest (10.000 Requirements ≤ 500ms).

---

## Detaillierte Test-Analyse (Datei für Datei)

### 1. Datei: `test_aggregator.py`

#### Hilfsfunktionen: `TestParseTimeframeDays`
(Tests: `test_p30d`, `test_p7d`, `test_p90d`, `test_invalid_falls_back_to_30`, `test_none_falls_back_to_30`, `test_p1y_falls_back_to_30`)
- **REQ-L2 ID:** REQ-L2-SM-002
- **Aktuelles Verhalten:** Testet lediglich die Utility-Funktion zur Regex-Zahlenextraktion isoliert (Unit-Test).
- **Akzeptanzkriterium:** Query-Parameter `?timeframe=...` am Metrik-Endpunkt sollen die Berechnung auf den Zeitraum beschränken oder Fallbacks nutzen.
- **Refactoring-Bedarf:** Die isolierten Tests können erhalten bleiben, aber es MUSS ein echter Aggregator-Test hinzugefügt werden, der AuditLog-Einträge mit unterschiedlichen Zeitstempeln (z.B. alt vs. neu) in eine echte Test-DB schreibt und validiert, dass der Zeitraum-Filter auf Query-Ebene korrekt appliziert wird.

#### Klasse: `TestMetricsAggregator`
(Tests: `test_compute_returns_all_four_metric_categories`, `test_default_timeframe_applied`, `test_audit_source_failure_returns_empty_volatility`, `test_threshold_warnings_generated`, `test_result_has_workspace_id_and_timeframe`, `test_to_dict_contains_all_required_fields`, `test_no_threshold_config_no_warnings`)
- **REQ-L2 ID:** REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-007, REQ-L2-SM-008, REQ-L2-SM-012
- **Aktuelles Verhalten (Shallow?):** Extrem shallow. Die vier Datenquellen (`_fetch_risks`, `_fetch_incomplete_states`, `_fetch_coverage`, `_fetch_audit_entries`) werden zu 100% via `@patch` gemockt. Es werden nur Fake-Daten in Dataclasses gesteckt und geprüft, ob die Datentypen der Ausgabe stimmen.
- **Akzeptanzkriterium:** Echtes JSON-Format mit echten berechneten Werten. Konfigurierbare Schwellwerte generieren `warnings`. 
- **Refactoring-Bedarf:** Alle `@patch`-Dekoratoren müssen entfernt werden. Der Test muss echte `Requirement`-, `TraceLink`- und `AuditLog`-Instanzen per Django ORM (oder FactoryBoy) in der Test-DB erzeugen. Anschließend muss `agg.compute()` aufgerufen werden, um sicherzustellen, dass die ORM-Queries der Aggregatoren fehlerfrei auf echten Datenbanktabellen funktionieren.

---

### 2. Datei: `test_cache.py`

#### Klasse: `TestMetricsCacheManagerDeserialization`
(Tests: `test_roundtrip_serialize_deserialize`, `test_deserialize_bad_json_returns_none`, `test_roundtrip_with_warnings`)
- **REQ-L2 ID:** REQ-L2-SM-009
- **Aktuelles Verhalten:** Prüft In-Memory die Serialization von Dataclasses nach JSON und zurück. Ist als reiner Unit-Test in Ordnung, aber deckt kein echtes Caching ab.
- **Akzeptanzkriterium:** Ergebnisse sollen optional materialisiert werden.
- **Refactoring-Bedarf:** Keiner für diese spezifischen Methoden, aber sie sind nicht hinreichend für die Anforderung.

#### Klasse: `TestThunderingHerdLock`
(Tests: `test_lock_acquire_and_release`, `test_second_acquire_blocked_by_first`, `test_release_unheld_lock_does_not_raise`)
- **REQ-L2 ID:** REQ-L2-SM-013
- **Aktuelles Verhalten (Shallow?):** Nutzt Pythons lokales `threading`-Modul, um zu testen, ob ein Lock gehalten wird. Das AC fordert aber explizit einen "distributed Lock-Mechanismus (z.B. Redis-Lock)".
- **Akzeptanzkriterium:** Bei einem Cache-Miss darf nur exakt EINE Celery-Task (via Lock) ausgelöst werden; 49 andere Requests warten.
- **Refactoring-Bedarf:** Der Test muss einen echten oder mockbaren Redis-basierten Distributed-Lock verwenden. Es muss simuliert werden, dass mehrere HTTP-Clients (oder Threads) den Service `compute_metrics` aufrufen, und es muss per Counter (z.B. durch Mocking der Celery `.delay()` Funktion) bewiesen werden, dass exakt EINE Aggregation gestartet wird und alle anderen den Lock respektieren.

#### Klasse: `TestMetricsCacheManagerWithDb`
- **REQ-L2 ID:** REQ-L2-SM-007, REQ-L2-SM-009
- **Aktuelles Verhalten (Shallow?):** Testet DB-Inserts für `MetricCache` und `ThresholdConfig`. Dies ist der einzige Testbereich, der die DB nutzt. Allerdings wird die Cache-Invalidierung (REQ-L2-SM-009) isoliert getestet (`mgr.invalidate(...)`), ohne den Auslöser (AuditLog/Requirement-Update) zu prüfen.
- **Akzeptanzkriterium:** Cache-Invalidierung SHALL bei Empfang eines Änderungsereignisses aus dem AuditLog erfolgen.
- **Refactoring-Bedarf:** Ein Integrationstest muss hinzugefügt werden: Cache befüllen -> Ein echtes Requirement im Workspace per API oder Service modifizieren -> Assert, dass der Metrik-Cache für diesen Workspace daraufhin automatisch geleert/invalidiert wurde (z.B. via Signal oder Audit-Event-Listener).

---

### 3. Datei: `test_calculators.py`

#### Alle Calculator-Klassen (`TestVolatilityCalculator`, `TestCoverageCalculator`, `TestWorkflowGapDetector`, `TestRiskClassifier`, `TestThresholdEvaluator`)
- **REQ-L2 ID:** REQ-L2-SM-003, REQ-L2-SM-004, REQ-L2-SM-005, REQ-L2-SM-006, REQ-L2-SM-007
- **Aktuelles Verhalten (Shallow?):** Alle Tests verwenden Fake-Dataclasses (`FakeAuditEntry`, `FakeCoverageReport`, `FakeRisk`) als Eingabe für die Kalkulatoren. Es handelt sich um reine Mathematik-Unit-Tests.
- **Akzeptanzkriterium:** Die Metriken basieren auf echten Datenquellen (z.B. `AuditLog` für Updates, `TraceabilityEngine` für Traces).
- **Refactoring-Bedarf:** Die Fake-Klassen müssen gelöscht werden. Die Kalkulatoren (bzw. die Services, die diese speisen) müssen anhand von echten Django-ORM-Objekten arbeiten. Bspw. `TestRiskClassifier`: Speichere echte Risk-Artefakte mit Status `Closed` und `Identified` in die DB, rufe den Classifier oder die Fetch-Methode auf, und verifiziere, dass die Query "Closed" ignoriert und nur "Identified" zählt. Nur so wird sichergestellt, dass die ORM-Queries stimmen.

---

### 4. Datei: `test_services.py`

#### Klasse: `TestComputeMetricsCachePath`
- **REQ-L2 ID:** REQ-L2-SM-002, REQ-L2-SM-009, REQ-L2-SM-013
- **Aktuelles Verhalten (Shallow?):** Totalausfall durch Mocks. Sowohl der `MetricsCacheManager` als auch der `MetricsAggregator` werden per `@patch` ausgetauscht. Der Test verifiziert lediglich, ob die Service-Methode die gemockten Methoden aufruft.
- **Akzeptanzkriterium:** Wiederholte Aufrufe -> Cache Hit. Cache Miss -> Live Berechnung.
- **Refactoring-Bedarf:** Mocks komplett entfernen! `compute_metrics` muss zweimal nacheinander für denselben `workspace_id` aufgerufen werden (mit echter DB im Hintergrund). Der Test muss asserten, dass beim ersten Mal reell gerechnet wird und beim zweiten Mal das exakt selbe Ergebnis wesentlich schneller (oder aus der reellen Cache-Tabelle) geliefert wird. 

---

### 5. Datei: `test_tenant_isolation.py`

#### Klassen: `TestCacheTenantIsolation`, `TestComputeMetricsTenantContext`
- **REQ-L2 ID:** REQ-L2-SM-010
- **Aktuelles Verhalten (Shallow?):** Prüft In-Memory-Verhalten von Dictionary-Schlüsseln (Cache-Keys). Mocks für den Aggregator im Service-Test.
- **Akzeptanzkriterium:** Tenant-1 ruft Workspace von Tenant-2 auf -> HTTP 403. Berechnungen enthalten nur Tenant-eigene Daten.
- **Refactoring-Bedarf:** 
  1. API-Test (via DRF `APIClient`): Login als User von Tenant A. GET-Request auf Workspace von Tenant B -> Erwarte HTTP 403 Forbidden (im Test ist dies momentan nicht abgedeckt, da nur die Service-Schicht gemockt aufgerufen wird).
  2. Daten-Isolation: Erstelle Requirements für Tenant A und Tenant B in der DB. Fordere Metriken für Tenant A an und assertiere strikt, dass die Metrik-Zahlen ausschließlich Objekte von Tenant A enthalten.

---

### 6. Datei: `test_views.py`

#### Klasse: `TestWorkspaceMetricsView` & `TestWorkspaceThresholdView`
- **REQ-L2 ID:** REQ-L2-SM-001, REQ-L2-SM-002, REQ-L2-SM-007, REQ-L2-SM-012
- **Aktuelles Verhalten (Shallow?):** Die Sichten (Views) testen zwar grundlegende HTTP-Fehlercodes (401, 400), der **Happy-Path (200 OK)** patcht jedoch den kompletten `compute_metrics` Service (`@patch("se_metrics.views.compute_metrics")`). Dadurch wird niemals getestet, ob die REST-Serialisierung echter Datenbank-Ergebnisse in das verlangte JSON-Format fehlerfrei funktioniert.
- **Akzeptanzkriterium:** HTTP 200 + strukturiertes, versioniertes JSON mit exakt 8 Pflicht-Feldern auf Basis echter Workspace-Daten.
- **Refactoring-Bedarf:** 
  1. `@patch` beim Happy-Path (`test_returns_200_with_valid_request`) entfernen.
  2. Testdatenbank mit 1-2 echten Requirements und Traces initialisieren.
  3. `GET /metrics/workspace/{id}/` als authentifizierter API-Request absetzen.
  4. Die HTTP-Antwort in JSON parsen und tiefgehend prüfen, dass das Format den OpenAPI/L2-Vorgaben entspricht und korrekte echte Berechnungen enthält.
  5. Für den PUT-Endpunkt (Thresholds) ohne Mocks echte Configs schreiben und per folgendem GET direkt im Anschluss auslesen, um End-to-End Persistenz zu beweisen.

---

### 7. Kritische Lücken (Fehlende Tests, die implementiert werden müssen)

1. **REQ-L2-SM-008 (Seiteneffektfreiheit):** 
   - *Bedarf:* Ein E2E-Test, der die exakte Anzahl von AuditLog-Einträgen, Requirements und TraceLinks VOR dem Aufruf von `GET /metrics/workspace/{id}` zählt, den Endpunkt aufruft, und danach sicherstellt, dass die Zähler identisch sind (keine Mutationen).
2. **REQ-L2-SM-009 (Celery Beat):** 
   - *Bedarf:* Test, der sicherstellt, dass die Celery-Beat-Task existiert, fehlerfrei getriggert werden kann und den Cache für aktive Workspaces aufwärmt.
3. **REQ-L2-SM-011 (Performance SLA):** 
   - *Bedarf:* Ein expliziter Lasttest (z.B. mit `pytest-benchmark`), der 10.000 generierte Requirements in die DB schreibt und sicherstellt, dass `compute_metrics` (ohne Cache) die Ausführungszeit von ≤ 500ms nicht überschreitet.

---
*Erstellt durch Antigravity (se-validator Rolle) | ReqFlow SE-Kaskade Audit*
