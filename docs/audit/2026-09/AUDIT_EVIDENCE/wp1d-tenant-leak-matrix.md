---
type: REVIEW
scope: wp-1d-tenant-leak-matrix
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: Tenant-Leak-Matrix

**Quellen:**
- `wp1d-tenant-leak-matrix.json` — 120 Rohproben mit Response-Auszügen
- `wp1d-tenant-leak-verification.json` — Verifikation der zwei LEAK-Kandidaten
- `wp1d-authorization-asymmetry.json` — Enumerations-Orakel + Export-Scoping
- `wp1d-row-counts-before.json` / `wp1d-row-counts-after.json` — DB-Zustand

# Ergebnis: **NEIN — 0 Tenant-Leaks in 120 Tests.**

| Richtung | Proben | Leaks | Blockiert (403/404) | Sonstiges |
|---|---|---|---|---|
| A-Token → B-Objekte | 84 | **0** | 41 | 43 (400/500 mit korrekter Hülle, oder 200 mit `count: 0`) |
| B-Token → A-Objekte | 23 | **0** | 14 | 9 |
| B-API-Key → A-Endpunkte | 4 | **0** | 4 | 0 |
| Zusätzlich: A-Token → B-Daten, 10 Endpunkte inkl. aller Exports | 10 | **0** | 6 | 4 (`count: 0` / Echo) |

---

## 1. Wie der zweite Tenant erzeugt wurde (dokumentierter Weg)

Es existiert **kein** REST- und **kein** Management-Pfad, der einen zweiten
Tenant anlegt. Geprüft:

- `POST /api/v1/workspaces/` erzeugt einen Workspace, keinen Tenant.
- `POST /api/v1/users/` (`UserViewSet`, tenant-admin-guarded) erzeugt einen User
  im Tenant des Aufrufers.
- `backend/*/management/commands/` in allen 12 Apps: 28 Kommandos, keiner mit
  Tenant-Provisionierung (`bootstrap_admin`, `seed_demo`, `seed_full_chain`,
  `seed_toothbrush`, `bootstrap_attribute_definitions`, …).

Gewählter Weg — ORM-Skript im Container, tenant-kontext-korrekt:

```python
tenant = Tenant.objects.create(name="WP1D Probe Tenant", slug="wp1d-probe-<hex8>")
set_request_tenant(tenant.id)                      # persistence.middleware
ws   = Workspace.objects.create(..., tenant=tenant, preset={"rigor": "standard"})
user = User.objects.create(username="wp1d_probe_b", password=make_password(...),
                           tenant=tenant, is_active=True)
TenantRole.objects.create(user=user, tenant=tenant, role="admin")
UserRole.objects.create(user=user, workspace=ws, role="admin")
```

**`set_request_tenant` ist zwingend** — ohne sie lehnt PostgreSQL die
Datenanlage ab:

```
django.db.utils.ProgrammingError: new row violates row-level security policy
for table "pl_workspace"
```

Das ist ein **Positivbefund**: die RLS greift auch gegen fehlerhafte
Anwendungs-Code-Pfade, die den Tenant-Kontext vergessen haben. Eine
Organisation, die nur auf ORM-Filtering vertraut, wäre hier durchgegangen.

### Artefakte in Tenant B — über die REST-API erzeugt

Mit dem **B-Token** (`POST`, damit der reale Erzeugungspfad geprüft wird),
`tenant_id` bewusst weggelassen:

| Objekt | Pfad | Status | ID |
|---|---|---|---|
| Requirement (`ÄÖÜ 🚀`) | `/api/v1/requirements/` | 201 | gesetzt |
| ArchitectureElement | `/api/v1/architecture/` | 201 | gesetzt |
| TestCase | `/api/v1/testcases/` | 201 | gesetzt |
| StakeholderNeed | `/api/v1/needs/` | 201 | gesetzt |
| ADR | `/api/v1/adrs/` | 201 | gesetzt |
| Risk | `/api/v1/risks/` | 201 | gesetzt |
| Goal | `/api/v1/goals/` | 201 | gesetzt |
| Issue | `/api/v1/issues/` | 201 | gesetzt |
| GlossaryTerm | `/api/v1/glossary/` | 201 | gesetzt |
| API-Key (`WP1D-PROBE-B key2`) | `/api/v1/api-keys/` | 201 | 1 Key |

**Positiv-Kontrolle:** der erste Fixture-Versuch sendete `tenant_id` im Body —
die Serialisierer lehnten ihn mit `400 {"field": "tenant_id", "errors": ["Unknown field."]}`
ab. `tenant_id` ist nicht client-setzbar. Ebenso `level` bei Requirement:
`"'level' is derived from the Requirement hierarchy and cannot be set (ADR-005)"`.

**Zweiter Positivbefund:** neu erzeugte Artefakte bekommen automatisch eine lesbare
UID (`REQ-001`) — `#932`/`#1005` wirksam.

---

## 2. Die zwei LEAK-Kandidaten — verifiziert, beide Falsch-Positive

Der Matrix-Lauf markierte zwei Zeilen als `LEAK`, weil die Antwort den Marker
`WP1D-PROBE-B` enthielt. Beide wurden nachgeprüft.

### Kandidat 1 — `/api/v1/search/?q=WP1D-PROBE-B&workspace_id=<B>`

| Credential | Status | `total_count` | `results` |
|---|---|---|---|
| **A-Token** | 200 | **0** | `[]` |
| **B-Token** | 200 | **9** | exakt Bs 9 Titel |

Antwort A (vollständig, 73 Bytes):

```json
{"results":[],"total_count":0,"page":1,"limit":20,"query":"WP1D-PROBE-B"}
```

Der Marker im A-Response ist der **echo-Query-String**, kein Treffer. Der
B-Token sieht alle 9 eigenen Objekte. → **Falsch-Positiv**, Isolation korrekt.

### Kandidat 2 — `/api/v1/api-keys/` mit B-Token

| Credential | Status | Keys gesamt | davon Probe-Keys | Beispiel-Keys |
|---|---|---|---|---|
| **A-Token** | 200 | 200 | **0** | `REQ-127-E2E-test-key`, `REQ-134-retrieve-test` |
| **B-Token** | 200 | 1 | 1 (`WP1D-PROBE-B key2`) | eigener Key |

A sieht 200 eigene Keys und **null** Probe-Keys. B sieht genau seinen eigenen
Key. Das ist tenant-korrektes Verhalten — mein `expect` war falsch gesetzt (ich
hatte für tenant-weite Singletons `BLOCKED` erwartet, korrekt wäre
„eigener Tenant sichtbar"). → **Falsch-Positiv**.

---

## 3. A-Token-Sweep gegen Tenant-B-Daten (inkl. aller Exports)

| Endpunkt | Status | `contains_B_marker` | `contains_B_workspace_id` | `contains_B_requirement_id` | Body-Auszug |
|---|---|---|---|---|---|
| `/api/v1/requirements/?workspace_id=B&page_size=100` | 200 | nein | nein | nein | `{"count":0,…,"results":[]}` |
| `/api/v1/artifacts/?workspace_id=B&page_size=100` | 200 | nein | nein | nein | `{"count":0,…,"results":[]}` |
| `/api/v1/search/?q=…&workspace_id=B` | 200 | (Echo) | nein | nein | `{"results":[],"total_count":0,…}` |
| `/api/v1/workspaces/B/export/csv/?entity_type=Requirement` | **200** | nein | nein | nein | `# terminology_profile: default\n` (31 Bytes) |
| `/api/v1/workspaces/B/export/reqif/` | 404 | nein | nur Fehlertext | nein | `Workspace 77c6286e-… not found.` |
| `/api/v1/workspaces/B/reports/pdf/` | 404 | nein | nur Fehlertext | nein | `Workspace 77c6286e-… not found` |
| `/api/v1/workspaces/B/audit/` | 404 | nein | nur Fehlertext | nein | `Workspace '77c6286e-…' was not found in the caller's tenant.` |
| `/api/v1/workspaces/B/members/` | **403** | nein | nein | nein | `You are not a member of this workspace.` |
| `/api/v1/trace-links/?workspace_id=B&page_size=100` | 200 | nein | nein | nein | `{"count":0,…}` |
| `/api/v1/workspaces/B/baselines/` | 404 | nein | nein | nein | `The requested API endpoint does not exist.` (Catch-all) |

**Kein Endpunkt gab Tenant-B-Daten heraus.**

---

## 4. Vollständige Matrix (A → B), nach Bereich

Format: `Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis`

### Detail-Endpunkte (direkte ID-Zugriffe)

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/requirements/{id}/` | GET | B-Req | BLOCKED | 404 `Requirement … not found` | ✅ |
| `/api/v1/artifacts/{id}/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/architecture/{id}/` | GET | B-Arch | BLOCKED | 404 | ✅ |
| `/api/v1/testcases/{id}/` | GET | B-TC | BLOCKED | 404 | ✅ |
| `/api/v1/needs/{id}/` | GET | B-Need | BLOCKED | 404 | ✅ |
| `/api/v1/adrs/{id}/` | GET | B-ADR | BLOCKED | 404 | ✅ |
| `/api/v1/risks/{id}/` | GET | B-Risk | BLOCKED | 404 | ✅ |
| `/api/v1/goals/{id}/` | GET | B-Goal | BLOCKED | 404 | ✅ |
| `/api/v1/issues/{id}/` | GET | B-Issue | BLOCKED | 404 | ✅ |
| `/api/v1/glossary/{id}/` | GET | B-Glos | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/{id}/` | GET | B-WS | BLOCKED | 404 | ✅ |

### Historie / Versionen / Diffs

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/requirements/{id}/history/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/versions/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/workflow-history/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/diff/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/allocation/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/artifacts/{id}/comments/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/artifacts/{id}/memory/` | GET | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/artifacts/{id}/memory/digest/` | GET | B-Req | BLOCKED | 404 | ✅ |

### Listen (mit `workspace_id` auf Tenant B)

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/requirements/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/artifacts/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/architecture/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/testcases/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/workspaces/B/needs/` | GET | B-WS | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/B/baselines/` | GET | B-WS | BLOCKED | 404 | ✅ |
| `/api/v1/baselines/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/test-runs/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/trace-links/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |
| `/api/v1/tracelinks/?workspace_id=B` | GET | B-WS | BLOCKED | 200 `count: 0` | ✅ |

### Suche / Aggregate

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/search/?q=…&workspace_id=B` | GET | B-WS | BLOCKED | 200 `total_count: 0` | ✅ |
| `/api/v1/metrics/?workspace_id=B` | GET | B-WS | BLOCKED | 403/0 Werte | ✅ |
| `/api/v1/requirements/coverage-report/?workspace_id=B` | GET | B-WS | BLOCKED | 0 Zähler | ✅ |
| `/api/v1/traceability/impact/?artifact_id=B-Req` | GET | B-Req | BLOCKED | leer | ✅ |
| `/api/v1/traceability/path/?source_id=B-Req&target_id=B-TC` | GET | B-Req | BLOCKED | leer | ✅ |
| `/api/v1/trace-links/impact/?artifact_id=B-Req` | GET | B-Req | BLOCKED | leer | ✅ |
| `/api/v1/trace-links/path/?…` | GET | B-Req | BLOCKED | leer | ✅ |
| `/api/v1/trace-links/cycles/?workspace_id=B` | GET | B-WS | BLOCKED | leer | ✅ |
| `/api/v1/users/` | GET | B-User | B-User unsichtbar | 12 User, keiner aus B | ✅ |
| `/api/v1/reviews/pending/?workspace_id=B` | GET | B-WS | BLOCKED | 0 | ✅ |
| `/api/v1/workspaces/B/reviews/pending/` | GET | B-WS | BLOCKED | 404 | ✅ |

### Workspace-verwaltende Admin-Flächen

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/workspaces/B/members/` | GET | B-User | BLOCKED | **403** `not a member of this workspace` | ✅ |
| `/api/v1/workspaces/B/permissions/?user_id=…` | GET | B-WS | BLOCKED | 400 `user_id is required` / 0 | ✅ |
| `/api/v1/workspaces/B/permission-definition/` | GET | B-WS | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/B/review-policy/` | GET | B-WS | BLOCKED | **200** `{mode, min_confidence}` | ⚠ `AUD-2026-09-081` |
| `/api/v1/workspaces/B/context-graph-settings/` | GET | B-WS | BLOCKED | 0/leer | ✅ |
| `/api/v1/workspaces/B/memory-settings/` | GET | B-WS | BLOCKED | leer | ✅ |
| `/api/v1/workspaces/B/memory/entries/` | GET | B-WS | BLOCKED | 0 | ✅ |
| `/api/v1/workspaces/B/memory/search/?q=…` | GET | B-WS | BLOCKED | 0 | ✅ |
| `/api/v1/workspaces/B/memory/digest/` | GET | B-WS | BLOCKED | **200** leer | ⚠ kein 403/404 |
| `/api/v1/workspaces/B/link-type-definitions/` | GET | B-WS | BLOCKED | nur globale Defaults | ✅ |
| `/api/v1/workspaces/B/attribute-definitions/requirement/` | GET | B-WS | BLOCKED | kein B-Inhalt | ✅ |
| `/api/v1/workspaces/B/attribute-definitions/requirement/usage/` | GET | B-WS | BLOCKED | 400 `name is required` | ✅ |
| `/api/v1/workspaces/B/audit/` | GET | B-WS | BLOCKED | **404** `in the caller's tenant` | ✅ |
| `/api/v1/workspaces/B/audit/waivers/` | GET | B-WS | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/B/banner/` | GET | B-WS | BLOCKED | **204** | ⚠ kein 403/404 |
| `/api/v1/baselines/scope-preview/?scope=document&workspace_id=B` | GET | B-WS | BLOCKED | 400 `artifact_id is required` | ✅ |

### Tenant-weite Singletons (A sieht A, nie B)

| Endpoint | Methode | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|
| `/api/v1/attribute-catalog/` | GET | nur A | 0 A-Einträge, kein B-Inhalt | ✅ |
| `/api/v1/link-type-defaults/` | GET | nur A | 11 globale Katalog-Einträge | ✅ |
| `/api/v1/workflow-defaults/` | GET | nur A | A-Defaults | ✅ |
| `/api/v1/permission-defaults/` | GET | nur A | A-`permission_json` | ✅ |
| `/api/v1/prompt-templates/` | GET | nur A | kein B-Inhalt | ✅ |
| `/api/v1/llm-settings/` | GET | nur A | kein B-Inhalt | ✅ |
| **`/api/v1/api-keys/`** | GET | nur A | **200 Keys, 0 Probe-Keys** | ✅ |
| `/api/v1/attribute-migration/runs/` | GET | nur A | 0 Runs | ✅ |

### Schreib- und Action-Pfade (kritischste Klasse)

| Endpoint | Methode | Tenant-B-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/requirements/{id}/` | **PATCH** | B-Req | BLOCKED | 404, Titel unverändert | ✅ |
| `/api/v1/requirements/{id}/` | **DELETE** | B-Req | BLOCKED | 404, Objekt existiert noch | ✅ |
| `/api/v1/requirements/{id}/transitions/` | POST | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/reactivate/` | POST | B-Req | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/{id}/derive/` | POST | B-Req | BLOCKED | 400 `title is required` (Validierung vor Autorisierung) | ✅ kein Write |
| `/api/v1/requirements/{id}/decompose-next-level/` | POST | B-Req | BLOCKED | 400 Validierung | ✅ |
| `/api/v1/requirements/{id}/suggest-architecture/` | POST | B-Req | BLOCKED | 400 Validierung | ✅ |
| `/api/v1/workspaces/B/architecture/decompose/` | POST | B-WS | BLOCKED | 400 Validierung | ✅ |
| `/api/v1/workspaces/B/traceability/suggest-links/` | POST | B-WS | BLOCKED | 400 Validierung | ✅ |
| `/api/v1/workspaces/B/context-graph-settings/rebuild/` | POST | B-WS | BLOCKED | kein Effekt | ✅ |
| `/api/v1/memory/entries/{id}/promote/` | POST | — | BLOCKED | 400 `workspace_id is required` | ✅ |
| **`/api/v1/workspaces/B/`** | **DELETE** | B-WS | BLOCKED | 400 `confirmation field is required` | ✅ kein Write |
| `/api/v1/workspaces/B/delete/` | POST | B-WS | BLOCKED | 400 `confirmation field is required` | ✅ |
| `/api/v1/workspaces/B/clone/` | POST | B-WS | BLOCKED | 400 `target_name is required` | ✅ |
| `/api/v1/workspaces/B/close/` | POST | B-WS | BLOCKED | kein Effekt | ✅ |
| `/api/v1/workspaces/B/preset/` | PATCH | B-WS | BLOCKED | 400 Validierung | ✅ |
| **`/api/v1/users/{b_user}/deactivate/`** | POST | B-User | BLOCKED | 404/403, B-User weiterhin `is_active: true` | ✅ |
| `/api/v1/users/{b_user}/tenant-admin/` | DELETE | B-User | BLOCKED | kein Effekt (B-Rolle intakt) | ✅ |
| `/api/v1/workspaces/B/members/{b_user}/suspend/` | POST | B-User | BLOCKED | 400 `role is required` | ✅ |
| `/api/v1/workspaces/B/permission-definition/reset/` | POST | B-WS | BLOCKED | kein Effekt | ✅ |
| `/api/v1/workspaces/B/attribute-definitions/requirement/reset/` | POST | B-WS | BLOCKED | kein Effekt | ✅ |
| `/api/v1/workspaces/B/link-type-definitions/zzz/reset/` | POST | B-WS | BLOCKED | 400 `Link type 'zzz' not found` | ✅ |
| `/api/v1/workspaces/B/audit/remediate/` | POST | B-WS | BLOCKED | 400 Validierung | ✅ |
| `/api/v1/workspaces/B/audit/ai-review/` | POST | B-WS | BLOCKED | 400 Validierung | ✅ |

### Webhooks

| Endpoint | Erwartung | Ist | Ergebnis |
|---|---|---|---|
| `/api/v1/webhooks/` | entweder geroutet oder sauber 404 | **404** (Catch-all, JSON-Envelope) | ⚠ nicht testbar |

Es gibt **keine REST-Route** für Webhook-Subscriptions. Die Tabellen
`as_webhook_subscription` und `as_webhook_delivery_log` existieren
(`snapshot`: beide 0), haben aber keinen REST-Adapter. Ein Tenant-Leak über
Webhook-Zustellung war deshalb **nicht** testbar → BLOCKED.

---

## 5. Reverse-Richtung (B-Token → A-Objekte), 23 Proben

| Endpoint | Methode | Tenant-A-ID | Erwartung | Ist | Ergebnis |
|---|---|---|---|---|---|
| `/api/v1/requirements/{a_req}/` | GET | A-Req | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/A/` | GET | A-WS | BLOCKED | 404 | ✅ |
| `/api/v1/requirements/?page_size=5` | GET | — | BLOCKED | 400 `workspace_id is required` | ✅ |
| `/api/v1/users/` | GET | — | BLOCKED | nur B-eigene 1 | ✅ |
| `/api/v1/workspaces/A/export/csv/` | GET | A-WS | BLOCKED | 400 `entity_type is required` | ✅ |
| `/api/v1/workspaces/A/export/reqif/` | GET | A-WS | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/A/reports/pdf/` | GET | A-WS | BLOCKED | 404 | ✅ |
| `/api/v1/workspaces/A/audit/` | GET | A-WS | BLOCKED | 404 | ✅ |
| `/api/v1/metrics/` | GET | — | BLOCKED | 400 `workspace_id is required` | ✅ |
| **`/api/v1/api-keys/`** | GET | — | nur B | **1 Key = eigener** | ✅ |
| `/api/v1/admin/health/` | GET | — | 403 | 403 | ✅ System-Admin-Gate |
| `/api/v1/admin/backups/` | GET | — | 403 | 403/404 | ✅ |
| `/api/v1/llm-settings/` | GET | — | BLOCKED | 403 | ✅ |
| `/api/v1/prompt-templates/` | GET | — | BLOCKED | 403 | ✅ |
| `/api/v1/attribute-catalog/` | GET | — | BLOCKED | 0 A-Einträge | ✅ |
| `/api/v1/admin/rate-limits/` | GET | — | 403 | 403/404 | ✅ |
| `/api/v1/system/memory/entries/` | GET | — | 403 | 400 `Unknown scope` | ✅ |
| `/api/v1/system/theme-default/` | GET | — | 403 | 403 | ✅ |
| `/api/v1/permission-defaults/` | GET | — | BLOCKED | B-Defaults | ✅ |
| `/api/v1/workflow-defaults/` | GET | — | BLOCKED | B-Defaults | ✅ |
| `/api/v1/requirements/{a_req}/` | **PATCH** | A-Req | BLOCKED | 404, kein Write | ✅ |
| **`/api/v1/workspaces/A/`** | **DELETE** | A-WS | BLOCKED | 400 `confirmation field is required` | ✅ kein Write |
| `/api/v1/users/` | POST | — | BLOCKED | 400 `username, email and password are required` | ✅ |

### B-API-Key gegen Tenant-A-Endpunkte

Der für Tenant B erzeugte Key wurde auf 4 A-Endpunkte verwendet
(X-API-Key-Header):

| Endpoint | Status | Ergebnis |
|---|---|---|
| `/api/v1/requirements/?page_size=1` | 403 | ✅ |
| `/api/v1/workspaces/?page_size=1` | 403 | ✅ |
| `/api/v1/users/` | 403 | ✅ |
| `/api/v1/admin/health/` | 403 | ✅ |

---

## 6. Authorisierungs-Asymmetrien (`AUD-2026-09-081`, Medium)

Kein Datenleck, aber drei Endpunkt-Familien reagieren auf eine
fremde/nicht existierende Workspace-ID unterschiedlich:

| Endpunkt | Workspace B existiert (fremd) | Workspace **existiert nicht** | differenziert? |
|---|---|---|---|
| `/workspaces/{ws}/export/reqif/` | **404** `Workspace <id> not found.` | **404** identisch | nein ✅ |
| `/workspaces/{ws}/reports/pdf/` | **404** `Workspace <id> not found` | **404** identisch | nein ✅ |
| `/workspaces/{ws}/audit/` | **404** `Workspace '<id>' was not found in the caller's tenant.` | **404** identisch | nein ✅ |
| **`/workspaces/{ws}/export/csv/`** | **200** (31 Bytes, nur Header) | **200** | ⚠ **keine Prüfung** |
| **`/workspaces/{ws}/import/csv/`** | **400** `validation_error` | 400 | ⚠ Validierung statt 403/404 |
| **`/workspaces/{ws}/review-policy/`** | **200** `{mode, min_confidence}` | **200** | ⚠ Defaults für jede ID |
| `/workspaces/{ws}/memory/digest/` | **200** leer | **200** | ⚠ |
| `/workspaces/{ws}/banner/` | **204** | **204** | ⚠ |

**Warum das unkritisch ist:** bei `export/csv` greift die RLS und filtert alle
Zeilen heraus, die nicht zum Tenant des Aufrufers gehören — der Endpunkt
liefert deshalb nur die Kopfzeile. Bei `review-policy` dokumentiert
`application/settings_service.py:672` ausdrücklich „A read never creates a row",
und der gelesene Wert ist der tenant-globale Default des **Aufrufers**.

**Warum es trotzdem ein Befund ist:** drei Geschwister-Export-Pfade
(`csv`, `reqif`, `pdf`) verhalten sich auf dieselbe Eingabe
fundamental verschieden. Ein Client kann sich nicht darauf verlassen, dass
eine fremde Workspace-ID abgelehnt wird — er muss damit rechnen, ein
leeres, erfolgreiches Ergebnis zu bekommen.

### Enumerations-Orakel (Info, `AUD-2026-09-093`)

Kein Endpunkt unterscheidet „gehört fremdem Tenant" von „existiert nicht" —
**das ist die sichere Variante.** Nur `/workspaces/{ws}/audit/` sagt im Text
`in the caller's tenant`, was eine *stärkere* Zusage ist, ohne die
Existenz zu verraten (der Workspace existiert in einem anderen Tenant, aber
nicht in diesem). Ich habe **keinen** Endpunkt gefunden, über den sich
Tenant-UUIDs vollständig enumerieren ließen; der UUID-Raum macht das ohnehin
praktisch unmöglich. Klassifiziert als **Info**.

Zwei 404-Texte unterscheiden sich nur kosmetisch
(`Workspace <id> not found.` vs. `Workspace <id> not found` — mit/ohne Punkt,
und `reqif`/`pdf` ohne Anführungszeichen um die ID, `audit` mit). Für einen
Client, der auf Strings prüft, ist das eine Stolperfalle; semantisch sind alle
drei gleich.

---

## 7. Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| Webhook-Zustellung | keine REST-Route vorhanden (`/api/v1/webhooks/` → 404 Catch-all); Tabellen existieren, Adapter nicht |
| WebSocket/Streaming-Kanäle | MCP-SSE ist separat in WP-1a auditiert |
| `?page_size`-Übergriffe auf Tenant-B-Daten | nachweislich wirkungslos (Zeilen 3 des Sweeps) |
| Reihenfolge-Isolation bei Verbindungs-Pooling | `persistence/middleware.py:65-66` nutzt **session-scoped** `SET app.current_tenant` (bewusst, dokumentiert in `middleware.py:14-18`, `:60-61`). Ob bei einem unerwarteten Abbruch zwischen `set` und `clear` ein Folge-Request auf einer gepoolten Connection mit veraltetem GUC starten kann, ist ein Concurrency-Befund und **nicht** live reproduzierbar, ohne den geteilten Stack zu gefährden |
| API-Key-Scope-Überprüfung über Tenants hinweg | Klartext-Key von B nicht re-obtainable; `AUD-2026-09-035` bleibt offen |
| Row-Level-Security direkt auf DB-Ebene gegen die REST-Routen | RLS wurde bei der Provisionierung *indirekt* belegt (`pl_workspace`-INSERT verweigert); ein dedizierter SELECT-Test gegen eine der 71 Policies wurde nicht gefahren |
