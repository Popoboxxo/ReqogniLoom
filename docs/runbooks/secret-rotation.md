---
type: RUNBOOK
title: "Secret-Rotation und Produktionskonfiguration"
status: aktiv
date: 2026-11-25
author_agent: senior-developer
language: de
scope: deploy, backend, ops
---

# Runbook: Secret-Rotation und Produktionskonfiguration

Begleitdokument zu den Arbeitspaketen **P1.1** (Produktionskonfiguration/Secrets
härten) und **P1.3** (`API_KEY_PEPPER` im Produktionsbetrieb erzwingen) aus
`docs/plans/2026-11-25-rest-mcp-findings-umsetzungsplan.md`.

**Geltungsbereich:** Betreiber des Deployment (Compose-Stack oder eigener
Host). Reine Betriebsdokumentation — sie ändert nichts am Code.

**Grundregel:** Reale Secrets liegen ausschließlich in der lokalen/deployment-
seitigen `.env` (git-ignoriert) bzw. im Secret-Store des Hosts. Sie werden
**nie** in das Repository geschrieben, nicht in Tickets kopiert und nicht in
Chat-/Agenten-Sessions ausgegeben. Backups eines Env-Files gehören **außerhalb**
des Checkouts (der Vorfall vom 2026-10-21 war genau eine `.env.bak` im Repo).

---

## 1. Template-Entscheidung: eine einzige Vorlage

Es gibt **genau eine** Vorlage: `.env.example` im Repository-Wurzelverzeichnis.
Ein `deploy/.env.example` existiert in diesem Repository **nicht** und wird
bewusst **nicht** angelegt (Abweichung von der Dateiliste des Plans in §5/§7,
dort noch als zweite Datei genannt). Begründung:

- Beide Compose-Varianten (`deploy/docker-compose.yml`, `…minimal.yml`,
  `…override.yml`) lesen dieselbe `.env` über `env_file:`; eine zweite Vorlage
  könnte nur auseinanderlaufen.
- Der Plan selbst verlangt „Templates ohne echte Secrets, ohne `admin`-Passwort
  und mit leeren Pflichtfeldern" — das erfüllt eine einzige gepflegte Datei
  vollständiger als zwei halb gepflegte.
- `scripts/setup.sh` liest den Pfad fest aus `$REPO_ROOT/.env.example`; eine
  zweite Vorlage hätte keinen Konsumenten.

`.env.example` enthält nur Platzhalter (`CHANGE-ME-…`) bzw. bewusst **leere**
Pflichtfelder (`API_KEY_PEPPER=`, `SYSTEM_ADMIN_PASSWORD=`) — niemals einen
echten Wert und niemals das Passwort `admin`.

Die beiden leeren Felder haben **unterschiedliche** Semantik, beide sind bewusst
so gewählt:

| Feld | leer bedeutet | nicht-leer, aber trivial bedeutet |
|---|---|---|
| `API_KEY_PEPPER` | Fehlt im Produktionskontext → `reqogniloom.E001` (Startabbruch). Muss erzeugt werden. | `reqogniloom.E002` (Startabbruch). |
| `SYSTEM_ADMIN_PASSWORD` | **Kein** Admin-Konto wird angelegt; der Stack startet normal (die dokumentierte „optional"-Betriebsart). | `migrate` bricht fail-closed ab (`ImproperlyConfigured`) — gewollt, ein Platzhalter ist eine übersehene Lücke, „leer" ist eine Entscheidung. |

---

## 2. Startprüfungen (`manage.py check`)

Die Checks liegen in `backend/reqogniloom/checks.py` und werden in
`RestApiConfig.ready` registriert. Sie laufen damit bei `manage.py check`,
`runserver` **und** im einmaligen `migrate`-Container — also vor dem ersten
Request. Sie sind ausschließlich im Produktionskontext aktiv:

> **Reichweite, präzise:** Ein `Error` aus einem System-Check blockiert **jeden
> Prozess, der die Django-System-Checks ausführt** (`manage.py check`,
> `runserver`, der `migrate`-Container). Er macht „Produktion ohne Pepper"
> **nicht unmöglich**: ein nackter ASGI-/gunicorn-Start ohne vorgeschalteten
> Check-Schritt (`gunicorn reqogniloom.asgi:application` direkt) käme ohne
> Pepper hoch. Das ist ein dokumentiertes Restrisiko, keine Garantie — und genau
> deshalb steht hier kein stärkerer Anspruch.
>
> Bewusst **kein** Runtime-Guard in `hash_api_key`: dieselbe Funktion wird von
> `api_key_hash_candidates` benutzt, um die **Legacy**-Form `sha256:` zu prüfen,
> und von `auth_tenancy.services.mfa` für Recovery-Codes. Ein Runtime-Fehler
> dort würde die API-Key-Authentifizierung **aller** bestehenden Deployments
> brechen — aus einer Konfigurationswarnung würde ein Login-Ausfall. Der
> Startcheck ist der Durchsetzungspunkt.

> **Optionale Nachschärfung (follow-up, nicht umgesetzt).** Wäre zusätzlich ein
> Runtime-Guard gewünscht, gehört er auf den **Erzeugungspfad**:
> `AuthenticationService.create_api_key` kann den Pepper verlangen, sobald ein
> neuer Key ausgestellt wird — dort gibt es keinen Bestand zu brechen, ein
> fehlender Pepper verhindert nur das Ausstellen eines *neuen* Keys, und kein
> laufender Login wird invalidiert. Ausdrücklich **nicht** in `hash_api_key`:
> dieselbe Funktion trägt die Legacy-Verifikation (`api_key_hash_candidates`)
> und das Hashen der MFA-Recovery-Codes, deshalb ist sie der falsche Ort für
> eine Konfigurationszusage.

> `DJANGO_ENV` **nicht** in `{development, dev, local, test}` **und**
> `DJANGO_SETTINGS_MODULE` ist nicht `…settings_test`.
>
> Dieselbe Regel wie `reqogniloom/settings.py::_is_production_secret_context`.
> Entwicklung, Tests und CI (`settings_test`) bleiben unberührt.

| Code | Schwere | Bedeutung | Abhilfe |
|---|---|---|---|
| `reqogniloom.E001` | **Error** | `API_KEY_PEPPER` fehlt/leer im Produktionskontext. | `bash scripts/setup.sh` (füllt ein leeres `API_KEY_PEPPER`), sonst `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Danach Deployment neu erzeugen (`up -d`, nicht `restart` — `env_file` wird beim Container-Erzeugen gelesen). |
| `reqogniloom.E002` | **Error** | `API_KEY_PEPPER` gesetzt, aber schwach: < 32 Zeichen oder mit `change-me`/`placeholder`/`dev-secret`-Marker. | Wert ersetzen (siehe E001). Achtung: das rotiert den Pepper → siehe §4.3. |
| `reqogniloom.W010` | Warning | `AUTH_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` oder `SESSION_COOKIE_SECURE` ist `False`, obwohl Produktion. | Hinter TLS alle drei auf `True` **und untereinander gleich** setzen. Ohne TLS bewusst `False` lassen (Browser verwerfen `Secure`-Cookies über `http://`). |
| `reqogniloom.W011` | Warning | `CORS_ALLOWED_ORIGINS` oder `CSRF_TRUSTED_ORIGINS` enthält `localhost`/`127.0.0.1`. | Durch die echten Browser-Origins ersetzen (Schema + Host + Port), z. B. `https://app.example.com`. |
| `reqogniloom.W012` | Warning | `SYSTEM_ADMIN_PASSWORD` ist **nicht-leer**, aber kürzer als 8 Zeichen, ein bekannter Trivialwert oder mit Platzhalter-Marker. Ein **leerer** Wert erzeugt **keinen** Befund (das ist der gewünschte Endzustand nach dem Bootstrap). | Starken Wert setzen — **oder die Variable entfernen** (leer = kein Admin wird angelegt). Ein solcher Wert lässt `migrate` auf einer frischen DB ohnehin abbrechen, deshalb eskaliert er in `SECURITY_STRICT_PRODUCTION_CHECKS=True` zu `E012`. |
| `reqogniloom.W013` | Warning | `SECURE_SSL_REDIRECT` ist `False` **oder** `SECURE_HSTS_SECONDS` ist `0`. | Nur setzen, wenn ein TLS-terminierender Proxy davorsteht (sonst wird das Deployment unerreichbar). HSTS erst zusammen mit dem Redirect aktivieren. |
| `reqogniloom.W014` | Warning | `CSP_POLICY` ist im Produktionskontext leer/blank — der `Content-Security-Policy`-Header wird dann ohne jede Policy ausgeliefert und beschränkt nichts. | Variable **entfernen** (dann greift der mitgelieferte restriktive Default `default-src 'self'; frame-ancestors 'none'; base-uri 'self'`) oder `CSP_POLICY` auf eine eigene Policy setzen. Eskaliert in `SECURITY_STRICT_PRODUCTION_CHECKS=True` zu `E014`. |
| `reqogniloom.E010`–`E014` | **Error** | Wie W010–W014, aber eskaliert. | `SECURITY_STRICT_PRODUCTION_CHECKS=True`. |

Jede Meldung nennt ausschließlich den **Variablennamen** und die Abhilfe,
niemals den Wert — die Ausgabe landet in Container-Logs, CI-Logs und
Bug-Reports.

### `SECURITY_STRICT_PRODUCTION_CHECKS`

`False` (Default) → W010–W014 bleiben Warnungen, das Deployment startet.
`True` → dieselben Befunde werden zu Errors und stoppen `migrate`/`runserver`.

Warum der Default `False` ist: der mitgelieferte Compose-Stack unterstützt
Produktionsmodus **ohne** TLS-Terminierung (siehe die Cookie-Kommentare in
`.env.example`). Ein `True`-Default würde die dokumentierte HTTP-only-
Inbetriebnahme beim nächsten `migrate` abbrechen. Für gehärtete Deployments und
CI ist `True` die richtige Wahl.

---

## 3. Werte erzeugen und pflegen

```bash
bash scripts/setup.sh                 # <repo>/.env, interaktiv nichts
bash scripts/setup.sh --env-file /pfad/zu/prod.env
bash scripts/setup.sh --check-ports   # zusätzlich Host-Ports prüfen
```

Das Skript

- legt die Zieldatei aus `.env.example` an, wenn sie fehlt;
- generiert **nur** `CHANGE-ME`-Platzhalter **sowie** zwei bewusst leer
  ausgelieferte Schlüssel, wenn sie vorhanden und leer (oder nur aus Leerzeichen
  bestehend) sind: `API_KEY_PEPPER` (P1.3) und `SYSTEM_ADMIN_PASSWORD` (P1.1).
  Ein bereits gesetzter Wert wird **nie** überschrieben;
- sichert eine schon existierende Datei ausschließlich **außerhalb** des Repos
  (`${XDG_STATE_HOME:-$HOME/.local/state}/reqogniloom/env-backups/…`, Mode 600);
- setzt Mode 600 auf die Zieldatei und bricht mit Exit 3 ab, wenn ein Ziel
  **innerhalb** des Repos liegt und nicht git-ignoriert ist (damit Secrets nicht
  einen `git add -A` entfernt sind);
- generiert bewusst **keine** optionalen Secrets (`REDIS_PASSWORD`,
  `HONCHO_WEBHOOK_SECRET`, `IMPORT_FINGERPRINT_SECRET`, `QDRANT_API_KEY`, …):
  leer bedeutet dort eine dokumentierte, gültige Betriebsart (kein
  `requirepass`, Webhook-Empfänger deaktiviert).

---

## 4. Rotation: Reihenfolge und Blast Radius

### 4.1 Reihenfolge (Empfehlung)

1. **`FIELD_ENCRYPTION_KEY`** — zuerst, weil sie Daten *at rest* betrifft und
   eine Rotation ohne Re-Encrypt bestehende `LlmSettings.api_key`-Werte
   unlesbar macht. Nur mit Re-Encrypt-Verfahren rotieren (siehe 4.5).
2. **`DB_PASSWORD`** (Superuser/`migrate`-Rolle) und **`DB_APP_PASSWORD`**
   (Laufzeitrolle) — getrennt voneinander, jeweils mit `up -d` (nicht
   `restart`), damit `migrate`/`backend`/`celery` mit dem neuen Passwort
   authentifizieren.
3. **`REDIS_PASSWORD`** — Broker/Backend für Celery und Cache. Reihenfolge:
   Redis mit neuem `requirepass` starten, dann `backend`/`celery`/`celery-beat`
   neu erzeugen. Ein leerer Wert ist die dokumentierte „kein requirepass"-
   Betriebsart.
4. **`SECRET_KEY`** — bricht MFA-Challenges, Workflow-Siegel
   (`workflow/signature_gate.py`) und Import-Idempotenz-Fingerprints; MFA-
   Nutzer müssen sich neu enrolieren bzw. neu anmelden.
5. **`AUTH_JWT_SECRET`** — invalidiert **alle** Access- und Refresh-Tokens:
   jeder Nutzer wird ausgeloggt (kontrolliert, per Silent-Refresh schlägt der
   Refresh fehl → Login erforderlich). Am besten in einem Wartungsfenster.
6. **`API_KEY_PEPPER`** — invalidiert **alle peppered** API-Keys; Clients müssen
   neu ausgestellt bekommen (siehe 4.3). Nach `AUTH_JWT_SECRET`, weil
   API-Keys typischerweise Agenten/CI betreffen und separat koordiniert werden.
7. **`SYSTEM_ADMIN_PASSWORD`** — nur relevant beim Anlegen oder bei
   `python manage.py bootstrap_admin --reset-password` (das zusätzlich **alle**
   Refresh-Sessions des Kontos widerruft).

### 4.2 Blast-Radius-Tabelle

| Variable | Sofortige Wirkung bei Änderung | Nutzer-/Client-Wirkung | Rückrollbar? |
|---|---|---|---|
| `SECRET_KEY` | MFA-Challenges, Workflow-Siegel, Import-Fingerprints werden ungültig | MFA-Neuanmeldung/-Enrollment; laufende Import-Idempotenz verliert ihre Wiedererkennung (Re-Import kann Duplikate erzeugen) | ja (alten Wert zurück), solange keine neuen Siegel entstanden sind |
| `AUTH_JWT_SECRET` | alle JWTs ungültig | jeder Nutzer wird ausgeloggt; API-Keys sind **nicht** betroffen | ja (alter Wert stellt alte Tokens wieder her — nur innerhalb deren TTL sinnvoll) |
| `API_KEY_PEPPER` | jeder `sha256p1:`-Hash passt nicht mehr | **jeder** peppered API-Key → 401; Clients brauchen neue Keys | nein (alter Pepper stellt alte Keys nur wieder her, wenn man ihn zurückrollt — dann ist die Rotation wirkungslos) |
| `DB_PASSWORD` | `migrate` kann sich nicht mehr verbinden | Deployment-Start scheitert | ja |
| `DB_APP_PASSWORD` | Laufzeit-Rolle authentifiziert nicht mehr | alle Requests 5xx | ja |
| `REDIS_PASSWORD` | Celery/Cache können sich nicht verbinden | async Tasks/Cache degradiert (dokumentierter Fail-open für Rate-Limits) | ja |
| `FIELD_ENCRYPTION_KEY` | bestehende Ciphertexte (`LlmSettings.api_key`) sind nicht mehr entschlüsselbar | LLM-Features fallen auf „nicht konfiguriert" zurück; Keys müssen neu eingetragen werden | nur, wenn der alte Key aufbewahrt wurde **und** keine neuen Werte unter dem neuen Key geschrieben wurden |
| `SYSTEM_ADMIN_PASSWORD` | nur beim Anlegen/Reset | Admin-Login mit neuem Passwort; Sessions werden beim Reset widerrufen | ja (Reset erneut) |

### 4.3 `API_KEY_PEPPER` im Detail (P1.3)

- **Neue Keys** werden als `sha256p1:<hmac>` gespeichert (HMAC-SHA256 mit dem
  Pepper als Schlüssel).
- **Alte Keys** bleiben im Format `sha256:<digest>` lesbar und
  authentifizieren weiter. Das Präfix unterscheidet die Variante — deshalb ist
  **keine Schema-Migration** nötig.
- Diese Alt-Hashes sind **Rotationskandidaten, keine Dauerlösung**: sie tragen
  den ursprünglichen Risikozustand (ein DB-Dump genügt zum Offline-Test). Ziel
  ist, dass jeder Client irgendwann einen `sha256p1:`-Key besitzt.
- **Pepper rotieren** = jeder peppered Key wird ungültig. Ablauf:
  1. neue Keys für alle Clients vorab ausstellen (alte bleiben gültig),
  2. Pepper setzen/ändern, Deployment neu erzeugen,
  3. Clients umstellen,
  4. alte Keys widerrufen.
  Ein „einfach umstellen" ohne Schritt 1 ist ein Ausfall für jeden Agenten/CI-Job.
- Der Pepper gehört **nicht** in die Datenbank und **nicht** ins Image — nur in
  die Umgebung des Deployments.

### 4.4 `SYSTEM_ADMIN_PASSWORD` (P1.1)

- Wird **nur** gelesen, wenn das Admin-Konto angelegt wird, oder bei
  `python manage.py bootstrap_admin --reset-password`.
- Untergrenze (neu): ≥ 8 Zeichen, kein Trivialwert aus
  `admin`/`password`/`changeme`/`change-me`/`letmein`/`12345678`/`qwerty`/
  `admin123`, kein `change-me`/`changeme`/`placeholder`-Marker.
  Ein abgelehnter Wert führt zu `CommandError` (Kommando) bzw.
  `ImproperlyConfigured` (Self-Init beim `migrate` einer **frischen** DB) — ohne
  den Wert zu wiederholen.
- Die Django-`AUTH_PASSWORD_VALIDATORS` bleiben für diesen Operator-Pfad
  bewusst außen vor (Disaster Recovery); die Untergrenze ist nur ein Floor.
- **Leer ist der gewünschte Endzustand.** Sobald das Admin-Konto existiert, darf
  die Variable vollständig entfernt werden: sie wird dann nie gelesen, und der
  Startcheck meldet für einen leeren Wert **nichts** (kein `W012`, in
  `SECURITY_STRICT_PRODUCTION_CHECKS=True` auch kein `E012`).
- Ein **nicht-leerer** Trivial-/Platzhalterwert in der `.env` bleibt zur Laufzeit
  folgenlos, solange kein Passwort geschrieben wird (create-only), wird aber als
  `W012` gemeldet — und lässt `migrate` auf einer **frischen** DB abbrechen
  (fail-closed). Deshalb: entweder starker Wert oder Variable entfernen.

### 4.5 `FIELD_ENCRYPTION_KEY` (Re-Encrypt)

Ein Wechsel ohne Re-Encrypt macht vorhandene `LlmSettings.api_key`-Werte
unlesbar. Vorgehen: alten Key behalten, unter neuem Key neu verschlüsseln
(Admin-Oberfläche: LLM-Einstellungen erneut speichern), erst danach den alten
Key aus der Umgebung entfernen. Bis dahin müssen beide Prozesse denselben Key
sehen — deshalb immer zuerst `migrate`/`backend` gemeinsam neu erzeugen.

---

## 5. Ablauf einer Rotation (Kurzform)

1. Wartungsfenster/Ankündigung festlegen (relevant für `AUTH_JWT_SECRET`,
   `API_KEY_PEPPER`).
2. Backup **außerhalb** des Repos anlegen (`scripts/setup.sh` macht das
   automatisch für eine existierende Datei; zusätzlich einen vollständigen
   DB-Dump ziehen).
3. Neue Werte erzeugen (`bash scripts/setup.sh` bzw. die dokumentierten
   `python -c`-Einzeiler) und **nur** in die Ziel-Umgebung schreiben.
4. `docker compose … up -d` (nicht `restart` — `env_file` wird beim Erzeugen
   gelesen). `migrate` läuft dabei erneut und führt die Startprüfungen aus.
5. Verifikation: `GET /health/` (inkl. `csrf_cookie_secure_matches_auth`),
   Login, ein `POST` über die UI, ein MCP-Tool-Call mit API-Key.
6. Betroffene Clients über ungültige Keys/Tokens informieren (4.2).
7. Alte Werte sicher löschen; Rollback-Werte nur so lange aufbewahren, wie der
   Rollback sinnvoll ist.

---

## 6. Offene manuelle Restpunkte (nicht durch diesen Lauf erledigt)

Diese Punkte sind **Betreiber-Aufgaben** und wurden bewusst nicht automatisiert:

1. **`API_KEY_PEPPER` setzen, bevor der Stack das nächste Mal neu erzeugt wird.**
   Seit P1.3 ist ein leeres `API_KEY_PEPPER` im Produktionskontext ein
   **Error** (`reqogniloom.E001`), d. h. der `migrate`-Container verweigert den
   Start, bis der Wert existiert. Abhilfe ist ein Befehl:
   `bash scripts/setup.sh` (füllt ein leeres `API_KEY_PEPPER` in der Zieldatei,
   überschreibt nichts anderes) — danach `up -d`.
   **Wichtig:** das *erstmalige* Setzen invalidiert **keine** bestehenden
   API-Keys. Vorhandene Keys liegen als Legacy-`sha256:`-Hashes vor und bleiben
   lesbar; nur neu erzeugte Keys werden peppered (und nur die würden von einer
   *späteren* Rotation betroffen). Wird nichts gesetzt, startet der
   **Compose-Stack** nicht mehr — sein `migrate`-Container führt die
   System-Checks aus und bricht ab (die gewollte fail-closed-Semantik, aber der
   Reihenfolge nach eine Betreiber-Entscheidung). Das gilt **nicht** für einen
   Backend-only-Start ohne Check-Schritt (nacktes
   `gunicorn reqogniloom.asgi:application`), der ohne Pepper hochkäme — siehe
   die Reichweite in §2.
2. **Reale Secrets der lokalen `.env` rotieren** — außerhalb des Repos, mit
   dem Ablauf aus §5. Der Agenten-Lauf hat die Datei weder gelesen noch
   verändert; es wurden keine Werte generiert, ausgegeben oder gesichert.
3. **`SYSTEM_ADMIN_PASSWORD` prüfen.** Falls in der Deployment-`.env` noch ein
   Trivialwert gesetzt ist (z. B. `admin`), ist er die schwächste Stelle des
   Stacks — dann stark setzen und bewusst entscheiden:
   - wenn das Admin-Konto bereits existiert, ändert die Variable allein **nichts**
     (create-only) — das Passwort muss über die UI oder
     `python manage.py bootstrap_admin --reset-password` gesetzt werden
     (letzteres widerruft alle Refresh-Sessions des Kontos);
   - die Variable danach auf den starken Wert setzen — oder **entfernen**, denn
     leer bedeutet „kein Admin wird angelegt" und ist der gewünschte Endzustand
     (Startcheck: kein `W012`, auch nicht in Strict-Mode).
   Ist der Wert nicht-leer und trivial, meldet der Startcheck `W012` (bzw.
   `E012` bei `SECURITY_STRICT_PRODUCTION_CHECKS=True`) und `migrate` bricht auf
   einer frischen DB ab. Ob ein solcher Wert in einer bestimmten Umgebung
   tatsächlich gesetzt ist, lässt sich nur dort prüfen — diese Runbook-Aussage
   behauptet es für keine Umgebung.
4. **`DJANGO_ENV` des lokalen Stacks überprüfen** — erst **nach** der Rotation
   entscheiden, ob der Stack weiter mit `DJANGO_ENV=production` läuft
   (dann sind `AUTH_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/
   `SESSION_COOKIE_SECURE=False` und `localhost` in den Origins nur noch
   Warnungen, die man bewusst akzeptiert bzw. beseitigt) oder ob er auf
   `DJANGO_ENV=development` umgestellt wird (dann sind die W010–W014-Checks
   inaktiv, was der ehrlichere Zustand für einen HTTP-only-Lokalbetrieb ist).
5. **`SECURITY_STRICT_PRODUCTION_CHECKS=True`** für das echte
   Produktionsdeployment setzen, sobald TLS-Terminierung und echte Origins
   konfiguriert sind — damit die Warnungen zu Startfehlern werden.
6. **Pepper-Rollout abschließen:** verbleibende `sha256:`-Alt-Keys identifizieren
   und Clients schrittweise auf `sha256p1:`-Keys umstellen (§4.3).
