---
type: REVIEW
scope: wp1b-llm-timeout-retry-errors
status: complete
date: 2026-09-29
author_agent: backend-reviewer
work_package: WP-1b
---

# WP-1b — LLM-Adapter: Timeout / Retry / Circuit-Breaker und Fehlerpfade

Alle Matrizen unten sind **live gemessen** (Probe im Backend-Container gegen
In-Process-Stub, der Statuscode/Body pro Szenario liefert und die Anzahl der
tatsächlich angekommenen HTTP-Requests zählt). `llm_adapter.resilient_transport._sleep`
wurde für die Messung auf `lambda s: None` gesetzt — die Retry-Schleife selbst
bleibt beobachtbar, nur die Wartezeit entfällt.

---

## 1. Timeout-Matrix

| Schicht | Ort | Wert | Quelle |
|---|---|---|---|
| Provider-Config-Default | `providers.py:80` | `LLM_TIMEOUT` = **30 s** | Env, Default `"30"` (`providers.py:113`) |
| Sync-Hart-Timeout (Request-Thread) | `timeouts.py:64-70` | `LLM_SYNC_TIMEOUT` = **25 s** | `settings.py:734` |
| Workspace-weite Prompts | `timeouts.py:73-84` | `LLM_LONG_RUNNING_TIMEOUT` = **180 s** | `settings.py:746-748` |
| PolicyEngine pro Versuch | `resilient_transport.py:280` | `= timeout_seconds` | pro Versuch, nicht pro Aufruf |
| Celery-Task | — | **kein Task-Zeitlimit im Adapter** | `tasks.py:77` `@shared_task(bind=True, name=...)` — **kein `time_limit`, kein `soft_time_limit`** |

**Unendlich = Fehler?** Nein, für den Sync-Pfad nicht: 25 s hart. Für den
Async-Pfad **ja**: `llm_adapter/tasks.py` setzt weder `time_limit` noch
`soft_time_limit`, und `_effective_timeout` fällt auf `ProviderConfig.timeout`
zurück, der per Env **gesetzt werden kann** — aber der Aufrufer
`AiDerivationService._complete` reicht `resolve_timeout_seconds(purpose)` nur an
`provider.complete()` durch, und `run_capability` (`tasks.py:155`) ruft
`method(**kwargs)` **ohne** Timeout-Argument. Für Celery-Capabilities
(`decompose_requirement`, `check_consistency`, `derive_requirements`,
`complete`) fällt damit **immer** der 30-s-Providerdefault wirksam, nie ein
spezifischer Wert. → `AUD-2026-09-056` Medium.

Gemessen: Verbindungs refused, `timeout=2` → **5,3 s** (4 Außenversuche ×
kurze Fehlverbindung, Backoff neutralisiert).

---

## 2. Retry-Matrix (live, `attempts` = HTTP-Requests am Stub)

| HTTP-Status | Klassifikation | attempts | Erwartet laut Doku | Status |
|---|---|---|---|---|
| 200 | — | 1 | 1 | ✅ |
| **400** | `NonRetryableError` | **1** | 1 | ✅ |
| **401** | `NonRetryableError` „authentication failed" | **1** | 1 | ✅ |
| **403** | `NonRetryableError` „authentication failed" | **1** | 1 | ✅ |
| **429** | `TransientError` | **12** | 4 | ❌ Amplifikation |
| **500** | `TransientError` | **12** | 4 | ❌ Amplifikation |
| **503** | `TransientError` | **12** | 4 | ❌ Amplifikation |

**Antwort auf die Kernfrage „Wird bei 429/5xx korrekt retryed, bei 4xx/401/403
NICHT?"** → **Klassifikation ist korrekt und vorbildlich**: 401/403 werden
explizit als Auth-Fehler erkannt (`resilient_transport.py:137-139`, MRO-Namensmatch
über `_is_authentication_error`), 400 bricht nach 1 Versuch ab, kein Retry auf
Auth-Fehler. **Aber** die *Zahl* der Retries ist 3× zu hoch, weil die
SDK-eigene Retry-Schicht mitgezählt wird (siehe `wp1b-llm-adapter-matrix.md` §4).
Kein Geld wird auf Auth-Fehler verschwendet ✅, aber auf 429/5xx wird 3× so
viel ausgegeben wie deklariert ❌.

Backoff: `LLM_BACKOFF_BASE_SECONDS=1.0`, `FACTOR=2.0`, `MAX=4.0`
(`resilient_transport.py:49-51`) → 1 s / 2 s / 4 s. Für Workspace-Calls
(`timeout >= 60 s`) Budget auf 1 Retry reduziert (`max_retries_for_timeout`,
`resilient_transport.py:199-215`).

---

## 3. Circuit-Breaker

| Aspekt | Befund | Beleg |
|---|---|---|
| Greift der CB auf LLM-Pfade? | **Ja.** `resilient_call` bindet `CircuitBreaker("llm:<provider>")` vor jedem Versuch (`resilient_transport.py:286`) | live: 12 attempts bei 500 → CB wurde nach jedem Fehlschlag gefüttert |
| Fast-Fail bei OPEN | Ja, `can_execute()` vor dem Aufruf, `LlmTransportError` mit „circuit open" (`resilient_transport.py:289-294`) | Code |
| Keying | **pro Provider-Klasse + Tenant** (`CircuitBreakerState`, tenant-scoped) — ein `llm:anthropic`-Zustand pro Tenant, nicht pro Instanz | `circuit_breaker.py:39-53` |
| Half-Open-Probe | Ja, Single-Probe-Semantik | `circuit_breaker.py:74-83` |
| **Außerhalb eines Tenant-Kontexts** | **CB deaktiviert** → `_NullCircuitBreaker` | live gemessen: `breaker class outside tenant ctx: _NullCircuitBreaker` (`resilient_transport.py:186-195`) |

**Konsequenz der letzten Zeile:** `_breaker_for` ruft
`TenantContext.get_tenant()` und fällt bei Fehlen still auf den No-op-Breaker
zurück (nur `logger.debug`). Im **Celery-Pfad** ist `set_request_tenant` vorher
gesetzt (`tasks.py:142`), dort greift der CB also. In **Management-Commandos,
`manage.py shell` und Unit-Tests ohne Tenant** läuft der Retry-Pfad ohne
Circuit-Breaker — bei 12 Versuchen pro Aufruf und 4 Aufrufen pro Sekunde ist
das ein unkontrollierter Lastspitzenpfad, aber kein Produktpfad. → **Info**,
kein Finding.

---

## 4. Fehlerpfad-Matrix (live gemessen, Anthropic-Stub)

| Szenario | Ergebnis | Sauber propagiert? |
|---|---|---|
| happy path 200 | `LlmResult(score=0.9, ...)` | ✅ |
| 401 | `LlmTransportError: ... authentication failed (HTTP 401)` | ✅ |
| 400 | `LlmTransportError: ... non_retryable` | ✅ |
| 429/500/503 | `LlmTransportError: ... transient_exhausted` | ✅ |
| Verbindung refused | `LlmTransportError: ... transient_exhausted: Connection error.` | ✅ |
| **Prose+Markdown → `validate_artifact`** | `LlmResult(score=0.0, suggestions=['LLM provider returned a non-JSON response; ...'])` | ✅ ehrlich degradiert |
| **Prose+Markdown → `check_consistency`** | `score=0.9, suggestions=['a']` — **Extraktion gelingt** | ✅ |
| **Prose+Markdown → `decompose_requirement`** | **`RAISED JSONDecodeError: Expecting value: line 1 column 1 (char 0)`** | ❌ **`AUD-2026-09-057` High** |
| **leerer Response-Text** | `score=0.0` + „non-JSON response"-Hinweis | ✅ (aber Score 0.0 ≠ „unbekannt") |
| **`usage` fehlt in Response** | **`RAISED AttributeError: 'NoneType' object has no attribute 'input_tokens'`** | ❌ **`AUD-2026-09-059` Medium** |
| kaputtes JSON generisch | siehe oben | ⚠️ |

### Warum `decompose_requirement` kaputt ist

`providers.py` hat drei Parser:

| Parser | Ort | markdown-fence | `{...}`-Extraktion | Fallback |
|---|---|---|---|---|
| `_parse_validation_response` | `:984-1018` | ja | nein | `score=0.0` |
| `_parse_consistency_response` | `:1021-1064` | ja | **ja** (`:1049-1054`) | `score=0.0` |
| `_parse_derivation_response` | `:958-981` | ja | nein | `children=[{...}]` |

`decompose_requirement` benutzt in **allen fünf HTTP-Providern** einen
**nackten `json.loads(raw)`** statt des vorhandenen Parsers:

- `providers.py:1215` (Anthropic)
- `providers.py:1407` (OpenAI)
- `providers.py:1595` (Ollama)
- `providers.py:1749` (Azure)
- `providers.py:1941` (OpenCode Go)

Der Docstring von `_parse_validation_response` (`providers.py:989-996`)
beschreibt exakt diesen Fehler und die bereits erfolgte Reparatur **für die
beiden anderen Capabilitys** — Issue #576 hat `validate_artifact` und
`check_consistency` geheilt, `decompose_requirement` **nicht**. Das ist
derselbe Bug, eine Ebene tiefer, mit derselben Ursache: `JSONDecodeError` mit
Roh-Parsertext.

### Warum das im Produkt sichtbar wird

`decompose_requirement` ist in `_ASYNC_CAPABILITIES` (`router.py:76`), läuft also
über Celery. `dispatcher.get_task_status` gibt bei `FAILURE` den
**Roh-Exception-Text** weiter:

```python
# backend/llm_adapter/dispatcher.py:187-193
elif state == "FAILURE":
    exc = async_result.result
    return TaskStatusResult(task_id=task_id, status="failed",
                            error=str(exc) if exc is not None else "Unknown error")
```

und `router.get_task_status` (`router.py:516-519`) legt ihn als
`out["error"]` in die Antwort. Das ist genau der in `providers.py:1026-1033`
beschriebene „systemaudit 2026-09-02, R5/R7"-Leak, den #576 für die anderen
zwei Capabilities behoben hat — für den Decompose-Pfad besteht er weiter.
Verstärkend: `router._execute_sync` maskiert denselben Text korrekt auf
`_GENERIC_PROVIDER_ERROR` (`router.py:123,331`) — **MCP/REST maskiert,
Celery-Status gibt roh aus**. Das ist eine konkrete Ausprägung von
`AUD-2026-09-036` (inkonsistente Fehler-Mapping-Politik).

### `usage`-Lücke

`providers.py:1160-1164` (Anthropic) und die Pendants in den anderen Providern:
```python
token_usage = (message.usage.input_tokens + message.usage.output_tokens
               if hasattr(message, "usage") else None)
```
`hasattr` ist `True`, wenn das Attribut existiert — auch wenn es `None` ist.
Live belegt: Antwort ohne `usage`-Feld →
`AttributeError: 'NoneType' object has no attribute 'input_tokens'`.
Korrekt wäre `getattr(message, "usage", None) is not None`.
