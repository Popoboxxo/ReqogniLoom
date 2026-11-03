# OpenCode 2 Native Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ReqogniLoom unterstützt OpenCode 2 nativ und OpenCode 1 weiterhin, mit einer gemeinsamen, getesteten Konfiguration. Was nicht belegt ist, steht als offenes Issue (#1702–#1706), nicht als Annahme.

**Architecture:** Beide Versionen verbinden sich per Streamable HTTP auf `/mcp/`. Der Spike vom 2026-11-03 zeigt: V2 hat keinen SSE-Fallback (POST auf `/mcp/sse/` → 404), V1 spricht Streamable HTTP und fällt nur bei Misserfolg auf SSE zurück, und V2 liest die V1-Form `mcp.reqogniloom` und normalisiert sie selbst. Eine einzige Konfiguration (V1-Form, URL `…/mcp/`) genügt daher; es gibt keinen zweiten Registry-Eintrag, kein Merge-Tool und keinen Versions-Autodetect.

**Tech Stack:** Bash (`install.sh`, `verify.sh`), Python 3 + pytest + PyYAML (Builder, Renderer, Tests), YAML-Registry, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-01-opencode-v2-support-design.md` (Abschnitt „Stand 2026-11-03" ersetzt dort §3 und §4)

## Messstand des Spikes (2026-11-03)

Gemessen mit `@opencode/cli@2.2.5` (npm, Binaries `opencode` und `opencode2`) und OpenCode 1.18.35 gegen einen **Mock**-MCP-Server (stdlib-Python, Streamable HTTP auf `POST /mcp/`, Header `X-API-Key`). `opencode mcp list`:

| Config | V1 1.18.35 | V2 2.2.5 |
|---|---|---|
| V1-Form, URL `/mcp/` | verbunden | verbunden |
| V1-Form, URL `/mcp/sse/` (heutiges Snippet) | verbunden über SSE-Fallback | **fehlgeschlagen** (POST → 404) |
| V2-Form `mcp.servers.…`, URL `/mcp/` | nicht geprüft | verbunden, mit und ohne `oauth:false` |
| V2-Form, URL `/mcp/sse/` | nicht geprüft | **fehlgeschlagen** |

**Nicht belegt** (je ein Issue): echter ReqogniLoom-Endpunkt (#1703), Code Mode und Tool-Aufrufe über das LLM (#1704), CI-Abdeckung und Stage-2-Paket (#1705), Warnung zu `subagent_depth` in der Repo-`opencode.json` (#1706). Weiteres V2-Verhalten: Nach einer Config-Änderung muss der V2-Hintergrunddienst neu starten, sonst zeigt `mcp list` „No MCP servers configured".

## Global Constraints

- Branch `fix/opencode-two-streamable-http` (oder `feat/…`) **von `origin/main`**; lokales `main` nicht auschecken/resetten. Git-Mutationen nur über den `git`-Agenten.
- Kein Plugin-Code. Der `opencode_go`-LLM-Provider bleibt unverändert.
- Nie einen literalen `reqlo_`-Key in Config, Snippet oder argv; nur `{env:NAME}`-Platzhalter. `--key-env` ist ein Env-Var-**Name**.
- Generierte Dateien (`docs/clients/**`) nie von Hand editieren: `python scripts/clients/render.py` ausführen und committen.
- `*_de` und `*_en` im Registry-Eintrag paritätisch halten.
- Die lokale OpenCode-Installation und `~/.config/opencode` werden nicht angefasst; Tests mit gesetztem `HOME`/`XDG_CONFIG_HOME` auf ein Scratch-Verzeichnis.
- Tests sequenziell (Host-RAM ~5,8 GiB). Commits: Conventional Commits, Englisch, ≤72 Zeichen.

## Review Focus

- Installer-Aufruf mit `--url` mit und ohne Schrägstrich am Ende → URL ist immer genau `<base>/mcp/` (nie `//mcp/`, nie `/mcp/sse/`).
- `--key-env` mit Leerzeichen, `$`, `{`, `}` → Installer lehnt ab, schreibt nichts.
- Snippet und Registry enthalten nirgends `sse` als Transport oder `/mcp/sse/` für OpenCode; andere Clients (Claude Code, Antigravity) bleiben unverändert auf SSE.
- V1-Nutzer mit bestehender SSE-Config: Update-Hinweis in der Doku („Eintrag ersetzen"), der Installer überschreibt keinen vorhandenen Eintrag ohne `--refresh`.

---

### Task 1: Config auf Streamable HTTP umstellen (#1702)

**Files:**
- Modify: `clients/registry.yaml` (Eintrag `opencode`, ca. Z. 271–340)
- Modify: `dist/opencode/build_opencode_package.py` (URL im Snippet)
- Modify: `dist/opencode/test_build_opencode_package.py` (URL-Assertion)
- Modify: `scripts/clients/install.sh` (`install_opencode`, ca. Z. 209–225)
- Create: `scripts/clients/test_install_opencode.py`
- Generate: `dist/opencode/opencode.json.snippet`, `docs/clients/opencode.md`, `docs/clients/opencode.de.md`, `docs/clients/README.md`, `docs/clients/README.de.md`

**Interfaces:**
- Produces: Snippet `{"mcp": {"reqogniloom": {"type": "remote", "url": "{env:REQOGNILOOM_MCP_URL}/mcp/", "headers": {"X-API-Key": "{env:REQOGNILOOM_API_KEY}"}}}}`; Installer-Aufruf `opencode mcp add reqogniloom --url "<base>/mcp/" --header "X-API-Key={env:<KEY_ENV>}"`.

- [ ] **Step 1: Failing Tests schreiben.**
  - In `test_build_opencode_package.py`: `server["url"] == "{env:REQOGNILOOM_MCP_URL}/mcp/"` und `"sse" not in json.dumps(snippet)`.
  - In `scripts/clients/test_install_opencode.py` (neu): Hilfsfunktion `dry_run(url, key_env="REQOGNILOOM_API_KEY")` startet `bash scripts/clients/install.sh --client opencode --url <url> --key-env <key_env> --dry-run --yes` mit `HOME` in `tmp_path` und gibt stdout zurück. Tests: `test_url_gets_mcp_path_exactly_once` (für `http://h:8001` und `http://h:8001/` enthält die Ausgabe `--url http://h:8001/mcp/` und nicht `/mcp/sse/` und nicht `//mcp/`), `test_key_header_is_env_placeholder` (Ausgabe enthält `X-API-Key={env:MY_KEY}` für `--key-env MY_KEY`, kein `reqlo_`), `test_bad_key_env_is_rejected` (`'A B'`, `'A$B'`, `'{x}'` → Exit ≠ 0).
- [ ] **Step 2: Tests laufen lassen.** `pytest dist/opencode/test_build_opencode_package.py scripts/clients/test_install_opencode.py -v` — Erwartet: FAIL.
- [ ] **Step 3: Builder anpassen.** URL im Snippet auf `{env:REQOGNILOOM_MCP_URL}/mcp/` ändern.
- [ ] **Step 4: Installer anpassen.** In `install_opencode` `"$URL/mcp/sse/"` durch `"$URL/mcp/"` ersetzen; vor dem Aufruf den Env-Namen gegen `^[A-Za-z_][A-Za-z0-9_]*$` prüfen (sonst `exit 2` mit Meldung).
- [ ] **Step 5: Registry anpassen.** Im Eintrag `opencode`: `transport: streamable_http`, `url_path: /mcp/`, URLs in `install_*` und `fallback_*` auf `/mcp/`, `tested_version: "1.18.35 / 2.2.5"`, Hinweis in `pitfalls_*` („OpenCode 2 hat keinen SSE-Fallback; Update von älterer Config: Eintrag `reqogniloom` auf `…/mcp/` ersetzen"; „nach Config-Änderung V2-Hintergrunddienst neu starten") und in `update_*` (SSE-Hinweis streichen).
- [ ] **Step 6: Snippet und Doku erzeugen.** `python dist/opencode/build_opencode_package.py` und `python scripts/clients/render.py`.
- [ ] **Step 7: Tests laufen lassen.** `pytest scripts/clients dist/opencode dist/test_mcp_convention_parity.py -v` und `python scripts/clients/render.py --check` — Erwartet: PASS bzw. Exit 0.
- [ ] **Step 8: Commit.** `git add clients dist scripts docs/clients` · `git commit -m "fix(clients): connect OpenCode via Streamable HTTP /mcp/ (#1702)"`

---

### Task 2: Echter Endpunkt und Tool-Call für V1 und V2 (#1703)

Braucht eine laufende Instanz und einen `reqlo_`-Key mit Read-only-Rolle. Kein Repo-Code außer dem Bericht.

**Files:**
- Create: Testbericht (Ablageort laut Entscheidung in #1703; `docs/test-reports/` ist gitignored, Alternative `docs/clients/`)

- [ ] **Step 1: Instanz bereitstellen.** `make up` (Platte prüfen: `df -h /` ≥ 10 GB frei; Docker-Daten notfalls nach `/var/tmp`). Key als `REQOGNILOOM_API_KEY`, `REQOGNILOOM_MCP_URL=http://localhost:8001` exportieren.
- [ ] **Step 2: V2 isoliert installieren.** `npm install --prefix <scratch>/npm @opencode/cli@2.2.5`; `HOME`/`XDG_*` auf Scratch setzen.
- [ ] **Step 3: Installer pro Version laufen lassen.** `bash scripts/clients/install.sh --client opencode --url "$REQOGNILOOM_MCP_URL" --key-env REQOGNILOOM_API_KEY --yes` je einmal mit V1- und V2-Binary im `PATH`; danach `bash scripts/clients/verify.sh --client opencode`. V2 vorher: Hintergrunddienst beenden bzw. `mcp list --standalone`.
- [ ] **Step 4: Handshake prüfen.** Serverseitig `initialize`, Notification, `GET /mcp/` (SSE-Stream), `tools/list` mit allen Tools (282 laut `CLAUDE.md`, Wert aus `docs/agent-templates/tool-manifest.json` prüfen) und ein echter Aufruf `requirement_query` je Version (Erwartung laut Registry: 49 Requirements in der QA-Instanz).
- [ ] **Step 5: Bericht schreiben** mit Tabelle Version × Schritt, genauen Versionen und Abweichungen; bei Abweichung Issue anlegen statt Plan anpassen.

---

### Task 3: Code Mode in OpenCode 2 klären (#1704)

**Files:**
- Modify (je nach Ergebnis): `dist/opencode/build_opencode_package.py`, `clients/registry.yaml`, `dist/opencode/skills/*/SKILL.md` (generiert aus `dist/agent-skills/`; Quelle ändern, nicht die Kopie)

- [ ] **Step 1: Messen.** Mit der Instanz aus Task 2 in V2 `codemode` an (Default) und aus (`"codemode": false`, V2-Form `mcp.servers.reqogniloom`) vergleichen: wie sieht das Modell die Tools (Namen `reqogniloom_<tool>`), Katalog-Latenz gegen `timeout.catalog` (Default 30 s), Token-Kosten, und ob die sechs Skills ihre Tools finden.
- [ ] **Step 2: V1-Verträglichkeit prüfen.** Nimmt V1 den Schlüssel `codemode` an oder lehnt es die Config ab? (Nur relevant, wenn die gemeinsame V1-Form ihn bekommen soll; sonst V2-Form im Snippet erwägen.)
- [ ] **Step 3: Entscheidung dokumentieren** im Issue #1704 (Default behalten + Skills anpassen, oder `codemode:false` ausliefern) und die Umsetzung als eigenen Commit mit Test liefern (Snippet-Assertion in `test_build_opencode_package.py`).

---

### Task 4: CI, Registry und Stage-2-Paket für V2 (#1705)

**Files:**
- Modify: `.github/workflows/client-smoke.yml` (Matrix, Z. ~40–46), `.github/workflows/release-client-artifacts.yml` (Z. ~101), `.github/workflows/publish-npm.yml` (nur prüfen)
- Modify: `clients/registry.yaml` und generierte Doku

- [ ] **Step 1: Smoke-Matrix.** Zweites OpenCode-Glied `opencode-2` ergänzen (Node 22, `npm install -g @opencode/cli@2.2.5`, SHA-gepinnte Actions wie im Rest der Datei) und im Job `continue-on-error` nur dann setzen, wenn Task 2 Instabilität zeigt; Grund im Kommentar.
- [ ] **Step 2: `verify.sh` für V2.** Vor `mcp list` bei V2 `--standalone` nutzen oder den Hintergrunddienst neu starten (Erkennung über `opencode --version`, Major 2).
- [ ] **Step 3: Stage-2 prüfen.** Passt `opencode plugin <module>` (Registry `update_*`, `@popoboxxo/reqogniloom-opencode`) zu V2 (V1-Plugins laufen nicht, wir liefern keinen Plugin-Code)? Ergebnis in #1705 und Doku festhalten.
- [ ] **Step 4: Tarball** in `release-client-artifacts.yml` bleibt bei einem Snippet; prüfen, dass `opencode.json.snippet` die neue URL enthält.
- [ ] **Step 5: Tests und Commit.** `pytest scripts/clients -v`, YAML laden (`python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/*.yml`) · `git commit -m "ci(clients): cover OpenCode 2 in client smoke (#1705)"`

---

### Task 5: `subagent_depth` in der Repo-`opencode.json` (#1706)

- [ ] **Step 1: Herkunft klären.** `git log --follow opencode.json`; Vergleich mit `.agent-meta/opencode.json` (Submodul, nicht editieren).
- [ ] **Step 2: V2-Normalisierung prüfen.** `opencode debug config` (V2) im Repo laufen lassen; alle „configuration normalization diagnostic"-Zeilen sammeln (z. B. `permissions`-Form).
- [ ] **Step 3: Ergebnis festhalten.** Wenn der Fehler aus agent-meta kommt: Issue im agent-meta-Repo anlegen und #1706 verlinken; sonst Korrektur in `opencode.json` mit Commit `chore(opencode): drop settings OpenCode 2 does not support`.

---

## Self-Review

- **Abdeckung:** F1 (SSE) → Task 1; F2 (OAuth) gemessen, kein Handlungsbedarf (Header-Auth läuft ohne `oauth:false`); F4 (Code Mode) → Task 3; F7/F8 (Installer, Binary-Name) → Task 1/4 (`opencode` bleibt Befehl, `opencode2` ist Alias); F9 (Beta) entfällt, `@opencode/cli` steht bei `latest` 2.2.5; Skills (F6) unverändert; Spike-Lücken → Tasks 2–5, je ein Issue.
- **Verworfen gegenüber dem ersten Entwurf:** zweiter Registry-Eintrag `opencode-v2`, V2-Snippet, `merge_config.py`, Versions-Autodetect im Installer. Der Spike zeigt, dass sie nicht nötig sind.
- **Typkonsistenz:** Snippet-URL `{env:REQOGNILOOM_MCP_URL}/mcp/` in Task 1 (Builder, Registry, Doku) und in Task 4 (Tarball-Prüfung) identisch; Env-Namensregex nur in Task 1.
- **Offene Annahmen:** Alles bis Task 2 beruht auf dem Mock; Task 2 ist das Gate für „nativ unterstützt".
