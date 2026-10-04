---
type: EVIDENCE
scope: wp4-preset-hardcoding-inventory
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 3 — Rigor-Presets: Hartcodierungs-Inventar

## 1. Antwort auf die Kernfrage

**Die Presets sind *teilweise* datengetrieben und teilweise hartkodiert — und die
hartkodierte Hälfte steuert die fachlich gewichtigere Achse.**

| Achse | Mechanismus | Daten-getrieben? | Hartkodiert? | Wirksam? |
|---|---|---|---|---|
| Feature-Flags (5 Keys) | `PresetConfig.features` (`presets/registry.py:159-213`) | **ja**, Frozen-Dataclass + Registry-Dict | nein | **ja** |
| `mandatory_fields` | `PresetConfig.mandatory_fields` | ja | nein | **nein** (Legacy, `:942-963` meldet „no consumer") |
| Baseline-Scopes | `PresetConfig.baseline_scopes` (`:166,182,214`) | **ja** | nein | **ja** |
| `workflow_configurability` | `PresetConfig` | ja | nein | **ja** |
| `change_reason` | `PresetConfig` | ja | nein | **ja** |
| **Workflow-Graph** | `workflow/definition_store.py:715` | **nein** | **ja, separate Tabelle** | **ja** |
| **Attribut-Stufen** | `attribute_definitions/stage_matrix.py:64-68` `PRESET_STAGE` | **nein** | **ja, separate Tabelle** | **nein** (`stage_mandatory` un konsumiert) |
| **Architektur-Invarianten** | `application/validators.py:55` `RIGOR_INVARIANT_PRESETS` | **nein** | **ja, separate Tabelle** | **ja** |
| **SE-Audit-Regel-Registry** | `traceability/audit/registry.py` („mirrors …RIGOR_INVARIANT_PRESETS") | **nein** | **ja, separate Tabelle** | **ja** |
| **Tier-Mitgliedschaft** | `workflow/transition_validator.py:58` `_PRESET_TIERS` | **nein** | **ja** | **ja** |
| **„proposed"-Ausnahme** | `workflow/definition_store.py:628` `SCHEMAS_WITHOUT_PROPOSED` | **nein** | **ja** | **ja** |
| **N1-Sperre** | `application/architecture_decompose_service.py:351` `if tier == "minimal": raise` | **nein** | **ja, Magic String** | **ja** |
| **Downgrade-Blocker** | `presets/gate.py:536` `if target_tier in ("minimal","standard")` | **nein** | **ja, Magic-Tupel** | **schwach** (fail-open, s. §4) |

**Zählung:** 12 relevante Preset-Achsen, davon **7 datengetrieben** (alle aus
`PresetConfig`/`_DEFAULT_REGISTRY`) und **5+ hartkodiert in mindestens 6 voneinander
unabhängigen Modulen**.

Das ist der Kern: `presets/registry.py:13` deklariert
*„This module is the Single Source of Truth for all preset rule data (ADR-04)"*.
Diese Aussage ist **falsch** — sie gilt nur für die 5 Feature-Flags plus 4 Skalar-Felder.
Workflow-Graphen, Attribut-Stufen, Invarianten-Sätze, Tier-Mitgliedschaft und
`proposed`-Ausnahme liegen in **sechs** getrennten Modulen und sind in `PresetConfig`
**nicht** abgebildet.

→ **AUD-2026-09-160** (High, ADR-Kandidat).

## 2. Zählung der Preset-Referenzen im Code

```
$ rg -c "minimal" backend --glob "*.py" --glob "!**/tests/**"
TOTAL files: 51
TOTAL occurrences: 116
```

Top-Dateien (Vorkommen):

| Datei | n | Art |
|---|---|---|
| `backend/workflow/definition_store.py` | 11 | **funktional** (`:628` `SCHEMAS_WITHOUT_PROPOSED`, `:715` Preset-Graph) |
| `backend/application/architecture_decompose_service.py` | 9 | **funktional** (`:351` N1-Gate) + 6 Kommentar |
| `backend/traceability/audit/registry.py` | 4 | **funktional** (Invarianz-Registry) |
| `backend/application/workspace_provisioning.py` | 4 | **funktional** |
| `backend/presets/gate.py` | 4 | **funktional** (`:280`, `:536`) |
| `backend/presets/registry.py` | 4 | **funktional** (Tier-Literale) |
| `backend/application/change_request_service.py` | 4 | **funktional** (`:74`, `:695`, `:743`, `:981`) |
| `backend/attribute_definitions/stage_matrix.py` | 2 | **funktional** (`PRESET_STAGE`) |
| `backend/application/validators.py` | 2 | **funktional** (`RIGOR_INVARIANT_PRESETS`) |

Funktionale `if preset == …`-Vergleiche in Produktion: **3** (`:351` N1-Gate,
`:536` Downgrade-Ziel, `:1284` Workflow-Konfigurierbarkeit).

Ein gebündeltes Suchen nach `settings.RIGOR_LEVEL` liefert **0 Treffer** — es gibt kein
globales Rigor-Level-Setting, das verstreut geprüft würde. Das ist zugunsten des
Projekts: die Rigor-Entscheidung fließt ausschließlich über `WorkspacePresetConfig`
(1 Zeile pro Workspace), nicht über verstreute Settings.

## 3. Live-Wirkung: der Presetwechsel ist auf der Workflow-Achse wirksam

Read-only, live, ohne Mutation (Login `admin`, `GET` auf
`/api/v1/workflow-defaults/{item_type}/{preset}/`):

| item_type/preset | states | transitions |
|---|---|---|
| `Requirement/minimal` | 2 | 1 |
| `Requirement/standard` | 5 | 5 |
| `Requirement/extended` | 8 | 9 |
| `TestCase/minimal` | 2 | 1 |
| `TestCase/standard` | 5 | 5 |
| `TestCase/extended` | 8 | 9 |

Vollständiger `Requirement/extended`-Graph (live):

```
initial_state: draft
states: draft, proposed, in_review, approved, implemented, verified, deprecated, rejected
transitions: draft→in_review, in_review→approved, approved→deprecated, in_review→draft,
            approved→implemented, implemented→verified, verified→deprecated,
            proposed→draft, proposed→rejected
allowed_roles: draft→in_review [editor,approver,admin]; in_review→approved [approver,admin]; …
requires_change_reason: true (außer proposed→draft)
scope: "global"   updated_at: 2026-09-10T21:15:37Z
```

→ Der Presetwechsel ist auf **Workflow-Graph, Rollen und Change-Reason-Pflicht** nachweisbar
wirksam. `minimal` hat korrekt **kein** `proposed` (spec §4.1 / `definition_store.py:611-628`).

**Verteilung der Presets auf der Live-Instanz:**

```sql
SELECT COALESCE(c.active_tier,'<none>'), count(*)
  FROM pl_workspace w LEFT JOIN pc_workspace_preset_config c ON c.workspace_id=w.id
 GROUP BY 1;
-- extended | 89
-- standard | 311
-- <none>   | 1
-- minimal  | 0        <<<
```

→ **AUD-2026-09-163** (Medium): **kein einziger Workspace ist auf `minimal`.** Alle
`minimal`-spezifischen Zweige (`architecture_decompose_service.py:351`,
`definition_store.py:628/715`, `stage_matrix.py:65`, `audit_service.py:357`) sind auf
dieser Instanz **unverifiziert** — kein Lauf, kein E2E, kein Live-Datenbestand berührt sie.

## 4. `_collect_downgrade_incompatibilities` ist **fail-open**

`backend/presets/gate.py:518-551`

```python
def _collect_downgrade_incompatibilities(self, workspace_id, target_tier):
    issues: List[str] = []
    # Extended → Standard: global baselines must not exist
    if target_tier in ("minimal", "standard"):                      # :536  Magic-Tupel
        try:
            count = BaselineSnapshot.unscoped.filter(
                workspace_id=workspace_id, scope="global").count()  # :538-541
            if count:
                issues.append(f"Downgrade blocked: {count} global baseline…")
        except Exception:                                            # :547
            # PersistenceLayer unavailable in test context; skip check.  :548
            pass                                                      # :549
    return issues
```

Bei `downgrade_policy == "block"` (`gate.py:511-512`) ist `validate_downgrade` das
einzige, was einen Downgrade mit vorhandenen Global-Baselines verhindert. Wirft die
Zählung — RLS-Berechtigung, `OperationalError`, ein Bug —, wird `issues` leer,
`validate_downgrade` gibt `[]` zurück (`:506-507`) und der Downgrade **läuft durch**.

`BaselineSnapshot.unscoped` hebt den Tenant-Manager auf; der Fehlerfall ist damit nicht
hypothetisch, sondern die Designentscheidung schafft genau den Raum, in dem der
`except` greift.

Zweitens ist `:536` ein Magic-Tupel außerhalb der Registry: `PresetConfig` weiß, dass
`global_baselines` nur in `extended` `True` ist (`registry.py:209`), aber der Blocker
prüft gegen eine hartkodierte String-Liste statt gegen das Flag.

→ **AUD-2026-09-162** (High).

## 5. `stage_mandatory` ist geseedet, aber **nirgends konsumiert**

`attribute_definitions/stage_matrix.py:40-47` (Wortlaut):

> „The matrix's `P` (Pflicht) is therefore carried by the additive `stage_mandatory`
> property. It is **seeded and discoverable but deliberately not yet consumed** by
> `attribute_definitions.mandatory_fields`: turning it into an approval gate requires
> the **WS7/AWMS value migration (#940)** …"

Volltextsuche:

```
$ rg -n "stage_mandatory" backend --glob "*.py"
  → stage_matrix.py:29,40,876,887,899,907            (Schreiber)
  → attribute_definitions/tests/test_stage_matrix.py  (Tests)
  → attribute_definitions/tests/test_schema.py:59     (Test-Fixture)
```

**Null Produktionskonsumenten.** Auch `stage_mandatory_names()` — der in
`test_stage_matrix.py:338-342` getestete Leser — hat keinen Produktionsaufrufer.

Damit ist die **Stufen-Differenzierung des Rigor-Presets auf Attributebene nicht wirksam**:
`minimal`/`standard`/`extended` erzeugen zwar unterschiedliche `visible`/`audience`/
`stage_mandatory`-Metadaten (`stage_matrix.py:876-907`), aber kein Approve-Gate liest sie.
Der einzige Gate-Konsument bleibt `mandatory_fields` — und das ist laut
`bootstrap_attribute_definitions.py:942-963` (`unmatched_mandatory_fields`) für die
Built-in-Presets die **leere Menge**.

Nebenbefund: der Docstring zitiert **#940** als offenen Blocker. #940 („Attribut v3 – WS7
AWMS Werte-Migration") ist **geschlossen** und war eine **Daten**-Migration; der echte
offene Nachbar ist **#1112** (Metadaten-Migration). Der Verweis zeigt damit auf einen
geschlossen Vorgang und begründet einen weiterhin bestehenden Zustand.

→ **AUD-2026-09-161** (High), **AUD-2026-09-164** (Low).

## 6. Reconciliation

| AUD | Klassifikation | Begründung |
|---|---|---|
| 160 | **NEU** | `CR-15`/`CR-16`/`CR-17` betreffen TraceLink/Baseline/RLS. Kein CR-Track behandelt die Preset-SSOT-Behauptung. |
| 161 | **NEU** | Kein CR-Track. |
| 162 | **NEU** | `CR-09`/`CR-10` betreffen die *Workflow*-Definition, nicht den Preset-Downgrade-Blocker. |
| 163 | **NEU** | Reine Live-Messung; in der Vor-Audit nicht abgedeckt. |
| 164 | **NEU** | Doku-Drift; `#1104` (AGENTS.md-Zahlen) betrifft MCP-Tool-/Link-Typ-Zahlen, nicht #940/#1112. |
| 165 | **INFO/PASS** | Wirksamkeitsnachweis der Workflow-Achse. |
