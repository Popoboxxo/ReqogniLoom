---
type: REVIEW
scope: wp-1d-roundtrip-csv
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: CSV-Bulk-Import-Round-Trip

**Quellen:** `wp1d-csv-import-matrix.json` (Kontrolltabelle, 16 Fälle +
Idempotenz), `wp1d-csv-import-matrix-v1.json` (Vorlauf, 18 Fälle),
`wp1d-roundtrip-v1/v2.json`, Backend-Log.

**Aufrufform:** `POST /api/v1/workspaces/{id}/import/csv/`,
`multipart/form-data` mit `file` (CSV) und `entity_type`
(`Requirement|ArchitectureElement|TestCase`), umgesetzt in
`backend/rest_api/views.py:7951-8045`.

> Zwei Vorbedingungen mussten erst ermittelt werden, weil sie nicht im
> OpenAPI-Schema stehen und der Auftrag sie nicht nennt:
> **(1)** `entity_type` ist ein **Formularfeld**, kein Query-Parameter.
> **(2)** Der Body muss `multipart/form-data` sein. Ein reiner
> `text/csv`-Body ergibt `415 UNSUPPORTED_MEDIA_TYPE`.

---

## 1. Der Kernbefund (`AUD-2026-09-070`, Critical)

### Was der Exporter schreibt

```
GET /api/v1/workspaces/<B>/export/csv/?entity_type=Requirement
```

Zeile 1:
```
# terminology_profile: default
```
Zeile 2:
```
"title","description","category","status","type","level","complexity_fibonacci","verification_method","suspect","lifecycle_status","uid","id","artifact_id","version","created_at","modified_at"
```

### Was der Importer daraus macht

Import genau dieser Datei (unverändert, nur die Datenzeile ergänzt):

```
HTTP 201
{"success": true,
 "imported_count": 0,
 "skipped_count": 0,
 "status": "ok",
 "errors": [],
 "warnings": ["Unrecognized column(s) ignored, their data was NOT imported:
               , 1, CLEAN-1, SyReq, demo, draft, plain desc.
               Expected columns for 'Requirement': artifact_id, category, …"]}
```

**HTTP 201 „success", 0 importierte Zeilen.** Die Warnung listet die *Datenwerte*
als „unbekannte Spalten" — weil der Importer die Kommentarzeile als Kopfzeile
liest und damit jede echte Spaltenzuordnung verliert.

### Kausalitätsbeweis

Identische Datei, **nur** die erste Zeile entfernt:

```
POST mit Zeile 2 als Header
→ HTTP 201 {"success": true, "imported_count": 1, "skipped_count": 0,
            "status": "ok", "errors": [], "warnings": []}
```

Damit ist die Kommentarzeile die Ursache, nicht die Datenlage. Der Row-Counter
in Tenant B (`GET /api/v1/requirements/?workspace_id=B`) stieg nur im zweiten
Fall.

### Warum das mehr als ein Komfortfehler ist

`backend/application/export_service.py:17-18` dokumentiert die Zusage:

> „includes identity/audit columns … so that `export_csv -> ImportService.import_csv`
> is a lossless round-trip (the ReqFlow self-migration safety net)"

und `import_service.py:14`:

> „Identity / audit columns emitted by ExportService … so `export_csv →
> ImportService.import_csv` is a lossless round-trip"

Diese Zusage gilt für den Self-Migration-Pfad, und sie ist für den
Standardpfad (`# terminology_profile: default`, der Default der
Terminology-Profile `default`/`dev_mode`/`se_mode`) **nicht erfüllt**. Ein
Migration auf eine frische Instanz über den vorgesehenen Weg importiert
**nichts** und meldet Erfolg.

**Kein Regressionsnachweis möglich:** ob der Defekt durch eine kürzere Header-
Liste oder durch das Entfernen der Kommentarzeile behoben wird, war nicht
Gegenstand dieses Audits (keine Produkt-Fixes).

---

## 2. Kontrolltabelle (korrekter Header, ASCII-sicher)

16 Fälle, alle mit dem Header des Exporters **ohne** Kommentarzeile, Import
in Tenant B.

| # | Fall | Status | `imported_count` | `status` | `errors` | Bewertung |
|---|---|---|---|---|---|---|
| 1 | 1 gültige Zeile | 201 | 1 | ok | `[]` | ✅ |
| 2 | 2 gültige Zeilen | 201 | 2 | ok | `[]` | ✅ |
| 3 | ungültiger `status` (`NOT_A_STATUS`) | **201** | **1** | **ok** | **`[]`** | ⚠ **Enum nicht validiert** |
| 4 | ungültiger `type` (`NOT_A_TYPE`) | 400 | 0 | **rollback** | **`[]`** | ⚠ stiller Fehlschlag |
| 5 | ungültiges `level` (`NOT_AN_INT`) | 400 | 0 | **rollback** | **`[]`** | ⚠ stiller Fehlschlag |
| 6 | fehlender Titel | 400 | 0 | validation_error | `[{row_number: 2, field: "title", message: "Required field 'title' is missing or empty."}]` | ✅ vorbildlich |
| 7 | `ÄÖÜ äöü € 🚀` im Titel | 201 | 1 | ok | `[]` | ✅ UTF-8 korrekt |
| 8 | `"desc, with comma"` (gequotet) | 201 | 1 | ok | `[]` | ✅ RFC-4180-konform |
| 9 | Semikolon statt Komma | 400 | 0 | validation_error | `[{row_number: 2, field: "title", …}]` + Warnung | ⚠ kein Delimiter-Sniffing, irreführende Meldung |
| 10 | UTF-8-BOM | 400 | 0 | validation_error | `[{row_number: 2, field: "title", …}]` | ⚠ BOM nicht erkannt, irreführende Meldung |
| 11 | kaputtes Quoting `"RTQ-11 unterminated,…` | **201** | **1** | **ok** | **`[]`** | ⚠ **kaputte Zeile still importiert** |
| 12 | 1 gültig + 1 ohne Titel + 1 mit `BAD_STATUS` | 400 | 0 | validation_error | **nur 1** Fehler (`row_number: 3`), `skipped_count: 3` | ⚠ Fehlerliste unvollständig |
| 13 | unbekannte Spalte `totally_new_col` | 201 | 1 | ok | `[]` + Warnung mit Spaltennamen | ✅ vorbildlich (Fix #120) |
| 14 | Latin-1-Bytes | 400 | – | – | `CSV file must be UTF-8 encoded.` | ✅ sauber |
| 15 | kein `file`-Part | 400 | – | – | `No CSV file uploaded. Provide a 'file' field in multipart/form-data.` | ✅ |
| 16 | unbekannter `entity_type` | 400 | – | – | `Unsupported entity_type 'RequirementX'. Allowed: ['ArchitectureElement', 'Requirement', 'TestCase']` | ✅ |

### Fall 11 im Detail — was importiert wurde

```
Anfrage:  "RTQ-11 unterminated,demo,draft,SyReq,1,,,,,,,,\n
Antwort:  HTTP 201, imported_count: 1, errors: [], warnings: []
Ergebnis: GET /requirements/?workspace_id=B →
          "RTQ-11 unterminated,demo,draft,SyReq,1,,,,,,,,"
```

Ein RFC-4180-Verstoß (unterminiertes Anführungszeichen) führt dazu, dass die
gesamte Restzeile in **ein einziges Feld** kollabiert und dieses Feld als
Titel gespeichert wird. Kein Fehler, keine Warnung. Bei einer Migration mit
Tausenden Zeilen ist das stiller Datenverlust.

### Fall 3 vs. Fall 4 — Enum-Validierung ist inkonsistent

Gleiche Fehlerklasse, zwei völlig verschiedene Ergebnisse:

| Feld | ungültiger Wert | Ergebnis |
|---|---|---|
| `status` | `NOT_A_STATUS` | **201 success**, Zeile importiert |
| `type` | `NOT_A_TYPE` | 400, `status: "rollback"`, `errors: []` |
| `level` | `NOT_AN_INT` | 400, `status: "rollback"`, `errors: []` |

`status` durchläuft einen Pfad, der den Wert **still auf einen Default
zurückfällt**; `type`/`level` scheitern tiefer (DB/Domain-Ebene) und werden
dann vom nackten `except` verschluckt.

---

## 3. Idempotenz (`AUD-2026-09-072`, High)

Dieselbe Datei `title,description,category,status,type,level\nRTQ-IDEM,desc,demo,draft,SyReq,1\n`
**dreimal** importiert:

| Import | Status | Antwort |
|---|---|---|
| 1 | 201 | `{"success": true, "imported_count": 1, "skipped_count": 0, "status": "ok", "errors": [], "warnings": []}` |
| 2 | 201 | `{"success": true, "imported_count": 1, "skipped_count": 0, "status": "ok", "errors": [], "warnings": []}` |
| 3 | 201 | `{"success": true, "imported_count": 1, "skipped_count": 0, "status": "ok", "errors": [], "warnings": []}` |

Endstand in Tenant B:

```
["RTQ-1", "RTQ-2", "RTQ-3", "RTQ-7", "RTQ-8",
 "RTQ-11 unterminated,demo,draft,SyReq,1,,,,,,,,",
 "RTQ-13", "RTQ-IDEM", "RTQ-IDEM", "RTQ-IDEM",
 "WP1D-PROBE-B Requirement ÄÖÜ 🚀"]
```

**Drei Zeilen mit identischem Titel `RTQ-IDEM`.** Kein `skipped_count`, keine
Warnung, kein Fehler.

**Bewertung:** Der Importer kennt `_IDENTITY_COLUMNS`
(`import_service.py:71-73`, „Identity / audit columns handled specially by
`_insert_rows`") — der Identity-Pfad existiert also, greift aber nur, wenn die
Datei diese Spalten mitbringt. Meine Testdatei hatte **keine** `id`/`uid`-Spalte
und die Daten besitzen keine `uid`. Ein erneuter Import **derselben Datei**
erzeugt aber Duplikate, weil ohne Identitätsspalte nichts verglichen werden
kann. Das ist die für Bulk-Import übliche Anforderung
(`#113`-Umfeld: Re-Import einer bereits importierten Datei) und ist nicht
abgedeckt.

Klarstellung: In der Realität liefert der eigene **Export** die
Identity-Spalten (`id`, `artifact_id`, `uid`, `version`, `created_at`,
`modified_at`) mit, sodass der Identity-Pfad greift — **wenn** die
Kommentarzeile den Import nicht bereits scheitern lässt (F1). Die Duplikat-
Anforderung ist also nicht für den Export→Import-Pfad belegt, sondern für den
**importierten Fremd-CSV ohne Identitätsspalte**. Beides sind reale Wege.

---

## 4. Root Cause der stillen Fehlschläge

`backend/application/import_service.py:300-314`:

```python
        except Exception:
            logger.exception(
                "ImportService: DB error during atomic insert, rolling back. "
                "entity_type=%s workspace_id=%s",
                entity_type,
                ws_uuid,
            )
            return ImportResult(
                success=False,
                imported_count=0,
                skipped_count=len(rows),
                errors=[],            # ← keine Diagnose
                status="rollback",
                warnings=warnings,
            )
```

Der konkrete Fehler im Log (12× im Fenster, aus dem Fall `1_good_crlf_utf8`
mit verschobener Spaltenzuordnung):

```
File "/app/application/import_service.py", line 279, in import_csv
  imported = self._insert_rows(
File "/app/application/import_service.py", line 591, in _insert_rows
  value = _import_value(row.get(col), kind)
File "/app/application/import_service.py", line 101, in _import_value
  return int(stripped) if stripped else None
ValueError: invalid literal for int() with base 10: 'SyReq'
```

`_insert_rows` greift `row.get(col)` mit der **Spaltenzuordnung aus dem Header**;
sobald der Header nicht zum Feldspec passt (Kommentarzeile, BOM, Semikolon),
landet ein String in einem Integer-Feld, `int()` wirft, und der nackte
`except` macht daraus eine leere Fehlerliste.

**Einordnung:** Fehler-Maskierung ist an sich richtig und gewollt
(`backend/rest_api/tests/test_error_masking_cwe209.py` prüft genau das, und
`views.py:217` mappt `ValidationError` bewusst auf 400 statt 500). Das Problem
ist nicht das Maskieren, sondern dass die Maske **leer** ist: der Client
bekommt `success: false`, `status: "rollback"`, `imported_count: 0` — und kann
nicht unterscheiden zwischen

- „Datei enthielt 0 verwertbare Zeilen",
- „Berechtigung fehlt",
- „DB-Constraint verletzt",
- „Datei ist defekt",
- „Spalten passen nicht".

Ein nicht-leerer generischer Code (`IMPORT_ROLLED_BACK`) plus die
`row_number`-Liste, die der `validation_error`-Pfad **schon** liefert, wäre die
Nahelösung.

---

## 5. Transaktionsgrenze

| Prüfung | Ergebnis |
|---|---|
| `imported_count` nach jedem Fehlversuch | 0 ✅ |
| Row-Counter in Tenant B nach 9 Importversuchen | unverändert ✅ |
| `status` bei Validierungsfehlern | `validation_error` (Zeilen einzeln benannt) ✅ |
| `status` bei DB-Fehlern | `rollback` (ohne Zeilenangabe) ⚠ |
| Teilimport (einige Zeilen ok, andere nicht) | **nein** — immer alles oder nichts ✅ |

**Die Transaktionsgrenze ist korrekt: all-or-nothing, kein Partial-Import.**
Das ist die richtige Entscheidung für einen Bulk-Import.

Die Status-Semantik ist aber nicht interpretierbar: `skipped_count` zählt
**Zeilen**, nicht Fehler, und `errors` listet nicht alle Fehler (Fall 12:
`skipped_count: 3`, aber nur 1 Eintrag). Ein Client kann `status` nicht als
Fehlerursache verwenden.

---

## Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| Import von **>1000 Zeilen** (Zeilenlimit) | `import_service.py` nennt ein „row limit exceeded"; die Grenze wurde nicht ausgelöst, weil der Probedatensatz klein blieb und ein Absicht-300-Zeilen-Stress keine zusätzliche Erkenntnis für die identifizierten Defekte gebracht hätte |
| `ArchitectureElement` / `TestCase` als `entity_type` | getestet wurde nur `Requirement`; die Feld-Specs unterscheiden sich (`export_service.py:134ff`), das Verhalten bei unbekanntem `entity_type` ist belegt |
| Import in **Tenant A** mit dessen echten Daten | hätte in den Produktiv-Workspace des geteilten Stacks geschrieben; der Foreign-Workspace-Test (A-Token → Workspace B) belegt stattdessen das Fehlerbild, ist aber **kein** Positivtest |
| `dry_run`-Äquivalent beim CSV | existiert nicht (nur beim ReqIF-Import, dort `dry_run: false` beobachtet) |
| Verhalten bei **gleichem `id`** in der Datei (Identity-Pfad) | der Identity-Pfad wurde nicht mit einer Datei getestet, die `id`/`uid` enthält — das hätte eine Kollision mit Bestandsdaten ausgelöst |
