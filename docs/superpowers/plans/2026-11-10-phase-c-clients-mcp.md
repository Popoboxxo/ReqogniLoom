# Phase C — Clients und MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #1703 (OpenCode 1 und 2 gegen den echten `/mcp/`-Endpunkt belegen) und #1704 (Code Mode gegen 290 Tools messen) mit reproduzierbaren Messungen schließen. Das Ergebnis ist ein Bericht, ein wiederverwendbares Probe-Skript und ein erweiterter `client-smoke`-Workflow.

**Architecture:** Ein kleines Stdlib-Python-Skript (`scripts/clients/mcp_probe.py`) spricht das MCP-Protokoll direkt gegen `/mcp/` (Handshake, SSE, `tools/list`, `tools/call`). Damit ist die Serverseite unabhängig vom Client belegt. Die Clientseite (OpenCode 1.18.x und 2.2.x) wird mit `install.sh` und `verify.sh` in einem isolierten `HOME` gegen denselben Stack geprüft. Der Workflow `client-smoke.yml` bekommt Schritte für Key-Anlage und Probe. Er bleibt `workflow_dispatch`-only.

**Tech Stack:** Python 3 (Stdlib, `pytest` wie `scripts/clients/test_*.py`), Bash, Docker Compose (`deploy/docker-compose.yml` + `testing/docker-compose.test.yml`), OpenCode `opencode-ai@1.18.35` (V1) und `@opencode/cli@2.2.5` bzw. 2.2.6 (V2), GitHub Actions.

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md`, Phase C, Entscheidung 6. Hintergrund: `docs/superpowers/specs/2026-11-01-opencode-v2-support-design.md` (D2), `docs/test-reports/opencode-v2-spike.md`, `docs/clients/opencode-v2-known-issues.md`.

## Befund (origin/main 4f8aa29f, beta.29)

- **#1704 ist zur Hälfte entschieden:** Spec D2 (2026-11-01) hat `codemode:false` festgelegt. `dist/opencode/opencode.v2.json.snippet` und `docs/clients/opencode-v2.md:69` tragen es ("mandatory"). Es fehlt die **Messung** (Sichtbarkeit der Tools, Auflösung der sechs Skills, Token-Kosten, Katalog-Latenz, V1-Verhalten mit dem Key `codemode`).
- **Tool-Zahl:** 290 Tools laut `docs/agent-templates/tool-manifest.json` (die Issues sagen 248). `tools/list` ist key-abhängig (z. B. 98 für Read-Keys, #1593/#1730). Die Prüfung darf deshalb keine feste Zahl behaupten.
- **#1703:** Der V2-Restart-Quirk steht schon im Kopf von `client-smoke.yml` und in `opencode-v2-known-issues.md`. Es fehlt der echte End-to-End-Lauf. Das Issue verlangt zusätzlich einen Ablageort für den Bericht (`docs/test-reports/` ist gitignored, `docs/test-reports/opencode-v2-spike.md` existiert aber im Repo) und die Entscheidung zu CI.
- **CI heute:** `client-smoke.yml` ist ein Entwurf (`workflow_dispatch`), startet `postgres redis backend` auf Port 8001 und prüft nur die Verbindung (`verify.sh` → `opencode mcp list`). Das Secret `QA_CLIENT_KEY` existiert noch nicht. Es gibt keinen Schritt, der einen Key anlegt oder Daten seedet.
- **Lokal:** `opencode v2.2.6` ist installiert (`/home/hermes/.local/bin/opencode`). Auf diesem Host läuft kein ReqogniLoom-Stack (Port 8000 antwortet mit etwas anderem). Der Stack muss gestartet werden. Host hat ~5,8 GiB RAM, nur ein Stack gleichzeitig, keine parallelen Volltests.
- **Offen im Code:** Der Pin im Workflow ist `@opencode/cli@2.2.5`, lokal ist 2.2.6. Ob der Pin angehoben wird, entscheidet Daniel (Task 6).

## Global Constraints

- Keine Änderungen in `.agent-meta/` (Submodul-Schutz). Funde dort werden als Issue im agent-meta-Repo gemeldet.
- Scratch nur unter `.tmp/`. Isolierter Client-`HOME` unter `.tmp/oc-home-v1` und `.tmp/oc-home-v2`, nie das echte `~/.config/opencode` anfassen.
- API-Keys und Passwörter nie in Dateien oder Commits. Nur über Umgebungsvariablen (`REQOGNILOOM_API_KEY`), im Workflow über Secrets.
- Das Probe-Skript sendet nur lesende Aufrufe (Key mit `scope=read`). `tools/call` nur mit `requirement_query`.
- Kommentare und Berichte: intern Deutsch, Skript-Docstrings Englisch.
- `client-smoke.yml` bleibt `workflow_dispatch`-only (E5 deferred). Kein Trigger wird aktiviert.
- Commits: Conventional Commits, Englisch, höchstens 72 Zeichen, Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`. Git-Mutationen nur über den `git`-Agenten.
- Volle Testläufe sequentiell. Zielgerichtet: `cd scripts/clients && python -m pytest test_mcp_probe.py -v`.

## Review Focus

- Key-abhängige Tool-Liste (#1730): Die Probe vergleicht mit einer festen Zahl und schlägt für Read-Keys fehl. Test: Task 1 prüft nur `0 < count`, `requirement_query` enthalten, und liest `_meta`/Filterhinweis, falls vorhanden.
- SSE-Stream bleibt offen: Die Probe hängt am GET. Test: Task 1 erzwingt ein Timeout (5 s) und wertet "erste Zeile oder Timeout ohne Fehler" als Ergebnis.
- Leerer Workspace: `requirement_query` liefert 0 Ergebnisse und wird als Fehler gewertet. Test: Task 1 trennt "Aufruf erfolgreich" von "Daten vorhanden".
- Falscher Key liefert 401 und die Probe meldet einen Absturz statt einer klaren Meldung. Test: Task 1, 401-Fall.
- Client schreibt in das echte Home: Test: Task 3 prüft nach dem Lauf, dass `~/.config/opencode` unverändert ist (Zeitstempel/Hash vorher und nachher).

---

### Task 1: `mcp_probe.py` mit Stub-Test

**Files:**
- Create: `scripts/clients/mcp_probe.py`
- Test: `scripts/clients/test_mcp_probe.py`

**Interfaces:**
- Consumes: nichts aus früheren Tasks.
- Produces:
  - `probe(url: str, api_key: str, *, tool: str = "requirement_query", sse_timeout: float = 5.0) -> ProbeResult`
  - `@dataclass ProbeResult: initialize_ok: bool; initialized_ok: bool; sse_status: int | None; tool_count: int; has_tool: bool; call_ok: bool; call_result_count: int | None; latency_ms: dict[str, float]; errors: list[str]`
  - CLI: `python scripts/clients/mcp_probe.py --url http://localhost:8001 --key-env REQOGNILOOM_API_KEY [--json]`, Exit 0 bei `initialize_ok and tool_count > 0 and has_tool and call_ok`, sonst 1.

- [ ] **Step 1: Failing Tests mit Stdlib-Stub-Server**

```python
# test_mcp_probe.py — Stub: http.server, POST /mcp/ (JSON-RPC), GET /mcp/ (SSE)
def test_probe_ok_against_stub(stub_server):
    r = probe(stub_server.url, "k")
    assert r.initialize_ok and r.initialized_ok and r.call_ok
    assert r.tool_count == 3 and r.has_tool

def test_probe_reports_401_without_crash(stub_server_401):
    r = probe(stub_server_401.url, "bad")
    assert not r.initialize_ok and any("401" in e for e in r.errors)

def test_probe_sse_timeout_is_not_an_error(stub_server_sse_hangs):
    r = probe(stub_server_sse_hangs.url, "k", sse_timeout=0.5)
    assert r.sse_status == 200 and r.errors == []

def test_probe_empty_data_is_separate_from_call_failure(stub_server_empty):
    r = probe(stub_server_empty.url, "k")
    assert r.call_ok and r.call_result_count == 0
```
Run: `cd scripts/clients && python -m pytest test_mcp_probe.py -v` — Expected: FAIL, `mcp_probe` fehlt.

- [ ] **Step 2: `mcp_probe.py` implementieren**

`urllib.request`/`http.client`, Header `X-API-Key`, `Content-Type: application/json`, `Accept: application/json, text/event-stream`. Ablauf: `initialize` (Protokollversion aus der Antwort übernehmen), `notifications/initialized`, GET `/mcp/` mit `sse_timeout`, `tools/list` (bei `nextCursor` weiter blättern), `tools/call` mit `name=tool`, `arguments` aus `--workspace-id` falls gesetzt. Zeitmessung je Schritt in `latency_ms`. Jede Ausnahme wird zu einem Eintrag in `errors`, nie zu einem Absturz.

- [ ] **Step 3: Tests grün**

Run: `cd scripts/clients && python -m pytest test_mcp_probe.py -v` — Expected: PASS.

- [ ] **Step 4: Commit** (über `git`-Agent): `test(clients): add a stdlib MCP probe for /mcp/`

---

### Task 2: Echten Stack starten und Read-only-Key anlegen

**Files:**
- Create: `.tmp/phase-c/env` (Scratch, gitignored, nicht committen)
- Create: `.tmp/phase-c/bootstrap.sh` (Scratch)

**Interfaces:**
- Consumes: `probe` aus Task 1.
- Produces: laufender Stack auf `http://localhost:8001`, Umgebungsvariablen `REQOGNILOOM_MCP_URL=http://localhost:8001` und `REQOGNILOOM_API_KEY=<read-key>` nur in der aktuellen Shell.

- [ ] **Step 1: Speicher prüfen**

Run: `free -g | head -2`
Expected: mindestens 3 GiB `available`. Sonst keine Volltests parallel starten, andere Container stoppen (nur nach Rückfrage bei Daniel).

- [ ] **Step 2: Stack starten**

```bash
cp .env.example .tmp/phase-c/env && sed -i 's/^SYSTEM_ADMIN_PASSWORD=.*/SYSTEM_ADMIN_PASSWORD=<zufälliges Passwort, nur Scratch>/' .tmp/phase-c/env
cp .tmp/phase-c/env .env   # .env ist gitignored; Vorhandensein einer echten .env vorher prüfen, nie überschreiben
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml up -d postgres redis backend
for i in $(seq 1 60); do curl -fsS http://localhost:8001/health/ && break; sleep 2; done
```
Vor `cp`: `test -e .env && echo vorhanden`. Wenn eine echte `.env` existiert, Variante mit `--env-file .tmp/phase-c/env` verwenden, nicht überschreiben.
Expected: `/health/` antwortet 200.

- [ ] **Step 3: Admin-Token und Read-only-Key**

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login/ -H 'Content-Type: application/json' -d '{"username":"admin","password":"<Scratch-Passwort>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -X POST http://localhost:8001/api/v1/api-keys/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"phase-c-probe","scope":"read_only"}'
```
Expected: 201, der Klartext-Key steht im Feld `plaintext` und erscheint nur einmal (`ApiKeyCreateResponseSerializer`). Der Login setzt Cookies (`reqogniloom_access`, `reqogniloom_refresh`); das Feld `token` im Body ist deprecated (#696), für diese Scratch-Bootstrap-Aufgabe aber vorhanden. Fehlt es in einer künftigen Version, Cookie plus CSRF-Header nutzen. Scope-Name: `read_only` (kanonisch), `read` ist nur ein Legacy-Alias.

- [ ] **Step 4: Daten seeden**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml exec backend python manage.py seed_demo`
Expected: Workspace mit Requirements. Seed braucht `SEED_DEMO_ALLOW_DEFAULT_PASSWORD` oder das gesetzte Admin-Passwort (siehe `.env.example:791`).

- [ ] **Step 5: Probe laufen lassen**

Run: `python scripts/clients/mcp_probe.py --url http://localhost:8001 --key-env REQOGNILOOM_API_KEY --json > .tmp/phase-c/probe.json`
Expected: Exit 0, `tool_count > 0`, `has_tool: true`, `call_ok: true`, `call_result_count > 0`. Der Key `read` liefert weniger als 290 Tools, das ist erwartet und wird im Bericht mit Zahl festgehalten.

---

### Task 3: OpenCode 1 und 2 gegen den echten Endpunkt (#1703)

**Files:**
- Read: `scripts/clients/install.sh`, `scripts/clients/verify.sh`, `dist/opencode/opencode.json.snippet`, `dist/opencode/opencode.v2.json.snippet`
- Create: `docs/clients/opencode-endpoint-verification.md`

**Interfaces:**
- Consumes: Stack und Key aus Task 2.
- Produces: Messtabelle V1/V2 (Verbindung, Tool-Zahl, Fehlermeldungen), V2-Restart-Quirk bestätigt, Ergebnis "CI-fähig: ja/nein".

- [ ] **Step 1: V1 isoliert installieren und prüfen**

```bash
mkdir -p .tmp/oc-home-v1 && npm install --prefix .tmp/oc-v1 opencode-ai@1.18.35
HOME=$PWD/.tmp/oc-home-v1 PATH=$PWD/.tmp/oc-v1/node_modules/.bin:$PATH \
  bash scripts/clients/install.sh --client opencode --url http://localhost:8001 --key-env REQOGNILOOM_API_KEY --yes
HOME=$PWD/.tmp/oc-home-v1 PATH=$PWD/.tmp/oc-v1/node_modules/.bin:$PATH bash scripts/clients/verify.sh --client opencode
```
Expected: `ok: found 'connected'` oder der in `verify.sh:55-75` erwartete Marker.

- [ ] **Step 2: V2 isoliert prüfen, inklusive Restart-Quirk**

Mit installiertem `opencode v2.2.6` (und separat mit `@opencode/cli@2.2.5`) und `HOME=$PWD/.tmp/oc-home-v2`. `install.sh --client opencode-v2`, dann `opencode mcp list`. Bestätigen oder widerlegen, dass nach dem Schreiben der Config "No MCP servers configured" erscheint, bis der Hintergrunddienst neu startet (`--standalone` oder Dienst neustarten). Ergebnis mit Befehl und Ausgabe festhalten.

- [ ] **Step 3: Tool-Sichtbarkeit je Client**

`opencode debug --help` lesen. Das Unterkommando verwenden, das MCP-Tools auflistet. Fehlt eines, ist der Tool-Aufruf über den Client ohne LLM-Provider nicht möglich: dann wird `tools/list` und `tools/call` durch Task 2 Step 5 auf Protokollebene belegt, und der Bericht benennt diese Grenze ausdrücklich.

- [ ] **Step 4: Echtes `HOME` unverändert**

Vorher und nachher `find ~/.config/opencode -type f -exec sha256sum {} + | sha256sum` vergleichen.
Expected: identische Summen.

- [ ] **Step 5: Bericht schreiben**

`docs/clients/opencode-endpoint-verification.md`, Deutsch. Abschnitte: Versionen und Datum, Stack-Stand (Commit), Ergebnistabelle V1 und V2, Restart-Quirk, Tool-Zahlen je Key-Scope, Grenzen der Messung, Entscheidung CI (Step 3 von Task 6). Ablageort: `docs/clients/` (Entscheidung Daniel, 2026-11-10), nicht das gitignorierte `docs/test-reports/`.

- [ ] **Step 6: Commit** (über `git`-Agent): `docs(clients): add OpenCode endpoint verification report`

---

### Task 4: Code Mode messen (#1704)

**Files:**
- Modify: `docs/clients/opencode-endpoint-verification.md` (Abschnitt "Code Mode")
- Read: `dist/opencode/opencode.v2.json.snippet`, die sechs Skills unter `dist/opencode/` (Pfad mit `find dist/opencode -name SKILL.md` bestimmen)

**Interfaces:**
- Consumes: Stack und Key (Task 2), V2-Client (Task 3).
- Produces: Vergleichstabelle `codemode: true` gegen `codemode: false` mit Messwerten.

- [ ] **Step 1: Skill-Namensauflösung prüfen (ohne Client)**

```bash
for f in $(find dist/opencode -name SKILL.md); do grep -oE '\b[a-z_]+_[a-z_]+\b' "$f" | sort -u; done > .tmp/phase-c/skill-tool-names.txt
python3 - <<'EOF'
import json
manifest = {t["name"] for t in json.load(open("docs/agent-templates/tool-manifest.json"))["tools"]}
names = {l.strip() for l in open(".tmp/phase-c/skill-tool-names.txt")}
print(sorted(n for n in names if n in manifest))
print(sorted(n for n in names if n not in manifest and "_" in n))
EOF
```
Expected: die von den Skills genannten Tools stehen im Manifest. Der Skript-Aufbau der Manifest-Struktur (`["tools"]`) vorher mit `python3 -c "import json;d=json.load(open('docs/agent-templates/tool-manifest.json'));print(list(d)[:3])"` prüfen.

- [ ] **Step 2: Sichtbarkeit je Modus**

Zwei V2-Configs in isolierten Homes: `codemode: false` (Auslieferungszustand) und Default/`true`. Je Modus mit dem Debug-Befehl aus Task 3 Step 3 die Toolnamen erfassen. Erwartung laut Spike: ohne `codemode:false` heißen sie `reqogniloom_<tool>` und kommen über einen Katalog. Messen: Namensschema, ob `requirement_query` direkt auffindbar ist.

- [ ] **Step 3: Größe und Latenz**

`tools/list` als Rohbytes (`wc -c`) und Antwortzeit aus `probe.json` (`latency_ms.tools_list`). Token-Kosten nur als Näherung (Bytes / 4), im Bericht als Näherung markiert. Der Katalog-Timeout (`timeout.catalog` Default 30 s) wird gegen die gemessene Latenz gehalten.

- [ ] **Step 4: V1 mit dem Key `codemode`**

Eine V1-Config mit `"codemode": false` im `mcp.reqogniloom`-Block anlegen, `opencode mcp list` mit V1 laufen lassen. Ergebnis: ignoriert oder abgelehnt. Das entscheidet, ob eine einzige Config für beide Versionen tragbar ist (Spec: eine Konfiguration in V1-Form trägt beide).

- [ ] **Step 5: Empfehlung festhalten**

Abschnitt "Code Mode" im Bericht: Tabelle, Empfehlung (beibehalten oder ändern) mit Beleg. Bei Änderung: Folge-Issue, nicht in diesem Plan.

- [ ] **Step 6: Commit** (über `git`-Agent): `docs(clients): measure OpenCode 2 Code Mode against the tool set`

---

### Task 5: `client-smoke.yml` um Key-Anlage und Probe erweitern

**Files:**
- Modify: `.github/workflows/client-smoke.yml`
- Modify: `scripts/clients/verify.sh` (optional, nur wenn Task 3 zeigt, dass der Marker nicht reicht)

**Interfaces:**
- Consumes: `mcp_probe.py` (Task 1), API-Muster aus Task 2 Step 3.
- Produces: Workflow, der ohne Secret `QA_CLIENT_KEY` lauffähig ist.

- [ ] **Step 1: Schritt "Bootstrap admin and read-only key" einfügen**

Nach "Wait for the backend health endpoint", vor "Install client": setzt `SYSTEM_ADMIN_PASSWORD` aus einem im Job generierten Zufallswert (`openssl rand -hex 16`, mit `::add-mask::`), loggt sich ein, legt per `POST /api/v1/api-keys/` einen Key mit `scope=read` an und schreibt ihn über `$GITHUB_ENV` als `REQOGNILOOM_API_KEY`. Das Passwort muss vor dem `docker compose up` in die `.env` (Schritt "Materialise compose env file" erweitern).

- [ ] **Step 2: Schritt "Probe the MCP endpoint" einfügen**

`python scripts/clients/mcp_probe.py --url http://localhost:8001 --key-env REQOGNILOOM_API_KEY --json`. Läuft pro Matrix-Leg, ist für `opencode-v2` weiter `continue-on-error`.

- [ ] **Step 3: Secrets-Verweis ersetzen**

`${{ secrets.QA_CLIENT_KEY }}` in den Schritten "Install client" und "Verify" durch die Job-Variable ersetzen. Der Kommentar "May not exist yet" entfällt.

- [ ] **Step 4: Statische Prüfung**

Run: `python3 -c "import yaml,sys;yaml.safe_load(open('.github/workflows/client-smoke.yml'))"` und, falls vorhanden, `actionlint .github/workflows/client-smoke.yml`
Expected: kein Fehler. `workflow_dispatch` bleibt der einzige Trigger (`grep -n "^on:" -A3`).

- [ ] **Step 5: Commit** (über `git`-Agent): `ci(clients): create a read key and probe /mcp/ in client-smoke`

---

### Task 6: Pin-Entscheidung, Doku und Schließen

**Files:**
- Modify: `docs/clients/opencode-v2-known-issues.md` (Messergebnisse, Restart-Quirk bestätigt)
- Modify: ggf. `.github/workflows/client-smoke.yml` (Pin `@opencode/cli@2.2.5` → `2.2.6`)

**Interfaces:** Consumes: Berichte aus Tasks 3 und 4.

- [ ] **Step 1: Pin-Entscheidung**

Lokal ist V2 2.2.6. Wenn die Messung auf 2.2.6 und 2.2.5 identisch ist, Pin anheben und das im Bericht vermerken. Weichen sie ab, Pin lassen und die Abweichung dokumentieren. Daniel entscheidet bei Abweichung.

- [ ] **Step 2: Issues schließen (nach Freigabe durch Daniel)**

```bash
gh issue close 1703 --reason completed --comment "Real-Endpoint-Test für OpenCode 1.18.x und 2.2.x gegen den Stack (beta.29). Bericht: docs/clients/opencode-endpoint-verification.md. Probe: scripts/clients/mcp_probe.py. V2-Restart-Quirk bestätigt und in docs/clients/opencode-v2-known-issues.md dokumentiert. CI: client-smoke legt jetzt einen Read-Key an und ruft die Probe auf (weiterhin nur workflow_dispatch)."
gh issue close 1704 --reason completed --comment "Gemessen: Code Mode an gegen codemode:false (Tools, Skills, Größe, Latenz), V1-Verhalten mit dem Key codemode. Ergebnis und Empfehlung: docs/clients/opencode-endpoint-verification.md, Abschnitt Code Mode."
```

- [ ] **Step 3: Stack abbauen**

Run: `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml down -v` und `rm -rf .tmp/phase-c .tmp/oc-home-v1 .tmp/oc-home-v2 .tmp/oc-v1`
Expected: keine Container, keine Scratch-Reste. `.env` nur löschen, wenn sie in Task 2 von dieser Aufgabe angelegt wurde.

- [ ] **Step 4: Endstand prüfen**

Run: `gh issue view 1703 --json state --jq .state; gh issue view 1704 --json state --jq .state`
Expected: zweimal `CLOSED`.

---

## Self-Review

- **Abdeckung:** #1703 (Handshake, `initialized`, SSE, `tools/list`, `requirement_query`, V2-Quirk, Ablageort, CI-Entscheidung) durch Tasks 1 bis 3 und 5. #1704 (Messung beider Modi, V1-Verhalten, Skill-Auflösung, Empfehlung) durch Task 4.
- **Abweichung von den Issues:** Beide nennen 248 Tools und 49 Requirements. Auf beta.29 sind es 290 Tools, key-abhängig. Der Plan verwendet relative Prüfungen und nennt die Zahlen im Bericht.
- **Bekannte Grenze:** Ein Tool-Aufruf über den Client selbst braucht einen LLM-Provider. Ohne ihn belegt die Probe den Aufruf auf Protokollebene. Task 3 Step 3 hält das im Bericht fest.
- **Typkonsistenz:** `ProbeResult`-Felder aus Task 1 werden in Tasks 2 bis 4 gelesen (`tool_count`, `latency_ms`, `call_result_count`).
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Login-Token und Key-Felder sind im Review am Code bestätigt (`token` im Login-Body, deprecated #696; `plaintext`, `scope=read_only`). Der Docker-Stack wurde nicht gestartet.
