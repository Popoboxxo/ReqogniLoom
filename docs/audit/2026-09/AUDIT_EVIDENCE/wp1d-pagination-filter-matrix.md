---
type: REVIEW
scope: wp-1d-pagination-filter-matrix
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: Pagination- und Filter-Matrix

**Quellen:**
- `wp1d-pagination-matrix.json` → `inventory` (44 Endpunkte) + `stress` (144 Messungen)
- `wp1d-auth-pagination-filter-errors-live.json` → `pagination_inventory`, `filters` (60 Messungen)

**Stack:** `http://localhost:8001`, Tenant A, Workspace
`4eee7ca1-eedd-4a7e-bb14-47e6493cbf88` (888 Requirements, 1176 Artefakte,
1974 TraceLinks, 401 Workspaces).

---

## Teil 1 — Pagination-Inventar (44 List-Endpunkte)

Alle mit `?workspace_id=<WS_A>&page_size=1` aufgerufen.

| Envelope | Anzahl | Endpunkte |
|---|---|---|
| `page` — `{count, next, previous, results, page_size, max_page_size}` | **24** | requirements, artifacts, architecture, testcases, trace-links, tracelinks, workspaces, adrs, risks, goals, main-goals, issues, change-requests, test-runs, diagrams, icds, glossary, needs, workflows, baselines, permission-mismatches, `workspaces/{id}/needs/`, `workspaces/{id}/baselines/`, `workspaces/{id}/reviews/pending/` |
| `custom` — eigenes Shape | **16** | search (`{results, total_count, page, limit}`), metrics, interviews, comments, notifications (`{notifications, unread_count}`), traceability/cycles, attribute-catalog (`{entries}`), link-type-definitions, permission-defaults, attribute-migration/runs, `workspaces/{id}/memory/entries/`, `workspaces/{id}/permissions/`, admin/theme-palettes, prompt-variables (`{…, count}`), admin/rate-limits, system/memory/entries |
| **`BARE-LIST` — nackte Liste** | **4** | **`/api/v1/api-keys/`**, `/api/v1/users/`, `/api/v1/link-type-defaults/`, `workspaces/{id}/link-type-definitions/` |

### Beleg für den Bare-List-Fall

```
GET /api/v1/api-keys/?page_size=1        → 200, 54 452 Bytes, 200 Elemente
GET /api/v1/api-keys/?page_size=100000    → 200, 54 452 Bytes, 200 Elemente
GET /api/v1/api-keys/?page=1              → 200, 54 452 Bytes, 200 Elemente
GET /api/v1/api-keys/?page=0              → 200, 54 452 Bytes, 200 Elemente
GET /api/v1/api-keys/?page=abc            → 200, 54 452 Bytes, 200 Elemente
GET /api/v1/api-keys/?limit=10000&offset=0→ 200, 54 452 Bytes, 200 Elemente
```

`page` und `page_size` werden **vollständig ignoriert** — jede Variante liefert
byte-identisch alle 200 Keys. Verantwortliche Klassen:
`rest_api/api_key_views.py:81` (`ApiKeyViewSet(ViewSet)`),
`rest_api/user_management_views.py:81` (`UserViewSet(ViewSet)`) — beide erben
**nicht** von `BaseEntityViewSet` und setzen daher `pagination_class` nicht.

`/api/v1/metrics/` antwortet mit **782 446 Bytes** in einer einzelnen Response und
ignoriert jede Paging-Angabe.

→ **`AUD-2026-09-074` (High, DoS/Skalierung).**

---

## Teil 2 — `page_size`-Deckelung (dieser Teil ist sauber)

`StandardPagination` (`rest_api/serializers.py:328-470`), gesetzt als
`DEFAULT_PAGINATION_CLASS` in `settings.py:536`, `PAGE_SIZE = 25`
(`settings.py:537`), `max_page_size = 100` (`serializers.py:364`).
`TraceLinkPagination` (`serializers.py:478`, erbt) nutzt `max_page_size = 500`
(`serializers.py:497`).

| `?page_size=` | `/requirements/` (n=888) | `/trace-links/` (n=1974) | `/workspaces/` (n=401) | `/glossary/` (n=6) |
|---|---|---|---|---|
| `1` | 1, `page_size: 1` | 1, `ps: 1` | 1, `ps: 1` | 1, `ps: 1` |
| `100000` | **100 geklemmt** | **500 geklemmt** | **100 geklemmt** | **100 (auf n begrenzt)** |
| `99999999999999999999` | 100 geklemmt, **kein Overflow-Fehler** | 500 geklemmt | 100 geklemmt | 100 |
| `0` | 25 (Default) | 25 | 25 | 25 |
| `-5` | 25 | 25 | 25 | 25 |
| `abc` | 25 | 25 | 25 | 25 |
| `1e400` | 25 | 25 | 25 | 25 |
| `limit=10000&offset=0` | 25 | 25 | 25 | 25 |

Bemerkenswert: `StandardPagination` **echo`t den angewendeten Wert** als
`page_size` und als `max_page_size` in jeder Antwort
(`serializers.py:381-394`) — genau die Designentscheidung, die der
Docstring `serializers.py:346-353` als Grund für `max_page_size` nennt
(„`?page_size=5000` answered 200 with 100 … and no signal"). Das sollte
erhalten bleiben; es ist der Referenzfall für die anderen Endpunkte.

Der `page_size`-Parameter trägt im Schema korrekt `maximum: 100`
(`serializers.py:402-418`).

---

## Teil 3 — Fehlerhafte `page`-Werte → **500** (`AUD-2026-09-073`)

| Endpunkt | `page=0` | `page=-3` | `page=abc` | `page=99999999` | `page=99999999999999999999` | `page=100` (gültig) |
|---|---|---|---|---|---|---|
| `/api/v1/workspaces/` | 404 `Invalid page.` | 404 | 404 | 404 | 404 | ✅ 200 |
| **`/api/v1/trace-links/`** | **500** | **500** | **500** | **500** | **500** | ✅ 200 |
| **`/api/v1/glossary/`** | **500** | **500** | **500** | **500** | **500** | ✅ 200 |
| `/api/v1/requirements/` | 200 | 200 | 200 | 200 | 200 | ✅ |
| `/api/v1/search/` | 400 `page must be >= 1.` | 400 | 400 `page and limit must be integers` | 200 (leer) | 200 (leer) | ✅ |
| `/api/v1/api-keys/` | 200 (ignoriert) | 200 | 200 | 200 | 200 | ✅ |

Antwortkörper der 500er (95 Bytes, konsistent):

```json
{"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred."}}
```

**Einordnung:** DRFs `PageNumberPagination.paginate_queryset` wirft für eine
nicht existierende Seite `NotFound` — deshalb liefert `/api/v1/workspaces/`
korrekt 404. `TraceLinkPagination` erweitert `StandardPagination`
(`serializers.py:478`) und sollte sich identisch verhalten; die 500er kommen
aus dem Listen-ViewSet-Pfad, der den `NotFound` nicht abfängt. Ein
clientseitiger Tippfehler, ein Crawler oder ein `?page=0` aus einem
Frontend-Default erzeugt damit Serverfehler — bei 10 Werten pro Endpunkt
leicht maschinell reproduzierbar.

`/api/v1/search/` verhält sich als **drittes** Schema: eigener `page`/`limit`,
eigene Fehlermeldungen, `?limit=10000` → 400 `limit must be between 1 and 100.`
(cap ✅), aber `?page_size=100000` wird still ignoriert.

---

## Teil 4 — Filter (60 Messungen: 5 Endpunkte × 12 Proben)

### Aggregat

| Probe | Status-Verteilung | Fehlercodes | still ignoriert |
|---|---|---|---|
| `unknown-filter` (`?no_such_filter=1`) | 200 ×5 | – | **5/5** |
| `filter-injection` (`?title=1' OR '1'='1`) | 200 ×5 | – | – |
| `filter-injection-2` (`?ordering=title; DROP TABLE artifacts--`) | 200 ×5 | – | – |
| `filter-injection-3` (`?search=') OR 1=1 --`) | 200 ×5 | – | – |
| `ordering-arbitrary-field` (`?ordering=tenant_id`) | 200 ×5 | – | – |
| `ordering-related-join` (`?ordering=created_by__password`) | 200 ×5 | – | – |
| `ordering-nonexistent` (`?ordering=does_not_exist`) | 400 ×5 | `VALIDATION_ERROR` ×5 | 0/5 |
| `ordering-sql` (`?ordering=id; --`) | 400 ×5 | `VALIDATION_ERROR` ×5 | 0/5 |
| `workspace-id-unknown` (fremde UUID) | 200 ×5, `count: 0` | – | – |
| `workspace-id-not-uuid` (`?workspace_id=abc`) | 400 ×5 | `VALIDATION_ERROR` ×5 | – |
| `filter-unknown-value-type` (`?level=%00binary`) | 200 ×5 | – | – |
| `page-size-string` (`?page_size=1e400`) | 200 ×5, Fallback 25 | – | – |

### Auswertung

**Keine SQL-Injection.** Alle drei Injection-Probes werden als Literal
behandelt und liefern eine normale, gefilterte 200-Antwort. `ordering` läuft
gegen eine Allow-List: `does_not_exist` und `id; --` werden mit
`VALIDATION_ERROR` abgewiesen. Das ist die richtige Konstruktion.

**Unbekannte Filter werden still verworfen** (5/5 Endpunkte, 200 statt 400).
Kein Sicherheitsproblem — RLS greift unabhängig von der Filterauswertung — aber
ein Tippfehler wie `?workpsace_id=` liefert still eine (ungefilterte)
Trefferliste und sieht für den Aufrufer wie Erfolg aus.

**`ordering=tenant_id` und `ordering=created_by__password` werden mit 200
quittiert.** Ob die Sortierung tatsächlich angewendet wird, ist aus dem
Statuscode **nicht** ableitbar — nicht verifiziert (→ BLOCKED). Wäre sie es,
erlaubte das Sortieren über beliebige Modellfelder einen Feld-Orakel-Seitenzähler
(Information über Feldinhalte). Da die Allow-List `does_not_exist` ablehnt,
ist die Wahrscheinlichkeit einer wirksamen freien Feldwahl gering; der Nachweis
steht aus.

**`?workspace_id=<UUID eines fremden Tenants>`** → durchgängig 200 mit
`count: 0`, `results: []`. Kein Fehler, kein Hinweis, ob die ID existiert. Das
ist die RLS/ORM-Filterung, die korrekt arbeitet — siehe
`wp1d-tenant-leak-matrix.md`.
