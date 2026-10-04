---
type: REVIEW
scope: wp-2-plugin-inventar-manifest-matrix
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-2 Evidenz 1 — Plugin-Inventar und Manifest-Feldmatrix

Alle Zahlen gemessen (`git ls-files`, `Get-ChildItem`, `git check-ignore`), nicht geschätzt.
Stand: Branch `chore/system-audit-2026-09` @ `3dcc80d8`, main-Anker `abd61aed`.

## 1. Was existiert physisch — fünf Plugins, nicht drei

Der Auftrag nennt `integrations/hermes-plugin/` und `dist/plugins/{antigravity,claude-code}/`.
Tatsächlich sind es **fünf** getrennte Plugin-Bundles:

| # | Bundle | Pfad | Trackerdateien | Status |
|---|---|---|---|---|
| 1 | Hermes **TS** Desktop | `integrations/hermes-plugin/reqogniloom/` | 14 | versioniert, `dist/`-Build **ignoriert** |
| 2 | Hermes **Python** Agent | `integrations/hermes-agent-plugin/` | 7 | versioniert |
| 3 | Claude Code | `dist/plugins/claude-code/` | 13 | versioniert |
| 4 | Antigravity | `dist/plugins/antigravity/` | 10 | versioniert |
| 5 | Hermes **Dist-Builder** | `dist/plugins/hermes/` | 2 | **kein Plugin-Artefakt** — nur Builder + Test |

`git ls-files dist | Measure-Object` = **56** versionierte Dateien.
`git ls-files integrations` = **40** versionierte Dateien.

### 1a. Ist `dist/` versioniert? Ja.

```
git check-ignore -v dist/plugins/antigravity/reqogniloom/plugin.json   -> (kein Treffer)
git check-ignore -v dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json -> (kein Treffer)
```

`dist/` ist **keine** Build-Artefakt-Ausgabe im Ignore-Sinne — es ist versioniert und
damit reproduzierbar. **Die vom Auftrag vermutete Reproduzierbarkeets-Lücke existiert für
`dist/` nicht.** (Für `integrations/hermes-plugin/reqogniloom/dist/` — das *gebaute*
TS-Bundle — gilt das Gegenteil, siehe 1c.)

### 1b. `dist/plugins/hermes/` enthält kein auslieferbares Plugin

```
dist/plugins/hermes/
├── build_hermes_plugin.py         41 Zeilen
├── test_build_hermes_plugin.py   128 Zeilen
└── __pycache__/                            (untracked)
```

`build_hermes_plugin.py:20` schreibt **in-place** nach
`integrations/hermes-plugin/reqogniloom` (`package.json` + `hermes-plugin.json`).
Es erzeugt also kein `dist/plugins/hermes/reqogniloom/`-Paket. Das Verzeichnis ist
eine reine Builder-Wohnung, kein Distributions-Artefakt. **Kein Finding**, aber eine
benennungsirreführende Struktur, die in der Doku nirgends aufgelöst wird.

### 1c. Das *gebaute* Hermes-TS-Bundle ist NICHT versioniert

`integrations/hermes-plugin/reqogniloom/.gitignore`:
```
node_modules/
dist/
```
```
git check-ignore -v integrations/hermes-plugin/reqogniloom/dist/plugin.js
-> integrations/hermes-plugin/reqogniloom/.gitignore:2:dist/
```

`hermes-plugin.json:7` deklariert `"main": "dist/plugin.js"`. In einem frischen Clone
existiert diese Datei **nicht**; ein Host, der das Plugin nach `hermes-plugin.json`
lädt, findet keinen Einstiegspunkt, bis jemand `npm install && npm run build`
ausführt. `docs/agent-templates/INSTALL.md` dokumentiert **keinen** Hermes-Schritt
(Abschnitte: Claude Code, OpenCode, Antigravity, Regeneration, Konvention) — die
Hermes-Installation ist damit **undokumentiert**. → AUD-2026-09-100.

### 1d. Leer-/Platzhalter-Verzeichnisse

Skript über `integrations/` + `dist/` (ohne `node_modules`, `__pycache__`,
`.pytest_cache`): **keine leeren Verzeichnisse gefunden.** Kein Finding.

## 2. Manifest-Feldmatrix (feldweise)

### 2.1 `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` (47 Z.)

| Feld | Zeile | Wert | Audit-Bewertung |
|---|---|---|---|
| `id` | 2 | `reqogniloom.reqogniloom` | **inkonsistent** zu allen anderen Bundles (`reqogniloom`) |
| `name` | 3 | `ReqogniLoom` | ok |
| `version` | 4 | `1.8.0-beta.17` | == `VERSION` ✔ |
| `description` | 5 | `Connect Hermes IDE to your ReqogniLoom workspace` | ok |
| `author` | 6 | `ReqogniLoom` | ok |
| `main` | 7 | `dist/plugin.js` | **Datei ist gitignored** → AUD-2026-09-100 |
| `activationEvents` | 8-12 | `[{type: onStartup}]` | **Format-Frage**: VS-Code-Schema; Hermes-SDK erwartet laut `docs/SYSTEMAUDIT_2026-09-02_GROB.md:356` `manifest.json {name, api}` → AUD-2026-09-101 |
| `contributes.commands` | 14-20 | `reqogniloom.open` | **nie registriert** — `activate.ts:60-75` registriert nur `ctx.register({id, area})`; der String `reqogniloom.open` kommt im Bundle nicht vor → AUD-2026-09-102 |
| `contributes.panels` | 21-28 | `reqogniloom-panel` ✔ | konsistent mit `activate.ts:22` |
| `contributes.statusBarItems` | 29-38 | `reqogniloom.status` ✔ | konsistent mit `activate.ts:23` |
| `engines.hermes` | 40-42 | `>=3.0.0` | **nicht einsehbar/prüfbar**; kein Code liest dieses Feld → AUD-2026-09-103 |
| `permissions` | 43-46 | `["network","storage"]` | **kein Code liest dieses Feld**; reale Nutzung ist `globalThis.fetch` + `ctx.storage` (activate.ts:43-50) → AUD-2026-09-103 |
| `capabilities`/`tools`/`commands` | — | **Feld fehlt vollständig** | keine deklarative Tool-Oberfläche; → AUD-2026-09-104 |
| `auth` | — | **Feld fehlt** | kein auth-Spezifikation im Manifest; Token kommt rein aus dem UI-Formular → AUD-2026-09-105 |

### 2.2 `integrations/hermes-plugin/reqogniloom/package.json` (30 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name` | 2 | `@reqogniloom/hermes-plugin` | ok (gescoped) |
| `version` | 3 | `1.8.0-beta.17` | == `VERSION` ✔ |
| `private` | 4 | `true` | ok |
| `type` | 5 | `module` | ✔ nötig für das ESM-Bundle |
| `scripts.build` | 7 | `vite build` | ✔ |
| `scripts.postbuild` | 8 | `npm run verify-build` | ✔ selbstprüfend |
| `scripts.verify-build` | 9 | `node --experimental-vm-modules scripts/verify-build.mjs` | ✔ |
| `devDependencies` | 13-26 | react 18.3, vite ^8.0.0, vitest ^4.1.0 | ✔ |
| `peerDependencies.react` | 27-29 | `^18.0.0` | ✔ Host liefert React |

`package-lock.json:3` und `:9` = `1.8.0-beta.17` ✔ (der in RELEASE_beta.12 dokumentierte
Lock-Drift ist nicht wieder aufgetreten).

### 2.3 `integrations/hermes-agent-plugin/plugin.yaml` (5 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name` | 1 | `reqogniloom` | ok |
| `version` | 2 | **`0.1.0`** | **Drift**: alle anderen Bundles `1.8.0-beta.17`; `build_hermes_plugin.py` fasst dieses Manifest nicht an → AUD-2026-09-106 |
| `description` | 3 | Slash-Command + Dashboard | ✔ deckungsgleich mit `register()` + `dashboard/manifest.json` |
| `author` | 4 | `ReqogniLoom` | ok |
| `hooks` | 5 | `[]` | ✔ kein Hook deklariert, keiner implementiert — konsistent |
| `secrets`/`env`/`port` | — | **fehlen** | `plugin_api.py:10-42` begründet das ausdrücklich und schaltet deshalb `REQOGNILOOM_DASHBOARD_TOKEN` fail-closed. **Bewusst, kein Defekt.** |

### 2.4 `integrations/hermes-agent-plugin/dashboard/manifest.json` (11 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name`/`label` | 2-3 | `reqogniloom` / `ReqogniLoom` | == `plugin.yaml:1` ✔ |
| `description` | 4 | stats | ok |
| `icon` | 5 | `ClipboardList` | ok |
| `version` | 6 | **`0.1.0`** | **Drift**, identisch zu 2.3 → AUD-2026-09-106 |
| `tab.path` | 7 | `/reqogniloom` | == Slash-Command-Name ✔ |
| `tab.position` | 7 | `after:analytics` | nicht prüfbar ohne Host → **BLOCKED**, s. §6 |
| `entry` | 8 | `dist/index.js` | **existiert und ist versioniert** (293 Z.) ✔ |
| `css` | 9 | `dist/style.css` | existiert, 36 Z. ✔ |
| `api` | 10 | `plugin_api.py` | existiert ✔, liefert `router` ✔ |

### 2.5 `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` (8 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name` | 2 | `reqogniloom` | ✔ (= `SERVER_NAME` im Builder, `build_claude_plugin.py:25`) |
| `version` | 3 | `1.8.0-beta.17` | == `VERSION` ✔ |
| `description` | 4 | SE agent roles + native MCP | ✔ |
| `author.name` | 6 | `ReqogniLoom` | ✔ |
| `capabilities`/`tools`/`commands` | — | **fehlt** | bei Claude-Code korrekt: Rollen-Permissions stehen in `agents/*.md` → kein Defekt |
| `minHostVersion` | — | **fehlt** | kein Host-Mindestversion-Gate → AUD-2026-09-103 (Info) |
| `mcp`-Endpoint | — | **nicht im Manifest** | liegt in `.mcp.json` (getrennte Datei, Claude-Code-Konvention) ✔ |

### 2.6 `dist/plugins/claude-code/reqogniloom/.mcp.json` (11 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `mcpServers.reqogniloom.type` | 4 | `sse` | **live verifiziert**, s. Evidenz 3 §2 |
| `…url` | 5 | `${REQOGNILOOM_MCP_URL}/mcp/sse/` | **live verifiziert erreichbar** (kein Phantom) — Evidenz 3 §2 |
| `…headers.X-API-Key` | 7 | `${REQOGNILOOM_API_KEY}` | Env-Template, kein Literal-Key ✔ (`dist/test_mcp_convention_parity.py` pinnt das) |

### 2.7 `dist/plugins/claude-code/.claude-plugin/marketplace.json` (13 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name` | 2 | `reqogniloom-marketplace` | ✔ (`build_claude_plugin.py:145`) |
| `owner.name` | 4 | `ReqogniLoom` | ✔ |
| `plugins[0].name` | 8 | `reqogniloom` | == `plugin.json:2` ✔ |
| `plugins[0].source` | 9 | `./reqogniloom` | ✔ relativ, `claude plugin marketplace add dist/plugins/claude-code` findet es (Builder-Kommentar 136-139) |
| `plugins[0].version` | — | **fehlt** | ⚠️ Marketplace-Eintrag ohne Version → **BLOCKED**: ohne echte `claude` CLI nicht verifizierbar, ob Claude Code das akzeptiert. s. §6 |

### 2.8 `dist/plugins/antigravity/reqogniloom/plugin.json` (5 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `name` | 2 | `reqogniloom` | ✔ |
| `version` | 3 | `1.8.0-beta.17` | == `VERSION` ✔ |
| `description` | 4 | SE-domain agent skills + native MCP | ✔ |
| `author` | — | **fehlt** | ⚠️ Claude-Code-Pendant hat `author`, Antigravity nicht — Asymmetrie ohne dokumentierten Grund → Info |
| `capabilities`/`minHostVersion` | — | fehlen | Antigravity hat kein öffentlich dokumentiertes Manifest-Schema → **BLOCKED**, s. §6 |

### 2.9 `dist/plugins/antigravity/reqogniloom/mcp_config.json` (10 Z.)

| Feld | Zeile | Wert | Bewertung |
|---|---|---|---|
| `mcpServers.reqogniloom.url` | 4 | `${REQOGNILOOM_MCP_URL}/mcp/sse/` | ✔ identisch zu `.mcp.json:5`, live verifiziert |
| `…headers.X-API-Key` | 6 | `${REQOGNILOOM_API_KEY}` | ✔ kein Literal |

## 3. Versions-Sync — Ergebnis

**Prämisse des Auftrags widerlegt.** `1.8.0-beta.18` existiert **nirgends** im Repo:

```
git grep -n "1\.8\.0-beta\.18" -- .        -> (kein Treffer, alle Dateien)
Get-Content VERSION                        -> 1.8.0-beta.17
git log --oneline -3                       -> 3dcc80d8 / cd002d94 / abd61aed
                                            56d8f511 chore(release): v1.8.0-beta.17
```

Der letzte Release-Commit ist **`v1.8.0-beta.17`**. `VERSION` = `1.8.0-beta.17`.

| Carrier | Ort | Wert | == `VERSION`? |
|---|---|---|---|
| Root | `VERSION:1` | `1.8.0-beta.17` | (Anker) |
| Frontend | `frontend/package.json:3` | `1.8.0-beta.17` | ✔ |
| Frontend-Lock | `frontend/package-lock.json:3,9` | `1.8.0-beta.17` | ✔ |
| Hermes-TS | `integrations/hermes-plugin/reqogniloom/package.json:3` | `1.8.0-beta.17` | ✔ |
| Hermes-TS-Lock | `…/package-lock.json:3,9` | `1.8.0-beta.17` | ✔ |
| Hermes-TS-Manifest | `…/hermes-plugin.json:4` | `1.8.0-beta.17` | ✔ |
| Claude Code | `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json:3` | `1.8.0-beta.17` | ✔ |
| Antigravity | `dist/plugins/antigravity/reqogniloom/plugin.json:3` | `1.8.0-beta.17` | ✔ |
| Env-Vorlage | `.env.example:560` (`REQOGNILOOM_VERSION`) | `1.8.0-beta.17` | ✔ |
| Compose full | `deploy/docker-compose.yml:567,683,755,802,893,953` | `${REQOGNILOOM_VERSION:-1.8.0-beta.17}` | ✔ |
| Compose minimal | `deploy/docker-compose.minimal.yml:117,177,211` | `${REQOGNILOOM_VERSION:-1.8.0-beta.17}` | ✔ |
| Site-Badge | `site/index.html:94,628` | `v1.8.0-beta.17` | ✔ |
| Doku | `docs/api/MCP-SURFACE.md:28`, `docs/CODEBASE_OVERVIEW.md:20,657,1139` | `v1.8.0-beta.17` | ✔ |
| **Hermes-Python** | `integrations/hermes-agent-plugin/plugin.yaml:2` | **`0.1.0`** | ✘ |
| **Hermes-Python-Dash** | `integrations/hermes-agent-plugin/dashboard/manifest.json:6` | **`0.1.0`** | ✘ |
| **MCP `serverInfo`** | `backend/mcp_server/protocol_handler.py:505` | **`"1.0.0"`** (hart) | ✘ |
| **MCP `GET /mcp/`** | `backend/mcp_server/views.py:431` | **`"1.0.0"`** (hart) | ✘ |

Live-Belege:

```
POST /mcp/ initialize
-> {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
    "capabilities":{"tools":{}},"serverInfo":{"name":"ReqogniLoom","version":"1.0.0"}}}

GET /mcp/  (X-API-Key)
-> {"server":"ReqogniLoom MCP Server","protocol":"JSON-RPC 2.0",
    "transports":["http","sse"],"version":"1.0.0"}

GET /api/v1/version/
-> 200 {"app_version":"unknown","commit_short":"unknown"}
```

→ **Plugin-Manifest-Versions-Sync: PASS** (alle drei generierten + der TS-Manifest auf
`VERSION`). Zwei Drift-Brutstellen: das Python-Plugin (`0.1.0`, von keinem Builder
erfasst → AUD-2026-09-106) und die hartkodierte MCP-`serverInfo.version` (`1.0.0`,
unabhängig von `VERSION` → AUD-2026-09-107, Klasse wie CR-21).

`GET /api/v1/version/` liefert live `"unknown"` — im laufenden Container ist weder
`APP_VERSION` gesetzt noch ein Repo-Root vorhanden (`version.py:78-105`). Damit ist die
Version **zur Laufzeit nicht verifizierbar**; ein Plugin/Host kann den Versionsstand
nicht gegenprüfen. → AUD-2026-09-108 (Low).

## 4. Sicherheits-Schnellbewertung der Plugin-Quellen

Statischer Scan über `integrations/hermes-plugin/reqogniloom/src/*.{ts,tsx}`,
`scripts/*.mjs`, `integrations/hermes-agent-plugin/{*.py,dashboard/*.py,dashboard/dist/*.js}`,
`dist/plugins/**/*.py`:

| Muster | Treffer | Bewertung |
|---|---|---|
| `eval(` / `new Function(` | 0 | ✔ |
| `child_process` / `spawnSync` / `execSync` | 0 (nur `importRe.exec(source)` in `verify-build.mjs:133`, Regex-Exec, keine Prozessausführung) | ✔ |
| `shell=True` / `os.system` / `subprocess` | 0 in Plugin-Laufzeitcode | ✔ |
| `subprocess.run` | 4 Treffer, **alle in Build-Tests** (`dist/plugins/*/test_build_*_plugin.py`), feste Argumentliste `[sys.executable, <skript>, --out, tmp_path]`, `cwd=REPO_ROOT`, **kein `shell=`** | ✔ kein RCE |
| `pickle` / `yaml.load` ohne Loader | 0 | ✔ |
| Fremd-URLs / Tracking | 0 | ✔ siehe unten |
| `console.*` | 1: `activate.ts:80` `console.error("ReqogniLoom: initState failed…", err)` | ⚠️ loggt ein `Error`-Objekt; `api.ts:138` wirft `ReqogniLoomApiError` mit Server-Text, **niemals** den Key → unkritisch |

Vollständige URL-Inventur in Plugin-Quellen:

```
ConnectScreen.tsx:48       https://reqogniloom.example.com     <- placeholder-Attribut, kein Request
plugin_api.py:24,91,96     http://localhost:* / 127.0.0.1:* / [::1]:*   <- Allowlist-Defaults
reqogniloom_client.py:66,71  http://localhost:8001                     <- Default-Base-URL
```

→ **Keine Drittanbieter-, Tracking- oder Analytics-Calls. Kein RCE. Kein
`eval`/`exec`/`shell=true`. Keine ungeprüften Pfade.** Isolation des Netz-Ausgangs
wird zusätzlich **laufend** belegt: das komplette Netlog des E2E-Laufs besteht aus
4 Requests, alle gegen `http://localhost:8001` (Evidenz 3 §3).

## 5. Discovery-/Installations-Mechanismus

| Plugin | Mechanismus | Code | Doku | fail-closed bei kaputtem Manifest? |
|---|---|---|---|---|
| Claude Code | **Explizit**: `claude plugin marketplace add dist/plugins/claude-code` → findet `.claude-plugin/marketplace.json` → `claude plugin install reqogniloom` → findet `reqogniloom/.claude-plugin/plugin.json` + `.mcp.json` | `build_claude_plugin.py:136-159` | `INSTALL.md:5-29` ✔ | **Nein** — der Builder schreibt `marketplace.json` **nur bei erfolgreichem** `build()`; ein fehlendes Manifest beim Install ist Host-Verhalten, nicht im Repo abgesichert. `test_build_claude_plugin.py:49-56` prüft nur den Builder-Pfad |
| Antigravity | **Hybrid**: `mcp_config.json` in die Antigravity-MCP-Konfiguration importieren **oder** `npx skills add … -a antigravity` | `build_antigravity_plugin.py:56-70` | `INSTALL.md:78-103` ✔ | **Nein**, wie oben |
| Hermes TS | **Manifest-gesteuert**: Host liest `hermes-plugin.json`, lädt `main` | `activate.ts:84-90` (default export) | **fehlt komplett** in `INSTALL.md` | **Nein**: `verify-build.mjs:43-46` bricht mit `process.exit(1)` ab, wenn das Bundle fehlt — aber das ist ein **Postbuild-Guard**, kein Laufzeit-Discovery-Gate. Ein Host, der `hermes-plugin.json` findet und `dist/plugin.js` nicht, bekommt keinen Fehler, sondern ein kaputes Plugin → AUD-2026-09-100 |
| Hermes Python | **Code-Import**: Host lädt `plugin.yaml`, ruft `register(ctx)` → `ctx.register_command("reqogniloom", …)` | `__init__.py:168-173` | `integrations/hermes-agent-plugin/README.md` (190 Z.) ✔ | **Nein** |
| Hermes Python Dash | **Host-gemountet**: Hermes mountet `plugin_api.router` unter `/api/plugins/reqogniloom/`; Pfad aus `manifest.json:7` (`tab.path: /reqogniloom`) | `plugin_api.py:296,308-339` | README ✔ | **Ja, fail-closed**: `enforce_dashboard_auth:130-146` wirft `DashboardAuthError(403)` wenn `REQOGNILOOM_DASHBOARD_TOKEN` leer ist — „Misconfiguration fails closed, not open". Gate läuft **doppelt**: Router-Dependency (`:294`) **und** in jedem Handler (`:311,323,334`). Positiv-Befund |

**Befund zum Mechanismus:** Kein Plugin verwendet Auto-Discovery per
Verzeichnis-Scan; alle vier nutzen einen expliziten Manifest-/Mount-Pfad. Der
**Python-Dash-Auth-Guard** ist das einzige fail-closed-Gate im ganzen Bestand — und
es ist das einzige Plugin, dessen Auth-Pfad ich vollständig statisch verifizieren
konnte (kein Host verfügbar).

## 6. Was ausdrücklich NICHT verifizierbar war (BLOCKED, nicht PASS)

| Nr | Sachverhalt | Grund |
|---|---|---|
| B1 | Ob `claude plugin marketplace add`/`install` die Pakete real akzeptiert (v. a. `marketplace.json` ohne `version`) | `claude` CLI nicht auf diesem Host installiert |
| B2 | Ob Antigravity `plugin.json` (5 Felder) und `mcp_config.json` ohne `type` akzeptiert | Antigravity nicht installiert; kein öffentlich gepinntes Manifest-Schema im Repo |
| B3 | `tab.position: "after:analytics"` | Hermes-Dashboard nicht installiert |
| B4 | Ob Hermes die `engines.hermes >=3.0.0`-Beschränkung tatsächlich durchsetzt | Hermes nicht installiert; kein Code im Repo liest das Feld |
| B5 | Ob Antigravity/Claude-Code `${VAR}` in `mcpServers.url`/`headers` auflösen (anders als OpenCodes `{env:VAR}`) | Hosts nicht installiert; `INSTALL.md:89-90` behauptet es, ist aber unbelegt |

Diese fünf Punkte sind **BLOCKED**. Keiner davon wurde als PASS gewertet.
