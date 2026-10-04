---
type: REVIEW
scope: wp1b-llm-cost-tracking-degradation
status: complete
date: 2026-09-29
author_agent: backend-reviewer
work_package: WP-1b
---

# WP-1b — Kosten-/Token-Tracking, Graceful Degradation, Provider-Auswahl, Async

---

## 1. Kosten-/Token-Tracking

### 1.1 Zwei getrennte Erfassungspfade

| Pfad | Ort | Quelle der Zahl | ehrlich? |
|---|---|---|---|
| **A — Dataclass-Capabilities** (`validate_artifact`, `decompose_requirement`, `check_consistency`, `derive_requirements`) | `router.py:286-292` (sync), `tasks.py:160-172` (async) | echte API-Response, **außer** Mock | ⚠️ siehe 1.3 |
| **B — freie `complete()`-Calls** (alle AI-Derivation, Review, Traceability, Interview, Bundle, Goals, Risks, Glossary, ADR) | `ai_derivation_service.py:2216-2221` u.a. | `approximate_token_count()` — ~4 Zeichen/Token | ✅ **klar deklarierte Schätzung** |

Der Docstring von `approximate_token_count` (`token_tracking.py:39-73`) sagt
explizit, dass dies *kein* Tokenizer ist und bewusst keiner eingeführt wurde.
**Das ist ehrliche Schätzung.** Pfad A ist die Problemzone.

### 1.2 Aggregation

- **Nach Tenant:** ja. `TokenUsageRecord` ist tenant-scoped; alle Queries laufen
  über `TokenUsageRecord.objects` (`:158, :196`).
- **Nach Provider:** ja. `aggregate_usage()` gruppiert `values("provider")`
  (`:197`). **NICHT** nach Modell und **NICHT** nach Capability aggregiert
  verfügbar — `capability` und `workspace_id` werden zwar geschrieben
  (`:118-121`), aber es gibt **keine** Aggregationsfunktion dafür. Die Aufgabe
  fragt „nach Modell/Provider/tenant" — **Provider ✅, Tenant ✅, Modell ❌**
  (das Modell steht im Audit-Log-`details`, nicht in `TokenUsageRecord`).
- **Nach Workspace:** Feld existiert (`workspace_id`), wird von 4 Pfaden
  befüllt, aber nie abgefragt.

### 1.3 Zwei Defekte in Pfad A

**(a) Input/Output sind nicht trennbar, `output_tokens` ist immer 0.**

```python
# router.py:286-292  (identisch tasks.py:166-172)
record_token_usage(
    provider=provider_name, capability=capability,
    input_tokens=result.token_usage or 0,
    output_tokens=0,                       # ← hart auf 0
    workspace_id=kwargs.get("workspace_id"),
)
```

`LlmResult.token_usage` ist laut Interface-Docstring
(`interface.py:40, 136`) die **Gesamtsumme** — Anthropic liefert
`input + output` (`providers.py:1161`), OpenAI `total_tokens`
(`providers.py:1361`). Die Gesamtsumme landet **vollständig in
`input_tokens`**, `output_tokens` ist **konstruktionsbedingt 0**.

Der Docstring von `record_token_usage` gibt das selbst zu
(`token_tracking.py:92-95`): *„input_tokens: Prompt/input token count (or the
combined total when a provider only exposes a single number)"*.

**Konsequenz:** Jede nach Modell/Provider differenzierte **Kosten**rechnung
(Output-Preise sind bei allen drei Providern ≥ Input-Preisen) ist mit diesen
Daten **nicht möglich**. Das Budget (`get_daily_usage` summiert Input+Output,
`:158-160`) ist als Gesamtmengen-Wächter korrekt, aber als
Kosten-Attribution unbrauchbar. → `AUD-2026-09-062` High.

**(b) Ollama verwirft die Input-Tokens.**

```python
# providers.py:1549-1550
# Ollama does not expose token counts in the same format; use eval_count
token_usage = data.get("eval_count") or None
```

Live belegt: Der Stub lieferte `eval_count=7, prompt_eval_count=11`; der
Adapter meldete `token_usage=7` — **`prompt_eval_count` wird nie gelesen**.
Ollama liefert beide Felder in `/api/generate`; der Code nimmt nur die
Output-Hälfte. Bei jedem Ollama-Aufruf ist der verzeichnete Verbrauch
**systematisch zu niedrig** (im Testfall 7 statt 18 = 39 % Verlust). Da
`output_tokens=0` gesetzt wird, ist der Datensatz dann *auch* falsch beschriftet
(7 Output-Tokens stehen als 7 Input-Tokens in der DB). → `AUD-2026-09-054` Medium.

**(c) Fehlende `usage` → harter Crash statt 0.**
Siehe `wp1b-llm-timeout-retry-errors.md` §4: `AttributeError` bei
`hasattr(message, "usage")` mit `usage=None`. Die Aufgabe fragt „Wird still 0
gerechnet?" — **nein, es wird gecrasht.** Das ist die andere Richtung des
Fehlers, aber die Frage ist damit beantwortet: es gibt **kein** stilles 0,
sondern einen unbehandelten `AttributeError`, der in `router._execute_sync` als
`LLM_PROVIDER_ERROR` maskiert wird (Datenverlust, kein Absturz) bzw. in
`tasks.py:174-176` als Celery-FAILURE mit Rohtext durchschlägt.

### 1.4 Fail-open (bewusst, dokumentiert)

`record_token_usage` (`token_tracking.py:123-129`) und `get_daily_usage`
(`:162-165`) fangen **alles** und loggen `warning`. `is_over_daily_limit`
(`:233-243`) gibt bei jedem Fehler `False` zurück. Begründung: „a broken
accounting layer can never take down the AI features". **Das ist eine
akzeptierte, dokumentierte Policy** — aber sie bedeutet: ein DB- oder RLS-Ausfall
deaktiviert das Budget **lautlos**. Nur `logger.warning`. Kein Health-Check, kein
MCP/REST-Signal. → Teil von `AUD-2026-09-063` Medium.

### 1.5 Reconciliation CR-20

**Befund `AUD-2026-09-020` unabhängig geprüft → BESTAETIGT, aber enger
präzisiert.**

| Aspekt | Vor-Audit-Claim | Eigene Prüfung |
|---|---|---|
| `settings.py:747-753` | Budget-Default `None` | **BESTÄTIGT.** `settings.py:764-766` `TENANT_TOKEN_LIMIT_PER_DAY` Default `None`; `token_tracking.py:240-242` → `is_over_daily_limit()` gibt dann **immer** `False`. Live: Variable ist im laufenden Container **nicht gesetzt** (`env \| grep LLM_` zeigt `LLM_PROVIDER, LLM_CAPABILITIES, LLM_LONG_RUNNING_TIMEOUT, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL, LLM_OPENCODE_SESSION` — **kein** `TENANT_TOKEN_LIMIT_PER_DAY`). **Im Audit-Stack läuft das Produkt faktisch ohne jedes Token-Budget.** |
| `cross_cutting.py:132-179` | `context.change_impact` umgeht Budget | **BESTÄTIGT, wörtlich.** `_complete_change_impact` (`:132-179`) ruft `provider.complete(...)` direkt — **kein** `is_over_daily_limit()`, **kein** `record_token_usage()`. Weder im Docstring (`:132-150`) noch im Code. |
| Weitere Umgeher | „mehrere Pfade" | **BESTÄTIGT und erweitert.** Gleiches Muster in: `ai_derivation_service._complete` — nein, dort **ist** es eingebaut (`:2119`, `:2216`). Die Umgeher sind: `cross_cutting._complete_change_impact`, `bundle_compression_service._call_provider` (prüft Budget, aber **nur** wenn nicht `degraded` — `:623`), `architecture_decompose_service` (`:828`, nur wenn nicht `degraded`), `traceability_suggest_service` (`:654`, nur wenn nicht `degraded`), `ai_review_service` (`:470`, nur wenn nicht `degraded`). Der `not degraded`-Guard heißt: **im Mock-Fallback-Modus läuft der Verbrauch ohne Budgetkontrolle.** |
| Severity P1/Hoch | „P1 (98/100)" | **relativiert.** `12-evidence-validation-and-corrections.md:27` stuft selbst auf „Bestätigt, Severity überhöht — P2 oder policyabhängig P1" herab. Ich bestätige: für self-hosted/QS **P2**, für verbindliches Tenant-Budget **P1**. Ohne gesetztes `TENANT_TOKEN_LIMIT_PER_DAY` ist das Feature **abschaltbar per Env-Auslass**. |

## 2. Graceful Degradation (ADR-02)

### 2.1 Stufen

| Stufe | Auslöser | Verhalten | Beleg |
|---|---|---|---|
| L0 | `LLM_PROVIDER` leer | `{"error":{"code":"LLM_NOT_CONFIGURED", ...}}` | `providers.py:2062-2067` |
| L0b | Capability nicht in `LLM_CAPABILITIES` | `LLM_NOT_CONFIGURED` + Hinweis | `router.py:209-223` |
| L0c | unbekannter Providername | `LlmProviderUnknownError` → `LLM_NOT_CONFIGURED`, Registry-Liste im Text | `providers.py:2071-2074` |
| L1 | SDK fehlt | `LlmNotConfiguredError("...not installed. Run: pip install ...")` | `providers.py:1094-1097` |
| L2 | Provider-Aufbau ok, Call scheitert | `LLM_PROVIDER_ERROR`, **generische** Message, Rohtext nur im Log/Audit | `router.py:123, 323-357` |
| L3 | Circuit OPEN | `LlmTransportError("circuit open ...")` → `LLM_PROVIDER_ERROR` | `resilient_transport.py:291-294` |
| **L4** | **Credential-/Konfigurationsfehler** | **Fallback auf `MockLlmProvider`, Ergebnis mit `[MOCK FALLBACK] `-Präfix markiert** | `ai_derivation_service.py:2066-2082, 2144-2168` |

### 2.2 Ist L4 ehrlich? — **Ja, das ist die stärkste Stelle des Adapters**

```
MOCK_FALLBACK_MARKER = "[MOCK FALLBACK] "     # ai_derivation_service.py:101
```

- Der Marker wird **vor** dem Parsen entfernt, aber `is_mock_fallback` wird
  **vorher** gelesen und als dritter Rückgabewert durchgereicht
  (`_complete_retrying`, `:2290`). Der eigene Docstring (`:2267-2281`)
  beschreibt exakt das Problem, dass beide Parser den Marker strippen und
  damit das einzige Beweismittel vernichten.
- Fallback-Antworten werden **nie gecacht** (`:2234` — `elif not
  result.startswith(MOCK_FALLBACK_MARKER)`), damit ein degradierter Wert nicht
  eine spätere echte Antwort verdrängt.
- Der Fallback wird **geloggt** (`:2072-2076`, `:2148-2152`).
- Er wird **auditiert** mit `success=False` (`:2153-2160`).
- Der Marker überlebt bis in die **publizierte MCP-Tool-Doku**:
  > *"'is_mock_fallback'=true means no real LLM ran and 'text' is a
  > '[MOCK FALLBACK] '-prefixed placeholder. Treat that as 'no compression
  > available', not as a compressed bundle."*

Das ist **ADR-02-konforme, ehrliche Degradation**. Ein Nutzer, der
`is_mock_fallback` liest, wird nicht getäuscht.

### 2.3 Aber: **L4 maskiert Konfigurationsfehler als Platzhalter**

Die Schwäche: `get_provider()` wirft `LlmNotConfiguredError` bei
**jedem** Konfigurationsproblem, und L4 fängt **alle** davon ab und
liefert Mock-Platzhalter. Konkret heißt das:

| Auslöser | Was der Nutzer sieht | Was wirklich passiert |
|---|---|---|
| `LLM_PROVIDER=anthropic` ohne `LLM_API_KEY` | plausible Platzhalter-Antwort | Provider **nie** konfiguriert |
| `claude-3-opus-20240229` retired (Default!) | nach L2 `LLM_PROVIDER_ERROR` | Modell existiert nicht mehr |
| SDK-Import schlägt fehl | Platzhalter | Paket fehlt |

Im ersten Fall gibt es **keinen** Fehler im Produkt — nur einen
`logger.warning` auf dem Server. Der Nutzer sieht eine看似 fertige
Antwort. Das ist der Punkt, an dem ADR-02 kippt: die Markierung ist
**ehrlich**, aber sie ist **versteckt** — sie steht in einem String, den
der UI-Pfad je nach Screen vielleicht nicht rendert.

→ `AUD-2026-09-064` Medium: **Feature-Gate fehlt.** Es gibt keinen
Produkt-Switch „LLM ist nicht konfiguriert → AI-Buttons deaktivieren /
Tooltip", der die Degradation **vor** dem Klick sichtbar macht. `LLM_PROVIDER=mock`
ist im Audit-Stack gesetzt, d.h. das Produkt läuft dauerhaft auf Stufe L4
ohne dass ein Nutzer es erfährt.

## 3. Provider-Auswahl im Produkt

### 3.1 Ist die Auswahl wirksam? — **Ja, zweistufig**

```
LlmSettings (DB, pro Tenant)  ──überschreibt──►  Env (LLM_PROVIDER etc.)
        ▲                                              ▲
   Admin-UI / REST                          docker-compose / .env
```

- `_apply_db_settings` (`providers.py:131-172`): `row.provider` **gewinnt
  immer**, sobald eine Zeile existiert.
- `get_llm_settings` (`settings_service.py:146-172`) liefert bei fehlender Zeile
  eine **ungespeicherte** Env-Spiegelung — Read-Pfade erzeugen **nie** eine Zeile
  (Issue #276).
- Im Celery-Pfad wird `tenant_id` über die Queue getragen und die Tenant-Settings
  werden im Worker neu aufgelöst (`tasks.py:146`) — **nicht** die Env. Wirkung
  nachweisbar: `tasks.py:147-152` loggt den pro Worker aufgelösten Provider.

**Wirkung vorhanden ✅.** Live bestätigt:
`GET /api/v1/llm-settings/` → `{"provider":"mock","base_url":"","model_name":"","api_key_is_set":false}`

### 3.2 Tippfehler / ungültiger Providername

| Fall | Verhalten | Bewertung |
|---|---|---|
| `LLM_PROVIDER` ungültig, **kein** DB-Row | `LlmProviderUnknownError` → `LLM_NOT_CONFIGURED` mit Registry-Liste | ✅ **graceful, kein 500** |
| `PATCH /llm-settings/` mit ungültigem Provider | DRF `ChoiceField` → **400** | ✅ |
| `EMBEDDING_PROVIDER` ungültig | `manage.py check` → `llm_adapter.W002` Warning | ✅ vorbildlich |
| `opencode_go` ohne Session | `manage.py check` → `llm_adapter.W003` Warning + Compose-Preflight | ✅ vorbildlich |
| **`LLM_API_KEY` fehlt bei anthropic/openai/azure** | **kein** Check, **kein** Warning | ❌ → `AUD-2026-09-065` Medium |
| **`AZURE_OPENAI_DEPLOYMENT` fehlt** | **kein** Check; `azure_deployment=""` → SDK-ValueError, 3× retried | ❌ Teil desselben Befunds |

**Muster:** Das Projekt hat für die *seltenen* Konfigurationen (#1050, #794)
ausgezeichnete Preflight-Checks gebaut — für die *häufigste* Fehlkonfiguration
(fehlender API-Key) gibt es **keinen**. `checks.py` prüft
`opencode_session` (`:150`), aber nie `api_key`.

### 3.3 Deckungsgleichheit UI ↔ Implementierung

| Quelle | Wert | `azure` enthalten? |
|---|---|---|
| `_PROVIDER_REGISTRY` (`providers.py:2010`) | anthropic, openai, ollama, azure, opencode_go, mock | **ja** |
| `LlmProvider` Enum (`models.py:2417-2421`) | anthropic, openai, ollama, opencode_go, mock | **nein** |
| `SettingsService.provider_choices()` (`settings_service.py:127`) | = Enum | **nein** |
| `LLM_PROVIDERS` UI (`llm-settings.ts:24-30`) | anthropic, openai, ollama, opencode_go, mock | **nein** |
| `README.md:333` | „`azure` — Azure OpenAI (set `LLM_API_KEY`, `LLM_BASE_URL` ...)" | **ja, beworben** |
| `.env.example:197-200` | `# LLM_PROVIDER=azure` Beispiel | **ja, beworben** |
| `settings.py:702` Kommentar | „Supported: mock \| anthropic \| openai \| ollama \| azure" | **ja, beworben** |

**`azure` ist implementiert, in Doku und Env-Beispiel beworben, aber über
keinen Produktpfad konfigurierbar** — die DB-Enum, das REST-ChoiceField und die
UI-Liste kennen es nicht. Ein Admin kann es nur setzen, indem er es
**manuell in der Datenbank** umgeht. → `AUD-2026-09-058` High.

## 4. Async-/Celery-Pfad

| Aspekt | Befund |
|---|---|
| Sync vs. async | `validate_artifact` **sync** (25 s hart); `decompose_requirement`, `check_consistency`, `derive_requirements` **async** über Celery (`router.py:73-76`) |
| Task-Zeitlimit | **keins** in `tasks.py:77` — siehe `AUD-2026-09-056` |
| Broker nicht konfiguriert | `BROKER_NOT_CONFIGURED` **sofort**, kein 500 (`dispatcher.py:119-128`) ✅ |
| **Worker fällt aus** | `_dispatch_async` gibt `{"task_id": ...}` zurück, sobald `apply_async` **in den Broker geschrieben** hat (`dispatcher.py:149-152`). Kein Worker → Nachricht liegt in Redis, `get_task_status` meldet dauerhaft **`pending`** (`dispatcher.py:177-178`). **Kein Timeout, kein Abandon, kein Fehler.** Der Nutzer pollt endlos. |
| Tenant-Propagation | `tenant_id` als String über die Queue, im Worker `set_request_tenant` (beide Layer, `:142`) — RLS korrekt (#444) ✅ |
| Secret über die Queue | Nur `tenant_id`, **niemals** der API-Key (`:101-106`) ✅ |
| Whitelist | `ALLOWED_CAPABILITIES` als `frozenset`, `ValueError` bei unbekanntem Namen (`:108-109`) ✅ kein `getattr` auf beliebige Namen |
| Task-Result-Shape | `_serialise` via `dataclasses.asdict` (`:45-49`) ✅ |
| **Fehlertext** | `dispatcher.py:187-193` gibt `str(exc)` **roh** weiter → siehe `AUD-2026-09-057` |

**Worker-Ausfall ist der gravierendste Async-Befund:** Ein ausgefallener
Celery-Worker sieht für den Aufrufer **identisch** aus wie ein Auftrag, der
noch läuft. Es gibt kein `ETA`, kein Ablaufdatum, keine
`CELERY_TASK_TIME_LIMIT`-Default. → `AUD-2026-09-066` High.
