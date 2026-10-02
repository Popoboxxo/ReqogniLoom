---
adr_id: ADR-013
title: "Collection-Route-Regel als Amendment zu ADR-011: List filtert, Create leitet Ziel-Workspace aus der Payload ab, 404-vs-403 ohne Existenzleck"
status: proposed
date: "2026-10-02"
deciders: [user, senior-developer]
affected_reqs: [REQ-L0-008, REQ-L1-010, REQ-L1-039, REQ-L1-042, REQ-L1-098, REQ-L2-AT-002, REQ-L2-AT-003, REQ-L2-AT-018, REQ-L2-RA-006, REQ-L2-PL-010]
superseded_by: null
---

# ADR-013: Collection-Route-Regel als Amendment zu ADR-011

**Status:** proposed
**Datum:** 2026-10-02
**Entscheider:** user, senior-developer
**Amendment zu:** `docs/se/ADR/ADR-011_autorisierungsachse_workspace_tenant.md` (`accepted`) —
dieser ADR ändert ADR-011 nicht, er präzisiert dessen Entscheidungspunkte 2–4 für Routen
**ohne einzelnes Zielobjekt**.
**Betroffene REQs (belegt aus `docs/se/traceability-matrix.md`):**
REQ-L0-008 (Mandantenfähige Isolation), REQ-L1-010 (Rollenbasierte Zugriffskontrolle),
REQ-L1-039 (Granulare Item-Level-Zugriffskontrolle), REQ-L1-042 (Workspace-Lifecycle mit RBAC),
REQ-L1-098 (Data Integrity & Tenant Isolation), REQ-L2-AT-002 (API Key Authentication),
REQ-L2-AT-003 (Role-Based Permission Enforcement), REQ-L2-AT-018 (Item-Level Permission
Enforcement), REQ-L2-RA-006 (RBAC-Enforcement auf API-Ebene), REQ-L2-PL-010 (PostgreSQL RLS).
**Bezug:** Finding `AUD-2026-09-222` / `N2`; SEC-02; Code:
`backend/auth_tenancy/resource_scope.py`, `backend/auth_tenancy/rest.py`,
`backend/rest_api/auth_enforcer.py`, `backend/application/workspace_lookup.py`.

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
     auf genau diesen Workspace. Ist keiner benannt, greift die eigene Validierung
     des Endpunkts (in der Regel 400) bzw. sein serverseitiger Filter — kein
     pauschales 403. Ein Workspace mit Rollen sieht nur dessen Objekte.
   - **Create / Collection:** Der Ziel-Workspace wird aus dem **validierten Payload**
     `workspace_id` abgeleitet (bei verschachtelten Routen aus dem URL-Kwarg); der
     Auth-Layer skopiert die Rollen darauf. Fehlt er, antwortet die View-eigene
     Validierung mit 400/404. Der Seam erfindet dort kein 403.
   - Endpunkte **ohne** Objekt- und ohne Collection-Charakter (Import/Export,
     Workspace-Mitglieder, …) bleiben fail-closed: Ist kein Ziel-Workspace im
     Request auflösbar, lautet die Antwort `WORKSPACE_UNRESOLVABLE_DENIAL` (403).
     Damit bleibt die Coverage-Gate-Erwartung aus ADR-011 (§4) erhalten.

2. **Objekt-Routen bleiben objekt-abgeleitet und fail-closed — mit 404-vs-403-Regel.**
   Für `retrieve`/`update`/`partial_update`/`destroy` und Custom-Detail-Aktionen gilt:
   - Löst der Seam das Zielobjekt auf **und existiert dessen Workspace im aktiven
     Tenant**, ist eine aktive Rolle in diesem Workspace erforderlich —
     sonst `WORKSPACE_MEMBERSHIP_DENIAL` (403).
   - Löst der Seam **kein** Objekt auf (nicht existent, malformte ID oder Objekt eines
     anderen Tenants), wird am Seam **nicht** verweigert. Die tenant-geskopte View
     antwortet 404/400. Ein fremd-tenantes Objekt bleibt damit von einem fehlenden
     ununterscheidbar — **kein Existenzleck**. Ein `tenant`-geskopiertes oder
     `exception`-Ressourcen-Objekt benötigt weiterhin keinen Ziel-Workspace.

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

---

## Konsequenzen

**Positiv:**

- SEC-02 ist umgesetzt: Der Seam ist scharf, ohne die Collection-API zu blockieren.
  Gemessen `rest_api`: **430 → 0** Fehler bei Flag ON; der gesamte Backend-Lauf ist
  bis auf zwei belegte Umgebungsfehler grün.
- 404-vs-403 ist konsistent und ohne Existenzleck: bestehende Objekte ohne Rolle 403,
  fehlende/mandantfremde Objekte 404.
- Eine Durchsetzungsstelle bleibt (ADR-007-Muster); neue Collection-Routen erben die
  Regel automatisch, neue Objekt-Routen bleiben fail-closed.
- Der Auth-Layer und der Seam widersprechen sich nicht mehr (Rollen-Wiederverwendung).

**Negativ:**

- Der Seam ist jetzt auf die DRF-Aktion `view.action` angewiesen; Nicht-DRF-Aufrufer
  müssen ihre Aktion sauber setzen oder fallen in den Objekt-/fail-closed-Zweig.
- Boundary-/Unit-Tests, die eine unklassifizierte Mock-View oder einen synthetischen
  `AuthContext` ohne `workspace_id` verwenden, mussten an die neue Default-Lage
  angepasst werden (klassifizierte View bzw. rollen-tragender Kontext). Die
  Sicherheits-Assertions dieser Tests blieben unverändert.
- Zwei Umgebungsfehler (`mcp_server/tests/test_mcp_api_key_roles.py`, 4 Setup-Errors)
  sind **unabhängig** von diesem ADR: Sie verlangen ein geseedetes `Demo Workspace`
  (`seed_demo`/`bootstrap_admin`), das im Test-Stack fehlt; sie treten mit Flag `False`
  identisch auf.
- Trace-Link-Autorisierung folgt dem Quell-Artefakt; ein Nutzer mit Rolle nur am
  Ziel-Artefakt eines workspace-übergreifenden Links sieht den Link-by-id nicht.

---

## Umsetzungs-Nachweis (nicht Teil der Entscheidung)

- Seam: `backend/auth_tenancy/resource_scope.py`
  (`_is_collection_action`, `_workspace_in_active_tenant`, überarbeitetes
  `enforce_request_scope`, `_has_active_role_in_workspace`).
- Objektauflösung: `backend/application/workspace_lookup.py` (`trace_link`).
- Settings: `backend/reqogniloom/settings.py` (`AUTHZ_WORKSPACE_SCOPE_ENFORCED=True`).
- Tests: neue Collection-Regel-Fälle in
  `backend/rest_api/tests/test_sec02_sec03_workspace_fence.py`.

*Erstellt durch `senior-developer` am 2026-10-02. Status `proposed`; Review durch
`concept-reviewer` folgt extern. Kein Push, kein Tag, kein Merge.*
