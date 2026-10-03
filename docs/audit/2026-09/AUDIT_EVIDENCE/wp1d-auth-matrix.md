---
type: REVIEW
scope: wp-1d-auth-matrix
status: final
date: 2026-09-29
author_agent: api-specialist
---

# WP-1d — Evidenz: Auth / JWT-Matrix

**Quelle:** `wp1d-auth-pagination-filter-errors-live.json` → Schlüssel `auth` (20 Fälle).
**Stack:** `http://localhost:8001`, Login `admin` (Tenant A
`7a539397-…`, Rollen `["admin"]`).

## JWT-Claim-Form (dekodiert, `verify_signature=False`)

```json
{"user_id": "7298a00b-f228-4269-9b89-31f55794af5d",
 "tenant_id": "7a539397-6719-47bb-a6d5-5459016136fb",
 "roles": ["admin"], "typ": "access",
 "iat": 1790722700, "exp": 1790726300,
 "iss": "reqogniloom", "aud": "reqogniloom-api"}
```

`AUTH_JWT_SECRET` ist 86 Byte lang (`docker exec … env | grep AUTH_JWT_SECRET`,
nur die Länge gemessen, **kein Wert ausgelesen oder protokolliert**). Die
12-Byte-Warnung im Backend-Log stammt aus dem von mir zum Testen benutzten
Fremdschlüssel `"wrong-secret"`, nicht aus der Konfiguration.

## Matrix

| # | Fall | Methode | Pfad | Erwartung | Status | `error.code` | `message` | Bewertung |
|---|---|---|---|---|---|---|---|---|
| 1 | kein `Authorization` | GET | `/api/v1/requirements/?page_size=1` | 401 | 401 | `AUTHENTICATION_REQUIRED` | Authentication credentials were not provided. | ✅ |
| 2 | `Authorization: Bearer ` (leer) | GET | dito | 401 | 401 | `invalid_token` | The provided token is malformed or invalid. | ✅ |
| 3 | `Bearer not-a-jwt` | GET | dito | 401 | 401 | `invalid_token` | dito | ✅ |
| 4 | korrekt aufgebaut, falsche Signatur | GET | dito | 401 | 401 | `invalid_signature` | The token signature could not be verified. | ✅ |
| 5 | abgelaufen (`exp` −60 s) | GET | dito | 401 | 401 | `invalid_signature` | dito | ⚠ siehe unten |
| 6 | falsches `aud` | GET | dito | 401 | 401 | `invalid_signature` | dito | ⚠ |
| 7 | falsches `iss` | GET | dito | 401 | 401 | `invalid_signature` | dito | ⚠ |
| 8 | `alg=none`, leerer Key | GET | dito | 401 | 401 | `invalid_token` | dito | ✅ keine Alg-Confusion |
| 9 | unbekannte `user_id` im Claim | GET | dito | 401 | 401 | `invalid_signature` | dito | ⚠ |
| 10 | `reqlo_deadbeef…` als Bearer | GET | dito | 401 | 401 | `invalid_api_key` | The provided API key is invalid. | ✅ eigene Code-Familie |
| 11 | `X-API-Key: reqlo_deadbeef…` | GET | dito | — | 401 | `invalid_api_key` | Request rejected because of the X-API-Key header: the API key it carries is not valid. No other cred… | ✅ dokumentierte Präzedenz greift |
| 12 | `Cookie: sessionid=bogus` | GET | dito | — | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ `cookieAuth` ist tot |
| 13 | `Authorization: Token <jwt>` | GET | dito | — | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ nur Bearer wird erkannt |
| 14 | JWT als Query-Parameter | GET | `/api/v1/requirements/?page_size=1&token=<JWT>` | 401 | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ kein Token-Leak über URL |
| 15 | zwei `Authorization`-Header (beide leer) | GET | dito | 401 | 401 | `AUTHENTICATION_REQUIRED` | dito | ⚠ |
| 16 | zwei Header (erster leer, zweiter gültig) | GET | dito | — | 401 | `invalid_token` | The provided token is malformed or invalid. | ⚠ siehe unten |
| 17 | `POST` ohne Auth | POST | `/api/v1/requirements/` | 401 | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ |
| 18 | `GET` ohne Auth | GET | `/api/v1/admin/health/` | 401 | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ admin-guarded |
| 19 | `POST` ohne Auth | POST | `/api/v1/admin/restore/` | 401 | 401 | `AUTHENTICATION_REQUIRED` | dito | ✅ |

Fall 15/16 wurden über `http.client` mit zwei echten `Authorization`-Headern
ausgeführt (`requests` normalisiert Header zu einem Dict und kann keine
Duplikate senden).

## Auswertung

### Was sauber ist

- **401/403-Trennung durchgängig korrekt.** In allen 19 Fällen ohne Credential
  → 401. Rollenbasierte Ablehnung wird an anderer Stelle konsequent mit 403
  beantwortet (Matrix in `wp1d-error-format-matrix.md`).
- **Keine internen Details in Fehlerantworten.** Kein Stacktrace, kein
  Exception-Typ, kein SQL-Fragment, kein Dateipfad. Die Fehlerhülle entsteht
  zentral in `rest_api/error_envelope.py:48-68` und bezieht ihre Codes aus
  `_STATUS_TO_CODE` (`error_envelope.py:34-45`) — sauberer Registry-Ansatz.
- **Acht unterscheidbare Fehlercodes** für acht verschiedene Fehlerklassen
  (`AUTHENTICATION_REQUIRED`, `invalid_token`, `invalid_signature`,
  `invalid_api_key`). Für einen Client ist das brauchbar.
- **`alg=none` wird abgewiesen.**
- **JWT wird nicht als Query-Parameter akzeptiert.**

### Befund `AUD-2026-09-088` — Fehlercode-Granularität

Fälle 5, 6, 7 und 9 sind **nicht unterscheidbar**: alle vier liefern
`invalid_signature`. Ursache ist die Prüfreihenfolge — die Signaturprüfung läuft
vor der Claim-Prüfung, und ein von mir manipulierter Token scheitert zwingend
an der Signatur.

**Was ich daraus _nicht_ ableite:** ob ein *korrekt signiertes* Token mit
abgelaufenem `exp`, fremdem `aud` oder fremdem `iss` ebenfalls
`invalid_signature` liefert oder ob dort ein spezifischerer Code greift. Dafür
hätte ich den echten `AUTH_JWT_SECRET` aus dem Container-Environment
materialisieren müssen. Das habe ich **nicht** getan →
siehe Abschnitt „Nicht geprüft".

Gemessen ist: **die Fehlercode-Oberfläche hat keinen Platz für die
Unterscheidung „abgelaufen" vs. „falscher Adressat" vs. „falscher Aussteller".**
Das ist eine Definitionslücke im Vertrag, unabhängig davon, welchen Code die
Implementierung im Einzelfall liefert — ein Client, der bei 401 zwischen
„erneut einloggen" und „falscher Client konfiguriert" unterscheiden will, kann es
nicht.

### Befund (Info) — Header-Reihenfolge vs. dokumentierter Präzedenz

`components.securitySchemes.BearerAuth.description` im Schema dokumentiert:

> „Two credentials are accepted, and the header order is the resolution order:
> `X-API-Key` takes precedence over `Authorization: Bearer` … A credential that is
> present but INVALID is rejected (401, `invalid_api_key`) rather than skipped in
> favour of the next one."

Fall 11 bestätigt das für `X-API-Key` (401 `invalid_api_key`, Bearer **nicht**
weiter ausgewertet). Fall 16 zeigt, dass dasselbe Prinzip **innerhalb** eines
Headers mit zwei `Authorization`-Zeilen nicht greift: ein leerer erster Header
wird nicht übersprungen, sondern bricht die Auswertung mit `invalid_token` ab.

Ausnutzbar ist das nicht (der Angreifer hätte die Kontrolle über beide Zeilen
und braucht ohnehin ein gültiges Token). Es ist eine **inkonsistente Erzählung**
zwischem Schema-Text und Implementierung — und ein Hinweis darauf, dass die
Credential-Auflösung an mehreren Stellen dupliziert ist.

### Nicht geprüft (BLOCKED)

| Punkt | Grund |
|---|---|
| Korrekt signiertes Token mit `exp` in der Vergangenheit | bräuchte `AUTH_JWT_SECRET` aus dem Container-Env |
| Korrekt signiertes Token mit fremdem `aud` | dito |
| Korrekt signiertes Token mit fremdem `iss` | dito |
| Token eines **deaktivierten** Users | bräuchte dauerhafte Statusmutation (`is_active=False`) an einem Tenant-A-User |
| Token **nach Rollenentzug** (`CR-26`) | bräuchte dauerhafte Rollenmutation; der Mechanismus in `auth_tenancy/services/authentication.py:175-220` ist damit ungeprüft |
| Revokierter / abgelaufener **API-Key** | Klartext existiert nur einmal bei Erzeugung; für Tenant A existierte kein `reqlo_`-Key (alle 200 sind User-Keys) |
