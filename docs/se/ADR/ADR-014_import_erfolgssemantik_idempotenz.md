---
adr_id: ADR-014
title: "Fehler-/Erfolgssemantik und Idempotenz von Importen und Outbox: ein Import-Ergebnismodell, Idempotency-Key und event_id-Dedupe"
status: proposed
date: "2026-10-02"
deciders: [user, api-specialist]
affected_reqs: [REQ-147, REQ-L1-034, REQ-L2-RQ-001, REQ-072]
superseded_by: null
---

# ADR-014: Fehler-/Erfolgssemantik und Idempotenz von Importen und Outbox

**Status:** proposed
**Datum:** 2026-10-02
**Entscheider:** user (Entscheidungsinstanz/Freigabe), api-specialist (Autor)
**Review:** ausstehend. Der Lifecycle-Übergang `proposed → review` erfolgt durch
`concept-reviewer`, die DoD-/Traceability-Prüfung durch `validator`; den Statuswechsel
nimmt ausschließlich `se-architect`/User vor.
**Betroffene REQs:** REQ-147 (ReqIF-Import: atomar, Upsert per IDENTIFIER-Matching,
Dry-Run, Roundtrip idempotent, `docs/REQUIREMENTS.md:205`),
REQ-L1-034 (ReqIF-Import und -Export für MBSE-Datenaustausch,
`docs/se/traceability-matrix.md:132`),
REQ-L2-RQ-001 (ReqIF-Import; AC5 verlangt HTTP 422 bei invalider Datei,
`docs/se/traceability-matrix.md:512`,
`docs/se/L1/Gesamtsystem/L2/ReqIFServiceSystem/L2_ReqIFServiceSystem_Requirements.md:31-55,118-127`),
REQ-072 (Celery-Task-Idempotenz für Outbox-Dispatch: at-least-once mit idempotenten
Handlern, `docs/REQUIREMENTS.md:103`).
**Bezug:** Implementation-Plan-Slot **Kandidat v** — „Welche Fehler-/Erfolgssemantik und
welche Idempotenz garantieren Importe/Outbox?" (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:224`);
Empfehlung `api-specialist` Option A für Importe + MCP strikt JSON-RPC 2.0
(`IMPLEMENTATION_PLAN.md:234-236`); Entscheidungsvorlage und belegter Ist-Zustand
`docs/audit/2026-09/review/plan/INTERFACE_CONTRACTS.md` §2 (`:87-213`), §2.8 (`:207-213`),
§6 (`:532-547`), §7.2 (`:578-598`); Findings 071 (`success:true` hart), 072 (fehlende
Dedupe), 079 (leere `errors` bei Rollback), 083 (BOM); `AUD-2026-09-283` (Outbox
at-least-once, nicht-idempotenter Abonnent), Plan-Befund N3/DATA-09.

---

## Kontext

### Ist-Zustand: divergierende Import-Antworten (belegt)

ReqIF- und CSV-Import liefern heute **unterschiedliche** Ergebnismodelle und
**unterschiedliche** Erfolgsbegriffe. Belegt gegen die in `INTERFACE_CONTRACTS.md:89-100`
dokumentierten Code-Stellen:

| Ort | Befund |
|---|---|
| `reqif_import_service.py:482-489` | `success=True` **hart** kodiert; Fehler stehen nur in `needs/requirements/relations.errors` (Finding 071) |
| `reqif_import_service.py:413-443` | pro-Objekt-Rettung zählt `skipped`/`errors`, bricht aber **nicht** auf `success` durch |
| `reqif_import_service.py:264-270` | `ReqifEntityReport` kennt `created/updated/skipped/errors` — **kein** `failed` |
| `import_service.py:300-314` | DB-Rollback liefert `success=False` mit **leerer** `errors`-Liste (Finding 079) |
| `import_service.py:662,695` | `Artifact.objects.create` **ohne Dedupe** — wiederholter Import dupliziert (Finding 072) |
| `views.py:8018` | `decode("utf-8")` ⇒ BOM (`\ufeff`) landet im ersten Header-Feld (Finding 083) |
| `views.py:8060-8077` | CSV-Antwort **201/400** mit `success/imported_count/skipped_count/errors` |
| `views.py:8319` | ReqIF-Antwort **immer 200**, `success:true` |

Die Folgen sind genau die beiden Audit-Muster „stilles Scheitern" (`success:true` trotz
Fehlern) und „nicht auswertbare Teil-Erfolge" (`errors` leer bei Rollback): ein Aufrufer
kann Erfolg von Teilerfolg und Totalfehler nicht unterscheiden, und ein Retry erzeugt
Duplikate.

### Idempotenz/Dedupe fehlt auf beiden Seiten

- **Import:** Es gibt keinen Idempotenz-Schlüssel; ein zweiter Upload desselben Inhalts
  erzeugt neue Zeilen (Finding 072). REQ-147 verlangt zwar Upsert per
  IDENTIFIER-Matching und einen idempotenten Roundtrip, der CSV-Pfad hat diese Garantie
  aber nicht.
- **Outbox:** Die Transactional Outbox ist **at-least-once**. Der reale Abonnent
  `audit/writer.py:207` schreibt `audit_entry` **ohne** `event_id` (nackter INSERT),
  eine doppelte Zustellung erzeugt also eine zweite Schreibwirkung
  (`AUD-2026-09-283`; `application/event_bus.py:314,477-479`). REQ-072 fordert für den
  Outbox-Dispatch at-least-once-taugliche, idempotente Handler — die Forderung ist
  gestellt, aber nicht erzwungen.

### Kein bestehender ADR regelt das

Kein ADR des Repos beschreibt Import-Erfolgssemantik oder Idempotenz-Garantien.
`ADR-002_Event-Bus.md` betrifft die **Zustellung** (Producer/Consumer, Transaktions-Outbox),
**nicht** die Idempotenz der Abonnenten und nicht die Import-Ergebnisse — kein Konflikt,
aber auch keine Deckung. `ADR-004_traeger_modell_und_auc.md` berührt REQ-147 nur über den
`uid`-Träger, nicht die Erfolgs-/Status-Semantik.

### Keine bestehende REQ formuliert den Import-Vertrag

Es gibt **keine** REQ, die das Import-Ergebnismodell (`succeeded/skipped/failed` +
`cause.code`), die HTTP-Abbildung (207/422) oder den `Idempotency-Key` festschreibt. Die
**nächstliegenden belegten** Anforderungen sind:

- **REQ-147** (`docs/REQUIREMENTS.md:205`) — ReqIF-Import: atomar, Upsert per
  IDENTIFIER-Matching, Dry-Run, Roundtrip idempotent. Deckt die **Idempotenz-Absicht**,
  aber nicht das Ergebnismodell/Statuscodes.
- **REQ-L2-RQ-001** (`docs/se/traceability-matrix.md:512`;
  `L2_ReqIFServiceSystem_Requirements.md:123`) — AC5 verlangt **HTTP 422** bei invalider
  ReqIF-Datei; das stützt die 422-Zuordnung des Totalfehlers.
- **REQ-L1-034** (`docs/se/traceability-matrix.md:132`) — ReqIF-Import/-Export als
  Systemanforderung.
- **REQ-072** (`docs/REQUIREMENTS.md:103`) — at-least-once-taugliche, idempotente
  Outbox-Handler. Deckt die **Outbox-Seite** dieses ADR.

Für den **CSV-Erfolgsvertrag** existiert keine REQ in `docs/REQUIREMENTS.md` oder
`docs/se/traceability-matrix.md`; die nächstliegende belegte Import-Anforderung ist
REQ-L2-RQ-001. Es wird **keine** REQ neu erfunden und **keine** REQ-Datei geändert.
`open_adrs` existiert repo-weit nicht (`AUD-2026-09-333`); die REQ↔ADR-Verknüpfung bleibt
daher eine Folgeaufgabe (siehe Konsequenzen).

### Abgrenzung: MCP

Der native MCP-Server (`/mcp/`, JSON-RPC 2.0) ist **nicht** Gegenstand des
Import-Ergebnismodells. Er bleibt strikt spec-konform; Validierungsfehler werden als
JSON-RPC-Fehlerframe mit `-32602` ausgeliefert (`INTERFACE_CONTRACTS.md:421-528`), nicht
als Import-Ergebnis. Diese ADR entscheidet nur, dass MCP **bewusst ausgenommen** ist.

---

## Alternativen

### Option A: Ein Importmodell für alle Pfade + `Idempotency-Key`; MCP strikt JSON-RPC 2.0 — GEWÄHLT

**Beschreibung:** ReqIF- und CSV-Import liefern **dasselbe** Ergebnismodell
(`succeeded/skipped/failed` + `cause.code`, `success ⇔ counts.failed == 0`). Zusätzlich
gibt es einen optionalen `Idempotency-Key`-Header; als Fallback ohne Key wirkt eine
fachliche Dedupe über den natürlichen Schlüssel. Der MCP-Server wird **nicht** in das
Importmodell gezwungen, sondern bleibt strikt JSON-RPC 2.0. Für die Outbox gilt
at-least-once je Abonnent mit Dedup über `event_id`.

**Abwägung:** Beseitigt die **beiden** Audit-Muster zugleich: `success` wird aus
`failed` abgeleitet (kein stilles Scheitern), und Teil-Erfolge werden maschinenlesbar
(207 statt pauschalem 201/400). Die fachliche Dedupe sichert auch Clients ohne Key ab und
ist damit robuster als eine rein Header-getriebene Lösung. Der MCP-Server bleibt
standardkonform, weil JSON-RPC 2.0 ein öffentlicher Standard ist und ein Import-Modell
dort ein Spec-Bruch wäre.

**Risiko:** Der Beweis `success:true → false` bei Objektfehlern und der Statuswechsel
201/400 → 207/422 sind **breaking** für Bestandskonsumenten. Das Risiko wird über ein
dreiphasiges Deprecation-Fenster und ein Feature-Flag abgefedert (siehe Entscheidung).

---

### Option B: Nur MCP auf Spec bringen; Importe unverändert lassen — VERWORFEN

**Beschreibung:** Es wird ausschließlich der MCP-Fehlerkontrakt auf JSON-RPC 2.0
korrigiert (INT-07). Die divergierenden Import-Antworten (`success:true` hart, CSV
201/400, leere `errors` bei Rollback, fehlende Dedupe) bleiben bestehen.

**Abwägung:** Minimaler Eingriff, kein Breaking Change. Sie löst aber den Kern von
Finding 071/072/079 **nicht**: der Aufrufer kann Erfolg weiterhin nicht von stillem
Scheitern unterscheiden, und ein Retry dupliziert weiterhin. Die Intention von REQ-147
(idempotenter Re-Import) bleibt auf dem CSV-Pfad uneingelöst. Der Aufwand für MCP ist
Sofort-Fix (keine ADR nötig, `INTERFACE_CONTRACTS.md:526`) — dieses ADR wäre für Option B
überflüssig.

**Risiko:** MITTEL-HOCH — das P0-Muster „still erfolgreich" bleibt produktiv, und
`INT-01/04/06` bleiben blockiert.

---

### Option C: Verschärfte Erfolgsbedingung ohne programmatische Teil-Erfolgs-Auswertung — VERWORFEN

**Beschreibung:** `success` wird bei jedem Fehler auf `false` gesetzt, aber es gibt
**keine** strukturierte, maschinenlesbare Auswertung von Teil-Erfolgen (kein `counts`,
kein `items`, kein 207). Der Aufrufer erhält nur ein binäres `success` und einen
Klartext-Fehler.

**Abwägung:** Beseitigt wenigstens das stille Scheitern und ist einfach. Es liefert aber
**keine** programmatische Teil-Erfolgs-Auswertung: `0 < failed < total` ist von
`failed == total` nicht unterscheidbar, und der Aufrufer kann nicht erkennen, **welche**
Objekte persistiert wurden. Das widerspricht der Anforderung, Importe als teilbare
Operationen auswertbar zu machen, und macht ein sinnvolles Retry (nur die fehlgeschlagenen
Objekte) unmöglich.

**Risiko:** MITTEL — der Statuscode bleibt grob, Teil-Erfolge bleiben für Automatisierung
unsichtbar; `DATA-09` und die Idempotenz-Frage bleiben offen.

---

## Entscheidung

**Option A wird gewählt: ein Import-Ergebnismodell für alle Importpfade, ergänzt um
`Idempotency-Key` und fachliche Dedupe; MCP bleibt strikt JSON-RPC 2.0; die Outbox
dedupliziert je Abonnent über `event_id`.** Verbindlich und prüfbar:

### 1. Ein Ergebnismodell (`ImportResultV2`)

ReqIF- und CSV-Import liefern **dasselbe** Modell. Jedes Objekt/jede Zeile trägt genau
einen Status aus `succeeded | skipped | failed`. `success` folgt **einer** Regel:

> `success ⇔ counts.failed == 0`

`skipped` (z. B. `DUPLICATE`, `UNKNOWN_TYPE`) sowie Warnings beeinflussen `success`
**nicht**. `counts` enthält `succeeded`, `skipped`, `failed`, `total`. Die Maske ist
maschinenlesbar:

```json
{
  "success": false,
  "contract": "v2",
  "dry_run": false,
  "counts": { "succeeded": 12, "skipped": 3, "failed": 1, "total": 16 },
  "items": [
    {
      "row": 7,
      "identifier": "REQ-4711",
      "kind": "Requirement",
      "status": "failed",
      "cause": { "code": "PERSISTENCE_ERROR", "message": "<lokalisiert>" }
    }
  ],
  "warnings": ["Unrecognized column(s) ignored: Beschreibung"],
  "idempotent_replay": false,
  "request_id": "<uuid>"
}
```

Jeder Fehler/Warnhinweis trägt einen **stabilen, maschinenlesbaren** `cause.code`
(SCREAMING_SNAKE); die Klartext-`message` ist lokalisiert:

| `cause.code` | Bedeutung | Status |
|---|---|---|
| `DUPLICATE` | fachliches Duplikat (Idempotenz-/Dedupe-Treffer) | `skipped` (im `error`-Modus: `failed`) |
| `UNKNOWN_TYPE` | unbekannter SPEC-OBJECT-TYPE / `entity_type` | `skipped` |
| `MISSING_REQUIRED_FIELD` | Pflichtfeld leer | `failed` |
| `INVALID_VALUE` | Wert außerhalb des Wertebereichs | `failed` |
| `TYPE_MISMATCH` | falscher Typ (z. B. `term: 42`) | `failed` |
| `QUOTING_ERROR` | RFC-4180-Verstoß, Restzeile | `failed` |
| `PERSISTENCE_ERROR` | DB-/Integritätsfehler je Objekt | `failed` |
| `BOM_DETECTED` | BOM entfernt (Hinweis) | Warning |
| `UNKNOWN_COLUMN` | Spalte ignoriert | Warning |

Bei `failed > 0` enthält `items` **mindestens einen** Eintrag; bei einem Rollback ist
`items` **nie leer** und enthält mindestens einen `PERSISTENCE_ERROR` (Finding 079).

### 2. HTTP-Abbildung

| Situation | Status |
|---|---|
| `failed == 0` (skipped erlaubt) | **201** (CSV) / **200** (ReqIF; `dry_run` ohnehin 200) |
| `0 < failed < total` (Teilerfolg) | **207 Multi-Status** |
| `failed == total` (Totalfehler) bzw. `failed > 0` ohne jeden Erfolg | **422 Unprocessable Entity** |
| Request-Ebene: leere Datei, falsches Encoding, unbekannter `entity_type`, Größenlimit | **400** (unverändert) |

Die Request-Ebene (400) ist strikt von der **Objekt**-Ebene (207/422) getrennt: Ein
unparsbarer Request bleibt 400, unabhängig von Einzelobjekt-Ergebnissen. `dry_run`
persistiert nichts und liefert den Bericht statusgleich aus.

**Abgrenzung zu `REQ-L3-IMP-002` (CSV, All-or-Nothing):** REQ-L3-IMP-002 verlangt den
Rollback nur bei einem **DB-Fehler nach der Validierung**; Validierungsfehler einzelner
Zeilen blockieren laut REQ-L3-IMP-001 die übrigen Zeilen nicht. Damit ist 207 für
Validierungs-Teilerfolge (gültige Zeilen persistiert, ungültige als `failed`) mit
REQ-L3-IMP-002 vereinbar; ein DB-Fehler bleibt der Totalfehler-Fall (Rollback → 422).
Es wird **keine** REQ-Datei geändert.

### 3. `Idempotency-Key` und fachliche Dedupe

- **`Idempotency-Key`** (optionaler Request-Header, opak, **≤ 255 Zeichen**): Die erste
  Anfrage speichert `key → Result-Fingerprint` für ein definiertes Fenster. Ein Replay
  mit demselben Key liefert **dasselbe** Ergebnis mit `idempotent_replay: true` und
  **demselben** HTTP-Status, ohne eine zweite Schreibwirkung.
- **Fachliche Dedupe** (wirkt auch **ohne** Key): Treffer über den natürlichen Schlüssel
  je Entität (ReqIF: `reqif_identifier`; CSV: entity-spezifischer Natural Key) ⇒
  `skipped` mit `DUPLICATE`. Konfigurierbar über `duplicate_policy`:
  - `skip` (**Default**) ⇒ Status `skipped`, `cause.code = DUPLICATE`;
  - `error` ⇒ Status `failed`, `cause.code = DUPLICATE` (damit `success=false`).

### 4. Outbox-Idempotenz

Die Outbox bleibt **at-least-once je Abonnent**. Jeder Abonnent MUSS über die
`event_id` deduplizieren, sodass eine wiederholte Zustellung **genau eine**
Schreibwirkung erzeugt (REQ-072). Prüfbar ist das je realem Abonnenten
(`ContextGraphProjector`, `MemoryProjector`, `WebhookDispatcher`; `AUD-2026-09-283`) über
einen `event_id`-Dedup-Fenster- bzw. `get_or_create`-Nachweis; `audit_entry` erhält die
`event_id`. Es darf nie eine zweite Schreibwirkung für dasselbe `event_id` entstehen.

### 5. Deprecation-Fenster (3-phasig) und Rollback

Kein Breaking Change ohne Fenster (mindestens 2 Minor-Releases **oder** 90 Tage, whichever
is longer) mit `Deprecation: true`- und `Sunset`-Header:

| Phase | Inhalt | Bricht |
|---|---|---|
| **1 — additiv** | `contract`, `counts`, `items`, `idempotent_replay`, `request_id` ergänzt; Legacy-Keys `imported_count`, `skipped_count`, `errors`, `status`, `needs/requirements/relations` bleiben; `success` noch **alt** (ReqIF weiter `true`). | nichts |
| **2 — Semantik** | `success = (failed == 0)`; Teilerfolg ⇒ 207, Totalfehler ⇒ 422. | Clients, die `success === true` auch bei `failed > 0` erwarten |
| **3 — Cleanup** | Legacy-Keys entfernt. | nicht migrierte Clients |

**Rollback:** Feature-Flag `IMPORT_CONTRACT_V2` (Default in Phase 1 `off`); Abschalten
stellt das Phase-1-Verhalten wieder her. Importe sind atomar bzw. je Objekt gekapselt —
kein Datenverlust. Der `Idempotency-Key`-Replay ist additiv und separat abschaltbar.
(Bezug: `INTERFACE_CONTRACTS.md` §2.4 `:165-179`, §2.7 `:201-205`.)

### 6. MCP bleibt strikt JSON-RPC 2.0

MCP wird **nicht** in das Importmodell gezwungen. Alle Fehler bleiben
JSON-RPC-2.0-Fehlerframes mit **integer** `code`; Validierungsfehler werden `-32602`
(nie `-32603`), Tool-Ausführungsfehler bleiben `result.isError: true`. Das ist eine
spec-getriebene Korrektur (INT-07), keine ADR-blockierte Semantikfrage.

**Diese Entscheidung war blockierend** für `INT-01` (ReqIF), `INT-04` (CSV),
`INT-06` (gemeinsames Fehlermodell) und `DATA-09` (`IMPLEMENTATION_PLAN.md:372`;
`INTERFACE_CONTRACTS.md:207-213`). Mit `accepted` werden die Vorschläge aus
`INTERFACE_CONTRACTS.md` §2 vom Vertragsvorschlag zum verbindlichen Vertrag. Bis dahin
gilt: keine Umsetzung der ADR-blockierten Teile (BOM-Fix `utf-8-sig`, `errors`-nie-leer
und `request_id` sind davon unabhängig und nicht blockiert).

---

## Konsequenzen

**Positiv:**

- **Erfolg wird verlässlich:** `success ⇔ counts.failed == 0` gilt für **beide** Importe;
  der P0-Kern von Finding 071 (`success:true` trotz Fehler) ist beseitigt. Der Aufrufer
  kann Erfolg, Teilerfolg und Totalfehler unterscheiden.
- **Teil-Erfolge werden automatisierbar:** 207 + `counts`/`items` erlauben gezieltes
  Retry nur der `failed`-Objekte und maschinenlesbare Auswertung.
- **Retry-Sicherheit:** `Idempotency-Key` und fachliche Dedupe verhindern Duplikate
  (Finding 072); der ReqIF-Roundtrip aus REQ-147 wird auch auf dem CSV-Pfad abgesichert.
- **Outbox-Korrektheit:** `event_id`-Dedupe liefert die von REQ-072 geforderte genau-eine
  Schreibwirkung je Event und schließt `AUD-2026-09-283`.
- **MCP bleibt standardkonform:** kein Spec-Bruch durch ein fremdes Importmodell.

**Negativ:**

- **Bewusster Breaking Change:** ReqIF wechselt `success` von `true` auf `false` bei
  Objektfehlern (Kern von Finding 071). CSV wechselt bei Teil-/Totalfehler von 201/400 auf
  **207/422**. Clients, die `success === true` bzw. den alten Statuscode prüfen, müssen
  migrieren; deshalb sind Fenster und Flag Teil der Entscheidung.
- **Migrationsaufwand für `errors`-Parser:** Wer die flache `errors`-Liste liest, muss auf
  `items[].cause` umstellen (Legacy bleibt bis Phase 3).
- **Zusätzlicher Zustand:** `Idempotency-Key`-Speicherung und `event_id`-Dedup-Fenster
  benötigen persistente Ablage/Cleanup — ein Betriebs- und Speicheraufwand, der geplant
  und begrenzt werden muss.
- **`duplicate_policy: error`** kann einen bislang „erfolgreichen" Re-Import in einen
  Fehler verwandeln; das ist beabsichtigt, aber eine Verhaltensänderung pro Workspace.
- **Keine REQ trägt den Vertrag:** Die Zuordnung zu REQ-147/REQ-L1-034/REQ-L2-RQ-001/
  REQ-072 ist eine **Näherung**, keine getrackte Verknüpfung; `open_adrs` fehlt repo-weit.

---

## Folgeaufgaben (nicht Teil dieser Entscheidung)

1. **`open_adrs`-Feld einführen** (`AUD-2026-09-333`), damit die betroffenen REQs dieses
   ADR referenzieren können. Bis dahin wird **keine** REQ-Datei geändert.
2. **Lifecycle-Review:** `proposed → review` durch `concept-reviewer`, DoD-/Traceability-
   Prüfung durch `validator`; Statuswechsel nur durch `se-architect`/User.
3. **`event_id`-Nachweis je realem Outbox-Abonnenten** (`ContextGraphProjector`,
   `MemoryProjector`, `WebhookDispatcher`) inkl. `audit_entry.event_id`
   (`AUD-2026-09-283`).
4. **Idempotency-Key-Lebenszyklus festlegen** (Fensterlänge, Cleanup, Kollisionsverhalten,
   Antwort bei noch laufender identischer Anfrage).
5. **`cause.code`-Katalog mit INT-06 koordinieren** (gemeinsames Fehler-Envelope,
   `request_id`) und im OpenAPI-Schema deklarieren.
6. **Vertragsvorschläge aus `INTERFACE_CONTRACTS.md` §2** nach diesem `accepted`-Status
   als verbindlichen Vertrag nachziehen.

---

*Erstellt durch `api-specialist` am 2026-10-02 als reines Doku-Artefakt. Kein
Produktcode, keine Migration, keine REQ-ID erfunden; Belege gegen
`docs/audit/2026-09/review/plan/INTERFACE_CONTRACTS.md` §2/§7.2 und die genannten
Code-Stellen geprüft. Status `proposed`; Review und Freigabe stehen aus.*
