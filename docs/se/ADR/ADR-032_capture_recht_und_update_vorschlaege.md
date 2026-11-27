---
adr_id: ADR-032
title: "Capture-Recht am API-Key und Update-Vorschläge — Ergänzung zu ADR-019"
status: proposed
date: "2026-11-27"
deciders: [orchestrator, user]
affected_reqs: [REQ-L1-009, REQ-L2-RV-001, REQ-L2-AI-007, REQ-L2-AI-008]
superseded_by: null
---

# ADR-032: Capture-Recht am API-Key und Update-Vorschläge — Ergänzung zu ADR-019

## Kontext

ADR-019 legt den generischen Vorschlags-Lebenszyklus fest und begrenzt die
**Produktion** bewusst auf Agent-/API-Key-Kontexte (Zusage 7(f)), während die
**Entscheidung** menschlich bleibt (Zusage 7(c)). Diese Trennung ist für
`traceability.suggest_links` richtig: dort produziert ein Agent, ein Mensch
bestätigt.

Der Listen-Modus (Spec `2026-11-21-listen-modus-alle-clients-design.md`,
Entscheidungen D1/D2/D12) stellt zwei zusätzliche Anforderungen, die ADR-019
nicht abdeckt:

1. **Ein Credential pro Client-Relay.** Ein Client-Hook soll die Nutzernachricht
   erfassen und als Vorschlag abgeben. Hält er dafür einen Agent-Key und für die
   Annahme einen Nutzer-Key, muss jede der sieben Client-Integrationen zwei
   Schlüssel einrichten und synchron halten — ein Einrichtungsfehler, der still
   zu „keine Vorschläge" führt (Hermes-Befund H2).
2. **„Anpassen, erweitern, korrigieren".** ADR-019 kennt nur erzeugende
   Vorschläge (`artifact_create`) und Link-/Feld-Vorschläge. Eine
   Nutzernachricht, die ein **bestehendes** Artefakt erweitert, hat keinen
   Vorschlagstyp — sie würde entweder ein Duplikat anlegen oder gar nicht
   erfasst.

Zusätzlich verlangt die Spec eine serverseitige Verarbeitungskette (Schalter,
Schwärzung, Regel-Filter, Duplikatsschutz, genau ein zustandsloser
Modellaufruf), weil Gleichheit zwischen Clients nur durch Zentralisierung
haltbar ist (Spec G3/G4).

**Threat-Model (4 Fragen, Datenfluss Nutzernachricht → Vorschlag):**

1. *Was gebaut?* Ein Aufruf `suggestion.capture` (REST + MCP, gleiches
   Verhalten), der Nutzernachrichten als Vorschläge persistiert; ein neues
   Key-Recht `capture`; zwei Vorschlags-Operationen (`create`/`update`) im
   bestehenden Posteingang; Text verlässt den Rechner zum konfigurierten
   Modellanbieter.
2. *Was schiefgeht?* (a) Ein Erfassungs-Key erlangt Entscheidungsrechte und ein
   Agent bestätigt sich selbst. (b) Klartext-Geheimnisse landen in der
   Vorschlagszeile oder im Prompt. (c) Prompt-Injection im Nachrichtentext löst
   Schreibvorgänge aus. (d) Ein Update-Vorschlag überschreibt einen neueren
   Stand. (e) Ein kompromittierter Relay-Key erzeugt unbegrenzt Vorschläge und
   Kosten. (f) Ein Client sendet in einen fremden Workspace.
3. *Gegenmaßnahme?* (a) `capture` ist ein eigenes, additives Recht; die
   Annahme bleibt human-only und wird je Adapter geprüft. (b) Schwärzung vor
   Speicherung **und** vor dem Modellaufruf; überwiegend geschwärzte Nachrichten
   werden verworfen; Rohtext wird nie persistiert. (c) Das Modell liefert nur
   Vorschläge, die durch dieselbe Proposal-Prüfung wie `interview.formalize`
   gehen; Capture ruft **keinen** Domänen-Schreibpfad auf. (d) Update-Vorschläge
   tragen die serverseitig gelesene `base_version`; die Annahme geht durch die
   normale Update-Fassade mit `expected_version`. (e) Obergrenzen für Textlänge,
   offene Vorschläge, Aufrufe je Stunde und ein **fail-closed** Tagesbudget.
   (f) `workspace_id` ist Pflicht, der Workspace-Zugriff wird gegen Tenant,
   Rolle und Key-Fence geprüft (`WORKSPACE_FORBIDDEN`).
4. *Konsequenz?* Ohne diese Ergänzung wäre der Listen-Modus entweder nicht
   einrichtbar (zwei Keys) oder nicht sicher (Erfassungsrecht implizit im
   Agent-Key). Mit ihr entsteht ein zusätzliches Recht, ein zusätzlicher
   Vorschlagstyp und eine zweite Schreibsemantik im Posteingang — beides
   auditierbar und ohne Änderung an M1–M4.

## Alternativen

- **a) Zwei Keys pro Client (Agent-Key für Capture, Nutzer-Key für Annahme).**
  Ändert ADR-019 nicht, verdoppelt aber die Einrichtung in jedem der sieben
  Clients und macht den Fehlerfall „falscher Key" unsichtbar. **Verworfen.**
- **b) Capture-Recht für Nutzer-Keys (interner Agent-Kontext).** Ein Key, aber
  es ändert die Sicherheitsaussage von ADR-019 Zusage 7(f), weil der Server
  einen Agent-Kontext synthetisiert, den der Aufrufer nicht besitzt.
  **Verworfen.**
- **c) Neues Recht `capture` am Key.** Kleinste Ausweitung: genau ein Aufruf
  konsultiert es, unabhängig von Rolle und `scope`-Stufe. **Gewählt.**
- **d) Update-Vorschläge als neues Artefakt plus Trace-Link.** Erzeugt
  Duplikate und verlagert die Entscheidung „anpassen oder neu" in den Menschen.
  **Verworfen.**
- **e) Update-Vorschläge über den Workflow-Zustand `proposed` (M1).** TraceLinks
  und Felder haben strukturell keine State-Machine (ADR-019 Kontext 4); ein
  Update ist kein Zustandsübergang. **Verworfen.**

## Entscheidung

1. **Neues Key-Recht `capture`** (`ApiKey.capture_enabled`, Default `false`).
   `suggestion.capture` verlangt zusätzlich zu einem API-Key mit
   schreibfähigem `scope`. Das Recht autorisiert **ausschließlich** die
   Produktion von Vorschlägen; es autorisiert **keine** Annahme. Ein Agent-Key
   darf weiterhin nie annehmen — die Prüfung liegt zusätzlich in jedem
   Capture-Adapter, nicht nur im Transport.
2. **`artifact_create` wird aktiviert.** Produzieren persistiert nur die
   Quittung; Annehmen ruft denselben Produktions-`create_X()`-Pfad wie
   `interview.formalize` (Workflow-Initialisierung, `uid`, Audit inklusive) und
   trägt das erzeugte Artefakt als Ziel der Quittung ein — damit ist die
   Herkunft (Client, Sitzung, Hash → Vorschlag → Artefakt) begehbar.
3. **Neue Vorschlagsart `artifact_update`** mit `operation`, `target_artifact_id`
   und `base_version`. Annehmen ruft die normale Update-Fassade des Zieltyps;
   eine veraltete `base_version` wird als Konflikt (409 `CONFLICT`) beantwortet
   und überschreibt nichts. Konkret delegiert der Adapter an
   `application.artifact_fields_update.update_artifact_fields` — dieselbe
   Fassade, die Bulk- und Inline-Bearbeitung nutzen, inklusive
   Content-Allowlist, Gateway-Feldern (`owner`/`priority`/`custom_fields`),
   Workflow-/Freeze-Gate, Item-Recht, Optimistic Lock und Audit.
   **Grenze in v1:** unterstützt werden die Typen, die diese Fassade kennt
   (Requirement, StakeholderNeed, ArchitectureElement, TestCase, Adr, Risk,
   Issue, GlossaryTerm). **Goal fehlt bewusst**: Goals sind unveränderliche
   Zeilen je Version, die gemeinsame Fassade hat keinen Goal-Adapter, und ein
   paralleler Schreibpfad hier würde genau die Prüfungen umgehen, die dieses ADR
   wiederverwendet. Goal-Update-Vorschläge sind damit offener Punkt, nicht
   stiller Bestandteil.
4. **Die Verarbeitung liegt vollständig im Server**: Schalter
   `capture.enabled` je Workspace (Default aus), Schwärzung, Regel-Filter,
   Duplikat-Schutz (Idempotenzschlüssel → offene/kürzlich verworfene Vorschläge
   → Bestandsabgleich), genau ein zustandsloser Modellaufruf, Prüfung über die
   vorhandene Proposal-Validierung. Rohtext wird nicht persistiert (nur
   geschwärzter Auszug + SHA-256).
5. **Duplikat-Schutz erkennt Wiederholung als Update.** Wiederholt ein
   Vorschlag den Titel eines bestehenden Artefakts und bringt mindestens ein
   weiteres Feld mit, wird daraus ein Update-Vorschlag auf dieses Artefakt;
   ohne neues Feld ist er ein Duplikat und wird verworfen.
   Der Inhaltsabgleich ist **workspace-weit**, nicht client-weise: dieselbe
   Nachricht aus zwei Clients ergibt *einen* Vorschlag (ein Posteingang, eine
   Entscheidung) — die Herkunft des zuerst eingegangenen wird festgehalten.
   Ein offener Vorschlag unterdrückt dieselbe Nachricht nur bis `expires_at`;
   ein verworfener für sieben Tage.
6. **Grenzen sind fail-closed, wo Geld oder Rechte betroffen sind:** Textlänge,
   offene Vorschläge je Workspace, Aufrufe je Key/Workspace/Stunde und das
   Tagesbudget. Nur der Stundenzähler ist fail-open, wenn der Cache fehlt — das
   Tagesbudget bleibt der harte Riegel.

## Konsequenzen

- Positiv: ein Credential je Relay; „anpassen/erweitern/korrigieren" ist ein
  Vorschlag statt eines Duplikats; Filter, Schwärzung und Prompt existieren
  einmal und gelten für jeden Client; die Annahme bleibt menschlich und
  auditierbar; M1–M4 bleiben unverändert. Die Herkunft ist von der Quittung zum
  Artefakt begehbar (Quittung → `target_item_id` = Entity-Id,
  `payload.accepted_artifact_id` = Artifact-Id); die Gegenrichtung
  (Artefakt → Quittung) ist eine Suche über `target_item_id`, kein
  zurückgeschriebener Zeiger.
- Negativ: ein zusätzliches Recht und ein zusätzlicher Vorschlagstyp im
  Posteingang; `Suggestion` bekommt zehn Spalten und eine partielle
  Unique-Constraint; ein Update-Vorschlag kann zwischen Erfassung und Annahme
  veralten — das ist gewollt (Konflikt statt Overwrite), kostet den Menschen
  aber einen zweiten Blick. Der Bestandsabgleich ist in v1 deterministisch über
  Titelähnlichkeit; der in der Spec genannte Embedding-Abgleich bleibt offen.
- Offen (nicht blockierend): Retention/Löschpfad für abgelaufene Vorschläge
  (ADR-019 O9), Embedding-basierter Duplikat-Schutz, Update-Vorschläge auf Goal
  (die gemeinsame Update-Fassade hat keinen Goal-Adapter), Client-Hooks (P4/P5).

## Statuswechsel

- 2026-11-27 — `proposed`: angelegt als Ergänzung zu ADR-019 (Entscheidungen
  D1/D2/D12 der Listen-Modus-Spec, freigegeben durch `user`). Review durch
  `concept-reviewer` steht aus.
