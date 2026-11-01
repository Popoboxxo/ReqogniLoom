# OpenCode V2 — Capability-Spike (Task 0)

> Datum: 2026-11-01 · Branch: `feat/opencode-v2-support` · Isoliert in `/tmp`, System-V1 unangetastet.
> Quellen: `docs/superpowers/specs/2026-11-01-opencode-v2-support-design.md`, `docs/superpowers/plans/2026-11-01-opencode-v2-support.md` (Task 0).

## Umgebung

| Komponente | Wert |
|---|---|
| OpenCode V2 | `v2.2.5` (GitHub-Release `sst/opencode`, Asset `opencode-linux-x64.tar.gz`) |
| OpenCode V1 (System) | `1.19.5` (`/usr/local/bin/opencode`) |
| ReqogniLoom | Dev-Stack, Backend `http://localhost:8001`, MCP `http://localhost:8001/mcp/` |
| Isolation | eigenes `HOME`/`XDG_CONFIG_HOME`/`XDG_DATA_HOME` unter `/tmp/opencode/v2/scratch*`; V2-Binary ebenfalls unter `/tmp` |

## Matrix

| Test | V2 2.2.5 | V1 1.19.5 | Beobachtung |
|---|---|---|---|
| Globale Config `~/.config/opencode/opencode.json` mit `mcp.servers.reqogniloom` | ✅ `✓ reqogniloom connected` | n/a | `mcp list` braucht einen Projekt-/CWD-Kontext; ohne Projekt meldet V2 „No MCP servers configured". |
| Projekt-Config `<git-root>/opencode.json` | ✅ connected | ✅ connected | Projekt-Config hat Vorrang; beide Formen werden gelesen. |
| Streamable HTTP `/mcp/` | ✅ connected | ✅ connected | **F1 bestätigt**; V1 kann ebenfalls `/mcp/` (D1 möglich, im Plan bewusst nicht umgesetzt). |
| SSE `/mcp/sse/` | nicht getestet (nicht nötig) | ✅ connected | V1-Bestand unverändert. |
| Header-Auth `X-API-Key: {env:…}` ohne OAuth-Aufforderung | ✅ mit `oauth:false` | ✅ | **F2 bestätigt**: ohne `oauth:false` ist OAuth der Default. |
| `mcp add --global` | schreibt `mcp.servers`, **setzt kein `oauth:false`** | nutzt `mcp add` | **F7 bestätigt**: `mcp add` reicht für V2-Header-Auth nicht → JSON-Merge-Pfad nötig. |
| `codemode:false` | akzeptiert (Config gültig) | n/a | **F4**: Tools direkt statt Code-Mode; Tool-Namen bleiben `reqogniloom_<tool>`. |
| Binary-Name | `opencode` | `opencode` | **F8**: V2 ersetzt V1 (kein Side-by-Side); `opencode2` nicht beobachtet → `OPENCODE_BIN`-Override. |
| Echter Tool-Call (`requirement_query`) | nicht ausgeführt | nicht ausgeführt | Scratch-`HOME` hat keine LLM-Auth; Transport + Auth sind durch `connected` belegt. |

## Entscheidungen (aus dem Spike)

- **Transport:** Streamable HTTP `/mcp/` für V2. V1 bleibt auf dem bestehenden Pfad (Plan-Global-Constraint), obwohl V1 1.19.5 `/mcp/` ebenfalls spricht.
- **OAuth:** `oauth:false` ist Pflicht für Header-Auth.
- **Code Mode:** `codemode:false`, damit Skills und Tool-Namen unverändert gelten.
- **Config-Form:** `mcp.servers.reqogniloom` (nicht `mcp.<name>`).
- **MCP-Registrierung:** `mcp add` kann `oauth:false`/`codemode:false` nicht setzen → Installer merged das V2-Snippet per JSON.
- **Version:** `2.2.5` (aktueller Release-Stand, Verbindung real geprüft).
- **Pfadhinweis:** Der Installer schreibt global (`~/.config/opencode/opencode.json`); `opencode mcp list` zeigt den Server beim Aufruf **innerhalb eines Projekts**.

## Befund für die Umsetzung

- **Versionsausgabe:** V2 gibt `opencode v2.2.5` aus (Programmname + `v`), V1 `1.19.5`. Die im Plan skizzierte Regex (`^\([0-9]+\)\.`) erkannte V2 deshalb nicht und fiel auf V1 zurück. `detect_opencode_major` überspringt jetzt einen beliebigen Nicht-Ziffern-Präfix; Regressionstest `test_auto_detect_handles_program_prefixed_version`.
- **Service-Port:** Ein V2-Hintergrunddienst aus einem anderen Scratch-`HOME` kann den festen Port belegen; `mcp list` scheitert dann mit `Server process exited with code 1`. Kein Produktfehler — isoliertes `HOME` bzw. gestoppter Dienst löst es.

## Abnahme (Task 6)

- [x] **V2-E2E:** `install.sh --client opencode` mit V2 2.2.5 im `PATH` → Auto-Detect wählt V2, schreibt `~/.config/opencode/opencode.json` mit `mcp.servers.reqogniloom` (`/mcp/`, `oauth:false`, `codemode:false`); `verify.sh --client opencode-v2` → `✓ reqogniloom connected`, `verify: opencode OK`.
- [x] **V1-E2E:** `install.sh --client opencode` mit V1 1.19.5 → unveränderter `mcp add`-Pfad (`/mcp/sse/`), Projekt-Config; `verify.sh --client opencode` → `verify: opencode OK`.
- [x] V1-Snippet byte-gleich; 91 Tests + `render.py --check` grün.
- [ ] Echter Tool-Call (`requirement_query`) im Scratch-`HOME` — keine Modell-Auth vorhanden; Transport/Auth sind durch `connected` belegt.
