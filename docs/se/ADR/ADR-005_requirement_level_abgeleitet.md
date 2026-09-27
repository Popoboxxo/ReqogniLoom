---
adr_id: ADR-005
title: "Requirement.level wird abgeleitet und schreibgeschützt"
status: accepted
date: "2026-09-27"
deciders: [user]
affected_reqs: [REQ-L0-039, REQ-L0-019]
superseded_by: null
---

# ADR-005: Requirement.level wird abgeleitet und schreibgeschützt

**Status:** accepted
**Datum:** 2026-09-27
**Entscheider:** user
**Betroffene REQs:** REQ-L0-039 (Systemebenen-Orientierung durch Hierarchie-Darstellung),
REQ-L0-019 (Projektübergreifende Traceability für rekursive SE-Zerlegung)
**Bezug:** Issue **#1086**; `application/requirement_service.py:387-406, 1042-1047`;
`application/artifact_service.py:353-355`; `traceability/trace_link_manager.py:402-442`;
`traceability/audit/hierarchy.py:53-58, 145-172`; `traceability/audit/rules/level_progression.py:132-191`;
`rest_api/serializers.py:958`; `rest_api/views.py:1117-1152`;
`attribute_definitions/management/commands/bootstrap_attribute_definitions.py:358-360`;
`attribute_definitions/stage_matrix.py:667`; `mcp_server/tools/requirements.py:601-611`

---

## Kontext

`Requirement.level` (V-Modell-Kaskadenebene, Integer-Kernspalte) ist nicht bloß redundant.
Das Feld darf heute **falsch werden** — es ist nicht invariant gehalten.

`RequirementService.decompose()` setzt `child_level = parent_level + 1`
(`application/requirement_service.py:1042-1047`). Es existieren aber **drei**
Hierarchie-Schreibpfade, und nur einer davon fasst das Feld an:

- `decompose()` — setzt `level`
- `ArtifactViewSet.partial_update` → `application/artifact_service.py:353-355` schreibt
  `Artifact.parent_id` — fasst `level` **nicht** an
- TraceLink create/delete für `decomposes` / `derives-from`
  (`traceability/trace_link_manager.py:402-442`) — fasst `level` **nicht** an

Der Audit-Graph liest die **TraceLink**-Kanten (`traceability/audit/hierarchy.py:145-172`),
und `Artifact.parent_id` ist ein *eigener* FK-Baum, den der Graph nicht normalisiert
(`traceability/audit/hierarchy.py:57-58`). Ein Nutzer kann also ein Artefakt umhängen
oder neu verlinken, der Auditor sieht die neue Hierarchie, und das Feld widerspricht
ihr. Der Widerspruch ist nicht transient: er bleibt bestehen, bis jemand
`decompose()` erneut aufruft.

Verschärfend: `RequirementService.update_requirement` besitzt **gar keinen**
`parent_id`-Parameter (`application/requirement_service.py:387-406`), und
`RequirementSerializer.parent_id` ist zwar deklariert
(`rest_api/serializers.py:958`), wird in `partial_update` aber **stillschweigend
verworfen** (`rest_api/views.py:1117-1152`) — ein PATCH mit `parent_id` liefert
`200` und verändert nichts.

Die einzige heute existierende Konsistenzregel auf dieses Feld ist `CONS-P11`
(`traceability/audit/rules/level_progression.py:132-191`); sie behauptet exakt, dass
das Feld mit dem Graphen übereinstimmt.

---

## Alternativen

### Option A: `level` vollständig entfernen — VERWORFEN

**Beschreibung:** Die Spalte entfällt; die Ebeneninformation wird ausschließlich aus
dem Graphen gelesen.

**Abwägung:** Semantisch die sauberste Lösung, aber teuer. `level == L4` ist heute der
**einzige** L4-Ausnahmefilter für drei Audit-Regeln
(`rules/decomposition_consistency.py:229-245, 306-341`; `rules/coverage_consistency.py:29-30, 110-132, 306-310`).
`traceability/audit/hierarchy.py` hat **kein eigenes L4-Konzept** — die L4-Semantik
steckt ausschließlich im Feld. Hinzu kommen sechs dokumentative Konsumenten sowie der
Export- und Import-Vertrag (`application/export_service.py:127`,
`application/requirement_bundle_service.py:105`,
`frontend/src/components/CsvImport/csvPreview.ts:45`) und die Frontend-Typen.

**Risiko:** HOCH — reißt die L4-Semantik aus drei Regeln heraus

> Verworfen als **teuer, nicht als falsch**. Die Grundidee dieser Option ist korrekt
> und bleibt die Zielrichtung, falls `hierarchy.py` jemals ein eigenes L4-Konzept
> bekommt.

---

### Option B: Nur in `decompose()` ableiten, die anderen zwei Pfade unangetastet lassen — VERWORFEN

**Beschreibung:** `level` wird read-only, die Neuberechnung bleibt aber an den
Zerlegungs-Workflow gekoppelt.

**Abwägung:** Das lässt genau den „kann falsch werden"-Defekt stehen, den diese
Entscheidung beseitigen soll — nur nicht mehr von Hand editierbar. Das ist
**schlechter als der Status quo**, weil ein schreibgeschütztes Feld *vertrauenswürdig
aussieht*: Nutzer, UI und Exporte würden einen Wert anzeigen, der nach einem
Re-Paring falsch ist, ohne jede Warnung.

**Risiko:** HOCH — erzeugt einen stillen Vertrauensverlust

---

### Option C: Feld frei editierbar lassen und `CONS-P11` verschärfen — VERWORFEN

**Beschreibung:** Das Feld bleibt Schreibfeld; die Audit-Regel wird strenger, um
Inkonsistenzen zuverlässig zu melden.

**Abwägung:** `CONS-P11` feuert heute ausschließlich auf TraceLink-normalisierte
Kanten und überspringt Paare mit `NULL`-Ebene
(`traceability/audit/rules/level_progression.py:157-158`). Sie kann den Pfad über
`Artifact.parent_id` also **konstruktiv nicht sehen** — genau der Pfad, um den es
hier geht. Eine Verschärfung der Regel würde den realen Defekt nicht fangen, nur
lauter über den bereits abgedeckten Pfad berichten.

**Risiko:** MITTEL — Scheinlösung

---

### Option D: Abgeleitet, schreibgeschützt, Neuberechnung bei **jeder** Hierarchieänderung (GEWÄHLT)

**Beschreibung:** `level` wird abgeleitetes Feld mit genau einem Schreiber: der
Hierarchie-Schreiblogik. Alle drei Pfade lösen die Neuberechnung aus.

**Vorteile:**
- Der „kann falsch werden"-Defekt ist strukturell beseitigt, nicht nur erschwert
- Das Feld behält seine L4-Semantik für die drei Audit-Regeln, die sie brauchen
- Der ebenfalls verworfene `parent_id` im PATCH wird angewendet statt still verworfen —
  der Fund ist damit zugleich eine Silent-Drop-Korrektur (AUC-Verstoß, ADR-004)

**Nachteile:**
- `CONS-P11` wird tautologisch und muss entfallen (siehe Konsequenzen)
- Entfernung eines `mandatory`-Flags in der Stage-Matrix, sonst bricht jedes Create
  im extended-Preset
- Der Service-Parameter `level` und die MCP-Werbung eines schreibbaren `level`
  verschwinden — eine **brechende** Änderung an der REST/MCP-Oberfläche

**Risiko:** NIEDRIG–MITTEL — kein Datenmodellumbau, aber API-Vertrag wird enger

---

## Entscheidung

`Requirement.level` wird ein **abgeleitetes, schreibgeschütztes** Feld.

1. **Abgeleitet, nicht gepflegt.** `level` wird bei **jeder** Hierarchieänderung neu
   berechnet — nicht nur in `decompose()`, sondern in allen drei Schreibpfaden:
   `decompose()`, der `Artifact.parent_id`-Schreibpfad
   (`application/artifact_service.py:353-355`) sowie TraceLink create/delete für
   `decomposes` und `derives-from` (`traceability/trace_link_manager.py:402-442`).
2. **Read-only im Attributsystem.** `level` tritt in `READ_ONLY_MODEL_FIELDS`
   (`attribute_definitions/management/commands/bootstrap_attribute_definitions.py:358-360`).
3. **Read-only im Serializer.** Das Feld wird `read_only=True`.
4. **Kein Service-Parameter mehr.** Der `level`-Parameter in
   `RequirementService.update_requirement` entfällt.
5. **Kein schreibbares `level` im MCP-Update-Pfad.** Der Aufruf in
   `mcp_server/tools/requirements.py:601-611` leitet `level` heute bereits **nicht**
   weiter; das wird damit konsistent, statt eine Lücke zu bleiben.
6. **Stage-Matrix-Anpassung.** Der Override `"level": {"visible": {2, 3}, "mandatory": {3}}`
   (`attribute_definitions/stage_matrix.py:667`) **verliert sein `mandatory`-Flag**,
   bleibt aber sichtbar. Ohne diese Änderung würde jedes Create im extended-Preset
   mit HTTP 400 scheitern, weil ein abgeleitetes Feld nicht eingeschickt werden kann.
7. **Der verworfene `parent_id` wird angewendet.** Der Wert, den
   `RequirementSerializer.parent_id` deklariert, `partial_update` aber stillschweigend
   verwirft, wird tatsächlich auf die Hierarchie angewendet — sonst wäre
   `level` nach Umhängen weiterhin der alte Wert.
8. **`CONS-P11` entfällt** — siehe Konsequenzen.

---

## Konsequenzen

**Positiv:**

- `level` ist invariant. Der Widerspruch zwischen Feld und Graph kann strukturell
  nicht mehr entstehen, auf keinem der drei Schreibpfade.
- `level == L4` bleibt als Filter für `TRACE-P5`, `ARCH-003` und `VERIF-P8`
  erhalten; die L4-Semantik wird nicht aus den Audit-Regeln herausgerissen.
- Der still verworfene `parent_id` im Requirement-PATCH wird behoben — ein
  REST/MCP-Vertragsbruch (AUC) fällt weg.
- Die Gate-Reihenfolge ist ehrlich: Nutzer können `level` nicht mehr setzen, aber
  auch nicht mehr falsch setzen. Der Vertrauenswert des Feldes steigt.

**Negativ:**

- **`CONS-P11` wird tautologisch und wird entfernt.** Die Regel behauptet, das Feld
  stimme mit dem Graphen überein — nach dieser Entscheidung ist das Feld aus dem
  Graphen *abgeleitet*. Die Regel kann nie mehr feuern. Das Repository hat diese
  Argumentation an anderer Stelle schon einmal exakt so getroffen
  (`traceability/audit/hierarchy.py:53-56`: „feeding it normalised edges would make
  the rule tautologically true"). `CONS-P11` wird **mitsamt seiner sechs
  dokumentativen Konsumenten** entfernt.
- **Was dadurch verloren geht:** `hierarchy.py` besitzt **kein eigenes L4-Konzept**.
  Würde man `level` doch entfernen (Option A), verlören genau die drei Regeln ihren
  L4-Ausnahmefilter. Genau deshalb wurde Option A verworfen.
- **Brechende Änderung:** REST und MCP bieten `level` nicht mehr als Eingabefeld an.
  Clients, die es setzen, erhalten nach dem Umbau `400` bzw. eine ignorierte Angabe.
- Die Neuberechnung an allen drei Pfaden ist zusätzliche Logik in drei
  Schreibpfaden statt einer — der Preis dafür, dass es keine Ausnahme gibt.
- `REQUIRED`-Wirkung auf Ebene 3 entfällt für `level`; ohne `mandatory` besteht
  keine Aussage mehr darüber, dass `level` in Stufe 3 gesetzt sein **müsste** —
  es ist ja abgeleitet.

---
