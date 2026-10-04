---
type: EVIDENCE
scope: wp4-baseline-and-artifact-model
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 6 — Baselines (3 Scopes) + Generic Artifact Model

## Teil A — Baselines

### A.1 Anzahl der Scopes: 3, konsistent über alle Ebenen

| Ebene | Ort | Wert |
|---|---|---|
| Modell-Docstring | `backend/baseline/services.py:322-329` | `document` / `project` / `global` |
| Code-Dispatch | `backend/baseline/services.py:360-364` | `if scope not in ("document","project","global"): raise ValueError` |
| Registry-Daten | `backend/presets/registry.py:166,182,214` | `minimal: ()`, `standard: ("document","project")`, `extended: ("document","project","global")` |
| Registry-Validierung | `backend/presets/registry.py:129-133` | `known_scopes = ("document","project","global")` — **zweite, hartkodierte Scope-Liste** |
| Delta-Index-Builder | `backend/baseline/delta_index_builder.py:250` | `scope == "document"`-Zweig |
| Live-DB | `bl_baseline_snapshot` | 17 `document` + 21 `project` + **0 `global`** |

→ Die **Anzahl 3 stimmt** mit `AGENTS.md` (ADR-07) überein.

**Aber: die 3 Scopes sind nicht überall verfügbar.** `_MINIMAL.baseline_scopes = ()`
(`registry.py:166`) heißt: ein `minimal`-Workspace kann **gar keine** Baseline anlegen.
`global` ist `extended` vorbehalten (`registry.py:180-181, 214`). Und
`validate_downgrade` (`gate.py:536`) blockiert den Weg zurück, auf dem man `global`
sonst erzeugen würde.

**Live-Beleg der Wirksamkeit (read-only, `GET`):** s. `wp4-preset-hardcoding-inventory.md` §3.

**Live-Beleg der *Nicht*-Abdeckung:**

```sql
SELECT scope, count(*) FROM bl_baseline_snapshot GROUP BY 1 ORDER BY 1;
-- document | 17
-- project  | 21
-- global   |  0     <<< der 3. Scope ist auf der Live-Instanz ungenutzt
```

→ **AUD-2026-09-173** (Medium): Der `global`-Scope ist implementiert, validiert und
dokumentiert, aber auf der Live-Instanz **null** mit Daten belegt. Sein Code-Pfad
(workspace_id wird bewusst ignoriert, `services.py:327-328, 398-406`) ist damit
**nicht ausgeführt verifiziert** — inklusive der Leserwartung, dass ein `global`-Snapshot
Artefakte **tenantweit** enthält, die dann in Workspaces ohne Baseline-Erlaubnis
sichtbar werden.

### A.2 Scope-Trennung — kein Datenleck zwischen den Scopes messbar

`backend/baseline/services.py:370-451`, drei disjunkte SQL-Zweige:

| Scope | Filter | live verifiziert |
|---|---|---|
| `document` | `a.workspace_id = %s AND a.tenant_id = %s` + rekursiver CTE über `parent_id` ∪ `derives-from` (`:420-451`) | 5 Parameter, alle gebunden |
| `project` | `a.workspace_id = %s AND a.tenant_id = %s` (`:380-397`) | 2 Parameter |
| `global` | `a.tenant_id = %s` — **`workspace_id` bewusst ignoriert** (`:398-406`) | 1 Parameter |

**Tenant-Isolation in allen drei Zweigen vorhanden** (`:374, 384, 402` je `tenant_id = %s`).
Kein Scope-Zweig fehlt den Tenant-Filter — das ist der entscheidende Punkt, weil `global`
per Definition workspace-übergreifend ist.

**Cross-Scope-Kontamination, live gemessen:** TraceLinks sind streng workspace-gebunden,
sodass ein `global`-Snapshot keine fremden Workspaces erfassen kann:

```sql
-- 0: TraceLink über Workspace-Grenzen hinweg
SELECT count(*) FROM pl_tracelink t
  JOIN pl_artifact s ON s.id=t.source_id
  JOIN pl_artifact g ON g.id=t.target_id
 WHERE s.workspace_id IS DISTINCT FROM g.workspace_id;                  -- 0
-- 0: TraceLink über Tenant-Grenzen hinweg
SELECT count(*) FROM pl_tracelink t
  JOIN pl_artifact s ON s.id=t.source_id
  JOIN pl_artifact g ON g.id=t.target_id
 WHERE s.tenant_id<>g.tenant_id OR s.tenant_id<>t.tenant_id
    OR g.tenant_id<>t.tenant_id;                                        -- 0
```

→ **PASS** für die Scope-Trennung auf Tenant-Ebene. Die *innerhalb* eines Tenants
gewollte `global`-Semantik (Tenant-weit statt Workspace-weit) ist per Definition ein
bewusstes Überschreiten der Workspace-Grenze und dokumentiert (`:327-328`).

**Einschränkung, die ich nicht ausräumen konnte (BLOCKED):** die *Vollständigkeit* des
`global`-Snapshots (enthält er alle Artefakte des Tenants, auch aus Workspaces ohne
Baseline-Freigabe?) ist **nicht** read-only entscheidbar, weil es 0 `global`-Snapshots
gibt. Der Code ist statisch korrekt (`:398-406` filtert nur `tenant_id`).

### A.3 Diff-Engine — Korrektheits-Stichprobe

`backend/baseline/diff_engine.py` wurde **nicht** ausgeführt (kein Testlauf, kein
`pytest`, keine Mutation). Die statische Prüfung beschränkt sich auf zwei bereits
bekannte Punkte:

- `CR-16` („DiffEngine verschluckt Store-/RLS-Fehler", `baseline/diff_engine.py:109-177`)
  — **nicht** eigenständig nachgemessen, aber auch **nicht** widerlegt.
- `CR-16` („VCRM akzeptiert `baseline_id`, lehnt Snapshot-Abdeckung aber ab",
  `traceability/coverage_calculator.py:216-262`) — **nicht** eigenständig nachgemessen.

→ **AUD-2026-09-190** — **BLOCKED**, ausdrücklich: *nicht verifizierbar ohne
Datenmutation*. Wird als **kein PASS** geführt.

### A.4 `known_scopes` doppelt

`presets/registry.py:129` `known_scopes = ("document","project","global")` ist eine
**zweite** hartkodierte Scope-Liste neben `PresetConfig.baseline_scopes` (`:166,182,214`)
und neben `baseline/services.py:360`. Drei Stellen, ein Fakt. Bei einer künftigen
Scope-Erweiterung muss `known_scopes` zuerst erweitert werden, sonst wirft
`is_scope_allowed` `ScopeNotAvailableError` — **bevor** `baseline_scopes` überhaupt
 consulted wird.

→ **AUD-2026-09-175** (Low).

## Teil B — Generic Artifact Model

### B.1 Die tatsächliche Typenliste

```sql
SELECT artifact_type, count(*) FROM pl_artifact GROUP BY 1 ORDER BY 2 DESC;
-- Requirement|2112   ArchitectureElement|502   StakeholderNeed|176   TestCase|126
-- Icd|124            Diagram|111                Issue|76
-- TestCase:Unit|69   Risk|59                    Adr|33
-- TestCase:System|30 GlossaryTerm|15            Interview|9
```

**13 verschiedene `artifact_type`-Werte** bei 3062 Artefakten. Davon **2 keine Typen,
sondern Sub-Typ-Tags** (`TestCase:Unit` 69, `TestCase:System` 30) — 99 Zeilen,
**3,2 %** des Bestands. Siehe `wp4-constraints-and-migrations.md` §2.2.

### B.2 Drei parallele, voneinander unabhängige Typ-Registries

| Registry | Ort | Umfang | Abweichung |
|---|---|---|---|
| **A** Attribut-Definitionen | `backend/attribute_definitions/schema.py:22` `ITEM_TYPES` | **11**: Adr, ArchitectureElement, ChangeRequest, GlossaryTerm, Goal, Icd, Issue, Requirement, Risk, StakeholderNeed, TestCase | **kein** Diagram, **kein** Interview, **keine** getaggten Varianten |
| **B** Suche / MCP-Enum | `backend/application/search_service.py:183-244` `_TABLE_SPECS` | **10**: Requirement, ArchitectureElement, TestCase, StakeholderNeed, Adr, Risk, Issue, ChangeRequest, Goal, GlossaryTerm | **kein** Icd, **kein** Diagram, **kein** Interview |
| **C** tatsächliche Daten | `pl_artifact.artifact_type` | **13** (s. B.1) | 3 Varianten, die in A und B nicht existieren |

Registry B ist ausdrücklich als SSOT deklariert
(`search_service.py:248-250`: *„Public, stable view of the searchable artifact types —
the **single source of truth** for the `type_filter` enum published by MCP
`artifact.search`"*) — gilt aber nur für die Suche. Live-Beleg: `pl_artifact` führt
124 `Icd`-, 111 `Diagram`- und 9 `Interview`-Artefakte, die **über MCP-Suche nicht
auffindbar** sind.

→ **AUD-2026-09-187** (Medium). **Antwort auf die Auftragsfrage „ist das Modell wirklich
generisch":** Das *Datenmodell* ist generisch (ein `pl_artifact` + `artifact_type`-String
+ `custom_fields`-JSON, plus je Entity-Typ eine schmale typed Extension-Tabelle). Die
*Typenverwaltung* ist es nicht: es gibt drei handgepflegte, auseinanderlaufende Listen,
von denen keine aus der anderen abgeleitet ist. Eine neue Entity-Art muss in **allen
drei** plus in `builtin.py`-`allowed_pairs` plus im Frontend registriert werden.

### B.3 Wie Entity-Typen registriert werden — datengetrieben oder hartkodiert?

Antwort: **beides, mit klarer Trennlinie.**

| Aspekt | Mechanismus | Datengetrieben? |
|---|---|---|
| Katalog der Link-Endpunkt-Paare | `link_types/builtin.py:78` `BUILTIN_LINK_TYPES[*]["allowed_pairs"]` (Daten, keine Code-Verzweigung) + `lt_workspace_definition` | **ja** |
| Attribut-Definitionen | `ad_global_definition` / `ad_workspace_definition`, JSONField, per `(item_type, preset)` | **ja** |
| Workflow-Definitionen | `we_engine_definition.workflow_json`, per `(workspace, item_type, preset)` | **ja** |
| **Erlaubte `item_type`-Werte** | `attribute_definitions/schema.py:22` `ITEM_TYPES` (Python-Tupel) | **nein** |
| **Suchbare Typen + MCP-Enum** | `search_service.py:183-244` (Python-Dict mit 10 Einträgen) | **nein** |
| **Erlaubte Presto-Tiers** | `workflow/transition_validator.py:58` `_PRESET_TIERS` | **nein** |
| **Prüfbare Rigor-Invarianten** | `application/validators.py:55` `RIGOR_INVARIANT_PRESETS` | **nein** |
| **Frontend-Routen pro Typ** | `frontend/src/utils/artifactRoutes.ts:31` | **nein** |
| **Link-Typ-Frontend-Labels** | `frontend/src/constants/traceLinkLabels.ts:42-87` (11, bewusst Fallback) | teilweise |
| **TraceLink-Payload-Pfad** | `TraceLinkSerializer` (`:1394`) + `pl_tracelink` | **ja** |

**Bilanz:** die *Daten* (Definitionen, Kataloge, Paare) sind sauber datengetrieben und
pro Tenant materialisiert. Die *zulässigen Namen* sind an 5+ Stellen hartkodiert.
Das ist der übliche und akzeptable Zuschnitt — aber es ist die Ursache von B.2, und
B.2 ist messbar.

### B.4 Frontend-Routen vs. Backend-Typen

`frontend/src/utils/artifactRoutes.ts:31` `TestCase: "/testcases"` — die getaggten
Varianten sind dort **nicht** abgebildet. Für einen `artifact_type="TestCase:Unit"`
liefert der Frontend-Router damit keinen Pfad. Das ist derselbe 99-Zeilen-Defekt wie
in `wp4-constraints-and-migrations.md` §2.2, an der UI-Kante.

→ Teil von **AUD-2026-09-181** (kein separates Finding; gleiche Ursache, anderes Symptom).

## Teil C — Reconciliation

| AUD | Klassifikation | Begründung |
|---|---|---|
| 173 | **NEU** | `CR-16` behandelt VCRM-`baseline_id` und DiffEngine-Fehler-Verschlucken, nicht die Scope-Abdeckung. |
| 175 | **NEU** | Kein CR-Track; `CR-15`/`CR-16` sind andere Punkte. |
| 187 | **NEU** | Kein CR-Track behandelt die drei Typ-Registries. |
| 190 | **BLOCKED** | DiffEngine-Korrektheit ohne Testlauf nicht messbar. Ausdrücklich **kein PASS**. |
