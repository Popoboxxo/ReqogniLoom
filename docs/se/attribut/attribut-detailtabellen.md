# Attribut-Modell für die Artefakt-Masken — 3-Stufen-Vorschlag

**Stand:** 11.09.2026 · Basis **v1.8.0-beta.10** (`b4c3a91`) · Autor: SE/RE/Test-Expertenanalyse
**Auftrag:** Welche Attribute sollen in welcher Maske in welcher Stufe stehen — und was fehlt heute.
**Legende:** ✅ vorhanden · ➕ neu vorzuschlagen · ⚠️ **wird gefordert, existiert aber nicht** · ◐ vorhanden, aber unzureichend

---

## 0. Der wichtigste Befund vorab — es gibt heute KEINE Stufen

Ich habe die **live ausgelieferten** Attribut-Definitionen aller 11 Artefakttypen × 3 Presets aus der QS
gezogen (`/api/v1/attribute-defaults/{type}/{preset}/`, Rohdaten: `attr_bestand.json` (Rohdaten, nicht eingecheckt)):

```
Requirement/minimal    n=11   Requirement/standard   n=11   Requirement/extended  n=11
StakeholderNeed/…      n=6    TestCase/…             n=6    Risk/…                n=12   …
```

**Die Attributliste und die `required`-Flags sind über alle drei Presets IDENTISCH.**
Pflicht ist überall nur `title` (und `status`, das die Workflow-Engine füllt). Im Requirement sind
`description` und `acceptance_criteria` in **allen** Presets optional — obwohl `presets/registry.py:170`
für `standard` genau diese als `mandatory_fields` deklariert und `:186` für `extended` zusätzlich
`classification`, `traceability_target`, `change_reason`.

Außerdem existieren die geforderten Felder teils **gar nicht als Attribut**:

| Preset fordert (`presets/registry.py`) | Attribut vorhanden? |
|---|---|
| `title` (minimal/standard/extended) | ✅ |
| `description` (standard/extended) | ✅ vorhanden, aber `required=false` |
| `acceptance_criteria` (standard/extended) | ✅ vorhanden, aber `required=false` |
| **`priority`** (standard/extended) | ⚠️ **Attribut existiert nicht** |
| **`classification`** (extended) | ⚠️ existiert nicht (nur `category`/`type`/`level`) |
| **`traceability_target`** (extended) | ⚠️ existiert nicht |

→ Das ist die Ursache des bereits gemeldeten **#912** („Preset mandatory_fields laufen ins Leere").
Für StakeholderNeed/TestCase/Adr/Risk/Issue/Goal ist es noch schärfer: dort greift die **Requirement**-
`mandatory_fields`-Liste, deren Feldnamen es in diesen Modellen nicht gibt.

**Fazit:** Die drei Presets sind heute nur **Feature-Schalter** (Baselines, Workflows, change_reason),
aber **kein Attribut-Stufenmodell**. Genau das schlage ich unten vor.

---

## 1. Normative Grundlage (recherchiert)

| Quelle | Inhalt | Wofür im Modell |
|---|---|---|
| **ISO/IEC/IEEE 29148:2018** §5.2.8 „Requirements attributes" | Attributkatalog für Anforderungen | Requirement, StakeholderNeed |
| **ISO/IEC/IEEE 29148:2018** §8.3/§9.3 BRS, §9.4 StRS, §8.4 SyRS | Inhaltsstruktur Business-/Stakeholder-/System-Requirements | Gliederung + Gruppen |
| **ISO/IEC/IEEE 29148:2018** §5.2.5/5.2.6 | Characteristics of individual/set of requirements (notwendig, eindeutig, verifizierbar, …) | Pflichtkriterien je Stufe |
| **ISO/IEC/IEEE 15288:2015** | Life-Cycle-Prozesse; funktionale/allokierte/physische Baseline | ArchitectureElement, Baseline, ChangeRequest |
| **ISO/IEC/IEEE 42010:2022** | Stakeholder, Concern, Viewpoint, View, **Architecture Rationale**, Correspondence | ArchitectureElement, Adr |
| **ISO/IEC/IEEE 29119-3:2021** §8.3–8.11 | Test case: identifier, objective, pre/postconditions, inputs, expected results, priority, traceability | TestCase |
| **BABOK v3 / ISO 29148 BRS** | Business purpose, mission/goals/objectives, major stakeholders, operational modes/quality, constraints | StakeholderNeed, Goal |
| **INCOSE SE Handbook / NASA NPR 7123.1** | MOP/TPM (Measures of Performance / Technical Performance Measures) | Goal |
| **ISO 31000** | Risiko: Identifikation, Bewertung, Behandlung (avoid/reduce/transfer/accept), Restrisiko | Risk |

**Der klassische 29148-Attributkatalog** (ReqView-Mapping des Standards):
`Id · Heading · Text · Owner · Priority · Source · Rationale · Difficulty · Type · Status · Verification Method`
— ergänzt um `Risk` und `Stakeholder Priority` aus §5.2.8 der Vorgängerfassung.

**ISO 29119-3 Testfall-Elemente:**
`identifier · objective · pre-/postconditions · inputs/actions (steps) · expected results · priority · traceability`

---

## 2. Die drei Stufen — Definition

| Stufe | Name | Leitidee | Wirkung |
|---|---|---|---|
| **1** | **Basissatz (additiv)** | „Ein Artefakt ist anlegbar, identifizierbar, auffindbar." Alles Weitere **optional**. Kein Arbeitsfluss wird blockiert. | keine Pflicht-Hürden, `required` nur auf 2–3 Feldern |
| **2** | **Gehobene Stringenz** | „Ein Artefakt ist bewertbar, prüfbar, begründet." Eselsbrücke: **wer will es, warum, wie prüfen wir es, wie wichtig.** | `required` + Workflow-Gates auf Attribut-Ebene |
| **3** | **Full-Blown Systems Engineering** | „Ein Artefakt ist Teil einer lückenlosen SE-Kette." Vollständige Rückverfolgbarkeit, Risiko, Kritikalität, MOP/TPM, Baseline/Change Control. | alle SE-Auditor-Regeln greifen; Baseline-fähig |

**Gruppierung (Sections)** — gilt für alle Typen, sofern zutreffend:
1. **Identifikation** · 2. **Inhalt** · 3. **Klassifikation** · 4. **Attributierung/Qualität** ·
5. **Verifikation/Validierung** · 6. **Traceability** · 7. **Änderungskontrolle** · 8. **Typ-spezifisch**

---

## 3. Requirement (Anforderung) — 11 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid` | text | ✅P | ✅P | ✅P | ✅ (auto) | 29148 Id |
| Identifikation | `title` / Heading | text | ✅ | ✅ | ✅ | ✅ | 29148 Heading |
| Inhalt | `description` (Text) | textarea | ○ | **✅P** | ✅P | ◐ optional | 29148 Text |
| Inhalt | `acceptance_criteria` | textarea | ○ | **✅P** | ✅P | ◐ optional | 29148 §5.2.5 |
| Klassifikation | `type` (funktional/nicht-funktional/…) | enum | ○ | ✅ | ✅ | ✅ | 29148 Type |
| Klassifikation | `level` (L1–L4) | enum | ○ | ✅ | ✅ | ✅ | 15288 |
| Klassifikation | **`priority`** | enum (Must/Should/Could/Won't) | ○ | **✅P** | ✅P | ⚠️ **fehlt** | 29148 Priority |
| Klassifikation | **`difficulty`** | enum | – | ○ | ✅ | ➕ neu | 29148 Difficulty |
| Klassifikation | **`criticality`** (safety/security) | enum (ASIL/DAL/Klasse) | – | ○ | ✅ | ➕ neu | ISO 26262/IEC 61508 |
| Attributierung | **`source`** | text | – | **✅P** | ✅P | ➕ **fehlt** | 29148 Source |
| Attributierung | **`rationale`** | textarea | – | **✅P** | ✅P | ➕ **fehlt** | 29148 Rationale |
| Attributierung | **`owner`** | user | – | ○ | ✅ | ➕ neu | 29148 Owner |
| Attributierung | `status` | enum (workflow) | ✅ | ✅ | ✅ | ✅ | Workflow |
| Verifikation | `verification_method` | enum (T/D/I/A) | – | **✅P** | ✅P | ✅ vorhanden | 29148 VerMethod |
| Verifikation | **`verification_status`** | enum | – | ○ | ✅ | ➕ neu | 29148 |
| Verifikation | **`validation_method`** | enum | – | – | ✅ | ➕ neu | 29148 §5.2.5 |
| Traceability | `allocated-to` (Systemelement) | reference | ○ | **✅P** | ✅P | ✅ als TraceLink | siehe #928 |
| Traceability | `derives-from` (Bedarf) | reference | ○ | ✅ | ✅P | ✅ als TraceLink | 29148 |
| Traceability | **`mop_tpm_ref`** | reference | – | – | ✅ | ➕ neu | INCOSE/NASA |
| Traceability | **`origin_link`** (Quelle im Dokument) | text | – | ○ | ✅ | ➕ neu | 29148 §5.2.8 |
| Änderungskontrolle | `change_reason` | textarea | – | ○ | **✅P** | ✅ (Preset-gated) | 15288 |
| Typ-spezifisch | `complexity_fibonacci` | enum | – | ○ | ○ | ✅ vorhanden | – |

**Fehlende Muss-Attribute:** `priority`, `source`, `rationale` — die drei Kernattribute des ISO-29148-
Katalogs fehlen komplett. Ohne `priority` ist die Preset-Pflicht aus `standard`/`extended` **nicht
erfüllbar**.

---

## 4. StakeholderNeed (Bedarf) — 6 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title` | text | ✅ | ✅ | ✅ | ✅ | 29148 Id/Heading |
| Inhalt | `description` | textarea | ✅ | ✅ | ✅ | ◐ optional | StRS |
| Klassifikation | `category` | text | ○ | ✅ | ✅ | ✅ | StRS |
| Klassifikation | `moscow_priority` | enum | – | ✅ | ✅ | ✅ vorhanden | StRS/Priority |
| Attributierung | **`stakeholder`** (Rolle/Gruppe) | text/user | – | **✅P** | ✅P | ➕ **fehlt** | 42010 Stakeholder |
| Attributierung | **`rationale`** | textarea | – | ✅ | ✅P | ➕ **fehlt** | StRS „purpose" |
| Attributierung | **`owner`** | user | – | ○ | ✅ | ➕ neu | 29148 Owner |
| Attributierung | **`concern`** (42010) | enum/multi | – | ○ | ✅ | ➕ neu | 42010 |
| Verifikation | **`validation_criteria`** | textarea | – | ○ | ✅ | ➕ neu | 29148 §5.2.5 |
| Traceability | **`effect_measure`** (KPI) | text | – | – | ✅ | ➕ neu | INCOSE MOP |
| Traceability | `derived-to` (→ Requirement) | reference | ○ | ✅ | ✅ | ✅ als TraceLink | 29148 |
| Attributierung | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

**Lücke:** Kein `stakeholder`-Feld — bei einem „Stakeholder Need" das zentrale Attribut. `rationale`
und `validation_criteria` fehlen (ohne sie ist eine Bedarfs-Validierung nicht belegbar).

---

## 5. ArchitectureElement (Systemelement) — 9 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title`, `element_type` | text | ✅ | ✅ | ✅ | ✅ | 42010 |
| Inhalt | `description` | textarea | ○ | ✅ | ✅ | ◐ optional | 42010 |
| Struktur | `parent_id` | reference | ○ | ✅ | ✅ | ✅ | 42010 Composition |
| Klassifikation | **`viewpoint`/`view`** | enum | – | – | ✅ | ➕ neu | 42010 Viewpoint |
| Klassifikation | **`criticality`/`safety_level`** | enum | – | ○ | ✅ | ◐ `asil_level` vorhanden | 42010/26262 |
| Klassifikation | `make_or_buy` | enum | – | ○ | ✅ | ✅ vorhanden | 15288 |
| Klassifikation | **`technology`** | text | – | ○ | ✅ | ➕ neu | 42010 |
| Attributierung | **`rationale`** (Arch. Rationale) | textarea | – | ○ | ✅ | ➕ neu | **42010 explizit** |
| Verifikation | **`verification_method`** | enum | – | ○ | ✅ | ➕ neu | 15288 |
| Traceability | `allocated-to` (eingehend, Anforderungen) | reference | ○ | ✅ | ✅ | ✅ als TraceLink | #928 |
| Traceability | **ICD-Kanten** (Schnittstellen) | reference | ○ | ✅ | ✅ | ✅ via Icd-Typ | 42010 Correspondence |
| Traceability | **`performance_budget`** | number/text | – | – | ✅ | ➕ neu | INCOSE TPM |
| Änderungskontrolle | `change_reason` | textarea | – | ○ | ✅ | ✅ | 15288 |

**Lücke:** 42010 verlangt **Architecture Rationale** ausdrücklich — fehlt. Kein Viewpoint/View-Feld.
Keine Schnittstellen-Sektion in der Maske (ICDs existieren als eigener Typ, sind aber nicht aus dem
Element heraus bedienbar).

---

## 6. TestCase (Testfall) — 6 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title` | text | ✅ | ✅ | ✅ | ✅ | 29119-3 identifier |
| Inhalt | **`objective`** | textarea | – | ✅ | ✅P | ➕ **fehlt** | 29119-3 objective |
| Inhalt | `description` | textarea | ○ | ✅ | ✅ | ◐ optional | 29119-3 |
| Inhalt | `steps` | widget | ✅ | ✅ | ✅ | ✅ | 29119-3 inputs/actions |
| Inhalt | **`preconditions`** | textarea | – | **✅P** | ✅P | ➕ **fehlt** | 29119-3 pre |
| Inhalt | **`postconditions`** | textarea | – | ○ | ✅ | ➕ neu | 29119-3 post |
| Inhalt | **`expected_result`** | textarea | – | **✅P** | ✅P | ➕ **fehlt** | 29119-3 outcomes |
| Klassifikation | `test_type` | enum | ○ | ✅ | ✅ | ✅ | 29119-3 |
| Klassifikation | **`test_level`** (Unit/Integration/System/Acceptance) | enum | – | ○ | ✅ | ➕ neu | 29119-3 |
| Klassifikation | **`priority`** | enum | – | ✅ | ✅ | ➕ **fehlt** | 29119-3 priority |
| Attributierung | **`author`**, **`review_status`** | user/enum | – | ○ | ✅ | ➕ neu | 29119-3 |
| Verifikation | **`test_data`** | textarea | – | ○ | ✅ | ➕ neu | 29119-3 §8.5 |
| Verifikation | **`test_environment`** | textarea | – | – | ✅ | ➕ neu | 29119-3 §8.6 |
| Traceability | **`verifies`** (→ Requirement) | reference | ○ | **✅P** | ✅P | ✅ als TraceLink | 29119-3 traceability |
| Typ-spezifisch | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

**Lücke, schwerwiegend:** Ein Testfall ohne **erwartetes Ergebnis**, **Vorbedingung**, **Ziel** und
**Priorität** ist nach 29119-3 **kein dokumentierter Testfall** — der Typ hat heute nur `steps`.
Die Traceability-Kante `verifies` existiert als Link, ist aber nicht als Pflicht verankert.

---

## 7. Adr (Architekturentscheidung) — 8 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title` | text | ✅ | ✅ | ✅ | ✅ | MADR |
| Inhalt | `context`, `decision`, `consequences` | textarea | ✅ | ✅ | ✅P | ✅ | MADR |
| Inhalt | **`alternatives`** (betrachtete Optionen) | textarea | – | **✅P** | ✅P | ➕ **fehlt** | 42010 Rationale |
| Inhalt | **`decision_drivers`** | text/list | – | ○ | ✅ | ➕ neu | MADR |
| Attributierung | **`deciders`**, **`decided_at`** | user/date | – | ✅ | ✅ | ➕ **fehlt** | MADR |
| Attributierung | `status` | enum | ✅ | ✅ | ✅ | ✅ | MADR |
| Traceability | **`supersedes`/`superseded_by`** | reference | – | ✅ | ✅ | ➕ **fehlt** | MADR |
| Traceability | **`affects`** (Requirement/Arch) | reference | – | ○ | ✅ | ➕ neu | 42010 |
| Attributierung | `decision_record` | widget | ○ | ✅ | ✅ | ✅ | – |

**Lücke:** `alternatives` fehlt — eine ADR ohne verworfene Optionen ist nach 42010 keine
Architecture Rationale. `supersedes` fehlt, obwohl im Frontend bereits ein `AdrSupersedePanel` existiert.

---

## 8. Risk (Risiko) — 12 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title`, `description` | text | ✅ | ✅ | ✅ | ✅ | ISO 31000 |
| Klassifikation | `category`, `probability`, `impact`, `detection` | enum/num | ○ | ✅ | ✅ | ✅ | ISO 31000 |
| Klassifikation | `risk_matrix` | widget | – | ✅ | ✅ | ✅ | – |
| Klassifikation | **`risk_type`** (Chance/Bedrohung) | enum | – | ○ | ✅ | ➕ neu | ISO 31000 |
| Klassifikation | **`severity`/RPN** (abgeleitet) | number | – | ✅ | ✅ | ➕ (ableitbar) | ISO 31000 |
| Klassifikation | **`residual_risk`** | enum | – | ○ | ✅P | ➕ **fehlt** | ISO 31000 |
| Attributierung | `owner`, `owner_user_id` | text/user | ○ | ✅ | ✅P | ✅ | ISO 31000 |
| Attributierung | `mitigation_strategy` | textarea | ○ | ✅ | ✅ | ✅ | ISO 31000 |
| Attributierung | **`response_strategy`** | enum (avoid/reduce/transfer/accept) | – | ○ | ✅ | ➕ neu | ISO 31000 |
| Attributierung | **`review_cycle`/`due_date`** | date | – | ○ | ✅ | ➕ neu | ISO 31000 |
| Traceability | **`affects`** (betroffene Artefakte) | reference | – | ○ | ✅ | ➕ neu | ISO 31000 |
| Typ-spezifisch | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

**Vergleichsweise gut.** Es fehlen Restrisiko, Behandlungsstrategie und die Verknüpfung zu den
betroffenen Artefakten (heute nur als freie TraceLinks möglich).

---

## 9. Issue (Problem) — 8 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `uid`, `title`, `description` | text | ✅ | ✅ | ✅ | ✅ | – |
| Klassifikation | `category`, `severity` | enum | ○ | ✅ | ✅ | ✅ | – |
| Klassifikation | **`priority`** | enum | – | ✅ | ✅ | ➕ **fehlt** | – |
| Attributierung | **`assignee`** | user | – | ✅ | ✅P | ➕ **fehlt** | – |
| Attributierung | `due_date`, `tag_list` | date/widget | – | ✅ | ✅ | ✅ | – |
| Verifikation | **`resolution`**, **`root_cause`** | textarea | – | ○ | ✅ | ➕ neu | 8D/CAPA |
| Traceability | **`affects`** (Artefakte) | reference | – | ○ | ✅ | ➕ neu | – |
| Typ-spezifisch | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

---

## 10. Goal (Ziel) — 3 Attribute heute ⚠️ dünnster Typ

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `title`, `description` | text | ✅ | ✅ | ✅ | ✅ | BRS |
| Klassifikation | **`priority`** | enum | – | ✅ | ✅ | ➕ **fehlt** | BRS |
| Attributierung | **`owner`**, **`timeframe`** | user/date | – | ✅ | ✅P | ➕ **fehlt** | BRS |
| **Messgröße** | **`measure`** (MOP/TPM) | text | – | ○ | **✅P** | ➕ **fehlt** | INCOSE/NASA |
| **Messgröße** | **`target_value`**, **`unit`**, **`threshold`** | number/text | – | – | **✅P** | ➕ **fehlt** | INCOSE/NASA |
| Traceability | **`parent_goal`** | reference | – | ○ | ✅ | ➕ neu | BRS |
| Traceability | **`addresses`** (Bedarf) | reference | – | ○ | ✅ | ➕ neu | BRS |
| Typ-spezifisch | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

**Kritisch:** Ein Ziel ohne **Messgröße und Zielwert** ist nicht überprüfbar. Genau das fordert die
Zielpyramide (Mission → Goal → MOP → TPM → Requirement) in INCOSE/NASA. Der Typ hat heute 3 Felder.

---

## 11. Icd (Schnittstellenspezifikation) — 7 Attribute heute

| Gruppe | Attribut | Typ | S1 | S2 | S3 | Bestand | Quelle |
|---|---|:--:|:--:|:--:|:--:|---|---|
| Identifikation | `name`, `source_element_id`, `target_element_id` | text/ref | ✅ | ✅ | ✅ | ✅ | 42010 Correspondence |
| Klassifikation | `direction`, `interface_type` | enum | ✅ | ✅ | ✅ | ✅ | – |
| Inhalt | `semantic_description` | textarea | ○ | ✅ | ✅ | ◐ optional | – |
| Inhalt | **`data_elements`** (Payload/Struktur) | textarea/widget | – | ✅ | ✅P | ➕ **fehlt** | – |
| Inhalt | **`protocol`**, **`version`** | text | – | ○ | ✅ | ➕ neu | – |
| Klassifikation | **`timing`/`performance`** | text | – | – | ✅ | ➕ neu | 15288 |
| Klassifikation | **`safety_classification`** | enum | – | – | ✅ | ➕ neu | 26262 |
| Typ-spezifisch | `status` | enum | ✅ | ✅ | ✅ | ✅ | Workflow |

---

## 12. GlossaryTerm und ChangeRequest

**GlossaryTerm (4):** `term`, `definition`, `abbreviation`, `status` — für ein Glossar **ausreichend**.
Optional S3: `synonyms` (existiert im Backend-Adapter bereits), `source`, `owner`.

**ChangeRequest (7):** `title`, `description`, `impact_assessment`, `change_reason`,
`requestor_id`, `assigned_reviewer_id`, `status`

| Gruppe | Attribut | S1 | S2 | S3 | Bestand |
|---|--:|:--:|:--:|:--:|---|
| **`affected_artifacts`** | – | ✅ | ✅P | ➕ **fehlt** (15288 Baseline) |
| **`ccb_decision`** + **`decided_at`** | – | ✅ | ✅P | ➕ **fehlt** (Configuration Control Board) |
| **`target_baseline`** | – | ○ | ✅ | ➕ neu (15288 funktionale/allokierte Baseline) |
| **`verification_of_change`** | – | – | ✅ | ➕ neu |
| **`change_class`** (Major/Minor) | – | ✅ | ✅ | ➕ neu |

---

## 13. Zusammenfassung: die 12 wichtigsten Lücken

| Prio | Artefakt | Fehlt | Norm | Wirkung |
|---|---|---|---|---|
| **1** | **Alle** | **Stufenmodell fehlt** — Attribute/`required` identisch über minimal/standard/extended | – | Presets sind nur Feature-Schalter (#912) |
| **2** | Requirement | **`priority`** | 29148 Priority | `standard`/`extended` fordern es, Feld existiert nicht |
| **3** | Requirement | **`source`**, **`rationale`** | 29148 Source/Rationale | Herkunft & Begründung nicht belegbar |
| **4** | TestCase | **`expected_result`**, **`preconditions`**, **`objective`**, **`priority`** | 29119-3 | kein dokumentierter Testfall nach Norm |
| **5** | Goal | **`measure`**, **`target_value`**, **`unit`**, **`threshold`** | INCOSE/NASA MOP/TPM | Ziel nicht überprüfbar |
| **6** | StakeholderNeed | **`stakeholder`**, `rationale`, `validation_criteria` | 42010/29148 StRS | Bedarf ohne Quelle/Validierung |
| **7** | Adr | **`alternatives`**, `deciders`, `decided_at`, `supersedes` | 42010 Rationale | keine echte Architektur-Rationale |
| **8** | ArchitectureElement | **`rationale`**, `viewpoint` | 42010 (explizit) | Begründung der Struktur fehlt |
| **9** | ChangeRequest | **`affected_artifacts`**, `ccb_decision` | 15288 | Änderung ohne Wirkungsliste/Beschluss |
| **10** | Risk | `residual_risk`, `response_strategy`, `affects` | ISO 31000 | Risiko-Behandlung unvollständig |
| **11** | Icd | **`data_elements`**, `protocol`, `version` | – | Schnittstelle ohne Payload-Definition |
| **12** | Issue | **`priority`**, **`assignee`**, `resolution` | – | Problem nicht steuerbar |

---

## 14. Umsetzung mit dem vorhandenen Attribut-Feature (v2)

Das Attribut-Feature kann **alles** davon tragen — es braucht **keine** Schema-Änderung:

1. **Sections** anlegen: `identification`, `content`, `classification`, `attribution`,
   `verification`, `traceability`, `change_control` (+ vorhandenes `general` als Fallback).
   `SECTION_LAYOUTS` unterstützt `full`/`half` → zweispaltige Masken für Stufe 2/3.
2. **Neue Attribute als `kind="extended"`** je `(item_type, preset)` — genau dafür ist der Typ da.
3. **Stufen** werden über `required` + `visible` + `audience` (`basic`/`expert`) abgebildet:
   - **Stufe 1** = Preset `minimal`: nur Kernattribute `visible`, 2–3 `required`.
   - **Stufe 2** = Preset `standard`: zusätzliche Attribute `visible`, `audience="basic"`, mehr `required`.
   - **Stufe 3** = Preset `extended`: alle `visible`, `audience="expert"`, SE-Auditor-Gates scharf.
4. **Was heute blockiert:** `presets/registry.py` deklariert `mandatory_fields` **pro Preset, nicht pro
   Item-Typ** — für StakeholderNeed/TestCase/… sind die Namen sinnlos (#912). Vorschlag:
   `mandatory_fields` je `(item_type, preset)` auflösen **oder** ganz auf `required` in der
   Attribut-Definition verlassen (letzteres ist die sauberere, weil UI-getriebene Variante).
5. **Traceability-Attribute** (`allocated-to`, `verifies`, `derives-from`) bleiben TraceLinks, nicht
   Attribute — sie sind coverage-relevant (siehe #928). In der Maske als **Referenz-Widget** zeigen,
   persistiert als Link.
6. **Beziehungen als Pflicht** (Stufe 3) brauchen einen Gate im SE-Auditor bzw. Workflow —
   passend zu **#19** (`REQ_MUST_HAVE_ALLOCATION`, `REQ_MUST_HAVE_TEST_LINK`, `REQ_MUST_HAVE_SOURCE`).

---

## 15. Offene Entscheidungen

1. **Stufe 1 wirklich nur 2–3 Pflichtfelder?** Mein Vorschlag: `title` + `description` (Inhalt) —
   ohne Inhalt ist ein Artefakt wertlos. Oder ganz radikal nur `title` (wie heute)?
2. **`priority`-Skala**: MoSCoW (wie `moscow_priority` im Need) oder numerisch 1–5 oder
   Stakeholder-priority (29148)? Ein System für alle Typen wäre konsistent.
3. **`rationale` Pflicht ab Stufe 2?** 29148 verlangt ihn, aber er erhöht die Eingabehürde deutlich.
4. **Kritikalitäts-Skala**: ASIL (Automotive, `asil_level` existiert schon) oder generisch
   (low/medium/high/critical) — ein Feld für alle Artefakttypen?
5. **Traceability als Pflicht ab Stufe 3** — über den SE-Auditor (blockierend) oder als Warnung?
6. Soll ich daraus **ein GH-Issue als Master-Tabelle** machen + je Artefakttyp ein Unter-Issue?
