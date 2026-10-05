# One-Click-Installation je Provider-Harness — Umsetzungskonzept

| Feld | Wert |
|---|---|
| **Status** | Entwurf zur Review (noch nicht umgesetzt) |
| **Datum** | 2026-10-04 |
| **Basis** | `v1.8.0-beta.18`, QS-Sandbox `172.20.5.120`, empirische Client-Tests |
| **Bezug** | #1171 (konsolidiertes Issue), #1170 (`artifact_search`), #1169 (Codex headless), #1153 (Session-Header), #1085 (Doku-Drift) |
| **Bugfix-Hub** | Umsetzung läuft als Bundle **B0** — [`docs/bugfix-hub/README.md`](../bugfix-hub/README.md) · [`docs/plans/2026-10-05-bugfix-hub-integrationen.md`](2026-10-05-bugfix-hub-integrationen.md) |
| **Geltung** | Claude Code, Codex CLI, OpenCode, Kimi Code, Antigravity, Hermes |
| **Nicht Teil dieses Plans** | Änderungen am MCP-Server selbst, an Rollen/Skills-Inhalten, an der LLM-Anbindung des Backends |

---

## 0. Management Summary

Ziel ist ein Zustand, in dem **jeder** unterstützte Coding-Harness mit **einem Befehl** an eine ReqogniLoom-Instanz angebunden ist — inklusive Rollen/Skills und einem **verifizierten** Smoke-Test. Heute gilt:

1. **Fünf von sechs Harnessen können das technisch schon** — die nativen Mechanismen existieren (`claude plugin marketplace add`, `codex mcp add`, `opencode mcp add`/`opencode plugin`, `hermes mcp install` aus dem Nous-Katalog, Antigravity MCP-Store). Sie werden nur **nicht genutzt, nicht veröffentlicht und nicht dokumentiert**.
2. **Ein Harness kann es nicht**: Kimi Code hat **kein** MCP-Add-Kommando; dort ist ein Installer-Skript heute der einzige Weg (plus Upstream-Feature-Request).
3. **Die Doku widerspricht sich**: OpenCode steht in `docs/agent-templates/INSTALL.md` anders als in `dist/opencode/opencode.json.snippet` (zwei verschiedene Transport-/Typ-Angaben für denselben Client).
4. **Zwei Harnesse fehlen komplett** (Kimi Code: 0 Treffer; Hermes: nur das POC-Agent-Plugin, keine MCP-Anbindung).
5. **Die Modell-/Provider-Seite fehlt überall** — genau dort lagen in der QA die echten Blocker (Codex `wire_api`, Approval-Policy, `x-opencode-session`).

Der Plan teilt die Umsetzung bewusst in zwei Stufen:

| Stufe | Inhalt | Abhängigkeiten | Ergebnis |
|---|---|---|---|
| **Stufe 1** | **Lokale/git-basierte Installation** — Skripte, `docs/clients/` (DE+EN), Smoke-Tests, CI-Gates. **Keine Store-Veröffentlichung.** | keine (Repo-Zugriff genügt) | Jeder Client ist aus dem Repo in einem Befehl installierbar; Doku vollständig und widerspruchsfrei |
| **Stufe 2** | **Store-/Registry-Bereitstellung** — MCP-Registry, Claude-Marketplace-Repo, Codex-Marketplace, npm-Paket, Hermes-Katalogeintrag, Antigravity-Store, Kimi-Upstream — inkl. **GitHub-Actions-Pipelines** | Stufe 1 abgeschlossen; Accounts/Zugänge (npm-Org, Registry-Namespace) | `one-click` ohne Kenntnis dieses Repos: nur Name/URL nötig |

**Geschätzter Gesamtaufwand:** Stufe 1 ≈ **9–13 Personentage (PT)**, Stufe 2 ≈ **18–27 PT** (Details in §4.4 / §5.7). Stufe 1 liefert bereits **80 % des Nutzens** für alle, die dieses Repo kennen (Team, Kunden-Onboarding, interne Deployments) — deshalb die strikte Trennung.

**Zu entscheiden (§8):** Namespace-Konto für die MCP-Registry (persönlich vs. Organisation), npm-Scope-Name, ob ein eigenes Marketplace-Repo entsteht oder `dist/` mitveröffentlicht wird, und ob Pre-Releases (beta) in die Stores dürfen oder dort nur stabile Versionen erscheinen.

---

## 1. Zielbild und Begriffe

### 1.1 Definition „One-Click" (Stufenmodell)

„One-Click" wird hier nicht als Marketing-Wort, sondern als **testbare Leiter** definiert. Jeder Client wird genau einer Stufe zugeordnet; die Zielstufe ist **L3**.

| Stufe | Name | Definition | Beispiel |
|---|---|---|---|
| **L0** | Manuell | Datei selbst editieren, Werte manuell einsetzen, ohne Anleitung | TOML/JSON von Hand nachbauen |
| **L1** | Snippet | Copy-Paste-Block aus der Doku + dokumentierte Env-Vars | Heutiger Stand bei Codex/OpenCode |
| **L2** | Ein Befehl (lokal) | **Ein** dokumentierter Befehl gegen ein Git-Repo/Verzeichnis installiert MCP + Rollen/Skills | `codex mcp add …`, `claude plugin install …` gegen lokalen Marketplace |
| **L3** | Ein Befehl (verteilt) | **Ein** Befehl gegen einen öffentlichen Store/Registry, ohne Kenntnis dieses Repos — plus automatische Updates | `claude plugin marketplace add <owner>/<repo>` → `install`; `hermes mcp install reqogniloom` |

**Ergänzend gilt für jede Stufe ab L2 die Drei-Punkte-Regel:**
1. Der Client verbindet sich (Transport + Auth korrekt).
2. Rollen/Skills sind installiert und im Client sichtbar.
3. Ein definierter **Smoke-Test** läuft grün und liefert ein **erwartetes Ergebnis** (nicht nur „irgendeine Antwort").

### 1.2 Erfolgreich ist der Plan, wenn …

* **K1:** Jeder der sechs Clients erreicht L3 (Zielzustand), mindestens L2 nach Stufe 1.
* **K2:** Es gibt je Client **eine** Doku-Seite auf **Deutsch und Englisch** mit identischem Inhalt (Parität maschinell geprüft).
* **K3:** Ein neuer Nutzer kann ohne Rückfrage an das Team in ≤ 5 Minuten von „Repo bekannt" zu „MCP verbunden" kommen.
* **K4:** Ein CI-Job beweist bei jedem Release, dass die ausgelieferten Artefakte (Snippets, `plugin.json`, `marketplace.json`, `server.json`) **syntaktisch gültig** und **versionskonsistent** mit `VERSION` sind.
* **K5:** Kein Client-Dokument enthält noch einen Widerspruch zu einem anderen (OpenCode-Fall darf nicht erneut auftreten).

### 1.3 Nicht-Ziele

* Kein Umbau des MCP-Servers, keine neuen Tools, keine Änderung der Auth-Architektur (`reqlo_`-Präfix, `X-API-Key`/Bearer bleiben).
* Keine automatische Provisionierung des **Backends** (Compose-Deployment bleibt `deploy/` + `DEPLOY_RUNBOOK.md`).
* Kein Zwang, alle Aggregatoren (Smithery, Glama, PulseMCP …) zu bedienen — sie sind in §5.1 als *optional* markiert.

### 1.4 Geltungsbereich: Client-Matrix (verifiziert)

Alle Angaben stammen aus der beta.18-QA (`--help`-Ausgaben der installierten CLIs + echte Tool-Calls), nicht aus Hersteller-Doku.

| Client | Getestete Version | Transport (verifiziert) | Auth | MCP-Registrierung | Zielstufe |
|---|---|---|---|---|---|
| **Claude Code** | 2.1.267 | SSE `…/mcp/sse/` | `X-API-Key: reqlo_…` | `claude plugin marketplace add` + `install` / `claude mcp add` | **L3** |
| **Codex CLI** | 0.151.0 | Streamable HTTP `…/mcp/` | Bearer (`bearer_token_env_var`) | `codex mcp add <name> --url <url>` | **L3** |
| **OpenCode** | 1.18.31 | stdio-Bridge (verifiziert) oder `remote`/SSE | `X-API-Key` | `opencode mcp add`, `opencode plugin <modul>` | **L3** |
| **Kimi Code** | 2.1.1 | HTTP `…/mcp/` | Bearer-Env-Var | **kein** natives Kommando → Datei/Installer | **L2** (L3 erst mit Upstream-Feature) |
| **Antigravity** | (CLI auf QS-VM nicht lauffähig) | SSE `…/mcp/sse/` | `X-API-Key` | MCP-Store-Import + `npx skills add` | **L3** |
| **Hermes** | aktueller Stack | stdio-Bridge | Key in `~/.hermes/.env` | `hermes mcp add` / **Katalog** `hermes mcp install` | **L3** |

---

## 2. Ausgangslage

### 2.1 Was heute existiert

| Datei | Umfang | Deckt ab | Sprache |
|---|---|---|---|
| `docs/agent-templates/INSTALL.md` | ~8 KB | Claude Code, OpenCode, Antigravity (+ Codex nur in der Konventionstabelle), Regenerierungs-Pipeline | EN |
| `README.md` §9 „Connect an MCP Client" | — | Claude Desktop, Cursor, OpenCode, Codex CLI | EN |
| `dist/codex/config.toml.snippet` | 348 B | `url` + `bearer_token_env_var` | EN |
| `dist/opencode/opencode.json.snippet` | 197 B | MCP-Block | — |
| `dist/plugins/claude-code/` | Paket + Build-Skript | MCP-Config + Skills (Marketplace-fähig) | EN |
| `dist/plugins/antigravity/` | Paket + Build-Skript | MCP-Config + Skills | EN |
| `dist/plugins/hermes/` | Build-Skript | Hermes-Plugin-Paket | — |
| `integrations/hermes-agent-plugin/README.md` | ~12,6 KB | Hermes-**Agent**-Plugin (POC, mit „Known gaps") | EN |
| `integrations/hermes-plugin/` | Quellcode | Desktop-Plugin — **ohne README** | — |

**Beobachtung:** Die *Bausteine* sind zu ~80 % vorhanden (generierte Pakete + Build-Skripte). Es fehlen die **Veröffentlichung**, die **einheitliche Struktur** und die **Wahrheit zwischen den Dateien**.

### 2.2 Die fünf Lückenklassen

**(A) Fehlende Clients.** Kimi Code kommt in der Client-Doku **nicht ein einziges Mal** vor. Hermes ist nur als POC-Agent-Plugin beschrieben; die MCP-Server-Anbindung (`mcp_servers`, Bridge, `hermes mcp test`) fehlt.

**(B) Widersprüchliche Angaben.** Zwei Formen für denselben Client im selben Repo (siehe §2.3). Zusätzlich: `/mcp/` bei Codex, `/mcp/sse/` bei OpenCode-Snippet, Antigravity und Claude — beide laufen, aber **keine Regel, wann welcher**.

**(C) Modell-/Provider-Seite fehlt vollständig.** Kein Dokument erwähnt, dass der Client selbst ein Modell braucht. Genau dort lagen die Blocker: `wire_api="responses"` (Codex ≥ 0.151 lehnt `"chat"` ab, sonst kein Start), `--dangerously-bypass-approvals-and-sandbox` (sonst blockiert die Approval-Policy **jeden** MCP-Call), `x-opencode-session` (sonst HTTP 400 `MissingSessionID`), `ANTHROPIC_BASE_URL`/`ANTHROPIC_CUSTOM_HEADERS` (für eigene Anthropic-Endpunkte).

**(D) Verifikation fehlt.** „Verify"-Schritte gibt es nur für Claude Code, OpenCode, Antigravity. Für **Codex, Kimi, Hermes** fehlt jeder Nachweis — obwohl genau diese drei den Nutzern am häufigsten „verbunden, aber stumm" erscheinen.

**(E) Keine Sprachparität.** Die Client-Anleitung ist ausschließlich englisch, während zentrale Projektdokumente (`REQUIREMENTS.md`, `UI_KONZEPT.md`, `docs/plans/*`) deutsch sind.

### 2.3 Der OpenCode-Widerspruch (Musterfall für Doku-Drift)

```
docs/agent-templates/INSTALL.md          dist/opencode/opencode.json.snippet
{                                        {
  "mcp": {                                 "mcp": {
    "reqogniloom": {                         "reqogniloom": {
      "type": "http",           <-- anders   "type": "remote",       <-- anders
      "url": "{env:...}/mcp/",  <-- anders   "url": "{env:...}/mcp/sse/", <-- anders
      "options": { "headers": { "X-API-Key": … } }   "headers": { "X-API-Key": … }
```
In der QA real verbunden war eine **dritte** Variante: `"type":"local"` + stdio-Bridge (`command: ["python3", "…/bridge.py"]`). Damit existieren drei Formen; keine ist als „die richtige" markiert. Genau dieses Muster (zwei Dateien, ein Client, kein Single Source of Truth) ist die **Wurzel** aller Doku-Lücken — daher sieht §3.4/§4.1 dafür eine technische Sperre vor.

### 2.4 Verifizierte Fallstricke (Grundlage der Troubleshooting-Matrix, Anhang C)

| Symptom | Ursache | Fix |
|---|---|---|
| Codex startet nicht / Abbruch bei Custom-Provider | `wire_api = "chat"` nicht mehr unterstützt | `wire_api = "responses"` |
| Codex: „MCP tool call requires approval, but approval policy is never" | headless Call ohne Bypass | `--dangerously-bypass-approvals-and-sandbox` (nur in vertrauenswürdigen Läufen) |
| HTTP 400 `MissingSessionID` | Endpunkt verlangt `x-opencode-session` | Header setzen (Proxy/Config) |
| HTTP 403 `error code: 1010` | Cloudflare blockt Nicht-Browser-UA | `User-Agent` setzen |
| Kimi: „Skipping invalid entry … (id, name, api, type, models)" | Registry-Eintrag ohne `type` | `"type":"openai"` ergänzen |
| Antigravity: „FATAL ERROR … pclmul enabled" (exit 132) | Host-CPU ohne `pclmulqdq` (QEMU-CPU) | Host-/VM-CPU-Modell ändern (nicht software-lösbar) |
| Server „connected", aber keine Tools | falscher Transport (`/mcp/` vs `/mcp/sse/`) | Transportmatrix aus §3.3 nutzen |
---

## 3. Gemeinsame Architektur (für beide Stufen)

### 3.1 Die vier Bausteine jeder Client-Anbindung

Jede Anbindung besteht aus exakt vier Teilen. Die Doku muss **alle vier** abdecken — heute fehlen meist (2) und (4):

| # | Baustein | Inhalt | Heutige Abdeckung |
|---|---|---|---|
| 1 | **MCP-Endpunkt** | URL + Transport (SSE/HTTP/stdio) | vorhanden (Snippets) |
| 2 | **Auth/Konto** | Key-Erzeugung, Rolle/Scope, Header-Form | teilweise (Werte ja, *Bezug* nein) |
| 3 | **Rollen/Skills** | Skill-Dateien + `DOMAIN_MODEL.md` am richtigen Ort | vorhanden, aber pro Client verschieden |
| 4 | **Verifikation** | Smoke-Test mit **erwartetem** Ergebnis | **lückenhaft** |

### 3.2 Einheitliches Konfigurationsmodell

| Fakt | Wert | Quelle der Wahrheit |
|---|---|---|
| Endpunkt-Basis | `REQOGNILOOM_MCP_URL` (z. B. `https://reqogniloom.example`) | Deployment |
| API-Key | `REQOGNILOOM_API_KEY`, Präfix `reqlo_` | `backend/auth_tenancy/` (MCP erzwingt Präfix; JWT wird abgelehnt) |
| Auth-Header (Standard) | `X-API-Key` — **Ausnahme Codex: `Authorization: Bearer`** | Transport-Implementierung der Clients |
| Key-Scope | Rolle am Server entscheidet, **nicht** das Skill | Rollen-/RBAC-Modell |
| Skill-Ablage | je Client: `.opencode/skills`, `.agents/skills`, `~/.claude/skills`, … | `INSTALL.md` |
| `DOMAIN_MODEL.md` | muss mit ausgeliefert werden (relative Erwartung `../../DOMAIN_MODEL.md`) | Build-Skripte |

**Harte Regel:** Der Key wird **nie** in eine Config-Datei geschrieben, die ins Repo oder in ein öffentliches Verzeichnis gelangt. Alle Clients unterstützen Env-Var-Expansion (`{env:…}` bei OpenCode, `${…}` bei Antigravity, `bearer_token_env_var` bei Codex, Env bei Claude/Hermes).

### 3.3 Transport-Entscheidungsregel (neu)

Beide Transporte sind verifiziert lauffähig. Es fehlt die Regel — hier die vorgeschlagene:

| Transport | Pfad | Wann verwenden | Verifiziert bei |
|---|---|---|---|
| **Streamable HTTP** | `/mcp/` | Client spricht Streamable HTTP nativ (bevorzugt: weniger bewegliche Teile) | Codex 0.151.0 (12 Workspaces) |
| **SSE** | `/mcp/sse/` | Client-Plugin/Store-Lösung sieht SSE vor (Claude-Plugin, Antigravity) | Claude Code 2.1.267 (49 Requirements), Antigravity (`tools/list` → 222 Tools) |
| **stdio-Bridge** | lokales Skript | Client kann nur stdio (OpenCode `type:"local"`, Hermes) — nötig für Env-Isolation | OpenCode, Hermes (222 Tools) |

### 3.4 Single Source of Truth für die Client-Artefakte

Ursache des OpenCode-Widerspruchs ist die Doppelpflege. Vorschlag:

```
clients/registry.yaml                 <-- EINE Quelle: Endpunkte, Transport, Auth, Artefaktpfade
      │
      ├─> scripts/clients/render.py   <-- erzeugt aus registry.yaml:
      │       ├─ dist/**/…snippet / mcp_config.json / plugin.json
      │       ├─ docs/clients/*.md  +  *.de.md  (Blocks zwischen Markern)
      │       └─ <marketplace.json>  /  server.json  (Stufe 2)
      └─> .github/workflows/client-artifacts-check.yml (driftet? -> CI rot)
```

**Akzeptanzkriterium:** Ändert jemand nur die Doku oder nur ein Snippet, wird CI rot (dasselbe Muster wie `version-drift-check.yml` heute für Versionen). Damit ist Klasse (B) technisch ausgeschlossen, nicht nur „redaktionell verbessert".

### 3.5 Versionskopplung

Alle Client-Artefakte werden aus `VERSION` gespeist (`1.8.0-beta.18`). Für Stores gilt zusätzlich:

* **SemVer + Pre-Release-Kennzeichnung** bleiben wie in `VERSION`.
* npm: Pre-Releases gehen auf den **dist-tag `next`**, stabile Releases auf `latest` (die bestehende Docker-Publish-Logik macht das für Images genauso — Konsistenz).
* Marketplace-Einträge führen `version` explizit (Claude Code aktualisiert Plugins nur bei Versionsänderung).
* `server.json` (MCP-Registry) trägt dieselbe Version wie `VERSION`; Drift = CI rot.
---

## 4. STUFE 1 — Installation ohne Store-Veröffentlichung

**Definition:** Alles, was ohne Registrierung in externen Stores funktioniert — Installation aus dem geklonten Repo heraus (lokales Verzeichnis, lokaler Marketplace, Git-URL des Repos). Zielstufe: **L2** für alle sechs Clients, mit vollständiger DE/EN-Doku.

### 4.1 Gemeinsame Vorarbeit (Basis für alle Clients)

**AP-1.1 — `clients/registry.yaml` (Single Source of Truth)** · 1 PT
Enthält je Client: Name, getestete Version, Transport, Pfade, Auth-Form, Env-Vars, Skill-Ablage, Verify-Kommando + erwartetes Ergebnis. Grundlage für Renderer (AP-1.2) und CI (AP-1.5).

**AP-1.2 — Renderer `scripts/clients/render.py`** · 2 PT
Erzeugt aus AP-1.1: die bestehenden Snippets (`dist/**`), die `docs/clients/*.md` (Blöcke zwischen `<!-- generated:begin/end -->`-Markern), sowie Stufe-2-Artefakte (`marketplace.json`, `server.json`). **Idempotent** — ein zweiter Lauf ändert nichts.

**AP-1.3 — Installer/Verifier-Skripte** · 2 PT
* `scripts/clients/install.sh --client <name> --url <url> --key-env <VAR> [--dry-run] [--yes]`
  * prüft Voraussetzungen (Binary vorhanden? Version?), schreibt **nur** die Client-Config (mit Backup `.bak-<timestamp>`),
  * ruft danach automatisch `verify.sh` auf.
* `scripts/clients/verify.sh --client <name>` — der einheitliche Smoke-Test (§4.3).
* Beide Skripte: `set -euo pipefail`, keine Secrets in `argv` (nur **Namen** von Env-Vars), `--dry-run` zeigt die Diffs.

**AP-1.4 — Doku-Baum `docs/clients/`** · 3 PT (überwiegend Redaktion)
```
docs/clients/
  README.md          README.de.md          # Matrix, Entscheidungshilfe, Troubleshooting
  claude-code.md     claude-code.de.md
  codex.md           codex.de.md
  opencode.md        opencode.de.md
  kimi-code.md       kimi-code.de.md
  antigravity.md     antigravity.de.md
  hermes.md          hermes.de.md
```
Feste Abschnittsfolge je Seite (siehe Anhang A), damit Nutzer und Prüf-Workflow (AP-1.5) sich darauf verlassen können. `README.md` §9 und `INSTALL.md` werden auf `docs/clients/` **verlinkt** (nichts wird gelöscht).

**AP-1.5 — CI-Gate „Client-Artefakte"** · 1,5 PT
Neuer Job (im bestehenden `ci.yml` oder als eigenes Workflow): 
1. `render.py` laufen lassen → `git diff --exit-code` (fängt Doku-Drift, Klasse B),
2. JSON/TOML der Snippets gegen Schema/Minimalregeln validieren,
3. DE/EN-Parität prüfen (gleiche Überschriften-Anzahl, gleiche Codeblöcke),
4. Versionskonsistenz gegen `VERSION`,
5. Link-Check auf `docs/clients/**`.
Alles read-only, keine Secrets → auch auf PRs lauffähig.

### 4.2 Clients im Detail

> Struktur je Client identisch: **a)** Voraussetzungen · **b)** Ein-Befehl (L2) · **c)** Fallback manuell · **d)** Modell/Provider · **e)** Verify (erwartet) · **f)** Fallstricke · **g)** Testkriterien · **h)** offen bis Stufe 2.

#### 4.2.1 Claude Code (2.1.267) — AP-1.6 · 1 PT

**a) Voraussetzungen:** `claude` ≥ 2.1.x (Binary im PATH), Netzwerk zum MCP-Endpunkt, `reqlo_…`-Key mit passender Rolle (read-only für Audit-Zwecke empfohlen).
**b) Ein-Befehl (lokal, L2):**
```bash
# 1) Marketplace aus dem Repo registrieren, 2) Plugin installieren
claude plugin marketplace add ./dist/plugins/claude-code
claude plugin install reqogniloom@claude-code      # Name aus dem Marketplace-Eintrag
# Env vor dem Start:
export REQOGNILOOM_MCP_URL="https://<host>"
export REQOGNILOOM_API_KEY="reqlo_…"
```
**c) Fallback (ohne Marketplace):** `claude mcp add --transport http reqogniloom "<URL>/mcp/sse/" --header "X-API-Key: ${REQOGNILOOM_API_KEY}"` — nützlich für Einzelplatz ohne Plugin.
**d) Modell/Provider:** Standard (Anthropic-Abo/Key) unverändert. Für eigene Anthropic-kompatible Endpunkte: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_CUSTOM_HEADERS` (verifiziert: `/v1/messages` mit `x-api-key` + Pflicht-Session-Header → HTTP 200). Warnung `[claude-code:unrecognized_model]` ist bei Fremdmodellen **kosmetisch**.
**e) Verify (erwartet):**
```bash
claude mcp list      # -> plugin:reqogniloom:reqogniloom: http://<host>/mcp/sse/ (SSE) - ✔ Connected
claude plugin details reqogniloom   # -> Skill-/Agent-Inventar
# Smoke-Test im Client: "Nutze reqogniloom und nenne die Anzahl der Requirements im Workspace <w>"
# -> "49 Requirements" (Referenzwert QS-Workspace)
```
**f) Fallstricke:** Marketplace-/Entry-Name **muss** mit `plugin.json → name` übereinstimmen (sonst `Plugin "x" not found in marketplace "y"`); reservierte Marketplace-Namen (`claude-plugins-official`) sind gesperrt; relative `source`-Pfade werden ab Marketplace-Wurzel geschrieben.
**g) Testkriterien:** `claude plugin validate ./dist/plugins/claude-code` → `✔ Validation passed`; `claude plugin list` → `enabled`; Smoke-Test liefert exakt `49`.
**h) Offen bis Stufe 2:** öffentliches Marketplace-Repo; Env-Var-Automatisierung (Prüfung, ob `plugin.json` einen Config-Mechanismus anbietet, sonst dokumentierter `/plugin`-Schritt).

#### 4.2.2 Codex CLI (0.151.0) — AP-1.7 · 1 PT

**a) Voraussetzungen:** `codex` ≥ 0.151 (Binary im PATH), Key, **Modell-Provider konfiguriert** (siehe d).
**b) Ein-Befehl (L2):**
```bash
codex mcp add reqogniloom --url "https://<host>/mcp/"
codex mcp list            # -> reqogniloom   enabled
export REQOGNILOOM_API_KEY="reqlo_…"   # wird via bearer_token_env_var gelesen
```
**c) Fallback:** Snippet `dist/codex/config.toml.snippet` in `~/.codex/config.toml` bzw. `.codex/config.toml` mergen (nur vertrauenswürdige Projekte).
**d) Modell/Provider (der heute fehlende Teil):**
```toml
# Custom-Provider: Chat-Completions ist entfernt, Responses-API ist Pflicht
[model_providers.<name>]
wire_api = "responses"
```
Headless-MCP-Calls brauchen `--dangerously-bypass-approvals-and-sandbox`; ohne Bypass blockiert die Approval-Policy **jeden** MCP-Aufruf („MCP tool call requires approval, but approval policy is never") — nur in kontrollierten Läufen verwenden (siehe #1169).
**e) Verify (erwartet):**
```bash
codex mcp list                                  # -> enabled
codex exec "Nutze reqogniloom und liste die Workspaces" --skip-git-repo-check \
  --dangerously-bypass-approvals-and-sandbox
# -> "12 Workspaces, der erste heißt QA-HONCHO-…" (Bindeglied: REST-Gegenprobe count=12)
```
**f) Fallstricke:** `wire_api="chat"` → Abbruch; Warnung „bubblewrap not found" betrifft nur die Shell-Sandbox (für MCP irrelevant); Modell-Metadaten-Warnung bei Fremdmodellen ist kosmetisch.
**g) Testkriterien:** 2× reproduzierter Lauf mit identischem Ergebnis (QA-Beleg: 1.082 / 1.152 Tokens, zwei Sessions).
**h) Offen bis Stufe 2:** Codex-Marketplace (`codex plugin marketplace add` + `codex plugin add`).

#### 4.2.3 OpenCode (1.18.31) — AP-1.8 · 1,5 PT

**a) Voraussetzungen:** `opencode` im PATH, Key; Skills-Ablage beschreibbar.
**b) Ein-Befehl (L2) — zwei gleichwertige Wege:**
```bash
# Weg A (empfohlen in Stufe 1, verifiziert): stdio-Bridge, isoliert Env
opencode mcp add reqogniloom      # interaktiv -> command python3 <bridge>
# Weg B: remote
opencode mcp add reqogniloom --url "https://<host>/mcp/sse/"
```
**c) Widerspruch auflösen (Kern dieser AP):** Es gibt drei Formen in der Wildbahn:
| Form | Wo | Status |
|---|---|---|
| `"type":"local"` + `command: ["python3","…/bridge.py"]` | installierte QA-Config | **verifiziert verbunden** |
| `"type":"remote"` + `url …/mcp/sse/` + Top-Level-`headers` | `dist/opencode/opencode.json.snippet` | plausibel, **nicht** gegengeprüft |
| `"type":"http"` + `url …/mcp/` + `options.headers` | `docs/agent-templates/INSTALL.md` | **widerspricht** dem Snippet |
→ **Aufgabe:** genau eine Form als „supported" festlegen, gegen einen echten Client prüfen, die beiden anderen Dateien anpassen. Bis dahin dokumentiert die Seite alle drei **mit Statuskennzeichnung**.
**d) Modell/Provider:** `opencode-go/…` funktioniert (verifiziert: echter Tool-Call → 49 Requirements). Free-Tier-Modelle (`opencode/*-free`) waren zum Testzeitpunkt serverseitig defekt (`UnknownError`) — als Umgebungszustand kennzeichnen, nicht als Produktfehler.
**e) Verify (erwartet):**
```bash
opencode mcp list                 # -> ✓ reqogniloom connected
# Skill-/Tool-Test: requirement_query gegen den QS-Workspace -> 49
```
**f) Fallstricke:** `{env:NAME}` wird expandiert, ein blankes `{...}` nicht (wird literal gesendet → stille Fehlfunktion); `DOMAIN_MODEL.md` muss **zwei Ebenen über** `skills/<name>/SKILL.md` liegen; es gibt **keine** client-seitige Tool-Beschränkung je Skill → Rechte über den Key-Scope steuern.
**g) Testkriterien:** `opencode mcp list` grün + echter Tool-Call (nicht nur „connected").
**h) Offen bis Stufe 2:** npm-Plugin-Paket, damit `opencode plugin <modul>` MCP **und** Skills in einem Schritt installiert.
#### 4.2.4 Kimi Code (2.1.1) — AP-1.9 · 1,5 PT

**a) Voraussetzungen:** `kimi` im PATH, Key, Schreibzugriff auf `~/.kimi-code/`.
**b) Ein-Befehl (L2, Skriptweg — Kimi hat kein natives MCP-Add):**
```bash
scripts/clients/install.sh --client kimi-code --url "https://<host>" --key-env REQOGNILOOM_API_KEY
# schreibt ~/.kimi-code/mcp.json  +  Skills in das auto-discovered --skills-dir
kimi doctor        # -> Konfiguration valide
```
**c) Fallback:** `~/.kimi-code/mcp.json` von Hand setzen (Struktur im Anhang B).
**d) Modell/Provider:** Kimi arbeitet mit eigenen/managed Providern. Fremd-Provider nur über eine Registry: `kimi provider add <api.json>` — dabei gilt: **das Feld `type` ist Pflicht** (fehlt es, wird der Eintrag verworfen: „Skipping invalid entry … (id, name, api, type, models)"). Managed-Quota kann einen Lauf mit 403 blockieren („usage limit") — kein ReqogniLoom-Fehler.
**e) Verify (erwartet):** Tool-Call über den MCP-Server → „Die Workspace-Liste enthält **12** Workspaces" (verifiziert; REST-Gegenprobe 12).
**f) Fallstricke:** kein `kimi mcp`-Kommando; Cloudflare kann Nicht-Browser-Clients mit `403 code: 1010` abweisen (UA setzen); Config-Validierung nur per `kimi doctor`.
**g) Testkriterien:** `kimi doctor` grün + echter Tool-Call mit Gegenprobe.
**h) Offen bis Stufe 2:** Upstream-Feature-Request für ein natives `kimi mcp add`; bis dahin bleibt L2 die Obergrenze.

#### 4.2.5 Antigravity — AP-1.10 · 1,5 PT

**a) Voraussetzungen:** Antigravity-Installation; **Host-CPU mit `pclmulqdq`** (auf der QS-VM nicht erfüllt → Binary bricht mit exit 132 und „This binary was compiled with pclmul enabled" ab; nicht software-lösbar, siehe Anhang C); Key.
**b) Ein-Befehl (L2):**
```bash
# MCP-Config importieren (Store oder Datei)
#  -> dist/plugins/antigravity/reqogniloom/mcp_config.json   (endet auf .../mcp/sse/, Header X-API-Key)
npx skills add ./dist/plugins/antigravity/reqogniloom -a antigravity
```
**c) Fallback:** `mcpServers.reqogniloom`-Block manuell in `~/.gemini/config/mcp_config.json` bzw. `.agents/mcp_config.json` mergen; Variablen `${REQOGNILOOM_MCP_URL}` / `${REQOGNILOOM_API_KEY}` müssen in der Umgebung aufgelöst werden.
**d) Modell/Provider:** Kein ReqogniLoom-spezifischer Teil; Hinweis auf die Plattform-Reife (Preview) bleibt.
**e) Verify (erwartet):** SSE-Session gegen `/mcp/sse/` mit `X-API-Key` → `initialize` (202 + Event) → `tools/list` liefert **222 Tools** (verifiziert). Antigravity-Panel zeigt `reqogniloom` verbunden.
**f) Fallstricke:** CPU-Feature (oben); Antigravity ist Preview mit dokumentierten Sicherheitsfindungen → **Read-only-Key** empfehlen; wie OpenCode **keine** Tool-Beschränkung je Skill.
**g) Testkriterien:** Paket-Build-Test (rc=0, `plugin.json`/`mcp_config.json` md5-gleich zum Repo-`dist`), SSE-Handshake, Tool-Zahl 222.
**h) Offen bis Stufe 2:** Veröffentlichung im MCP-Store statt Datei-Merge.

#### 4.2.6 Hermes — AP-1.11 · 1 PT

**a) Voraussetzungen:** Hermes-Installation (dieser Stack), MCP-Bridge (`reqogniloom-mcp-bridge`), Key in `~/.hermes/.env`.
**b) Ein-Befehl (L2):**
```bash
hermes mcp add reqogniloom          # discovery-first
hermes mcp test reqogniloom         # -> ✓ Connected, 222 Tools
```
**c) Fallback:** `mcp_servers.<name>` in der Hermes-Konfiguration + Bridge-Pfad; Desktop-Plugin zusätzlich über `integrations/hermes-plugin/` (README fehlt → AP-1.11 liefert sie nach).
**d) Modell/Provider:** unabhängig (Hermes nutzt seine eigene LLM-Config).
**e) Verify (erwartet):** `hermes mcp test` → `✓ Connected` (QA: 2232 ms, 222 Tools); echte Calls: `requirement_query` → **49**, `architecture_query` → 1, `artifact_search "Motorsafe"` → Top-Treffer korrekt.
**f) Fallstricke:** Zwei getrennte Integrationspfade (Desktop-Plugin vs. Agent-Plugin) — in der Doku klar trennen; `integrations/hermes-plugin/` hat heute keine README.
**g) Testkriterien:** `mcp test` grün + zwei echte Tool-Calls mit Gegenprobe.
**h) Offen bis Stufe 2:** Katalogeintrag (dann `hermes mcp install reqogniloom` = L3).

### 4.3 Einheitlicher Smoke-Test (Definition)

Ein **einziger** Testfall, der über alle Clients identisch formuliert ist — damit Ergebnisse vergleichbar und gegenprüfbar sind:

| Element | Wert |
|---|---|
| **Referenz-Workspace** | dedizierter QA-Workspace (`QA-CLIENTSMOKE-<datum>`), **nicht** produktiv |
| **Aufgabe an den Client** | „Nutze das reqogniloom-MCP-Werkzeug und nenne die Anzahl der Requirements im Workspace `<id>`." |
| **Erwartung** | eine Zahl, die exakt der REST-Gegenprobe entspricht (`GET /api/v1/requirements/?workspace_id=…` → `count`) |
| **Zweitabfrage** | „Liste die Workspaces" → Anzahl muss der REST-Gegenprobe entsprechen |
| **Bestanden, wenn** | beide Zahlen übereinstimmen **und** im Client-Log der MCP-Call sichtbar ist (kein Freitext-Raten) |

**Negativtests (gehören in `verify.sh`):** falscher Transport (SSE gegen einen HTTP-only-Client) → muss sauber scheitern; ungültiger Key → 401/403 **ohne** Absturz; leerer Workspace → 0, nicht „Fehler".

### 4.4 Aufwand Stufe 1

| AP | Inhalt | PT |
|---|---|---|
| AP-1.1 | `registry.yaml` | 1,0 |
| AP-1.2 | Renderer + Idempotenz-Test | 2,0 |
| AP-1.3 | `install.sh` / `verify.sh` | 2,0 |
| AP-1.4 | `docs/clients/**` (7×2 Dateien) | 3,0 |
| AP-1.5 | CI-Gate Client-Artefakte | 1,5 |
| AP-1.6–1.11 | je Client (Verifikation, Fallstricke, Abnahme) | 6 × 0,5–1,5 |
| **Summe** | | **≈ 9–13 PT** |

### 4.5 Definition of Done — Stufe 1

1. `scripts/clients/install.sh --client <x>` funktioniert für **alle sechs** Clients und ist idempotent (2. Lauf ohne Änderung).
2. `docs/clients/README.md` + `README.de.md` listen alle sechs Clients mit Transport, Auth, Verify und Fallstricken.
3. Je Client existiert ein **belegter** Smoke-Test (Ausgabe im PR/Issue dokumentiert).
4. CI-Gate „Client-Artefakte" ist grün und würde Doku-Drift rot machen (Nachweis: absichtliche Drift im Test-PR).
5. Kein Client-Dokument widerspricht einem anderen (Peer-Review gegen `registry.yaml`).
6. `README.md` §9 und `docs/agent-templates/INSTALL.md` verweisen auf `docs/clients/` (keine Doppelpflege mehr).
---

## 5. STUFE 2 — Store-/Registry-Bereitstellung

**Definition:** Verteilung über öffentliche Stores/Registries, sodass „One-Click" **ohne** Kenntnis dieses Repos funktioniert (L3) — inklusive automatischer Updates und maschineller Nachvollziehbarkeit (Provenance).

### 5.1 Store-Landkarte

| # | Store / Kanal | Wer installiert daraus | Artefakt | Aufnahmeverfahren (verifiziert) | Aufwand | Risiko |
|---|---|---|---|---|---|---|
| S1 | **Offizielle MCP-Registry** `registry.modelcontextprotocol.io` | jeder registry-fähige MCP-Client | `server.json` (+ Paket zur Ownership-Prüfung) | `mcp-publisher init` → `login github-oidc` → `publish`; Namespace `io.github.<owner>/*`; npm braucht `mcpName` == `server.json.name` | 2–3 PT | **Preview**: Breaking Changes/Daten-Resets möglich |
| S2 | **Claude-Code-Marketplace** (Git-Repo mit `.claude-plugin/marketplace.json`) | Claude-Code-Nutzer | `marketplace.json` + Plugin-Eintrag | **im eigenen Repo möglich** (Repo = Marketplace) → `claude plugin marketplace add Popoboxxo/ReqogniLoom` + `install reqogniloom@…`; `claude plugin validate` | 1 PT | gering |
| S3 | **Anthropic Plugin Directory** (optional) | alle Claude-Code-Nutzer | dito, geprüft | Submission-Verfahren von Anthropic, Review | 0,5 PT + Wartezeit | Review kann ablehnen |
| S4 | **Codex-Plugin-Marketplace** | Codex-Nutzer | Marketplace-Snapshot + Plugin | `codex plugin marketplace add` + `codex plugin add` | 2 PT | Format noch zu verifizieren |
| S5 | **npm** (`@<scope>/reqogniloom-opencode`, `…-kimi-installer`) | `opencode plugin <modul>`, `npx`-Installer | npm-Paket | **Trusted Publishing (OIDC)**, `id-token: write`, CLI ≥ 11.5.1/Node ≥ 22.14, GitHub-hosted Runner; Pre-Releases → dist-tag `next` | 2 PT + 1 PT/Paket | Scope-/Namenwahl nötig |
| S6 | **Hermes MCP-Katalog (Nous)** | Hermes-Nutzer | Katalogeintrag | Aufnahme in den geprüften Katalog (= Voraussetzung für `hermes mcp install reqogniloom`) | 1 PT + Fremdprozess | Abhängig von Nous |
| S7 | **Antigravity MCP-Store** + Skills-Registry | Antigravity-Nutzer | `mcp_config.json` + Skills | Store-Import statt Datei-Merge; `npx skills add … -a antigravity` | 1–2 PT | Preview-Plattform |
| S8 | **Aggregatoren** (Smithery, Glama, PulseMCP, mcp.so, awesome-mcp-servers) | Discoverability | Verweis/Metadaten | Liste/PR je Anbieter | 0,25–0,5 PT je | gering, optional |
| S9 | **OCI/GHCR** (Option) | Registry-Einträge, die auf ein Container-Paket zeigen | bestehendes Image | GHCR ist eine von der MCP-Registry akzeptierte Paketquelle | 0 (existiert) | nur relevant, falls Server als Paket ausgeliefert wird |

**Wichtige Erkenntnis:** Für **S2 muss kein zweites Repository** entstehen. `marketplace.json` kann im ReqogniLoom-Repo selbst liegen (`.claude-plugin/marketplace.json`) und die Plugins per `source` referenzieren:
```json
{
  "source": "git-subdir",
  "url": "Popoboxxo/ReqogniLoom",
  "path": "dist/plugins/claude-code"
}
```
Damit ist der öffentliche Ein-Befehl-Weg nur noch eine Datei + ein CI-Check entfernt.

### 5.2 Artefakt- und Releasemodell

| Artefakt | Pfad (erzeugt von) | Veröffentlicht in | Version aus | Update-Mechanismus |
|---|---|---|---|---|
| Claude-Plugin + `marketplace.json` | `dist/plugins/claude-code/`, `.claude-plugin/marketplace.json` | S2, S3 | `VERSION` | Nutzer: `claude plugin update` |
| Codex-Snippet + Paket | `dist/codex/` | Repo, S4 | `VERSION` | Marketplace-Snapshot |
| OpenCode-npm-Paket | `dist/opencode/` → npm-Build | S5 | `VERSION` | `npm i -g` / `opencode plugin` |
| Kimi-Installer | `scripts/clients/install.sh` (+ optional npm) | Repo, S5 | `VERSION` | Repo-Pull / npx |
| Antigravity-Plugin | `dist/plugins/antigravity/` | Repo, S7 | `VERSION` | Store-Update |
| Hermes Eintrag | `server.json`-artige Metadaten | S6 | `VERSION` | Katalog-Update |
| `server.json` | Repo-Wurzel (generiert) | S1 | `VERSION` | Workflow bei Tag |

**Regeln:** (1) Jedes Artefakt wird **generiert**, nie handgepflegt (bereits Repo-Konvention). (2) Pre-Releases (`-beta.*`) gehen **nicht** in kuratierte Verzeichnisse (S3, S6), sondern nur auf `next`-Kanäle. (3) Jede Veröffentlichung trägt eine Version, die exakt `VERSION` entspricht — `version-drift-check.yml` wird um die Store-Versionen erweitert.

### 5.3 GitHub-Actions-Pipelines

**Designprinzip:** Die neuen Workflows **erben** die bestehende Härtung aus `docker-publish.yml` — `needs: ci` als Gate, `concurrency` ohne `cancel-in-progress` bei Publishes, **alle Actions SHA-gepinnt**, minimale `permissions`, Environment-Gate (`staging`/`release`) vor jedem Schreibzugriff, Attestierungen/Provenance.

| Workflow | Trigger | Zweck | Secrets/Rechte |
|---|---|---|---|
| `client-artifacts-check.yml` | PR, push `main` | Drift-/Paritäts-/Schema-Prüfung (Stufe 1) | keine (read-only) |
| `release-client-artifacts.yml` | Tag `v*.*.*` | Pakete bauen, validieren, an GH-Release hängen | `contents: write` |
| `publish-npm.yml` | Tag `v*.*.*`, `workflow_dispatch` | npm-Publish (OIDC) | `id-token: write` (kein Token!) |
| `publish-marketplace.yml` | Tag, nach `release-client-artifacts` | `marketplace.json`+`plugin.json`-Versionen aktualisieren, committen/PR | `contents: write` |
| `publish-mcp-registry.yml` | Tag, `workflow_dispatch` | `server.json` → MCP-Registry | `id-token: write` |
| `client-smoke.yml` | nightly + `workflow_dispatch` | echte Clients gegen QA-Instanz (Matrix) | Test-Key, keine Prod-Daten |

**Auszug `publish-npm.yml` (OIDC, keine Long-Lived-Tokens):**
```yaml
name: Publish npm package
on:
  push:
    tags: ['v*.*.*']
  workflow_dispatch:
concurrency:
  group: npm-publish-${{ github.ref }}
  cancel-in-progress: false
permissions:
  contents: read
  id-token: write          # OIDC für Trusted Publishing (ersetzt NPM_TOKEN)
jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release   # Gate mit Reviewer, wie docker-publish
    needs: []              # in der Praxis: needs: client-artifacts-check
    steps:
      - uses: actions/checkout@<SHA>          # gepinnt, wie repo-üblich
      - uses: actions/setup-node@<SHA>
        with:
          node-version: '22.14'
          registry-url: 'https://registry.npmjs.org'
          package-manager-cache: false         # nie Caching in Release-Builds
      - run: npm ci --ignore-scripts
      - run: npm run build --if-present
      - name: dist-tag bestimmen
        run: |
          if [[ "${{ github.ref_name }}" == *-* ]]; then echo "TAG=next"; else echo "TAG=latest"; fi >> "$GITHUB_ENV"
      - run: npm publish --provenance --tag "$TAG" --access public
```

**Auszug `publish-mcp-registry.yml`:**
```yaml
name: Publish to MCP Registry
on:
  push:
    tags: ['v*.*.*']
permissions:
  contents: read
  id-token: write          # GitHub-OIDC, kein PAT
jobs:
  publish:
    runs-on: ubuntu-latest
    environment: release
    steps:
      - uses: actions/checkout@<SHA>
      - name: mcp-publisher installieren
        run: |
          curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
          sudo mv mcp-publisher /usr/local/bin/
      - name: server.json prüfen
        run: mcp-publisher validate        # Fail-fast vor dem Publish
      - name: Login (OIDC)
        run: mcp-publisher login github-oidc
      - name: Publish
        run: mcp-publisher publish
```
> **Voraussetzungen, die vorher im Repo entstehen müssen:** `server.json` mit
> `name = "io.github.popoboxxo/reqogniloom"`, `description`, `repository`, `version` == `VERSION`,
> Transport-/Umgebungsvariablen-Block. Für den **Remote-Server**-Fall gilt die `remotes`-Variante des Schemas —
> die exakte Feldform ist vor der ersten Veröffentlichung gegen `server.schema.json` (2025-12-11) zu prüfen.

**Auszug `publish-marketplace.yml` (Kern):**
```yaml
      - name: Marketplace-Versionen aus VERSION spiegeln
        run: python scripts/clients/render.py --write-marketplace
      - run: claude plugin validate ./.claude-plugin/../   # Marketplace-Wurzel validieren
      - name: Commit (oder PR) wenn sich etwas geändert hat
        run: |
          git config user.name  "github-actions[bot]"
          git diff --quiet && exit 0
          git commit -am "chore(marketplace): sync versions from VERSION [skip ci]"
          git push
```

**Auszug `client-smoke.yml` (Matrix, Stufe 1+2 abgesichert):**
```yaml
jobs:
  smoke:
    strategy:
      fail-fast: false
      matrix:
        client: [claude-code, codex, opencode, kimi-code, hermes]
        # antigravity: nur mit self-hosted Runner (CPU mit pclmulqdq)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - run: docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.ci.yml up -d
      - run: scripts/clients/install.sh --client ${{ matrix.client }} --url http://localhost:8001 --key-env QA_KEY --yes
      - run: scripts/clients/verify.sh --client ${{ matrix.client }}   # erwartet: REST-Gegenprobe == Client-Antwort
```
**Hinweis zur Realität:** Antigravity ist in GitHub-hosted Runnern **nicht** testbar (CPU ohne `pclmulqdq`). Entweder self-hosted Runner (dann aufnehmen) oder bewusst aus der CI nehmen und nur manuell abnehmen — die Entscheidung gehört in §8.

### 5.4 Rollout in Wellen

| Welle | Inhalt | Abhängig von | Ergebnis |
|---|---|---|---|
| **W0** | Stufe 1 komplett (Doku, Skripte, CI-Gate) | — | L2 für alle sechs, Doku DE/EN |
| **W1** | `marketplace.json` im Repo + `release-client-artifacts` + `publish-marketplace` | W0 | **L3 für Claude Code** (kein Fremdkonto nötig) |
| **W2** | npm-Paket(e) + `publish-npm` | npm-Scope, W0 | L3 für OpenCode (Plugin-Weg), Kimi-Installer via npx |
| **W3** | `server.json` + `publish-mcp-registry` | Namespace-Konto, W2 (npm-Ownership) | Auffindbarkeit in registry-fähigen Clients |
| **W4** | Codex-Marketplace (S4), Antigravity-Store (S7) | Formate verifiziert, W0 | L3 für Codex + Antigravity |
| **W5** | Hermes-Katalogeintrag (S6), Kimi-Upstream-FR, Aggregatoren (S8) | Fremdprozesse | L3 für Hermes, Perspektive für Kimi |

### 5.5 Risikoregister

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| MCP-Registry ist **Preview** (Resets/Breaking Changes) | Eintrag kann verschwinden | `server.json` im Repo versionieren; Publish idempotent per Workflow; Registrierung als „nice to have" führen |
| Kimi ohne natives MCP-Add | kein echtes L3 | Installer-Skript + Upstream-FR; Erwartung in Doku ehrlich auf L2 setzen |
| Antigravity-CPU-Anforderung | CI nicht abbildbar | self-hosted Runner oder dokumentierte manuelle Abnahme |
| Zwei Marktplätze (Claude/Codex) driften auseinander | unterschiedliche Versionen | beides aus `registry.yaml` generieren |
| Secrets in Client-Configs | Key-Leak | nur Env-Var-Namen in Skripten; `.gitignore`-Check + CI-Sekret-Scan |
| Preview-Harnesse mit Schreibrechten | ungewollte Änderungen an echten Daten | **Read-only-Rolle** als Empfehlung (Antigravity!), QA-Workspaces |
| Fremd-Review (S3/S6) verzögert | Plan blockiert | W1/W2/W4 liefern unabhängig davon Nutzen |

### 5.6 Aufwand Stufe 2

| Welle | Inhalt | PT |
|---|---|---|
| W1 | Marketplace im Repo + 2 Workflows | 3 |
| W2 | npm-Pakete + Workflow | 4 |
| W3 | MCP-Registry + Workflow + `server.json` | 3 |
| W4 | Codex-Marketplace + Antigravity-Store | 4 |
| W5 | Hermes-Katalog, Kimi-FR, Aggregatoren | 3 |
| Querschnitt | Tests, Doku-Sync, Review, Release-Prozess | 3–6 |
| **Summe** | | **≈ 18–27 PT** |

### 5.7 Definition of Done — Stufe 2

1. Für **Claude Code, Codex, OpenCode, Antigravity** existiert ein veröffentlichter Ein-Befehl-Weg (L3), belegt durch einen Test von einem **fremden** Rechner/Account.
2. npm-Pakete sind mit **Provenance** veröffentlicht; kein Long-Lived-Token im Repo.
3. `server.json` ist in der MCP-Registry abrufbar (Suche per API) — oder die Entscheidung, darauf zu verzichten, ist dokumentiert.
4. Alle Publishes laufen **nur** über Workflows (kein manueller Publish), mit Environment-Gate und `needs: ci`.
5. Die Store-Versionen entsprechen `VERSION`; `version-drift-check` prüft das mit.
---

## 6. Sicherheit und Supply-Chain

Dieser Plan führt **keine** neue Schwachstelle ein, sondern erweitert bestehende Mechanismen. Leitplanken:

1. **Kein Long-Lived-Secret.** Publishes laufen über **OIDC** (npm Trusted Publishing, MCP-Registry `login github-oidc`) — dieselbe Linie wie die bestehende Keyless-`cosign`-Signatur in `docker-publish.yml`.
2. **SHA-gepinnte Actions.** Neue Workflows übernehmen die Repo-Konvention (jede Action auf Commit-SHA, `# vX`-Kommentar). Kein `@vN`-Rolling-Tag in Release-Pipelines.
3. **Gate vor Publish.** `needs: ci` + `environment: release` mit Reviewer, `concurrency` ohne `cancel-in-progress` — verhindert halb veröffentlichte Releases.
4. **Provenance/Attestierung** für npm-Pakete (`--provenance`) analog zur SLSA-Attestierung der Images.
5. **Key-Hygiene.** Skripte akzeptieren **nur Env-Var-Namen**, nie Werte; Beispiele in der Doku nutzen `reqlo_…`-Platzhalter; `.gitignore`-Check und Sekret-Scan im CI-Gate.
6. **Rechte-Minimierung pro Client.** Empfehlung: für Audit-/Preview-Clients (Antigravity, OpenCode-Skills ohne Tool-Restriktion) eine **read-only-Rolle** am Server binden — der Key-Scope ist die einzige wirksame Grenze, nicht die Skill-Auswahl.
7. **Agenten-Schreibrechte.** Clients mit Schreib-Tools (CCB/Baselines) nur in QA-Workspaces testen; Smoke-Tests nutzen ausschließlich einen dedizierten QA-Workspace.

---

## 7. Metriken

| Metrik | Zielwert | Erhebung |
|---|---|---|
| **Time-to-first-MCP-Call** (neuer Nutzer, Repo bekannt) | ≤ 5 min | Stichprobe im Team, dokumentiert |
| **Time-to-first-MCP-Call** (fremder Nutzer, Store) | ≤ 2 min | Store-Kommentare/Support |
| Anzahl Clients auf L2 / L3 | 6/6 (L2), ≥4/6 (L3) | Statusspalte in `docs/clients/README.md` |
| Doku-Drift-Vorfälle | 0 nach W0 | CI-Gate rot = Vorfall |
| Support-Anfragen „Client verbindet nicht" | sinkend ggü. heute | Issue-Labels |
| Store-Verfügbarkeit (Registry/Store-Eintrag erreichbar) | 100 % der Releases, die dort sein sollen | `client-smoke.yml` + Registry-API-Abfrage |

---

## 8. Entscheidungsbedarf (Decision Log)

| # | Frage | Empfehlung |
|---|---|---|
| E1 | MCP-Registry-Namespace: persönlich (`io.github.popoboxxo`) oder Organisation? | **Organisation**, falls vorhanden (Owner-Rechte nötig); sonst persönlich starten und später umziehen. |
| E2 | npm-Scope: `@reqogniloom` (neu) oder `@popoboxxo`? | **`@popoboxxo`** — ein Scope, ein Eigentümer, weniger Verwaltung; `@reqogniloom` bleibt Option. |
| E3 | Eigenes Marketplace-Repo oder Marketplace **im** Repo? | **Im Repo** (`.claude-plugin/marketplace.json`) — ein Befehl, kein zweites Artefakt zu pflegen. |
| E4 | Dürfen **Betas** in Stores? | Nein für kuratierte Verzeichnisse (S3/S6); Ja für npm (`next`) und für „latest"-Kanäle mit klarem Pre-Release-Label. |
| E5 | Antigravity in der CI? | **Self-hosted Runner** (CPU mit `pclmulqdq`) oder dokumentierte manuelle Abnahme — vor W4 entscheiden. |
| E6 | Kimi: L2 akzeptieren oder auf Upstream-Feature warten? | **L2 akzeptieren + FR stellen** — L2 deckt den realen Bedarf. |
| E7 | Aggregatoren (S8) jetzt mitnehmen? | **Später** (nach W3) — Discoverability ohne Funktionsgewinn. |

---

## 9. Anhänge

### Anhang A — Soll-Struktur jeder Client-Seite (DE/EN identisch)

```markdown
# <Client> — ReqogniLoom-Anbindung
> Getestet mit <Version> · Stand: <Datum>

## 1. Voraussetzungen            (Binary, Version, Netzwerk, Key/Rolle)
## 2. Installation (ein Befehl)  (L2/L3, copy-paste)
## 3. Konfiguration              (vollständig, generiert, mit Marker-Block)
## 4. Modell / Provider          (nur falls der Client einen eigenen braucht)
## 5. Verifikation               (Befehl + ERWARTETE Ausgabe)
## 6. Fallstricke                (Symptom -> Ursache -> Fix)
## 7. Rechte & Key-Scope         (welche Rolle nötig, read-only-Empfehlung)
## 8. Update / Deinstallation
```
**Paritäts-Regel:** Nummerierung, Überschriften und Codeblöcke sind zwischen `x.md` und `x.de.md` identisch; nur Fließtext ist übersetzt. CI prüft das (AP-1.5, Punkt 3).

### Anhang B — Verifizierte Kommandoreferenz (QA beta.18)

| Zweck | Kommando | Belegt durch |
|---|---|---|
| Claude-Plugin lokal registrieren | `claude plugin marketplace add ./dist/plugins/claude-code` | `claude plugin marketplace add --help` |
| Claude-Plugin installieren | `claude plugin install reqogniloom@<marketplace>` | Marketplace-Doku + `claude plugin --help` |
| Claude: Fallback ohne Plugin | `claude mcp add --transport http <name> <url> --header "X-API-Key: …"` | `claude mcp --help` |
| Claude: Server-Status | `claude mcp list` → `✔ Connected (SSE)` | QA-Lauf |
| Codex: MCP registrieren | `codex mcp add <NAME> --url <URL>` | `codex mcp add --help` |
| Codex: Plugin-Marktplatz | `codex plugin marketplace add` / `codex plugin add` | `codex plugin --help` |
| Codex: headless Call | `codex exec … --dangerously-bypass-approvals-and-sandbox` | QA-Erfolgslauf (12 Workspaces, 2×) |
| OpenCode: MCP | `opencode mcp add [name]` / `opencode mcp list` | `opencode mcp --help` + QA |
| OpenCode: Plugin-Install | `opencode plugin <module>` (`-g` für global) | `opencode plugin --help` |
| Kimi: Provider-Registry | `kimi provider add <api.json>` (Feld `type` Pflicht) | QA (`Skipping invalid entry …`) |
| Kimi: Config-Check | `kimi doctor` | `kimi --help` |
| Hermes: MCP-Install | `hermes mcp add` / `hermes mcp test <name>` | QA (222 Tools, 2232 ms) |
| Hermes: Katalog | `hermes mcp catalog` / `hermes mcp install <name>` | `hermes mcp --help` |
| Antigravity: Skills | `npx skills add <pkg> -a antigravity` | `INSTALL.md` |
| MCP-Registry: Publish | `mcp-publisher init/login github-oidc/publish/validate` | Registry-Doku |

### Anhang C — Troubleshooting-Matrix (erweitert)

| Symptom | Ursache | Fix |
|---|---|---|
| Client „connected", aber 0 Tools | falscher Transport | Matrix §3.3 |
| HTTP 400 `MissingSessionID` | Pflicht-Session-Header fehlt | `x-opencode-session` setzen |
| HTTP 403 `error code: 1010` | Cloudflare vs. Nicht-Browser-UA | `User-Agent` setzen |
| Codex bricht sofort ab | `wire_api="chat"` | `wire_api="responses"` |
| Codex-MCP-Call „requires approval" | Approval-Policy `never` headless | Bypass-Flag (nur kontrolliert) |
| Kimi ignoriert Registry-Eintrag | `type` fehlt | `"type":"openai"` |
| Antigravity exit 132, `pclmul` | CPU ohne `pclmulqdq` | Host-/VM-CPU ändern (nicht SW-lösbar) |
| OpenCode: Config wirkt nicht | blankes `{…}` statt `{env:…}` | Env-Syntax verwenden |
| Skill findet `DOMAIN_MODEL.md` nicht | falsche Ebene | zwei Ebenen über `skills/<name>/` ablegen |
| Client antwortet frei statt per Tool | Modell kann ohne Tool antworten | Verify verlangt Tool-Call-Nachweis im Log |

### Anhang D — Glossar

| Begriff | Bedeutung |
|---|---|
| **L0–L3** | One-Click-Reifegrade (§1.1) |
| **Harness** | Der Coding-Client (Claude Code, Codex, …) |
| **SSE / Streamable HTTP / stdio** | Die drei MCP-Transportarten |
| **Server-Entry** | `server.json` der offiziellen MCP-Registry |
| **Marketplace** | Git-Repo mit `.claude-plugin/marketplace.json`, aus dem Plugins installiert werden |
| **Trusted Publishing** | OIDC-basiertes npm-Publish ohne Token |
| **Drift** | Auseinanderlaufen von Quelle (`registry.yaml`/`VERSION`) und generiertem Artefakt |

---

## 10. Zusammenfassung der nächsten Schritte

1. **W0 starten:** AP-1.1 … AP-1.5 (Skripte, `docs/clients/`, CI-Gate) — liefert sofort L2 für alle sechs Clients und beseitigt die Widersprüche.
2. **Entscheidungen E1–E7** aus §8 beantworten (blockieren erst ab W1).
3. **W1 (Claude-Code L3)** ist der schnellste sichtbare Gewinn: eine Datei im Repo + zwei Workflows.
4. **Betas bleiben draußen** aus kuratierten Stores; npm nutzt `next`.
5. Nach jedem Schritt: Smoke-Test-Beleg im Issue/PR (kein „sollte gehen").
