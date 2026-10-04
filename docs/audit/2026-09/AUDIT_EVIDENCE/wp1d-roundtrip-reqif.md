---
type: REVIEW
scope: wp-1d-roundtrip-reqif
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: ReqIF-1.2-Round-Trip

**Quellen:**
- `wp1d-reqif-export-A.excerpt.xml` — gekürzter Export (Tenant A, 915 SPEC-OBJECT)
- `wp1d-reqif-export-B.xml` — vollständiger Export (Tenant B, 2 SPEC-OBJECT)
- `wp1d-roundtrip-v1.json`, `wp1d-roundtrip-v2.json` — Request/Response + Kennzahlen
- Backend-Log (`docker logs ai-native-reqflow-poc-backend-1`)

**Testrichtung:** Export Tenant A (888 Requirements) → Import Tenant B →
Re-Export Tenant B → Kennzahlenvergleich.

---

## 1. Export (`GET /api/v1/workspaces/{A}/export/reqif/`)

| Kennzahl | Wert |
|---|---|
| Status | 200 |
| Bytes | 2 059 496 |
| `Content-Type` | `application/xml` |
| `Content-Disposition` | `attachment; filename="zahnburste-syseng-demo.reqif"` |
| XML-Deklaration | `<?xml version="1.0" encoding="UTF-8"?>` ✅ |
| `SPEC-OBJECT` gesamt | 915 |
| `SPEC-OBJECT-TYPE` | 2 (`ST-Requirement`, `ST-StakeholderNeed`) |
| `VALUES`-Blöcke | 915 |
| **`SPEC-OBJECT-CONTENT`** | **0** |
| `ATTRIBUTE-VALUE-*`-Elemente | 3 660 |
| `ATTRIBUTE-DEFINITION-STRING` | 8 |
| `DATATYPE-DEFINITION-STRING` | 1 (`DT-String`) |
| `IDENTIFIER`-Attribute gesamt | 2 731 |

### UTF-8 / Sonderzeichen — **korrekt**

Der Export von Tenant B (`wp1d-reqif-export-B.xml`) enthält die
Titelwerte unverändert:

```
THE-VALUE="REQ-001"
THE-VALUE="WP1D-PROBE-B Requirement ÄÖÜ 🚀"
THE-VALUE="probe"
THE-VALUE="draft"
THE-VALUE=""
```

`has_utf8_payload: true` — Umlaute **und** Emoji überstehen den Export.
**Kein Befund.**

---

## 2. ReqIF-1.2-Konformität des Exports (`AUD-2026-09-076`, High)

Geprüft gegen `http://www.omg.org/spec/ReqIF/20110401/reqif.xsd`.

| Merkmal | ReqIF 1.2 verlangt | Export liefert | Konform |
|---|---|---|---|
| `REQ-IF-HEADER/@IDENTIFIER` | Pflicht | `_header-4eee7ca1-eedd-4a7e-bb14-47e6493cbf88` | ✅ |
| **`REQ-IF-HEADER/@reqIFVersion`** | **Pflicht** (`xs:decimal`) | **fehlt** | ❌ |
| **`REQ-IF-HEADER/@THE-VERSION`** | **Pflicht** (`xs:decimal`) | **fehlt** | ❌ |
| `THE-HEADER` | Pflicht | vorhanden | ✅ |
| `CORE-CONTENT` | Pflicht | vorhanden | ✅ |
| `SPECIFICATION` | 1 | 1 | ✅ |
| `SPEC-OBJECT/@VALUES` | Pflicht | 915/915 | ✅ |
| **`SPEC-OBJECT/@SPEC-OBJECT-CONTENT`** | **genau 1, Pflicht** | **0/915** | ❌ |
| `SPEC-OBJECT/@TYPE` | Pflicht | `ST-Requirement` / `ST-StakeholderNeed` | ✅ |
| `ATTRIBUTE-DEFINITION-STRING` | ≥1 je benutztem Attribut | 8 | ✅ |
| `DATATYPE-DEFINITION-STRING` referenziert | muss definiert sein | `DT-String` definiert | ✅ |

Beleg aus dem Excerpt (vollständig, gekürzt):

```xml
<REQ-IF-HEADER IDENTIFIER="_header-4eee7ca1-eedd-4a7e-bb14-47e6493cbf88">
```

— kein `reqIFVersion`, kein `THE-VERSION`. Und ein vollständiges `SPEC-OBJECT`:

```xml
<SPEC-OBJECT IDENTIFIER="_00498935-f75a-411e-bf2e-526d4bd6c53c">
  <VALUES>
    <ATTRIBUTE-VALUE-STRING THE-VALUE="">
      <DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ATTR-UID</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION>
    </ATTRIBUTE-VALUE-STRING>
    <ATTRIBUTE-VALUE-STRING THE-VALUE="Widerstand R1 muss 10kOhm mit 1% Toleranz betragen.">
      <DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ATTR-TITLE</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION>
    </ATTRIBUTE-VALUE-STRING>
    ...
  </VALUES>
  <TYPE><SPEC-OBJECT-TYPE-REF>ST-Requirement</SPEC-OBJECT-TYPE-REF></TYPE>
</SPEC-OBJECT>
```

— kein `SPEC-OBJECT-CONTENT`.

**Konsequenz:** eine DOORS- oder Polarion-Instanz, die das Dokument
validiert, lehnt es ab. Der Import in eine andere ReqIF-Implementierung ist
nicht zuverlässig möglich. Das ist relevant, weil
`backend/rest_api/views.py:8180-8181` die Export-Funktion ausdrücklich mit
„REQ-146 … for DOORS/Polarion interoperability" begründet.

---

## 3. UID / Identität (`AUD-2026-09-092`, Low)

**Die Frage: ist `feat/reqif-uid-identity-1003` gemergt und wirksam?**

| Prüfung | Kommando | Ergebnis |
|---|---|---|
| Branch existiert | `git branch -a --list "*reqif*"` | `feat/reqif-uid-identity-1003` + `remotes/origin/…` — **Branch nicht gemergt** |
| Merge-Commit existiert | `git log --all --grep=reqif` | `a6541783 feat(reqif): separate external ReqIF identity from the local uid (#1003) (#1004)` |
| Merge-Commit in HEAD | `git merge-base --is-ancestor a6541783 HEAD` | **Exit 0 → ist Ancestor von HEAD** ✅ |
| Feature-Commit in HEAD | `git merge-base --is-ancestor 6a69c20a HEAD` | Exit 1 → der Branch-Commit selbst ist es nicht (er wurde per Squash/Merge übernommen) |

→ **Ja, gemergt und wirksam.**

Wirksamkeit live belegt an zwei Stellen:

**a) Neuanlage** — ein frisch über REST erzeugtes Requirement bekommt eine lesbare UID:

```
GET /api/v1/requirements/?workspace_id=<B>&page_size=5
  'WP1D-PROBE-B Requirement ÄÖÜ 🚀' -> uid = 'REQ-001'
```

Der Export schreibt für dieses Artefakt `THE-VALUE="REQ-001"` — der Fallback
`external_uid or need.uid` (`reqif_export_service.py:662`) greift.

**b) Bestandsdaten** — die ~888 vorbestehenden Seed-Artefakte:

```
GET /api/v1/requirements/?workspace_id=<A>&page_size=3
  id = 'fe0d8a68-0268-4f36-88c5-eb3a0f17782e'
  uid = None
```

und im Export entsprechend:

```xml
<ATTRIBUTE-VALUE-STRING THE-VALUE="">
  <DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>ATTR-UID</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION>
</ATTRIBUTE-VALUE-STRING>
```

**Bewertung: Backfill-Lücke, kein Regressionsfehler.** `feat: auto-generate
local readable uid for artifacts (#932) (#1005 PR)` ist gemergt und erzeugt UIDs
für Neuanlagen; für die vor dem Merge geseedeten Datensätze fehlt eine
Migration. Der Effekt ist auf den ReqIF-Round-Trip beschränkt: die Identität
dieser Artefakte geht beim Export verloren.

Zusätzlich gemessen: `external_uid` kommt aus
`reqif_uid_by_id: Dict[UUID, str] = {a["id"]: (a["reqif_uid"] or "") …}`
(`reqif_export_service.py:565-567`). Das ist der für #1003 eingeführte
„externe ReqIF-Ursprung" — bei ReqIF-importierten Artefakten hätte er Vorrang.

---

## 4. Import (`POST /api/v1/workspaces/{B}/import/reqif/`)

### 4a. Content-Type (`AUD-2026-09-078`, High)

| gesendeter `Content-Type` | Status | Antwort |
|---|---|---|
| `application/xml` | **415** | `UNSUPPORTED_MEDIA_TYPE` |
| `text/xml` | **415** | dito |
| `application/octet-stream` | **415** | dito |
| **`multipart/form-data`** (mit `file`-Part) | **200** | Ergebnis unten |

Der **Export** liefert `application/xml`, der **Import** akzeptiert nur
`multipart/form-data`. Der Klartext-Content-Type des Exports ist damit kein
gültiger Import-Input — wer `curl -H 'Content-Type: application/xml'` auf den
Import setzt (die naheliegende Annahme), bekommt 415.

Verschärfend: **das OpenAPI-Schema deklariert für die Import-Operation keinen
`requestBody`.** Aus dem Schema lässt sich der korrekte Aufbau also nicht
ableiten; man findet ihn nur in `backend/rest_api/views.py:8176ff` bzw. im
Quelltext des Service.

### 4b. Ergebnis des Imports (`AUD-2026-09-071`, Critical)

```json
{"success": true, "dry_run": false,
 "needs": {"created": 0, "updated": 0, "skipped": 20,
   "errors": [{"identifier": "_069f1bd2-3adc-403e-b5cb-ae123d4f2c4f",
               "message": "An internal error occurred while importing this object."},
              … 914 weitere …]}}
```

| Kennzahl | Wert |
|---|---|
| HTTP-Status | **200** |
| `success` | **`true`** |
| `created` | 0 |
| `updated` | 0 |
| `skipped` | 915 |
| `errors` | **915** — alle mit derselben Meldung |
| Requirements in B vorher | 1 |
| Requirements in B nachher | **1** |
| `SPEC-OBJECT` im Re-Export von B | **2** (nur Bs eigene 2 Artefakte) |

**`success: true` bei 915 Fehlern.** Das ist dieselbe Signatur wie beim
CSV-Import (`AUD-2026-09-070`): ein grünes Top-Level-Flag, das den
tatsächlichen Ausgang verschleiert.

### 4c. Root Cause (Backend-Log, 915× identisch)

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "pl_artifact_pkey"
  → django.db.utils.IntegrityError
  → File "/app/application/reqif_import_service.py", line 697, in _upsert_spec_object
       artifact = Artifact.objects.create(...)
  → File "/app/application/reqif_import_service.py", line 681, in _upsert_spec_object
  → django.db.transaction.TransactionManagementError:
       An error occurred in the current transaction.
       You can't execute queries until the end of the 'atomic' block.
  → File "/app/application/reqif_import_service.py", line 415, in import_reqif
```

Log-Meldung pro Objekt:
`ReqifImportService: unexpected error importing _069f1bd2-…` (915 Einträge,
alle mit derselben `request_id`).

Zählung über das gesamte Logfenster:

| Exception | Anzahl |
|---|---|
| `psycopg2.errors.UniqueViolation` | 915 |
| `django.db.utils.IntegrityError` | 915 |
| `TransactionManagementError` | 1 830 (2× je Objekt) |
| Verletzte Constraints | **ausschließlich** `pl_artifact_pkey` |

**Mechanik:** `SPEC-OBJECT/@IDENTIFIER` *ist* die `pl_artifact.id` (der Export
schreibt `_00498935-f75a-411e-bf2e-526d4bd6c53c`). Beim Import in Tenant B
kollidieren diese IDs mit den globalen Primärschlüsseln des Quell-Tenants A.
Der Importer fängt den Fehler **pro Objekt** ab (`try` um `_upsert_spec_object`)
und macht mit dem nächsten weiter — aber die Transaktion ist nach dem ersten
`IntegrityError` gebrochen, also scheitert jede weitere Zeile an
`TransactionManagementError`, nicht an der eigentlichen Ursache.

### 4d. Sicherheitsbewertung des Verhaltens

Kein Datenleck: `tenant_id` stammt aus dem Auth-Kontext, nicht aus der Datei.
Der Versuch, eine Zeile mit einer fremden Primärschlüssel-ID anzulegen, wird
vom `pl_artifact_pkey`-Constraint gestoppt, nicht von RLS.

Latentes Risiko, nicht ausnutzbar gemessen: **wäre die PK-ID frei** (z. B. weil
Tenant A das Artefakt gelöscht hat), würde Tenant B ein Artefakt mit einer
historisch zu Tenant A gehörenden UUID anlegen. Das ist kein Tenant-Leak, aber
eine **Identifier-Kollision über Tenant-Grenzen hinweg** — die Identität des
PK-Raums wird vom Import-Client kontrolliert, statt serverseitig vergeben zu
werden.

---

## 5. Idempotenz

| Import | Status | `created` | `updated` | `skipped` | `errors` |
|---|---|---|---|---|---|
| 1. (multipart) | 200 | 0 | 0 | 915 | 915 |
| 2. (`application/xml`) | 415 | – | – | – | – |
| 2. Versuch mit gleichem Medium wie 1. | **200** | **0** | **0** | **915** | **915** |
| Requirements in B nach 1. | 1 | | | | |
| Requirements in B nach 2. | **1** | | | | |

**Idempotent im Sinne von „erzeugt keine Duplikate" — aber aus dem falschen
Grund.** Der Import erkennt nichts wieder; er scheitert an jedem Objekt
neu. `updated` bleibt 0, es gibt keine Wiedererkennung über
`SPEC-OBJECT/@IDENTIFIER`. Ein echter Same-Tenant-Round-Trip
(Export A → Import A → Export A) wurde **nicht** getestet — genau dort wäre
`updated > 0` zu erwarten. Siehe „Nicht geprüft".

---

## 6. UID-Überlappung A ↔ B

| Kennzahl | Wert |
|---|---|
| `IDENTIFIER` in Export A | 2 731 |
| `IDENTIFIER` in Export B (nach Import) | 24 |
| Überlappung | 12 |
| Überlappung (Inhalt) | ausschließlich **Katalog-/Definitions-IDs**: `ATTR-CATEGORY`, `ATTR-CUSTOM-FIELDS`, `ATTR-DESCRIPTION`, `ATTR-MOSCOW-PRIORITY`, `ATTR-STATUS`, `ATTR-TITLE`, `ATTR-UID`, `ATTR-VERIFICATION-METHOD` |

**Null Überlappung bei Objekt-Identifikatoren** — korrekt, denn es wurde kein
Objekt importiert. Die 12 gemeinsamen IDs sind die statischen
`ATTR-*`-Definitionen, die in jedem Dokument gleich heißen; das ist so
vorgesehen und kein Kollisionsproblem.

---

## Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| **Same-Tenant-Round-Trip** (A → A) | der eigentliche „Round-Trip"; der tenant-übergreifende Test traf stattdessen den PK-Kollisions-Pfad. Ein A→A-Import hätte in **Tenant A** 888 fach Daten erzeugt bzw. geändert — für einen Audit ohne Datenmutation nicht vertretbar |
| Import von **ReqIF-Dateien fremder Tools** (DOORS/Polarion) | keine echte `.reqif`-Datei verfügbar; nur der eigene Export als Input |
| `dry_run`-Pfad des Imports | das Feld `dry_run: false` ist in der Antwort belegt; der `dry_run: true`-Pfad wurde nicht aufgerufen (er wäre read-only, wurde aber aus Zeitgründen nicht priorisiert) |
| `SPEC-OBJECT-CONTENT` / Markdown-Export | im Export wird kein Description-Body erzeugt, auch nicht `EXPORT-…`; ob das eine bewusste Entscheidung oder eine unimplementierte ReqIF-1.2-Fähigkeit ist, geht aus dem Code nicht eindeutig hervor |
| Schema-Validierung des Exports gegen dieReqIF-1.2-XSD | kein `xmllint`/Schema-Validator im Stack; die Merkmale wurden manuell gegen die XSD-Regeln geprüft (Tabelle in §2), nicht per Validator belegt |
| `reqIFVersion`-Wert, der bei **korrekter** Angabe entstünde | der Code erzeugt die Datei ohne das Attribut; es gibt keine Konfiguration, die einen Wert setzt |
