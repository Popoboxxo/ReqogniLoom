---
type: REVIEW
scope: wp-1a-mcp-server-evidence-index
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-1a Evidence-Index — MCP-Server

Stack: `http://localhost:8001` (ASGI/uvicorn, 8 Container healthy),
Frontend `http://localhost:5173`, `GET /health/` → 200 `{"status":"ok"}`.
Branch `chore/system-audit-2026-09` @ `abd61aed` (+ `fc505524` WP-3-Commit,
während WP-1a lief). Keine Produkt-Code-Änderung vorgenommen.

| Datei | Inhalt |
|---|---|
| `wp1a-mcp-jsonrpc-and-transports.json` | 82 Roh-Request/Response-Paare: JSON-RPC-Konformität, id-Varianten, malformed frames, Batch, params-Shapes, Transport-Existenz, Auth-Matrix, CORS-Preflight, Discovery |
| `wp1a-mcp-tool-count-analysis.json` | Registry (219) vs. Manifest (219) vs. `tools/list` (80/219) — Namens- und Feld-Diff, versteckte Tool-Liste |
| `wp1a-mcp-tool-count-resolution.md` | Auflösung Issue #1104 inkl. Mechanik (`datei.py:zeile`) und 12-Mutationstest-Tabelle |
| `wp1a-mcp-validator-matrix.json` | 39 Eingabevalidierungs-Fälle über 12 Tools (leer, falscher Typ, unbekanntes Feld, SQL-Metazeichen, Unicode/Emoji, 20 000 Zeichen, Null-Byte) |
| `wp1a-mcp-tenant-isolation-matrix.json` | 65 Fälle Tenant-A-Key gegen **echten** zweiten Tenant (by-id reads, workspace-scoped reads, tenant-global, writes) |
| `wp1a-mcp-degradation-baseline.json` | 12 Probes mit laufendem Stack (Referenz) |
| `wp1a-mcp-degradation-redis-down.json` | dieselben 12 Probes mit gestopptem Redis — alle hängen |
| `wp1a-mcp-registry-manifest-219.json` | `export_tool_manifest`-Ausgabe (unveränderte Kopie, 219 Tools) |
| `wp1a-mcp-auth-and-key-tenant.md` | Auth-Matrix, `ApiKey.tenant_id`-Defekt, Scope-Validierungslücke, CORS |

## API-Keys (maskiert)

| Alias | Scope | Herkunft | Status nach dem Lauf |
|---|---|---|---|
| `reqlo_***porejYR` | `readwrite` (nicht anerkannt) | vorbestehend, `stack-seeds.md` §5 | unverändert (nicht angefasst) |
| `...POtV` | `admin` | temporär für dieses Audit gemintet | **gelöscht** |
| `...MsEC` | `admin`, Tenant B | temporär, Tenant B für die Isolationsmatrix | **gelöscht** (Tenant B ebenfalls entfernt) |
| `...UY0v` | `admin` | temporär für CR-04/CR-05-Reconciliation | **gelöscht** |
| `...lQ8s` | `admin`, Tenant-B-Besitzer in Tenant A | temporär, für die Tenant-Hypothese | **gelöscht** |

Klartext-Keys stehen ausschließlich in
`docs/audit/2026-09/AUDIT_EVIDENCE/stack-seeds.md` (bewusst uncommitted) und in
den drei temporären Container-Skripten unter `/tmp` (flüchtig). Kein
Klartext-Key in einercommitteten Datei.

## Runtime-Rückstände nach dem Lauf

* **Alle** von diesem Audit erzeugten `pl_glossary_term`- und
  `mem_memory_entry`-Zeilen gelöscht (verifiziert: 0 Restzeilen).
* Alle `wp1a-*`-API-Keys gelöscht. Die zwei vorbestehenden
  `audit-live-probe`-Keys blieben unangetastet.
* Demo-Workspace `4eee7ca1-…` weiterhin `is_active = true`.
* **Bewusster Rest:** ein leerer Tenant `4e0b5ab3-…` („wp1a-audit-tenant-B")
  mit 2 `audit_entry`-Zeilen. `audit_entry` ist per Datenbank-Trigger
  **append-only** (`RaiseException: audit_entry is append-only: DELETE is not
  permitted (REQ-L2-AL-003)`), deshalb nicht löschbar — das ist korrektes
  Verhalten des Audit-Trails, kein Restfehler.
* Ein Audit-Tenant `4854f768-…` wurde vollständig entfernt.
* `docker restart` von Redis wurde nach dem Degradationstest ausgeführt;
  Health-Check danach 200.

## Test-Werkzeuge

Alle Live-Probes liefen gegen `http://localhost:8001` mit
`urllib.request` (kein Playwright, kein Browser). Container-seitige
Untersuchungen liefen über `docker exec … python` mit
`PYTHONPATH=/app` und `DJANGO_SETTINGS_MODULE=reqogniloom.settings`.
Die Skripte lagen unter `C:\Users\duchr\AppData\Local\Temp\opencode\wp1a\`
außerhalb des Repos; eine versehentlich im Repo angelegte Hilfsdatei
(`backend/wp1a_mint_keys.py`) wurde sofort gelöscht — `git status` ist
sauber bis auf die beiden untracked Audit-Verzeichnisse.
