---
adr_id: ADR-011
title: "Zwei-Ebenen-Autorisierung: Tenant bleibt Isolationshülle, Workspace wird objektabgeleitete Achse mit explizitem Ressourcen-Scope"
status: accepted
date: "2026-10-01"
deciders: [user, senior-developer]
affected_reqs: [REQ-L0-008, REQ-L1-042, REQ-L1-098, REQ-L2-AS-041, REQ-L2-AT-002, REQ-L2-AT-003, REQ-L2-AT-018, REQ-L2-PL-010, REQ-L2-PL-012, REQ-L2-RA-006]
superseded_by: null
---

# ADR-011: Zwei-Ebenen-Autorisierung: Tenant bleibt Isolationshülle, Workspace wird objektabgeleitete Achse mit explizitem Ressourcen-Scope

**Status:** accepted
**Datum:** 2026-10-01
**Entscheider:** user, senior-developer
**Betroffene REQs:** REQ-L0-008 (Mandantenfähige Isolation), REQ-L1-042 (Workspace-Lifecycle mit RBAC),
REQ-L1-098 (Data Integrity & Tenant Isolation), REQ-L2-AS-041 (Service-Level Autorisierung RBAC & Tenant),
REQ-L2-AT-002 (API Key Authentication), REQ-L2-AT-003 (Role-Based Permission Enforcement),
REQ-L2-AT-018 (Item-Level Permission Enforcement), REQ-L2-PL-010 (PostgreSQL RLS),
REQ-L2-PL-012 (Vollständige Tenant-Isolation), REQ-L2-RA-006 (RBAC-Enforcement auf API-Ebene)
**Bezug:** Kandidat #1 / Arbeitseinheit `SEC-01` (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:33-73`,
`docs/audit/2026-09/review/plan/SECURITY_AUTHZ.md:19-31`);
`backend/auth_tenancy/workspace_scope.py:79-131`; `backend/auth_tenancy/rest.py:259-277`;
`backend/rest_api/auth_enforcer.py:109-120`; `backend/mcp_server/tool_registry.py:1347-1401,1592-1601`;
`backend/auth_tenancy/services/authentication.py:552-571`; `backend/auth_tenancy/models.py:155-162`;
`backend/rest_api/api_key_views.py:371-408`; `backend/application/requirement_service.py:754-757`;
`backend/auth_tenancy/migrations/0011_rls_policies.py:43-64`

**Review-/Lifecycle-Vermerk:** Statuswechsel `proposed → accepted` am 2026-10-01.
Review-Verdikt `concept-reviewer` **APPROVED**, `validator` **COMPLIANT** (MADR-Lifecycle,
Datum + Grund dokumentiert). `deciders` bleiben `user, senior-developer`; User ist die
Freigabe-Instanz, die Reviewer ändern den Status nicht.

---

## Kontext

**Zwei Autorisierungsachsen existieren nebeneinander, aber nur eine ist durchgesetzt.**

**1. Tenant ist vollständig dicht und muss es bleiben.** Row-Level-Security (REQ-L2-PL-010) ist
implementiert und getestet; in 120 Cross-Tenant-Proben (REST) und 65 (MCP) wurde kein Leak
gemessen. **Fundstelle der Ausnahmen:** `at_api_key` und `at_user_role` sind als
Pre-Auth-Ausnahmen in der RLS-Migration dokumentiert
(`auth_tenancy/migrations/0011_rls_policies.py:43-64`); `audit_entry` steht **nicht** dort,
sondern als Eintrag in `persistence/tests/test_rls_coverage.py` (`RLS_EXEMPT_TABLES`,
`:75-262`, `audit_entry` `:99-110`). Auch `at_refresh_token` und die vier `as_*`-Tabellen
sind dort geführt; die noch offenen `as_*`-Tabellen ohne `tenant_id` sind der Gegenstand
von `DATA-07`, keine Frage dieser Achse.

**2. Workspace ist offen, weil die Zielsicht nicht objektabgeleitet ist.** `UserRole` ist
workspace-gebunden (`workspace` FK ist `NOT NULL`, `workspace_scope.py:3-5`) — das Datenmodell
kennt gar keine tenant-weite Rolle. Der Fence wird aber nur ausgelöst, wenn der **Client** eine
`workspace_id` mitsendet: `resolve_request_workspace_id` liest sie aus URL-Kwarg, Query-Parameter
oder JSON-Body (`workspace_scope.py:79-131`, insbesondere `:86` Query und `:111` Body). Liefert
das keinen Treffer, fällt `rest.py:259-277` auf die **tenant-weite UNION** aller Rollen zurück —
also genau auf die Menge, aus der der Fence ausgeschlossen werden sollte. `auth_enforcer.py:109-120`
prüft den Capability-Scope des API-Keys, aber **nicht** die Ziel-Workspace-Zugehörigkeit; und
`requirement_service.py:754-757` lädt ein Requirement nur tenant- plus id-skopiert. Von 311
mutierenden Routen sind 269 ohne Fence (`AUDIT_ADR_CANDIDATES.md:43-46`, Finding `AUD-2026-09-222`;
technische Fundstellen `SECURITY_AUTHZ.md:35-37`).

**3. Der MCP-Pfad beweist, dass die objektabgeleitete Variante funktioniert.** Dort werden die
Rollen aus dem **Tool-Argument** `workspace_id` aufgelöst (`tool_registry.py:1377-1380`), und der
API-Key-Fence wird auf das Ziel-Workspace des Aufrufs angewandt — fail-closed, wenn keins ableitbar
ist (`tool_registry.py:1592-1601`, Funktion `_check_workspace_fence` `:1568-1601`). Für
Agent-Keys sind `scope`, ein nicht-leeres `workspace_ids` und ein `expires_at` bereits Pflicht
(`authentication.py:552-558`). REST macht nichts davon: die Fence existiert heute **nur
MCP-seitig**; `RbacPermission`/`AuthTenancyAuthentication` (`auth_enforcer.py:109-120`,
`rest.py:259-277`) haben kein funktionales Äquivalent. Der gemeinsame Seam (MCP und REST)
ist damit **Liefergegenstand von `SEC-02`/`SEC-03`**, keine bereits geteilte Implementierung.

**4. Ein Live-Befund zeigt, dass die Achsen-/Ownership-Frage auch das Key-Management erfasst.**
Ein `admin`-Capability-Key (maskiert `34e0aeae…`, `expires_at=NULL`) ist an ein `e2e-user`-Konto
gebunden und über den self-scoped Admin-Endpunkt **nicht widerrufbar** — `DELETE /api/v1/api-keys/<pk>/`
liefert 404, weil `revoke_api_key(...)` ausschließlich auf die Keys des **anfragenden** Users
skopiert (`api_key_views.py:380-408`). Nicht der Key ist das Problem, sondern die **nicht
deklarierte Besitz-/Governance-Achse**: Wer einen Governance-Key mit `admin`-Scope administrieren
darf, ist heute aus dem Request abgeleitet statt aus der Ressource. Dasselbe Muster wie der
Workspace-Fence.

**Der Präzedenzfall `ADR-007` (`accepted`) entscheidet dieselbe Frageklasse für Regeln:** nicht
*wer* handelt, sondern *wo* durchgesetzt wird — ein einziger Durchsetzungspunkt statt Duplikation
über viele Pfade (`docs/se/ADR/ADR-007_se_regeln_am_baseline_gate.md:100-120`). Genau diese Form
fehlt der Autorisierung. **Abgrenzung `ADR-002`:** Der Event-Bus regelt die asynchrone Zustellung
interner Ereignisse, nicht Zugriffskontrolle; es gibt keinen inhaltlichen Konflikt, und der
Event-Pfad ist von dieser Entscheidung nicht betroffen.

**Zuordnungs-Status (offen):** Die Zuordnung dieses ADR zu den unter „Betroffene REQs"
genannten Anforderungen ist eine **Näherung**, keine bereits getrackte Verknüpfung.
`open_adrs` existiert repo-weit nicht (0/835 REQs, `AUD-2026-09-333`) — die
REQ↔ADR-Rückverfolgbarkeit kann heute nicht maschinell eingetragen werden und bleibt eine
Folgeaufgabe (siehe „Folgeaufgaben"). Es wird **keine** REQ neu erfunden und **keine**
REQ-Datei geändert.

---

## Alternativen

### Option A: Workspace als führende Achse, pro Route objektabgeleitet — VERWORFEN (als alleiniges Modell)

**Beschreibung:** Jeder Lese-/Schreibpfad leitet den Ziel-Workspace **aus dem Zielobjekt** ab; ein
`workspace_id` im Request wird zur Optimierung, nicht zur Bedingung.

**Abwägung:** Die **Semantik** ist richtig und wird übernommen. Als alleiniges Modell bleibt aber
die Fehlerfläche bestehen, die `222` erzeugt hat: Die Ableitung wird in 269 Handlern wiederholt.
Der Audit-Beleg aus `ADR-007` (`stage_matrix.py`-Migrationsregression) zeigt, dass eine
Durchsetzung, die pro Pfad verdrahtet ist, driftet — genau deshalb scheiterte dort ein Create-Gate
über alle Clients. Neue Routen erben hier keinen Fence, sondern müssen ihn erneut korrekt bauen.

**Risiko:** MITTEL — Semantik korrekt, aber die Klasse kehrt bei jeder neuen Route zurück.

### Option B: Tenant als führende Achse, Workspace als konfigurierbare Policy — VERWORFEN

**Beschreibung:** Tenant bleibt der Kern; Workspace-Sichtbarkeit wird eine pro Tenant zuschaltbare
Policy, deklariert über ein `x-requires-workspace`-Flag je View.

**Abwägung:** Löst `222` nicht, sondern macht die Lücke **konfigurierbar** und damit unsichtbar.
Die Policy muss weiterhin überall gesetzt werden — dieselbe Fehlerklasse wie heute, nur mit
Schalter. Für Mandanten, die bewusst workspaceübergreifend arbeiten, wäre das ein legitimes
**Feature**; es ist aber keine Antwort auf einen Fence, der für 269 Routen schlicht fehlt. Eine
Lücke als Produktfeature zu dokumentieren, ohne sie vorher zu schließen, kehrt Ursache und Wirkung um.

**Risiko:** HOCH — lässt die gemessene Lücke offen und verlagert sie in die Dokumentation.

### Option C: Zwei-Ebenen-Modell mit explizitem Ressourcen-Scope — GEWÄHLT

**Beschreibung:** Jede Ressource bzw. Route deklariert **einmal** ihren Scope: `tenant` oder
`workspace`. Der Fence wird aus dieser Deklaration an **einer** Stelle abgeleitet
(`RbacPermission` / `AuthTenancyAuthentication`), nicht pro Route verdrahtet. Für `workspace`-Scope
gilt: Autorität folgt dem **Zielobjekt** (A-Semantik); ist kein Ziel-Workspace ableitbar, wird
**fail-closed** mit 403 abgelehnt — kein Rückfall auf die tenant-weite UNION. Tenant bleibt die
nicht verhandelbare Isolationshülle der RLS.

**Vorteile:**
- Die Fehlerklasse `222` wird **strukturell** geschlossen: eine Deklarationsstelle statt 269 Pfade;
  eine neue Route erbt den richtigen Fence automatisch.
- `ADR-007` fortgesetzt: **eine** Durchsetzungsstelle, an der eine Coverage-Prüfung greifen kann
  (analog Registry/Waiver), statt einer Pro-Pfad-Konvention.
- Die objektabgeleitete Semantik des MCP-Pfads (`tool_registry.py:1377-1380`, Funktion
  `_check_workspace_fence` `:1568-1601`) wird zur REST-paritätischen Regel. Der gemeinsame
  Seam ist **Liefergegenstand von `SEC-02`/`SEC-03`**: heute existiert die Fence nur
  MCP-seitig; REST (`RbacPermission`/`AuthTenancyAuthentication`) zieht nach.
- `DATA-06`/`DATA-07` werden architektonisch kohärent: die Ressource trägt ihren Scope
  (`we_item_state` erhält Workspace-FK; `as_*`-Tabellen erhalten `tenant_id` + RLS), statt dass
  jede Route ihn erraten muss.

**Nachteile:**
- Ein Fehler in der Deklaration bzw. im Seam wirkt **sofort auf alle** Ressourcen dieses Scopes —
  die Coverage muss daher testgesichert sein, bevor der Seam scharf wird.
- Jede Ressource/Klasse muss klassifiziert werden (`tenant` vs. `workspace`); dateilose bzw.
  nicht-workspace-gebundene Objekte brauchen eine benannte Ausnahme.
- Bestehende Agent-Keys ohne `workspace_ids`/`expires_at` werden strikter → Policy-Migrationsfenster
  (von `SEC-03` bereits vorgesehen).

**Risiko:** MITTEL — hohe Einführungsdisziplin, dafür keine Pro-Pfad-Drift.

---

## Entscheidung

1. **Tenant bleibt die Isolationshülle.** RLS (REQ-L2-PL-010) wird nicht angetastet; die
   dokumentierten Pre-Auth-Ausnahmen (`at_api_key`, `at_user_role`, `audit_entry`) bleiben benannt.
   Die noch fehlende RLS-Deckung der `as_*`-Tabellen ist `DATA-07`, nicht Teil dieser Achse.

2. **Workspace ist die führende Ebene der Objekt-Autorisierung.** Für eine `workspace`-skopierte
   Ressource wird die Autorität aus dem **Zielobjekt** abgeleitet, **nie** aus einem
   client-gelieferten `workspace_id`. Ein `workspace_id` im Request bleibt höchstens Optimierung.

3. **Eine Scope-Deklaration, ein Seam — mit DEFAULT-DENY für Unklassifiziertes.** Jede
   Ressource/Klasse deklariert `tenant` **oder** `workspace` in einem zentralen
   **Klassifikator** (eine Registrierung, kein Pro-Route-Flag); der Fence wird an **einer**
   Stelle daraus abgeleitet und zentral in `RbacPermission`/`AuthTenancyAuthentication`
   verankert (analog zur bereits zentralisierten Capability-Prüfung,
   `auth_enforcer.py:109-118`). **Maßgeblich ist die Deklaration, nicht der Request.** Ist
   eine Ressource nicht deklariert oder ihr Scope unbekannt, lautet die Antwort
   **fail-closed: 403** — es gibt **keinen** Rückfall auf die tenant-weite UNION aus
   `rest.py:259-277` und **keine** implizite `tenant`-Annahme für Unklassifiziertes. **Nur
   für `workspace`-skopierte Ressourcen** gilt zusätzlich: lässt sich der **Ziel-Workspace**
   nicht auflösen, ebenfalls **fail-closed: 403**. Eine `tenant`-skopierte Ressource braucht
   **keinen** Ziel-Workspace und wird von dieser Regel **nicht** betroffen. Ein unbekannter
   Scope wird wie ein unbekannter Workspace behandelt: deny. Damit entscheidet der
   **Klassifikator** — nicht der Client — über fail-open vs. fail-closed der 269
   ungefenceten Routen.

4. **Coverage-Gate vor Scharfschaltung des Seams.** Ein Test enumeriert alle
   **Ressourcen/Klassen** über den Klassifikator und wird **rot**, solange **eine**
   unklassifizierte Ressource existiert; er prüft zusätzlich, dass eine
   **`workspace`-skopierte Ressource ohne auflösbaren Ziel-Workspace 403 liefert, statt auf
   die tenant-weite UNION zurückzufallen — für `tenant`-skopierte Ressourcen gilt diese
   Prüfung nicht**, da sie keinen Ziel-Workspace benötigen. Der Seam wird erst scharf
   geschaltet, wenn dieser Test grün ist — dieselbe „Registry + Coverage + Waiver"-Form,
   die `ADR-007` für Regeln belegt. Das Gate läuft **vor** dem Scharfschalten, damit die
   269 Routen nicht durch eine stille `tenant`-Default-Annahme fail-open werden.

5. **API-Key-Fence und Ablauf werden an demselben Seam durchgesetzt.** Die heute nur in MCP
   wirksame Prüfung von `workspace_ids` (`tool_registry.py:1592-1601`, Funktion
   `_check_workspace_fence` `:1568-1601`) und `expires_at` gilt
   damit ebenfalls für REST. Für Agent-Keys bleiben `scope`, explizites `workspace_ids` und
   `expires_at` Pflicht (`authentication.py:552-558`); Legacy-`user`-Keys ohne Ablauf sind das
   Ziel der Key-Rotation (`SECTRACK-01`), nicht dieser ADR.

6. **Ownership ist eine deklarierte Ressourceneigenschaft, keine Request-Ableitung — mit
   Minimalregel.** Der Live-Fall `admin`-Key (`34e0aeae…`, `expires_at=NULL`) an
   `e2e-user`, nicht widerrufbar via `api_key_views.py:380-408`, wird zum Regelfall:
   **Minimalregel:** Ein `admin`-/Governance-Key ist gegen die **Governance-Ebene seines
   eigenen Tenants** administrierbar (widerrufbar durch einen Tenant-Admin), **unabhängig
   davon, an welchem User-Konto er hängt** — nicht nur self-scoped durch den anfragenden
   User. `revoke_api_key(...)` (`api_key_views.py:403`) ist entsprechend um die
   Governance-Achse zu erweitern. Die vollständige Rollen-/Scope-Matrix (wer darf welchen
   `scope` widerrufen, Key-Rotation, Ablauf-Erzwingung) ist eine **Folge-ADR**
   (Ownership-/Governance-ADR) zu `SEC-04`/`SECTRACK-01`; hier ist nur die Richtung und die
   Minimalregel festgehalten.

7. **Kaskade der abhängigen Arbeitseinheiten.** `SEC-02` (REST-Workspace-Fence objekt-abgeleitet),
   `SEC-03` (API-Key-`workspace_ids`+`expires_at` auf REST), `SEC-04` (Admin-/Webhook-Härtung),
   `DATA-06` (`we_item_state` Workspace-FK) und `DATA-07` (RLS-Deckung der `as_*`-Tabellen)
   referenzieren diesen ADR und setzen ihn um; `DATA-06`/`DATA-07` liefern dabei die
   ressourcenseitige Scope-Information, auf der der Seam aufsetzt.

---

## Konsequenzen

**Positiv:**

- Die Klasse `222` ist **strukturell** geschlossen: neue Routen erben den Fence, statt ihn erneut
  zu implementieren; die 269 pfadbasierten Wiederholungen entfallen.
- REST und MCP teilen **einen** Seam — sobald `SEC-02`/`SEC-03` ihn bereitstellen:
  `_check_workspace_fence` (`tool_registry.py:1568-1601`) ist die MCP-Referenz,
  `auth_enforcer.py:109-118` das REST-Ziel. Heute sind es noch zwei Pfade; die
  Zusammenführung ist der Liefergegenstand, keine Bestandsaufnahme.
- Der Fence ist **fail-closed** definiert — auch für **Unklassifiziertes** (DEFAULT-DENY,
  kein impliziter `tenant`-Fallback); der Rückfall auf die tenant-weite UNION
  (`rest.py:259-277`) verschwindet als stille Erweiterung.
- `DATA-06`/`DATA-07` bekommen ihre architektonische Begründung: die Ressource trägt ihren Scope,
  statt ihn pro Route erraten zu lassen; die Migrationen sind damit Teil der Entscheidung, nicht
  isolierte Härtung.
- `ADR-007` wird als Muster fortgeführt: eine Durchsetzungsstelle mit testbarer Coverage statt
  einer Pro-Pfad-Konvention.

**Negativ:**

- **Blast-Radius der Deklaration:** Ein Fehler im Scope-Seam wirkt sofort auf alle Ressourcen
  dieses Scopes. Der Seam muss durch einen Coverage-Test abgesichert sein, **bevor** er scharf
  wird — der Test wird für **jede** unklassifizierte Ressource rot. Ohne dieses Gate droht
  derselbe Kalibrierungsbruch, den `ADR-007` für Gates dokumentiert, nur mit umgekehrtem
  Vorzeichen: statt stiller Freigabe eine flächige 403.
- **Klassifikationsaufwand:** jede Ressource/Klasse muss `tenant` oder `workspace` deklarieren;
  dateilose bzw. bewusst workspaceübergreifende Objekte brauchen eine **benannte** Ausnahme
  (nicht: stiller Fallback).
- **Kollateral-Regressionen auf Detailrouten** sind wahrscheinlich, sobald der Fence greift
  (`SEC-02` sieht dafür Feature-Flag/Branch-Rollback vor). Bestehende Bearer-/API-Key-Flows können
  dort 200 → 403 wechseln; die Regressionssuite ist mitzuziehen.
- **Policy-Migrationsfenster für Agent-Keys:** Keys ohne `workspace_ids`/`expires_at` werden durch
  `SEC-03` strikter; Key-Rotation/Inventarisierung (`SECTRACK-01`) muss der Verschärfung
  vorausgehen, sonst brechen laufende e2e-/Client-Flows.
- **Entscheidung getroffen, Umsetzung offen:** Mit dem Status `accepted` (2026-10-01) ist der
  Start der abhängigen Fixes (`SEC-02/03/04`, `DATA-06/07`) freigegeben; bis zu deren
  Umsetzung bleibt die gemessene Lücke offen und dokumentiert.
- **Kein Ersatz für `SECTRACK`:** Der Live-Fall `34e0aeae…` (maskiert) zeigt eine reale,
  noch zu rotierende `admin`-Key-Instanz; diese ADR beschreibt die Zielachse, sie widerruft
  keinen Key.

---

## Folgeaufgaben (nicht Teil dieser Entscheidung)

1. **`open_adrs`-Feld einführen** (repo-weit, `AUD-2026-09-333`), damit die unter
   „Betroffene REQs" genannten Anforderungen diesen ADR referenzieren können. Bis dahin
   wird **keine** REQ-Datei geändert.
2. **Ownership-/Governance-ADR** (`SEC-04`/`SECTRACK-01`): vollständige Matrix, wer welchen
   `scope` widerrufen darf, Key-Rotation und Ablauf-Erzwingung. Die Minimalregel aus
   Entscheidung Punkt 6 ist der Startpunkt.
3. **Gemeinsamen Workspace-Fence bereitstellen** (`SEC-02`/`SEC-03`): `_check_workspace_fence`
   aus dem MCP-Pfad als geteilten Seam extrahieren und in `RbacPermission`/
   `AuthTenancyAuthentication` verankern; das Coverage-Gate (Entscheidung Punkt 4) geht voran.
4. **Review-/Lifecycle-Nachweis:** Der Übergang `proposed → accepted` ist am 2026-10-01
   durch Re-Review (`concept-reviewer` **APPROVED**) und Validierung (`validator`
   **COMPLIANT**) belegt, inkl. Prüfung gegen die betroffenen REQs und die
   Default-Deny-Abgrenzung zu `rest.py:259-277`.

---

### Amendment-Hinweis (Info, nicht Teil der Entscheidung)

`ADR-013` (Collection-Route-Regel, `accepted`) präzisiert §3 und die 403-Teilaussage von
§4 für Collection-Routen (`list`/`create`): §4 gilt in **Mechanik/No-Union-Fallback**
(„eine Deklaration, ein Seam", Coverage-Gate) unverändert, seine fail-closed-403-Aussage
(„`workspace`-skopierte Ressource ohne auflösbaren Ziel-Workspace ⇒ 403") gilt **nur für
Nicht-Collection-Routen**. Die Entscheidung dieses ADR bleibt davon unberührt.

---

*Erstellt durch `senior-developer` am 2026-10-01. Status `accepted` seit 2026-10-01 —
`concept-reviewer` APPROVED, `validator` COMPLIANT; die Achsenwahl hat der User freigegeben.
Kein Produktcode, keine Migration, kein Push.*
