---
type: REVIEW
scope: wp1b-llm-mock-double
status: complete
date: 2026-09-29
author_agent: backend-reviewer
work_package: WP-1b
---

# WP-1b — Mock-Adapter: Ist er ein ehrlicher Testdouble?

Klasse: `backend/llm_adapter/providers.py:329-829` (`MockLlmProvider`)
Urteil: **Ehrlicher Testdouble auf Capability-Ebene, unehrliche Token-Zahlen,
kein ehrliches Kosten-/Budget-Signal.**

---

## Antwort in einem Satz

> Der Mock **fälscht keine fachlichen Ergebnisse** — er ist als „kein LLM
> verfügbar" klar erkennbar und markiert jeden Degradations-Pfad sichtbar —,
> **aber er liefert pro Aufruf fest verdrahtete Token-Zahlen (42/100/120/200),
> die weder aus dem Prompt noch aus einer Response stammen** und die
> unverändert in die Kosten-Aggregation und das Tagesbudget einfließen.

---

## (a) Schema-Plausibilität

`complete()` kennt **12 Purpose-Strings** und liefert für jeden ein
schema-konformes JSON. Gemessen (live, `probe.py`):

```
mock suggestions      : ['Mock suggestion for artifact REQ-1']
mock children titles  : ['Mock child 1', 'Mock child 2']
mock consistency score: 0.95 issues: []
mock complete(unknown purpose): []
mock complete(no purpose)     : '[]'
```

Positiv: Die Platzhalter sind **bewusst strukturer Natur**. `context_change_impact`
(`:704-727`), `traceability_suggest_links` (`:659-702`) und `audit_ai_review`
(`:617-657`) erfinden **bewusst keine IDs** — sie re-emitieren nur die
`candidate_index` / `index` / `id`-Werte, die der Aufrufer ihnen in
`context` gegeben hat, damit die Referenzintegritäts-Auflösung des Services
immer einen Treffer findet. Das ist die richtige Entscheidung und in den
Docstrings auch so begründet.

Negativ: **Unbekannte Purposes fallen still auf `json.dumps([])` zurück**
(`providers.py:829`). Der Mock signalisiert „unbekannter Purpose" **nicht**.
Ein Tippfehler in einem Purpose-String (z. B. `need_to_sys_req`) liefert
`[]` statt eines Fehlers → der aufrufende Service sieht „LLM hat nichts
geliefert" und meldet das als fachliches Ergebnis. → Teil von `AUD-2026-09-060`.

## (b) Fachliche Qualität der „Analysen"

**Kein zufälliger Text, kein auskommentierter Code.** Jeder Pfad ist
bewusst deterministisch und der Code ist ausführend:

| Purpose | Ausgabe | fachlich sinnvoll? |
|---|---|---|
| `need_to_sysreq` | N Requirements, `count` aus `max_requirements_per_need` | Platzhalter, aber strukturell korrekt |
| `sysreq_to_arch_assign` | `arch_ids[:1]` | „erstes Element" — willkürlich, aber deterministisch |
| `sysreq_decompose_next_level` | 2 Kinder, erstes mit `suggested_arch_element_id` | Platzhalter |
| `arch_decompose_tree` | rekursiver Baum, `max_breadth` × `max_depth` | **echte Rekursion**, `element_type` aus Baumposition abgeleitet (`:551-589`) |
| `test_derive_from_requirement` | 1 TestCase mit 2 Schritten | Platzhalter |
| `audit_ai_review` | Gruppierung nach `(rule_id, scope_artifact_id)` | echte Gruppierungslogik |
| `traceability_suggest_links` | Re-Ranking der übergebenen Kandidaten | nur Re-Ranking, keine Bewertung |
| `context_change_impact` | **alle** Kandidaten `likely_affected: True` | **das ist der problematischste Wert** (`:715-720`) |
| `derive_risks_from_architecture` | 1 Risiko, `probability/impact: medium` | Platzhalter |
| `derive_glossary_from_workspace` | 1 Term, Definition = „Placeholder definition" | ehrlich als Platzhalter benannt |
| `goal_aggregate` | Prosa, echte Goal-Titel joined | ehrlich |
| `derive_adr_from_decision` | 1 ADR-Gerüst | Platzhalter |

Der `rationale`-Text von `context_change_impact` ist selbstredend und ehrlich:
> `"Directly linked to the changed entity via the trace graph (mock provider — no semantic assessment performed)."`
(`providers.py:719-722`)

## (c) Token-/Kosten-Zahlen — **das ist der Unehrlichkeitspunkt**

```python
# providers.py:385-391
return LlmResult(score=0.85, suggestions=[...], provider="mock",
                 model=self.model_name, token_usage=42)       # validate
# :413   token_usage=100                                    # decompose
# :438   token_usage=200                                    # check_consistency
# :455   token_usage=120                                    # derive_requirements
```

Live belegt — **der Wert ist konstant, unabhängig von der Eingabe**:

```
mock ignores content?  r1.token_usage=42 r2.token_usage=42
```

wobei `r1` ein 5000-Zeichen-`content` war und `r2` der String `"short"`. Der
Wert hängt also **weder von der Prompt-Länge noch von irgendeinem Response ab**
— er ist eine Konstante. Ein echter Adapter liefert `input+output` aus der API
(`providers.py:1160-1164`), Ollama liefert `eval_count` (`providers.py:1550`).

**Konsequenz in der Kosten-Aggregation:**

`router.py:286-292` und `tasks.py:166-172` schreiben
`input_tokens=result.token_usage or 0, output_tokens=0`. Der Mock speist also
pro Aufruf eine **erfundene** Zahl in `TokenUsageRecord` ein. Diese Zahlen
fließen in:

1. `get_daily_usage()` (`token_tracking.py:132-164`) → `is_over_daily_limit()`
2. `aggregate_usage()` (`:167-208`) → `get_token_usage()` → REST/MCP
3. Der Audit-Log (`audit_logger.py:143-150`, `token_usage` im `details`-Dict)

**Ein Mock-Lauf kann ein Tagesbudget erschöpfen, das für echte Aufrufe
gedacht war** — und umgekehrt maskiert ein Mock-lastiger Betrieb das reale
Kostenvolumen. → `AUD-2026-09-061` High.

**Kontrahierend:** Die freien `_complete()`-Pfade schreiben
`approximate_token_count(prompt)` / `approximate_token_count(result)`
(`ai_derivation_service.py:2216-2221`) — das ist eine **offen deklarierte
Schätzung** (~4 Zeichen/Token, `token_tracking.py:39-73`) und damit ehrlich.
Der Mock-Capability-Pfad erfindet dagegen eine Zahl, die **als exakte API-Nutzung
dargestellt** wird. Genau diese Asymmetrie ist der Befund.

## (d) Determinismus / Flakiness

**Deterministisch — bis auf eine Ausnahme.**

| Aspekt | Befund |
|---|---|
| `validate_artifact` / `decompose_requirement` / `check_consistency` / `derive_requirements` | deterministisch, kein State, kein `random` |
| `complete()` mit Purpose | deterministisch, hängt nur an `context` |
| `_simulate()` (`providers.py:359-367`) | `time.sleep(mock_delay)` + **`random.random() < mock_error_rate`** |
| Default | `MOCK_LLM_ERROR_RATE="0.0"` (`providers.py:126`) → **kein Zufall im Default-Betrieb** |
| `mock-model-v1`-Instabilität | behoben: `self.model_name = config.model_name or MODEL_NAME` (`:357`) |

`_simulate()` ist damit **kein Produktcode**, sondern ein CI-Knopf: nur wenn
explizit `MOCK_LLM_ERROR_RATE>0` gesetzt ist, wird gewürfelt. **Kein Flaky-Risiko
im Default.** Sauber.

Aber: `_simulate()` wirft `RuntimeError("MockLlmProvider: simulated error")`
(`:367`) — dieser **kein** `LlmNotConfiguredError`/`LlmProviderUnknownError`.
Im `CapabilityRouter._execute_sync` fällt er in den generischen
`except Exception` → `LLM_PROVIDER_ERROR` (korrekt). In
`AiDerivationService._complete` fällt er ebenfalls in `except Exception` →
`LlmResponseError` (korrekt, **kein** Mock-Fallback). Konsistent.

## (e) Gibt es einen Test, der Mock ≠ echten Provider sichert?

**Teilweise, und die Lücke ist genau die Problematische.**

| Test | Was er sichert | Deckt Mock-vs-echt? |
|---|---|---|
| `tests/test_provider_contracts.py` | alle 6 Provider erben `LlmCapabilityInterface`, implementieren alle 5 Methoden | **Struktur ja, Verhalten nein** |
| `tests/test_llm_adapter.py` | Mock liefert stabile Werte | **bestätigt den Mock als Testdouble** |
| `tests/test_token_tracking.py` | Approximation, Aggregation | nein |
| `tests/test_resilient_transport.py` | Klassifikation 4xx/5xx/401 | Adapter-unabhängig |
| `tests/test_long_running_timeout.py` | Purpose-Timeouts | nein |

**Es gibt keinen Test der Form „Mock-Verhalten ≠ echtes Provider-Verhalten".**
Konkrete Folgen, live gemessen:

1. **Mock toleriert kaputtes JSON nicht, echte Provider schon** —
   `_parse_validation_response` / `_parse_consistency_response` sind *nur* in den
   HTTP-Providern, der Mock hat **keine** Parser und **keinen** Fehlerpfad.
   Ein Mock-basierter Test kann den `decompose_requirement`-Bug
   (`AUD-2026-09-057`) prinzipiell **nicht** finden.
2. **Mock kennt kein `usage`-Feld** — der `hasattr`-Bug (`AUD-2026-09-059`)
   ist gegen den Mock ebenfalls nicht testbar.
3. **Der Mock hat keinen Timeout-Pfad** — `timeout=` wird akzeptiert
   („for interface parity but do not alter the output", `:379-383`) und
   **völlig ignoriert**. Ein Test mit `timeout=0.001` gegen den Mock läuft
   durch.

## Wird der Mock-Pfad als Beweis für LLM-Funktionalität verwendet?

**Ja, in mindestens drei nachweisbaren Produkt-/Doku-Stellen:**

1. **`/health/`** — `llm_provider_env: "ok"` (live:
   `{"status":"ok","checks":{...,"llm_provider_env":"ok",...}}`). Der Check
   bestätigt `LLM_PROVIDER` *gesetzt*, nicht *funktionsfähig*. Mit
   `LLM_PROVIDER=mock` ist er grün, obwohl kein LLM existiert.
2. **CI** — `.github/workflows/ci.yml:136` und
   `.github/workflows/playwright.yml:106,166` setzen `LLM_PROVIDER: mock`.
   Die gesamte grüne CI-Pipeline ist also ein Beweis, dass der **Mock**
   funktioniert — nie, dass ein echter Provider funktioniert. Genau darum ist
   die `claude-3-opus-20240229`-Regression (seit 2026-01-05) durch keinerlei
   Gate aufgefallen.
3. **MCP-Tool-Beschreibungen** — 4 Tool-Beschreibungen in der publizierten
   Registry sagen wörtlich „via the LLM adapter (**mock by default**)"
   (`context.change_impact`, `audit.ai_review`, `traceability.suggest_links`,
   `goal.generate_ai`). Das ist **transparent** — der Mock wird offen
   benannt, nicht als echtes LLM verkauft. Positiv zu vermerken.

**Fairness:** `settings.py:704` defaultet `LLM_PROVIDER` auf `mock` und
`.env.example:145` auf `mock`. Das ist für ein self-hosted POC die richtige
Default-Wahl. Der Befund ist **nicht** „mock ist Default", sondern „mock ist
Default **und** liefert erfundene Kostenzahlen **und** `/health/` +
CI behandeln ihn als Funktionsnachweis".

## Fazit-Matrix

| Frage | Antwort |
|---|---|
| (a) Plausibles Schema? | ✅ ja, 12 Purposes, schema-konform |
| (b) Fachlich sinnvoll / zufällig / auskommentiert? | ✅ deterministisch, nicht zufällig, bewusst gestaltet; ⚠️ ein Purpose (`context_change_impact`) markiert **alle** Kandidaten als betroffen |
| (c) Token-Zahlen ehrlich? | ❌ **nein** — 4 Konstanten, prompt-unabhängig, als exakte Nutzung ausgewiesen |
| (d) Deterministisch? | ✅ ja (Default), `random` nur bei explizitem `MOCK_LLM_ERROR_RATE>0` |
| (e) Test „Mock ≠ echter Provider"? | ❌ **nein** — genau die Lücke, die (c) und die JSON-/usage-Bugs unentdeckt lässt |
