---
type: REVIEW
scope: "WP-1d (REST API & Data Integration) — adversarial second review"
status: final
date: 2026-10-01
author_agent: backend-reviewer
branch: chore/audit-review-2026-09
method: >
  Adversariale Zweitprüfung. Kein Audit-eigenes AUDIT_EVIDENCE/* als Beweis:
  jede Aussage wurde neu aus dem Produktcode abgeleitet
  (backend/application/**, backend/rest_api/**, backend/reqogniloom/**,
  backend/persistence/**, backend/auth_tenancy/**, backend/traceability/**).
  Zwei-Pass-Protokoll (Recall → Adversar). Jede zitierte Stelle wurde auf
  Inhalt geprüft; Fehlzitate sind als solche ausgewiesen.
targets:
  critical: ["AUD-2026-09-071"]
  control: ["AUD-2026-09-070"]
  high: ["AUD-2026-09-072","AUD-2026-09-073","AUD-2026-09-074","AUD-2026-09-075","AUD-2026-09-076","AUD-2026-09-077","AUD-2026-09-078"]
  medium: ["AUD-2026-09-079","AUD-2026-09-080","AUD-2026-09-081","AUD-2026-09-083","AUD-2026-09-085","AUD-2026-09-086"]
  low: ["AUD-2026-09-088","AUD-2026-09-090","AUD-2026-09-092"]
  info: ["AUD-2026-09-093"]
  baseline_head: "10dc620f"
  audit_baseline: "main @ abd61aed"
environment:
  docker_daemon: down
  live_claims: "NICHT VERIFIZIERBAR (kein Stack); Code-Ursachen statisch geprüft"
---

# REVIEW WP-1d — Adversariale Zweitprüfung (REST API & Data Integration)

## 1. Scope / Methodik

Gegenprüft wurde der WP-1d-Block `AUD-2026-09-070` … `-093` (ID-Bereich 070–093)
des Systemaudits 2026-09 gegen den echten Produktcode am HEAD `10dc620f`
(Branch `chore/audit-review-2026-09`).

**Verbindliches Protokoll:**

1. **Kein Evidenz-Zirkelschluss.** `docs/audit/2026-09/AUDIT_EVIDENCE/*` wurde nur
   als *Ortungshinweis* gelesen. Jeder Befund/jede Widerlegung stützt sich auf
   Produktcode (`<pfad>:<zeile>` + Zitat).
2. **Adversar-Pass.** Jede Kandidatenaussage wurde am realen Code auf ihre
   Mechanik geprüft (nicht auf ihren Wortlaut). Unbeweisbares wurde verworfen
   bzw. als `NICHT VERIFIKABAR` markiert.
3. **Docker-Daemon ist DOWN.** Alle Live-Behauptungen (z. B. „dreifacher Import
   ⇒ 3 Duplikate", „915 Objektfehler", „200 Items/54 KB", „432/439") sind ohne
   Stack **nicht reproduzierbar**. Sie sind unten als `NICHT VERIFIKABAR`
   ausgewiesen — die jeweilige *Code-Ursache* wurde statisch geprüft.
4. Kein Produktcode verändert, kein Push, read-only. `.kimi-code/` und
   `stack-seeds.md` unangetastet.
5. Lokale Toolchain: `django`/`rest_framework`/`reqif` **nicht installiert**,
   daher kein Schema-Regenerierungslauf möglich (`manage.py spectacular` fehlt).
   Fehlender Prüfschritt jeweils benannt.

**Verdikt-Vokabular:** `BESTAETIGT · TEILWEISE · FALSCH · UEBERZOGEN ·
UNTERSCHAETZT · NICHT VERIFIKABAR`. `070` ist eine Kontrolle (bereits
`WIDERLEGT`), kein offenes Finding.

---

## 2. Gegenbeweis-Tabelle

Legende: **Verdikt** = Bewertung der *Aussage*; **Live** = Reproduzierbarkeit
ohne Stack. „Korr. Schwere" nur bei Abweichung.

| ID | Sev (Reg.) | Verdikt | Gegenbeweis `<pfad>:<zeile>` + Zitat | Live | Korr. Schwere |
|---|---|---|---|---|---|
| **070** | Info (Kontrolle) | **BESTAETIGT** (Widerlegung korrekt) | `application/import_service.py:341-344`: `clean_lines = [line for line in csv_text.splitlines() if not line.startswith("#")]` → `:347 csv.DictReader(io.StringIO(clean_text))`. Jede `#`-Zeile wird **vor** dem Reader entfernt; Export-Kommentar `:382 buf.write(f"# terminology_profile: …")` wird nicht als Header gelesen. Die Aussage „WIDERLEGT" ist korrekt. | herm. belegt, live irrelevant | — |
| **071** | Critical | **BESTAETIGT** | `reqif_import_service.py:482-489 `success=True` **hart kodiert**; `:273-287` Docstring „`success: Always True when returned`"; `:296-304 to_dict()` liefert `needs/requirements/relations` **inkl. `errors`** → Antwort listet die Fehler (kein stiller Fehlschlag). Savepoint-Rettung: `:413-414 try: with transaction.atomic(): self._upsert_spec_object(...)`; `:688-703` fängt `IntegrityError` **innerhalb** dieses Savepoints und ruft in `:697` erneut `Artifact.objects.create(...)` auf — ohne Rollback des Savepoints; die Folge-Query stirbt an der abgebrochenen Transaktion und wird von `:429 except Exception` als „internal error" (`:437-441`) verbucht. Mechanik exakt wie in der K-3-Korrektur des Registers. | 915 Fehler live nicht reproduzierbar | — |
| **072** | High | **BESTAETIGT** | `import_service.py:662 artifact = Artifact.objects.create(**artifact_kwargs)` und `:695 obj = model.objects.create(**create_kwargs)` — **keine** Dedupe-/Upsert-Prüfung im gesamten `import_csv`-Pfad (`:179-323`). Neue UUIDs je Lauf ⇒ keine Idempotenz. | „3 Duplikate" live nicht reproduzierbar | — |
| **073** | High | **BESTAETIGT** | Ursache exakt im Code: `views.py:3111` (TraceLink) und `:8369` (Glossary) rufen `self.paginator.paginate_queryset(...)`/`_paginate(...)` **innerhalb** eines `try` mit `except Exception ... _service_error_response(exc, lang)` (`:3249-3252` bzw. `:8372-8374`); die DRF-`NotFound` des Paginators wird dadurch zu **500** (`_service_error_response` → `:253-254` Default `HTTP_500_INTERNAL_SERVER_ERROR`). Kontrast: `WorkspaceViewSet.list` ruft `_paginate` **außerhalb** des `try` (`views.py:5335-5337`) → `NotFound` erreicht DRF → **404**. | 500er live nicht reproduzierbar | — |
| **074** | High | **BESTAETIGT** | 4 nackte Listen: `api_key_views.py:147-158` `return Response(keys, …)`; `user_management_views.py:104-126` `return Response([...])`; `link_type_views.py:56-57` / `:93-97` `_handle(...)` → `Response(payload)`. Keine dieser Klassen erbt von `BaseEntityViewSet` (dessen `pagination_class = StandardPagination`, `views.py:326`) → `page`/`page_size` werden ignoriert. **Fehlzitate:** `api_key_views.py:81` ist Docstring, `user_management_views.py:81` ist die Klassendeklaration — der jeweilige `list`-Body liegt bei `:147` bzw. `:104`. | 200 Items/54 KB live nicht reproduzierbar | — |
| **075** | High | **TEILWEISE** | Struktur belegt: `openapi.py:71-98` definiert `COMMON_ERROR_RESPONSES`; repo-weite Suche findet **keine** produktive Verwendung (nur `openapi.py`-Definition/`__all__` und `rest_api/tests/test_openapi.py`). Nur wenige Views deklarieren überhaupt `responses=` (`auth_views.py:249`, `diagram_canvas_views.py`). Die **exakten Zahlen 432/439** hängen am live generierten Schema (431/439 fehlerfrei = 98,4 %). Ohne Django/DRF lokal und ohne Stack **nicht unabhängig nachzählbar**. | Zahlen NICHT VERIFIZIERBAR | — |
| **076** | High | **TEILWEISE** | `reqif_export_service.py:394-402` setzt explizit `req_if_version="1.2"` im `ReqIFReqIFHeader`; der Export serialisiert über die Fremdbibliothek (`:409 xml = ReqIFUnparser.unparse(bundle)`). Damit widerspricht der **Code** der Behauptung „`reqIFVersion` fehlt" auf Header-Ebene — ob die Bibliothek das Feld tatsächlich emittiert, ist ohne installiertes `reqif`-Paket (lokal `ModuleNotFoundError`) **nicht entscheidbar**. **Fehlzitat:** `:296` ist `_header_id(workspace_id)`, nicht die Header-Konstruktion (die liegt `:392-407`). Die `SPEC-OBJECT-CONTENT`-Behauptung stützt sich auf dieselbe nicht lauffähige Grundlage. | Schema-/XSD-Validierung NICHT VERIFIZIERBAR | — |
| **077** | High | **UEBERZOGEN** | `error_envelope.py:61-67` baut nur `{"error": {code, message, details}}` → **kein** `trace_id`/`request_id` im Body: korrekt. Aber die Korrelation **existiert** als Response-Header: `reqogniloom/middleware.py:85 response["X-Request-ID"] = request_id`. „500er sind für Clients nicht korrelierbar" ist damit zu weit; es fehlt nur die Body-Kopie. | Body-Beleg statisch; Header statisch | **High → Low/Medium** |
| **078** | High | **BESTAETIGT** | Import: `views.py:8265 uploaded_file = request.FILES.get("file")` — nur `multipart/form-data`; kein `@extend_schema(request=…)` an `ReqifImportView` (`:8226-8319`) ⇒ kein `requestBody` im Schema. Export: `views.py:8216-8217 HttpResponse(result.content, content_type=result.media_type)` mit `ExportResult.media_type="application/xml"` (`reqif_export_service.py:414`). Asymmetrie + Schema-Lücke bestätigt. | 415 live nicht reproduzierbar | — |
| **079** | Medium | **TEILWEISE** | `status` wird nie validiert: `_validate_row` (`import_service.py:380-411`) prüft nur Pflichtfelder + Titellänge; `status` läuft durch `_map_status` (`:610`), das nie ablehnt (`:202-228`). Breite Exception-Hülle liefert **immer** `errors=[]`: `:300-314` `except Exception: … ImportResult(..., errors=[], status="rollback")`. Damit ist „Rollenback mit leerer Fehlerliste" code-belegt; der konkrete Auslöser `type`/`level` und der Live-Status 400/201 sind nicht reproduzierbar. | Live-Verhalten NICHT VERIFIZIERBAR | — |
| **080** | Medium | **TEILWEISE** | `import_service.py:346-351` nutzt `csv.DictReader` mit Default-Dialekt (`strict=False`); `csv.Error` wird `:351-354` gefangen, kaputtes Quoting aber nicht erkannt — „still" ist plausibel. **Fehlzitat:** `:196` ist Docstring (`workspace_id: Target workspace UUID.`), nicht Parser-Code. „Restzeile landet im Titel" ist datenabhängig und ohne Stack nicht belegbar. | Live NICHT VERIFIZIERBAR | — |
| **081** | Medium | **TEILWEISE** | CSV-Export ohne Workspace-Tenant-Check: `export_service.py:372-376` setzt nur TenantContext und fetcht per ORM (RLS) → fremder Workspace = leere 200. `ReviewPolicyView.get` (`settings_views.py:579-585`) prüft nur `ctx.has_role(ROLE_ADMIN)`, **keine** Workspace-Zugehörigkeit. CSV-Import dagegen (`views.py:8038-8057` → `import_service.py:529 Workspace.objects.get`) schlägt fehl. Die „drei Geschwister, drei Verhaltensweisen" ist strukturell gestützt; die exakten Live-Codes (200/400/200) nicht reproduzierbar. | Live NICHT VERIFIZIERBAR | — |
| **083** | Medium | **BESTAETIGT** | BOM: `views.py:8018 csv_text = uploaded_file.read().decode("utf-8")` (nicht `utf-8-sig`) ⇒ `\ufeff` bleibt am ersten Headerfeld; kein `csv.Sniffer` (`import_service.py:347`). Beide Fälle enden in `:396 message=f"Required field '{field_name}' is missing or empty."` — genau der behauptete irreführende Text. | Live NICHT VERIFIZIERBAR, Code-Ursache klar | — |
| **085** | Medium | **BESTAETIGT** | MCP-Pfade sind reine Django-`include`s (`reqogniloom/urls.py:51-52 path("api/v1/mcp/", include("mcp_server.urls"))`, `path("mcp/", …)`; `mcp_server/urls.py:18-25`) und damit außerhalb der drf-spectacular-Enumeration. Das Schema schließt sich selbst aus: `settings.py:591 "SERVE_INCLUDE_SCHEMA": False`. Der DRF-API-Root wird von drf-spectacular nicht deklariert. **Einschränkung:** die gezählten „7" enthalten laut Beleg `wp1d-{}` (JSON-404-Catch-all, `urls.py:59`) als **absichtlich** undokumentiert — unbeabsichtigt sind also 6, nicht 7. | Resolver-Zählung live NICHT VERIFIZIERBAR | — |
| **086** | Medium | **BESTAETIGT** | `traceability/pdf_report_generator.py:220 styles = getSampleStyleSheet()` → reportlab-Defaultfonts (Helvetica/-Bold, WinAnsi); im ganzen Modul **kein** `registerFont`/`TTFont`/`UnicodeCIDFont`. Emoji/CJK/Kyrillisch sind damit nicht darstellbar. **Fehlzitat:** Ort ist `traceability/pdf_report_generator.py`, nicht `application/pdf_report_generator`. | Font-Tabelle live nicht reproduzierbar | — |
| **088** | Low | **TEILWEISE** | Die Klammer „(alle `invalid_signature`)" ist **falsch**: `jwt_tokens.py:114-115` liefert für abgelaufene Tokens `AuthenticationFailed("token_expired")`, `:109-113`/`:117-119` für fehlendes `exp`/`nbf` `invalid_token`; unbekannter `user_id` → `authentication.py:218 invalid_token`. Nur `iss`- und `aud`-Fremdheit teilen sich mit falscher Signatur `invalid_signature` (`jwt_tokens.py:121-125`). Die Kernbeobachtung (iss/aud nicht von Signaturfehler unterscheidbar) stimmt, drei der vier genannten Fälle nicht. | Auth-Messung war laut Audit selbst BLOCKED (kein Secret) | — |
| **090** | Low | **BESTAETIGT** | `settings.py:523 "rest_framework.authentication.SessionAuthentication"` in `DEFAULT_AUTHENTICATION_CLASSES` ⇒ drf-spectacular erzeugt das `cookieAuth`-Scheme automatisch; `:593 "SECURITY": [{"BearerAuth": []}]` und `:597-621 APPEND_COMPONENTS` nennen nur `BearerAuth`; keine der Operationen aktiviert SessionAuth explizit ⇒ `cookieAuth` bleibt unreferenziert. | Live-Schema nicht reproduzierbar | — |
| **092** | Low | **TEILWEISE** | `persistence/models.py:1473-1482 uid = models.CharField(..., null=True, blank=True)` mit Help „auto-generated per (workspace, item_type) … (issue #932)". `null=True` erlaubt genau die gemeldete Lücke; kein Backfill-Migrationsfile `*1005*` auffindbar. Die Menge „~888" ist reine Live-Messung. | Mengenangabe NICHT VERIFIZIERBAR | — |
| **093** | Info | **BESTAETIGT** | Beide 404-Texte existieren: `workspace_service.py:187 raise NotFoundError(f"Workspace {workspace_id} not found")` und `rest_api/audit_views.py:219 f"Workspace '{workspace_id}' was not found in the caller's tenant."` → zwei Formulierungen für denselben Sachverhalt. | „6 Endpunkte" live nicht reproduzierbar | — |

---

## 3. Register-Quercheck (`AUDIT_FINDINGS.md` §3/§5)

| Prüfpunkt | Ergebnis |
|---|---|
| **§3-Master-Tabelle 071** | Loc `:483` (hart kodiert), `:688-703`, `:414` — **alle drei korrekt**. Kurztitel nennt korrekt „Antwort listet alle 915 Objektfehler" und die Savepoint-Ursache. ✅ |
| **§5-Detail 071 vs. §3** | **Inkonsistenz:** die §5-Überschrift (`:556`) trägt noch die **alte** Ursache „Ursache `pl_artifact_pkey`-UniqueViolation, weil `SPEC-OBJECT/@IDENTIFIER` die globale `Artifact.id` ist", während der §5-K-3-Vermerk und die §3-Zeile die korrigierte Savepoint-Ursache führen. Die Überschrift wurde bei der K-3-Korrektur nicht mitgezogen. ⚠ |
| **§3-Tabelle 073** | Loc `GET /trace-links/?page=0\|abc\|99999999`, `GET /glossary/?page=0\|abc`; Titel „5 Werte je Endpunkt" — deckungsgleich mit dem Code-Mechanismus (§2). ✅ |
| **§3-Tabelle 074** | Die drei zitierten Zeilen sind Näherungen (s. §2). Substanz korrekt, Zitat unscharf. ⚠ |
| **§3-Tabelle 079** | „ungültiger `status` still akzeptiert … `type`/`level` … 400 `status:"rollback"` mit **leerer** `errors`-Liste" — die leere Liste ist über `import_service.py:311` belegt. ✅ (Teil) |
| **§3-Tabelle 083** | Wortlaut `title is missing or empty` — exakter Code-Text lautet `Required field 'title' is missing or empty.` (`:396`). Sinngemäß korrekt. ✅ |
| **§3-Tabelle 085** | „7 geroutete Pfade fehlen" — Register verschweigt, dass einer davon (404-Catch-all) **absichtlich** fehlt (Beleg `wp1d-schema-drift.md:53`). Zahl damit um 1 zu hoch für „Lücke". ⚠ |
| **§3-Tabelle 086** | Ort `application/pdf_report_generator` — falscher Modulpfad (`traceability/pdf_report_generator.py`). ⚠ |
| **§3-Tabelle 088** | Übernimmt die falsche Klammer „(alle `invalid_signature`)" unverändert aus dem WP-Report. ⚠ |
| **§3-Tabelle 090** | `cookieAuth` — konsistent mit `settings.py:523` + drf-spectacular-Autogen. ✅ |
| **§3-Tabelle 076** | Ort `:296` ist ein Helper, nicht die Header-Konstruktion. ⚠ |
| **Klassifikation 070** | `WIDERLEGT`, Severity auf `Info` herabgesetzt, getrennt von der Finding-Zählung — korrekt gemäß §2.4 PASS-Regel. ✅ |

**Fazit Register:** Keine erfundenen oder verschwundenen Findings; die Schweregrade
sind bis auf `077` (überzogen) vertretbar. Die Schwäche liegt in
**Zitat-Präzision** (074, 076, 080, 086) und in **einer nicht mitgezogenen
Überschrift** (071 §5).

---

## 4. Verdikt-Zählung

**18 Findings** (071–078 High/Critical, 079–093 Stichprobe) + **1 Kontrolle** (070).

| Verdikt | Anzahl | IDs |
|---|---:|---|
| **BESTAETIGT** | 10 | 071, 072, 073, 074, 078, 083, 085, 086, 090, 093 |
| **TEILWEISE** | 7 | 075, 076, 079, 080, 081, 088, 092 |
| **UEBERZOGEN** | 1 | 077 (High → Low/Medium) |
| FALSCH | 0 | — |
| UNTERSCHAETZT | 0 | — |
| NICHT VERIFIKABAR (Verdikt) | 0 | — |
| **Kontrolle 070** | 1 | Widerlegung **korrekt bestätigt** |

**Live-Vorbehalt:** Alle Zahlen-/HTTP-Status-Behauptungen (915 Fehler, 432/439,
200 Items/54 KB, 400/500-Codes, ~888 `uid=null`) sind ohne Docker-Stack
**NICHT VERIFIZIERBAR**. Statisch geprüft wurde jeweils die Code-Ursache; bei
071, 073 und 083 trägt sie das Verdikt auch ohne Live-Lauf.

---

## 5. Key-Verdikte

### 5.1 AUD-2026-09-071 (Critical) — BESTAETIGT, zentrale Ursachenbehauptung trägt

Die K-3-Korrektur des Registers ist am Code **vollständig belegbar** und die
ursprüngliche Ursachenangabe (`pl_artifact_pkey` als *primäre* Ursache) ist
präzise widerlegt:

- **Hart kodiert:** `reqif_import_service.py:482-489` gibt immer
  `success=True` zurück; `:273-287` dokumentiert dies sogar als Vertrag
  („Always True when returned"). Ein vollständig gescheiterter
  Interoperabilitäts-Import wird damit als Erfolg gemeldet — Critical ist
  gerechtfertigt.
- **Kein stiller Fehlschlag:** `to_dict()` (`:296-304`) liefert die
  `errors`-Listen aller drei `ReqifEntityReport`; die Antwort *listet* die
  Fehler. Die Formulierung „still" ist zu streichen (bereits erfolgt).
- **Savepoint-Rettung unwirksam:** `:413-414` öffnet den per-Objekt-Savepoint,
  aber `:688-703` fängt `IntegrityError` **innerhalb** dieses Blocks ab. Django
  rollt einen Savepoint nur zurück, wenn die Exception den Block *verlässt*;
  hier wird sie geschluckt, der Retry in `:697` läuft gegen die abgebrochene
  Transaktion und scheitert. Der `except Exception` in `:429-443` verbucht das
  als „An internal error occurred while importing this object.".

**Restunsicherheit:** Die *Kette* ist statisch zweifelsfrei; ob wirklich 915
Objekte betroffen sind und ob *alle* am PK-Konflikt (nicht an einer anderen
Constraint) starten, ist nur mit Stack/DB nachstellbar.

### 5.2 AUD-2026-09-073 (High) — BESTAETIGT, Mechanik zeilengenau

Der Kontrast `/trace-links/`+`/glossary/` = 500 vs. `/workspaces/` = 404 ist
nicht „Zufall der Daten", sondern Folge der Fehlerbehandlung:

- 500-Pfad: `views.py:3111`/`:8369` paginieren **im** `try`; `except Exception`
  (`:3251-3252`, `:8372-8374`) schluckt die DRF-`NotFound` und
  `_service_error_response` (`:253`) mappt alles Unbekannte auf 500.
- 404-Pfad: `WorkspaceViewSet.list` (`:5325-5337`) paginiert **nach** dem
  `try` → die `NotFound` erreicht den DRF-Handler → 404.

Damit ist der Befund unabhängig von der Live-Messung tragfähig.

### 5.3 AUD-2026-09-074 (High) — BESTAETIGT, aber Zitate unscharf

Alle vier Endpunkte sind echte `APIView`/`ViewSet`-Klassen ohne Pagination.
Die im Register genannten Zeilen treffen jedoch Docstring bzw. Klassendeklaration
statt der `list`-/`get`-Handler (siehe §2). Physisch handelt es sich um **3
Dateien** für **4 Endpunkte** (zwei Routen in `link_type_views.py`) — die
Register-Formulierung „`link_type_views.py:90`" nennt nur einen davon.

### 5.4 AUD-2026-09-077 (High) — UEBERZOGEN (High → Low/Medium)

Kern (kein `request_id` im Fehlerbody) ist korrekt, aber die App liefert
`X-Request-ID` als Response-Header (`middleware.py:85`) und loggt dieselbe ID
(`settings.py:905-924`). Clientseitige Korrelation ist damit bereits möglich;
der Befund ist eine Komfort-/Konsistenzlücke, kein High-Verlust.

### 5.5 AUD-2026-09-070 (Kontrolle) — WIDERLEGUNG KORREKT

`import_service.py:341-344` strippt jede `#`-Zeile vor `csv.DictReader`; der
Export-Kommentar `:382` ist damit kein Header. Die im Register dokumentierte
WIDERLEGUNG ist inhaltlich richtig. **Nebenbefund** (siehe §6): der Strip
erfasst nur Zeilen mit `#` an Spalte 0 und behebt nicht die BOM-Anfälligkeit
aus AUD-083.

---

## 6. NEU-AUDIT-LUECKE (nicht im WP-1d-Register)

1. **NEU — `AUD-083` Wurzelort unvollständig.** Die BOM-Ursache liegt bereits
   in der View, nicht erst im Service: `views.py:8018
   uploaded_file.read().decode("utf-8")`. Ein `decode("utf-8-sig")` würde das
   BOM entfernen. Das Register/der Report nennt nur `import_service` — der
   konkrete Fix-Ort fehlt. (Medium, Konfidenz 95 %.)
2. **NEU — `AUD-088` ist teilweise falsch.** `token_expired` existiert als
   eigener Code (`jwt_tokens.py:114-115`); die Klammer „alle `invalid_signature`"
   ist zu korrigieren. (Low.)
3. **NEU — `AUD-077` überzogen (X-Request-ID-Header).** Korrelation ist über
   den Response-Header gegeben; Body-Kopie ist nice-to-have, nicht High.
   (Schweregrad-Korrektur.)
4. **NEU — `UserViewSet.list` N+1.** `user_management_views.py:117-124` ruft
   `is_tenant_admin(...)` **pro Zeile** auf (im Code selbst so dokumentiert).
   Zusammen mit der fehlenden Pagination (`AUD-074`) skaliert der Endpunkt
   quadratisch mit der Tenant-Nutzzerzahl. Nicht als eigenes Finding im
   WP-1d-Register. (Low/Medium, Konfidenz 90 %.)
5. **NEU — `Success`-Vertrag statt `Success`-Wert.** Bei `AUD-071` ist nicht
   nur der Rückgabewert falsch, sondern der **dokumentierte Vertrag**
   (`reqif_import_service.py:278`). Ein Fix, der nur `:483` ändert, lässt die
   Docstring-Lüge bestehen. (Hinweis zur Maßnahmenplanung.)
6. **Register-Hygiene.** Die §5-Überschrift zu `071` trägt weiter die alte
   PK-Ursache; die K-3-Korrektur ist nur im Fließtext. Sollte vereinheitlicht
   werden, sonst führt ein späterer Leser die beiden Ursachen zusammen.

---

## 7. Verdikt-Zusammenfassung (kompakt)

- **Critical 071:** BESTAETIGT — `success:true` hart kodiert, Fehlerliste
  vorhanden, Savepoint-Rettung nachweislich unwirksam. Kein Widerspruch zur
  K-3-Korrektur; die §5-Überschrift des Registers ist veraltet.
- **High 072/073/074/078:** BESTAETIGT (Code-Ursache klar, Live-Zahlen offen).
  **075:** TEILWEISE (Struktur ja, 432/439 nicht nachzählbar). **076:**
  TEILWEISE (Code setzt `req_if_version="1.2"`; Fremdbibliothek/XSD nicht
  prüfbar, Zitat `:296` falsch). **077:** UEBERZOGEN (High → Low/Medium).
- **Medium-Stichprobe 079/080/081/088:** TEILWEISE. **083/085/086:**
  BESTAETIGT. **Low 090/093:** BESTAETIGT. **Low 092:** TEILWEISE.
- **Kontrolle 070:** Widerlegung korrekt.
- **Keine Phantom-Gegenbeweise.** Wo der Live-Nachweis fehlt, ist der fehlende
  Prüfschritt benannt (Stack + `manage.py spectacular` bzw. installiertes
  `reqif`-Paket).

MERGE_SCORE: 72
