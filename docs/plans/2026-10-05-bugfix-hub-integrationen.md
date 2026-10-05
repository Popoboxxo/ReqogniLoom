# Bugfix-Hub — Arbeitsplan: Externe Anbindungen, Plugins, API & Integrationen

| Feld | Wert |
|---|---|
| **Status** | Entwurf zur Umsetzung |
| **Datum** | 2026-10-05 |
| **Basis** | `v1.8.0-beta.18`, Issue-Bestand 2026-10-05 |
| **Hub-Index** | [`docs/bugfix-hub/README.md`](../bugfix-hub/README.md) |
| **Bezug** | #1171 (One-Click-Client-Doku), #1153, #1155/#1156, #1164, #1177, #1185 |
| **Geltung** | Fremd-Clients/-Provider, MCP-Surface, REST-/OpenAPI, Plugins, Supply-Chain |
| **Nicht Teil** | Reine UI-/Datenmodell-Kampagnen, RLS-Härtung, SE-Kaskade (siehe Hub §2) |

---

## 0. Management Summary

Der Issue-Bestand enthält eine klar abgrenzbare Gruppe von Fehlern und Lücken an der
**Außengrenze** des Systems: Fremd-Harnesse, MCP-Server-Surface, REST-Contract, externe
LLM-Provider und Plugins. Diese Issues werden in **vier Fix-Bundles** (B1–B4) plus das
**Leit-Bundle B0** (Client-Onboarding, #1171) geordnet.

Leitprinzip: **Erst den Fremd-Vertrag beweisbar machen, dann schließen.** Jedes Issue gilt erst
als erledigt, wenn ein Smoke-Test gegen den betroffenen Client/Provider das erwartete Ergebnis
zeigt — nicht, wenn nur „der Code geändert" ist.

- **B0** setzt den bestehenden One-Click-Plan (Stufe 1) um: `docs/clients/` (DE/EN),
  `clients/registry.yaml` als Single Source of Truth, Installer/Verifier, CI-Gate.
- **B1** schließt die MCP↔REST-Paritätslücken (#1164, #1098, #1097) und dokumentiert die
  MCP-only-Flächen (#1101) sowie das Suchverhalten (#1170).
- **B2** härtet die externen Provider-Pfade: `score:null` (#1163), Honcho-Header (#1153),
  Preflight-Beleg (#1186) und das Fehler-Mapping bei LLM-Timeouts (#1165).
- **B3** bringt die Plugins auf den echten Serververtrag (#1152) und aktualisiert das
  vendored Bluepencil-Bundle (#988).
- **B4** vereinheitlicht den REST-Contract (#1177) und schließt den Info-Leak (#1185).

**Grobe Reihenfolge:** B4/B3-Sofortfixes (klein, risikolos) → B2 → B1 → B0-Doku → B0-Stores.

---

## 1. Zielbild und Definition „erledigt"

Jedes Bundle hat ein eigenes DoD. Übergreifend gilt für **jedes** Issue:

1. **Reproduktion** dokumentiert (Befehl + realer Ist-Zustand, wo möglich gegen Sandbox/Client).
2. **Fix** auf `feat/*`/`fix/*`, keine Änderung auf `main`.
3. **Verifikation** mit erwartetem Ergebnis (Smoke-Test oder Regressionstest im Repo).
4. **Close-Kommentar** am Issue mit Beleg; Status-Board im Hub auf `closed`.

---

## 2. Inventar — Bundles

| Bundle | Name | Issues | Prio-Mix |
|---|---|---|---|
| **B0** | Client-Onboarding / One-Click | #1171, #1169, #649, #92, #1138 | P1–P2 |
| **B1** | MCP-Surface-Parität | #1164, #1098, #1097, #1170, #1101, #1133 | P1–P3 |
| **B2** | Externe LLM-/Provider-Robustheit | #1153, #1186, #1163, #1165 | P1–P2 |
| **B3** | Plugin-Runtime & Fremd-Bundles | #1152, #988 | P2 |
| **B4** | API-Contract-Konsistenz | #1177, #1185 | P1 |

---

## 3. Bundles im Detail

### 3.1 B4 — API-Contract-Konsistenz (Sofortstart)

**Ziel:** Ein generischer REST-Client (SDK-Generator, Automation) kann alle Ressourcen ohne
Sonderfälle konsumieren; Fehlerantworten leaken keine DB-Interna.

**AP-B4.1 — Import-Fehlerantwort entschärfen (#1185)** · 0,5 PT
- `backend/application/import_service.py:426-442`: `type(exc): str(exc)` aus der
  Client-Antwort entfernen; intern loggen, nach außen generische Meldung + stabile
  `code` (Muster aus dem bestehenden Envelope).
- Test: Import mit absichtlich fehlerhafter Payload → Antwort enthält **kein** `psycopg`/
  Traceback-Fragment; Log enthält den vollen Fehler.

**AP-B4.2 — REST-Inkonsistenzen (#1177)** · 2–3 PT
1. `/api/v1/users/` auf paginierte Envelope umstellen (`{count,…,results}`) — Breaking Change
   nur mit Versionierung/Übergang; Entscheidung E1.
2. `/api/v1/reviews/` Collection-Root ergänzen (Liste delegiert an `pending/`-Daten).
3. Bindestrich-Schema: Ist-Zustand dokumentieren **oder** Alias-Routen ergänzen
   (`/testcases/` ↔ `/test-cases/` etc.) — Entscheidung E2.
4. `/openapi.json` (JSON) bereitstellen; `/api/schema/` mit korrektem `Content-Type`
   (`application/vnd.oai.openapi+json` bzw. `application/yaml`) ausliefern.

**DoD B4:** `openapi.json` per `Content-Type` korrekt abrufbar; `/users/` und `/reviews/`
im Envelope konsistent; kein DB-Interna-Leak; Regressionstests in `backend/rest_api/tests/`.

---

### 3.2 B3 — Plugin-Runtime & Fremd-Bundles

**Ziel:** Die ausgelieferten Plugins bedienen den **tatsächlichen** Serververtrag.

**AP-B3.1 — Hermes-Plugin `Cancel` → `interview.abandon` (#1152)** · 0,5–1 PT
- `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts`: `interviewAbandon()` ergänzen
  (Tool existiert serverseitig, write-gated; `session_id`-Guard wie `formalize`).
- `state.ts::cancelInterview()`: erst `interviewAbandon(sessionId)`, dann Liste neu laden;
  Fehler analog `formalizeInterview` behandeln. Veralteten Kommentar („no interview.abandon
  MCP tool exists") entfernen.
- Tests: `__tests__/mcpClient.test.ts` + `state.test.ts` — `cancelInterview` ruft
  `interview.abandon` mit `session_id`; veralteter Kommentar weg.

**AP-B3.2 — Bluepencil-Bundle re-vendorn (#988)** · 1 PT
- `frontend/public/bluepencil/latest/` aus einem Build mit Upstream-#15 neu vendorn,
  `latest.json` SHA256 synchronisieren, Frontend-Image neu bauen.
- Verifikation: Notiz eines eingeloggten Nutzers wird mit dessen Namen gespeichert,
  nicht `anonymous`; Export zeigt App statt `"unknown"` (letzteres ggf. Upstream-Rest).

**DoD B3:** `cancelInterview` schließt die Session serverseitig (`abandoned`); Bluepencil
speichert den realen Autor.

---

### 3.3 B2 — Externe LLM-/Provider-Robustheit

**Ziel:** Provider-Fehler und Provider-Antworten sind deterministisch, korrekt gemappt und belegt.

**AP-B2.1 — `score: null` normalisieren (#1163)** · 0,5 PT *(in Arbeit)*
- Helper `_score_or_default(value, default)` in `backend/llm_adapter/providers.py`; alle
  `float(data.get("score", X))`-Stellen (aktuell 20) darauf umstellen, **Default je Aufrufer
  erhalten** (0.0 für consistency/validation, 1.0 für derive).
- Test: `{"score": null, …}` → `score == default`, kein `TypeError`; ebenso `"abc"`,
  `[]`, fehlender Key.

**AP-B2.2 — Honcho-Dialektik-Header (#1153)** · 1–2 PT
- Konfigurationspfad prüfen: liest der Dialektik-Resolver
  `DIALECTIC_LEVELS__*__MODEL_CONFIG__OVERRIDES__PROVIDER_PARAMS__EXTRA_HEADERS__*`?
- Fix im Honcho-Override/Deployment **oder** Upstream-Meldung; bis dahin Dialektik als
  „nicht betreibbar" kennzeichnen.
- Preflight-Beleg (#1186): Test, der beweist, dass der Header **beim Provider ankommt**
  (nicht nur gesetzt ist). Quelle/Anschluss: #1050/#1051, `test_opencode_session_check_1050.py`.

**AP-B2.3 — LLM-Timeout-Fehler-Mapping (#1165)** · 1 PT
- `architecture_decompose_views.py`: `LlmTransportError`/`TimeoutError` → **503/504** mit
  `code: LLM_TIMEOUT|LLM_UNAVAILABLE` (Muster `LlmNotConfiguredError → LLM_NOT_CONFIGURED`).
- `arch_decompose_tree` in `llm_adapter/timeouts.py::WORKSPACE_WIDE_PURPOSES` aufnehmen.
- Retry-Politik für Timeouts prüfen (4×30 s + Backoff = ~128 s bis sicherer Fehlschlag).
- Test: Provider-Timeout → 503/504 statt generischer 500.

**Abhängigkeit:** #1166 (DB-Pool-Erschöpfung) ist Betriebsthema und wird hier nur als
Umgebungszustand referenziert (nicht gefixt); er verfälscht sonst B2-Messungen.

---

### 3.4 B1 — MCP-Surface-Parität

**Ziel:** Keine Fähigkeit existiert nur auf einem der beiden Transporte; jede Asymmetrie ist
begründet und dokumentiert.

**AP-B1.1 — Interview-Symmetrie (#1164)** · 1,5–2 PT
- REST-Action `POST /api/v1/interviews/{id}/set_target/` → `InterviewService.set_target`
  (gleiche Status-Guards wie MCP).
- MCP-Tool `interview.chat` → derselbe Service-Pfad wie `InterviewViewSet.chat`
  (Guard „nur `in_progress`", single/multi-Dispatch; vgl. #1152).
- Optional: beide Oberflächen aus einer gemeinsamen Operationsliste ableiten.

**AP-B1.2 — TraceLink-Enumerieren über MCP (#1098)** · 1 PT
- `traceability.query_links` mit den REST-Filtern (`workspace_id`, `link_type`,
  `source_id`/`target_id`, `item_type`, Pagination); read-only, in `_READ_ONLY_TOOL_NAMES`.
- `entity_surface_matrix.py` von Gap auf „kein Gap"; `docs/api/MCP-SURFACE.md` aktualisieren.

**AP-B1.3 — `main_goal.query` (#1097)** · 1 PT
- Rollenentscheidung nötig (E3): wer darf MainGoals eines Workspace listen?
- Tool + Rollen-Vertrag in der Tool-Beschreibung; Tenant-Isolation wie übrige Queries.

**AP-B1.4 — `artifact_search`-Schwelle/Transparenz (#1170)** · 0,5–1 PT
- Optionaler `min_score` (Default > 0) **oder** Tool-Schema/Beschreibung korrigieren,
  damit `total_count` echte Treffer spiegelt; Pass (tsvector vs. Substring) benennen.

**AP-B1.5 — VCRM-Sichtbarkeit & toter Code (#1101)** · 0,5–1 PT
- Empfehlung (b): im OpenAPI/MCP-Surface markieren, dass VCRM MCP-only ist; alternativ
  `GET /api/v1/vcrm/` (Produktentscheidung E4).
- `export_vcrm_pdf`: an einen Transport hängen **oder** als tot markieren.

**AP-B1.6 — MCP-Rollentests self-seeding (#1133)** · 0,5 PT
- `test_mcp_api_key_roles.py`: Fixture erzeugt Workspace/Rolle über den kanonischen
  Provisioning-Pfad, statt `"Demo Workspace"` anzunehmen; sonst klarer Skip.

---

### 3.5 B0 — Client-Onboarding / One-Click (Leit-Bundle #1171)

Umsetzung des bestehenden Plans
[`2026-10-04-one-click-client-installation.md`](2026-10-04-one-click-client-installation.md),
hier als Bundle geführt. Stufe 1 (ohne Store-Veröffentlichung) = AP-B0.1…B0.3.

**AP-B0.1 — Stufe 1: Registry + Renderer + Skripte + Doku DE/EN + CI-Gate**
(Plan-APs 1.1–1.5) · ≈ 9–13 PT
- `clients/registry.yaml` (Single Source of Truth), `scripts/clients/render.py` (idempotent),
  `scripts/clients/install.sh` / `verify.sh`, `docs/clients/**` (7×2 Dateien),
  CI-Gate „Client-Artefakte" (Drift-/Paritäts-/Schema-/Versions-Check).
- **Status: umgesetzt.** Alle Artefakte vorhanden; `render.py --check` meldet
  „16 client/store artifacts up to date", Renderer-Tests (7) und `dist`-Paritäts-/Regenerationstests (46) grün.

**AP-B0.2 — Doku-Sofortfixes (unabhängig publizierbar)**
- **#1169** Codex: `wire_api="responses"` + Approval-Bypass für headless + geeignete Modelle.
- **#1171** Kernlücken: Kimi Code, Hermes-MCP, OpenCode-Widerspruch auflösen.
- Transport-Entscheidungsregel (`/mcp/` vs. `/mcp/sse/` vs. stdio-Bridge) zentral dokumentieren.
- **Status: umgesetzt.** Codex-Headless-Konfiguration im Registry-/Renderer-Modell abgebildet
  (#1169 → `verify`); Kimi Code/Hermes/OpenCode in `docs/clients/**` generiert und der
  OpenCode-Widerspruch beseitigt; Transportregel zentral in der Matrix dargestellt.

**AP-B0.3 — Hermes-Skill-Connector (#649)** · 1 PT
- `integrations/hermes-skill/reqogniloom/` (`SKILL.md` + stdlib-`scripts/` + `references/`)
  gemäß Issue-Entwurf; verifiziert über `hermes skills install <url>` bzw. `tap add`.
  Additiv zum Desktop-Plugin, ersetzt dessen Wert für Web/TUI/CLI.

**AP-B0.4 — Workspace-Tokens & MCP-Config-Copy (#92)** · 2–3 PT
- Backend: workspace-scoped Token (Scope im Token, kein Cross-Workspace-Zugriff).
- UI: Workspace-UUID sichtbar + Copy; „MCP Connection Info"-Panel mit Copy-Config.
- Verzahnung mit #1171: die kopierte Config muss dem `registry.yaml`-Modell entsprechen.

**AP-B0.5 — Plugin-Versionierungs-Anker (#1138)** · SE-Entscheidung
- Traceability-Anker für Plugin-Versionierung (ADR-017-Lücke) festlegen; Auswirkung auf
  Store-Versionen (B0 Stufe 2, `VERSION`-Kopplung).

**Status Stufe 2 — Drafts liegen:** `.claude-plugin/marketplace.json` und `server.json`
(beide aus `VERSION`) sowie fünf Workflow-Drafts (`release-client-artifacts`, `publish-npm`,
`publish-marketplace`, `publish-mcp-registry`, `client-smoke`) und `docs/clients/STAGE2.md`
sind vorbereitet; **keine Publikation aktiv** (Trigger nur `workflow_dispatch`,
Entscheidungen E1–E7 offen).

**DoD B0:** Plan-DoD Stufe 1 erfüllt (ein Befehl je Client, DE/EN-Parität, CI-Gate grün,
belegter Smoke-Test); #1169/#649/#92 geschlossen oder explizit auf Store-Welle geplant.

---

## 4. Verzahnung mit #1171 und dem One-Click-Plan

- #1171 ist der **Dach-Issue** für B0; der bestehende Plan liefert bereits eine verifizierte
  Client-Matrix, Transportregel und Store-Landkarte. Dieser Arbeitsplan **dupliziert ihn nicht**,
  sondern verankert ihn im Hub und schneidet die sofort machbaren Teile heraus.
- Der Hub verlinkt beide Richtungen: Hub → Plan (dieser) → One-Click-Plan.
- **Nächster konkreter Schritt für #1171:** `clients/registry.yaml` als Single Source of Truth
  anlegen und `docs/clients/` daraus generieren — damit ist der OpenCode-Widerspruch
  technisch ausgeschlossen (nicht nur redaktionell).

---

## 5. Reihenfolge (Wellen)

| Welle | Inhalt | Typ | Abhängigkeit |
|---|---|---|---|
| **W0** | B4.1 (#1185), B3.1 (#1152), B2.1 (#1163) | Sofortfixes, klein/risikolos | — |
| **W1** | B2 komplett (#1153, #1186, #1165) | Provider-Robustheit | W0 |
| **W2** | B1 komplett (#1164, #1098, #1097, #1170, #1101, #1133) | MCP-Parität | — |
| **W3** | B3.2 (#988) | Plugin/Frontend | — |
| **W4** | B0 Doku + Registry/Skripte (#1171/#1169/#649) | Client-Onboarding | W2 (Config-Modell stabil) |
| **W5** | B0 Stores + Tokens (#92, #1138) | Supply-Chain/Produkt | W4, Entscheidungen E1–E7 |

---

## 6. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Breaking Change am REST-Envelope (#1177) | Clients brechen | Übergangs-/Versionierungsentscheidung E1, erst nach SDK-Abgleich |
| Honcho-Fix ist Upstream (#1153) | nicht lokal lösbar | Deploy-Override + Upstream-Meldung + ehrliche Doku |
| Bluepencil-Re-Vendor (#988) braucht externen Build | Verzögerung | Host-Bridge ist bereits da; nur Bundle-Tausch nötig |
| #1171 Stufe 1 ist 9–13 PT | lange Kette | strikt Stufe 1/2 trennen, Doku zuerst |
| Zwei Marktplätze (Claude/Codex) driften | inkonsistente Versionen | beides aus `registry.yaml` generieren |
| Provider-Timeout-Messung durch #1166 verfälscht | falsche Diagnose | DB-Pool-Zustand vor B2-Messung prüfen |

---

## 7. Entscheidungsbedarf

| # | Frage | Empfehlung |
|---|---|---|
| E1 | `/users/`-Envelope-Bruch: sofort oder versioniert? | Versionierter Übergang (Alias/`v2`), nie still umstellen |
| E2 | Bindestrich-Schema: dokumentieren oder Alias-Routen? | Alias-Routen ergänzen + Neuanlagen normen |
| E3 | Wer darf `main_goal.query` (Rollenvertrag)? | Workspace-Mitglied read-only; Vertrag in Tool-Beschreibung |
| E4 | VCRM REST (#1101): neues Interface oder MCP-only sichtbar? | Zuerst MCP-only sichtbar machen (b) |
| E5 | #92 Token-Scope: Header oder In-Token? | In-Token (Scope gehasht), UI zeigt nur Workspace-UUID |
| E6 | Bluepencil: eigenes Re-Vendor oder Upstream-Sync-Prozess? | Einmal re-vendorn + `latest.json`-SHA als CI-Check |

---

## 8. Anhänge

### Anhang A — Issue → Bundle → Closure-Kriterium

| Issue | Bundle | Closure-Kriterium |
|---|---|---|
| #1185 | B4 | Regressionstest: keine DB-Interna in Antwort |
| #1177 | B4 | `/openapi.json` + Envelope-Tests grün |
| #1152 | B3 | Test: `cancelInterview` → `interview.abandon` |
| #988 | B3 | Notiz trägt realen Autor, SHA synchron |
| #1163 | B2 | Test: `score:null` → Default, kein `TypeError` |
| #1153 | B2 | Dialektik-Call 200 **oder** Doku „nicht betreibbar" |
| #1186 | B2 | Preflight beweist Header-Zustellung |
| #1165 | B2 | Timeout → 503/504 mit `LLM_TIMEOUT` |
| #1164 | B1 | `set_target` REST + `interview.chat` MCP verifiziert |
| #1098 | B1 | `traceability.query_links` ohne `artifact_id` |
| #1097 | B1 | `main_goal.query` mit Rollenvertrag |
| #1170 | B1 | Schwelle/Transparenz + Paritäts-Matrix |
| #1101 | B1 | VCRM sichtbar/tot-Code entschieden |
| #1133 | B1 | Tests self-seeding, keine SetupErrors |
| #1171 | B0 | Plan-DoD Stufe 1 |
| #1169 | B0 | Codex-Doku korrigiert |
| #649 | B0 | Hermes-Skill installierbar/verifiziert |
| #92 | B0 | Workspace-Token + UI-Copy |
| #1138 | B0 | ADR-Anker gesetzt |
