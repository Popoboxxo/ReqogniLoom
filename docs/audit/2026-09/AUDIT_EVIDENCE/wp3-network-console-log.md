---
type: REVIEW
scope: wp-3-network-console-log
status: complete
date: 2026-09-29
author_agent: e2e-tester
method: browser_network_requests + browser_console_messages, je Screen nach Navigation
note: "Erwartet" = erwartetes Verhalten laut Implementierung. Keine Credentials/JWT in dieser Datei.
---

# WP-3 — Netzwerk- und Konsolenprotokoll je Screen

Format: `Screen | Endpoint | Status | Auffälligkeit`

## Global (jeder Screen-Load)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| alle | `GET /api/v1/favicon.ico` | **404** | **Auffällig** — `index.html` referenziert kein Favicon; der Browser fordert es trotzdem. Konsolenfehler auf jeder Seite. Produktionskosmetik |
| alle | `GET /api/v1/version/` | 200 | ⚠️ Antwort liefert offenbar keinen Build → Sidebar-Footer zeigt dauerhaft **„Build unknown"** (auf allen 28 Screens) |
| alle | `GET /api/v1/auth/me/` | 200 | ✅ **2× pro Page-Load** (Request #81/#83, #86/#88) — doppelter Session-Restore. Dev-Double-Invoke oder zwei Provider; in Prod zu verifizieren |
| alle | `GET .../link-type-definitions/` | 200 | ✅ |
| alle | `GET /api/v1/admin/banners/global/` | 200 | ✅ **2×** pro Load (global + workspace-Kontext) |
| alle | `GET /api/v1/notifications/?limit=20` | 200 | ✅ |
| alle | `GET /api/v1/users/me/notification-preferences/` | 200 | ✅ |
| alle | `GET /api/v1/admin/theme-palettes/`, `users/me/theme-preference/`, `system/theme-default/` | 200 | ✅ |
| alle | `GET .../banner/` | 204 | ✅ No Content (kein Banner) |

## 1 — `/` Dashboard (BEFUND AUD-2026-09-001)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/` | `GET /api/v1/workspaces/?page_size=100` | 200 | ⚠️ Start des Paginierungs-Sturms |
| `/` | `GET /api/v1/workspaces/?page=2&page_size=100` | 200 | |
| `/` | `GET /api/v1/workspaces/?page=3&page_size=100` | 200 | |
| `/` | `GET /api/v1/workspaces/?page=4&page_size=100` | 200 | |
| `/` | `GET /api/v1/workspaces/?page=5&page_size=100` | 200 | **Kein `page=6`** ⇒ 401 Workspaces sind der vollständige Bestand |
| `/` | `GET /api/v1/requirements/?workspace_id=<uuid>&page_size=100` × **401** | 200 | ❌ **N+1**: ein Call pro Workspace, identische URL-Form 401×. Requests #131–#531 |
| `/` | **Gesamt** | 446×200, 4×204, 4×401 | ❌ **453 Requests für einen einzigen Page-Load** |

## 2 — `/login` (alle Pfade korrekt)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/login` | (Submit leer) | **kein Request** | ✅ Client-Validierung greift, `role="alert"` |
| `/login` | (nur Benutzername) | **kein Request** | ✅ |
| `/login` | `POST /api/v1/auth/login/` (falsch) | **401** | ✅ Erwartet; Klartext-Fehlermeldung in `role="alert"`; Browser-Console loggt den 401 als „Failed to load resource" (Normalfall) |
| `/login` | `POST /api/v1/auth/login/` (korrekt) | **200** | ✅ → Redirect `/` |

## 3 — Auth-Restore mit abgelaufenem Access-Token (BESTAETIGT korrekt)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| Restore | `GET /api/v1/auth/me/` | **401** | ✅ Korrekt — abgelaufener Access-Token |
| Restore | `POST /api/v1/auth/refresh/` | **200** | ✅ Silent Refresh, kein User-Eingriff |
| Restore | `GET /api/v1/auth/me/` | **200** | ✅ Sitzung wiederhergestellt |
| Restore | `GET .../link-type-definitions/` | 401 → 200 | ✅ Zweiter Versuch nach Refresh |

## 4 — `/requirements`

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/requirements` | `GET /api/v1/requirements/?workspace_id=…&page_size=100` | 200 | ✅ genau 1 Call, 2 Treffer |
| `/requirements` | Delete-Dialog geöffnet | **kein Request** | ✅ Bestätigung vor destruktiver Aktion |

## 5 — `/test-runs` (BEFUND AUD-2026-09-014 / -015)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/test-runs` | `GET /api/v1/workspaces/?page_size=100` + `page=2..5` | 200×5 | ⚠️ **Blockiert den Workspace-Kontext** |
| `/test-runs` | `GET /api/v1/test-runs/?workspace_id=…&page_size=100` | 200 | Daten da — UI zeigte trotzdem ~10 s „Laden…" |
| `/test-runs` | `GET /api/v1/users/me/preferences/?workspace_id=…` | 200 | |
| **Ergebnis** | | 0 Fehler | ❌ **Alle Requests 200, UI 10 s tot** ⇒ Reihenfolge-/Rendering-Problem, kein Netzwerkfehler |

## 6 — `/settings` (BEFUND AUD-2026-09-010)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/settings` (6 Tabs) | div. `/api/v1/workspaces/{id}/…` | 200 | ✅ **0 Konsolenfehler, 0 Fehlerantworten** — die i18n-Befunde sind rein präsentational |

## 7 — `/workflows` (BEFUND AUD-2026-09-018)

| Screen | Endpoint | Status | Auffälligkeit |
|---|---|---|---|
| `/workflows` | div. `/api/v1/workflows/…` | 200 | ✅ |
| `/workflows` | **Console-WARNUNG** | — | ⚠️ `React Flow: It seems like you are hiding the attribution. Please only do this when you are subscribed to React Flow Pro` ⇒ **Attribution entfernt ohne Pro-Abo** (Compliance) |

## 8 — Saubere Screens (0 Fehler, 0 Warnungen, nur 200/204)

`/needs` · `/adrs` · `/risks` · `/issues` · `/glossary` · `/architecture` · `/traceability` ·
`/impact` · `/icds` · `/diagrams` · `/testcases` · `/baselines` · `/import` · `/audit` ·
`/goals` · `/metrics` · `/memory` · `/interviews` · `/profile` · `/user-management` ·
`/system-settings` · `/reviews` · `/attributes`

| Screen | Endpoint-Muster | Status | Auffälligkeit |
|---|---|---|---|
| alle obigen | `GET /api/v1/<entity>/?workspace_id=…&page_size=100` | 200 | ✅ |
| alle obigen | `GET /api/v1/users/me/…` | 200 | ✅ |
| alle obigen | **Console** | 0 Errors / 0 Warnings | ✅ |

## Statuscode-Gesamtbilanz (Dashboard-Session, 454 Requests)

| Status | Anzahl | Bewertung |
|---|---|---|
| 200 | 446 | ✅ |
| 204 | 4 | ✅ (leere Banner) |
| 401 | 4 | ✅ (Auth-Restore-Kette, erwartet) |
| 404 | 1 | ⚠️ nur `favicon.ico` |
| **5xx** | **0** | ✅ **Kein Serverfehler auf irgendeinem der 28 Screens** |
