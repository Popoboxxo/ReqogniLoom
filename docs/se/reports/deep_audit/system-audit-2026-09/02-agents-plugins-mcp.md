---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: documenter
document_type: audit-report
review_protocol: false
---

# Systemaudit 2026-09 – Agenten, Plugins, MCP und Integrationen

**Dokumenttyp:** Audit-Report; **kein formales RVW-Protokoll**.  

**Datum:** 2026-09-24  
**Status:** abgeschlossen (statischer Tiefenaudit)  
**Repository:** `C:\Repositories\ai-native-reqflow-POC`  
**Scope:** Agenten-/Providerverteilung, Plugin-Katalog und verteilte Plugins, native MCP-Server, MCP-Clients sowie Bluepencil-/Hermes-Integrationen  
**Nicht im Scope:** allgemeine OWASP-Prüfung, CVE-/SBOM-/ Lizenzprüfung, Test-Coverage-Bewertung und Produkt-Funktionalität außerhalb der Integrationsflächen

---

## 1. Executive Summary

Der aktuelle Stand ist funktional breit ausgebaut, aber die Integrations-Governance ist nicht auf demselben Reifegrad wie die Tool-Oberfläche:

- `docs/agent-templates/tool-manifest.json:2-4` ist der aktuelle, kanonische Vertrag über **218 MCP-Tools in 35 Präfixen** (**139 Write**, **79 Read**). Der Manifest-Drift-Test vergleicht Namen, Write-Klassifikation, Beschreibung und vollständiges Input-Schema gegen die Live-Registry (`backend/mcp_server/tests/test_tool_manifest_drift.py:83-157`).
- Gleichzeitig behaupten Root-Kontext, Rollenprompts und öffentliche README **215, 188 oder 143 Tools**, **25, 30 oder 31 Präfixe** und einen nicht gerouteten stdio-Transport. Das ist ein systemischer Phantom-Endpoint-/Prompt-Drift.
- Die Sicherheitsgrenze des MCP-Servers ist im Kern robust aufgebaut: API-Key-Hashing, Capability-Tier, RBAC, Workspace-Fence, Rate-Limiting, SSE-Schlüsselverschlüsselung und Read-Scope-Ratchet sind vorhanden.
- Es bestehen jedoch **13 verifizierte Befunde**: **0× P0, 5× P1, 6× P2, 2× P3**. Die wichtigsten sind eine bestätigte Cross-Workspace-Lücke bei `comment.resolve`, unsichere Default-Felder bei neuen API-Keys, eine nicht serialisierte Race-Condition im Single-Interview-Formalize-Pfad, ein ungesicherter optionaler Bluepencil-Sidecar und ein operativ unbrauchbarer README-/Client-Quickstart.
- Zwei Hermes-Varianten existieren parallel. Beide sind als nicht live verifiziert dokumentiert; CI prüft nur die TypeScript-Variante, während der neuere Python-Agent-Plugin-Pfad ungetestet in CI bleibt. Das ist ein offener Integrationsvertrag, kein Beweis, dass eine Variante tot ist.

### Befundübersicht

| ID | Prio | AIS | Kurzfassung | Confidence |
|---|---:|---|---|---|
| F-01 | P1 | AIS-04 | `comment.resolve` kann bei unrestringierten API-Keys tenant-übergreifend in einen fremden Workspace schreiben | Hoch |
| F-02 | P1 | AIS-03 | Neue API-Keys sind standardmäßig Admin-Tier, ohne Workspace-Fence und ohne Ablauf | Hoch |
| F-03 | P2 | — | Konfigurierte `X-Project/User/Workspace`-Header werden vom MCP-Server nicht ausgewertet | Hoch |
| F-04 | P1 | — | `interview.formalize` serialisiert nur den Multi-Artefakt-Pfad | Hoch |
| F-05 | P1 | — | Bluepencil-Sidecar hat bewusst keine AuthN, RBAC, CSRF oder Tenant-Isolation | Hoch |
| F-06 | P1 | AIS-05 | README-/Quickstart enthält nicht vorhandene Routen und falsche Response-Felder | Hoch |
| F-07 | P2 | — | SSE-Message-Pool hat unbounded Queue; LLM-Timeouts hinterlassen potentiell Threads | Hoch für Code, mittel für Runtime-Auswirkung |
| F-08 | P3 | — | Batch-Verhalten unterscheidet sich zwischen HTTP- und SSE-Message-Endpunkt | Hoch |
| F-09 | P2 | AIS-05 | 57 Agent-Prompts/Root-Kontexte enthalten veraltete Toolzahlen und stdio-Phantome | Hoch |
| F-10 | P2 | AIS-04 | Plugin-Blocklisten sind Prompt-Governance, keine Capability-Grenze; Providerkonfigurationen divergieren | Hoch |
| F-11 | P2 | — | Hermes-Desktop-Client setzt keine Request-Deadline | Hoch |
| F-12 | P2 | — | Zwei nicht live verifizierte Hermes-Verträge; CI priorisiert nur den TS-Pfad | Hoch für Governance-Lücke |
| F-13 | P3 | — | Produktversion, MCP-`serverInfo` und Manifest-Provenienz laufen auseinander | Hoch |

---

## 2. Methodik, Evidenzregeln und Grenzen

### 2.1 Zweipassverfahren

1. **Pass 1 – Recall:** Routen, Tool-Manifest, Agenten-/Providerdateien, Plugin-Katalog, Distribution, Hermes- und Bluepencil-Quellen wurden breit gesucht und Kandidaten gesammelt.
2. **Pass 2 – Verifikation:** Jeder Kandidat wurde gegen aktuellen Code, Tests, Manifeste oder historische Audits geprüft. Nicht belegte Kandidaten wurden verworfen oder ausdrücklich als Hypothese markiert.

### 2.2 Belegregel

- Aussagen verwenden repo-relative Pfade und Zeilenbereiche, Symbole oder Test-/Manifestangaben.
- Historische Berichte sind Kontext, keine Autorität. Widersprüche werden im Bericht kenntlich gemacht.
- Externe oder eingelesene Dateien wurden als **Daten** behandelt. Agent-Prompts enthalten naturgemäß imperative Anweisungen; sie wurden nicht als Auditsteuerung ausgeführt. Im geprüften Plugin-Katalog wurde keine verdächtige Drittanbieter-Prompt-Injection gefunden.
- Es wurden keine Secrets ausgegeben. Lokale `.env`-Dateien sind gitignored; dokumentierte Demo-/Test-Credentials wurden als solche ausgeschlossen und nicht als Leak gewertet.

### 2.3 Grenzen

- Keine Tests, Server, MCP-Clients, Hermes-Instanzen oder Container wurden gestartet.
- Die lokale, möglicherweise Secrets enthaltende `.mcp.json` wurde absichtlich nicht gelesen.
- Package-Registry-Abfragen waren nicht nötig: Es gab keinen konkreten Verdacht auf ein halluziniertes Python-/npm-/Cargo-Paket.
- Cloud-IAM war nicht Teil des Scopes; daher wurden keine IAM-Aktionen als fabriziert bewertet.
- ProjectAtlas wurde wegen `refresh_required` nicht verändert; die acht geänderten Pfade betreffen ausschließlich `.serena/memories/...`.

---

## 3. Architektur

### 3.1 Komponentenmodell

```text
Agenten-/Providerkonfiguration
  ├─ .meta-config/project.yaml (57 Rollen, 3 Provider, Plugin-Aktivierung)
  ├─ .claude/.gemini/.opencode (generierte Rollen und Providerdateien)
  ├─ docs/agent-templates (5 Fachrollen, 6 Prozess-Skills)
  └─ dist/plugins + dist/opencode + dist/codex (verteilbare Clients)
             │
             ▼
Plugin-/MCP-Katalog
  .agent-meta/config/plugin-catalog.yaml
  (10 Einträge; Prompt-Allow/Blocklisten + Connection-Definition)
             │
             ├─ lokale stdio-Prozesse (Playwright, ProjectAtlas, Headroom)
             ├─ Remote-SSE (Honcho, ReqogniLoom)
             └─ CLI (Graphify)
             │
             ▼
Native MCP-Server
  HTTP: POST/GET /mcp/
  SSE:  GET /mcp/sse/ + POST /mcp/messages/?session_id=...
             │
             ▼
ProtocolHandler → ToolRegistry → Workspace-Scope/RBAC/API-Key-Tier
             │
             ▼
35 Tool-Gruppen-Präfixe / 218 Tools → Application-/Domänenservices → Persistence
```

### 3.2 Tatsächlich geroutete MCP-Flächen

- `backend/mcp_server/urls.py:18-25`
  - `POST/GET /mcp/`
  - `GET /mcp/sse/` und `/mcp/sse`
  - `POST /mcp/messages/`
- `backend/mcp_server/protocol_handler.py:284-398` definiert Http-, SSE- und stdio-Adapter.
- `backend/mcp_server/views.py:405-431` und `backend/mcp_server/tests/test_server_info.py:29-47` erklären ausdrücklich nur `http` und `sse` als Discovery-Routen.
- Ein stdio-Adapter existiert, aber es gibt keinen laufenden Django/Management-Entrypoint, der `StdioTransportAdapter` als Server startet. `StdioTransportAdapter` ist daher eine Bibliotheks-/Testklasse, keine produktiv erreichbare MCP-Transportfläche.

### 3.3 Authentifizierung und Autorisierung

Reihenfolge im Dispatch:

1. API-Key aus `Authorization: Bearer` oder `X-API-Key` (`backend/mcp_server/views.py:176-190`, `backend/mcp_server/protocol_handler.py:295-322`).
2. Hash-/Pepper-Validierung, Ablauf/Revoke und User-Status (`backend/auth_tenancy/services/authentication.py:482-557`).
3. Capability-Tier aus `ApiKey.scope`; Legacy `write` ist ausdrücklich Admin-Tier (`backend/auth_tenancy/services/authorization.py:53-93`).
4. Workspace-Fence aus `ApiKey.workspace_ids`; leer bedeutet historisch „kein Fence“ (`backend/auth_tenancy/models.py:153-160`).
5. Ziel-Workspace-Auflösung und fail-closed Read-Gate (`backend/mcp_server/workspace_scope.py:100-228`, `backend/mcp_server/tool_registry.py:1524-1656`).
6. Write-/Read-RBAC, Preset-Gate und Tool-Ausführung (`backend/mcp_server/tool_registry.py:1199-1278`).

Diese Basis ist grundsätzlich richtig. Die Befunde betreffen einzelne Lücken bzw. den Contract zwischen Client, Plugin und Server.

---

## 4. Inventar

### 4.1 Aktuelles Tool-Manifest

Quelle: `docs/agent-templates/tool-manifest.json:2-4`.

| Präfix | Tools | Write | Read |
|---|---:|---:|---:|
| `admin` | 3 | 2 | 1 |
| `adr` | 7 | 5 | 2 |
| `ai_derivation` | 6 | 6 | 0 |
| `architecture` | 9 | 7 | 2 |
| `artifact` | 2 | 0 | 2 |
| `attribute_catalog` | 8 | 5 | 3 |
| `attribute_definition` | 13 | 11 | 2 |
| `attribute_migration` | 6 | 3 | 3 |
| `audit` | 5 | 2 | 3 |
| `baseline` | 4 | 1 | 3 |
| `change_request` | 7 | 5 | 2 |
| `comment` | 3 | 2 | 1 |
| `context` | 4 | 1 | 3 |
| `diagram` | 6 | 4 | 2 |
| `events` | 2 | 1 | 1 |
| `glossary` | 7 | 5 | 2 |
| `goal` | 10 | 7 | 3 |
| `icd` | 4 | 2 | 2 |
| `interview` | 10 | 6 | 4 |
| `issue` | 7 | 5 | 2 |
| `link_type` | 5 | 3 | 2 |
| `main_goal` | 5 | 3 | 2 |
| `memory` | 6 | 2 | 4 |
| `needs` | 8 | 5 | 3 |
| `permissions` | 4 | 2 | 2 |
| `prompt_template` | 4 | 2 | 2 |
| `prompt_variable` | 4 | 2 | 2 |
| `requirement` | 11 | 8 | 3 |
| `requirement_bundle` | 3 | 0 | 3 |
| `review` | 4 | 3 | 1 |
| `risk` | 7 | 5 | 2 |
| `test` | 13 | 10 | 3 |
| `traceability` | 5 | 3 | 2 |
| `user` | 9 | 8 | 1 |
| `workspace` | 7 | 3 | 4 |
| **Summe** | **218** | **139** | **79** |

Toolset-Filter und kompakte Schemas sind in `backend/mcp_server/tool_registry.py:58-110,162-194` vorhanden; `tools/filter` teilt die Implementierung mit `tools/list` (`backend/mcp_server/protocol_handler.py:519-551`).

### 4.2 Agenten und Provider

- Drei aktive Provider: Claude, OpenCode, Gemini (`.meta-config/project.yaml:6-10`).
- 57 Rollen sind kanonisch registriert (`.meta-config/project.yaml:11-68`).
- Dateibestand:
  - `.claude/agents`: 59 Dateien = 57 generierte Rollen plus `.claude/agents/reqogniloom-operator.md` und `.claude/agents/se-consultant.md`.
  - `.gemini/agents`: 57 Dateien.
  - `.opencode/agents`: 57 Dateien.
- 56 der 57 generierten Claude-Agenten enthalten den alten Kontext „188 Tools; stdio“. `.claude/agents/reqogniloom-operator.md` enthält 143/26 plus stdio; `.claude/agents/se-consultant.md` ist separat und nicht im Rollenregister.

### 4.3 Fachrollen und Skills

| Rolle | Tools | Prozess-Skill | Rolle |
|---|---:|---|---|
| Requirements Architecture Manager | 31 | `vmodell-decomposition` | Requirements/Needs/AI-Derivation/Traceability |
| Test Engineer | 14 | `test-lifecycle` | Tests/TestRuns/Requirements |
| Risk Analyst | 15 | `risk-derivation` | Risks/Architecture/Diagram |
| Change Manager | 39 | `ccb-approval-and-baseline` | ADR/Issue/CR/Review/Baseline |
| Quality Auditor | 25 | `traceability-audit` | strikt read-only |

Belege: `docs/agent-templates/requirements-architecture-manager.md:7-39`, `docs/agent-templates/test-engineer.md:7-22`, `docs/agent-templates/risk-analyst.md:7-23`, `docs/agent-templates/change-manager.md:7-47`, `docs/agent-templates/quality-auditor.md:7-33`.

Sechs verteilte Skills liegen unter `dist/agent-skills/`:

1. `vmodell-decomposition`
2. `test-lifecycle`
3. `risk-derivation`
4. `ccb-approval-and-baseline`
5. `traceability-audit`
6. `interview-management`

Die Rollen-Whitelists werden gegen das Manifest und die Skill-Prose getestet (`docs/agent-templates/test_role_tools_exist_in_manifest.py:81-159`); `quality-auditor` muss read-only bleiben (`docs/agent-templates/test_role_tools_exist_in_manifest.py:96-101`).

### 4.4 Plugin-Katalog

`.agent-meta/config/plugin-catalog.yaml:1-418` enthält 10 Einträge:

| Plugin | Kind/Transport | Projektstatus | Tool-Governance |
|---|---|---|---|
| home-assistant | Remote SSE | aus | allow + block |
| influxdb | lokal stdio | aus | allow + block |
| viz-logger | repo-owned stdio | aus | allow |
| a2a-handoff | repo-owned stdio | aus | allow |
| honcho | Remote SSE | aus | allow + block; OpenCode-Skip |
| reqogniloom | Remote SSE | aus | 54 allow, 18 block |
| playwright | lokal stdio | an | allow + 4 block |
| graphify | CLI | an | CLI-Hooks |
| project-atlas | lokal stdio | an | allow leer |
| headroom | lokal stdio | aus | allow |

Aktivierung: `.meta-config/project.yaml:546-566`.

Wichtig: Der ReqogniLoom-Katalog kennt 54 allow- und 18 block-Tools, das Servermanifest jedoch 218. Das ist als bewusste Teilfreigabe interpretierbar, aber nicht als vollständige Toolklassifikation. Die 18 „blocked“-Tools werden in Agenttext injiziert, nicht in die Providerverbindung (`.agent-meta/scripts/lib/registry_query.py:177-192`, `.agent-meta/scripts/lib/mcp_provider_config.py:152-175`).

### 4.5 Verteilte Plugins

- Claude-Code-Plugin: `dist/plugins/claude-code/build_claude_plugin.py:27-38,47-124`.
  - 5 Fachrollen, 6 Skills, SSE-Verbindung, Toolnamen im Agent-Frontmatter.
- Antigravity-Plugin: `dist/plugins/antigravity/build_antigravity_plugin.py:18-22,25-73`.
  - Plugin-Metadaten, SSE-Verbindung, 6 Skills, keine Rollen.
- OpenCode-/Codex-Snippets:
  - `dist/opencode/build_opencode_package.py:33-60`
  - `dist/codex/build_codex_package.py:51-72`
- Versionsstände:
  - `VERSION:1` = `1.8.0-beta.15`
  - Claude-Plugin `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json:2-4`
  - Antigravity-Plugin `dist/plugins/antigravity/reqogniloom/plugin.json:2-4`
  - Hermes-TS `integrations/hermes-plugin/reqogniloom/package.json:2-4`
  - Hermes-Python `integrations/hermes-agent-plugin/plugin.yaml:1-3` = `0.1.0`

---

## 5. Request- und Event-Pfade

### 5.1 HTTP JSON-RPC

```text
Client
  → POST /mcp/
  → Ambient-Cookie-Reject + Rate-Limit
  → Batch-Preflight (Array wird abgewiesen)
  → ProtocolHandler
  → API-Key-Header
  → ToolRegistry
  → Ziel-Workspace / API-Key-Fence / Scope / RBAC / Preset
  → ToolGroup → ApplicationService → Persistence
  → direktes JSON-RPC-Ergebnis bzw. ToolResult-Fehler
```

Belege: `backend/mcp_server/views.py:247-344`, `backend/mcp_server/protocol_handler.py:447-632`, `backend/mcp_server/tool_registry.py:1166-1278`.

### 5.2 SSE

```text
GET /mcp/sse/
  → API-Key prüfen
  → session_id minten/resumen
  → API-Key verschlüsselt in Redis (8 h)
  → endpoint-Event
  → PubSub + 15-s-Keepalive
  → optionaler Replay ab Last-Event-ID (100 Events)

POST /mcp/messages/?session_id=...
  → Session-Fence/TTL
  → Session-Key entschlüsseln und intern als Header setzen
  → ThreadPool(max_workers=10), unbounded Queue
  → ProtocolHandler
  → Ergebnis in Redis-PubSub/Replay-Puffer
```

Belege: `backend/mcp_server/views.py:480-612,628-714`, `backend/mcp_server/sse_pubsub.py:13-23,74-164,193-264`.

### 5.3 Hermes

- Python-Agent-Plugin: Slash-Command → `ReqogniLoomClient` → REST `/api/v1/...`, 10-s-Timeout (`integrations/hermes-agent-plugin/reqogniloom_client.py:25-56,66-97`).
- Hermes-Desktop/TS: UI → `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts` → direkte Methode auf `POST /mcp/`, z. B. `interview.start` (`integrations/hermes-plugin/reqogniloom/src/mcpClient.ts:52-81,106-139`).
- Der TS-Client nutzt keine SSE-Session und sendet nur `X-API-Key`; Workspace/Scope muss daher aus Key-Claims und Tool-Parametern kommen.

### 5.4 Bluepencil

```text
React Loader → /bluepencil/latest/attach.js
             → same-origin /bluepencil/api/*
             → Nginx → bluepencil:8787
             → eine gemeinsame notes.json
```

Belege: `frontend/src/bluepencil/loader.ts:4-15,262-305`, `frontend/nginx.conf:85-99`, `deploy/docker-compose.yml:812-844`, `deploy/bluepencil/server.js:1678-1746`.

---

## 6. Detaillierte Findings

### Finding F-01 — `comment.resolve` umgeht den Ziel-Workspace-Fence

**Priorität:** P1  
**Regel:** AIS-04 (bypassbare Sicherheitslogik)  
**Origin:** unklar; AI-/Mensch-Anteil ohne Git-Historie nicht belegbar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `backend/mcp_server/workspace_scope.py:9-24` beschreibt genau das bekannte Anti-Muster: ohne auflösbaren Ziel-Workspace wird die tenant-weite Rollenunion verwendet.
- `backend/mcp_server/workspace_scope.py:173-176` hält ausdrücklich fest, dass `comment.resolve` mangels `ENTITY_SPECS`-Key nicht zielauflösbar ist und deshalb wie zuvor über die Rollenunion läuft.
- `backend/mcp_server/tool_registry.py:1524-1561` fällt bei fehlendem Target auf genau diesen tenant-weiten Kontext zurück.
- `backend/application/comment_service.py:151-173` prüft nur allgemeine Write-Berechtigung und lädt den Kommentar tenant-scoped; der Workspace des Artifacts wird nicht geprüft.
- `backend/application/models.py:233-253` zeigt, dass `Comment` nur `TenantScopedModel` ist; der Workspace ergibt sich indirekt über `artifact_id`.
- Der Read-Coverage-Ratchet klassifiziert nur Read-Tools (`backend/mcp_server/tests/test_mcp_workspace_scope.py:411-460`), nicht alle Write-Tools.

**Risiko**

Ein Benutzer mit Editor-Rolle in Workspace A und einem unrestringierten API-Key kann `comment.resolve` mit einer Kommentar-ID aus Workspace B desselben Tenants aufrufen. Weil die Rolle aus A in der tenant-weiten Union enthalten ist, passiert das Write-Gate. Der Kommentar wird anschließend in B als aufgelöst markiert. Ein workspace-fenced Key wird in diesem Fall korrekt abgewiesen, bleibt aber funktional unbenutzbar.

**Root Cause**

Die Target-Auflösung kennt nur Entity-Specs mit direkter Workspace-Zuordnung. `Comment` besitzt keine eigene `workspace_id`; der korrekte Pfad wäre `comment → artifact → workspace`.

**Gegenmaßnahme**

1. `comment` als read/write-fähige Workspace-Lookup-Entity ergänzen und auf `comment.artifact.workspace_id` auflösen.
2. `"comment.resolve": (("id", "comment"),)` in `_TOOL_TARGETS` registrieren.
3. Defense-in-depth im Service: Workspace des Artifacts laden und gegen `ctx.active_roles` bzw. einen explizit aufgelösten Zielkontext prüfen.
4. Den Coverage-Ratchet auf alle Write-Tools erweitern, die weder `workspace_id` erforderlich noch Instanz-/Tenant-Operation sind.

**Aufwand:** M (1–2 Tage inklusive Cross-Workspace-Tests).

**Alternativen**

- Nur Service-Check: schneller, aber dupliziert Mapping-Logik und schützt andere Dispatch-Pfade nicht.
- `Comment` um eigenes `workspace_id` ergänzen: migrationsstark und redundant, da es bereits über `Artifact` vererbt wird.

**Verifikation**

- Integrationstest: Editor nur in A, Kommentar in B, unrestringierter Key → `PERMISSION_DENIED` und kein Write.
- Positivtest: Editor in B → Erfolg.
- Fenced-Key-Test: Ziel B außerhalb des Fences → immer `PERMISSION_DENIED`, auch wenn Target-Auflösung ausfällt.

---

### Finding F-02 — API-Key-Defaults sind für AI-Agenten fail-open

**Priorität:** P1  
**Regel:** AIS-03 (insecure AI default)  
**Origin:** wahrscheinlich menschengeschriebener Backwards-Compatibility-Vertrag; nicht belegbar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `backend/auth_tenancy/models.py:72-90` definiert die Legacy-Aliasse; `write` bedeutet Admin-Tier.
- `backend/auth_tenancy/services/authorization.py:68-93` bestätigt ausdrücklich, dass `write` der **weiteste** Tier ist.
- `backend/auth_tenancy/models.py:153-160` setzt den Modelldefault ebenfalls auf `write`; leere `workspace_ids` bedeuten „alle Workspaces, in denen der Owner eine Rolle hat“, und `expires_at=None` bedeutet unbegrenzt.
- `backend/rest_api/api_key_views.py:285-317` übernimmt bei fehlendem Request-Feld `scope="write"` und `workspace_ids=[]`.
- `backend/auth_tenancy/services/authentication.py:561-571` wiederholt den Default auf Serviceebene.
- `backend/rest_api/tests/test_api_key_agent_fields.py:45-55` fixiert diese Defaults ausdrücklich.

**Risiko**

Ein Integrator erzeugt einen API-Key für Claude/Hermes und lässt die neuen Felder weg. Der Key erhält den Admin-Capability-Tier, keinen Workspace-Fence und keinen Ablauf. Die Rollenmatrix begrenzt zwar die effektiven Aktionen auf die Rollen des Owners; bei einem Tenant-Admin ist der Key jedoch maximal. Ein kompromittierter oder prompt-injizierter Agent erhält damit mehr Capabilities als für eine fachliche Schreibrolle nötig und potenziell dauerhaft.

**Root Cause**

Historische Kompatibilität: Legacy-`write` darf bestehende Keys nicht verändern. Dieselbe Default-Funktion wird aber auch für neu erzeugte, explizit als Agent gedachte Keys verwendet.

**Gegenmaßnahme**

1. Für `principal_type="agent"` verpflichtend verlangen: kanonischer Scope, nichtleere `workspace_ids`, `expires_at`.
2. Neuen REST-Default auf `author` setzen; `admin` nur explizit zulassen.
3. UI/CLI sollen bei Agent-Keys ein enges Key-Profil vorschlagen.
4. Bestehende unrestringierte, nicht abgelaufene Legacy-Keys inventarisieren und einen Rotations-Interim-Bericht erzeugen.
5. Keine bestehenden Keys still verändern; Kompatibilität über einen expliziten Migrations-/Reissue-Prozess erhalten.

**Aufwand:** M (2–3 Tage inklusive API-, UI- und Migrationskonzept).

**Alternativen**

- Nur eine Bestätigungswarnung: schwach, weil ein Fehlklick weiterhin den Admin-Default erzeugt.
- Nur Host-Allowlist: schützt den MCP-Client, nicht REST-/Direktaufrufe mit demselben Key.

**Verifikation**

- POST ohne `scope`/Fence/Expiry für User-Principal → `author` oder expliziter 400.
- POST `principal_type=agent` ohne Fence/Expiry → 400.
- Admin-Tier und Workspace-übergreifende Nutzung nur nach expliziter Angabe.
- Bestandskeys bleiben bis zur Rotation semantisch unverändert.

---

### Finding F-03 — Plugin-Workspace-Header sind dekorativ

**Priorität:** P2  
**Regel:** Integrations-/Auth-Check; Route zur `security-auditor`  
**Origin:** unklar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `.agent-meta/config/plugin-catalog.yaml:273-286` konfiguriert `X-Project-ID`, `X-User-ID` und `X-Workspace-ID` und erklärt alle fünf Variablen zu Secrets.
- `backend/mcp_server/views.py:176-190` liest ausschließlich `X-API-Key` und `Authorization`.
- `backend/auth_tenancy/services/authentication.py:545-556` leitet User, Tenant, Scope und Workspace-Fence ausschließlich aus der `ApiKey`-Datenbankzeile ab.
- Im gesamten `backend/`-Baum existiert keine Verarbeitung der drei deklarierten `X-*-ID`-Header.
- `.claude/settings.json:57-65` enthält dieselben Header, während die verteilten Claude-/Antigravity-Plugins korrekt nur `X-API-Key` setzen (`dist/plugins/claude-code/build_claude_plugin.py:72-86`).

**Risiko**

Ein Betreiber glaubt, `X-Workspace-ID` begrenze einen Key, während der Server nur den Key-Fence verwendet. Besonders bei neu erzeugten unrestringierten Keys entsteht falsche Sicherheit: Der Header ändert weder Tenant noch Rolle noch Ziel-Workspace.

**Root Cause**

Historische Connection-Metadaten wurden nicht gegen den aktuellen Auth-Contract bereinigt.

**Gegenmaßnahme**

- Die drei Header und Variablen aus Katalog und Provider-Beispielen entfernen.
- Dokumentieren: Der Key ist die einzige Identitäts-/Scope-Quelle; `workspace_id` im Tool-Parameter wählt nur das Ziel.
- Falls Kompatibilitätsheader benötigt werden, müssen sie serverseitig validiert und mit den Key-Claims verglichen werden; bei Widerspruch ist fail-closed abzulehnen.

**Aufwand:** S (0,5–1 Tag).

**Alternativen**

- Header als untrusted metadata ignorieren: sicher, aber irreführende Konfiguration entfernen.
- Header erzwingen: nicht ausreichend, da Clients sie frei setzen; nur als zusätzlichen Consistency-Check verwenden.

**Verifikation**

- Contract-Test: beliebige `X-Workspace-ID`-Werte ändern weder Fence noch Rollenauflösung.
- Generator-Snapshot enthält nur `Authorization`/`X-API-Key`.

---

### Finding F-04 — Single-Interview-Formalize ist nicht gegen Parallelaufrufe serialisiert

**Priorität:** P1  
**Regel:** Datenintegrität/Idempotenz; fachlich außerhalb OWASP  
**Origin:** AI-/menschgemischte Inkonsistenz nicht belegbar  
**Status:** Tatsache aus statischem Kontrollfluss; Laufzeitduplikat nicht ausgeführt  
**Confidence:** Hoch für Race, mittel für Häufigkeit

**Evidenz**

- `backend/application/interview_service.py:900-949` öffnet nur die äußere Transaktion und prüft `in_progress` ohne `select_for_update`.
- Der Single-Pfad `backend/application/interview_service.py:951-1147` erstellt oder aktualisiert Artefakte direkt; erst danach wird der Workflow abgeschlossen.
- Nur der Multi-Pfad sperrt die Session erneut: `backend/application/interview_service.py:1182-1201`.
- Der Kommentar dort nennt genau die verhinderten parallelen Doppel-Batches.
- Der Regressionstest ist ausdrücklich auf Multi beschränkt: `backend/application/tests/test_interview_multi_review_fixes.py:15-16,137-163`.
- Es gibt keinen MCP-Idempotency-Key oder Request-Deduplication im Handler/Registry-Pfad.

**Risiko**

Zwei parallele HTTP-Aufrufe oder ein Client-Retry nach Verbindungsabbruch können beide `in_progress` sehen und im Single-Pfad doppelte Artefakte erzeugen. Beide erzeugen Provenance-/Outbox-Ereignisse. Die nachgelagerte Workflow-Transition kann den zweiten Auftrag scheitern lassen, nachdem das Artefakt bereits erzeugt wurde; die Transaktion sollte dies zurückrollen, aber der Single-Pfad schützt die entscheidende Statusänderung nicht vor dem Check-then-Act.

**Root Cause**

Das M2-Hardening wurde nur für `_formalize_multi` umgesetzt. Der öffentliche Einstieg `formalize()` serialisiert beide Modi nicht.

**Gegenmaßnahme**

1. Session direkt zu Beginn von `formalize()` mit `select_for_update` laden und Status unter Lock prüfen.
2. Optional eine Unique-Constraint auf `InterviewSessionArtifact(session, artifact_id)` als zweite Datenintegritätsgrenze.
3. Für at-least-once MCP-Clients einen Idempotency-Key `(api_key_id, session_id, operation, request_id)` mit gespeichertem Resultat einführen.
4. Nach bereits abgeschlossenem Status das bestehende Resultat zurückgeben, sofern es eindeutig einem Abschluss entspricht.

**Aufwand:** M (1–2 Tage).

**Alternativen**

- Nur Unique-Constraint: verhindert doppelte Provenance, nicht doppelte Artefakte vor dem Join.
- Nur Idempotency-Key: schützt Retry, nicht zwei verschiedene Clients/Requests ohne Key.

**Verifikation**

- Postgres-Integrationstest mit zwei Threads/Connections auf dieselbe Single-Session.
- Erwartung: genau ein Artefakt, ein Abschluss, ein Outbox-Event; zweiter Aufruf erhält kontrollierten `already formalized`/Idempotency-Response.

---

### Finding F-05 — Bluepencil-Sidecar ist als Integrationsfläche absichtlich ungesichert

**Priorität:** P1 (bedingt: nur wenn aktiviert)  
**Regel:** Security-Integration; zuständig `security-auditor`  
**Origin:** wahrscheinlich menschengeschriebener Debug-/QS-Entwurf  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `deploy/bluepencil/README.md:1,10-20` kennzeichnet den Sidecar als Debug/QS-only und nennt fehlende AuthN, Tenant-Isolation und gemeinsamen JSON-Speicher ausdrücklich.
- `deploy/docker-compose.yml:813-844` bestätigt das Compose-Profil, den gemeinsamen Store und die fehlende Sicherheitsgrenze.
- `deploy/bluepencil/server.js:1678-1746` prüft Route/ Methode/ Read-only, aber weder Cookie noch API-Key, Tenant oder Workspace.
- `frontend/src/bluepencil/host.ts:48-57` sendet nur optional CSRF und hat als Default-Gate `true`; Identity/Route sind laut Kommentar Metadaten.
- `frontend/nginx.conf:85-99` proxyt den Pfad same-origin zum Sidecar.
- `frontend/src/bluepencil/loader.ts:277-305` überspringt bei fehlendem WebCrypto den Bundle-Integritätscheck und lädt weiter.

**Risiko**

Wer Compose-Profil **und** Frontend-Flag in einer geteilten QS-/LAN-Umgebung aktiviert, kann Notes aller Workspaces in einer Datei lesen/verändern. Ein Nutzer derselben Origin oder ein erreichbarer Compose-Client benötigt keine fachliche Berechtigung. QS-Daten können dadurch gegenseitig sichtbar werden.

**Root Cause**

Der Sidecar ist als lokaler Visualisierungs-/Messpfad gebaut und wurde nicht alsmandantenfähiges Backend entworfen.

**Gegenmaßnahme**

- Kurzfristig: CI-Regel, die Aktivierung in Shared-/Produktionsprofilen blockiert; eigener Loopback-Port/Netz-Policy und Hinweis, dass selbst QS-Daten sensibel sind.
- Produktionsreif: DRF-Store mit JWT/API-Key, TenantContext/RLS, RBAC, CSRF und Audit.
- Alternativ mindestens Shared-Token, Origin-Allowlist, Request-Größen-/Mengenlimits und getrennte Stores pro Umgebung; dies ersetzt keine Tenant-Isolation.

**Aufwand:** S für sichere Abschaltung/Guardrail, L für echten mandantenfähigen Store.

**Alternativen**

- Nur localhost-Binding: verhindert andere Hosts, nicht andere Nutzer desselben Frontend-Origins.
- Nur README-Warnung: unzureichend, wenn das Flag versehentlich aktiviert wird.

**Verifikation**

- Negativtest: beide Flags gesetzt, Aufruf ohne Auth → 401/403; Cross-Workspace-Notiz nicht sichtbar.
- CI-Integrationstest verhindert `--profile bluepencil` in Release- und Shared-QS-Compose-Dateien.

---

### Finding F-06 — Öffentlicher MCP-Quickstart ist strukturell nicht ausführbar

**Priorität:** P1  
**Regel:** AIS-05 (nicht existierende Endpunkte/Phantom-API)  
**Origin:** AI-/menschgenerierter Dokumentationsdrift nicht belegbar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `README.md:1052-1073` listet stdio und erwartet, dass `GET /mcp/` `["http","sse","stdio"]` zurückgibt.
- Tatsächlich liefert der Server `["http","sse"]` (`backend/mcp_server/views.py:405-431`, Test `backend/mcp_server/tests/test_server_info.py:29-47`).
- `README.md:1154-1188` postet an `/mcp/stdio/`; diese Route existiert nicht (`backend/mcp_server/urls.py:18-25`).
- `README.md:391-410` leitet einen einseitigen SSE-Stream mit `curl -N` als stdio-Bridge an Claude Desktop;/stdin des Servers erhält dadurch keine Requests.
- `README.md:461-465` liest den API-Key aus `.key`; die View antwortet mit `plaintext` (`backend/rest_api/api_key_views.py:355-364`).
- `README.md:1121-1129` liest `.access`; der Loginvertrag liefert optional `token` und kennzeichnet es als deprecated (`backend/rest_api/auth_views.py:180-205,234-256`).
- `README.md:480-483` nennt außerdem einen veralteten Servernamen und eine alte Version.
- Der grobe Systemaudit vom 2026-09-02 dokumentierte stdio-/Port-/Bridge-Defekte bereits (`docs/SYSTEMAUDIT_2026-09-02_GROB.md:361-373`), die im aktuellen README weiterhin vorhanden sind.

**Risiko**

Ein neuer Benutzer oder AI-Agent erzeugt nach dem Quickstart einen leeren Key, ruft nicht vorhandene Routen auf oder erwartet stdio-Support. Das offiziell dokumentierte Onboarding ist damit kein verlässlicher Installations- oder Agentenvertrag.

**Root Cause**

Manuell gepflegte Dokumentation ohne CI-Smoke-Test gegen Serverinfo, OpenAPI-Schema und reale Client-Konfiguration.

**Gegenmaßnahme**

1. Nicht implementierte stdio-Beispiele entfernen oder bis zu einem echten Entrypoint deaktivieren.
2. Claude Desktop auf einen tatsächlich unterstützten HTTP/SSE-Client bzw. offizielles STDIO-Bridge-Tool verweisen; keine `curl -N`-Einweg-Bridge.
3. Key-Feld auf `plaintext` und Login-Feld auf `token` korrigieren; deprecated Token-Hinweis übernehmen.
4. README-Fragmente aus OpenAPI, Tool-Manifest und `/mcp/`-Discovery generieren.
5. Einen CI-Smoke-Test ergänzen, der mindestens `GET /mcp/`, Key-Erstellung, `tools/list` und einen read-only Tool-Call gegen einen frischen Stack ausführt.

**Aufwand:** M (1–2 Tage).

**Alternativen**

- Manuell korrigieren: schneller, aber kein dauerhafter Drift-Schutz.
- README-MCP-Abschnitt als experimentell markieren: reduziert Erwartungen, ersetzt aber keine korrekten Client-Snippets.

**Verifikation**

- Jeder README-Befehl wird in einem sauberen CI-Container ohne manuelle Korrektur ausgeführt.
- Negative Route- und Feldnamen-Drift wird durch generierte Artefakte verhindert.

---

### Finding F-07 — SSE-Message-Pool und LLM-Timeouts können Ressourcen aufbauen

**Priorität:** P2  
**Regel:** Resilience/Verfügbarkeit; teilweise `sre-engineer`  
**Origin:** unklar  
**Status:** Code-Tatsache; Runtime-Auswirkung plausibel, nicht belastet  
**Confidence:** Hoch für Mechanik, mittel für Produktionsauswirkung

**Evidenz**

- `backend/mcp_server/views.py:148-156` begrenzt zehn Worker, verwendet aber die Standard-`ThreadPoolExecutor`-Queue ohne Capacity.
- `backend/mcp_server/views.py:579-612` nimmt jede gültige Session-Nachricht per `.submit()` an und antwortet sofort 202; es gibt weder Queue-Limit noch Deadline.
- `backend/llm_adapter/router.py:406-438` erzeugt für jeden synchronen Aufruf einen neuen Ein-Thread-Pool. Nach `future.result(timeout=...)` wird `cancel()` auf einen bereits laufenden Python-Thread nur angefordert und `shutdown(wait=False)` lässt den Worker weiterlaufen.
- Workspace-weite LLM-Aufrufe dürfen 180 Sekunden laufen (`backend/llm_adapter/timeouts.py:29-51`), normale 25 Sekunden.
- Rate-Limiting existiert, begrenzt aber nicht die.queue- oder Thread-Lebensdauer (`backend/mcp_server/views.py:499-507`).

**Risiko**

Ein Burst langsamer oder nicht kooperierender Provider-Aufrufe füllt die unbounded Queue und kann parallel verwaiste Router-Threads aufbauen. SSE-Clients erhalten früh 202, während Arbeit unbegrenzt wartet; Memory, Threads und queued Request-Payloads steigen. Das ist ein Availability-/Cost-Risiko bei AI-Integrationen.

**Root Cause**

„Bounded worker pool“ wurde mit „bounded work“ verwechselt; Timeouts werden am Future, nicht an der Provider-I/O-Grenze durchgesetzt.

**Gegenmaßnahme**

- Bounded Queue oder `Semaphore`; bei voller Kapazität deterministisch 429/503 mit `Retry-After`.
- Provider-Calls mit gemeinsamem, begrenztem Executor und echtem HTTP-Client-Timeout ausführen.
- Lang laufende AI-Tools als Celery-Tasks/async Jobs behandeln; SSE liefert nur Task-Status.
- Queue-Tiefe, Wartezeit, Laufzeit, Timeouts, Threadzahl und Abbruchquote als Metriken ausgeben.
- Kein eigener Thread pro LLM-Aufruf; Cancellation nur als Optimierung, nicht als I/O-Terminierung.

**Aufwand:** M (2–3 Tage).

**Alternativen**

- Nur Queue-Cap: verhindert Memory-Wachstum, nicht verwaiste Provider-Threads.
- Nur Timeout-Erhöhung/Reduktion: verschiebt das Problem und erhöht Latenz.

**Verifikation**

- Loadtest mit 100/1000 langsamen Tool-Calls: Queue bleibt begrenzt, Server bleibt gesund, Clients erhalten deterministisches Backpressure-Signal.
- Threadcount bleibt während wiederholter Timeouts innerhalb eines festen Grenzwerts.

---

### Finding F-08 — Batch-Verhalten ist zwischen HTTP und SSE inkonsistent

**Priorität:** P3  
**Regel:** Protokoll-/Fehlervertrag  
**Origin:** unklar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `backend/mcp_server/views.py:281-304` lehnt JSON-Array-Batches auf `/mcp/` sauber mit 400 ab.
- `backend/mcp_server/views.py:480-612` validiert den Body des Message-Endpunkts nicht similarly; ein Array wird in `_process` eingereiht.
- `backend/mcp_server/protocol_handler.py:447-455` ruft auf dem Array `.get()` auf; der äußere `_process`-Catch publiziert `INTERNAL_ERROR` statt `INVALID_REQUEST`.
- README deklariert Batch-Unterstützung nicht als Feature und direktes HTTP lehnt sie explizit ab.

**Risiko**

Ein MCP-Client, der die vom SSE-Endpoint gelieferte Message-URL nutzt und Batch-JSON sendet, erhält erst 202 und danach einen generischen Internal Error mit `id=null`. Das erschwert Retry-Klassifikation und verletzt die Transportkonsistenz.

**Root Cause**

Preflight-Validierung wurde nur im synchronen HTTP-View implementiert.

**Gegenmaßnahme**

- Gemeinsame `parse_and_validate_json_object(body)`-Funktion vor Redis-Queue und im direkten HTTP-View verwenden.
- Array/ungültiges JSON vor 202 ablehnen; Fehler-ID, sofern sicher extrahierbar, erhalten.
- Optional Batch-Unterstützung als eigener Vertrag implementieren; nicht implizit.

**Aufwand:** S (<0,5 Tag).

**Alternativen**

- Dokumentation „kein Batch“ reicht nicht, wenn der SSE-Pfad einen Internal Error erzeugt.
- Arrays generell akzeptieren wäre ein neuer, ungetesteter MCP-Vertrag.

**Verifikation**

- Parametrisierter Test für `/mcp/` und `/mcp/messages/`: gleiches Array ergibt vor Queueing 400 `INVALID_REQUEST`.

---

### Finding F-09 — Agent-Kontexte enthalten Phantom-stdio und drei verschiedene Toolstände

**Priorität:** P2  
**Regel:** AIS-05  
**Origin:** KI-generierter Projektkontext, konkrete Generationsprovenienz nicht vorhanden  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- Kanonisches Manifest: 218 Tools/35 Präfixe (`docs/agent-templates/tool-manifest.json:2-4`).
- Root-Kontext: 31 Präfixe/215 Tools (`AGENTS.md:8,30`, `.meta-config/project.yaml:97-103`).
- 56 generierte Claude-Agenten enthalten 188 Tools und stdio; repräsentativ `.claude/agents/accessibility-specialist.md:97,115`.
- `systemagents/reqogniloom-operator.md:48-52` und `.claude/agents/reqogniloom-operator.md:48-52` nennen 26 Präfixe/143 Tools/stdio.
- `README.md:1050,1191` nennt sogar 25 Präfixe.
- Server und Test erklären stdio ausdrücklich als nicht geroutet (`backend/mcp_server/views.py:423-430`, `backend/mcp_server/tests/test_server_info.py:16-19`).
- `docs/REQUIREMENTS.md:182` markiert REQ-131 als Done, verlangt aber gleichzeitig „genau implementierte Transports“ und nennt danach stdio.

**Risiko**

Agenten treffen Tool- und Transportentscheidungen auf Basis falscher Capabilities. Das erzeugt nicht vorhandene stdio-Konfigurationen, falsche Endpoint-Wahlen und unnötige Vollcontext-Kosten. Die Phantomangabe ist außerdem in Requirements als Done markiert, sodass ein Traceability-Check die Diskrepanz nicht erkennt.

**Root Cause**

Projektkontext und Agentdateien wurden nicht aus dem Manifest/Discovery-Endpoint generiert; es gibt keinen semantischen Drift-Gate für Toolzahl, Präfixe oder Transport.

**Gegenmaßnahme**

- Toolzahl/Präfixe aus `docs/agent-templates/tool-manifest.json` generieren.
- stdio aus allen Agent-/Root-Kontexten entfernen, bis ein realer Entrypoint existiert.
- `reqogniloom-operator` entweder registrieren und aus Manifest synchronisieren oder explizit als lokale Legacy-Datei markieren.
- CI-Test: Kein generierter Agent darf eine andere `tool_count`/Präfixzahl oder stdio als Discovery behaupten.
- REQ-131 auf die tatsächliche Discovery korrigieren und erneut referenzieren.

**Aufwand:** M (1 Tag Synchronisierung plus Tests).

**Alternativen**

- Einen deutenden Hinweis „Zahlen können veraltet sein“ reduziert nur die Fehlalarme, nicht die Phantom-Endpoint-Anweisung.
- stdio ohne Server zu bewerben ist keine akzeptable Alternative.

**Verifikation**

- Generierter Prompt wird gegen Manifest und `GET /mcp/` geprüft.
- Kein `stdio` in Runtime-Kontexten, solange `backend/mcp_server/urls.py` keinen Entrypoint besitzt.

---

### Finding F-10 — Plugin-Allow/Blocklisten sind keine Security Boundary und Providerflächen divergieren

**Priorität:** P2  
**Regel:** AIS-04  
**Origin:** Framework-/AI-Konfiguration  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `.agent-meta/config/plugin-catalog.yaml:243-261` markiert 18 ReqogniLoom-Tools als „blocked“.
- `.agent-meta/scripts/lib/registry_query.py:177-192` rendert diese nur zu einer Markdown-Guardrail.
- `.agent-meta/scripts/lib/mcp_provider_config.py:152-175` schreibt in die Connection ausschließlich `type/url/command/args/env/headers`, nicht `allowedTools`/`disabledTools`.
- Rollen-Fronmatter kann am Host eine reale Toolbindung erzeugen (`dist/plugins/claude-code/build_claude_plugin.py:99-115`), aber Main-Chat-/Providerkonfigurationen ohne passende Rollenbindung erhalten den vollem Server-Toolbestand.
- Kanonisch sind ReqogniLoom/Honcho deaktiviert (`.meta-config/project.yaml:553-558`); `.claude/settings.json:56-83` enthält beide zusätzlich als `mcpServers`.
- Gemini enthält exakt Playwright/ProjectAtlas (`.gemini/settings.json:5-21`); OpenCode enthält Playwright, ProjectAtlas und ein nicht im Katalog geführtes Firecrawl (`opencode.json:16-47`).

**Risiko**

Eine Prompt-Injection kann einen Agenten dazu verleiten, ein als „absolut verboten“ markiertes Tool aufzurufen. Die serverseitige Key-Scope/RBAC-Grenze bleibt wirksam, aber die Plugin-Governance erzeugt falsche Sicherheitsgewissheit. Zusätzlich erschwert die doppelte Providerkonfiguration Audits: Je nach Host können verschiedene MCP-Server und Toolmengen sichtbar sein.

**Root Cause**

Prompt-, Host- und Server-Authorization werden als eine Sicherheitsgrenze behandelt. Providerkonfigurationen dürfen manuelle Einträge erhalten, während ein kanonischer Katalog existiert.

**Gegenmaßnahme**

1. `blocked` als „Agent Guidance“ markieren, nicht als Security Boundary.
2. Für jede distributierte Rolle ausschließlich einen vorab scoped API-Key plus Host-Tool-Allowlist verwenden.
3. Provider-native `enabledTools`/`disabledTools` nur ergänzen, wenn der Host sie tatsächlich erzwingt; durch Integrationstest verifizieren.
4. Duale MCP-Konfigurationsquellen beseitigen oder als getrennte Scopes (`managed` vs. `local/manual`) inventarisieren.
5. CI vergleicht committed Provider-Server mit `.meta-config/project.yaml`-Aktivierung und meldet manuelle Abweichungen explizit.

**Aufwand:** M (1–2 Tage).

**Alternativen**

- Nur längere Prompt-Verbote: AIS-04, nicht robust gegen Prompt-Injection.
- Nur API-Key-Scope: notwendige Servergrenze, ersetzt aber nicht die lokale Tool-Sichtbarkeit/UX.

**Verifikation**

- Adversarialer Prompt versucht ein blockiertes Tool; Provider/Key verweigert die Ausführung.
- Snapshot der pro Provider sichtbaren Server/Tools stimmt mit einer genehmigten Matrix überein.

---

### Finding F-11 — Hermes-Desktop-Requests haben keine Deadline

**Priorität:** P2  
**Regel:** Timeout/Integration  
**Origin:** TypeScript-Client, Herkunft nicht belegbar  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- `integrations/hermes-plugin/reqogniloom/src/mcpClient.ts:52-70` ruft `network.fetch` ohne `AbortSignal` oder Timeout auf.
- `integrations/hermes-plugin/reqogniloom/src/api.ts:107-130` reicht REST-Requests ebenfalls ohne Deadline durch.
- `integrations/hermes-plugin/reqogniloom/src/state.ts:102-123,189-198` setzt `connecting`/`interviewBusy` vor dem Aufruf; ein hängendes Promise wird nie durch einen eigenen Timer beendet.
- Der separate Python-Agent-Client setzt dagegen `urlopen(..., timeout=10)` (`integrations/hermes-agent-plugin/reqogniloom_client.py:36-50`).

**Risiko**

Ein nicht antwortender oder halb offener Backend-Socket lässt den Hermes-Panel dauerhaft im Verbindungs-/Busy-Zustand. Nutzer können den Zustand nicht normal zurücksetzen; bei mehreren Panels/Versuchen sammeln sich hängende UI-Operationen.

**Root Cause**

Der TS-Adapter normalisiert zwei unsichere `fetch`-Rückgabeformen, hat aber keinen zentralen Request-Governor.

**Gegenmaßnahme**

- `AbortSignal.timeout(...)` je Read/Write-Aufruf, mit verständlichem Timeout-Fehler.
- `finally`-Pfad, der `connecting`/`interviewBusy` immer zurücksetzt.
- REST 10–30 s, MCP 30 s, optional lange Formalize-Aufrufe als asynchroner Job.
- Python- und TS-Timeout-/Fehlerverhalten in gemeinsame Contract-Tests überführen.

**Aufwand:** S (0,5–1 Tag).

**Alternativen**

- Nur UI-Spinner beenden: Blendet das Problem, ohne Netzwerkressourcen zu beenden.
- Globales sehr langes Timeout: verschlechtert UX und Diagnose.

**Verifikation**

- Test mit `fetch`, das nie auflöst: UI kehrt nach Timeout in den Ausgangszustand zurück und zeigt einen stabilen Fehlercode.

---

### Finding F-12 — Hermes-Zielverträge sind ungeklärt und CI priorisiert nur den TS-Pfad

**Priorität:** P2  
**Regel:** Phantom-Integrationsrisiko, noch nicht als nicht existent bestätigt  
**Origin:** KI-übernommene SDK-Typen ausdrücklich unverified  
**Status:** Tatsache: Governance-Lücke; Hypothese: einer der beiden Hostverträge ist nicht installierbar  
**Confidence:** Hoch für Lücke, mittel für konkrete Hostzuordnung

**Evidenz**

- `integrations/hermes-plugin/reqogniloom/src/hermes-sdk-types.ts:2-16` bezeichnet den lokalen SDK-Vertrag als „unverified“, nicht publiziert und nicht live geladen.
- `integrations/hermes-plugin/reqogniloom/hermes-plugin.json:1-47` verwendet ein VS-Code-artiges Manifest.
- `integrations/hermes-agent-plugin/README.md:7-23` nennt beide Varianten ungetestet und vermutet zunächst, der TS-Pfad sei dead code.
- Der aktuelle Grobaudit korrigiert diese Vermutung: Python-Agent-Plugin und Desktop-TS können komplementäre Hermes-Flächen sein; live verifiziert wurde keine (`docs/SYSTEMAUDIT_2026-09-02_GROB.md:333-359`).
- Der CI-Job `hermes-plugin-test` installiert/typecheckt/testet/built ausschließlich `integrations/hermes-plugin/reqogniloom` (`.github/workflows/ci.yml:284-319`).
- Für `integrations/hermes-agent-plugin/` existieren Tests, die im Workflow nicht referenziert werden (`integrations/hermes-agent-plugin/tests/test_reqogniloom_client.py`, `integrations/hermes-agent-plugin/tests/test_slash_command.py`, `integrations/hermes-agent-plugin/tests/test_plugin_api.py`).

**Risiko**

Das Projekt kann nicht belastbar sagen, welche Hermes-Oberfläche unterstützt wird. Ein falsches Manifest, falscher Installationspfad oder falscher SDK-Adapter führt zum Nichtladen des Plugins. Gleichzeitig signalisiert die grüne TS-CI fälschlich Integrationsreife, obwohl der neuere Python-Agent-Pfad ungeprüft ist.

**Root Cause**

Es fehlt eine verbindliche Hermes-Supported-Surfaces-Matrix mit realer Hostversion, Manifestform, Installationspfad und Smoke-Test.

**Gegenmaßnahme**

1. Produktentscheidung: Hermes Agent Plugin (Python), Hermes Desktop Plugin (TS) oder beide.
2. Je unterstütztem Surface authoritative Manifest, SDK-Version, Installationspfad und最小 Smoke-Test definieren.
3. CI: beide Codebasen mindestens kompilieren/unit-testen; Live-Smoke nightly oder release-gebunden.
4. Falsches/überflüssiges Manifest entfernen oder explizit als unsupported markieren.
5. Versionsstrategie zwischen `0.1.0` und Produktversion vereinheitlichen.

**Aufwand:** M (1–3 Tage ohne echte Hermes-Hostkomplexität).

**Alternativen**

- Nur Python-Agent-Pfad: weniger Oberfläche, aber Desktop-Panel entfällt.
- Nur TS-Pfad: verliert Slash-Command/Dashboard der Hermes-Agent-Erweiterung.

**Verifikation**

- Zwei dokumentierte Hermes-Versionen; Plugin lädt, registriert UI/Command, führt einen read-only und einen kontrollierten write-only Interview-Call aus.

---

### Finding F-13 — Versions- und Provenienzmetadaten laufen auseinander

**Priorität:** P3  
**Regel:** Contract-/Release Governance  
**Origin:** verteilte Literale  
**Status:** Tatsache  
**Confidence:** Hoch

**Evidenz**

- Produktversion: `VERSION:1` = `1.8.0-beta.15`.
- `GET /mcp/` und `initialize` melden weiterhin `1.0.0` (`backend/mcp_server/views.py:405-432`, `backend/mcp_server/protocol_handler.py:478-488`).
- Tool-Manifest sagt `generated_from: reqogniloom==unknown`, obwohl der Exportcode im Host die `VERSION` bevorzugt (`docs/agent-templates/tool-manifest.json:2`, `backend/mcp_server/management/commands/export_tool_manifest.py:45-53,81-85`).
- Der Drift-Test vergleicht den Toolvertrag, nicht `generated_from` (`backend/mcp_server/tests/test_tool_manifest_drift.py:120-157`).
- Claude-/Antigravity-/TS-Hermes-Pakete tragen `1.8.0-beta.15`; das Python-Hermes-Plugin trägt `0.1.0`.

**Risiko**

Support kann Client, Server und Plugin nicht eindeutig korrelieren. Ein Incident Report kann nicht zuverlässig sagen, welches Toolmanifest oder welche MCP-Serverversion lief. `unknown` verhindert automatische Release-Provenienz.

**Root Cause**

Mehrere unabhängige Versionsliterale und Container-Export ohne erzwungene `APP_VERSION`.

**Gegenmaßnahme**

- Eine Runtime-Version aus `VERSION`/Package-Metadaten laden und in Discovery sowie `serverInfo` verwenden.
- Im Manifest zusätzlich Produktversion, Commit-SHA und Buildzeitpunkt speichern.
- CI prüft alle verteilten Pluginversionen und `generated_from` gegen die Release-Version.

**Aufwand:** S (0,5–1 Tag).

**Alternativen**

- Nur SemVer-Text synchronisieren: löst Provenienz und Driftursprung nicht vollständig.

**Verifikation**

- `/mcp/`, `initialize`, Tool-Manifest, Claude-/Antigravity-/Hermes-Artefakte melden dieselbe Release-Version; `generated_from` ist nie `unknown` in CI.

---

## 7. Bereits vorhandene positive Kontrollen

| Kontrolle | Evidenz | Bewertung |
|---|---|---|
| Vollständiger Manifest-Drift | `backend/mcp_server/tests/test_tool_manifest_drift.py:83-157` | vergleicht Namen, Write-Flag, Prefix, Description, Schema und Count |
| Qualitätsauditor read-only | `docs/agent-templates/test_role_tools_exist_in_manifest.py:96-101` | sinnvoller Rollen-Gate |
| Rollen-Tools ↔ Skills | `docs/agent-templates/test_role_tools_exist_in_manifest.py:104-159` | verhindert undokumentierte Whitelist-Erweiterungen |
| Read-Workspace-Ratchet | `backend/mcp_server/tests/test_mcp_workspace_scope.py:411-522` | gut; muss auf Write-Tools erweitert werden |
| Fail-closed Write-Klassifikation | `backend/mcp_server/tool_registry.py:380-438` | unbekannte Tools werden wie Write behandelt |
| Key-Scope-Gate | `backend/mcp_server/tool_registry.py:1209-1250` | unabhängig von Rollen-Exemptions |
| API-Key-Hashing/Revoke/Expiry | `backend/auth_tenancy/services/authentication.py:482-557` | korrekt umgesetzt |
| Kein Query-Key-Fallback | `backend/mcp_server/views.py:176-190` | schützt Logs/Proxy |
| SSE-Keyverschlüsselung | `backend/mcp_server/sse_pubsub.py:74-131` | Fernet in Redis, konstantes Binding-Compare |
| SSE-Replay | `backend/mcp_server/sse_pubsub.py:133-191,193-264` | 100 Events, 8 h, Session-Fence |
| Bluepencil standardmäßig aus | `deploy/docker-compose.yml:813-844`, `frontend/src/bluepencil/loader.ts:262-269` | reduziert Risiko, ersetzt aber keine Abschaltung in Shared QS |
| CI für Manifest/Templates | `.github/workflows/ci.yml:50-52,236-253` | vorhanden; deckt semantischen Prompt-/Providerdrift noch nicht ab |

---

## 8. Historischer Abgleich und Widersprüche

1. `docs/se/reports/deep_audit/McpServerSystem_DeepAudit.md` ist ein autogenerierter **Test-Coverage-Bericht** (2.138 Zeilen), keine aktuelle Architektur- oder Toolinventarquelle. Er wurde nicht als Wahrheitsquelle verwendet.
2. `docs/archive/audits/SYSTEMAUDIT_2026-08-27.md:190,216` erkannte stdio bereits als Adapter ohne Runtime-Entrypoint. Der Befund ist 2026 weiterhin offen.
3. `docs/SYSTEMAUDIT_2026-09-02_GROB.md:361-373` dokumentierte die nicht funktionierende stdio-/curl-Brücke und Port-/Config-Drift. Mehrere aktuelle README-Zeilen zeigen, dass diese Befunde nicht integriert wurden.
4. Die Aussage im Python-Hermes-README, der TS-Pfad sei sicher tot, ist durch den aktuellen Grobaudit nicht bestätigt. Deshalb wird F-12 als ungeklärter Dualvertrag, nicht als bewiesenes Phantom-Plugin formuliert.

---

## 9. AI-spezifische Sicherheitsklassifikation

| AIS-Regel | Anzahl | Zuordnung |
|---|---:|---|
| AIS-01 Halluzinierte Dependencies | 0 | keine bestätigte nicht existierende Package-Referenz |
| AIS-02 Fabriezierte IAM-Aktionen | 0 | kein Cloud-IAM im Scope |
| AIS-03 Insecure AI Defaults | 1 | F-02 |
| AIS-04 Brittle/Bypassbare Logik | 2 | F-01, F-10 |
| AIS-05 Phantom-Endpunkte/APIs | 2 eindeutige Phantomflächen | stdio-Transport; `/mcp/stdio/` |
| AIS-06 Leaked Training Data/Secrets | 0 | keine bestätigten Literal-Credentials im Scope; Demo-Fixtures ausgeschlossen |

Zusätzliche Verteilung:

- **Default Security:** 1
- **Insecure Integration:** 2 (F-03, F-05)
- **Unvalidated Prompt Integration:** 1 (F-10)

---

## 10. Priorisierter Maßnahmenplan

### Sofort / vor Release

1. **F-01:** `comment.resolve` workspace-scopen und Write-Ratchet erweitern.
2. **F-02:** Agent-Key-Profil fail-closed machen; bestehende Keys rotieren.
3. **F-04:** Single-Interview-Formalize serialisieren/idempotent machen.
4. **F-06:** Official Quickstart reparieren und executable CI-Smoke-Test ergänzen.
5. **F-05:** Bluepencil in Shared-/Produktionsumgebungen technisch blockieren.

### Danach

6. **F-09/F-13:** Agentkontext, Toolzahlen, Transport und Versionen aus einem Vertrag generieren.
7. **F-10:** Prompt-Allow/Blocklisten ehrlich als Guidance kennzeichnen; scoped Keys/Host-Allowlists erzwingen.
8. **F-07:** SSE-/LLM-Backpressure und echte Provider-Timeouts.
9. **F-12:** Hermes-Surface-Matrix und Live-Smoke für beide möglichen Targets.
10. **F-03/F-08/F-11:** Header-, Batch- und Timeout-Contracts bereinigen.

---

## 11. Abschlussstatus

STATUS: done
RESULT: Der statische Tiefenaudit ist abgeschlossen; 13 verifizierte Befunde (0 P0, 5 P1, 6 P2, 2 P3) sind mit Evidenz, Risiko, Root Cause, Gegenmaßnahme und Verifikationsplan dokumentiert. Nächster Schritt ist die Behebung der vier P1-Daten-/Sicherheitsbefunde und des fehlerhaften offiziellen Quickstarts.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/02-agents-plugins-mcp.md
