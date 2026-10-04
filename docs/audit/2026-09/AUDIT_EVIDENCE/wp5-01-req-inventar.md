---
type: REVIEW
scope: wp5-evidence-req-inventar
status: final
date: 2026-09-29
author_agent: validator
---

# WP-5 Evidenz 1 — REQ-Inventar

> Roh-Evidenz. Alle Kommandos read-only gegen `chore/system-audit-2026-09` @ `75beb750`.
> Regex: `REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}` (deckt `REQ-L0-001`, `REQ-L2-AS-001`,
> `REQ-L2-AppSvc-014`, `REQ-L3-AI001-001`, `REQ-L3-EXP-009` ab).

## 1. Grundgesamtheiten

| Menge | Kommando | eindeutige REQ-L-IDs |
|---|---|---|
| **SOLL-Quelle** `docs/se/L0/` + `docs/se/L1/` (vom Matrix-Generator als Eingabe benannt, `traceability-matrix.md:12-16`) | `rg -o --no-filename 'REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}' docs/se/L0 docs/se/L1 \| Sort-Object -Unique` | **835** |
| **Matrix-Text** `docs/se/traceability-matrix.md` | `rg -o --no-filename <regex> docs/se/traceability-matrix.md \| Sort-Object -Unique` | **511** |

### 1.1 Verteilung nach Ebene

| Ebene | SOLL-Quelle (835) | Matrix-Text (511) |
|---|---|---|
| L0 | 58 | 58 |
| L1 | 94 | 94 |
| L2 | 329 | 305 |
| L3 | 354 | 54 |
| **Summe** | **835** | **511** |

### 1.2 Verteilung L2 nach Subsystem (SOLL-Quelle)

```
AI 8 | AL 9 | AppSvc 15 | AS 44 | AT 20 | BL 12 | CM 3 | CV 5 | DS 12 | ICD 6
LA 10 | MC 21 | PC 14 | PL 18 | RA 28 | RF 37 | RO 6 | RQ 2 | SM 13 | TE 20
VS 4 | WE 10   →  329
```

### 1.3 Verteilung L3 nach Namensraum (SOLL-Quelle)

Zwei inkompatible Schemata nebeneinander:

| Schema | Beispiel | Anzahl |
|---|---|---|
| `REQ-L3-<SUBSYS><NNN>-<NNN>` (komponentengebunden) | `REQ-L3-AS001-001`, `REQ-L3-MC004-002` | 250 |
| `REQ-L3-<TOKEN>-<NNN>` (funktionsgebunden, alt) | `REQ-L3-EXP-001`, `REQ-L3-WHOOK-007`, `REQ-L3-ISSUE-011` | 104 |

## 2. Drift Matrix ↔ Quelle — beide Richtungen

### 2.1 Phantom-REQs (nur in der Matrix, in keiner Quelldatei)

```
PHANTOM_COUNT = 0
```

**Keine.** Die Matrix erfindet keine REQ-ID. Dieser Teil der Kette ist sauber.

### 2.2 Fehlende REQs (in der Quelle, fehlen in der Matrix)

```
MISSING_COUNT = 324
  L0:   0
  L1:   0
  L2:  24
  L3: 300
```

**L2 (24):**

```
REQ-L2-AppSvc-001 REQ-L2-AppSvc-002 REQ-L2-AppSvc-003 REQ-L2-AppSvc-004
REQ-L2-AppSvc-005 REQ-L2-AppSvc-010 REQ-L2-AppSvc-013 REQ-L2-AppSvc-015
REQ-L2-AppSvc-021 REQ-L2-AppSvc-024 REQ-L2-AppSvc-025
REQ-L2-AS-045 REQ-L2-CV-001 REQ-L2-CV-002 REQ-L2-CV-003 REQ-L2-CV-004
REQ-L2-CV-005 REQ-L2-PL-023 REQ-L2-PL-024 REQ-L2-PL-025 REQ-L2-RA-021
REQ-L2-RF-013 REQ-L2-RF-027 REQ-L2-WE-012
```

Fundstellen (Auszug):

| REQ-ID | Quelle |
|---|---|
| `REQ-L2-AppSvc-014` | `docs/se/L1/.../L2_ApplicationServiceSystem_Requirements.json` (26 Treffer) |
| `REQ-L2-AppSvc-014` | `backend/application/import_service.py:5`, `backend/application/tests/test_import_service.py:5` (**Code + Test**) |
| `REQ-L2-AS-045` | `L3_COMP-AS-008_ExportService_Requirements.md`, `L3_COMP-AS-010_SearchService_Requirements.md` |
| `REQ-L2-CV-001..005` | `docs/se/L1/.../L2_DiagramServiceSystem_Requirements.md` |
| `REQ-L2-PL-023..025` | `L3_COMP-PL-001_Requirements.md`, `L3_COMP-PL-002_Requirements.md` |
| `REQ-L2-RA-021` | `L3_COMP-RA-007_Requirements.md` |
| `REQ-L2-RF-013` | `L2_ReactFrontendSystem_Requirements.md` |
| `REQ-L2-RF-027` | `L3_COMP-RF-006_Requirements.md` |
| `REQ-L2-WE-012` | `L2_WorkflowEngineSystem_Architecture.md` |

**L3 (300):** alle 300 fehlenden REQ-L3-IDs sind vollständig in
`docs/se/L1/**/L3_*_Requirements.md` bzw. `L2_*_Requirements.md` belegt. Beispiele:
`REQ-L3-AI001-001`, `REQ-L3-AL003-003`, `REQ-L3-AT003-004`, `REQ-L3-BL004-003`,
`REQ-L3-MC006-001`, `REQ-L3-PC003-004`, `REQ-L3-TE004-003`, `REQ-L3-WE004-003`.

## 3. Interne Konsistenz der Matrix

### 3.1 Eigene Coverage Summary vs. eigene Tabellen

`traceability-matrix.md:649-655` behauptet:

| Ebene | Behauptet (Z. 649-655) | In den eigenen Tabellen zählbar | Gemessen in der Quelle |
|---|---|---|---|
| REQ-L0 | 58 | 58 | 58 ✔ |
| REQ-L1 | 94 | 94 | 94 ✔ |
| REQ-L2 | 290 | 290 (Summe §3.1-§3.20) | **329** ✘ (+39) |
| REQ-L3 | 369 | **0** (keine L3-Tabelle vorhanden) | **354** ✘ (−15) |

`rg -c '^\| REQ-L3-' docs/se/traceability-matrix.md` → **kein Treffer**.
Die Matrix publiziert **keine einzige REQ-L3-Zeile**. Die Zahl 369 stammt aus dem
Generator-Korpus (`scripts/generate_traceability_matrix.py:697`, `:748`), ist aber
aus dem SOLL-Artefakt heraus **nicht nachprüfbar**.

### 3.2 Tote Verweise im eigenen Lücken-Report

`traceability-matrix.md:721` listet 15 `REQ-L2-AppSvc-*` unter
„Verweise auf nicht existierende REQ-IDs". Diese IDs existieren sehr wohl:
26 Treffer in `L2_ApplicationServiceSystem_Requirements.json` plus
`backend/application/import_service.py:5`. Der Matrix-Generator liest das
JSON-Schattendokument nicht, das Markdown schon → Selbstwiderspruch.

### 3.3 L0-Nummerierungslücke

```
REQ-L0-IDs in docs/se/L0/SN_Stakeholder_Needs.md: 58
Lücken in 1..62: 31, 57, 58, 59
```

`traceability-matrix.md:60` springt von `REQ-L0-030` direkt auf `REQ-L0-032`.
`REQ-L0-031` existiert in keiner Datei. `SN_Stakeholder_Needs_Backlog.md`
enthält 0 REQ-L0-IDs.

### 3.4 Doppelte REQ-IDs (aus Matrix §5, Z. 724, bestätigt)

20 IDs tauchen mehrfach als `###`-Überschrift im selben Dokument auf, u. a.
`REQ-L1-085/086/087`, `REQ-L2-AT-017/018`, `REQ-L2-BL-004..009`,
`REQ-L2-CM-001..003`, `REQ-L2-RQ-001/002`, `REQ-L2-VS-001..003`,
`REQ-L3-AS002-004`. Zählregel: „letzter gesetzter Wert gewinnt" (Z. 728) — die
Marker sind damit positionsabhängig und nicht eindeutig.

Zusätzlich gemessen: `L1_Gesamtsystem_Requirements.md` enthält **97**
`###`-REQ-Blöcke bei 94 eindeutigen IDs → 3 Dubletten.

## 4. Code-seitige REQ-Referenzen (außerhalb `docs/`)

```
rg -l 'REQ-L2-AppSvc' backend   →  import_service.py, export_service.py,
                                   tests/test_import_service.py
```

Das heißt: **Backend-Code referenziert ein REQ-Schema (`AppSvc`), das die
Traceability-Matrix als „nicht existent" führt.** Drei ID-Räume existieren
parallel: `REQ-L<level>-<NNN>` (L0/L1), `REQ-L2-<SUB>-<NNN>` (kanonisch),
`REQ-L2-AppSvc-<NNN>` (Legacy, im Code lebend).

## 5. Roh-Kommandos

```powershell
$rx='REQ-L[0-3](?:-[A-Za-z0-9]{2,7})?-[0-9]{3}'
rg -o --no-filename $rx docs/se/L0 docs/se/L1 | Sort-Object -Unique   # 835
rg -o --no-filename $rx docs/se/traceability-matrix.md | Sort-Object -Unique  # 511
rg -c '^\| REQ-L3-' docs/se/traceability-matrix.md                    # 0
rg -o 'REQ-L0-[0-9]{3}' docs/se/L0/SN_Stakeholder_Needs.md --no-filename | Sort-Object -Unique | Measure-Object
```
