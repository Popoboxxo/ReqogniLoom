---
type: Spec
title: "Dokumentensicht (DocumentView) — bearbeitbare Dokumentansicht über Artefakte"
status: draft
date: 2026-11-04
author_agent: claude (Sonnet 5.5), gemeinsam mit dem Product Owner erarbeitet
language: de
supersedes: ["docs/superpowers/specs/2026-09-03-dokumentensicht-design.md", "docs/superpowers/plans/2026-09-03-dokumentensicht.md (Plan wird neu geschrieben)"]
amends: ["docs/se/ADR/ADR-026_document_artefakt.md (Entscheidung ENT-F2 = b: Sicht ist nicht mehr schreibgeschützt)"]
depends_on: ["docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md (sort_key P1, Sperre P4)", "docs/superpowers/specs/2026-09-03-tabellenansicht-design.md (Filter-Sprache, bulk-update)"]
evidence: "Stand origin/main 8cda953f; Belege als `pfad:zeile`"
---

# Dokumentensicht (`DocumentView`)

> **Status: Entwurf zur Freigabe.** Im Gespräch vom 2026-11-04 entschieden sind E1–E7. Alles mit **[Vorschlag]** ist meine Festlegung und noch nicht bestätigt.

## 1. Ziel

Der Nutzer legt in einem Workspace eigene **Sichten** an, die wie ein lesbares Dokument aussehen (Kapitel, Nummerierung, Fließtext), aus beliebigen Artefakten und frei gewählten Attributen. Die Sicht ist der aktuelle Stand der Artefakte, **keine Kopie**. Man kann darin **lesen, exportieren, drucken und bearbeiten**. Jede Änderung läuft über dieselben Regeln wie überall (Workflow-Sperre, Rechte, Versionsschutz).

### Nicht-Ziele

- Kein Artefakt mit Lebenszyklus, Freeze oder Freigabe: das bleibt das `Document` aus Plan F (ADR-026).
- Kein Generator, der Markdown-Dateien ins Repository schreibt, keine Quellbindung (Plan F, WP F5, ENT-F5 = a).
- Kein Teilen von Sichten zwischen Nutzern (O1), kein DOCX-Export.
- Keine eigene Filter-Sprache (kommt aus der Tabellenansicht, E6).

### Anti-Ziele

- Ein Bearbeiten, das eine Regel umgeht, die die Einzelbearbeitung kennt (Sperre, Rechte, Versionskonflikt).
- Ein Sammel-Speichern, das einen Teil schreibt und einen Teil nicht.
- Eine Sicht, die Artefakte zeigt, die der Nutzer nicht lesen darf.

## 2. Ist-Stand (origin/main 8cda953f)

| Thema | Befund | Beleg |
|---|---|---|
| `Document` (Artefakt) | gebaut: eigenes Modell, Lebenszyklus, Freeze, Link-Typ `documented-in` | `persistence/models.py:4566`, ADR-026, Spec `2026-11-02-f2-document-design.md` |
| `DocumentView` / `DocumentSection` | **existiert nicht**; Name von ENT-F2 = b reserviert | Suche `git grep DocumentView` ohne Modell |
| Gespeicherte Sichten | gibt es nicht; vorhanden ist `UserWorkspacePreference` (Einstellung je Nutzer und Workspace) | `auth_tenancy/models.py:467`, `rest_api/preference_views.py:41` |
| Sammel-Schreiben | `bulk-update` existiert nicht (nur in der Tabellenansicht-Spec geplant) | `git grep bulk_update` ohne Treffer in `rest_api/views.py` |
| Filter für Listen | `allocated`, `level` fehlen; kombinierbare Filter-Sprache fehlt | Spec `2026-11-04-ordnung-allokation-design.md` §2, Tabellenansicht-Spec |
| Reihenfolge der Geschwister | gibt es nicht (kommt mit `sort_key`, #1670 P1) | dito |
| Baseline-Bindung | `Baseline.scope="document"` nimmt bereits das `Document` samt Kindern | ADR-026 Kontext Punkt 3 |

## 3. Entscheidungen

### 3.1 Vom Product Owner entschieden

| ID | Entscheidung |
|---|---|
| **E1** | Die Sicht sieht aus wie ein lesbares Dokument aus Artefakten und **einstellbaren Attributen**. |
| **E2** | Die Darstellung der Attribute (Zeile unter dem Titel oder kleine Tabelle) ist **pro Kapitel wählbar**, es gibt eine **Grundeinstellung für das ganze Dokument**, ein Kapitel überschreibt sie. |
| **E3** | Die Sicht ist **bearbeitbar**, immer zu 100 % regelkonform (siehe §4.4). |
| **E4** | Zwei Speichermodi, umschaltbar: **sofort** (je Änderung) und **sammeln** (alles oder nichts). |
| **E5** | Nutzer legen **eigene Sichten je Workspace** an (Besitzer = Nutzer). |
| **E6** | Kapitelfilter kommen aus der **Tabellenansicht**; die Dokumentensicht wird danach gebaut. |
| **E7** | Speicherung als **eine Tabelle `DocumentView`** mit Kapiteln als **schemageprüftem JSON**; später in eigene Tabellen auslagerbar. |

### 3.2 Meine Festlegungen **[Vorschlag]**

| ID | Vorschlag |
|---|---|
| **V1** | `DocumentView` ist **kein Artefakt** (kein Lebenszyklus, keine Baseline-Erfassung). Es ist eine Konfiguration wie `UserWorkspacePreference`, aber mit eigener Tabelle, Mandantenschutz (RLS) und Routen. |
| **V2** | Kapitelquelle ist genau eine von: `subtree` (Wurzel-Artefakt, optional Typfilter), `filter` (Filterausdruck der Tabellenansicht), `list` (feste, geordnete Artefakt-IDs). Kapitel dürfen bis Tiefe 4 verschachtelt sein, höchstens 100 Kapitel je Sicht. |
| **V3** | Reihenfolge: `subtree` und `filter` in **Baumreihenfolge** (`sort_key`, #1670), `list` in der gespeicherten Listenreihenfolge. |
| **V4** | Nur **Besitzer** ändern seine Sicht; Workspace-Admins sehen und löschen alle Sichten. Ein Artefakt, das der Nutzer nicht lesen darf, fehlt in der Ausgabe. Maßgeblich sind die Rollenrechte plus die Rechte pro Artefakt (`ItemPermission`, nur einschränkend; `auth_tenancy/services/item_permission.py`, `application/effective_permission_service.py`). Im Kapitel steht **kein** Hinweis auf ausgeblendete Einträge, damit nichts über ihre Existenz verraten wird. |
| **V5** | Bearbeitbar ist ein Attribut nur, wenn der **Einzel-Dienst des Artefakttyps** es ändern darf. Die Oberfläche fragt das über `editable_fields` ab; durchgesetzt wird allein im Backend. |
| **V6** | Zeigt eine Quelle auf ein gelöschtes oder outdated Artefakt, steht im Kapitel ein Hinweis; der Rest der Sicht lädt weiter. |
| **V7** | Der Markdown-Export enthält den **Lesestand** (ohne Bearbeitungsmarken), nach demselben Renderer wie die Oberfläche. MCP liefert denselben Text. |
| **V8** | Neues Attribut-Auswahlmodell je Artefakttyp: erlaubt sind die Felder, die der Typ-Serializer ausgibt und die der Nutzer lesen darf. Neue Typen kommen ohne Codeänderung dazu, solange sie das Attributkatalog-Muster nutzen. |

### 3.3 Festlegungen aus dem Builder-Check **[Vorschlag]**

| ID | Festlegung |
|---|---|
| **B1** | Die Arbeit an dieser Spec baut **weder** `bulk-update` **noch** die Filter-Sprache. Beides liefert die Tabellenansicht (E6); ein Umsetzungsplan entsteht erst, wenn #1670 P1, #1670 P4 und die Tabellenansicht gemerged sind. |
| **B2** | Nummerierung: `subtree`-Kapitel werden **verschachtelt** nummeriert (Kapitel 2, darunter 2.1, 2.1.1 nach Baumtiefe); `filter`- und `list`-Kapitel sind **flach** (2.1, 2.2 …), Vorfahren werden nicht ergänzt. Die Nummern werden serverseitig über das **ganze Kapitel** berechnet; eine Seite ist ein Ausschnitt davon, die Nummern bleiben über Seiten stabil. |
| **B3** | Export, Druck und MCP-`render` lesen **alle** Seiten nacheinander. Eine Sicht darf höchstens **5000** Artefakte ausgeben; darüber antwortet der Export mit 400 und nennt die Grenze. Ein asynchroner Export ist nicht Teil. |
| **B4** | Sammeln und Konflikt: Ist ein Eintrag veraltet (Versionskonflikt), wird der **ganze** Stapel abgelehnt. Die Oberfläche behält **alle** Entwürfe (nur im Browser, ohne Speicherung auf dem Server), markiert das betroffene Artefakt und bietet "dieses Artefakt neu laden" an. |
| **B5** | `editable_fields` kommt aus den schreibbaren Feldern des Typ-Serializers abzüglich der durch Sperre oder Rechte verbotenen, ohne zu schreiben (eine Leseabfrage). In der ersten Version sind **Textfelder** (Titel, Beschreibung, Akzeptanzkriterien, Begründung) und **Auswahlfelder** (Zustand ausgenommen: Zustandswechsel bleiben beim Workflow) bearbeitbar, für Typen mit Update-Dienst. Verknüpfungen bearbeitest du nicht in der Sicht. |
| **B6** | Einstieg in die Oberfläche: Eintrag "Dokumente" im Workspace-Menü, darunter die Liste "Meine Sichten". Der Platz ist Sache des Umsetzers. |

## 4. Zielbild

### 4.1 Datenmodell

`DocumentView(TenantScopedModel)`: `workspace`, `owner_user`, `title` (255), `config` (JSON), `version` (Integer für Versionsschutz), `created_at`, `modified_at`. Eindeutig `(workspace, owner_user, title)`. RLS-Policy wie die übrigen Mandantentabellen.

`config` (`schema_version: 1`):

```json
{"schema_version": 1,
 "defaults": {"attribute_layout": "line|table", "numbering": "decimal|none",
              "visible_attributes": {"Requirement": ["uid","title","state"]}},
 "chapters": [{"id": "uuid", "title": "…",
               "source": {"kind": "subtree|filter|list", "root_artifact_id": "…",
                          "artifact_type": "…", "filter": {}, "artifact_ids": []},
               "overrides": {"attribute_layout": "table", "visible_attributes": {}},
               "children": []}]}
```

Das Schema wird beim Speichern geprüft (unbekannte Schlüssel, falsche Typen, Tiefe, Anzahl → 400). Verweise werden beim Lesen aufgelöst (V6), nicht per Fremdschlüssel gesichert.

### 4.2 Leseobjekt

`GET /api/v1/document-views/{id}/render/` liefert die Kapitel aufgelöst und nummeriert: je Kapitel eine Seite von Artefakten (Standard 200, Maximum 500), je Artefakt `{id, uid, type, number, attributes, editable_fields, locked: {state}|null, version}`. Alle Abfragen mit konstanter Abfragezahl (kein N+1). Dasselbe Objekt speist Lesemodus, Bearbeiten, Export und Druck.

### 4.3 Oberfläche

Vom Product Owner bestätigt (Visual Companion, 2026-11-04):
- **Einrichten:** Liste "Meine Sichten"; links die Grundeinstellung, rechts die Kapitel (Quelle, Darstellung, Überschreibungen, Umsortieren).
- **Lesen/Bearbeiten:** Schalter Lesen ↔ Bearbeiten und Sofort ↔ Sammeln in der Kopfleiste. Blau = geändert, orange = Konflikt oder Regelverstoß mit Grund des Backends, grau mit Schloss = gesperrt. Im Sammelmodus: Leiste "n Änderungen nicht gespeichert" mit "Alle speichern" und "Verwerfen".
- Route `/document-views/<id>`, Druck-Stylesheet, `data-testid` an jedem interaktiven Element, Tastaturbedienung, i18n DE/EN.

### 4.4 Bearbeiten, regelkonform

- **Sofort:** je Änderung der Einzel-Dienst des Typs mit `If-Match` (Versionsschutz). Fehler erscheinen am Artefakt.
- **Sammeln:** ein Endpunkt `PATCH /api/v1/artifacts/bulk-update/` (aus der Tabellenansicht, E6). Je Eintrag `{artifact_id, expected_version, fields}`; **eine Transaktion, alles oder nichts**; jeder Eintrag läuft durch denselben Dienst wie das Einzel-Update; bei einem Fehler wird nichts geschrieben und die Antwort listet jeden fehlerhaften Eintrag mit Code und Grund. Höchstens 100 Einträge.
- Sperre (Workflow, `freeze_on_enter`, #1670 P4) wirkt wie beim Einzel-Update: 409 `CONFLICT`. Rechte, Audit und Versionen entstehen wie sonst.
- Die Sicht ändert nie die Struktur (Verschieben, Allokieren): das geht nur in den Bäumen und der Zusammenhangs-Ansicht.

## 5. API und MCP

| Zweck | REST | MCP |
|---|---|---|
| Sichten verwalten | `GET/POST/PATCH/DELETE /api/v1/document-views/` (`If-Match`) | `document_view.list/get/create/update/delete` |
| Sicht ausgeben | `GET /api/v1/document-views/{id}/render/` | `document_view.render` (Markdown) |
| Export | `GET /api/v1/document-views/{id}/export/?format=markdown` | wie render |
| Sammel-Schreiben | `PATCH /api/v1/artifacts/bulk-update/` (aus Tabellenansicht) | `artifact.bulk_update` |

Präfix `document_view` (nicht `document`), damit es nicht mit den Tools des Artefakts `Document` kollidiert. Bei jeder neuen Route und jedem Tool: Manifest, `test_tool_manifest_drift.py`, OpenAPI-Tests und Zähler wie in der Spec zu #1670.

## 6. Reihenfolge und Abhängigkeiten

```
#1670 P1 (sort_key) ──┐
#1670 P4 (Sperre)  ───┼──> D0 … D6 (diese Spec)
Tabellenansicht    ───┘     (Filter-Sprache, bulk-update)
```

Vor Beginn: Plan der Tabellenansicht auf Aktualität prüfen (Attribut v3, `Document`). Bis dahin ist diese Spec nur Entwurf; ein Umsetzungsplan entsteht erst danach.

## 7. Teilprojekte und Akzeptanz

| # | Inhalt | Akzeptanz (prüfbar) |
|---|---|---|
| **D0** | ADR-026 anpassen (Sicht bearbeitbar), alte Spec und Plan als überholt kennzeichnen | ADR-Eintrag, Index aktualisiert |
| **D1** | `DocumentView` (Modell, RLS, Schema-Prüfung, CRUD REST) | Fremder Nutzer/Mandant kann Sicht nicht lesen; ungültige `config` → 400; Versionskonflikt → 412 |
| **D2** | Leseobjekt `render` mit Auflösung, Nummerierung, `editable_fields`, Rechte | Konstante Abfragezahl für 50 und 500 Einträge; nicht lesbare Artefakte fehlen; gelöschte Quelle zeigt Hinweis |
| **D3** | Oberfläche Lesen, Export (Markdown), Druck, Einrichten | Export gleich Lesestand; Druckvorschau ohne Bedienelemente; E2E |
| **D4** | Bearbeiten sofort | Gesperrtes Artefakt nicht bearbeitbar (409); Versionskonflikt am Artefakt sichtbar |
| **D5** | Bearbeiten sammeln über `bulk-update` | Ein ungültiger Eintrag → nichts geschrieben; Antwort nennt Eintrag und Grund; 101 Einträge → 400 |
| **D6** | MCP-Tools `document_view.*` | Manifest-Drift-Test grün; Agent kann Markdown lesen |

## 8. Risiken

| # | Risiko | Maßnahme |
|---|---|---|
| R1 | Große Sichten sind langsam | Seitenweise je Kapitel, konstante Abfragezahl als Test |
| R2 | Verweise im JSON werden ungültig | Auflösung beim Lesen, Hinweis statt Fehler (V6) |
| R3 | Rechte-Leck über Filter | Rechteprüfung in der Auflösung, Test mit zwei Rollen |
| R4 | Sammel-Speichern umgeht Regeln | Pflicht: gleicher Dienst je Eintrag, Test je Regel (Sperre, Recht, Version) |
| R5 | Lange Abhängigkeitskette (#1670, Tabellenansicht) | Reihenfolge in §6, keine Vorab-Implementierung |
| R6 | Schema-Entwicklung der `config` | `schema_version`, Migration pro Version |
| R7 | Rechte pro Artefakt (`ItemPermission`, Cache 60 s) dürfen die konstante Abfragezahl nicht brechen | Stapelweise Rechteprüfung je Seite in D2 entwerfen und messen; Test mit einer Sperre pro zehnten Artefakt |

## 9. Offene Fragen

| ID | Frage |
|---|---|
| **O1** | Sollen Sichten später mit anderen Nutzern geteilt werden (Workspace-Sicht)? Aktuell nicht Teil. |
| **O2** | Welcher Editor bearbeitet lange Markdown-Beschreibungen in der Sicht (der vorhandene Editor der Formulare)? |
| **O3** | Gelten Tiefe 4 und 100 Kapitel als richtig? |

## 10. Bezüge

ADR-026, Spec `2026-11-02-f2-document-design.md`, Spec `2026-11-04-ordnung-allokation-design.md` (PR #1711), Spec `2026-09-03-tabellenansicht-design.md`, #1374 (F5 bleibt eigenes Vorhaben), #1257 (konfigurierbare Baumanzeige als Muster), #1670.
