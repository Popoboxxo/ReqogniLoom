---
adr_id: ADR-007
title: "SE-Regeln werden am Baseline-Gate durchgesetzt; die drei Vokabulare kollabieren auf die Audit-Registry"
status: accepted
date: "2026-09-27"
deciders: [user]
affected_reqs: [REQ-L0-049, REQ-L0-011]
superseded_by: null
---

# ADR-007: SE-Regeln werden am Baseline-Gate durchgesetzt; die drei Vokabulare kollabieren auf die Audit-Registry

**Status:** accepted
**Datum:** 2026-09-27
**Entscheider:** user
**Betroffene REQs:** REQ-L0-049 (Stage-Gating & Guardrails — Strenge SE-Regeln),
REQ-L0-011 (Vollständiger Audit-Trail)
**Bezug:** Issue **#19**; `traceability/audit/registry.py:54-104, 261-279`;
`application/baseline_facade.py:488`; `application/audit_service.py:406-441`;
`baseline/waivers.py` (`BaselineGateWaiver`), `baseline/models.py:190-215`;
`attribute_definitions/stage_matrix.py:30-46, 776`;
`attribute_definitions/field_validation.py`;
`traceability/audit/rules/trace_derivation_allocation.py:403-428`

---

## Kontext

Drei Regel-Vokabulare koexistieren und referenzieren einander **nicht**:

**(a) `REQ_MUST_HAVE_SOURCE`, `REQ_MUST_HAVE_ALLOCATION`, `REQ_MUST_HAVE_TEST_LINK`**
— dokumentiert in `docs/se/attribut/attribut-modell-3-stufen.md:363` und
`docs/se/attribut/attribut-detailtabellen.md:333`, **nirgends implementiert**. Zwei
weitere IDs aus dem Issue — `REQ_MUST_BE_ATOMIC` und `NO_ORPHAN_TRACE_LINKS` — haben
**null** Fundstellen im gesamten Repository.

**(b) `CONS-P9/P10/P11`, `TRACE-P1..P7`, `VERIF-P8`, `VAL-P1`, `ARCH-003`** —
`traceability/audit/registry.py:54-104`, vierzehn Regeln. Die Registry ist ein
solider, erweiterbarer Wirt (`@register_rule`, `registry.py:261-279`).

**(c) Attribut-`required` / `stage_mandatory`** — `attribute_definitions/stage_matrix.py:776`,
durchgesetzt von `attribute_definitions/field_validation.py` **bei Create und Update**.

**Der empirische Befund, der entscheidet:** Create/Update-Durchsetzung wurde bereits
versucht und **widerlegt**. `attribute_definitions/stage_matrix.py:30-32` und `:36-46`
halten es fest: `mandatory_fields` als Create-Gate zu erzwingen hat 400 auf **jeden**
bestehenden Client, **jeden** Quick-Create-Dialog und rund **fünfzehn** E2E-Specs
ausgelöst (Migration `0005_relax_requirement_create_required`; Regressionstest
`rest_api/tests/test_bootstrapped_definition_allows_creates.py:36-46`). Dieselbe Datei
stellt `stage_mandatory` als „seeded and discoverable but deliberately not yet
consumed" dar (`:36-39`).

---

## Alternativen

### Option A: Relation-Regeln als Create/Update-Gate erzwingen — VERWORFEN

**Beschreibung:** `REQ_MUST_HAVE_*` wird über die Attribut-Validierung auf Create und
Update durchgesetzt, analog zu `required`/`stage_mandatory`.

**Abwägung:** Genau der Weg, der bereits einmal gegangen ist und dokumentiert
widerlegt ist. Er erzeugt keine *bessere* SE-Qualität, sondern eine breitere
Kontaktfläche mit Clients — und die Korrektur (Lockerung) kostete eine eigene
Migration plus Regressionstest. Ein Gate, das zurückgenommen werden muss, ist kein
Gate.

**Risiko:** HOCH — empirisch bereits gescheitert

---

### Option B: Drei Vokabulare parallel weiterführen, jede für sich — VERWORFEN

**Beschreibung:** (a) bleibt Dokumentation, (b) bleibt Registry, (c) bleibt
Feldvalidierung; jede Ebene behält ihr eigenes Regelwerk.

**Abwägung:** Erzeugt genau die Lage, die #19 meldet: drei Sätze von Ids, von denen
zwei Drittel nicht existieren, ohne dass ein Nutzer erkennen kann, welcher gilt.
`(c)` bleibt dabei aus gutem Grund getrennt — es ist ein **Payload-Vertrag**, keine
Regel —, aber (a) und (b) beschreiben denselben Sachverhalt in zwei Sätzen.

**Risiko:** MITTEL — Documentation-Drift bleibt die Ursache des Issues

---

### Option C: `REQ_MUST_HAVE_ALLOCATION` als BLOCKER promoten — VERWORFEN

**Beschreibung:** Die Allocations-Regel wird auf `TRACE-P2` abgebildet und von WARNING
auf BLOCKER gehoben, damit das Baseline-Gate sie durchsetzt.

**Abwägung:** Reproduziert exakt die Kalibrierungsregression aus #581, dokumentiert
in `traceability/audit/rules/trace_derivation_allocation.py:403-428`: „100% blocker
rate, unpassable baseline gate (#490/#513/#821)". Das Gate wäre damit dauerhaft
unpassierbar.

**Risiko:** HOCH — reproduzierter Kalibrierungsbruch

---

### Option D: Relation-Regeln am Baseline-Gate; Vokabular kollabiert auf (b); `source` wird Konvention (GEWÄHLT)

**Beschreibung:** Der einzige Durchsetzungspunkt für Relation-Regeln ist das
Baseline-Gate. Die Ids werden auf die bestehende Registry abgebildet, nicht
dupliziert. `REQ_MUST_HAVE_SOURCE` wird gar keine Regel.

**Vorteile:**
- Der Erzeuger existiert bereits und ist **einzig**:
  `application/baseline_facade.py:488` → `AuditService.blocking_findings`
  (`application/audit_service.py:406-441`)
- Es ist die einzige Stelle mit einem vollständigen Remediation-Pfad — einer
  Waiver **pro Finding** (`baseline/waivers.py`, `BaselineGateWaiver`,
  `baseline/models.py:190-215`). Ein Create-Gate hat keinen.
- Ein Registry-Set statt dreier Satzmengen: neue Regeln haben genau einen Ort

**Nachteile:**
- Erst zur Baseline hin wird die Relation geprüft; ein frisch angelegtes Artefakt
  trägt den Befund früher als heute (der heute gar nicht geprüft wird)
- Die Abbildung muss gepflegt werden, sonst driftet die Dokumentation erneut

**Risiko:** NIEDRIG

---

## Entscheidung

1. **Relation-Regeln werden am Baseline-Gate durchgesetzt, nicht bei Create/Update.**
   Der Erzeuger existiert bereits und ist einzig: `application/baseline_facade.py:488`
   → `AuditService.blocking_findings` (`application/audit_service.py:406-441`). Es ist
   die einzige Stelle, die bereits einen vollständigen Remediation-Pfad besitzt — einen
   Waiver pro Finding (`baseline/waivers.py`, `BaselineGateWaiver`,
   `baseline/models.py:190-215`).
   **Felderobligationen bleiben bei `field_validation.py`**, das bereits bei Create
   **und** Update mit feldgenauen 400-Details ablehnt. Feldpflicht und
   Relationspflicht werden damit nicht vermischt.

2. **Das Vokabular kollabiert auf (b).**
   - `REQ_MUST_HAVE_ALLOCATION` → **`TRACE-P2`**, und bleibt **WARNING**. Eine
     Promotion auf BLOCKER reproduziert den dokumentierten Kalibrierungsbruch aus #581
     (`trace_derivation_allocation.py:403-428`: „100% blocker rate, unpassable baseline
     gate (#490/#513/#821)").
   - `REQ_MUST_HAVE_TEST_LINK` → **`VERIF-P8` plus `TRACE-P6`**, damit als **abgedeckt**
     geschlossen.
   - `REQ_MUST_BE_ATOMIC` und `NO_ORPHAN_TRACE_LINKS` werden aus der Dokumentation
     **entfernt** — sie haben keine Implementierung und keine Code-Fundstelle, auf die
     sie sich abbilden ließen.
   - (b) bleibt das **einzige** Registry. (c) bleibt ein **eigener** Mechanismus, weil
     es ein Payload-Vertrag ist und keine Regel.

3. **`REQ_MUST_HAVE_SOURCE` wird eine Coverage-Konvention, keine Regel.** Der Code
   trägt das: `source` ist ein reines Nutzer-Freitextfeld — **kein Writer** füllt es
   (die LLM-Ableitung mappt nur `rationale`, `mcp_server/tools/ai_derivation.py:140-142`;
   der CSV-Export lässt es weg, `application/export_service.py:121-132`; der ReqIF-Export
   ebenfalls, `reqif_export_service.py:246-253`). Eine Regel, die ein Artefakt wegen
   eines Feldes zurückweist, das nichts befüllen kann, ist eine Regel, die Nutzer
   formal erfüllen lernen. Sie wird stattdessen im Attribut-Katalog dokumentiert.

---

## Konsequenzen

**Positiv:**

- Genau **eine** Durchsetzungsstelle für Relation-Regeln, mit Remediation-Pfad
  (Waiver pro Finding) — statt Regeln, die es nur auf Papier gibt
- Die Ids aus #19 hören auf, zwei Wahrheiten zu behaupten: `REQ_MUST_HAVE_TEST_LINK`
  ist geschlossen als abgedeckt, die beiden Phantom-Ids sind weg
- Die #581-Kalibrierung wird nicht wiederholt; `TRACE-P2` bleibt WARNING
- Feldpflicht und Relationspflicht sind getrennte Mechanismen mit getrennten
  Fehlerbildern (feldgenaues 400 vs. Baseline-Befund mit Waiver)

**Negativ:**

- **`stage_mandatory` bleibt bis zum AWMS-Backfill (#940) unkonsumiert.** Würde es
  jetzt durchgesetzt, würde jedes bereits freigegebene Artefakt über Nacht
  unfreigebbar — dieselbe Grandfathering-Regel, der `required` folgt. Das bleibt eine
  **benannte Abhängigkeit**, keine stille Lücke.
- Die Relation wird erst zur Baseline hin geprüft; ein neu angelegtes Artefakt trägt
  den Befund später als ein Create-Gate ihn melden würde.
- Für die Zuordnung der Ids auf Registry-Regeln braucht es eine gepflegte Abbildung —
  ohne sie entsteht genau die Doku-Drift, die dieses ADR beseitigt.
- `REQ_MUST_HAVE_SOURCE` wird **keine** durchgesetzte Regel. Das ist eine bewusste
  Abnahme von Maschinenprüfung zugunsten einer Konvention — wer Vollständigkeit
  erzwingen wollte, verliert diese Möglichkeit.

---
