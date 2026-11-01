# OpenCode V2 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ReqogniLoom verbindet sich mit OpenCode V1 (unverändert) und OpenCode V2 (Beta) über je einen eigenen Client-Eintrag, Snippet, Installer-Pfad und Doku-Seite.

**Architecture:** V2 bekommt einen eigenen Registry-Eintrag `opencode-v2`, ein eigenes Snippet `opencode.v2.json.snippet` (Form `mcp.servers.reqogniloom`, Streamable HTTP `/mcp/`, `oauth:false`, `codemode:false`) und einen Installer-Pfad, der die Config per JSON-Merge schreibt. `install.sh --client opencode` erkennt die Major-Version und wählt V1 oder V2. Der V1-Pfad bleibt unangetastet.

**Tech Stack:** Bash (`install.sh`, `verify.sh`), Python 3 + pytest + PyYAML (Builder, Renderer, Tests), YAML-Registry, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-01-opencode-v2-support-design.md`

## Global Constraints

- Branch `feat/opencode-v2-support`, **von `origin/main`** abzweigen (lokales `main` ist divergiert, nie auschecken/resetten).
- Git-Mutationen (Branch, Commit, Push, PR) nur über den `git`-Agenten, nie als Self-Declare im Hook.
- Kein Plugin-Code, keine Änderung an `opencode_go` (LLM-Provider) und keine Änderung am V1-Snippet oder V1-Installerpfad.
- Nie einen literalen `reqlo_`-Key in Config, Snippet oder argv; nur `{env:NAME}`-Platzhalter. `--key-env` ist ein Env-Var-**Name**.
- Generierte Dateien (`docs/clients/**`) nie von Hand editieren: `python scripts/clients/render.py` ausführen und das Ergebnis committen.
- Die lokale V1-Installation (`~/.config/opencode`) wird in keinem Task angefasst; alle Läufe mit gesetztem `HOME`/`XDG_CONFIG_HOME` auf ein Scratch-Verzeichnis.
- Commits: Conventional Commits, Englisch, max. 72 Zeichen, Imperativ.
- Doku-Sprachen: `*_de` und `*_en` im Registry-Eintrag immer paritätisch (gleiche Anzahl Überschriften und Code-Blöcke).
- Tests laufen sequenziell (Host hat ~5,8 GiB RAM).

## Review Focus

- Bestehende `opencode.json` hat **Kommentare (JSONC)** oder ist ungültig → Merge bricht mit Exit ≠ 0 ab und schreibt nichts (Backup bleibt unberührt).
- Bestehende `opencode.json` enthält **andere MCP-Server** und V1-Einträge (`mcp.<name>`) → bleiben byte-gleich erhalten.
- `opencode.json` existiert nicht → wird angelegt, Verzeichnis inklusive.
- Zweiter Lauf des Installers → identisches Ergebnis, kein doppelter Eintrag, keine Verschachtelung.
- `--key-env` mit Leerzeichen, `$`, `{` oder `}` → Installer lehnt ab (kein Config-Injection-Pfad).
- `opencode --version` fehlt oder liefert Unparsebares → Erkennung fällt auf V1 zurück, V1-Pfad läuft wie bisher.

---

### Task 0: Spike — V2 in Isolation gegen eine echte Instanz

Gate für alle weiteren Tasks. Kein Repo-Code. Ergebnis ist ein Bericht; weichen Befunde von den Annahmen in `Architecture` ab, wird dieser Plan **vor Task 1** angepasst.

**Files:**
- Create: `docs/test-reports/opencode-v2-spike.md`

**Interfaces:**
- Produces: Antworten auf F1 (Streamable HTTP auf `/mcp/` mit V2), F2 (`oauth:false` verhindert OAuth-Flow), F4 (Tool-Namen mit `codemode:false`), F7 (kann `mcp add` `oauth:false` setzen?), F8 (Binary-Name `opencode` vs `opencode2`), V1-Frage (spricht V1 `1.18.x` Streamable HTTP auf `/mcp/`?).

- [ ] **Step 1: Scratch-Umgebung anlegen.** `export SCRATCH=$(mktemp -d)`, dann `export HOME=$SCRATCH/home XDG_CONFIG_HOME=$SCRATCH/home/.config XDG_DATA_HOME=$SCRATCH/home/.local/share` und `mkdir -p "$HOME"`. Alle folgenden Befehle in derselben Shell.
- [ ] **Step 2: V2 installieren, ohne das System-V1 zu ersetzen.** Installationsweg laut `https://opencode.ai/v2/docs` wählen und auf einen Prefix unter `$SCRATCH` lenken. Lässt sich der Installer nicht isolieren (die Doku sagt, er ersetze das V1-Binary), **abbrechen und den Nutzer fragen**. Erwartet: `"$SCRATCH"/…/opencode --version` zeigt `2.x`.
- [ ] **Step 3: Testinstanz und Key bereitstellen.** Backend lokal mit `make up`, `reqlo_`-Key mit Read-only-Rolle als `REQOGNILOOM_API_KEY` exportieren, `REQOGNILOOM_MCP_URL=http://localhost:8001`.
- [ ] **Step 4: V2-Matrix ausführen.** Für jede Zeile die Config in `$XDG_CONFIG_HOME/opencode/opencode.json` von Hand schreiben, dann `opencode mcp list` und ein Tool-Call über `opencode run "call requirement_query"` (oder interaktiv): (a) `mcp.servers.reqogniloom` mit `url …/mcp/`, `oauth:false`, `codemode:false`; (b) dieselbe URL `…/mcp/sse/`; (c) `…/mcp/` ohne `oauth:false`; (d) `codemode:true`; (e) `opencode mcp add reqogniloom --url …/mcp/ --header 'X-API-Key={env:REQOGNILOOM_API_KEY}'` und die entstandene Config lesen.
- [ ] **Step 5: V1-Frage prüfen.** Mit dem System-`opencode` (1.18.x, aber **gleiches Scratch-`HOME`**) einen V1-Eintrag `mcp.reqogniloom` mit URL `…/mcp/` anlegen, `opencode mcp list` und Tool-Call.
- [ ] **Step 6: Bericht schreiben.** `docs/test-reports/opencode-v2-spike.md` mit einer Tabelle (Test, V1, V2, Beobachtung, genaue Version) und den fünf Entscheidungen: Transport, `oauth`, `codemode`, `mcp add` ausreichend ja/nein, Binary-Name.
- [ ] **Step 7: Gate.** Wenn V2 `/mcp/` mit Key-Header nicht verbindet oder `oauth:false` nicht wirkt: Plan hier stoppen und mit dem Nutzer neu entscheiden. Sonst Weiter.
- [ ] **Step 8: Commit (über `git`-Agent).** `git add docs/test-reports/opencode-v2-spike.md` · `git commit -m "docs: record OpenCode V2 spike results"`

---

### Task 1: V2-Snippet und Server-Eintrag im Builder

**Files:**
- Modify: `dist/opencode/build_opencode_package.py`
- Modify: `dist/opencode/test_build_opencode_package.py`
- Modify: `dist/test_mcp_convention_parity.py:130-134` (zweiter Eintrag `opencode-v2`)
- Create (generiert): `dist/opencode/opencode.v2.json.snippet`

**Interfaces:**
- Produces: `v2_server_entry(url: str, key_env: str) -> dict[str, Any]` in `build_opencode_package.py`. `url` ist die Basis ohne Pfad (`"http://h:8001"` oder `"{env:REQOGNILOOM_MCP_URL}"`); Rückgabe:
  `{"type": "remote", "url": f"{url}/mcp/", "headers": {"X-API-Key": f"{{env:{key_env}}}"}, "oauth": False, "codemode": False}`. Task 2 und 4 konsumieren das.
- Produces: Datei `opencode.v2.json.snippet` = `{"mcp": {"servers": {"reqogniloom": v2_server_entry("{env:REQOGNILOOM_MCP_URL}", "REQOGNILOOM_API_KEY")}}}`.

- [ ] **Step 1: Failing Test schreiben** in `dist/opencode/test_build_opencode_package.py`: `test_v2_snippet_shape` baut nach `tmp_path`, lädt `opencode.v2.json.snippet`, assertet `snippet["mcp"]["servers"]["reqogniloom"] == {"type": "remote", "url": "{env:REQOGNILOOM_MCP_URL}/mcp/", "headers": {"X-API-Key": "{env:REQOGNILOOM_API_KEY}"}, "oauth": False, "codemode": False}` und `"reqlo_" not in json.dumps(snippet)`. Zweiter Test `test_v2_entry_uses_literal_url_and_env_key` ruft `v2_server_entry("http://h:8001", "MY_KEY")` und assertet `url == "http://h:8001/mcp/"` sowie `headers == {"X-API-Key": "{env:MY_KEY}"}`.
- [ ] **Step 2: Test laufen lassen.** `pytest dist/opencode/test_build_opencode_package.py -v` — Erwartet: FAIL (`v2_server_entry` / Datei fehlt).
- [ ] **Step 3: `v2_server_entry` und Snippet-Ausgabe implementieren** in `build_opencode_package.py`; `build()` schreibt `opencode.v2.json.snippet` nach demselben Muster (`json.dumps(..., indent=2) + "\n"`) wie das V1-Snippet. V1-Ausgabe bleibt unverändert.
- [ ] **Step 4: Parity-Eintrag ergänzen.** In `dist/test_mcp_convention_parity.py` den `opencode`-Block (Z. 130–134) kopieren: `name="opencode-v2"`, `out_subpath="opencode.v2.json.snippet"`, `committed_path=Path("dist/opencode/opencode.v2.json.snippet")`.
- [ ] **Step 5: Snippet erzeugen.** `python dist/opencode/build_opencode_package.py` (Default `--out` ist das Verzeichnis selbst).
- [ ] **Step 6: Tests laufen lassen.** `pytest dist/opencode dist/test_mcp_convention_parity.py -v` — Erwartet: PASS.
- [ ] **Step 7: Commit.** `git add dist/opencode dist/test_mcp_convention_parity.py` · `git commit -m "feat(opencode): add V2 config snippet and entry builder"`

---

### Task 2: Config-Merge für V2

**Files:**
- Create: `dist/opencode/merge_config.py`
- Create: `dist/opencode/test_merge_config.py`

**Interfaces:**
- Consumes: `v2_server_entry(url: str, key_env: str) -> dict[str, Any]` aus Task 1 (Import per `from build_opencode_package import v2_server_entry`, gleiche Konvention wie der vorhandene Test).
- Produces: `merge_v2(config: dict[str, Any], url: str, key_env: str) -> dict[str, Any]` (setzt `config["mcp"]["servers"]["reqogniloom"]`, mutiert nicht den Eingang, lässt alles andere unberührt) und CLI `python dist/opencode/merge_config.py --config PATH --url URL --key-env NAME [--dry-run]`. Exit 0 bei Erfolg, Exit 2 bei Eingabefehler (ungültiges JSON, ungültiger Env-Name), Exit 3 wenn die Datei nicht schreibbar ist. Task 4 ruft die CLI.

- [ ] **Step 1: Failing Tests schreiben** in `dist/opencode/test_merge_config.py`:
  - `test_merge_keeps_other_servers_and_v1_entries`: Eingang `{"mcp": {"legacy": {"type": "remote", "url": "x"}, "servers": {"other": {"type": "local", "command": ["x"]}}}, "model": "m"}` → `legacy`, `other` und `model` unverändert, `servers.reqogniloom == v2_server_entry(url, key_env)`.
  - `test_merge_is_idempotent`: zweimal anwenden → gleiches Ergebnis.
  - `test_merge_creates_missing_structure`: `merge_v2({}, …)` liefert `{"mcp": {"servers": {"reqogniloom": …}}}`.
  - `test_cli_creates_file_and_parent_dir`: `--config tmp/new/dir/opencode.json` → Datei existiert, valides JSON.
  - `test_cli_refuses_jsonc_and_leaves_file_untouched`: Datei mit `// comment\n{}` → Exit 2, Inhalt byte-gleich, **kein** `.bak-*` angelegt.
  - `test_cli_rejects_bad_key_env`: `--key-env 'A B'`, `'A$B'`, `'{x}'` → Exit 2.
  - `test_cli_dry_run_writes_nothing`.
  - `test_cli_writes_backup_before_changing_existing_file`: bestehende Datei → danach existiert `opencode.json.bak-<14 Ziffern>` mit altem Inhalt.
- [ ] **Step 2: Test laufen lassen.** `pytest dist/opencode/test_merge_config.py -v` — Erwartet: FAIL (Modul fehlt).
- [ ] **Step 3: Implementieren** in `merge_config.py`: Env-Name gegen `^[A-Za-z_][A-Za-z0-9_]*$` prüfen; Datei mit `json.load` lesen (Fehler → Exit 2, Meldung nennt „JSONC/Kommentare werden nicht unterstützt, Eintrag von Hand einfügen" und das Snippet `opencode.v2.json.snippet`); Backup nach Muster `<datei>.bak-%Y%m%d%H%M%S` nur wenn die Datei existiert und sich der Inhalt ändert; atomar schreiben (Temp-Datei im selben Verzeichnis + `os.replace`); JSON mit `indent=2` und Newline am Ende.
- [ ] **Step 4: Tests laufen lassen.** `pytest dist/opencode -v` — Erwartet: PASS.
- [ ] **Step 5: Commit.** `git add dist/opencode/merge_config.py dist/opencode/test_merge_config.py` · `git commit -m "feat(opencode): add safe V2 config merge tool"`

---

### Task 3: Registry-Eintrag `opencode-v2` und generierte Doku

**Files:**
- Modify: `clients/registry.yaml` (neuer Eintrag nach `opencode`, vor `kimi-code`, ca. Z. 363)
- Modify: `scripts/clients/render.py:54-61` (`CLIENT_IDS`)
- Generate: `docs/clients/opencode-v2.md`, `docs/clients/opencode-v2.de.md`, `docs/clients/README.md`, `docs/clients/README.de.md`
- Test: `scripts/clients/test_render.py` (bestehende Tests, keine neuen Funktionen nötig)

**Interfaces:**
- Consumes: Datei `dist/opencode/opencode.v2.json.snippet` aus Task 1 (muss `/mcp/` enthalten).
- Produces: Client-Id `opencode-v2`, auf die `install.sh`/`verify.sh`/CI (Task 4/5) verweisen.

- [ ] **Step 1: `opencode-v2` in `CLIENT_IDS` eintragen** (nach `"opencode"`). `pytest scripts/clients/test_render.py -v` — Erwartet: FAIL (`test_every_client_has_both_language_pages`, Registry kennt die Id nicht).
- [ ] **Step 2: Registry-Eintrag anlegen.** Alle Felder, die `render_client` liest: `id: opencode-v2`, `name: OpenCode V2 (Beta)`, `tested_version` = **im Spike ermittelte V2-Version** (als String), `target_level: L2`, `status: beta`, `transport: streamable_http`, `url_path: /mcp/`, `auth_header: X-API-Key`, `config_artifact: dist/opencode/opencode.v2.json.snippet`, `skills_dir: "~/.config/opencode/skills"`, `install_de/en` (Befehl `bash scripts/clients/install.sh --client opencode-v2 --url "$REQOGNILOOM_MCP_URL" --key-env REQOGNILOOM_API_KEY`), `fallback_de/en` (Inhalt des V2-Snippets als `json`-Block), `verify` (`command: "opencode mcp list"`, erwartet verbundenen Server, danach `requirement_query` → `tool_result: "49 Requirements"`), `prereq_de/en`, `pitfalls_de/en`, `roles_de/en`, `update_de/en`. `roles_*` und `provider_*` aus dem `opencode`-Eintrag übernehmen. `pitfalls_*` nennen mindestens: Beta-Hinweis (Daten/APIs können sich ändern), `oauth:false` ist nötig, `codemode:false` und warum, `mcp.servers` statt `mcp.<name>`, JSONC-Configs werden vom Installer nicht gemergt, Streamable HTTP statt SSE.
- [ ] **Step 3: Generieren.** `python scripts/clients/render.py` — Erwartet: neue/geänderte Dateien unter `docs/clients/`, Exit 0.
- [ ] **Step 4: Tests laufen lassen.** `pytest scripts/clients/test_render.py -v` und `python scripts/clients/render.py --check` — Erwartet: PASS bzw. Exit 0 (inkl. DE/EN-Parität und Snippet-Pfad-Prüfung).
- [ ] **Step 5: Commit.** `git add clients/registry.yaml scripts/clients/render.py docs/clients` · `git commit -m "feat(clients): register OpenCode V2 (beta) and render docs"`

---

### Task 4: Installer und Verify für V2 mit Versionserkennung

**Files:**
- Modify: `scripts/clients/install.sh` (neue Funktionen nach `install_opencode`, Z. ~209; `case` Z. ~369; Kopfkommentar „Supported ids")
- Modify: `scripts/clients/verify.sh:52-57` (Fall `opencode`, neuer Fall `opencode-v2`)
- Create: `scripts/clients/test_install_opencode.py`

**Interfaces:**
- Consumes: CLI `python dist/opencode/merge_config.py --config PATH --url URL --key-env NAME [--dry-run]` aus Task 2; Client-Id `opencode-v2` aus Task 3.
- Produces: Bash-Funktionen `detect_opencode_major` (gibt `1` oder `2` auf stdout, Default `1`), `install_opencode_v1` (= bisheriger Rumpf von `install_opencode`), `install_opencode_v2`; Umgebungsvariable `OPENCODE_BIN` (Default `opencode`) für den Fall `opencode2`.

- [ ] **Step 1: Failing Tests schreiben** in `scripts/clients/test_install_opencode.py`. Hilfsfunktion `run_install(args, env)` startet `bash scripts/clients/install.sh … --yes` mit `HOME`/`XDG_CONFIG_HOME` in `tmp_path` und `PATH` auf ein Verzeichnis mit einem Fake-`opencode`-Skript (`tmp_path/bin/opencode`; `--version` gibt `$FAKE_VERSION` aus, `mcp add` protokolliert seine Argumente in eine Datei). Tests:
  - `test_v2_writes_servers_entry_with_env_key_only`: `--client opencode-v2 --url http://h:8001 --key-env MY_KEY` → `tmp/.config/opencode/opencode.json` enthält `mcp.servers.reqogniloom.url == "http://h:8001/mcp/"`, `headers["X-API-Key"] == "{env:MY_KEY}"`, `oauth is False`, und `"reqlo_"` kommt nirgends vor; Skills landen in `--skills-dir`.
  - `test_auto_detect_picks_v2_for_major_2`: `--client opencode`, `FAKE_VERSION=2.0.0-beta.3` → V2-Eintrag geschrieben, `mcp add` **nicht** aufgerufen.
  - `test_auto_detect_picks_v1_for_major_1`: `FAKE_VERSION=1.18.35` → Fake-`mcp add` mit `/mcp/sse/` aufgerufen, keine `opencode.json` geschrieben.
  - `test_missing_or_garbled_version_falls_back_to_v1`: Fake gibt `garbage` aus bzw. fehlt → V1-Pfad.
  - `test_v2_rerun_is_idempotent`: zweimal ausführen → `opencode.json` danach unverändert, höchstens ein `.bak-*`.
  - `test_v2_keeps_existing_servers`: vorab angelegte `opencode.json` mit `mcp.servers.other` → bleibt.
  - `test_v2_aborts_on_jsonc_without_touching_file`: Datei mit Kommentar → Exit ≠ 0, Inhalt gleich.
  - `test_bad_key_env_is_rejected`: `--key-env 'A B'` → Exit ≠ 0, nichts geschrieben.
  - `test_dry_run_v2_writes_nothing`: `--dry-run` → keine Datei, Ausgabe beginnt Zeilen mit `[dry-run]`.
- [ ] **Step 2: Test laufen lassen.** `pytest scripts/clients/test_install_opencode.py -v` — Erwartet: FAIL (Client `opencode-v2` unbekannt).
- [ ] **Step 3: `install.sh` anpassen.** (a) `OPENCODE_BIN="${OPENCODE_BIN:-opencode}"`; (b) `detect_opencode_major`: `"$OPENCODE_BIN" --version 2>/dev/null | sed -n 's/^\([0-9][0-9]*\)\..*/\1/p' | head -1`, leer → `1`; (c) bisheriges `install_opencode` unverändert nach `install_opencode_v1` umbenennen (nutzt `$OPENCODE_BIN`); (d) `install_opencode_v2`: Env-Name per Regex `^[A-Za-z_][A-Za-z0-9_]*$` prüfen (sonst `exit 2`), `run python3 "${REPO_ROOT}/dist/opencode/merge_config.py" --config "${XDG_CONFIG_HOME:-$HOME/.config}/opencode/opencode.json" --url "$URL" --key-env "$KEY_ENV"` (bei `DRY_RUN` mit `--dry-run`), danach Skills und `DOMAIN_MODEL.md` wie im V1-Pfad kopieren; (e) `install_opencode` wird zur Weiche (`[ "$(detect_opencode_major)" = 2 ]`); (f) `case`: `opencode-v2) confirm; install_opencode_v2 ;;` und Kopfkommentar „Supported ids" um `opencode-v2` ergänzen. `require_bin` im V2-Pfad **nicht** aufrufen (kein Binary nötig zum Schreiben der Config).
- [ ] **Step 4: `verify.sh` anpassen.** Fall `opencode|opencode-v2)`: `OPENCODE_BIN` nutzen, `mcp list` prüfen wie bisher (`expect_marker "$out" "reqogniloom"`); bei `opencode-v2` zusätzlich Zeile `info: OpenCode V2 is a beta; config lives in mcp.servers.reqogniloom`.
- [ ] **Step 5: Tests laufen lassen.** `pytest scripts/clients -v` und `bash -n scripts/clients/install.sh scripts/clients/verify.sh` — Erwartet: PASS, keine Syntaxfehler.
- [ ] **Step 6: Commit.** `git add scripts/clients` · `git commit -m "feat(clients): install and verify OpenCode V2 with auto-detect"`

---

### Task 5: CI, Release-Artefakt, Changelog

**Files:**
- Modify: `.github/workflows/client-smoke.yml:40-46` (Matrix, `continue-on-error`)
- Modify: `.github/workflows/release-client-artifacts.yml:101`
- Modify: `CHANGELOG.md` (Abschnitt Unreleased)

**Interfaces:**
- Consumes: Client-Id `opencode-v2` und Datei `dist/opencode/opencode.v2.json.snippet`.

- [ ] **Step 1: Smoke-Matrix erweitern.** `opencode-v2` unter `client:` ergänzen und am Job `continue-on-error: ${{ matrix.client == 'opencode-v2' }}` setzen (Beta darf Release nicht blockieren). Kommentar nennt Grund.
- [ ] **Step 2: Release-Tarball erweitern.** In Z. 101 `opencode.v2.json.snippet` neben `opencode.json.snippet` aufnehmen.
- [ ] **Step 3: Changelog.** Ein Eintrag unter Unreleased: „OpenCode V2 (beta): own client entry, `opencode.v2.json.snippet`, installer auto-detects the major version".
- [ ] **Step 4: Prüfen.** `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in sys.argv[1:]]" .github/workflows/client-smoke.yml .github/workflows/release-client-artifacts.yml` — Erwartet: kein Fehler. Prüfen, dass `git grep -n "opencode.json.snippet" .github` den Tarball-Eintrag mit beiden Dateien zeigt.
- [ ] **Step 5: Commit.** `git add .github CHANGELOG.md` · `git commit -m "ci(clients): smoke and ship OpenCode V2 snippet"`

---

### Task 6: Gesamtabnahme

**Files:** keine Änderungen, nur Läufe.

- [ ] **Step 1: Alle betroffenen Tests, sequenziell.** `pytest scripts/clients dist/opencode dist/test_mcp_convention_parity.py -v` — Erwartet: alles PASS.
- [ ] **Step 2: Drift-Gate.** `python scripts/clients/render.py --check` — Erwartet: Exit 0.
- [ ] **Step 3: Echter End-to-End in Isolation** (Scratch-`HOME` wie Task 0): `bash scripts/clients/install.sh --client opencode --url http://localhost:8001 --key-env REQOGNILOOM_API_KEY --yes` mit V2-Binary im `PATH`, dann `bash scripts/clients/verify.sh --client opencode-v2` und ein echter `requirement_query`. Danach dasselbe mit V1-Binary und `--client opencode`. Erwartet: beide verbunden, V1-Konfig byte-gleich zu vorher.
- [ ] **Step 4: Ergebnis in den Bericht.** Befunde und Versionsnummern in `docs/test-reports/opencode-v2-spike.md` unter „Abnahme" nachtragen.
- [ ] **Step 5: Commit und PR (über `git`-Agent).** `git commit -m "docs: add OpenCode V2 acceptance results"`, Push, PR gegen `main` mit Verweis auf Spec und Plan.

---

## Self-Review

- **Spec-Abdeckung:** F1/F2/F4/F7/F8 → Task 0 (Beweis) und Task 1/4 (Umsetzung); F3 (Config-Form) → Task 1/2; F5 → kein Aufwand, im Snippet nicht gesetzt; F6 (Skills) → keine Änderung nötig, Task 4 kopiert dieselben Skills; F9 (Beta) → `status: beta`, `continue-on-error`. D1 (V1 ebenfalls auf `/mcp/`) bewusst **nicht** umgesetzt: V1 bleibt unverändert, Folgeticket falls Task 0 es stützt. D2/D3/D4 → Task 1/3.
- **Abweichung vom Spec:** `variants` im Registry entfällt zugunsten eines eigenen Eintrags `opencode-v2` (Renderer-Umbau gespart, Spec entsprechend angepasst).
- **Typkonsistenz:** `v2_server_entry(url, key_env)` (Task 1) wird in Task 2 (`merge_v2`) und Task 4 (CLI-Parameter `--url`/`--key-env`) mit denselben Namen genutzt; `OPENCODE_BIN` und `detect_opencode_major` nur in Task 4.
- **Annahmen mit Spike-Vorbehalt:** `/mcp/`, `oauth:false`, `codemode:false`, Binary `opencode`. Task 0 Step 7 ist das Gate.
- **Nicht abgedeckt:** `opencode2`-Binary-Autodetect (nur über `OPENCODE_BIN` manuell), JSONC-Merge (Installer bricht ab und verweist aufs Snippet), Plugin-Migration (entfällt).
