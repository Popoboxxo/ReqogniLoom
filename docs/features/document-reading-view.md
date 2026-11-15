# Bearbeitbare Dokumentansicht

Kurzreferenz für Anwender und Integratoren. Sie beschreibt, was die Dokumentansicht
unter `/documents/:id` zeigt, wer worauf schreiben darf und wie gespeichert und
exportiert wird. Grundlage ist der Code dieses Repository-Stands (Stand
2026-11-15), nicht der Wunschzustand; Bauplan und Schnitte:
`docs/superpowers/plans/2026-11-15-document-view-on-document.md` (R1–R7),
Entscheidungshintergrund: `docs/se/ADR/ADR-026_document_artefakt.md` (Nachtrag
2026-11-15) und `docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md`.

## Was die Sicht zeigt

- **Datenquelle** ist `GET /api/v1/documents/{id}/view/` — ein Leseobjekt aus
  `backend/application/document_reading_service.py`. Die Oberfläche rendert nur
  dieses Objekt (`frontend/src/components/Documents/DocumentReadingView.tsx`).
- **Kopf:** Titel, `uid` (oder die ersten acht Zeichen der id), `kind`,
  Workflow-Status, `version` und `doc_date`.
- **Inhaltsverzeichnis und Kapitel:** links ein `<nav>` mit allen Kapiteln, rechts
  je Kapitel eine `<section>` mit eigener Überschrift. Die Anker kommen aus dem
  Backend, ein Deep-Link übersteht also einen Reload.
- **Kapitel sind die Markdown-Überschriften des `body`**
  (`backend/application/markdown_chapters.py`): ATX (`## Titel`) und Setext,
  bis Ebene `###`. `####` und tiefer bleiben Fließtext, Überschriften in fenced
  Code-Blöcken zählen nicht. Text vor der ersten Überschrift erscheint als
  unbenannte Präambel. Nummeriert wird hierarchisch (`1`, `1.1`, `1.1.1`); bei
  übersprungenen Ebenen bleibt die Nummer kurz, dann kann sie doppelt vorkommen —
  die Identität ist der Anker, nicht die Nummer.
- **Felder:** `title`, `description`, `body`, `doc_date`, `custom_fields` als
  Liste aus Name, Wert und gegebenenfalls Sperrgrund. `body` wird als Feld nur
  angekündigt („wird als Kapiteltext dargestellt"), der Inhalt steht in den
  Kapiteln.
- **Hinweis am Kopf:** ein freigegebenes Dokument zeigt `frozen_at`/`frozen_fields`,
  ein nicht beschreibbares den Grund aus `capabilities.read_only_reason`.

## Wer schreiben darf

Das Backend entscheidet, die Oberfläche zeigt nur das Ergebnis. Je Feld liefert das
Leseobjekt `fields[].editable` und `fields[].locked {code, detail}`; zusätzlich
gibt es `capabilities.can_write` und `capabilities.read_only_reason`. Die Regel
steht in `backend/application/document_edit_policy.py` und greift in dieser
Reihenfolge (erster Treffer gewinnt):

| Code | Bedeutung |
|---|---|
| `PERMISSION` | Die RBAC-Matrix oder eine Item-Regel verweigert das Schreiben. Rechte sind einschränkend, nie erweiternd. |
| `REPO_EXTERNAL` | Der Inhalt gehört einem externen Repository (`owner_mode = repo_external`); hier wird nie geschrieben — erst nach `adopt`. |
| `FIELD_FROZEN` | Die Freigabe hat das Feld eingefroren (`FROZEN_FIELDS = title, description, body, kind`). `doc_date` und `custom_fields` bleiben schreibbar. |

`kind` ist bewusst **nicht** Teil von `EDITABLE_FIELDS_V1`: es ist Klassifikation,
kein Inhalt, und wird in der Sicht nie inline geändert. `custom_fields` ist Teil
der Policy und meldet `editable: true`, solange kein leerer Attributkatalog
gemeldet wird (der Lesedienst übergibt `allowed_custom_fields = None`).

## Speichern: sofort oder sammeln

Beide Wege benutzen die vorhandenen Dienste — es gibt keinen zweiten Schreibpfad
und keine eigene Prüfung in der Oberfläche.

- **Sofort (ein Feld):** `PATCH /api/v1/documents/{id}/` mit genau einem Feld und
  `If-Match: "<version>"`. Der Dienst prüft Syntax → Freeze → Optimistic Lock.
- **Sammeln (ein Stapel):** `PATCH /api/v1/artifacts/bulk-update/` mit
  `entries: [{artifact_id, expected_version, fields}]` — höchstens 100 Einträge,
  **eine** Transaktion, alles oder nichts. Jeder Eintrag läuft durch den Dienst
  seines Typs (`Document` → `DocumentService.update_document`, `Requirement` →
  `RequirementService.update_requirement`, Tabelle `UPDATE_DISPATCH` in
  `backend/application/bulk_update_service.py`). Derselbe Stapel ist als MCP
  `artifact.bulk_update` verfügbar.

## Konflikte

| Antwort | Wann | Was der Client daraus macht |
|---|---|---|
| `412` | `If-Match` passt nicht mehr (Sofortmodus): die `version` ist veraltet. | Das betroffene Feld markieren, neu laden anbieten. |
| `409 FIELD_FROZEN` | Das Feld wurde zwischen Laden und Speichern freigegeben. | Sperrgrund am Feld anzeigen. |
| `409` (Stapel) | Mindestens ein Eintrag wurde abgelehnt — stale `expected_version`, Freeze, unbekanntes Feld, fremder Workspace, fehlende Berechtigung. | **Nichts** wurde geschrieben; `errors[]` nennt `index`, `artifact_id`, `code`, `message` und optional `field`. Die Entwürfe bleiben beim Nutzer. |
| `400` | Der Stapel selbst ist fehlerhaft (leere `entries`, mehr als 100, kaputtes Schema). | Anfrage korrigieren. |
| `403` | Keine Schreibrolle im Workspace. | Kein Schreibangebot. |

## Markdown-Export

`GET /api/v1/documents/{id}/view/?format=markdown` liefert `text/markdown` — genau
den Lesestand der Oberfläche: dieselben Kapitel in derselben Reihenfolge mit
Nummern. Der Export setzt keine Bearbeitungsmarken — weder `editable`/`locked`-
Angaben noch Capability-Flags noch eigene HTML-Kommentare. Ein leerer `body`
ergibt ein leeres Dokument, nie
eine einsame Überschrift. Dieselbe Antwort trägt `ETag: "<version>"` und dieselben
`403`/`404` wie das JSON-Leseobjekt. Einen zusätzlichen MCP-Endpunkt gibt es
bewusst nicht: `document.projection` liefert bereits Markdown.

## Grenzen

- **Kein Kapitel-Modell und keine Kapitel-Konfiguration.** Kapitel sind reine
  Textverarbeitung des `body`; es gibt keine artefakt-übergreifenden Kapitel,
  keine Filter-Sprache und keine Attribute je Kapitel.
- **`custom_fields`** wird als Wert angezeigt; eine Inline-Bearbeitung der Map
  gibt es in v1 nicht.
- **`repo_external`** ist bis zum `adopt` schreibgeschützt — ein Schreibzugriff
  würde den `source_sha256`-Vertrag fälschen.
- **Die Sicht ändert nie die Struktur** (Verschieben, Allokieren); das läuft über
  Bäume und Verbindungsansicht.
- **Noch nicht in diesem Stand:** Inline- und Sammel-Speichern in der Oberfläche
  (R5/R6 — „Bearbeiten" öffnet weiterhin das Formular), Druck-Stylesheet und der
  E2E-Test (R7.2). Kein DOCX-Export, kein Teilen von Sichten.
