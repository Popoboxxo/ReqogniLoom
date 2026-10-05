# Client-Onboarding Smoke — Bundle B0 (Plan §4.3)

| Feld | Wert |
|---|---|
| **Datum** | 2026-10-05 |
| **Branch** | `feat/bugfix-hub-integrations` |
| **Host** | Windows (win32), Shell: Git Bash 5.3.15 (MINGW64); Backend via Docker |
| **Stack** | Compose-Projekt `ai-native-reqflow-poc` (Label-Configs: `deploy/docker-compose.yml` + `deploy/docker-compose.override.yml`) |
| **Backend** | `ai-native-reqflow-poc-backend-1`, Host-Port **:8001** (bereits laufend, kein `up` nötig) |
| **Health** | `HTTP 200 {"status":"ok", checks: database/memory_backend/cache/celery_worker/celery_beat = ok}` |
| **Leit-Definition** | `docs/plans/2026-10-04-one-click-client-installation.md` §4.3 |
| **Re-Smoke** | siehe §9 — Re-Test nach Fix der vier Installer-Defekte (2026-10-06) |

## 1. Referenzdaten (REST-Gegenprobe)

Provisioniert mit `docker exec ai-native-reqflow-poc-backend-1 python manage.py seed_demo --reset-password`
(Admin-User `admin`), danach JWT-Login und QA-Workspace + 3 Requirements + Admin-API-Key angelegt.

| Element | Wert |
|---|---|
| **QA-Workspace** | `QA-CLIENTSMOKE-2026-10-05` |
| **Workspace-ID** | `50bb1cf7-bac9-42ed-a50a-57329bcf6fff` |
| **REST Workspaces count** | **420** (`GET /api/v1/workspaces/`, `X-API-Key`) |
| **REST Requirements count** | **3** (`GET /api/v1/requirements/?workspace_id=50bb1cf7-…`) |
| **API-Key** | `reqlo_****RPlq` (maskiert; plaintext nur einmalig ausgegeben) |
| **API-Key-ID** | `7ed9bb7f-1f1c-4812-ad32-1585a9342902` |
| **Requirements** | `SMOKE-01` / `SMOKE-02` / `SMOKE-03` (Titel) |

## 2. Server-seitiger MCP-Nachweis (raw JSON-RPC)

Stateless HTTP-Transport `POST /mcp/`, Header `X-API-Key: reqlo_****RPlq` (curl):

| Call | Ergebnis |
|---|---|
| `initialize` | 200 — `serverInfo.name="ReqogniLoom"`, `protocolVersion="2024-11-05"` |
| `tools/list` | 200 — **223 Tools** |
| `tools/call workspace.list` | 200 — `count = 420` ✅ == REST |
| `tools/call requirement.query {workspace_id}` | 200 — 3 Requirements (SMOKE-01/02/03) ✅ == REST |

Damit sind Key + Transport + Tool-Surface server-seitig belegt.

## 3. Ergebnis-Tabelle

| Client | installiert? | install.sh | verify.sh | Echter Tool-Call | Ergebnis |
|---|---|---|---|---|---|
| **claude-code** | ja (2.1.273) | **FAIL** (falsche Marketplace-ID) | FAIL → Fallback OK | blockiert (OAuth abgelaufen) | **ENV-LIMITED** |
| **opencode** | ja (1.18.34) | PASS | PASS (`mcp list`) | **PASS** via Fallback (3 / 420) | **PASS*** |
| **kimi-code** | ja (2.1.1) | PASS (Config geschrieben) | info-only (kein nativer Check) | **FAIL** (keine MCP-Tools exponiert) | **FAIL** |
| **hermes** | ja (v0.18.2) | **FAIL** (`--url` fehlt) | FAIL → Fallback OK | blockiert (Provider HTTP 400) | **ENV-LIMITED** |
| **codex** | **nein** | — | — | — | **ENV-LIMITED** |
| **antigravity** | **nein** | — | — | — | **ENV-LIMITED** |

\* opencode PASS nur mit dokumentierter Abweichung (API-Key-Header manuell ergänzt + neutrales CWD).

---

## 4. Detail je Client

### 4.1 claude-code

**Install (verbatim, gekürzt):**
```
$ bash scripts/clients/install.sh --client claude-code --url http://localhost:8001 \
    --key-env REQOGNILOOM_API_KEY --yes
Adding marketplace…✔ Successfully added marketplace: reqogniloom-marketplace
Installing plugin "reqogniloom@claude-code"...
✘ Failed to install plugin "reqogniloom@claude-code":
   Plugin "reqogniloom" not found in marketplace "claude-code".
### install exit=1 ###
$ bash scripts/clients/verify.sh --client claude-code
fail: expected marker 'reqogniloom' not found
### verify exit=1 ###
```
**Ursache:** `install.sh` installiert als `reqogniloom@claude-code`, die Marketplace-Deklaration heißt
aber `reqogniloom-marketplace` (`dist/plugins/claude-code/.claude-plugin/marketplace.json`). ⇒ **Defekt in `install.sh`.**

**Fallback (Abweichung):** `claude plugin install reqogniloom@reqogniloom-marketplace -y`
```
✔ Successfully installed plugin: reqogniloom@reqogniloom-marketplace (scope: user)
$ claude mcp list
plugin:reqogniloom:reqogniloom: http://localhost:8001/mcp/sse/ (SSE) - ✔ Connected
$ bash scripts/clients/verify.sh --client claude-code
ok: found 'reqogniloom' / verify: claude-code OK
```
**Echter Tool-Call:** `claude -p "…" --allowedTools "mcp__reqogniloom"` →
`Failed to authenticate: OAuth session expired and could not be refreshed` ⇒ nicht ausführbar.
**Ergebnis: ENV-LIMITED** — Connect-Nachweis (`✔ Connected`) vorhanden, echter Call fehlt (OAuth-Session abgelaufen, keine Re-Auth durchgeführt).

### 4.2 opencode

**Install (verbatim, gekürzt):**
```
$ bash scripts/clients/install.sh --client opencode --url http://localhost:8001 \
    --key-env REQOGNILOOM_API_KEY --yes --skills-dir "$HOME/.config/opencode/skills"
◆  MCP server "reqogniloom" added to C:\Users\duchr\.config\opencode\opencode.json
installed: …/skills/{ccb-approval-and-baseline,interview-management,risk-derivation,
           test-lifecycle,traceability-audit,vmodell-decomposition}
install: opencode configured
ok: found 'reqogniloom' / verify: opencode OK
```
**Befund:** Die generierte Config enthält **keinen** Auth-Header:
```json
"reqogniloom": { "type": "remote", "url": "http://localhost:8001/mcp/sse/" }
```
⇒ `install.sh` reicht den API-Key für opencode nicht durch (nur `--url`).

**Echter Tool-Call (as-installed, Repo-CWD):** `opencode run "…requirement.query…"` — Modell
liest Repo-Kontext/Skills und ruft das MCP-Tool **nicht** auf (kein Ergebnis).

**Fallback (Abweichung):** Header ergänzt und aus neutralem CWD gestartet:
```
$ opencode mcp add reqogniloom --url http://localhost:8001/mcp/sse/ --header "X-API-Key=reqlo_…"
$ opencode run   # neutrales CWD
⚙ reqogniloom_requirement_query {"workspace_id":"50bb1cf7-…"}  → 3 requirements.   ✅ == REST 3
⚙ reqogniloom_workspace_list                                    → 420 workspaces.   ✅ == REST 420
```
**Ergebnis: PASS\*** — beide Zahlen identisch zur REST-Gegenprobe, MCP-Call im Client-Log sichtbar;
gültig nur mit manuellem Header + neutralem CWD.

### 4.3 kimi-code

**Install:** Config geschrieben + Skills kopiert; `verify.sh` ist info-only (`verify: kimi-code OK`).
```json
~/.kimi-code/mcp.json:
{ "mcpServers": { "reqogniloom": { "type": "http", "url": "http://localhost:8001/mcp/",
  "headers": { "Authorization": "Bearer ${REQOGNILOOM_API_KEY}" } } } }
```
**Echter Tool-Call:** `kimi -p "…"` (auch aus Repo-CWD wiederholt) →
```
Error: EPERM: operation not permitted, watch 'C:\Users\duchr\.kimi-code\workspaces.json'
…
"… I don't have a reqogniloom MCP tool in my available tools … none of them expose
 a ReqogniLoom requirement.query interface. … I won't invent a count."
```
⇒ Headless kimi (v2.1.1) registriert den in `mcp.json` deklarierten Server **nicht** (Tool-Liste nur built-in).
**Ergebnis: FAIL** — Config vorhanden, aber im Client nicht wirksam.

### 4.4 hermes

**Install (verbatim, gekürzt):**
```
$ bash scripts/clients/install.sh --client hermes --url http://localhost:8001 \
    --key-env REQOGNILOOM_API_KEY --yes
  ✗ Must specify --url <endpoint>, --command <cmd>, or --preset <name>
installed: /c/Users/duchr/.hermes/skills/reqogniloom
install: hermes configured
fail: expected marker 'Connected' not found
### install exit=1 ###
```
**Ursache:** `install.sh` ruft `hermes mcp add reqogniloom` **ohne** `--url` auf; die CLI verlangt `--url`/`--command`/`--preset`.

**Nativer Fallback-Versuch:** `hermes mcp add reqogniloom --url http://localhost:8001/mcp/ [--auth header]`
→ interaktiver Prompt (`Does this server require authentication? [Y/n]:`) über TTY; **headless nicht automatisierbar** (stdin-Pipe wirkungslos) ⇒ **ENV-LIMITED**.

**Konfig-Fallback (entspricht Plan §4.2 lit. c, `mcp_servers.<name>`):**
`mcp_servers.reqogniloom` in `~/AppData/Local/hermes/config.yaml` + Key in `~/AppData/Local/hermes/.env`:
```yaml
  reqogniloom:
    url: http://localhost:8001/mcp/
    headers:
      Authorization: Bearer ${REQOGNILOOM_API_KEY}
    enabled: true
```
```
$ hermes mcp list                      → reqogniloom  http://localhost:8001/mcp/  ✓ enabled
$ hermes mcp test reqogniloom          → ✓ Connected (219ms)
$ bash scripts/clients/verify.sh --client hermes
ok: found 'Connected' / verify: hermes OK
```
**Echter Tool-Call:** `hermes -z "…workspace.list…"` →
`HTTP 400: Request is missing x-opencode-session …` (Provider `OpenCode Go` / `deepseek-v4-pro`; keine API-Keys/OAuth aktiv).
**Ergebnis: ENV-LIMITED** — Connect-Nachweis vorhanden, echter Call am LLM-Provider gescheitert.

### 4.5 codex / 4.6 antigravity

```
$ command -v codex        → NOT FOUND
$ command -v antigravity  → NOT FOUND
```
Nicht installiert (Host). **ENV-LIMITED** — nicht ausführbar; `install.sh` würde zusätzlich `codex`/`antigravity`
Binaries voraussetzen (`require_bin`).

---

## 5. Abweichungen / Deviations

1. **Git Bash statt PowerShell** für alle Client-Kommandos.
2. **opencode:** `--skills-dir "$HOME/.config/opencode/skills"` gesetzt, damit Skills **nicht** in den
   Repo-Working-Tree (`.opencode/skills`) geschrieben werden.
3. **opencode echt-Call:** API-Key-Header manuell ergänzt + neutrales CWD (Repo-Kontext lenkt das Modell ab; as-installed fehlt der Header).
4. **claude-code:** Plugin mit korrekter Marketplace-ID `reqogniloom-marketplace` installiert (statt `claude-code`).
5. **hermes:** Statt des interaktiven `mcp add` wurde der in Plan §4.2 lit. c dokumentierte Konfig-Fallback
   (`mcp_servers.<name>` + Key in `.env`) genutzt.
6. **Make up nicht nötig:** Backend lief bereits gesund auf :8001.

## 6. Backup / Restore-Status

| Feld | Wert |
|---|---|
| **Backup-Dir** | `C:\Users\duchr\AppData\Local\Temp\opencode\reqlo-smoke\backup-20261005-220543` |
| **Gesichert** | `~/.claude.json`, `~/.claude/{settings.json,settings.local.json,CLAUDE.md}`, `.claude/plugins/{installed_plugins.json,known_marketplaces.json}`, `~/.config/opencode/{opencode.json,opencode.jsonc}`, `~/.kimi-code/config.toml` (+ `mcp.json` absent), `~/AppData/Local/hermes/config.yaml`; Manifeste der Skills-/Plugin-Dirs |
| **Restore-Status** | **absichtlich belassen (intentionally left)** — nicht zurückgespielt |
| **Hinweis** | API-Key-Klartext liegt in `~/.config/opencode/opencode.json` und `~/AppData/Local/hermes/.env`; Key-ID `7ed9bb7f-…` (Revoke: `DELETE /api/v1/api-keys/7ed9bb7f-1f1c-4812-ad32-1585a9342902/` mit Bearer-JWT). QA-Workspace + 3 Requirements bleiben als Beleg erhalten. |

## 7. Working-Tree-Änderungen durch diesen Lauf

- **Nur diese Report-Datei:** `docs/bugfix-hub/smoke/2026-10-05-client-smoke.md` (neu).
- Repo-`opencode.json` / `.mcp.json` **unverändert** (SHA vor == nach); `git status` zeigt keine neuen Änderungen.
- Die 3 vorbestehenden untracked Fremdpfade (`docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md`,
  `knowledge/wiki/plans/`, `knowledge/wiki/specs/`) wurden **nicht** berührt.

## 8. Blocker / ENV-LIMITED (je eine Zeile)

- **claude-code:** `install.sh` nutzt falsche Marketplace-ID `claude-code` statt `reqogniloom-marketplace` (Fix nötig); Cloud-Call scheitert an abgelaufener Claude-OAuth-Session.
- **opencode:** `install.sh` schreibt keinen `X-API-Key`-Header (nur `--url`) → ohne Key kein MCP-Zugriff.
- **kimi-code:** Headless-Session exponiert den `mcp.json`-Server nicht (keine MCP-Tools) + `EPERM` fs-watch auf `workspaces.json`.
- **hermes:** `install.sh` ruft `hermes mcp add` ohne `--url` auf; nativer Add ist TTY-interaktiv; One-Shot scheitert an Provider `OpenCode Go` (`HTTP 400 … x-opencode-session`, deckt sich mit #1186).
- **codex / antigravity:** Binaries auf diesem Host nicht installiert.

---

## 9. Re-Smoke (nach Fix) — 2026-10-06

Nach Behebung der vier im ersten Lauf gefundenen Installer-Defekte wurde der Smoke-Test gegen
denselben Stack (`http://localhost:8001`, frischer API-Key) wiederholt. Der erste Lauf (§1–§8)
bleibt als Historie erhalten; dieses Kapitel dokumentiert den Stand danach und **supersediert**
die Cleanup-/Key-Aussagen aus §6.

### 9.1 Behobene Installer-Defekte (Quelle: `scripts/clients/install.sh`, `clients/registry.yaml`)

| # | Client | Defekt (1. Smoke, §4) | Fix |
|---|---|---|---|
| 1 | **claude-code** | installierte `reqogniloom@claude-code`; Marketplace heißt `reqogniloom-marketplace` | Marketplace-Name wird jetzt aus `dist/plugins/claude-code/.claude-plugin/marketplace.json` gelesen; Install = `claude plugin install reqogniloom@reqogniloom-marketplace --scope user -y` |
| 2 | **opencode** | `mcp add` schrieb keinen Auth-Header | `--header "X-API-Key={env:REQOGNILOOM_API_KEY}"` (Env-Indirektion; resultierende Config enthält exakt den Platzhalter) |
| 3 | **hermes** | `hermes mcp add reqogniloom` brach ab (benötigt `--url`; `mcp add` ist Discovery/interaktiv, `--env` nur stdio) | `hermes config set mcp_servers.reqogniloom.url "$URL/mcp/"` + `hermes config set mcp_servers.reqogniloom.headers.Authorization "Bearer ${REQOGNILOOM_API_KEY}"` |
| 4 | **kimi-code** | schrieb `~/.kimi-code/mcp.json` mit `headers.Authorization: "Bearer ${VAR}"`; Kimi interpoliert das **nicht** → 401 / keine Tools | Root Cause: korrektes Schema `{"transport":"http","url":"<URL>/mcp/","bearerTokenEnvVar":"REQOGNILOOM_API_KEY"}` (nur Env-Var-**Name**) |

**Fallstrick hermes:** `hermes config set` schreibt `config.yaml` via PyYAML neu und **entfernt
Kommentarzeilen** — vorher Backup ziehen.

`clients/registry.yaml` (install_*/fallback/pitfalls) wurde für alle vier Clients nachgezogen,
DE/EN-Parität hergestellt, `python scripts/clients/render.py` regeneriert die Doku;
`render.py --check` = `OK: 16 client/store artifacts up to date`; `test_render.py` = **7 passed**.

### 9.2 Re-Smoke-Ergebnis (frischer Key, `http://localhost:8001`)

| Client | install | connect/verify | Echter Tool-Call | Ergebnis |
|---|---|---|---|---|
| **claude-code** | **PASS** | **PASS** (`claude mcp list` → plugin `reqogniloom` connected, SSE `http://localhost:8001/mcp/sse/`) | **ENV-LIMITED** — headless `claude -p` scheitert an „OAuth session expired" (gleiche Env-Grenze wie zuvor) | install/connect PASS; Daten-Call **ENV-LIMITED** |
| **opencode** | **PASS** | **PASS** | **full PASS** — echte MCP-Calls: `reqogniloom_requirement_query` (WS `50bb1cf7-…`) → **3**, `reqogniloom_workspace_list` → **420** (== REST) | **PASS** |
| **hermes** | **PASS** | **PASS** (`hermes mcp test` → Connected; `hermes mcp list` → `reqogniloom` enabled `http://localhost:8001/mcp/`) | **ENV-LIMITED** — Provider HTTP 400 (`missing x-opencode-session`) | install/connect PASS; Daten-Call **ENV-LIMITED** |
| **kimi-code** | **PASS** (korrekte `mcp.json`, **kein** Klartext-Secret) | — | **ENV-LIMITED** — headless exponiert weiterhin **keine** MCP-Tools („EPERM … watch workspaces.json" + Provider 403 Monatslimit) | **ENV-LIMITED / L2** (kein PASS) |

**REST-Gegenprobe:** `GET /api/v1/workspaces/` → **420**; `GET /api/v1/requirements/?workspace_id=50bb1cf7-…` → **3**.

**Server-seitiger MCP-Nachweis (frischer Key):** `initialize` → `serverInfo.name="ReqogniLoom"`,
`protocolVersion="2024-11-05"`; `tools/list` → **223 Tools**; `workspace.list` → **420**;
`requirement.query` → **3** — alle == REST.

### 9.3 Cleanup-Beleg

- **Alter Smoke-Key** `7ed9bb7f-1f1c-4812-ad32-1585a9342902`: `DELETE` → **204**; verifiziert `revoked:true`.
  **Nuance (SOFT-Delete):** die Zeile bleibt in `GET /api/v1/api-keys/` sichtbar, authentifiziert
  aber nicht mehr (`401 api_key_revoked`) — dadurch kann sie fälschlich „aktiv" wirken.
- **Frischer Re-Smoke-Key:** angelegt und wieder revoked (`DELETE 204`; nicht mehr im aktiven Set;
  negativer MCP-`tools/list` → **401**).
- **Host-Configs byte-identisch aus Backup `backup-20261005-220543` zurückgespielt** (10/10 Dateien:
  Claude-Trio, `opencode.json`/`.jsonc`, Kimi `config.toml`, Hermes `config.yaml`; Backup-Verzeichnis
  `plugins-registry` entspricht live `plugins`).
- **Vom Smoke erzeugte Artefakte entfernt:** `~/.kimi-code/mcp.json`, `~/.claude/plugins/cache/reqogniloom-*`,
  `~/.hermes/skills/reqogniloom`, Smoke-Skill-Dirs.
- `%LOCALAPPDATA%\hermes\.env`: **nur** die Zeile `REQOGNILOOM_API_KEY=` entfernt (Datei existierte
  vorher mit weiterem Inhalt).
- Abschließender Grep über die Config-Surface nach dem Key-Präfix `reqlo_***` → **0 Treffer**;
  Backend `/health/` → **200**.
- Roh-Ausgaben archiviert unter `.tmp/reqlo-smoke-resmoke/` (gitignored).

### 9.4 DoD-3-Stand nach Re-Smoke

**Weitgehend erfüllt, aber nicht vollständig.** Die vier Installer-Defekte sind **behoben und
re-verifiziert**; **opencode** ist ein **full PASS** (echte MCP-Tool-Calls == REST).
**claude-code** und **hermes** sind install/connect PASS, ihr Daten-Tool-Call bleibt jedoch durch
**externe LLM-/Provider-Auth** ENV-LIMITED. **kimi-code** bleibt **ENV-LIMITED/L2**.
Der server-seitige MCP bleibt **PASS**. Ein Gesamt-PASS wird **nicht** behauptet.

**Working-Tree-Änderungen dieses Re-Smokes:** nur Addendum §9 in dieser Report-Datei. Die 3
vorbestehenden untracked Fremdpfade (`docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md`,
`knowledge/wiki/plans/`, `knowledge/wiki/specs/`) wurden **nicht** berührt.
