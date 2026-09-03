# MCP-Modernisierung — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. C5 (alter Protokollstand,
Tools-only), C6 (MCP/REST nicht paritätisch), E3.4 (Modernisierungs-Punkt aus Kap. E),
I.7 (MCP-Kontextkosten). Achte von mehreren unabhängigen Folge-Specs aus demselben Audit.
**Scope:** Die reinen Bugfixes aus Kap. H1/H4/R4 (GET `/mcp/` liefert 200 statt 405,
JSON-RPC-Batch → 500, Parse-Error → falscher HTTP-Code) sind bereits als GitHub-Issue
**#846** gemeldet — nicht Teil dieser Spec, die sich auf die architektonische
Modernisierung konzentriert, nicht auf die Kleinreparaturen.

## 1. Problem

`MCP_PROTOCOL_VERSION = "2024-11-05"` (`protocol_handler.py:45`) — aktueller Spec-Stand
ist 2025-06-18. `initialize` meldet nur `capabilities: {"tools": {}}` — keine
`resources`, keine `prompts`. `McpArtifactProvider` (Artefakt als Markdown) und das
Prompt-Template-System wären natürliche Resources bzw. Prompts, laufen aber als Tools.
27 Tool-Gruppen, ~175 Tools — REST kennt aber Endpoints, die MCP nicht hat (ICDs,
Metrics, API-Keys, ...), und umgekehrt. Live gemessen: 99 KB Manifest, 172 Tools, 212 ms
`tools/list`-Antwortzeit (Kap. R4) — mit jeder neu gebauten Tool-Gruppe (aus den anderen
Specs dieser Session: `attribute_definition.*`, `link_type.*`, `comment.*`,
`integration.github.*`/`integration.jira.*`) wächst das weiter.

**Präzisierung gegenüber dem Audit-Text:** das Manifest ist *nicht* für jeden Caller
identisch — `TenantToolRegistry.list_tools()` filtert bereits heute Write-Tools für
Caller ohne Write-Rolle raus (das P0-Sicherheits-Fail-Closed-Gate, `_is_write_tool()`).
Die 99-KB-Messung aus R4 spiegelt vermutlich einen Admin-Key. Diese Spec baut auf diesem
bestehenden Filter auf, statt ihn zu ersetzen.

## 2. Ziel

1. Protokoll auf 2025-06-18, Streamable HTTP mit `Mcp-Session-Id`-Header.
2. `resources/*` für Artefakt-Markdown, `prompts/*` für Prompt-Templates.
3. `icd.*`-Tool-Gruppe für REST/MCP-Parität bei einem Kernartefakt.
4. Zwei zusätzliche, additive Manifest-Filter auf der bestehenden Gate-Logik — einer mit
   echter Sicherheitswirkung, einer rein kuratorisch (Abschnitt 5, wichtige Trennung).

## 3. Protokoll & Transport

- `MCP_PROTOCOL_VERSION` → `"2025-06-18"`.
- Streamable HTTP (POST `/mcp/`, Response wahlweise JSON oder SSE-Stream je nach
  `Accept`-Header) wird primärer, empfohlener Transport, mit `Mcp-Session-Id` als
  HTTP-Header statt `session_id` als Query-Parameter im alten SSE-Modell.
- **Legacy-SSE-Transport bleibt bestehen**, nicht entfernt — der OpenCode-Fallback-Pfad
  aus Issue #846 hängt daran (`opencode.json` fällt bei fehlgeschlagenem StreamableHTTP
  auf SSE zurück). Modernisierung heißt hier "zusätzlich", nicht "ersetzt".
- `initialize`-Antwort: `capabilities` bekommt `resources: {}` und `prompts: {}` neben
  dem bestehenden `tools: {}`.

## 4. `resources/*` und `prompts/*`

**`resources/list`, `resources/read`, `resources/templates/list`:** URI-Schema
`reqogniloom://artifact/{id}` liest denselben Markdown-Renderer, den
`McpArtifactProvider` heute für das Tool `artifact.get` nutzt — Resources ist ein
zusätzlicher Zugriffsweg auf dieselbe Logik, `artifact.get` bleibt unverändert bestehen
(kein Breaking Change für bestehende Aufrufer).

**`prompts/list`, `prompts/get`:** das bestehende, versionierte `PromptTemplate`-System
(Phase 4, längst in main gemergt) wird zusätzlich über MCP Prompts angeboten — der
natürliche Nutzungspfad für einen Client, der einem Menschen eine Auswahl fertiger Prompts
zeigen will, statt über das `prompt_template.*`-Tool selbst zu iterieren. Die
`prompt_template.*`-Tool-Gruppe bleibt für Verwaltung (create/update, Admin-Gate)
bestehen — Prompts-Capability ist Lese-/Nutzungspfad, kein Ersatz für die
Verwaltungs-Tools.

## 5. `icd.*`-Tool-Gruppe

Read-Fokus für den MVP: `icd.get`, `icd.query` — schließt die von C6 gemeldete Lücke
("ein KI-Agent kann Schnittstellen nicht lesen, obwohl das Produkt sie als Kernartefakt
führt"). Schreibende ICD-Tools (`icd.create`/`icd.update`) sind ein separater,
natürlicher Ausbau, aber nicht Teil dieser Spec — Lesezugriff ist der dringende Bedarf
laut Audit-Text, Schreiben nicht explizit gefordert.

## 6. Manifest-Filter — zwei Mechanismen mit unterschiedlicher Wirkung

**Wichtige Unterscheidung, die in der Kurzdarstellung nicht klar war:**

### 6.1 `ApiKey.scope="read"` — echte Sicherheitsgrenze

Aus der KI-Vorschlag-als-Zustand-Spec bereits vorgesehen. Für einen Key mit
`scope="read"`:
- `tools/list` filtert Write-Tools raus (Erweiterung der bestehenden
  `_is_write_tool()`-Logik um eine zusätzliche Bedingung).
- `dispatch_request()`/`tools/call` **lehnt den Aufruf eines Write-Tools tatsächlich ab**
  (`PERMISSION_DENIED`), unabhängig davon, ob der Tool-Name dem Aufrufer bekannt ist oder
  nicht — dieselbe Durchsetzung wie heute schon bei fehlender Write-Rolle, nur zusätzlich
  an `scope` geprüft. Hier fehlt echte Funktionalität, kein Kuration-Placebo.

### 6.2 `ApiKey.tool_groups` — reine Katalog-Kuration, keine Sicherheitsgrenze

Neues optionales Feld (Liste von Gruppennamen, leer/null = alle Gruppen wie heute):

```python
tool_groups = models.JSONField(default=list, blank=True)  # z.B. ["requirement", "traceability"]
```

`tools/list` zeigt nur Tools aus den gelisteten Gruppen. **`tools/call` funktioniert für
JEDES Tool weiterhin normal**, unabhängig von `tool_groups` — solange Rolle und `scope`
(Abschnitt 6.1) es erlauben. `tool_groups` verändert nur, was im Manifest sichtbar ist
(weniger Tokens im Kontext eines Clients, der nur einen Ausschnitt braucht), **nicht**,
was ausführbar ist. Ein Key mit engen `tool_groups` verliert dadurch keine Fähigkeit —
er bekommt nur ein kleineres Menü angezeigt und kann trotzdem jedes andere erlaubte Tool
direkt beim Namen aufrufen.

**Neues Introspektions-Tool `tool.list_groups`:** immer sichtbar, ungefiltert (reine
Metadaten, kein Sicherheitsrisiko) — listet alle existierenden Gruppen mit Tool-Anzahl,
damit ein Client/Agent vor der Key-Konfiguration weiß, welche Gruppen es gibt.

## 7. Migration

Additiv, kein Datenumbau bestehender Zeilen:

1. Protokollversion-Konstante ändern, `capabilities` erweitern.
2. Streamable-HTTP-Handler zusätzlich zum bestehenden SSE-Handler.
3. `resources.py`/`prompts.py`-Handler in `protocol_handler.py` verdrahten.
4. `icd.*`-Tool-Gruppe registrieren.
5. `ApiKey.tool_groups`-Feld (additiv, `ApiKey.scope` existiert bereits aus der
   KI-Vorschlag-als-Zustand-Spec) — `list_tools()`/`dispatch_request()` um die
   Zusatzprüfung erweitern.
6. `tool.list_groups` als neues, always-visible Introspektions-Tool.

## 8. Risiken

- **Protokoll-Downgrade-Kompatibilität:** ein Client, der noch strikt 2024-11-05 spricht,
  muss weiterhin funktionieren — MCP-Versionierung ist grundsätzlich
  abwärtskompatibel gedacht, aber nicht jeder Client-SDK hält sich daran. Vor dem Rollout:
  Testlauf gegen mindestens Claude Code und OpenCode (dieselben Clients, die H1/H2 schon
  geprüft haben).
- **`resources/*` dupliziert Zugriffslogik** (`artifact.get`-Tool und
  `resources/read` lesen denselben Renderer über zwei Pfade) — Divergenz-Risiko, wenn
  künftig nur einer der beiden Pfade gepflegt wird. Empfehlung für die Implementierung:
  eine gemeinsame interne Funktion, zwei dünne Adapter (Tool-Handler, Resource-Handler).
- **`tool_groups` als reine UX-Kuration** könnte in der Praxis falsch verstanden und als
  Sicherheitsfeature missbraucht werden, wenn die Unterscheidung zu `scope` nicht
  deutlich genug in der Dokumentation/UI steht — muss in der Implementierung (Tooltip,
  Docs) explizit gemacht werden, nicht nur in dieser Spec.
