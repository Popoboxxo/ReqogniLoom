---
type: RUNBOOK
title: "Produktions-Härtung: TLS, Cookies, HSTS und CSP"
status: aktiv
date: 2026-11-25
author_agent: senior-developer
language: de
scope: deploy, backend, ops
---

# Runbook: Produktions-Härtung (TLS, Cookies, HSTS, CSP)

Begleitdokument zu Arbeitspaket **P2.9** (Befund **m-14**, „HSTS/SSL/CSP nur
auskommentiert") aus `docs/plans/2026-11-25-rest-mcp-findings-umsetzungsplan.md`.

**Geltungsbereich:** Betreiber eines Deployments (Compose-Stack oder eigener
Host). Reine Betriebsdokumentation — dieses Runbook ändert keine Defaults.

**Verhältnis zu den anderen Dokumenten:**

| Dokument | Inhalt |
|---|---|
| `.env.example`, Block „TLS production block" | die **einzige** Vorlage mit Werten (alles auskommentiert) |
| dieses Runbook | die verbindliche Checkliste, Vorbedingungen und Reihenfolge |
| `docs/runbooks/secret-rotation.md` | Secrets (`API_KEY_PEPPER`, `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, Rotation) |
| `frontend/nginx-security-headers.conf` | CSP und Header der **SPA** (nicht `CSP_POLICY`) |

**Grundregel:** Keine echten Secrets, Hostnamen oder Zugangsdaten in diesem
Dokument. Werte stehen ausschließlich im deployment-seitigen Env-File.

---

## 1. Zwei Betriebsarten — und warum die Defaults so sind

Der mitgelieferte Compose-Stack fährt **Produktionsmodus ohne TLS-Terminierung**:
`DJANGO_ENV=production` erzwingt `DEBUG=False`, aber die TLS-abhängigen
Schalter bleiben auf ihren unsicheren, startfähigen Werten. Das ist Absicht:
Browsern verwerfen `Secure`-Cookies über `http://`, und ein HTTPS-Redirect ohne
Proxy macht das Deployment unerreichbar. Erst der Betreiber mit TLS-Terminator
darf diese Werte umstellen.

| Schalter | Default (Produktion) | Begründung |
|---|---|---|
| `SECURE_SSL_REDIRECT` | `False` | ohne TLS-Proxy würde jeder Request auf ein `https://` umgeleitet, auf dem nichts lauscht |
| `SECURE_PROXY_SSL_HEADER` | `None` bzw. `("HTTP_X_FORWARDED_PROTO", "https")`, **abgeleitet** aus `SECURE_SSL_REDIRECT` | nur ein Deployment, das den Redirect will, darf den Forwarded-Header vertrauen |
| `AUTH_COOKIE_SECURE` | `not DEBUG` → `True` | gilt für **beide** Auth-Cookies (Access + Refresh) |
| `CSRF_COOKIE_SECURE` | = `AUTH_COOKIE_SECURE` | Mismatch erzeugt 403 auf jedem UI-Write |
| `SESSION_COOKIE_SECURE` | = `AUTH_COOKIE_SECURE` | dito für die Session |
| `SECURE_HSTS_SECONDS` | `31536000` (1 Jahr) | in Produktion an; `0` schaltet HSTS ab |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | in Produktion an |
| `SECURE_HSTS_PRELOAD` | `True` | in Produktion an — siehe §5, das ist **kein** Freibrief |
| `CSP_POLICY` | `default-src 'self'; frame-ancestors 'none'; base-uri 'self'` | restriktiv, API-only-Backend |
| `SECURITY_STRICT_PRODUCTION_CHECKS` | `False` | `True` würde die unterstützte HTTP-only-Inbetriebnahme beim `migrate` abbrechen |

Quelle der Defaults: `backend/reqogniloom/settings.py` (Abschnitte „Security"
und „HSTS / Content-Security-Policy").

---

## 2. TLS-Terminator und Proxy-Header

Der Backend-Container spricht **HTTP**. TLS endet davor.

1. Terminator aufsetzen (nginx, Traefik, HAProxy, Cloud-Load-Balancer) und
   dorthin `X-Forwarded-Proto: https` weiterreichen. Der Header muss vom
   Terminator **gesetzt/überschrieben** werden — kommt er ungeprüft vom Client
   durch, ist er fälschbar.
2. `SECURE_SSL_REDIRECT=True` erst danach setzen. Die Settings leiten daraus
   `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` ab; ein
   Redirect ohne diesen Header führt zu einer Redirect-Schleife bzw. zu einer
   unerreichbaren `https://`-URL.
3. Host-/Origin-Listen auf die echten Browser-Origins stellen:
   `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` — Schema,
   Host und ggf. Port, **kein** `localhost`/`127.0.0.1`.
4. Health prüfen: `curl https://<host>/health/` — erwartet 200, und in der
   Advisory-Ausgabe `csrf_cookie_secure_matches_auth: "ok"`.

Ein nginx-Beispiel steht in `README.md` (§ „Reverse Proxy Setup"); die
Vorlage dort ist ein Muster, keine Zertifikats-/Hosting-Empfehlung.

---

## 3. Cookies: vier Cookies, drei Schalter, eine Regel

| Cookie | Zweck | Schalter |
|---|---|---|
| `reqogniloom_access` | Access-JWT, httpOnly | `AUTH_COOKIE_SECURE` |
| `reqogniloom_refresh` | Refresh-JWT, httpOnly, lange Laufzeit | `AUTH_COOKIE_SECURE` (derselbe Wert) |
| `csrftoken` | CSRF-Token für state-changing Requests | `CSRF_COOKIE_SECURE` |
| `sessionid` | Django-Session (Admin) | `SESSION_COOKIE_SECURE` |

**Must-Match-Regel:** `AUTH_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` und
`SESSION_COOKIE_SECURE` müssen **denselben** Wert haben. Ist einer `True` und
ein anderer `False` (oder unset und damit anders aufgelöst), schlägt **jeder**
UI-Write mit einem rohen Django-403-CSRF-Fehler fehl, obwohl die Session gültig
aussieht.

Prüfpunkt: `GET /health/` liefert im Advisory
`csrf_cookie_secure_matches_auth` — `"mismatch"` ist der Fehlerfall. Achtung:
dieser Health-Vergleich deckt **AUTH vs. CSRF** ab; `SESSION_COOKIE_SECURE`
folgt per Default `AUTH_COOKIE_SECURE`, kann aber unabhängig gesetzt werden und
ist deshalb manuell mitzuprüfen (die Startprüfung `W010` prüft alle drei).

Ohne TLS: alle drei bewusst `False` lassen (Default in der HTTP-Inbetriebnahme
über das dev-Overlay). Mit TLS: alle drei `True`.

---

## 4. HSTS

`SECURE_HSTS_SECONDS` sagt dem Browser, wie lange er diesen Host **nur** über
HTTPS ansprechen darf. Der Wert wird clientseitig gecacht — ein Fehler ist
nicht serverseitig korrigierbar.

Vorbedingungen:

- HTTPS ist der einzige Schemazugang dieses Hosts (Redirect steht, §2).
- Das Zertifikat ist gültig und bleibt es (Erneuerung automatisiert).
- Für `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`: **jeder** Subdomain-Host liefert
  HTTPS. Ein einzelner HTTP-only-Subdomain-Host wird sonst unerreichbar.
- Für `SECURE_HSTS_PRELOAD=True`: zusätzlich (a) stabile Header über einen
  ausreichend langen Zeitraum, (b) keine geplante Rückkehr zu HTTP,
  (c) die Domain ist tatsächlich in die Browser-Preload-Listen eingetragen
  (der Header allein bewirkt die Aufnahme nicht).

Empfohlene Reihenfolge beim Rollout: Redirect → kurze `max-age` (z. B. 300 s)
→ beobachten → `31536000` → `INCLUDE_SUBDOMAINS` → ggf. `PRELOAD`. Die
Header-Werte aus §1 (`PRELOAD=True`) sind der Produktions-Default; ein
kontrollierter Rollout setzt deshalb bewusst `SECURE_HSTS_PRELOAD=False`, bis
die drei Bedingungen erfüllt sind.

**Startprüfung:** `reqogniloom.W013` meldet `SECURE_HSTS_SECONDS<=0`. In einer
Produktionskonfiguration ist `DEBUG` erzwungen `False`, also ist der Default
`31536000` — der Befund entsteht nur, wenn jemand explizit `0` setzt (oder
einen nicht-numerischen Wert, der als `0` gelesen wird). Ein separater Fehlercode
existiert für diesen Zustand nicht.

---

## 5. Content-Security-Policy: zwei getrennte Policies

Es gibt **zwei** CSPs, die nichts miteinander zu tun haben:

| Policy | Wo konfiguriert | Gilt für |
|---|---|---|
| Backend-CSP | `CSP_POLICY` (Settings) | Antworten des Backends: API, `/health/`, Django-Admin |
| SPA-CSP | `frontend/nginx-security-headers.conf` (nginx `add_header`) | die React-Oberfläche aus dem Frontend-Container |

**Backend-CSP.** `reqogniloom.security_middleware.ContentSecurityPolicyMiddleware`
schreibt `settings.CSP_POLICY` unverändert in den Header
`Content-Security-Policy`. Default:
`default-src 'self'; frame-ancestors 'none'; base-uri 'self'`.

- Variable **weglassen** = Default gilt. Das ist der empfohlene Zustand.
- Erweitern nur bei konkretem Bedarf (z. B. eine zusätzliche `connect-src`-Origin)
  und den Wert in Anführungszeichen setzen, damit Semikolons/Leerzeichen den
  Parser überstehen: `CSP_POLICY="default-src 'self'; connect-src 'self' https://api.example.com; frame-ancestors 'none'; base-uri 'self'"`
- **Leerer Wert** (`CSP_POLICY=`) ist der einzige Weg, den Schutz still
  abzuschalten: der Header wird dann mit leerem Wert gesendet und beschränkt
  nichts. Das meldet `reqogniloom.W014` (strikt: `E014`).

**SPA-CSP.** Wird mit dem Frontend ausgeliefert und ist **nicht** über
`CSP_POLICY` änderbar. `frontend/scripts/check-nginx-headers.sh` bzw. der
CI-Job `nginx-headers-smoke` verbieten `'unsafe-inline'`/`'unsafe-eval'` in
`script-src`. Braucht die SPA eine zusätzliche Quelle, gehört die Änderung in
diese nginx-Konfiguration — nicht in `CSP_POLICY`.

---

## 6. `SECURITY_STRICT_PRODUCTION_CHECKS`

`False` (**Default**): `W010`–`W014` bleiben Warnungen, das Deployment startet.
`True`: dieselben Befunde werden zu `E010`–`E014` und stoppen `migrate` und
`runserver`.

Wann `True`: gehärtete Deployments und CI, die die TLS-Werte **verpflichtend**
haben wollen. Wann nicht: die dokumentierte HTTP-only-Inbetriebnahme — dort
würden `W010`/`W013` zu Errors und der erste `migrate` bricht ab.

Der Default bleibt bewusst `False`; ein `True`-Default wäre eine stille
Verhaltensänderung an einer unterstützten Betriebsart.

---

## 7. Check-ID-Tabelle

Die Checks liegen in `backend/reqogniloom/checks.py`, werden über
`RestApiConfig.ready` registriert und laufen bei `manage.py check`,
`runserver` und im einmaligen `migrate`-Container — vor dem ersten Request.
Sie sind nur im Produktionskontext aktiv (`DJANGO_ENV` nicht in
`{development, dev, local, test}` **und** `DJANGO_SETTINGS_MODULE` nicht
`…settings_test`).

| Code | Schwere | Befund | Abhilfe |
|---|---|---|---|
| `reqogniloom.E001` | **Error** | `API_KEY_PEPPER` fehlt/leer in Produktion | `bash scripts/setup.sh` — Details: `secret-rotation.md` §2 |
| `reqogniloom.E002` | **Error** | `API_KEY_PEPPER` schwach/Platzhalter | Wert ersetzen (Rotation!) — `secret-rotation.md` §4 |
| `reqogniloom.W010` | Warning | einer der drei Cookie-Schalter `False` | §3 — mit TLS alle drei `True` **und gleich** |
| `reqogniloom.W011` | Warning | `localhost`/`127.0.0.1` in `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` | §2 Punkt 3 |
| `reqogniloom.W012` | Warning | `SYSTEM_ADMIN_PASSWORD` nicht-leer, aber trivial (leer = **kein** Befund) | starken Wert setzen oder Variable entfernen |
| `reqogniloom.W013` | Warning | `SECURE_SSL_REDIRECT=False` **oder** `SECURE_HSTS_SECONDS<=0` | §2, §4 |
| `reqogniloom.W014` | Warning | `CSP_POLICY` leer/blank im Produktionskontext | §5 — Variable entfernen (Default) oder Policy setzen |
| `reqogniloom.E010`–`E014` | **Error** | dieselben Befunde, eskaliert | `SECURITY_STRICT_PRODUCTION_CHECKS=True` (§6) |

Jede Meldung nennt nur den **Variablennamen** und die Abhilfe, niemals den Wert
— die Ausgabe landet in Container-Logs, CI-Logs und Bug-Reports.

**Reichweite, präzise:** ein Error blockiert jeden Prozess, der die
Django-System-Checks ausführt. Ein nackter ASGI-/gunicorn-Start ohne
vorherigen Check-Schritt kommt auch mit einer fehlerhaften Konfiguration hoch —
das ist ein dokumentiertes Restrisiko (`secret-rotation.md` §2), keine Garantie.

---

## 8. Matrix: lokale Entwicklung vs. Produktion hinter TLS

| Punkt | Lokal / HTTP-Dev (Compose-Default) | Produktion hinter TLS |
|---|---|---|
| `DJANGO_ENV` | `development` (dev-Overlay) | `production` |
| `DEBUG` | via Overlay erlaubt | erzwungen `False` |
| `SECURE_SSL_REDIRECT` | `False` | `True` (nur mit Proxy, §2) |
| `SECURE_PROXY_SSL_HEADER` | `None` | abgeleitet: `X-Forwarded-Proto: https` |
| Cookie-Schalter | alle `False` (sonst Login kaputt) | alle `True`, untereinander gleich |
| HSTS | `0` / aus | `31536000`, `INCLUDE_SUBDOMAINS` nach §4 |
| Backend-CSP | Default | Default (nur bei Bedarf erweitert) |
| Origin-Listen | `localhost`/`127.0.0.1` erlaubt | nur echte Origins |
| `SECURITY_STRICT_PRODUCTION_CHECKS` | `False` | `True` (empfohlen) |
| `manage.py check` | grün, ohne TLS-Warnungen (dev-Kontext) | grün **oder** bewusst akzeptierte Warnungen |

Wichtig: die lokale Spalte ist kein „unsicherer Modus", sondern der Preis
dafür, dass die dokumentierte Inbetriebnahme über `http://` funktioniert
(Browser verwerfen `Secure`-Cookies dort).

---

## 9. Vor dem ersten HTTPS-Start

In dieser Reihenfolge abarbeiten — jede Zeile einzeln prüfbar:

- [ ] TLS-Terminator steht, gültiges Zertifikat, Erneuerung automatisiert.
- [ ] Terminator sendet `X-Forwarded-Proto: https` und überschreibt einen
      clientseitig gesendeten Wert.
- [ ] `ALLOWED_HOSTS` nennt die echten Hostnamen (kein `localhost`).
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` nennen die echten
      Browser-Origins (Schema + Host + Port).
- [ ] `SECURE_SSL_REDIRECT=True` gesetzt (erst jetzt).
- [ ] `AUTH_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`,
      `SESSION_COOKIE_SECURE=True` — identisch.
- [ ] `SECURE_HSTS_SECONDS=31536000`; `SECURE_HSTS_INCLUDE_SUBDOMAINS` nur,
      wenn alle Subdomains HTTPS können; `SECURE_HSTS_PRELOAD` nach §4.
- [ ] `CSP_POLICY` nicht leer (Variable entfernen ist der Normalfall).
- [ ] `SECURITY_STRICT_PRODUCTION_CHECKS=True` für gehärtete/CI-Deployments.
- [ ] Secrets erzeugt und rotiert nach `secret-rotation.md`.
- [ ] Container **neu erzeugen** (`up -d`), nicht `restart` — `env_file` wird
      beim Erzeugen gelesen.
- [ ] `manage.py check` zeigt keine `reqogniloom.W01x`/`E01x` mehr, die nicht
      bewusst akzeptiert sind.
- [ ] `curl https://<host>/health/`: 200,
      `csrf_cookie_secure_matches_auth: "ok"`.
- [ ] Login im Browser über `https://` funktioniert; ein UI-Write
      (z. B. ein Kommentar) geht ohne 403 durch.
- [ ] Antwort-Header stichprobenartig prüfen: `Strict-Transport-Security`,
      `Content-Security-Policy`, `X-Frame-Options: DENY`,
      `X-Content-Type-Options: nosniff` — auf Backend **und** SPA.

---

## 10. Rückweg (wenn HTTPS wieder weg muss)

Reihenfolge umgekehrt, und in dieser Reihenfolge zwingend:

1. `SECURE_HSTS_PRELOAD=False`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=False`,
   `SECURE_HSTS_SECONDS` schrittweise auf `0`.
2. `SECURE_SSL_REDIRECT=False`.
3. Cookie-Schalter auf `False`.
4. Erst danach TLS am Terminator abbauen.

Grund: ein bereits ausgelieferter HSTS-Header wirkt im Browser weiter, bis
seine `max-age` abgelaufen ist. Wer die Reihenfolge umdreht, sperrt
Client-Browser von einem Host aus, der wieder HTTP spricht.
