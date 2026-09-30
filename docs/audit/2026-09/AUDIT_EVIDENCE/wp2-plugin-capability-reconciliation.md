---
type: REVIEW
scope: wp-2-capability-reconciliation
status: final
date: 2026-09-29
author_agent: senior-developer
---

# WP-2 Evidenz 2 — Fähigkeits-Reconciliation: deklariert vs. Plugin-Code vs. Registry

Drei Ebenen getrennt geprüft:
**(a)** Was deklariert das Manifest/die Rolle/das Skill?
**(b)** Gibt es den Aufruf im Plugin-Code?
**(c)** Gibt es den Server-Tool/Endpoint — und ist er live erreichbar?

Referenzmenge: `docs/agent-templates/tool-manifest.json`, `tool_count = 219`,
`len(tools) = 219`, 35 Präfixe — deckungsgleich mit WP-1a
(`wp1a-mcp-tool-count-resolution.md:18-24`).

## 1. Hermes-TS-Plugin: deklarierte vs. realisierte MCP-Tools

Das Manifest deklariert **keine** Tool-Liste. Die real deklarierte Oberfläche ist der
Quelltext. `mcpClient.ts` ruft genau sieben JSON-RPC-Methoden:

| # | `mcpClient.ts` | JSON-RPC `method` | in Registry (219)? | live aufgerufen? | Ergebnis |
|---|---|---|---|---|---|
| 1 | `:128` `interviewStart` | `interview.start` | ✔ | ✔ | **200**, Session `24be6e81-…` angelegt |
| 2 | `:139` `interviewGetState` | `interview.get_state` | ✔ (read) | ✔ | **200**, `phase: identification` |
| 3 | `:151` `interviewAnswer` | `interview.answer` | ✔ (write) | ✔ | **200**, `collected_fields.description` gesetzt |
| 4 | `:163` `interviewGroundingContext` | `interview.grounding_context` | ✔ (write) | ✔ | **200** `{"candidates": []}` |
| 5 | `:173` `interviewFormalize` | `interview.formalize` | ✔ (write) | ⚠️ nur read | s. §1a |
| 6 | `:185` `interviewList` | `interview.list` | ✔ (read) | ✔ | **200** `{"sessions":[…3…],"count":0}` |
| 7 | `:197` `interviewSetTarget` | `interview.set_target` | ✔ (write) | ✖ | s. §1a |

**7/7 deklarierte Calls existieren in der Registry. 0 Phantom-Tools. 0 Über-Deklaration.**

### 1a. Zwei nicht ausführbar gemachte Calls — mit Begründung, kein Defekt

`interview.formalize` und `interview.set_target` fire-and-forget im Plugin nie, weil:

* `interview-start-*`-Buttons existieren, aber die **Formalize**-Schaltfläche bleibt
  `disabled={state.interviewBusy || interview.missing_fields.length > 0}`
  (`InterviewFormView.tsx:120`). Gemessen: nach `interview.start` (missing 1) und nach
  `interview.answer` (missing 1, `title`) war `Formalize` **disabled** →
  Log: `[drive] formalize button present=false`.
* `set_target` wird nur geklickt, wenn `grounding_snapshot.candidates.length > 0`
  (`InterviewFormView.tsx:89-106`). Live war `candidates` leer
  (`net#3 -> {"candidates": []}`) → der Button existierte nie.

Das ist **korrekte Feature-Verdeckung**, kein toter Code. Nicht als Finding gewertet.
`interview.formalize` wurde zusätzlich **über den Python-Pfad** live ausgeführt
(s. §3), damit der Write-Pfad nicht ungeprüft bleibt.

## 2. Hermes-TS-Plugin: REST-Oberfläche

`api.ts:147` ruft `GET /api/v1/workspaces/` mit `X-API-Key` + `Content-Type: application/json`.

Live (net#1 eines Happy-Path-Laufs):

```
GET http://localhost:8001/api/v1/workspaces/  -> 200 (69 ms, 13390 B)
{"count":401,"next":"http://localhost:8001/api/v1/workspaces/?page=2","previous":null,
 "page_size":25,"max_page_size":100,"results":[…25…]}
```

**Der Endpoint existiert und antwortet. Der Plugin-Code liest aber nur `results[]`**
(`api.ts:149-152`) und ignoriert `next`. Gemessen im gerenderten DOM:

```
[drive] workspace picker shows 25 of count=401
[drive] looking for workspace containing "Zahnb" -> index -1
[drive] workspace picker shows 25 of count=401 (api.ts listWorkspaces reads results[] only, ignores next)
```

→ Der Ziel-Workspace **„Zahnbürste SysEng Demo" (`4eee7ca1-…`) ist über die eigene
Plugin-UI nicht erreichbar**, weil er auf Seite 2+ liegt. → **AUD-2026-09-109 (High).**

Testlücke dazu: **alle 6** `listWorkspaces`-Fixtures in
`integrations/hermes-plugin/reqogniloom/src/__tests__/api.test.ts` (Zeilen 8-9, 31, 42-43,
62-63, …) benutzen `"next": null` — der Mehrseiten-Fall wird nie getestet. Die Suite
läuft grün (`npm test`: *Test Files 6 passed, Tests 104 passed*).

## 3. Hermes-Python-Plugin: deklarierte vs. existierende REST-Endpoints

Manifest-Deklaration (`__init__.py:58-72`, `_HELP_TEXT`) nennt 9 Subcommands.
Client-Methoden (`reqogniloom_client.py`) und Live-Probe:

| Subcommand | Client-Methode | HTTP | Live-Status | Befund |
|---|---|---|---|---|
| `start` | `start_interview` `:143` | `POST /api/v1/interviews/` | **201** | ✅ existiert — aber `artifact_type` muss PascalCase sein (s. §3a) |
| `status` | `get_state` `:161` | `GET /api/v1/interviews/{id}/state/` | **200** | ✅ |
| `answer` | `answer` `:164` | `POST …/answer/` | **200** | ✅ (setzte `phase: formalization`) |
| `chat` | `chat` `:167` | `POST …/chat/` | **200** `{"reply":"[]","state":{…}}` | ✅ |
| `formalize` | `formalize` `:170` | `POST …/formalize/` | **200** `{"resulting_artifact_ids":["538097f4-…"],"status":"completed"}` | ✅ Endpoint; Ausgabe-Format fehlerhaft (s. §3b) |
| `abandon` | `abandon` `:173` | `POST …/abandon/` | **200** bei in_progress | ✅ |
| `workspaces` | `list_workspaces` `:136` | `GET /api/v1/workspaces/` | **200** `count=401` | ⚠️ nur Seite 1 (s. §3c) |
| `stats` | `stats` `:178` | `GET …/requirements/`, `/testcases/`, `/interviews/` | **200 / 200 / 200** | ⚠️ ein Zähler dauerhaft `None` (s. §3d) |
| `help` | — | — | lokal | ✅ |

**8/8 deklarierte Endpunkte existieren. 0 Phantom-Endpoints.**

Zusätzlich verifiziert: die Plugin-Auth-Konvention
(`Authorization: Bearer <reqlo_…>`, `reqogniloom_client.py:95`) wird vom Backend
akzeptiert — **6/6 GET-Probes mit Bearer `reqlo_`-Key → 200**. Das ist eine **zweite,
von `INSTALL.md:137-139` nicht dokumentierte** Auth-Konvention neben `X-API-Key`.

### 3a. `start requirement` — der eigene Hilfetext-Beispielwert wird abgelehnt

`_HELP_TEXT` (`__init__.py:62`) dokumentiert wörtlich:
`start <artifact_type> [workspace_id]   Start a new interview (e.g. "requirement", "need").`

Live, Slash-Command über den echten `register_command`-Handler:

```
[slash] /reqogniloom start requirement 4eee7ca1-eedd-4a7e-bb14-47e6493cbf88
[slash] RETURNED type=str
[slash] ReqogniLoom error: 400: {"error":{"code":"VALIDATION_ERROR",
        "message":"Interviews are not available for artifact_type='requirement'
        (MainGoal stays read-only; other unknown types are unsupported).","details":[]}}
```

Wertematrix (8 Probes, live):

| `artifact_type` | Status |
|---|---|
| `requirement` | ❌ 400 |
| `Requirement` | ✅ **201** `id=0cffb8db-…` |
| `need` | ❌ 400 |
| `Need` | ❌ 400 |
| `main_goal` | ❌ 400 |
| `adr` | ❌ 400 |
| `Adr` | ✅ **201** `id=456813b2-…` |
| `issue` | ❌ 400 |

Nur die exakte PascalCase-Form funktioniert. Der Client (`__init__.py:105-107`,
`reqogniloom_client.py:143`) normalisiert den Nutzerinput **nicht**. Der
**Kopfangebot des Slash-Commands ist damit unbenutzbar**, und `plugin.yaml:3`
beschreibt das Plugin als „Start and drive ReqogniLoom requirements interviews".
→ **AUD-2026-09-110 (High).**

### 3b. `formalize` gibt das rohe Dict statt der Artefakt-ID aus

`__init__.py:138`:
```python
return f"Formalized. Artifact: {result.get('artifact_id', result)}"
```

Live-Antwort des Servers: `{"resulting_artifact_ids":["538097f4-…"],"status":"completed"}`
— **kein `artifact_id`-Key**. `.get('artifact_id', result)` fällt also auf den
**kompletten Response-Dict** zurück; der Nutzer sieht statt einer ID einen JSON-Dump.
Vergleich: das TS-Plugin typisiert denselben Call korrekt als
`{resulting_artifact_ids: string[]; status: string}` (`mcpClient.ts:172-176`).
Live-Nebenbeleg aus demselben Lauf:
```
[slash] /reqogniloom formalize
[slash] ReqogniLoom error: 400: {... "message":"InterviewSession d4063ce6-… is not
        complete yet -- missing required field(s): title. Cannot formalize."}
```
→ Der Fehlerpfad ist sauber, nur der Erfolgspfad formatiert falsch.
→ **AUD-2026-09-111 (Medium).**

### 3c. `workspaces` listet nur Seite 1

`_list_results` (`reqogniloom_client.py:37-51`) gibt bei einem dict mit `results[]`
genau diese Liste zurück; `next` wird nie verfolgt. Live-Ausgabe des Slash-Commands
umfasste 25 von `count=401` Workspaces. `resolve_workspace_id` (`:214-236`) nimmt
blind `workspaces[0]` — also immer denselben, für den Nutzer nicht wählbaren ersten
Workspace. Derselbe Defekt wie §2, zweite Implementierung. → **AUD-2026-09-109**
(zwei Fundstellen: `api.ts:143-153` und `reqogniloom_client.py:136-139`).

### 3d. `stats` liefert `open interviews` dauerhaft `None`

`reqogniloom_client.py:54-60` liest den DRF-`count`-Feld. Live-Antwort von
`GET /api/v1/interviews/?workspace_id=…&status=in_progress`:

```
$ j.PSObject.Properties.Name   ->   results
count field present = False
results length = 5
raw head: {"results":[{"id":"384dc3e5-…",…
```

Das `/interviews/`-Envelope hat **kein `count`** (anders als `/requirements/`
(`count=888`) und `/testcases/` (`count=30`)). `_total_count` gibt daher `None`
zurück, und `stats()` degradiert **ohne Fehler** auf `None`:

```
[slash] /reqogniloom stats 4eee7ca1-eedd-4a7e-bb14-47e6493cbf88
[slash] workspace:       4eee7ca1-eedd-4a7e-bb14-47e6493cbf88
[slash] requirements:    889
[slash] testcases:       30
[slash] open interviews: None          <- dauerhaft, kein Hinweis auf Ursache
```

Das ist exakt das Fehlermuster, das #1118 für die *Seitenlänge als Gesamtzahl*
korrigiert hat — der Zähler wurde auf `count` umgestellt, aber `count` existiert für
diesen Endpunkt nicht. **Stiller Fehlschlag.** → **AUD-2026-09-112 (Medium).**

## 4. Claude-Code-/Antigravity-Pakete: Rollen-Whitelists vs. Registry

`build_claude_plugin.py:111-113` schreibt `mcp__reqogniloom__<tool>` in die
`tools:`-Whitelist jeder Rolle. Gemessen:

| Rolle | Tools | Datei |
|---|---|---|
| `requirements-architecture-manager.md` | 31 | `agents/requirements-architecture-manager.md` |
| `change-manager.md` | 39 | `agents/change-manager.md` |
| `quality-auditor.md` | 25 | `agents/quality-auditor.md` |
| `risk-analyst.md` | 15 | `agents/risk-analyst.md` |
| `test-engineer.md` | 14 | `agents/test-engineer.md` |
| **distinct gesamt** | **80** | |

```
deklarierte Tools, die NICHT in der 219er-Registry sind : 0
deklariert ∩ manifest read-only (is_write=false)       : 35 von 80
deklariert ∩ manifest write     (is_write=true)        : 45 von 139
Registry-Tools ohne jede Rollen-Whitelist              : 139 von 219  (Abdeckung 36.5 %)
```

**Null Über-Deklaration, null Phantom-Tools.** Beide dist-Pakete sind in dieser
Hinsicht sauber — das ist der positive Gegenpol zum Python-Plugin.

### 4a. Umgekehrte Lücke: 45 **read-only**-Tools sind über kein Agenten aufrufbar

```
admin.backup_list, adr.query, attribute_catalog.{export,list,search},
attribute_definition.{get,list}, attribute_migration.{get_run,list_runs,plan},
audit.{ai_review,query,waivers}, comment.list, context.{change_impact,query,test_coverage},
events.dlq_list, glossary.query, goal.list_versions, icd.{query,read},
interview.{get,get_state,list,propose}, issue.query, link_type.{get,list},
main_goal.list_versions, memory.{digest,get,list,query}, needs.query,
permissions.{check,list}, prompt_variable.{get,list}, risk.query, test.run_list,
user.list, workspace.{get_preferences,list,llm_system_prompt}
```

Darunter die gesamte `interview.*`-Familie (alle 10 Tools,
`inAgentWhitelist=False` für **jedes** einzelne), ferner die komplette
`context.*`-Achse (Change-Impact, Test-Coverage) und `audit.*`.

Konkrete Konsequenz: das **mitgelieferte** `skills/interview-management/SKILL.md`
ist im Claude-Code-Paket **vollständig unbenutzbar** —
`docs/agent-templates/skills-tool-refs.json` ordnet ihm 5 Tools zu, und **alle 5
sind außerhalb jeder Whitelist**:

| Skill-Tool-Referenz (aus `skills-tool-refs.json`) | in irgendeiner Rollen-Whitelist? |
|---|---|
| `interview.start` | ❌ |
| `interview.get_state` | ❌ |
| `interview.answer` | ❌ |
| `interview.grounding_context` | ❌ |
| `interview.formalize` | ❌ |

Über alle 6 Skills und **129** Tool-Referenzen ist das der **einzige** blockierte
Skill. → **AUD-2026-09-113 (Medium).**

### 4b. Skill-Text-Referenzen: 0 Phantome

Regex-Scan über alle 12 `SKILL.md` in `dist/plugins/**` (je 6 in Claude-Code und
Antigravity): **82** distinct dotted Tool-Referenzen, **0** davon außerhalb der
219er-Registry. Zusätzlich `skills-tool-refs.json`: 129 Referenzen, **0 Phantom**.
(Anders als im Python-Plugin: hier trennen Mock und Realität nicht — s. §5.)

## 5. Testabdeckung vs. Realität — der zentrale-systemische Befund

| Suite | Ergebnis | Was live kaputt ist |
|---|---|---|
| `integrations/hermes-agent-plugin/tests` | **106 passed, 69 subtests passed** | `_fmt_state` stürzt ab (§6) |
| `integrations/hermes-plugin/reqogniloom` (`npm test`) | **104 passed, 6 Test Files** | Workspace-Pagination (§2) |
| `dist/plugins/*/test_build_*.py` | Builder-Verhalten | (unproblematisch) |

Beide Suffixe sind dasselbe Muster: **die Fixtures kodieren einen Vertrag, den der
Server nicht erfüllt.**

* `test_slash_command.py:40` → `"missing_fields": ["title"]`
  Live: `"missing_fields": [{"name":"title","type":"text","choices":null}]`
* `api.test.ts:8-9,31,42-43,62-63` → `"count": N, "next": null`
  Live: `"count": 401, "next": "…?page=2"`

→ **AUD-2026-09-114 (High)** als übergreifender Befund; die beiden Einzelfunde
sitzen in 109 und 121.

## 6. Kernbefund: `_handle_slash` verletzt seinen eigenen Vertrag

`__init__.py:87-88`:
> `"""Entry point registered via ``ctx.register_command``. Never raises —
> every error path returns a human-readable string instead."""`

Live-Ausführung über den echten `register_command`-Handler gegen die laufende Instanz:

```
[slash] /reqogniloom start Requirement 4eee7ca1-…
[slash] *** RAISED TypeError: sequence item 0: expected str instance, dict found ***
  File "integrations\hermes-agent-plugin\__init__.py", line 110, in _handle_slash
    return f"Started interview {session['id']} …" + _fmt_state(session)
  File "integrations\hermes-agent-plugin\__init__.py", line 79, in _fmt_state
    lines.append(f"missing:   {', '.join(missing)}")
TypeError: sequence item 0: expected str instance, dict found

[slash] /reqogniloom status
[slash] *** RAISED TypeError: sequence item 0: expected str instance, dict found ***   (Zeile 120)

[slash] /reqogniloom answer description X
[slash] *** RAISED TypeError: sequence item 0: expected str instance, dict found ***   (Zeile 127)
```

Ursache: `_fmt_state:77-79` behandelt `missing_fields` als Liste von **Strings**,
der Server liefert eine Liste von **Dicts**. `except ReqogniLoomError` (`__init__.py:162`)
fängt `TypeError` nicht.

Betroffen sind **`start`, `status` und `answer`** — also die drei Kernbefehle des
Slash-Commands. `formalize`, `abandon`, `workspaces`, `stats`, `help` und die
Fehlerpfade funktionieren. Der Slash-Command ist damit in seinem **Hauptpfad
unbenutzbar**, obwohl 106 Tests grün sind.

→ **AUD-2026-09-115 (Critical).**
