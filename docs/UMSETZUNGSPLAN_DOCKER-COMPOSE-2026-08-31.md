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

### F — Honcho-Compose-Profile (`feat/honcho-compose-profile`)

RFC-Punkte: #5, #10, #11 (stark reduziert — UI und ENV-Grundgerüst existieren bereits)

- [ ] `honcho`, `honcho-postgres`, `honcho-redis` als Services in `docker-compose.yml`, alle mit `profiles: ["honcho"]`
- [ ] Default-Verhalten (`docker compose up`) bleibt ohne Honcho — `MEMORY_BACKEND=pgvector` bleibt Default
- [ ] `docker compose --profile honcho up` startet den Honcho-Stack zusätzlich mit
- [ ] Envs (`HONCHO_DB_PASSWORD`, Embedding-/LLM-Pinning) sind in `.env.example` bereits vorbereitet — nur an den neuen Compose-Service anbinden
- [ ] Kein neuer UI-Code nötig — `MemorySystemSettingsSection.tsx` deckt Backend-Auswahl und Verbindungsstatus bereits ab; nur End-to-End-Test der Verbindung (bundled und extern gehostet)

---

## Offene Punkte / bewusst nicht übernommen

- **RFC #14** (App-User muss Superuser für RLS sein): verworfen, siehe Ist-Stand-Check. Architektur ist korrekt so wie sie ist.
- **RFC #15** (Auto-Gen `FIELD_ENCRYPTION_KEY` in Datei): abgelehnt zugunsten von Sub-Projekt C (Pflicht bleibt, nur besser dokumentiert).

## Nächster Schritt

Start mit Sub-Projekt A (Compose-Kern) nach Freigabe.
