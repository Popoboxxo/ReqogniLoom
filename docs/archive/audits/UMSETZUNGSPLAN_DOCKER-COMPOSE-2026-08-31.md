# Umsetzungsplan: Docker-Compose-Optimierung & Backup-Integration

**Datum:** 2026-08-31
**Ausgangspunkt:** GitHub Issue [#792](https://github.com/Popoboxxo/ReqogniLoom/issues/792) — "[RFC] System-Wide Improvements: Deployment, Security, Operations & DX"
**Auslöser:** Produktions-Incident vom 2026-08-31 (QS/PROD-Port-Verwechslung, Datenverlust). RFC wurde von einer fremden KI verfasst und enthält teils veraltete/falsche Annahmen über den Ist-Stand — siehe Abschnitt "Ist-Stand-Check" unten.
**Prozess:** Kompakte Task-Liste je Sub-Projekt (kein formales Spec-Dokument), abgestimmt mit dem Projektverantwortlichen per Brainstorming-Dialog. Passt zum DoD-Preset `rapid-prototyping` dieses Projekts.
**Priorität lt. Nutzer:** Backup, Named Volumes, saubere Env-Handhabung bei Neuinstallation, Admin-User/Passwort via ENV. Named Volumes und Admin-Creds sind bereits erledigt (siehe unten) — Fokus liegt daher auf Backup-Härtung und Install-Sauberkeit.
**Best-Practice-Check (2026-08-31):** Plan gegen aktuelle Docker-Compose-Best-Practices per Web-Recherche geprüft, auf expliziten Nutzerwunsch ("so simpel wie möglich"). Ergebnis: YAML-Anchors und `profiles` für optionale Services sind der offiziell dokumentierte Weg (docs.docker.com/reference/compose-file/fragments/) und bleiben wie geplant. Ein Punkt aus dem RFC war falsch und wurde korrigiert — siehe Sub-Projekt A.
**Zweiter Review-Pass (2026-08-31):** Vollständiger Plan-Review durchgeführt. Zwei Logikfehler gefunden und korrigiert (Override-Warnung und Pre-Wipe-Hook waren am falschen Ort/technisch nicht umsetzbar wie ursprünglich formuliert — beide aus dem RFC-Snippet unkritisch übernommen), zwei Risiken entschärft (zu breiter `x-django-env`-Anchor hätte DB-Rollen-Verwechslung ermöglichen können; ein einzelner Healthcheck-Anchor passt nicht auf alle Services, da zwei unterschiedliche Werte-Gruppen existieren), ein zusätzlicher struktureller Fix ergänzt (Image-Version als eine zentrale Variable statt 5x hardcodiert — behebt die Drift-Ursache, nicht nur den aktuellen Wert).

---

## Ist-Stand-Check (vor Planung verifiziert)

| RFC-Punkt | Behauptung der fremden KI | Tatsächlicher Ist-Stand | Bewertung |
|---|---|---|---|
| Named Volumes | (implizit fehlend) | 3 Named Volumes vorhanden: `postgres_data`, `postgres_backup_data`, `backend_dr_backups` | ✅ bereits erledigt |
| #9 Admin-Creds via ENV | "muss manuell erstellt werden" | `SYSTEM_ADMIN_USERNAME`/`_EMAIL`/`_PASSWORD` bereits ENV-basiert, idempotent (create-only) via `post_migrate`-Receiver (`backend/application/self_init.py`) | ✅ bereits erledigt |
| #3 Backup | "Backup ist over-engineered, kein Django-Command" | Backup läuft bereits als Sidecar (`postgres-backup`) mit `backend/scripts/backup_postgres.sh`, Retention, gzip-Dump. Funktioniert, ist aber nicht verifiziert/alarmiert. | 🟡 teilweise — härten statt neu bauen |
| #6 `.env.example` | "fehlt komplett" | Existiert bereits, 300+ Zeilen, gut kommentiert | 🟡 teilweise — Lücken schließen |
| #4 Frontend tmpfs/user:root | "muss manuell konfiguriert werden" | Bereits Default in `docker-compose.yml` (non-root Image, `tmpfs` gesetzt) | ✅ bereits erledigt |
| #14 RLS: App-User muss Superuser sein | "RLS blockiert Non-Superuser" | Falsch. `DB_APP_USER` ist bewusst `NOSUPERUSER` (Migration `0048_app_role.py`, ADR-03). RLS ist genau so konzipiert, dass es *ohne* Superuser funktioniert. | ❌ verworfen — RFC irrt |
| Compose-Image-Tags | (nicht erwähnt) | `docker-compose.yml` zeigt `1.7.0`, aktueller Stand ist `1.8.0-beta.5` | 🐛 echter Bug, on top gefunden |
| #5 Honcho Single-Stack | "muss gemergt werden" | ENV-Variablen (`MEMORY_BACKEND`, `HONCHO_BASE_URL`, `HONCHO_API_KEY`) bereits vorbereitet. UI zur Konfiguration/Anzeige (`MemorySystemSettingsSection.tsx`) existiert bereits vollständig. Es fehlt nur die optionale Compose-Einbindung des Honcho-Service selbst. | 🟡 teilweise — nur Compose-Wiring fehlt |
| #15 FIELD_ENCRYPTION_KEY Auto-Gen | "muss automatisch generiert und in Datei persistiert werden" | Aktuell Pflichtfeld ohne Default (`config("FIELD_ENCRYPTION_KEY")`, crasht ohne). Auto-Gen + Datei-Persistenz ist riskant: Volume-Verlust = Daten dauerhaft unrettbar verschlüsselt. **Entscheidung des Nutzers: Pflicht bleibt, nur besser dokumentiert/generiert bei Erstsetup.** | 🔴 bewusst nicht wie RFC vorgeschlagen umgesetzt |

Reale, ungeprüfte Duplikation bestätigt: `backend`, `celery`, `celery-beat` teilen sich fast identische `environment`-Blöcke (~20 Zeilen je Service) — YAML-Anchors sind hier ein echter Gewinn.

## Live-Validierung 2026-09-01 (QS-Fresh-Deploy mit Honcho+Ollama)

Externes Feedback nach einem echten Fresh-Deploy (alle Volumes weg, v1.8.0-beta.5, inkl. Honcho + lokal erreichbarem Ollama) gegen den Plan A–F geprüft. Kernaussage: **Plan ist nach dem 2. Review-Pass korrekt** — beide dort gefundenen Logikfehler (Override-Warnung, Pre-Wipe-Hook) hätten live tatsächlich wieder zugeschlagen, wenn sie nicht vorher korrigiert worden wären. Zwei Punkte mussten trotzdem nachgezogen werden:

| Sub-Projekt | Live-Befund | Konsequenz |
|---|---|---|
| A | Image-Tag-Drift real aufgetreten (5x manuell gepatcht) | Bestätigt `REQOGNILOOM_VERSION`-Fix |
| A | DB-Rollen-Footgun nicht getroffen, aber Risiko real bestätigt | Bestätigt 2-Anchor-Trennung |
| A | Migrate-als-Service verhinderte unklaren Honcho-Dimension-Fehler | Bestätigt Best-Practice-Korrektur |
| A | **Memory-Limits zu knapp:** Backend 512M → 99,8 % + Worker-SIGKILL, Celery 384M → 96 %, Beat 256M → 99,8 %. Stabil erst bei Backend 1G / Celery 768M / Beat 512M | 🆕 Neue Aufgabe in A (siehe unten) |
| A | Frontend brauchte live `user: root` + `tmpfs /var/run` + expliziten `command`, sonst blieb Container in `Created` (kein Start) — widerspricht dem SA-48-Kommentar im File ("non-root ist Default") | 🆕 Neue Aufgabe in A: Ursache klären statt Root-Workaround blind übernehmen |
| B | Override-Warnung gehört in `setup.sh`, nicht Entrypoint | Bestätigt A→B-Verschiebung; Override lag live wieder da und verursachte `exit 127 npm: not found` |
| B | `.env` ohne `setup.sh` braucht manuelles Nachpatchen (`DJANGO_ENV`, `CORS_ALLOWED_ORIGINS`, Ollama-IP) | Bestätigt Lücke, keine Planänderung nötig |
| C | Kein Auto-Gen, Pflicht blieb Pflicht | Bestätigt Nutzer-Entscheidung |
| D | Sidecar läuft, aber Verify/Alert/`safe-down.sh` fehlen weiterhin; `down -v` weiterhin ungeschützt | Bestätigt offenen Stand, keine Planänderung nötig |
| E | Healthcheck hat live einen Backend-OOM sichtbar gemacht und das Frontend-Gate korrekt blockiert (statt 502) | Bestätigt Kritikalität, keine Planänderung nötig |
| F | **Unterschätzt.** Siehe eigener Abschnitt unten | 🔴 Sub-Projekt F wird neu geschnitten |

**Neue, bislang nicht im Plan erfasste Erkenntnisse:**
- Bei 2 Instanzen (QS+PROD) + Honcho (3 weitere Container) auf einem Host mit 5,8 GB RAM + 8 GB Swap ist der Spielraum knapp — die Systemanforderungen-Tabelle (Sub-Projekt B) muss die angehobenen Limits + Honcho einrechnen, nicht nur die alten Werte übernehmen.
- Ollama-Erreichbarkeit ist netzwerkspezifisch: eine `x.x.x.255`-Adresse ist je nach Subnetzmaske oft die Broadcast-Adresse und nicht erreichbar. Muss pro Umgebung verifiziert werden (z. B. `curl http://<ip>:11434/api/tags`), nicht blind aus einer Dokumentationszeile übernommen werden.
- Es gibt noch keinen einheitlichen Start-Befehl: aktuell `docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.honcho.yml up -d`, im ursprünglichen Plan F war von `docker compose --profile honcho up` die Rede. Muss VOR der Umsetzung von F entschieden werden (siehe dort).

## Vergleich mit "cleaner" Compose-Beispielen (paperless-ngx)

Nutzer brachte paperless-ngx' `docker-compose.yml` als Referenz für "so simpel wie möglich". Geprüft, was übertragbar ist und was nicht:

- **Nicht übertragbar (bewusster Unterschied, nicht "unclean"):** `deploy.resources.limits` (Memory-Limits) — bei paperless nicht vorhanden, bei ReqogniLoom nach echtem OOM-Incident eingebaut; Healthchecks mit `condition: service_healthy` — paperless nutzt nur `depends_on:` als reine Start-Reihenfolge ohne Bereitschaftsprüfung, ReqogniLoom braucht das (z. B. Celery-Beat-Restart-Loop #171 wurde nur dank Healthcheck sichtbar); dedizierter `migrate`-Service — siehe Korrektur oben, bleibt aus Best-Practice-Gründen.
- **Übertragbar, in den Plan aufgenommen:** `x-healthcheck-defaults`-Anchor (s. o.) gegen die Wiederholung von `interval`/`timeout`/`retries`/`start_period`.
- **Geprüft und bewusst NICHT übernommen:** Auslagern der inline WHY-Kommentare (CVE-Fixes, Incident-Historie, REQ-IDs) nach `docs/` mit nur Kurz-Pointern im Compose. Nutzer-Entscheidung: Kommentare bleiben inline — verhindert, dass ein Fix ohne sichtbaren Grund versehentlich rückgängig gemacht wird (genau das Incident-Muster aus Issue #792).

---

## Sub-Projekte

Der volle Umfang aus Issue #792 (18 Einzelpunkte) wurde auf Wunsch des Nutzers vollständig übernommen, aber in sechs unabhängig umsetzbare, sequentiell abzuarbeitende Sub-Projekte zerlegt. Jedes Sub-Projekt bekommt einen eigenen Branch und einen eigenen PR (Conventional Commits, `feat/`, `fix/`, `refactor/`, `chore/`, `docs/` je nach Art — nie direkt auf `main`, siehe `.claude/rules/branch-guard.md`). Git-Mutationen (Branch, Commit, Push) laufen über den `git`-Agent, nicht direkt im Main-Chat.

**Reihenfolge:** A → B → C → D → E → F (vom Nutzer bestätigt).

### A — Compose-Kern (`refactor/compose-cleanup`)

RFC-Punkte: #1, #2 (revidiert), #4 (bereits erledigt), #18, + Image-Tag-Bugfix

> **Korrektur nach Best-Practice-Check:** RFC-Punkt #2 (Migrate → Entrypoint) ist **kein** Best Practice, sondern erhöht das Risiko. Mehrere unabhängige Quellen (u. a. pythonspeed.com "Decoupling database migrations from server startup") empfehlen einen dedizierten Migrate-Service mit `condition: service_completed_successfully`, gerade um Race Conditions bei mehreren Replicas zu vermeiden. Das bestehende Setup macht das schon richtig — inkl. sauberem, einmaligem Admin-Self-Init. **Migrate bleibt eigener Service.** Nur die Duplikation wird per Anchor entfernt.

- [ ] `x-logging`-Anchor: einheitlicher `json-file`-Logging-Block für alle 8 Services
- [ ] `x-common-env`-Anchor: NUR was `backend`/`celery`/`celery-beat`/`migrate` wirklich alle vier teilen (`DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DEBUG`, `DB_NAME`, `DB_HOST`, `DB_PORT`). **Nicht** `DB_USER`/`DB_PASSWORD` mit reinnehmen — siehe Footgun-Notiz unten.
- [ ] `x-app-role-env`-Anchor: zweiter, engerer Anchor NUR für `backend`/`celery`/`celery-beat` (die drei, NICHT `migrate`) mit `DB_USER: ${DB_APP_USER:-reqogniloom_app}`, `DB_PASSWORD: ${DB_APP_PASSWORD}`, `REDIS_PASSWORD`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `LLM_*`-Block
  - ⚠️ **Footgun-Warnung:** `migrate` braucht zwingend `DB_USER: ${DB_USER:-reqogniloom}` (Superuser für DDL/RLS-Rollen-Setup), die App-Services brauchen `DB_APP_USER` (RLS-Rolle). Ein einzelner, zu breiter Anchor über alle vier Services mit einem DB_USER-Default ist gefährlich — wer beim Bauen vergisst, `migrate` explizit zu überschreiben, lässt die Migration mit falscher Rolle laufen. Deshalb zwei getrennte Anchors, `migrate` bekommt `DB_USER`/`DB_APP_USER`/`DB_APP_PASSWORD`/`DB_STATEMENT_TIMEOUT_MS`/`SYSTEM_ADMIN_*` weiterhin lokal, ungeankert.
- [ ] `x-healthcheck-infra`-Anchor: `interval: 10s`/`timeout: 5s`/`retries: 5`/`start_period: 30s` für `postgres`+`redis` (identische Werte)
- [ ] `x-healthcheck-app`-Anchor: `interval: 30s`/`timeout: 10s`/`retries: 3`/`start_period: 40s` für `backend`+`celery`+`celery-beat`+`frontend` (identische Werte, andere Gruppe als infra) — jeweils nur `test:` bleibt lokal
- [ ] `REQOGNILOOM_VERSION`-Variable statt 5x hardcodierter Image-Tag: `image: ghcr.io/popoboxxo/reqogniloom-backend:${REQOGNILOOM_VERSION:-1.8.0-beta.5}` (analog `-frontend`) in `backend`, `migrate`, `celery`, `celery-beat`, `frontend` — behebt strukturell genau den Drift-Bug, der `1.7.0` vs. `1.8.0-beta.5` verursacht hat, nicht nur einmalig den Wert korrigieren
- [ ] `migrate`-Service **bleibt bestehen** (Best Practice, siehe oben) — keine Änderung an der Architektur, nur Anchor-Anwendung
- [ ] 🆕 **Memory-Limits anheben** (Live-Validierung 2026-09-01): `backend`/`migrate` 512M→1G, `celery` 384M→768M, `celery-beat` 256M→512M. Alte Werte liefen live in OOM/SIGKILL. Diese Werte stehen bereits als unkommitteter Hotfix im Arbeitsverzeichnis (`docker-compose.yml`) — beim Umsetzen von A übernehmen, nicht die alten Werte aus dem Git-Stand neu ansetzen. System-Requirements-Tabelle in B entsprechend mit den neuen Werten befüllen.
- [ ] 🆕 **Frontend `user: root`-Ursache klären** (Live-Validierung 2026-09-01): Container blieb ohne `user: root` + `tmpfs /var/run` + expliziten `command` in `Created` hängen — widerspricht dem SA-48-Kommentar im File ("non-root ist bereits Default, funktioniert"). Vor der Umsetzung klären: Regression im Frontend-Image seit dem SA-48-Fix, oder umgebungsspezifisch? Wenn Root wirklich nötig ist: Ursache im `frontend/Dockerfile` beheben (korrekte Verzeichnis-Permissions für den nginx-User), NICHT den Root-Workaround unkommentiert übernehmen — sonst wird die SA-48-Härtung stillschweigend wieder aufgehoben.
- [ ] ~~`docker-compose.override.yml`-Warnung im Backend-Entrypoint~~ **falscher Ort, verschoben nach Sub-Projekt B.** Der Container sieht die host-seitige Override-Datei nie (Compose liest sie vor dem Containerstart, sie wird nirgends gemountet) — ein Entrypoint-Check darin ist wirkungslos. Muss host-seitig in `setup.sh` geprüft werden.
- [ ] Verifikation: `docker compose config` validiert fehlerfrei, Stack hochfahren, alle Healthchecks grün, Migration läuft weiterhin genau einmal beim Deploy über den dedizierten Service

### B — Install-Sauberkeit (`chore/setup-script`)

RFC-Punkte: #6 (Rest), #7, #8, #12

- [ ] `setup.sh`: `.env` aus `.env.example` erzeugen (falls nicht vorhanden), Secrets generieren (`SECRET_KEY`, `AUTH_JWT_SECRET`, `DB_PASSWORD`, `DB_APP_PASSWORD`, `API_KEY_PEPPER`), Named Volumes anlegen, Postgres hochfahren + warten, Migration anstoßen
- [ ] `docker-compose.override.yml`-Warnung: **hierher verschoben aus Sub-Projekt A** (Entrypoint im Container kann die host-seitige Datei nicht sehen). `setup.sh` prüft vor dem `docker compose up`, ob die Datei existiert, und gibt eine deutliche Warnung aus (kein automatisches Verschieben — nur Hinweis)
- [ ] Port-Check vor dem Start: prüft `BACKEND_PORT`/`FRONTEND_PORT` auf Kollisionen, bricht mit klarer Fehlermeldung ab statt kryptischem Docker-Fehler
- [ ] `.env.example`: Diff gegen tatsächlich in `settings.py` gelesene `config(...)`-Variablen, fehlende Variablen ergänzen
- [ ] README: Systemanforderungen-Tabelle (Memory/CPU je Service) — Werte aus den bereits in `docker-compose.yml` gesetzten `deploy.resources.limits` übernehmen, nicht neu erfinden

### C — Secrets-Bootstrap (`docs/encryption-key-warning`)

RFC-Punkt: #15 (abgewandelt — siehe Ist-Stand-Check)

- [ ] Keine Auto-Generierung mit Datei-Persistenz (Nutzer-Entscheidung, Datenverlustrisiko)
- [ ] `setup.sh` (Sub-Projekt B) generiert `FIELD_ENCRYPTION_KEY` einmalig beim allerersten `.env`-Erzeugen und gibt einen unübersehbaren Warnhinweis aus ("Sichere diesen Key außerhalb des Volumes — ohne ihn sind verschlüsselte Felder für immer unlesbar")
- [ ] README/CLAUDE.md: Abschnitt "Was passiert, wenn `FIELD_ENCRYPTION_KEY` verloren geht" (Konsequenzen, Backup-Empfehlung)

### D — Backup-Härtung (`fix/backup-hardening`)

RFC-Punkte: #3 (abgewandelt), #13, #17

- [ ] `backup_postgres.sh`: Verify-Step nach jedem Dump (z. B. `gzip -t` auf das Ergebnis)
- [ ] Fehlschlag beim Dump oder Verify → sichtbarer Exit-Code ungleich 0 in `docker logs`, optionaler Alert-Hook (Webhook, falls `BACKUP_ALERT_WEBHOOK_URL` gesetzt ist)
- [ ] Pre-Wipe-Snapshot-Helper: Docker Compose hat **keinen** Pre-Hook für `down -v` — "automatisch" ist nicht möglich, nur als Wrapper-Skript (`scripts/safe-down.sh`), das erst snapshotted und dann `docker compose down -v` aufruft. Ersetzt nicht den rohen Befehl, ergänzt ihn nur — README muss klarstellen, dass der rohe `docker compose down -v` weiterhin ungeschützt ist
- [ ] Django-Admin-Action "Backup erstellen" — nutzt den bestehenden Backup-Mechanismus, kein neuer Codepfad
- [ ] Restore-Doku im README: Schritt-für-Schritt-Anleitung (`gunzip -c ... | psql ...`, existiert als Kommentar in `docker-compose.yml`, muss ins README)

### E — Healthcheck-Erweiterung (`feat/healthcheck-db-redis`)

RFC-Punkt: #16 (schlanker als vorgeschlagen — kein neues Package, da unnötige Abhängigkeit)

- [ ] `/health/`-Endpoint erweitern: zusätzlich zu "Prozess läuft" auch DB-Check (`SELECT 1`) und Redis-Check (`PING`)
- [ ] Bestehender Compose-Healthcheck (`curl -f http://localhost:8000/health/`) bleibt unverändert, wird aber aussagekräftiger

### F — Honcho-Härtung (`feat/honcho-hardening`)

RFC-Punkte: #5, #10, #11 — **Neu geschnitten nach Live-Validierung 2026-09-01, ursprüngliche Annahme "nur Wiring fehlt" war falsch.**

> **Korrektur der Ausgangslage:** Anders als ursprünglich angenommen existiert `docker-compose.honcho.yml` bereits als eigene, ausgereifte Overlay-Datei — inkl. `honcho-postgres`, `honcho-redis`, dediziertem `honcho-migrate` (Alembic) und bereits dokumentiertem Dimension-Pitfall-Kommentar. Es fehlt **nicht** die Compose-Einbindung, sondern Betriebssicherheit rund um Embedding-Dimensionen und Ollama-Erreichbarkeit. UI (`MemorySystemSettingsSection.tsx`) und ENV-Grundgerüst waren korrekt bereits vorhanden.

- [ ] **Entscheidung vor Umsetzung nötig:** bestehendes Overlay-Datei-Muster (`-f docker-compose.yml -f docker-compose.honcho.yml`) behalten, oder auf `profiles:` innerhalb einer Datei umstellen? Overlay-Datei ist bereits erprobt, dokumentiert und erfüllt "kostet nichts, wenn nicht eingebunden" schon — eine Umstellung auf `profiles:` wäre reiner Umbau ohne funktionalen Zusatznutzen und mit Migrationsrisiko für alle, die den Overlay-Befehl schon nutzen. **Empfehlung: Overlay-Datei behalten**, nur den einen offiziellen Start-Befehl dokumentieren (README/CLAUDE.md) statt zwei parallele Muster zu haben.
- [ ] **Embedding-Dimension-Sicherung:** Live bestätigt: Wird `EMBEDDING_VECTOR_DIMENSIONS` geändert, nachdem `honcho-migrate` bereits gegen ein bestehendes Volume gelaufen ist, bleibt das DB-Schema auf der alten Dimension (z. B. `vector(1536)`) — der Fehler zeigt sich erst spät als `StartupValidationError` im `honcho`-Service, nicht schon bei `honcho-migrate`. Baue eine Prüfung (Shell-Skript oder zusätzlicher `honcho-migrate`-Schritt), die die tatsächliche Spalten-Dimension gegen `EMBEDDING_VECTOR_DIMENSIONS` vergleicht und bei Mismatch **sofort und verständlich** abbricht — mit der Handlungsanweisung (frisches Volume ODER `ALTER TABLE ... TYPE vector(n)` + `REINDEX`) direkt in der Fehlermeldung, nicht erst in Doku suchen müssen.
- [ ] **Ollama-Erreichbarkeit dokumentieren, ohne konkrete IP festzuschreiben:** `.env.example`/`setup.sh` sollen einen Hinweis + Check-Befehl bekommen (z. B. `curl http://<eure-ollama-host>:11434/api/tags`), inkl. Warnung, dass eine auf `.255` endende Adresse je nach Subnetzmaske die Broadcast-Adresse sein kann und nicht erreichbar ist. Keine echten internen IPs in Doku/Compose committen.
- [ ] Envs (`HONCHO_DB_PASSWORD`, Embedding-/LLM-Pinning) sind in `.env.example` bereits vorbereitet — keine Änderung nötig
- [ ] Kein neuer UI-Code nötig — `MemorySystemSettingsSection.tsx` deckt Backend-Auswahl und Verbindungsstatus bereits ab; nur End-to-End-Test der Verbindung (bundled und extern gehostet), inkl. Dimension-Mismatch-Fall

---

## Update 2026-09-01: Reduktion auf minimal + full (supersediert Teile von A/F)

Nutzerentscheidung, unabhängig vom bisherigen Sub-Projekt-Zuschnitt: alle empfohlenen Compose-Dateien auf **zwei** reduzieren — `docker-compose.yml` (full) und `docker-compose.minimal.yml`. `docker-compose.override.yml` (lokale Dev-Overrides/Secrets) und `docker-compose.test.yml` (CI) bleiben bewusst separat (Standard-Compose-Mechanismus bzw. eigener CI-Zweck, kein Teil der "wie viele Deployment-Varianten"-Frage).

**Umgesetzt:**
- `docker-compose.honcho.yml` entfernt, Inhalt 1:1 in `docker-compose.yml` verschoben, alle vier Services (`honcho-postgres`, `honcho-redis`, `honcho-migrate`, `honcho`) mit `profiles: ["honcho"]` markiert. **Supersediert Sub-Projekt F, Punkt 1** ("Empfehlung: Overlay-Datei behalten") — die Live-Validierung fand das noch richtig, der explizite Nutzerwunsch heute ("eine minimal + eine full Datei") übersteuert das bewusst. Funktional unverändert: `docker compose --profile honcho up -d` startet exakt das, was vorher `-f docker-compose.yml -f docker-compose.honcho.yml` startete — kostet nichts ohne den Flag.
- `docker-compose.minimal.yml` neu angelegt: `postgres`, `redis`, `backend`, `migrate`, `frontend` — kein Celery, kein Backup-Sidecar, kein Honcho. Redis bleibt drin (harte Abhängigkeit über Djangos `CACHES`-Backend, siehe `reqogniloom/settings.py:792`), auch wenn primär als Celery-Broker beschrieben.
- Image-Tag-Drift-Bug (Sub-Projekt A, dort noch offen) nebenbei mitgefixt, weil ohnehin jede Service-Zeile neu geschrieben wurde: `REQOGNILOOM_VERSION`-Variable (Default `1.8.0-beta.5`) statt 5x hardcodiertem `1.7.0`, in beiden Dateien.
- `docker compose config` gegen beide Dateien (full, full+honcho-Profil, minimal) grün validiert.
- README, `docker-compose.override.example.yml` auf die neue Struktur aktualisiert.

**Bewusst NICHT mitgemacht** (bleibt Sub-Projekt A, eigener Scope/eigene Freigabe nötig):
- YAML-Anchors (`x-common-env`, `x-app-role-env`, `x-healthcheck-*`, `x-logging`)
- Memory-Limit-Anhebung aus der Live-Validierung (Backend 512M→1G etc.)
- Frontend-`user: root`-Ursachenklärung

**Gefunden, nicht behoben (out of scope):** `scripts/backup.sh` referenziert eine nicht existierende `docker-compose.backup.yml` (Stand 2026-07-14, Kommentar "Uses docker-compose.backup.yml service definition") — vermutlich Legacy aus der Zeit vor dem heutigen `postgres-backup`-Sidecar in `docker-compose.yml`, in keinem Makefile-Target aufgerufen. Kandidat für Cleanup, aber nicht Teil dieser Änderung.

---

## Update 2026-09-01 (Fortsetzung): Verzeichnis-Reorg (`deploy/` + `testing/`) und Erklärkommentare

Zweite Nutzeranforderung direkt im Anschluss an die minimal/full-Reduktion: die Compose-Dateien sollen an einer Stelle im Repo liegen, die ein Anwender sofort als "Deployment-Beispiele" erkennt; repo-interne Test-Composes sollen an einer offensichtlichen Testing-Stelle liegen, getrennt davon; die Beispiel-Deployment-Dateien sollen im README sauber benannt und verlinkt sein; und es soll einen Abschnitt geben, den ein AI-Agent lesen kann, falls jemand das System per KI deployen lässt.

**Umgesetzt:**
- Neues Verzeichnis `deploy/`: `docker-compose.yml` (full), `docker-compose.minimal.yml`, `docker-compose.override.yml`, `docker-compose.override.example.yml` — alle vier zusammen, da sie dieselbe Frage beantworten ("wie starte ich diesen Stack").
- Neues Verzeichnis `testing/`: `docker-compose.test.yml` — bewusst getrennt von `deploy/`, da es kein Deployment-File ist, sondern nur CI-/lokale Test-Container baut (`backend-test`/`frontend-test`).
- **Technischer Zwangspunkt:** sobald Compose-Dateien nicht mehr im Repo-Root liegen, braucht jeder direkte `docker compose`-Aufruf zusätzlich `--project-directory .` — sonst löst Compose `.env` und alle relativen Bind-Mounts (`./backend`, `./docker/postgres/initdb`, `./docs`) relativ zu `deploy/` statt zum Repo-Root auf. Verifiziert: `docker compose -f deploy/docker-compose.yml --project-directory . config` zeigt den Bind-Mount-Pfad korrekt auf dem Repo-Root, nicht auf `deploy/docker/...`. Zusatzeffekt: das automatische Override-Merging (`docker-compose.yml` + `docker-compose.override.yml` ohne `-f`) funktioniert nicht mehr, weil beide Dateien nicht mehr im selben Default-Suchpfad liegen und immer explizit per `-f` aufgerufen werden müssen.
- Makefile um `make up`/`make down` (Full-Stack + Dev-Override), `make minimal`/`make minimal-down`, `make honcho` (Honcho-Profil zusätzlich zum laufenden Dev-Stack) ergänzt, damit der Alltag trotz der zusätzlichen Flags ein kurzer Befehl bleibt. `scripts/build.sh`, `scripts/backup.sh`, `scripts/restore.sh` auf die neuen Pfade + `--project-directory .` aktualisiert.
- Neues `deploy/README.md`: kompaktes, unmissverständliches Deployment-Dokument mit Datei-Tabelle, der `--project-directory .`-Pflicht als eigenem Absatz, Schritt-für-Schritt-Sequenzen für full/minimal/honcho, und einem eigenen Abschnitt "For AI agents" mit maschinenlesbaren Canonical-Commands, Health-Check-URL und Fehlerfall-Anleitung.
- README.md verlinkt `deploy/README.md` direkt am Anfang von "How to Start"; die ausführliche menschenlesbare Anleitung bleibt zusätzlich als Langfassung erhalten (nur Pfad-/Befehlskorrekturen, keine inhaltliche Kürzung).
- Compose-Dateien selbst um Erklärkommentare ergänzt (Nutzerfrage: warum `${VAR:-default}`, warum Named Volumes vs. Bind-Mounts, warum `logging`-Block, warum das Redis-`if/else`-Command) — direkt in `deploy/docker-compose.yml`/`deploy/docker-compose.minimal.yml`, nicht nur in dieser Doku, damit sie beim Lesen der Datei selbst sichtbar sind.

**Bewusst NICHT angefasst:** archivierte/historische Docs (`docs/superpowers/plans/Archive/**`, `docs/reviews/**`, `docs/SYSTEMAUDIT_2026-08-18.md`, `docs/se/DEEP_SYSTEM_ANALYSIS.md`, `docs/REQUIREMENTS.md`) behalten ihre alten Pfad-Referenzen als Zeitpunkt-Dokumentation — analog zur Regel "alte Commits nie nachträglich rewriten".

**Nebenbei gefunden und korrigiert:** README.md (Schritt 2/5) und `deploy/README.md` behaupteten, `SYSTEM_ADMIN_PASSWORD` gehöre zu den Secrets, ohne die der Stack nicht startet. Stimmt nicht — gegen `backend/application/self_init.py` verifiziert: fehlt `SYSTEM_ADMIN_PASSWORD` auf einer frischen DB, wird die Admin-Provisionierung übersprungen (geloggt, nicht fatal), `migrate` läuft trotzdem durch. Nur `SECRET_KEY`/`AUTH_JWT_SECRET`/`FIELD_ENCRYPTION_KEY`/`DB_PASSWORD`/`DB_APP_PASSWORD` sind harte Pflichtfelder. Beide READMEs entsprechend präzisiert; zusätzlich ergänzt: Admin-Provisionierung ist create-only (Passwort-Änderung in `.env` wirkt nur beim allerersten Lauf gegen eine leere DB), und `.env`-Änderungen werden erst bei Container-Neuerstellung (`up -d`) übernommen, nicht bei `restart`.

## Update 2026-09-01 (3. Fortsetzung): deployment/ entfernt, BACKEND_PORT/FRONTEND_PORT nachgezogen, generierte Docs gefixt

Nutzerfrage "haben wir die README so optimiert, dass KIs alle Infos zum Deployment schnell finden?" deckte auf: ein bis dahin unbekanntes drittes Verzeichnis `deployment/` (GHCR-Pull-Compose seit 2026-07-26, Unraid-Community-Applications-Template seit 2026-07-19) existierte parallel zu `deploy/` — **nirgendwo in README.md oder CLAUDE.md verlinkt**, seit Juli unauffindbar. Zusätzlich echte Namenskollision: zwei inhaltlich unterschiedliche `docker-compose.minimal.yml` in `deploy/` vs. `deployment/`. `deployment/unraid/` war zuletzt heute (vor dieser Session) von echten IPs/Domain bereinigt worden — sah nach Live-Infrastruktur aus, war es laut Nutzer aber nicht mehr ("Unraid nutze ich nicht mehr fürs erste").

**Nutzerentscheidung:** komplettes `deployment/` (inkl. GHCR-Pull-Varianten und Unraid) löschen, alles auf `deploy/` konsolidieren — `deploy/docker-compose.yml` pullt ohnehin schon standardmäßig GHCR-Images, der Unterschied zur alten `ghcr.yml` war marginal.

**Beim Vergleich gefunden und mitgenommen:** `deployment/.env.example` hatte `BACKEND_PORT`/`FRONTEND_PORT` als Overrides, die in `deploy/` fehlten (Ports waren hardcoded `8001`/`5173`). Das ist genau die Fehlerklasse des Produktions-Incidents vom 2026-08-31, der diesen ganzen Plan ausgelöst hat (QS/PROD-Port-Verwechslung) — jetzt in `deploy/docker-compose.yml` + `deploy/docker-compose.minimal.yml` nachgezogen (`${BACKEND_PORT:-8001}`/`${FRONTEND_PORT:-5173}`), inkl. Doku in `.env.example`, `deploy/README.md`.

**Separater Fund währenddessen:** `CLAUDE.md`/`AGENTS.md`/`.gemini/GEMINI.md` (die von diesem Projekt selbst als "einzige Quelle für Agenten" deklarierten Dateien) waren seit der ersten Reorg-Runde veraltet (`docker-compose build`/`up` ohne `deploy/`-Pfad, kein Hinweis auf `deploy/README.md`). Ursache: `sync.py` (agent-meta-Submodul) crasht auf dieser Windows-Maschine mit einem echten Bug (`re.PatternError: bad escape \s`, Windows-Pfad-Backslashes in einem `re.sub`-Replacement-String) beim Opencode-Context-Sync — Feedback dazu eingereicht. Workaround: `.meta-config/project.yaml` (der einzige erlaubte Editier-Ort) korrekt gefixt, `CLAUDE.md`/`AGENTS.md`/`.gemini/GEMINI.md` manuell nachgezogen (Inhalt entspricht dem, was ein funktionierender Sync aus der jetzt korrekten `project.yaml` erzeugen würde — kein Drift, sobald der Sync-Bug behoben ist).

**Nebenbei korrigiert:** `docs/CODEBASE_OVERVIEW.md`s Deployment-Tabelle zeigte noch auf `deployment/`; `.github/workflows/docker-publish.yml`-Kommentar zeigte auf Root-`docker-compose.yml`.

## Offene Punkte / bewusst nicht übernommen

- **RFC #14** (App-User muss Superuser für RLS sein): verworfen, siehe Ist-Stand-Check. Architektur ist korrekt so wie sie ist.
- **RFC #15** (Auto-Gen `FIELD_ENCRYPTION_KEY` in Datei): abgelehnt zugunsten von Sub-Projekt C (Pflicht bleibt, nur besser dokumentiert).

## Nächster Schritt

Start mit Sub-Projekt A (Compose-Kern) nach Freigabe.
