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

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Django-Modell besitzt Feld `token_hash` (kein `token`).
- [ ] Validierung gegen den Header vergleicht via `check_password(klartext, token_hash)` konstant-zeitig.
- [ ] Auth-Middleware nutzt diesen Service, um bei Pattern `Bearer rf_*` den Token zu validieren und den Request dem entsprechenden Django-User zuzuordnen.
