---
type: REVIEW
scope: wp-1d-schema-drift
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: OpenAPI-Schema-Drift

**Quellen:**
- `wp1d-openapi-drift.json` — Auswertung
- `wp1d-resolved-routes.json` — 487 aufgelöste `/api/v1/*`-URL-Muster aus dem
  Django-URLResolver (im Container per `django.urls.get_resolver()` erzeugt)
- `wp1d-viewset-apiview-inventory.json` — AST-Inventar der View-Klassen
- `wp1d-reqif-export-A.excerpt.xml`, `wp1d-reqif-export-B.xml` — Round-Trip-Belege

**Schemaquelle:** `GET http://localhost:8001/api/schema/`, HTTP 200,
613 769 Bytes (nicht 599 KB — der Wert schwankt mit der Datenmenge).

---

## 1. Schema-Kennzahlen

| Kennzahl | Wert |
|---|---|
| `openapi` | 3.0.3 |
| `info.version` | 0.1.0 |
| **Paths** | **296** |
| **Operationen** | **439** |
| Component-Schemas | 106 |
| Security-Schemes | 2 (`BearerAuth`, `cookieAuth`) |
| Globales `security` | **nicht gesetzt** (`security: null`) |

## 2. Pfad-/Methoden-Abdeckung — der stärkste Teil des Audits

| Richtung | Anzahl | Bewertung |
|---|---|---|
| Im Schema deklariert, **nicht** im URLResolver | **0** | ✅ |
| Im URLResolver geroutet, **nicht** im Schema | **7** | ⚠ alle einzeln erklärt |
| Methoden-Drift auf gemeinsamen Pfaden | **0** | ✅ (nach Ausfilterung von `OPTIONS`/`HEAD` und der DRF-Format-Suffix-Varianten `…/diff.{format}/?`) |

### Die 7 nicht deklarierten Pfade

| Pfad | Ursache | Bewertung |
|---|---|---|
| `/api/v1` | DRF-`DefaultRouter` liefert einen `APIRootView`; drf-spectacular deklariert ihn nicht | **Low-Bug** — Clients, die das Schema traversieren, sehen die Ressourcenliste nicht |
| `/api/v1/mcp/messages` | `mcp_server.urls` ist nicht Teil der spectacular-Enumeration | **Docs-Drift** |
| `/api/v1/mcp/sse` | dito | **Docs-Drift** |
| `/api/v1/mcp` | Alias ohne Slash (`reqogniloom/urls.py:51`) | **Docs-Drift** |
| `/api/v1/schema` | `SpectacularAPIView` (`rest_api/urls.py:950-954`) | **Docs-Drift** — das Schema beschreibt sich selbst nicht |
| `/api/v1/schema/swagger-ui` | `SpectacularSwaggerView` (`rest_api/urls.py:956-960`) | **Docs-Drift** |
| `/api/v1/{}` | JSON-404-Catch-all `re_path(r"^api/v1/", api_not_found)` (`reqogniloom/urls.py:59`) | ✅ **absichtlich** nicht im Schema |

Der MCP-Eintritt fehlt als Ganzes: `/api/v1/mcp/` und `/mcp/` sind zwei
Registrierungen desselben Include (`reqogniloom/urls.py:51-52`) und in keiner
Form im REST-Schema sichtbar. Wer das Schema als API-Referenz nutzt, findet
den AI-Einstieg nicht.

→ **`AUD-2026-09-085` (Medium, Contract/OpenAPI).**

---

## 3. Fehler-Schemata (`AUD-2026-09-075`, High)

### Histogramm der deklarierten 4xx/5xx je Operation

```
[]                432   ← KEINE Operation deklariert einen Fehlerfall
['401']              1
['404']              3
['400','404']        3
```

| Kennzahl | Wert |
|---|---|
| Operationen mit **irgendeinem** 4xx | **7** von 439 (1,6 %) |
| Operationen mit **irgendeinem** 5xx | **0** von 439 |
| Operationen mit 4xx **inklusive Response-Body** | **0** |
| Histogramm der gesamten Response-Code-Menge | `['200']` 364 · `['204']` 41 · `['201']` 27 · `['200','404']` 3 · `['200','400','404']` 3 · `['200','401']` 1 |

**432 von 439 Operationen (98,4 %) haben keinen einzigen deklarierten
Fehlerfall.** Ein Client, der das Schema als Vertragsgrundlage nimmt, kann
Fehlerbehandlung nicht generieren.

### Die Deklaration existiert, wird aber nicht verwendet

`rest_api/openapi.py:71-98` definiert `COMMON_ERROR_RESPONSES`:

```python
COMMON_ERROR_RESPONSES = {
    400: OpenApiResponse(response=ErrorResponseSerializer, description="Validation error.", examples=[…]),
    401: OpenApiResponse(response=ErrorResponseSerializer, description="Authentication required."),
    403: OpenApiResponse(response=ErrorResponseSerializer, description="RBAC permission denied."),
    404: OpenApiResponse(response=ErrorResponseSerializer, description="Resource not found."),
    500: OpenApiResponse(response=ErrorResponseSerializer, description="Internal server error."),
}
```

`rg "COMMON_ERROR_RESPONSES" backend` findet **nur die Definition** — kein
`extend_schema(responses=COMMON_ERROR_RESPONSES)`, kein `APPEND_RESULTS`, kein
Hook. Die einzige Verwendung von `ErrorResponseSerializer` im ganzen Backend ist
`auth_views.py:281`.

Die Beispiele in der Deklaration sind übrigens auch nicht deckungsgleich mit der
Realität — deklariert ist `{"error": {"code": …, "message": …, "details": []}}`,
`details` ist live ein Array von `{"field","errors"}`-Objekten
(siehe `wp1d-error-format-matrix.md`).

---

## 4. `required`, Typen, Formate

**Ergebnis: keine Abweichung gefunden.** Geprüft wurde:

- Listen-Antworten: das Schema deklariert die Response-Struktur der
  ViewSets über die Serializer; die live gelieferte Hülle
  `{count, next, previous, results, page_size, max_page_size}` ist im Schema
  konsistent abgebildet.
- `page_size`-Parameter: `StandardPagination.get_schema_operation_parameters`
  (`serializers.py:402-418`) setzt `maximum: 100` und einen
  Klammerungs-Hinweistext. Der Wert `100` stimmt mit `max_page_size`
  (`serializers.py:364`) überein — konsistent zwischen Code und Schema.
- `TraceLinkPagination` (`serializers.py:497`, `max_page_size = 500`) — die
  Beschreibung wird vererbt und nennt korrekt 500.

Das ist rare Sorgfalt und sollte als Positivbefund stehen bleiben: die
`page_size`-Dokumentation inklusive `maximum`-Constraint ist besser als in
den meisten vergleichbaren Projekten.

---

## 5. Security-Deklaration

| Kennzahl | Wert |
|---|---|
| Operationen **ohne** `security`-Attribut | **0** von 439 |
| Globales `security` | nicht gesetzt → jede Operation deklariert es selbst |

### Öffentliche Endpunkte

Drei Operationen sind bewusst anonym, verwenden aber nicht die kanonische
OpenAPI-Form `security: []`:

```yaml
security:
  - BearerAuth: []
  - {}
```

| Operation | Deklaration |
|---|---|
| `POST /api/v1/auth/login/` | `[{BearerAuth: []}, {}]` |
| `POST /api/v1/auth/refresh/` | `[{BearerAuth: []}, {}]` |
| `GET /api/v1/public/banners/login/` | `[{BearerAuth: []}, {}]` |

Semantisch korrekt (die leere Anforderung `{}` bedeutet „Auth optional"),
aber nicht idiomatisch — die kanonische Schreibweise für „kein Auth" ist
`security: []`. → **`AUD-2026-09-091` (Low).**

### Toter Security-Scheme

`components.securitySchemes.cookieAuth`:

```yaml
cookieAuth:
  type: apiKey
  in: cookie
  name: sessionid
```

Von **keiner** der 439 Operationen referenziert. Live bestätigt: ein
`Cookie: sessionid=bogus` ergibt `401 AUTHENTICATION_REQUIRED`, und
`django_session` ist im Datenbestand leer (Snapshot `wp1d-row-counts-before.json`
→ `"django_session": 0`). Das Schema deklariert damit einen Auth-Weg, den es
nicht gibt. → **`AUD-2026-09-090` (Low).**

---

## 6. Inventar ViewSets / APIViews (`AUD-2026-09-084`)

Zählmethode und vollständige Klassenliste in
`wp1d-viewset-apiview-inventory.json` (jede Klasse mit `file:line` und
Basis-Kette).

| Kennzahl | Wert |
|---|---|
| Klassen mit `ViewSet` in der Basis-Kette, `backend/rest_api/` | **28** |
| davon abstrakte Basis `BaseEntityViewSet` (`views.py:304`, Docstring „Shared behaviour", nie geroutet) | 1 |
| **Konkrete, geroutete ViewSets** | **27** |
| **APIViews in `backend/rest_api/`** | **76** |
| APIViews in Sub-Apps (`admin_ops` 13, `memory` 17, `auth_tenancy` 3, `reqogniloom` 1) | 34 |
| APIViews backendweit | 110 |
| ViewSets backendweit außerhalb `rest_api/` | 0 |

### Reconciliation

| Quelle | ViewSets | APIViews | Verdikt |
|---|---|---|---|
| `AGENTS.md`, Besondere Patterns | 27 | 67 | ViewSets **exakt korrekt**; APIViews **9 zu niedrig** |
| Audit-Auftrag | 28 | 74 | 28 = inkl. abstrakter `BaseEntityViewSet`; 74 vs. 76 gemessen |
| **Messung** | **28 / 27 konkret** | **76** | — |

`AGENTS.md` nennt zusätzlich „27 ViewSets + 67 APIViews" an zwei Stellen
(Projektbeschreibung und „Besondere Patterns"). Die ViewSet-Zahl stimmt
**zweimal exakt** — wer sie prüft, hält sie für aktuell; die APIView-Zahl ist
aber um 9 daneben, was die Gesamtaussage widerlegt.

Zusatzbeobachtung: `ItemPermissionViewSet`
(`auth_tenancy/rest_item_permission.py:155`) heißt „ViewSet", erbt aber von
`APIView`. Eine reine Namenszählung `class \w+ViewSet` fände 28 Klassen im
Backend, von denen 27 ViewSets und 1 APIView sind — eine weitere Erklärung für
die 28.

---

## Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| `?format=api` / `.json`-Suffix-Varianten | in der Normalisierung als dieselbe Operation behandelt; nicht getrennt gezählt |
| Schema-Validierung gegen die OpenAPI-3.0-Metadaten-Spezifikation | `drf-spectacular`'s eigener Validator wurde nicht ausgeführt (er braucht eine Django-Management-Umgebung mit Schema-Cache); stattdessen Struktur-/Referenz-Auswertung über das geladene YAML |
| `drf-spectacular`-Warnings (`--fail-on-warn`) | Schema ist live ausgeliefert worden, nicht lokal generiert; ein Generierungslauf mit `--fail-on-warn` hätte den Stack nicht verändert, wurde aber nicht durchgeführt |
| MCP-Ingress-Schema | es existiert keins — genau das ist der Befund `AUD-2026-09-085` |
