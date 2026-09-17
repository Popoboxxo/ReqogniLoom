# Attribut-Matrix — alle Artefakte × alle Attribute × 3 Stufen

**Teil der** `attribut-umsetzungsspezifikation.md`
**Stufen:** S1 = `minimal`, S2 = `standard`, S3 = `extended`
**Legende:** `P` = Pflicht · `o` = optional/sichtbar · `-` = nicht vorhanden/ausgeblendet
**Träger:** `core` = echte Spalte · `ext` = `custom_fields` · `system` = systemisch, read-only · `link` = TraceLink · `widget` = strukturiertes Widget · `entity` = eigene Tabelle

> Neue/geänderte Einträge gegenüber heute sind mit **Neu** markiert. `uid` wird zum externen
> Import-Schlüssel (nicht mehr Nutzer-Attribut); die **einzige** Identität ist `id`.

---

## 0. Querschnitts-Systemfelder (auf `Artifact`, gelten für alle 11 Typen)

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| id | Identifikation | text | **system** | o | o | o | UUID, `visible=false`, `reveal=click`, `copyable`, `mask=short` |
| owner | Attribution | actor | **system** | - | o | P | Kombi-Feld, `allow_external=true` |
| reporter | Attribution | actor | **system** | - | o | o | Kombi-Feld |
| priority | Klassifikation | enum | **core** | - | P | P | Skala `low/medium/high/critical` |
| status | Klassifikation | enum | **system** | P | P | P | Workflow (`editable=workflow`) |

---

## 1. Requirement

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | P | P | |
| description_editor | Inhalt | widget | widget | o | o | o | markdown_tab_group |
| category | Klassifikation | text | core | o | o | o | |
| type | Klassifikation | enum | core | - | o | P | funktional/nicht-funktional/… |
| level | Klassifikation | enum | core | - | o | P | L0–L4 |
| difficulty | Klassifikation | enum | ext | - | o | P | **Neu** |
| criticality | Klassifikation | enum | ext | - | o | P | **Neu**, low/medium/high/critical |
| acceptance_criteria | Verifikation | textarea | core | o | P | P | |
| verification_method | Verifikation | enum | core | - | P | P | |
| verification_status | Verifikation | enum | ext | - | o | P | **Neu** |
| validation_method | Verifikation | enum | ext | - | - | P | **Neu** |
| rationale | Attribution | textarea | ext | - | P | P | **Neu** (#871) |
| source | Attribution | text | ext | - | o | P | **Neu** (#871) |
| complexity_fibonacci | Klassifikation | enum | ext | - | o | o | |
| change_reason | Änderung | textarea | core | - | o | P | |
| allocated-to | Traceability | link | link | o | P | P | TraceLink |
| derives-from | Traceability | link | link | o | P | P | TraceLink |
| origin_link | Traceability | text | ext | - | o | P | **Neu** |
| mop_tpm_ref | Traceability | reference | entity | - | o | P | `Measure` (#393) |

---

## 2. StakeholderNeed

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | P | P | |
| category | Klassifikation | text | core | o | o | o | |
| moscow_priority | Klassifikation | enum | ext | - | P | P | **Neu**: von Modellspalte nach extended gefaltet |
| stakeholder | Attribution | actor | ext | - | P | P | **Neu** (Rolle/Gruppe) |
| rationale | Attribution | textarea | ext | - | o | P | **Neu** |
| validation_criteria | Verifikation | textarea | ext | - | o | P | **Neu** |
| concern | Attribution | multi-enum | ext | - | - | P | **Neu** (ISO 42010) |
| effect_measure | Traceability | reference | entity | - | - | o | **Neu** (MOP) |
| derived-to | Traceability | link | link | o | P | P | TraceLink |

---

## 3. ArchitectureElement

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| element_type | Klassifikation | enum | core | o | o | P | |
| description | Inhalt | textarea | core | o | P | P | |
| description_editor | Inhalt | widget | widget | o | o | o | |
| parent_id | Struktur | reference | core | o | P | P | |
| asil_level | Klassifikation | enum | core | - | o | P | |
| make_or_buy | Klassifikation | enum | core | - | o | P | |
| rationale | Attribution | textarea | ext | - | o | P | **Neu** (ISO 42010) |
| viewpoint | Klassifikation | enum | ext | - | - | P | **Neu** |
| technology | Klassifikation | text | ext | - | o | P | **Neu** |
| verification_method | Verifikation | enum | ext | - | o | P | **Neu** |
| performance_budget | Klassifikation | number | ext | - | - | P | **Neu** |
| interfaces | Traceability | link | link | o | P | P | über Icd |
| allocated-to | Traceability | link | link | o | P | P | TraceLink |

---

## 4. TestCase

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | o | P | |
| steps | Inhalt | widget | widget | o | P | P | steps_editor |
| objective | Inhalt | textarea | ext | - | o | P | **Neu** |
| preconditions | Inhalt | textarea | ext | - | P | P | **Neu** |
| postconditions | Inhalt | textarea | ext | - | o | P | **Neu** |
| expected_result | Inhalt | textarea | ext | - | P | P | **Neu** |
| test_type | Klassifikation | enum | core | o | P | P | |
| test_level | Klassifikation | enum | ext | - | o | P | **Neu** |
| priority | Klassifikation | enum | core | - | P | P | generisch |
| test_data | Verifikation | textarea | ext | - | o | P | **Neu** |
| test_environment | Verifikation | textarea | ext | - | - | P | **Neu** |
| review_status | Attribution | enum | ext | - | o | P | **Neu** |
| verifies | Traceability | link | link | o | P | P | TraceLink |

---

## 5. Adr

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| context | Inhalt | textarea | core | P | P | P | |
| decision | Inhalt | textarea | core | P | P | P | |
| consequences | Inhalt | textarea | core | o | P | P | |
| alternatives | Inhalt | textarea | ext | - | P | P | **Neu** (ISO 42010) |
| decision_drivers | Inhalt | multi-enum | ext | - | o | P | **Neu** |
| deciders | Attribution | actor | ext | - | o | P | **Neu**, `multiple=true` |
| decided_at | Attribution | date | ext | - | o | P | **Neu** |
| decision_record | Attribution | widget | widget | o | o | o | |
| supersedes | Traceability | reference | ext | - | o | P | **Neu** |
| affects | Traceability | link | link | - | o | P | **Neu** |

---

## 6. Risk

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | P | P | |
| category | Klassifikation | enum | core | o | o | o | |
| probability | Klassifikation | enum | core | o | P | P | |
| impact | Klassifikation | enum | core | o | P | P | |
| detection | Klassifikation | enum | core | - | o | o | |
| risk_matrix | Klassifikation | widget | widget | - | o | P | risk_matrix_rpz |
| severity | Klassifikation | number | ext | - | o | P | **Neu**, `automation` (RPN) |
| risk_type | Klassifikation | enum | ext | - | o | P | **Neu** (Chance/Bedrohung) |
| residual_risk | Klassifikation | enum | ext | - | o | P | **Neu** |
| response_strategy | Attribution | enum | ext | - | o | P | **Neu** (avoid/reduce/transfer/accept) |
| mitigation_strategy | Attribution | textarea | core | o | P | P | |
| review_cycle | Attribution | date | ext | - | o | P | **Neu** |
| affects | Traceability | link | link | - | o | P | **Neu** |

> `owner`/`owner_user_id` gehen in das Systemfeld `owner` (Abschnitt 0) über; Legacy-Freitext wird per AWMS migriert.

---

## 7. Issue

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | P | P | |
| category | Klassifikation | enum | core | o | o | o | |
| severity | Klassifikation | enum | core | o | P | P | |
| priority | Klassifikation | enum | core | - | P | P | generisch |
| due_date | Attribution | date | core | - | o | P | |
| tag_list | Attribution | widget | widget | - | o | o | tag_input |
| assignee | Attribution | actor | ext | - | o | P | **Neu** (aus `assignee_id`), Kombi-Feld |
| resolution | Inhalt | textarea | ext | - | o | P | **Neu** |
| root_cause | Inhalt | textarea | ext | - | o | P | **Neu** |
| affects | Traceability | link | link | - | o | P | **Neu** |

---

## 8. Goal

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | o | P | P | |
| priority | Klassifikation | enum | core | - | P | P | generisch |
| timeframe | Attribution | date | ext | - | o | P | **Neu** |
| measure_name | Klassifikation | text | ext | - | o | P | **Interim** bis `Measure` |
| target_value | Klassifikation | number | ext | - | o | P | **Interim** |
| unit | Klassifikation | text | ext | - | o | P | **Interim** |
| threshold | Klassifikation | number | ext | - | o | P | **Interim** |
| measure | Traceability | reference | entity | - | - | P | **`Measure`-Entität (#393)** |
| parent_goal | Traceability | reference | ext | - | o | P | **Neu** |
| addresses | Traceability | link | link | - | o | P | **Neu** |

---

## 9. Icd

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| name | Identifikation | text | core | P | P | P | |
| source_element_id | Struktur | reference | core | P | P | P | |
| target_element_id | Struktur | reference | core | P | P | P | |
| direction | Klassifikation | enum | core | P | P | P | |
| interface_type | Klassifikation | enum | core | P | P | P | |
| semantic_description | Inhalt | textarea | core | o | P | P | |
| data_elements | Inhalt | textarea | ext | - | P | P | **Neu** (Payload/Struktur) |
| protocol | Klassifikation | text | ext | - | o | P | **Neu** |
| version | Klassifikation | text | ext | - | o | P | **Neu** |
| timing | Klassifikation | text | ext | - | - | P | **Neu** |
| safety_classification | Klassifikation | enum | ext | - | - | P | **Neu** |

> Icd erhält als einziger Typ, der bisher **keinerlei** Attribut-Anbindung hat, sowohl REST- als auch die neue `icd.*`-MCP-Gruppe.

---

## 10. GlossaryTerm

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| term | Identifikation | text | core | P | P | P | |
| definition | Inhalt | textarea | core | P | P | P | |
| abbreviation | Identifikation | text | core | o | o | o | |
| synonyms | Inhalt | multi-enum | ext | - | o | o | **Neu** |
| source | Attribution | text | ext | - | o | P | **Neu** |
| owner | Attribution | actor | system | - | o | P | Systemfeld |

---

## 11. ChangeRequest

| Attribut | Gruppe | Typ | Träger | S1 | S2 | S3 | Hinweis |
|---|---|---|---|---|---|---|---|
| title | Identifikation | text | core | P | P | P | |
| description | Inhalt | textarea | core | P | P | P | |
| impact_assessment | Inhalt | textarea | core | o | P | P | |
| change_reason | Änderung | textarea | core | o | P | P | |
| change_class | Klassifikation | enum | ext | - | P | P | **Neu** (Major/Minor) |
| affected_artifacts | Traceability | link | link | - | P | P | **Neu** |
| ccb_decision | Änderung | enum | ext | - | P | P | **Neu** |
| decided_at | Attribution | date | ext | - | o | P | **Neu** |
| target_baseline | Traceability | reference | ext | - | o | P | **Neu** |
| verification_of_change | Verifikation | textarea | ext | - | - | P | **Neu** |

> `requestor_id` → Systemfeld `reporter`; `assigned_reviewer_id` → `assignee` (actor). Beide Legacy-UUIDs werden per AWMS auf `Actor` migriert.

---

## 12. Nicht-Attribut-Träger (Abgrenzung)

| Anforderung | Träger | Quelle |
|---|---|---|
| Zeitreihen MOP/TPM | `Measure`-Entität | #393 |
| Personen intern/extern | `Actor`-Entität | diese Spec, Abschnitt 4 |
| Semantische Ketten | `TraceLink` | 8 built-in Link-Typen |
| Strukturierte Werte | Widget-Registry | `schema.py` `WIDGET_KEYS` |
