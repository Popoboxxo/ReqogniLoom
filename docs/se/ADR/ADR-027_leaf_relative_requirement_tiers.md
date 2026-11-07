---
adr_id: ADR-027
title: "Requirement-Stufen werden leaf-relativ aus der Allokation berechnet"
status: accepted
date: 2026-11-05
deciders: [se-architect, user]
affected_reqs: [REQ-L0-039, REQ-L0-019]
superseded_by: null
---

# ADR-027: Requirement-Stufen werden leaf-relativ aus der Allokation berechnet

## Kontext

ADR-005 machte `Requirement.level` zu einem abgeleiteten, schreibgeschützten
Feld, leitete den Wert aber ausschließlich aus der Requirement-Hierarchie
(Eltern + 1) ab. Das Modell kennt fest vier Stufen und klemmt tiefere Zweige auf
`NULL`. Mit der Allokation auf Architekturelemente (N:1, P2) gibt es eine
stärkere Quelle: die Position des Elements im Baum. Die bisherige Tiefenregel
(`ARCHITECTURE_DEPTH_TO_LEVEL`) ist starr, setzt die Wurzel immer auf L1 und
kann ungleich tiefe Zweige nicht sauber abbilden.

Der Product Owner hat am 2026-11-04 entschieden: Die Stufe eines Elements wird
**vom Blatt her** bestimmt; die Leiter ist pro Workspace konfigurierbar; es gibt
kein Klemmen; `level` bleibt dauerhaft der Integer-Alias (Position + 1).

## Alternativen

- **Tiefen-Relativ (Ist-Zustand, abgelehnt):** Stufe = Baumtiefe, feste Skala
  1–4, tiefere Zweige `NULL`. Einfach, aber ungleich tiefe Zweige werden falsch
  oder gar nicht abgebildet, und die feste Skala widerspricht der konfigurierbaren
  Leiter.
- **Leaf-relativ (gewählt):** Wurzel → erste Stufe; sonst `from_end`-Eintrag mit
  Höhe = längster Weg zum Blatt; sonst `middle`. Der Blattabstand macht den Wert
  unabhängig von der absoluten Tiefe und eindeutig für gemischte Zweige.

## Entscheidung

`Requirement.tier_key` trägt den stabilen Leiter-Schlüssel, `level` bleibt der
permanente Integer-Alias (`position + 1`). Die Quelle hat folgende Rangfolge:

1. `manual` — ein expliziter menschlicher Override bleibt unangetastet;
2. `allocation` — die Stufe des allokierten Architekturelements
   (`level_source = derived_allocation`);
3. Hierarchie — die Stufe des Eltern-Requirements, eine Position weiter zur
   Blattseite (`derived_hierarchy`); von der letzten Position gibt es keine
   weitere Stufe (`unresolved`);
4. Typ-Default — die erste Leiterposition (`derived_type`);
5. `unresolved` — `tier_key`/`level` bleiben `NULL`, nichts wird geraten.

Die Leiter (`WorkspaceTier`) hat genau einen `first`-Eintrag, höchstens einen
`middle` und genau einen `from_end=0` (Blatt). Es gibt keine feste Stufenzahl und
kein Klemmen. Der einzige Schreiber bleibt
`application.tier_compute.recompute_workspace_tiers`.

## Konsequenzen

- Positiv: gemischte Baumtiefen sind eindeutig; die Stufe folgt der
  Architektur-Allokation; Betreiber können die Namen der Stufen ändern, ohne
  Daten zu berühren.
- Positiv: `level` bleibt als Alias erhalten; bestehende Exporte und Filter
  funktionieren weiter, solange sie die Position lesen.
- Negativ/Bruch: Der alte TRACE-P5-L4-Skip ist ausgemustert. Leaf-relative
  Stufen legen jedes Blatt auf die letzte Position; der Skip hätte damit den
  gesamten Zerlegungsgraphen von der Prüfung ausgenommen.
- Negativ: Ein Baseline-Diff kann zusätzlich „Stufe verschoben“ melden, wenn
  eine Baumänderung die Stufe verschiebt. Das ist gewollt (R11).
- **Literaturhinweis (unverifiziert):** Die Behauptung, eine Norm lege die
  Stufenzahl fest, wird hier nicht zitiert. Vor einer externen Veröffentlichung
  sind die Quellen zu prüfen (R11).
