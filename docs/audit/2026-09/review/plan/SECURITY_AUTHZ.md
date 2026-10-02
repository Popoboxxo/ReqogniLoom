---
type: PLAN
scope: audit-review-2026-09-sec-authz
status: final
date: 2026-10-01
author_agent: planner
epic: SEC — Security & Authorization
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic SEC — Security & Authorization

> Detailplan. Ort = Produktcode-Anker aus der Review. Akzeptanz ist messbar/observabel.
> **Aufwand:** verbindliche PT-Spannen in `plan/EFFORT_ESTIMATES.md` §1 — die
> `Aufwand: S/M/L`-Angaben hier sind nur Groborientierung. Reihenfolge: SEC-01 ist
> ADR-Blocker für SEC-02/03.

## SEC-01 — ADR Tenant- vs. Workspace-Autorisierungsmodell (P0, W1)

- **Findings:** 222, N2, 240, 081, 043
- **Ort:** `docs/se/ADR/` (neu); Analysebasis `auth_tenancy/workspace_scope.py:114`,
  `auth_tenancy/rest.py:259-277`, `rest_api/auth_enforcer.py:112-120`
- **Zielverhalten:** Entscheidung dokumentiert (Option A/B/C aus `AUDIT_ADR_CANDIDATES.md` #1),
  inkl. `affected_reqs` und Lifecycle-Status; die von der Entscheidung abhängigen Fixes
  referenzieren die ADR.
- **Akzeptanz:** ADR-Datei nach MADR-Minimal vorhanden, ≥2 Alternativen mit Abwägung,
  Status `accepted` oder begründet `proposed`; `open_adrs`-Konvention berücksichtigt.
- **Test:** Review durch `se-critic`/`concept-reviewer`; kein Code-Test.
- **Aufwand:** S · **Risiko/Rollback:** keine (Doku) · **Deps:** — · **ADR:** schreibt (ii)
- **Nicht behauptet:** ADR-Entscheidung selbst — sie ist User-Entscheidung.

## SEC-02 — REST-Workspace-Fence objekt-abgeleitet (P0, W1)

- **Findings:** 222
- **Ort:** `auth_tenancy/workspace_scope.py:114` (`resolve_request_workspace_id`, client-gesteuert
  `:79-86` Query/`:89-111` Body); `auth_tenancy/rest.py:259-277` (sonst tenant-weite UNION);
  `rest_api/auth_enforcer.py:112-120` (liest `workspace_id` nicht);
  `application/requirement_service.py:754-757` (nur tenant-+id-skopiert)
- **Zielverhalten:** Auf mutierenden/lesenden Detailrouten ohne Workspace-Pfad wird der
  Ziel-Workspace **aus dem Zielobjekt** abgeleitet und in die Autorisierung einbezogen;
  fehlende Auflösung ⇒ fail-closed (403), nicht tenant-weite UNION. Cookie-Auth bleibt
  fail-closed (heute bereits `rest.py:273-279`).
- **Akzeptanz:** Ein Bearer/API-Key-Nutzer mit Rolle in WS A, nicht in B, erhält beim
  Zugriff auf ein B-Objekt über eine Detailroute **403** (nicht 200); die Regressionssuite
  `rest_api/tests/test_workspace_scoped_roles.py` um Detailrouten ohne `workspace`-Pfad
  erweitert und grün. Live-Nachtest mit Scoped-User.
  **Präzisiert durch `ADR-013` (2026-10-02):** Das „fehlende Auflösung ⇒ fail-closed (403)"
  gilt für **Objekt-Routen**. Für **Collection-Routen** (`list`/`create`) gilt die in
  ADR-013 definierte Regel (List filtert/erfordert Workspace, Create validiert den
  Ziel-Workspace content-type-unabhängig, kein pauschales 403). Siehe
  `docs/se/ADR/ADR-013_collection_route_autorisierung.md`.
- **Test:** pytest (erweitert) + Live-Nachtest (Scoped-User); Unit-Test für
  Objekt-Fence-Auflösung.
- **Aufwand:** L · **Risiko/Rollback:** Kollateral-Regressionen bei dateilosen Objekten →
  Feature-Flag/Dekorator je Route, revert per Branch. · **Deps:** SEC-01 (ADR ii) ·
  **ADR:** ii

## SEC-03 — API-Key `workspace_ids` + `expires_at` auf REST durchsetzen (P0, W1)

- **Findings:** N2, 240, 035
- **Ort:** `auth_tenancy/models.py:160,162`; `auth_tenancy/services/authentication.py:552-571`
  (`api_key_workspace_ids` gesetzt); Durchsetzung nur `mcp_server/tool_registry.py:1592-1601`;
  0 Treffer in `rest_api/`/`auth_enforcer.py`
- **Zielverhalten:** Dieselbe Fence-Prüfung wie in MCP wird zentral in
  `RbacPermission`/`AuthTenancyAuthentication` verankert, sodass REST sie ebenfalls
  durchsetzt. `expires_at=NULL` (nie ablaufend) wird für Agent-Keys verboten/default-deny;
  `workspace_ids=[]` bedeutet weiter „alle Rollen-Workspaces", aber neue Agent-Keys
  müssen explizit gesetzt werden.
- **Akzeptanz:** Workspace-gefenceter Key (WS A) ⇒ REST-Zugriff auf WS-B-Ressource 403;
  abgelaufener Key ⇒ 401. Test deckt MCP **und** REST mit derselben Fence.
- **Test:** pytest (auth_tenancy + rest_api) + Live-Nachtest (gefenceter Key). 
- **Aufwand:** M · **Risiko/Rollback:** Bestehende Agent-Keys ohne Fence werden strikter →
  Policy-Migrationsfenster; revert über Setting. · **Deps:** SEC-01 · **ADR:** ii

## SEC-04 — Django-Admin-Härtung + Webhook-Secret (P1, W2)

- **Findings:** 223, N1
- **Ort:** `reqogniloom/urls.py:33` (`/admin/` offen), kein Lockout (`rg axes` = 0);
  `application/models.py:178,183` (`workspace_id` UUID ohne FK, `secret` Klartext-CharField);
  `application/admin.py:117-131` (kein `get_queryset`-Tenant-Filter, kein `readonly_fields`)
- **Zielverhalten:** `/admin/` hinter Tenant-/Rollen-Gate + Brute-Force-Schutz
  (django-axes o. ä.); `WebhookSubscriptionAdmin` filtert `get_queryset` tenant-scharf,
  `secret`/`workspace_id` read-only oder maskiert; `as_webhook_subscription` erhält
  Tenant-Zuordnung/RLS.
- **Akzeptanz:** Staff-Session Tenant A sieht/ändert keinen Tenant-B-Datensatz; `secret`
  ist im Admin nicht editierbar/auslesbar; Login-Brute-Force wird limitiert.
- **Test:** pytest (Admin-View-Tenant-Filter), Live-Nachtest Admin-Session.
- **Aufwand:** M · **Risiko/Rollback:** Admin-Nutzbarkeit; revert per Branch. ·
  **Deps:** SEC-01 (ii) · **ADR:** ii (Tenant-Achse)

## SEC-05 — CORS tote Konfiguration (P2, W3)

- **Findings:** 226 · **Ort:** `settings.py:143-160` vs. `INSTALLED_APPS:180-235`/`MIDDLEWARE:240-273`
- **Zielverhalten:** Entweder `django-cors-headers` aktivieren + `CorsMiddleware` eintragen
  oder die tote Konfiguration entfernen (Entscheidung).
- **Akzeptanz:** Cross-Origin-Request verhält sich gemäß Konfiguration; keine toten Settings.
- **Test:** pytest/HTTP-Smoke. · **Aufwand:** S · **Risiko/Rollback:** gering · **Deps:** — · **ADR:** —

## SEC-06 — Proxy-/NUM_PROXIES-Konfiguration (P2, W3)

- **Findings:** 229 · **Ort:** `rest_api/throttling.py:391,404-408` (kein `NUM_PROXIES`/`USE_X_FORWARDED_FOR`)
- **Zielverhalten:** Explizites Proxy-Setting, damit Buckets hinter Reverse-Proxy nicht kollabieren.
- **Akzeptanz:** Mit gesetztem Proxy werden Client-IPs getrennt gezählt. · **Test:** Unit-Throttle-Test.
- **Aufwand:** S · **Risiko/Rollback:** gering · **Deps:** RES-02 (Throttle-Umbau) · **ADR:** —

## SEC-07 — Budget-Fail-open sichtbar machen (P2, W3)

- **Findings:** 231, 063 · **Ort:** `settings.py:764-766`; `llm_adapter/token_tracking.py:233-243`
- **Zielverhalten:** Ohne konfiguriertes Limit kein stilles Fail-open — Health-/Warn-Signal,
  damit der Zustand sichtbar ist (Kopplung an RES-03).
- **Akzeptanz:** Fehlendes/fehlerhaftes Budget erzeugt sichtbaren Status, nicht still `False`.
- **Test:** Unit-Test + Health-Check. · **Aufwand:** S · **Risiko/Rollback:** gering ·
  **Deps:** RES-03 · **ADR:** —

## SEC-08 — CI/CD-Supply-Chain + Staging-Gate (P1, W2)

- **Findings:** 137, 149, 225
- **Ort:** `.github/workflows/docker-publish.yml:26-27,102,168`; `ci.yml:4-7`;
  `deploy/verify-backup-command.sh:90,103` (Credential, siehe SECTRACK-05)
- **Zielverhalten:** Tag-Push baut erst nach CI-Gate; gescanntes Artefakt = gepushtes
  Artefakt (SBOM/Signing/Provenance); Actions SHA-gepinnt; Staging-/Approval-Gate.
- **Akzeptanz:** Publish-Job hat `needs:`/`workflow_run`; alle `uses:` auf Digest gepinnt;
  SBOM-Artefakt vorhanden; kein Build-vs-Push-Doppel.
- **Test:** CI-Lauf (Workflow-Diff), `actionlint`. · **Aufwand:** M · **Risiko/Rollback:**
  CI-Umbau → Branch, reversibel · **Deps:** — · **ADR:** —
