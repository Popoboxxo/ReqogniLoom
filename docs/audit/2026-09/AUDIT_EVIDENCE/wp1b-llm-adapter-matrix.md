---
type: REVIEW
scope: wp1b-llm-adapter-matrix
status: complete
date: 2026-09-29
author_agent: backend-reviewer
work_package: WP-1b
---

# WP-1b — LLM-Adapter: Adapter-Matrix und Request-Formate (feldweise)

Revision: `chore/system-audit-2026-09` == `main` @ `abd61aed`
Container: `ai-native-reqflow-poc-backend-1` (image `f45053df0afc`, Django 6.1.1, Python 3.12.14)
Methode: statische Analyse + **Request-Capture gegen In-Process-Stub** (kein `LLM_PROVIDER`-Umschalten).

---

## 1. Adapter-Inventar (Ist, nicht Soll)

Registry: `backend/llm_adapter/providers.py:2010-2017`

| Registry-Key | Klasse | Datei:Zeile | In `__all__`? | In `LlmProvider`-Enum? | In UI-Liste? |
|---|---|---|---|---|---|
| `anthropic` | `AnthropicProvider` | `providers.py:1072` | ja | ja | ja |
| `openai` | `OpenAiProvider` | `providers.py:1325` | ja | ja | ja |
| `ollama` | `OllamaProvider` | `providers.py:1486` | ja | ja | ja |
| `azure` | `AzureOpenAiProvider` | `providers.py:1663` | **nein** | **nein** | **nein** |
| `opencode_go` | `OpencodeGoProvider` | `providers.py:1817` | **nein** | ja | ja |
| `mock` | `MockLlmProvider` | `providers.py:329` | ja | ja | ja |

**Es gibt 6 Adapter, nicht 5.** `opencode_go` (Issue #1050 / PR-Nachlauf) ist real
implementiert und in der Produktkonfiguration wählbar, fehlt aber in `__all__`
(`providers.py:2096-2118`) und in der Aufgaben-Soll-Angabe.

**`azure` ist implementiert, aber im Produkt nicht konfigurierbar** →
siehe Finding `AUD-2026-09-058`.

Enum-Quelle: `backend/persistence/models.py:2411-2421` (`LlmProvider` = anthropic|openai|ollama|opencode_go|mock).
Serializer-Enum: `backend/application/settings_service.py:125-127` → `list(LlmProvider.values)`.
UI-Liste: `frontend/src/api/llm-settings.ts:22-30`.

---

## 2. Request-Matrix (feldweise, live verifiziert)

Alle Zeilen durch tatsächlichen HTTP-Capture gegen `http.server`-Stub belegt
(Probe lief im Backend-Container, `PYTHONPATH=/app`, Provider direkt mit
explizitem `ProviderConfig` konstruiert — `LLM_PROVIDER` des geteilten
Containers blieb auf `mock`).

### 2.1 Anthropic

| Feld | Ist | Soll (Anthropic API) | Status |
|---|---|---|---|
| URL | `POST /v1/messages` | `https://api.anthropic.com/v1/messages` | ✅ |
| Methode | POST | POST | ✅ |
| Auth-Header | `X-Api-Key: <key>` | `x-api-key` | ✅ |
| Versions-Header | `anthropic-version: 2023-06-01` | Pflicht | ✅ |
| Timeout | `timeout=25.0` an SDK + Policy | — | ✅ |
| `max_tokens` | 1024 (validate) / 4096 (decompose, consistency) | Pflicht | ✅ |
| Modell-ID | **`claude-3-opus-20240229`** | **RETIRED 2026-01-05** | ❌ → `AUD-2026-09-052` |

Body (live):
```json
{"max_tokens":1024,
 "messages":[{"role":"user","content":"Validate the following artifact (id: REQ-1).\n\n###\nTitle: T\nContent:\nC\n###\n\nReturn a JSON object with keys: score (0-1), suggestions (list of strings)."}],
 "model":"claude-3-opus-20240229"}
```
Beachte: kein `system`-Prompt, keine `temperature`. Prompt-Injection-Mittel
`###`-Fence ist im Body sichtbar (`providers.py:209,248-262`).

### 2.2 OpenAI

| Feld | Ist | Soll | Status |
|---|---|---|---|
| URL | `POST {base_url}/v1/chat/completions` | `/v1/chat/completions` | ✅ |
| Auth-Header | `authorization: Bearer <key>` | `Authorization: Bearer` | ✅ |
| Timeout | `timeout=` an `OpenAI(...)` + Policy | — | ✅ |
| Modell-ID | **`gpt-4`** | Alias zeigt auf `gpt-4-0613`, **Shutdown 2026-10-23** | ⚠️ → `AUD-2026-09-053` |

Body (live): `{"messages":[{"role":"user","content":"..."}],"model":"gpt-4"}`

### 2.3 Ollama

| Feld | Ist | Soll | Status |
|---|---|---|---|
| URL | `POST {base_url}/api/generate` | `/api/generate` | ✅ |
| Auth-Header | **keiner** (korrekt) | keiner | ✅ |
| Timeout | `timeout=` an `requests.post` | — | ✅ |
| Body | `{"model","prompt","stream":false}` | korrekt | ✅ |
| Modell-ID | `llama3` | existiert | ✅ |
| `raise_for_status()` | **innerhalb** `_resilient` | nötig für 5xx-Klassifikation | ✅ (`providers.py:1543`) |
| Token-Nutzung | `eval_count` **nur Output**; `prompt_eval_count` verworfen | — | ❌ → `AUD-2026-09-054` |

Body (live):
```json
{"model":"llama3","prompt":"Validate the following artifact (id: REQ-1).\n\n###\nTitle: T\nContent:\nC\n###\n\nReturn JSON: {score, suggestions}. Return score as a decimal between 0.0 and 1.0.","stream":false}
```

### 2.4 Azure OpenAI

| Feld | Ist | Soll | Status |
|---|---|---|---|
| URL | `POST {endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...` | korrekt | ✅ |
| Auth-Header | `api-key: <key>` | Azure nutzt `api-key` | ✅ |
| `api_version` | `2024-02-01` Default | veraltet aber gültig | ⚠️ |
| Modell im Body | `self._config.azure_deployment or self.model_name` | Deployment-Name | ✅ (`providers.py:1698`) |
| Timeout | `timeout=` + Policy | — | ✅ |

Body (live, `AZURE_OPENAI_DEPLOYMENT=my-deployment`):
`{"messages":[...],"model":"my-deployment"}` an
`/openai/deployments/my-deployment/chat/completions?api-version=2024-02-01`

**Achtung Fehlpfad:** Ohne `AZURE_OPENAI_DEPLOYMENT` konstruiert `AzureOpenAI`
mit `azure_deployment=""` (`providers.py:1692`) → SDK-`ValueError`, der als
`TransientError` klassifiziert und **3× wiederholt** wird (siehe §4).

### 2.5 OpenCode Go (nicht beauftragt, aber real)

| Feld | Ist | Soll | Status |
|---|---|---|---|
| URL | `POST {base_url}/chat/completions`, Default `https://opencode.ai/zen/go/v1` | OpenAI-kompatibel | ✅ |
| Auth-Header | `authorization: Bearer` + `x-opencode-session` | Pflicht | ✅ (`providers.py:1881`) |
| Modell-ID | `claude-sonnet-4-5` | aktiv, Shutdown frühestens 2026-09-29 | ⚠️ Info |
| Session-Pflicht | System-Check `llm_adapter.W003` | ✅ | `checks.py:150-212` |

### 2.6 Mock

| Feld | Ist |
|---|---|
| Netzwerk | **keines** (`providers.py:472` „The mock never performs network I/O") |
| URL/Header | entfällt |
| Modell-ID | `mock-model-v1`, überschrieben durch konfiguriertes `model_name` |

---

## 3. Modell-ID-Prüfung gegen echte Provider-Nachweise

| Adapter | Default in Code | Quelle | Status 2026-09-29 | Befund |
|---|---|---|---|---|
| anthropic | `claude-3-opus-20240229` | `providers.py:1080` | **RETIRED 2026-01-05**, „API requests to it now fail" | `AUD-2026-09-052` Critical |
| openai | `gpt-4` | `providers.py:1333` | Alias → `gpt-4-0613`, **Shutdown 2026-10-23** | `AUD-2026-09-053` High |
| ollama | `llama3` | `providers.py:1499` | gültiger Ollama-Tag | ok |
| azure | `gpt-4` | `providers.py:1675` | nur Fallback, wenn `azure_deployment` leer | Info |
| opencode_go | `claude-sonnet-4-5` | `providers.py:1852` | aktiv, Shutdown frühestens 2026-09-29 | Info |

### Nachweis Anthropic

`platform.claude.com/docs/en/about-claude/model-deprecations` (abgerufen 2026-09-29):
`claude-3-opus-20240229` → **Retired**, retirement date 2026-01-05, Recommended
replacement `claude-opus-4-8`. Deprecation-History-Eintrag: `2025-06-30 |
claude-3-opus-20240229 | 2026-01-05 | claude-opus-4-8`.

`modeldeprecations.dev/anthropic/claude-3-opus-20240229`:
„Yes — Claude Opus 3 is retired. Anthropic deprecated it on June 30, 2025 and
shut it down on January 5, 2026; **API requests to it now fail**."

**Reichweite:** Jeder `AnthropicProvider`-Aufruf **ohne** explizit gesetztes
`LLM_MODEL`/`LlmSettings.model_name` bricht mit HTTP 404/410. Da der
Deployment-Default `LLM_MODEL` leer ist (`.env.example:152`, alle
compose-Files `LLM_MODEL: ${LLM_MODEL:-}`), ist der **Auslieferungszustand
"LLM_PROVIDER=anthropic ist komplett tot"**.

### Reconciliation zu Issue #118 (GESCHLOSSEN 2026-07-31)

`docs/audit/2026-09/AUDIT_EVIDENCE/issue-inventory.md:236`:
> #118 GESCHLOSSEN — „[AUDIT][DOGFOOD] MEDIUM: Anthropic-Provider hartcodiert ein
> zurueckgezogenes Modell und ignoriert die konfigurierte model_name"

Der Fix hat **nur den Override** hergestellt
(`providers.py:852-853` `_BaseHttpProvider.__init__`), **nicht die Default-ID
angefasst**. `MODEL_NAME = "claude-3-opus-20240229"` steht unverändert in
`providers.py:1080`. Das Issue ist damit **nicht vollständig geschlossen** —
gleiche Ursache, andere Ausprägung (Override funktioniert, Default nicht).
→ Klassifikation `BESTAETIGT`, nicht `NEU`.

### Nachweis OpenAI

`developers.openai.com/api/docs/deprecations` + Community-Thread
(2026-05-25) nennt `gpt-4-0613` mit **Shutoff 2026-10-23**; `gpt-4-1106-preview`
und `gpt-4-0125-preview` waren bereits 2026-03-26 abgeschaltet. Der Alias `gpt-4`
zeigt auf `gpt-4-0613`. **Nicht** von einem API-Fehler heute betroffen, aber
Restlaufzeit ~3 Wochen ab Auddatum → `High` mit Datum, nicht `Critical`.

### Gegenprobe: dokumentierte Modelle sind aktuell

`.env.example:184` empfiehlt `claude-3-5-sonnet-20241022` (Retired 2025-10-28)
und `.env.example:189` `gpt-4o` (in ChatGPT 2026-02-13 retired, API noch
verfügbar). Beide Beispiele im Quickstart sind ebenfalls veraltet →
Teil des Befunds `AUD-2026-09-053`.

---

## 4. Retry-Amplifikation (live gemessen)

Befund: **12 ausgehende HTTP-Requests bei einer einzigen logischen 5xx.**

```
=== retry amplification ===
  anthropic  HTTP 500 -> 12 outbound requests
  openai     HTTP 500 -> 12 outbound requests
  anthropic SDK default max_retries : 2
  openai    SDK default max_retries : 2
  policy max_retries (short call)   : 3
  policy max_retries (long call)    : 1
```

Rechenweg: `PolicyEngine` macht `max_retries + 1` = 4 Versuche
(`resilience/policy_engine.py:93`). Jeder Versuch geht an den SDK-Client, der
**eigenständig** `max_retries=2` (Default, nie überschrieben) anwendet → 3
HTTP-Requests pro Versuch. 4 × 3 = 12.

Weder `anthropic.Anthropic(...)` (`providers.py:1100-1103`) noch
`openai.OpenAI(...)` (`providers.py:1347-1351`) noch `AzureOpenAI(...)`
(`providers.py:1689-1695`) übergeben `max_retries`. → `AUD-2026-09-055` High.

Konsequenz bei HTTP 429 (günstigster Fehlerfall): **12 kostenpflichtige
Anfragen pro logischem Aufruf**, plus 7 s Backoff (1+2+4) pro Außenversuch.
