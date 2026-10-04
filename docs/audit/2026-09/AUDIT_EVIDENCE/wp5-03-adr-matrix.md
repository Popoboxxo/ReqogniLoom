---
type: REVIEW
scope: wp5-evidence-adr-matrix
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 Evidenz 3 — ADR-Traceability-Prüfung

> Prüfmaßstab: `AGENTS.md`, Abschnitte „SE-Kaskade: ADR-Standard" und
> „SE-Kaskade: Review-Lifecycle"; Schema `schemas/se-adr.schema.json`.
> Bestand: `docs/se/ADR/` = 10 Dateien.

## 1. Ergebnis-Matrix über alle 10 ADRs

| Datei | `affected_reqs` ≥1? | YAML-Frontmatter? | `status` regelkonform? | Lifecycle eingehalten? | Dateiname konform? | `status` |
|---|---|---|---|---|---|---|
| `ADR-001_Sandbox-Mechanismus.md` | ✔ (3) | ✘ **kein** | ✘ `PROPOSED` (uppercase) | offen seit 2026-06-28 | ✘ CamelCase | proposed |
| `ADR-002_Event-Bus.md` | ✔ (3) | ✘ **kein** | ✘ `PROPOSED` | offen seit 2026-06-28 | ✘ CamelCase | proposed |
| `ADR-003_Glossar-Storage.md` | ✔ (3) | ✘ **kein** | ✘ `PROPOSED` | offen seit 2026-06-28 | ✘ CamelCase | proposed |
| `ADR-004_traeger_modell_und_auc.md` | ⚠ `[REQ-147]` — **anderer ID-Raum** | ✔ | ✔ `proposed` | proposed, kein review | ✔ snake_case | proposed |
| `ADR-005_requirement_level_abgeleitet.md` | ✔ (2) | ✔ | ✔ `accepted` | ✘ **Sprung** proposed→accepted | ✔ | accepted |
| `ADR-006_personenfelder_und_freitext.md` | ✔ (2) | ✔ | ✔ `accepted` | ✘ **Sprung** | ✔ | accepted |
| `ADR-007_se_regeln_am_baseline_gate.md` | ✔ (2) | ✔ | ✔ `accepted` | ✘ **Sprung** | ✔ | accepted |
| `ADR-008_moe_mop_tpm_nicht_modelliert.md` | ✔ (2) | ✔ | ✔ `accepted` | ✘ **Sprung** | ✔ | accepted |
| `ADR-009_benachrichtigungen_im_assistenten.md` | ✔ (2) | ✔ | ✔ `accepted` | ✘ **Sprung** | ✔ | accepted |
| `ADR-DS-02_DiagramNodeGraphPositionPersistence.md` | ✔ (3) | ✘ **kein** | ✘ `ACCEPTED` (uppercase) | n/a | ✘✘ **`DS-02` nicht 3-stellig** + CamelCase | accepted |

**Zusammenfassung:**

| Kriterium | erfüllt | verletzt |
|---|---|---|
| `affected_reqs` mit ≥1 REQ-ID | 9/10 | 1 (ADR-004, fremder ID-Raum) |
| YAML-Frontmatter | 6/10 | **4** (001, 002, 003, DS-02) |
| `status` im lowercase-Enum | 6/10 | **4** (PROPOSED/ACCEPTED) |
| Lifecycle `proposed→review→accepted` | 0/6 der akzeptierten | **5** (005-009) |
| Dateiname `ADR-NNN_kurztitel` | 6/10 | **4** |
| Ablage `SE/ADR/` | 10/10 | 0 |
| `superseded_by` korrekt | 6/6 (alle `null`, Status ≠ superseded) | 0 |

## 2. `open_adrs` — vollständig nicht umgesetzt

```
rg -o 'open_adrs' docs --no-filename   →  0
rg -l 'open_adrs' docs backend frontend/src   →  (leer)
```

`AGENTS.md` schreibt vor: *„Jede REQ listet die sie betreffenden, noch nicht
akzeptierten ADRs im Frontmatter-Feld `open_adrs: []`."*

Es existieren **4 offene ADRs** (ADR-001, -002, -003, -004), die zusammen
**11 REQ-IDs** betreffen:

| ADR | betroffene REQ-IDs |
|---|---|
| ADR-001 | `REQ-L1-045`, `REQ-L2-BL-010`, `REQ-L2-RF-017` |
| ADR-002 | `REQ-L1-043`, `REQ-L2-TE-016`, `REQ-L2-VS-002` |
| ADR-003 | `REQ-L1-044`, `REQ-L2-AS-033`, `REQ-L2-RA-014` |
| ADR-004 | `REQ-147` (fremder ID-Raum) |

**0 von 11** REQ-IDs führen `open_adrs`. Die Rückverfolgungsrichtung
REQ → offene ADR ist damit im gesamten Repository nicht implementiert; nur die
Gegenrichtung (ADR → REQ) ist gepflegt.

## 3. `arch_impact: true` REQs ohne ADR-Bezug

`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md` setzt
`arch_impact: true` bei **15** REQ-L1 (Auswertung zeilenweise, Feld steht
jeweils im REQ-Block unter „Architektur-Impact"):

```
REQ-L1-001  REQ-L1-006  REQ-L1-011  REQ-L1-015  REQ-L1-017
REQ-L1-018  REQ-L1-025  REQ-L1-026  REQ-L1-029  REQ-L1-031
REQ-L1-032  REQ-L1-033  REQ-L1-056  REQ-L1-057  REQ-L1-100
```
(einziger `false`: `REQ-L1-042`)

REQs mit ADR-Bezug: **nur `REQ-L1-100`** (ADR-DS-02).

> **14 von 15 `arch_impact: true`-REQ-L1 (93 %) haben keinen ADR-Bezug.**
> `AGENTS.md`: *„Architektur-relevante REQs (`arch_impact: true`) ohne ADR-Bezug
> sind ein Kaskaden-Verstoß."*

Zusätzlich: **kein einziges akzeptiertes ADR referenziert eine REQ-L1 oder
REQ-L2.** Die fünf akzeptierten ADRs (005-009) decken ausschließlich
REQ-L0-IDs ab (`REQ-L0-039, -019, -047, -042, -049, -011, -020, -060, -005`).
Damit ist die gesamte L1-/L2-Architekturentscheidung undokumentiert — bei 15
als architekturrelevant markierten Systemanforderungen.

## 4. `arch_impact` Parent/Child-Widerspruch

`docs/se/L1/Gesamtsystem/L1_clarifications_iter-1.md` setzt `arch_impact: true`
für REQ-L1-034 (ReqIF, Z. 40), REQ-L1-037 (Kommentare, Z. 89) und REQ-L1-038
(Vektorsuche, Z. 106). Die zugehörigen L2-Dokumente drehen das Feld auf `false`:

| REQ-L1 (Eltern) | `arch_impact` | L2-System | REQ-L2 | `arch_impact` | Beleg |
|---|---|---|---|---|---|
| REQ-L1-034 ReqIF | `true` (clarifications:40) | ReqIFServiceSystem | REQ-L2-RQ-001/002 | **`false`** ×2 | `L2_ReqIFServiceSystem_Requirements.md:41,69` |
| REQ-L1-037 Kommentare | `true` (clarifications:89) | CommentServiceSystem | REQ-L2-CM-001/002/003 | **`false`** ×3 | `L2_CommentServiceSystem_Requirements.md:42,70,98` |
| REQ-L1-038 Vektorsuche | `true` (clarifications:106) | VectorSearchServiceSystem | REQ-L2-VS-001..004 | **`false`** ×4 | `L2_VectorSearchServiceSystem_Requirements.md:52,80,108` |

In allen drei Fällen: Parent `true` (erfordert ADR), Child `false`, **kein ADR
vorhanden**. Das ist der direkte Beleg, dass das `arch_impact`-Feld bei der
L2-Ableitung ohne ADR-Bezug umgeschrieben wurde.

## 5. Frontmatter-Pflicht für SE-Dokumente

`AGENTS.md`, „Artefakt-Taxonomie": *„YAML-Frontmatter-Pflicht für alle
SE-Dokumente, mindestens: `type`, `scope`, `status`, `date`, `author_agent`."*

```
docs/se/**/*.md                     = 326 Dokumente
  davon mit YAML-Frontmatter        = 148  (45.4 %)

docs/se/**/*Requirements*.md        = 121 Dokumente
  davon mit YAML-Frontmatter        =  17  (14.0 %)   ← Requirement-Dokumente
docs/se/**/*Architecture*.md        = 101 Dokumente
  davon mit YAML-Frontmatter        =  73  (72.3 %)

docs/se/L0/SN_Stakeholder_Needs.md  = KEIN Frontmatter
  (verwendet stattdessen "> **Level:** L0 … > **Status:** formalisiert")
docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md = KEIN Frontmatter
```

**86 % aller Requirement-Dokumente (104 von 121) verletzen die
Frontmatter-Pflicht.** Das erklärt, warum `open_adrs` und `arch_impact`
strukturell nicht gepflegt werden können: das Feld existiert im Format, das die
Dokumente tatsächlich verwenden, gar nicht.

## 6. Roh-Belege

```
# Frontmatter
Get-ChildItem -Recurse docs/se -Filter *.md | Where-Object { (Get-Content $_ -TotalCount 1) -eq '---' }

# open_adrs
rg -o 'open_adrs' docs --no-filename                       # 0
rg -o 'arch_impact' docs/se/L1 --no-filename | Measure-Object  # 44

# arch_impact:true REQ-Zuordnung (L1)
$lines = Get-Content docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md
for($i=0;$i -lt $lines.Count;$i++){ if($lines[$i] -match '^### (REQ-L1-\d{3})'){$cur=$matches[1]}
  if($lines[$i] -match 'arch_impact'){ "L$($i+1) $cur $($lines[$i].Trim())" } }

# Lifecycle
rg -n '^\*\*Status:\*\*|^status:' docs/se/ADR
```
