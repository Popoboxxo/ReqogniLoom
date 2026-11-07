# Ordnung und Allokation

Kurzreferenz für Betreiber und Integratoren (P1–P6, Issue #1670).

## Reihenfolge

- Jedes Requirement und Architekturelement trägt `sort_key` (Fractional Index,
  Collation `C`) am `Artifact`. Geschwister werden danach sortiert, dann nach
  `created_at, id`.
- `POST /api/v1/artifacts/{id}/move/` mit `{parent_id, after_id}`:
  `after_id` fehlt = ans Ende, `null` = an den Anfang, sonst direkt hinter das
  genannte Geschwister. Zusätzlich als MCP `artifact.move`.
- `GET /api/v1/workspaces/{id}/tree/?type=requirement|architecture` liefert den
  sortierten Wald.

## Allokation (N:1)

- Ein Requirement hat höchstens ein Architekturelement (partieller Unique-Index
  auf `allocated-to.source`).
- Schreiben nur über `TraceLinkService.allocate` (`deallocate` zum Lösen).
  Der generische TraceLink-Pfad antwortet bei einer zweiten Allokation mit 409.
- `Requirement.allocation_intent`: `allocated`, `not_allocatable` (bewusst
  ausgenommen, zählt nicht als Lücke) oder `unassigned`.
- `POST /api/v1/trace-links/bulk/` allokiert mehrere Requirements atomar
  (ein Fehler rollt die ganze Charge zurück).

## Stufen-Leiter

- Jeder Workspace hat eine geordnete Leiter (`GET/PUT
  /api/v1/workspaces/{id}/tiers/`): genau eine `first`-Stufe, höchstens eine
  `middle`, genau eine `from_end=0` (Blatt).
- Die Stufe eines Elements wird vom Blatt her bestimmt (längster Weg nach
  unten). Ein Requirement erbt: Allokation > Eltern-Stufe + 1 > Typ-Default
  (erste Stufe) > `unresolved`. `level` bleibt der Integer-Alias (Position + 1).
- Das Requirement-Payload liefert `tier_key` (stabiler Leiter-Schlüssel) und
  `tier_name` (lesbarer Name, schreibgeschützt, pro Request gebatcht).
  `level` bleibt daneben der dauerhafte Integer-Alias.
- Generischer Export, Requirement-Bundle und ReqIF-Export geben `tier_key` und
  `tier_name` zusätzlich aus; `level` bleibt unverändert.
- Die Audit-Regeln kennen keine feste Skala 1..4 mehr: ARCH-003 und VERIF-P8
  überspringen die letzte Stufe nicht, TRACE-P1/P1b/P2/P3 schließen sie nicht
  aus. CONS-P13 verlangt, dass jedes aktive Requirement einen `level_source`
  trägt; CONS-P12 meldet unaufgelöste Stufen.
- `python manage.py report_requirement_levels` ist ein Dry-Run; `--apply`
  schreibt. Manuelle Overrides bleiben unangetastet.

## Workflow-Sperre

- Ein Workflow-Zustand mit `state_meta.freeze_on_enter` sperrt Position,
  Elternknoten und Allokation des Artefakts (409 `WORKFLOW_FROZEN`).
- Ein gesperrtes Architekturelement darf weiterhin Ziel neuer Allokationen sein;
  maßgeblich ist immer der Zustand des Requirements.
- Beide klassischen Bäume (`RequirementList`, `ArchitectureEditors`) holen die
  Sperren einmal pro Mount über
  `GET /api/v1/workspaces/{id}/locks/?type=requirement|architecture`. Die Antwort
  ist `{locks: {<id>: <Zustandsname>}}` und enthält nur gesperrte Artefakte.
- Gesperrte Zeilen tragen ein Sperr-Symbol mit Tooltip (Zustandsname); Drag,
  Alt+↑/↓ und der „Verschieben…“-Dialog sind für sie deaktiviert.
- Ein 409 nennt den Zustandsnamen des Backends im Klartext.

## Gruppen

- Eine Gruppe ist ein `Artifact` vom Typ `Group`; Mitgliedschaft ist ein
  `grouped-in`-Link (Requirement → Group, mehrere Gruppen pro Requirement).
- Die Reihenfolge innerhalb einer Gruppe liegt in `TraceLink.sort_key`.
- Gruppen sind rein visuell: sie ändern weder Stufe noch Allokation.
- REST: `GET/POST /api/v1/groups/`, `GET/POST /api/v1/groups/{id}/members/`,
  `POST /api/v1/groups/{id}/members/{remove,move}/`.

## Gespeicherte Sichten und Kartenfelder

Beides sind registrierte Präferenzen auf den drei Ebenen, kein
Browser-Speicher:

| Schlüssel | Typ | Ebenen | Rang |
|---|---|---|---|
| `ui.connection_view.saved_views` | `str_list` | USER | — |
| `ui.allocation_graph.card_fields` | `str_list` | GLOBAL, WORKSPACE, USER | user > workspace > global |

- Die gespeicherten Sichten der Verbindungssicht liegen als JSON-kodierte
  Dokumente in `ui.connection_view.saved_views` (nur Benutzerebene).
- Die Kartenfelder des Allokationsgraphen liegen in
  `ui.allocation_graph.card_fields`: Die Workspace-Ebene ist der Standard für
  alle Mitglieder, die Benutzerebene überschreibt ihn, die globale Ebene liefert
  den Mandanten-Default.
- Einen localStorage-Fallback gibt es nicht mehr. Ein fehlgeschlagenes Speichern
  wird angezeigt (Toast bzw. Fehlerzustand), statt still zu verschwinden.
