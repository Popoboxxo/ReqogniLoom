---
type: EVIDENCE
scope: wp4-link-types-4level
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 1 — Link-Typen: 4-Ebenen-Konsistenzmatrix

## 0. Verifizierte Grundzahl

**11 built-in Link-Typen.** Eigenzählung, nicht aus `AGENTS.md` übernommen.

`backend/link_types/builtin.py:78` `BUILTIN_LINK_TYPES: dict[str, dict[str, Any]]` enthält
genau 11 Einträge. Unabhängig bestätigt durch:

| Quelle | Datei:Zeile | Wert |
|---|---|---|
| Katalog-SSOT | `backend/link_types/builtin.py:78-…` | 11 |
| Python-Enum | `backend/traceability/types.py:44-67` | 11 (`DERIVES_FROM, DECOMPOSES, ALLOCATED_TO, VERIFIES, DECIDES, MITIGATES, REFERENCES, DIAGRAM_REF, REFINES, SATISFIES, REALIZES`) |
| ReqIF-Exporter | `backend/application/reqif_export_service.py:71-72` | 11 (namentlich aufgezählt) |
| Frontend-Fallback | `frontend/src/constants/traceLinkLabels.ts:42-87` | 11 |
| Live-DB (global) | `lt_global_definition` je Tenant | 11 |
| Live-DB (workspace) | `lt_workspace_definition` | 11 (401/402 Workspaces), 8 (1 Orphan) |

**Historische Zahlen 6 und 8 existieren weiterhin im Code selbst** (nicht nur in Doku):

| Zahl | Ort | Wortlaut |
|---|---|---|
| 8 | `backend/traceability/services.py:227` | `InvalidLinkTypeError: link_type not in 8 valid types.` |
| 8 | `backend/traceability/trace_link_manager.py:356` | Kommentar `the 8 relation types are semantically distinct directed graphs` |
| 10 | `backend/traceability/exceptions.py:19-24` | `not in the 10 valid types` + nennt 10 **retired** Keys (`parent-child, derives-from, satisfies, verifies, implements, refines, documents, realizes, traces, copy-of`) |

→ **AUD-2026-09-328**. KeinCR-Duplikat: `CR-15` behandelt TraceLink-Update/Batch-Zyklenvertrag,
nicht die Zahlen-Drift in Docstrings.

## 1. Die 4-Ebenen-Matrix

Alle vier Ebenen geprüft. **Der primäre Katalog ist auf allen vier Ebenen konsistent offen
(kein Enum) — das ist ein PASS.** Die Abweichungen liegen in den *sekundären* Konsumenten.

| Ebene | Ort | Repräsentation | Enum? | 11er-Liste? | Abweichung |
|---|---|---|---|---|---|
| (a) DB/Persistenz | `pl_tracelink.link_type` | `character varying`, **keine** Enum, **keine** CHECK | nein | n/a | keine (offen = korrekt) |
| (a) DB/Katalog | `lt_global_definition` / `lt_workspace_definition` | `definition_json` JSONField, `key` varchar(64) | nein | 11 | 1 Orphan-Workspace mit 8 |
| (b) REST-Serializer | `backend/rest_api/serializers.py:1394` | `serializers.CharField(max_length=64)` | nein | n/a | keine |
| (b) OpenAPI | `/api/schema/`, 4 Felder | `link_type: {type: string, maxLength: 64}` | nein | n/a | keine |
| (c) MCP | `backend/mcp_server/tools/cross_cutting.py:291-299` | `"type": "string"` + „call link_type.list" | nein | n/a | keine |
| (c) MCP | `backend/mcp_server/tools/architecture.py:265-274` | dito, explizit „Deliberately NOT an enum" | nein | n/a | keine |
| (d) Frontend-Typ | `frontend/src/types/index.ts:324` | `export type LinkType = string;` | nein | n/a | keine |
| (d) Frontend-Labels | `frontend/src/constants/traceLinkLabels.ts:42-87` | `FALLBACK_TRI_LABELS` | n/a | **11** | keine |

Beleg OpenAPI (live, read-only, `GET http://localhost:8001/api/schema/`, 613 769 Bytes):

```
16447:        link_type:
16448:          type: string
16449:          minLength: 1
16450:          maxLength: 64
17665:        link_type:
17666:          type: string
17667:          maxLength: 64
```

Live-DB-Messung `pl_tracelink` (2099 Links, nur 7 Typen tatsächlich benutzt):

```
allocated-to|921
derives-from|913
decomposes|145
references|55
verifies|31
mitigates|22
decides|12
```

→ `refines`, `realizes`, `satisfies`, `diagram-ref` haben **0 Links**. Die 11 Typen sind
implementiert, aber 4 davon sind auf der laufenden Instanz ungenutzt.

## 2. Sekundäre Konsumenten mit abweichender Liste (die eigentlichen Findings)

### 2.1 `refines` fehlt in ALLEN drei Hierarchie-Definitionen

`refines` ist laut eigener Definition eine Hierarchiekante
(`backend/link_types/builtin.py:139-152`): *„Same direction as `derives-from` … a weaker claim"*,
`allowed_pairs = [Requirement → Requirement]`. Trotzdem ist `refines` in **keiner** der drei
Hierarchie-Tabellen enthalten:

| # | Ort | Definition | `refines`? |
|---|---|---|---|
| 1 | `backend/traceability/audit/hierarchy.py:172-186` | `PARENT_TO_CHILD={decomposes}`, `CHILD_TO_PARENT={derives-from}` | **nein** |
| 2 | `backend/baseline/services.py:430` | SQL `tl.link_type = 'derives-from'` | **nein** |
| 3 | `backend/baseline/delta_index_builder.py:288` | SQL `tl.link_type = 'derives-from'` | **nein** |
| 4 | `frontend/src/utils/traceEndpoints.ts:72-75` | `HIERARCHY_LINK_TYPES = ["derives-from","decomposes"]` | **nein** |

Erschwerend: `backend/traceability/audit/hierarchy.py:34-38` behauptet im Docstring
*„`refines` no longer exists as a link type: the migration folded it into `derives-from`"* —
das ist **Stand vor Issue #950**, das `refines` als Built-in mit neuer Semantik
wieder eingeführt hat (`builtin.py:136-140`, `link_types/migrations/0008_seed_satisfaction_link_types.py:1`).

**Folge:** `Requirement.level` (ADR-005, `hierarchy.py:61-64`) und die Root/Leaf-Klassifikation
für TRACE-P1/VERIF-P8 leiten sich aus einer Hierarchie ab, die `refines`-Kanten ignoriert.
Ein nur über `refines` abgeleitetes Requirement gilt als **Wurzel (L1)**.

**Dokumentations-Drift im selben Paket** (derselbe Defekt, zwei weitere Belege):

- `backend/baseline/services.py:324` — Docstring: *„via `derives-from`/**`refines`** TraceLinks"*,
  SQL in derselben Funktion (`:430`): nur `'derives-from'`.
- `backend/baseline/delta_index_builder.py:262` und `:272` — Docstring *„`derives-from` / `refines`"*,
  SQL in derselben Funktion (`:288`): nur `'derives-from'`.

→ **AUD-2026-09-325** (High). Kein CR-Duplikat: `CR-15` nennt
`trace_link_manager.py:463-583` / `trace_link_service.py:273-347` (Update/Batch-Zyklusvertrag),
nicht die Hierarchie-Semantik.

### 2.2 `VALID_LINK_TYPES` wird als Autorität benutzt, obwohl der Code sie als Nicht-Autorität deklariert

Drei Aussagen, die sich widersprechen:

| Ort | Aussage |
|---|---|
| `backend/traceability/types.py:76-78` | „**No longer a validation authority** — `link_types.catalog.validate_link_pair` decides" |
| `backend/traceability/trace_link_manager.py:62-73` | „**Not the authority.** … `VALID_LINK_TYPES` is deliberately kept a superset" |
| `backend/link_types/catalog.py:2-5` | „This module is the **single seam** … Nothing else queries `WorkspaceLinkTypeDefinition`" |
| `backend/traceability/services.py:65` + `:472` | **re-exportiert `VALID_LINK_TYPES` als öffentliche API** (`__all__`) |
| `backend/application/reqif_import_service.py:886` | **benutzt `VALID_LINK_TYPES` tatsächlich als Autorität** |

→ **AUD-2026-09-326 / -154**.

## 3. Tenant-Extensibility — funktioniert, mit einer Lücke

**Positiv belegt:** Der Katalog ist ein echter, materialisierter Tenant-Katalog
(`link_types/models.py:27-83`), nicht ein Enum:

- `lt_global_definition`: 44 Zeilen / 4 Tenants × 11 Keys, UNIQUE `(tenant_id, key)` ✓
- `lt_workspace_definition`: 4419 Zeilen, UNIQUE `(tenant_id, workspace_id, key)` ✓
- `source_global` FK mit `SET_NULL` (`models.py:61-67`) — Löschen der Vorlage kaskadiert nicht ✓
- Anlegen/Verwenden/Validieren: REST `/api/v1/workspaces/{id}/link-type-definitions/[/{key}/[/reset/]]`
  (live im OpenAPI), MCP `link_type.create/update/reset/list/get`
  (`backend/mcp_server/tools/link_type.py:56-114`), UI `frontend/src/components/LinkTypeEditor/` ✓

**Lücke 1 — Orphan-Workspace mit unvollständigem Katalog (live gemessen):**

```sql
SELECT d.workspace_id, count(*) AS keys
FROM lt_workspace_definition d
WHERE NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id = d.workspace_id)
GROUP BY 1;
-- 3ef86cd6-ac51-4c11-b754-214716d65ebb | 8
-- keys: allocated-to, decides, decomposes, derives-from, diagram-ref, mitigates, references, verifies
-- fehlend: refines, realizes, satisfies   (die 3 Keys aus Migration link_types.0008)
```

`lt_workspace_definition` hat **keinen FK auf `pl_workspace`**, also greift die
Referenzielle Integrität nicht. Alle 401 echten Workspaces haben 11 Keys
(401 × 11 = 4411, + 8 Orphan = 4419 ✓ rechnerisch konsistent).

**Lücke 2 — `link_types.0008` ist eine Datenmigration ohne Re-Run-Mechanismus** (siehe
`wp4-constraints-and-migrations.md`, Abschnitt 3).

→ **AUD-2026-09-155** (Medium), **AUD-2026-09-156** (Low).

## 4. Regeln (Zyklen, Same-Type, Richtung) — werden NICHT überall durchgesetzt

`validate_link_pair` hat **genau eine Produktionsaufrufstelle**:

```
$ rg -n "validate_link_pair" backend --glob "!**/tests/**"
backend\application\trace_link_service.py:365:  from link_types.catalog import validate_link_pair
backend\application\trace_link_service.py:388:  validate_link_pair(
backend\link_types\catalog.py:98:              def validate_link_pair(
(sonst: nur Tests, Migrationen, Kommentare)
```

`TraceLinkManager.create` ruft sie **nicht** auf — es dokumentiert explizit, dass der
Aufrufer sie aufrufen muss (`backend/traceability/trace_link_manager.py:62-73`).
Damit sind alle Layer-1-Einstiege, die direkt `traceability.services.create_trace_link`
aufrufen, Bypass-Pfade:

| # | Bypass-Pfad | Ort | Folge |
|---|---|---|---|
| B1 | **ReqIF-Import** | `backend/application/reqif_import_service.py:886-897` | prüft nur `link_type in VALID_LINK_TYPES` (statische 11er-Liste), schreibt `TraceLink.objects.get_or_create(...)`. **Kein** Katalog, **keine** Paar-Prüfung, **kein** `manual_creatable`-Gate. Eine `.reqif`-Datei kann damit `verifies` Risk→Requirement, `decomposes` Requirement→TestCase oder den system-verwalteten `diagram-ref` manuell anlegen. |
| B2 | **ICD-Connector** | `backend/icd/traceability_connector.py:82-87` → `traceability/services.py:232` → `trace_link_manager.py:334` | ruft `create_trace_link(link_type="decomposes")`; die Prüfung erfolgt **nur** gegen `VALID_LINK_TYPES` (`trace_link_manager.py:62-75`), **keine** Paar-Prüfung gegen den Workspace-Katalog. Belegt vom Kommentar `traceability_connector.py:437`: „which never calls link_types.catalog.validate_link_pair". |
| B3 | **Diagram-Reconciler** | `backend/diagram/traceability_connector.py` | dokumentierter System-Pfad, `manual=False` — das ist **korrekt** und kein Finding. |

→ **AUD-2026-09-326** (ReqIF, High), **AUD-2026-09-327** (ICD, High).

**Zyklenverbot:** `trace_link_manager.py:372-377` filtert `TraceLink.objects.filter(link_type=link_type)`
— die Zyklusprüfung ist **pro Link-Typ**, nicht global (bewusst, `:356-362`). Der
`#1021`-Fix (`:379-392`) deckt nur die *Vereinigung* der Hierarchie-Typen ab
(`HIERARCHY_LINK_TYPES` = `{decomposes, derives-from}`). Für **tenant-eigene** Typen gibt
es keine Union-Prüfung → ein Zyklus über zwei tenant-eigene Typen ist schreibbar.
Ebenso ist ein **Self-Link** (`source_id == target_id`) an keiner Stelle abgelehnt —
weder in `create()` noch in `validate_link_pair` noch in der DB (kein CHECK).

→ **AUD-2026-09-157** (Medium). Kein CR-Duplikat: `CR-15` betrifft den
Update-/Batch-Zyklusvertrag, nicht den create-Pfad und nicht tenant-Typen.

## 5. Reconciliation

| AUD | Klassifikation | Begründung |
|---|---|---|
| 150 | **NEU** | CR-15 = Update/Batch-Zyklusvertrag. Hier: Hierarchie-Semantik + stale Docstring. |
| 151 | **NEU** | ReqIF-Import umgeht den Katalog. `CR-15`/`CR-47` erwähnen den ReqIF-Importer nur als *Zeile*, nicht als Validierungs-Bypass. |
| 152 | **NEU** | ICD-Connector. Kommt in keinem CR-Track vor. |
| 153 | **NEU** | Zahlen-Drift 6/8/10/11. `CR-21` ist MCP-Toolzahlen, nicht Link-Typ-Zahlen. |
| 154 | **NEU** | Widersprüchliche Autoritätsaussage + Public-API-Re-Export. |
| 155 | **NEU** | Orphan in `lt_workspace_definition`. `CR-09` betrifft `workflow/global_definition_store.py` — **anderer** Store. |
| 156 | **NEU** | Datenmigration ohne Re-Run. |
| 157 | **NEU** | Zyklusprüfung pro Typ + Self-Link nicht abgelehnt. |
| 159 | **INFO/PASS** | 4-Ebenen-Konsistenz des Primärkatalogs. |
