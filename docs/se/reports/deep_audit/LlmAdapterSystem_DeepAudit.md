# Deep Test-Coverage Audit: LlmAdapterSystem

**Datum:** 2026-07-09
**System:** LlmAdapterSystem (ARCH-L1-009)

## Management Summary
Der aktuelle Testbestand in `backend/llm_adapter/tests/test_llm_adapter.py` zeichnet sich durch extensives Mocking aus. Viele Tests prüfen lediglich die Interfaces und Dataklassen oder mocken die *Methoden, die sie eigentlich testen sollten*. Echte Integrationen (Provider, Celery, Audit-Log-Datenbank) werden umgangen, was zu einem stark ausgeprägten "Shallow Testing"-Anti-Pattern führt.

---

## Detaillierte Test-Analyse (Zeile für Zeile & pro Anforderung)

### 1. `TestLlmResultDataclasses`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-004
- **Test-Namen:** `test_llm_result_valid_score_zero` bis `test_llm_consistency_result_default_issues` (Zeilen 31-99)
- **Aktuelles Verhalten (Shallow-Check):** Die Tests instanziieren lediglich die Python-Dataklassen (`LlmResult`, `LlmDecompositionResult`, etc.) direkt im Speicher und prüfen, ob die Attribute korrekt gesetzt wurden oder Validierungsfehler werfen.
- **Akzeptanzkriterium:** "Alle Provider liefern identische Datenklassen-Struktur"
- **Refactoring-Bedarf:** Das Instanziieren von Dataklassen zu testen ist trivial und oberflächlich. Um die Akzeptanzkriterien wirklich zu prüfen, müssen Tests geschrieben werden, die die *echten* Provider (`OpenAiProvider`, `AnthropicProvider`, etc.) mit gemockten HTTP-Responses aufrufen und verifizieren, dass diese Provider korrekte `LlmResult`-Instanzen zurückgeben.

### 2. `TestLlmCapabilityInterface`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-001
- **Test-Namen:** `test_cannot_instantiate_directly`, `test_incomplete_subclass_raises_on_instantiation`, `test_complete_subclass_instantiates` (Zeilen 101-140)
- **Aktuelles Verhalten (Shallow-Check):** Prüft lediglich die Standard-Funktionalität des Python `abc`-Moduls (Abstract Base Classes), indem lokale Dummy-Klassen abgeleitet werden. 
- **Akzeptanzkriterium:** Provider-Implementierungen sollen über ein Interface austauschbar sein.
- **Refactoring-Bedarf:** Python's Sprachfeatures (`abc`) müssen nicht getestet werden. Stattdessen müssen die tatsächlichen Provider (`AnthropicProvider`, `OpenAiProvider`, `OllamaProvider`) importiert und daraufhin überprüft werden, ob sie das Interface `LlmCapabilityInterface` korrekt implementieren und instanziierbar sind.

### 3. `TestProviderRegistry` & `TestMockLlmProvider`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-001
- **Test-Namen:** `test_mock_provider_returned_when_set` bis `test_mock_provider_has_stable_results` (Zeilen 146-264)
- **Aktuelles Verhalten (Shallow-Check):** Die Registry wird nur mit dem `MockLlmProvider` und Custom-Mock-Providern getestet. Die echten Provider (OpenAI, Anthropic, Ollama) werden ignoriert.
- **Akzeptanzkriterium:** "Provider-Wechsel via `.env` ohne Code-Änderung" für Anthropic, OpenAI, Ollama.
- **Refactoring-Bedarf:** Es müssen Tests hinzugefügt werden, die `LLM_PROVIDER=openai`, `LLM_PROVIDER=anthropic` und `LLM_PROVIDER=ollama` in die Umgebungsvariablen setzen und verifizieren, dass `get_provider()` die entsprechenden korrekten System-Klassen (und nicht den Mock) zurückgibt.

### 4. `TestCapabilityRouterGracefulDegradation`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-002, REQ-L2-LA-003
- **Test-Namen:** `test_no_provider_returns_not_configured` bis `test_no_exception_escapes_router` (Zeilen 270-325)
- **Aktuelles Verhalten (Shallow-Check):** Ziemlich solide für die reine Konfigurations-Logik.
- **Akzeptanzkriterium:** "LLM-Provider nicht erreichbar -> gleicher strukturierter Fehler" (`LLM_NOT_CONFIGURED` oder `LLM_PROVIDER_ERROR`).
- **Refactoring-Bedarf:** Ein Testfall muss ergänzt werden, der einen konfigurierten Provider simuliert, bei dem der echte HTTP-Verbindungsaufbau fehlschlägt (z.B. Connection Refused / Timeout vor dem Senden), um zu verifizieren, dass die Applikation nicht crasht und den strukturierten Fehler zurückgibt.

### 5. `TestCapabilityRouterSyncExecution`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-005
- **Test-Namen:** `test_provider_error_returns_provider_error_code`, `test_timeout_error_returns_timed_out`, `test_rate_limit_message` (Zeilen 327-395)
- **Aktuelles Verhalten (Shallow-Check):** Es wird lediglich die Methode `get_provider()` gemockt, sodass sie globale Python-Exceptions wirft. Das testet nur den try-except-Block im `CapabilityRouter`.
- **Akzeptanzkriterium:** Provider-Fehler (Timeout, API-Error, Rate-Limit) als strukturierter Fehler, konfigurierbares Timeout.
- **Refactoring-Bedarf:** Die echten Provider müssen via `httpx` / `requests` Mocks (z.B. `respx` oder `responses`) so getestet werden, dass echte HTTP 500, HTTP 429 oder ReadTimeouts vom Provider-Client geworfen werden. Zudem fehlt die Test-Überprüfung der Celery-Timeouts (`CELERY_TASK_SOFT_TIME_LIMIT`).

### 6. `TestLlmAuditLogger` & `TestTokenExtraction`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-006
- **Test-Namen:** `test_log_llm_call_calls_log_write` bis `test_returns_none_when_usage_attribute_missing` (Zeilen 462-612)
- **Aktuelles Verhalten (Shallow-Check):** Extrem flach! Der Test `test_log_llm_call_calls_log_write` mockt die Methode `log_llm_call` direkt auf dem Objekt, das er testen soll, und prüft, ob der Methodenaufruf ausgeführt wurde. Das testet absolut keine Logik. Die Token-Tests mocken zudem nur rohe Dictionaries.
- **Akzeptanzkriterium:** Erfolgreicher/Fehlgeschlagener Aufruf -> AuditLog Eintrag (Datenbank).
- **Refactoring-Bedarf:** Der Patch auf `log_llm_call` muss entfernt werden. Stattdessen muss die zugrundeliegende Abhängigkeit (z.B. der DB-Service `audit.services.log_write`) gemockt werden. Der Test muss verifizieren, dass dieser Service mit den exakten Payloads (`provider`, `capability`, `token_usage`, `success`) aus dem AuditLogger heraus aufgerufen wird.

### 7. Fehlende Provider Tests (`AzureOpenAiProvider`)
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-007
- **Test-Namen:** N/A (Fehlen komplett)
- **Aktuelles Verhalten (Shallow-Check):** Anforderung ist im Requirements-Dokument als "Missing" markiert.
- **Akzeptanzkriterium:** `LLM_PROVIDER=azure` -> `AzureOpenAiProvider`-Instanz, Azure-spezifische Konfiguration wird verarbeitet.
- **Refactoring-Bedarf:** Neue Testklasse anlegen, die das Setup, die Konfiguration (Endpoint, Deployment-Name, API-Version) und die Ausführung des Azure-Providers verifiziert.

### 8. `TestAsyncTaskDispatcher`
- **Verknüpfte REQ-L2 ID:** REQ-L2-LA-008
- **Test-Namen:** `test_dispatch_async_returns_error_when_no_broker` bis `test_dispatch_async_with_mock_celery` (Zeilen 618-670)
- **Aktuelles Verhalten (Shallow-Check):** Die gesamte Celery-Infrastruktur wird weggemockt (`_get_celery_app`, `_make_task`). Geprüft wird nur, ob `apply_async` auf einem MagicMock ausgeführt wurde.
- **Akzeptanzkriterium:** Status-Abfrage via `task.status(task_id)` liefert reale Zustände (`pending`, `running`, `done`, `failed`).
- **Refactoring-Bedarf:** Echte Status-Übergänge werden nicht geprüft. Die Tests sollten den Celery Eager-Modus (`task_always_eager=True`) verwenden oder einen echten In-Memory-Worker konfigurieren, um zu garantieren, dass die Tasks bei Übergabe an Celery korrekt decodiert, ausgeführt und deren Results aus dem Broker/Backend abrufbar sind.

### 9. `TestServiceFacade` & `TestEndToEndWithMockProvider`
- **Verknüpfte REQ-L2 ID:** Übergreifend
- **Test-Namen:** Zeilen 676-787
- **Aktuelles Verhalten (Shallow-Check):** Verifizieren lediglich, dass die Fassaden-Funktionen in `services.py` korrekt an den Router delegieren, wieder nur mit dem `MockLlmProvider`.
- **Refactoring-Bedarf:** Für sinnvolle Integrationstests müssen echte Provider zusammen mit dem Router und dem Celery-Dispatcher (ohne exzessives Mocking der internen Klassen) in einem durchgehenden Datenfluss getestet werden, bei dem lediglich der finale ausgehende HTTP-Request ans LLM gemockt wird.
