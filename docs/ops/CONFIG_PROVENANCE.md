# Konfigurations-Provenienz — sicherheitsrelevante Defaults

> **Zweck:** Nachvollziehbare Herkunft und Produktiv-Haltung aller sicherheitsrelevanten
> Konfigurations-Defaults. Dieses Dokument ergänzt den bestehenden Key-Drift-Gate um die
> *semantische* Bewertung (Default, Begründung, Fail-Open-Klassifikation), die der Gate
> fachlich nicht leisten kann. Es ist **keine** zweite Key-Liste (siehe §5).
>
> **Owner:** `devops-engineer` · **Review-Datum:** 2026-11-18 · **Klassifikation:** intern
> Sprachregel gemäß `AGENTS.md`: interne Doku → Deutsch; technische Bezeichnungen und
> Quellzitate bleiben englisch.
>
> **Audit-Bezug:** SEC-002, `docs/audit/2026-11-16-deep-dive-findings.md:67`, `:420`, `:1154`;
> Entscheidung E2 in `docs/audit/gates/2026-11-16/mvp-gates.md:26`.

## 1. Geltungsbereich und Lesart

Erfasst sind ausschließlich sicherheits-, tenant- und auth-relevante Defaults aus
`backend/reqogniloom/settings.py`. Kosmetische Werte (Timeouts, Summary-/Sweep-Intervalle,
Token-Budgets ohne Sicherheitswirkung) sind bewusst nicht aufgeführt. **Es werden keine
Credential-Werte dokumentiert** — nur Schlüsselnamen und ihre Defaults. Pflicht-Secrets
sind als „kein Default (Pflicht)“ markiert.

Klassifikation der Fail-Verhaltensweise:

| Klasse | Bedeutung |
|---|---|
| **fail-open** | Fehlende/falsche Konfiguration lässt die Kontrolle unwirksam; Risiko ist *mehr* Zugriff bzw. Exposition. |
| **fail-closed** | Fehlende/falsche Konfiguration verweigert oder härtet; Risiko ist Ausfall/Degradation, nicht Datenabfluss. |
| **fail-closed by env** | Produktiv-Default restriktiv, Non-Prod bewusst permissiv (via `DJANGO_ENV`). |
| **fail-closed (validiert)** | Wert wird beim Start geprüft; unzulässige Werte werfen `ImproperlyConfigured` → kein Start. |

Spalte „SEC-002-Bezug“: **direkt** = Tenant-Isolierung/DB-Backstop; **mittelbar** = verwandte
Auth-/Autz-Härtung; **n/a** = anderes Finding (z. B. SA-33/AI-003, SEC-001).

Alle Zeilen wurden gegen den Dateistand `f60697d` verifiziert; Zeilennummern sind
`settings.py`-Zeilen und können bei Code-Änderungen driften — dann ist diese Tabelle im
gleichen Commit nachzuziehen (kein separater Audit-Fund daraus machen).

## 2. Katalog sicherheitsrelevanter Defaults

| Schlüssel | Aktueller Default (Quelle, `settings.py`) | Produktions-Empfehlung | Begründung | Klassifikation | Owner | SEC-002-Bezug |
|---|---|---|---|---|---|---|
| `DJANGO_ENV` | `"production"` — :82 | `"production"` | Master-Schalter: steuert `_IS_NON_PROD` (:530) und damit alle env-abhängigen Defaults. Falscher Wert öffnet Non-Prod-Erleichterungen. | fail-closed | devops-engineer | direkt |
| `DEBUG` | `False`, zusätzlich `DEBUG = _debug_requested and DJANGO_ENV in _NON_PROD_ENVS` — :84-85 | `False` (code-seitig erzwungen) | Prod-DEBUG-Sperre (REQ-115): selbst gesetztes `DEBUG=true` wirkt in Produktion nicht. | fail-closed | devops-engineer | mittelbar |
| `SECRET_KEY` | `_get_required_secret("SECRET_KEY")`, kein Default; `ImproperlyConfigured` bei leer — :44-65, :75 | Pflicht, aus Secret-Manager; Rotation nach SEC-001 | Fehlt der Wert, startet die Anwendung gar nicht. Kein Wert in dieser Datei. | fail-closed (validiert) | devops-engineer | n/a (SEC-001) |
| `AUTH_JWT_SECRET` | `_get_required_secret("AUTH_JWT_SECRET")`, kein Default — :1036 | Pflicht, aus Secret-Manager; Rotation nach SEC-001 | Signatur-Schlüssel für Access/Refresh-Tokens; Fail-Fast wie `SECRET_KEY`. | fail-closed (validiert) | devops-engineer | n/a (SEC-001) |
| `FIELD_ENCRYPTION_KEY` | `config("FIELD_ENCRYPTION_KEY")`, kein Default; `ImproperlyConfigured` — :149-155 | Pflicht (Fernet-Key), aus Secret-Manager | Verschlüsselte Felder wären ohne Key nicht lesbar; Start wird verweigert. | fail-closed (validiert) | devops-engineer | n/a (REQ-081) |
| `RLS_AS_ENFORCED` | `config("RLS_AS_ENFORCED", default=False, cast=bool)` — :380 | **`true`** (mit Coverage-Gate, siehe §3) | GUC-gestützte Policy ist bei unset `IS DISTINCT FROM 'on' …` vollständig permissiv (:362-371); Flag armt das Tenant-Prädikat. | **fail-open** | devops-engineer | **direkt** |
| `RLS_PREAUTH_ENFORCED` | `config("RLS_PREAUTH_ENFORCED", default=False, cast=bool)` — :381 | **`true`** (mit Coverage-Gate, siehe §3) | Gleicher Mechanismus für `at_api_key`/`at_user_role` und die `as_*`-Tabellen; ohne Flag kein DB-Backstop. | **fail-open** | devops-engineer | **direkt** |
| `AUTHZ_WORKSPACE_SCOPE_ENFORCED` | `default=True` — :945-947 | `true` | ADR-011/013: Default-Deny der Workspace-Grenze; `false` nur als Rollback-Fenster. | fail-closed | devops-engineer | direkt |
| `AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED` | `default=True` — :952-954 | `true` | SEC-03: API-Key-`workspace_ids`-Fence, spiegelt den MCP-Dispatcher; `false` nur im Policy-Migrationsfenster (SECTRACK-01). | fail-closed | devops-engineer | direkt |
| `MFA_STAFF_ENFORCEMENT` | `default="optional"` — :768-770; Modi `off/optional/required` und `ImproperlyConfigured` bei unbekanntem Wert — :771-776 | `"required"` nach abgeschlossener Enrollment-Rollout-Welle | `optional` fordert nur enrolte Nutzer heraus; Staff ohne zweiten Faktor bleibt ungeschützt. Bewusst dreistufiger Rollout-Dial (WP E3.2/E3.9). | **fail-open** (bis `required`) | devops-engineer (Review: security-auditor, Block `auth-flow`) | mittelbar |
| `MFA_CHALLENGE_TTL_SECONDS` | `default=300`; Hartgrenze 900 s via `ImproperlyConfigured` — :789-804 | 300 (nicht erhöhen) | Challenge ist bereits ein Passwort-Erfolgsnachweis → langlebiges Credential. | fail-closed (validiert) | devops-engineer | mittelbar |
| `MFA_TOTP_VALID_WINDOW` | `default=1`; Hartgrenze ≤ 2 — :808-821 | 1 | Jede Erhöhung vergrößert die gültigen Codes linear (Brute-Force-Budget). | fail-closed (validiert) | devops-engineer | mittelbar |
| `MFA_ENROLL_GRANT_TTL_SECONDS` | `default=86400`; Hartgrenze 24 h — :827-835 | 86400 | Längere Grants wären eine stehende Enrollment-Berechtigung (QR-S01). | fail-closed (validiert) | devops-engineer | mittelbar |
| `MFA_MAX_FAILED_ATTEMPTS` / `MFA_LOCKOUT_SECONDS` | `5` / `900` — :785, :787 | 5 / 900 | Sperrt nach fünf Fehlversuchen für 15 Minuten. | fail-closed | devops-engineer | mittelbar |
| `ADMIN_LOGIN_LOCKOUT_ENABLED` | `default=True` (+ Threshold 5, Window 900, Duration 900) — :738-749 | `true` | Brute-Force-Schutz für Admin-Login; Abschalten nur mit externem Equivalentschutz. | fail-closed | devops-engineer | mittelbar |
| `AUTH_REFRESH_REUSE_GRACE_SECONDS` | `default=0` — :1099-1101 | 0 (strikt) | `0` erkennt Reuse sofort; jeder positive Wert ist ein nicht erkanntes Replay-Fenster (SA-32/F7). | fail-closed | devops-engineer | mittelbar |
| `AUTH_LOGIN_INCLUDE_BODY_TOKEN` | `default=True` — :1085-1087 | `false` nach Client-Migration (siehe §4) | Token im Response-Body erhöht die Exposition via Logs/Proxies; Abschaltung ist Deprecation-Ziel. | **fail-open** (Deprecation) | devops-engineer | mittelbar |
| `API_KEY_PEPPER` | `default=""` — :1054 | aus Secret-Manager setzen | Defence-in-Depth für API-Key-Hashes; optional (nicht fail-fast), Rotation = erzwungene Key-Rotation. Leerer Wert = kein Pepper. | **fail-open** (optional) | devops-engineer | mittelbar (SEC-001) |
| `IMPORT_FINGERPRINT_SECRET` | `default=""` — :1568-1570 | aus Secret-Manager setzen | Ohne Secret sind Import-Idempotency-Fingerprints ungesalzen. | **fail-open** | devops-engineer | mittelbar |
| `AUTH_JWT_TTL_SECONDS` | `default=3600` — :1063 | ≤ 3600 | 60-minütiges Access-Token-Fenster (#77); längere TTL vergrößert Missbrauchsfenster. | fail-closed | devops-engineer | mittelbar |
| `AUTH_JWT_ISSUER` / `AUTH_JWT_AUDIENCE` | `"reqogniloom"` / `"reqogniloom-api"` — :1056-1057 | deployment-spezifisch setzen | Valide Tokens fremder Instanzen mit identischen Claims wären sonst akzeptiert. | neutral (empfohlen: fail-closed) | devops-engineer | mittelbar |
| `AUTH_COOKIE_SECURE` | `default=not DEBUG` — :94 | `true` | Cookie nur über HTTPS; in Prod Default `true`, für HTTP-Internals überstimmbar (SA-41). | fail-closed by env | devops-engineer | mittelbar |
| `SESSION_COOKIE_SECURE` | `default=AUTH_COOKIE_SECURE` — :95-97 | `true` | Folgt dem Auth-Cookie-Default, damit keine Session über Klartext läuft. | fail-closed by env | devops-engineer | mittelbar |
| `CSRF_COOKIE_SECURE` | `default=AUTH_COOKIE_SECURE` — :98 | `true` | CSRF-Cookie darf nicht über HTTP abfließen. | fail-closed by env | devops-engineer | mittelbar |
| `SECURE_SSL_REDIRECT` | `default=False` — :104 | `true` **nur** mit TLS-terminierendem Reverse Proxy | Opt-in, weil ein Redirect ohne HTTPS-Listener das Deployment bricht. Ohne Proxy bleibt Traffic unverschlüsselt. | **fail-open** (Opt-in) | devops-engineer | mittelbar |
| `SECURE_PROXY_SSL_HEADER` | `("HTTP_X_FORWARDED_PROTO","https")` nur wenn `SECURE_SSL_REDIRECT`, sonst `None` — :108-110 | nur mit explizit konfiguriertem Proxy | Verhindert, dass Clients `X-Forwarded-Proto` fälschen und HTTPS-Prüfungen umgehen (N3). | fail-closed | devops-engineer | mittelbar |
| `SECURE_HSTS_SECONDS` | `0 if DEBUG else 31536000` — :312 | 31536000 (1 Jahr) | HSTS erst mit echtem HTTPS sinnvoll; Prod-Default bereits gesetzt. | fail-closed by env | devops-engineer | n/a (SEC-008) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `default=not DEBUG` — :313-315 | `not DEBUG` | Subdomain-Schutz; bewusste Entscheidung bei Wildcard-Zertifikaten. | fail-closed by env | devops-engineer | n/a (SEC-008) |
| `SECURE_HSTS_PRELOAD` | `default=not DEBUG` — :316 | bewusst entscheiden (Preload ist praktisch irreversibel) | Default ist sicher, aber Preload-Listen-Eintrag überdauert einen Domain-Wechsel. | fail-closed by env | devops-engineer | n/a (SEC-008) |
| `CSP_POLICY` | `"default-src 'self'; frame-ancestors 'none'; base-uri 'self'"` — :320-323 | restriktiv belassen | API-only-Backend benötigt keine Inline-Skripte oder Frames. | fail-closed | devops-engineer | n/a (SEC-008) |
| `ALLOWED_HOSTS` | `"localhost,127.0.0.1"` — :111-113 | explizite FQDN-Liste | Host-Header-Angriffe werden durch enge Liste blockiert. | fail-closed | devops-engineer | mittelbar |
| `CORS_ALLOWED_ORIGINS` | `"http://localhost:3000,http://localhost:5173"` — :166-170 | explizite Prod-SPA-Origin, nie `*` | Reflektieren eines beliebigen Origin mit `Allow-Credentials` wäre credentialed CSRF. | fail-closed | devops-engineer | n/a (REQ-081) |
| `CSRF_TRUSTED_ORIGINS` | localhost-Ports 5173/3000 — :185-190 | explizite Prod-SPA-Origin | State-changing Requests scheitern sonst mit 403; zu weite Liste schwächt CSRF-Schutz. | fail-closed | devops-engineer | mittelbar |
| `LLM_ALLOW_PRIVATE_BASE_URL` | `default=_IS_NON_PROD` — :1128-1130; `_IS_NON_PROD = DJANGO_ENV in _NON_PROD_ENVS` — :530, :83 | `false` (Prod-Default) + `LLM_BASE_URL_ALLOWED_HOSTS` statt Blanket-Flag | SSRF-Guard: private Ziele wären ein Proxy in Cloud-Metadata/DB/Redis. Non-Prod darf lokales Ollama erreichen. DNS-Rebinding nicht abgedeckt (`llm_adapter/url_guard.py`). | **fail-open by env** (nur Non-Prod) | devops-engineer | n/a (SA-33/AI-003) |
| `LLM_BASE_URL_ALLOWED_HOSTS` | `default=""` — :1133 | engste mögliche Host-Liste | Leer = keine Ausnahme vom SSRF-Guard; enge Liste ist der bevorzugte Weg gegenüber dem Blanket-Flag. | fail-closed | devops-engineer | n/a (SA-33/AI-003) |
| `LLM_API_KEY` | `default=""` — :1108 | aus Secret-Manager setzen (bei echtem Provider) | Leer ist korrekt für `mock`/Ollama; bei Cloud-Provider ohne Key funktioniert der Adapter nicht. Kein Wert hier dokumentiert. | fail-closed | devops-engineer | n/a |
| `HEALTH_STRICT_READINESS` | `default=True`; Konverter akzeptiert nur exakt `"false"` als Deaktivierung — :1166-1181 | `true` | ADR-010 §6: ungesunde Pflicht-Dependency → HTTP 503; Default ist fail-closed „by omission“. | fail-closed | devops-engineer | mittelbar (OPS-001) |
| `TENANT_TOKEN_LIMIT_PER_DAY` | `default=None` (unbegrenzt) — :1191-1193 | positiver Budgetwert | REQ-106: ohne Limit keine Kosten-/Missbrauchsbremse pro Tenant (429 `LLM_TOKEN_LIMIT_EXCEEDED`). | **fail-open** (Kosten/Abuse) | devops-engineer | mittelbar |
| `MAX_ACTIVE_API_KEYS_PER_USER` | `default=10` — :1199-1201 | 10 oder niedriger | Harter Cap aktiver Keys verhindert unbegrenzte Credential-Spreuung (#606). | fail-closed | devops-engineer | mittelbar |
| `REDIS_PASSWORD` | `default=""` — :1212 | aus Secret-Manager setzen | Leer = unauthentifizierter Zugriff auf Cache/Celery-Broker im selben Netz. Kein Wert hier dokumentiert. | **fail-open** | devops-engineer | mittelbar |
| `SELF_INIT_ON_MIGRATE` | `default=True` — :1653 | `false` nach erfolgtem Bootstrap | Auto-Bootstrap legt Admin/Tenant/Workspace auf leerer DB an; in Prod nach Initialisierung abschalten. | **fail-open** | devops-engineer | mittelbar |
| `DEFAULT_TENANT_ID` | `default=1` — :1577 | 1 (v1 Single-Tenant) | Für v2-Multi-Tenancy explizit setzen; falsche ID verknüpft Daten mit falschem Tenant. | neutral | devops-engineer | direkt (v2) |
| `API_RATE_LIMIT_USER` / `_ANON` | `600/min` / `120/min` (Prod) — :541-548 | Prod-Werte beibehalten, nie leeren | Env-abhängig (`_throttle_rate`, :533-535); **leerer Wert deaktiviert das Throttle vollständig** (:520-524) → operatorseitiger Fail-Open. | fail-closed in Prod | devops-engineer | mittelbar (Block `rate-limiting`) |
| `LOGIN_THROTTLE_RATE` / `LOGIN_IP_THROTTLE_RATE` | `10/min` / `60/min` (Prod) — :550-558 | Prod-Werte beibehalten, nie leeren | Credential-Stuffing-/Spray-Bremse; IP-Rate muss über der User-Rate bleiben. | fail-closed in Prod | devops-engineer | mittelbar |
| `REFRESH_THROTTLE_RATE` / `MCP_RATE_LIMIT_KEY` | `30/min` / `240/min` (Prod) — :560-574 | Prod-Werte beibehalten, nie leeren | Unauthentifizierter Refresh-Endpoint und MCP-Views liegen außerhalb der DRF-Default-Throttles. | fail-closed in Prod | devops-engineer | mittelbar |

## 3. SEC-002 — Produktiv-Haltung (explizite Entscheidung)

**Ausgangslage (Audit, noch offen):** `docs/audit/2026-11-16-deep-dive-findings.md:1154`
fordert einen Decision Gate: *„explicitly choose the production posture — enforce RLS, or
declare isolation app-layer-only and remove the marketing claim.“* Der Befund ist weiterhin
offen; die Default-Deployment (`RLS_AS_ENFORCED=False`, `RLS_PREAUTH_ENFORCED=False` settings.py:380-381,
`.env.example:973-974`, keine Flags in `deploy/`) ist permissiv und macht den DB-Layer wirkungslos
(`docs/audit/gates/2026-11-16/mvp-gates.md:26`, E2: BESTÄTIGT).

**Entscheidung (Owner `devops-engineer`, Review 2026-11-18): RLS in Produktion erzwingen.**
Die Produktiv-Haltung lautet damit für **alle** in §2 als *fail-open* klassifizierten Knobs:

1. `RLS_AS_ENFORCED=true` und `RLS_PREAUTH_ENFORCED=true` sind verpflichtende
   Produktiv-Konfiguration. Die Isolierung bleibt primär in `TenantContext`/ORM (ADR-03),
   erhält aber einen wirksamen DB-Backstop — die Marketing-Aussage „Multi-Tenancy via RLS“
   bleibt damit gedeckt.
2. Zusätzlich muss `pl_rls_enforcement.hard_enforced=true` per Owner-SQL gesetzt werden.
   Der GUC ist sonst für die App-Rolle per Session-`SET` rücksetzbar (`R-7`, PG16 nicht
   behebbar, `rls_hardening.py:15-20`); ohne Owner-Control ist der Backstop partial.
3. Die produktiven Defaults `MFA_STAFF_ENFORCEMENT=required`,
   `AUTH_LOGIN_INCLUDE_BODY_TOKEN=false`, `SELF_INIT_ON_MIGRATE=false` sowie gesetzte
   `API_KEY_PEPPER`/`IMPORT_FINGERPRINT_SECRET`/`REDIS_PASSWORD` und ein positiver
   `TENANT_TOKEN_LIMIT_PER_DAY` sind Zielbild derselben Haltung — kein fail-open Knob
   darf ohne dokumentierte Ausnahme in Produktion verbleiben.
4. Die Env-abhängigen Defaults (`LLM_ALLOW_PRIVATE_BASE_URL`, `DEBUG`, Cookie-/HSTS-Flags,
   Throttles) gelten nur bei `DJANGO_ENV` aus `_NON_PROD_ENVS` (`development`, `dev`,
   `local`, `test`). In Produktion ist der restriktive Zweig maßgeblich.

**Rollout-Gate (Shadowing vermeiden):** Die Flags werden nicht direkt in Produktion
umgeschaltet. Reihenfolge: Coverage-Gate grün (`persistence.E001` System-Check,
`backend/persistence/checks.py`; `test_rls_coverage.py`) → Staging mit RLS-enforced Rolle →
Abnahme → Produktion per IaC mit manuellem Approval-Gate. Ein direkter Prod-Change ohne
Staging ist unzulässig (Staging-Validierung, kein Bypass). Falls der Coverage-Gate vor dem
Go-Live nicht grün ist, gilt die Ausnahmeregel: Residenzrisiko im Risikoregister führen und
die Isolation vorläufig **explizit als app-layer-only** kommunizieren — nicht stillschweigend
weitermachen.

**Residualrisiken / Review-Grenzen:** DNS-Rebinding wird vom SSRF-Guard nicht abgedeckt
(`llm_adapter/url_guard.py`); die MFA-Härtung erfordert eine Enrollment-Welle, bevor
`required` sicher geschaltet werden kann. Die Fail-Open-Klassifikation dieser Tabelle wurde
gegen `security-auditor` (SEC-002) abgestimmt. Die **formelle Schließung** des Audit-Findings
erfolgt durch `security-auditor`/CCB — dieses Dokument liefert die vom Gate geforderte
explizite Wahl, ändert aber keinen Finding-Status.

## 4. Deprecations und Sunset-Referenzen

| Flag / Alias | Quelle | Nachfolger | Sunset / Datum | Status |
|---|---|---|---|---|
| `/api/v1/mcp/` (deprecated Alias) | `backend/reqogniloom/urls.py:82-87`; Header-Logik `backend/mcp_server/views.py:97-124` | kanonisch `/mcp/` | `2027-04-01` (`_LEGACY_MCP_PATH_SUNSET`, views.py:99-102) | aktiv deprecated; Antworten tragen `Deprecation: true`, `Sunset`, `Link: </mcp/>; rel="alternate"` (RFC 9745/8594) |
| `/health/` (deprecated Alias) | `backend/reqogniloom/health.py:16`; `settings.py:1183-1185` | `/health/ready`, `/health/live` | `HEALTH_ALIAS_SUNSET`, Default `2027-04-01` (ADR-010 §3) | aktiv deprecated; `Sunset`-Header via `health.py:1310-1330,1369` |
| Legacy Import Contract v1 | `settings.py:1533-1553` | `IMPORT_CONTRACT_V2=true` (Default, :1552) | `IMPORT_CONTRACT_SUNSET`, Default `2026-12-31` | aktiv deprecated; `Deprecation`/`Sunset` auf Legacy-Responses |
| `AUTH_LOGIN_INCLUDE_BODY_TOKEN` | `settings.py:1078-1087` | Token ausschließlich via Cookie/Refresh-Flow | **kein Datum gesetzt** — Kandidat nach Migration der In-Repo-Consumer (`e2e/helpers/auth.ts`, `e2e/helpers/preconditions.ts`) | Deprecation empfohlen (:1081-1084), noch kein Sunset-Header |
| `MCP_SERVICE_BACKED_QUERIES` | `settings.py:1556-1561` | Service-basierte Pfade (`application.user_query_service`, `change_impact_service`) | „eine Release“ (:1557-1558), kein fixes Datum | Rollback-Escape-Hatch, Default `true` |
| `RLS_AS_ENFORCED` / `RLS_PREAUTH_ENFORCED` | `settings.py:362-381` | dauerhaft `true` (siehe §3) | Ziel: Coverage-Gate in allen Umgebungen grün | temporäre Rollout-Dials, keine Header-Deprecation |
| `AUTHZ_WORKSPACE_SCOPE_ENFORCED` / `AUTHZ_API_KEY_WORKSPACE_FENCE_ENFORCED` | `settings.py:938-954` | dauerhaft `true` (ADR-011/013, SEC-03) | MigrationWindow / SECTRACK-01, kein fixes Datum | temporäre Rollback-Knobs |

**Hinweis:** `MCP_LEGACY_PATH_SUNSET` (views.py:100-121) ist ein *Django-Setting* per
`getattr`-Override, **kein** `config(...)`-Env-Key und deshalb nicht in der Key-Enumerierung
(§5) enthalten. Es wird hier als Sunset-Metadatum geführt, nicht als Konfigurationsschlüssel.

## 5. Authoritative Key-Enumerierung — Single Source

`scripts/check_env_example_keys.py` ist die **einzige** maßgebliche Instanz der
Schlüsselliste. Es leitet die Keys zur Laufzeit aus drei Quellen ab:

- `compose_keys()` — interpolierte Variablen aus `deploy/docker-compose*.yml` (:28, :53-63),
- `settings_keys()` — alle `config(...)`-Aufrufe in `settings.py` über Regex
  `_SETTINGS_KEY = re.compile(r"config\(\s*[\"']([A-Z0-9_]+)")` (:45, :66-71),
- `env_keys()` — aktive und kommentierte Einträge in `.env.example` (:30, :74-84).

Ein Key fehlt in `.env.example` (bzw. ist doppelt aktiv gesetzt) → Gate rot. Verdrahtung:
Unit-Tests in `scripts/test_check_env_example_keys.py` (CI `.github/workflows/ci.yml:431`),
Gate-Schritt `python scripts/check_env_example_keys.py` (`.github/workflows/ci.yml:444-447`).
Der Gate ist derzeit **grün**.

**Grenze des Gates:** Er prüft ausschließlich *Präsenz* und Duplikate — **nicht** Werte,
Defaults oder Produktiv-Haltung. Genau diese Lücke füllt §2/§3 dieser Datei.

**Regeln:**

1. Diese Datei darf die Key-Liste **nicht** manuell duplizieren. Bei neuen/umbenannten Keys
   werden Code und `.env.example` geändert; der Gate verifiziert. Danach werden nur die
   betroffenen Zeilen in §2/§4 nachgezogen.
2. Kein separater Loader, kein zweites Parsing, keine neue Abhängigkeit — der Gate ist der
   Drift-Gate; Provenance ist Dokumentation, nicht Runtime-Code.
3. Die `ALLOWLIST` im Skript (:32-39) ist die einzige erlaubte Ausnahme von der
   Dokumentationspflicht (aktuell: `COMPOSE_PROFILES`) und wird dort begründet, nicht hier.

## 6. Owner und Review

| Rolle | Verantwortung |
|---|---|
| `devops-engineer` | Owner dieses Dokuments; Default-Katalog, Produktiv-Haltung, Rollout-Gate, Review 2026-11-18. |
| `security-auditor` | Gegenreview der Fail-Open-Klassifikation (SEC-002) und der Paved-Road-Blöcke `auth-flow`, `rate-limiting`, `secret-scanning`; formelle Finding-Schließung via CCB. |
| `dependency-auditor` | `dependency-check` (SBOM + CVE) vor jedem Deploy — nicht Inhalt dieses Katalogs, aber Teil der Supply-Chain-Haltung. |

Änderungen an §2/§3 erfolgen ausschließlich auf `fix/infra-*` bzw. `fix/s5-3-*` Branches mit
Review; Produktiv-Umschaltungen der fail-open Knobs nur per IaC, über Staging und mit
manuellem Approval (siehe §3).
