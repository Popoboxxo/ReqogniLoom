---
type: REVIEW
scope: WP-1b (LLM-Adapter) — adversarial second review
status: final
date: 2026-10-01
author_agent: backend-reviewer
branch: chore/audit-review-2026-09
method: read-only static verification against real product source/config; Docker daemon DOWN → no live tests
targets: [AUD-2026-09-052, -053, -055, -057, -058, -061, -062, -066; Stichprobe -054, -056, -059, -060, -063, -065; -067]
---

# REVIEW_WP1B — adversariale Verifikation der WP-1b-Findings (LLM-Adapter)

**Scope.** Unabhängiger, read-only Gegenbeweis-Versuch gegen die WP-1b-Behauptungen
aus `docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5 und
`docs/audit/2026-09/AUDIT_EXTERNAL_INTEGRATIONS.md` §WP-1b (Z. 1019–1253),
gegen den echten Produktcode unter `backend/llm_adapter/**` plus
`backend/persistence/models.py`, `backend/application/settings_service.py`,
`backend/reqogniloom/{settings.py,celery.py}`, `frontend/src/api/llm-settings.ts`,
`.env.example`, `deploy/docker-compose*.yml`.

**Methodik / Grenzen.** Das audit-eigene `AUDIT_EVIDENCE/*` wurde **nicht** als
Beweis verwendet; jede Aussage wurde neu aus Produktcode/-config abgeleitet. Der
Docker-Daemon ist DOWN, es wurden **keine** Live-Tests gefahren. Externe Fakten
(Provider-Retirement-Daten) sind ohne Netz **nicht statisch belegbar** und werden
als solche markiert. Beide Pässe des Protokolls wurden gefahren (Recall →
Adversary); jedes Zitat wurde auf Inhalt geprüft. Keine Datei außerhalb
`docs/audit/2026-09/review/` wurde verändert. HEAD/Branch verifiziert:
`10dc620f` auf `chore/audit-review-2026-09`.

---

## 1. Gegenbeweis-Tabelle

| ID | orig_sev | REVIEW_VERDICT | corrected_sev | Gegenbeweis (file:line + Zitat) | Note |
|---|---|---|---|---|---|
| AUD-2026-09-052 | Critical | **TEILWEISE** | **High** | Default bestätigt: `providers.py:1080` `MODEL_NAME = "claude-3-opus-20240229"`; wirksam über `providers.py:853` `self.model_name = config.model_name or self.MODEL_NAME`; env-Auflösung `providers.py:120-121` `os.environ.get("LLM_MODEL_NAME") or os.environ.get("LLM_MODEL") or ""`; DB-Overlay `providers.py:167-168` `if row.model_name: cfg.model_name = row.model_name`. Leer: `settings.py:707` `LLM_MODEL ... default=""`; `deploy/docker-compose.yml:599` `LLM_MODEL: ${LLM_MODEL:-}` (ebenso :828, :919; minimal :141). **Aber Trigger nur opt-in:** `settings.py:704` `LLM_PROVIDER ... default="mock"` / compose `:596` `${LLM_PROVIDER:-mock}` — im ausgelieferten Default ist Anthropic gar nicht aktiv. | Kernkausalität (Default → Modell-ID) **bestätigt**. Teilaussage „seit 2026-01-05 retired" ist eine **externe** Tatsache → **NICHT VERIFIKABAR** (kein Netz, kein Repo-Beleg). Die Register-Behauptung „jeder Aufruf … schlägt fehl" gilt nur bei `LLM_PROVIDER=anthropic`. Critical überzogen, da der Shipped-Default `mock` ist. |
| AUD-2026-09-053 | High | **TEILWEISE** | High | Code-Default bestätigt: `providers.py:1333` `MODEL_NAME = "gpt-4"` (gleiche Auflösung wie 052). `.env.example`-Teilaussage teils falsch: `.env.example:184` `# LLM_MODEL=claude-3-5-sonnet-20241022`, `:189` `# LLM_MODEL=gpt-4o` — `gpt-4o` ist **kein** abgekündigtes Modell (externe Aussage, jedenfalls unbelegt); „nennt ebenfalls retired Modelle" trifft für `:189` nicht zu. | Shutdown-/Alias-Aussage (`gpt-4-0613`, 2026-10-23) **NICHT VERIFIKABAR** (extern). Trigger nur bei `LLM_PROVIDER=openai`. High bleibt als Konfigurationsfalle vertretbar, stützt sich aber auf unbelegte Retirement-Daten. |
| AUD-2026-09-055 | High | **BESTAETIGT** | High | SDK-Clients ohne `max_retries`: `providers.py:1100-1103` `anthropic.Anthropic(api_key=..., base_url=...)`; `:1347-1351` `OpenAI(api_key=..., base_url=..., timeout=...)`; `:1689-1695` `AzureOpenAI(...)` (kein `max_retries`); `:1882-1887` `OpenAI(...)` (opencode). Policy-Ebene: `resilient_transport.py:39` `LLM_MAX_RETRIES = 3`; `:199-215` `max_retries_for_timeout` → 3 bei <60 s; `:279-285` `Policy(..., max_retries=max_retries_for_timeout(...))`; `policy_engine.py:92-93` `# Total attempts = 1 initial + max_retries.` / `for attempt in range(self.policy.max_retries + 1)`. | Multiplikation **stimmt**: 4 PolicyEngine-Versuche × (1 + 2 SDK-Retries) = **12**. Die drei zitierten Zeilen (1100/1347/1689) sind korrekt. Zahl „5 HTTP-Provider" stimmt (anthropic/openai/ollama/azure/opencode_go; mock zählt nicht). |
| AUD-2026-09-057 | High | **BESTAETIGT** | High | Nackte `json.loads` in allen 5 HTTP-Providern: `providers.py:1215` (`data = json.loads(raw)`), `:1407`, `:1595`, `:1749`, `:1941`. Danach Roh-Parsertext ins Client: `dispatcher.py:187-193` `elif state == "FAILURE": ... error=str(exc)`. | **Verschärfend bestätigt:** die Schwester-Parser `_parse_validation_response` (`providers.py:984-1018`) und `_parse_consistency_response` (`:1021-1064`) sind laut Docstring ausdrücklich gegen #576 gehärtet („every provider's validate_artifact used a bare json.loads"), `decompose_requirement` wurde **nicht** mitgezogen. Echte Asymmetrie, kein Testdouble-Problem. |
| AUD-2026-09-058 | High | **BESTAETIGT** | High | Implementiert: `providers.py:2014` `"azure": AzureOpenAiProvider,`; Doku: `.env.example:142` `# Supported: mock | anthropic | openai | ollama | azure`, `:197-200` Azure-Block; `settings.py:702`. **Nicht wählbar:** `models.py:2417-2421` Enum `ANTHROPIC/OPENAI/OLLAMA/OPENCODE_GO/MOCK` (kein `azure`); `settings_service.py:125-127` `provider_choices() -> list(LlmProvider.values)`; `llm-settings.ts:22` `export type LlmProvider = "anthropic" | "openai" | "ollama" | "opencode_go" | "mock"`. | Alle drei geforderten Stellen **bestätigt**. Wording-Korrektur: die Report-Aussage „über **keinen** Produktpfad konfigurierbar" ist zu weit — `LLM_PROVIDER=azure` per Env funktioniert (`providers.py:2060-2076` + `_read_env_config`). Es fehlen DB-Enum/REST/UI, aber der Env-Pfad existiert. |
| AUD-2026-09-061 | High | **TEILWEISE** | **Medium** | Konstanten exakt: `providers.py:390` `token_usage=42`, `:413` `token_usage=100`, `:438` `token_usage=200`, `:455` `token_usage=120`. Sie fließen unverändert in die Buchung: `router.py:286-292` `record_token_usage(..., input_tokens=result.token_usage or 0, output_tokens=0, ...)`. | Testdouble-Eigenheit **mit** Produktwirkung: der Mock ist per Default (`settings.py:704`) der aktive Provider, seine erfundenen Zahlen landen in `TokenUsageRecord` und damit in Budget/Aggregation. Ein **echter** Produktdefekt ist aber nur die Persistenz ohne Mock-Marker (spätere Vermischung mit echten Provider-Zeilen); im reinen Mock-Betrieb entstehen keine realen Kosten. High → Medium. |
| AUD-2026-09-062 | High | **TEILWEISE** | **Medium** | Code bestätigt: `router.py:286-292` `input_tokens=result.token_usage or 0, output_tokens=0`; `tasks.py:166-172` identisch. | Titel zu weit: **Provider**-Attribution **existiert** (`token_tracking.py:194-204` `.values("provider").annotate(...)`, `by_provider`). Fehlend ist nur die Input/Output-Trennung und ein Modellfeld. High → Medium. |
| AUD-2026-09-066 | High | **BESTAETIGT** | **Medium** | `dispatcher.py:177-178` `if state == "PENDING": return TaskStatusResult(task_id=task_id, status="pending")` — kein ETA/Deadline; Dispatch `:149-151` `run_capability.apply_async(args=[...])`. Celery liefert für unbekannte Task-IDs ebenfalls `PENDING`. | Sachverhalt korrekt. Kein Datenverlust (Task läuft nach Worker-Rückkehr), reine Beobachtbarkeitslücke → High → Medium. |
| AUD-2026-09-054 | Medium | **BESTAETIGT** | Medium | `providers.py:1549-1550` `# Ollama does not expose token counts ...` / `token_usage = data.get("eval_count") or None` — `prompt_eval_count` wird verworfen. | Wortlaut und Zeile korrekt. |
| AUD-2026-09-056 | Medium | **UEBERZOGEN** | **Low** | Task-Decorator ohne explizite Limits: `tasks.py:77` `@shared_task(bind=True, name="llm_adapter.run_capability")`. **Aber globales Limit existiert:** `settings.py:850-851` `CELERY_TASK_SOFT_TIME_LIMIT = max(...160)` / `CELERY_TASK_TIME_LIMIT = max(...180)`, wirksam über `celery.py:14` `app.config_from_object('django.conf:settings', namespace='CELERY')`. | „kein Abbruch" ist **falsch**: es greift ein globales Hard-Limit 180 s. Richtig bleibt nur „kein limit am Decorator / kein Per-Task-Override". Medium → Low. |
| AUD-2026-09-059 | Medium | **BESTAETIGT** | Medium | Viermal die unsichere Form: `providers.py:1114-1118`, `:1160-1164` (`if hasattr(message, "usage")`), `:1216-1220`, `:1270-1274`. Die OpenAI/Azure/OpenCode-Pendants nutzen korrekt `if response.usage else None` (`:1361`, `:1704`, `:1896`). | Latenter Defekt bei `usage=None` bestätigt; die realen Anthropic-SDK-Antworten tragen `usage`, der Trigger ist ein nicht-standardkonformer/Proxy-Response. Medium grenzwertig, aber vertretbar. |
| AUD-2026-09-060 | Medium | **BESTAETIGT** | **Low** | `providers.py:829` `return json.dumps([])` als Fallthrough für unbekannte `purpose`. | Sachverhalt korrekt. Wirkung begrenzt: `purpose` ist Entwickler-kontrolliert, mehrere Aufrufer behandeln den Mock-Fallback explizit (z. B. `bundle_compression_service`). Kein Nutzer-Input. Medium → Low. |
| AUD-2026-09-063 | Medium | **BESTAETIGT** | **Low** | Fail-open belegt: `token_tracking.py:123-129` `except Exception ... logger.warning(...)`; `:162-165` `return 0` bei Query-Fehler; `:233-243` `is_over_daily_limit()` → `False` ohne Limit. | Der Fail-open ist im Modul-Docstring **bewusst** dokumentiert. Es fehlt tatsächlich ein Health-Signal, aber der Effekt ist eine dokumentierte Design-Entscheidung (Überlappung mit AUD-231) → Medium → Low. |
| AUD-2026-09-065 | Medium | **TEILWEISE** | **Low** | In `checks.py` existieren nur `W001`/`W002`/`W003` (`checks.py:40-50`), **kein** `LLM_API_KEY`-Check. **Aber Abdeckung existiert zur Laufzeit:** `admin_ops/health_rest.py:273-278` `if not settings.LLM_API_KEY: return {..., STATUS_DEGRADED, "provider=..., but LLM_API_KEY is not set"}`, plus realer Probe-Call `:304-324`. | „Kein System-Check" ist wörtlich wahr, die Implikation „ungedeckt" ist **überzogen**. Zudem mappt ein fehlender Key via `AuthenticationError` → `LLM_PROVIDER_ERROR` sichtbar (kein stiller Ausfall). Medium → Low. |
| AUD-2026-09-067 | Info | **BESTAETIGT** (Sachverhalt) | Info | `_NullCircuitBreaker` definiert in `resilient_transport.py:159-175`; Auswahl in `:178-196` `_breaker_for(...)` `except Exception: ... return _NullCircuitBreaker()`. | **Fehlzitat:** die Register-/Report-Angabe `audit_logger.py:174-191` zeigt auf die Audit-Write-Fehlerbehandlung (`except Exception ... warnings.warn`), **nicht** auf den Circuit-Breaker. Sachverhalt korrekt, Ort falsch. |

**Zitierprüfung.** Alle zitierten `file:line` der Targets wurden inhaltlich geprüft.
Fehlzitat: **AUD-2026-09-067** (`audit_logger.py:174-191` → richtige Stelle
`resilient_transport.py:159-196`). Nebenaussage-Fehlzitat: **AUD-2026-09-053**
(`.env.example:189` ist `gpt-4o`, nicht „retired").

---

## 2. Register-Quercheck

1. **052 Klassifikations-Widerspruch im Register selbst.** §3 Master-Zeile 192 führt
   Klassifikation `NEU` und CR-Track `BESTAETIGT (CR-20-Nachbar; #118)`; der
   WP-Report (Z. 1224) führt `BESTAETIGT`. §5 (Z. 533) wiederholt `NEU`. Das ist
   inkonsistent, nicht schweregradrelevant.
2. **067 falscher Ort** (siehe oben) — Fehlzitat in §3 Zeile 458 **und** in
   `AUDIT_EVIDENCE`-Querverweisen.
3. **063 Wortlautfehler.** Registertext „Fail-open des Budgets ist vollständig
   **laut**" ergibt keinen Sinn; gemeint ist „vollständig **offen**" (bzw. „greift").
4. **056 Setzung vs. globale Settings.** Weder Register noch Report erwähnen die
   globalen `CELERY_TASK_TIME_LIMIT`/`CELERY_TASK_SOFT_TIME_LIMIT`; die
   Behauptung „kein Abbruch" ist dadurch widerlegt.
5. **065 Doppelspur.** Weder Register noch Report erwähnen den vorhandenen
   Laufzeit-Check `admin_ops/health_rest.py:273`.
6. **052/053 Retirement.** Das Register behandelt die externen Retirement-Daten
   (`2026-01-05`, `2026-10-23`) als gesichert; statisch/repo-intern sind sie
   **nicht** belegbar. Das ist die stärkste offene Unsicherheit beider Findings.
7. **Zahlen.** 42/100/200/120 exakt; „12 Requests" nachgerechnet korrekt;
   „5 HTTP-Provider" korrekt. Keine Zählabweichung gefunden.

---

## 3. Verdikt-Zählung (Targets, n=15)

- **BESTAETIGT: 9** — 054, 055, 057, 058, 059, 060, 063, 066, 067
- **TEILWEISE: 5** — 052, 053, 061, 062, 065
- **UEBERZOGEN: 1** — 056 (Fakt bestätigt, Schweregrad/Wirkung falsch)
- **FALSCH: 0**
- **UNTERSCHAETZT: 0**
- **NICHT VERIFIKABAR: 0** (als Gesamtfinding; **Teilaussagen** in 052/053 sind
  NICHT VERIFIKABAR)
- **KEIN REQOGNILOOM-BEZUG: 0**

> Korrigierte Schweregrade: 052 Critical→High · 056 Medium→Low · 060 Medium→Low ·
> 061 High→Medium · 062 High→Medium · 063 Medium→Low · 065 Medium→Low ·
> 066 High→Medium. **8 von 15** Schweregraden sind zu hoch angesetzt.

---

## 4. Key-Verdikte

1. **052 TEILWEISE (Critical→High).** Der Anthropic-Default ist tatsächlich
   wirksam (`providers.py:1080` + `:853` + `:120-121` + `:167-168`; `LLM_MODEL`
   leer in `settings.py:707`/compose). Die Aussage „seit 2026-01-05 retired" ist
   **NICHT VERIFIKABAR** (externe Tatsache). Der Trigger ist opt-in
   (`LLM_PROVIDER=anthropic`), der Shipped-Default ist `mock` → kein Critical.
2. **055 BESTAETIGT.** Die 12-Request-Amplifikation ist statisch exakt
   nachvollziehbar: 4 PolicyEngine-Versuche (`resilient_transport.py:39,279-285`;
   `policy_engine.py:92-93`) × SDK-Default 2 Retries (kein `max_retries` in
   `providers.py:1100/1347/1689`) = 12.
3. **057 BESTAETIGT (verschärft).** `decompose_requirement` blieb als einziger der
   drei Parser ungehärtet, obwohl `validate_artifact`/`check_consistency` für
   #576 bereits Fallback-Parser haben (`providers.py:984-1064`); der Roh-Fehler
   erreicht den Client über `dispatcher.py:187-193`.
4. **056 UEBERZOGEN (Medium→Low).** Ein globales Celery-Hard-Limit von 180 s
   existiert (`settings.py:850-851` via `celery.py:14`); „kein Abbruch" ist falsch.
5. **061/062 TEILWEISE (High→Medium).** Beides sind echte, aber **Mess-/Kosten-**
   Defekte, keine Funktionsausfälle. 062 überzeichnet zudem (Provider-Aggregation
   existiert, `token_tracking.py:194-204`).

---

## 5. NEU-AUDIT-LUECKE — übersehene LLM-Probleme

| # | Sev | Ort | Befund | Evidenz |
|---|---|---|---|---|
| N1 | Medium | `backend/llm_adapter/providers.py:1504-1508` vs. `:116-118` | **Falscher Env-Variablenname in der Fehlermeldung:** `OllamaProvider.__init__` wirft „Set `OLLAMA_BASE_URL` environment variable.", aber `_read_env_config` liest ausschließlich `LLM_API_BASE_URL`/`LLM_BASE_URL`. Ein Operator, der der Meldung folgt, konfiguriert wirkungslos. | `providers.py:1507` Zitat; `.env.example:193` dokumentiert korrekt `LLM_BASE_URL`. |
| N2 | Medium | `backend/llm_adapter/providers.py:155-172` | **Silenter Provider-Fallback bei DB-/RLS-Ausfall:** `_apply_db_settings` fängt `Exception` und gibt die unveränderte Env-Config zurück. Ein DB-Ausfall oder eine fehlerhafte RLS-Policy ersetzt damit still die mandantenspezifisch konfigurierte (echte) Provider-Konfiguration durch die Env-Config — potenziell `mock`. Kein Log auf `warning`-Ebene (nur `logger.debug`). | `providers.py:170-172` `except Exception: logger.debug(...); return cfg`. Nicht durch 052/063/065 abgedeckt. |
| N3 | Low | `backend/llm_adapter/providers.py:1675` | **Zweiter retired-Default derselben Klasse wie 053, aber unbenannt:** `AzureOpenAiProvider.MODEL_NAME = "gpt-4"`. AUD-053 zitiert nur `providers.py:1333` (OpenAI) — die Azure-Kopie fehlt. | `providers.py:1675`; gleiche Auflösung `:853`; Default-API-Version hart `"2024-02-01"` (`:1693`). |
| N4 | Low/Medium | `deploy/docker-compose.yml:596-599` vs. `router.py:110-113` | **`LLM_CAPABILITIES` wird in Compose nicht explizit gemappt** (nur via `env_file: .env`, `compose:577`). Fehlt die Variable, liefert `_read_enabled_capabilities()` ein leeres Set → **alle** Capabilities geben `LLM_NOT_CONFIGURED` zurück (`router.py:209-223`), ohne Startup-Check. Ein minimales Deployment, das nur die `environment:`-Keys setzt, fährt mit stumm deaktivierten AI-Funktionen. | `router.py:110-113`; `.env.example:149` hat die Variable, Compose mappt sie nicht. (REQ-163 deckt den `.env.example`-Teil, nicht den fehlenden Check/Compose-Key.) |
| N5 | Low | `backend/llm_adapter/providers.py:113,125-126` | **Ungeschützte Env-Typparsing beim Provider-Bau:** `int(os.environ.get("LLM_TIMEOUT", "30"))` sowie `float(...)` für `MOCK_LLM_DELAY`/`MOCK_LLM_ERROR_RATE` werfen `ValueError` bei nicht-numerischem Wert — zur Provider-Instanziierung (Request-Pfad/Worker), nicht beim Start. Kein System-Check. | `providers.py:113` `timeout=int(os.environ.get("LLM_TIMEOUT", "30"))`; `:125-126`. |

**Bewusst nicht als Lücke geführt:** der `hasattr`-Bug in `audit_logger.extract_token_usage`
ist bereits korrekt defensiv (`audit_logger.py:71-73` `getattr(usage, None)`);
`LLM_CAPABILITIES`-Fehlkonfiguration ist teilweise durch REQ-163 getrackt; die
Ollama-`eval_count`-Lücke ist AUD-054.

---

*Read-only Review. Kein Produktcode geändert, kein Push. AUDIT_EVIDENCE/* nur als
Kontext, nicht als Beweis verwendet.*
