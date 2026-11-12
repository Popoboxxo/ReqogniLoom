# OpenCode 1 und 2 gegen den echten MCP-Endpunkt — Verifikation

**Datum:** 2026-11-12
**Stack:** lokal gebaut aus `backend/` @ `f30e3ef2` (Branch-Basis des Probe-PRs), Image-Tag `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.29`
**Clients:** OpenCode V1 `1.18.35`, OpenCode V2 `2.2.6`
**Methode:** `scripts/clients/mcp_probe.py` (JSON-RPC direkt, unabhängig vom Client) plus `install.sh`/`verify.sh` in isolierten `HOME`-Verzeichnissen.
**Issues:** #1703 (Client-Verifikation), #1704 (Code Mode)

> Diese Messung lief auf einem Host mit ~5 GiB RAM. Der Stack bestand nur aus `postgres`, `redis`, `migrate` und `backend` (Port 8001); `celery`/`celery-beat` waren bewusst nicht gestartet. `/health/` antwortet deshalb mit `status: "degraded"` (nur `celery_worker`/`celery_beat` down), Datenbank, Cache und Memory-Backend sind `ok`. Ein „degraded" aus diesem Grund ist kein Fehler dieser Verifikation.

---

## 1. Server-Seite (Protokollebene)

`mcp_probe.py` gegen `http://localhost:8001/mcp/` mit einem **Read-only-API-Key** (`scope=read_only`, über `POST /api/v1/api-keys/` als Admin angelegt):

| Messwert | Ergebnis |
|---|---|
| `initialize` | ok, 52 ms |
| `notifications/initialized` | ok (202), 31 ms |
| Discovery-GET mit `Accept: text/event-stream` | **HTTP 405** (bewusst, s. u.), 5 ms |
| `tools/list` | **107 Tools**, 274 ms, 66.408 Bytes Rohkatalog |
| `tools/call` `requirement.query` | ok, 1 Zeile, 631 ms |
| Exit-Code | 0 (`initialize_ok`, `tool_count > 0`, `has_tool`, `call_ok`) |

**Tool-Zahl ist scope-abhängig.** Die 107 sind der Katalog eines Read-only-Keys auf einem geseedeten Workspace, nicht die Gesamtzahl. Das Manifest nennt 290 Tools (`docs/agent-templates/tool-manifest.json`). Eine feste Zahl darf daraus nicht abgeleitet werden (#1593/#1730).

**Discovery-GET = 405 ist gewollt.** `McpHttpTransportView.get` beantwortet einen SSE-Accept mit 405, damit Clients nicht in einen Reconnect-Loop gegen einen nicht bedienten Stream laufen (H1/H5.2). Die Probe wertet 405 als sauberen Zustand, nicht als Fehler.

**Tool-Namen sind punktiert.** `requirement.query`, `requirement.get`, `change_request.query` — nicht `requirement_query` wie im Phase-C-Plan angenommen. Die Probe nutzt den echten Namen; der Plan ist an dieser Stelle veraltet.

---

## 2. Client-Seite (V1 und V2)

Beide Clients wurden in einem isolierten `HOME` installiert (`install.sh`) und über `verify.sh` geprüft. **Wichtig:** Die Prüfung muss *außerhalb* des Repos laufen — siehe Abschnitt 4.

| Client | Version | Installation | `mcp list` | Tool-Katalog |
|---|---|---|---|---|
| V1 | 1.18.35 | Config in `$HOME/.config/opencode/opencode.jsonc` | `✓ reqogniloom connected` | nicht über CLI introspizierbar |
| V2 | 2.2.6 | Config unter `$HOME/.config/opencode/`, Block `mcp.servers.reqogniloom` (V2 schreibt die reine JSON-Form; seine Merge-Stufe akzeptiert kein JSONC) | `✓ reqogniloom connected` | nicht über CLI introspizierbar |

**V2-Restart-Quirk bestätigt und im Verifier abgefangen.** Direkt nach `install.sh` meldete `verify.sh --client opencode-v2` „expected marker 'reqogniloom' not found". Ein zweiter `opencode mcp list` wenige Sekunden später zeigte `✓ reqogniloom connected`. Die Config ist also geschrieben, der laufende Dienst übernimmt sie aber nicht im selben Moment. `verify.sh` wiederholt die Abfrage deshalb (bis zu 10 Versuche à 2 s, per `VERIFY_RETRY_ATTEMPTS`/`VERIFY_RETRY_DELAY` übersteuerbar) und pinnt das mit `scripts/clients/test_verify_opencode.py`.

**Kein clientseitiger Tool-Katalog messbar.** `opencode debug` bietet (in 2.2.6) nur `agents`, `config`, `heap-dump`, `paths` — kein Unterkommando, das MCP-Tools auflistet. Die Tool-Sichtbarkeit ist deshalb nur serverseitig belegt (Abschnitt 1). Das ist die im Plan vorgesehene Grenze, nicht ein Fehler der Messung.

**Echtes `HOME` unverändert.** SHA-256 über alle Dateien in `~/.config/opencode` vor und nach den Läufen: identisch (`fafed686…`).

---

## 3. Code Mode (#1704)

| Prüfpunkt | Ergebnis |
|---|---|
| Auslieferungszustand | `codemode: false` ist im Snippet und in der erzeugten V2-Config wirksam (`opencode debug config` zeigt `codemode: false`) |
| Kataloggröße | 66.408 Bytes für 107 Tools ≈ **16,6k Token** (Bytes/4, ausdrücklich Näherung) |
| Katalog-Latenz | 274 ms (weit unter dem `timeout.catalog`-Default von 30 s) |
| Skills → Tools | Die sechs Skills unter `dist/opencode/` nennen **92 der 290** Manifest-Tools; alle 92 existieren im Manifest (einziger Treffer ohne Manifest-Bezug ist der Regex-Artefakt-String `e.g`) |
| V1 mit `codemode`-Key | **toleriert**: V1 verbindet mit `codemode: false` im Server-Block (`✓ reqogniloom connected`) — eine Config-Form trägt beide Versionen |
| Sichtbarkeit `codemode: true` vs. `false` | **nicht messbar** ohne clientseitige Tool-Introspektion; die Spike-Aussage (`reqogniloom_<tool>` über Katalog) bleibt unbelegt |

**Empfehlung:** `codemode: false` beibehalten (Spec D2). Die Messung stützt das indirekt: der Katalog ist mit ~16,6k Token kein Kostenproblem, aber die Namensauflösung über einen Wrapper-Katalog ist unbelegt und bringt ohne Messung keinen Vorteil. Eine Änderung wäre ein eigenes Issue.

---

## 4. Befund: Repo-Root-Config leckt in die Client-Prüfung

Wird `verify.sh` **innerhalb** des Checkouts ausgeführt, lädt OpenCode zusätzlich die Client-Config im Wurzelverzeichnis des Haupt-Checkouts (`/home/hermes/repos/ReqogniLoom/`). `opencode debug config` listet es als zweite Quelle; in `mcp list` erscheint dadurch ein fremder Server (`playwright`), der nicht aus dem isolierten `HOME` stammt.

**Abgestellt in `verify.sh`:** Der OpenCode-Zweig führt den Client jetzt aus einem temporären Verzeichnis aus (`mktemp -d`), damit die Projekt-Config des Checkouts nicht mehr in die Antwort leckt. Ein Test (`test_verify_opencode.py`) pinnt Arbeitsverzeichnis und Retry-Verhalten. Für manuelle Läufe bleibt wichtig: `PATH` explizit auf die gewünschte Client-Version setzen — beide Binaries heißen `opencode`, die Reihenfolge entscheidet, welche Version läuft. Ohne diese Vorkehrung misst man eine Mischkonfiguration — genau der Fall, der in dieser Messung zuerst auftrat und korrigiert wurde.

---

## 5. CI-Entscheidung

- **Server-Probe: CI-fähig.** `mcp_probe.py` braucht nur Python-Stdlib, einen laufenden Backend-Container und einen Read-only-Key. Kein Client-Download, keine `HOME`-Isolation, stabiles Ergebnis. Sie gehört in `client-smoke.yml` (Task 5).
- **Client-Läufe V1/V2: bleiben `workflow_dispatch`.** Der V2-Restart-Quirk und die nötige `HOME`-/`PATH`-Disziplin machen sie für einen Pflicht-Trigger zu fragil (E5 bleibt vertagt).

---

## 6. Grenzen dieser Messung

- Kein LLM-Provider im Stack: ein echter Tool-Aufruf *durch ein Modell* wurde nicht ausgeführt, nur der JSON-RPC-Aufruf auf Protokollebene.
- Keine Screenshots/UI-Prüfung (kein Frontend-Container gestartet).
- Tool-Zahlen gelten für einen Read-only-Key auf einem Demo-Workspace.
- Code-Mode-Sichtbarkeit ist unbelegt (Abschnitt 3).
- Der Stack lief ohne Celery; asynchrone Pfade wurden nicht geprüft.
