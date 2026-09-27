---
adr_id: ADR-008
title: "MOE/MOP/TPM werden nicht modelliert; die interim Goal-Attribute bleiben"
status: accepted
date: "2026-09-27"
deciders: [user]
affected_reqs: [REQ-L0-020, REQ-L0-047]
superseded_by: null
---

# ADR-008: MOE/MOP/TPM werden nicht modelliert; die interim Goal-Attribute bleiben

**Status:** accepted
**Datum:** 2026-09-27
**Entscheider:** user
**Betroffene REQs:** REQ-L0-020 (Metrikbasiertes Steuern des SE-Prozesses),
REQ-L0-047 (Präzises, domänenspezifisches Datenmodell)
**Bezug:** Issue **#393**; `attribute_definitions/stage_matrix.py:47-49, 583-596`;
`docs/se/attribut/attribut-modell-3-stufen.md:146-160, 309`;
`docs/REAUDIT_2026-09-03.md:85, 461`

---

## Kontext

MOE (Measures of Effectiveness), MOP (Measures of Performance) und TPM (Technical
Performance Measures) kommen im Repository ausschließlich in **Dokumentation** vor.
Eine belastbare Zählung über die versionierten Dateien ergibt Dutzende Fundstellen in
Markdown — und **keine einzige** in `backend/`, `frontend/src/` oder `e2e/*.ts`. Die
einzigen Nicht-Markdown-Treffer liegen in PNG-Binaries und im mitgelieferten
Dritt-Artefakt `frontend/dist/assets/katex-*.js`; es ist kein Projekt-Quellcode.

Die Audits des Repositories kommen **unabhängig** zum selben Ergebnis
(`docs/REAUDIT_2026-09-03.md:85, 461`: „MOE / MOP / TPM fehlen vollständig"; Volltextsuche
bestätigt: keine Modelle oder Felder in `backend/persistence/models.py`).

Der Katalog kennt `performance_budget` als Number-Attribut
(`attribute_definitions/stage_matrix.py:481`) — und die Dokumentation des Repositories
sagt selbst, warum das nicht reicht: **ein Skalar kann keine Zeitreihe halten**
(`docs/se/attribut/attribut-modell-3-stufen.md:146-160`; dort auch die Korrektur
„Skalar ≠ Zeitreihe", `:309`).

`attribute_definitions/stage_matrix.py:47-49` führt `Measure` als `entity`-Zeile mit
dem Zusatz, dass es **noch keine Tabelle** gibt — „intentionally absent and listed in
the report as open points".

---

## Alternativen

### Option A: `Measure`-Entität jetzt modellieren (MOE/MOP/TPM als `kind`) — VERWORFEN

**Beschreibung:** Eigene Entität `Measure` mit `kind ∈ {MOE, MOP, TPM}`, `unit`,
`target_value`, `threshold`, `current_value`, `measured_at` sowie Zeitreihe, wie es
`docs/se/attribut/attribut-modell-3-stufen.md:102` vorsieht.

**Abwägung:** Das ist die architektonisch vollständige Lösung — und sie ist die
**richtige**, falls ReqogniLoom je zum SE-Steuerungswerkzeug werden soll. Sie wird
**nicht** verworfen, weil sie schlecht ist, sondern weil **kein Nutzer sie braucht**:
kein Seed, kein Demo, kein Test und kein Leser im Repository trägt heute einen
Messwert. Eine versionierte Entität mit Zeitreihe ist der volle Preis einer Fähigkeit,
die ausschließlich theoretisch getragen wird.

**Risiko:** NIEDRIG technisch, HOCH als Produktinvestition

---

### Option B: `Measure` modellieren **ohne** Zeitreihe, als skalare `Goal`-Attribute — VERWORFEN

**Beschreibung:** `kind`, `unit`, `target_value`, `threshold` jetzt als Attribute anlegen
(`docs/se/attribut/attribut-modell-3-stufen.md:376` schlägt genau das als
Zwischenschritt vor).

**Abwägung:** Das ist bereits der Ist-Zustand — `measure_name`, `target_value`, `unit`
und `threshold` auf `Goal` (`attribute_definitions/stage_matrix.py:583-596`) sind genau
dieser Schritt, und sie sind im Katalog ausdrücklich als **„Interim bis zur
Measure-Entität (#393)"** markiert. Die Option wiederholt den Zustand, den die
Entscheidung bereits hat, und liefert zusätzlich den Anteil `kind`, der ohne
Zeitreihe fachlich irreführend ist: eine Momentaufnahme ist keine MOP.

**Risiko:** NIEDRIG, aber ohne Erkenntnisgewinn

---

### Option C: Nicht modellieren; die interim Goal-Attribute bleiben (GEWÄHLT)

**Beschreibung:** Es entsteht keine `Measure`-Entität. Die bestehenden
`Goal`-Attribute `measure_name`, `target_value`, `unit`, `threshold` bleiben als
gekennzeichneter Interim-Träger bestehen. Das `critical`-Label entfällt; der
Re-Audit wird Rationale-Referenz.

**Vorteile:**
- Drei unabhängige Evidenzlinien konvergieren (siehe Entscheidung)
- Kein Datenmodellumbau, keine Migration, keine neue Entität ohne Leser
- Die Interim-Kennzeichnung bleibt ehrlich sichtbar, statt still zu verschwinden

**Nachteile:**
- `REQ-L0-020` (Metrikbasiertes Steuern) wird nicht durch dieses Datenmodell getragen
- Der Katalog führt weiterhin Platzhalter-Attribute statt eines echten Messkonzepts
- Ein künftiger Bedarf an Zeitreihen trifft auf ein bereits belegtes Feld — die
  Migration ist dann nicht mehr gratis

**Risiko:** NIEDRIG

---

## Entscheidung

**MOE/MOP/TPM werden nicht modelliert. Die interim Goal-Attribute bleiben.**

Drei voneinander unabhängige Evidenzlinien konvergieren:

1. **Kein Träger.** Kein Seed, kein Demo-Datensatz, kein Test und kein Leser irgendwo im
   Repository trägt einen Messwert. Der Bedarf ist theoretisch.
2. **Der einzige vorhandene Träger ist ausdrücklich Interim.**
   `attribute_definitions/stage_matrix.py:583-596` — `measure_name` trägt den Helptext
   „Interim bis zur Measure-Entität (#393)"; `target_value`, `unit` und `threshold`
   stehen daneben.
3. **`custom_fields` kann keine Serie halten,** und das einzige erprobte Muster für eine
   versionierte Entität im Repository (`lineage_id` + `sequence_number` + unveränderliche
   Zeile, `Goal`/`MainGoal`) **ist** der volle Preis einer `Measure` mit Zeitreihe.

### Was diese Entscheidung *nicht* ist

Sie ist **keine** Aussage, dass Measures unwichtig sind. Sie ist die Aussage, dass
ReqogniLoom ein **Requirements-Tracking-Werkzeug** ist, und dass ein `critical`-Label
auf einer nicht modellierten Fähigkeit ein **falsches Signal** ist. Das `critical`-Label
kommt ab; `docs/REAUDIT_2026-09-03.md` wird die Rationale-Referenz.

### Aus der Triage zusätzlich festgehalten

**#877 (LogicalFunction / funktionale Architekturebene) und #879 (Meilensteine
SRR/PDR/CDR) sind nicht dieselbe Entscheidung und werden nicht mit dieser gebündelt.**
#879 braucht **keine** `Measure`-Entität: ein Meilenstein ist ein **Zeitpunkt-Ereignis
mit Freigabetor**, ein Measure ist ein **Wert mit Ziel und Schwelle**. Das ist ein
anderer Sachverhalt mit einer anderen Datenform.
`docs/superpowers/plans/2026-09-22-se-validation-completeness-spec.md:1067` gruppiert
alle drei als „Cluster 6" — **ein Cluster in einem Planungsdokument ist keine
gemeinsame Entscheidung.** Jeder der beiden Punkte bleibt eine eigenständige
Scope-Frage.

---

## Konsequenzen

**Positiv:**

- Kein Datenmodellumbau und keine Migration für eine Fähigkeit ohne Leser
- Die Evidenzlage ist dokumentiert und überprüfbar — das Re-Audit bleibt die
  nachvollziehbare Referenz
- Die Interim-Kennzeichnung der `Goal`-Attribute bleibt ehrlich im Katalog sichtbar
- `critical` wird von einem nicht modellierten Feature genommen: das Issue-Backlog
  signalisiert wieder echte Risiken statt theoretischer
- #877 und #879 behalten ihre eigene Scope-Frage, statt in einer Sammelentscheidung
  unterzugehen

**Negativ:**

- **`REQ-L0-020` (Metrikbasiertes Steuern des SE-Prozesses) wird von diesem
  Datenmodell nicht getragen.** Das ist eine bewusste Abnahme: die L0-Anforderung
  beschreibt eine Fähigkeit, die diese Entscheidung nicht liefert.
- Der Katalog führt weiterhin `performance_budget` (Number) und die
  `Goal`-Interim-Attribute — also Skalare an Stellen, an denen fachlich eine Zeitreihe
  hingehört. Der Interim-Charakter ist markiert, nicht behoben.
- Der Bedarf ist **nicht weg** — er ist vertagt. Ein späterer Bedarf trifft auf bereits
  belegte Felder; die dann nötige Migration ist teurer als eine von Anfang an
  geplante.
- Der Scope dieses ADR endet mit der Feststellung, dass zwei weitere Issues (#877, #879)
  ungelöst bleiben. Das ist Absicht, kein Versehen.

---
