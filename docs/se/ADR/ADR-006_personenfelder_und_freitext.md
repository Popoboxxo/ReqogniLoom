---
adr_id: ADR-006
title: "Zwei Feldarten: Personenreferenz (System) und Freitext; Stakeholder als Mehrfachauswahl"
status: accepted
date: "2026-09-27"
deciders: [user]
affected_reqs: [REQ-L0-047, REQ-L0-042]
superseded_by: null
---

# ADR-006: Zwei Feldarten: Personenreferenz (System) und Freitext; Stakeholder als Mehrfachauswahl

**Status:** accepted
**Datum:** 2026-09-27
**Entscheider:** user
**Betroffene REQs:** REQ-L0-047 (Präzises, domänenspezifisches Datenmodell),
REQ-L0-042 (Ontologie-Vielfalt)
**Bezug:** Issue **#1088**; `persistence/models.py:818, 1223-1238, 1250-1265`;
`application/artifact_attribute_gateway.py:147-175`;
`attribute_definitions/stage_matrix.py:180, 425-448`;
`attribute_definitions/migration_plan.py:3`

---

## Kontext

Drei Felder sind aus **demselben** Grund Freitext: `Artifact.custom_fields` ist eine
**flache** Map und weist verschachtelte Dicts ab (REQ-L2-AS-037;
`persistence/models.py:1250-1265` — Schlüssel Strings, Werte `str`/`int`/`float`/`bool`/`null`).
Ein Objektwert kann dort strukturell nicht abgelegt werden.

`owner` und `reporter` haben dieses Problem **anders** gelöst: als
**Actor-Fremdschlüssel auf `Artifact` selbst**
(`persistence/models.py:818` `class Actor`, `:1223-1238`), verdrahtet über
`application/artifact_attribute_gateway.py:147-175`. `Actor` trägt echte interne
Benutzer *und* externe Platzhalter (`kind="user"` / `kind="external"`).

Der Kommentar in `attribute_definitions/stage_matrix.py:437-441` ist insofern
**irreführend**: er vertagt die Lücke auf „WS7/AWMS #940". AWMS ist aber das
**Attribut-Wert-Migrationssystem** (`attribute_definitions/migration_plan.py:3`) —
der **Actor-Träger selbst ist bereits gelandet**, als WS2/#936. Der Verweis zeigt auf
die falsche Arbeit.

**Korrektur der Ausgangsprämisse von #1088:** `source` ist ein `Requirement`-Feld,
`stakeholder` ist ein `StakeholderNeed`-Feld. Die beiden sind **keine Konkurrenten auf
einem Entity** — die Issue-PRämise war insoweit falsch.

Der Helptext zu `source` beantwortet heute in einem Satz zwei Fragen:
`"Herkunft/Stakeholder der Anforderung."` (`stage_matrix.py:425-429`). Genau das ist
der wörtliche Beschwerdekern von #1088.

---

## Alternativen

### Option A: Alle drei Felder bleiben Freitext (Status quo) — VERWORFEN

**Beschreibung:** `deciders`, `assignee` und `stakeholder` bleiben skalare
Textattribute.

**Abwägung:** Kein Aufwand, aber `deciders` und `assignee` bleiben getippte Namen
statt echter Referenzen: keine FK-Integrität, keine Anzeigeauflösung, keine
Umbenennungsresilienz — genau die Eigenschaften, wegen derer `owner`/`reporter`
einen Actor-Träger bekommen haben. Der Status quo behandelt drei Felder
unterschiedlich, obwohl zwei davon denselben Sachverhalt meinen.

**Risiko:** MITTEL — bekannter Mangel bleibt bestehen

---

### Option B: Alle drei Felder werden Personenfelder auf `Actor` — VERWORFEN

**Beschreibung:** `deciders`, `assignee` **und** `stakeholder` werden (Multi-Value-)
Actor-Referenzen.

**Abwägung:** Für `deciders` und `assignee` richtig, für `stakeholder` **falsch**.
Der Stakeholder eines Needs ist eine **Rolle oder Gruppe** (ISO 42010, so bereits in
`stage_matrix.py:445` formuliert) — eine *Klassifikation*, keine *Identität*. Ein
Actor-Feld zwingt hier erzwungenermaßen dazu, für jede Rolle einen Actor-Datensatz
anzulegen; das vervielfacht die Entitäten und macht die Rollenwahl unmöglich, die
ISO 42010 verlangt.

**Risiko:** MITTEL — falsche Typisierung erzwingt Datenmodell-Müll

---

### Option C: Verschachtelte Objektwerte in `custom_fields` zulassen — VERWORFEN

**Beschreibung:** `custom_fields` wird um verschachtelte Dicts erweitert, alle drei
Felder werden dort als Objekt gespeichert.

**Abwägung:** Hebt die Randbedingung auf, statt sie zu lösen — und bricht dabei
REQ-L2-AS-037, den GIN-Index-Zugriffsweg und die flache Vertragserwartung, auf die
sich Import/Export und der Bundle-Vertrag verlassen. Ein Objekt im Träger, den das
Attributsystem nicht kennt, ist wieder ein Feld ohne Validierung.

**Risiko:** HOCH — bricht einen bestehenden Datenvertrag

---

### Option D: Zwei Feldarten — Personenfeld (System) und Freitext; `stakeholder` als katalogdefinierte Mehrfachauswahl (GEWÄHLT)

**Beschreibung:** Das Attributsystem erkennt für diesen Fallkontext **zwei** Feldarten:
ein **Personenfeld**, das auf die systemeigenen internen Actor-Daten referenziert, und
ein **Freitextfeld**. Ein Personenfeld ist eine echte Referenz, kein von Hand
getippter Name. `stakeholder` wird eine **Mehrfachauswahl mit Katalog-Optionen**.

**Vorteile:**
- `deciders` und `assignee` erhalten den bereits erprobten, in `owner`/`reporter`
  gelebten Mechanismus — kein neuer Mechanismus, sondern eine zweite Anwendung
- `stakeholder` bleibt das, was es ist: eine Auswahl aus Klassifikationen, je
  Workspace über den Attribut-Katalog definierbar, wie andere Enum-Optionen
- Jede der drei Felder bekommt den Typ, der zu ihrem Sachverhalt passt

**Nachteile:**
- Zwei Felder brauchen **zwei** neue Mechanismen (Multi-Value-Actor-Referenz und
  Multi-Value-Enum) — das ist mehr Code als eine gemeinsame Lösung
- Der Katalog muss Optionslisten für Mehrfachauswahl überhaupt erst anbieten können

**Risiko:** NIEDRIG–MITTEL

---

## Entscheidung

1. Das Attributsystem erkennt **zwei Feldarten** für diesen Fallkontext: ein
   **Personenfeld** mit Referenz auf die systemeigenen internen Actor-Daten und ein
   **Freitextfeld**. Ein Personenfeld ist eine **echte Referenz**, kein von Hand
   getippter Name.
2. **`StakeholderNeed.stakeholder` wird eine Mehrfachauswahl mit im Attribut-Katalog
   definierten Optionen** — **kein** Personenfeld. Der Stakeholder eines Needs ist
   eine Rolle oder Gruppe (ISO 42010), also eine Klassifikation und keine Identität.
   Die Optionen sind pro Workspace über den Attribut-Katalog definierbar, wie andere
   Enum-Optionen.
3. **`Adr.deciders` wird ein Personenfeld aus dem System** (Multi-Value-Actor-Referenz).
4. **`Issue.assignee` wird ebenso.**

### Aus derselben Untersuchung fallendes Aufräumen

- **`origin_link` hat null Schreiber.** Im gesamten Backend existiert **kein** einziger
  Writer; es gibt nur zwei Katalog-Referenzen
  (`attribute_definitions/stage_matrix.py:180, 430-434`). Das Attribut ist ein Phantom:
  es wird als Feld präsentiert, das niemand befüllt. Es wird **entweder verdrahtet
  oder entfernt** — nicht in dieser Form weitergeführt.
- **Der `source`-Helptext wird auf Herkunft geschärft.** Der heutige Text
  `"Herkunft/Stakeholder der Anforderung."` beantwortet zwei Fragen in einem Satz
  (`stage_matrix.py:425-429`) und wird auf origin-only zugespitzt.

---

## Konsequenzen

**Positiv:**

- `deciders` und `assignee` teilen **einen** Mechanismus — denselben, den `owner` und
  `reporter` bereits benutzen. Für die Domänensemantik ist das die stärkere der
  beiden Identitätsbindungen, und der Mechanismus ist bereits gelandet und verdrahtet.
- `stakeholder` wird befüllbar, ohne dass Rollen als Datensätze erfunden werden
  müssen; die Optionen sind workspace-spezifisch konfigurierbar.
- Die Phase-Bestimmung, wer welchen Input bekommt, erfolgt implizit über den Feldtyp —
  die irreführende Kommentarlage in `stage_matrix.py:437-441` entfällt.
- `origin_link` wird vom Phantom-Attribut zu einer Entscheidung: verdrahtet oder weg.

**Negativ:**

- **Sub-Entities brauchen ihre eigene `actor`-typisierte Kernspalte.** Das Muster
  existiert bisher **nur auf `Artifact`** (`persistence/models.py:1223-1238`), nicht
  pro Entity-Typ. `Adr.deciders` und `Issue.assignee` sind die ersten Fälle, die diese
  Erweiterung brauchen.
- **Die Mehrfachauswahl für `stakeholder` ist ein eigenständiger Mechanismus** — eine
  Multi-Value-Variante des bestehenden Enum-Typs, **nicht** dieselbe Technik wie der
  Actor-Träger. Zwei Mechanismen, nicht einer.
- Der Katalog muss Optionslisten für Mehrfachauswahl erst anbieten können; das ist
  Voraussetzung, nicht Nebenaspekt.
- `origin_link` zu entfernen ist eine **sichtbare** Katalog-Änderung: Nutzer, die das
  Feld heute (leer) sehen, sehen es danach nicht mehr.

---
