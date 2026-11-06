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
- `python manage.py report_requirement_levels` ist ein Dry-Run; `--apply`
  schreibt. Manuelle Overrides bleiben unangetastet.

## Workflow-Sperre

- Ein Workflow-Zustand mit `state_meta.freeze_on_enter` sperrt Position,
  Elternknoten und Allokation des Artefakts (409 `WORKFLOW_FROZEN`).
- Ein gesperrtes Architekturelement darf weiterhin Ziel neuer Allokationen sein;
  maßgeblich ist immer der Zustand des Requirements.

## Gruppen

- Eine Gruppe ist ein `Artifact` vom Typ `Group`; Mitgliedschaft ist ein
  `grouped-in`-Link (Requirement → Group, mehrere Gruppen pro Requirement).
- Die Reihenfolge innerhalb einer Gruppe liegt in `TraceLink.sort_key`.
- Gruppen sind rein visuell: sie ändern weder Stufe noch Allokation.
- REST: `GET/POST /api/v1/groups/`, `GET/POST /api/v1/groups/{id}/members/`,
  `POST /api/v1/groups/{id}/members/{remove,move}/`.
