---
type: REVIEW
scope: wp-1d-evidence-index
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz-Index

**Stack:** `http://localhost:8001` (ASGI/uvicorn im Container
`ai-native-reqflow-poc-backend-1`), Branch `chore/system-audit-2026-09`
== main @ `abd61aed` + WP-1a/WP-3-Commits.

**Findings dieses Abschnitts:** `AUD-2026-09-070` … `AUD-2026-09-093`
(Fortsetzung nach `AUD-2026-09-043` aus WP-1a; `050`–`0xx` sind für WP-1b
reserviert).

## Dateien

| Datei | Inhalt | Größe |
|---|---|---|
| `wp1d-viewset-apiview-inventory.json` | AST-Inventar aller ViewSet-/APIView-Klassen in `backend/rest_api/` mit `file:line` + Basis-Kette. Zählweg für `AUD-2026-09-084` | 41 KB |
| `wp1d-resolved-routes.json` | 487 aufgelöste `/api/v1/*`-URL-Muster aus dem Django-URLResolver (im Container erzeugt), je Pfad View-Klasse + Methoden | 79 KB |
| `wp1d-openapi-drift.json` | Pfad-/Methoden-/Security-/Fehler-/Parameter-Diff zwischen live erzeugtem Schema und URLResolver. Basis für `AUD-2026-09-075`, `-085`, `-090`, `-091` | 3 KB |
| `wp1d-auth-pagination-filter-errors-live.json` | 20 Auth-Fälle, 33 Pagination-Inventar-Zeilen, 72 `page_size`/`page`-Stress-Messungen, 60 Filter-Proben, 16 Fehlerformat-Fälle, 12 Ingress-Proben | 53 KB |
| `wp1d-pagination-matrix.json` | 44 Pagination-Inventar-Zeilen + 144 Stress-Messungen. Basis für `AUD-2026-09-073`, `-074` | 41 KB |
| `wp1d-tenant-leak-matrix.json` | 120 Cross-Tenant-Proben mit Response-Auszügen, Tenant-B-Fixture-IDs, Token-Fingerabdrücke (sha256, 12 Hex) | 48 KB |
| `wp1d-tenant-leak-verification.json` | Verifikation der zwei LEAK-Kandidaten (Search-Echo, API-Key-Liste) + 10-Endpunkt-Sweep gegen Tenant-B-Daten | 3,8 KB |
| `wp1d-authorization-asymmetry.json` | Tenant-Existenz-Orakel (6 Endpunkte × 3 Workspace-IDs), CSV-Export-Scoping (3 Credentials), 6 Fehlerhüllen-Formen. Basis für `AUD-2026-09-081`, `-082`, `-093` | 6,5 KB |
| `wp1d-ingress-symmetry.json` | 4 Prefixe × 3 Credentials, JSON-RPC `initialize`. Basis für die Korrektur der WP-1a-Beobachtung | 3,2 KB |
| `wp1d-roundtrip-v1.json` | Erster Durchgang ReqIF/CSV/PDF (mit den noch falschen Content-Types) | 5,7 KB |
| `wp1d-roundtrip-v2.json` | Korrekter Durchgang: ReqIF via multipart, CSV via multipart/form-data, PDF-Zeitmessung | 7,5 KB |
| `wp1d-csv-import-matrix.json` | 16 Kontrollfälle + 3× Idempotenz. Basis für `AUD-2026-09-070`, `-072`, `-079`, `-080`, `-083` | 4,8 KB |
| `wp1d-csv-import-matrix-v1.json` | 18 Vorlauffälle (mit dem Export-Header inkl. Kommentarzeile) — zeigt den 201/0-Import | 9,6 KB |
| `wp1d-reqif-export-A.excerpt.xml` | Gekürzter Export (915 → 2 SPEC-OBJECT, 13 KB) zur ReqIF-1.2-Konformitätsprüfung | 13 KB |
| `wp1d-reqif-export-B.xml` | Vollständiger Export (2 SPEC-OBJECT, 9 KB) mit Sonderzeichen im Titel | 9,4 KB |
| `wp1d-pdf-report-tenantA.pdf` | PDF-Export, 888 Requirements, 0,75 s. Font-Tabelle als Beleg für `AUD-2026-09-086` | 59 KB |
| `wp1d-pdf-report-tenantB.pdf` | PDF-Export, 1 Requirement mit `ÄÖÜ 🚀` — enthält `ZapfDingbats` als Fallback-Font | 2,2 KB |
| `wp1d-row-counts-before.json` | Zeilenzahlen aller 100 Tabellen vor der Provisionierung (unter Tenant-A-RLS) | 2,8 KB |
| `wp1d-row-counts-after.json` | Dieselben Zeilenzahlen nach dem Cleanup — Differenz in `wp1d-cleanup-verification.md` | 2,8 KB |
| `wp1d-cleanup-verify-api.json` | API-seitige Verifikation: Tenant-B-Login 401, Tenant-A-Logins und -Zähler normal | 1 KB |
| `wp1d-viewset-apiview-counting-method.md` | siehe `wp1d-schema-drift.md` §6 | — |

## Menschenlesbare Evidenzdateien

| Datei | Inhalt |
|---|---|
| `wp1d-auth-matrix.md` | 19 Auth-Fälle mit Status, `error.code`, `message`, Bewertung; Fehlercode-Granularität; Header-Reihenfolge |
| `wp1d-schema-drift.md` | Schema-Kennzahlen, Pfad-/Methoden-Abdeckung, Fehler-Schema-Histogramm, `COMMON_ERROR_RESPONSES`-Nutzungsnachweis, Security, Zählmethode der ViewSets/APIViews |
| `wp1d-pagination-filter-matrix.md` | 44 Pagination-Inventar-Zeilen, `page_size`-Deckelungstabelle, 500er-Matrix auf ungültige `page`-Werte, 60 Filter-Proben |
| `wp1d-error-format-matrix.md` | Matrix A (konsistente Fälle) und B (5 Abweichungsformen), Fehlercode-Registry-Lücken |
| `wp1d-tenant-leak-matrix.md` | **120 Tests als `Endpoint \| Methode \| Tenant-B-ID \| Erwartung \| Ist \| Ergebnis`**, Verifikation der Falsch-Positive, Authorisierungs-Asymmetrien |
| `wp1d-roundtrip-reqif.md` | Export-Kennzahlen, ReqIF-1.2-Konformitätstabelle, Merge-Nachweis für `#1003` (Issue) / `#1004` (PR), Import-415-Matrix, Root Cause aus dem Log, Idempotenz |
| `wp1d-roundtrip-csv.md` | Kommentarzeilen-Befund mit Kausalitätsbeweis, 16-Fälle-Kontrolltabelle, Idempotenztest, Root Cause `import_service.py:300-314`, Transaktionsgrenze |
| `wp1d-roundtrip-pdf.md` | Zeitmessung, Font-/Encoding-Tabelle, `Content-Disposition`/`charset`, Tenant-Scoping |
| `wp1d-cleanup-verification.md` | Testdaten-Inventar, API- und DB-Verifikation, Rückstandsbegründung |

**Kein** separates Zählmethoden-Skript: die Methode ist vollständig in
`wp1d-schema-drift.md` §6 beschrieben.

## Reproduzierbarkeit

Alle JSON-Artefakte wurden aus Live-Antworten bzw. aus einem
Django-URLResolver-Lauf im Container erzeugt. Die Mess-Skripte selbst sind
bewusst **nicht** im Repository abgelegt (Auftrag: keine Produkt-Fixes, nur
Audit-Artefakte); die Zählmethode für das ViewSet-/APIView-Inventar ist in
`wp1d-schema-drift.md` §6 so beschrieben, dass sie ohne das Skript nachvollziehbar
ist (AST-Walk + transitive Basisauflösung).

## Datenschutz / Geheimnisse

- **Keine Klartext-Secrets in den Evidenzdateien.** Geprüft per Regex auf
  `Wp1dProbe` (Probe-Passwort), `eyJhbGciOi` (JWT) und
  `SECRET_KEY=` / `AUTH_JWT_SECRET=` — **0 Treffer**.
  Ein JWT war kurzzeitig in `wp1d-auth-…live.json` gelandet (Echo der
  Probe „Token im Query-String") und wurde durch `<JWT-REDACTED>` ersetzt.
- **Kein Secret-Wert ausgelesen.** `AUTH_JWT_SECRET` wurde nur als **Länge**
  gemessen (86 Byte), nie als Wert ausgegeben.
- **Bearer-Token in den Artefakten nur als Fingerabdruck** (`sha256:…`, 12 Hex)
  bzw. vollständig redigiert.
- `wp1d-reqif-export-A.excerpt.xml` enthält bewusst **Demo-Seed-Daten**
  (Zahnbürste-SysEng-Demo) in gekürzter Form; der vollständige 2-MB-Export
  wurde **nicht** ins Repository übernommen.
- Die beiden PDF-Artefakte enthalten Demo-Seed-Daten des Tenant A bzw. die
  Probe-Daten des inzwischen gelöschten Tenant B.
