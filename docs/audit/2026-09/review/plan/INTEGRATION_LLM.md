---
type: PLAN
scope: audit-review-2026-09-integration-llm
status: final
date: 2026-10-01
author_agent: planner
epic: INT — Externe Schnittstellen & LLM
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic INT — Externe Schnittstellen & LLM

> Detailplan. `349` ist toter Link (070 widerlegt) — Umsetzung nutzt nur den CSV-`success`-Kern.
> `052`/`053`-Retirement-Daten sind NICHT VERIFIKABAR; Fix zielt auf die Konfigurationsfalle.
>
> **Verträge (`plan/INTERFACE_CONTRACTS.md`, api-specialist).** INT-01/INT-04/INT-06
> nutzen das Import-Ergebnismodell §2 (`succeeded/skipped/failed`, `success ⇔ failed==0`,
> `Idempotency-Key`), INT-05 die Pagination §4, INT-07 den JSON-RPC-2.0-Fehlerkontrakt §5.
> **ADR-blockiert = Vertragsvorschlag, kein Sofort-Fix:** Semantikwechsel `success`
> (INT-01), HTTP 207/422 und die Idempotenz-Wahl hängen an **ADR v** (§2.8/§6);
> sofort zulässig sind nur BOM-Fix (`utf-8-sig`), `errors`-nie-leer, `request_id`,
> `page`-404 und MCP-`-32602`. Kein widerlegtes Finding (`042`, `283`, `204`) ist hier
> Fixgegenstand.
>
> **Aufwand.** Verbindliche PT-Spannen: `plan/EFFORT_ESTIMATES.md` §1; die Angaben
> `Aufwand: S/M/L` in dieser Datei sind nur Groborientierung.

## INT-01 — ReqIF `success`-Vertrag + Savepoint wirksam (P0, W1)

- **Findings:** 071, 079
- **`349`:** toter Link auf das **widerlegte `070`** — nur Register-/Doku-Korrektur
  (`DOC-06`), **kein** eigenständiger INT-01-Fixgegenstand.
- **Ort:** `application/reqif_import_service.py:482-489` (`success=True` hart; Docstring
  `:273-287`), `:413-414`/`:688-703` (Savepoint wird geschluckt), `:429-443`, `to_dict :296-304`
- **Zielverhalten (ADR-blockiert = Vertragsvorschlag `INTERFACE_CONTRACTS.md` §2; nicht
  umsetzbar bis ADR v):** **ADR (v) entscheidet** Fehlersemantik; danach: `success=false`
  (bzw. 207/422), sobald Objektfehler auflaufen; die per-Objekt-Savepoint-Rettung rollt ein
  fehlerhaftes Objekt tatsächlich zurück, ohne die Folge-Query auf einer abgebrochenen
  Transaktion zu töten. Der Vertrag in `:273-287` wird korrigiert (nicht nur `:483`).
- **Akzeptanz:** ReqIF-Import mit einem fehlerhaften Objekt ⇒ Antwort meldet `success=false`
  + strukturierte Fehler; die übrigen Objekte bleiben importiert (kein Gesamtabbruch).
- **Test:** pytest (Import-Mutation) + Live-Nachtest mit Test-Workspace (vom Review als
  fehlender Schritt benannt).
- **Aufwand:** M · **Risiko/Rollback:** Clients, die auf `success:true` prüfen → Deprecation,
  optionales Kompatibilitätsfeld. · **Deps:** ADR v · **ADR:** v

## INT-02 — LLM-Defaults/Provider-Auswahl (P1, W2)

- **Findings:** 052, 053, 058, N8, 346 (=052, zusammengeführt)
- **Ort:** `llm_adapter/providers.py:1080,853,1333,1675` (MODEL_NAME-Defaults, harrend
  `claude-3-opus-20240229`/`gpt-4`); `models.py:2417-2421` (kein `azure`), `llm-settings.ts:22`;
  `OllamaProvider`-Fehlermeldung `providers.py:1504-1508` (falscher Env-Name);
  `_apply_db_settings :155-172` (silenter Env-Fallback); `int()/float()`-Env `:113,125-126`
- **Zielverhalten:** Modell-Defaults sind nicht-retired/konfigurierbar; `azure` im DB-Enum,
  REST und UI wählbar; Fehlermeldung nennt den **korrekten** Env-Namen (`LLM_BASE_URL`);
  Env-Typparsing abgefangen; DB-/RLS-Ausfall loggt ≥ WARNING statt still auf `mock` zu fallen.
- **Akzeptanz:** `LLM_PROVIDER` aller fünf Provider ist über DB/UI wählbar; ungültiges
  `LLM_TIMEOUT` startet kontrolliert; Provider-Ausfall erzeugt Logzeile.
- **Test:** pytest (Config-Auflösung je Provider) + Frontend-Unit-Test für `azure`. ·
  **Aufwand:** M · **Risiko/Rollback:** Modell-ID-Wechsel → Env/DB-Override, reversibel. ·
  **Deps:** — · **ADR:** —

## INT-03 — LLM-Parser-Härtung, Retry-Amplifikation, Usage (P1, W2)

- **Findings:** 057, 055, 059, 061, 062, 054
- **Ort:** `providers.py:1215,1407,1595,1749,1941` (nackte `json.loads`), `:1100,1347,1689`
  (kein `max_retries`), `:1114-1164,1216-1220,1270-1274` (`hasattr` statt `usage`),
  Mock-Zahlen `:390,413,438,455`, `:1549-1550` (`prompt_eval_count` verworfen)
- **Zielverhalten:** `decompose_requirement` erhält denselben robusten Fallback-Parser wie
  `validate`/`consistency`; SDK-`max_retries=0` (Amplifikation 12→4) oder Policy angepasst;
  `usage=None` sicher; Mock-Usage wird markiert (keine Vermischung mit echten Kosten);
  Ollama liefert `prompt_eval_count`.
- **Akzeptanz:** Fehlerhafter Provider-Body ⇒ freundliche Fehlermeldung, kein Roh-Parsertext;
  Retry-Test zählt max. 4 Policy-Versuche × 1 SDK-Versuch; Mock-Records tragen `provider=mock`.
- **Test:** pytest (Parser-Feeds, Retry-Zähler, Usage-Aggregation). · **Aufwand:** M ·
  **Risiko/Rollback:** Retry-Reduktion ändert Resilienz → Policy-konfigurierbar. ·
  **Deps:** — · **ADR:** —

## INT-04 — CSV-Import: Dedupe/Idempotenz + BOM/Fehlermeldung (P1, W2)

- **Findings:** 072, 079, 080, 081, 083
- **Ort:** `application/import_service.py:662,695` (keine Dedupe), `:610` (`_map_status` nie
  ablehnend), `:300-314` (leere `errors`), `:346-354` (Quoting); `rest_api/views.py:8018`
  (`decode("utf-8")` ⇒ BOM); `export_service.py:372-376`/`settings_views.py:579-585`
- **Zielverhalten:** Import ist idempotent/dedupliziert (gemäß ADR v: `Idempotency-Key` oder
  fachliche Duplikaterkennung — **Vertragsvorschlag** `INTERFACE_CONTRACTS.md` §2.3, bis ADR v
  nicht umsetzbar); `errors` nie leer bei Rollback (**sofort zulässig**); BOM wird via
  `utf-8-sig` entfernt (**sofort zulässig**); irreführende Meldung durch
  Ursachen-beschreibende ersetzt.
- **Akzeptanz:** Zweifacher Import derselben Datei erzeugt keine Duplikate; BOM-Datei
  importiert korrekt; Fehlerantwort nennt die Ursache.
- **Test:** pytest (Import-Round-Trip, BOM-Fixture) + Live-Import im Test-Workspace. ·
  **Aufwand:** M · **Risiko/Rollback:** Dedupe könnte gewollte Duplikate verhindern →
  Konfiguration, reversibel. · **Deps:** ADR v, INT-01 · **ADR:** v

## INT-05 — REST-Pagination: ungepagte Listen + 500-vs-404 (P1, W2)

- **Findings:** 073, 074
- **Ort:** `rest_api/api_key_views.py:147-158`, `user_management_views.py:104-126`,
  `link_type_views.py:56-57,93-97` (nackte Arrays);
  `views.py:3111,8369` (Paginierung **im** `try` ⇒ DRF-`NotFound` ⇒ 500)
- **Zielverhalten:** Die 4 Listen-Endpunkte paginieren (`StandardPagination`); ungültiges
  `page` liefert **404** statt 500 (Paginierung außerhalb des `try` wie
  `WorkspaceViewSet.list` `:5335-5337`).
- **Akzeptanz:** `?page=0|abc|99999999` ⇒ 404 für trace-links/glossary; die 4 Listen liefern
  `count`/`next`.
- **Test:** pytest + Live-Nachtest (Statuscodes).
- **Aufwand:** M · **Risiko/Rollback:** Breaking für Clients, die Arrays erwarten →
  Deprecation, reversibel. · **Deps:** — · **ADR:** —

## INT-06 — OpenAPI/Fehlerkontrakt (P1, W2)

- **Findings:** 075, 076, 078, 090, 077
- **Ort:** `openapi.py:71-98` (unbenutzte `COMMON_ERROR_RESPONSES`); `reqif_export_service.py:394-409`;
  `views.py:8265` (ReqIF-Import ohne `requestBody`), `:8216-8217`; `settings.py:523,593,597-621`
  (`cookieAuth` unreferenziert); Fehlerbody ohne `request_id`
- **Zielverhalten:** Fehlerantworten sind im Schema deklariert (Ergebnis-Envelope gemäß
  **ADR v = Vertragsvorschlag** `INTERFACE_CONTRACTS.md` §1/§2); ReqIF-Import hat
  `requestBody`, Export deklariert `application/xml`; `reqIFVersion` ist korrekt/validierbar;
  `cookieAuth` referenziert oder entfernt; `request_id` im Body (Kopplung RES-07,
  **sofort zulässig**).
- **Akzeptanz:** `manage.py spectacular` läuft und Schema enthält die Responses/Bodies;
  ReqIF-XSD-Validierung gegen installiertes Paket.
- **Test:** `test_openapi.py` erweitert; Schema-Generierung im CI. · **Aufwand:** M ·
  **Risiko/Rollback:** Schemaänderung → dokumentiert, reversibel. · **Deps:** ADR v
  (`request_id`-Kopplung zu RES-07 ist **lose, kein Blocker** — `request_id` ist sofort
  zulässig; **keine** Cross-Wave-Abhängigkeit INT-06(W2)→RES-07(W3)) · **ADR:** v

## INT-07 — MCP-Fehlervertrag & Validierung (P2, W3)

- **Findings:** 032, 033, 036, 034, 045, 046, 047, 048, 037, N5
- **Ort:** `mcp_server/views.py:291-325` (str-Envelope) vs. `protocol_handler.py:264-268`
  (int `code`); `protocol_handler.py:536` (`clean_params` außerhalb try), `:489`;
  `tools/generic.py:496-499,512-515`; `authentication.py:616`; `glossary_service.py:156-167`;
  `test_tool_manifest_drift.py:83` (DB-Setup)
- **Zielverhalten:** Ein einheitlicher JSON-RPC-Fehlervertrag (int `code`), ungültige
  `params` ⇒ `-32602` statt 500, Eingabefehler ⇒ `VALIDATION_ERROR` statt `INTERNAL_ERROR`,
  `definition`-Längengrenze, Guard ohne unnötiges DB-Setup; Tool-Zahl-Doku = Manifest (219).
- **Akzeptanz:** Nicht-dict `params` erzeugt definierten Fehlercode; Tool-`term:42` ⇒
  Validierungsfehler; Manifest-Drift-Test ohne `django_db`.
- **Test:** pytest (MCP-Tool-Tests) + `test_tool_manifest_drift`.
- **Aufwand:** M · **Risiko/Rollback:** Fehlercode-Änderung bricht Clients → Spec-konform,
  dokumentiert. · **Deps:** INT-06 · **ADR:** —
