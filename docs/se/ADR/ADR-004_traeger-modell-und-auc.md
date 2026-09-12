---
adr_id: ADR-004
title: "Träger-Modell und Attribute Usability Contract (AUC)"
status: proposed
date: 2026-09-12
deciders: [senior-developer, user]
affected_reqs: []
superseded_by: null
---

# ADR-004: Träger-Modell und Attribute Usability Contract (AUC)

**Status:** proposed
**Datum:** 2026-09-12
**Entscheider:** senior-developer, user
**Betroffene REQs:** — (keine REQ-IDs für das Attribut-Thema vorhanden; siehe Bezug)
**Bezug:** Epic **#934** (Attribut-System v3), WS0 **#941** (Fundament);
`docs/se/attribut/attribut-umsetzungsspezifikation.md` §2, §9, §11, §14;
`docs/se/attribut/attribut-matrix-3-stufen.md`

> Hinweis zur Rückverfolgbarkeit: Das ADR-Standard fordert mindestens eine REQ-ID in
> `affected_reqs`. Für das Attribut-Thema existieren im Repo noch keine passenden
> REQ-IDs, daher ist das Feld leer und die Verfolgbarkeit läuft über die Issues
> #934 / #941.

---

## Kontext

Das Attribut-System v3 besteht aus drei Schichten: **Definition** (funktioniert:
Auflösung über `(tenant, item_type, preset)`, Validierung, Admin-Gating),
**Transport** (REST + MCP — divergent und teils gebrochen) und **Identität/Werte**
(`uid` tot, AWMS fehlt). Der eigentliche Defekt liegt in der Transportschicht:

- **REST:** `custom_fields` fehlt in Serializer und/oder View bei `Goal`,
  `ChangeRequest`, `GlossaryTerm` (teils Silent-Success); `Icd` hat keine
  Attribut-Anbindung; `ChangeRequest`-Create validiert die Definition nicht;
  Discovery (`attribute-schema`) existiert nur für `Requirement`.
- **MCP:** Handler für `Requirement`/`Needs`/`Test`/`Architecture` verwerfen
  `custom_fields` (`additionalProperties: false`); `Adr`/`Risk`/`Issue` sind
  schreibbar, aber nicht lesbar (`generic._to_dict` liest Modell-`__dict__` statt
  `artifact.custom_fields`); `GlossaryTerm`/`ChangeRequest`/`Goal` kennen
  `custom_fields` im Service nicht; `Icd` hat keine Tools; `artifact.search` und
  `get_tree` liefern keine Attribute.

Jeder Item-Typ verdrahtet REST und MCP heute getrennt — dadurch **divergieren die
Transporte pro Typ** und einzelne Attribute werden still verworfen. Es fehlt sowohl
ein einheitliches Speicher-Träger-Modell (wo liegt welches Attribut) als auch ein
Verhaltensversprechen, das für alle Typen und Presets über beide Transporte gilt.

**Treiber:** Feature-Parität REST ↔ MCP, keine Silent-Drops, ein einziger
Werte-Pfad, maschinell erzwungene Konformität (nicht per Zusicherung),
Anschlussfähigkeit an AWMS (#930).

---

## Alternativen

### Option A: Einheitliches Träger-Modell + zentraler `ArtifactAttributeGateway` + Contract-Matrix-Ratchet (GEWÄHLT)

**Beschreibung:** Ein Sechs-Träger-Modell (core / extended / system / link /
widget / entity) legt je Attribut den Speicherort fest. REST-Views **und**
MCP-Handler gehen durch **einen** gemeinsamen `ArtifactAttributeGateway`
(Discovery, Lesen, Schreiben, Validierung). Eine parametrisierte Contract-Matrix
prüft für jede `(item_type, preset)` × Transport × Attribut W/R/V/Round-Trip.

**Vorteile:**
- Eine Werte-Pipeline statt per-Typ-Verdrahtung → Divergenz ist strukturell nicht
  mehr möglich, kein Silent-Drop
- Validierung zentral (gilt automatisch für REST **und** MCP)
- Neue Attribute und Item-Typen müssen die Matrix bestehen (CI-blockierend)
- Träger-Modell macht Filter-/Join-/FK-Entscheidungen explizit und referenzierbar
- Klarer Migrations-Zielzustand für AWMS (#930)

**Nachteile:**
- Gateway wird zentraler Pfad → Performance-/Kopplungs-Hotspot
- Ratchet startet **rot** (dokumentiert alle Alt-Lücken) und blockiert CI, bis die
  Parität hergestellt ist
- Einmaliger Refactor-Aufwand über alle 11 Item-Typen und 3 Presets

**Risiko:** NIEDRIG–MITTEL — keine Paradigmen-Umstellung, aber breit

---

### Option B: Per-Typ-Verdrahtung für REST und MCP beibehalten (Status quo) — VERWORFEN

**Beschreibung:** Jeder Item-Typ behält eigene Serializer, eigene Views und eigene
MCP-Handler mit je eigener Feldliste.

**Abwägung:** Kein Refactor nötig, aber genau die in Spec §9 dokumentierte
Divergenz (REST kann `Goal`/`ChangeRequest`/`GlossaryTerm`-`custom_fields` nicht
oder nur scheinbar schreiben; MCP-Handler verwerfen sie teils vollständig) ist der
**Fehlermodus**, den dieses Epic behebt. Ohne gemeinsamen Pfad entsteht bei jedem
neuen Attribut oder Typ erneut Drift; Silent-Drops bleiben möglich.

**Risiko:** HOCH — der Defekt wird zementiert

---

### Option C: Alles in einem einzigen JSONB-Blob speichern — VERWORFEN

**Beschreibung:** Sämtliche Attribute (inkl. `id`, `owner`, `reporter`, `priority`,
`status`) liegen als ein JSONB-Dokument je Artefakt vor.

**Abwägung:** Maximale Flexibilität ohne Migrationen, aber: keine echte
Sortierung/Filterung ohne Ausdrucks-Indizes, keine FK-Integrität (Owner/Reporter,
Referenzen), kein erstklassiger API-/MCP-Schema-Contract, keine referenzierbare
Identität. Verletzt die Entscheidungsregel (Felder, die sortier-/filter-/FK- oder
schema-erstklassig sind, gehören auf echte Spalten).

**Risiko:** MITTEL–HOCH — Datenintegrität und Query-Fähigkeit gehen verloren

---

### Option D: Per-Typ-Handler aus der Definition code-generieren — VERWORFEN

**Beschreibung:** Die Attribut-Definition generiert zur Build-Zeit Serializer- und
MCP-Handler-Code pro Typ.

**Abwägung:** Reduziert handgeschriebene Verdrahtung, aber generierter Code driftet
vom Laufzeit-Definitionsstand ab (Tenant-/Preset-Konfiguration ist Laufzeit), die
Round-Trip-Semantik über beide Transporte bleibt ungeprüft, und die Toolchain
(Generator, Build-Step, Debugging generierter Artefakte) erhöht die Wartungslast
ohne den Nutzen eines echten gemeinsamen Gateways. Kein Ersatz für ein
Contract-Ratchet.

**Risiko:** MITTEL — Tooling-Komplexität ohne Konformitätsgarantie

---

## Entscheidung

Es werden **zwei** zusammenhängende Entscheidungen festgezurrt.

### 1. Träger-Modell (sechs Träger)

| Träger | Speicher | Wofür |
|---|---|---|
| **core** | echte Spalte (Spezialtabelle **oder** generische `Artifact`) | sortier-/filter-/join-relevant, API-/MCP-erstklassig |
| **extended** | `Artifact.custom_fields` (JSONB) | konfigurierbar je Tenant/Preset, ohne Migration |
| **system** | core, aber `editable="system"`, `locked` | ID, Status; nicht schreibbar |
| **link** | `TraceLink` | semantische Ketten (derives-from, allocated-to, verifies …) |
| **widget** | core/extended + Widget-Komponente | strukturierte Werte (steps, risk_matrix, ICD-Payload) |
| **entity** | eigene Tabelle | `Measure` (Zeitreihe), `Actor` (Personen) |

**Entscheidungsregel:** Ein Modellfeld (core) wird nur dann angelegt, wenn
mindestens eines zutrifft — **(a)** sortier-/filterbar nötig, **(b)** im API/MCP-Schema
erstklassig nötig, **(c)** FK-Integrität nötig, **(d)** auf jedem Artefakt des Typs
normativ. **Sonst extended.**

**Festlegungen (Auszug, verbindlich):**

| Attribut | Träger |
|---|---|
| `id`, `owner`, `reporter`, `priority` | **core auf `Artifact`** (alle 11 Typen, eine Migration) |
| `status` | **system** (workflow) — existiert |
| `rationale`, `source` | **extended** |
| `moscow_priority` | **extended nur StakeholderNeed** (Legacy-Spalte wird per AWMS gefaltet) |
| alle übrigen Einträge | teils core, teils extended — je Zeile in `attribut-matrix-3-stufen.md` |

> Präzisierung: Die `system`-Kennzeichnung in Matrix §0 für `id`/`owner`/`reporter`/`status`
> meint die **Editability-Facette** (read-only, `editable="system"`, `locked`) der
> core-gestützten `Artifact`-Felder; die Speicherung selbst ist core. Das ist
> konsistent mit der Definition des `system`-Trägers („core, aber
> `editable=system`, locked"). `id` ist die **einzige** Identität; `uid` wird zum
> externen Import-Schlüssel (ReqIF), nicht zum Nutzer-Attribut.

### 2. Attribute Usability Contract (AUC)

> Für jedes `(workspace, item_type ∈ 11, preset ∈ 3)` und jedes **sichtbare**
> Attribut der aufgelösten Definition gilt: **W** (schreibbar), **R** (lesbar),
> **V** (identisch validiert) und **Round-Trip** — auf **beiden** Transporten
> (REST **und** MCP), **immer**. Kein Silent-Drop. Discovery der Definition ist für
> **jeden** Item-Typ verfügbar.

Die 11 Item-Typen sind `Requirement`, `StakeholderNeed`, `ArchitectureElement`,
`TestCase`, `Adr`, `Risk`, `Issue`, `Goal`, `Icd`, `GlossaryTerm`,
`ChangeRequest`; die 3 Presets sind `minimal`, `standard`, `extended`.

**Durchsetzung — nicht per Zusicherung, sondern per Ratchet:** Die AUC wird durch
die **Contract-Matrix** als parametrisierter, CI-blockierender Test erzwungen —
verortet unter
`backend/attribute_definitions/tests/test_transport_contract_matrix.py`
(parametrisiert über `ITEM_TYPES` × `PRESETS` × Transport). Die Matrix startet
**rot** (sie dokumentiert alle heutigen Lücken aus Spec §9) und ist erst grün, wenn
beide Transporte für alle Typen/Presets/Attribute W/R/V/Round-Trip erfüllen. Jedes
neue Attribut und jeder neue Item-Typ muss die Matrix bestehen. Der Test ist ein
WS0-Deliverable und in diesem Branch noch **nicht** angelegt; dieses ADR bindet
seinen Pfad und seine Rolle.

**Ein gemeinsamer Werte-Pfad:** REST-Views und MCP-Handler verwenden den zentralen
`ArtifactAttributeGateway`, damit keine per-Typ-Verdrahtung mehr abweichen kann.

---

## Konsequenzen

**Positiv:**
- Transport-Parität ist maschinell garantiert, nicht behauptet — Silent-Drops sind
  durch die Matrix sichtbar und blockierend
- Validiert wird genau einmal zentral → REST und MCP validieren identisch (V)
- Ein zentraler Gateway beseitigt die Divergenzursache und senkt die zukünftige
  Änderungslast pro Attribut/Item-Typ
- Das Träger-Modell gibt AWMS (#930) einen klaren Zielzustand für Werte-Migrationen
- Discovery ist über alle Item-Typen einheitlich verfügbar

**Negativ:**
- Der Gateway wird zentraler Pfad: Performance- und Kopplungs-Hotspot, muss
  sorgfältig (Caching, Query-Design) umgesetzt werden
- Die Contract-Matrix startet rot und blockiert CI, bis WS1 die Parität herstellt —
  bewusst sichtbarer Zwischenzustand
- Erweiterte Attribute liegen in JSONB und sind damit für komplexe
  Cross-Attribut-Queries teurer als echte Spalten
- Die `system`-Semantik (read-only, `editable="system"`, `locked`) erfordert
  konsistentes Policy-Plumbing in Gateway und UI
- Legacy-Felder (`Risk.owner`, `created_by_name`, `moscow_priority`,
  `requestor_id`, `assignee_id`) müssen per AWMS auf die neuen Träger migriert
  werden

---

## Status-Lifecycle

Der Status ist `proposed`; er löst den Review-Trigger (`se-critic`) aus. Ein
Wechsel auf `accepted` erfolgt erst nach erfolgtem Review durch die zuständige
Rolle.
