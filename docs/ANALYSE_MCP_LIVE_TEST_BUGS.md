# Analyse: MCP-Server Live-Funktionstest — Bugs & Findings

> Status: **Analyse — noch nicht umgesetzt.** Dieses Dokument fasst die Ergebnisse eines
> pragmatischen Live-Funktionstests aller MCP-Server-Endpoints gegen den laufenden
> Docker-Stack zusammen. Keiner der beschriebenen Bugs wurde im Rahmen dieses Tests behoben.
>
> Datum: 2026-07-20
> Kontext: JSON-RPC-2.0-Requests (`initialize`, `tools/list`, `tools/call`) gegen
> `http://localhost:8000/mcp/`, Auth via `rf_*`-API-Key (Demo-User `admin`). Getestet:
> alle 18 in `backend/mcp_server/tool_registry.py` registrierten Tool-Präfixe
> (72 Tools laut `tools/list`), ca. 30 Live-Requests.

---

## Ground Truth: Tool-Gruppen-Registrierung

`backend/mcp_server/tool_registry.py::_ensure_groups()` registriert **18 Präfixe** auf
**16 ToolGroup-Instanzen** (13 Klassen; `traceability`/`artifact` teilen sich eine
`CrossCuttingToolGroup`-Instanz, `audit`/`events` eine `AuditToolGroup`-Instanz). Das weicht
von „11 Tool-Gruppen" in `CLAUDE.md` ab — die tatsächliche Registrierung wurde hier als
Ground Truth verwendet, `CLAUDE.md` ggf. nachziehen.

Status je Präfix (alle 18 getestet): 14 fehlerfrei (`requirement.get/query`, `needs.read`,
`architecture.get/query`, `test.get/query`, `traceability.query`, `artifact.search`,
`workspace.get_context`, `permissions.list/check`, `admin.backup_list`, `audit.query`,
`events.dlq_list`, `user.list`, `glossary.read`, `prompt_template.get`,
`ai_derivation.derive_requirements_from_need`), 4 mit reproduzierbaren Bugs
(`adr`, `risk`, `issue`, `artifact.get_tree`, `requirement.decompose`/`derive`).

---

## 1. `adr.read` / `risk.read` → HTTP 500, unhandled crash

**Schweregrad:** Hoch (Crash statt sauberem JSON-RPC-Fehler)

**Repro:**
```
tools/call adr.read {"id": "<existing adr id>"}
→ HTTP 500  {"error_code":"INTERNAL_ERROR","message":"Internal server error."}
```
Backend-Log: `TypeError: Object of type datetime is not JSON serializable`.

**Root Cause:**
- `GenericCrudToolGroup._to_dict()` (`backend/mcp_server/tools/generic.py:108-118`)
  stringifiziert `uuid.UUID`-Felder, aber **keine** `datetime`-Felder (`created_at`,
  `updated_at` auf ADR/Risk sind rohe `datetime`-Objekte im `__dict__`).
- `_handle_read` gibt daraufhin einen **erfolgreichen** `ToolResult.ok(...)` zurück — der
  Crash passiert erst zwei Layer höher, beim Response-Serialisieren in
  `backend/mcp_server/protocol_handler.py:504`
  (`json.dumps(result.data, indent=2)`, kein `default=str`-Fallback, kein Try/Except um
  diese Zeile).
- Betrifft vermutlich auch `adr.create/update` und `risk.create/update` (gleicher
  `_to_dict`-Pfad) — nicht separat verifiziert.

**Fix-Optionen:**
1. `_to_dict()` um `datetime`/`date`/`Decimal`-Handling erweitern (analog zum bestehenden
   UUID-Fall).
2. Zusätzlich als Sicherheitsnetz: `json.dumps(..., default=str)` in
   `protocol_handler.py:504`, damit ein einzelner nicht-serialisierbarer Wert nie den
   ganzen Request mit einem unhandled 500 crasht.

---

## 2. `artifact.get_tree` faktisch unbenutzbar

**Schweregrad:** Hoch (Kernfeature nicht diskoverable)

**Repro:**
```
architecture.get / artifact.search liefern "id": "3fa18e04-..." (ArchitectureElement.id)
tools/call artifact.get_tree {"root_id": "3fa18e04-...", "workspace_id": "..."}
→ isError: "Artifact 3fa18e04-... not found in workspace ..."
```

**Root Cause:**
- `root_id` referenziert intern `pl_artifact.id` (generisches `Artifact`-Model,
  `backend/persistence/models.py:553-605`), nicht die PK der Fachentität.
- `ArchitectureElement` (und `Requirement`, `StakeholderNeed`, `TestCase`, `Adr`, `Risk`,
  `Issue`, `GlossaryTerm`) haben eine **eigene** PK `id` plus eine separate FK
  `artifact_id` (bzw. `artifact` OneToOneField) auf die generische `Artifact`-Tabelle.
  REST- und MCP-Responses exponieren durchgängig nur die Entitäts-`id`, nie `artifact_id`.
- Empirisch verifiziert (Django-Shell):
  `ArchitectureElement.id = 3fa18e04-...` (nicht gefunden in `pl_artifact`) vs.
  `ArchitectureElement.artifact_id = 211bd580-...` (existiert in `pl_artifact`,
  `get_tree` liefert damit korrekt einen Baum zurück).
- **Konsequenz:** Ein MCP-Client kann ohne direkten DB-Zugriff niemals ein gültiges
  `root_id` ermitteln — `artifact.get_tree` ist über die dokumentierte API-Oberfläche
  nicht benutzbar (REQ-L2-AS-002).

**Fix-Optionen:**
1. `artifact.get_tree` akzeptiert wahlweise Entitäts-`id` und löst intern über die
   `artifact`-FK auf.
2. Oder: Entitäts-Serializer (REST + MCP) exponieren `artifact_id` konsistent, damit
   Clients zwischen beiden Identitäten wechseln können.

---

## 3. `requirement.decompose` — Schema/Implementierung inkonsistent

**Schweregrad:** Hoch (Tool über dokumentiertes Schema nicht aufrufbar)

**Repro:**
```
tools/list → requirement.decompose: inputSchema.required = ["id"]
tools/call requirement.decompose {"id": "<req>"}
→ isError: "Error: Required parameter 'requirement_id' is missing."
```

**Root Cause:** `_TOOL_SCHEMAS` in `backend/mcp_server/tools/requirements.py:157-167`
deklariert Property/Required als `id`, `_handle_decompose`
(`backend/mcp_server/tools/requirements.py:342`) liest aber
`require_uuid(params, "requirement_id")`. Schema und Handler wurden offenbar unabhängig
voneinander geändert und sind auseinandergelaufen.

**Fix:** Schema auf `requirement_id` umstellen (konsistent mit `requirement.validate`,
das bereits korrekt `requirement_id` verwendet) — oder Handler auf `id` umstellen,
konsistent mit den übrigen `requirement.*`-Tools.

---

## 4. `requirement.derive` — Schema massiv unvollständig

**Schweregrad:** Hoch (Tool über dokumentiertes Schema nicht aufrufbar)

**Repro:**
```
tools/list → requirement.derive: inputSchema.required = ["id"]
tools/call requirement.derive {"id": "<req>"}
→ isError: "Error: Required parameter 'parent_requirement_id' is missing."
```

**Root Cause:** Schema (`requirements.py:179-189`) deklariert nur `{"id"}`. Der Handler
`_handle_derive` (`requirements.py:379-386`) verlangt tatsächlich
`parent_requirement_id`, `architecture_element_id` und `title` — drei völlig andere
Pflichtfelder, die im Schema gar nicht auftauchen.

**Fix:** Schema an die tatsächliche Signatur von `_handle_derive` /
`RequirementService.derive_requirement` anpassen.

---

## 5. `issue.create` — undokumentiertes Pflichtfeld

**Schweregrad:** Mittel

**Repro:**
```
tools/list → issue.create: inputSchema.required = ["workspace_id"], additionalProperties: true
tools/call issue.create {"workspace_id": "<ws>", "title": "..."}
→ isError: "Error: IssueService.create_issue() missing 1 required positional argument: 'severity'"
```

**Root Cause:** `GenericCrudToolGroup` (`backend/mcp_server/tools/generic.py`) generiert
für alle `<prefix>.create`-Tools ein **generisches** Schema, das nur `workspace_id` als
required deklariert (`additionalProperties: true` deckt den Rest pauschal ab). Das
entspricht aber nicht der tatsächlichen Service-Signatur:
`IssueService.create_issue(workspace_id, title, severity, ctx, ...)`
(`backend/application/issue_service.py:151-164`) — `severity` ist Pflicht-Positional-
Argument ohne Default. Der Fehler kommt als roher Python-`TypeError`-Text statt als
sauberer `VALIDATION_ERROR` durch (immerhin von `_handle_create`s generischem
`except Exception` abgefangen, kein Crash).

**Fix:** `GenericCrudToolGroup` müsste die tatsächlich required Felder pro Entität
(z. B. via `inspect.signature()` auf die `create_*`-Methode, ähnlich wie bereits für
`_resolve_id_param` gemacht) ins Schema übernehmen, statt pauschal nur `workspace_id`
zu verlangen. Vermutlich auch bei `adr.create`/`risk.create`/`glossary.create` mit
eigenen Pflichtfeldern relevant — nicht separat verifiziert.

---

## 6. Preset-Gating (REQ-L2-MC-008) faktisch wirkungslos

**Schweregrad:** Mittel (Design-Gap, kein Crash)

**Befund:**
- `_TOOL_FEATURE_MAP` (`backend/mcp_server/tool_registry.py:103-110`) referenziert die
  Feature-Keys `llm_decompose`, `llm_validate`, `architecture_links`, `test_links`,
  `traceability`, `artifact_tree`.
- Keine der drei Preset-Configs (`_MINIMAL`/`_STANDARD`/`_EXTENDED` in
  `backend/presets/registry.py:152-206`) definiert einen dieser Keys — die `features`-
  Dicts enthalten nur `baselines`, `global_baselines`, `approval_workflows`,
  `custom_workflows`, `change_reason_mandatory`.
- `ToolRegistry._check_preset()` (`tool_registry.py:591-617`) nutzt
  `features.get(feature_key, True)` → fällt für alle sechs gemappten Tools immer auf
  `True` (= erlaubt) zurück, unabhängig vom Preset-Tier.
- Zusätzlich läuft der Gate-Check nur, wenn `workspace_id` in den Call-Params gesetzt ist
  (`dispatch_request`, `tool_registry.py:422-429`). Tools wie `requirement.decompose`
  verlangen laut Schema aber gar kein `workspace_id` — ein Aufrufer kann den Check also
  durch simples Weglassen umgehen.
- **Empirisch verifiziert:** `requirement.decompose` auf einem Requirement in einer
  `minimal`-Tier-Workspace lief (bis auf Bug 3) ungehindert durch alle Auth-Stufen —
  keine `FEATURE_NOT_ENABLED`-Fehlermeldung, obwohl `llm_decompose` in einer
  Minimal-Preset-Workspace konzeptionell gesperrt sein sollte.

**Fix-Optionen:**
1. Feature-Keys aus `_TOOL_FEATURE_MAP` in den Preset-Configs tatsächlich definieren
   (z. B. `llm_decompose: False` für `minimal`).
2. Betroffene Tool-Schemas (`requirement.decompose` etc.) um ein required `workspace_id`
   ergänzen, damit der Gate-Check nicht umgangen werden kann.
3. Vorab mit `requirements`/Architektur klären, ob REQ-L2-MC-008 striktes Enforcement für
   alle Presets fordert oder das aktuelle Fail-Open-Verhalten bewusst so gewählt wurde.

---

## 7. Dead Config: `prompt_template`-Write-Prefixes ohne Implementierung

**Schweregrad:** Kosmetisch, kein funktionaler Impact

**Befund:** `_WRITE_TOOL_PREFIXES` (`tool_registry.py:53-97`) listet
`prompt_template.create`, `prompt_template.update`, `prompt_template.delete`.
`PromptTemplateToolGroup` (`backend/mcp_server/tools/prompt_template.py`) implementiert
laut Docstring bewusst **nur** `prompt_template.get` (read-only). Ein Aufruf dieser
Tool-Namen würde ohnehin an `UNKNOWN_TOOL` im Router scheitern — die RBAC-Einträge sind
totes/irreführendes Config-Deadwood.

**Fix:** Drei Zeilen aus `_WRITE_TOOL_PREFIXES` entfernen.

---

## 8. Doku-Abweichung: API-Key-Format

**Schweregrad:** Doku, kein Code-Bug**

**Befund:** Projekt-Kontext (`CLAUDE.md` / Agent-Briefings) nennt das API-Key-Format
`rfk_*`. Tatsächlich generiertes und akzeptiertes Format ist `rf_*`
(`backend/auth_tenancy/services/authentication.py:35`,
`_API_KEY_PREFIX = "rf_"`; verifiziert durch erfolgreiche Live-Key-Erzeugung über
`POST /api/v1/api-keys/`).

**Fix:** Doku-Referenzen auf `rf_*` korrigieren (`documenter`).

---

## Fehlerbehandlung — für sich genommen robust

JSON-RPC-Protokollebene funktioniert korrekt und wurde stichprobenartig verifiziert:

| Fall | Ergebnis |
|---|---|
| Malformed JSON Body | `-32700 Parse error` |
| Fehlendes `jsonrpc`-Feld | `-32600 Invalid Request` |
| Unbekanntes Tool / unbekannte Methode | `-32601 Unknown tool` (Direct-Method-Dispatch als Feature bestätigt, kein Bug) |
| Fehlender API-Key | `-32000 API key is required` |
| Ungültiger API-Key | `-32000 Authentication failed: invalid_api_key` |
| Fehlender Tool-Parameter (korrekt implementierte Tools) | sauberer `isError:true`-Text im MCP-Content-Format |

Die unter Punkt 1 beschriebenen Crashes sind ein Datenserialisierungs-Bug im
Erfolgspfad, kein genereller Defekt der Fehlerbehandlung.

---

## Zusammenfassung

18/18 Tool-Gruppen (72 Tools laut `tools/list`) getestet, ca. 30 Live-Requests gegen den
laufenden Docker-Stack. **8 Findings**: 4× Hoch (2 Crashes, 2 Schema/Implementierungs-
Mismatches), 2× Mittel (undokumentiertes Pflichtfeld, Preset-Gating wirkungslos),
1× kosmetisch, 1× Doku. Kein Code im Rahmen dieses Tests geändert; der temporäre
Test-API-Key wurde nach Abschluss widerrufen.
