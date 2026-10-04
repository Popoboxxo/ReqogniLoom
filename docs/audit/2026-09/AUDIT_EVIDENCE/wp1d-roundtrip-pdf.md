---
type: REVIEW
scope: wp-1d-roundtrip-pdf
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: PDF-Report-Export

**Quellen:** `wp1d-pdf-report-tenantA.pdf` (60 664 B),
`wp1d-pdf-report-tenantB.pdf` (2 202 B), `wp1d-roundtrip-v1/v2.json`,
`wp1d-oracle-and-envelope.json` (`csv_export_scoping`,
`error_envelope_shapes`).

**Aufruf:** `GET /api/v1/workspaces/{id}/reports/pdf/`
(`rest_api/views.py`, PDF-Pfad delegiert an
`application/pdf_report_generator` / `export_service`, das laut
`export_service.py:27-28` reportlab nutzt).

---

## 1. Messungen

| Fall | Workspace | Status | Dauer | Bytes | `Content-Type` | `Content-Disposition` |
|---|---|---|---|---|---|---|
| Tenant A (eigen) | `4eee7ca1-…` (888 Requirements) | 200 | **0,75 s** | 60 664 | `application/pdf` | `attachment; filename="Zahnbürste_SysEng_Demo_requirement_document.pdf"` |
| Tenant B (eigen) | `77c6286e-…` (1 Requirement) | 200 | 0,06 s | 2 202 | `application/pdf` | `attachment; filename="WP1D_Probe_WS_requirement_document.pdf"` |
| **fremder Workspace mit A-Token** | Tenant B mit A-Token | **404** | – | 112 | `application/json` | – |
| `?async=true` | Tenant A | 200 | – | 60 664 | `application/pdf` | – (synchron) |
| `?async=true` mit B-Token auf B | Tenant B | 404 | – | – | – | – |

**Ergebnis:**

- **Synchron gerendert** im Request-Thread. `?async=true` wird ignoriert — es
  gibt weder 202 noch eine Task-ID, die Response ist byteweise dieselbe.
- **Kein Tenant-Leak.** Tenant Bs PDF enthält ausschließlich Bs 1 Requirement
  (2 202 B); Tenant As PDF ausschließlich A-Daten. Ein Fremd-Workspace ergibt
  404 mit der korrekten Fehlerhülle.
- **Bei dieser Datenmenge kein Timeout-Risiko**: 888 Requirements in 0,75 s
  (~1 180 Anforderungen/s End-to-End inkl. PDF-Render).

---

## 2. Schriften / Glyphen (`AUD-2026-09-086`, Medium)

Aus der PDF-Objekttabelle beider Dateien:

| Eigenschaft | Tenant A | Tenant B |
|---|---|---|
| `/BaseFont` | `Helvetica`, `Helvetica-Bold` | `Helvetica`, `Helvetica-Bold`, **`ZapfDingbats`** |
| `/Encoding` | `WinAnsiEncoding` | `WinAnsiEncoding` |
| `/FontFile` / `/FontFile2` / `/FontFile3` | **nicht vorhanden** | **nicht vorhanden** |
| `/Type0` (CID-Font) | **nein** | **nein** |
| `/Identity-H` | **nein** | **nein** |
| `/ToUnicode` (CMap für Text-Extraktion) | **nein** | **nein** |
| PDF-Version | `%PDF-1.4` | `%PDF-1.4` |

**Befund:** es wird ausschließlich eine der Base-14-Schriften mit fester
WinAnsi-Kodierung verwendet. **Kein einziger eingebetteter Font, kein
CID-Font.** Damit ist der darstellbare Zeichenvorrat auf WinAnsiEncoding
festgelegt — ungefähr Latin-1 plus einige Sonderzeichen. **Nicht darstellbar
sind:**

| Zeichenbereich | Beispiel | Kodierung |folge |
|---|---|---|---|
| Emoji / Astral | 🚀 U+1F680, ✅ U+2705 | 4 Byte UTF-8, kein WinAnsi | Ersatzzeichen / Leerbox |
| CJK | 漢 U+6F22 | 3 Byte, kein WinAnsi | Ersatzzeichen |
| Kyrillisch / Griechisch | Д U+0414, Ω U+03A9 | kein WinAnsi | Ersatzzeichen |
| `€` U+20AC | € | WinAnsi **0x80** | ✅ darstellbar |

**Der Testbogen lieferte den Beleg mit:** Tenant Bs einziges Requirement
trägt den Titel `WP1D-PROBE-B Requirement ÄÖÜ 🚀`. Tenant Bs PDF enthält
zusätzlich `ZapfDingbats` in der Font-Liste, Tenant As PDF **nicht** — As
Daten sind ASCII. `ZapfDingbats` ist reportlabs Ersatzschrift für
nicht darstellbare Zeichen in Base-14-Fonts. Das ist ein korrespondierendes
Indiz, dass für das Emoji ein Fallback verwendet wurde.

**Nicht behauptet:** welchen exakten Ersatz-Glyphen reportlab setzt. Die
Content-Streams sind ASCII85+Flate kodiert; meine Extraktion der
Text-Operatoren hat den Titel nicht als Klartext gefunden, und ich habe den
PDF-Stream-Encoder nicht weiter dekompiliert. Der Beleg ist die Font-Tabelle
der beiden Dateien (objektiv auslesbar), nicht der gerenderte Glyphe.

**Auswirkung auf das Projekt:** ein europäisches Anforderungsportfolio kommt
mit WinAnsi aus (Umlaute, ß, €, typografische Anführungszeichen). Sobald ein
Autor Emoji, kyrillische oder chinesische Zeichen in einem Titel oder
Kommentar verwendet, ist der Text im PDF nicht lesbar — **und weil es keine
`/ToUnicode`-CMap gibt, ist er auch aus dem PDF nicht extrahierbar**. Ein
PDF-Archiv verliert damit Texte stillschweigend.

---

## 3. `Content-Disposition` (`AUD-2026-09-087`, Medium)

```
Content-Disposition: attachment; filename="Zahnbürste_SysEng_Demo_requirement_document.pdf"
```

`Zahnbürste` enthält `ü` — ein Nicht-ASCII-Zeichen im `filename`-Parameter.

**Fehlend:** die RFC-6266/5987-Ergänzung

```
; filename*=UTF-8''Zahnb%C3%BCrste_SysEng_Demo_requirement_document.pdf
```

**Auswirkung:** RFC 6266 §4.3 legt für `filename` ISO-8859-1 nahe; Browser
und HTTP-CLients wenden ihre eigene Locale an. Ergebnis sind
Ersatzzeichen (`ZahnbÃ¼rste…`) oder ein von der Locale abhängiger Dateiname.
Ein ASCII-Fallback wie `Zahnburste_…` zusätzlich zu `filename*` wäre die
Standardlösung.

Vergleich: der CSV- und der ReqIF-Export sind **nicht** betroffen —
`export_requirement.csv` bzw. `zahnburste-syseng-demo.reqif` sind ASCII
(der ReqIF-Slug ist bewusst kleingeschrieben).

---

## 4. CSV-Export: fehlende `charset` (`AUD-2026-09-087`, Medium)

```
GET /api/v1/workspaces/<B>/export/csv/?entity_type=Requirement
Content-Type: text/csv
```

**Kein `charset=utf-8`.** Die Bytes sind korrekt UTF-8 — verifiziert auf
Rohbyte-Ebene:

```
raw:  b'WP1D-PROBE-B Requirement \xc3\x84\xc3\x96\xc3\x9c \xf0\x9f\x9a\x80","probe"'
      =  "WP1D-PROBE-B Requirement ÄÖÜ 🚀"
```

Das ist kein Encoding-Bug im Generator. Es ist ein **Deklarationsproblem**:
RFC 4180 legt für CSV kein Standard-Encoding fest, und `text/csv` ohne
`charset` überlässt die Interpretation dem Client. Excel mit de-DE-Einstellung
(Standard für den deutschsprachigen Zielkontext dieser Anwendung) interpretiert
ohne `BOM`/`charset` als Windows-1252 und stellt `ÄÖÜ` als `Ã„Ã–Ãœ` dar.

Der im ersten Durchlauf sichtbare „Mojibake" war eine Konsolen-Artefakt meines
Ausgabeterminals — die Rohbytes sind korrekt. Ich prüfe das explizit, weil
ein blinder Befund hier falsch gewesen wäre.

---

## 5. Tenant-Scoping des Exports — `AUD-2026-09-081`

| Credential | Ziel | Status | Body-Größe | Inhalt |
|---|---|---|---|---|
| A-Token | Tenant-As eigenes WS | 200 | 239 940 B | A-Daten |
| A-Token | **Tenant B** | **200** | **31 B** | nur `# terminology_profile: default\n` |
| B-Token | Tenant B | 200 | 481 B | Bs 1 Requirement (UTF-8 korrekt) |

Der A-Token bekommt für Tenant Bs Workspace **200 statt 403/404** — aber nur
die Kopfzeile, weil die RLS alle Zeilen filtert. Kein Datenabfluss, aber ein
**drittes Verhalten** neben `reqif` (404) und `pdf` (404). Detailliert in
`wp1d-tenant-leak-matrix.md` §6.

---

## 6. Was funktioniert

- **Tenant-Isolation:** sauber, inkl. der Fehlerpfade.
- **Synchron-Render ist schnell genug** für die gemessene Datenmenge.
- **Deterministische, korrekte PDF-Struktur** (`%PDF-1.4`, `Helvetica` +
`Helvetica-Bold` als Standard-14, `ZapfDingbats` als Fallback).
- **Konsistente Fehlerhülle:** der 404 auf einen fremden Workspace kommt im
  `{"error": {code, message, details}}`-Format.
- **Umlaute im Dateinamen der Dateninhalte** sind im PDF *gerendert* (nicht
  nur kodiert) — WinAnsi deckt sie ab.

---

## Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| **Timeout / Request-Abbruch bei sehr großen Datenmengen** | nur 888 Requirements (0,75 s) und 1 Requirement gemessen. Ob der Sync-Render bei >10 000 Artefakten in einen Request-Timeout oder Worker-Abbruch läuft, ist **nicht** belegt. Das Projekt kennt das Muster — `bundle-compression-status/{task_id}/` und `consistency-status/{task_id}/` existieren für genau solche asynchronen Dispatches (`rest_api/urls.py:908-921`), der PDF-Pfad nutzt es nicht |
| **Exakter Ersatz-Glyphe für nicht darstellbare Zeichen** | PDF-Stream war ASCII85+Flate-kodiert; die Dekodierkette habe ich nicht vollständig verifiziert (siehe §2) |
| **Bild-/Logo-Einbettung, Seitenumbrüche, Kopf-/Fußzeilen** | nicht Gegenstand des Auftrags |
| **Report-Inhalte jenseits Requirements** (Architecture, TestCase, TraceLinks) | der Endpoint hat nur den Requirement-Dokument-Modus erzeugt; weitere Modi nicht durchprobiert |
| **PDF für ein Workspace mit ausschließlich asiatischen Daten** | hätte Testdaten in einem weiteren Tenant erzeugt; der Font-Befund aus der Font-Tabelle ist bereits eindeutig |
| **Barrierefreiheit des PDFs** (Tagging, Lesezeichen, `Alt`-Text für Tabellen) | nicht Gegenstand des Auftrags; bei `Helvetica` ohne Font-Einbettung sehr wahrscheinlich nicht vorhanden |
