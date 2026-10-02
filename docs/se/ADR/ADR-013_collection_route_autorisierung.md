---
adr_id: ADR-013
title: "Collection-Route-Regel als einschränkendes Amendment zu ADR-011 §3: List filtert/erfordert Workspace, Create validiert den Ziel-Workspace, 404-vs-403 ohne cross-tenant Existenzleck"
status: accepted
date: "2026-10-02"
last_updated: "2026-10-02"
deciders: [user, senior-developer]
affected_reqs: [REQ-L0-008, REQ-L1-010, REQ-L1-039, REQ-L1-042, REQ-L1-098, REQ-L2-AT-002, REQ-L2-AT-003, REQ-L2-AT-018, REQ-L2-RA-006, REQ-L2-PL-010]
superseded_by: null
---

# ADR-013: Collection-Route-Regel als Amendment zu ADR-011

**Status:** accepted (seit 2026-10-02; Lifecycle-Vermerk am Ende)
**Datum:** 2026-10-02
**Entscheider:** user, senior-developer
**Amendment zu:** `docs/se/ADR/ADR-011_autorisierungsachse_workspace_tenant.md` (`accepted`).
Dieser ADR **präzisiert und beschränkt ADR-011 §3**: Die dort aufgestellte Regel
„`workspace`-skopierte Ressource ohne auflösbaren Ziel-Workspace ⇒ fail-closed 403"
gilt ab ADR-013 **nur noch für Objekt-Routen**. Für Collection-Routen (`list`/`create`)
delegiert der Seam an den Endpunkt (List filtert bzw. erfordert einen Workspace;
Create validiert den Ziel-Workspace), weil die pauschale 403-Regel die Collection-API
blockierte (gemessen 430 Fehler bei Flag ON). ADR-011 §3 wird damit **eingeschränkt,
nicht aufgehoben**; ADR-011 §4 (Coverage-Gate, „eine Deklaration, ein Seam") bleibt
unverändert gültig und wird um das Collection-Gate dieses ADR ergänzt
(`rest_api/tests/test_resource_scope_coverage.py`).
**Betroffene REQs (belegt aus `docs/se/traceability-matrix.md`):**
REQ-L0-008 (Mandantenfähige Isolation), REQ-L1-010 (Rollenbasierte Zugriffskontrolle),
REQ-L1-039 (Granulare Item-Level-Zugriffskontrolle), REQ-L1-042 (Workspace-Lifecycle mit RBAC),
REQ-L1-098 (Data Integrity & Tenant Isolation), REQ-L2-AT-002 (API Key Authentication),
REQ-L2-AT-003 (Role-Based Permission Enforcement), REQ-L2-AT-018 (Item-Level Permission
Enforcement), REQ-L2-RA-006 (RBAC-Enforcement auf API-Ebene), REQ-L2-PL-010 (PostgreSQL RLS).
**Bezug:** Finding `AUD-2026-09-222` / `N2`; SEC-02; Review-Nachbesserung M1–M4 / CODE-1–4; Code:
`backend/auth_tenancy/resource_scope.py`, `backend/auth_tenancy/workspace_scope.py`,
`backend/auth_tenancy/rest.py`, `backend/rest_api/auth_enforcer.py`,
`backend/application/workspace_lookup.py`.

---

## Kontext

ADR-011 hat den zentralen Ressourcen-Scope-Seam eingeführt (`resource_scope.py`) und für
`workspace`-skopierte Ressourcen die Regel „Autorität folgt dem **Zielobjekt**, kein
Rückfall auf die tenant-weite UNION; ohne auflösbaren Ziel-Workspace fail-closed 403"
festgelegt. Der Seam ist über `AUTHZ_WORKSPACE_SCOPE_ENFORCED` gated und war bislang
**default aus** (Hard-Stop). Wird er eingeschaltet, entstehen zwei Fehlerklassen, die
ADR-011 nicht adressiert:

1. **Collection-Routen ohne Zielobjekt.** Bei `list`/`create` gibt es kein einzelnes
   Objekt, aus dem sich ein Ziel-Workspace ableiten ließe. Die pauschale
   403-Regel verweigert damit jede flache Collection-Anfrage — gemessen
   **430 failed / 1756 passed** in `rest_api` mit Flag ON. Das ist kein Befund,
   sondern eine Über-Deckung: Die List-Endpunkte lösen ihren Workspace selbst aus
   URL/Query auf, die Create-Endpunkte aus der validierten Payload.
2. **404 vs. 403.** Ein Seam, der vor der View-Validierung 403 liefert, verschiebt
   nicht existente, malformte oder mandantenfremde Objekte von 404/400 auf 403 und
   macht damit die Existenz eines Objekts (auch über Tenant-Grenzen) beobachtbar.

Hinzu kommt ein Sonderfall: `TraceLinkViewSet` war in ADR-011 als „ownership resolved by
the link service" ohne Objektauflösung deklariert, sodass seine Detail-/Mutationsrouten
mit Flag ON nicht objekt-abgeleitet autorisiert werden konnten.

**Treiber:** SEC-02 soll abgeschlossen und der Seam scharf geschaltet werden
(ADR-011 will Default-Deny), ohne die Collection-API zu brechen und ohne ein
Existenzleck einzuführen.

---

## Alternativen

### Option A: Collection-Routen ebenfalls fail-closed (Status quo) — VERWORFEN

**Beschreibung:** Jede `workspace`-skopierte Route ohne auflösbaren Ziel-Workspace
liefert 403, auch `list`/`create`.

**Abwägung:** Sicher, aber falsch kalibriert. Die 430 Messfehler sind überwiegend
legitime List-/Create-Aufrufe, die ihre Workspace-Auflösung selbst besitzen. Zudem
verschiebt die Vor-Verweigerung 404/400 zu 403. Ein Seam, der die halbe Collection-API
sperrt, wird praktisch abgeschaltet — das Gegenteil des ADR-011-Ziels.

**Risiko:** HOCH — Blockiert die API, erzwingt Flag-off.

### Option B: Collection-Routen ganz aus dem Seam nehmen und dem View überlassen — VERWORFEN

**Beschreibung:** `list`/`create` werden gar nicht mehr geprüft; nur der API-Key-Fence
greift.

**Abwägung:** Löst die 403-Welle, aber der Objekt-Scope geht für Collection-Routen
verloren: Ein `create` in einen fremden Workspace hätte keinen zentralen Fence mehr.
Die Autorisierung wandert zurück in 269 Pfade — genau die Pro-Route-Drift, die ADR-011
strukturell beseitigen wollte.

**Risiko:** MITTEL — Funktioniert heute, öffnet die Klasse für neue Routen.

### Option C: Collection-Regel pro Routen-Form mit Objekt-Vorrang — GEWÄHLT

**Beschreibung:** Der Seam unterscheidet **Collection-Aktionen** (DRF `list`/`create`)
von **Objekt-Routen**. Für Collection-Routen keine pauschale Verweigerung; für
Objekt-Routen objekt-abgeleitete Autorisierung mit der 404-vs-403-Regel.

**Vorteile:** Eine Deklarations-/Durchsetzungsstelle bleibt; die Collection-API wird
nicht gebrochen; Detail-/Mutationsrouten bleiben fail-closed; kein Existenzleck.

**Nachteile:** Der Seam braucht den DRF-Action-Kontext (`view.action`), um die Form
sicher zu erkennen.

**Risiko:** NIEDRIG — ergänzt ADR-011, ohne seine Semantik zu ändern.

---

## Entscheidung

1. **Collection-Aktionen (`list`/`create`) werden nicht pauschal verweigert.**
   Sie werden am zentralen Seam über die DRF-Aktion `view.action ∈ {list, create}`
   erkannt (nicht über den Client). Begründung: Die Collection-Endpunkte besitzen
   ihre Zielauflösung bereits selbst, und der Auth-Layer skopiert die Rollen bereits.
   - **List / Retrieve-many:** Der Endpunkt löst den Workspace aus URL/Query auf
     (`?workspace_id=` bzw. `workspaces/<uuid>/…`); der Auth-Layer filtert die Rollen
     auf genau diesen Workspace. Ist ein Ziel-Workspace **benannt**, erzwingt der Seam
     zusätzlich die Rolle des Aufrufers darin (ein Mitglied von A listet B nicht).
     Ist keiner benannt, greift die eigene Validierung des Endpunkts (in der Regel 400)
     bzw. sein serverseitiger Filter — kein pauschales 403.
   - **Create / Collection:** Der Ziel-Workspace wird **content-type-unabhängig** aus
     URL-Kwargs, Query **und** Body aufgelöst (JSON, `application/x-www-form-urlencoded`
     **und** `multipart/form-data`; SEC-02-Review M1). Ist ein Ziel-Workspace aufgelöst und
     liegt er nicht in den Rollen des Aufrufers, lautet die Antwort **403**
     (`WORKSPACE_MEMBERSHIP_DENIAL`) — der zuvor offene form-encoded Create-Bypass in einen
     fremden Workspace desselben Tenants ist damit geschlossen. Liegt der aufgelöste
     Workspace in einem **anderen Tenant**, wird am Seam nicht verweigert; die
     tenant-geskopte View antwortet 400/404 (kein cross-tenant Existenzleck). Ist **kein**
     Ziel-Workspace auflösbar, erfindet der Seam kein 403: Der Endpunkt validiert ihn
     (`workspace_id` ist in den Create-Serializern Pflicht, sonst 400) oder sein Service
     löst den Workspace aus der Parent-Entität und erzwingt die Mitgliedschaft selbst
     (z. B. `TraceLinkViewSet.create` → `source__workspace_id`; `CommentViewSet.create`
     ist ein Non-Writer und antwortet 405). Diese Trust-Boundaries sind je Registry-Eintrag
     dokumentiert und durch das Collection-Gate abgesichert.
   - Endpunkte **ohne** Objekt- und ohne Collection-Charakter (Import/Export,
     Workspace-Mitglieder, …) bleiben fail-closed: Ist kein Ziel-Workspace im
     Request auflösbar, lautet die Antwort `WORKSPACE_UNRESOLVABLE_DENIAL` (403).
     Damit bleibt die Coverage-Gate-Erwartung aus ADR-011 (§4) erhalten. Ist einer
     aufgelöst, erzwingt der Seam die Mitgliedschaft (Workspace-Rolle **oder**
     System-Admin-Elevation, s. Punkt 6); Ausnahmen mit bewusstem Service-Bootstrap
     tragen einen registrierten `handler_guard`.

2. **Objekt-Routen bleiben objekt-abgeleitet und fail-closed — mit 404-vs-403-Regel
   ohne *cross-tenant* Existenzleck.** Für `retrieve`/`update`/`partial_update`/
   `destroy` und Custom-Detail-Aktionen gilt (drei Fälle):
   - **Objekt aufgelöst, Workspace im aktiven Tenant:** eine aktive Rolle in diesem
     Workspace ist erforderlich — sonst `WORKSPACE_MEMBERSHIP_DENIAL` (403).
   - **Objekt aufgelöst, Workspace *nicht* im aktiven Tenant** (`_workspace_in_active_tenant`
     false): der Seam verweigert **nicht**; die tenant-geskopte View antwortet 404. Ein
     fremd-tenantes Objekt erzeugt also nie ein 403 und bleibt von einem fehlenden
     ununterscheidbar — **kein cross-tenant Existenzleck**. (Test:
     `test_foreign_tenant_object_detail_is_404_not_403`.)
   - **Objekt nicht aufgelöst** (nicht existent, malformte ID): ebenfalls keine
     Seam-Verweigerung; die View antwortet 404/400.
   Ein `tenant`-geskoptes oder `exception`-Ressourcen-Objekt benötigt weiterhin keinen
   Ziel-Workspace. **Residual (deklariert):** *innerhalb* eines Tenants bleibt
   403 (fehlende Rolle) von 404 (fehlendes Objekt) für Mitglieder bewusst
   unterscheidbar. Das ist gewollt (ein Mitglied darf erfahren, dass ein Objekt existiert,
   auf das es keine Rolle hat) und ist **kein** Mandantenleck; es wird hier explizit als
   Residual benannt, damit die ADR-Aussage nicht „kein Existenzleck überhaupt"
   überzeichnet.

3. **Rollen-Wiederverwendung statt Doppelprüfung.** Der Auth-Layer
   (`AuthTenancyAuthentication`) leitet den Ziel-Workspace bei Objekt-Routen bereits
   objekt-abgeleitet ab und skopiert `active_roles` darauf. Der Seam nutzt diese
   geskopten Rollen, wenn `auth_context.workspace_id` dem Ziel-Workspace entspricht.
   Ist der Kontext auf einen **anderen** Workspace geskopiert (Client nannte X, Objekt
   liegt in Y), erfolgt eine echte Membership-Prüfung in Y — der Cross-Workspace-
   Eskalationsfall bleibt geschlossen. Ist der Kontext **gar nicht** workspace-geskopiert
   (direkte Handler-Aufrufe/Boundary-Tests), gilt die bisherige Semantik: die Rollen des
   Kontexts. Für gerouteten Verkehr ist dieser Fall unerreichbar, weil der Auth-Layer
   `workspace_id` vor der Permission-Schicht setzt.

4. **Trace-Link-Objekte werden objekt-abgeleitet autorisiert.** `TraceLink` trägt keine
   eigene `workspace`-Spalte; sein Ziel-Workspace wird über den **Quell-Artefakt**
   (`source__workspace_id`) aufgelöst (`workspace_lookup.ENTITY_SPECS["trace_link"]`).
   Damit sind `retrieve`/`destroy`/`confirm`/`discard` objekt-abgeleitet; die
   Collection-Aktionen (`list`/`create`) folgen Regel 1.

5. **Flag scharf geschaltet.** `AUTHZ_WORKSPACE_SCOPE_ENFORCED` ist ab jetzt
   **default `True`** (`settings.py`). Das Coverage-Gate
   (`rest_api/tests/test_resource_scope_coverage.py`) ist grün; ein Betreiber kann den
   Env-Wert auf `False` setzen, um ein Rollback-Fenster zu fahren.
   `AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED` bleibt unverändert `True`.

6. **Defense-in-Depth auf workspace-benannten Routen wiederhergestellt (CODE-1).**
   Der zuvor ersatzlos gestrichene zentrale Membership-Check für `entity_key=None`-Routen
   ist wieder aktiv: Ist ein Ziel-Workspace aufgelöst und im aktiven Tenant, benötigt der
   Aufrufer **eine Workspace-Rolle oder die System-Admin-Elevation** (TenantRole admin) —
   sonst `WORKSPACE_MEMBERSHIP_DENIAL` (403). Die Elevation ist nötig, damit die bewusst
   `required_operation=None` deklarierten Routen (Workspace-Mitglieder, Banner,
   Memory-Settings) den dokumentierten Tenant-Admin-Override behalten. Die **einzige**
   Route, die die Membership-Entscheidung vollständig an den Service delegiert, ist
   `WorkspaceMembersView`: dort lebt der SEC-05-Bootstrap (rollenloser Self-Assign in
   einem admin-losen Workspace des eigenen Tenants), den ein zentraler Rollen-Check
   fälschlich sperren würde. Diese Ausnahme trägt einen registrierten
   `handler_guard`; das Coverage-Gate hält die Allowlist auf genau diese Menge fest
   (`test_only_expected_routes_defer_membership_to_the_handler`).

7. **Collection-Erkennung und Objektauflösung gehärtet (CODE-2/3/4).** Als Collection
   gilt nur, was `view.action ∈ {list, create}` **und** `view.detail is False` erfüllt
   (CODE-4). Der Objekt-Workspace wird pro Request genau einmal aufgelöst und im
   Objekt-Zweig wiederverwendet (CODE-3); die Tenant-Existenzprüfung teilt sich mit der
   Authentifizierung `workspace_scope.workspace_exists` (CODE-3). Ein Fehler dieser
   Prüfung fällt **fail-closed** aus und wird als `logger.warning` sichtbar (CODE-2);
   nur der Boundary-Fall „kein aktiver Tenant" (handgebaute Unit-Test-Kontexte) bleibt
   die 404-Delegation, weil es nichts zu scopen gibt.

---

## Threat Model (4 Fragen, kompakt)

1. **Was bauen wir?** Einen zentralen, deklarativen Autorisierungs-Seam für
   `workspace`-skopierte REST-Ressourcen. Speicherung/Auth/RLS bleiben unverändert;
   die Achse Workspace wird gegenüber der Tenant-Hülle präzisiert. Betroffen sind
   alle REST-Routen, deren Objekte in einem Workspace leben (Artefakte,
   Requirements, Trace-Links, Workspace-Import/Export, Mitglieder, Banner, …).
2. **Was kann schiefgehen?**
   (a) **Create-Bypass:** ein form-/multipart-Create schmuggelt eine fremde
   `workspace_id` desselben Tenants vorbei (SEC-02-Review M1) und schreibt in einen
   fremden Workspace.
   (b) **Cross-Tenant-Oracle:** ein Seam-403 verrät die Existenz eines Objekts eines
   anderen Tenants.
   (c) **Collection-Drift:** eine neue Collection-Route validiert ihren Ziel-Workspace
   nicht und wird so still fail-open.
   (d) **Elevation-Lockout:** ein zentraler Rollen-Check sperrt den dokumentierten
   Tenant-Admin-/Bootstrap-Pfad.
3. **Was tun wir dagegen?**
   (a) Der Ziel-Workspace wird **content-type-unabhängig** aus URL/Query/Body aufgelöst;
   ein aufgelöster fremder Workspace ⇒ 403; ein Regressionstest weist form-encoded und
   multipart nach, dass **nie** geschrieben wird.
   (b) Fremd-tenante Objekte werden am Seam **nicht** verweigert; die tenant-geskopte
   View antwortet 404 (Test `test_foreign_tenant_object_detail_is_404_not_403`).
   (c) Ein Gate iteriert **jede** `workspace`-skopierte Registry-Klasse und erzwingt, dass
   `list`/`create` gegen einen benannten Ziel-Workspace fencen; die No-Target-Guards sind
   je Eintrag dokumentiert.
   (d) `_has_workspace_authority` akzeptiert Workspace-Rolle **oder** System-Admin;
   `WorkspaceMembersView` trägt den einzigen registrierten `handler_guard` für den
   SEC-05-Bootstrap.
4. **Was sind die Konsequenzen?** Ein Fehler im Seam wirkt auf alle `workspace`-skopierten
   Ressourcen (Blast-Radius, deshalb Coverage-Gate + Feature-Flag-Rollback). Die
   Collection-API bleibt nutzbar (430 → 0 Fehler), Objekt-Routen bleiben fail-closed.
   Verbleibendes Residual: innerhalb eines Tenants ist 403-vs-404 für Mitglieder
   unterscheidbar (deklariert, kein Mandantenleck).

---

**Positiv:**

- SEC-02 ist umgesetzt: Der Seam ist scharf, ohne die Collection-API zu blockieren.
  Nach der Review-Nachbesserung (M1) ist zusätzlich der form-/multipart-Create-Bypass
  geschlossen: ein Create in einen fremden Workspace desselben Tenants wird **403**,
  unabhängig vom Content-Type, und schreibt nachweislich nichts.
- 404-vs-403 ist konsistent und **ohne cross-tenant Existenzleck**: bestehende Objekte
  ohne Rolle 403, fehlende sowie fremd-tenante Objekte 404.
- Eine Durchsetzungsstelle bleibt (ADR-007-Muster); neue Collection-Routen erben die
  Regel automatisch (Collection-Gate), neue Objekt-Routen bleiben fail-closed.
- Der Auth-Layer und der Seam widersprechen sich nicht mehr (Rollen-Wiederverwendung);
  der Membership-Check auf workspace-benannten Routen ist als Defense-in-Depth
  wiederhergestellt, ohne Elevation/Bootstrap zu sperren (CODE-1).

**Negativ:**

- Der Seam ist auf die DRF-Aktion `view.action` **und** `view.detail is False` angewiesen
  (CODE-4); Nicht-DRF-Aufrufer müssen ihre Aktion sauber setzen oder fallen in den
  Objekt-/fail-closed-Zweig.
- Boundary-/Unit-Tests, die eine unklassifizierte Mock-View oder einen synthetischen
  `AuthContext` ohne `workspace_id` verwenden, mussten an die neue Default-Lage
  angepasst werden (klassifizierte View bzw. rollen-tragender Kontext). Die
  Sicherheits-Assertions dieser Tests blieben unverändert.
- **Residual Pro-Route-Drift (M2):** Für Collections ohne *auflösbaren* Ziel-Workspace
  delegiert der Seam an den Endpunkt. Zwei Klassen von Guards fangen das ab: die
  Create-Serializer erfordern `workspace_id` (sonst 400, kein Write) bzw. der Service
  löst den Workspace aus der Parent-Entität (`TraceLinkViewSet`) oder die Route ist ein
  Non-Writer (`CommentViewSet` 405). Ein neuer Collection-Endpunkt ohne diese Guards würde
  erst durch das Collection-Gate auffallen — der Seam allein deckt den No-Target-Fall
  nicht ab. Das Gate (`test_every_workspace_collection_action_is_fenced`) und die
  Registry-Dokumentation sind damit die eigentliche Absicherung, nicht der Seam-Zweig.
- **Residual 403-vs-404 innerhalb eines Tenants (M3):** für Mitglieder bleibt ein
  existierendes Objekt ohne Rolle (403) von einem fehlenden (404) unterscheidbar;
  gewollt, aber explizit benannt.
- Zwei Umgebungsfehler (`mcp_server/tests/test_mcp_api_key_roles.py`, 4 Setup-Errors)
  sind **unabhängig** von diesem ADR: Sie verlangen ein geseedetes `Demo Workspace`
  (`seed_demo`/`bootstrap_admin`), das im Test-Stack fehlt; sie treten mit Flag `False`
  identisch auf.
- Trace-Link-Autorisierung folgt dem Quell-Artefakt; ein Nutzer mit Rolle nur am
  Ziel-Artefakt eines workspace-übergreifenden Links sieht den Link-by-id nicht.

---

## Umsetzungs-Nachweis (nicht Teil der Entscheidung)

- Seam: `backend/auth_tenancy/resource_scope.py` — `_is_collection_action` (action **und**
  `detail is False`, CODE-4), `_enforce_collection_scope` (benannter Ziel-Workspace wird
  gefenct), `_resolve_target_workspaces` (Objektauflösung einmalig, CODE-3),
  `_workspace_in_active_tenant` (fail-closed + `logger.warning`, CODE-2),
  wiederhergestellter Membership-Check mit `_has_workspace_authority`/`_is_tenant_admin`
  (CODE-1), `handler_guard`-Ausnahme für `WorkspaceMembersView`.
- Body-Auflösung: `backend/auth_tenancy/workspace_scope.py` — `_from_body` liest JSON,
  `application/x-www-form-urlencoded` und `multipart/form-data`; geteiltes
  `workspace_exists` (CODE-3), an das `auth_tenancy/rest.py::_workspace_exists` delegiert.
- Objektauflösung: `backend/application/workspace_lookup.py` (`trace_link`).
- Settings: `backend/reqogniloom/settings.py` (`AUTHZ_WORKSPACE_SCOPE_ENFORCED=True`).
- Tests:
  - `backend/rest_api/tests/test_sec02_sec03_workspace_fence.py`:
    `test_form_create_with_foreign_workspace_is_denied_and_never_written` (form-urlencoded
    + multipart, M1), `test_form_create_in_own_workspace_still_succeeds`,
    `test_foreign_tenant_object_detail_is_404_not_403` (M3),
    `test_non_member_denied_on_workspace_named_write_route` (CODE-1, parametrisiert über
    Banner/Review-Policy/Mitglieder), `test_tenant_admin_elevation_still_reaches_workspace_named_write_route`.
  - `backend/rest_api/tests/test_resource_scope_coverage.py`:
    `test_every_workspace_collection_action_is_fenced` (M2-Gate über alle
    `workspace`-skopierten Klassen), `test_collection_action_requires_detail_false`
    (CODE-4), `test_workspace_named_route_without_authority_is_denied` (CODE-1),
    `test_workspace_in_active_tenant_fails_closed_on_error` (CODE-2),
    `test_only_expected_routes_defer_membership_to_the_handler` (CODE-1-Allowlist).
  - `backend/auth_tenancy/tests/test_workspace_scope.py`:
    `test_resolves_form_urlencoded_body_on_write_methods`,
    `test_resolves_multipart_body_on_write_methods`,
    `test_body_ignored_for_unsupported_content_type`.

**Messbelege (exakte Kommandos):**

- Vollsuite (Backend, Test-Overlay):
  `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest -q`
- Fokus-Seam: `pytest -q rest_api/tests/test_sec02_sec03_workspace_fence.py rest_api/tests/test_resource_scope_coverage.py auth_tenancy/tests/test_workspace_scope.py`
- Breiter Regressionslauf: `pytest -q rest_api auth_tenancy admin_ops memory`
- M2-Gate-Selektor: `pytest -q "rest_api/tests/test_resource_scope_coverage.py::test_every_workspace_collection_action_is_fenced"`
- M1-Regression: `pytest -q "rest_api/tests/test_sec02_sec03_workspace_fence.py::test_form_create_with_foreign_workspace_is_denied_and_never_written"`
- M3-Regression: `pytest -q "rest_api/tests/test_sec02_sec03_workspace_fence.py::test_foreign_tenant_object_detail_is_404_not_403"`

### `open_adrs`-Notiz (analog ADR-010/ADR-011/ADR-012)

Das Frontmatter-Feld `open_adrs` existiert repo-weit nicht (0/835 REQs,
`AUD-2026-09-333`; vgl. `ADR-011_autorisierungsachse_workspace_tenant.md:90`,
`ADR-012_backup_wahrheit.md:239-245`). Die REQ↔ADR-Verknüpfung der unter „Betroffene
REQs" genannten Anforderungen kann daher **nicht** maschinell in den REQ-Dateien
eingetragen werden und bleibt Folgeaufgabe (`DOC-01`). Es wird **keine** REQ-Datei und
**keine** Traceability-Matrix geändert.

### Akzeptanz-Präzisierung

Die SEC-02-Akzeptanz in
`docs/audit/2026-09/review/plan/SECURITY_AUTHZ.md` (Zeilen 33-52) wird durch ADR-013
**präzisiert**: Das dortige „fehlende Auflösung ⇒ fail-closed (403)" gilt für
**Objekt-Routen**; für **Collection-Routen** gilt die in diesem ADR definierte,
gemessene Regel (List filtert/erfordert Workspace, Create validiert den
Ziel-Workspace, kein pauschales 403). Der Nachweis ist mit demselben Kommando zu
führen.

*Erstellt durch `senior-developer` am 2026-10-02. Ursprünglich `proposed`; nach
Review-Nachbesserung (M1–M4 / CODE-1–4) und grüner Vollsuite auf `accepted` gesetzt.
Kein Push, kein Tag, kein Merge.*

## Lifecycle-Vermerk

- **2026-10-02 — `proposed` → `accepted`.** Grund: Concept-Review und Code-Review
  (beide CHANGES_REQUESTED) wurden adressiert. Behoben: M1 (content-type-unabhängiger
  Create-Fence, form/multipart, 403 bei fremdem Workspace), M2 (Collection-Gate über
  alle `workspace`-skopierten Klassen + deklariertes Pro-Route-Residual), M3
  (cross-tenant-Existenzleck präzisiert, Fremd-Tenant-Test 404), M4
  (ADR-011-§3-Einschränkung statt „ändert nicht"), CODE-1 (Membership-Defense-in-Depth
  + dokumentierter Bootstrap-`handler_guard`), CODE-2 (fail-closed mit Warnung),
  CODE-3 (geteilte `workspace_exists`, einmalige Objektauflösung), CODE-4
  (`view.detail is False`). Nachweis: Vollsuite
  `10062 passed, 13 skipped, 1 xfailed, 4 errors` (die 4 errors sind die vorbestehenden,
  umgebungsbedingten `mcp_server/tests/test_mcp_api_key_roles.py`-Seed-Fehler, mit Flag
  `False` identisch).
- Nächster formaler Schritt: Re-Review durch `concept-reviewer` (`accepted` bleibt bis
  dahin bestehen, da der Code-Fix und die Suite die Voraussetzung sind).
