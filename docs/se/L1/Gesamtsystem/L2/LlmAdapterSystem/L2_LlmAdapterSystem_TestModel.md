# L2 LlmAdapterSystem Test Model

> **Level:** L2 (Subsystem)
> **System:** LlmAdapterSystem (ARCH-L1-009)
> **Parent Architecture:** L2_LlmAdapterSystem_Architecture.md
> **Status:** entworfen

---

## 1. Teststrategie

Die Teststrategie für das `LlmAdapterSystem` fokussiert sich auf die funktionale Korrektheit des internen Routings, die korrekte asynchrone Entkopplung von Langläufer-Tasks und die Einbindung der Resilienz-Schicht.

**Kernaspekte:**
- **Mocking externer Abhängigkeiten:** Externe Systeme wie der `ResilienceOrchestrator` (IF-L1-050), das `AuditLog` (IF-LA-EXT-OUT-002) und die `Celery-Task-Queue` (IF-LA-EXT-OUT-003) werden in den Integrationstests als Mocks bereitgestellt, um das System isoliert prüfen zu können.
- **Provider-Abstraktion prüfen:** Die `ProviderRegistry` muss ohne echte HTTPS-Aufrufe getestet werden können. Mocks auf Ebene des `ResilienceOrchestrators` stellen die simulierten LLM-Antworten bereit.
- **Synchrones vs. Asynchrones Verhalten:** Es wird stark unterschieden zwischen synchronen (z. B. `validate_artifact`) und asynchronen (z. B. `decompose_requirement`, `check_consistency`) Workflows. Das Systemverhalten bzgl. der `task_id`-Vergabe muss deterministisch validiert werden.

---

## 2. Strukturelle Schnittstellentests (Interface Tests)

Diese Tests prüfen ausschließlich die Verträge (Contracts) der Schnittstellen, unabhängig von der Geschäftslogik.

### 2.1 Externe Schnittstellen
| Test-ID | Schnittstelle | Testziel / Erwartetes Verhalten |
|---------|---------------|---------------------------------|
| TEST-IF-EXT-01 | IF-LA-EXT-IN-001 | Aufruf von `execute_capability(capability_name, **kwargs)` mit gültigen/ungültigen Typen akzeptieren bzw. ablehnen. |
| TEST-IF-EXT-02 | IF-L1-050 | `ProviderRegistry` übergibt sauber formatierte API-Requests an den `ResilienceOrchestrator` und kann dessen Responses parsen. |
| TEST-IF-EXT-03 | IF-LA-EXT-OUT-002 | `LlmAuditLogger` generiert gültige Python-Datenstrukturen, die vom in-process `AuditLog` akzeptiert werden. |
| TEST-IF-EXT-04 | IF-LA-EXT-OUT-003 | `AsyncTaskDispatcher` ruft `dispatch_task` mit korrekter Signatur auf und extrahiert die zurückgegebene `task_id`. Aufruf von `get_task_status` funktioniert. |

### 2.2 Interne Schnittstellen
| Test-ID | Schnittstelle | Testziel / Erwartetes Verhalten |
|---------|---------------|---------------------------------|
| TEST-IF-INT-01 | IF-LA-INT-001 | `CapabilityRouter` interagiert typensicher mit dem `CapabilityInterface`. |
| TEST-IF-INT-02 | IF-LA-INT-002 | `ProviderRegistry` liefert eine gueltige Instanz, die `LlmCapabilityInterface` implementiert. |
| TEST-IF-INT-03 | IF-LA-INT-003 | Vererbung und Klassenimplementierung sicherstellen: Provider setzen `validate_artifact`, `decompose_requirement` um. |
| TEST-IF-INT-04 | IF-LA-INT-004 | Aufruf zur Protokollierung (`log_llm_call`) überträgt Erfolgsstatus und Fehlerstrukturen an den Logger. |
| TEST-IF-INT-05 | IF-LA-INT-005 | Asynchrones Dispatching liefert stringbasierte/UUID `task_id` und blockiert den Caller nicht. |

---

## 3. Testdesign: BVA, Äquivalenzklassen & Edge-Cases

### 3.1 Grenzwertanalyse (Boundary Value Analysis - BVA)
- **Token-Limits:** Testen des Verhaltens bei Eingaben knapp unter, exakt auf und über dem maximalen Token-Limit des konfigurierten LLM-Providers.
- **Payload-Größe:** Leere Payloads (0 Bytes) sowie extrem große Eingaben (z. B. >10MB Texte) validieren.
- **Timeouts:** Antworten knapp unterhalb und oberhalb des festgelegten Timeout-Schwellenwerts beim `ResilienceOrchestrator`.

### 3.2 Äquivalenzklassen
- **Client-Fehler (4xx):** Invalid Token, Bad Request (Fehler beim Client, kein Retry sinnvoll).
- **Server-Fehler (5xx):** Interne Provider-Ausfälle, Overload (Retry durch `ResilienceOrchestrator` auslösen).
- **Rate Limits (HTTP 429):** Spezifische Behandlung von Throttling am `ResilienceOrchestrator` prüfen.

### 3.3 Edge-Cases
- **Leere LLM Antworten:** Provider meldet HTTP 200, liefert aber einen leeren String in der Completion.
- **Malformed JSON:** Das LLM liefert kein valides JSON für strukturierte Fähigkeiten wie `decompose_requirement` zurück.
- **Circuit Breaker Open:** Schnelles Fail-Fast-Szenario prüfen, wenn der `ResilienceOrchestrator` in den Open-Status geht (Fehlerzustände gezielt abdecken).
- **Celery Ausfall:** `AsyncTaskDispatcher` kann keine Verbindung zur Queue aufbauen (Task-Submission schlägt fehl).

---

## 4. Komponententests

Die internen Komponenten (White-Box) werden isoliert auf ihr Verhalten getestet.

### COMP-LA-001: CapabilityInterface
- **TEST-C001-01 (Data Classes):** Instanziierung von `LlmResult`, `LlmDecompositionResult` und `LlmConsistencyResult` prüfen. Typensicherheit und Defaults sicherstellen.
- **TEST-C001-02 (Interface Contract):** Sicherstellen, dass abgeleitete Provider-Klassen zwingend die Methoden `validate_artifact`, `decompose_requirement` und `check_consistency` implementieren (z. B. via abc.ABC).

### COMP-LA-002: ProviderRegistry
- **TEST-C002-01 (Provider Selection):** Auswahl des korrekten Providers basierend auf Mock-Environment-Variablen (z. B. OpenAI vs. Anthropic).
- **TEST-C002-02 (Routing to Orchestrator):** Provider-Implementierungen rufen für ausgehende Requests ausschließlich IF-L1-050 (ResilienceOrchestrator) auf, direkte HTTP-Calls (requests.post etc.) sind nicht vorhanden/erlaubt.

### COMP-LA-003: CapabilityRouter
- **TEST-C003-01 (Sync Routing):** Aufruf von `validate_artifact` wird synchron zur Registry weitergeleitet.
- **TEST-C003-02 (Async Routing):** Aufruf von `decompose_requirement` wird an den `AsyncTaskDispatcher` übergeben.
- **TEST-C003-03 (Graceful Degradation):** Wenn die `ProviderRegistry` keinen konfigurierten Provider findet, fängt der Router dies ab und liefert ein fehlerhaftes, aber valides strukturiertes Ergebnis zurück.

### COMP-LA-004: LlmAuditLogger
- **TEST-C004-01 (Token Tracking):** Extrahierte Token-Verbräuche (Prompt vs. Completion) werden akkumuliert und im Log-Eintrag persistiert.
- **TEST-C004-02 (Failure Logging):** Bei einem gescheiterten LLM-Request wird der Fehlergrund vollständig (aber ohne sensible Header/Keys) in das AuditLog übertragen.

### COMP-LA-005: AsyncTaskDispatcher
- **TEST-C005-01 (Dispatch):** Übergabe einer Capability und der Argumente an den Celery-Mock erzeugt eine erwartete Aufruf-Signatur in der Queue.
- **TEST-C005-02 (Status Retrieval):** Funktion `get_task_status(task_id)` nutzt deterministische Task-Mocks (ohne `sleep` oder Polling-Flakiness) zur synchronen Status-Auswertung des simulierten Task-Backends (`Pending`, `Success` oder `Failed`).

---

## 5. Integrationstests (Verhaltens- / Szenario-Tests)

Diese Tests validieren das Zusammenwirken der 5 Komponenten des `LlmAdapterSystems`.

### Szenario 1: Erfolgreiche synchrone Validation (validate_artifact)
- **Aktion:** `ApplicationService` ruft `execute_capability('validate_artifact', ...)` auf.
- **Erwartet:**
  1. `CapabilityRouter` verarbeitet den Request.
  2. Ruft synchron die `ProviderRegistry` auf.
  3. `ResilienceOrchestrator` (Mock) liefert Erfolgsergebnis.
  4. `LlmAuditLogger` loggt das Ergebnis inkl. Tokens.
  5. Der Router liefert das finale `LlmResult` an den Aufrufer zurück.

### Szenario 2: Erfolgreiche asynchrone Decomposition (decompose_requirement)
- **Aktion:** `ApplicationService` ruft `execute_capability('decompose_requirement', ...)` auf.
- **Erwartet:**
  1. `CapabilityRouter` erkennt die Capability als Langläufer.
  2. Leitet den Call an den `AsyncTaskDispatcher` weiter.
  3. Dispatcher gibt sofort eine simulierte `task_id` zurück.
  4. Der Router gibt ein Antwort-Objekt zurück, das signalisiert: `Async Task gestartet mit ID xyz`.
  5. (Sub-Test) Ein späterer Aufruf von `get_task_status('xyz')` liefert das finale `LlmDecompositionResult`.

### Szenario 3: Fehlerbehandlung bei externem LLM-Ausfall
- **Aktion:** Synchrone oder asynchrone Ausführung, während der `ResilienceOrchestrator` (Mock) einen finalen Fehler (z. B. HTTP 503 nach Retries) zurückmeldet.
- **Erwartet:**
  1. Provider-Modul fängt die Exception nicht, bzw. transformiert sie in einen LLM-Error.
  2. Router (oder Dispatcher) übersetzt dies in ein geordnetes Fehlerszenario.
  3. `LlmAuditLogger` verbucht den Request als gescheitert.
  4. Dem Aufrufer wird nicht das System zum Absturz gebracht, sondern er erhält ein Ergebnisobjekt mit `status="failed"` und klarer Fehlermeldung.

---

## 6. Traceability Matrix

| Test-ID / Szenario | Abgedeckte REQ-L2 |
|--------------------|-------------------|
| TEST-C001-* | REQ-L2-LA-001, REQ-L2-LA-004 |
| TEST-C002-* | REQ-L2-LA-001, REQ-L2-LA-005, REQ-L2-LA-007 |
| TEST-C003-* | REQ-L2-LA-002, REQ-L2-LA-003, REQ-L2-LA-005 |
| TEST-C004-* | REQ-L2-LA-006 |
| TEST-C005-* | REQ-L2-LA-008 |
| Szenario 1 | REQ-L2-LA-001, REQ-L2-LA-002, REQ-L2-LA-006, REQ-L2-LA-007 |
| Szenario 2 | REQ-L2-LA-003, REQ-L2-LA-008 |
| Szenario 3 | REQ-L2-LA-002, REQ-L2-LA-005, REQ-L2-LA-006 |

---

*Erstellt durch se-test-engineer-Agent | ReqFlow SE-Kaskade*
