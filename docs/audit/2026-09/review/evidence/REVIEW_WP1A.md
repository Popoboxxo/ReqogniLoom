---
type: REVIEW
scope: "WP-1a (MCP Server) — adversarial second review"
status: final
date: 2026-10-01
author_agent: backend-reviewer
branch: chore/audit-review-2026-09
method: read-only static verification against real product source (HEAD 10dc620f); audit-owned AUDIT_EVIDENCE/* explicitly NOT used as proof; Docker daemon DOWN → no live reproduction
targets:
  - AUD-2026-09-030
  - AUD-2026-09-031
  - AUD-2026-09-032
  - AUD-2026-09-033
  - AUD-2026-09-034
  - AUD-2026-09-035
  - AUD-2026-09-036
  - AUD-2026-09-037
  - AUD-2026-09-039
  - AUD-2026-09-041
  - AUD-2026-09-042
  - AUD-2026-09-043
  - AUD-2026-09-045
  - AUD-2026-09-046
  - AUD-2026-09-047
  - AUD-2026-09-048
  - AUD-2026-09-049
  - AUD-2026-09-050
  - AUD-2026-09-051
---

# REVIEW_WP1A — adversarial second review of the WP-1a MCP-Server findings

**Scope.** Independent, read-only falsification attempt of the WP-1a register
claims (`docs/audit/2026-09/AUDIT_FINDINGS.md` §3/§5, detail in
`AUDIT_EXTERNAL_INTEGRATIONS.md` §WP-1a). Findings-ID block 030–051.
The audit's own `AUDIT_EVIDENCE/*` was **not** used as proof; every verdict is
derived from product code at HEAD `10dc620f` (`chore/audit-review-2026-09`).
Docker daemon is DOWN: live behaviours (Redis-outage hang, 65-case isolation
matrix, 12/12 manifest mutations, uvicorn access-log leak) are **runtime-only**
and are marked as such — a static mechanism that supports or refutes the claim
is given where one exists. No file outside
`docs/audit/2026-09/review/evidence/` was modified.

**Method.**
1. Recall: locate every cited `file:line` in the current source.
2. Adversary: try to falsify each claim; keep only what product code proves.
3. Cite the counter-evidence (or the supporting code) verbatim with `file:line`.
4. A claim is `BESTAETIGT` only if the cited location exists **and** the code at
   that location does what the finding says. Wrong citations are recorded even
   when the underlying claim survives.

---

## 2. Counter-evidence table (targets n=19)

| ID | orig sev | verdict | corr. sev | counter-evidence (`file:line` + quote) | note |
|---|---|---|---|---|---|
| AUD-030 | Critical | **TEILWEISE** | Critical (unverändert) | `backend/reqogniloom/settings.py:879-884` `CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}` — **kein** `OPTIONS`, **kein** `SOCKET_TIMEOUT`. `throttling.py:164` `for throttle in (McpApiKeyRateThrottle(credential or ""), McpIpRateThrottle()):`; `views.py:272` `retry_after = check_mcp_rate_limit(request)` (ebenso `:401`, `:505`, `:736`). `rest_api/throttling.py:164-176` fängt nur `Exception` und ist sonst „fail-open" — ein **blockierender** Socket wirft keine Exception, der `try/except` greift also gerade im Redis-Ausfall nicht. | Mechanismus bestätigt. **Zahlenkorrektur:** „13 Endpoints" ist die Anzahl der *Proben* (12 Tools + `GET /mcp/sse/`), nicht der HTTP-Endpunkte. `mcp_server/urls.py` deklariert 4 Routen (`""`, `sse/`, `sse`, `messages/`); real betroffen sind alle 4 MCP-Handler-Methoden, die `check_mcp_rate_limit` rufen (HTTP `get`/`post`, messages `post`, SSE `get`), × 2 Mounts (`/mcp/`, `/api/v1/mcp/`). |
| AUD-031 | Critical | **BESTAETIGT** | Critical (unverändert) | `backend/reqogniloom/health.py:118-315`: `grep -n "cache\|Cache\|Redis" health.py` ⇒ **0** Treffer. `/health/` prüft nur `database`, `memory_backend`, `embedding_dimensions`, `llm_provider_env`, `csrf_cookie_secure_matches_auth`, Workflow-Definitionen. Register-§5-K-3 (`AUDIT_FINDINGS.md:525`) ist korrekt: DB-Ausfall ⇒ `health.py:134-135` `status["status"]="degraded"; http_status=503` / `:160-161` dito; Cache-/Worker-Ausfall wird gar nicht geprüft ⇒ `:312-315` `status["status"]="warning"`/`"ok"` bei HTTP 200. | Kern-Gap (keine Cache-/Worker-/Beat-Probe) bestätigt. Siehe §3 zum behaupteten 200-Widerspruch. |
| AUD-032 | High | **TEILWEISE** | High (unverändert) | Beide zitierten Stellen nutzen **denselben** String-Envelope: `views.py:291-304` (Batch) `"error_code": "INVALID_REQUEST"`; `views.py:311-325` (500) `"error_code": "INTERNAL_ERROR"`. Der numerische `code` entsteht erst im Handler: `protocol_handler.py:264-268` `rpc_code = ERROR_CODE_MAP.get(...); body = {"code": rpc_code, ...}`. | Kern (zwei inkompatible Hüllen auf demselben Endpunkt) stimmt: Transport-Rejections = `error_code` str vs. Handler-Fehler = `code` int. Die **zitierte Zeilenpaarung beweist den int/str-Kontrast aber nicht** (beide sind str) — Fehlzitat. |
| AUD-033 | High | **BESTAETIGT** | High (unverändert) | `protocol_handler.py:536` `clean_params = {k: v for k, v in params.items() if k != "api_key"}` liegt außerhalb jedes `try`; `params` kommt aus `:489` `params = frame.get("params") or {}` (nicht-dict, nicht-leer ⇒ roher Wert). `handle_http_request` (`:653-668`) → `handle` ohne Klammer-try; `views.py:311` fängt als generischen 500. | Bestätigt. Nuance: nur *nicht-leere* Nicht-dicts (`[]`, `""` sind falsy ⇒ `{}`). |
| AUD-034 | High | **UEBERZOGEN** | **Medium** | `authentication.py:616` `effective_scope = "write" if scope is None else scope` (User-Keys ungeprüft) — bestätigt. **Aber** der einzige Produkt-Aufrufer validiert: `rest_api/api_key_views.py:290-301` `scope = normalize_api_key_scope(raw_scope); if scope_present and scope is None: … VALIDATION_ERROR` (seit `ac0ecfc3b`, 2026-09-16, **vor** der Audit-Basis `abd61aed`). Kein MCP-Tool ruft `create_api_key`. | Service-Vertragslücke, aber über die ausgelieferte API nicht erreichbar ⇒ High nicht tragfähig. Zusatz: ein unbekannter Scope denied **alles** (`authorization.py:151-153,227-232`), nicht nur Writes. |
| AUD-035 | High | **BESTAETIGT** | High (unverändert) | `authentication.py:511-515` `ApiKey.unscoped.select_related("user").filter(key_hash__in=candidates).first()`; `:562` `tenant_id=api_key.user.tenant_id`. | `ApiKey.tenant_id` wird im Auth-Pfad nicht zur Tenant-Ableitung genutzt. Bestätigt. |
| AUD-036 | High | **BESTAETIGT** | High (unverändert) | `mcp_server/tools/generic.py:512-515` `except Exception: logger.exception(...); return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")`, während `:496-499` `ValidationError`/`NotFoundError` korrekt mappt. REST: `rest_api/views.py:_EXC_TO_CODE` (per Report `:217`) mappt dieselbe `ValidationError` auf 400. | Transport-Paritätsbruch bestätigt. |
| AUD-037 | Medium | **BESTAETIGT** | Medium (unverändert) | `AGENTS.md:8,30,58` „31 Tool-Gruppen-Präfixe, 215 Tools"; `README.md:77` „35 tool-group prefixes … 219 individual tools"; `README.md:1191` „Tool Groups (25 prefixes)". Manifest-Messung: `docs/agent-templates/tool-manifest.json` `tool_count=219`, `len(tools)=219`, 35 Präfixe, 139 `is_write=true` / 80 `false`. | Alle drei Teilaussagen (215/31 stale, 25-vs-35-Selbstwiderspruch, stdio-Phantom) bestätigt. |
| AUD-039 | Medium | **BESTAETIGT** | Medium (unverändert) | `protocol_handler.py:469` `if frame is None or frame.get("_parse_error"):` — `None` ⇒ Short-circuit ⇒ PARSE_ERROR `-32700`; `str/int/bool` ⇒ `.get` ⇒ `AttributeError` ⇒ `views.py:311` 500. `JsonRpcValidator.validate` (`:229-241`) prüft den `id`-Typ nicht. | Bestätigt. |
| AUD-041 | Medium | **BESTAETIGT** | Medium (unverändert) | `views.py:176-190` begründet die Ablehnung von `?api_key=` mit „query strings are routinely written to proxy and web-server access logs … would leak … API keys". `grep -rn "redact\|REDACT" backend` ⇒ **0** Produktions-Redaction für `reqlo_*`. | Statisch bestätigt: die App *wertet* Query-Keys nicht aus, verhindert aber die *Aufzeichnung* durch den uvicorn-Access-Log nicht. Live-Reproduktion (Log-Zeile) Docker-Down blockiert → Live-Lücke. |
| AUD-042 | Medium | **FALSCH** | — | `mcp_server/tools/interview.py:85-95` deklariert `session_kind` (`enum: ["single","multi"]`), **kein** `mode`; `:305-315` `artifact_type = params.get("artifact_type")` (optional), `session_kind = params.get("session_kind") or …SINGLE`; `:322` wird an den Service durchgereicht. Blame: Multi-Support seit `17ee5b667` (2026-08-25), **vor** der Audit-Basis. Die zitierte Stelle `:181-202` ist `interview.formalize`, nicht `interview.start`. | Multi-Interview ist über MCP startbar (`session_kind="multi"`, `artifact_type` weggelassen). Zitat und Aussage beide falsch. |
| AUD-043 | Medium | **TEILWEISE** | Medium (unverändert) | Manifest `comment.create/list/resolve` deklarieren nur `artifact_id`/`text` bzw. `id` — **kein** `workspace_id` (bestätigt). Die Workspace-Ableitung läuft stattdessen über `workspace_scope.py:115,172` `"comment.create": (("artifact_id","artifact"),)`; `comment_service.py:154-166` löst Artefakt+Workspace binnen Tenant auf und autorisiert WRITE. | Schema-Lücke bestätigt. Das behauptete Symptom „Artifact not found" auf ein *anderes-Workspace*-Artefakt ist statisch nicht reproduzierbar (der Service würde eher `PermissionDeniedError` liefern) → Live-Prüfschritt fehlt. |
| AUD-045 | Low | **BESTAETIGT** | Low (unverändert) | `protocol_handler.py:226-241`: `validate()` prüft `jsonrpc`, `method`, `id`-Präsenz — **keinen** `id`-Typ; `request_id = frame.get("id")` (`:476`) wird unverändert zurückgegeben. | Bestätigt. |
| AUD-046 | Low | **BESTAETIGT** | Low (unverändert) | `generic.py:493` `obj = self._create_method(ctx=…, **kwargs)` → `glossary_service.py:166` `if not term.strip() …` ⇒ `AttributeError` bei `term: 42`; gefangen von `generic.py:512` ⇒ INTERNAL_ERROR. | Bestätigt. |
| AUD-047 | Low | **BESTAETIGT** | Low (unverändert) | `glossary_service.py:156-167` enthält keinerlei Längenprüfung. `persistence/models.py:2387` `definition = models.TextField()` ⇒ keine DB-Grenze; `:2386` `term = models.CharField(max_length=255)` (Term ist DB-seitig begrenzt). | Bestätigt für `definition` (das im Live-Test genutzte Feld). |
| AUD-048 | Low | **BESTAETIGT** | Low (unverändert) | `mcp_server/tests/test_tool_manifest_drift.py:83` `@pytest.mark.django_db` über `test_committed_manifest_matches_live_registry`; `build_manifest()` wird ohne DB-Zugriff importiert (`:23-26`). | Bestätigt: der Guard erzwingt DB-Setup (Test-DB-Erstellung), obwohl die verglichene Registry-Build-Funktion keine DB braucht. |
| AUD-049 | Info | **BESTAETIGT** | Info (unverändert) | `reqogniloom/urls.py:52` `path("mcp/", include("mcp_server.urls"))`; JSON-Fallback `:59` `re_path(r"^api/v1/", api_not_found)` ist auf `/api/v1/` beschränkt; Kommentar `:57-58` „so /admin/, /mcp/ … keep Django's HTML 404". | Bestätigt. |
| AUD-050 | Info | **BESTAETIGT (WIDERLEGT)** | Info (unverändert) | `authentication.py:562` `tenant_id=api_key.user.tenant_id` ⇒ der vermeintliche „Tenant-B"-Key eines Users mit `User.tenant_id = A` operiert in A; `views.py`/`tool_registry.py` leiten den Tenant nirgends aus `ApiKey.tenant_id` ab. | Widerlegung bestätigt: kein Cross-Tenant-Leak; die Ursache ist AUD-035. Die 65/65-Isolationsmatrix ist live (Docker down) nicht nachprüfbar. |
| AUD-051 | Info | **TEILWEISE** | Info (unverändert) | `test_tool_manifest_drift.py:102-157` vergleicht die **komplette** Signatur (`name`, `is_write`, `prefix`, `description`, `inputSchema` über `_canonical`) plus `tool_count` und failt bei nicht erreichbarem Manifest. | Guard-Stärke aus Produktcode bestätigt. Die Zahl **12/12 Mutationen** ist ein audit-eigener Nachbau und nicht aus Produktcode ableitbar → NICHT VERIFIZIERBAR (fehlender Prüfschritt: Mutationslauf reproduzieren). |

---

## 3. Register-Quercheck (insb. der AUD-031-Widerspruch)

**Auftragsannahme korrigiert.** Der Auftrag fragt, ob `degraded` „wie
WP-1a/Register behauptet" HTTP 200 liefert. Das ist **nicht** die Register-Aussage:

* Register §3 (`AUDIT_FINDINGS.md:191`) sagt für **Redis-/Worker-Ausfall** „weiterhin
  `200 ok`" — das ist korrekt, weil diese Abhängigkeiten gar nicht geprüft werden
  (`health.py` = 0 Cache-Referenzen).
* Register §5 K-3 (`:525`) stellt ausdrücklich klar: „**DB-Ausfall liefert korrekt
  503.** Der belegte Fehlfall ist der **Cache-/Redis-Ausfall** bei gesunder DB — dort
  bleiben `status="ok"` und HTTP 200 (`:312-315`)."
* `REVIEW_WP1C.md:32,38-43,60-62` prüft die Aussage von **AUD-129** (WP-1c), nicht von
  AUD-031: Register `:228` behauptet „`degraded` liefert HTTP **200**". Das ist gegen den
  Code **falsch**: `health.py:134-135` und `:160-161` setzen bei `status="degraded"`
  **immer** `http_status = 503`.

**Ergebnis:** Es gibt keinen Widerspruch *innerhalb* von AUD-031. Der Widerspruch ist
`AUD-129`/`AUDIT_INFRASTRUCTURE.md` (degraded ⇒ 200) vs. Code. `REVIEW_WP1C` hat recht;
das Register hat AUD-031 in K-3 bereits korrekt präzisiert. Die WP-1a-Reportzeile
(`AUDIT_EXTERNAL_INTEGRATIONS.md:278`) „/health/ meldet „ok"" beschreibt den
Cache-Ausfall und ist damit ebenfalls korrekt.

---

## 4. Verdikt-Zählung (Zielmenge, n=19)

* **BESTAETIGT: 13** — 031, 033, 035, 036, 037, 039, 041, 045, 046, 047, 048, 049, 050
* **TEILWEISE: 4** — 030 (Mechanik ja / Zahl nein), 032 (Kern ja / Fehlzitat), 043 (Schema ja / Symptom unbelegt), 051 (Guard ja / 12-12-Zahl audit-seitig)
* **UEBERZOGEN: 1** — 034 (High → **Medium**)
* **FALSCH: 1** — 042
* **NICHT VERIFIKABAR: 0** (Live-Lücken sind je Befund als Prüfschritt ausgewiesen)
* **KEIN REQOGNILOOM-BEZUG: 0**

Severity-Korrekturen der Zweitprüfung: **1** (AUD-034 High → Medium).

---

## 5. Key-Verdikte

1. **AUD-030 TEILWEISE (Critical bleibt).** Kein `SOCKET_TIMEOUT`/`OPTIONS` in
   `CACHES` (`settings.py:879-884`) und jeder MCP-Handler geht zuerst durch
   `check_mcp_rate_limit` (`views.py:272,401,505,736` → `throttling.py:164`). Der
   4-fache Zustellungspunkt bleibt. Der bestehende „fail-open"-Schutz
   (`rest_api/throttling.py:164-176`) greift **nur gegen Exceptions**, nicht gegen einen
   blockierenden Redis-Socket ohne Timeout — er entschärft den Befund also gerade nicht.
   Korrektur: „13" sind Proben, nicht Endpunkte.

2. **AUD-031 BESTAETIGT (Critical).** Cache/Worker/Beat werden nicht geprüft; `degraded`
   liefert sehr wohl 503 (`health.py:134-135,160-161`). Der echte Defekt ist die
   **fehlende Probe**, nicht ein falsches 200. Der Register-Stand (K-3) ist korrekt; die
   129-Kurzformulierung ist es nicht.

3. **AUD-042 FALSCH.** `interview.start` nutzt `session_kind` (nicht `mode`), akzeptiert
   `multi` ohne `artifact_type` (`interview.py:85-95,305-315,322`) — seit 2026-08-25.
   Zitierte Stelle ist zudem `interview.formalize`. Finding gehört geschlossen.

4. **AUD-034 UEBERZOGEN (High → Medium).** Die Service-Funktion akzeptiert
   beliebige User-Scopes (`authentication.py:616`), aber die einzige ausgelieferte
   Aufrufstelle validiert (`api_key_views.py:290-301`). Kein erreichbarer
   „stumm schreibunfähiger" Key über die API/MCP.

5. **AUD-035/AUD-036 BESTAETIGT.** `ApiKey.tenant_id` ist im Auth-Pfad dekorativ
   (`authentication.py:511-515,562`); MCP maskiert Domänen-Exceptions
   (`generic.py:512-515`) gegen REST-400 — beides sauber belegt.

---

## 6. NEU-AUDIT-LUECKE (nicht im WP-1a-Register)

1. **Tool-Zahl 218 vs. 219.** `.meta-config/project.yaml:103,150,151,180,236,305,365`
   (und die daraus generierten Agent-Prompts) nennen „35 Tool-Gruppen-Präfixe mit
   **218** Tools". Gemessen am Manifest: `tool_count = 219`, `len(tools) = 219`
   (`docs/agent-templates/tool-manifest.json`). Die 218 ist eine dritte, bisher nicht
   registrierte Doku-Drift neben AGENTS.md (215/31) und README (25/35). → **Neu, Medium.**

2. **„Fail-open if the cache is down" ist irreführend.** `rest_api/throttling.py:165-176`
   dokumentiert Fail-open für den Cache-Ausfall, fängt aber nur `Exception`. Genau der
   Redis-Ausfall-Szenariofall (Blockieren ohne Timeout) wird **nicht** abgedeckt. Der
   Kommentar sollte den Unterschied „Verbindungsfehler (fail-open) vs. Hang (kein
   Schutz)" benennen. → **Neu, Low** (Präzisierung zu AUD-030).

3. **AUD-042-Zitat-Klasse.** Die Zweitprüfung fand mit AUD-042 nicht nur eine falsche
   Aussage, sondern auch ein falsches `file:line`-Zitat (formalize statt start). Analog
   ist AUD-032s Zeilenpaarung irreführend. Empfehlung: Zitat-Audit als eigener
   Gate-Schritt, da falsche Anker die Reproduktion der Findings verhindern.

---

## Anhang — geprüfte, aber nicht im Register korrigierte Stellen

* `backend/mcp_server/urls.py:18-26` — 4 MCP-Routenbestandteile.
* `backend/auth_tenancy/services/authorization.py:151-153,227-232` — unbekannter Scope
  ⇒ Tier −1 ⇒ **alle** Operationen denied (präzisiert AUD-034).
* `backend/application/comment_service.py:154-166` — Artefakt/Workspace-Auflösung mit
  `PermissionDeniedError`-Pfad (AUD-043).
* `backend/persistence/models.py:2386-2387` — `term` 255 vs. `definition` TextField
  (AUD-047).
