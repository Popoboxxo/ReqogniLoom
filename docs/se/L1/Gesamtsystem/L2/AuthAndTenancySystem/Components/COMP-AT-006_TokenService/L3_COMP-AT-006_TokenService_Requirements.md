decomposition_status: terminal

# L3 TokenService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AT-006 — TokenService
> **Parent-System:** AuthAndTenancySystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Kernlogik des AuthAndTenancySystems für die Persistenz (Django Model) und kryptografische Validierung (Hashing) von Personal Access Tokens.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AT-020 | Persistierung und Validierung von PATs |

## L3 Komponenten-Anforderungen

### REQ-L3-AT006-001: Kryptografische Sicherung (Hashing)

Beim Generieren MUSS der Token (z.B. über Python `secrets.token_urlsafe()`) erzeugt, via Django's `make_password` gehasht in die Datenbank geschrieben und der Klartext nur für das Return-Statement im Arbeitsspeicher gehalten werden.

**Implementation State:** Erfüllt durch bestehende Komponente (kein separates COMP-AT-006 erforderlich)
**Priority:** mandatory
**Acceptance Criteria:**
- [x] Django-Modell besitzt Feld `token_hash` (kein `token`). → `ApiKey.key_hash` (`backend/auth_tenancy/models.py:60`), Format `sha256:<hex>`, unique+indexed.
- [x] Validierung gegen den Header vergleicht via `check_password(klartext, token_hash)` konstant-zeitig. → SHA-256-Vergleich in `AuthenticationService` (konstant-zeitig), siehe REQ-L2-AT-002.
- [x] Auth-Middleware nutzt diesen Service, um bei Pattern `Bearer rf_*` den Token zu validieren und den Request dem entsprechenden Django-User zuzuordnen. → bereits umgesetzt via REQ-L2-AT-007, Präfix `rf_` bereits identisch zur Spezifikation.

> **Architektur-Entscheidung (2026-07-04):** REQ-L2-AT-020 wird vollständig durch die bestehende Komponente `COMP-AT-001_AuthenticationService` (inkl. `ApiKey`-Modell, `AuthenticationService.create_api_key/list_api_keys/revoke_api_key`) erfüllt. Diese Anforderung spezifiziert funktional dasselbe Feature (self-service, gehashte Bearer-Tokens mit `rf_`-Präfix, revoke, shown-once) wie das bereits produktive `ApiKey`-System (REQ-L2-AT-002, REQ-L2-AT-009). Eine zweite, parallele Token-Validierungs-Pipeline würde ein Sicherheitsrisiko darstellen (zwei konkurrierende Bearer-Auth-Pfade). **COMP-AT-006 wird daher nicht als eigene Komponente implementiert** — Traceability zeigt stattdessen auf COMP-AT-001.

---

### REQ-L3-AT006-002: L3 Context Generators Implementation

Derives from REQ-L2-AUT-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-AT006-003: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-AUT-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
