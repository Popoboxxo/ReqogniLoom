---
adr_id: ADR-025
title: "Additiver Baseline-Rollback mit CCB-Freigabe"
status: proposed
date: 2026-10-31
deciders: [user]
affected_reqs: [REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-012]
superseded_by: null
type: ADR
scope: baseline
author_agent: documenter
---

# ADR-025: Additiver Baseline-Rollback mit CCB-Freigabe

**Status:** proposed (Entwurf 2026-10-31) — der Statuswechsel auf `accepted` ist
Nutzerentscheidung, nicht Teil dieses Dokuments.
**Datum:** 2026-10-31
**Entscheider:** `user`; **Text:** `documenter` (Rollen gemäß Plan F §F4.0).
**Betroffene REQs:** REQ-L2-BL-001, REQ-L2-BL-002 (Immutability der Baseline-Tabellen),
REQ-L2-BL-012.
**Bezug:** Issue **#50** (Kommentar 2: Rollback additiv als neue Version, Immutability-Zusage
halten); Plan `docs/plans/2026-10-21-plan-f-dokumente-baselines.md` §F4.0 (`:383`), §F4.4
(`:482`), §(vii) Risiken (`:739`), §(ix) ENT-F4/ENT-F6 (`:793`, `:795`).
**Beleg (Code, gelesen am 2026-10-31):** `backend/baseline/migrations/0001_initial.py:159-193`;
`backend/baseline/migrations/0011_baseline_admin_delete_trigger.py`;
`backend/baseline/state_capture.py:117-127`.

---

## Kontext

**1. Die Anforderung.** Issue #50, Kommentar 2, verlangt einen Rollback, der **additiv** wirkt:
Die Wiederherstellung eines früheren Baseline-Stands darf die Immutability-Zusage der
Baseline-Tabellen nicht brechen, sondern muss selbst als **neue Version** erscheinen.

**2. Die technische Lage lässt nur den additiven Weg zu.** Der Trigger `bl_raise_immutable`
(`backend/baseline/migrations/0001_initial.py:159-193`) liegt als
`BEFORE UPDATE OR DELETE` auf `bl_baseline_snapshot` und `bl_delta_index_entry`;
`INSERT` ist frei. `UPDATE` wirft immer. `DELETE` wirft, sofern nicht der transaktionslokale
GUC `app.baseline_admin_delete` gesetzt ist — eine Ausnahme, die ausschließlich
`BaselineFacade.purge_baseline` (Admin-Rolle, auditiert) setzt
(`0011_baseline_admin_delete_trigger.py:18-33`). Ein Rollback über diese Tabellen ist damit
strukturell nicht möglich, ohne die Zusage selbst aufzugeben.

**3. Voraussetzung ist ein lückenloser Snapshot.** `state_capture.py:117-127` hält die
Bedingung selbst fest: „A field that is not captured here is a field whose drift is
structurally invisible". Fehlt ein Feld im Snapshot, kann ein Rollback es nicht
wiederherstellen — er würde raten. Bekannte Lücken bei `rationale`, `source`,
`acceptance_criteria_items`, `level_source` sowie den Artifact-Hüllenfeldern `owner`,
`reporter`, `priority`, `stakeholder` (Befund R-F4-1, Plan F §F4.1).

**4. Planbasis.** Der Rollback ist nur „mit CR-Freigabe" vorgesehen (Plan F §F4.4, R2). Der
Kommentar aus #50 empfiehlt „additiv jetzt, CCB optional"; die Planbasis entschied
„mit CR-Freigabe" (Befund R-F4-5, `:815`). Diese ADR folgt der Planbasis.

**5. Abgrenzung.** Dieses ADR regelt den **Wiederherstellungspfad** für Baseline-Inhalte. Es
regelt nicht den Baseline-Scope, nicht die Snapshot-Erzeugung (F4.1) und nicht die
Baseline-Tags (F4.2, eigene Tabelle `bl_baseline_tag`).

---

## Alternativen

### (a) Trigger-Bypass per GUC (analog Admin-Purge) — VERWORFEN

**Beschreibung:** Der Rollback setzt `app.baseline_admin_delete` (oder ein analoges GUC) und
schreibt den alten Stand per `UPDATE` in die Baseline-Tabellen zurück.

**Abwägung:** Verworfen. Der GUC existiert heute ausschließlich für den **Lösch**-Fall
(`0011_baseline_admin_delete_trigger.py:23`: „UPDATE keeps raising unconditionally — content
immutability is untouched"). Ein Bypass für Inhalts-Rollback macht die Immutability-Zusage der
Baseline-Tabellen unbeweisbar: Nach dem ersten Rollback wäre nicht mehr feststellbar, ob ein
Snapshot dem Stand zum Erzeugungszeitpunkt entspricht oder später umgeschrieben wurde. Genau
diese Zusage ist der Zweck der Trigger (REQ-L2-BL-002).

**Risiko:** HOCH — die Zusage, die das ADR schützen soll, wird zu ihrer Umsetzung aufgegeben.

### (b) Additiver Rollback ohne Freigabe — VERWORFEN

**Beschreibung:** Die Wiederherstellung läuft additiv (neue Versionen), aber ohne
ChangeRequest; jeder mit Schreibrecht darf sie auslösen.

**Abwägung:** Verworfen. Die Planbasis verlangt die CR-Freigabe ausdrücklich (§F4.4 R2), und
ein Massen-Rollback über bis zu 2000 Items ist eine Governance-Handlung, keine
Einzelkorrektur. Ohne CR fehlt zudem der Träger für Plan-Bindung (R3), Doppelausführungs-Sperre
(R5) und den Audit-Eintrag mit Begründung (R6) — der Rollback wäre nicht mehr nachvollziehbar
als jeder andere Massenschreibvorgang.

**Risiko:** HOCH — Governance-Umgehung; die Änderung wäre nicht mehr auf eine Entscheidung
zurückführbar.

### (c) Additiv + CR-Pflicht (ChangeRequest/CCB) — GEWÄHLT

**Beschreibung:** Baseline-Tabellen werden nur gelesen; die Wiederherstellung erzeugt neue
Versionen über die Domain-Services der jeweiligen Typen, ausgelöst durch einen im CCB
freigegebenen `ChangeRequest`.

**Abwägung:** Erfüllt beide Vorgaben gleichzeitig: Die Immutability der Baseline bleibt
beweisbar (kein `UPDATE`, kein `DELETE`), und die Freigabe bleibt der einzige Weg. Der
ChangeRequest-Mechanismus existiert bereits mit Rollen, SoD und `change_reason`; die
Plan-Bindung (`version_before`) und der Abschlusszustand `implemented` sind vorhandene
Mechanismen, keine Neuschöpfung. Preis: Der Rollback erbt die Grenzen des CR-Workflows —
insbesondere die rigor-abhängige SoD (siehe Konsequenzen).

**Risiko:** NIEDRIG–MITTEL — die SoD-Lücke in Standard ist benannt, nicht verdeckt.

---

## Entscheidung

**Entschieden: Additiver Rollback über die Domain-Services, ausgelöst ausschließlich durch
einen freigegebenen ChangeRequest.**

**R1 — Additiv.** Die Baseline-Tabellen werden ausschließlich per `SELECT` gelesen. Jede
Wiederherstellung ist eine **neue Version** über den Domain-Service des jeweiligen Typs
(inklusive `ArtifactVersion` und Audit). Der Trigger `bl_raise_immutable`
(`0001_initial.py:159-193`) bleibt unverändert; es gibt keinen neuen GUC und keinen
DDL-Bypass.

**R2 — CR-Pflicht.** Eine Ausführung ist nur mit einem `ChangeRequest` im Zustand `approved`
zulässig, dessen `baseline_id` die Ziel-Baseline ist, der im selben Workspace liegt und dessen
`affected_items` nicht leer sind. Ergibt diese Menge nach R4 nichts Wiederherstellbares,
endet `request` mit `400 ROLLBACK_EMPTY`. Die bestehenden CCB-Gates (Rollen, SoD,
`change_reason`) gelten unverändert — dieses ADR lockert sie nicht und ergänzt sie nicht.

**R3 — Plan-Bindung.** Beim Antrag wird je betroffenem Item `version_before` erfasst. Bei der
Ausführung muss die aktuelle Version des Items `version_before` entsprechen; andernfalls
`409 ROLLBACK_PLAN_STALE` mit der Liste der abweichenden Items. Damit kann ein freigegebener
Plan keine zwischenzeitlichen Änderungen überschreiben.

**R4 — Umfang.** Wiederhergestellt werden ausschließlich die in `RESTORABLE_FIELDS`
deklarierten Felder (F4.1). Soft-gelöschte Items werden per `reactivate` reaktiviert. Fehlende
Trace-Links der Baseline werden neu angelegt; system-owned Typen wie `diagram-ref` werden
übersprungen und gemeldet.
**Nicht** wiederhergestellt werden: der Workflow-Zustand, `level`, `uid`, Felder, die der
(ältere) Snapshot nicht erfasst (`unrestorable_fields`), und Artefakte, die nach der Baseline
neu angelegt wurden — letztere werden nur gemeldet (ENT-F6 = a, `:795`). Stellt die
Affected-Item-Menge des CR nach diesen Regeln **nichts** wieder her — kein restorable Item,
keine Reaktivierung, kein nachzuziehender Link —, ist der Plan leer: `request` antwortet
`400 ROLLBACK_EMPTY`, ein wirkungsloser CR entsteht nicht.

**R5 — Atomar und gegen Doppelausführung gesperrt.** `apply` läuft in **einer** Transaktion:
(1) `select_for_update()` auf die **ChangeRequest-Zeile** — die Sperre deckt ausschließlich
diese Zeile ab; (2) **danach** Status und Version lesen. Beides steht nicht auf der CR-Zeile,
sondern im `WorkflowItemState` (`we_item_state`), das von der CR-Zeilensperre **nicht** erfasst
wird: `implemented` → `409 ROLLBACK_ALREADY_APPLIED`, jeder andere Status ≠ `approved` →
`409 ROLLBACK_NOT_APPROVED`; (3) Schreibvorgänge in fester Reihenfolge nach `item_id`
(keine Deadlocks zwischen Items); (4) `transition_status(..., expected_version=<unter Sperre
gelesene Version>)` in derselben Transaktion. `expected_version` ist die **zweite
Verteidigungslinie** gegen einen konkurrierenden CCB-Übergang (z. B. Reject), der die
CR-Zeilensperre nicht teilt: Der `WorkflowItemState.version`-Vergleich schlägt dann fehl und
der Aufruf endet mit `409` „Version conflict“ — dem Optimistic-Lock-Konflikt der
Workflow-Engine, für den dieses ADR keinen eigenen Rollback-Code einführt —, statt den
Gewinner zu überschreiben. Ein Fehler in einem Schritt rollt die Transaktion zurück: nichts
geschrieben, der CR bleibt `approved`.

**R6 — Abschluss und Audit.** Nach Erfolg steht der CR auf `implemented` (mit gefülltem
`state_after`). Auf **Rollback-Ebene** entsteht genau **ein** Audit-Eintrag:
`entity_type="Baseline"`, `operation="update"`,
`details={"rollback_change_request", "restored", "reactivated", "links_recreated",
"actor_type": "user"}`, in derselben Transaktion. Davon unabhängig schreibt jeder
Domain-Service je wiederhergestelltem Item seinen normalen Audit-Eintrag (R1); „genau ein
Eintrag“ gilt also für die Rollback-Ebene, **nicht** für die Summe aller Einträge. Abgelehnte
Versuche (403/409/400) schreiben nichts und loggen WARNING mit CR-ID, User und Fehlercode. Es
wird **keine neue EventType** eingeführt — Domain-Events laufen über die bestehenden
`*_UPDATED`-Outbox-Pfade.

**R7 — Item-Rechte.** `preview` und `request` enthalten nur Items, auf die der Aufrufer READ
hat; gesperrte Items erscheinen weder in der Item-Liste noch in den Zählungen noch in den
wiederherzustellenden Links. `apply` prüft vor dem ersten Schreibvorgang WRITE je
betroffenem Item; fehlt es bei mindestens einem, endet der Aufruf mit
`403 PERMISSION_DENIED` ohne jeden Schreibvorgang.

**R8 — Nur Menschen führen aus.** `apply` (REST und MCP) ist ausschließlich für
`ctx.actor_type == "user"` zulässig. Agent-Prinzipale erhalten `403 PERMISSION_DENIED`
beziehungsweise MCP `-32001`. `preview` und `request` sind für Agenten erlaubt: `preview` ist
lesend, `request` erzeugt nur einen CR im Zustand `draft` — die Freigabe bleibt im CCB.

**R9 — Massen-Grenze.** `MAX_ROLLBACK_ITEMS = 2000`; `request` und `apply` prüfen die Anzahl
der Affected-Items und antworten darüber mit `400 ROLLBACK_TOO_LARGE`. Die Ausführung ist
bewusst **synchron**; es gibt keinen Hintergrund-Job.

**Fehlercodes:** `ROLLBACK_NOT_APPROVED`, `ROLLBACK_ALREADY_APPLIED`, `ROLLBACK_PLAN_STALE`,
`ROLLBACK_EMPTY`, `ROLLBACK_TOO_LARGE`.

---

## Konsequenzen

**Positiv:**

- Die Immutability der Baseline-Tabellen bleibt **beweisbar**: kein `UPDATE`, kein `DELETE`,
  kein neuer GUC. Ein Rollback hinterlässt keine Spur in den Baseline-Tabellen, die ihre
  Aussage verändern könnte.
- Jede Wiederherstellung ist historisiert und auditierbar — sie ist eine neue Version mit
  `ArtifactVersion` und genau einem Baseline-Audit-Eintrag mit CR-Bezug.
- Der ChangeRequest/CCB bleibt der einzige Weg; es entsteht kein zweiter Freigabemechanismus
  neben dem bestehenden.
- Die Plan-Bindung (R3) verhindert, dass ein freigegebener Plan zwischenzeitliche Änderungen
  still überschreibt.
- Wiederholte Ausführung ist ausgeschlossen (R5) und explizit als
  `ROLLBACK_ALREADY_APPLIED` benannt, statt als Datenfehler aufzufallen.

**Positiv (Abgrenzung):**

- Workflow-Zustände werden **nicht** zurückgesetzt. Ein Rollback stellt Inhalte wieder her,
  nicht Governance-Zustände — ein freigegebenes Artefakt bleibt freigegeben, auch wenn die
  Baseline es im Entwurf sah. Das ist die einzige Lesart, die mit der CR-Freigabe vereinbar
  ist.

**Negativ:**

- **SoD ist heute rigor-gated** (`approval_workflows`, nur im Extended-Preset). In Standard
  kann der Requestor zugleich der Approver sein; der Rollback erbt damit eine Freigabe, die
  keine echte Vier-Augen-Kontrolle ist. Dieses Restrisiko wird hier **ausdrücklich
  dokumentiert**, nicht stillschweigend hingenommen (Plan F §(vii), `:746`). Eine
  tier-unabhängige SoD für Rollbacks wäre eine eigene Folgeentscheidung.
- Der Rollback ist synchron und durch `MAX_ROLLBACK_ITEMS = 2000` begrenzt. Sehr große
  Projekt-Baselines benötigen mehrere Anträge; ein einzelner Antrag kann sie nicht abdecken.
- Felder, die ein älterer Snapshot nicht erfasst, werden als `unrestorable_fields` **gemeldet
  statt geraten**. Ein Rollback auf einen Snapshot aus der Zeit vor F4.1 stellt damit
  weniger wieder her, als der Nutzer erwartet — sichtbar, aber unvollständig.
- Der Rollback ist auf acht Artefakt-Typen und deren `RESTORABLE_FIELDS` begrenzt; fehlt einem
  Domain-Service ein Parameter für ein Feld, wandert dieses Feld nach `NON_RESTORABLE` statt
  per Roh-`UPDATE` geschrieben zu werden. Die Abdeckung wächst nur mit den Services.
- Nach der Baseline neu angelegte Artefakte bleiben unberührt (ENT-F6 = a). Ein Rollback
  erzeugt damit bewusst **keinen** exakten historischen Stand, sondern einen additiv
  bereinigten.

---

*Erstellt durch `documenter` am 2026-10-31 auf Branch
`docs/adr-025-additive-baseline-rollback` (Basis HEAD `338f6a42`). Enthält keinen
Produktcode, keine Migration, keine Config-Änderung und keine REQ-Datei-Änderung. Der Status
bleibt `proposed`; Review und Statuswechsel liegen nicht bei diesem Dokument.*
