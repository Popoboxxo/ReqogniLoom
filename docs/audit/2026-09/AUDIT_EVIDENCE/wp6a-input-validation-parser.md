---
type: EVIDENCE
scope: wp6a-input-validation-parser
status: success
date: 2026-09-29
author_agent: security-auditor
---

# WP-6a Evidenz — Input-Validation, Mass-Assignment, Parser & Traversal

---

## 1. Mass-Assignment — `setattr()`-Inventar (vollständig)

`rg -e 'setattr\(' backend/ --glob '!**/tests/**' --glob '!**/migrations/**'` → **10 Treffer**, alle geprüft:

| # | Datei:Zeile | Ziel | Quelle des Feldnamens | Allowlist? | Ergebnis |
|---|---|---|---|---|---|
| 1 | `application/artifact_attribute_gateway.py:964` | `target.<attribut>` | serverseitige `AttributeDefinition` | nötig (Definitions-getrieben) | 🟢 |
| 2 | `application/artifact_attribute_gateway.py:981` | `artifact.<attribut>` | dito | dito | 🟢 |
| 3 | `application/artifact_attribute_gateway.py:988` | `artifact.custom_fields` (als Ganzes) | eigener Merge-Pfad | — | 🟢 |
| 4 | `application/memory_settings_service.py:137` | `row.<field>` | `SystemMemorySettingsWriteSerializer` (`memory_rest.py:200-233`) — **9 explizite Felder**, alle `ChoiceField`/`IntegerField(min_value)`/`CharField(max_length)` | ja | 🟢 |
| 5 | `application/memory_settings_service.py:167` | `row.<field> = None` | dieselbe Serializer-Feldliste | ja | 🟢 |
| 6 | `auth_tenancy/services/profile_service.py:55` | `user.<field>` | **harte Allowlist** `_EDITABLE_PROFILE_FIELDS = ("first_name","last_name")` (`:24`) | **ja** | 🟢 |
| 7 | `application/settings_service.py:219` | `obj.<field>` | Serializer-`validated_data` | ja | 🟢 |
| 8 | `persistence/artifact_backing.py:111,119,121` | `<entity>_id`, `<field>` | interner FQN (nicht client-gesteuert) | — | 🟢 |
| 9 | `rest_api/serializers.py:2534` | `instance.<field>` | `validated_data` + `.strip()` | ja | 🟢 |

**Ergebnis: kein Mass-Assignment-Finding.** `is_staff`, `is_superuser`, `is_active`, `tenant` und `password` sind
nirgends über den Profil-Pfad setzbar.

### 1.1 Gefährliche Felder — explizit geprüft

| Feld | Wo | Status |
|---|---|---|
| `is_superuser` / `is_staff` | `persistence/models.py:531-534` | **nicht** im `_EDITABLE_PROFILE_FIELDS`; `UserViewSet` nutzt `HasOperationPermission` + `is_tenant_admin` je Aktion |
| `password` | `User` (`:512-513` Docstring) | kein REST-Pfad schreibt es; nur `set_password` in `UserManager._create_user` |
| `tenant` / `tenant_id` | `TenantManager.create` (`tenancy.py:145-158`) | injiziert nur, **wenn** weder `tenant` noch `tenant_id` im kwargs — explizite Client-Werte werden **nicht** überschrieben |
| `role` / `suspended_at` | `auth_tenancy/models.py:262` `UserRole` | nur über `rest_workspace_members` mit `active_roles_for`-Gate |

---

## 2. Direkte `request.data`-Zugriffe

`rg -e 'request\.data' backend/rest_api/*.py` — Muster:

| Muster | Anzahl Views | Bewertung |
|---|---|---|
| `data = request.data` + Serializer(`data=request.data`) | alle `create`/`partial_update`-Handler | 🟢 `serializer.is_valid()` vor jedem Zugriff |
| `data.get("level")`, `data.get("title")`, `data.get("linked_requirement_id")` | `views.py:973,1349-1350,2784` | 🟢 danach `_validate_patch_payload` bzw. gezielte Typprüfung |
| `body_workspace_id = self.request.data.get("workspace_id")` | `preset_guard.py:232` | 🟢 nur zur Preset-Auflösung, kein Schreibpfad |
| `_auth_or_401` + `request.data.get("content"/"confidence"/"scope")` | `memory/memory_rest.py:876-880, 682-686, 823-827` | 🟢 Service validiert (`MemoryEntryService.write` → `ValidationError`) |
| `request.data.get("backup_id")`, `("confirmation_text")`, `("restore_type")` | `admin_ops/rest.py:499,511,534` | 🟢 UUID-Parsing + Captcha + Choices |
| `request.data.get("username"/"password")` | `auth_views.py:293-294` | 🟢 `isinstance(..., str)`-Gate, gleicher Fehlercode wie falsches Passwort |

**Ergebnis: kein Finding.** Kein unvalidiertes JSON-Feld mit Schreibwirkung gefunden.

---

## 3. Parser-Analyse

### 3.1 Gefährliche Muster — globaler Sweep

```
rg -e 'shell\s*=\s*True' -e '\beval\(' -e '\bexec\(' -e 'pickle\.' -e 'yaml\.load\('
   -e 'os\.system\(' -e 'subprocess\.' -e 'marshal\.' -e '__import__'
   backend/ scripts/ --glob '!**/tests/**' --glob '!**/migrations/**'
```

| Treffer | Datei:Zeile | Bewertung |
|---|---|---|
| `__import__("datetime").timezone.utc` | `mcp_server/tools/audit.py:255` | 🟢 hartkodiertes Modul, kein Client-Input |
| `__import__(module_path, fromlist=[class_name])` | `application/workspace_lookup.py:138` | 🟡 Registry-Lookup über Modellpfad; **kein** Client-Input (interner Dispatch) |
| `subprocess.run(["git","rev-parse","HEAD"], shell=False, timeout=2)` | `reqogniloom/version.py:58-64` | 🟢 feste Argumente, kein `shell=True`, kein User-Input |
| `eval()` | `attribute_definitions/migration_plan.py:144` | 🟢 nur im **Kommentar** („never `eval()`") |
| `shell=True` / `pickle` / `yaml.load` / `os.system` / `marshal` | — | **0 Treffer** |

### 3.2 XXE — ReqIF/XML (mit Lauf verifiziert)

**Pfad:** `rest_api/views.CsvImportView`/`ReqifImportView` → `application/reqif_import_service.py:504-509`

```python
from reqif.parser import ReqIFParser          # :504
bundle = ReqIFParser.parse_from_string(reqif_text)   # :507
```

**Parser-Kette:** `reqif==0.1.0` (`requirements.lock:128`, Range `>=0.1.0,<0.2`) →
`reqif/parsers/__init__.py:96` → `etree.parse(io.BytesIO(bytes(content,"UTF-8")))` — **lxml-Default-Parser**.

Default-Werte (empirisch an der installierten Version geprüft):
`load_dtd=False`, `no_network=True`, `resolve_entities=True`, `huge_tree=False`.

**Versuchsprotokoll** (lokal, offline, gegen eine Canary-Datei außerhalb des Repos;
`%TEMP%\opencode\xxe\secret.txt` mit Zufallsinhalt; keine Netz-/Stack-/Produktivdatenberührung):

| # | Payload | Parser-Verhalten | Befund |
|---|---|---|---|
| A | interne Entity `<!ENTITY a "AAAA">` | `PARSED in 0.00s textlen=4` | interne Expansion **aktiv** |
| B | **externe** Entity `<!ENTITY xxe SYSTEM "file:///…/secret.txt">` + Referenz | `XMLSyntaxError: Entity 'xxe' not defined` | 🟢 **kein XXE-Dateilesen** |
| C | Parameter-Entity `<!ENTITY % p SYSTEM "file:///…"> %p;` | `XMLSyntaxError: PEReference: expecting ';'` | 🟢 abgelehnt |
| D | **externe** DTD-Subset `<!DOCTYPE r SYSTEM "file:///…">` | `PARSED in 0.00s textlen=1` — kein Canary | 🟢 nicht geladen |
| E | **Billion-Laughs**, 12 Ebenen, **392 Byte** Payload | `PARSED in 0.0s textlen=100` — **kein** Fehler, **keine** Expansionsexplosion | 🟢 libxml2-Default begrenzt |

**Ergebnis: XXE-WIDERLEGUNG.** Weder File-Disclosure über externe Entities noch Entity-Expansion-DoS.
Ursache: `load_dtd=False` verwirft die interne Entity-Deklaration für `SYSTEM`-Entities,
`no_network=True` blockiert Netzwerk, und `huge_tree=False` deaktiviert die libxml2-Huge-Tree-Grenze nicht —
die Billion-Laughs-Kette bricht an der Standard-Entity-Sicherheitsgrenze ab.

**Rest-Risiko (LOW, kein Finding):** `reqif==0.1.0` ist eine ungepflegte 0.x-Version. Das ist ein
Wartungs-/Abhängigkeitsrisiko (`SEC-05`), kein XXE-Befund. Empfehlung: Pin auf ≥1.x oder den Parser
selbst auf `etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)`
umstellen, damit die Absicherung nicht von einem Default abhängt.

**Zusätzliche Eindämmung vorhanden:** `_MAX_DOCUMENT_CHARS = 20 * 1024 * 1024` (`reqif_import_service.py:163`),
`_MAX_SPEC_OBJECTS = 5000` (`:160`). Plus Django-Default `DATA_UPLOAD_MAX_MEMORY_SIZE = 2,5 MB` ⇒ die
20-MB-Grenze ist praktisch nie erreichbar; die wirksame Grenze ist Djangos.

### 3.3 CSV-Formel-Injection — **abgesichert**

`application/export_service.py`:

| Zeile | Inhalt |
|---|---|
| 23 | Docstring: „OWASP-documented CSV/formula-injection mitigation. Re-importing that cell …" |
| 54 | `from application.csv_safety import neutralize_csv_formula` |
| 226-250 | `_csv_cell(value)` → delegiert für Strings an `neutralize_csv_formula` |
| 395 | `writer.writerow({k: _csv_cell(v) for k, v in row.items()})` — **jede** Zelle |

⇒ **Negativbefund.** Die OWASP-CSV-Injection-Mitigation ist zentral und flächendeckend eingebunden.

### 3.4 JSON-Deserialisierung

| Pfad | Verfahren | Bewertung |
|---|---|---|
| DRF-Request-Bodies | `rest_framework.request.Request._parse` → `json.loads` | 🟢 kein `pickle`/`yaml` |
| MCP JSON-RPC | `json.loads(request.body)` + `isinstance(frame, dict)`-Gate (`mcp_server/views.py:288-292`, JSON-Array explizit mit 400 abgelehnt) | 🟢 |
| `custom_fields` JSON | `json.loads(cf_attr.value)` + `isinstance(parsed, dict)` (`reqif_import_service.py:587-588`) | 🟢 |
| MCP-SSE `session_id` | Vergleich gegen gespeicherte Sessions | 🟢 |

### 3.5 Template-Injection

Django-Templates (`TEMPLATES` → `django.template.backends.django.DjangoTemplates`) rendern **keine**
Benutzereingaben: die einzigen Templates sind `django.contrib.admin` (→ 500, siehe 5.1) und Fehlerseiten.
Kein Jinja2, kein `Template(user_input).render()`. ⇒ 🟢

Der Live-Beweis ist unangenehm eindeutig: `/admin/login/` → 500 ⇒ das einzige gerenderte Django-Template
ist faktisch tot.

### 3.6 Subprocess

| Aufruf | Datei:Zeile | Bewertung |
|---|---|---|
| `subprocess.run(["git","rev-parse","HEAD"], capture_output=True, timeout=2, check=True)` | `reqogniloom/version.py:58-64` | 🟢 0 Client-Input |
| `scripts/*.sh` | `rg 'shell=True'` in `backend/`+`scripts/` | **0 Treffer** |

### 3.7 Pfad-Traversal

| Zugang | Parameter-Typ | Pfadkonstruktion | Bewertung |
|---|---|---|---|
| `POST /api/v1/admin/restore/` | `backup_id: UUID` (geparst über `_parse_uuid`) | **kein** Pfad im Request | 🟢 `admin_ops/rest.py:499-508` |
| `GET /api/v1/admin/backups/` | UUID-Liste aus DB | — | 🟢 |
| CSV-/ReqIF-Export | DB-IDs, serverseitig benannt | — | 🟢 |
| `reqogniloom/version.py:36` | `Path(__file__).resolve().parent…` — **modulrelativ**, kein Request-Input | 🟢 |
| Theme-/Banner-Palette | UUID-PK, keine Dateinamen | 🟢 |
| `health.py:51` | `connection.cursor()` mit SQL-Literal | 🟢 |

⇒ **Kein Path-Traversal-Finding.**

---

## 4. ReDoS

`rg -e 're\.compile' backend/ --glob '!**/tests/**'` — Regexe liegen in
`auth_tenancy/rest.py:32`, `rest_api/not_found.py`, `sanitization.py`, `persistence/free_text.py`.
Alle sind **lineare Muster** (Zeichenklassen, Anker, keine verschachtelten Quantifier).
Der einzige regex-lastige Pfad ist die Postgres-Volltextsuche (`websearch_to_tsquery`),
die serverseitig gegen Indizes läuft. ⇒ **kein Finding.**

---

## 5. Sonstige Parser-/Dienstbefunde

### 5.1 Django-Admin ⇒ HTTP 500 (Finding 223)

Live:

```
GET /admin/        → 302  (→ /admin/login/?next=/admin/)
GET /admin/login/  → 500
```

Server-Log (read-only via `docker logs --tail`):

```
ValueError: Missing staticfiles manifest entry for 'admin/css/base.css'
  File ".../django/contrib/staticfiles/storage.py", line 601, in stored_name
  … "Internal Server Error: /admin/login/", "status_code": 500
```

Ursache: `ManifestStaticFilesStorage` ist aktiv, `collectstatic` wurde im Image nicht (vollständig) ausgeführt.

**Sicherheitsrelevanz:** `django.contrib.admin` ist in `INSTALLED_APPS` und unter `/admin/` geroutet,
`SessionMiddleware` + `AuthenticationMiddleware` sind aktiv. Sobald der Manifest-Fehler behoben ist,
steht eine **zweite Administrationsfläche** offen, die komplett an der eigenen Audit-Logik vorbeiläuft:

* **kein** DRF-Throttle (Django-Views kennen `DEFAULT_THROTTLE_CLASSES` nicht),
* `ADMIN_ATTEMPTS_BEFORE_LOCKOUT` ist in `settings.py` **nicht gesetzt** ⇒ Django-Default `None` ⇒ Lockout **deaktiviert**,
* kein CSRF-Bypass (Django-Default ist korrekt), aber auch kein Audit-Log, kein MCP/REST-Throttle, keine Session-Rotation.

⇒ **Finding 223 (HIGH):** entweder `/admin/` aus `urls.py` entfernen, **oder** dreifach absichern
(`ADMIN_ATTEMPTS_BEFORE_LOCKOUT=5`, `collectstatic` im Image, `admin`-Rate-Limit).

### 5.2 `Server: uvicorn` (Finding 235)

Live-Response-Header `/api/v1/auth/me/`:
`server: uvicorn`. Django setzt `Server` nicht selbst; ASGI-Server tun es. Kein `X-Powered-By`
( Django unterdrückt das standardmäßig). ⇒ LOW, reines Fingerprinting-Risiko.

### 5.3 Pagination-Cap-Semantik (Finding 234)

Live:

```
GET /api/v1/requirements/?workspace_id=W               → 200,  1 314 B
GET /api/v1/requirements/?workspace_id=W&page_size=1…  → 200,  1 315 B  (auf Workspace ohne Daten)
GET /api/v1/api-keys/?page_size=100000                 → 404
GET /api/v1/users/?page_size=100000                   → 404
GET /api/v1/link-type-defaults/?page_size=100000      → 404
```

`StandardPagination` **deckelt** korrekt (kein 100 000-Row-Response), antwortet bei Über-Cap aber mit
**404** statt 400/422. Semantisch falsch (der Fehler ist ein Validierungs-, kein Routing-Fehler) und
potenziell informations-leakend (404 vs. 400 unterscheidet existierende/unexistierende Kollektionen,
hier aber ohne Nutzen). ⇒ LOW, Finding 234.

### 5.4 `/api/v1/` API-Root (Finding 237)

`/api/v1/` ist auf `rest_framework.routers.APIRootView` gemappt und öffentlich erreichbar (live 200).
Listet die registrierten Router-Routen. Da das OpenAPI-Schema ohnehin öffentlich ist, kein zusätzlicher
Leak — aber die Einstiegspunkt-Aufzählung ist vermeidbar. ⇒ LOW.